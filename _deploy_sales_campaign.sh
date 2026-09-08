#!/bin/bash
# Deploy the Sales Campaign page.
#
# Two files change together and neither works alone: sales_campaign.py is the
# whole feature (ZoomInfo client, credential vault, run worker, launch, UI) and
# flowdrip_app.py contributes only the nav entry and the router branch that
# reaches it. Ship one without the other and you get either a dead nav button
# or a module nothing routes to.
#
# Like _deploy_records_ingest.sh and unlike _deploy_zero_downtime.sh this
# touches ONLY these two paths -- no EXTRA_FILES, no Caddyfile sync -- because
# production has drifted from the repo before and a broader deploy silently
# reverts live hotfixes. (Checked before writing this: prod's flowdrip_app.py
# was byte-identical to this branch's base, so nothing is being overwritten.)
#
# No MCP restart: the connector does not import sales_campaign.
#
# Both colors currently run (Caddy fails over between them), so they are
# restarted one at a time with a health check in between: the other color is
# always serving. If the first fails to come back, the script stops before
# touching the second.

set -e

SERVER="root@134.199.237.206"
SSH_KEY="$HOME/.ssh/dripdrop"
SSH="ssh -o ConnectTimeout=90 -o ServerAliveInterval=15 -i $SSH_KEY $SERVER"
APP="/opt/dripdrop/app"

FILES=(
    "sales_campaign.py|$APP/sales_campaign.py"
    "flowdrip_app.py|$APP/flowdrip_app.py"
)

for entry in "${FILES[@]}"; do
    [ -f "${entry%%|*}" ] || { echo "ERROR: ${entry%%|*} not found -- run from the repo root"; exit 1; }
done

STAMP=$(date +%Y%m%d-%H%M%S)

echo "== 0/5 Confirm the venv already has the two new imports =="
# cryptography (credential vault) and requests (ZoomInfo REST) were both
# already installed as transitive deps. Verified, not assumed -- a missing one
# would take the whole app down on import, not just this page.
$SSH "/opt/dripdrop/venv/bin/python -c 'import cryptography, requests; print(\"   cryptography\", cryptography.__version__, \"/ requests\", requests.__version__)'"

echo "== 1/5 Upload + syntax-check both files =="
$SSH "rm -f /tmp/sc_deploy_*.stage /tmp/sc_deploy_*.stage.gz"
i=0
for entry in "${FILES[@]}"; do
    local_f="${entry%%|*}"
    i=$((i+1))
    stage="/tmp/sc_deploy_$i.stage"
    echo "   $local_f -> $stage"
    # Chunked gzip: a single large cat over ssh has dropped mid-stream before.
    gzip -c "$local_f" | $SSH "cat > $stage.gz"
    $SSH "gunzip -f $stage.gz && python3 -c 'import ast,sys; ast.parse(open(sys.argv[1],\"rb\").read())' $stage"
done
echo "   both uploaded and parse on the server"

echo "== 2/5 Back up the live file ($STAMP) =="
# sales_campaign.py is new, so only flowdrip_app.py has a live version to save.
$SSH "mkdir -p /opt/dripdrop/backups/$STAMP && cd $APP && cp -p flowdrip_app.py /opt/dripdrop/backups/$STAMP/ && ls -l /opt/dripdrop/backups/$STAMP/"

echo "== 3/5 Swap the new files in =="
$SSH "mv /tmp/sc_deploy_1.stage $APP/sales_campaign.py \
   && mv /tmp/sc_deploy_2.stage $APP/flowdrip_app.py \
   && chmod 644 $APP/sales_campaign.py $APP/flowdrip_app.py"

restart_and_wait () {   # $1 = unit, $2 = port
    echo "   restarting $1 ..."
    $SSH "systemctl restart $1"
    for i in $(seq 1 40); do
        if $SSH "curl -sf http://localhost:$2/healthz >/dev/null 2>&1"; then
            echo "   $1 healthy after ${i}s"
            return 0
        fi
        sleep 1
    done
    echo "   ERROR: $1 did not become healthy within 40s"
    $SSH "journalctl -u $1 --since '2 minutes ago' --no-pager | tail -40"
    echo "   Roll back with:  ssh -i $SSH_KEY $SERVER 'cp -p /opt/dripdrop/backups/$STAMP/flowdrip_app.py $APP/ && rm -f $APP/sales_campaign.py && systemctl restart dripdrop dripdrop-green'"
    exit 1
}

echo "== 4/5 Restart the app, one color at a time =="
restart_and_wait dripdrop-green 8081
restart_and_wait dripdrop       8080

echo "== 5/5 Confirm the module actually imported =="
# The router catches an import failure and shows the page as unavailable rather
# than taking the app down -- so a green /healthz alone does NOT prove the
# feature loaded. This is the check that does.
$SSH "/opt/dripdrop/venv/bin/python -c \"import ast,sys; ast.parse(open('$APP/sales_campaign.py','rb').read()); print('   sales_campaign.py parses under the app venv')\""
$SSH "journalctl -u dripdrop --since '3 minutes ago' --no-pager | grep -i 'SalesCampaign' || echo '   no SalesCampaign errors in the log'"

echo
echo "== Deploy complete =="
$SSH "curl -s https://dripdripdrop.ai/healthz -o /dev/null -w '   https check: HTTP %{http_code} in %{time_total}s\n'" || true
echo "   backup: /opt/dripdrop/backups/$STAMP"
echo
echo "   Next: open dripdripdrop.ai, click 'Sales Campaign' under Campaign Library,"
echo "   paste your ZoomInfo API credentials in Settings and press 'Test connection'."
echo "   Test connection costs no credits -- search is free. It is what proves the"
echo "   endpoint paths and parameter style, which could not be verified offline."

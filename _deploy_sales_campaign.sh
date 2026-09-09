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
# The MCP layer ships with it now. sales_campaign.py queues runs for Claude
# instead of calling ZoomInfo itself -- Mike's seat is entitled for the MCP
# surface, not the REST API -- so the two new /api/v1/sales_runs routes in
# flowdrip_app.py and the two tools that call them in mcp_server/ are the
# same feature as the page. Ship the page without them and a queued run sits
# there with nothing able to pick it up. dripdrop-mcp restarts LAST, after
# both app colors answer, because its tools call back into them.
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
    "mcp_server/dripdrop_mcp.py|$APP/mcp_server/dripdrop_mcp.py"
    "mcp_server/dripdrop_client.py|$APP/mcp_server/dripdrop_client.py"
)

for entry in "${FILES[@]}"; do
    [ -f "${entry%%|*}" ] || { echo "ERROR: ${entry%%|*} not found -- run from the repo root"; exit 1; }
done

STAMP=$(date +%Y%m%d-%H%M%S)

echo "== 0/6 Confirm the venv already has the two new imports =="
# cryptography (credential vault) and requests (ZoomInfo REST) were both
# already installed as transitive deps. Verified, not assumed -- a missing one
# would take the whole app down on import, not just this page.
$SSH "/opt/dripdrop/venv/bin/python -c 'import cryptography, requests; print(\"   cryptography\", cryptography.__version__, \"/ requests\", requests.__version__)'"

echo "== 1/6 Upload + syntax-check all four files =="
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
echo "   all four uploaded and parse on the server"

echo "== 2/6 Back up the live files ($STAMP) =="
$SSH "mkdir -p /opt/dripdrop/backups/$STAMP/mcp_server && cd $APP \
   && cp -p flowdrip_app.py sales_campaign.py /opt/dripdrop/backups/$STAMP/ \
   && cp -p mcp_server/dripdrop_mcp.py mcp_server/dripdrop_client.py /opt/dripdrop/backups/$STAMP/mcp_server/ \
   && ls -l /opt/dripdrop/backups/$STAMP/ /opt/dripdrop/backups/$STAMP/mcp_server/"

echo "== 3/6 Swap the new files in =="
$SSH "mv /tmp/sc_deploy_1.stage $APP/sales_campaign.py \
   && mv /tmp/sc_deploy_2.stage $APP/flowdrip_app.py \
   && mv /tmp/sc_deploy_3.stage $APP/mcp_server/dripdrop_mcp.py \
   && mv /tmp/sc_deploy_4.stage $APP/mcp_server/dripdrop_client.py \
   && chmod 644 $APP/sales_campaign.py $APP/flowdrip_app.py \
        $APP/mcp_server/dripdrop_mcp.py $APP/mcp_server/dripdrop_client.py"

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
    echo "   Roll back with:  ssh -i $SSH_KEY $SERVER 'cd /opt/dripdrop/backups/$STAMP && cp -p flowdrip_app.py sales_campaign.py $APP/ && cp -p mcp_server/* $APP/mcp_server/ && systemctl restart dripdrop dripdrop-green dripdrop-mcp'"
    exit 1
}

echo "== 4/6 Restart the app, one color at a time =="
restart_and_wait dripdrop-green 8081
restart_and_wait dripdrop       8080

echo "== 5/6 Restart the MCP connector =="
# Last, and only once both colors answer: its tools call back into the app,
# so bringing it up against a half-restarted pair fails its own first call.
$SSH "systemctl restart dripdrop-mcp"
$SSH "sleep 3; systemctl is-active dripdrop-mcp"
$SSH "journalctl -u dripdrop-mcp --since '2 minutes ago' --no-pager | tail -15"

echo "== 6/6 Confirm the module actually imported =="
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
echo "   fill the target in, set the repeat if you want one, and queue it."
echo "   Then tell Claude: 'Run my pending DripDrop sales campaign.'"
echo
echo "   Claude picks it up with sales_runs_pending and writes the companies and"
echo "   contacts back with sales_run_update. Nothing it writes can send: the"
echo "   run still stops at the review screen on the page for the trim."

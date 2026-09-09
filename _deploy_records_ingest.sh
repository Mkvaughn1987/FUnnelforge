#!/bin/bash
# Deploy the structured-record candidate ingest.
#
# Four files change together and none of them works alone: ats.py holds
# ingest_records(), flowdrip_app.py exposes it at /api/v1/candidates/records,
# and the two mcp_server files are the connector tool that calls that route.
# So this ships all four and restarts all three services.
#
# Unlike _deploy_zero_downtime.sh this touches ONLY these four paths -- no
# EXTRA_FILES, no Caddyfile sync -- because production has drifted from the
# repo before and a broader deploy silently reverts live hotfixes.
#
# Both colors currently run (Caddy fails over between them), so they are
# restarted one at a time with a health check in between: the other color is
# always serving. If either fails to come back, the script stops before
# touching the second one.

set -e

SERVER="root@134.199.237.206"
SSH_KEY="$HOME/.ssh/dripdrop"
SSH="ssh -o ConnectTimeout=90 -o ServerAliveInterval=15 -i $SSH_KEY $SERVER"
APP="/opt/dripdrop/app"

FILES=(
    "ats.py|$APP/ats.py"
    "flowdrip_app.py|$APP/flowdrip_app.py"
    "mcp_server/dripdrop_mcp.py|$APP/mcp_server/dripdrop_mcp.py"
    "mcp_server/dripdrop_client.py|$APP/mcp_server/dripdrop_client.py"
)

for entry in "${FILES[@]}"; do
    [ -f "${entry%%|*}" ] || { echo "ERROR: ${entry%%|*} not found -- run from the repo root"; exit 1; }
done

STAMP=$(date +%Y%m%d-%H%M%S)
echo "== 1/5 Upload + syntax-check all four files =="
$SSH "rm -f /tmp/rec_deploy_*.stage"
i=0
for entry in "${FILES[@]}"; do
    local_f="${entry%%|*}"
    i=$((i+1))
    stage="/tmp/rec_deploy_$i.stage"
    echo "   $local_f -> $stage"
    # Chunked gzip: a single large cat over ssh has dropped mid-stream before.
    gzip -c "$local_f" | $SSH "cat > $stage.gz"
    $SSH "gunzip -f $stage.gz && python3 -c 'import ast,sys; ast.parse(open(sys.argv[1],\"rb\").read())' $stage"
done
echo "   all four uploaded and parse on the server"

echo "== 2/5 Back up the live files ($STAMP) =="
$SSH "mkdir -p /opt/dripdrop/backups/$STAMP && cd $APP && cp -p ats.py flowdrip_app.py mcp_server/dripdrop_mcp.py mcp_server/dripdrop_client.py /opt/dripdrop/backups/$STAMP/ && ls /opt/dripdrop/backups/$STAMP/"

echo "== 3/5 Swap the new files in =="
$SSH "mv /tmp/rec_deploy_1.stage $APP/ats.py \
   && mv /tmp/rec_deploy_2.stage $APP/flowdrip_app.py \
   && mv /tmp/rec_deploy_3.stage $APP/mcp_server/dripdrop_mcp.py \
   && mv /tmp/rec_deploy_4.stage $APP/mcp_server/dripdrop_client.py \
   && chmod 644 $APP/ats.py $APP/flowdrip_app.py $APP/mcp_server/dripdrop_mcp.py $APP/mcp_server/dripdrop_client.py"

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
    echo "   Roll back with:  ssh -i $SSH_KEY $SERVER 'cp -p /opt/dripdrop/backups/$STAMP/* $APP/ && cp -p /opt/dripdrop/backups/$STAMP/dripdrop_*.py $APP/mcp_server/ && systemctl restart dripdrop dripdrop-green dripdrop-mcp'"
    exit 1
}

echo "== 4/5 Restart the app, one color at a time =="
restart_and_wait dripdrop-green 8081
restart_and_wait dripdrop       8080

echo "== 5/5 Restart the MCP connector =="
$SSH "systemctl restart dripdrop-mcp && sleep 3 && systemctl is-active dripdrop-mcp"

echo
echo "== Deploy complete =="
$SSH "curl -s https://dripdripdrop.ai/healthz -o /dev/null -w '   https check: HTTP %{http_code} in %{time_total}s\n'" || true
echo "   backup: /opt/dripdrop/backups/$STAMP"

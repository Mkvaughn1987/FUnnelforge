#!/bin/bash
# Deploy the radius/mileage search fix.
#
# ONE file changes: ats.py. Nothing else -- production has drifted from the
# repo in flowdrip_app.py and funnel_forge/arena_pdfs.py (undeployed live
# hotfixes), so _deploy_zero_downtime.sh would silently revert them. This
# touches ats.py only, leaving that drift alone.
#
# Both colors run (Caddy fails over between them), so they restart one at a
# time with a health check between: the other color is always serving. If the
# first fails to come back, the script stops before touching the second.
#
# The MCP connector does not import ats.py's geocode path, so it is not
# restarted.

set -e

SERVER="root@134.199.237.206"
SSH_KEY="$HOME/.ssh/dripdrop"
SSH="ssh -o ConnectTimeout=90 -o ServerAliveInterval=15 -i $SSH_KEY $SERVER"
APP="/opt/dripdrop/app"

[ -f ats.py ] || { echo "ERROR: ats.py not found -- run from the repo root"; exit 1; }

EXPECT_LIVE="e9d2a243d2f730db07d8b2ea7bd13e58496d0681"
STAMP=$(date +%Y%m%d-%H%M%S)

echo "== 1/4 Confirm prod is where we branched from =="
LIVE=$($SSH "git -C $APP hash-object ats.py")
echo "   live ats.py: $LIVE"
if [ "$LIVE" != "$EXPECT_LIVE" ]; then
    echo "   ERROR: prod ats.py is not $EXPECT_LIVE -- someone hotfixed it."
    echo "   Reconcile that change into this branch before deploying."
    exit 1
fi

echo "== 2/4 Upload + syntax-check =="
gzip -c ats.py | $SSH "cat > /tmp/geo_deploy.stage.gz"
$SSH "gunzip -f /tmp/geo_deploy.stage.gz && python3 -c 'import ast,sys; ast.parse(open(sys.argv[1],\"rb\").read())' /tmp/geo_deploy.stage"
echo "   uploaded and parses on the server"

echo "== 3/4 Back up the live file ($STAMP) and swap =="
$SSH "mkdir -p /opt/dripdrop/backups/$STAMP && cp -p $APP/ats.py /opt/dripdrop/backups/$STAMP/ \
   && mv /tmp/geo_deploy.stage $APP/ats.py && chmod 644 $APP/ats.py"

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
    echo "   Roll back with:  ssh -i $SSH_KEY $SERVER 'cp -p /opt/dripdrop/backups/$STAMP/ats.py $APP/ats.py && systemctl restart dripdrop dripdrop-green'"
    exit 1
}

echo "== 4/4 Restart the app, one color at a time =="
restart_and_wait dripdrop-green 8081
restart_and_wait dripdrop       8080

echo
echo "== Deploy complete =="
$SSH "curl -s https://dripdripdrop.ai/healthz -o /dev/null -w '   https check: HTTP %{http_code} in %{time_total}s\n'" || true
echo "   backup: /opt/dripdrop/backups/$STAMP/ats.py"

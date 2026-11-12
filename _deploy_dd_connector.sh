#!/bin/bash
# Ships the full DD Claude connector: /api/v1/dd/* routes in flowdrip_app.py
# plus the MCP tools/client in mcp_server/. dripdrop-mcp restarts LAST, after
# the app is healthy, so no tool ever points at a route that is not live.
# ats.py is deliberately NOT shipped: prod runs uncommitted ats.py work.
# Hard-aborts unless prod's CR-stripped blob of both files equals the base
# commit this branch was cut from, so nothing live-but-untracked is clobbered.
# Blue/green flip copied from _deploy_flowdrip_only.sh: start the idle colour,
# wait for /healthz, let Caddy route, stop the old colour.
set -e

SERVER="root@134.199.237.206"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=90 -o ServerAliveInterval=15 $SERVER"
APP="/opt/dripdrop/app"
BASE="${BASE:-912f706}"
FILES=(flowdrip_app.py mcp_server/dripdrop_mcp.py mcp_server/dripdrop_client.py)

for f in "${FILES[@]}"; do
    [ -f "$f" ] || { echo "ERROR: $f not found -- run from the worktree root"; exit 1; }
done
STAMP=dd-connector-$(date +%Y%m%d-%H%M%S)

echo "== 0/6 Hash-guard: prod must equal base $BASE on every file =="
for f in "${FILES[@]}"; do
    want=$(git rev-parse "$BASE:$f")
    have=$($SSH "tr -d '\r' < $APP/$f | git hash-object --stdin")
    if [ "$want" != "$have" ]; then
        echo "   ABORT: prod $f = $have, base = $want (prod has moved; rebase first)"
        exit 1
    fi
    echo "   $f ok ($have)"
done

echo "== 1/6 Upload + syntax-check =="
$SSH "rm -f /tmp/ddconn_*.stage /tmp/ddconn_*.stage.gz"
for f in "${FILES[@]}"; do
    stage="/tmp/ddconn_${f//\//_}.stage"
    gzip -c "$f" | $SSH "cat > $stage.gz"
    $SSH "gunzip -f $stage.gz && python3 -c 'import ast,sys; ast.parse(open(sys.argv[1],\"rb\").read())' $stage"
    # the staged bytes must be the local bytes
    l=$(git hash-object --no-filters "$f"); r=$($SSH "git hash-object $stage")
    [ "$l" = "$r" ] || { echo "   ABORT: staged $f differs from local ($l vs $r)"; exit 1; }
    echo "   $f staged + parses ($r)"
done

echo "== 2/6 Back up live files -> /opt/dripdrop/backups/$STAMP =="
$SSH "mkdir -p /opt/dripdrop/backups/$STAMP && cd $APP && cp -p --parents ${FILES[*]} /opt/dripdrop/backups/$STAMP/ && ls -lR /opt/dripdrop/backups/$STAMP/"

echo "== 3/6 Detect active colour =="
BLUE_ACTIVE=$($SSH "systemctl is-active dripdrop 2>/dev/null || echo inactive")
GREEN_ACTIVE=$($SSH "systemctl is-active dripdrop-green 2>/dev/null || echo inactive")
echo "   blue: $BLUE_ACTIVE   green: $GREEN_ACTIVE"
if [ "$BLUE_ACTIVE" = "active" ] && [ "$GREEN_ACTIVE" != "active" ]; then
    UP_SVC="dripdrop-green"; UP_PORT=8081; DOWN_SVC="dripdrop"
elif [ "$GREEN_ACTIVE" = "active" ] && [ "$BLUE_ACTIVE" != "active" ]; then
    UP_SVC="dripdrop"; UP_PORT=8080; DOWN_SVC="dripdrop-green"
else
    UP_SVC="dripdrop"; UP_PORT=8080; DOWN_SVC="dripdrop-green"
fi

echo "== 4/6 Swap the two files in + start $UP_SVC on :$UP_PORT =="
MV=""
for f in "${FILES[@]}"; do MV="$MV mv /tmp/ddconn_${f//\//_}.stage $APP/$f && chmod 644 $APP/$f &&"; done
$SSH "$MV systemctl restart $UP_SVC"

HEALTHY=0
for i in $(seq 1 40); do
    if $SSH "curl -sf http://localhost:$UP_PORT/healthz >/dev/null 2>&1"; then
        echo "   $UP_SVC healthy after ${i}s"; HEALTHY=1; break
    fi
    sleep 1
done
if [ "$HEALTHY" = "0" ]; then
    echo "   ERROR: $UP_SVC not healthy in 40s. $DOWN_SVC left running."
    $SSH "journalctl -u $UP_SVC --since '2 minutes ago' --no-pager | tail -40"
    echo "   Roll back: ssh $SERVER 'cp -rp /opt/dripdrop/backups/$STAMP/. $APP/ && systemctl restart $DOWN_SVC && systemctl stop $UP_SVC'"
    exit 1
fi

echo "== 5/6 Let Caddy route to $UP_SVC, then stop $DOWN_SVC =="
sleep 6
if $SSH "systemctl is-active $DOWN_SVC >/dev/null 2>&1"; then
    $SSH "systemctl stop $DOWN_SVC"; echo "   $DOWN_SVC stopped"
else
    echo "   ($DOWN_SVC was not active)"
fi

echo "== 6/6 Verify =="
for f in "${FILES[@]}"; do
    want=$(git rev-parse "HEAD:$f")
    have=$($SSH "tr -d '\r' < $APP/$f | git hash-object --stdin")
    [ "$want" = "$have" ] && echo "   $f == HEAD ($have)" || { echo "   MISMATCH $f: prod $have vs HEAD $want"; exit 1; }
done
echo "   restarting dripdrop-mcp"
$SSH "systemctl restart dripdrop-mcp; sleep 4; systemctl is-active dripdrop-mcp"
$SSH "journalctl -u dripdrop-mcp --since '1 minute ago' --no-pager | tail -8"
# New routes answer 401 without a key (route exists), never 404.
for r in pipeline top10 ai_prompts sales_contacts clients running_campaigns sales_assets home profile          tasks/done tasks/briefing replies contacts contact_lists campaigns/contacts campaigns/action          campaigns/edit send_preview newsletters newsletters/issue newsletters/edit settings dnc campaign_styles; do
    $SSH "curl -s -o /dev/null -w '   POST /api/v1/dd/$r -> %{http_code}\n' -X POST http://localhost:$UP_PORT/api/v1/dd/$r"
done
for r in tasks replies contacts/search newsletters analytics settings mailboxes dnc; do
    $SSH "curl -s -o /dev/null -w '   GET  /api/v1/dd/$r -> %{http_code}\n' http://localhost:$UP_PORT/api/v1/dd/$r"
done
$SSH "journalctl -u $UP_SVC --since '3 minutes ago' --no-pager | grep -iE 'traceback|error' | tail -5 || echo '   no errors in the log'"
$SSH "curl -s https://dripdripdrop.ai/healthz -o /dev/null -w '   https: HTTP %{http_code} in %{time_total}s\n'" || true
echo "== Done. Active: $UP_SVC :$UP_PORT. Backup: /opt/dripdrop/backups/$STAMP =="

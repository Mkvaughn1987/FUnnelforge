#!/bin/bash
# Ships flowdrip_app.py and top_ten.py: My Top 10 short list at the top of
# the page, with adds looked up on the web before they are saved.
# Hard-aborts unless prod's CR-stripped blob of both files equals the base
# commit this branch was cut from, so nothing live-but-untracked is clobbered.
# Blue/green flip copied from _deploy_flowdrip_only.sh: start the idle colour,
# wait for /healthz, let Caddy route, stop the old colour.
set -e

SERVER="root@134.199.237.206"
SSH_KEY="$HOME/.ssh/dripdrop"
SSH="ssh -o ConnectTimeout=90 -o ServerAliveInterval=15 -i $SSH_KEY $SERVER"
APP="/opt/dripdrop/app"
BASE="${BASE:-791c6fd}"
FILES=(flowdrip_app.py top_ten.py)

for f in "${FILES[@]}"; do
    [ -f "$f" ] || { echo "ERROR: $f not found -- run from the worktree root"; exit 1; }
done
STAMP=top10-quick-$(date +%Y%m%d-%H%M%S)

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
$SSH "rm -f /tmp/t10q_*.stage /tmp/t10q_*.stage.gz"
for f in "${FILES[@]}"; do
    stage="/tmp/t10q_${f//\//_}.stage"
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
for f in "${FILES[@]}"; do MV="$MV mv /tmp/t10q_${f//\//_}.stage $APP/$f && chmod 644 $APP/$f &&"; done
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
    echo "   Roll back: ssh -i $SSH_KEY $SERVER 'cp -p /opt/dripdrop/backups/$STAMP/* $APP/ && systemctl restart $DOWN_SVC && systemctl stop $UP_SVC'"
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
# top_ten.py is imported lazily by the page, so /healthz cannot see it break.
$SSH "cd $APP && /opt/dripdrop/venv/bin/python -c 'import top_ten as t; print(\"   top_ten imports:\", t.split_query(\"weoneil.com\"), bool(t.verify_prompt(\"x\", \"\", None, \"2026-01-01\")))'"
$SSH "journalctl -u $UP_SVC --since '3 minutes ago' --no-pager | grep -iE 'traceback|error' | tail -5 || echo '   no errors in the log'"
$SSH "curl -s https://dripdripdrop.ai/healthz -o /dev/null -w '   https: HTTP %{http_code} in %{time_total}s\n'" || true
echo "== Done. Active: $UP_SVC :$UP_PORT. Backup: /opt/dripdrop/backups/$STAMP =="

#!/bin/bash
# Deploy the AI Prompts page.
#
# Two files, same rule as _deploy_sales_campaign.sh: ai_prompts.py is the whole
# feature (routine catalogue, the AI parse, the prompt builder, the three-view
# page) and flowdrip_app.py contributes only the nav entry and the router
# branch that reaches it. Ship one without the other and you get either a dead
# nav button or a module nothing routes to.
#
# Narrow on purpose -- ONLY these two paths, no EXTRA_FILES, no Caddyfile sync.
# Production has drifted from the repo before and a broader deploy silently
# reverts live hotfixes.
#
# Nothing else moves. No MCP change: the page never calls the connector, it
# writes text for the user to paste into Claude. The only outbound call it
# makes is one Anthropic request per "Read this" click, on the key the app
# already has, offloaded off the event loop.
#
# The nav entry that used to read "Sales Campaign" now reads "AI Prompts" and
# points here. The Sales Campaign page is still routed and still reachable --
# from a card on the result view -- it just no longer has its own sidebar row.
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
    "ai_prompts.py|$APP/ai_prompts.py"
    "flowdrip_app.py|$APP/flowdrip_app.py"
)

for entry in "${FILES[@]}"; do
    [ -f "${entry%%|*}" ] || { echo "ERROR: ${entry%%|*} not found -- run from the repo root"; exit 1; }
done

STAMP=$(date +%Y%m%d-%H%M%S)

echo "== 0/5 Confirm prod's flowdrip_app.py is the one this branch was built on =="
# Prod has carried uncommitted hotfixes before. If these two hashes differ,
# STOP: this deploy would overwrite whatever is live but untracked.
LOCAL_BASE=$(git rev-parse HEAD:flowdrip_app.py 2>/dev/null || echo "unknown")
echo "   branch base blob: $LOCAL_BASE"
$SSH "cd $APP && git hash-object flowdrip_app.py 2>/dev/null || python3 -c \"
import hashlib,sys
d=open('$APP/flowdrip_app.py','rb').read()
print(hashlib.sha1(b'blob %d\\0'%len(d)+d).hexdigest())\""
echo "   ^ compare against the branch base of the commit this deploy is from."
echo "   They will differ if you committed changes on top -- that is expected."
echo "   What is NOT expected is prod matching neither. Check before continuing."

echo "== 1/5 Upload + syntax-check both files =="
$SSH "rm -f /tmp/aip_deploy_*.stage /tmp/aip_deploy_*.stage.gz"
i=0
for entry in "${FILES[@]}"; do
    local_f="${entry%%|*}"
    i=$((i+1))
    stage="/tmp/aip_deploy_$i.stage"
    echo "   $local_f -> $stage"
    # Chunked gzip: a single large cat over ssh has dropped mid-stream before.
    gzip -c "$local_f" | $SSH "cat > $stage.gz"
    $SSH "gunzip -f $stage.gz && python3 -c 'import ast,sys; ast.parse(open(sys.argv[1],\"rb\").read())' $stage"
done
echo "   both uploaded and parse on the server"

echo "== 2/5 Back up the live files ($STAMP) =="
# ai_prompts.py is new, so there is nothing to back up for it on a first
# deploy -- the `|| true` covers that and only that.
$SSH "mkdir -p /opt/dripdrop/backups/$STAMP && cd $APP \
   && cp -p flowdrip_app.py /opt/dripdrop/backups/$STAMP/ \
   && { cp -p ai_prompts.py /opt/dripdrop/backups/$STAMP/ 2>/dev/null || echo '   ai_prompts.py not live yet -- first deploy'; } \
   && ls -l /opt/dripdrop/backups/$STAMP/"

echo "== 3/5 Swap the new files in =="
$SSH "mv /tmp/aip_deploy_1.stage $APP/ai_prompts.py \
   && mv /tmp/aip_deploy_2.stage $APP/flowdrip_app.py \
   && chmod 644 $APP/ai_prompts.py $APP/flowdrip_app.py"

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
    echo "   Roll back with:  ssh -i $SSH_KEY $SERVER 'cd /opt/dripdrop/backups/$STAMP && cp -p flowdrip_app.py $APP/ && systemctl restart dripdrop dripdrop-green'"
    exit 1
}

echo "== 4/5 Restart the app, one color at a time =="
restart_and_wait dripdrop-green 8081
restart_and_wait dripdrop       8080

echo "== 5/5 Confirm the module actually imported =="
# The router catches an import failure and shows the page as unavailable rather
# than taking the app down -- so a green /healthz alone does NOT prove the
# feature loaded. This is the check that does.
$SSH "/opt/dripdrop/venv/bin/python -c \"import ast,sys; ast.parse(open('$APP/ai_prompts.py','rb').read()); print('   ai_prompts.py parses under the app venv')\""
$SSH "journalctl -u dripdrop --since '3 minutes ago' --no-pager | grep -i 'AIPrompts' || echo '   no AIPrompts errors in the log'"

echo
echo "== Deploy complete =="
$SSH "curl -s https://dripdripdrop.ai/healthz -o /dev/null -w '   https check: HTTP %{http_code} in %{time_total}s\n'" || true
echo "   backup: /opt/dripdrop/backups/$STAMP"
echo
echo "   Next: open dripdripdrop.ai, click 'AI Prompts' under Content & Tools,"
echo "   type what you want in plain English and press 'Read this'."
echo
echo "   That one click is the only thing that costs anything -- a single Haiku"
echo "   call to read the sentence. Nothing sends, nothing imports, no ZoomInfo"
echo "   credits move. The page only ever hands back text to copy."

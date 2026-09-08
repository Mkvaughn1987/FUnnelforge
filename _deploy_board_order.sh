#!/bin/bash
# Board order: Google Jobs first, then ZipRecruiter.
#
# Two files, text changes only:
#   ai_prompts.py    -- the sales_campaign routine's step 1, which is what the
#                       generated prompt tells Claude to do
#   sales_campaign.py -- handoff_brief's "DO ONLY THE TWO THINGS" block, which
#                       is what the Sales Campaign page hands Claude, plus the
#                       "source" enum in the sourcing schema (google added)
#
# flowdrip_app.py is NOT shipped -- it did not change. Narrow on purpose: no
# EXTRA_FILES, no Caddyfile sync (that would re-break the :8082 MCP block).
#
# No behaviour change beyond the wording of two prompts. Nothing sends,
# nothing is queued, no credits move.

set -e

SERVER="root@134.199.237.206"
SSH_KEY="$HOME/.ssh/dripdrop"
SSH="ssh -o ConnectTimeout=90 -o ServerAliveInterval=15 -i $SSH_KEY $SERVER"
APP="/opt/dripdrop/app"

FILES=(
    "ai_prompts.py|$APP/ai_prompts.py"
    "sales_campaign.py|$APP/sales_campaign.py"
)

for entry in "${FILES[@]}"; do
    [ -f "${entry%%|*}" ] || { echo "ERROR: ${entry%%|*} not found -- run from the repo root"; exit 1; }
done

STAMP=$(date +%Y%m%d-%H%M%S)

echo "== 0/5 Confirm prod carries no untracked drift in these two files =="
for f in ai_prompts.py sales_campaign.py; do
    echo "   $f"
    echo "      HEAD blob: $(git rev-parse HEAD:$f 2>/dev/null || echo unknown)"
    $SSH "python3 -c \"
import hashlib
d=open('$APP/$f','rb').read()
print('      prod blob: '+hashlib.sha1(b'blob %d\\0'%len(d)+d).hexdigest())\""
done
echo "   ^ these should match the commit this deploy is built on top of."
echo "     Matching NEITHER means prod has an untracked hotfix -- stop."

echo "== 1/5 Upload + syntax-check both files =="
$SSH "rm -f /tmp/bo_deploy_*.stage /tmp/bo_deploy_*.stage.gz"
i=0
for entry in "${FILES[@]}"; do
    local_f="${entry%%|*}"
    i=$((i+1))
    stage="/tmp/bo_deploy_$i.stage"
    echo "   $local_f -> $stage"
    gzip -c "$local_f" | $SSH "cat > $stage.gz"
    $SSH "gunzip -f $stage.gz && python3 -c 'import ast,sys; ast.parse(open(sys.argv[1],\"rb\").read())' $stage"
done
echo "   both uploaded and parse on the server"

echo "== 2/5 Back up the live files ($STAMP) =="
$SSH "mkdir -p /opt/dripdrop/backups/$STAMP && cd $APP \
   && cp -p ai_prompts.py sales_campaign.py /opt/dripdrop/backups/$STAMP/ \
   && ls -l /opt/dripdrop/backups/$STAMP/"

echo "== 3/5 Swap the new files in =="
$SSH "mv /tmp/bo_deploy_1.stage $APP/ai_prompts.py \
   && mv /tmp/bo_deploy_2.stage $APP/sales_campaign.py \
   && chmod 644 $APP/ai_prompts.py $APP/sales_campaign.py"

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
    echo "   Roll back with:  ssh -i $SSH_KEY $SERVER 'cd /opt/dripdrop/backups/$STAMP && cp -p ai_prompts.py sales_campaign.py $APP/ && systemctl restart dripdrop dripdrop-green'"
    exit 1
}

echo "== 4/5 Restart the app, one color at a time =="
restart_and_wait dripdrop-green 8081
restart_and_wait dripdrop       8080

echo "== 5/5 Confirm the new wording is actually live =="
# A green /healthz only proves the app booted -- the router swallows a bad
# import and shows one page as unavailable. This is the check that matters.
$SSH "grep -c 'Google Jobs first' $APP/ai_prompts.py"
$SSH "grep -c 'Google Jobs (udm=8) first' $APP/sales_campaign.py"
$SSH "journalctl -u dripdrop --since '3 minutes ago' --no-pager | grep -iE 'AIPrompts|SalesCampaign' || echo '   no page errors in the log'"

echo
echo "== Deploy complete =="
$SSH "curl -s https://dripdripdrop.ai/healthz -o /dev/null -w '   https check: HTTP %{http_code} in %{time_total}s\n'" || true
echo "   backup: /opt/dripdrop/backups/$STAMP"

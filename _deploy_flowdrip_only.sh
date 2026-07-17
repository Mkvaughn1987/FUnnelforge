#!/bin/bash
# SAFE SINGLE-FILE DEPLOY — pushes ONLY flowdrip_app.py.
#
# Why this exists: _deploy_zero_downtime.sh also ships EXTRA_FILES (ats.py,
# arena_pdfs.py, jway_banner.png) and can sync the Caddyfile. If the local
# copy of any of those has drifted from production, a normal deploy silently
# reverts the live file. When a change touches ONLY flowdrip_app.py (like the
# candidate-import API), use this script so nothing else can be clobbered.
#
# Same blue/green mechanics as the full deploy: stage the new file, start the
# idle color, wait for /healthz, flip Caddy, stop the old color. If the new
# color never goes healthy, the old one is left running and the site stays up.

set -e

SERVER="root@134.199.237.206"
SSH_KEY="$HOME/.ssh/dripdrop"
SSH="ssh -o ConnectTimeout=90 -o ServerAliveInterval=15 -i $SSH_KEY $SERVER"

LOCAL_FILE="flowdrip_app.py"
REMOTE_FILE="/opt/dripdrop/app/flowdrip_app.py"

if [ ! -f "$LOCAL_FILE" ]; then
    echo "ERROR: $LOCAL_FILE not found in current directory"
    exit 1
fi

echo "== 1/6 Upload $LOCAL_FILE via chunked gzip =="
TMP_GZ="/tmp/dripdrop_deploy_$$.gz"
gzip -c "$LOCAL_FILE" > "$TMP_GZ"
SIZE=$(wc -c < "$TMP_GZ")
echo "   gzipped size: $SIZE bytes"

SPLIT_PREFIX="/tmp/dripdrop_deploy_$$_chunk."
split -b 200000 "$TMP_GZ" "$SPLIT_PREFIX"
CHUNKS=( ${SPLIT_PREFIX}* )
echo "   chunks: ${#CHUNKS[@]}"

$SSH "rm -f /tmp/dripdrop_deploy_*.gz /tmp/dripdrop_deploy_chunk.*"

for chunk in "${CHUNKS[@]}"; do
    chunk_name=$(basename "$chunk")
    success=0
    for attempt in 1 2 3 4; do
        if cat "$chunk" | $SSH "cat >> /tmp/dripdrop_deploy_chunk.bin" 2>/dev/null; then
            success=1
            break
        fi
        echo "     retry $attempt for $chunk_name after reset"
        $SSH "rm -f /tmp/dripdrop_deploy_chunk.bin" 2>/dev/null || true
        sleep 3
    done
    if [ "$success" = "0" ]; then
        echo "ERROR: failed to upload $chunk_name after 4 attempts"
        rm -f "$TMP_GZ" "${SPLIT_PREFIX}"*
        exit 1
    fi
done
rm -f "$TMP_GZ" "${SPLIT_PREFIX}"*

# Decompress + integrity-check on the server; do NOT overwrite the live file
# yet — the atomic mv happens only after the new color is chosen.
$SSH "mv /tmp/dripdrop_deploy_chunk.bin /tmp/dripdrop_deploy.gz && gunzip -f /tmp/dripdrop_deploy.gz && python3 -c 'import ast; ast.parse(open(\"/tmp/dripdrop_deploy\").read())' >/dev/null"
echo "   upload complete + parses on server"

echo "== 2/6 Detect which color is currently active =="
BLUE_ACTIVE=$($SSH "systemctl is-active dripdrop 2>/dev/null || echo inactive")
GREEN_ACTIVE=$($SSH "systemctl is-active dripdrop-green 2>/dev/null || echo inactive")
echo "   blue:  $BLUE_ACTIVE"
echo "   green: $GREEN_ACTIVE"

if [ "$BLUE_ACTIVE" = "active" ] && [ "$GREEN_ACTIVE" != "active" ]; then
    UP_SVC="dripdrop-green"; UP_PORT=8081
    DOWN_SVC="dripdrop";       DOWN_PORT=8080
elif [ "$GREEN_ACTIVE" = "active" ] && [ "$BLUE_ACTIVE" != "active" ]; then
    UP_SVC="dripdrop";       UP_PORT=8080
    DOWN_SVC="dripdrop-green"; DOWN_PORT=8081
else
    UP_SVC="dripdrop";       UP_PORT=8080
    DOWN_SVC="dripdrop-green"; DOWN_PORT=8081
fi

echo "== 3/6 Stage new code + start $UP_SVC on :$UP_PORT =="
$SSH "mv /tmp/dripdrop_deploy $REMOTE_FILE && systemctl restart $UP_SVC"

echo "== 4/6 Wait for $UP_SVC /healthz to respond =="
HEALTHY=0
for i in $(seq 1 30); do
    if $SSH "curl -sf http://localhost:$UP_PORT/healthz >/dev/null 2>&1"; then
        echo "   $UP_SVC healthy after ${i}s"
        HEALTHY=1
        break
    fi
    sleep 1
done
if [ "$HEALTHY" = "0" ]; then
    echo "   ERROR: $UP_SVC did not become healthy within 30s"
    echo "   Leaving $DOWN_SVC running so the site stays up."
    $SSH "journalctl -u $UP_SVC --since '1 minute ago' --no-pager | tail -40"
    exit 1
fi

echo "== 5/6 Wait ~6s for Caddy to route traffic to $UP_SVC =="
sleep 6

echo "== 6/6 Stop $DOWN_SVC =="
if [ "$DOWN_SVC" = "dripdrop" ] && [ "$BLUE_ACTIVE" = "active" ]; then
    $SSH "systemctl stop $DOWN_SVC"; echo "   blue stopped"
elif [ "$DOWN_SVC" = "dripdrop-green" ] && [ "$GREEN_ACTIVE" = "active" ]; then
    $SSH "systemctl stop $DOWN_SVC"; echo "   green stopped"
else
    echo "   (was not active, skipping)"
fi

echo
echo "== Deploy complete. Active: $UP_SVC on :$UP_PORT =="
sleep 4
$SSH "curl -s https://dripdripdrop.ai/healthz -o /dev/null -w 'https check: HTTP %{http_code} in %{time_total}s\n'" || true

#!/bin/bash
# Zero-downtime deploy using blue/green + Caddy's first-healthy-upstream
# failover.
#
# Strategy:
#   1. Upload code to disk (shared path, both colors read from it)
#   2. Detect which color is currently active (blue = :8080, green = :8081)
#   3. Start the OTHER color on its port
#   4. Wait for it to respond to /healthz
#   5. Stop the previously-active color — Caddy's health checker flips
#      traffic to the new one within ~3 seconds
#
# Upload path: historically we used plain scp, but scp kept failing with
# "connection reset by peer" on large files (flowdrip_app.py is ~1.9MB).
# We now upload the file gzipped in three chunks over ssh stdin with
# per-chunk retries — slower than scp by a couple seconds, but reliable.
#
# Notes:
#   - Both colors read from /opt/dripdrop/app/flowdrip_app.py. The running
#     interpreter already loaded the module at startup, so the old process
#     briefly runs the OLD code even though disk has the NEW code. Fine.
#   - Leader election inside flowdrip_app.py ensures only one process ever
#     sends email. The passive side hot-standbys waiting for takeover.
#   - Users on existing Socket.IO sessions stay connected to the old
#     process until it stops, then NiceGUI's reconnect overlay routes
#     them to the new one. No kicked-back-to-main-page.

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

# Optional: extra files to deploy alongside the main app. Space-separated
# pairs of "local_path:remote_path". Uncomment and edit as needed.
EXTRA_FILES=(
    "funnel_forge/arena_pdfs.py:/opt/dripdrop/app/funnel_forge/arena_pdfs.py"
    "ats.py:/opt/dripdrop/app/ats.py"
)

echo "== 1/7 Upload $LOCAL_FILE via chunked gzip =="
TMP_GZ="/tmp/dripdrop_deploy_$$.gz"
gzip -c "$LOCAL_FILE" > "$TMP_GZ"
SIZE=$(wc -c < "$TMP_GZ")
echo "   gzipped size: $SIZE bytes"

# Split into ~200KB chunks
SPLIT_PREFIX="/tmp/dripdrop_deploy_$$_chunk."
split -b 200000 "$TMP_GZ" "$SPLIT_PREFIX"
CHUNKS=( ${SPLIT_PREFIX}* )
echo "   chunks: ${#CHUNKS[@]}"

# Wipe any leftover chunk files on server
$SSH "rm -f /tmp/dripdrop_deploy_*.gz /tmp/dripdrop_deploy_chunk.*"

# Upload each chunk, retry up to 4 times on connection reset
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

# Decompress and stage on server (don't overwrite production file yet —
# we want the overwrite to be atomic once we know we have the whole file)
$SSH "mv /tmp/dripdrop_deploy_chunk.bin /tmp/dripdrop_deploy.gz && gunzip -f /tmp/dripdrop_deploy.gz && python3 -c 'open(\"/tmp/dripdrop_deploy\", \"rb\").read()' >/dev/null"
echo "   upload complete"

echo "== 2/7 Upload extra files (if any) =="
for pair in "${EXTRA_FILES[@]}"; do
    src="${pair%%:*}"
    dst="${pair##*:}"
    if [ ! -f "$src" ]; then
        echo "   skip: $src not found"
        continue
    fi
    echo "   $src  ->  $dst"
    TMP2="/tmp/dripdrop_extra_$$.gz"
    gzip -c "$src" > "$TMP2"
    # Extras are usually small enough for a single chunk
    success=0
    for attempt in 1 2 3 4; do
        if cat "$TMP2" | $SSH "cat > /tmp/dripdrop_extra.gz && gunzip -f /tmp/dripdrop_extra.gz && mv /tmp/dripdrop_extra $dst" 2>/dev/null; then
            success=1
            break
        fi
        echo "     retry $attempt for extra file"
        sleep 2
    done
    rm -f "$TMP2"
    if [ "$success" = "0" ]; then
        echo "ERROR: failed to upload $src"
        exit 1
    fi
done

echo "== 2b/7 Sync Caddyfile if changed =="
# Uploads the Caddyfile to the server only when it's different from the
# deployed copy. Safety: we back up the current remote Caddyfile, stage
# the new one to a temp path, run `caddy validate` on it, and only
# atomically swap + reload on success. Any failure restores the backup
# so the site stays up.
LOCAL_CADDY="deploy/Caddyfile"
if [ -f "$LOCAL_CADDY" ]; then
    REMOTE_CADDY_SHA=$($SSH "sha256sum /etc/caddy/Caddyfile 2>/dev/null | awk '{print \$1}'" || echo "")
    LOCAL_CADDY_SHA=$(sha256sum "$LOCAL_CADDY" | awk '{print $1}')
    if [ "$REMOTE_CADDY_SHA" != "$LOCAL_CADDY_SHA" ]; then
        echo "   Caddyfile differs — staging + validating"
        if ! cat "$LOCAL_CADDY" | $SSH "cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak && cat > /etc/caddy/Caddyfile.new && caddy validate --config /etc/caddy/Caddyfile.new >/dev/null 2>&1 && mv /etc/caddy/Caddyfile.new /etc/caddy/Caddyfile && systemctl reload caddy"; then
            echo "   ERROR: Caddyfile validation or reload failed. Restoring backup."
            $SSH "test -f /etc/caddy/Caddyfile.bak && cp /etc/caddy/Caddyfile.bak /etc/caddy/Caddyfile && systemctl reload caddy; rm -f /etc/caddy/Caddyfile.new" || true
            exit 1
        fi
        echo "   Caddy reloaded"
    else
        echo "   Caddyfile in sync"
    fi
fi

echo "== 3/7 Detect which color is currently active =="
BLUE_ACTIVE=$($SSH "systemctl is-active dripdrop 2>/dev/null || echo inactive")
GREEN_ACTIVE=$($SSH "systemctl is-active dripdrop-green 2>/dev/null || echo inactive")
echo "   blue:  $BLUE_ACTIVE"
echo "   green: $GREEN_ACTIVE"

# Decide which to bring up and which to take down.
if [ "$BLUE_ACTIVE" = "active" ] && [ "$GREEN_ACTIVE" != "active" ]; then
    UP_SVC="dripdrop-green"; UP_PORT=8081
    DOWN_SVC="dripdrop";       DOWN_PORT=8080
elif [ "$GREEN_ACTIVE" = "active" ] && [ "$BLUE_ACTIVE" != "active" ]; then
    UP_SVC="dripdrop";       UP_PORT=8080
    DOWN_SVC="dripdrop-green"; DOWN_PORT=8081
else
    # Both off OR both on — bring up blue, stop green (safe default).
    UP_SVC="dripdrop";       UP_PORT=8080
    DOWN_SVC="dripdrop-green"; DOWN_PORT=8081
fi

# Atomic swap of the staged file into the live path, then start up_svc
echo "== 4/7 Stage new code + start $UP_SVC on :$UP_PORT =="
$SSH "mv /tmp/dripdrop_deploy $REMOTE_FILE && systemctl restart $UP_SVC"

echo "== 5/7 Wait for $UP_SVC /healthz to respond =="
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

echo "== 6/7 Wait ~6s for Caddy to route traffic to $UP_SVC =="
# Caddy's health_interval is 3s. Give it two cycles so the old upstream
# is fully drained before we stop it.
sleep 6

echo "== 7/7 Stop $DOWN_SVC =="
if [ "$DOWN_SVC" = "dripdrop" ] && [ "$BLUE_ACTIVE" = "active" ]; then
    $SSH "systemctl stop $DOWN_SVC"
    echo "   blue stopped"
elif [ "$DOWN_SVC" = "dripdrop-green" ] && [ "$GREEN_ACTIVE" = "active" ]; then
    $SSH "systemctl stop $DOWN_SVC"
    echo "   green stopped"
else
    echo "   (was not active, skipping)"
fi

echo
echo "== Deploy complete. Active: $UP_SVC on :$UP_PORT =="
# Caddy's health check runs every 3s, so give it one more cycle to
# fully drain the stopped upstream before the final check. Without this
# sleep, the curl sometimes lands right when Caddy is between polls and
# returns a transient 502 even though the site is healthy.
sleep 4
$SSH "curl -s https://dripdripdrop.ai/healthz -o /dev/null -w 'https check: HTTP %{http_code} in %{time_total}s\n'" || true

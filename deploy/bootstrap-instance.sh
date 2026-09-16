#!/bin/bash
# Bootstrap a new DripDrop instance, end to end.
#
# Run this ONCE on a fresh droplet, AFTER deploy/setup-server.sh has finished.
# It does every remaining step: clone, install, generate secrets, write the
# .env, point Caddy at your hostname, install the queue-pruning cron, and
# start the service.
#
#   ssh root@YOUR_DROPLET_IP
#   curl -fsSL https://raw.githubusercontent.com/Mkvaughn1987/FUnnelforge/feat/whitelabel-instance/deploy/bootstrap-instance.sh -o bootstrap.sh
#   bash bootstrap.sh
#
# It asks five questions and generates everything else. Nothing here reaches
# Arena: the API key, the session secret and the invite code are all this
# instance's own.

set -euo pipefail

REPO="${REPO:-https://github.com/Mkvaughn1987/FUnnelforge.git}"
BRANCH="${BRANCH:-feat/whitelabel-instance}"
APP=/opt/dripdrop/app
ENVFILE=/opt/dripdrop/.env

if [ ! -d /opt/dripdrop ]; then
    echo "ERROR: /opt/dripdrop missing. Run deploy/setup-server.sh first." >&2
    exit 1
fi

echo "=== DripDrop instance bootstrap ==="
echo

# ---------------------------------------------------------------- questions
# Everything else is derived or generated. Defaults are shown in brackets.

read -rp "Hostname for this instance [app.inboxslide.ai]: " DOMAIN
DOMAIN="${DOMAIN:-app.inboxslide.ai}"

read -rp "Your login email [mkvaughn1987@gmail.com]: " OWNER
OWNER="${OWNER:-mkvaughn1987@gmail.com}"

# -s so the key never lands in the shell history or the scrollback.
read -rsp "Anthropic API key (sk-ant-...): " APIKEY; echo
[ -n "$APIKEY" ] || { echo "API key is required." >&2; exit 1; }

# CAN-SPAM: commercial email must carry the sending entity's real name and a
# registered physical address. These go in every footer, so a placeholder here
# is a legal problem, not a cosmetic one.
read -rp "Legal company name (goes in every email footer): " COMPANY
[ -n "$COMPANY" ] || { echo "Company name is required (CAN-SPAM)." >&2; exit 1; }

read -rp "Postal address, pipe-separated (Name | Street | City, ST ZIP US): " ADDRESS
[ -n "$ADDRESS" ] || { echo "Postal address is required (CAN-SPAM)." >&2; exit 1; }

# ---------------------------------------------------------------- generated
# Never reuse Arena's. The secret signs this instance's sessions; sharing one
# would let a cookie from either instance authenticate on the other. The invite
# code must be set explicitly -- leaving it unset does NOT close registration,
# it falls back to a code compiled into every build, Arena's included.
SECRET="$(openssl rand -hex 32)"
INVITE="$(openssl rand -hex 6)"

# Caddy requests a certificate the moment it starts, over HTTP-01 on port 80.
# That only works if the hostname already resolves to THIS box and Cloudflare is
# not proxying it yet (grey cloud). Checking now turns a confusing 20-minute
# TLS failure into a clear message before anything is written.
echo
echo "Checking DNS for $DOMAIN ..."
MYIP="$(curl -fsS --max-time 10 https://api.ipify.org || true)"
DNSIP="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1; exit}' || true)"
if [ -z "$DNSIP" ]; then
    echo "ERROR: $DOMAIN does not resolve yet." >&2
    echo "  Add an A record for it pointing at $MYIP, DNS-only (grey cloud)," >&2
    echo "  wait a minute, then run this again." >&2
    exit 1
fi
if [ -n "$MYIP" ] && [ "$DNSIP" != "$MYIP" ]; then
    echo "WARNING: $DOMAIN resolves to $DNSIP but this droplet is $MYIP." >&2
    echo "  If that is a Cloudflare proxy IP, set the record to DNS-only (grey" >&2
    echo "  cloud) until the certificate is issued, or Caddy cannot complete the" >&2
    echo "  HTTP-01 challenge." >&2
    read -rp "  Continue anyway? [y/N] " _go
    [ "$_go" = "y" ] || [ "$_go" = "Y" ] || exit 1
fi

echo
echo "[1/6] Cloning $BRANCH ..."
if [ -d "$APP/.git" ]; then
    git -C "$APP" fetch origin "$BRANCH" && git -C "$APP" checkout "$BRANCH" && git -C "$APP" pull
else
    rm -rf "$APP"
    git clone -b "$BRANCH" "$REPO" "$APP"
fi

echo "[2/6] Installing Python packages ..."
/opt/dripdrop/venv/bin/pip install -q -r "$APP/requirements.txt"

echo "[3/6] Writing $ENVFILE ..."
# systemd reads this file directly (EnvironmentFile= in dripdrop.service), so
# values are unquoted and run to end of line. No inline comments.
cat > "$ENVFILE" <<ENV
ANTHROPIC_API_KEY=$APIKEY
DRIPDROP_SECRET=$SECRET
DRIPDROP_INVITE_CODES=$INVITE

DRIPDROP_PUBLIC_ORIGIN=https://$DOMAIN
DRIPDROP_OWNER_EMAIL=$OWNER
DRIPDROP_SUPER_ADMINS=$OWNER
DRIPDROP_ADMIN_EMAILS=$OWNER
DRIPDROP_ATS_EMAILS=$OWNER
DRIPDROP_ROUNDUP_OWNER=$OWNER
DRIPDROP_ROUNDUP_EMAILS=$OWNER

DRIPDROP_COMPANY_NAME=$COMPANY
DRIPDROP_COMPANY_ADDRESS=$ADDRESS

# Which addresses on a parsed resume belong to the operator, not the candidate.
# Matched on the FULL address: putting a consumer domain in
# DRIPDROP_INTERNAL_DOMAINS instead would silently discard the real email of
# most candidates, with no error and no way to tell which records lost one.
DRIPDROP_INTERNAL_EMAILS=$OWNER
DRIPDROP_INTERNAL_DOMAINS=

# EDIT BEFORE THE FIRST 4x4 SEND. Default below is a DRAFT of terms a new firm
# can truthfully offer. It deliberately drops the fill-rate and fill-time
# claims that ship in the code default -- those are Arena's placement history
# and a new venture cannot assert them. Replace with your own or set empty.
DRIPDROP_VALUE_PROPS=Contingency-Based - you pay nothing to review our candidates. Replacement Guarantee - if a hire doesn't work out, we replace them at no cost. Cost-Effective - internal hiring can cost upwards of \$25,000 per role. Dedicated Attention - you work directly with the person running your search.

DRIPDROP_JWAY_BANNER_URL=

# Where NiceGUI keeps browser sessions (app.storage.user). Its default is
# <working dir>/.nicegui, i.e. inside the root-owned git checkout, which the
# dripdrop service user cannot create: every login then logs a PermissionError
# and nothing persists across restarts. Keep it with the rest of the data.
NICEGUI_STORAGE_PATH=/opt/dripdrop/data/.nicegui
ENV
chmod 600 "$ENVFILE"
chown dripdrop:dripdrop "$ENVFILE"

echo "[4/6] Configuring Caddy for $DOMAIN ..."
# One Caddyfile per hostname: Caddy attempts ACME for every site block it
# loads, so a stray block for a host pointing at another droplet makes this box
# fail certificate renewal forever.
sed "s|^app\.inboxslide\.ai {|$DOMAIN {|" "$APP/deploy/Caddyfile.inboxslide" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl restart caddy

echo "[5/6] Installing the queue-pruning cron ..."
# Arena's instance reached a 133MB scheduled_queue.json before this existed.
# Preventing the growth is far cheaper than remediating it.
cat > /etc/cron.d/dripdrop-prune <<'CRON'
17 4 * * * dripdrop /opt/dripdrop/venv/bin/python /opt/dripdrop/app/deploy/queue_maintenance.py >> /var/log/dripdrop-prune.log 2>&1
CRON

echo "[6/6] Starting the service ..."
cp "$APP/deploy/dripdrop.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now dripdrop
sleep 3
systemctl --no-pager --lines=5 status dripdrop || true

echo
echo "=== Done ==="
echo "  URL:          https://$DOMAIN"
echo "  Invite code:  $INVITE      <-- you need this to register"
echo
echo "Remaining, in this order:"
echo "  1. Wait ~30s, then open https://$DOMAIN. If it loads with a valid"
echo "     padlock, Caddy got its certificate. If not:"
echo "       journalctl -u caddy -n 40 --no-pager"
echo "  2. ONLY after that works, go to Cloudflare and: set SSL/TLS mode to"
echo "     Full (strict), then switch the A record to Proxied (orange cloud)."
echo "     Doing it in the other order breaks certificate issuance, and"
echo "     Flexible mode causes an infinite redirect loop."
echo "  3. Register at https://$DOMAIN with email + password. Use the invite"
echo "     code above. Do NOT use any Google sign-in button -- that flow also"
echo "     grants gmail.send and would make the app send from your gmail."
echo "  4. Settings -> connect Brevo or SendGrid for outbound mail."
echo "  5. Review DRIPDROP_VALUE_PROPS in $ENVFILE before the first 4x4 send,"
echo "     then: systemctl restart dripdrop"

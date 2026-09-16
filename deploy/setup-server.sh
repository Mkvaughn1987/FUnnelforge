#!/bin/bash
# DripDrop Server Setup Script
# Run this on a fresh Ubuntu 24.04 DigitalOcean Droplet
# Usage: ssh root@YOUR_IP 'bash -s' < setup-server.sh

set -e

echo "=== DripDrop Server Setup ==="

# 1. System updates
echo "[1/8] Updating system..."
apt update && apt upgrade -y

# 2. Install Python 3.11+ and essentials
echo "[2/8] Installing Python and dependencies..."
apt install -y python3 python3-venv python3-pip git ufw

# 3. Install Caddy (reverse proxy + auto SSL)
echo "[3/8] Installing Caddy..."
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy

# 4. Create dripdrop user and directories
echo "[4/8] Creating user and directories..."
useradd --system --shell /bin/false --home /opt/dripdrop dripdrop || true
mkdir -p /opt/dripdrop/{app,data,data/Campaigns,data/Contacts,data/PDFs}
chown -R dripdrop:dripdrop /opt/dripdrop

# 5. Create Python virtual environment
echo "[5/8] Setting up Python venv..."
python3 -m venv /opt/dripdrop/venv
/opt/dripdrop/venv/bin/pip install --upgrade pip

# 6. Firewall
echo "[6/8] Configuring firewall..."
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable

echo ""
echo "=== Setup complete! ==="
echo ""
echo "=== Setup complete! ==="
echo ""
echo "ONE next step. Do NOT upload files by hand -- the bootstrap script clones"
echo "the whole repo, which is the only way to get every runtime file."
echo ""
echo "  curl -fsSL https://raw.githubusercontent.com/Mkvaughn1987/FUnnelforge/feat/whitelabel-instance/deploy/bootstrap-instance.sh -o bootstrap.sh"
echo "  bash bootstrap.sh"
echo ""
echo "Before you run it, the DNS A record for your hostname must already point"
echo "at this droplet, DNS-only (grey cloud in Cloudflare). The bootstrap starts"
echo "Caddy, which immediately requests an SSL certificate -- that fails if the"
echo "name does not resolve here yet, or if Cloudflare is proxying it."

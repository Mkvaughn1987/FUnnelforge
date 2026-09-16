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
echo "Next steps:"
echo "  1. Upload your app files:"
echo "     scp flowdrip_app.py funnelforge_core.py dripdrop_logo.png requirements.txt root@YOUR_IP:/opt/dripdrop/app/"
echo "     scp -r assets root@YOUR_IP:/opt/dripdrop/app/"
echo ""
echo "  2. Create .env file:"
echo "     echo 'ANTHROPIC_API_KEY=your-key-here' > /opt/dripdrop/.env"
echo ""
echo "  3. Install Python packages:"
echo "     /opt/dripdrop/venv/bin/pip install -r /opt/dripdrop/app/requirements.txt"
echo ""
echo "  4. Copy the systemd service:"
echo "     cp /opt/dripdrop/app/deploy/dripdrop.service /etc/systemd/system/"
echo "     systemctl daemon-reload"
echo "     systemctl enable dripdrop"
echo "     systemctl start dripdrop"
echo ""
echo "  5. Copy the Caddyfile for THIS instance (one per hostname - Caddy tries"
echo "     to get a cert for every site block it loads, so the wrong file makes"
echo "     the box fail ACME forever for a host that points elsewhere):"
echo "       Arena:  cp /opt/dripdrop/app/deploy/Caddyfile     /etc/caddy/Caddyfile"
echo "       171:    cp /opt/dripdrop/app/deploy/Caddyfile.171 /etc/caddy/Caddyfile"
echo "     systemctl restart caddy"
echo ""
echo "  6. In Cloudflare, set SSL/TLS mode to 'Full (strict)'"
echo "     (Flexible sends plain HTTP to a Caddy that redirects to HTTPS -> loop)"
echo ""
echo "  Done! Visit https://dripdripdrop.ai (or https://171.dripdripdrop.ai)"

#!/usr/bin/env bash
# Deploy feat/whitelabel-instance to the inboxslide box (run ON the box as root).
# Install once:  cp /opt/dripdrop/app/deploy/deploy-inboxslide.sh ~/bin/ && chmod +x ~/bin/deploy-inboxslide.sh
# Then:          bash ~/bin/deploy-inboxslide.sh
set -euo pipefail
APP=/opt/dripdrop/app
ENV=/opt/dripdrop/.env
BRANCH=feat/whitelabel-instance

cd "$APP"
cp "$ENV" "$ENV.bak.$(date +%Y%m%d%H%M%S)"
echo "== before: $(git rev-parse --short HEAD)"
git pull --ff-only origin "$BRANCH"
echo "== after:  $(git rev-parse --short HEAD)"
if [ -f requirements.txt ] && [ -x /opt/dripdrop/venv/bin/pip ]; then
  /opt/dripdrop/venv/bin/pip install -q -r requirements.txt || true
fi
python3 deploy/sync_brand_env.py --apply
systemctl restart dripdrop
sleep 15
systemctl is-active dripdrop
systemctl show dripdrop -p NRestarts -p ExecMainStartTimestamp
START=$(systemctl show dripdrop -p ExecMainStartTimestamp --value)
echo "== errors since process start (should be empty):"
journalctl -u dripdrop --since "$START" --no-pager | grep -iE "traceback|error|nameerror" | tail -20 || true
echo "== app: $(curl -s -o /dev/null -w '%{http_code}' https://app.inboxslide.ai/)"

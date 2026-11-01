#!/usr/bin/env bash
# Nightly backup of the instance data directory: campaigns, contacts, the
# send queue, OAuth tokens, per-user configs, PDFs. Keeps 14 days locally.
# Copy the newest archive off the box too; a local backup does not survive
# the box.
#
# Install once (as root on the box):
#   cp /opt/dripdrop/app/deploy/dripdrop-backup.sh /usr/local/bin/ && chmod +x /usr/local/bin/dripdrop-backup.sh
#   cp /opt/dripdrop/app/deploy/dripdrop-backup.cron /etc/cron.d/dripdrop-backup && chmod 644 /etc/cron.d/dripdrop-backup
#   /usr/local/bin/dripdrop-backup.sh      # first run, check the output
set -euo pipefail
DEST=${DRIPDROP_BACKUP_DIR:-/opt/dripdrop/backups/nightly}
KEEP_DAYS=${DRIPDROP_BACKUP_KEEP_DAYS:-14}
mkdir -p "$DEST"
tar czf "$DEST/data-$(date +%Y%m%d-%H%M).tgz" -C /opt/dripdrop data
find "$DEST" -name "data-*.tgz" -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) ok $(ls "$DEST" | wc -l) archives, $(du -sh "$DEST" | cut -f1)"

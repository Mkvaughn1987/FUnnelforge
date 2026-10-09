#!/bin/bash
# Push a clean copy of DripDrop to the new owner's GitHub repo.
#
#   bash deploy/handover_export.sh https://github.com/<owner>/<repo>.git [--force]
#
# 1. Compares every .py the live server runs (app root + mcp_server/) with
#    this checkout, line endings stripped. A difference means the server has
#    a change the repo lacks, or the reverse: stop and reconcile first,
#    or pass --force to export anyway.
# 2. Exports the committed tree (git archive HEAD) into a new repo with ONE
#    commit and no history, so nothing from before the split (inboxslide
#    included) goes along. Pushes it as main.
#
# Read-only on the server. Run from the repo root with a clean tree.
set -e

REMOTE="$1"; FORCE="$2"
SERVER="root@134.199.237.206"
SSH="ssh -o ConnectTimeout=90 -i $HOME/.ssh/dripdrop $SERVER"
APP="/opt/dripdrop/app"

[ -n "$REMOTE" ] || { echo "usage: $0 <new-repo-url> [--force]"; exit 1; }
[ -f flowdrip_app.py ] || { echo "run from the repo root"; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "commit or discard local changes first"; exit 1; }

# Known and harmless (see docs/HANDOVER.md, "Server vs repo"):
#   arena_pdfs.py  - April copy in the app root; the app loads
#                    funnel_forge/arena_pdfs.py instead.
#   scripts_backfill_api_key_plaintext.py - one-off, already run.
#   funnelforge_core.py - the repo holds a newer version that was never
#                    deployed; the server's older one is what runs.
KNOWN=" arena_pdfs.py scripts_backfill_api_key_plaintext.py funnelforge_core.py "

echo "== 1/2 Repo vs live server =="
DIFF=0
while read -r sum f; do
    case "$KNOWN" in *" $f "*) echo "   known: $f"; continue ;; esac
    if ! git cat-file -e "HEAD:$f" 2>/dev/null; then
        echo "   only on server: $f"; DIFF=1; continue
    fi
    mine=$(git show "HEAD:$f" | tr -d '\r' | sha256sum | cut -d' ' -f1)
    [ "$mine" = "$sum" ] || { echo "   differs: $f"; DIFF=1; }
done < <($SSH "cd $APP && for f in *.py mcp_server/*.py funnel_forge/*.py; do echo \"\$(tr -d '\r' < \$f | sha256sum | cut -d' ' -f1) \$f\"; done")
if [ $DIFF = 1 ] && [ "$FORCE" != "--force" ]; then
    echo "   The repo and the server disagree (above). Bring the server's"
    echo "   versions into the repo, or rerun with --force."
    exit 1
fi
[ $DIFF = 0 ] && echo "   every server file matches the repo"

echo "== 2/2 Clean export to $REMOTE =="
SRC_SHA=$(git rev-parse --short HEAD)
TMP=$(mktemp -d)
git archive HEAD | tar -x -C "$TMP"
(
    cd "$TMP"
    git init -q -b main
    git add -A
    git commit -q -m "DripDrop as of $(date +%Y-%m-%d) (handover from $SRC_SHA)"
    git remote add origin "$REMOTE"
    git push -u origin main
)
echo "   pushed. Local copy: $TMP"

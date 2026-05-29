#!/usr/bin/env python3
"""One-time migration: un-block contacts that were wrongly opted-out by
TRANSIENT send failures (e.g. "Bounced: MS Graph send failed: Graph API
error: HTTP 500"). Those are not real bounces — the recipient address is
fine; Graph/Gmail just hiccupped at send time.

Real NDR bounces ("Bounced (NDR): ...") and reply-driven opt-outs
("Auto-detected opt-out from reply") are preserved.

Usage:
    python _unblock_transient_optouts.py [USERS_DIR]            # dry-run
    python _unblock_transient_optouts.py [USERS_DIR] --apply    # write

USERS_DIR defaults to /opt/dripdrop/data/users (the live server layout).
Pass a local path as the first arg when testing.

Spec: docs/superpowers/specs/2026-05-26-transient-send-error-optout-fix-design.md
"""
import json
import sys
from pathlib import Path

DEFAULT_USERS_DIR = "/opt/dripdrop/data/users"


def _is_transient_optout_reason(reason: str) -> bool:
    """True if a DNC entry was created by a transient send failure and
    should be un-blocked. Matches the scheduler's stored reason strings:
    "Bounced: MS Graph send failed: ..." and "Bounced: Gmail send failed: ...".
    Does NOT match real bounces ("Bounced (NDR): ...") or opt-out replies."""
    r = (reason or "").strip().lower()
    return (r.startswith("bounced: ms graph send failed")
            or r.startswith("bounced: gmail send failed"))


def _process_user(dnc_path: Path, apply: bool) -> list:
    """Return the list of removed entries for one user's dnc_list.json.
    Writes the kept entries back only when apply=True."""
    try:
        entries = json.loads(dnc_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ! skip {dnc_path}: unreadable ({e})")
        return []
    if not isinstance(entries, list):
        print(f"  ! skip {dnc_path}: not a JSON list (got {type(entries).__name__})")
        return []
    removed = [e for e in entries
               if _is_transient_optout_reason(e.get("reason", ""))]
    if removed and apply:
        kept = [e for e in entries
                if not _is_transient_optout_reason(e.get("reason", ""))]
        tmp = dnc_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(kept, indent=2), encoding="utf-8")
        tmp.replace(dnc_path)
    return removed


def main(argv) -> int:
    args = [a for a in argv if not a.startswith("--")]
    apply = "--apply" in argv
    users_dir = Path(args[0]) if args else Path(DEFAULT_USERS_DIR)
    if not users_dir.exists():
        print(f"Users dir not found: {users_dir}")
        return 1

    mode = "APPLY (writing changes)" if apply else "DRY-RUN (no changes)"
    print(f"Un-block transient opt-outs — {mode}")
    if apply:
        # Footgun guard: after the 2026-05-26 deploy, the scheduler's
        # PERMANENT-failure path still writes "Bounced: MS Graph/Gmail
        # send failed: ..." for genuinely-bad addresses. This script's
        # predicate matches that same prefix, so a LATER run would
        # un-block real permanent blocks. It's a one-time cleanup for
        # historical transient-error blocks — run it once, right after
        # deploy, then don't run it again.
        print("WARNING: one-time migration. Running this AFTER new permanent-failure "
              "blocks have accumulated will wrongly un-block real bad addresses. "
              "Only proceed if this is the initial post-deploy cleanup.")
    print(f"Scanning: {users_dir}\n")

    total_removed = 0
    for user_dir in sorted(users_dir.iterdir()):
        if not user_dir.is_dir():
            continue
        dnc_path = user_dir / "dnc_list.json"
        if not dnc_path.exists():
            continue
        removed = _process_user(dnc_path, apply)
        if removed:
            total_removed += len(removed)
            emails = ", ".join(e.get("email", "?") for e in removed)
            print(f"{user_dir.name} — removed {len(removed)}: {emails}")

    print(f"\nTotal entries {'removed' if apply else 'to remove'}: {total_removed}")
    if not apply and total_removed:
        print("Re-run with --apply to write the changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

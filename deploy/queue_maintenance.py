#!/usr/bin/env python3
"""Shrink every user's scheduled_queue.json. Safe to run daily, unattended.

DripDrop is a single-process NiceGUI app, so any page or scheduler tick that
parses a giant queue blocks the event loop for every user at once. Arena's
instance reached 133 MB / 22k items and presented as "slow, sometimes won't
load" with an otherwise idle server. Two thirds of that was removable:
cancelled residue, and the full HTML body inlined on every already-sent item.

The app's own archive_old_queue_entries() only runs at STARTUP, and these boxes
stay up for months, so it cannot be relied on. Hence the cron.

Two rules, both verified safe against every consumer of the queue:

  1. Drop status == "cancelled" items entirely. requeue_campaign clears
     cancelled items itself and does not use them for deduplication.

  2. Blank body and attachments on status == "sent" items. requeue_campaign
     dedups on to/subject/step_name, never on body; the History table renders
     metadata only; the send already happened.

PENDING and FAILED bodies are left alone -- pending has not been sent yet and
failed is retriable. Deleting either loses the email's content irrecoverably.

Note also what this deliberately does NOT do: archive sent items younger than
30 days. That would break requeue's dedup and cause double-sends. Strip the
bodies instead; keep the rows.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATA_DIR = Path(os.environ.get("DRIPDROP_DATA_DIR", "/opt/dripdrop/data"))
DRY_RUN = "--dry-run" in sys.argv


def prune(path: Path) -> tuple[int, int]:
    """Return (bytes_before, bytes_after). Rewrites only if something changed."""
    before = path.stat().st_size
    try:
        queue = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  !! unreadable, skipped: {path} ({exc})")
        return before, before
    if not isinstance(queue, list):
        return before, before

    kept, dropped, stripped = [], 0, 0
    for item in queue:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        status = item.get("status")
        if status == "cancelled":
            dropped += 1
            continue
        if status == "sent" and (item.get("body") or item.get("attachments")):
            item["body"] = ""
            item["attachments"] = []
            stripped += 1
        kept.append(item)

    if not dropped and not stripped:
        return before, before

    if DRY_RUN:
        after = len(json.dumps(kept).encode("utf-8"))
    else:
        # Write beside the original and replace atomically: a crash mid-write
        # would otherwise leave a truncated queue, which loses pending sends.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(kept), encoding="utf-8")
        os.replace(tmp, path)
        after = path.stat().st_size

    print(f"  {path.parent.name}: -{dropped} cancelled, {stripped} bodies "
          f"stripped, {before // 1024} KB -> {after // 1024} KB")
    return before, after


def main() -> int:
    users = DATA_DIR / "users"
    if not users.is_dir():
        print(f"No users directory at {users}; nothing to do.")
        return 0

    total_before = total_after = 0
    for user_dir in sorted(users.iterdir()):
        queue = user_dir / "scheduled_queue.json"
        if user_dir.is_dir() and queue.exists():
            b, a = prune(queue)
            total_before += b
            total_after += a

    saved = total_before - total_after
    print(f"{'[dry run] ' if DRY_RUN else ''}"
          f"total {total_before // 1024} KB -> {total_after // 1024} KB "
          f"(saved {saved // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Move Do-Not-Contact entries between DripDrop instances.

Each instance keeps its own `dnc_list.json` per user, so a brand-new instance
starts with no memory of who unsubscribed or bounced anywhere else. Running two
instances without reconciling them means you can email the same prospect from
two companies in one week, or email someone who explicitly opted out. Both are
CAN-SPAM problems, and the second one is the kind that gets a sending domain
blocked.

This runs in two halves, on two different servers:

    # On the instance you are copying FROM (e.g. Arena's):
    python3 dnc_transfer.py export --out /tmp/dnc-export.json

    # Copy the file across, then on the instance you are copying TO:
    python3 dnc_transfer.py import --in /tmp/dnc-export.json \
        --user you@example.com

Export unions every user's list on the source box, because a suppression is a
fact about the recipient, not about whichever colleague happened to trigger it.
Import is additive and idempotent: existing entries always win, nothing is ever
removed, and running it twice changes nothing the second time.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("DRIPDROP_DATA_DIR", "/opt/dripdrop/data"))


def _key(entry):
    """Dedup key: the address, lowercased. Domain rules keep their leading @."""
    return (entry.get("email") or "").lower().strip()


def _dnc_files():
    """Every dnc_list.json on this box — per-user dirs plus the legacy base one."""
    found = []
    base = DATA_DIR / "dnc_list.json"
    if base.exists():
        found.append(base)
    users = DATA_DIR / "users"
    if users.is_dir():
        found.extend(sorted(users.glob("*/dnc_list.json")))
    return found


def _read(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  ! skipping {path}: {exc}", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def _write_atomic(path, payload):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def cmd_export(args):
    files = _dnc_files()
    if not files:
        print(f"No dnc_list.json found under {DATA_DIR}.", file=sys.stderr)
        return 1

    merged = {}
    for path in files:
        entries = _read(path)
        kept = 0
        for entry in entries:
            key = _key(entry)
            if not key or key in merged:
                continue
            merged[key] = entry
            kept += 1
        print(f"  {path}: {len(entries)} entries, {kept} new")

    out = Path(args.out)
    _write_atomic(out, list(merged.values()))
    domains = sum(1 for k in merged if k.startswith("@"))
    print(f"\nWrote {len(merged)} unique entries ({domains} domain rules) to {out}")
    print("Copy it to the other server, then run the import half there.")
    return 0


def cmd_import(args):
    src = Path(getattr(args, "in"))
    if not src.exists():
        print(f"{src} does not exist.", file=sys.stderr)
        return 1
    incoming = _read(src)
    if not incoming:
        print(f"{src} has no usable entries.", file=sys.stderr)
        return 1

    safe = args.user.lower().strip().replace("@", "_at_").replace(".", "_")
    user_dir = DATA_DIR / "users" / safe
    if not user_dir.is_dir():
        print(
            f"No data directory for {args.user} at {user_dir}.\n"
            "Register and log in on this instance once, then run this again —\n"
            "the directory is created at first login.",
            file=sys.stderr,
        )
        return 1

    target = user_dir / "dnc_list.json"
    existing = _read(target) if target.exists() else []
    seen = {_key(e) for e in existing if _key(e)}

    stamp = datetime.now(timezone.utc).isoformat()
    added = 0
    for entry in incoming:
        key = _key(entry)
        if not key or key in seen:
            continue
        merged = dict(entry)
        merged.setdefault("name", "")
        merged.setdefault("company", "")
        merged.setdefault("reason", "suppressed on another instance")
        merged["source"] = f"import:{src.name}"
        merged.setdefault("added_at", stamp)
        existing.append(merged)
        seen.add(key)
        added += 1

    if args.dry_run:
        print(f"Dry run: would add {added} entries, leaving {len(existing) - added} untouched.")
        return 0

    if target.exists():
        backup = target.with_suffix(f".json.bak.{int(datetime.now().timestamp())}")
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backed up existing list to {backup}")

    _write_atomic(target, existing)
    try:
        import pwd, grp
        os.chown(target, pwd.getpwnam("dripdrop").pw_uid, grp.getgrnam("dripdrop").gr_gid)
    except Exception:
        pass  # Non-root or no such user — the app usually owns the dir already.

    print(f"Added {added} entries. {args.user} now suppresses {len(existing)} addresses.")
    print("Restart to pick it up:  systemctl restart dripdrop")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    exp = sub.add_parser("export", help="union every user's DNC list on this box")
    exp.add_argument("--out", default="/tmp/dnc-export.json")
    exp.set_defaults(func=cmd_export)

    imp = sub.add_parser("import", help="merge an exported list into one user here")
    imp.add_argument("--in", required=True, dest="in", metavar="FILE")
    imp.add_argument("--user", required=True, help="the login email on THIS instance")
    imp.add_argument("--dry-run", action="store_true")
    imp.set_defaults(func=cmd_import)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

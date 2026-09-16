#!/usr/bin/env python3
"""Copy the branding variables out of an env example and into a live .env.

Why this exists: the look of an instance -- logo, palette, vocabulary,
landing-page voice -- is now about thirty environment variables, and hand-
transcribing thirty lines onto a server at 11pm is how a typo becomes a
broken image in production.

Deliberately NOT a general "sync the whole file" tool. The example carries
placeholder values for real secrets (API keys, the OAuth client secret), and
a blind copy would overwrite live credentials with the word CHANGEME. Only
keys matching PREFIXES below are ever touched, and only when the example
sets them for real -- a commented-out line in the example is skipped, not
treated as "unset this".

Existing keys are replaced in place, so the .env keeps its own ordering and
comments. New keys are appended in one labelled block at the end.

Usage:
    python3 deploy/sync_brand_env.py                  # show what would change
    python3 deploy/sync_brand_env.py --apply          # write it, with a backup
    python3 deploy/sync_brand_env.py --example X --env Y
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import sys
from pathlib import Path

# Only variables whose names start with one of these are considered. Anything
# to do with credentials, hosts, paths or limits is out of scope on purpose.
PREFIXES = (
    "DRIPDROP_BRAND_",
    "DRIPDROP_WEB_",
    "DRIPDROP_TERM_",
    "DRIPDROP_THEME_",
    "DRIPDROP_GREETINGS",
)

_ASSIGN = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*)=(?P<val>.*)$")


def _in_scope(key: str) -> bool:
    return key.startswith(PREFIXES)


def _read_assignments(text: str) -> dict[str, str]:
    """Uncommented KEY=VALUE lines, last one wins -- which is what both
    systemd and python-dotenv do."""
    out: dict[str, str] = {}
    for line in text.split("\n"):
        m = _ASSIGN.match(line.strip())
        if m and _in_scope(m.group("key")):
            out[m.group("key")] = m.group("val")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--example", default="deploy/env.inboxslide.example")
    ap.add_argument("--env", default="/opt/dripdrop/.env")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes; without this it is a dry run")
    args = ap.parse_args(argv)

    ex_path, env_path = Path(args.example), Path(args.env)
    for p in (ex_path, env_path):
        if not p.is_file():
            print(f"not found: {p}", file=sys.stderr)
            return 2

    ex_text = ex_path.read_text(encoding="utf-8")
    env_text = env_path.read_text(encoding="utf-8")

    wanted = _read_assignments(ex_text)
    current = _read_assignments(env_text)
    if not wanted:
        print(f"{ex_path} sets no branding variables -- nothing to do.")
        return 0

    changed = {k: v for k, v in wanted.items() if current.get(k) != v}
    if not changed:
        print(f"{env_path} already matches {ex_path} on all "
              f"{len(wanted)} branding variables.")
        return 0

    for k, v in sorted(changed.items()):
        was = current.get(k)
        print(f"  {'update' if k in current else '   add'}  {k}")
        if was is not None:
            print(f"            was  {was[:70]}")
        print(f"            now  {v[:70]}")

    if not args.apply:
        print(f"\n{len(changed)} change(s). Dry run -- nothing written. "
              f"Re-run with --apply.")
        return 0

    # Replace in place where the key already exists, so the file keeps its
    # own layout and comments; collect the rest for a single appended block.
    lines = env_text.split("\n")
    seen: set[str] = set()
    for i, line in enumerate(lines):
        m = _ASSIGN.match(line.strip())
        if not m:
            continue
        key = m.group("key")
        if key in changed:
            lines[i] = f"{key}={changed[key]}"
            seen.add(key)

    appended = sorted(k for k in changed if k not in seen)
    if appended:
        stamp = _dt.date.today().isoformat()
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", f"# ── Branding, synced from {ex_path.name} on {stamp} ──"]
        lines += [f"{k}={changed[k]}" for k in appended]
    lines.append("")

    backup = env_path.with_suffix(env_path.suffix + f".bak.{_dt.datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(env_path, backup)
    env_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {env_path}  ({len(seen)} updated, {len(appended)} added)")
    print(f"backup at {backup}")
    print("now: systemctl restart dripdrop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

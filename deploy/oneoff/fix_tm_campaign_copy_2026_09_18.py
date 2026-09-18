"""One-off copy fixes to Mike's inboxslide campaigns (2026-09-18).

Dry run by default; pass --apply to write. Every file it touches is copied
to <user>/_backup_2026-09-18/ first. Idempotent: a second run finds nothing
left to change. Exact-string replacements only, each asserted to match once,
so an unexpected file is left alone rather than half-edited.

  1. Retire the pre-ThriveModal "General Contracting - BIM Manager Campaign"
     (an Arena recruiting pitch). MOVED to the backup dir, not deleted. Its
     offshore replacement already exists: "General Contracting BIM/VDC
     Coordinator Outreach - 2026".
  2. That replacement: "Vdc" -> "VDC" in three subject lines (title-casing).
  3. S+B James step 3 call script: "[Your Name]" -> "Mike".
  4. Forensic Accounting step 4: "usually lands at less than half that"
     -> ThriveModal's approved "up to 60-70% less" wording.
"""
import json
import os
import shutil
import sys
from pathlib import Path

USER = Path("/opt/dripdrop/data/users/mkvaughn1987_at_gmail_com")
CAMP = USER / "Campaigns"
BACKUP = USER / "_backup_2026-09-18"

RETIRE = "General_Contracting_-_BIM_Manager_Campaign.json"

# file -> list of (field, old, new); field is "subject" or "body"
EDITS = {
    "General_Contracting_BIM_VDC_Coordinator_Outreach_-_2026.json": [
        ("subject", "Pricing a Vdc Coordinator for Your Team",
                    "Pricing a VDC Coordinator for Your Team"),
        ("subject", "What a Vdc Coordinator Would Actually Do",
                    "What a VDC Coordinator Would Actually Do"),
        ("subject", "Last Note on Vdc Coordinator Placement",
                    "Last Note on VDC Coordinator Placement"),
    ],
    "S_B_James_Construction_Campaign.json": [
        ("body", "this is [Your Name] following up", "this is Mike following up"),
    ],
    "Corporate_Finance__Wealth_Management__Forensic_Accounting_-_.json": [
        ("body",
         "working your hours inside your own engagement management system, "
         "usually lands at less than half that.",
         "working your hours inside your own engagement management system, "
         "can come in at up to sixty to seventy percent less, depending on "
         "the role and experience level."),
    ],
}


def backup(p: Path, apply: bool):
    if apply:
        BACKUP.mkdir(exist_ok=True)
        dst = BACKUP / p.name
        if not dst.exists():
            shutil.copy2(p, dst)


def write_like(p: Path, data: dict):
    st = p.stat()
    p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.chown(p, st.st_uid, st.st_gid)


def main(apply: bool):
    changed = 0
    r = CAMP / RETIRE
    if r.exists():
        print(f"RETIRE  {RETIRE} -> {BACKUP.name}/")
        if apply:
            BACKUP.mkdir(exist_ok=True)
            shutil.move(str(r), str(BACKUP / RETIRE))
        changed += 1
    else:
        print(f"skip    {RETIRE} (already retired)")

    for fname, edits in EDITS.items():
        p = CAMP / fname
        if not p.exists():
            print(f"MISSING {fname} - left alone")
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        todo = 0
        for field, old, new in edits:
            hits = [e for e in data.get("emails", []) if old in (e.get(field) or "")]
            if not hits:
                done = any(new in (e.get(field) or "") for e in data.get("emails", []))
                print(f"skip    {fname}: {'already fixed' if done else 'TEXT NOT FOUND'}: {old[:50]!r}")
                continue
            assert len(hits) == 1, f"{fname}: {old!r} matched {len(hits)} steps"
            hits[0][field] = hits[0][field].replace(old, new)
            print(f"EDIT    {fname}: {old[:50]!r}")
            todo += 1
        if todo:
            changed += todo
            if apply:
                backup(p, apply)
                write_like(p, data)

    print(f"\n{changed} change(s) {'APPLIED' if apply else 'found (dry run; add --apply)'}")


if __name__ == "__main__":
    main("--apply" in sys.argv)

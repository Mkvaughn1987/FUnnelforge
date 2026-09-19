"""Give saved ThriveModal outreach campaigns their AI candidate profiles.

One-off remediation (2026-09-19). New campaigns get 3 candidate profiles
(title, years, estimated hourly rate, 2-3 bullets) from the builder; this adds
the same to campaigns saved before that, via _tm_add_campaign_profiles: one
follow-up email, never the first, before its closing ask. Role, location and
industry come from the campaign, corrected by tm_refresh_campaign_pdfs's
OVERRIDES.

Without --apply it generates and prints the profiles but writes nothing. Run
on the box as the service user, with its environment:

  systemd-run --quiet --uid=dripdrop --gid=dripdrop \\
    -p EnvironmentFile=/opt/dripdrop/.env \\
    -p Environment=DRIPDROP_DATA_DIR=/opt/dripdrop/data \\
    -p WorkingDirectory=/opt/dripdrop/app --wait --pipe \\
    /opt/dripdrop/venv/bin/python deploy/tm_add_campaign_profiles.py \\
    --user mkvaughn1987@gmail.com [--apply]

Each changed file is backed up next to itself as <name>.json.bak-profiles-<ts>.
Drafts and newsletters are skipped. Re-running replaces the last run's set.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "deploy"))
os.chdir(APP)
import flowdrip_app as fa  # noqa: E402
from tm_refresh_campaign_pdfs import _skip, _subject  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default="", help="substring of the file name")
    ap.add_argument("--count", type=int, default=fa.TM_CAMPAIGN_PROFILES_MIN)
    a = ap.parse_args()

    fa._CURRENT_USER_EMAIL.set(a.user)
    cdir = fa._user_campaigns_dir()
    print(f"campaigns: {cdir}\nmode:      {'APPLY' if a.apply else 'dry run'}\n")
    import anthropic
    client = anthropic.Anthropic(api_key=fa.ANTHROPIC_API_KEY)
    ts = time.strftime("%Y%m%d%H%M%S")
    done = failed = 0
    for p in sorted(cdir.glob("*.json")):
        if a.only and a.only not in p.name:
            continue
        camp = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(camp, dict):
            continue
        why = _skip(p, camp)
        if why:
            print(f"SKIP  {p.name} ({why})")
            continue
        subj = _subject(p.stem, camp)
        if not subj["role"]:
            print(f"SKIP  {p.name} (no role; add an OVERRIDE)")
            continue
        brief = camp.get("synopsis") or camp.get("brief") or ""
        try:
            out = fa._tm_add_campaign_profiles(
                client, camp, a.count, subj["role"],
                subj["industry"] or subj["company"], company=subj["company"],
                brief=brief)
        except Exception as ex:
            print(f"FAIL  {p.name}: {ex}")
            failed += 1
            continue
        profs = out["profiles"]
        print(f"{'DONE' if a.apply else 'PLAN'}  {p.name}\n      {subj}\n"
              f"      {len(profs)} profiles on email "
              f"{(out['email'] + 1) if out['email'] is not None else '-'}")
        for q in profs:
            print(f"        {q['title']} | {q['years']} yrs | "
                  f"{q['rate'] or 'NO RATE'}")
            for b in q["bullets"]:
                print(f"          - {b}")
        if not a.apply:
            continue
        if len(profs) < fa.TM_CAMPAIGN_PROFILES_MIN or out["email"] is None:
            print("      !! fewer than 3 profiles placed; file NOT written")
            failed += 1
            continue
        bak = p.with_name(p.name + f".bak-profiles-{ts}")
        bak.write_bytes(p.read_bytes())
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(camp, indent=2), encoding="utf-8")
        tmp.replace(p)
        done += 1
    print(f"\nwritten: {done}, not written: {failed}")


if __name__ == "__main__":
    main()

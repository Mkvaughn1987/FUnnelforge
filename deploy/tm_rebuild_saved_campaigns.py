"""Rewrite saved ThriveModal outreach campaigns in the model-email house style.

One-off remediation (2026-09-21). Mike's seven model emails became the house
style and Standard Outreach went to seven emails; he asked for the saved
campaigns to be rewritten too. Each campaign is rebuilt as the type it was
made from (recorded, or read off its old step names below), with fresh
research, then gets its Sales Assets PDFs back through the same path as
tm_refresh_campaign_pdfs.py. Contacts, name, status and schedule settings are
kept; only the steps and synopsis change.

Dry run by default. Active campaigns are skipped unless --include-active
(their contacts are mid-sequence). Run on the box as the service user:

  systemd-run --uid=dripdrop -p EnvironmentFile=/opt/dripdrop/.env \\
    -p Environment=DRIPDROP_DATA_DIR=/opt/dripdrop/data \\
    -p WorkingDirectory=/opt/dripdrop/app --wait --pipe --quiet \\
    /opt/dripdrop/venv/bin/python deploy/tm_rebuild_saved_campaigns.py \\
    --user mkvaughn1987@gmail.com [--apply] [--only NAME]

Each changed file is backed up next to itself as <name>.json.bak-rebuild-<ts>.
"""
import argparse
import importlib.util
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "tm_refresh_campaign_pdfs", HERE / "tm_refresh_campaign_pdfs.py")
refresh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refresh)  # also imports flowdrip_app and chdirs
fa = refresh.fa

# Campaigns saved before the type was recorded, keyed by file stem, read off
# their step names: "The signal" = They're Hiring; "What actually transfers"
# / "Email 1..." = the old Standard Outreach; S+B James carries the Priority
# Account Push arc. Anything unlisted and untyped becomes Standard Outreach.
TYPE_OVERRIDES = {
    "Commercial_Healthcare_Architecture_-_Estimator___VDC_Special": "tm_hiring_signal",
    "Corporate_Finance__Wealth_Management__Forensic_Accounting_-_": "tm_hiring_signal",
    "RK_Mechanical_-_Estimator_Support_Campaign": "tm_hiring_signal",
    "S_B_James_Construction_Campaign": "tm_conversation",
}
KEEP_KEYS = ("name", "subject", "body", "delay_days", "time", "step_type",
             "week")


def _type_for(stem, camp):
    if stem in TYPE_OVERRIDES:
        return TYPE_OVERRIDES[stem]
    t = fa._tm_camp_type(camp)
    return t if t in fa._TM_TYPE_KEYS else "tm_fivebyseven"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default="", help="substring of the file name")
    ap.add_argument("--include-active", action="store_true")
    a = ap.parse_args()

    fa._CURRENT_USER_EMAIL.set(a.user)
    cdir = fa._user_campaigns_dir()
    print(f"campaigns: {cdir}\nmode:      {'APPLY' if a.apply else 'dry run'}\n")
    client = None
    if a.apply:
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
        why = refresh._skip(p, camp)
        if not why and camp.get("status") == "active" and not a.include_active:
            why = f"active, {len(camp.get('contacts') or [])} contact(s) mid-sequence"
        if why:
            print(f"SKIP  {p.name} ({why})")
            continue
        subj = refresh._subject(p.stem, camp)
        if not subj["role"]:
            print(f"SKIP  {p.name} (no role to build for; add an OVERRIDE)")
            continue
        camp_type = _type_for(p.stem, camp)
        old = len(camp.get("emails") or [])
        print(f"{'BUILD' if a.apply else 'PLAN '} {p.name}\n      {camp_type} "
              f"(was {fa._tm_camp_type(camp) or camp.get('template_key')}, "
              f"{old} steps)  {subj}")
        if not a.apply:
            continue
        try:
            data = fa.generate_aicb_campaign(
                client, camp_type=camp_type, company=subj["company"],
                niche="" if subj["company"] else subj["industry"],
                industry=subj["industry"], roles=[subj["role"]],
                location=subj["location"])
        except Exception as ex:
            print(f"      !! build failed: {ex}; file NOT written")
            failed += 1
            continue
        emails = [{k: e[k] for k in KEEP_KEYS if k in e}
                  for e in data.get("emails") or []]
        if not emails:
            print("      !! no steps came back; file NOT written")
            failed += 1
            continue
        camp["emails"] = emails
        camp["aicb_camp_type"] = camp_type
        # Now ThriveModal copy, even where it was first built under Arena.
        camp["_playbook"] = fa.PLAYBOOK_THRIVEMODAL
        if data.get("synopsis"):
            camp["synopsis"] = data["synopsis"]
        out = fa._tm_refresh_campaign_pdfs(camp, **subj, client=client)
        print(f"      {len(emails)} steps, {out['attached']} PDFs: "
              + ", ".join(f"email {n}: {f}" for f, n in sorted(
                  out["where"].items(), key=lambda x: x[1])))
        bak = p.with_name(p.name + f".bak-rebuild-{ts}")
        bak.write_bytes(p.read_bytes())
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(camp, indent=2), encoding="utf-8")
        tmp.replace(p)
        done += 1
    if a.apply:
        print(f"\nwritten: {done}, not written: {failed}")


if __name__ == "__main__":
    main()

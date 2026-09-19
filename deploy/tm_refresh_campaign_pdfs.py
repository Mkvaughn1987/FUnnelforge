"""Give saved ThriveModal outreach campaigns the current Sales Assets PDFs.

One-off remediation (2026-09-19). Campaigns built before this change carry
either nothing, the six retired static ThriveModal PDFs, or Arena's curated set
(Market Pulse, Salary Guide, ...). This swaps those for freshly built Offshore
Role Blueprint + Staffing Cost Comparison (+ How We Work Together on long
sequences), placed by _tm_refresh_campaign_pdfs: never the first email, one per
email, on the step whose subject each PDF backs. Hand uploads are untouched.

Dry run by default. Run on the box as the service user, with its environment:

  sudo -u dripdrop bash -c 'set -a; . /opt/dripdrop/.env; set +a; \\
    cd /opt/dripdrop/app && /opt/dripdrop/venv/bin/python \\
    deploy/tm_refresh_campaign_pdfs.py --user mkvaughn1987@gmail.com [--apply]'

Each changed file is backed up next to itself as <name>.json.bak-pdfs-<ts>.
Drafts and newsletters are skipped. Re-running replaces what the last run built.
"""
import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
os.chdir(APP)
import flowdrip_app as fa  # noqa: E402

# Where a campaign's saved variables do not name the role ThriveModal would
# fill (the 3PL ones hold the BUYER's titles), or leave role/location/industry
# empty. Keyed by file stem. Everything else comes from the campaign itself.
OVERRIDES = {
    "3PL_Freight_WARN_Targets_-_Top_5_-_12wk__Sept_2026_": {
        "role": "Track and Trace Specialist", "location": "United States",
        "industry": "Logistics & Supply Chain"},
    "3PL_Freight_WARN_Targets_-_Top_5__Sept_2026_": {
        "role": "Track and Trace Specialist", "location": "United States",
        "industry": "Logistics & Supply Chain"},
    "3PL__Freight___Trucking_Operations_Staffing_Campaign": {
        "role": "Track and Trace Specialist", "location": "United States",
        "industry": "Logistics & Supply Chain"},
    "Redwood_Logistics_Campaign": {
        "company": "Redwood Logistics", "role": "Track and Trace Specialist",
        "location": "Chicago, IL", "industry": "Logistics & Supply Chain"},
    "S_B_James_Construction_Campaign": {
        "role": "Project Coordinator", "industry": "Construction"},
    "General_Contracting_BIM_VDC_Coordinator_Outreach_-_2026": {
        "role": "BIM Coordinator", "industry": "Construction"},
    "General_Contracting_-_BIM_Manager_Campaign": {"industry": "Construction"},
    "RK_Mechanical_-_Estimator_Support_Campaign": {"industry": "Construction"},
    "Commercial_Healthcare_Architecture_-_Estimator___VDC_Special": {
        "industry": "Architecture"},
    "Corporate_Finance__Real_Estate__Private_Equity_-_CPA_Campaig": {
        "industry": "Accounting & Finance"},
    "Corporate_Finance__Wealth_Management__Forensic_Accounting_-_": {
        "industry": "Accounting & Finance"},
    # TargetRole holds the buyers (Owner/Principal, VP of Operations, ...).
    "Property_Management__Manila_Style": {
        "role": "Maintenance Coordinator", "location": "United States",
        "industry": "Property Management"},
    "Fluor_Corporation_-_Structural_and_Civil_Support": {
        "location": "United States", "industry": "Engineering & Construction"},
}


def _subject(stem, camp):
    v = camp.get("variables") or {}
    o = OVERRIDES.get(stem, {})
    role = (v.get("TargetRole") or "").split(",")[0].strip()
    return {
        "company": o.get("company", (v.get("CompanyName") or "").strip()),
        "role": o.get("role", role),
        "location": o.get("location", (v.get("Geography") or "").strip()
                          or "United States"),
        "industry": o.get("industry", (v.get("Industry")
                                       or v.get("PrimaryIndustry") or "").strip()),
    }


def _skip(path, camp):
    if path.name.startswith("_Draft_") or camp.get("_is_wizard_draft"):
        return "draft"
    if camp.get("template_key") == "evergreen" or camp.get("newsletter_name"):
        return "newsletter"
    if not camp.get("emails"):
        return "no emails"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default="", help="substring of the file name")
    a = ap.parse_args()

    fa._CURRENT_USER_EMAIL.set(a.user)
    cdir = fa._user_campaigns_dir()
    print(f"campaigns: {cdir}\npdfs:      {fa._user_pdf_dir()}\n"
          f"mode:      {'APPLY' if a.apply else 'dry run'}\n")
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
        why = _skip(p, camp)
        if why:
            print(f"SKIP  {p.name} ({why})")
            continue
        subj = _subject(p.stem, camp)
        if not subj["role"]:
            print(f"SKIP  {p.name} (no role to build for; add an OVERRIDE)")
            continue
        if not a.apply:
            trial = copy.deepcopy(camp)
            out = fa._tm_refresh_campaign_pdfs(
                trial, **subj,
                build=lambda kinds, company, role, location, **_: {
                    k: fa._tm_campaign_pdf_filename(k, company or role)
                    for k in kinds})
        else:
            out = fa._tm_refresh_campaign_pdfs(camp, **subj, client=client)
        where = ", ".join(f"email {n}: {f}" for f, n in sorted(
            out["where"].items(), key=lambda x: x[1]))
        print(f"{'DONE' if a.apply else 'PLAN'}  {p.name}\n      {subj}\n"
              f"      removed {out['removed']} old, attached {out['attached']}: {where}")
        if not a.apply:
            continue
        if out["attached"] < 2:
            print("      !! fewer than 2 PDFs built; file NOT written")
            failed += 1
            continue
        bak = p.with_name(p.name + f".bak-pdfs-{ts}")
        bak.write_bytes(p.read_bytes())
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(camp, indent=2), encoding="utf-8")
        tmp.replace(p)
        done += 1
    if a.apply:
        print(f"\nwritten: {done}, not written: {failed}")


if __name__ == "__main__":
    main()

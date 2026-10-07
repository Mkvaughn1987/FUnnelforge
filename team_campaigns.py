"""Team-wide "who is already working this company" index.

Walks every campaign file belonging to the caller's team (same email
domain, e.g. everyone @arenastaffing.net) and records which company
email domains are in a campaign that started in the last WINDOW_DAYS.
New launches skip those companies so two reps (or one rep twice) never
run campaigns at the same company at the same time.

What counts:
  * every status, cancelled included: a cancelled campaign has usually
    already sent its first emails, and "deleting" a campaign in the app
    only cancels it.
  * company outreach only. Newsletters and slow drips (evergreen_only)
    are ongoing nurture lists that span hundreds of companies, and Find
    Candidates campaigns email candidates, so neither ever blocks.
  * start_date within the window (or in the future). Files with no
    start_date fall back to the file's modified date.

Pure file reads, no app imports, so it is unit-testable on its own.
"""
from __future__ import annotations

import json
import os
import threading
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

WINDOW_DAYS = 30

# Personal mailboxes say nothing about the company, so they never match.
FREE_MAIL = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com",
    "outlook.com", "live.com", "msn.com", "aol.com", "icloud.com", "me.com",
    "mac.com", "comcast.net", "att.net", "sbcglobal.net", "verizon.net",
    "protonmail.com", "proton.me", "gmx.com", "mail.com", "zoho.com",
    "cox.net", "charter.net", "earthlink.net", "bellsouth.net",
    "indeedemail.com",  # Indeed's candidate relay addresses
})

# Campaigns that email candidates, not companies.
CANDIDATE_TYPES = frozenset({"findcandidates"})

_cache: dict = {}            # path -> (mtime, summary | None)
_cache_lock = threading.Lock()


def email_domain(email: str) -> str:
    email = (email or "").strip().lower()
    if "@" not in email:
        return ""
    dom = email.rsplit("@", 1)[1].strip(". ")
    return "" if dom in FREE_MAIL else dom


def _contact_email(c: dict) -> str:
    return (c.get("email") or c.get("Email") or "").strip()


def _contact_company(c: dict) -> str:
    return (c.get("company") or c.get("Company") or "").strip()


def is_outbound(camp: dict) -> bool:
    """True only for campaigns that pitch companies. Newsletters / slow
    drips (nurture lists) and Find Candidates campaigns (which email
    candidates) neither block nor get blocked."""
    if camp.get("evergreen_only") or camp.get("newsletter_name"):
        return False
    if (camp.get("_chooser_origin") or "") == "candidate":
        return False
    kinds = {camp.get("aicb_camp_type"), camp.get("template_key"),
             camp.get("_chooser_origin")}
    return not (kinds & CANDIDATE_TYPES)


def team_suffix(owner_email: str) -> str:
    """'mike@arenastaffing.net' -> '_at_arenastaffing_net' (the user-dir
    suffix every teammate's folder shares)."""
    owner_email = (owner_email or "").strip().lower()
    if "@" not in owner_email:
        return ""
    return "_at_" + owner_email.rsplit("@", 1)[1].replace(".", "_")


def owner_from_dir(dirname: str) -> str:
    """'michael_vaughn_at_arenastaffing_net' -> 'michael vaughn' style label."""
    local = dirname.rsplit("_at_", 1)[0] if "_at_" in dirname else dirname
    return " ".join(p.capitalize() for p in local.split("_") if p)


def _summarize(path: Path, owner_dir: str) -> dict | None:
    try:
        camp = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(camp, dict) or not is_outbound(camp):
        return None
    contacts = [c for c in (camp.get("contacts") or []) if isinstance(c, dict)]
    domains: dict = {}
    companies: Counter = Counter()
    for c in contacts:
        dom = email_domain(_contact_email(c))
        if dom:
            domains.setdefault(dom, _contact_company(c))
        if _contact_company(c):
            companies[_contact_company(c)] += 1
    if not domains:
        return None
    started = (camp.get("start_date") or "").strip()[:10]
    if not started:
        try:
            started = date.fromtimestamp(path.stat().st_mtime).isoformat()
        except Exception:
            started = ""
    company = ""
    if companies:
        company = companies.most_common(1)[0][0]
    company = (company or (camp.get("variables") or {}).get("CompanyName")
               or camp.get("name") or path.stem)
    return {
        "campaign": camp.get("name") or path.stem,
        "company": company,
        "domains": sorted(domains),
        "contacts": len(contacts),
        "owner_dir": owner_dir,
        "owner": owner_from_dir(owner_dir),
        "started": started,
        "status": (camp.get("status") or "active").strip().lower(),
        "path": str(path),
    }


def _campaign_files(users_root: Path, suffix: str):
    if not suffix or not users_root.is_dir():
        return
    for udir in users_root.iterdir():
        if not udir.is_dir() or not udir.name.endswith(suffix):
            continue
        cdir = udir / "Campaigns"
        if not cdir.is_dir():
            continue
        for f in cdir.glob("*.json"):
            if f.name == "responded.json":
                continue
            yield udir.name, f


def team_campaigns(users_root, owner_email: str, today: date | None = None,
                   window_days: int = WINDOW_DAYS) -> list:
    """Every outbound campaign the owner's team started within the window,
    newest first. Re-parses only files whose mtime changed."""
    users_root = Path(users_root)
    today = today or date.today()
    cutoff = (today - timedelta(days=window_days)).isoformat()
    out = []
    seen = set()
    for owner_dir, f in _campaign_files(users_root, team_suffix(owner_email)):
        key = str(f)
        seen.add(key)
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        with _cache_lock:
            hit = _cache.get(key)
        if hit and hit[0] == mtime:
            summary = hit[1]
        else:
            summary = _summarize(f, owner_dir)
            with _cache_lock:
                _cache[key] = (mtime, summary)
        if summary and summary["started"] >= cutoff:
            out.append(summary)
    with _cache_lock:
        for k in [k for k in _cache if k not in seen and k.startswith(str(users_root))]:
            _cache.pop(k, None)
    out.sort(key=lambda r: (r["started"], r["campaign"]), reverse=True)
    return out


def _same_path(a: str, b: str) -> bool:
    if not a or not b:
        return False
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except Exception:
        return a == b


def worked_domains(records: list, exclude_path: str = "",
                   exclude_name: str = "", exclude_owner_dir: str = "") -> dict:
    """domain -> the newest record that already covers it, leaving out the
    campaign being launched (matched by file path, or by name within the
    same owner's folder for campaigns not saved yet)."""
    hits: dict = {}
    for r in records:
        if _same_path(r["path"], exclude_path):
            continue
        if (exclude_name and r["campaign"] == exclude_name
                and (not exclude_owner_dir or r["owner_dir"] == exclude_owner_dir)):
            continue
        for d in r["domains"]:
            hits.setdefault(d, r)
    return hits


def match(domain: str, hits: dict) -> dict | None:
    """Subdomain-aware lookup: mail.acme.com matches a campaign at acme.com
    and vice versa."""
    if not domain:
        return None
    if domain in hits:
        return hits[domain]
    for d, r in hits.items():
        if domain.endswith("." + d) or d.endswith("." + domain):
            return r
    return None


def describe(rec: dict) -> str:
    """'Galloway & Company is already in Sarah Henze's campaign
    "Galloway & Company" (started 2026-10-05).'"""
    when = rec.get("started") or "recently"
    try:
        when = datetime.fromisoformat(when).strftime("%b %d").replace(" 0", " ")
    except Exception:
        pass
    status = " (cancelled)" if rec.get("status") == "cancelled" else ""
    return (f"{rec['company']} is already in {rec['owner']}'s campaign "
            f"\"{rec['campaign']}\"{status}, started {when}.")

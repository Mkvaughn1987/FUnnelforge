"""Shared Arena Contacts: everyone the team has ever reached, by company.

Walks every teammate's folder (same email domain) and merges, by email
address, the contacts in

  * every campaign file, all time: company outreach, newsletters and slow
    drips alike. Find Candidates campaigns email candidates, so they are
    left out;
  * every saved contact list (Contacts/*.csv): CSV uploads, "Add one
    contact", and the lists DripDrop writes when a campaign launches.

Two things take a person OUT of the bank, for everyone:

  * a reply that said no (matched on the same opt-out phrases the reply
    monitor uses: "not interested", "remove me", ...), read from each rep's
    responded.json;
  * any teammate's Do Not Contact list (bounces, opt-outs, manual adds).

Other replies are kept and flagged: a person who answered is the warmest
contact a teammate could reuse.

Pure file reads, no app imports, so it is unit-testable on its own and the
MCP server / API can call it the same way the page does.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
from collections import Counter
from datetime import date
from pathlib import Path

import team_campaigns as _tc

TEAM_LABEL = _tc.TEAM_LABEL
PAGE_TITLE = f"Shared {TEAM_LABEL} Contacts"

# Keep in step with flowdrip_app._OPT_OUT_KEYWORDS (the reply monitor's
# list). A reply carrying any of these is a "no" and the person leaves the
# bank.
NEGATIVE_REPLY_KEYWORDS = (
    "opt out", "opt-out", "optout", "unsubscribe", "remove me",
    "stop emailing", "stop sending", "take me off", "no more emails",
    "do not contact", "don't contact", "don't email", "do not email",
    "leave me alone", "not interested", "hate email", "spam",
    "remove from list", "remove from your list",
)

# Header spellings seen across campaign files, ZoomInfo exports and the
# app's own CSVs, folded to lower case with spaces/underscores removed.
_FIELDS = {
    "email": ("email", "emailaddress", "workemail"),
    "first_name": ("firstname", "first"),
    "last_name": ("lastname", "last"),
    "name": ("name", "fullname", "contactname"),
    "title": ("title", "jobtitle", "position"),
    "company": ("company", "companyname", "organization", "employer"),
    "phone_mobile": ("phonemobile", "mobilephone", "mobile", "cell", "cellphone"),
    "phone_office": ("phoneoffice", "workphone", "officephone", "directphone", "phone", "directline"),
    "linkedin": ("linkedin", "linkedinurl", "linkedinpage", "linkedinprofile"),
    "city": ("city",),
    "state": ("state", "region"),
}
_ALIAS = {alias: field for field, aliases in _FIELDS.items() for alias in aliases}

_cache: dict = {}            # path -> (mtime, parsed)
_cache_lock = threading.Lock()


def _fold(key: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(key or "")).lower()


def norm_contact(raw: dict) -> dict | None:
    """One contact in the bank's shape, or None when it has no email."""
    if not isinstance(raw, dict) or raw.get("removed"):
        return None
    out = {f: "" for f in _FIELDS}
    for k, v in raw.items():
        f = _ALIAS.get(_fold(k))
        if f and v and not out[f]:
            out[f] = str(v).strip()
    out["email"] = out["email"].lower()
    if "@" not in out["email"]:
        return None
    if not out["name"]:
        out["name"] = " ".join(p for p in (out["first_name"], out["last_name"]) if p)
    elif not out["first_name"] and " " in out["name"]:
        out["first_name"], out["last_name"] = out["name"].split(" ", 1)
    st = out["state"].strip()
    out["state"] = _tc.state_of(st) or (st.upper() if len(st) == 2 and st.isalpha() and st.upper() in _tc.US_STATES else "")
    out["domain"] = out["email"].rsplit("@", 1)[1]
    return out


def _is_negative(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in NEGATIVE_REPLY_KEYWORDS)


# ── per-file parsers (cached by mtime) ──────────────────────────────────

def _parse_campaign(path: Path, owner_dir: str) -> list:
    try:
        camp = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(camp, dict):
        return []
    if (camp.get("_chooser_origin") or "") == "candidate":
        return []
    kinds = {camp.get("aicb_camp_type"), camp.get("template_key"), camp.get("_chooser_origin")}
    if kinds & _tc.CANDIDATE_TYPES:
        return []
    started = (camp.get("start_date") or "").strip()[:10]
    if not started:
        try:
            started = date.fromtimestamp(path.stat().st_mtime).isoformat()
        except Exception:
            started = ""
    source = {"kind": "campaign", "name": camp.get("name") or path.stem,
              "owner_dir": owner_dir, "date": started,
              "industry": _tc.industry_of(camp),
              "state": _tc.resolve_state(camp, []),
              "newsletter": bool(camp.get("evergreen_only") or camp.get("newsletter_name"))}
    out = []
    for c in camp.get("contacts") or []:
        n = norm_contact(c)
        if n:
            out.append((n, source))
    return out


def _parse_list(path: Path, owner_dir: str) -> list:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        when = date.fromtimestamp(path.stat().st_mtime).isoformat()
    except Exception:
        return []
    source = {"kind": "list", "name": path.stem.replace("_", " ").strip() or "Contacts",
              "owner_dir": owner_dir, "date": when, "industry": "", "state": "",
              "newsletter": False}
    out = []
    try:
        for row in csv.DictReader(io.StringIO(text)):
            n = norm_contact(row)
            if n:
                out.append((n, source))
    except Exception:
        return []
    return out


def _parse_responded(path: Path, owner_dir: str) -> list:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        em = (r.get("email") or "").strip().lower()
        if "@" not in em:
            continue
        out.append({"email": em, "date": (r.get("date") or "")[:10],
                    "campaign": r.get("campaign") or "", "owner_dir": owner_dir,
                    "negative": _is_negative((r.get("subject") or "") + " " + (r.get("reply_body") or ""))})
    return out


def _parse_dnc(path: Path, owner_dir: str) -> list:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in rows if isinstance(rows, list) else []:
        em = (r.get("email") if isinstance(r, dict) else r) or ""
        em = str(em).strip().lower()
        if "@" in em:
            out.append({"email": em, "reason": (r.get("reason") if isinstance(r, dict) else "") or "Do Not Contact",
                        "owner_dir": owner_dir})
    return out


def _cached(path: Path, owner_dir: str, parser):
    key = str(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    with _cache_lock:
        hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    parsed = parser(path, owner_dir)
    with _cache_lock:
        _cache[key] = (mtime, parsed)
    return parsed


def _team_dirs(users_root: Path, owner_email: str):
    suffix = _tc.team_suffix(owner_email)
    if not suffix or not users_root.is_dir():
        return
    for udir in sorted(users_root.iterdir()):
        if udir.is_dir() and udir.name.endswith(suffix):
            yield udir


def team_dnc(users_root, owner_email: str) -> tuple:
    """(emails, domains) on ANY teammate's Do Not Contact list. Domain
    blocks are stored as "@acme.com" and come back as "acme.com". Used at
    send time so one rep's opt-out or bounce stops every rep."""
    return _team_dnc(Path(users_root), _tc.team_suffix(owner_email))


def team_dnc_for_dir(users_root, user_dir_name: str) -> tuple:
    """team_dnc for the scheduler, which knows a user's folder name
    ('mike_at_arena_net'), not their email."""
    if "_at_" not in (user_dir_name or ""):
        return set(), set()
    return _team_dnc(Path(users_root), "_at_" + user_dir_name.rsplit("_at_", 1)[1])


def _team_dnc(users_root: Path, suffix: str) -> tuple:
    emails, domains = set(), set()
    if not suffix or not users_root.is_dir():
        return emails, domains
    for udir in sorted(users_root.iterdir()):
        if not (udir.is_dir() and udir.name.endswith(suffix)):
            continue
        dnc = udir / "dnc_list.json"
        if dnc.is_file():
            for r in _cached(dnc, udir.name, _parse_dnc):
                if r["email"].startswith("@"):
                    # A rep blocking "@gmail.com" for themselves must not
                    # silence every personal address for the whole team.
                    if r["email"][1:] not in _tc.FREE_MAIL:
                        domains.add(r["email"][1:])
                else:
                    emails.add(r["email"])
    return emails, domains


# ── the bank ────────────────────────────────────────────────────────────

def scan(users_root, owner_email: str) -> dict:
    """{"contacts": [record...], "excluded": n, "reps": {owner_dir: label}}.
    A record is one person (by email) with every source that reached them."""
    users_root = Path(users_root)
    people: dict = {}
    replies: dict = {}
    blocked: dict = {}
    reps: dict = {}
    seen_paths = set()
    for udir in _team_dirs(users_root, owner_email):
        owner_dir = udir.name
        reps[owner_dir] = _tc.owner_from_dir(owner_dir)
        cdir = udir / "Campaigns"
        if cdir.is_dir():
            for f in cdir.glob("*.json"):
                seen_paths.add(str(f))
                if f.name == "responded.json":
                    for r in _cached(f, owner_dir, _parse_responded):
                        prev = replies.get(r["email"])
                        if not prev or r["date"] > prev["date"]:
                            replies[r["email"]] = r
                        if r["negative"]:
                            replies[r["email"]] = dict(replies[r["email"]], negative=True)
                    continue
                for n, src in _cached(f, owner_dir, _parse_campaign):
                    _merge(people, n, src)
        ldir = udir / "Contacts"
        if ldir.is_dir():
            for f in ldir.glob("*.csv"):
                seen_paths.add(str(f))
                for n, src in _cached(f, owner_dir, _parse_list):
                    _merge(people, n, src)
        dnc = udir / "dnc_list.json"
        if dnc.is_file():
            seen_paths.add(str(dnc))
            for r in _cached(dnc, owner_dir, _parse_dnc):
                blocked.setdefault(r["email"], r)
    with _cache_lock:
        for k in [k for k in _cache if k.startswith(str(users_root)) and k not in seen_paths]:
            _cache.pop(k, None)

    blocked_domains = {k[1:] for k in blocked if k.startswith("@")}
    out = []
    excluded = 0
    for em, rec in people.items():
        rep = replies.get(em)
        if em in blocked or rec["domain"] in blocked_domains:
            excluded += 1
            continue
        if rep and rep["negative"]:
            excluded += 1
            continue
        rec["replied"] = rep["date"] if rep else ""
        rec["reps"] = sorted(rec["reps"])
        rec["sources"].sort(key=lambda s: s["date"], reverse=True)
        rec["last_seen"] = rec["sources"][0]["date"] if rec["sources"] else ""
        rec["first_seen"] = rec["sources"][-1]["date"] if rec["sources"] else ""
        out.append(rec)
    out.sort(key=lambda r: (r["last_seen"], r["name"]), reverse=True)
    return {"contacts": out, "excluded": excluded, "reps": reps}


def _merge(people: dict, n: dict, src: dict) -> None:
    rec = people.get(n["email"])
    if rec is None:
        rec = dict(n)
        rec["reps"] = set()
        rec["sources"] = []
        people[n["email"]] = rec
    else:
        for f in _FIELDS:
            if not rec.get(f) and n.get(f):
                rec[f] = n[f]
    rec["reps"].add(src["owner_dir"])
    rec["sources"].append(src)


# ── companies ───────────────────────────────────────────────────────────

def _company_key(rec: dict) -> str:
    dom = rec["domain"]
    if dom in _tc.FREE_MAIL:
        return ("company:" + rec["company"].lower()) if rec["company"] else ("free:" + dom)
    return dom


def group_by_company(records: list) -> list:
    """One row per company with its contacts, newest touch first."""
    by_co: dict = {}
    for rec in records:
        key = _company_key(rec)
        row = by_co.setdefault(key, {"key": key, "contacts": [], "domains": set(),
                                     "reps": set(), "names": Counter(),
                                     "states": Counter(), "industries": Counter()})
        row["contacts"].append(rec)
        if rec["domain"] not in _tc.FREE_MAIL:
            row["domains"].add(rec["domain"])
        row["reps"].update(rec["reps"])
        if rec["company"]:
            row["names"][rec["company"]] += 1
        if rec["state"]:
            row["states"][rec["state"]] += 1
        for s in rec["sources"]:
            if s.get("industry") and s["industry"] != _tc.INDUSTRY_OTHER:
                row["industries"][s["industry"]] += 1
            if not rec["state"] and s.get("state"):
                row["states"][s["state"]] += 1
    rows = []
    for row in by_co.values():
        contacts = sorted(row["contacts"], key=lambda r: (bool(r["replied"]), r["last_seen"]), reverse=True)
        names = row["names"].most_common(1)
        company = names[0][0] if names else (sorted(row["domains"])[0] if row["domains"] else row["key"])
        rows.append({
            "key": row["key"],
            "company": company,
            "domains": sorted(row["domains"]),
            "contacts": contacts,
            "reps": sorted(row["reps"]),
            "state": row["states"].most_common(1)[0][0] if row["states"] else "",
            "industry": row["industries"].most_common(1)[0][0] if row["industries"] else _tc.INDUSTRY_OTHER,
            "last_seen": max(c["last_seen"] for c in contacts),
            "replied": sum(1 for c in contacts if c["replied"]),
        })
    rows.sort(key=lambda r: (r["last_seen"], r["company"].lower()), reverse=True)
    return rows


def filter_rows(rows: list, rep: str = "", state: str = "", industry: str = "",
                replied: str = "", q: str = "") -> list:
    q = (q or "").strip().lower()
    out = []
    for row in rows:
        if rep and rep not in row["reps"]:
            continue
        if state and row["state"] != state:
            continue
        if industry and row["industry"] != industry:
            continue
        if replied == "replied" and not row["replied"]:
            continue
        if q:
            hay = " ".join([row["company"], *row["domains"]] + [
                " ".join((c["name"], c["title"], c["email"], c["city"]))
                for c in row["contacts"]]).lower()
            if q not in hay:
                continue
        out.append(row)
    return out


def sort_rows(rows: list, how: str = "newest") -> list:
    if how == "most":
        return sorted(rows, key=lambda r: (-len(r["contacts"]), r["company"].lower()))
    if how == "name":
        return sorted(rows, key=lambda r: r["company"].lower())
    return sorted(rows, key=lambda r: (r["last_seen"], r["company"].lower()), reverse=True)


def lookup(records: list, query: str, limit: int = 50) -> list:
    """Companies matching a name or email domain, for the connector.
    Subdomain-aware on domains; case-insensitive substring on names."""
    q = (query or "").strip().lower().lstrip("@")
    if not q:
        return []
    q_dom = q
    if "://" in q_dom or "/" in q_dom:
        q_dom = re.sub(r"^\w+://", "", q_dom).split("/", 1)[0]
    q_dom = q_dom[4:] if q_dom.startswith("www.") else q_dom
    rows = group_by_company(records)
    hits = []
    for row in rows:
        dom_hit = any(d == q_dom or d.endswith("." + q_dom) or q_dom.endswith("." + d)
                      for d in row["domains"]) if "." in q_dom else False
        name_hit = q in row["company"].lower()
        if dom_hit or name_hit:
            hits.append(row)
    hits.sort(key=lambda r: (not any(d == q_dom for d in r["domains"]), -len(r["contacts"])))
    return [dict(r, contacts=r["contacts"][:limit]) for r in hits[:5]]


def contact_public(c: dict) -> dict:
    """The fields the API and CSV hand out for one person."""
    return {
        "name": c["name"], "first_name": c["first_name"], "last_name": c["last_name"],
        "title": c["title"], "email": c["email"], "company": c["company"],
        "phone_mobile": c["phone_mobile"], "phone_office": c["phone_office"],
        "linkedin": c["linkedin"], "city": c["city"], "state": c["state"],
        "reps": [_tc.owner_from_dir(d) for d in c["reps"]],
        "last_reached": c["last_seen"], "replied": c["replied"],
        "campaigns": [s["name"] for s in c["sources"] if s["kind"] == "campaign"][:5],
    }


def rows_csv(rows: list) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Company", "Name", "Title", "Email", "Mobile", "Office phone", "LinkedIn",
                "City", "State", "Reps", "Last reached", "Replied", "Campaigns"])
    for row in rows:
        for c in row["contacts"]:
            p = contact_public(c)
            w.writerow([row["company"], p["name"], p["title"], p["email"], p["phone_mobile"],
                        p["phone_office"], p["linkedin"], p["city"], p["state"],
                        ", ".join(p["reps"]), p["last_reached"], p["replied"],
                        "; ".join(p["campaigns"])])
    return buf.getvalue()


def facet_counts(rows: list, key: str) -> Counter:
    return _tc.facet_counts(rows, key)

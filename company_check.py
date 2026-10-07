"""Is a company fair game? The connector's answer before any research.

Two things rule a company out, both read from DripDrop's own records so the
AI never has to guess:

  * it is a Current Client (the team's client blocklist, matched by email
    domain or client name);
  * someone on the team already has it in an outbound campaign that started
    in the last 30 days, cancelled ones included (team_campaigns, the same
    records the launch guard in queue_campaign_emails uses).

Pure functions over data the caller loads, no app imports, so the API, the
MCP tools and the tests all call it the same way.
"""
from __future__ import annotations

import re

import team_campaigns as _tc

# Words that say nothing about which company it is.
_NOISE = frozenset({
    "the", "and", "inc", "incorporated", "llc", "l", "ltd", "limited", "co",
    "corp", "corporation", "company", "companies", "group", "plc", "lp",
    "llp", "pc", "pllc", "pa", "holdings",
})
_MIN_KEY = 4          # a shorter name key only matches exactly


def name_key(name: str) -> str:
    """'Galloway & Company, Inc.' -> 'galloway'."""
    s = (name or "").lower().replace("&", " and ")
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in _NOISE]
    return " ".join(words)


def query_domain(query: str) -> str:
    """The email domain in a query, or '' when it is a company name."""
    q = (query or "").strip().lower()
    if not q or " " in q:
        return ""
    if "@" in q:
        q = q.rsplit("@", 1)[1]
    q = re.sub(r"^\w+://", "", q).split("/", 1)[0].split("?", 1)[0]
    q = q[4:] if q.startswith("www.") else q
    q = q.strip(". ")
    return q if re.match(r"^[a-z0-9.\-]+\.[a-z]{2,}$", q) else ""


def _dom_match(a: str, b: str) -> bool:
    return bool(a and b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def _names_match(a: str, b: str) -> bool:
    """Same company by name: equal keys, or one whole-word inside the other
    when the shorter is long enough to mean something."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    if len(short) < _MIN_KEY:
        return False
    return re.search(r"(?:^| )" + re.escape(short) + r"(?: |$)", long_) is not None


def _label(domain: str) -> str:
    """'gallowayus.com' -> 'gallowayus'."""
    parts = (domain or "").split(".")
    return parts[-2] if len(parts) >= 2 else ""


def _matches(query: str, names, domains) -> bool:
    q_dom = query_domain(query)
    if q_dom:
        return any(_dom_match(q_dom, d) for d in domains if d)
    key = name_key(query)
    if not key:
        return False
    if any(_names_match(key, name_key(n)) for n in names if n):
        return True
    # "Galloway" against gallowayus.com: the bare name as the domain label.
    flat = key.replace(" ", "")
    return len(flat) >= _MIN_KEY and any(_label(d) == flat for d in domains if d)


def client_match(query: str, clients: list) -> dict | None:
    """The Current Clients entry this company is, or None. `clients` are
    blocklist entries ({domain, client_name, website, active})."""
    for e in clients or []:
        if not isinstance(e, dict) or not e.get("active", True):
            continue
        dom = query_domain(e.get("domain") or "")
        site = query_domain(e.get("website") or "")
        if _matches(query, [e.get("client_name") or ""], [dom, site]):
            return {"client_name": (e.get("client_name") or "").strip() or dom,
                    "domain": dom}
    return None


def worked_matches(query: str, records: list) -> list:
    """Team campaigns at this company, newest first (records come from
    team_campaigns.team_campaigns, already newest first)."""
    return [r for r in records or []
            if _matches(query, [r.get("company") or ""], r.get("domains") or [])]


def check(query: str, clients: list, records: list) -> dict:
    """One company's verdict: 'skip' with the reasons, or 'ok'."""
    client = client_match(query, clients)
    worked = worked_matches(query, records)
    already = None
    if worked:
        w = worked[0]
        already = {
            "company": w["company"], "rep": w["owner"], "campaign": w["campaign"],
            "started": w["started"], "status": w["status"],
            "opens_again": _tc.opens_on(w["started"]),
            "domains": w["domains"], "other_campaigns": len(worked) - 1,
        }
    reasons = []
    if client:
        reasons.append(f"{client['client_name']} is a Current Client.")
    if worked:
        why = _tc.describe(worked[0])
        if already["opens_again"]:
            why += f" It opens again on {already['opens_again']}."
        reasons.append(why)
    return {
        "query": query,
        "verdict": "skip" if reasons else "ok",
        "current_client": client,
        "already_worked": already,
        "reason": " ".join(reasons),
    }

"""My Top 10: each recruiter's own named target companies, with hiring
signals checked every time they open the page.

The list is private to one user (top_ten.json in their folder). Ten
companies are active, up to ten more sit in a backup rotation; promoting a
backup into a full ten sends the lowest active company to the top of the
backups so the count stays at ten.

Opening the page re-checks hiring signals for every active company whose
last check is older than SIGNAL_TTL_HOURS. Signals are the same "you can
see it from outside the company" list AI Prompts uses
(staffing_prompts.UNIVERSAL_SIGNALS), found with a web search and saved
back on the company so a second visit the same day costs nothing.

Pure file reads and writes, no app imports, so it is unit-testable on its
own; flowdrip_app owns the model call and the page.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

PAGE_TITLE = "My Top 10"
FILE_NAME = "top_ten.json"
ACTIVE_MAX = 10
BACKUP_MAX = 10
SIGNAL_TTL_HOURS = 24

STATUSES = ("Not started", "Campaign running", "Talking", "Client", "Paused")

_lock = threading.Lock()


# ── storage ─────────────────────────────────────────────────────────────

def path_for(user_dir) -> Path:
    return Path(user_dir) / FILE_NAME


def _blank() -> dict:
    return {"companies": [], "focus": {"market": "", "industry": ""}, "seeded": False}


def load(path) -> dict:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _blank()
    if not isinstance(data, dict) or not isinstance(data.get("companies"), list):
        return _blank()
    data["companies"] = [_clean(c) for c in data["companies"] if isinstance(c, dict)]
    data["companies"] = [c for c in data["companies"] if c["company"]]
    focus = data.get("focus") if isinstance(data.get("focus"), dict) else {}
    data["focus"] = {"market": str(focus.get("market") or "").strip(),
                     "industry": str(focus.get("industry") or "").strip()}
    data["seeded"] = bool(data.get("seeded"))
    return data


def save(path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with _lock:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)


def _clean(c: dict) -> dict:
    out = {
        "id": str(c.get("id") or uuid.uuid4().hex[:12]),
        "company": str(c.get("company") or "").strip(),
        "website": str(c.get("website") or "").strip(),
        "city": str(c.get("city") or "").strip(),
        "state": str(c.get("state") or "").strip().upper()[:2],
        "lane": str(c.get("lane") or "").strip(),
        "req": str(c.get("req") or "").strip(),
        "status": c.get("status") if c.get("status") in STATUSES else STATUSES[0],
        "notes": str(c.get("notes") or "").strip(),
        "tier": "backup" if c.get("tier") == "backup" else "active",
        "added": str(c.get("added") or ""),
        "source": "auto" if c.get("source") == "auto" else "manual",
        "why": str(c.get("why") or "").strip(),
        "signals": c.get("signals") if isinstance(c.get("signals"), list) else [],
        "jobs": c.get("jobs") if isinstance(c.get("jobs"), list) else [],
        # {"n", "query", "loc", "checked"} from the last Pipeline check.
        "pipeline": c.get("pipeline") if isinstance(c.get("pipeline"), dict) else {},
        "signal_summary": str(c.get("signal_summary") or ""),
        "signals_checked": str(c.get("signals_checked") or ""),
        "signals_error": str(c.get("signals_error") or ""),
        "signals_tried": str(c.get("signals_tried") or ""),
    }
    return out


# ── the list ────────────────────────────────────────────────────────────

def active(data: dict) -> list:
    return [c for c in data["companies"] if c["tier"] == "active"]


def backups(data: dict) -> list:
    return [c for c in data["companies"] if c["tier"] == "backup"]


def find(data: dict, cid: str) -> dict | None:
    return next((c for c in data["companies"] if c["id"] == cid), None)


def _norm_name(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    n = re.sub(r"\b(inc|llc|co|corp|corporation|company|ltd|the)\b", " ", n)
    return " ".join(n.split())


def add(data: dict, fields: dict, today: str = "") -> tuple:
    """(company, message). Lands in the top 10 while there is room, then in
    the backups; refuses a duplicate name or a full list."""
    c = _clean(dict(fields, id="", tier="active", signals=[], signals_checked=""))
    if not c["company"]:
        return None, "Add a company name."
    key = _norm_name(c["company"])
    if any(_norm_name(x["company"]) == key for x in data["companies"]):
        return None, f"{c['company']} is already on your list."
    if len(active(data)) < ACTIVE_MAX:
        c["tier"] = "active"
    elif len(backups(data)) < BACKUP_MAX:
        c["tier"] = "backup"
    else:
        return None, "Your top 10 and backup 10 are both full. Remove one first."
    c["added"] = today or datetime.now().date().isoformat()
    data["companies"].append(c)
    where = "your top 10" if c["tier"] == "active" else "your backups"
    return c, f"Added {c['company']} to {where}."


def update(data: dict, cid: str, fields: dict) -> dict | None:
    c = find(data, cid)
    if not c:
        return None
    for k in ("company", "website", "city", "state", "lane", "req", "status", "notes"):
        if k in fields:
            c[k] = _clean({**c, k: fields[k]})[k]
    c["source"] = "manual"          # edited by hand: it is theirs now
    return c


def remove(data: dict, cid: str) -> bool:
    before = len(data["companies"])
    data["companies"] = [c for c in data["companies"] if c["id"] != cid]
    return len(data["companies"]) < before


def move(data: dict, cid: str, step: int) -> None:
    """Swap a company one place up (-1) or down (+1) within its own tier."""
    c = find(data, cid)
    if not c:
        return
    tier = [x for x in data["companies"] if x["tier"] == c["tier"]]
    i = tier.index(c)
    j = i + step
    if not 0 <= j < len(tier):
        return
    a, b = data["companies"].index(tier[i]), data["companies"].index(tier[j])
    data["companies"][a], data["companies"][b] = data["companies"][b], data["companies"][a]


def promote(data: dict, cid: str) -> str:
    """Backup -> top 10. When the ten is full, the last active company
    drops to the head of the backups."""
    c = find(data, cid)
    if not c or c["tier"] != "backup":
        return ""
    bumped = ""
    act = active(data)
    if len(act) >= ACTIVE_MAX:
        last = act[-1]
        last["tier"] = "backup"
        data["companies"].remove(last)
        first_backup = next((i for i, x in enumerate(data["companies"]) if x["tier"] == "backup"),
                            len(data["companies"]))
        data["companies"].insert(first_backup, last)
        bumped = last["company"]
    c["tier"] = "active"
    data["companies"].remove(c)
    last_active = max((i for i, x in enumerate(data["companies"]) if x["tier"] == "active"),
                      default=-1)
    data["companies"].insert(last_active + 1, c)
    return (f"{c['company']} is in your top 10; {bumped} moved to backups."
            if bumped else f"{c['company']} is in your top 10.")


def demote(data: dict, cid: str) -> str:
    c = find(data, cid)
    if not c or c["tier"] != "active":
        return ""
    if len(backups(data)) >= BACKUP_MAX:
        return "Your backups are full. Remove one first."
    c["tier"] = "backup"
    data["companies"].remove(c)
    first_backup = next((i for i, x in enumerate(data["companies"]) if x["tier"] == "backup"),
                        len(data["companies"]))
    data["companies"].insert(first_backup, c)
    return f"{c['company']} moved to backups."


# ── hiring signals ──────────────────────────────────────────────────────

def is_stale(c: dict, now: datetime | None = None, ttl_hours: int = SIGNAL_TTL_HOURS) -> bool:
    if not c.get("signals_checked"):
        return True
    try:
        checked = datetime.fromisoformat(c["signals_checked"])
    except ValueError:
        return True
    return (now or datetime.now()) - checked >= timedelta(hours=ttl_hours)


RETRY_AFTER_FAIL_HOURS = 1


def due_for_signals(data: dict, now: datetime | None = None) -> list:
    """Top 10 companies whose signals are missing or older than the TTL.
    Backups are only checked when the user asks. A check that failed in
    the last hour waits, so a page refresh does not hammer the search."""
    now = now or datetime.now()
    out = []
    for c in active(data):
        if not is_stale(c, now):
            continue
        if c.get("signals_error") and not is_stale(
                {"signals_checked": c.get("signals_tried", "")}, now, RETRY_AFTER_FAIL_HOURS):
            continue
        out.append(c)
    return out


def signal_prompt(c: dict, signal_defs: list, today: str, focus: dict | None = None) -> str:
    where = ", ".join(p for p in (c["city"], c["state"]) if p)
    lines = "\n".join(f"- {s['id']}: {s['label']}" for s in signal_defs)
    focus = focus or {}
    facts = [f"Company: {c['company']}"]
    if focus.get("market") or focus.get("industry"):
        facts.append("Recruiter's desk: " + " ".join(
            p for p in (focus.get("market", ""), focus.get("industry", "")) if p)
            + " (weight openings and news in that market higher)")
    if c["website"]:
        facts.append(f"Website: {c['website']}")
    if where:
        facts.append(f"Location: {where}")
    if c["lane"]:
        facts.append(f"Industry / lane: {c['lane']}")
    if c["req"]:
        facts.append(f"Role the recruiter is targeting: {c['req']}")
    return (
        f"Today is {today}. A staffing recruiter is tracking this company as a "
        "target client and wants two things: the jobs it posted most recently, and "
        "any hiring signals.\n\n"
        + "\n".join(facts) + "\n\n"
        "Search the web for this exact company (check the location so you do not "
        "confuse it with a similarly named firm).\n\n"
        f"FIRST, find its job postings from the last {FRESH_DAYS} days. Check the "
        f"company's own careers page and its company page on Indeed and ZipRecruiter "
        f"(search '{c['company']} jobs' and '{c['company']} careers'). Job boards show "
        "'Posted 3 days ago' or a date; use that. A posting with no visible date is "
        "still worth listing, with age left empty: an undated posting beats an empty "
        "list. Newest first, up to 8.\n\n"
        "SECOND, look for these signals from the last 60 days:\n" + lines + "\n\n"
        "Only report what you actually found on a page the search returned. Never "
        "invent a posting, a date or a URL. If you find nothing, return empty lists.\n\n"
        "Reply with ONLY a JSON object, no prose before or after:\n"
        '{"summary": "<one plain sentence a recruiter can read in two seconds>", '
        '"jobs": [{"title": "<job title>", "location": "<city, state>", '
        '"age_days": <whole number of days since posted, or null when the page shows none>, '
        '"date": "<YYYY-MM-DD or empty>", "pay": "<posted pay or empty>", "url": "<posting url>"}], '
        '"signals": [{"id": "<signal id from the list>", "title": "<what you saw>", '
        '"detail": "<one short sentence>", "date": "<YYYY-MM-DD or empty>", "url": "<source url>"}]}'
    )


def _age_days(job: dict, today) -> int | None:
    """Days since posted: the board's 'N days ago' first, else the date."""
    a = job.get("age_days")
    if isinstance(a, (int, float)) and not isinstance(a, bool) and a >= 0:
        return int(a)
    d = str(job.get("date") or "").strip()[:10]
    if d:
        try:
            from datetime import date as _date
            return max(0, (today - _date.fromisoformat(d)).days)
        except ValueError:
            pass
    return None


def parse_signals(text: str, signal_defs: list, retrieved_urls: list | None = None,
                  today=None) -> dict:
    """{"summary", "jobs", "signals"} from the model's reply. Drops unknown
    signal ids and, when retrieved_urls is given, any url the search never
    returned. Jobs come back newest first."""
    known = {s["id"]: s["label"] for s in signal_defs}
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("no JSON in reply")
    raw = json.loads(m.group(0))
    hosts = None
    if retrieved_urls is not None:
        hosts = {_host(u) for u in retrieved_urls if u}
    today = today or datetime.now().date()

    def _url(u) -> str:
        u = str(u or "").strip()
        if u and hosts is not None and _host(u) not in hosts:
            return ""
        return u if u.startswith(("http://", "https://")) else ""

    jobs = []
    for j in raw.get("jobs") or []:
        if not isinstance(j, dict) or not str(j.get("title") or "").strip():
            continue
        jobs.append({
            "title": str(j.get("title") or "").strip()[:120],
            "location": str(j.get("location") or "").strip()[:80],
            "age_days": _age_days(j, today),
            "date": str(j.get("date") or "").strip()[:10],
            "pay": str(j.get("pay") or "").strip()[:60],
            "url": _url(j.get("url")),
        })
    jobs.sort(key=lambda j: (j["age_days"] is None, j["age_days"] or 0))
    out = []
    for s in raw.get("signals") or []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id") or "").strip()
        if sid not in known:
            continue
        out.append({
            "id": sid,
            "label": known[sid],
            "title": str(s.get("title") or "").strip()[:160],
            "detail": str(s.get("detail") or "").strip()[:300],
            "date": str(s.get("date") or "").strip()[:10],
            "url": _url(s.get("url")),
        })
    return {"summary": str(raw.get("summary") or "").strip()[:300],
            "jobs": jobs[:8], "signals": out}


FRESH_DAYS = 10

# Two-or-three-word chip text per signal id; the model's own title and
# detail sit behind the chip.
SIGNAL_SHORT = {
    "reposted": "Reposted / stale role", "urgent": "Urgent hire",
    "several": "Several openings", "agency": "Agency-posted",
    "leader": "Leadership seat open", "recruiter": "Hiring a recruiter",
    "expansion": "Expansion news", "reviews": "Turnover complaints",
}


def chip_text(sig: dict) -> str:
    return SIGNAL_SHORT.get(sig.get("id", ""), (sig.get("label") or sig.get("title") or "")[:28])


def fresh_jobs(c: dict, days: int = FRESH_DAYS) -> list:
    """The company's postings dated within `days`, newest first."""
    return [j for j in c.get("jobs") or []
            if j.get("age_days") is not None and j["age_days"] <= days]


def freshest(data: dict, days: int = FRESH_DAYS, limit: int = 12) -> list:
    """(company, job) across the top 10, newest first, for the page's
    'posted in the last N days' strip."""
    out = []
    for c in active(data):
        for j in fresh_jobs(c, days):
            out.append((c, j))
    out.sort(key=lambda cj: (cj[1]["age_days"], cj[0]["company"].lower()))
    return out[:limit]


def pipeline_query(c: dict) -> tuple:
    """(keywords, location) to look up the user's Pipeline for people who
    fit what this company is hiring: the newest posting's title first,
    else the first role the recruiter is targeting. The location is the
    company's city and state when both are known (a bare state does not
    geocode), else empty."""
    jobs = c.get("jobs") or []
    title = ""
    for j in fresh_jobs(c) + [j for j in jobs if j not in fresh_jobs(c)]:
        if j.get("title"):
            title = j["title"]
            break
    if not title:
        parts = [p.strip() for p in re.split(r"[,;/]| and ", c.get("req") or "") if p.strip()]
        title = parts[0] if parts else ""
    title = re.sub(r"[^\w\s-]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    loc = f"{c['city']}, {c['state']}" if c.get("city") and c.get("state") else ""
    return title, loc


def record_pipeline(c: dict, n: int, query: str, loc: str, now: datetime | None = None) -> None:
    c["pipeline"] = {"n": int(n), "query": query, "loc": loc,
                     "checked": (now or datetime.now()).isoformat(timespec="seconds")}


def short_roles(req: str, keep: int = 2) -> str:
    """'PM, Superintendent, APM, Senior PM, CM' -> 'PM, Superintendent +3'."""
    parts = [p.strip() for p in re.split(r"[,;/]| and ", req or "") if p.strip()]
    if len(parts) <= keep:
        return ", ".join(parts)
    return ", ".join(parts[:keep]) + f" +{len(parts) - keep}"


def _host(url: str) -> str:
    h = re.sub(r"^[a-z]+://", "", (url or "").strip().lower()).split("/")[0].split(":")[0]
    return h[4:] if h.startswith("www.") else h


def record_signals(c: dict, result: dict | None, error: str = "",
                   now: datetime | None = None) -> None:
    """Store a check on the company. A failed check keeps the last good
    signals and is retried on the next visit."""
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    c["signals_tried"] = stamp
    if result is not None:
        c["signals"] = result["signals"]
        c["jobs"] = result.get("jobs") or []
        c["signal_summary"] = result["summary"]
        c["signals_checked"] = stamp
        c["signals_error"] = ""
    else:
        c["signals_error"] = (error or "Check failed")[:200]


def apply_check(path, cid: str, result: dict | None, error: str = "",
                now: datetime | None = None) -> None:
    """Re-read the file and write one company's check, so edits the user
    made while the search ran are kept."""
    with _lock:
        data = load(path)
    c = find(data, cid)
    if not c:
        return
    record_signals(c, result, error, now)
    save(path, data)


# ── focus + auto-fill from the user's own outreach ─────────────────────

# Picking "Construction" as the focus means the whole trade family, not
# just the leftover "Construction" bucket in team_campaigns.INDUSTRIES.
CONSTRUCTION_FAMILY = frozenset({
    "Construction", "General Contracting", "Mechanical Contracting",
    "Electrical Contracting", "Healthcare Construction",
    "Data Center / Mission Critical",
})
SEED_WINDOW_DAYS = 180


def industry_matches(focus_industry: str, record_industry: str) -> bool:
    if not focus_industry:
        return True
    if focus_industry == "Construction":
        return record_industry in CONSTRUCTION_FAMILY
    return record_industry == focus_industry


def set_focus(data: dict, market: str, industry: str) -> None:
    data["focus"] = {"market": (market or "").strip(), "industry": (industry or "").strip()}


def rank_outreach(records: list, owner_dir: str, focus: dict, state_of,
                  reply_domains: dict | None = None) -> list:
    """The user's own outbound companies, best first: most replies, then
    most campaigns, then most people reached, then newest. records are
    team_campaigns summaries; state_of turns the focus market into a state
    code. Companies outside the focus market or industry are left out."""
    reply_domains = reply_domains or {}
    want_state = state_of(focus.get("market", "")) if focus.get("market") else ""
    by_co: dict = {}
    for r in records:
        if r.get("owner_dir") != owner_dir:
            continue
        if want_state and r.get("state") != want_state:
            continue
        if not industry_matches(focus.get("industry", ""), r.get("industry", "")):
            continue
        key = _norm_name(r.get("company", ""))
        if not key:
            continue
        row = by_co.setdefault(key, {"company": r["company"], "domains": set(), "campaigns": 0,
                                     "contacts": 0, "last": "", "state": r.get("state", ""),
                                     "industry": r.get("industry", ""), "roles": r.get("roles", ""),
                                     "geo": r.get("geo", "")})
        row["campaigns"] += 1
        row["contacts"] += int(r.get("contacts") or 0)
        row["domains"].update(r.get("domains") or [])
        if r.get("started", "") > row["last"]:
            row["last"] = r.get("started", "")
            row["roles"] = r.get("roles") or row["roles"]
            row["geo"] = r.get("geo") or row["geo"]
    for row in by_co.values():
        row["replies"] = sum(reply_domains.get(d, 0) for d in row["domains"])
    return sorted(by_co.values(), key=lambda r: (r["replies"], r["campaigns"], r["contacts"], r["last"]),
                  reverse=True)


def _city_of(geo: str) -> str:
    """'Denver, CO' -> 'Denver'; 'Colorado Front Range (Denver metro, CO)'
    and 'Denver / Henderson, CO' -> '' (a region, not a city)."""
    if "," not in geo:
        return ""
    head = geo.split(",", 1)[0].strip()
    if "(" in head or "/" in head or len(head) > 24 or not head:
        return ""
    return head


def _why(row: dict) -> str:
    bits = [f"{row['campaigns']} campaign{'s' if row['campaigns'] != 1 else ''}",
            f"{row['contacts']} people reached"]
    if row["replies"]:
        bits.insert(0, f"{row['replies']} repl{'ies' if row['replies'] != 1 else 'y'}")
    return "From your outreach: " + ", ".join(bits)


def fill_from_outreach(data: dict, ranked: list, today: str = "") -> int:
    """Fill open top-10 and backup spots from rank_outreach, skipping
    companies already on the list. Returns how many were added."""
    added = 0
    for row in ranked:
        if len(active(data)) >= ACTIVE_MAX and len(backups(data)) >= BACKUP_MAX:
            break
        city = _city_of(row.get("geo") or "")
        site = next((d for d in sorted(row["domains"])), "")
        c, _msg = add(data, {"company": row["company"], "website": site, "city": city,
                             "state": row["state"], "lane": row["industry"],
                             "req": row.get("roles", "")}, today)
        if c:
            c["source"] = "auto"
            c["why"] = _why(row)
            added += 1
    data["seeded"] = True
    return added


def needs_seed(data: dict) -> bool:
    """Auto-fill once, the first time the page opens on an empty list.
    After that the user owns it; the Fill button tops it up on request."""
    return not data["companies"] and not data.get("seeded")


# ── teammates' campaigns ───────────────────────────────────────────────

def campaign_hits(companies: list, team_records: list) -> dict:
    """company id -> newest team campaign (team_campaigns record) whose
    company name or email domain matches."""
    out = {}
    for c in companies:
        key = _norm_name(c["company"])
        site = _host(c["website"]) if c["website"] else ""
        best = None
        for r in team_records:
            hit = (key and _norm_name(r.get("company", "")) == key) or (
                site and any(d == site or d.endswith("." + site) for d in r.get("domains", [])))
            if hit and (best is None or r.get("started", "") > best.get("started", "")):
                best = r
        if best:
            out[c["id"]] = best
    return out

"""Companies (Table | Board) and the Sales Dashboard: the roll-up pages in
the sidebar's CRM and PERFORMANCE sections.

Neither page owns a record type. A company is whatever `_company_index`
makes of the user's contacts (company_id, then a verified CompanyDomain,
then the company name; never an email domain), and everything shown about it
is counted at read time from files the app already keeps: the contact lists,
the campaign records, the send queue, the responded log and the team's
Clients blocklist. Reload the page and it recomputes.

The one thing this module writes is the pipeline record: the stage a rep
chose for a company, the next step and a note. That lives with the Clients
blocklist in the team's shared dir, because a company won or lost is a team
fact, not a per-user one.

Design: docs/superpowers/specs/2026-09-24-sales-companies-pipeline-design.md,
docs/superpowers/specs/2026-09-25-sales-dashboard-design.md and
docs/superpowers/specs/2026-09-25-crm-section-and-board-view-design.md (the
Pipeline page folded into Companies as a view).
"""
import asyncio
import json
import re
import sys
from datetime import datetime, timedelta

from nicegui import ui


def _ff():
    """The already-loaded flowdrip_app module (as 'flowdrip_app' or '__main__').
    Never `import flowdrip_app` - the server runs it as __main__, so importing
    re-executes the whole app. Same rule ai_prompts.py and ats.py follow."""
    for name in ("flowdrip_app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_BASE_DATA_DIR") and hasattr(m, "C"):
            return m
    import flowdrip_app as m  # standalone/test fallback
    return m


# ── Stages ───────────────────────────────────────────────────────────────
#
# Order matters: it is the board's column order and the sort inside a
# stage filter. Prospect / Contacted / Replied are derived from what the
# send path recorded; Meeting / Proposal / Lost only exist when a rep says
# so; Client comes from the Clients blocklist and beats everything, because
# that list is what actually stops us emailing a customer.

STAGES = [
    ("prospect",  "Prospect"),
    ("contacted", "Contacted"),
    ("replied",   "Replied"),
    ("meeting",   "Meeting"),
    ("proposal",  "Proposal"),
    ("client",    "Client"),
    ("lost",      "Lost"),
]
STAGE_LABEL = dict(STAGES)
STAGE_ORDER = {k: i for i, (k, _l) in enumerate(STAGES)}
STAGE_KEYS = [k for k, _l in STAGES]

# Record fields a rep may set. Anything else in a POST body is dropped.
RECORD_FIELDS = ("stage", "next_step", "note")
# Stage moves kept per record ({"stage", "at", "by"}, oldest dropped).
HISTORY_CAP = 50
# Stages only a rep can set. The dashboard dates a move by the record's
# history, or by its updated_at for a record written before history existed.
MANUAL_STAGES = ("meeting", "proposal", "lost")
# Sales Dashboard thresholds (days).
STALE_NEXT_STEP_DAYS = 14
QUIET_DAYS = 30


# ── Industry ─────────────────────────────────────────────────────────────
#
# The table is grouped under these headlines. A list's own Industry column
# decides when it has one: its wording is folded into a headline here
# ("Commercial & Residential Construction" is Construction), and an industry
# no pattern knows keeps its own name. Most hand-built lists carry no
# Industry column at all, so the company name is read next ("Bridge
# Logistics"), then the campaigns and newsletters the company is in ("The
# Freight Desk, After Hours"). First match wins, so the order matters. The
# labels match the Newsletters page's headlines where the two overlap.

COMPANY_INDUSTRIES = (
    ("Logistics & Freight", r"logistic|freight|truck|transport|supply chain|warehous"
                            r"|\b3pl\b|shipping|cargo|drayage|intermodal|multimodal"),
    ("Agriculture & Food", r"agricultur|\bfood\b|\bfarm"),
    ("Manufacturing", r"manufactur|machin|\bcnc\b|aerospace|packag|fabricat"),
    ("Construction", r"construct|contractor|contracting|\bbuilders?\b|homebuild"
                     r"|roofing|plumbing|\bhvac\b|mechanical"),
    ("Civil & Infrastructure", r"\bcivil\b|utilit|infrastructure"),
    ("Architecture & Design", r"architect"),
    ("Healthcare", r"health|medical|hospital|pharma|clinic|dental"),
    ("Technology", r"software|technology|\btech\b|\bsaas\b|internet"),
    ("Accounting & Finance", r"accounting|financ|\bcpa\b|bookkeep|\bbank|insurance|wealth"),
    ("Property & Real Estate", r"property management|real estate|realty|\breit\b"),
    ("Energy", r"energy|\boil\b|\bgas\b|solar|renewable"),
    ("Staffing & Recruiting", r"staffing|recruit"),
)
INDUSTRY_OTHER = "Other"


def industry_label(text) -> str:
    """The headline some text points at, or "" when it points at none."""
    t = str(text or "").lower()
    if not t.strip():
        return ""
    for label, pat in COMPANY_INDUSTRIES:
        if re.search(pat, t):
            return label
    return ""


def company_industry(industry, name, campaign_hints=()) -> str:
    """The headline a company sits under: its Industry column, else its
    name, else what most of its campaigns are about, else Other."""
    raw = " ".join(str(industry or "").split())
    if raw:
        return industry_label(raw) or raw
    label = industry_label(name)
    if label:
        return label
    votes = {}
    for hint in campaign_hints or ():
        label = industry_label(hint)
        if label:
            votes[label] = votes.get(label, 0) + 1
    if votes:
        return sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return INDUSTRY_OTHER


def industry_groups(rows) -> list:
    """[(industry, [rows])] with the biggest industry first and Other last.
    Rows keep the order they came in."""
    groups = {}
    for r in rows:
        groups.setdefault(r.get("industry_group") or INDUSTRY_OTHER, []).append(r)
    return sorted(groups.items(), key=lambda kv: (
        kv[0] == INDUSTRY_OTHER, -len(kv[1]), kv[0].lower()))


# ── Pure helpers ─────────────────────────────────────────────────────────

def _norm_ts(val) -> str:
    """ISO-ish timestamps from three files, made comparable as strings.
    '2026-09-24 10:12' and '2026-09-24T10:12:00' both sort correctly."""
    v = str(val or "").strip()
    if not v:
        return ""
    return v[:19].replace(" ", "T")


def _email_domain(email) -> str:
    e = str(email or "").strip().lower()
    return e.rsplit("@", 1)[1] if "@" in e else ""


def _domain_is_client(domain: str, client_domains) -> bool:
    """Same rule the send path uses for the blocklist: the domain itself or
    any subdomain of it."""
    d = (domain or "").strip().lower()
    if not d:
        return False
    for cd in client_domains:
        cd = (cd or "").strip().lower()
        if cd and (d == cd or d.endswith("." + cd)):
            return True
    return False


def _client_since(domains, client_entries) -> str:
    """The earliest added_at among the active Clients entries any of the
    company's domains match; "" when none matches or none is dated."""
    stamps = []
    for ent in client_entries:
        cd = str(ent.get("domain") or "")
        if any(_domain_is_client(d, [cd]) for d in domains if d):
            stamps.append(_norm_ts(ent.get("added_at")))
    stamps = [t for t in stamps if t]
    return min(stamps) if stamps else ""


def derived_stage(sent: int, replies: int) -> str:
    if replies:
        return "replied"
    if sent:
        return "contacted"
    return "prospect"


def resolve_stage(derived: str, record_stage: str, is_client: bool):
    """(stage, basis). Client beats the rep's word beats the data.

    A manual stage below the derived one is kept on purpose: if a rep marks
    a company that replied as Prospect, that is their call. The page shows
    the derived stage next to it so the mismatch is visible."""
    if is_client:
        return "client", "client"
    rs = (record_stage or "").strip().lower()
    if rs in STAGE_LABEL:
        return rs, "manual"
    return derived, "derived"


def _merge_contacts(contacts, campaigns):
    """One contact per email across the saved lists and every campaign's
    enrolled contacts. The first record seen wins; later ones fill blanks.
    Contacts without an email are kept as they are (nothing to merge on)."""
    by_email = {}
    out = []
    for c in list(contacts or []) + [
            x for camp in (campaigns or []) for x in (camp.get("contacts") or [])
            if isinstance(x, dict)]:
        if not isinstance(c, dict):
            continue
        em = str(c.get("email", "") or "").strip().lower()
        if not em:
            out.append(dict(c))
            continue
        cur = by_email.get(em)
        if cur is None:
            cur = by_email[em] = dict(c)
            cur["email"] = em
            out.append(cur)
        else:
            for k, v in c.items():
                if not cur.get(k) and v:
                    cur[k] = v
    return out


def company_rollup(contacts, campaigns, queue, responded, clients, records):
    """Every company the user has a contact at, with what has happened to it.

    Returns a list of dicts sorted by last activity (newest first), then
    name. Pure apart from `_company_index`, which is the app's own identity
    rule; nothing here touches the filesystem, so the API and the pages
    share it and tests feed it fixtures."""
    ff = _ff()
    people = _merge_contacts(contacts, campaigns)
    idx = ff._company_index(people)
    companies = idx["companies"]

    email_key = {}
    for key, ent in companies.items():
        for c in ent["contacts"]:
            em = str(c.get("email", "") or "").strip().lower()
            if em:
                email_key[em] = key

    stats = {key: {"sent": 0, "pending": 0, "failed": 0, "last": "",
                   "first_sent": "", "first_reply": "",
                   "campaigns": set(), "replies": [], "replied_emails": set()}
             for key in companies}

    def _first(cur: str, ts: str) -> str:
        return ts if ts and (not cur or ts < cur) else cur

    for item in (queue or []):
        key = email_key.get(str(item.get("to") or "").strip().lower())
        if not key:
            continue
        st = stats[key]
        status = str(item.get("status") or "").strip().lower()
        name = str(item.get("campaign") or "").strip()
        if name:
            st["campaigns"].add(name)
        if status == "sent":
            st["sent"] += 1
            st["last"] = max(st["last"], _norm_ts(item.get("sent_at")))
            st["first_sent"] = _first(st["first_sent"], _norm_ts(item.get("sent_at")))
        elif status == "failed":
            st["failed"] += 1
            st["last"] = max(st["last"], _norm_ts(item.get("failed_at")))
        elif status == "pending":
            st["pending"] += 1

    # What each campaign is about, for a company whose list and name say
    # nothing: the niche the user picked, else the campaign's own name.
    camp_hint = {}
    for camp in (campaigns or []):
        if str(camp.get("status") or "") == "draft":
            continue
        name = str(camp.get("name") or "").strip()
        if not name:
            continue
        niche = str(camp.get("market_niche") or "")
        camp_hint[name] = niche if industry_label(niche) else name
        for c in (camp.get("contacts") or []):
            if not isinstance(c, dict):
                continue
            key = email_key.get(str(c.get("email", "") or "").strip().lower())
            if key:
                stats[key]["campaigns"].add(name)

    for rec in (responded or []):
        em = str(rec.get("email") or "").strip().lower()
        key = email_key.get(em)
        if not key:
            continue
        st = stats[key]
        st["replies"].append(rec)
        st["replied_emails"].add(em)
        st["last"] = max(st["last"], _norm_ts(rec.get("replied_at")))
        st["first_reply"] = _first(st["first_reply"], _norm_ts(rec.get("replied_at")))

    client_entries = [e for e in (clients or [])
                      if isinstance(e, dict) and e.get("active", True)]
    client_domains = [str(e.get("domain") or "") for e in client_entries]
    records = records if isinstance(records, dict) else {}

    rows = []
    for key, ent in companies.items():
        st = stats[key]
        doms = {ent.get("domain", "")} | {
            _email_domain(c.get("email")) for c in ent["contacts"]}
        is_client = any(_domain_is_client(d, client_domains) for d in doms if d)
        rec = records.get(key) or {}
        derived = derived_stage(st["sent"], len(st["replies"]))
        stage, basis = resolve_stage(derived, rec.get("stage", ""), is_client)
        replies = sorted(st["replies"], key=lambda r: _norm_ts(r.get("replied_at")),
                         reverse=True)
        co_name = ent.get("name") or ent.get("domain") or key.split(":", 1)[-1]
        rows.append({
            "key": key,
            "name": co_name,
            "domain": ent.get("domain", ""),
            "industry": ent.get("industry", ""),
            "industry_group": company_industry(
                ent.get("industry", ""), co_name,
                [camp_hint.get(n, n) for n in sorted(st["campaigns"])]),
            "company_size": ent.get("company_size", ""),
            "contacts": ent["contacts"],
            "contact_count": len(ent["contacts"]),
            "campaigns": sorted(st["campaigns"]),
            "sent": st["sent"], "pending": st["pending"], "failed": st["failed"],
            "replies": replies, "reply_count": len(replies),
            "replied_emails": st["replied_emails"],
            "last_activity": st["last"],
            "first_sent": st["first_sent"], "first_reply": st["first_reply"],
            "is_client": is_client,
            "client_since": _client_since(doms, client_entries) if is_client else "",
            "stage": stage, "stage_basis": basis, "derived_stage": derived,
            "next_step": str(rec.get("next_step") or ""),
            "note": str(rec.get("note") or ""),
            "record": rec,
        })
    rows.sort(key=lambda r: (r["last_activity"] == "", -_ts_sort(r["last_activity"]),
                             r["name"].lower()))
    return rows


def _ts_sort(ts: str) -> float:
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return 0.0


def board_companies(rollup):
    """The Pipeline shows companies something has happened to: in a campaign,
    or with a record a rep wrote. A board of 800 untouched list rows is noise;
    those stay on the Companies page."""
    return [r for r in rollup if r["campaigns"] or r["record"] or r["is_client"]]


def board_columns(rollup, cap: int = 40):
    """{stage: {"rows": [...], "total": n}} in stage order, each column
    capped for rendering; total says how many the cap hid."""
    cols = {k: {"rows": [], "total": 0} for k in STAGE_KEYS}
    for r in board_companies(rollup):
        col = cols[r["stage"]]
        col["total"] += 1
        if len(col["rows"]) < cap:
            col["rows"].append(r)
    return cols


def filter_rollup(rollup, q: str = "", stage: str = "", industry: str = ""):
    q = (q or "").strip().lower()
    stage = (stage or "").strip().lower()
    industry = (industry or "").strip().lower()
    out = []
    for r in rollup:
        if stage and r["stage"] != stage:
            continue
        if industry and (r.get("industry_group") or "").lower() != industry:
            continue
        if q and q not in r["name"].lower() and q not in (r["domain"] or "").lower():
            continue
        out.append(r)
    return out


def public_row(r: dict) -> dict:
    """The connector's view of a company: counts and stage, no contact dump."""
    return {
        "key": r["key"], "name": r["name"], "domain": r["domain"],
        "industry": r["industry"],
        "industry_group": r.get("industry_group") or INDUSTRY_OTHER,
        "company_size": r["company_size"],
        "contacts": r["contact_count"], "campaigns": r["campaigns"],
        "sent": r["sent"], "scheduled": r["pending"], "replies": r["reply_count"],
        "last_activity": r["last_activity"], "is_client": r["is_client"],
        "stage": r["stage"], "stage_basis": r["stage_basis"],
        "next_step": r["next_step"], "note": r["note"],
    }


# ── Acting on a selection ────────────────────────────────────────────────

# What a person carries into a newsletter or a new campaign: who they are
# and their firmographics. The roll-up merges in each campaign's own copy of
# a contact, and that copy holds that campaign's state (removed, completed),
# which must not follow them into the next one.
_CONTACT_KEEP = ("email", "first_name", "last_name", "name", "company", "title",
                 "phone_mobile", "phone_office", "linkedin", "city", "state")


def _clean_contact(c: dict) -> dict:
    keep = _CONTACT_KEEP + tuple(getattr(_ff(), "_TARGETING_KEYS", {}).values())
    out = {k: c[k] for k in keep if c.get(k) not in (None, "")}
    out["email"] = str(c.get("email") or "").strip().lower()
    return out


def selected_contacts(rollup, keys) -> list:
    """The people at the picked companies, one per email address, in the
    order the page lists them. A person with no email is left out: neither
    a newsletter nor a campaign can reach them."""
    keys = set(keys or ())
    seen, out = set(), []
    for r in rollup:
        if r["key"] not in keys:
            continue
        for c in r["contacts"]:
            em = str(c.get("email") or "").strip().lower()
            if not em or em in seen:
                continue
            seen.add(em)
            out.append(_clean_contact(c))
    return out


def running_newsletters() -> list:
    """Newsletters that can take someone new: running, with an issue still
    to come. A paused or ended one would queue nothing."""
    ff = _ff()
    out = []
    for c in ff.load_campaigns():
        if not (c.get("evergreen_only") and c.get("market_analysis")):
            continue
        if str(c.get("status") or "active").strip().lower() != "active":
            continue
        try:
            if ff._is_evergreen_completed(c):
                continue
        except Exception:
            continue
        out.append(c)
    return sorted(out, key=lambda c: str(c.get("name") or "").lower())


def enroll_contacts(contacts, camp_name: str) -> dict:
    """Add people to a running newsletter through the app's own enrol call,
    the one the Replies page and the connector use, so Do Not Contact,
    people already on it and the queue are handled the same way.
    Returns {status: count}."""
    ff = _ff()
    camp = next((c for c in ff.load_campaigns()
                 if c.get("name") == camp_name), None)
    if camp is None:
        raise ValueError(f"no newsletter named {camp_name!r}")
    tally = {}
    for c in contacts or []:
        st = ff.enroll_contact_in_evergreen(dict(c), camp)
        tally[st] = tally.get(st, 0) + 1
    try:
        ff._cache_campaigns.invalidate()
    except Exception:
        pass
    return tally


def enroll_many(contacts, camp: dict) -> dict:
    """enroll_contact_in_evergreen for a whole selection at once.

    Same checks in the same order (no email, Do Not Contact, a newsletter
    with nothing left to send, already on it / taken off it / finished it),
    but the newsletter is saved and the queue written once for everybody
    instead of once per person. Returns {status: count}."""
    ff = _ff()
    tally = {}

    def _bump(k):
        tally[k] = tally.get(k, 0) + 1
    on_it = {}
    for c in camp.get("contacts", []) or []:
        if isinstance(c, dict):
            on_it[str(c.get("email") or "").strip().lower()] = c
    completed = ff._is_evergreen_completed(camp)
    new = []
    for c in contacts or []:
        em = str(c.get("email") or "").strip().lower()
        if not em:
            _bump("skipped_no_email"); continue
        if ff.is_on_dnc(em):
            _bump("skipped_dnc"); continue
        if completed:
            _bump("campaign_completed"); continue
        cur = on_it.get(em)
        if cur is not None:
            _bump("skipped_removed" if cur.get("removed") else
                  "skipped_completed" if cur.get("completed") else
                  "skipped_duplicate")
            continue
        c = dict(c, email=em)
        on_it[em] = c
        new.append(c)
    if new:
        camp.setdefault("contacts", []).extend(new)
        camp["contact_count"] = len([c for c in camp["contacts"]
                                     if isinstance(c, dict) and not c.get("removed")])
        start = ff._evergreen_start_step_for_enrollee(camp)
        temp = __import__("copy").deepcopy(camp)
        temp["contacts"] = list(new)
        ff.queue_campaign_emails(temp, start_step=start)
        ff.save_campaign(camp)
        try:
            ff._cache_campaigns.invalidate()
        except Exception:
            pass
        tally["enrolled"] = len(new)
    return tally


def enroll_summary(tally: dict, camp_name: str) -> str:
    """One line saying what the add did, and who was left out and why."""
    def _n(n, one, many):
        return f"{n} {one if n == 1 else many}"
    added = tally.get("enrolled", 0)
    parts = [f"Added {_n(added, 'contact', 'contacts')} to '{camp_name}'."
             if added else f"Nobody new was added to '{camp_name}'."]
    already = (tally.get("skipped_duplicate", 0) + tally.get("skipped_completed", 0))
    if already:
        parts.append(f"{_n(already, 'was', 'were')} already on it.")
    dnc = tally.get("skipped_dnc", 0)
    if dnc:
        parts.append(f"{_n(dnc, 'is', 'are')} on your Do Not Contact list.")
    removed = tally.get("skipped_removed", 0)
    if removed:
        parts.append(f"{_n(removed, 'was', 'were')} taken off it before.")
    if tally.get("campaign_completed", 0):
        parts.append("It has no issues left to send.")
    return " ".join(parts)


# The Companies page hands its picked people to whichever campaign the user
# goes on to build: the next Choose Contacts screen opens with them loaded.
# Two hours is plenty to write a campaign and short enough that an
# abandoned pick doesn't turn up in some unrelated campaign next week.
PENDING_TTL = timedelta(hours=2)


def set_pending(s, contacts, label: str) -> None:
    s._co_pending = {"contacts": [dict(c) for c in contacts or []],
                     "label": label or "",
                     "at": datetime.now().isoformat(timespec="seconds")}


def _take_pending(s):
    p = getattr(s, "_co_pending", None)
    if not isinstance(p, dict) or not p.get("contacts"):
        return None
    s._co_pending = None
    try:
        age = datetime.now() - datetime.fromisoformat(str(p.get("at")))
    except Exception:
        return None
    return p if age <= PENDING_TTL else None


def _pending_note(p) -> None:
    n = len(p["contacts"])
    try:
        ui.notify(f"{n} contact{'s' if n != 1 else ''} from Companies"
                  + (f" ({p['label']})" if p.get("label") else "")
                  + " are loaded. Change them here if you like.",
                  type="positive", timeout=6000)
    except Exception:
        pass


def apply_pending_to_campaign(s, camp: dict) -> bool:
    """Load the picked people into a campaign that has nobody yet. A
    campaign that already has contacts, or is running, is left alone and
    the pick waits for the next one."""
    if not isinstance(camp, dict) or camp.get("contacts"):
        return False
    if str(camp.get("status") or "draft").strip().lower() not in ("draft", ""):
        return False
    p = _take_pending(s)
    if not p:
        return False
    camp["contacts"] = [dict(c) for c in p["contacts"]]
    camp["contact_count"] = len(camp["contacts"])
    camp["contact_emails"] = [c.get("email", "") for c in camp["contacts"]]
    _pending_note(p)
    return True


def apply_pending_to_wizard(s) -> bool:
    """The same, for the classic wizard's Choose Contacts step (s.scon)."""
    if getattr(s, "scon", None):
        return False
    p = _take_pending(s)
    if not p:
        return False
    s.scon = [dict(c) for c in p["contacts"]]
    _pending_note(p)
    return True


def newsletter_sector_key(industry: str) -> str:
    """The New Newsletter dialog's sector for an industry headline, or ""."""
    ff = _ff()
    sectors = (getattr(ff, "_TM_NEWSLETTER_SECTORS", {}) if getattr(ff, "_SALES_MODE", False)
               else getattr(ff, "AICB_INDUSTRIES", {}))
    want = (industry or "").strip().lower()
    for k, v in (sectors or {}).items():
        lbl = str((v or {}).get("label") or "").strip().lower()
        if lbl and (lbl == want or industry_label(lbl) == industry):
            return k
    return ""


# ── Sales Dashboard numbers ──────────────────────────────────────────────

FUNNEL_KEYS = [k for k in STAGE_KEYS if k != "lost"]
WINDOW_TILES = [
    ("contacted", "Newly contacted"),
    ("replied",   "New replies"),
    ("moved",     "Moved to Meeting / Proposal"),
    ("won",       "Won"),
    ("lost",      "Lost"),
]
ATTENTION_LISTS = [
    ("replies_waiting", "Replies waiting",
     "Someone answered and nobody has set a stage or a next step."),
    ("stale_next_steps", "Stale next steps",
     f"A next step nobody has touched in {STALE_NEXT_STEP_DAYS} days."),
    ("going_quiet", "Going quiet",
     f"At Meeting or Proposal with nothing sent or received in {QUIET_DAYS} days."),
]


def _cutoff(now: datetime, days) -> str:
    """ISO cutoff for a window of `days`; "" means no cutoff (all time)."""
    if not days:
        return ""
    return (now - timedelta(days=int(days))).isoformat(timespec="seconds")


def _in_window(ts: str, cutoff: str) -> bool:
    """Undated records are inside every window, the rule the analytics page
    uses: a row that silently vanishes is one nobody notices is missing."""
    if not cutoff:
        return True
    ts = _norm_ts(ts)
    return not ts or ts >= cutoff


def _moves(r: dict):
    """(stage, at) for every stage move recorded on the company. A record
    written before history existed yields its current manual stage once,
    dated by updated_at, so a company moved back then still shows."""
    rec = r.get("record") or {}
    hist = [h for h in (rec.get("history") or []) if isinstance(h, dict)]
    if hist:
        return [(str(h.get("stage") or ""), _norm_ts(h.get("at"))) for h in hist]
    st = str(rec.get("stage") or "").strip().lower()
    if st in MANUAL_STAGES:
        return [(st, _norm_ts(rec.get("updated_at")))]
    return []


def dashboard_stats(rollup, days, now=None) -> dict:
    """Everything the Sales Dashboard shows, from the roll-up alone.

    funnel: companies at each stage or beyond (Lost excluded), with each
    step's share of the previous one. Not windowed: it is the book as it
    stands. window: the five tiles for the last `days` days (None = all
    time). attention: the three "needs a hand" lists, also not windowed."""
    now = now or datetime.now()
    cutoff = _cutoff(now, days)
    board = board_companies(rollup)

    live = [r for r in board if r["stage"] != "lost"]
    funnel, prev = [], None
    for k in FUNNEL_KEYS:
        n = sum(1 for r in live if STAGE_ORDER[r["stage"]] >= STAGE_ORDER[k])
        rate = (n / prev) if prev else None
        funnel.append({"key": k, "label": STAGE_LABEL[k], "count": n, "rate": rate})
        prev = n
    lost = sum(1 for r in board if r["stage"] == "lost")
    won = funnel[-1]["count"]
    win_rate = (won / (won + lost)) if (won + lost) else None

    window = {k: [] for k, _l in WINDOW_TILES}
    for r in board:
        if r["first_sent"] and _in_window(r["first_sent"], cutoff):
            window["contacted"].append(r)
        if r["first_reply"] and _in_window(r["first_reply"], cutoff):
            window["replied"].append(r)
        moves = _moves(r)
        if any(st in ("meeting", "proposal") and _in_window(at, cutoff) for st, at in moves):
            window["moved"].append(r)
        if any(st == "lost" and _in_window(at, cutoff) for st, at in moves):
            window["lost"].append(r)
        if r["is_client"] and _in_window(r.get("client_since", ""), cutoff):
            window["won"].append(r)

    stale_before = _cutoff(now, STALE_NEXT_STEP_DAYS)
    quiet_before = _cutoff(now, QUIET_DAYS)
    attention = {k: [] for k, _l, _d in ATTENTION_LISTS}
    for r in board:
        rec = r.get("record") or {}
        if r["stage"] == "replied" and r["stage_basis"] == "derived" and not r["next_step"]:
            attention["replies_waiting"].append(r)
        if r["next_step"]:
            touched = _norm_ts(rec.get("updated_at"))
            if touched and touched < stale_before:
                attention["stale_next_steps"].append(r)
        if r["stage"] in ("meeting", "proposal"):
            last = _norm_ts(r["last_activity"])
            if not last or last < quiet_before:
                attention["going_quiet"].append(r)

    return {"days": days, "funnel": funnel, "lost": lost, "win_rate": win_rate,
            "window": window, "attention": attention}


def public_dashboard(stats: dict) -> dict:
    """The connector's view: the same numbers, rows through public_row."""
    return {
        "days": stats["days"],
        "funnel": stats["funnel"], "lost": stats["lost"], "win_rate": stats["win_rate"],
        "window": {k: [public_row(r) for r in v] for k, v in stats["window"].items()},
        "attention": {k: [public_row(r) for r in v] for k, v in stats["attention"].items()},
        "thresholds": {"stale_next_step_days": STALE_NEXT_STEP_DAYS,
                       "quiet_days": QUIET_DAYS},
    }


# ── Pipeline records (team-scoped) ───────────────────────────────────────

def _pipeline_path(email=None):
    return _ff()._team_dir(email) / "sales_pipeline.json"


def load_pipeline(email=None) -> dict:
    p = _pipeline_path(email)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_pipeline_record(key: str, fields: dict, actor: str, email=None,
                         name: str = "") -> dict:
    """Merge `fields` into the company's record and write the file
    atomically. A blank stage removes the manual stage so the company goes
    back to its derived one. A record left with nothing in it is deleted."""
    key = str(key or "").strip()
    if not key:
        raise ValueError("company key required")
    email = email or actor
    data = load_pipeline(email)
    rec = dict(data.get(key) or {})
    stage_before = str(rec.get("stage") or "")
    for f in RECORD_FIELDS:
        if f not in (fields or {}):
            continue
        v = str(fields.get(f) or "").strip()
        if f == "stage":
            v = v.lower()
            if v and v not in STAGE_LABEL:
                raise ValueError(f"unknown stage {v!r}; one of {', '.join(STAGE_KEYS)}")
        if v:
            rec[f] = v
        else:
            rec.pop(f, None)
    if name:
        rec["name"] = name
    now_ts = datetime.now().isoformat(timespec="seconds")
    if "stage" in (fields or {}) and str(rec.get("stage") or "") != stage_before:
        # A move, including back to auto (""). The dashboard's "moved" and
        # "lost" tiles are dated from these; a note edit is not a move.
        hist = [h for h in (rec.get("history") or []) if isinstance(h, dict)]
        hist.append({"stage": str(rec.get("stage") or ""), "at": now_ts,
                     "by": actor or ""})
        rec["history"] = hist[-HISTORY_CAP:]
    if any(rec.get(f) for f in RECORD_FIELDS):
        rec["updated_at"] = now_ts
        rec["updated_by"] = actor or ""
        data[key] = rec
    else:
        data.pop(key, None)
        rec = {}
    p = _pipeline_path(email)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)
    return rec


# ── Loading the sources for a user ───────────────────────────────────────

def rollup_for_user(email: str) -> list:
    """The roll-up for one signed-in user, from their files and the team's.
    The pages and the connector both come through here."""
    ff = _ff()
    email = (email or "").strip().lower()
    if email:
        ff._CURRENT_USER_EMAIL.set(email)
    contacts = list(ff.load_contacts())
    try:
        for _name, path in ff.list_saved_contact_lists().items():
            contacts += ff.load_contacts(path)
    except Exception:
        pass
    campaigns = ff.load_campaigns()
    queue = ff._load_queue()
    responded = ff.load_responded()
    clients = ff._load_client_blocklist_raw(email)
    records = load_pipeline(email)
    return company_rollup(contacts, campaigns, queue, responded, clients, records)


# ── UI ───────────────────────────────────────────────────────────────────

def _fmt_when(ts: str) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromisoformat(ts).strftime("%b %d")
    except Exception:
        return ts[:10]


def _stage_badge(C, r):
    col = {"client": C["good"], "replied": C["good"], "lost": C["muted"],
           "prospect": C["muted"]}.get(r["stage"], C["teal"])
    with ui.element("span").style(
            f"display:inline-flex;align-items:center;gap:6px;padding:3px 10px;"
            f"border-radius:99px;font-size:11px;font-weight:600;white-space:nowrap;"
            f"color:{col};border:1px solid {col};"):
        ui.label(STAGE_LABEL[r["stage"]])
        if r["stage_basis"] == "manual" and r["derived_stage"] != r["stage"] \
                and STAGE_ORDER[r["derived_stage"]] > STAGE_ORDER[r["stage"]]:
            ui.label(f"· {STAGE_LABEL[r['derived_stage']].lower()}").style(
                f"color:{C['muted']};font-weight:500;")


def _stage_select(s, rf, r, actor, on_saved=None, dense=True):
    """Stage picker that writes the record on change. 'Auto' clears the
    manual stage. Client is read-only here: the Clients page decides that."""
    ff = _ff()
    C = ff.C
    if r["is_client"]:
        ui.label("Client (from the Clients list)").style(
            f"font-size:12px;color:{C['good']};")
        return
    opts = {"": f"Auto ({STAGE_LABEL[r['derived_stage']]})"}
    opts.update({k: l for k, l in STAGES if k != "client"})
    cur = r["record"].get("stage", "") if r["stage_basis"] == "manual" else ""

    def _pick(e):
        try:
            save_pipeline_record(r["key"], {"stage": e.value or ""}, actor,
                                 name=r["name"])
            ui.notify(f"{r['name']}: {opts.get(e.value or '', 'Auto')}", type="positive")
        except Exception as ex:
            ui.notify(f"Could not save the stage: {ex}", type="negative")
        if on_saved:
            on_saved()
        rf()

    sel = ui.select(options=opts, value=cur, on_change=_pick).classes("fd-input")
    if dense:
        sel.props("dense").style("min-width:170px;font-size:12px;")
    else:
        sel.style("width:100%;")
    return sel


def _page_head(s, rf, C, title, help_key, subtitle):
    with ui.element("div").style(
            "display:flex;align-items:flex-start;justify-content:space-between;"
            "gap:16px;margin-bottom:6px;"):
        with ui.element("div").style("flex:1;min-width:0;"):
            with ui.element("div").style("display:flex;align-items:center;"):
                ui.label(title).classes("fd-h1")
                _ff()._show_page_help(s, rf, help_key)
            ui.label(subtitle).classes("fd-sub")


def _empty_card(C, headline, body, cta_label=None, cta=None):
    # .fd-es is the app-wide empty-state component (flowdrip_app._polish_css).
    with ui.element("div").classes("fd-es wide").style("margin-top:16px;"):
        ui.label(headline).classes("fd-es-title")
        ui.label(body).classes("fd-es-body").style("max-width:60ch;")
        if cta_label and cta:
            with ui.element("div").classes("fd-es-actions"):
                with ui.element("button").classes("fd-pb").props('type="button"').on("click", cta):
                    ui.label(cta_label)


def _go(s, rf, page_key, came_from=""):
    ff = _ff()
    ff._sidebar_nav(s, rf, page_key, ff._sidebar_setup_status(),
                    came_from=came_from)


def _co_back_link(s, rf, C):
    """Companies is a sidebar page, so it gets no history Back. When you
    drilled in from the Sales Dashboard or a board card, say so and offer
    the way back."""
    came = getattr(s, "_came_from", "") or ""
    if came == "sales_dashboard":
        label = "← Back to Sales Dashboard"

        def _back():
            s._co_open = ""
            s._co_stage = ""
            _go(s, rf, "sales_dashboard")
    elif came == "companies_board":
        label = "← Back to the board"

        def _back():
            s._came_from = ""
            s._co_open = ""
            s._co_stage = ""
            s._co_view = "board"
            rf()
    else:
        return
    with ui.element("div").classes("fd-back-bar"):
        with ui.element("button").classes("fd-back-btn").on("click", _back):
            ui.label(label)


def p_companies(s, rf):
    ff = _ff()
    C = ff.C
    actor = (getattr(s, "_user_email", "") or "").strip().lower()
    rollup = rollup_for_user(actor)
    q = getattr(s, "_co_q", "") or ""
    stage = getattr(s, "_co_stage", "") or ""
    industry = getattr(s, "_co_ind", "") or ""
    open_key = getattr(s, "_co_open", "") or ""
    view = "board" if getattr(s, "_co_view", "") == "board" else "table"
    if view == "board" and getattr(s, "_came_from", "") == "companies_board":
        s._came_from = ""   # already back on the board

    _co_back_link(s, rf, C)
    _page_head(s, rf, C, "Companies", "companies",
               "Every company you have a contact at, grouped by industry, with "
               "what your campaigns have done there. Tick companies to add "
               "their people to a newsletter or start a campaign for them. "
               "Board lays the ones a campaign has touched out by stage.")

    if not rollup:
        _empty_card(C, "No companies yet",
                    "Companies appear here as soon as your contacts have a "
                    "company name. Upload a list to get started.",
                    "Go to Contacts", lambda: _go(s, rf, "contacts"))
        return

    n_camp = sum(1 for r in rollup if r["campaigns"])
    n_rep = sum(1 for r in rollup if r["reply_count"])
    n_cli = sum(1 for r in rollup if r["is_client"])
    with ui.element("div").classes("fd-stat-strip").style("margin:14px 0 14px;"):
        for val, lbl, col in [
            (str(len(rollup)), "Companies",    C["text_l"]),
            (str(n_camp),      "In campaigns", C["teal"] if n_camp else C["muted"]),
            (str(n_rep),       "Replied",      C["good"] if n_rep else C["muted"]),
            (str(n_cli),       "Clients",      C["good"] if n_cli else C["muted"]),
        ]:
            with ui.element("div").classes("fd-stat-cell" + (" zero" if val == "0" else "")):
                ui.label(val).classes("fd-sn").style(f"color:{col};")
                ui.label(lbl).classes("fd-sl")

    # ── Filters ──
    # .fd-filters keeps the fields at their own widths on one line (the page
    # wrapper otherwise stretches every q-field to 100%).
    with ui.element("div").classes("fd-filters").style("margin-bottom:12px;"):
        def _on_q(e):
            s._co_q = e.value or ""
            rf()
        ui.input(placeholder="Search company or domain", value=q,
                 on_change=_on_q).classes("fd-input").props(
            'dense clearable debounce="300"').style("width:260px;")
        stage_opts = {"": "All stages"}
        stage_opts.update({k: l for k, l in STAGES})

        def _on_stage(e):
            s._co_stage = e.value or ""
            rf()
        if view == "table":
            ui.select(options=stage_opts, value=stage, on_change=_on_stage).classes(
                "fd-input").props("dense").style("min-width:160px;font-size:12px;")
        ind_opts = {"": "All industries"}
        ind_opts.update({g: f"{g} ({len(rs)})" for g, rs in industry_groups(rollup)})
        if industry and industry not in ind_opts:
            industry = s._co_ind = ""

        def _on_ind(e):
            s._co_ind = e.value or ""
            rf()
        ui.select(options=ind_opts, value=industry, on_change=_on_ind).classes(
            "fd-input").props("dense").style("min-width:190px;font-size:12px;")
        # Table | Board toggle. The board used to be its own Pipeline page;
        # every CRM the market uses (Apollo, Close, Pipedrive) makes it a
        # view of the one list instead, so it lives here now.
        with ui.element("div").classes("fd-seg").style("margin-left:auto;"):
            for _v, _vl in (("table", "Table"), ("board", "Board")):
                def _pick_view(v=_v):
                    s._co_view = v
                    rf()
                with ui.element("button").classes(
                        "fd-seg-btn" + (" on" if _v == view else "")).props(
                        'type="button"').on("click", _pick_view):
                    ui.label(_vl)

    if view == "board":
        _board(s, rf, C, filter_rollup(rollup, q, "", industry), actor)
        return

    rows = filter_rollup(rollup, q, stage, industry)
    if not rows:
        _empty_card(C, "No companies match",
                    "Try a shorter search, another stage or another industry.")
        return
    shown = rows[:200]
    live = {r["key"] for r in rollup}
    sel = [k for k in (getattr(s, "_co_sel", None) or ()) if k in live]
    s._co_sel = sel
    sel_set = set(sel)

    def _set_sel(keys, on):
        cur = [k for k in (s._co_sel or ())]
        if on:
            cur += [k for k in keys if k not in set(cur)]
        else:
            drop = set(keys)
            cur = [k for k in cur if k not in drop]
        s._co_sel = cur
        rf()

    def _tri(keys):
        """True / False / None (some) for a checkbox over these keys."""
        n = sum(1 for k in keys if k in sel_set)
        return True if keys and n == len(keys) else (False if not n else None)

    _selection_bar(s, rf, C, rollup, rows, sel, _set_sel, _tri)

    def _toggle(key):
        s._co_open = "" if open_key == key else key
        rf()

    groups = industry_groups(shown)
    with ui.element("div").style(
            f"border:1px solid {C['border']};border-radius:10px;overflow:hidden;"
            f"background:{C['card']};"):
        with ui.element("table").classes("fd-tbl fd-co-tbl"):
            with ui.element("thead"):
                with ui.element("tr"):
                    with ui.element("th").style("width:44px;padding-right:0;"):
                        ui.checkbox(value=_tri([r["key"] for r in rows]),
                                    on_change=lambda e, ks=[r["key"] for r in rows]:
                                        _set_sel(ks, bool(e.value))).props(
                            'dense aria-label="Select every company listed"')
                    for h in ("Company", "Contacts", "Campaigns", "Sent",
                              "Replies", "Last activity", "Stage"):
                        with ui.element("th"):
                            ui.label(h)
            with ui.element("tbody"):
              for g_name, g_rows in groups:
                g_keys = [r["key"] for r in g_rows]
                g_people = sum(r["contact_count"] for r in g_rows)
                # One header row per industry, with its own select-all.
                with ui.element("tr").classes("fd-co-group"):
                    with ui.element("td").style("padding-right:0;"):
                        ui.checkbox(value=_tri(g_keys),
                                    on_change=lambda e, ks=g_keys: _set_sel(ks, bool(e.value))
                                    ).props(f'dense aria-label="Select every {g_name} company"')
                    with ui.element("td").props('colspan="7"'):
                        with ui.element("div").style(
                                "display:flex;align-items:baseline;gap:10px;"):
                            ui.label(g_name).style(
                                f"font-size:13px;font-weight:700;color:{C['text_l']};")
                            ui.label(f"{len(g_rows)} compan{'ies' if len(g_rows) != 1 else 'y'}"
                                     f" · {g_people} contact{'s' if g_people != 1 else ''}"
                                     ).style(f"font-size:12px;color:{C['muted']};")
                for r in g_rows:
                    is_open = r["key"] == open_key
                    with ui.element("tr").classes("fd-co-row" + (" on" if r["key"] in sel_set else "")):
                        with ui.element("td").style("padding-right:0;"):
                            ui.checkbox(value=r["key"] in sel_set,
                                        on_change=lambda e, k=r["key"]: _set_sel([k], bool(e.value))
                                        ).props(f'dense aria-label="Select {r["name"]}"')
                        with ui.element("td"):
                            with ui.element("div").style(
                                    "display:flex;flex-direction:column;cursor:pointer;"
                                    ).on("click", lambda k=r["key"]: _toggle(k)):
                                ui.label(r["name"]).style(
                                    f"font-weight:600;color:{C['text_l']};")
                                sub = r["domain"] or r["industry"]
                                if sub:
                                    ui.label(sub).style(
                                        f"font-size:11px;color:{C['muted']};")
                        with ui.element("td"):
                            ui.label(str(r["contact_count"]))
                        with ui.element("td"):
                            _n = len(r["campaigns"])
                            _el = ui.label(str(_n)).style(
                                f"color:{C['teal'] if _n else C['muted']};")
                            if _n:
                                _el.tooltip(", ".join(r["campaigns"][:8]))
                        with ui.element("td"):
                            ui.label(str(r["sent"]) + (
                                f" (+{r['pending']} scheduled)" if r["pending"] else ""))
                        with ui.element("td"):
                            ui.label(str(r["reply_count"])).style(
                                f"color:{C['good'] if r['reply_count'] else C['muted']};")
                        with ui.element("td"):
                            ui.label(_fmt_when(r["last_activity"]))
                        with ui.element("td"):
                            # The picker sits in the row so a move is one
                            # click, the convenience the board had.
                            _stage_select(s, rf, r, actor)
                            if r["stage_basis"] == "manual" and r["derived_stage"] != r["stage"] \
                                    and STAGE_ORDER[r["derived_stage"]] > STAGE_ORDER[r["stage"]]:
                                ui.label(f"data says {STAGE_LABEL[r['derived_stage']].lower()}").style(
                                    f"font-size:10px;color:{C['muted']};margin-top:2px;")
                    if is_open:
                        with ui.element("tr"):
                            with ui.element("td").props('colspan="8"').style(
                                    f"background:{C['surface']};padding:16px 18px;"):
                                _company_detail(s, rf, C, r, actor)
    if len(rows) > len(shown):
        ui.label(f"Showing {len(shown)} of {len(rows)}. Narrow it with the search box.").style(
            f"font-size:11px;color:{C['muted']};margin-top:8px;")


def _selection_bar(s, rf, C, rollup, rows, sel, set_sel, tri):
    """Select all, what is selected, and what to do with it."""
    row_keys = [r["key"] for r in rows]
    picked = [r for r in rollup if r["key"] in set(sel)]
    people = selected_contacts(rollup, sel)
    with ui.element("div").classes("fd-co-selbar" + (" on" if sel else "")):
        ui.checkbox(f"Select all {len(rows)}" + (" shown" if len(rows) != len(rollup) else ""),
                    value=tri(row_keys),
                    on_change=lambda e: set_sel(row_keys, bool(e.value))).props("dense")
        if not sel:
            ui.label("Pick companies to add their people to a newsletter or a "
                     "new campaign.").style(f"font-size:12px;color:{C['muted']};")
            return
        ui.label(f"{len(picked)} compan{'ies' if len(picked) != 1 else 'y'} selected · "
                 f"{len(people)} contact{'s' if len(people) != 1 else ''} with an email"
                 ).style(f"font-size:13px;font-weight:600;color:{C['text_l']};")
        with ui.element("div").style("display:flex;gap:8px;margin-left:auto;flex-wrap:wrap;"):
            def _clear():
                s._co_sel = []
                rf()
            with ui.element("button").classes("fd-gb").props('type="button"').style(
                    "padding:7px 14px;font-size:12px;").on("click", _clear):
                ui.label("Clear")
            off = "" if people else " disabled"
            with ui.element("button").classes("fd-gb").props(f'type="button"{off}').style(
                    "padding:7px 14px;font-size:12px;").on(
                    "click", lambda: _newsletter_dialog(s, rf, C, picked, people)):
                ui.label("Add to newsletter")
            with ui.element("button").classes("fd-pb").props(f'type="button"{off}').style(
                    "padding:7px 16px;font-size:12px;").on(
                    "click", lambda: _campaign_dialog(s, rf, C, picked, people)):
                ui.label("Start a campaign")


def _pick_label(picked) -> str:
    """'Logistics & Freight' when every pick is in one industry, else
    '12 companies'."""
    inds = {r.get("industry_group") or INDUSTRY_OTHER for r in picked}
    if len(inds) == 1 and INDUSTRY_OTHER not in inds:
        return next(iter(inds))
    return f"{len(picked)} compan{'ies' if len(picked) != 1 else 'y'}"


def _newsletter_dialog(s, rf, C, picked, people):
    """Add the picked people to a running newsletter, or start a new one
    with them on it."""
    ff = _ff()
    owner = (getattr(s, "_user_email", "") or "").strip().lower()
    nls = running_newsletters()
    label = _pick_label(picked)
    with ui.dialog() as dlg, ui.card().style(
            f"background:{C['card']};border:1px solid {C['border']};"
            f"width:520px;max-width:94vw;padding:22px 24px;"):
        ui.label("Add to a newsletter").style(
            f"font-size:17px;font-weight:800;color:{C['text_l']};"
            f"font-family:'Nunito',sans-serif;")
        ui.label(f"{len(people)} contact{'s' if len(people) != 1 else ''} at "
                 f"{len(picked)} compan{'ies' if len(picked) != 1 else 'y'} will get "
                 "every issue still to come. Anyone already on it, or on your "
                 "Do Not Contact list, is skipped.").style(
            f"font-size:12px;color:{C['muted']};line-height:1.5;margin:4px 0 14px;")
        opts = {}
        for c in nls:
            n_on = len([x for x in c.get("contacts") or []
                        if isinstance(x, dict) and not x.get("removed")])
            opts[c.get("name", "")] = f"{c.get('name', '')}  ·  {n_on} on it"
        opts["__new__"] = "+ Start a new newsletter for them"
        if not nls:
            ui.label("You have no running newsletters yet.").style(
                f"font-size:12px;color:{C['text']};margin-bottom:6px;")
        radio = ui.radio(opts, value=(next(iter(opts)) if nls else "__new__")).props(
            "dense").style(f"color:{C['text_l']};")
        status = ui.label("").style(f"font-size:12px;color:{C['muted']};margin-top:8px;")
        busy = {"on": False}

        async def _add():
            if busy["on"]:
                return
            pick = radio.value
            if pick == "__new__":
                dlg.close()

                def _created(camp):
                    t = enroll_many(people, camp)
                    ui.notify(enroll_summary(t, camp.get("name", "")),
                              type="positive", timeout=7000)
                    s._co_sel = []
                ff._create_newsletter_dialog(
                    s, rf, on_created=_created,
                    prefill={"name": f"{label} Newsletter",
                             "sector_key": newsletter_sector_key(label)})
                return
            camp = next((c for c in running_newsletters() if c.get("name") == pick), None)
            if camp is None:
                ui.notify("That newsletter is gone. Pick another.", type="warning")
                return
            busy["on"] = True
            status.text = f"Adding {len(people)} contacts…"
            done = {}

            def _run():
                try:
                    done["t"] = enroll_many(people, camp)
                except Exception as ex:
                    print(f"[Companies] newsletter add failed: {type(ex).__name__}: {ex}",
                          flush=True)
                    done["err"] = str(ex)
            ff._run_as_user(owner, _run, name="companies_newsletter_add")
            while not done:
                await asyncio.sleep(0.3)
            busy["on"] = False
            if "err" in done:
                status.text = "That didn't work. Nothing was added; try again."
                return
            ui.notify(enroll_summary(done["t"], pick), type="positive", timeout=7000)
            s._co_sel = []
            dlg.close()
            rf()

        with ui.element("div").style(
                "display:flex;justify-content:flex-end;gap:8px;margin-top:14px;"):
            with ui.element("button").classes("fd-gb").props('type="button"').style(
                    "padding:7px 14px;font-size:12px;").on("click", dlg.close):
                ui.label("Cancel")
            with ui.element("button").classes("fd-pb").props('type="button"').style(
                    "padding:7px 18px;font-size:12px;").on("click", _add):
                ui.label("Add them")
    dlg.open()


def _campaign_dialog(s, rf, C, picked, people):
    """Start a campaign for the picked people: a ready-made one or your
    own. Either way they are loaded on its Choose Contacts step."""
    ff = _ff()
    label = _pick_label(picked)
    with ui.dialog() as dlg, ui.card().style(
            f"background:{C['card']};border:1px solid {C['border']};"
            f"width:640px;max-width:94vw;padding:24px 26px;"):
        ui.label("Start a campaign").style(
            f"font-size:18px;font-weight:800;color:{C['text_l']};"
            f"font-family:'Nunito',sans-serif;")
        ui.label(f"For {len(people)} contact{'s' if len(people) != 1 else ''} at "
                 f"{len(picked)} compan{'ies' if len(picked) != 1 else 'y'}. They'll be "
                 "loaded when you reach Choose Contacts, so you can still change "
                 "them there.").style(
            f"font-size:12px;color:{C['muted']};line-height:1.5;margin:4px 0 16px;")

        def _go(kind):
            set_pending(s, people, label)
            s._co_sel = []
            dlg.close()
            if kind == "custom":
                ff._open_custom_campaign(s, rf)
            else:
                ff._sidebar_nav(s, rf, "start_seq", ff._sidebar_setup_status(), fresh=True)

        cards = (
            ("ready", "Use a ready-made campaign",
             "Pick one of our campaigns, like Standard Outreach or Quick Intro, "
             "and it's written for you.", "Choose a campaign"),
            ("custom", "Build a Custom Campaign",
             "Your steps, your words, and a little AI help when you ask.",
             "Build a custom campaign"),
        )
        with ui.element("div").classes("fd-side-start-grid"):
            for key, title, desc, cta in cards:
                card = ui.element("div").classes("fd-side-start-card").props(
                    'role="button" tabindex="0"')
                card.on("keydown.enter", lambda k=key: _go(k))
                with card.on("click", lambda k=key: _go(k)):
                    with ui.element("div").classes("fd-side-start-head"):
                        ui.label(title).classes("fd-side-start-title")
                    ui.label(desc).classes("fd-side-start-desc")
                    with ui.element("div").classes("fd-side-start-go"):
                        ui.label(cta + " →")
    dlg.open()


def _company_detail(s, rf, C, r, actor):
    with ui.element("div").style("display:grid;grid-template-columns:1.4fr 1fr;gap:18px;"):
        # ── Left: people + campaigns + latest reply ──
        with ui.element("div").style("min-width:0;"):
            ui.label("People").style(
                f"font-size:11px;font-weight:700;letter-spacing:.06em;"
                f"text-transform:uppercase;color:{C['muted']};margin-bottom:6px;")
            for c in r["contacts"][:25]:
                em = str(c.get("email", "") or "").strip().lower()
                nm = f"{c.get('first_name', '') or ''} {c.get('last_name', '') or ''}".strip() or em
                with ui.element("div").style(
                        "display:flex;align-items:baseline;gap:8px;padding:4px 0;"
                        f"border-bottom:1px solid {C['border']};"):
                    ui.label(nm).style(f"font-size:13px;color:{C['text_l']};font-weight:600;")
                    if c.get("title"):
                        ui.label(str(c["title"])).style(f"font-size:12px;color:{C['muted']};")
                    if em:
                        ui.label(em).style(
                            f"font-size:11px;color:{C['muted']};margin-left:auto;")
                    if em in r["replied_emails"]:
                        ui.label("replied").classes("fd-badge replied")
            if r["contact_count"] > 25:
                ui.label(f"+{r['contact_count'] - 25} more on the Contacts page").style(
                    f"font-size:11px;color:{C['muted']};margin-top:4px;")

            if r["campaigns"]:
                ui.label("Campaigns").style(
                    f"font-size:11px;font-weight:700;letter-spacing:.06em;"
                    f"text-transform:uppercase;color:{C['muted']};margin:14px 0 6px;")
                with ui.element("div").style("display:flex;flex-wrap:wrap;gap:6px;"):
                    for name in r["campaigns"]:
                        ui.label(name).classes("fd-badge active")

            if r["replies"]:
                latest = r["replies"][0]
                ui.label("Latest reply").style(
                    f"font-size:11px;font-weight:700;letter-spacing:.06em;"
                    f"text-transform:uppercase;color:{C['muted']};margin:14px 0 6px;")
                ui.label(f"{latest.get('name') or latest.get('email', '')} · "
                         f"{_fmt_when(_norm_ts(latest.get('replied_at')))}"
                         + (f" · {latest.get('campaign')}" if latest.get("campaign") else "")
                         ).style(f"font-size:12px;color:{C['text_l']};font-weight:600;")
                body = (latest.get("reply_body") or "").strip()
                if body:
                    ui.label(body[:400] + ("…" if len(body) > 400 else "")).style(
                        f"font-size:12px;color:{C['muted']};white-space:pre-wrap;")

        # ── Right: pipeline card ──
        with ui.element("div").style(
                f"background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:10px;padding:14px 16px;"):
            ui.label("Pipeline").style(
                f"font-size:11px;font-weight:700;letter-spacing:.06em;"
                f"text-transform:uppercase;color:{C['muted']};margin-bottom:8px;")
            ui.label("Stage").classes("fd-fl")
            _stage_select(s, rf, r, actor, dense=False)
            ui.label("Next step").classes("fd-fl").style("margin-top:10px;")
            _next = ui.input(placeholder="e.g. Send the proposal Friday",
                             value=r["next_step"]).classes("fd-input").style("width:100%;")
            ui.label("Note").classes("fd-fl").style("margin-top:10px;")
            _note = ui.textarea(placeholder="Anything the team should know",
                                value=r["note"]).classes("fd-input").props(
                "autogrow").style("width:100%;")

            def _save():
                try:
                    save_pipeline_record(
                        r["key"], {"next_step": _next.value or "", "note": _note.value or ""},
                        actor, name=r["name"])
                    ui.notify("Saved", type="positive")
                except Exception as ex:
                    ui.notify(f"Could not save: {ex}", type="negative")
                rf()
            with ui.element("div").style("display:flex;gap:8px;margin-top:12px;"):
                with ui.element("button").classes("fd-pb").style(
                        "padding:8px 14px;font-size:12px;").on("click", _save):
                    ui.label("Save")
                def _see_board():
                    s._co_view = "board"
                    s._co_open = ""
                    rf()
                with ui.element("button").classes("fd-gb").style(
                        "padding:8px 14px;font-size:12px;").on("click", _see_board):
                    ui.label("See on the board")

                def _close():
                    # Clicking the name again also closes it, but nothing
                    # on screen said so.
                    s._co_open = ""
                    rf()
                with ui.element("button").classes("fd-gb").style(
                        "padding:8px 14px;font-size:12px;margin-left:auto;").on(
                        "click", _close):
                    ui.label("Close")
            rec = r["record"]
            if rec.get("updated_at"):
                ui.label(f"Updated {_fmt_when(_norm_ts(rec['updated_at']))}"
                         + (f" by {rec['updated_by']}" if rec.get("updated_by") else "")
                         ).style(f"font-size:11px;color:{C['muted']};margin-top:8px;")


def _board(s, rf, C, rollup, actor):
    """The Board view of Companies: the companies a campaign has touched,
    one column per stage. Was the Pipeline page until 2026-09-25."""
    cols = board_columns(rollup)
    show_lost = bool(getattr(s, "_pl_show_lost", False))

    total = sum(c["total"] for c in cols.values())
    if not total:
        _empty_card(C, "Nothing on the board yet",
                    "Companies land here once they are in a campaign. Launch "
                    "one, or switch to Table and set a stage by hand.")
        return

    def _open_company(r):
        s._co_open = r["key"]
        s._co_q = ""
        s._co_stage = ""
        s._co_view = "table"
        s._came_from = "companies_board"
        rf()

    with ui.element("div").style(
            "display:flex;gap:12px;align-items:flex-start;overflow-x:auto;"
            "padding-bottom:8px;"):
        for k, lbl in STAGES:
            col = cols[k]
            collapsed = (k == "lost" and not show_lost)
            with ui.element("div").style(
                    f"flex:0 0 {'150px' if collapsed else '230px'};min-width:0;"
                    f"background:{C['surface']};border:1px solid {C['border']};"
                    f"border-radius:10px;padding:10px;"):
                with ui.element("div").style(
                        "display:flex;align-items:center;justify-content:space-between;"
                        "margin-bottom:8px;padding:0 2px;"):
                    ui.label(lbl).style(
                        f"font-size:12px;font-weight:700;letter-spacing:.04em;"
                        f"text-transform:uppercase;color:{C['text_l']};")
                    ui.label(str(col["total"])).style(
                        f"font-size:11px;color:{C['muted']};font-weight:600;")
                if collapsed:
                    def _show_lost():
                        s._pl_show_lost = True
                        rf()
                    with ui.element("button").classes("fd-gb").style(
                            "padding:6px 10px;font-size:11px;width:100%;").on(
                            "click", _show_lost):
                        ui.label("Show")
                    continue
                if not col["rows"]:
                    ui.label("—").style(
                        f"font-size:12px;color:{C['muted']};text-align:center;padding:10px 0;")
                for r in col["rows"]:
                    with ui.element("div").style(
                            f"background:{C['card']};border:1px solid {C['border']};"
                            f"border-radius:8px;padding:10px 12px;margin-bottom:8px;"):
                        ui.label(r["name"]).style(
                            f"font-size:13px;font-weight:700;color:{C['text_l']};"
                            f"cursor:pointer;line-height:1.3;").on(
                            "click", lambda _r=r: _open_company(_r))
                        meta = [f"{r['contact_count']} contact{'s' if r['contact_count'] != 1 else ''}"]
                        if r["reply_count"]:
                            meta.append(f"{r['reply_count']} repl{'ies' if r['reply_count'] != 1 else 'y'}")
                        if r["last_activity"]:
                            meta.append(_fmt_when(r["last_activity"]))
                        ui.label(" · ".join(meta)).style(
                            f"font-size:11px;color:{C['muted']};margin:2px 0 6px;")
                        if r["next_step"]:
                            ui.label("Next: " + r["next_step"]).style(
                                f"font-size:11px;color:{C['teal']};margin-bottom:6px;")
                        _stage_select(s, rf, r, actor)
                if col["total"] > len(col["rows"]):
                    def _see_rest(stage=k):
                        s._co_stage = stage
                        s._co_view = "table"
                        s._came_from = "companies_board"
                        rf()
                    ui.label(f"+{col['total'] - len(col['rows'])} more in the table").style(
                        f"font-size:11px;color:{C['teal']};text-align:center;"
                        f"padding:4px 0;cursor:pointer;").on("click", _see_rest)


# ── Sales Dashboard page ─────────────────────────────────────────────────

def _company_link(s, rf, C, r, meta: str = ""):
    """One clickable company line: name, muted meta, stage badge."""
    def _open():
        s._co_open = r["key"]
        s._co_q = ""
        s._co_stage = ""
        s._co_view = "table"      # the opened row only shows in the table
        _go(s, rf, "companies", came_from="sales_dashboard")
    with ui.element("div").style(
            f"display:flex;align-items:center;gap:10px;padding:8px 0;"
            f"border-bottom:1px solid {C['border']};"):
        with ui.element("div").style("flex:1;min-width:0;cursor:pointer;").on("click", _open):
            ui.label(r["name"]).style(
                f"font-size:13px;font-weight:600;color:{C['text_l']};"
                f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;")
            if meta:
                ui.label(meta).style(f"font-size:11px;color:{C['muted']};")
        _stage_badge(C, r)


def _section_title(C, text, top=20):
    ui.label(text).style(
        f"font-size:14px;font-weight:700;color:{C['text_l']};"
        f"font-family:'Nunito',sans-serif;margin:{top}px 0 8px;")


def _row_meta(r) -> str:
    bits = [f"{r['contact_count']} contact{'s' if r['contact_count'] != 1 else ''}"]
    if r["reply_count"]:
        bits.append(f"{r['reply_count']} repl{'ies' if r['reply_count'] != 1 else 'y'}")
    if r["last_activity"]:
        bits.append("last " + _fmt_when(r["last_activity"]))
    return " · ".join(bits)


def p_sales_dashboard(s, rf):
    ff = _ff()
    C = ff.C
    actor = (getattr(s, "_user_email", "") or "").strip().lower()
    days = getattr(s, "_sd_days", 30)
    if days not in (7, 30, None):
        days = 30
    pick = getattr(s, "_sd_pick", "") or ""
    stats = dashboard_stats(rollup_for_user(actor), days)

    # ── Header + window picker ──
    with ui.element("div").style(
            "display:flex;align-items:flex-start;justify-content:space-between;"
            "gap:16px;margin-bottom:6px;"):
        with ui.element("div").style("flex:1;min-width:0;"):
            with ui.element("div").style("display:flex;align-items:center;"):
                ui.label("Sales Dashboard").classes("fd-h1")
                ff._show_page_help(s, rf, "sales_dashboard")
            ui.label("Where the business stands, by company: how the funnel "
                     "converts, what moved recently and who is waiting on you. "
                     "Counted from the same lists, sends and replies as "
                     "Companies.").classes("fd-sub")
        with ui.element("div").classes("fd-seg").style("flex-shrink:0;"):
            for _win, _wlbl in [(7, "7 days"), (30, "30 days"), (None, "All time")]:
                def _pick_win(win=_win):
                    s._sd_days = win
                    rf()
                with ui.element("button").classes(
                        "fd-seg-btn" + (" on" if _win == days else "")).props(
                        'type="button"').on("click", _pick_win):
                    ui.label(_wlbl)

    if not stats["funnel"][0]["count"] and not stats["lost"]:
        _empty_card(C, "Nothing to report yet",
                    "Companies show up here once a campaign has touched them. "
                    "Launch one, or set a stage by hand on Companies.",
                    "Go to Companies", lambda: _go(s, rf, "companies"))
        return

    # ── Funnel ──
    _section_title(C, "Funnel", top=16)
    top = max(stats["funnel"][0]["count"], 1)

    def _open_stage(stage):
        # A bar opens Companies filtered to exactly that stage.
        s._co_stage = stage
        s._co_view = "table"
        s._co_open = ""
        s._co_q = ""
        _go(s, rf, "companies", came_from="sales_dashboard")

    with ui.element("div").style(
            "display:grid;grid-template-columns:minmax(0,1fr) 220px;gap:16px;"
            "align-items:start;"):
        with ui.element("div").style(
                f"background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:10px;padding:14px 18px;"):
            for i, f in enumerate(stats["funnel"]):
                col = C["good"] if f["key"] == "client" else C["teal"]
                pct = int(round(100 * f["count"] / top))
                width = (max(pct, 2) if f["count"] else 0)
                with ui.element("div").style(
                        "display:grid;grid-template-columns:90px minmax(0,1fr) 44px;"
                        "gap:12px;align-items:center;padding:6px 0;cursor:pointer;"
                        ).on("click", lambda _k=f["key"]: _open_stage(_k)):
                    ui.label(f["label"]).style(
                        f"font-size:12px;font-weight:600;color:{C['text_l']};")
                    with ui.element("div").style(
                            f"height:18px;background:{C['surface']};border-radius:4px;"
                            f"overflow:hidden;"):
                        ui.element("div").style(
                            f"height:100%;width:{width}%;background:{col};border-radius:4px;")
                    ui.label(str(f["count"])).style(
                        f"font-size:13px;font-weight:700;text-align:right;"
                        f"color:{C['text_l'] if f['count'] else C['muted']};")
                if f["rate"] is not None:
                    prev = stats["funnel"][i - 1]["label"]
                    ui.label(f"{f['rate'] * 100:.0f}% of {prev}").style(
                        f"font-size:11px;color:{C['muted']};margin:-4px 0 2px 102px;")
        with ui.element("div").style(
                f"background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:10px;padding:14px 18px;"):
            wr = stats["win_rate"]
            for val, lbl, col in [
                (str(stats["lost"]), "Lost", C["warn"] if stats["lost"] else C["muted"]),
                ("—" if wr is None else f"{wr * 100:.0f}%", "Win rate",
                 C["good"] if wr else C["muted"]),
            ]:
                ui.label(val).classes("fd-sn").style(f"color:{col};")
                ui.label(lbl).classes("fd-sl").style("margin-bottom:12px;")
            ui.label("Win rate is Client over Client plus Lost. Each funnel step "
                     "counts every company at that stage or beyond it; Lost is "
                     "left out of every step.").style(
                f"font-size:11px;color:{C['muted']};line-height:1.4;")

    # ── This window ──
    _wl = "all time" if days is None else f"the last {days} days"
    _section_title(C, f"Over {_wl}")
    with ui.element("div").classes("fd-stat-strip").style("margin:0 0 4px;"):
        for k, lbl in WINDOW_TILES:
            n = len(stats["window"][k])
            on = (pick == k)
            col = {"replied": C["good"], "won": C["good"],
                   "lost": C["warn"]}.get(k, C["teal"])

            def _pick_tile(key=k, is_on=on):
                s._sd_pick = "" if is_on else key
                rf()
            with ui.element("div").classes("fd-stat-cell").style(
                    "cursor:pointer;" + (
                        f"background:{C['card_h']};box-shadow:inset 0 -3px 0 {C['teal']};"
                        if on else "")).on("click", _pick_tile):
                ui.label(str(n)).classes("fd-sn").style(
                    f"color:{col if n else C['muted']};")
                ui.label(lbl).classes("fd-sl")
    ui.label("Newly contacted and new replies are dated by the first send and "
             "the first reply. Moved and Lost are dated by when a stage was "
             "set. Won is dated by the Clients list. Click a tile to see the "
             "companies.").style(
        f"font-size:11px;color:{C['muted']};margin-bottom:10px;")
    if pick in stats["window"]:
        rows = stats["window"][pick]
        lbl = dict(WINDOW_TILES)[pick]
        with ui.element("div").style(
                f"background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:10px;padding:6px 18px 2px;margin-bottom:8px;"):
            ui.label(f"{lbl}: {len(rows)}").style(
                f"font-size:12px;font-weight:700;color:{C['text_l']};padding:6px 0;")
            if not rows:
                ui.label("None in this window.").style(
                    f"font-size:12px;color:{C['muted']};padding-bottom:8px;")
            for r in rows[:40]:
                _company_link(s, rf, C, r, _row_meta(r))
            if len(rows) > 40:
                ui.label(f"+{len(rows) - 40} more on Companies").style(
                    f"font-size:11px;color:{C['muted']};padding:6px 0;")

    # ── Needs a hand ──
    _section_title(C, "Needs a hand")
    with ui.element("div").style(
            "display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));"
            "gap:12px;"):
        for k, lbl, desc in ATTENTION_LISTS:
            rows = stats["attention"][k]
            with ui.element("div").style(
                    f"background:{C['card']};border:1px solid {C['border']};"
                    f"border-radius:10px;padding:12px 18px;min-width:0;"):
                with ui.element("div").style(
                        "display:flex;align-items:baseline;justify-content:space-between;gap:8px;"):
                    ui.label(lbl).style(
                        f"font-size:13px;font-weight:700;color:{C['text_l']};")
                    ui.label(str(len(rows))).style(
                        f"font-size:13px;font-weight:700;"
                        f"color:{C['warn'] if rows else C['muted']};")
                ui.label(desc).style(
                    f"font-size:11px;color:{C['muted']};margin:2px 0 6px;line-height:1.4;")
                if not rows:
                    ui.label("Nothing here. Good.").style(
                        f"font-size:12px;color:{C['muted']};padding:6px 0;")
                for r in rows[:8]:
                    if k == "stale_next_steps":
                        meta = "Next: " + r["next_step"]
                    elif k == "going_quiet":
                        meta = ("last " + _fmt_when(r["last_activity"])
                                if r["last_activity"] else "no sends or replies yet")
                    else:
                        meta = ((r["replies"][0].get("reply_body") or "").strip()[:80]
                                if r["replies"] else "")
                    _company_link(s, rf, C, r, meta)
                if len(rows) > 8:
                    ui.label(f"+{len(rows) - 8} more on Companies").style(
                        f"font-size:11px;color:{C['muted']};padding:6px 0 0;")

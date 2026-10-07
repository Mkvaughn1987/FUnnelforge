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

import csv
import io
import json
import os
import re
import threading
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

WINDOW_DAYS = 30

# The team this build belongs to. The page title and sidebar row use it.
TEAM_LABEL = "Arena"
PAGE_TITLE = f"{TEAM_LABEL} Running Campaigns"

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
_STATE_NAMES = {v.lower(): k for k, v in US_STATES.items()}
_STATE_NAME_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, _STATE_NAMES), key=len, reverse=True)) + r")\b")
# A two-letter code counts only at the start of the text ("CA - Tilden-Coil")
# or right after a comma, slash or bracket ("Denver, CO", "Torrance, CA (LA
# metro)"). "LA County" and "PM Super" in the middle of a name are not states.
_STATE_CODE_RE = re.compile(r"(?:^|[,/(]\s*)([A-Z]{2})(?![A-Za-z])")
# Metro names that show up without a state. Kansas City is left out: it
# straddles KS and MO.
_METRO_STATES = (
    ("CA", ("los angeles", "la county", "orange county", "san diego", "bay area",
            "san francisco", "sacramento", "inland empire", "san jose", "socal",
            "southern california", "northern california")),
    ("CO", ("denver", "front range", "colorado springs", "boulder", "fort collins")),
    ("AZ", ("phoenix", "tucson", "scottsdale", "tempe")),
    ("TX", ("dallas", "houston", "austin", "san antonio", "dfw", "fort worth")),
    ("UT", ("salt lake",)),
    ("WA", ("seattle", "tacoma", "bellevue")),
    ("NC", ("raleigh", "charlotte", "durham")),
    ("IL", ("chicago",)),
    ("NV", ("las vegas", "reno")),
    ("OR", ("portland",)),
    ("OH", ("cincinnati", "columbus", "cleveland")),
    ("OK", ("oklahoma city", "tulsa")),
    ("NY", ("new york city", "nyc")),
    ("MA", ("boston",)),
    ("GA", ("atlanta",)),
    ("FL", ("miami", "tampa", "orlando")),
    ("MN", ("minneapolis",)),
    ("PA", ("philadelphia", "pittsburgh")),
    ("MI", ("detroit",)),
    ("WI", ("milwaukee",)),
)

# Industry buckets for the page filter. First match wins, so the order
# matters: "Civil Engineering" is Civil, not Construction, and "Heavy
# Equipment and Construction" is a dealer, not a builder. Then trades,
# Mechanical first: "Construction / Mechanical Contracting - Data Centers"
# is Mechanical and "Commercial Construction / Electrical Contracting" is
# Electrical. Then the niches (OSHPD hospitals, data centers), then GCs,
# and Construction keeps whatever is left.
INDUSTRIES = (
    ("Manufacturing", r"manuf|machin|\bcnc\b|aerospace|packag|\bcpg\b|fabricat|\bplant\b"
                      r"|\bfoods?\b|dairy|farm|agricult|bakery|beverage|brew"),
    ("Civil & Engineering", r"\bcivil\b|engineer|\baec\b|water|utilit|infrastructure"
                            r"|transportation|surveying|pipeline"),
    ("Heavy Equipment & Rental", r"heavy equipment|equipment rental|rental equipment"
                                 r"|construction equipment|equipment dealer|caterpillar"
                                 r"|john deere"),
    ("Mechanical Contracting", r"mechanical|hvac|plumb|pipefit|sheet metal|sprinkler"
                               r"|fire protection|refrigerat"),
    ("Electrical Contracting", r"electric"),
    ("Healthcare Construction", r"oshpd|\bhcai\b|(health ?care|hospital|medical)\W*"
                                r"(construction|builder)"),
    ("Data Center / Mission Critical", r"data cent|mission critical"),
    ("General Contracting", r"general contract|general construction|commercial construction"
                            r"|construction manag|design.build|\bgc\b|tenant improvement"),
    ("Construction", r"construct|\bbuild|contractor|contracting|superintendent|homebuild"
                     r"|residential|concrete|roofing|glazing|drywall|framing|paving"
                     r"|excavat|demolition|steel"),
    ("Healthcare", r"health|medical|hospital|pharma|senior living"),
    ("Architecture & Design", r"architect|\bdesign\b"),
    ("Technology", r"software|technology|\btech\b|\bsaas\b|\bit\b"),
    ("Logistics & Freight", r"logistic|freight|trucking|supply chain|warehous|3pl|distribut"),
    ("Energy", r"energy|\boil\b|\bgas\b|solar|renewable|mining"),
    ("Accounting & Finance", r"accounting|finance|financial|\bcpa\b|insurance|banking"),
    ("Real Estate", r"real estate|property|multifamily|development"),
    ("Automotive", r"automo|dealer|truck center"),
)
INDUSTRY_OTHER = "Other"
# The fixed list a campaign's industry_category (and the AI sort) picks from.
INDUSTRY_CHOICES = tuple(label for label, _ in INDUSTRIES) + (INDUSTRY_OTHER,)
_CHOICE_BY_LOWER = {c.lower(): c for c in INDUSTRY_CHOICES}
# Rows the AI sort offers to place: they name no trade or niche.
UNSORTED = ("Construction", INDUSTRY_OTHER)
OVERRIDES_FILE = "industry_overrides.json"
_overrides_lock = threading.Lock()

KIND_LABELS = {
    "fivebyfive": "Arena 5×5", "fourbyfour": "Arena 4×4", "fivebythree": "Arena 5×3",
    "fivebyseven": "Arena 5×7", "clientlookalike": "Client Lookalike", "byos": "My Style",
    "blitz": "Blitz", "sidequest": "Side Quest", "talentdrop": "Talent Drop",
    "__ai_generated__": "AI Generated",
}
KIND_OTHER = "Other"

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


def state_of(text) -> str:
    """'Denver, CO' / 'Colorado' / 'CA - Tilden-Coil - PM' / 'LA County'
    -> 'CO' / 'CO' / 'CA' / 'CA'. '' when the text names no state."""
    t = (text or "").strip()
    if not t:
        return ""
    for m in _STATE_CODE_RE.finditer(t):
        if m.group(1) in US_STATES:
            return m.group(1)
    # "Kansas City" is a metro on the KS/MO line, not the state of Kansas.
    low = re.sub(r"\bkansas city\b", " ", t.lower())
    m = _STATE_NAME_RE.search(low)
    if m:
        return _STATE_NAMES[m.group(1)]
    for code, metros in _METRO_STATES:
        if any(re.search(r"\b" + re.escape(x) + r"\b", low) for x in metros):
            return code
    return ""


def _name_prefix(name: str) -> str:
    """'CA - Tilden-Coil - PM Super - 2026-09-15' -> 'CA'. '' when the
    name has no 'X - ' prefix."""
    m = re.match(r"^\s*([A-Za-z .]+?)\s*-\s", name or "")
    return m.group(1) if m else ""


def resolve_state(camp: dict, contacts: list | None = None) -> str:
    """Two-letter state for a campaign: the name prefix first ("CA - …"),
    then the Geography variable, then the whole name, then the first
    contacts' state or city. '' when nothing names one."""
    v = camp.get("variables") or {}
    name = camp.get("name") or ""
    for src in (_name_prefix(name), v.get("Geography"), v.get("Location"),
                v.get("location"), camp.get("market_region"), name):
        st = state_of(src)
        if st:
            return st
    if contacts is None:
        contacts = [c for c in (camp.get("contacts") or []) if isinstance(c, dict)]
    for c in contacts[:10]:
        st = state_of(c.get("state") or c.get("State") or "")
        if not st:
            st = state_of(", ".join(p for p in (c.get("city") or c.get("City") or "",
                                                c.get("state") or c.get("State") or "") if p))
        if st:
            return st
    return ""


def category_label(value) -> str:
    """'general contracting' -> 'General Contracting'; '' when the value is
    not on INDUSTRY_CHOICES."""
    return _CHOICE_BY_LOWER.get(str(value or "").strip().lower(), "")


def industry_of(camp: dict) -> str:
    """Industry bucket: the category picked at creation wins, then the
    Industry variable when it says something, then the niche, the name and
    the target roles."""
    picked = category_label(camp.get("industry_category"))
    if picked:
        return picked
    v = camp.get("variables") or {}
    for src in (v.get("Industry"), camp.get("market_niche"), camp.get("name"),
                v.get("TargetRole")):
        t = str(src or "").lower().strip()
        if not t:
            continue
        for label, pat in INDUSTRIES:
            if re.search(pat, t):
                return label
    return INDUSTRY_OTHER


def kind_of(camp: dict) -> str:
    return (camp.get("aicb_camp_type") or camp.get("template_key")
            or camp.get("_chooser_origin") or "").strip()


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind or "", KIND_OTHER if not kind else kind)


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
    variables = camp.get("variables") or {}
    kind = kind_of(camp)
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
        "state": resolve_state(camp, contacts),
        "industry": industry_of(camp),
        "kind": kind,
        "kind_label": kind_label(kind),
        "geo": (variables.get("Geography") or "").strip(),
        "roles": (variables.get("TargetRole") or "").strip(),
        "industry_text": str(variables.get("Industry") or camp.get("market_niche") or "").strip(),
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


# ── Arena Running Campaigns page: pure helpers ────────────────────────────

def opens_on(started: str, window_days: int = WINDOW_DAYS) -> str:
    """ISO date a company opens up again after a campaign started on
    `started`. '' when the date is unusable."""
    try:
        return (date.fromisoformat((started or "")[:10]) + timedelta(days=window_days)).isoformat()
    except Exception:
        return ""


def group_by_company(records: list) -> list:
    """One row per company (keyed by its first email domain), newest
    campaign first. Each row carries every campaign at that company plus
    the state and industry read off the newest campaign that names one."""
    by_co: dict = {}
    for r in records:
        key = r["domains"][0]
        row = by_co.setdefault(key, {"key": key, "company": r["company"],
                                     "domains": set(), "camps": []})
        row["domains"].update(r["domains"])
        row["camps"].append(r)
    rows = []
    for row in by_co.values():
        camps = sorted(row["camps"], key=lambda c: c["started"], reverse=True)
        row["camps"] = camps
        row["domains"] = sorted(row["domains"])
        row["last_started"] = camps[0]["started"]
        row["opens"] = opens_on(row["last_started"])
        row["reps"] = sorted({c["owner_dir"] for c in camps})
        row["state"] = next((c["state"] for c in camps if c.get("state")), "")
        row["industry"] = next((c["industry"] for c in camps
                                if c.get("industry") and c["industry"] != INDUSTRY_OTHER),
                               INDUSTRY_OTHER)
        row["kinds"] = sorted({c["kind"] for c in camps if c.get("kind")})
        row["running"] = any(c["status"] != "cancelled" for c in camps)
        rows.append(row)
    return sort_rows(rows, "newest")


# ── Per-company industry, set by the AI sort ──────────────────────────────
# One team file, keyed by email domain, so nobody's campaign files are
# rewritten. Applied to the grouped rows on both team pages.

def overrides_path(users_root, owner_email: str) -> Path | None:
    """data/users -> data/teams/<team>/industry_overrides.json."""
    suffix = team_suffix(owner_email)
    if not suffix:
        return None
    return Path(users_root).parent / "teams" / suffix[len("_at_"):] / OVERRIDES_FILE


def load_overrides(path) -> dict:
    """{domain: category}; entries off the list are dropped."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for dom, cat in raw.items():
        label = category_label(cat)
        if label and isinstance(dom, str) and dom.strip():
            out[dom.strip().lower()] = label
    return out


def save_overrides(path, picks: dict) -> dict:
    """Merge picks into the file (atomic write) and return the result."""
    path = Path(path)
    with _overrides_lock:
        merged = load_overrides(path)
        for dom, cat in (picks or {}).items():
            label = category_label(cat)
            if label and isinstance(dom, str) and dom.strip():
                merged[dom.strip().lower()] = label
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    return merged


def apply_overrides(rows: list, overrides: dict) -> list:
    """Set row["industry"] from the team file and mark the row sorted."""
    for row in rows:
        for d in row.get("domains") or []:
            if d in overrides:
                row["industry"] = overrides[d]
                row["industry_sorted"] = True
                break
    return rows


def needs_sort(rows: list) -> list:
    """Rows that name no trade or niche and the AI has not placed yet."""
    return [r for r in rows if r.get("industry") in UNSORTED and not r.get("industry_sorted")]


def sort_schema() -> dict:
    return {
        "type": "object",
        "properties": {"picks": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "integer"},
                           "category": {"type": "string", "enum": list(INDUSTRY_CHOICES)}},
            "required": ["id", "category"],
            "additionalProperties": False}}},
        "required": ["picks"],
        "additionalProperties": False,
    }


def sort_prompt(rows: list) -> str:
    """One numbered line per company with what the team's campaigns say
    about it. Ids are 1-based positions in rows."""
    lines = []
    for i, row in enumerate(rows, 1):
        camps = row.get("camps") or []
        texts = sorted({c.get("industry_text") for c in camps if c.get("industry_text")})
        roles = sorted({c.get("roles") for c in camps if c.get("roles")})
        names = [c.get("campaign") for c in camps[:3] if c.get("campaign")]
        bits = [f"{i}. {row.get('company') or row.get('key')}",
                f"website: {', '.join(row.get('domains') or [])}"]
        if texts:
            bits.append(f"industry as typed: {'; '.join(texts)[:200]}")
        if roles:
            bits.append(f"hiring for: {'; '.join(roles)[:200]}")
        if names:
            bits.append(f"campaigns: {'; '.join(names)[:200]}")
        lines.append(" | ".join(bits))
    return (
        "Put each company below into the one category that best describes "
        "what the company itself does. Use what you know about the company "
        "from its name and website, plus the notes from our campaigns.\n\n"
        "Categories: " + "; ".join(INDUSTRY_CHOICES) + ".\n\n"
        "Guidance: a general contractor or construction manager is General "
        "Contracting. HVAC, plumbing, piping, sheet metal and fire protection "
        "contractors are Mechanical Contracting; electrical contractors are "
        "Electrical Contracting. Builders that mainly do hospitals and OSHPD "
        "work are Healthcare Construction; data center and mission critical "
        "builders are Data Center / Mission Critical. Equipment dealers and "
        "rental houses are Heavy Equipment & Rental. Use Construction for a "
        "builder that fits none of those (specialty trades, homebuilders, "
        "concrete), and Other only when no category fits.\n\n"
        "Return one pick per company, using its number as the id.\n\n"
        + "\n".join(lines))


def parse_picks(text: str, rows: list) -> dict:
    """{row key: category} from the model's JSON. Unknown ids, labels off
    the list and repeats are dropped."""
    try:
        data = json.loads(text)
    except Exception:
        return {}
    out = {}
    for p in (data.get("picks") if isinstance(data, dict) else None) or []:
        if not isinstance(p, dict):
            continue
        try:
            i = int(p.get("id"))
        except Exception:
            continue
        label = category_label(p.get("category"))
        if not label or not 1 <= i <= len(rows):
            continue
        out.setdefault(rows[i - 1]["key"], label)
    return out


def filter_rows(rows: list, rep: str = "", state: str = "", industry: str = "",
                kind: str = "", status: str = "", q: str = "") -> list:
    """Rows matching every filter that is set. `rep` is an owner_dir,
    `state` a two-letter code, `kind` a template key, `status` 'running'
    or 'cancelled'. The search looks at company, domains, reps, campaign
    names, geography and target roles."""
    q = (q or "").strip().lower()
    out = []
    for row in rows:
        if rep and rep not in row["reps"]:
            continue
        if state and row["state"] != state:
            continue
        if industry and row["industry"] != industry:
            continue
        if kind and kind not in row["kinds"]:
            continue
        if status == "running" and not row["running"]:
            continue
        if status == "cancelled" and row["running"]:
            continue
        if q:
            hay = " ".join([row["company"], *row["domains"]] + [
                " ".join((c["owner"], c["campaign"], c.get("geo", ""), c.get("roles", "")))
                for c in row["camps"]]).lower()
            if q not in hay:
                continue
        out.append(row)
    return out


def sort_rows(rows: list, how: str = "newest") -> list:
    if how == "opens":
        return sorted(rows, key=lambda r: (r["opens"] or "9999", r["company"].lower()))
    if how == "name":
        return sorted(rows, key=lambda r: r["company"].lower())
    return sorted(rows, key=lambda r: (r["last_started"], r["company"].lower()), reverse=True)


def facet_counts(rows: list, key: str) -> Counter:
    """How many rows carry each value of `key` ('reps' and 'kinds' are
    lists, so a row counts once per value)."""
    counts: Counter = Counter()
    for row in rows:
        val = row.get(key)
        if isinstance(val, (list, set, tuple)):
            counts.update(v for v in val if v)
        elif val:
            counts[val] += 1
    return counts


def opening_within(rows: list, days: int = 7, today: date | None = None) -> list:
    """Rows whose company opens up again within `days` of today."""
    today = today or date.today()
    end = (today + timedelta(days=days)).isoformat()
    return [r for r in rows if r["opens"] and today.isoformat() <= r["opens"] <= end]


def rows_csv(rows: list) -> str:
    """One line per campaign, ready for Excel."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Company", "Domains", "State", "Industry", "Rep", "Campaign",
                "Type", "Status", "Started", "Opens again"])
    for row in rows:
        for c in row["camps"]:
            w.writerow([row["company"], ", ".join(row["domains"]), row["state"],
                        row["industry"], c["owner"], c["campaign"], c["kind_label"],
                        "Cancelled" if c["status"] == "cancelled" else "Running",
                        c["started"], row["opens"]])
    return buf.getvalue()


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

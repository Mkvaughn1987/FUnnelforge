"""Find more targets (ThriveModal / inboxslide only): the Target List's scan
of Filipino resumes on Indeed Smart Sourcing for US companies that already
employ Filipino staff.

Indeed Smart Sourcing only works inside the user's own signed-in Indeed
seat, so the server cannot run the scan. The page builds the instructions
and opens them in a new Claude chat; Claude reads the result cards in the
user's Chrome and saves what it finds back through the connector
(tm_targets, POST /api/v1/tm/targets), which lands here in clean_rows and
add_found. Rows are per user, in tm_targets.json next to the card status.

Only companies are stored: name, HQ, the roles Filipinos held there, the
years, and how many people named it. Candidate names never are.

Pure module (no NiceGUI), so the page, the API route and the tests share it.
"""
import json
import re
import urllib.parse
from datetime import date

import tm_targets_data as data

SEARCH_URL = "https://resumes.indeed.com/search"
PAGE_SIZE = 50
MAX_ROWS_PER_CALL = 200
MAX_FOUND = 2000
MAX_SCANS = 30

MARKET_LABEL = dict(data.MARKETS)

# Roles a Filipino employee of a US company in this market holds. The first
# few start ticked; the user can tick the rest or type their own.
ROLE_PRESETS = {
    "freight": ["freight broker", "dispatcher", "track and trace", "carrier sales",
                "load planner", "drayage", "logistics coordinator", "customs broker"],
    "accounting": ["bookkeeper", "staff accountant", "accounts payable",
                   "accounts receivable", "tax preparer", "payroll specialist"],
    "construction": ["estimator", "quantity surveyor", "CAD drafter",
                     "project coordinator", "structural engineer", "civil engineer"],
    "manufacturing": ["purchasing", "inventory control", "supply chain",
                      "order entry", "production planner", "customer service"],
    "staffing": ["recruiter", "sourcer", "onboarding coordinator",
                 "account coordinator", "payroll specialist"],
    "other": ["property management", "leasing", "home care coordinator",
              "medical billing", "virtual assistant"],
}
DEFAULT_ROLE_COUNT = 3

YEARS_OPTIONS = (3, 5, 10)
DEFAULT_YEARS = 5
PAGES_OPTIONS = (3, 5, 10)
DEFAULT_PAGES = 5
SIZE_OPTIONS = ((200, "Under 200 staff"), (500, "Under 500 staff"), (0, "Any size"))
DEFAULT_SIZE = 500

# Employers on Filipino resumes that are not prospects: offshore staffing
# vendors and BPOs (their US client, when named, is the prospect) and
# training courses that trainees list as an employer.
VENDORS = ("MyFreightStaff", "Lean Solutions Group", "Valoroo", "D'Freight VA",
           "Riot Staffing", "Outsmart Workforce", "Orbis Business Solutions",
           "Staff Sphere", "iSupport Worldwide (Iswerk)", "Emapta", "Avattech",
           "Intogreat", "Offshore Business Processing", "Cloudstaff",
           "Support Sixeleven", "Total Back Office Solutions", "EagleLink",
           "TaskHero", "Thrivemodal")
COURSES = ("Freight Courses 101", "D'Freight VA", "Dispatchers Academy")

# Big firms the Target List leaves out (over 500 staff; not our buyers).
BIG = ("Landstar", "TForce Freight", "OMNI Logistics", "GlobalTranz", "C.H. Robinson",
       "XPO", "J.B. Hunt", "Expeditors", "Kuehne+Nagel", "CEVA Logistics", "DHL",
       "Maersk", "DB Schenker", "FedEx", "UPS", "Nippon Express", "Accenture")

# Never added by a scan, whatever the resume says.
LEAVE_OUT = {"CoVar Transport": "a ThriveModal client"}

_ROLE_OK = re.compile(r"[^\w &/+.,'-]+")


# ── The scan request ─────────────────────────────────────────────────────

def default_scan(market="freight"):
    market = market if market in ROLE_PRESETS else "freight"
    return {"market": market,
            "roles": ROLE_PRESETS[market][:DEFAULT_ROLE_COUNT],
            "years": DEFAULT_YEARS, "pages": DEFAULT_PAGES, "size": DEFAULT_SIZE}


def clean_role(role):
    role = _ROLE_OK.sub(" ", str(role or "")).strip()
    return " ".join(role.split())[:40]


def build_query(roles):
    """Indeed boolean search: the roles OR'd, multi-word ones quoted, plus
    "USA" so the cards lean to US employers."""
    terms = []
    for r in roles or []:
        r = clean_role(r)
        if not r or r.lower() in (t.strip('"').lower() for t in terms):
            continue
        terms.append(f'"{r}"' if " " in r else r)
    if not terms:
        return '"USA"'
    body = terms[0] if len(terms) == 1 else "(" + " OR ".join(terms) + ")"
    return body + ' "USA"'


def page_urls(query, pages):
    q = urllib.parse.quote(query, safe="")
    return [f"{SEARCH_URL}?q={q}&nl=false&start={i * PAGE_SIZE}"
            for i in range(max(1, int(pages or 1)))]


def since_year(years, today=None):
    today = today or date.today()
    return today.year - int(years or DEFAULT_YEARS)


def known_names(market, found=()):
    """Companies already on this market's Target List (seed + this user's
    finds), for the instructions' skip list."""
    names = [r["name"] for r in data.SEED if r.get("market") == market]
    names += [r["name"] for r in found or [] if r.get("market") == market]
    seen, out = set(), []
    for n in names:
        k = norm(n)
        if k and k not in seen:
            seen.add(k)
            out.append(n)
    return out


def build_prompt(scan, found=(), clients=(), today=None):
    """The instructions the user's Claude follows: read Indeed result cards
    in Chrome, keep US employers of Filipino staff, save them with
    tm_targets."""
    market = scan.get("market") or "freight"
    label = MARKET_LABEL.get(market, market)
    query = build_query(scan.get("roles"))
    pages = int(scan.get("pages") or DEFAULT_PAGES)
    since = since_year(scan.get("years"), today)
    size = int(scan.get("size") if scan.get("size") is not None else DEFAULT_SIZE)
    urls = page_urls(query, pages)
    skip = known_names(market, found)
    client_names = [c for c in clients or [] if c]
    client_names += [n for n in LEAVE_OUT if norm(n) not in {norm(c) for c in client_names}]

    size_rule = (f"- Skip any company you know has over {size} staff, and the big "
                 "household names (they are not our buyers)." if size else None)
    lines = [
        f"Find US companies in {label} that already employ Filipino staff, from "
        "Filipino resumes on Indeed Smart Sourcing, and save them to my inboxslide "
        "Target List.",
        "",
        "You need two things: Claude in Chrome (my Chrome, where I am signed in to "
        "Indeed Smart Sourcing with the Philippines seat), and the inboxslide "
        "connector (its tm_targets tool saves the companies). If either is missing, "
        "tell me which one and stop.",
        "",
        "HOW TO READ THE PAGES",
        f"- Open a new tab for each of these {len(urls)} result pages, one at a time:",
        *[f"  {u}" for u in urls],
        "- After each page opens, wait 8 to 10 seconds before reading it. A page "
        "read sooner shows names only.",
        "- Read the page text (the profile cards). Do NOT open any resume; the "
        "cards list each person's jobs with years, which is all we need.",
        "- If a page asks me to sign in or pick a seat, stop and ask me to do it, "
        "then carry on.",
        "",
        "WHAT TO KEEP",
        f"- An employer on a card where the person worked in {since} or later, in a "
        f"{label} role.",
        "- The company must be US-based: the card says USA, a US state or city, or "
        "LLC/Inc. with a US place, or a quick web search shows a US head office. "
        "Mark it verified=true only when you saw that proof; a US-sounding name "
        "alone is verified=false.",
        "- When several people name the same company, keep one row and count the "
        "people.",
        "",
        "WHAT TO SKIP",
        "- Training courses that trainees list as an employer: " + ", ".join(COURSES)
        + ", and any academy, bootcamp or course. Skip a person whose only "
        f"{label} line is a course.",
        "- Offshore staffing vendors and BPOs: " + ", ".join(VENDORS) + ". When the "
        "card names the vendor's US client (often in brackets), keep the client "
        "instead.",
        "- Companies based outside the US (Canada, Australia, the UK, Hong Kong and "
        "so on), including ones with US-sounding names.",
        size_rule,
        "- Companies already on my Target List: " + (", ".join(skip) if skip else "none yet") + ".",
        "- My clients (never prospect them): " + (", ".join(client_names) if client_names else "none listed") + ".",
        "- Never write down a candidate's name or personal details. Save companies only.",
        "",
        "HOW TO SAVE",
        f"- Call tm_targets with action=\"add\", market=\"{market}\", query={json.dumps(query)}, "
        "and companies = a list of up to 50 rows per call, each: {name, hq (city, "
        "state), roles (the job titles the Filipinos held, comma separated), years "
        "(e.g. \"2024-2026\"), people (how many cards named it), verified (true or "
        "false), size (staff count if you know it, else \"\"), note (one short line "
        "if something is worth knowing)}.",
        "- Save after every page or two, so nothing is lost if the run stops.",
        "- The tool tells you which rows it added and which it skipped (already "
        "listed, a client, and so on); skipped rows need nothing more.",
        "",
        "WHEN YOU ARE DONE",
        "Close the tabs you opened and tell me in a few lines: how many pages you "
        "read, how many companies were added, the three strongest new ones, and "
        "anything that looked off.",
    ]
    return "\n".join(x for x in lines if x is not None)


# ── Saving what Claude found ─────────────────────────────────────────────

_SUFFIX = re.compile(r"\b(inc|llc|l\.?p|corp|corporation|co|company|ltd|group|the)\b\.?")


def norm(name):
    """Same comparable form as tm_targets.norm (kept here so this module
    stays importable without NiceGUI)."""
    s = str(name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.split("/")[0]
    s = _SUFFIX.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _txt(v, n):
    return " ".join(str(v or "").split())[:n]


def _people(v):
    try:
        return max(1, min(99, int(v)))
    except Exception:
        return 1


def _truthy(v):
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1", "y")
    return bool(v)


def tier_for(verified, people):
    if verified and people >= 2:
        return "strong"
    return "medium" if verified else "weak"


def clean_rows(rows, market, today=None):
    """(rows, errors): each company Claude sent, in the Target List row
    shape. Unknown keys (anything about a candidate) are dropped."""
    today = (today or date.today()).isoformat()
    if market not in MARKET_LABEL:
        market = "other"
    out, errors = [], []
    for i, r in enumerate(rows or []):
        if isinstance(r, str):
            r = {"name": r}
        if not isinstance(r, dict):
            errors.append({"row": i, "error": "each company must be an object"})
            continue
        name = _txt(r.get("name") or r.get("company"), 120)
        if not name or not norm(name):
            errors.append({"row": i, "error": "name is required"})
            continue
        verified = _truthy(r.get("verified"))
        people = _people(r.get("people"))
        years = _txt(r.get("years") or r.get("when"), 30)
        ph = (f"{people} Filipino employees list them on their resumes"
              if people > 1 else "A Filipino employee lists them on their resume")
        ph += f" ({years})." if years else "."
        note = _txt(r.get("note"), 200)
        if not verified:
            note = (note + " " if note else "") + "Check HQ before a campaign."
        out.append({
            "name": name, "market": market, "tier": tier_for(verified, people),
            "kind": "resume",
            "hq": _txt(r.get("hq") or r.get("location"), 80) or ("US" if verified else "US (unverified)"),
            "size": _txt(r.get("size"), 30), "ph": ph,
            "roles": _txt(r.get("roles"), 200), "posted": "", "when": years, "pay": "",
            "sources": [], "note": note,
            "found": today, "people": people, "verified": verified,
        })
    return out, errors


def add_found(state, rows, market, query="", clients=(), today=None):
    """Add cleaned rows to state["found"], skipping companies already on the
    list (seed or earlier finds), clients, and repeats within the call.
    Records the run in state["scans"]. Returns {added, skipped, results}."""
    today_s = (today or date.today()).isoformat()
    found = state.setdefault("found", [])
    taken = {norm(n): "a staffing vendor, not a prospect" for n in VENDORS}
    taken.update({norm(n): "a training course" for n in COURSES})
    taken.update({norm(n): "over 500 staff" for n in BIG})
    taken.update({norm(n): why for n, why in LEAVE_OUT.items()})
    taken.update({norm(r["name"]): "already on your Target List" for r in data.SEED})
    taken.update({norm(r["name"]): "already found by an earlier scan" for r in found})
    for c in clients or []:
        if norm(c):
            taken[norm(c)] = "a client"
    results, added = [], 0
    for r in rows:
        k = norm(r["name"])
        why = taken.get(k)
        if why is None and len(found) >= MAX_FOUND:
            why = f"your list is full ({MAX_FOUND} found companies)"
        if why:
            results.append({"name": r["name"], "added": False, "reason": why})
            continue
        found.append(r)
        taken[k] = "repeated in this call"
        added += 1
        results.append({"name": r["name"], "added": True, "tier": r["tier"]})
    skipped = len(results) - added
    scans = state.setdefault("scans", [])
    cur = next((x for x in scans if x.get("date") == today_s and x.get("market") == market
                and x.get("query") == query), None)
    if cur is None:
        cur = {"date": today_s, "market": market, "query": query, "added": 0, "skipped": 0}
        scans.insert(0, cur)
    cur["added"] += added
    cur["skipped"] += skipped
    del scans[MAX_SCANS:]
    return {"added": added, "skipped": skipped, "results": results}


def client_names(blocklist):
    """Company names from the Clients list (load_client_blocklist rows):
    the name when set, else the domain without its ending."""
    out = []
    for c in blocklist or []:
        if not isinstance(c, dict):
            continue
        n = str(c.get("client_name") or "").strip()
        if not n:
            n = str(c.get("domain") or "").strip().split(".")[0]
        if n:
            out.append(n)
    return out


def scan_line(scan):
    """'Oct 16 · Freight & 3PL · 12 added' for the page's recent-scans line."""
    try:
        d = date.fromisoformat(scan.get("date", ""))
        when = d.strftime("%b ") + str(d.day)
    except Exception:
        when = scan.get("date", "")
    n = int(scan.get("added") or 0)
    return f"{when} · {MARKET_LABEL.get(scan.get('market'), 'Other')} · {n} added"

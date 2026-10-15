"""Buying News & Signals: the Tuesday and Thursday email on inboxslide.

A user opts in on the page, picks the industries they sell into (any number
of the ThriveModal verticals) and a location. Twice a week the scheduler
researches each picked industry with web search, keeps only companies
showing one of the seven buying signals below, dated inside the last two
weeks, and emails the user a ranked issue from their own connected mailbox.
The page shows the same issues so a signal can be acted on without digging
through email.

Everything here is ThriveModal-only: the sidebar row resolves through
_TM_NAV_PAGES, the router is gated on _is_thrivemodal, and the scheduler
skips any user whose workspace is not on that playbook. Arena renders and
sends nothing new.

Layout of this file:
  1. the signal catalogue (fixed, in code)
  2. per-user settings + issues (one JSON file)
  3. the due check (pure, tested)
  4. the research call and its parser (parser pure, tested)
  5. the email renderer (pure, tested)
  6. the scheduler tick + run (host-bound through _ff())
  7. the page
"""
import json
import os
import re
import sys
import threading
import time
from datetime import date, datetime, timedelta

from nicegui import ui


def _ff():
    """The already-loaded flowdrip_app module (as 'flowdrip_app' or
    '__main__'). Never `import flowdrip_app` at module level: the server
    runs it as __main__, so importing re-executes the whole app."""
    for name in ("flowdrip_app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_BASE_DATA_DIR") and hasattr(m, "C"):
            return m
    import flowdrip_app as m  # standalone/test fallback
    return m


# ── 1. The signal catalogue ───────────────────────────────────────────────
#
# Seven signals, fixed in code. "urgent" ones go under "Move on these now";
# the rest under "Worth a look". The id is what the model returns and what
# the parser checks against, so a made-up signal never reaches the email.
SIGNALS = [
    {"id": "pe", "urgent": True,
     "label": "Private equity acquisition or new investor",
     "why": "New owners push for cost reduction in the first twelve months."},
    {"id": "exec", "urgent": True,
     "label": "New CFO, COO or CEO",
     "why": "New leadership reviews vendor and headcount spend in its first quarter."},
    {"id": "cost", "urgent": True,
     "label": "Layoffs, WARN filing, closure or restructuring",
     "why": "They are actively looking to cut back-office cost."},
    {"id": "growth", "urgent": True,
     "label": "Big contract, expansion, new location or funding",
     "why": "The volume lands before the desks to cover it do."},
    {"id": "hiring", "urgent": False,
     "label": "Hiring surge or long-open back-office postings",
     "why": "They cannot fill on the terms they are offering."},
    {"id": "remote", "urgent": False,
     "label": "Fully remote or work-from-home postings",
     "why": "They have already decided the seat does not need to be in the building."},
    {"id": "offshore", "urgent": False,
     "label": "Offshore tells: Philippines, BPO, VA, US hours",
     "why": "Already buying the model, so this is a displacement conversation."},
]
SIGNAL_BY_ID = {s["id"]: s for s in SIGNALS}
URGENT_IDS = [s["id"] for s in SIGNALS if s["urgent"]]

# How far back a signal may be dated and still make an issue, and how long
# a company stays out of later issues once it has been sent.
FRESH_DAYS = 14
REPEAT_DAYS = 30
# Issues kept per user (newest first), and the local hour the email goes.
KEEP_ISSUES = 8
SEND_HOUR = 7
SEND_WEEKDAYS = (1, 3)   # Tuesday, Thursday (Monday is 0)

SETTINGS_FILE = "tm_signals.json"
MODEL = os.environ.get("DRIPDROP_TM_SIGNALS_MODEL", "claude-sonnet-5-5")

# Business-news and filings domains the research may search, on top of the
# app's standard allowlist. Fixed in code: the allowlist is what stops
# prompt injection in user content pivoting a search to attacker URLs.
#
# Never list a domain that blocks Anthropic's crawler (reuters, wsj,
# bloomberg, bizjournals, ft, forbes, businessinsider): the API rejects the
# WHOLE request with a 400 if the allowlist names one, and every scan fails.
# run_scan() also strips any domain the API names as blocked and retries,
# so a publisher that starts blocking later only costs one extra call.
NEWS_DOMAINS = [
    "prnewswire.com", "businesswire.com", "globenewswire.com",
    "axios.com", "sec.gov", "warntracker.com", "layoffs.fyi",
    "freightwaves.com", "supplychaindive.com", "joc.com", "ttnews.com",
    "accountingtoday.com", "cpapracticeadvisor.com", "pehub.com",
    "pitchbook.com", "constructiondive.com", "healthcaredive.com",
    "homehealthcarenews.com", "multifamilydive.com", "modernhealthcare.com",
    "retaildive.com", "industryweek.com", "achrnews.com", "contractormag.com",
    "mdm.com", "adweek.com", "travelweekly.com", "digitalcommerce360.com",
]


# ── 2. Settings + issues ──────────────────────────────────────────────────

def default_settings():
    return {"enabled": False, "industries": [], "location": "USA",
            "last_run_date": "", "issues": []}


def settings_path(user_root=None):
    root = user_root if user_root is not None else _ff()._resolve_user_root()
    return root / SETTINGS_FILE


def load_settings(user_root=None):
    try:
        p = settings_path(user_root)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out = default_settings()
                out.update(data)
                out["industries"] = [str(x) for x in (out.get("industries") or [])]
                out["issues"] = [i for i in (out.get("issues") or [])
                                 if isinstance(i, dict)]
                return out
    except Exception:
        pass
    return default_settings()


def save_settings(data, user_root=None):
    p = settings_path(user_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)


def verticals():
    """The ThriveModal verticals, key -> row, in catalogue order."""
    import tm_prompts
    return [(v["key"], v) for v in tm_prompts.VERTICALS]


def industry_label(key):
    for k, v in verticals():
        if k == key:
            return v["label"]
    return key


# ── 3. The due check ──────────────────────────────────────────────────────

def is_due(settings, now_local):
    """True when this user's issue should go out now: opted in, at least
    one industry, a Tuesday or Thursday at or after SEND_HOUR local, and
    nothing has run yet today. Pure: the caller supplies local time."""
    if not settings.get("enabled"):
        return False
    if not settings.get("industries"):
        return False
    if now_local.weekday() not in SEND_WEEKDAYS:
        return False
    if now_local.hour < SEND_HOUR:
        return False
    return settings.get("last_run_date", "") != now_local.date().isoformat()


def next_send(now_local):
    """The next Tuesday or Thursday SEND_HOUR after now_local."""
    for d in range(0, 8):
        day = (now_local + timedelta(days=d)).replace(
            hour=SEND_HOUR, minute=0, second=0, microsecond=0)
        if day.weekday() in SEND_WEEKDAYS and day > now_local:
            return day
    return now_local


# ── 4. The research call ──────────────────────────────────────────────────

SYSTEM = (
    "You are a buying-signal analyst for ThriveModal, which staffs offshore "
    "back-office teams in the Philippines for US companies. You find real, "
    "recent, verifiable events at real US companies and report them in JSON. "
    "You never invent a company, an event, a date or a URL. If you cannot "
    "verify something, leave it out."
)


def _signal_menu():
    return "\n".join(f"- {s['id']}: {s['label']}. {s['why']}" for s in SIGNALS)


def scan_prompt(vertical, location, today):
    """The research prompt for one industry."""
    return (
        f"Today is {today.strftime('%d %B %Y')}.\n\n"
        f"INDUSTRY: {vertical['label']}\n"
        f"COMPANY SIZE: {vertical.get('band', '')}\n"
        f"LOCATION: {location or 'USA'}\n"
        f"WHO BUYS: {vertical.get('buyers', '')}\n"
        f"WORK THRIVEMODAL TAKES ON: {vertical.get('roles', '')}\n"
        f"SOFTWARE TELLS: {vertical.get('tells', '')}\n\n"
        "Search the news, press releases, filings, WARN notices and job "
        "boards for companies in this industry and location that showed "
        f"one of these buying signals in the last {FRESH_DAYS} days:\n"
        f"{_signal_menu()}\n\n"
        "Return 6 to 12 companies, the strongest first. For each one:\n"
        "- company: the legal or trading name\n"
        "- location: city and state\n"
        "- signal: exactly one id from the list above\n"
        "- headline: what happened, under fifteen words\n"
        "- date: when it happened, YYYY-MM-DD\n"
        "- why_now: one sentence under thirty words on why this makes them "
        "a buyer this month\n"
        "- opener: the first sentence of a cold email that names the event, "
        "under thirty words, no claims about results or savings\n"
        "- source_url: the page you read it on\n\n"
        "Then 3 to 5 pieces of industry news from the same period that a "
        "seller into this market should know this week: headline (under "
        "fifteen words), date (YYYY-MM-DD), summary (one sentence under "
        "thirty words), source_url.\n\n"
        "Rules:\n"
        "- Only events you actually found in a search result. No guesses.\n"
        f"- Nothing older than {FRESH_DAYS} days. Drop it rather than stretch "
        "the date.\n"
        "- Direct employers only, not staffing agencies or BPOs.\n"
        "- Plain sentences, no markdown, no citation markup inside values.\n\n"
        "Return ONLY this JSON, no prose:\n"
        '{"companies": [{"company": "...", "location": "...", "signal": "pe", '
        '"headline": "...", "date": "YYYY-MM-DD", "why_now": "...", '
        '"opener": "...", "source_url": "https://..."}], '
        '"news": [{"headline": "...", "date": "YYYY-MM-DD", "summary": "...", '
        '"source_url": "https://..."}]}'
    )


def _parse_date(s):
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %B %Y", "%B %d, %Y", "%b %d, %Y",
                "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None
    return None


def _clean(s, limit=400):
    s = re.sub(r"<[^>]+>", "", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _ok_url(u):
    u = str(u or "").strip()
    return u if u.lower().startswith(("http://", "https://")) else ""


def parse_scan(text, today):
    """The JSON the model returned, checked. Companies keep only a known
    signal id, a name, a parseable date inside FRESH_DAYS, and an http
    source. News keeps a headline and a date inside the window (a missing
    date is tolerated for news, not for companies)."""
    clean = str(text or "").replace("```json", "").replace("```", "")
    m = re.search(r"\{.*\}", clean, re.DOTALL)
    if not m:
        return {"companies": [], "news": []}
    try:
        data = json.loads(m.group())
    except Exception:
        return {"companies": [], "news": []}
    if not isinstance(data, dict):
        return {"companies": [], "news": []}

    def fresh(d):
        if d is None:
            return False
        age = (today - d).days
        return -1 <= age <= FRESH_DAYS

    rows_in = data.get("companies")
    news_in = data.get("news")
    rows_in = rows_in if isinstance(rows_in, list) else []
    news_in = news_in if isinstance(news_in, list) else []

    companies, seen = [], set()
    for row in rows_in:
        if not isinstance(row, dict):
            continue
        name = _clean(row.get("company"), 120)
        sig = str(row.get("signal") or "").strip().lower()
        d = _parse_date(row.get("date"))
        url = _ok_url(row.get("source_url"))
        if not name or sig not in SIGNAL_BY_ID or not fresh(d) or not url:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        companies.append({
            "company": name,
            "location": _clean(row.get("location"), 80),
            "signal": sig,
            "headline": _clean(row.get("headline"), 160),
            "date": d.isoformat(),
            "why_now": _clean(row.get("why_now"), 300),
            "opener": _clean(row.get("opener"), 300),
            "source_url": url,
        })

    news = []
    for row in news_in:
        if not isinstance(row, dict):
            continue
        head = _clean(row.get("headline"), 160)
        if not head:
            continue
        d = _parse_date(row.get("date"))
        if d is not None and not fresh(d):
            continue
        news.append({
            "headline": head,
            "date": d.isoformat() if d else "",
            "summary": _clean(row.get("summary"), 300),
            "source_url": _ok_url(row.get("source_url")),
        })
    return {"companies": companies, "news": news[:5]}


def recent_companies(issues, today, days=REPEAT_DAYS):
    """Company names (lowercased) sent in any issue inside `days`."""
    out = set()
    for issue in issues or []:
        d = _parse_date(issue.get("date"))
        if d is None or (today - d).days > days:
            continue
        for sec in issue.get("sections") or []:
            for row in (sec.get("companies") or []):
                n = str(row.get("company") or "").strip().lower()
                if n:
                    out.add(n)
    return out


def rank(companies):
    """Urgent signals first, then newest first."""
    order = {s["id"]: i for i, s in enumerate(SIGNALS)}
    newest = sorted(companies, key=lambda r: r.get("date", ""), reverse=True)
    return sorted(newest, key=lambda r: (not SIGNAL_BY_ID[r["signal"]]["urgent"],
                                         order.get(r["signal"], 99)))


def build_issue(settings, today, scan):
    """One issue from the user's settings. `scan(vertical, location)`
    returns the model's text; it is called once per picked industry and a
    failure in one industry drops that section, not the issue."""
    seen = recent_companies(settings.get("issues"), today)
    sections = []
    for key, v in verticals():
        if key not in settings.get("industries", []):
            continue
        try:
            text = scan(v, settings.get("location") or "USA")
        except Exception as e:
            print(f"[Signals] {key}: scan failed: {e}", flush=True)
            sections.append({"industry": key, "label": v["label"],
                             "companies": [], "news": [], "error": str(e)[:200]})
            continue
        found = parse_scan(text, today)
        rows = [r for r in found["companies"] if r["company"].lower() not in seen]
        for r in rows:
            seen.add(r["company"].lower())
        sections.append({"industry": key, "label": v["label"],
                         "companies": rank(rows), "news": found["news"]})
    return {
        "id": today.strftime("%Y%m%d") + "-" + datetime.now().strftime("%H%M%S"),
        "date": today.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "subject": subject_for(today),
        "location": settings.get("location") or "USA",
        "sections": sections,
        "sent_at": "",
        "send_error": "",
    }


def subject_for(today):
    return "Buying news & signals: " + today.strftime("%a %d %b").replace(" 0", " ")


def issue_has_content(issue):
    for sec in issue.get("sections") or []:
        if sec.get("companies") or sec.get("news"):
            return True
    return False


def issue_failure(issue):
    """The error to show when research failed for EVERY picked industry,
    else "". A partial failure with nothing found is still "nothing found"."""
    secs = issue.get("sections") or []
    errs = [sec.get("error") for sec in secs if sec.get("error")]
    if not secs or len(errs) < len(secs):
        return ""
    return "Research failed: " + str(errs[0])[:160]


# Domains the API has told us it cannot reach, learned at runtime. A domain
# in here is left out of every later scan for the life of the process.
_BLOCKED_DOMAINS = set()


def blocked_domains_in(err_text):
    """The domains an Anthropic 400 names as "not accessible to our user
    agent", or [] when the error is about something else."""
    s = str(err_text or "")
    if "not accessible" not in s:
        return []
    m = re.search(r"\[([^\]]*)\]", s)
    if not m:
        return []
    return [d.strip().strip("'\"") for d in m.group(1).split(",") if d.strip()]


def search_domains(ff):
    wanted = list(NEWS_DOMAINS) + list(ff._WARN_SEARCH_DOMAINS)
    return [d for d in wanted if d not in _BLOCKED_DOMAINS]


def run_scan(client, vertical, location, today):
    """The live research call for one industry. Returns the model's text.
    If the API rejects the request because a listed domain blocks its
    crawler, that domain is dropped for good and the call is made again."""
    ff = _ff()
    for attempt in (1, 2):
        try:
            msg = ff._claude_create_with_retry(
                client,
                model=MODEL,
                max_tokens=6000,
                system=ff._injection_guarded_system(SYSTEM),
                messages=[{"role": "user",
                           "content": scan_prompt(vertical, location, today)}],
                tools=[ff._safe_web_search_tool(
                    max_uses=8, extra_domains=search_domains(ff))],
            )
            break
        except Exception as e:
            bad = blocked_domains_in(e)
            if attempt == 2 or not bad:
                raise
            _BLOCKED_DOMAINS.update(bad)
            print(f"[Signals] dropping blocked search domains {bad}; retrying",
                  flush=True)
    text = ""
    for part in msg.content:
        if hasattr(part, "text"):
            text += part.text + "\n"
    return text


# ── 5. The email ──────────────────────────────────────────────────────────
#
# Inline styles only: no <style> block, because _server_send_one runs the
# body through merge-token substitution and most mail clients strip the
# block anyway. Colours are ThriveModal's navy and green.

NAVY = "#082139"
GREEN = "#3D7A22"
RED = "#B42318"
INK = "#1F2937"
MUTED = "#6B7280"
LINE = "#E5E7EB"
BG = "#F4F6F8"


def _e(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _pretty_date(iso):
    d = _parse_date(iso)
    return d.strftime("%d %b").lstrip("0") if d else ""


def _company_card(row, app_url):
    sig = SIGNAL_BY_ID[row["signal"]]
    badge_bg = RED if sig["urgent"] else GREEN
    links = [f'<a href="{_e(row["source_url"])}" style="color:{GREEN};'
             f'text-decoration:none;font-weight:600;">Source</a>']
    if app_url:
        links.append(f'<a href="{_e(app_url)}/?open=tm_prompts" style="color:{GREEN};'
                     'text-decoration:none;font-weight:600;">Build a campaign</a>')
    loc = f' <span style="color:{MUTED};font-weight:400;">· {_e(row["location"])}</span>' \
        if row.get("location") else ""
    opener = (f'<p style="margin:8px 0 0;padding:8px 12px;border-left:3px solid {LINE};'
              f'color:{INK};font-size:13px;line-height:1.5;font-style:italic;">'
              f'{_e(row["opener"])}</p>') if row.get("opener") else ""
    return (
        f'<div style="border:1px solid {LINE};border-radius:10px;padding:14px 16px;'
        f'margin:0 0 10px;background:#ffffff;">'
        f'<div style="font-size:15px;font-weight:700;color:{NAVY};">{_e(row["company"])}{loc}</div>'
        f'<div style="margin:6px 0 0;">'
        f'<span style="display:inline-block;background:{badge_bg};color:#ffffff;'
        f'font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;">'
        f'{_e(sig["label"])}</span>'
        f'<span style="color:{MUTED};font-size:12px;margin-left:8px;">{_e(_pretty_date(row["date"]))}</span>'
        f'</div>'
        f'<p style="margin:8px 0 0;color:{INK};font-size:14px;line-height:1.5;font-weight:600;">'
        f'{_e(row["headline"])}</p>'
        f'<p style="margin:4px 0 0;color:{INK};font-size:13px;line-height:1.5;">{_e(row["why_now"])}</p>'
        f'{opener}'
        f'<div style="margin:10px 0 0;font-size:12px;">{" &nbsp;·&nbsp; ".join(links)}</div>'
        f'</div>'
    )


def _news_line(row):
    head = _e(row["headline"])
    if row.get("source_url"):
        head = (f'<a href="{_e(row["source_url"])}" style="color:{NAVY};'
                f'text-decoration:none;font-weight:600;">{head}</a>')
    when = f' <span style="color:{MUTED};font-size:12px;">{_e(_pretty_date(row["date"]))}</span>' \
        if row.get("date") else ""
    summ = (f'<div style="color:{INK};font-size:13px;line-height:1.5;">{_e(row["summary"])}</div>'
            if row.get("summary") else "")
    return (f'<div style="padding:8px 0;border-bottom:1px solid {LINE};">'
            f'<div style="font-size:14px;">{head}{when}</div>{summ}</div>')


def _h2(text, colour=NAVY):
    return (f'<h2 style="margin:22px 0 10px;font-size:13px;letter-spacing:.08em;'
            f'text-transform:uppercase;color:{colour};">{_e(text)}</h2>')


def render_email(issue, brand="inboxslide", app_url=""):
    """The issue as an HTML email body."""
    parts = []
    for sec in issue.get("sections") or []:
        urgent = [r for r in sec.get("companies") or [] if SIGNAL_BY_ID[r["signal"]]["urgent"]]
        watch = [r for r in sec.get("companies") or [] if not SIGNAL_BY_ID[r["signal"]]["urgent"]]
        news = sec.get("news") or []
        if not (urgent or watch or news):
            continue
        parts.append(f'<h1 style="margin:28px 0 4px;font-size:20px;color:{NAVY};">'
                     f'{_e(sec["label"])}</h1>')
        if urgent:
            parts.append(_h2("Move on these now", RED))
            parts.extend(_company_card(r, app_url) for r in urgent)
        if watch:
            parts.append(_h2("Worth a look", GREEN))
            parts.extend(_company_card(r, app_url) for r in watch)
        if news:
            parts.append(_h2("Industry news"))
            parts.extend(_news_line(r) for r in news)
    if not parts:
        parts.append(f'<p style="color:{INK};font-size:14px;">Nothing new this time. '
                     'The next issue comes on the next Tuesday or Thursday.</p>')
    when = _parse_date(issue.get("date"))
    when_s = when.strftime("%A %d %B %Y").replace(" 0", " ") if when else ""
    settings_link = (f'<a href="{_e(app_url)}/?open=tm_signals" style="color:{GREEN};">'
                     f'Buying Signals</a>') if app_url else "Buying Signals"
    return (
        f'<div style="background:{BG};padding:24px 12px;font-family:Arial,Helvetica,sans-serif;">'
        f'<div style="max-width:620px;margin:0 auto;background:#ffffff;border-radius:14px;'
        f'overflow:hidden;border:1px solid {LINE};">'
        f'<div style="background:{NAVY};padding:22px 24px;">'
        f'<div style="color:#ffffff;font-size:20px;font-weight:800;">Buying news &amp; signals</div>'
        f'<div style="color:#C9D3DE;font-size:13px;margin-top:4px;">{_e(when_s)} · '
        f'{_e(issue.get("location") or "USA")}</div>'
        f'</div>'
        f'<div style="padding:4px 24px 24px;">'
        + "".join(parts) +
        f'<p style="margin:28px 0 0;color:{MUTED};font-size:12px;line-height:1.5;">'
        f'You get this every Tuesday and Thursday because you opted in on {_e(brand)} &gt; '
        f'{settings_link}. Turn it off or change your industries there.</p>'
        f'</div></div></div>'
    )


# ── 6. The scheduler ──────────────────────────────────────────────────────

_TICK_EVERY = 5 * 60
_last_tick = [0.0]
_running = set()
_running_lock = threading.Lock()


def _user_now(ff, user_cfg):
    """Wall-clock time where the user is. Falls back to the default zone,
    then to the server's own clock (a box with no tzdata, as on Windows)."""
    from zoneinfo import ZoneInfo
    name = (user_cfg.get("user_timezone") or "").strip() or ff._DEFAULT_USER_TZ
    for key in (name, ff._DEFAULT_USER_TZ):
        try:
            return datetime.now(ZoneInfo(key)).replace(tzinfo=None)
        except Exception:
            continue
    return datetime.now()


def scheduler_tick(force=False):
    """Called from the server scheduler loop on every tick; does real work
    at most every five minutes. For each ThriveModal user who is due, the
    run date is stamped first (so a slow run is never started twice) and
    the research + send happens on a per-user thread."""
    now = time.monotonic()
    if not force and now - _last_tick[0] < _TICK_EVERY:
        return 0
    _last_tick[0] = now
    ff = _ff()
    users_dir = ff._BASE_DATA_DIR / "users"
    if not users_dir.exists():
        return 0
    started = 0
    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir() or not (user_dir / SETTINGS_FILE).exists():
            continue
        try:
            cfg_path = user_dir / "dripdrop_config.json"
            user_cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        except Exception:
            user_cfg = {}
        if not ff._is_thrivemodal(user_cfg):
            continue
        settings = load_settings(user_dir)
        local = _user_now(ff, user_cfg)
        if not is_due(settings, local):
            continue
        email = ff._email_from_user_path(user_dir)
        if not email:
            continue
        settings["last_run_date"] = local.date().isoformat()
        save_settings(settings, user_dir)
        ff._run_as_user(email, lambda e=email, d=user_dir: run_issue(e, d),
                        name="tm_signals_issue")
        started += 1
    return started


def run_issue(email, user_dir, send=True, today=None):
    """Research every picked industry, store the issue, email it to the
    user from their own mailbox. Returns the issue. Safe to call from the
    page ("Send me one now") and from the scheduler."""
    ff = _ff()
    with _running_lock:
        if email in _running:
            return None
        _running.add(email)
    try:
        today = today or date.today()
        settings = load_settings(user_dir)
        import anthropic
        client = anthropic.Anthropic(api_key=ff.ANTHROPIC_API_KEY)

        def scan(vertical, location):
            return run_scan(client, vertical, location, today)

        issue = build_issue(settings, today, scan)
        if send:
            if issue_has_content(issue):
                item = {"to": email, "subject": issue["subject"],
                        "body": render_email(issue, ff.BRAND, ff._PUBLIC_ORIGIN),
                        "is_html": True}
                ok, err = ff._server_send_one(item, user_dir / "dripdrop_config.json",
                                              user_dir=user_dir)
                if ok:
                    issue["sent_at"] = datetime.now().isoformat(timespec="seconds")
                    print(f"[Signals] sent to {email}: {issue['subject']}", flush=True)
                else:
                    issue["send_error"] = str(err)[:300]
                    print(f"[Signals] send failed for {email}: {err}", flush=True)
            elif issue_failure(issue):
                issue["send_error"] = issue_failure(issue) + " No email sent."
                print(f"[Signals] {email}: every industry failed, no email", flush=True)
            else:
                issue["send_error"] = "Nothing found this time; no email sent."
                print(f"[Signals] {email}: nothing found, no email", flush=True)
        settings = load_settings(user_dir)   # re-read: the page may have saved
        settings["issues"] = ([issue] + list(settings.get("issues") or []))[:KEEP_ISSUES]
        settings["last_run_date"] = today.isoformat()
        save_settings(settings, user_dir)
        return issue
    except Exception as e:
        print(f"[Signals] run failed for {email}: {e}", flush=True)
        return None
    finally:
        with _running_lock:
            _running.discard(email)


# ── 7. The page ───────────────────────────────────────────────────────────

def _css():
    ui.html(
        "<style>"
        ".tms-wrap{max-width:980px;}"
        ".tms-wrap .fd-input{padding:0 10px !important;}"
        ".tms-wrap .fd-input .q-field__control{min-height:38px !important;}"
        ".tms-wrap .fd-input .q-field__control:before,"
        ".tms-wrap .fd-input .q-field__control:after{display:none !important;}"
        ".tms-wrap .fd-input .q-field__bottom{display:none !important;}"
        ".tms-wrap .tms-card{background:var(--dd-card);border:1px solid var(--dd-border);"
        "border-radius:12px;padding:20px 22px;margin-bottom:18px;}"
        ".tms-wrap .tms-grid{display:grid;gap:14px;"
        "grid-template-columns:repeat(auto-fit,minmax(280px,1fr));}"
        ".tms-wrap .tms-sec{font-size:10px;font-weight:800;letter-spacing:.10em;"
        "text-transform:uppercase;display:block;margin:2px 0 10px;}"
        ".tms-wrap .tms-sig{display:flex;gap:8px;align-items:flex-start;padding:8px 10px;"
        "border-radius:9px;border:1px solid var(--dd-border);background:var(--dd-bg);}"
        ".tms-wrap .tms-row{border:1px solid var(--dd-border);border-radius:10px;"
        "padding:12px 14px;margin:0 0 8px;background:var(--dd-bg);}"
        ".tms-wrap .tms-badge{display:inline-block;color:#fff;font-size:10px;font-weight:700;"
        "padding:2px 8px;border-radius:999px;margin-right:8px;}"
        ".tms-wrap a{color:var(--dd-teal);text-decoration:none;font-weight:600;}"
        ".tms-wrap .tms-kv{display:grid;grid-template-columns:96px 1fr;gap:10px 12px;"
        "align-items:center;}"
        ".tms-wrap .tms-k{font-size:11px;font-weight:700;color:var(--dd-muted);"
        "text-transform:uppercase;letter-spacing:.06em;}"
        ".tms-wrap .tms-pills{display:flex;flex-wrap:wrap;gap:6px;align-items:center;}"
        ".tms-wrap .tms-pill{display:inline-flex;align-items:center;gap:6px;font-size:13px;"
        "font-weight:600;padding:6px 13px;border-radius:999px;line-height:1.3;"
        "border:1px solid var(--dd-border);background:var(--dd-card);color:var(--dd-text_l);"
        "font-family:inherit;}"
        ".tms-wrap button.tms-pill{cursor:pointer;transition:filter .12s,border-color .12s;}"
        ".tms-wrap button.tms-pill:hover{filter:brightness(.96);border-color:var(--dd-teal);}"
        ".tms-wrap .tms-pill.on{border-color:var(--dd-good);color:var(--dd-good);"
        "background:color-mix(in srgb,var(--dd-good) 12%,var(--dd-card));}"
        ".tms-wrap .tms-pill.off{color:var(--dd-muted);}"
        ".tms-wrap .tms-pill.ind{border-color:var(--dd-teal);padding-right:6px;"
        "background:color-mix(in srgb,var(--dd-teal) 10%,var(--dd-card));}"
        ".tms-wrap .tms-pill.add{border-style:dashed;color:var(--dd-teal);}"
        ".tms-wrap .tms-pill .q-icon{font-size:16px;}"
        ".tms-wrap .tms-pill .tms-edit{font-size:13px;color:var(--dd-muted);}"
        ".tms-wrap .tms-x{display:inline-flex;align-items:center;justify-content:center;"
        "width:20px;height:20px;border-radius:50%;border:0;padding:0;cursor:pointer;"
        "background:transparent;color:var(--dd-muted);}"
        ".tms-wrap .tms-x:hover{background:var(--dd-danger);color:#fff;}"
        ".tms-wrap .tms-x .q-icon{font-size:14px;}"
        ".tms-wrap .tms-note{display:flex;align-items:center;gap:6px;margin-top:14px;"
        "font-size:12px;color:var(--dd-muted);}"
        ".tms-wrap .tms-note.good{color:var(--dd-good);font-weight:700;}"
        ".tms-wrap .tms-note .q-icon{font-size:16px;}"
        "@media (max-width:520px){.tms-wrap .tms-kv{grid-template-columns:1fr;gap:4px;}"
        ".tms-wrap .tms-k{margin-top:8px;}}"
        "</style>", sanitize=False)


def _settings_panel(s, ff, C, labels, when, just_saved, save):
    """The email settings as pills. Each pill is its own control and every
    change saves at once, so there is no form and no Save button to miss."""
    on = bool(s._tms_enabled)
    picked = [k for k in labels if k in (s._tms_industries or [])]
    loc = (s._tms_location or "").strip() or "USA"

    def set_on():
        s._tms_enabled = not on
        save()

    def drop(k):
        s._tms_industries = [x for x in picked if x != k]
        save()

    def add(k):
        s._tms_industries = picked + [k]
        save()

    regions = ff._region_options()
    if loc not in regions:
        regions = [loc] + regions
    if "USA" not in regions:
        regions = ["USA"] + regions
    with ui.dialog() as loc_dlg, ui.card().style("min-width:340px;max-width:92vw;"):
        ui.label("Location").classes("fd-fl")
        loc_sel = ui.select(options=regions, value=loc, with_input=True,
                            new_value_mode="add-unique").classes("fd-input").style("width:100%;")
        _text("USA for a nationwide sweep, or one state or metro. Type to search or "
              "add your own.", C, 11, colour=C["muted"])

        def set_loc():
            s._tms_location = (loc_sel.value or "").strip() or "USA"
            loc_dlg.close()
            save()
        with ui.element("div").style("display:flex;gap:8px;justify-content:flex-end;"
                                     "width:100%;margin-top:8px;"):
            with ui.element("button").classes("fd-gb").style(
                    "padding:8px 16px;font-size:13px;").on("click", loc_dlg.close):
                ui.label("Cancel")
            with ui.element("button").classes("fd-pb").style(
                    "padding:8px 16px;font-size:13px;").on("click", set_loc):
                ui.label("Save")

    with ui.element("div").classes("tms-kv"):
        ui.label("Email").classes("tms-k")
        with ui.element("div").classes("tms-pills"):
            with ui.element("button").classes("tms-pill " + ("on" if on else "off")).on(
                    "click", set_on):
                ui.icon("notifications_active" if on else "notifications_off")
                ui.label("On: every Tuesday and Thursday, 7am" if on
                         else "Off: click to turn it on")

        ui.label("Industries").classes("tms-k")
        with ui.element("div").classes("tms-pills"):
            for k in picked:
                with ui.element("span").classes("tms-pill ind"):
                    ui.label(labels[k])
                    with ui.element("button").classes("tms-x").props(
                            f'title="Remove {_e(labels[k])}"').on(
                            "click", lambda k=k: drop(k)):
                        ui.icon("close")
            rest = [k for k in labels if k not in picked]
            if rest:
                with ui.element("button").classes("tms-pill add"):
                    ui.icon("add")
                    ui.label("Add industry" if picked else "Pick an industry")
                    with ui.menu():
                        for k in rest:
                            ui.menu_item(labels[k], on_click=lambda k=k: add(k))

        ui.label("Location").classes("tms-k")
        with ui.element("div").classes("tms-pills"):
            with ui.element("button").classes("tms-pill").props(
                    'title="Change location"').on("click", loc_dlg.open):
                ui.icon("place")
                ui.label(loc)
                ui.icon("edit").classes("tms-edit")

        if on and picked:
            ui.label("Next issue").classes("tms-k")
            with ui.element("div").classes("tms-pills"):
                with ui.element("span").classes("tms-pill"):
                    ui.icon("event")
                    ui.label(when)

    if just_saved:
        with ui.element("div").classes("tms-note good"):
            ui.icon("check_circle")
            ui.label("Saved.")
    elif not (on and picked):
        with ui.element("div").classes("tms-note"):
            ui.label("Turn the email on and pick at least one industry to get it.")


def _state(s, settings):
    # _tms_fresh is set by the host's _PAGE_LANDING on a sidebar click, so
    # the form always opens on what is saved, not on an unsaved edit.
    if getattr(s, "_tms_fresh", True):
        s._tms_fresh = False
        s._tms_enabled = bool(settings.get("enabled"))
        s._tms_industries = list(settings.get("industries") or [])
        s._tms_location = settings.get("location") or "USA"
    for attr, default in (("_tms_running", False), ("_tms_msg", ""),
                          ("_tms_open", "")):
        if not hasattr(s, attr):
            setattr(s, attr, default)


def _text(body, C, size=12, weight=400, colour=None, mb=0):
    ui.label(body).style(
        f"font-size:{size}px;font-weight:{weight};color:{colour or C['text_l']};"
        f"line-height:1.55;display:block;margin-bottom:{mb}px;")


def _issue_rows(C, issue):
    for sec in issue.get("sections") or []:
        rows = sec.get("companies") or []
        news = sec.get("news") or []
        if not rows and not news:
            continue
        _text(sec["label"], C, 15, 800, C["text_l"], 8)
        for group, title, colour in ((True, "Move on these now", C["danger"]),
                                     (False, "Worth a look", C["teal"])):
            sub = [r for r in rows if SIGNAL_BY_ID[r["signal"]]["urgent"] is group]
            if not sub:
                continue
            ui.label(title).classes("tms-sec").style(f"color:{colour};")
            for r in sub:
                sig = SIGNAL_BY_ID[r["signal"]]
                with ui.element("div").classes("tms-row"):
                    with ui.element("div").style("display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;"):
                        _text(r["company"], C, 14, 700, C["text_l"])
                        if r.get("location"):
                            _text(r["location"], C, 11, colour=C["muted"])
                    with ui.element("div").style("margin:4px 0 6px;"):
                        ui.html(f'<span class="tms-badge" style="background:{colour};">'
                                f'{_e(sig["label"])}</span>'
                                f'<span style="font-size:11px;color:{C["muted"]};">'
                                f'{_e(_pretty_date(r["date"]))}</span>', sanitize=False)
                    _text(r["headline"], C, 13, 600, C["text_l"], 2)
                    _text(r["why_now"], C, 12, colour=C["text_l"], mb=4)
                    if r.get("opener"):
                        ui.label(r["opener"]).style(
                            f"font-size:12px;color:{C['text_l']};font-style:italic;"
                            f"border-left:3px solid {C['border']};padding:4px 10px;"
                            "display:block;margin:0 0 6px;")
                    ui.html(f'<a href="{_e(r["source_url"])}" target="_blank" rel="noopener">Source</a>',
                            sanitize=False)
        if news:
            ui.label("Industry news").classes("tms-sec").style(f"color:{C['text_l']};")
            for n in news:
                with ui.element("div").style(f"padding:6px 0;border-bottom:1px solid {C['border']};"):
                    head = _e(n["headline"])
                    if n.get("source_url"):
                        head = f'<a href="{_e(n["source_url"])}" target="_blank" rel="noopener">{head}</a>'
                    when = (f' <span style="font-size:11px;color:{C["muted"]};">'
                            f'{_e(_pretty_date(n["date"]))}</span>') if n.get("date") else ""
                    ui.html(f'<div style="font-size:13px;">{head}{when}</div>', sanitize=False)
                    if n.get("summary"):
                        _text(n["summary"], C, 12, colour=C["text_l"])


def render_page(s, rf):
    ff = _ff()
    C = ff.C
    email = (getattr(s, "_user_email", "") or "").strip().lower()
    if email:
        try:
            ff._CURRENT_USER_EMAIL.set(email)
        except Exception:
            pass
    settings = load_settings()
    _state(s, settings)
    labels = {k: v["label"] for k, v in verticals()}

    def _save(notify=True):
        settings = load_settings()
        settings["enabled"] = bool(s._tms_enabled)
        settings["industries"] = [k for k in labels if k in (s._tms_industries or [])]
        settings["location"] = (s._tms_location or "").strip() or "USA"
        save_settings(settings)
        if notify:
            s._tms_just_saved = True
        rf()

    def _send_now():
        if not s._tms_industries:
            ui.notify("Pick at least one industry first.", type="warning")
            return
        if not ff.ANTHROPIC_API_KEY:
            ui.notify("Anthropic API key missing. See Email & AI Setup.", type="warning")
            return
        _save(notify=False)
        s._tms_running = True
        s._tms_msg = ""
        user_dir = ff._resolve_user_root()

        def _run():
            try:
                issue = run_issue(email, user_dir, send=True)
                if issue is None:
                    s._tms_msg = "That did not work. Try again in a minute."
                elif issue.get("sent_at"):
                    s._tms_msg = f"Sent to {email}."
                else:
                    s._tms_msg = issue.get("send_error") or "Built, but the email did not go."
            finally:
                s._tms_running = False
        rf()
        ff._run_as_user(email, _run, name="tm_signals_now")

    with ui.element("div").classes("tms-wrap"):
        _css()
        with ui.element("div").style("margin-bottom:14px;"):
            ui.label("Buying News & Signals").classes("fd-h1")
            ui.label("Every Tuesday and Thursday: companies in your industries showing a "
                     "signal worth moving on now, and the news behind them. "
                     f"Sent to {email or 'your login email'} from your connected mailbox."
                     ).classes("fd-sub")

        with ui.element("div").classes("tms-card"):
            ui.label("Your email").classes("tms-sec").style(f"color:{C['teal']};")
            when = next_send(_user_now(ff, ff.load_config() or {}))
            when_txt = when.strftime("%A %d %b, %I%p").replace(" 0", " ").lstrip("0")
            just_saved = bool(getattr(s, "_tms_just_saved", False))
            s._tms_just_saved = False
            _settings_panel(s, ff, C, labels, when_txt, just_saved, _save)
            with ui.element("div").style("display:flex;gap:10px;align-items:center;"
                                         "flex-wrap:wrap;margin-top:16px;"):
                if s._tms_running:
                    with ui.element("div").style("display:flex;align-items:center;gap:8px;"):
                        ui.spinner("dots", size="sm")
                        ui.label("Researching your industries. This takes a minute or two; "
                                 "the email lands when it is done.").style(
                            f"font-size:12px;color:{C['muted']};")

                    def _poll():
                        if not getattr(s, "_tms_running", False):
                            try:
                                rf()
                            except Exception:
                                pass
                    ui.timer(2.0, _poll)
                else:
                    with ui.element("button").classes("fd-gb").style(
                            "padding:10px 20px;font-size:13px;").on("click", _send_now):
                        ui.label("Send me one now")
                    if s._tms_msg:
                        _text(s._tms_msg, C, 12, colour=C["muted"])

        with ui.element("div").classes("tms-card"):
            ui.label("What counts as a signal").classes("tms-sec").style(f"color:{C['teal']};")
            with ui.element("div").classes("tms-grid"):
                for sig in SIGNALS:
                    with ui.element("div").classes("tms-sig"):
                        ui.html(f'<span class="tms-badge" style="background:'
                                f'{C["danger"] if sig["urgent"] else C["teal"]};margin-top:2px;">'
                                f'{"Now" if sig["urgent"] else "Watch"}</span>', sanitize=False)
                        with ui.element("div"):
                            _text(sig["label"], C, 12, 700, C["text_l"])
                            _text(sig["why"], C, 11, colour=C["muted"])

        issues = settings.get("issues") or []
        ui.label("Latest issues").classes("tms-sec").style(f"color:{C['teal']};margin-top:6px;")
        if not issues:
            with ui.element("div").classes("tms-card"):
                _text("No issues yet. Turn the email on, or press Send me one now.",
                      C, 13, colour=C["muted"])
            return
        for i, issue in enumerate(issues):
            d = _parse_date(issue.get("date"))
            title = d.strftime("%A %d %B").replace(" 0", " ") if d else issue.get("date", "")
            n = sum(len(sec.get("companies") or []) for sec in issue.get("sections") or [])
            note = (f"{n} compan{'y' if n == 1 else 'ies'}"
                    + (" · sent" if issue.get("sent_at") else
                       (" · " + issue["send_error"] if issue.get("send_error") else "")))
            with ui.element("div").classes("tms-card"):
                open_ = (s._tms_open == issue.get("id")) or (i == 0 and not s._tms_open)
                with ui.element("div").style("display:flex;justify-content:space-between;"
                                             "align-items:center;cursor:pointer;").on(
                        "click", lambda iid=issue.get("id"): (setattr(s, "_tms_open", iid), rf())):
                    with ui.element("div"):
                        _text(title, C, 14, 700, C["text_l"])
                        _text(note, C, 11, colour=C["muted"])
                    ui.icon("expand_less" if open_ else "expand_more").style(
                        f"color:{C['muted']};font-size:20px;")
                if open_:
                    with ui.element("div").style("margin-top:12px;"):
                        if n == 0 and not any(sec.get("news") for sec in issue.get("sections") or []):
                            _text(issue_failure(issue) or "Nothing found that time.",
                                  C, 12, colour=C["muted"])
                        else:
                            _issue_rows(C, issue)

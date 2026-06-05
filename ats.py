"""Arena ATS — a full-screen, gated resume-search app inside DripDrop.

Registered as its own page (`/ats`) with its own sidebar + top bar, so clicking
"ATS" in DripDrop leaves the main chrome and enters a dedicated application.
Visible ONLY to ALLOWED_EMAILS while in development.

Heavy app helpers (colors, AI key, base data dir, inject_styles) come from the
already-running flowdrip_app via _ff() — never `import flowdrip_app` directly
(the server runs it as __main__, so re-importing re-executes the whole app).
"""
import os, re, json, sqlite3, sys
from pathlib import Path
from nicegui import app, ui


def _ff():
    """The already-loaded flowdrip_app module (as 'flowdrip_app' or '__main__').
    Avoids re-executing the app — see the middleware-error fix."""
    for name in ("flowdrip_app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_BASE_DATA_DIR") and hasattr(m, "C"):
            return m
    import flowdrip_app as m  # standalone/test fallback
    return m


ALLOWED_EMAILS = {
    "michael.vaughn@arenastaffing.net",
    "mkvaughn1987@gmail.com",
}


def is_allowed(email: str) -> bool:
    return bool(email) and email.strip().lower() in ALLOWED_EMAILS


# ── Resources ─────────────────────────────────────────────────────────────
def _db_path() -> Path:
    p = os.environ.get("ATS_DB_PATH")
    if p:
        return Path(p)
    try:
        return _ff()._BASE_DATA_DIR / "ats.db"
    except Exception:
        return Path(os.path.expandvars(r"%LOCALAPPDATA%\DripDrop")) / "ats.db"


_notes_col_ensured = False


def _con():
    global _notes_col_ensured
    con = sqlite3.connect(str(_db_path()))
    con.row_factory = sqlite3.Row
    if not _notes_col_ensured:
        # One-time, idempotent schema top-ups.
        try:
            con.execute("ALTER TABLE talents ADD COLUMN notes TEXT DEFAULT ''")
        except Exception:
            pass  # already exists
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS pipelines("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, query TEXT, "
                "owner TEXT, created_at TEXT)")
        except Exception:
            pass
        con.commit()
        _notes_col_ensured = True
    return con


def save_notes(tid: int, text: str):
    import time
    con = _con()
    try:
        con.execute("UPDATE talents SET notes=?, updated_at=? WHERE id=?",
                    (text or "", time.strftime("%Y-%m-%dT%H:%M:%S"), tid))
        con.commit()
    except Exception:
        pass
    finally:
        con.close()


# ── Pipelines (saved talent segments) ────────────────────────────────────
def list_pipelines() -> list:
    con = _con()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM pipelines ORDER BY id")]
    except Exception:
        return []
    finally:
        con.close()


def add_pipeline(name: str, query: str, owner: str):
    import time
    con = _con()
    try:
        con.execute("INSERT INTO pipelines(name,query,owner,created_at) VALUES(?,?,?,?)",
                    (name.strip(), query.strip(), owner, time.strftime("%Y-%m-%dT%H:%M:%S")))
        con.commit()
    except Exception:
        pass
    finally:
        con.close()


def delete_pipeline(pid: int):
    con = _con()
    try:
        con.execute("DELETE FROM pipelines WHERE id=?", (pid,))
        con.commit()
    except Exception:
        pass
    finally:
        con.close()


def search_count(query: str) -> int:
    """Strict (AND) count of FTS matches for a pipeline — every term must hit."""
    terms = _terms(query)
    if not terms:
        return 0
    con = _con()
    try:
        expr = " AND ".join('"%s"' % t.replace('"', '') for t in terms)
        return con.execute(
            "SELECT COUNT(*) FROM talents_fts WHERE talents_fts MATCH ?",
            (expr,)).fetchone()[0]
    except Exception:
        return 0
    finally:
        con.close()


_DEFAULT_PIPELINES = [
    ("Los Angeles Construction", "Los Angeles construction"),
    ("Denver Construction", "Denver construction"),
    ("California Superintendents", "California superintendent"),
    ("Texas Project Managers", "Texas project manager"),
    ("Hawaii Construction", "Hawaii construction"),
    ("California Estimators", "estimator California"),
    ("Plant Managers", "plant manager"),
    ("Data Center Construction", "data center construction"),
    ("CNC Machinist · Utah", "CNC machinist Utah"),
]


def ensure_default_pipelines(owner: str):
    """Populate a richer set of starter pipelines once (idempotent via a meta
    flag), skipping any name that already exists so the user's own pipelines
    and deletions are respected."""
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS ats_meta(key TEXT PRIMARY KEY, value TEXT)")
        if con.execute("SELECT value FROM ats_meta WHERE key='defaults_v2'").fetchone():
            return
        existing = {r[0] for r in con.execute("SELECT name FROM pipelines")}
        import time
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        for nm, q in _DEFAULT_PIPELINES:
            if nm in existing:
                continue
            con.execute("INSERT INTO pipelines(name,query,owner,created_at) VALUES(?,?,?,?)",
                        (nm, q, owner, now))
        con.execute("INSERT OR REPLACE INTO ats_meta(key,value) VALUES('defaults_v2','1')")
        con.commit()
    except Exception:
        pass
    finally:
        con.close()


def _api_key() -> str:
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    try:
        ff = _ff()
        if ff.ANTHROPIC_API_KEY:
            return ff.ANTHROPIC_API_KEY
    except Exception:
        pass
    return ""


# ── Search ────────────────────────────────────────────────────────────────
_STOP = {"the", "and", "for", "with", "you", "your", "our", "are", "has",
         "have", "will", "that", "this", "from", "job", "role", "position",
         "candidate", "candidates", "experience", "years", "year", "work",
         "ability", "strong", "must", "should", "etc", "including", "plus"}


def _terms(text: str) -> list:
    out, seen = [], set()
    for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\.]*", text or ""):
        wl = w.lower()
        if len(w) < 2 or wl in _STOP or wl in seen:
            continue
        seen.add(wl)
        out.append(w)
    return out


def keyword_search(q: str, limit: int = 80, strict: bool = False) -> list:
    terms = _terms(q)
    if not terms:
        return []
    con = _con()
    try:
        def run(joiner):
            expr = joiner.join('"%s"' % t.replace('"', '') for t in terms)
            return con.execute(
                """SELECT t.*, bm25(talents_fts) AS rank
                   FROM talents_fts f JOIN talents t ON t.id=f.rowid
                   WHERE talents_fts MATCH ? ORDER BY rank LIMIT ?""",
                (expr, limit)).fetchall()
        rows = run(" AND ")
        # General search broadens to OR for recall; strict (pipelines) does not.
        if not rows and not strict:
            rows = run(" OR ")
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def jd_extract(jd_text: str) -> dict:
    key = _api_key()
    if not key:
        return {}
    try:
        import anthropic
        msg = anthropic.Anthropic(api_key=key).messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=400,
            system="You extract resume-search criteria from a job description. JSON only.",
            messages=[{"role": "user", "content":
                "From the job description below, extract terms to find matching "
                "resumes. Return ONLY JSON:\n"
                '{"title":"","must_have_skills":[],"nice_to_have":[],'
                '"location":"","seniority":""}\n'
                "Skills must be short keywords (1-3 words). Base it strictly on "
                "the JD.\n\nJOB DESCRIPTION:\n<<<\n" + (jd_text or "")[:6000] + "\n>>>"}])
        m = re.search(r"\{.*\}", msg.content[0].text, re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception:
        return {}


def jd_search(jd_text: str, limit: int = 80):
    crit = jd_extract(jd_text)
    terms = list(_terms(crit.get("title", "")))
    for s in (crit.get("must_have_skills") or []):
        terms += _terms(s)
    for s in (crit.get("nice_to_have") or []):
        terms += _terms(s)
    seen, uterms = set(), []
    for t in terms:
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        uterms.append(t)
    if not uterms:
        return crit, [], []
    con = _con()
    try:
        expr = " OR ".join('"%s"' % t.replace('"', '') for t in uterms)
        rows = con.execute(
            """SELECT t.*, bm25(talents_fts) AS rank
               FROM talents_fts f JOIN talents t ON t.id=f.rowid
               WHERE talents_fts MATCH ? ORDER BY rank LIMIT ?""",
            (expr, limit)).fetchall()
        return crit, [dict(r) for r in rows], uterms
    except Exception:
        return crit, [], uterms
    finally:
        con.close()


def match_reasons(row: dict, terms: list) -> list:
    hay = " ".join([row.get("current_title") or "", row.get("skills") or "",
                    row.get("city") or "", row.get("state") or "",
                    row.get("resume_text") or ""]).lower()
    return [t for t in terms if t.lower() in hay]


def recent(limit: int = 50) -> list:
    con = _con()
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM talents ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
    except Exception:
        return []
    finally:
        con.close()


def total_count() -> int:
    con = _con()
    try:
        return con.execute("SELECT COUNT(*) FROM talents").fetchone()[0]
    except Exception:
        return 0
    finally:
        con.close()


def get_one(tid: int) -> dict:
    con = _con()
    try:
        r = con.execute("SELECT * FROM talents WHERE id=?", (tid,)).fetchone()
        return dict(r) if r else {}
    except Exception:
        return {}
    finally:
        con.close()


# ── Pool aggregation (Dashboard) ─────────────────────────────────────────
_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


def _norm_state(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if len(s) == 2 and s.isalpha():
        return s.upper()
    return _STATES.get(s.lower(), s[:14])


# Ordered industry rules (first whole-word keyword hit wins). Tuned for a
# skilled-trades / construction / manufacturing pool.
_INDUSTRY_RULES = [
    ("Construction", ["superintendent", "project manager", "project mgr", "estimator",
        "estimating", "project engineer", "construction", "foreman", "civil", "concrete",
        "oshpd", "precon", "preconstruction", "general contractor", "field engineer",
        "carpenter", "drywall", "framing", "masonry", "contractor", "subcontractor"]),
    ("Manufacturing", ["plant manager", "plant director", "production", "manufacturing",
        "assembly", "fabrication", "machining", "cnc", "molding", "extrusion",
        "process engineer", "production supervisor"]),
    ("Skilled Trades", ["electrician", "welder", "plumber", "hvac", "pipefitter",
        "millwright", "machinist", "journeyman", "mechanic", "installer", "ironworker",
        "sheet metal", "boilermaker", "lineman", "apprentice"]),
    ("Engineering", ["engineer", "design", "drafter", "cad", "structural"]),
    ("Finance & Admin", ["controller", "accountant", "accounting", "cfo", "finance",
        "payroll", "bookkeeper", "audit", "human resources", "office manager",
        "administrative", "executive assistant", "recruiter"]),
    ("Sales & BD", ["sales", "business development", "account executive",
        "account manager", "marketing"]),
    ("Logistics & Supply", ["logistics", "supply chain", "distribution", "procurement",
        "warehouse", "materials", "inventory", "fleet"]),
    ("Healthcare", ["nurse", "clinical", "medical", "healthcare", "physician", "caregiver"]),
]


def _industry_of(title: str, skills: str) -> str:
    hay = ((title or "") + " " + (skills or "")).lower()
    for ind, kws in _INDUSTRY_RULES:
        for kw in kws:
            if re.search(r"\b" + re.escape(kw) + r"\b", hay):
                return ind
    return "Other"


_ROLE_RULES = [
    ("Superintendent", ["superintendent"]),
    ("Project Manager", ["project manager", "project mgr"]),
    ("Project Engineer", ["project engineer"]),
    ("Estimator", ["estimator", "estimating"]),
    ("Construction Manager", ["construction manager"]),
    ("Plant Manager", ["plant manager", "plant director"]),
    ("Production Manager", ["production manager", "production supervisor"]),
    ("Operations Manager", ["operations manager", "director of operations", "operations director"]),
    ("Foreman", ["foreman"]),
    ("Electrician", ["electrician"]),
    ("Controller", ["controller"]),
    ("Engineer", ["engineer"]),
    ("Director / VP", ["director", "vice president", "vp", "president", "chief", "executive"]),
    ("Manager", ["manager"]),
]


def _role_family(title: str) -> str:
    t = (title or "").lower()
    for fam, kws in _ROLE_RULES:
        for kw in kws:
            if re.search(r"\b" + re.escape(kw) + r"\b", t):
                return fam
    return ((title or "").strip()[:24]) or "Other"


def dashboard_stats() -> dict:
    from collections import Counter
    from datetime import date, timedelta
    con = _con()
    try:
        total = con.execute("SELECT COUNT(*) FROM talents").fetchone()[0]
        wk = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
        added_week = con.execute(
            "SELECT COUNT(*) FROM talents WHERE substr(created_at,1,10) >= ?", (wk,)
        ).fetchone()[0]
        rows = con.execute("SELECT current_title, skills, state FROM talents").fetchall()
    except Exception:
        return {"total": 0, "added_week": 0, "industries": [], "locations": [], "roles": []}
    finally:
        con.close()
    ind, role, loc = Counter(), Counter(), Counter()
    for r in rows:
        title = r["current_title"] or ""
        skills = r["skills"] or ""
        ind[_industry_of(title, skills)] += 1
        if title.strip():
            role[_role_family(title)] += 1
        stt = _norm_state(r["state"] or "")
        if stt:
            loc[stt] += 1
    inds = [(k, v) for k, v in ind.most_common() if k != "Other"]
    if ind.get("Other"):
        inds.append(("Other", ind["Other"]))
    return {
        "total": total, "added_week": added_week,
        "industries": inds,
        "locations": loc.most_common(10),
        "roles": role.most_common(10),
    }


# ── UI helpers ──────────────────────────────────────────────────────────
def _c(C, k, d):
    try:
        return C.get(k, d)
    except Exception:
        return d


_NAV = [
    ("dashboard",  "▦", "Dashboard"),
    ("candidates", "👥", "Candidates"),
    ("jobs",       "📋", "Jobs"),
    ("companies",  "🏢", "Companies"),
    ("searches",   "🔎", "Saved Searches"),
    ("reports",    "📈", "Reports"),
    ("settings",   "⚙", "Settings"),
]


def _fullname(d):
    return (f"{d.get('first_name','')} {d.get('last_name','')}").strip() or "(no name)"


def _loc(d):
    return ", ".join(x for x in [d.get('city', ''), d.get('state', '')] if x)


def _fit_pct(row, terms):
    """% of the active search terms this candidate matches (None if no search)."""
    if not terms:
        return None
    return int(round(len(match_reasons(row, terms)) / max(1, len(terms)) * 100))


def _fit_color(C, fit):
    return (_c(C, 'good', '#16A34A') if fit >= 75
            else _c(C, 'warn', '#D97706') if fit >= 40
            else _c(C, 'muted', '#94A3B8'))


def _ago(iso):
    from datetime import datetime
    try:
        dt = datetime.fromisoformat((iso or "")[:19])
    except Exception:
        return ""
    s = (datetime.now() - dt).total_seconds()
    if s < 3600:
        return f"{max(1, int(s // 60))}m ago"
    if s < 86400:
        return f"{int(s // 3600)}h ago"
    return f"{int(s // 86400)}d ago"


def _drill(st, refresh, query, strict=False):
    """Run a keyword search and jump to the Candidates view."""
    st["mode"] = "keywords"
    st["query"] = query
    st["results"] = keyword_search(query, strict=strict)
    st["terms"] = _terms(query)
    st["crit"] = {}
    st["view"] = "candidates"
    refresh()


def _add_pipeline_dialog(ff, st, refresh):
    C = ff.C
    with ui.dialog() as dlg, ui.card().style(
            f"background:{_c(C,'card','#FFFFFF')};border:1px solid {_c(C,'border','#E2E8F0')};"
            f"min-width:440px;padding:22px 24px;"):
        ui.label("New Pipeline").style(
            f"font-size:16px;font-weight:800;color:{_c(C,'text_l','#0F172A')};"
            f"font-family:'Nunito',sans-serif;margin-bottom:2px;")
        ui.label("A saved talent segment — name it and give it search terms "
                 "(role + location work great).").style(
            f"font-size:12px;color:{_c(C,'muted','#94A3B8')};margin-bottom:14px;")
        ui.label("Name").style(f"font-size:11px;font-weight:700;color:{_c(C,'muted','#94A3B8')};")
        name_in = ui.input(placeholder="e.g. CNC Machinist · Utah").props("outlined dense").style("width:100%;margin-bottom:10px;")
        ui.label("Search terms").style(f"font-size:11px;font-weight:700;color:{_c(C,'muted','#94A3B8')};")
        q_in = ui.input(placeholder="e.g. CNC Machinist Utah").props("outlined dense").style("width:100%;margin-bottom:6px;")

        def _save():
            nm = (name_in.value or "").strip()
            q = (q_in.value or "").strip()
            if not nm or not q:
                ui.notify("Give it a name and search terms.", type="warning"); return
            add_pipeline(nm, q, st.get("name", "") or "")
            dlg.close()
            refresh()
        with ui.element("div").style("display:flex;gap:8px;justify-content:flex-end;margin-top:12px;"):
            ui.button("Cancel", on_click=dlg.close).props("flat").style(f"color:{_c(C,'muted','#94A3B8')};")
            ui.button("Add Pipeline", on_click=_save).props("unelevated").style(
                f"background:{_c(C,'teal','#1AE3D9')};color:#08121f;font-weight:700;")
    dlg.open()


# ── Views ────────────────────────────────────────────────────────────────
def _bars(C, items, st, refresh):
    if not items:
        ui.label("No data yet.").style(f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")
        return
    maxc = max((c for _, c in items), default=1) or 1
    for label, count in items:
        pct = max(4, int(round(count / maxc * 100)))

        def _drill(_e=None, q=label):
            st["mode"] = "keywords"
            st["query"] = q
            st["results"] = keyword_search(q)
            st["terms"] = _terms(q)
            st["crit"] = {}
            st["view"] = "candidates"
            refresh()
        with ui.element("div").style(
                "display:flex;align-items:center;gap:12px;margin-bottom:9px;cursor:pointer;"
                ).on("click", _drill):
            ui.label(label).style(
                f"width:150px;flex-shrink:0;font-size:12px;color:{_c(C,'text','#334155')};"
                f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
            with ui.element("div").style(
                    f"flex:1;background:{_c(C,'surface','#EEF2F8')};border-radius:6px;"
                    f"height:20px;overflow:hidden;"):
                ui.element("div").style(
                    f"width:{pct}%;height:100%;background:{_c(C,'teal','#1AE3D9')};"
                    f"border-radius:6px;")
            ui.label(f"{count:,}").style(
                f"width:50px;text-align:right;font-size:12px;font-weight:700;"
                f"color:{_c(C,'text_l','#0F172A')};")


def _view_dashboard(ff, st, refresh):
    C = ff.C
    ensure_default_pipelines(st.get("name", "") or "Mike Vaughn")
    stats = dashboard_stats()
    ui.label("Your Talent Pool").style(
        f"font-size:22px;font-weight:800;color:{_c(C,'text_l','#0F172A')};"
        f"font-family:'Nunito',sans-serif;")
    ui.label("A high-level snapshot of what's in your database. Click any bar to "
             "see those candidates.").style(
        f"font-size:12px;color:{_c(C,'muted','#94A3B8')};margin-bottom:16px;")

    # Stat tiles
    with ui.element("div").style("display:flex;gap:14px;margin-bottom:18px;flex-wrap:wrap;"):
        for val, lbl in ((f"{stats['total']:,}", "Total talents"),
                         (f"{stats['added_week']:,}", "Added this week")):
            with ui.element("div").style(
                    f"flex:1;min-width:160px;background:{_c(C,'card','#FFFFFF')};"
                    f"border:1px solid {_c(C,'border','#E2E8F0')};border-radius:12px;"
                    f"padding:16px 18px;"):
                ui.label(val).style(
                    f"font-size:26px;font-weight:800;color:{_c(C,'teal','#1AE3D9')};"
                    f"font-family:'Nunito',sans-serif;line-height:1;")
                ui.label(lbl).style(
                    f"font-size:11px;font-weight:600;color:{_c(C,'muted','#94A3B8')};"
                    f"text-transform:uppercase;letter-spacing:.06em;margin-top:6px;")

    _box = (f"background:{_c(C,'card','#FFFFFF')};border:1px solid {_c(C,'border','#E2E8F0')};"
            f"border-radius:12px;padding:18px 20px;")
    _box_title = (f"font-size:15px;font-weight:800;color:{_c(C,'text_l','#0F172A')};"
                  f"font-family:'Nunito',sans-serif;")
    _sub_title = (f"font-size:12px;font-weight:700;color:{_c(C,'muted','#94A3B8')};"
                  f"text-transform:uppercase;letter-spacing:.05em;margin-bottom:12px;")

    # ── Pipelines box ──
    with ui.element("div").style(_box + "margin-bottom:14px;"):
        with ui.element("div").style("display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;"):
            ui.label("Pipelines").style(_box_title)
            with ui.element("button").style(
                    f"background:{_c(C,'teal','#1AE3D9')};color:#08121f;border:0;border-radius:8px;"
                    f"padding:6px 14px;font-size:12px;font-weight:700;cursor:pointer;font-family:inherit;"
                    ).on("click", lambda: _add_pipeline_dialog(ff, st, refresh)):
                ui.label("+ Add Pipeline")
        pls = list_pipelines()
        with ui.element("div").style("display:flex;flex-wrap:wrap;gap:12px;"):
            if not pls:
                ui.label("No pipelines yet — add one to track a niche (role + location).").style(
                    f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")
            for p in pls:
                cnt = search_count(p.get("query", ""))

                def _go(_e=None, q=p.get("query", "")):
                    _drill(st, refresh, q, strict=True)

                def _del(_e=None, pid=p.get("id")):
                    delete_pipeline(pid); refresh()
                with ui.element("div").style(
                        f"position:relative;flex:0 0 auto;min-width:180px;background:{_c(C,'surface','#F8FAFC')};"
                        f"border:1px solid {_c(C,'border','#E2E8F0')};border-radius:10px;"
                        f"padding:14px 16px;cursor:pointer;").on("click", _go):
                    ui.label(f"{cnt:,}").style(
                        f"font-size:24px;font-weight:800;color:{_c(C,'teal','#1AE3D9')};"
                        f"font-family:'Nunito',sans-serif;line-height:1;")
                    ui.label(p.get("name", "")).style(
                        f"font-size:12px;font-weight:600;color:{_c(C,'text_l','#0F172A')};margin-top:4px;")
                    with ui.element("div").style(
                            f"position:absolute;top:8px;right:10px;font-size:12px;color:{_c(C,'muted','#94A3B8')};"
                            f"cursor:pointer;").on("click.stop", _del):
                        ui.label("✕")

    # ── Talent Pool box: the 3 bar charts combined ──
    with ui.element("div").style(_box + "margin-bottom:14px;"):
        ui.label("Talent Pool").style(_box_title + "display:block;margin-bottom:14px;")
        with ui.element("div").style("display:grid;grid-template-columns:1fr 1fr 1fr;gap:28px;"):
            for sub, items in (("By Industry", stats["industries"]),
                               ("By Location", stats["locations"]),
                               ("By Role", stats["roles"])):
                with ui.element("div").style("min-width:0;"):
                    ui.label(sub).style(_sub_title)
                    _bars(C, items, st, refresh)

    # ── Recently Added box ──
    with ui.element("div").style(_box):
        ui.label("Recently Added").style(_box_title + "display:block;margin-bottom:10px;")
        recents = recent(10)
        if not recents:
            ui.label("Nothing yet.").style(f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")
        for r in recents:
            def _open_r(_e=None, i=r.get("id")):
                st["sel"] = i; st["tab"] = "resume"; st["view"] = "profile"; refresh()
            with ui.element("div").style(
                    f"display:flex;align-items:center;justify-content:space-between;gap:10px;"
                    f"padding:8px 0;border-bottom:1px solid {_c(C,'border','#EEF2F8')};cursor:pointer;"
                    ).on("click", _open_r):
                with ui.element("div").style("min-width:0;"):
                    ui.label(_fullname(r)).style(
                        f"font-size:12px;font-weight:700;color:{_c(C,'text_l','#0F172A')};")
                    ui.label(f"{r.get('current_title','') or '—'} · {r.get('added_by','') or '—'}").style(
                        f"font-size:11px;color:{_c(C,'muted','#94A3B8')};"
                        f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
                ui.label(_ago(r.get("created_at", ""))).style(
                    f"font-size:10px;color:{_c(C,'muted','#94A3B8')};flex-shrink:0;")
def _candidate_rows(C, st, refresh, rows, terms=None):
    if not rows:
        ui.label("No matches — try fewer or different keywords.").style(
            f"font-size:13px;color:{_c(C,'muted','#94A3B8')};padding:18px 2px;")
        return
    # header
    with ui.element("div").style(
            f"display:grid;grid-template-columns:1.4fr 1.5fr 0.9fr 0.9fr 0.7fr;gap:12px;"
            f"padding:8px 14px;border-bottom:1px solid {_c(C,'border','#243049')};"
            f"font-size:10px;font-weight:700;letter-spacing:.05em;"
            f"text-transform:uppercase;color:{_c(C,'muted','#94A3B8')};"):
        for h in ("Name", "Title / Employer", "Location", "Owner", "Status"):
            ui.label(h)
    for r in rows:
        tid = r.get("id")

        def _open(_e=None, i=tid):
            st["sel"] = i
            st["tab"] = "resume"
            st["view"] = "profile"
            refresh()
        with ui.element("div").style(
                f"display:grid;grid-template-columns:1.4fr 1.5fr 0.9fr 0.9fr 0.7fr;gap:12px;"
                f"padding:11px 14px;border-bottom:1px solid {_c(C,'border','#1c2740')};"
                f"cursor:pointer;align-items:center;").on("click", _open):
            with ui.element("div"):
                ui.label(_fullname(r)).style(
                    f"font-size:13px;font-weight:700;color:{_c(C,'text_l','#E6EDF7')};"
                    f"font-family:'Nunito',sans-serif;")
                if terms:
                    why = match_reasons(r, terms)[:6]
                    if why:
                        ui.label("matched: " + ", ".join(why)).style(
                            f"font-size:10px;color:{_c(C,'good','#34D399')};margin-top:2px;")
            with ui.element("div").style("min-width:0;"):
                ui.label(r.get("current_title", "") or "—").style(
                    f"font-size:12px;color:{_c(C,'text','#CBD5E1')};"
                    f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
                ui.label(r.get("current_employer", "") or "").style(
                    f"font-size:11px;color:{_c(C,'muted','#94A3B8')};"
                    f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
            ui.label(_loc(r) or "—").style(f"font-size:12px;color:{_c(C,'text','#CBD5E1')};")
            ui.label(r.get("added_by", "") or "—").style(
                f"font-size:12px;color:{_c(C,'text','#CBD5E1')};"
                f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
            with ui.element("div").style("text-align:right;"):
                fit = _fit_pct(r, terms)
                if fit is not None:
                    ui.label(f"{fit}% fit").style(
                        f"font-size:13px;font-weight:800;color:{_fit_color(C, fit)};line-height:1.1;")
                ui.label(r.get("status", "Candidate") or "Candidate").style(
                    f"font-size:10px;font-weight:600;color:{_c(C,'teal','#1AE3D9')};")


def _view_candidates(ff, st, refresh):
    C = ff.C
    with ui.element("div").style("display:flex;align-items:baseline;gap:10px;margin-bottom:14px;"):
        ui.label("Candidates").style(
            f"font-size:22px;font-weight:800;color:{_c(C,'text_l','#E6EDF7')};"
            f"font-family:'Nunito',sans-serif;")
        ui.label(f"{total_count():,} in database").style(
            f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")

    # Search card
    with ui.element("div").style(
            f"background:{_c(C,'card','#15203A')};border:1px solid {_c(C,'border','#243049')};"
            f"border-radius:12px;padding:16px 18px;margin-bottom:16px;"):
        def _set_mode(m):
            st["mode"] = m; refresh()
        with ui.element("div").style("display:flex;gap:8px;margin-bottom:12px;"):
            for mk, ml in (("keywords", "🔍 Keywords"), ("jd", "📄 Match a Job Description")):
                on = (st["mode"] == mk)
                with ui.element("button").style(
                        f"padding:7px 16px;font-size:12px;font-weight:600;border-radius:8px;"
                        f"cursor:pointer;font-family:inherit;border:1px solid "
                        f"{_c(C,'teal','#1AE3D9') if on else _c(C,'border','#243049')};"
                        f"background:{(_c(C,'teal','#1AE3D9')+'22') if on else 'transparent'};"
                        f"color:{_c(C,'teal','#1AE3D9') if on else _c(C,'text','#CBD5E1')};"
                        ).on("click", lambda _e, m=mk: _set_mode(m)):
                    ui.label(ml).style("pointer-events:none;")

        if st["mode"] == "keywords":
            _inp = ui.input(value=st.get("query", ""),
                            placeholder="e.g.  superintendent data center San Diego").props("outlined dense").style(
                f"width:100%;")

            def _do_kw():
                st["query"] = (_inp.value or "").strip()
                st["results"] = keyword_search(st["query"]) if st["query"] else []
                st["terms"] = _terms(st["query"])
                st["crit"] = {}
                refresh()
            _inp.on("keydown.enter", lambda _e: _do_kw())
            with ui.element("div").style("display:flex;justify-content:flex-end;margin-top:10px;"):
                with ui.element("button").style(
                        f"background:{_c(C,'teal','#1AE3D9')};color:#08121f;border:0;"
                        f"border-radius:8px;padding:8px 24px;font-size:13px;font-weight:700;"
                        f"cursor:pointer;font-family:inherit;").on("click", _do_kw):
                    ui.label("Search")
        else:
            _ta = ui.textarea(value=st.get("jd", ""),
                              placeholder="Paste the full job description here…").props("outlined").style(
                "width:100%;min-height:140px;")

            async def _do_jd():
                jd = (_ta.value or "").strip()
                st["jd"] = jd
                if not jd:
                    ui.notify("Paste a job description first.", type="warning"); return
                st["searching"] = True; refresh()
                from nicegui import run as _run
                crit, results, terms = await _run.io_bound(jd_search, jd)
                st["crit"], st["results"], st["terms"] = crit, results, terms
                st["searching"] = False
                refresh()
            with ui.element("div").style("display:flex;justify-content:flex-end;margin-top:10px;"):
                with ui.element("button").style(
                        f"background:{_c(C,'teal','#1AE3D9')};color:#08121f;border:0;"
                        f"border-radius:8px;padding:8px 24px;font-size:13px;font-weight:700;"
                        f"cursor:pointer;font-family:inherit;").on("click", _do_jd):
                    ui.label("✦ Find Matches")
            if st.get("searching"):
                with ui.element("div").style("display:flex;align-items:center;gap:8px;margin-top:10px;"):
                    ui.spinner("dots", size="18px", color=_c(C, 'teal', '#1AE3D9'))
                    ui.label("AI is reading the JD and ranking candidates…").style(
                        f"font-size:12px;color:{_c(C,'teal','#1AE3D9')};")
            elif st.get("crit"):
                cr = st["crit"]
                sk = ", ".join((cr.get("must_have_skills") or [])[:8])
                with ui.element("div").style(
                        f"background:{_c(C,'teal','#1AE3D9')}14;border:1px solid {_c(C,'teal','#1AE3D9')}40;"
                        f"border-radius:8px;padding:10px 14px;margin-top:10px;"):
                    ui.label(f"AI parsed: {cr.get('title','?')} ({cr.get('seniority','')}) · "
                             f"{cr.get('location','any location')}").style(
                        f"font-size:12px;font-weight:600;color:{_c(C,'teal','#1AE3D9')};")
                    if sk:
                        ui.label("Looking for: " + sk).style(
                            f"font-size:11px;color:{_c(C,'text_l','#E6EDF7')};margin-top:3px;")

    # Results / recent
    if st.get("results"):
        ui.label(f"{len(st['results'])} candidate(s)").style(
            f"font-size:12px;color:{_c(C,'muted','#94A3B8')};margin-bottom:6px;")
        _candidate_rows(C, st, refresh, st["results"], st.get("terms"))
    elif not st.get("searching"):
        ui.label("Recently added").style(
            f"font-size:11px;font-weight:700;color:{_c(C,'muted','#94A3B8')};"
            f"text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;")
        _candidate_rows(C, st, refresh, recent())


def _view_profile(ff, st, refresh):
    C = ff.C
    d = get_one(st.get("sel"))
    if not d:
        ui.label("Candidate not found.").style(f"color:{_c(C,'warn','#F59E0B')};")
        return

    def _back():
        st["view"] = "candidates"; st["sel"] = None; refresh()
    with ui.element("span").style(
            f"font-size:12px;color:{_c(C,'teal','#1AE3D9')};cursor:pointer;").on("click", _back):
        ui.label("← Candidates")

    with ui.element("div").style("display:grid;grid-template-columns:1fr 330px;gap:16px;margin-top:12px;"):
        # LEFT: header + tabs
        with ui.element("div"):
            with ui.element("div").style(
                    f"background:{_c(C,'card','#15203A')};border:1px solid {_c(C,'border','#243049')};"
                    f"border-radius:12px;padding:18px 20px;margin-bottom:14px;"):
                ui.label(_fullname(d)).style(
                    f"font-size:22px;font-weight:800;color:{_c(C,'text_l','#E6EDF7')};"
                    f"font-family:'Nunito',sans-serif;")
                ui.label(f"{d.get('current_title','') or '—'}  ·  {d.get('current_employer','')}").style(
                    f"font-size:13px;color:{_c(C,'muted','#94A3B8')};margin-top:2px;")
                with ui.element("div").style("display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;"):
                    for ic, val in (("📍", _loc(d)), ("✉", d.get('email', '')), ("☎", d.get('phone', ''))):
                        if val:
                            ui.label(f"{ic} {val}").style(f"font-size:12px;color:{_c(C,'text','#CBD5E1')};")

            # Tabs — Resume first.
            tabs = [("resume", "Resume"), ("summary", "Summary"), ("skills", "Skills"),
                    ("experience", "Experience"), ("activity", "Activity")]
            with ui.element("div").style(
                    f"display:flex;gap:4px;border-bottom:1px solid {_c(C,'border','#243049')};margin-bottom:12px;"):
                for tk, tl in tabs:
                    on = (st.get("tab", "resume") == tk)
                    def _set_tab(_e=None, k=tk):
                        st["tab"] = k; refresh()
                    with ui.element("div").style(
                            f"padding:8px 14px;font-size:12px;font-weight:600;cursor:pointer;"
                            f"color:{_c(C,'teal','#1AE3D9') if on else _c(C,'muted','#94A3B8')};"
                            f"border-bottom:2px solid {_c(C,'teal','#1AE3D9') if on else 'transparent'};"
                            ).on("click", _set_tab):
                        ui.label(tl)

            tab = st.get("tab", "resume")
            if tab == "summary":
                ui.label(d.get("summary", "") or "No summary parsed.").style(
                    f"font-size:13px;color:{_c(C,'text','#CBD5E1')};line-height:1.6;")
            elif tab == "skills":
                skills = [s.strip() for s in (d.get("skills", "") or "").split(",") if s.strip()]
                if skills:
                    with ui.element("div").style("display:flex;flex-wrap:wrap;gap:8px;"):
                        for s in skills:
                            ui.label(s).style(
                                f"background:{_c(C,'teal','#1AE3D9')}18;color:{_c(C,'teal','#1AE3D9')};"
                                f"border:1px solid {_c(C,'teal','#1AE3D9')}40;border-radius:99px;"
                                f"padding:4px 12px;font-size:12px;")
                else:
                    ui.label("No skills parsed.").style(f"color:{_c(C,'muted','#94A3B8')};font-size:12px;")
            elif tab == "resume":
                ui.html(
                    f'<div style="background:#FFFFFF;color:#0F172A;border-radius:8px;'
                    f'padding:18px;max-height:58vh;overflow:auto;white-space:pre-wrap;'
                    f'font-family:Arial,sans-serif;font-size:12px;line-height:1.5;">'
                    + (d.get("resume_text") or "(no resume text)").replace("<", "&lt;").replace(">", "&gt;")
                    + '</div>')
            else:
                ui.label("Coming soon.").style(f"color:{_c(C,'muted','#94A3B8')};font-size:12px;")

        # RIGHT rail: fit / status / owner / send, then Recruiter Notes
        with ui.element("div").style("display:flex;flex-direction:column;gap:14px;"):
            with ui.element("div").style(
                    f"background:{_c(C,'card','#15203A')};border:1px solid {_c(C,'border','#243049')};"
                    f"border-radius:12px;padding:16px;"):
                # Fit for the active search (if any)
                _terms = st.get("terms") or []
                _fit = _fit_pct(d, _terms) if _terms else None
                if _fit is not None:
                    ui.label("FIT FOR THIS SEARCH").style(
                        f"font-size:10px;font-weight:700;letter-spacing:.06em;color:{_c(C,'muted','#94A3B8')};")
                    ui.label(f"{_fit}%").style(
                        f"font-size:30px;font-weight:800;color:{_fit_color(C, _fit)};"
                        f"font-family:'Nunito',sans-serif;line-height:1;margin:2px 0 12px;")
                    ui.element("div").style(f"height:1px;background:{_c(C,'border','#243049')};margin:0 0 12px;")
                ui.label("STATUS").style(
                    f"font-size:10px;font-weight:700;letter-spacing:.06em;color:{_c(C,'muted','#94A3B8')};")
                ui.label(d.get("status", "Candidate") or "Candidate").style(
                    f"font-size:14px;font-weight:700;color:{_c(C,'teal','#1AE3D9')};margin:2px 0 12px;")
                ui.label("OWNER").style(
                    f"font-size:10px;font-weight:700;letter-spacing:.06em;color:{_c(C,'muted','#94A3B8')};")
                ui.label(d.get("added_by", "Mike Vaughn") or "Mike Vaughn").style(
                    f"font-size:13px;color:{_c(C,'text_l','#E6EDF7')};margin:2px 0 12px;")
                ui.element("div").style(f"height:1px;background:{_c(C,'border','#243049')};margin:6px 0 14px;")
                with ui.element("button").style(
                        f"width:100%;background:{_c(C,'teal','#1AE3D9')};color:#08121f;border:0;"
                        f"border-radius:8px;padding:10px;font-size:13px;font-weight:700;cursor:pointer;"
                        f"font-family:inherit;").on(
                        "click", lambda: ui.notify("Send to DripDrop outreach — coming next.", type="info")):
                    ui.label("✦ Send to Outreach")

            # Recruiter Notes — now on the right rail; saved notes show here.
            with ui.element("div").style(
                    f"background:{_c(C,'card','#15203A')};border:1px solid {_c(C,'border','#243049')};"
                    f"border-radius:12px;padding:16px;"):
                ui.label("RECRUITER NOTES").style(
                    f"font-size:10px;font-weight:700;letter-spacing:.06em;"
                    f"color:{_c(C,'muted','#94A3B8')};margin-bottom:8px;display:block;")
                _notes_in = ui.textarea(
                    value=d.get("notes", "") or "",
                    placeholder="Calls, availability, fit, rate, next steps…").props("outlined").style(
                    "width:100%;min-height:120px;")

                def _save_notes(_e=None, _i=d.get("id")):
                    save_notes(_i, _notes_in.value or "")
                    ui.notify("Notes saved.", type="positive", timeout=1500)
                _notes_in.on("blur", _save_notes)
                with ui.element("div").style("display:flex;justify-content:flex-end;margin-top:8px;"):
                    with ui.element("button").style(
                            f"width:100%;background:{_c(C,'teal','#1AE3D9')};color:#08121f;border:0;"
                            f"border-radius:8px;padding:8px;font-size:12px;font-weight:700;"
                            f"cursor:pointer;font-family:inherit;").on("click", _save_notes):
                        ui.label("Save Notes")


def _view_stub(ff, st, title, blurb):
    C = ff.C
    ui.label(title).style(
        f"font-size:22px;font-weight:800;color:{_c(C,'text_l','#E6EDF7')};"
        f"font-family:'Nunito',sans-serif;")
    with ui.element("div").style(
            f"background:{_c(C,'card','#15203A')};border:1px dashed {_c(C,'border','#243049')};"
            f"border-radius:12px;padding:36px;text-align:center;margin-top:16px;"):
        ui.label("🚧").style("font-size:32px;")
        ui.label(blurb).style(
            f"font-size:13px;color:{_c(C,'muted','#94A3B8')};margin-top:8px;")


def _render_app(ff, st, refresh):
    C = ff.C
    # Top bar
    with ui.element("div").style(
            f"flex:0 0 auto;height:56px;background:{_c(C,'card','#15203A')};"
            f"border-bottom:1px solid {_c(C,'border','#243049')};display:flex;"
            f"align-items:center;gap:14px;padding:0 20px;"):
        # DripDrop logo + Arena ATS brand (logo click → back to DripDrop home)
        with ui.element("div").style(
                "display:flex;align-items:center;gap:10px;cursor:pointer;").on(
                "click", lambda: ui.navigate.to("/")):
            ui.html('<img src="/static/dripdrop_logo.png?v=3" alt="DripDrop" '
                    'style="height:34px;display:block;" />')
            ui.label("Arena ATS").style(
                f"font-size:16px;font-weight:800;color:{_c(C,'teal','#1AE3D9')};"
                f"font-family:'Nunito',sans-serif;")
        ui.element("div").style("flex:1;")
        ui.label(st.get("name", "")).style(f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")
        with ui.element("button").style(
                f"background:transparent;border:1px solid {_c(C,'border','#243049')};"
                f"color:{_c(C,'text_l','#E6EDF7')};border-radius:8px;padding:6px 14px;"
                f"font-size:12px;cursor:pointer;font-family:inherit;").on(
                "click", lambda: ui.navigate.to("/")):
            ui.label("← DripDrop")

    # Body: sidebar + content
    with ui.element("div").style("flex:1;display:flex;min-height:0;"):
        # Sidebar
        with ui.element("div").style(
                f"flex:0 0 210px;background:{_c(C,'surface','#0E1726')};"
                f"border-right:1px solid {_c(C,'border','#243049')};padding:14px 10px;"
                f"display:flex;flex-direction:column;gap:2px;"):
            for key, icon, label in _NAV:
                on = (st["view"] == key) or (key == "candidates" and st["view"] == "profile")

                def _nav(_e=None, k=key):
                    st["view"] = k
                    if k != "profile":
                        st["sel"] = None
                    refresh()
                with ui.element("div").style(
                        f"display:flex;align-items:center;gap:10px;padding:9px 12px;"
                        f"border-radius:8px;cursor:pointer;"
                        f"background:{(_c(C,'teal','#1AE3D9')+'1f') if on else 'transparent'};"
                        ).on("click", _nav):
                    ui.label(icon).style("font-size:14px;width:18px;text-align:center;")
                    ui.label(label).style(
                        f"font-size:13px;font-weight:{700 if on else 500};"
                        f"color:{_c(C,'teal','#1AE3D9') if on else _c(C,'text','#CBD5E1')};")
            ui.element("div").style("flex:1;")
            ui.label(f"{total_count():,} talents").style(
                f"font-size:11px;color:{_c(C,'muted','#94A3B8')};padding:8px 12px;")

        # Content
        with ui.element("div").style("flex:1;min-width:0;overflow:auto;padding:24px 28px;"):
            v = st["view"]
            if v == "profile":
                _view_profile(ff, st, refresh)
            elif v == "candidates":
                _view_candidates(ff, st, refresh)
            elif v == "dashboard":
                _view_dashboard(ff, st, refresh)
            elif v == "jobs":
                _view_stub(ff, st, "Jobs", "Open requisitions — link candidates to roles and track submittals.")
            elif v == "companies":
                _view_stub(ff, st, "Companies", "Your client / CRM records.")
            elif v == "searches":
                _view_stub(ff, st, "Saved Searches", "Save a search or JD-match to re-run later.")
            elif v == "reports":
                _view_stub(ff, st, "Reports", "Time-to-fill, submittals, placements.")
            else:
                _view_stub(ff, st, "Settings", "ATS settings.")


@ui.page("/ats")
def ats_page():
    """Full-screen Arena ATS. Gated to ALLOWED_EMAILS."""
    if not app.storage.user.get("authenticated"):
        ui.navigate.to("/login"); return
    email = (app.storage.user.get("email") or "").strip().lower()
    if email not in ALLOWED_EMAILS:
        ui.navigate.to("/"); return
    ff = _ff()
    try:
        ff.inject_styles()
    except Exception:
        pass
    try:
        ff._switch_to_user_paths(app.storage.user.get("email", ""))
    except Exception:
        pass

    st = {
        "view": "dashboard", "tab": "summary", "mode": "keywords",
        "query": "", "jd": "", "results": [], "terms": [], "crit": {},
        "searching": False, "sel": None,
        "name": app.storage.user.get("name", "") or email,
    }
    root = ui.element("div").style(
        f"position:fixed;inset:0;overflow:hidden;display:flex;flex-direction:column;"
        f"background:{_c(ff.C,'surface','#0E1726')};")

    def refresh():
        root.clear()
        with root:
            _render_app(ff, st, refresh)
    refresh()

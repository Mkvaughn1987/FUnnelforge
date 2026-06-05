"""DripDrop ATS — gated, team-shared searchable resume database.

A SQLite + FTS5 database of Talent records parsed from resumes, plus a search
UI with two modes:
  * Keywords  — free-text full-text search across title/skills/resume body.
  * Match a JD — paste a job description; AI extracts the requirements and we
                 rank candidates by how well their resume matches.

Heavy app helpers (colors, AI key, base data dir) are imported LAZILY from
flowdrip_app so this module can be imported by flowdrip_app without a circular
import at load time, and tested standalone (set ATS_DB_PATH + ANTHROPIC_API_KEY
env to skip the heavy import).
"""
import os, re, json, sqlite3
from pathlib import Path
from nicegui import ui

# Emails allowed to see the ATS while it's in development. Mirror this in
# flowdrip_app's nav gate.
ALLOWED_EMAILS = {
    "michael.vaughn@arenastaffing.net",
    "mkvaughn1987@gmail.com",
}


def is_allowed(email: str) -> bool:
    return bool(email) and email.strip().lower() in ALLOWED_EMAILS


# ── Resources (lazy / fallback so the module is testable standalone) ──────
def _db_path() -> Path:
    p = os.environ.get("ATS_DB_PATH")
    if p:
        return Path(p)
    try:
        import flowdrip_app as ff
        return ff._BASE_DATA_DIR / "ats.db"
    except Exception:
        return Path(os.path.expandvars(r"%LOCALAPPDATA%\DripDrop")) / "ats.db"


def _con():
    con = sqlite3.connect(str(_db_path()))
    con.row_factory = sqlite3.Row
    return con


def _api_key() -> str:
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    try:
        import flowdrip_app as ff
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


def keyword_search(q: str, limit: int = 60) -> list:
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
        if not rows:  # too strict — broaden to OR for recall
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


def jd_search(jd_text: str, limit: int = 60):
    """Returns (criteria_dict, results, term_list)."""
    crit = jd_extract(jd_text)
    terms = list(_terms(crit.get("title", "")))
    for s in (crit.get("must_have_skills") or []):
        terms += _terms(s)
    for s in (crit.get("nice_to_have") or []):
        terms += _terms(s)
    # dedup preserving order
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


def recent(limit: int = 40) -> list:
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


# ── UI ──────────────────────────────────────────────────────────────────
def _detail_dialog(C, tid: int):
    d = get_one(tid)
    if not d:
        ui.notify("Talent not found.", type="warning")
        return
    with ui.dialog() as dlg, ui.card().style(
            f"background:{C['card']};border:1px solid {C['border']};"
            f"min-width:680px;max-width:760px;max-height:88vh;padding:0;"
            f"display:flex;flex-direction:column;"):
        with ui.element("div").style(
                f"padding:16px 22px;border-bottom:1px solid {C['border']};"
                f"display:flex;justify-content:space-between;align-items:flex-start;gap:12px;"):
            with ui.element("div").style("flex:1;min-width:0;"):
                ui.label(f"{d.get('first_name','')} {d.get('last_name','')}".strip()).style(
                    f"font-size:18px;font-weight:800;color:{C['text_l']};"
                    f"font-family:'Nunito',sans-serif;")
                ui.label(f"{d.get('current_title','')}  ·  {d.get('current_employer','')}").style(
                    f"font-size:13px;color:{C['muted']};margin-top:2px;")
                _loc = ", ".join(x for x in [d.get('city',''), d.get('state','')] if x)
                ui.label(f"{_loc}   |   {d.get('email','')}   |   {d.get('phone','')}").style(
                    f"font-size:12px;color:{C['text']};margin-top:6px;")
                if d.get("skills"):
                    ui.label("Skills: " + d["skills"]).style(
                        f"font-size:12px;color:{C['teal']};margin-top:6px;")
            with ui.element("button").classes("fd-gb").style(
                    "padding:6px 14px;font-size:12px;flex-shrink:0;").on("click", dlg.close):
                ui.label("Close")
        ui.html(
            f'<div style="flex:1;overflow:auto;padding:18px 22px;white-space:pre-wrap;'
            f'font-family:Consolas,monospace;font-size:12px;line-height:1.5;'
            f'color:{C["text"]};">'
            + (d.get("resume_text") or "(no resume text)").replace("<", "&lt;").replace(">", "&gt;")
            + '</div>')
    dlg.open()


def _results_table(C, rf, results: list, terms=None):
    if not results:
        ui.label("No matches. Try fewer/different keywords.").style(
            f"font-size:13px;color:{C['muted']};padding:16px 0;")
        return
    ui.label(f"{len(results)} candidate(s)").style(
        f"font-size:12px;color:{C['muted']};margin:6px 0 8px;")
    for r in results:
        tid = r.get("id")
        nm = f"{r.get('first_name','')} {r.get('last_name','')}".strip() or "(no name)"
        loc = ", ".join(x for x in [r.get('city', ''), r.get('state', '')] if x)
        reasons = match_reasons(r, terms) if terms else []
        with ui.element("div").style(
                f"background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:8px;padding:12px 16px;margin-bottom:8px;cursor:pointer;"
                ).on("click", lambda _e, i=tid: _detail_dialog(C, i)):
            with ui.element("div").style("display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;"):
                with ui.element("div").style("flex:1;min-width:0;"):
                    ui.label(nm).style(
                        f"font-size:14px;font-weight:700;color:{C['text_l']};"
                        f"font-family:'Nunito',sans-serif;")
                    ui.label(f"{r.get('current_title','') or '—'}  ·  "
                             f"{r.get('current_employer','') or ''}").style(
                        f"font-size:12px;color:{C['muted']};margin-top:1px;"
                        f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
                with ui.element("div").style("text-align:right;flex-shrink:0;"):
                    ui.label(loc or "—").style(f"font-size:11px;color:{C['text']};")
                    ui.label(r.get("status", "Candidate") or "Candidate").style(
                        f"font-size:10px;color:{C['teal']};font-weight:600;")
            if reasons:
                ui.label("matched: " + ", ".join(reasons[:8])).style(
                    f"font-size:10px;color:{C['good']};margin-top:6px;")


def render(s, rf):
    """ATS page — gated entry point called from flowdrip_app's dispatcher."""
    import flowdrip_app as ff
    C = ff.C

    # Per-session ATS state
    if not hasattr(s, "_ats_mode"):
        s._ats_mode = "keywords"
        s._ats_query = ""
        s._ats_jd = ""
        s._ats_results = []
        s._ats_terms = []
        s._ats_crit = {}
        s._ats_searching = False

    with ui.element("div").style("max-width:920px;margin:0 auto;padding:8px 12px 40px;"):
        with ui.element("div").style("display:flex;align-items:baseline;gap:10px;margin-bottom:4px;"):
            ui.label("ATS").classes("fd-h1").style("margin:0;")
            ui.label(f"{total_count():,} resumes searchable").style(
                f"font-size:12px;color:{C['muted']};")
        ui.label("Find candidates for a position — search by keywords, or paste a "
                 "job description and let AI rank the best matches.").classes("fd-sub")

        # Mode toggle
        def _set_mode(m):
            s._ats_mode = m; rf()
        with ui.element("div").style("display:flex;gap:8px;margin:14px 0 10px;"):
            for mk, ml in (("keywords", "🔍 Keywords"), ("jd", "📄 Match a Job Description")):
                on = (s._ats_mode == mk)
                with ui.element("button").classes("fd-pb" if on else "fd-gb").style(
                        "padding:8px 18px;font-size:13px;").on("click", lambda _e, m=mk: _set_mode(m)):
                    ui.label(ml).style("pointer-events:none;")

        # ── Keywords mode ──
        if s._ats_mode == "keywords":
            _inp = ui.input(value=s._ats_query,
                            placeholder="e.g.  superintendent data center San Diego").style(
                f"width:100%;background:{C['surface']};border:1px solid {C['border']};"
                f"border-radius:8px;padding:10px 14px;font-size:14px;color:{C['text_l']};")

            def _do_kw():
                s._ats_query = (_inp.value or "").strip()
                s._ats_results = keyword_search(s._ats_query) if s._ats_query else []
                s._ats_terms = _terms(s._ats_query)
                rf()
            _inp.on("keydown.enter", lambda _e: _do_kw())
            with ui.element("div").style("display:flex;justify-content:flex-end;margin-top:8px;"):
                with ui.element("button").classes("fd-pb").style(
                        "padding:8px 20px;font-size:13px;").on("click", lambda _e: _do_kw()):
                    ui.label("Search").style("pointer-events:none;")

        # ── JD mode ──
        else:
            _ta = ui.textarea(value=s._ats_jd,
                              placeholder="Paste the full job description here…").props(
                "outlined").style(
                f"width:100%;min-height:150px;background:{C['surface']};"
                f"border:1px solid {C['border']};border-radius:8px;padding:8px;"
                f"color:{C['text_l']};font-size:13px;")

            async def _do_jd():
                jd = (_ta.value or "").strip()
                s._ats_jd = jd
                if not jd:
                    ui.notify("Paste a job description first.", type="warning"); return
                s._ats_searching = True; rf()
                from nicegui import run as _run
                crit, results, terms = await _run.io_bound(jd_search, jd)
                s._ats_crit, s._ats_results, s._ats_terms = crit, results, terms
                s._ats_searching = False
                rf()
            with ui.element("div").style("display:flex;justify-content:flex-end;margin-top:8px;"):
                with ui.element("button").classes("fd-pb").style(
                        "padding:8px 20px;font-size:13px;").on("click", _do_jd):
                    ui.label("✦ Find Matches").style("pointer-events:none;")

            if s._ats_searching:
                with ui.element("div").style("display:flex;align-items:center;gap:8px;margin-top:10px;"):
                    ui.spinner("dots", size="18px", color=C["teal"])
                    ui.label("AI is reading the JD and ranking candidates…").style(
                        f"font-size:12px;color:{C['teal']};")
            elif s._ats_crit:
                _c = s._ats_crit
                _sk = ", ".join((_c.get("must_have_skills") or [])[:8])
                with ui.element("div").style(
                        f"background:{C['teal']}12;border:1px solid {C['teal']}40;"
                        f"border-radius:8px;padding:10px 14px;margin-top:10px;"):
                    ui.label(f"AI parsed: {_c.get('title','?')} "
                             f"({_c.get('seniority','')}) · {_c.get('location','any location')}").style(
                        f"font-size:12px;font-weight:600;color:{C['teal']};")
                    if _sk:
                        ui.label("Looking for: " + _sk).style(
                            f"font-size:11px;color:{C['text_l']};margin-top:3px;")

        # ── Results (or recent) ──
        ui.element("div").style(f"height:1px;background:{C['border']};margin:16px 0 8px;")
        if s._ats_results:
            _results_table(C, rf, s._ats_results, s._ats_terms)
        elif not s._ats_searching:
            ui.label("Recently added").style(
                f"font-size:11px;font-weight:700;color:{C['muted']};"
                f"text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;")
            _results_table(C, rf, recent())

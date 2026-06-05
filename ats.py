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


def _con():
    con = sqlite3.connect(str(_db_path()))
    con.row_factory = sqlite3.Row
    return con


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


def keyword_search(q: str, limit: int = 80) -> list:
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
        if not rows:
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


# ── Views ────────────────────────────────────────────────────────────────
def _candidate_rows(C, st, refresh, rows, terms=None):
    if not rows:
        ui.label("No matches — try fewer or different keywords.").style(
            f"font-size:13px;color:{_c(C,'muted','#94A3B8')};padding:18px 2px;")
        return
    # header
    with ui.element("div").style(
            f"display:grid;grid-template-columns:1.4fr 1.6fr 1fr 0.8fr;gap:12px;"
            f"padding:8px 14px;border-bottom:1px solid {_c(C,'border','#243049')};"
            f"font-size:10px;font-weight:700;letter-spacing:.05em;"
            f"text-transform:uppercase;color:{_c(C,'muted','#94A3B8')};"):
        for h in ("Name", "Title / Employer", "Location", "Status"):
            ui.label(h)
    for r in rows:
        tid = r.get("id")

        def _open(_e=None, i=tid):
            st["sel"] = i
            st["tab"] = "summary"
            st["view"] = "profile"
            refresh()
        with ui.element("div").style(
                f"display:grid;grid-template-columns:1.4fr 1.6fr 1fr 0.8fr;gap:12px;"
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
            ui.label(r.get("status", "Candidate") or "Candidate").style(
                f"font-size:11px;font-weight:600;color:{_c(C,'teal','#1AE3D9')};")


def _view_candidates(ff, st, refresh):
    C = ff.C
    with ui.element("div").style("display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:14px;"):
        with ui.element("div").style("display:flex;align-items:baseline;gap:10px;"):
            ui.label("Candidates").style(
                f"font-size:22px;font-weight:800;color:{_c(C,'text_l','#E6EDF7')};"
                f"font-family:'Nunito',sans-serif;")
            ui.label(f"{total_count():,} in database").style(
                f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")
        with ui.element("button").style(
                f"background:{_c(C,'teal','#1AE3D9')};color:#08121f;border:0;"
                f"border-radius:8px;padding:8px 16px;font-size:13px;font-weight:700;"
                f"cursor:pointer;font-family:inherit;").on(
                "click", lambda: ui.notify("Add Candidate / upload — coming next.", type="info")):
            ui.label("+ Add Candidate")

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
                ui.button("Search", on_click=_do_kw).props("unelevated").style(
                    f"background:{_c(C,'teal','#1AE3D9')};color:#08121f;font-weight:700;")
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
                ui.button("✦ Find Matches", on_click=_do_jd).props("unelevated").style(
                    f"background:{_c(C,'teal','#1AE3D9')};color:#08121f;font-weight:700;")
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

    with ui.element("div").style("display:grid;grid-template-columns:1fr 280px;gap:16px;margin-top:12px;"):
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

            # Tabs
            tabs = [("summary", "Summary"), ("skills", "Skills"),
                    ("resume", "Resume"), ("experience", "Experience"), ("activity", "Activity")]
            with ui.element("div").style(
                    f"display:flex;gap:4px;border-bottom:1px solid {_c(C,'border','#243049')};margin-bottom:12px;"):
                for tk, tl in tabs:
                    on = (st.get("tab", "summary") == tk)
                    def _set_tab(_e=None, k=tk):
                        st["tab"] = k; refresh()
                    with ui.element("div").style(
                            f"padding:8px 14px;font-size:12px;font-weight:600;cursor:pointer;"
                            f"color:{_c(C,'teal','#1AE3D9') if on else _c(C,'muted','#94A3B8')};"
                            f"border-bottom:2px solid {_c(C,'teal','#1AE3D9') if on else 'transparent'};"
                            ).on("click", _set_tab):
                        ui.label(tl)

            tab = st.get("tab", "summary")
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

        # RIGHT rail
        with ui.element("div"):
            with ui.element("div").style(
                    f"background:{_c(C,'card','#15203A')};border:1px solid {_c(C,'border','#243049')};"
                    f"border-radius:12px;padding:16px;"):
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
        ui.label("◆ Arena ATS").style(
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
                _view_stub(ff, st, "Dashboard", "Pipeline counts, recent adds, and your active candidates land here.")
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
        "view": "candidates", "tab": "summary", "mode": "keywords",
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

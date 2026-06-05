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


def ai_score_fit(intent: str, resume_text: str):
    """Ask AI to actually read the resume and rate 0-100 how well it fits the
    search. Returns (score:int|None, reason:str)."""
    key = _api_key()
    if not key or not (resume_text or "").strip():
        return None, ""
    try:
        import anthropic
        msg = anthropic.Anthropic(api_key=key).messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=120,
            system="You are a recruiter scoring how well a candidate's resume fits "
                   "a search. Be discerning and honest — most candidates are only a "
                   "partial fit. JSON only.",
            messages=[{"role": "user", "content":
                "Rate from 0-100 how well this candidate fits the search below. "
                "Weigh role/title match, relevant skills & experience, seniority, and "
                "location. Scoring guide: 85-100 = strong fit, 60-84 = decent, "
                "35-59 = weak, under 35 = not a fit. Do NOT give everyone a high score.\n"
                'Return ONLY JSON: {"score": <int 0-100>, "reason": "<max 8 words>"}\n\n'
                "SEARCH: " + (intent or "")[:600] + "\n\nRESUME:\n<<<\n"
                + (resume_text or "")[:4500] + "\n>>>"}])
        m = re.search(r"\{.*\}", msg.content[0].text, re.DOTALL)
        if m:
            d = json.loads(m.group())
            sc = int(d.get("score", 0))
            return max(0, min(100, sc)), str(d.get("reason", ""))[:60]
    except Exception:
        pass
    return None, ""


def score_results(intent: str, results: list, top_n: int = 25) -> list:
    """AI-score the top results against the search intent (parallel), attach
    fit_score/fit_reason, and sort scored-best-first."""
    from concurrent.futures import ThreadPoolExecutor
    head = results[:top_n]

    def _work(r):
        sc, why = ai_score_fit(intent, r.get("resume_text", ""))
        r["fit_score"] = sc
        r["fit_reason"] = why
        return r
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(_work, head))
    except Exception:
        pass
    results.sort(key=lambda r: (r.get("fit_score") is not None, r.get("fit_score") or 0),
                 reverse=True)
    return results


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


# ── Contact extraction (email / phone straight from résumé text) ──────────
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)")
# The recruiter's own address shows up in some résumés / fit-summaries — never
# treat it as the candidate's email.
_EMAIL_SKIP_DOMAINS = ("arenastaffing.net",)


def _extract_contacts(text: str) -> tuple:
    """Best-effort (email, phone) pulled straight from raw résumé text.

    Picks the candidate's own address (skips the recruiter's arenastaffing.net
    address that some docs carry in a header) and the first plausible phone.
    Never guesses — returns '' for anything it can't find."""
    text = text or ""
    email = ""
    for m in _EMAIL_RE.finditer(text):
        cand = m.group().strip().rstrip(".,;:")
        low = cand.lower()
        if any(low.endswith("@" + d) for d in _EMAIL_SKIP_DOMAINS):
            continue
        if low.endswith((".png", ".jpg", ".jpeg", ".gif")):
            continue
        email = cand
        break
    phone = ""
    pm = _PHONE_RE.search(text)
    if pm:
        phone = re.sub(r"\s+", " ", pm.group()).strip()
    return email, phone


def backfill_contacts() -> dict:
    """Fill blank email/phone columns from each candidate's résumé text.

    Deterministic, idempotent, and NON-destructive — never overwrites a value
    that's already set, only fills blanks. Safe to re-run any time (e.g. after
    a fresh ingest). Returns {'emails': n, 'phones': n, 'no_text': n}."""
    con = _con()
    out = {"emails": 0, "phones": 0, "no_text": 0}
    try:
        rows = con.execute(
            "SELECT id, email, phone, resume_text FROM talents").fetchall()
        for r in rows:
            cur_e = (r["email"] or "").strip()
            cur_p = (r["phone"] or "").strip()
            if cur_e and cur_p:
                continue
            txt = r["resume_text"] or ""
            if len(txt) < 40:
                out["no_text"] += 1
                continue
            ex_e, ex_p = _extract_contacts(txt)
            sets, vals = [], []
            if not cur_e and ex_e:
                sets.append("email=?"); vals.append(ex_e); out["emails"] += 1
            if not cur_p and ex_p:
                sets.append("phone=?"); vals.append(ex_p); out["phones"] += 1
            if sets:
                vals.append(r["id"])
                con.execute(
                    "UPDATE talents SET %s WHERE id=?" % ", ".join(sets), vals)
        con.commit()
    finally:
        con.close()
    return out


# ── Deduplication ─────────────────────────────────────────────────────────
def _norm_name_key(d: dict) -> str:
    fn = re.sub(r"[^a-z]", "", (d.get("first_name") or "").lower())
    ln = re.sub(r"[^a-z]", "", (d.get("last_name") or "").lower())
    return fn + "|" + ln


def _completeness(d: dict) -> float:
    """How much real info a record carries — used to keep the best of a set
    of duplicates. Email/phone dominate; a longer résumé and filled fields
    add; auto-generated 'Fit Summary' docs are penalised so a real résumé
    always wins."""
    score = 0.0
    if (d.get("email") or "").strip():
        score += 1000
    if (d.get("phone") or "").strip():
        score += 200
    score += min(len(d.get("resume_text") or ""), 20000) / 100.0
    for f in ("current_title", "current_employer", "skills", "summary", "city", "state"):
        if (d.get(f) or "").strip():
            score += 30
    sf = (d.get("source_file") or "").lower()
    if "fit_summary" in sf or "fit summary" in sf or "fit-summary" in sf:
        score -= 500
    return score


def _dup_clusters(rows: list) -> list:
    """Group records into same-person clusters via union-find.

    Same person if: same non-empty email, OR same normalized name + state.
    Records with a blank state merge into that name's group when the name maps
    to a single state; names spanning multiple states are split by state so
    two different people who share a name aren't merged."""
    from collections import defaultdict
    by_id = {r["id"]: r for r in rows}
    parent = {r["id"]: r["id"] for r in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_email = defaultdict(list)
    for r in rows:
        em = (r.get("email") or "").strip().lower()
        if em:
            by_email[em].append(r["id"])
    for ids in by_email.values():
        for i in ids[1:]:
            union(ids[0], i)

    by_name = defaultdict(list)
    for r in rows:
        by_name[_norm_name_key(r)].append(r)
    for nk, recs in by_name.items():
        if nk == "|":  # no name at all — never merge on name
            continue
        states = {_norm_state(x.get("state") or "") for x in recs}
        states.discard("")
        if len(states) <= 1:
            for x in recs[1:]:
                union(recs[0]["id"], x["id"])
        else:
            bystate = defaultdict(list)
            for x in recs:
                st = _norm_state(x.get("state") or "")
                if st:
                    bystate[st].append(x)
            for st, g in bystate.items():
                for x in g[1:]:
                    union(g[0]["id"], x["id"])

    clusters = defaultdict(list)
    for r in rows:
        clusters[find(r["id"])].append(by_id[r["id"]])
    return list(clusters.values())


def dedup_talents(dry_run: bool = True) -> dict:
    """Collapse duplicate candidate records to one per person — keeping the
    most complete résumé and backfilling any contact fields it's missing from
    the dropped copies.

    dry_run=True only reports the plan. dry_run=False deletes the extras and
    rebuilds the FTS index. Idempotent and safe to re-run after any bulk add.
    Returns a report dict (counts + example groups)."""
    con = _con()
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM talents")]
        clusters = _dup_clusters(rows)

        to_delete, merges, backfills = [], [], []
        for recs in clusters:
            if len(recs) < 2:
                continue
            recs.sort(key=lambda d: (_completeness(d),
                                     len(d.get("resume_text") or ""), -d["id"]),
                      reverse=True)
            keep, drop = recs[0], recs[1:]
            fill = {}
            for f in ("email", "phone", "current_title", "current_employer",
                      "city", "state", "skills", "summary"):
                if not (keep.get(f) or "").strip():
                    for dr in drop:
                        if (dr.get(f) or "").strip():
                            fill[f] = dr[f]
                            break
            name = ((keep.get("first_name") or "") + " " +
                    (keep.get("last_name") or "")).strip()
            merges.append((keep, [d["id"] for d in drop], name))
            if fill:
                backfills.append((keep["id"], fill))
            to_delete.extend(d["id"] for d in drop)

        report = {
            "total": len(rows),
            "dup_groups": len(merges),
            "to_delete": len(to_delete),
            "remaining": len(rows) - len(to_delete),
            "examples": [],
        }
        for keep, dropped, name in sorted(merges, key=lambda m: len(m[1]),
                                          reverse=True)[:12]:
            report["examples"].append({
                "name": name or "(no name)",
                "kept": "%s | %s | %s" % (
                    keep.get("current_title", "") or "—",
                    keep.get("email", "") or "no-email",
                    keep.get("source_file", "")),
                "dropped": len(dropped),
            })

        if not dry_run and to_delete:
            for keep_id, fill in backfills:
                sets = ", ".join("%s=?" % k for k in fill)
                con.execute("UPDATE talents SET %s WHERE id=?" % sets,
                            (*fill.values(), keep_id))
            con.executemany("DELETE FROM talents WHERE id=?",
                            [(i,) for i in to_delete])
            con.execute("INSERT INTO talents_fts(talents_fts) VALUES('rebuild')")
            con.commit()
            report["deleted"] = len(to_delete)
        return report
    finally:
        con.close()


def companies_from_campaigns() -> list:
    """Live list of companies the user has reached out to via DripDrop
    campaigns — aggregated from campaign contacts + each campaign's target
    company. Reads campaigns fresh, so new campaigns show up automatically."""
    ff = _ff()
    try:
        ff._cache_campaigns.invalidate()
    except Exception:
        pass
    try:
        camps = ff.load_campaigns()
    except Exception:
        return []
    agg = {}

    def _add(co, camp_name, contact=None, website=""):
        co = (str(co) if co is not None else "").strip()
        if not co or co.lower() in ("n/a", "none", "-"):
            return
        e = agg.setdefault(co.lower(), {"name": co, "contacts": 0,
                                        "campaigns": set(), "location": "", "website": ""})
        if camp_name:
            e["campaigns"].add(camp_name)
        if website and not e["website"]:
            e["website"] = website.strip()
        if contact is not None:
            e["contacts"] += 1
            if not e["location"]:
                e["location"] = ", ".join(
                    x for x in [(contact.get("city") or ""), (contact.get("state") or "")] if x)

    for c in (camps or []):
        cname = c.get("name", "") or ""
        _vars = c.get("variables") or {}
        _web = (_vars.get("Website") or c.get("aicb_website") or c.get("website") or "")
        for ct in (c.get("contacts") or []):
            _add(ct.get("company"), cname, ct,
                 website=(ct.get("website") or ct.get("Website") or ""))
        _add(_vars.get("Company"), cname, website=_web)
        _add(c.get("market_company"), cname, website=_web)

    out = [{"name": v["name"], "contacts": v["contacts"],
            "campaigns": sorted(v["campaigns"]), "location": v["location"],
            "website": v["website"]}
           for v in agg.values()]
    out.sort(key=lambda x: (x["contacts"], len(x["campaigns"])), reverse=True)
    return out


def send_to_dripdrop(candidate_ids, list_name) -> tuple:
    """Write the selected candidates as a DripDrop contact list (CSV in the
    user's Contacts dir) so they're pickable in the campaign builder.
    Returns (count_written, safe_list_name)."""
    ff = _ff()
    import csv, io, re as _re
    rows = []
    for i in candidate_ids:
        d = get_one(i)
        if not d:
            continue
        if not (d.get("email") or "").strip():
            # Last-ditch: pull an email straight from the résumé text.
            ex_e, ex_p = _extract_contacts(d.get("resume_text") or "")
            if ex_e:
                d["email"] = ex_e
                if not (d.get("phone") or "").strip() and ex_p:
                    d["phone"] = ex_p
        if (d.get("email") or "").strip():
            rows.append(d)
    if not rows:
        return 0, ""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=ff.CONTACT_FIELDS, restval="", extrasaction="ignore")
    w.writeheader()
    for d in rows:
        w.writerow({
            "Email": d.get("email", ""), "FirstName": d.get("first_name", ""),
            "LastName": d.get("last_name", ""), "Company": d.get("current_employer", ""),
            "JobTitle": d.get("current_title", ""), "MobilePhone": d.get("phone", ""),
            "City": d.get("city", ""), "State": d.get("state", ""),
        })
    safe = (_re.sub(r"[^\w\-]", "_", list_name)[:60].strip("_")) or "ATS_Selection"
    try:
        dest = ff._user_contacts_dir() / f"{safe}.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(buf.getvalue(), encoding="utf-8")
    except Exception:
        return 0, ""
    return len(rows), safe


MPC_MAX = 3  # DripDrop markets up to 3 candidates per MPC campaign


def _talent_to_pool(d: dict) -> dict:
    """Convert an ATS talent row into the pool-candidate dict shape the
    DripDrop MPC (candidate placement) builder expects."""
    name = ((d.get("first_name") or "") + " " + (d.get("last_name") or "")).strip()
    loc = ", ".join(x for x in [(d.get("city") or ""), (d.get("state") or "")] if x)
    return {
        "id": "ats_" + str(d.get("id", "")),
        "name": name or "Candidate",
        "target_role": d.get("current_title", "") or "",
        "location": loc,
        "salary": "",
        "summary": d.get("summary", "") or "",
        "resume_text": d.get("resume_text", "") or "",
        "redacted_resume": "",
        "email": d.get("email", "") or "",
        "phone": d.get("phone", "") or "",
        "company": d.get("current_employer", "") or "",
        "skills": d.get("skills", "") or "",
        "status": "active",
        "results": [],
    }


def start_mpc_campaign(candidate_ids) -> tuple:
    """Seed a DripDrop MPC campaign with the selected ATS candidates as the
    slate (max 3) and route the main app to the MPC builder. The candidates
    are stashed in app.storage.user so index() can hydrate AppState on landing.
    Returns (used, total_selected)."""
    ids = list(candidate_ids)
    total = len(ids)
    pool = []
    for i in ids[:MPC_MAX]:
        d = get_one(i)
        if d:
            pool.append(_talent_to_pool(d))
    if not pool:
        return 0, total
    app.storage.user["_pending_mpc_candidates"] = pool
    app.storage.user["_pending_page"] = "candidate_campaign"
    return len(pool), total


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


# Reverse: abbrev → full state name for display headers ("CA" → "California").
_STATE_NAMES = {abbr: full.title() for full, abbr in _STATES.items()}


def _state_name(abbr: str) -> str:
    return _STATE_NAMES.get(abbr, abbr)


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


def pool_by_location(top_states: int = 6, top_inds: int = 5) -> list:
    """Cross-tab the pool by state, then industry within each state — the
    location-first dashboard view. Returns a list of
    {state, name, total, industries:[(industry, count), ...]} sorted by size."""
    from collections import Counter, defaultdict
    con = _con()
    try:
        rows = con.execute("SELECT current_title, skills, state FROM talents").fetchall()
    except Exception:
        return []
    finally:
        con.close()
    by_state = defaultdict(Counter)
    state_total = Counter()
    for r in rows:
        stt = _norm_state(r["state"] or "")
        if not stt:
            continue
        ind = _industry_of(r["current_title"] or "", r["skills"] or "")
        by_state[stt][ind] += 1
        state_total[stt] += 1
    out = []
    for stt, cnt in state_total.most_common(top_states):
        named = [(k, v) for k, v in by_state[stt].most_common() if k != "Other"]
        inds = named[:top_inds] if named else by_state[stt].most_common(top_inds)
        out.append({"state": stt, "name": _state_name(stt),
                    "total": cnt, "industries": inds})
    return out


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


def _fmt_date(iso):
    """Absolute date like 'Mar 14, 2026' (Windows-safe — no %-d)."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat((iso or "")[:19])
    except Exception:
        return "—"
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"


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

    # ── Talent Pool by Location: state header + industry breakdown ──
    with ui.element("div").style(_box + "margin-bottom:14px;"):
        ui.label("Talent Pool by Location").style(_box_title + "display:block;")
        ui.label("Where your candidates are — and what they do. Click a state or "
                 "an industry to pull those candidates up.").style(
            f"font-size:12px;color:{_c(C,'muted','#94A3B8')};margin:4px 0 16px;display:block;")
        locs = pool_by_location()
        if not locs:
            ui.label("No location data yet.").style(
                f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")
        with ui.element("div").style(
                "display:grid;grid-template-columns:repeat(3,1fr);gap:14px;"):
            for L in locs:
                with ui.element("div").style(
                        f"background:{_c(C,'surface','#F8FAFC')};"
                        f"border:1px solid {_c(C,'border','#E2E8F0')};"
                        f"border-radius:12px;padding:15px 17px;"):
                    # State header — clickable
                    def _go_state(_e=None, q=L["name"]):
                        _drill(st, refresh, q)
                    with ui.element("div").style(
                            "display:flex;align-items:baseline;justify-content:space-between;"
                            "gap:8px;cursor:pointer;margin-bottom:13px;").on("click", _go_state):
                        ui.label(L["name"]).style(
                            f"font-size:16px;font-weight:800;color:{_c(C,'text_l','#0F172A')};"
                            f"font-family:'Nunito',sans-serif;"
                            f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
                        ui.label(f"{L['total']:,}").style(
                            f"font-size:16px;font-weight:800;color:{_c(C,'teal','#1AE3D9')};"
                            f"font-family:'Nunito',sans-serif;flex-shrink:0;")
                    # Industry breakdown within the state
                    _maxc = max((c for _, c in L["industries"]), default=1) or 1
                    for ind, c in L["industries"]:
                        _pct = max(6, int(round(c / _maxc * 100)))

                        def _go_ind(_e=None, q=f'{L["name"]} {ind}'):
                            _drill(st, refresh, q)
                        with ui.element("div").style(
                                "display:flex;align-items:center;gap:10px;"
                                "margin-bottom:8px;cursor:pointer;").on("click", _go_ind):
                            ui.label(ind).style(
                                f"width:104px;flex-shrink:0;font-size:12px;"
                                f"color:{_c(C,'text','#334155')};overflow:hidden;"
                                f"text-overflow:ellipsis;white-space:nowrap;")
                            with ui.element("div").style(
                                    f"flex:1;background:{_c(C,'card','#FFFFFF')};"
                                    f"border:1px solid {_c(C,'border','#E2E8F0')};"
                                    f"border-radius:5px;height:16px;overflow:hidden;"):
                                ui.element("div").style(
                                    f"width:{_pct}%;height:100%;"
                                    f"background:{_c(C,'teal','#1AE3D9')};border-radius:5px;")
                            ui.label(f"{c:,}").style(
                                f"width:38px;text-align:right;font-size:12px;font-weight:700;"
                                f"color:{_c(C,'text_l','#0F172A')};flex-shrink:0;")

    # ── Recently Added box ──
    with ui.element("div").style(_box):
        ui.label("Recently Added").style(_box_title + "display:block;margin-bottom:10px;")
        recents = recent(10)
        if not recents:
            ui.label("Nothing yet.").style(f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")
        for r in recents:
            def _open_r(_e=None, i=r.get("id")):
                st["sel"] = i; st["tab"] = "resume"; st["view"] = "profile"
                st["sel_fit"] = None; st["sel_reason"] = None; refresh()
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
    sel = st.setdefault("selected", set())
    _grid = "54px 1.3fr 1.4fr 0.85fr 0.85fr 0.7fr"
    all_ids = [r.get("id") for r in rows]
    all_sel = bool(all_ids) and all(i in sel for i in all_ids)

    def _toggle_all(_e=None):
        for i in all_ids:
            (sel.discard if all_sel else sel.add)(i)
        refresh()
    # header
    with ui.element("div").style(
            f"display:grid;grid-template-columns:{_grid};gap:12px;align-items:center;"
            f"padding:8px 14px;border-bottom:1px solid {_c(C,'border','#243049')};"
            f"font-size:10px;font-weight:700;letter-spacing:.05em;"
            f"text-transform:uppercase;color:{_c(C,'muted','#94A3B8')};"):
        with ui.element("div").style(
                "display:flex;align-items:center;height:100%;cursor:pointer;"
                ).on("click", _toggle_all):
            with ui.element("div").style(
                    f"width:20px;height:20px;border-radius:5px;border:1.5px solid "
                    f"{_c(C,'teal','#1AE3D9') if all_sel else _c(C,'muted','#94A3B8')};"
                    f"background:{_c(C,'teal','#1AE3D9') if all_sel else 'transparent'};"
                    f"display:flex;align-items:center;justify-content:center;"):
                if all_sel:
                    ui.label("✓").style("font-size:12px;color:#fff;line-height:1;")
        for h in ("Name", "Title / Employer", "Location", "Owner", "Date Added"):
            ui.label(h)
    for r in rows:
        tid = r.get("id")
        _checked = tid in sel

        def _toggle(_e=None, i=tid):
            (sel.discard if i in sel else sel.add)(i)
            refresh()

        def _open(_e=None, i=tid, _fit=r.get("fit_score"), _rsn=r.get("fit_reason")):
            st["sel"] = i
            st["tab"] = "resume"
            st["view"] = "profile"
            st["sel_fit"] = _fit
            st["sel_reason"] = _rsn
            refresh()
        with ui.element("div").style(
                f"display:grid;grid-template-columns:{_grid};gap:12px;"
                f"padding:13px 14px;border-bottom:1px solid {_c(C,'border','#1c2740')};"
                f"cursor:pointer;align-items:center;").on("click", _open):
            # Big, full-cell hit area so a near-miss checks instead of opening.
            with ui.element("div").style(
                    f"display:flex;align-items:center;height:100%;margin:-13px 0;padding:13px 0;"
                    f"cursor:pointer;").on("click.stop", _toggle):
                with ui.element("div").style(
                        f"width:20px;height:20px;border-radius:5px;border:1.5px solid "
                        f"{_c(C,'teal','#1AE3D9') if _checked else _c(C,'muted','#94A3B8')};"
                        f"background:{_c(C,'teal','#1AE3D9') if _checked else 'transparent'};"
                        f"display:flex;align-items:center;justify-content:center;"):
                    if _checked:
                        ui.label("✓").style("font-size:12px;color:#fff;line-height:1;")
            with ui.element("div"):
                ui.label(_fullname(r)).style(
                    f"font-size:13px;font-weight:700;color:{_c(C,'text_l','#E6EDF7')};"
                    f"font-family:'Nunito',sans-serif;")
                _reason = r.get("fit_reason")
                if _reason:
                    ui.label(_reason).style(
                        f"font-size:10px;color:{_c(C,'good','#34D399')};margin-top:2px;"
                        f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
                elif terms:
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
                fit = r.get("fit_score")
                if fit is not None:
                    ui.label(f"{fit}% fit").style(
                        f"font-size:14px;font-weight:800;color:{_fit_color(C, fit)};line-height:1.1;")
                ui.label(_fmt_date(r.get("created_at", ""))).style(
                    f"font-size:11px;font-weight:600;color:{_c(C,'text','#CBD5E1')};")


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

            async def _do_kw():
                st["query"] = (_inp.value or "").strip()
                st["crit"] = {}
                st["terms"] = _terms(st["query"])
                if not st["query"]:
                    st["results"] = []; refresh(); return
                st["searching"] = True; refresh()
                from nicegui import run as _run
                q = st["query"]
                st["results"] = await _run.io_bound(
                    lambda: score_results(q, keyword_search(q)))
                st["searching"] = False
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
                results = await _run.io_bound(lambda: score_results(jd, results))
                st["crit"], st["results"], st["terms"] = crit, results, terms
                st["searching"] = False
                refresh()
            with ui.element("div").style("display:flex;justify-content:flex-end;margin-top:10px;"):
                with ui.element("button").style(
                        f"background:{_c(C,'teal','#1AE3D9')};color:#08121f;border:0;"
                        f"border-radius:8px;padding:8px 24px;font-size:13px;font-weight:700;"
                        f"cursor:pointer;font-family:inherit;").on("click", _do_jd):
                    ui.label("✦ Find Matches")
            if st.get("crit"):
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

    # Selection action bar — appears when candidates are checked.
    _sel = st.setdefault("selected", set())
    if _sel:
        with ui.element("div").style(
                f"display:flex;align-items:center;justify-content:space-between;gap:12px;"
                f"background:{_c(C,'teal','#1AE3D9')}18;border:1px solid {_c(C,'teal','#1AE3D9')}60;"
                f"border-radius:10px;padding:10px 16px;margin-bottom:12px;"):
            ui.label(f"{len(_sel)} candidate(s) selected").style(
                f"font-size:13px;font-weight:700;color:{_c(C,'teal','#1AE3D9')};")
            with ui.element("div").style("display:flex;gap:8px;align-items:center;"):
                def _clear_sel():
                    _sel.clear(); refresh()
                with ui.element("button").style(
                        f"background:transparent;border:1px solid {_c(C,'border','#CBD5E1')};"
                        f"color:{_c(C,'text','#334155')};border-radius:8px;padding:6px 14px;"
                        f"font-size:12px;cursor:pointer;font-family:inherit;").on("click", _clear_sel):
                    ui.label("Clear")

                def _start_mpc():
                    used, total = start_mpc_campaign(list(_sel))
                    if not used:
                        ui.notify("Couldn't load the selected candidates.", type="warning")
                        return
                    _sel.clear()
                    if total > used:
                        ui.notify(f"An MPC campaign markets up to {MPC_MAX} candidates at "
                                  f"once. Using {used} — you can swap candidates on the next "
                                  f"screen.", type="info", timeout=7000)
                    ui.navigate.to("/")
                with ui.element("button").style(
                        f"background:{_c(C,'teal','#1AE3D9')};color:#08121f;border:0;"
                        f"border-radius:8px;padding:7px 18px;font-size:13px;font-weight:700;"
                        f"cursor:pointer;font-family:inherit;").on("click", _start_mpc):
                    ui.label("✦ Start an MPC Campaign")

    # Results / recent
    if st.get("searching"):
        with ui.element("div").style("display:flex;align-items:center;gap:10px;padding:26px 2px;"):
            ui.spinner("dots", size="22px", color=_c(C, 'teal', '#1AE3D9'))
            ui.label("Reading résumés and scoring fit…").style(
                f"font-size:13px;color:{_c(C,'teal','#1AE3D9')};")
    elif st.get("results"):
        _has_fit = any(r.get("fit_score") is not None for r in st["results"])
        ui.label(f"{len(st['results'])} candidate(s)" + (" · ranked by fit" if _has_fit else "")).style(
            f"font-size:12px;color:{_c(C,'muted','#94A3B8')};margin-bottom:6px;")
        _candidate_rows(C, st, refresh, st["results"], st.get("terms"))
    else:
        ui.label("Recently added").style(
            f"font-size:11px;font-weight:700;color:{_c(C,'muted','#94A3B8')};"
            f"text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;")
        _candidate_rows(C, st, refresh, recent())


def _view_companies(ff, st, refresh):
    C = ff.C
    ui.label("Companies").style(
        f"font-size:22px;font-weight:800;color:{_c(C,'text_l','#0F172A')};"
        f"font-family:'Nunito',sans-serif;")
    ui.label("Companies you've reached out to through DripDrop campaigns — "
             "updates automatically as you run new campaigns.").style(
        f"font-size:12px;color:{_c(C,'muted','#94A3B8')};margin-bottom:16px;")
    cos = companies_from_campaigns()
    with ui.element("div").style(
            f"background:{_c(C,'card','#FFFFFF')};border:1px solid {_c(C,'border','#E2E8F0')};"
            f"border-radius:12px;padding:18px 20px;"):
        ui.label(f"{len(cos):,} companies").style(
            f"font-size:12px;color:{_c(C,'muted','#94A3B8')};margin-bottom:10px;display:block;")
        if not cos:
            ui.label("No companies yet — run a DripDrop campaign and the companies "
                     "you contact will appear here automatically.").style(
                f"font-size:13px;color:{_c(C,'muted','#94A3B8')};padding:8px 0;")
            return
        _cols = "1.9fr 1.2fr 1.4fr 0.7fr"
        with ui.element("div").style(
                f"display:grid;grid-template-columns:{_cols};gap:12px;"
                f"padding:8px 6px;border-bottom:1px solid {_c(C,'border','#E2E8F0')};"
                f"font-size:10px;font-weight:700;letter-spacing:.05em;"
                f"text-transform:uppercase;color:{_c(C,'muted','#94A3B8')};"):
            for h in ("Company", "Location", "Website", "Campaigns"):
                ui.label(h)
        for co in cos:
            def _open_co(_e=None, c=co):
                st["company"] = c
                st["view"] = "company_detail"
                refresh()
            with ui.element("div").style(
                    f"display:grid;grid-template-columns:{_cols};gap:12px;align-items:center;"
                    f"padding:10px 6px;border-bottom:1px solid {_c(C,'border','#EEF2F8')};cursor:pointer;"
                    ).on("click", _open_co):
                ui.label(co["name"]).style(
                    f"font-size:13px;font-weight:700;color:{_c(C,'text_l','#0F172A')};"
                    f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
                ui.label(co["location"] or "—").style(
                    f"font-size:12px;color:{_c(C,'text','#334155')};")
                ui.label(co["website"] or "—").style(
                    f"font-size:12px;color:{_c(C,'muted','#94A3B8')};"
                    f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
                ui.label(f"{len(co['campaigns']):,}").style(
                    f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")


def _view_company_detail(ff, st, refresh):
    """Read-only company profile — name, location, website, and outreach
    footprint from DripDrop campaigns. No people listed under it (by design,
    for now). Reached from the Companies list."""
    C = ff.C
    co = st.get("company") or {}
    if not co:
        st["view"] = "companies"; refresh(); return

    def _back():
        st["view"] = "companies"; st["company"] = None; refresh()
    with ui.element("span").style(
            f"font-size:12px;color:{_c(C,'teal','#1AE3D9')};cursor:pointer;").on("click", _back):
        ui.label("← Companies")

    camps = co.get("campaigns") or []
    web = (co.get("website") or "").strip()
    web_url = web if (web.startswith("http://") or web.startswith("https://")) else ("https://" + web if web else "")

    # Header card
    with ui.element("div").style(
            f"background:{_c(C,'card','#FFFFFF')};border:1px solid {_c(C,'border','#E2E8F0')};"
            f"border-radius:12px;padding:20px 22px;margin-top:12px;margin-bottom:14px;"):
        ui.label(co.get("name", "")).style(
            f"font-size:22px;font-weight:800;color:{_c(C,'text_l','#0F172A')};"
            f"font-family:'Nunito',sans-serif;")
        with ui.element("div").style("display:flex;gap:22px;flex-wrap:wrap;margin-top:8px;align-items:center;"):
            ui.label(f"📍 {co.get('location') or '—'}").style(
                f"font-size:12px;color:{_c(C,'text','#334155')};")
            if web:
                with ui.element("a").props(f'href="{web_url}" target="_blank"').style(
                        f"font-size:12px;color:{_c(C,'teal','#1AE3D9')};text-decoration:none;"):
                    ui.label(f"🌐 {web}")
            else:
                ui.label("🌐 No website on file").style(
                    f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")

    # Stat tiles
    with ui.element("div").style("display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;"):
        for val, lbl in ((f"{len(camps):,}", "Campaigns reached"),
                         (f"{co.get('contacts', 0):,}", "People contacted")):
            with ui.element("div").style(
                    f"background:{_c(C,'card','#FFFFFF')};border:1px solid {_c(C,'border','#E2E8F0')};"
                    f"border-radius:12px;padding:16px 18px;"):
                ui.label(val).style(
                    f"font-size:26px;font-weight:800;color:{_c(C,'text_l','#0F172A')};"
                    f"font-family:'Nunito',sans-serif;line-height:1;")
                ui.label(lbl).style(
                    f"font-size:11px;color:{_c(C,'muted','#94A3B8')};margin-top:4px;display:block;")

    # Campaigns this company appeared in
    with ui.element("div").style(
            f"background:{_c(C,'card','#FFFFFF')};border:1px solid {_c(C,'border','#E2E8F0')};"
            f"border-radius:12px;padding:16px 18px;"):
        ui.label("REACHED VIA CAMPAIGNS").style(
            f"font-size:10px;font-weight:700;letter-spacing:.06em;"
            f"color:{_c(C,'muted','#94A3B8')};margin-bottom:10px;display:block;")
        if camps:
            with ui.element("div").style("display:flex;flex-wrap:wrap;gap:8px;"):
                for nm in camps:
                    ui.label(nm).style(
                        f"background:{_c(C,'teal','#1AE3D9')}14;color:{_c(C,'text_l','#0F172A')};"
                        f"border:1px solid {_c(C,'teal','#1AE3D9')}40;border-radius:99px;"
                        f"padding:4px 12px;font-size:12px;")
        else:
            ui.label("—").style(f"font-size:12px;color:{_c(C,'muted','#94A3B8')};")

    ui.label("People and open jobs can be linked to this company soon — for now this is "
             "the company record.").style(
        f"font-size:11px;color:{_c(C,'muted','#94A3B8')};margin-top:14px;display:block;")


def _view_profile(ff, st, refresh):
    C = ff.C
    d = get_one(st.get("sel"))
    if not d:
        ui.label("Candidate not found.").style(f"color:{_c(C,'warn','#F59E0B')};")
        return
    # Surface contact details pulled from the résumé even if the stored columns
    # were blank (display-only; backfill_contacts persists them for real).
    if not (d.get("email") or "").strip() or not (d.get("phone") or "").strip():
        ex_e, ex_p = _extract_contacts(d.get("resume_text") or "")
        if not (d.get("email") or "").strip() and ex_e:
            d["email"] = ex_e
        if not (d.get("phone") or "").strip() and ex_p:
            d["phone"] = ex_p

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

        # RIGHT rail: contact / fit / status / owner / send, then Recruiter Notes
        with ui.element("div").style("display:flex;flex-direction:column;gap:14px;"):
            # Contact details — pulled from the résumé.
            with ui.element("div").style(
                    f"background:{_c(C,'card','#15203A')};border:1px solid {_c(C,'border','#243049')};"
                    f"border-radius:12px;padding:16px;"):
                ui.label("CONTACT DETAILS").style(
                    f"font-size:10px;font-weight:700;letter-spacing:.06em;"
                    f"color:{_c(C,'muted','#94A3B8')};margin-bottom:10px;display:block;")
                _contact = [
                    ("✉", "Email", (d.get("email") or "").strip()),
                    ("☎", "Phone", (d.get("phone") or "").strip()),
                    ("📍", "Location", _loc(d)),
                ]
                for ic, lbl, val in _contact:
                    with ui.element("div").style(
                            "display:flex;align-items:center;gap:9px;margin-bottom:9px;"):
                        ui.label(ic).style("font-size:13px;width:16px;text-align:center;")
                        if val:
                            ui.label(val).style(
                                f"font-size:12px;color:{_c(C,'text_l','#E6EDF7')};"
                                f"word-break:break-all;")
                        else:
                            ui.label(f"No {lbl.lower()} in résumé").style(
                                f"font-size:12px;color:{_c(C,'muted','#94A3B8')};font-style:italic;")

            with ui.element("div").style(
                    f"background:{_c(C,'card','#15203A')};border:1px solid {_c(C,'border','#243049')};"
                    f"border-radius:12px;padding:16px;"):
                # AI fit for the search this candidate was opened from (if any)
                _fit = st.get("sel_fit")
                if _fit is not None:
                    ui.label("FIT FOR THIS SEARCH").style(
                        f"font-size:10px;font-weight:700;letter-spacing:.06em;color:{_c(C,'muted','#94A3B8')};")
                    ui.label(f"{_fit}%").style(
                        f"font-size:30px;font-weight:800;color:{_fit_color(C, _fit)};"
                        f"font-family:'Nunito',sans-serif;line-height:1;margin:2px 0 4px;")
                    if st.get("sel_reason"):
                        ui.label(st["sel_reason"]).style(
                            f"font-size:11px;color:{_c(C,'text','#CBD5E1')};margin-bottom:12px;display:block;")
                    ui.element("div").style(f"height:1px;background:{_c(C,'border','#243049')};margin:6px 0 12px;")
                ui.label("STATUS").style(
                    f"font-size:10px;font-weight:700;letter-spacing:.06em;color:{_c(C,'muted','#94A3B8')};")
                ui.label(d.get("status", "Candidate") or "Candidate").style(
                    f"font-size:14px;font-weight:700;color:{_c(C,'teal','#1AE3D9')};margin:2px 0 12px;")
                ui.label("OWNER").style(
                    f"font-size:10px;font-weight:700;letter-spacing:.06em;color:{_c(C,'muted','#94A3B8')};")
                ui.label(d.get("added_by", "Mike Vaughn") or "Mike Vaughn").style(
                    f"font-size:13px;color:{_c(C,'text_l','#E6EDF7')};margin:2px 0 12px;")
                ui.element("div").style(f"height:1px;background:{_c(C,'border','#243049')};margin:6px 0 14px;")
                def _mpc_one(_e=None, _i=d.get("id")):
                    used, _ = start_mpc_campaign([_i])
                    if not used:
                        ui.notify("Couldn't load this candidate.", type="warning"); return
                    ui.navigate.to("/")
                with ui.element("button").style(
                        f"width:100%;background:{_c(C,'teal','#1AE3D9')};color:#08121f;border:0;"
                        f"border-radius:8px;padding:10px;font-size:13px;font-weight:700;cursor:pointer;"
                        f"font-family:inherit;").on("click", _mpc_one):
                    ui.label("✦ Start an MPC Campaign")

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
                on = (st["view"] == key) or (key == "candidates" and st["view"] == "profile") \
                    or (key == "companies" and st["view"] == "company_detail")

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
                _view_companies(ff, st, refresh)
            elif v == "company_detail":
                _view_company_detail(ff, st, refresh)
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

"""Target List (ThriveModal / inboxslide only): US companies that already hire
or employ Filipino staff, plus every company from the user's Buying Signals
issues, on one page.

Companion module, lazy-imported by the host like tm_signals, so a failure
here takes out this page and nothing else.

Data:
- The researched companies ship in tm_targets_data.SEED (same for every
  ThriveModal user; it is the 2026-10-15 Who's Hiring research).
- Buying Signals companies come from the user's own tm_signals.json issues.
  A researched company that also has a signal gets the signal on its card;
  a signal company that is not in the seed becomes a card of its own.
- Per-user card status (New / Working / Contacted / Not a fit) lives in
  tm_targets.json in the user's folder. "Not a fit" hides the card.

Order: buying signals first, then newest posting first, then cards with no
posting day (staff counts, resumes) by tier. Every card says how long ago
it was posted, or what the evidence is when there is no posting day.
"""
import json
import re
import sys
from datetime import date

from nicegui import ui

import tm_targets_data as data


def _ff():
    """The already-loaded flowdrip_app module (see tm_signals._ff)."""
    for name in ("flowdrip_app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_BASE_DATA_DIR") and hasattr(m, "C"):
            return m
    import flowdrip_app as m  # standalone/test fallback
    return m


STATE_FILE = "tm_targets.json"
STATUSES = (("new", "New"), ("working", "Working"),
            ("contacted", "Contacted"), ("no_fit", "Not a fit"))
STATUS_LABEL = dict(STATUSES)
MARKET_LABEL = dict(data.MARKETS)
TIER_LABEL = dict(data.TIERS)
TIER_RANK = {"strong": 0, "medium": 1, "weak": 2}
KIND_LABEL = {"hiring": "Job post", "staff": "Filipino staff", "resume": "On a Filipino resume",
              "list": "Filipino hire on the books", "signal": "Buying signal"}
FRESH_DAYS = 30

# Buying Signals industry key -> Target List market.
SIGNAL_MARKET = {
    "logistics": "freight", "freight_forwarding": "freight",
    "accounting": "accounting", "construction_aec": "construction",
    "manufacturing": "manufacturing", "distributors": "manufacturing",
}

_SUFFIX = re.compile(r"\b(inc|llc|l\.?p|corp|corporation|co|company|ltd|group|the)\b\.?")


# ── Pure helpers (tested) ────────────────────────────────────────────────

def norm(name):
    """Comparable company name: lowercase, no brackets, suffixes or
    punctuation. 'Ally Logistics, LLC' and 'Ally Logistics' match."""
    s = str(name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.split("/")[0]
    s = _SUFFIX.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def key_of(name):
    return norm(name).replace(" ", "-") or "x"


def parse_iso(s):
    try:
        return date.fromisoformat(str(s or "")[:10])
    except Exception:
        return None


def days_since(posted, today):
    d = parse_iso(posted)
    if d is None:
        return None
    return max(0, (today - d).days)


def age_label(row, today):
    """'Posted today' / 'Posted 3 days ago' / 'Posted 4 months ago', or the
    looser wording when the source gave no day."""
    n = days_since(row.get("posted"), today)
    verb = "Signal" if row.get("kind") == "signal" else "Posted"
    if n is None:
        return row.get("when") or "Date not given"
    if n == 0:
        return f"{verb} today"
    if n == 1:
        return f"{verb} 1 day ago"
    if n < 60:
        return f"{verb} {n} days ago"
    months = n // 30
    return f"{verb} {months} months ago"


def signal_rows(issues):
    """One row per company across the stored Buying Signals issues, newest
    signal kept. Issues are stored newest first."""
    out = {}
    for issue in issues or []:
        for sec in issue.get("sections") or []:
            market = SIGNAL_MARKET.get(sec.get("industry"), "other")
            for c in sec.get("companies") or []:
                name = (c.get("company") or "").strip()
                if not name:
                    continue
                k = norm(name)
                prev = out.get(k)
                if prev and (prev["date"] or "") >= (c.get("date") or ""):
                    continue
                out[k] = {"company": name, "market": market,
                          "signal": c.get("signal") or "",
                          "headline": c.get("headline") or "",
                          "why_now": c.get("why_now") or "",
                          "offshore_history": c.get("offshore_history") or "",
                          "location": c.get("location") or "",
                          "date": c.get("date") or issue.get("date") or "",
                          "source_url": c.get("source_url") or ""}
    return list(out.values())


def build_rows(seed, signals):
    """Seed rows with any matching signal attached, plus a row for each
    signal company the research did not have."""
    by_norm = {norm(sg["company"]): sg for sg in signals}
    rows = []
    used = set()
    for r in seed:
        row = dict(r)
        row["key"] = key_of(r["name"])
        sg = by_norm.get(norm(r["name"]))
        row["signal"] = sg
        if sg:
            used.add(norm(sg["company"]))
        rows.append(row)
    for k, sg in by_norm.items():
        if k in used:
            continue
        rows.append({
            "name": sg["company"], "market": sg["market"],
            "tier": "strong" if sg["offshore_history"] else "medium",
            "kind": "signal", "hq": sg["location"], "size": "",
            "ph": sg["offshore_history"] or "", "roles": "",
            "posted": sg["date"], "when": "", "pay": "",
            "sources": ([{"label": "Source", "url": sg["source_url"]}]
                        if sg["source_url"] else []),
            "note": "", "key": key_of(sg["company"]), "signal": sg})
    return rows


def sort_rows(rows):
    """Signals first, then newest posting, then undated by tier and name."""
    def k(r):
        d = parse_iso(r.get("signal", {}).get("date") if r.get("signal") else None) \
            or parse_iso(r.get("posted"))
        return (0 if r.get("signal") else 1,
                0 if d else 1,
                -(d.toordinal() if d else 0),
                TIER_RANK.get(r.get("tier"), 3),
                r.get("name", "").lower())
    return sorted(rows, key=k)


def filter_rows(rows, status, market="", strong_only=False, q="", show_hidden=False):
    q = (q or "").strip().lower()
    out = []
    for r in rows:
        st = status.get(r["key"], "new")
        if show_hidden != (st == "no_fit"):
            continue
        if market and r.get("market") != market:
            continue
        if strong_only and r.get("tier") != "strong":
            continue
        if q:
            hay = " ".join(str(r.get(f) or "") for f in ("name", "hq", "roles", "ph", "note")).lower()
            if q not in hay:
                continue
        out.append(r)
    return out


def size_label(size):
    """'~213' -> '~213 staff'; words ('small', '28 trucks') stay as they are."""
    size = str(size or "").strip()
    if re.fullmatch(r"~?[\d,]+(-[\d,]+)?", size):
        return size + " staff"
    return size


def next_status(cur):
    keys = [k for k, _l in STATUSES]
    i = keys.index(cur) if cur in keys else 0
    return keys[(i + 1) % len(keys)]


def counts(rows, status, today):
    live = [r for r in rows if status.get(r["key"], "new") != "no_fit"]
    fresh = 0
    for r in live:
        n = days_since(r.get("posted"), today)
        if n is not None and n <= FRESH_DAYS and r.get("kind") == "hiring":
            fresh += 1
    return {"total": len(live),
            "strong": sum(1 for r in live if r.get("tier") == "strong"),
            "fresh": fresh,
            "signals": sum(1 for r in live if r.get("signal")),
            "hidden": len(rows) - len(live)}


# ── Per-user state ───────────────────────────────────────────────────────

def state_path(user_root=None):
    root = user_root if user_root is not None else _ff()._resolve_user_root()
    return root / STATE_FILE


def load_state(user_root=None):
    try:
        p = state_path(user_root)
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("status"), dict):
                return {"status": {str(k): str(v) for k, v in d["status"].items()
                                   if v in STATUS_LABEL}}
    except Exception:
        pass
    return {"status": {}}


def save_state(state, user_root=None):
    p = state_path(user_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(p)


def all_rows():
    try:
        import tm_signals
        issues = tm_signals.load_settings().get("issues") or []
    except Exception as e:
        print(f"[Targets] signals unavailable: {e}", flush=True)
        issues = []
    return sort_rows(build_rows(data.SEED, signal_rows(issues)))


# ── Page ─────────────────────────────────────────────────────────────────

def _e(s):
    import html
    return html.escape(str(s or ""), quote=True)


def _css():
    ui.html(
        "<style>"
        ".tmt-wrap{max-width:1180px;}"
        ".tmt-wrap .fd-input{padding:0 10px !important;}"
        ".tmt-pills{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 12px;}"
        ".tmt-pill{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:600;"
        "padding:6px 13px;border-radius:999px;border:1px solid var(--dd-border);"
        "background:var(--dd-card);color:var(--dd-text_l);cursor:pointer;font-family:inherit;"
        "transition:filter .12s,border-color .12s;}"
        ".tmt-pill:hover{border-color:var(--dd-teal);}"
        ".tmt-pill.on{border-color:var(--dd-teal);color:var(--dd-text_l);"
        "background:color-mix(in srgb,var(--dd-teal) 14%,var(--dd-card));}"
        ".tmt-pill .n{font-size:11px;color:var(--dd-muted);font-weight:700;}"
        ".tmt-grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(440px,1fr));}"
        "@media (max-width:980px){.tmt-grid{grid-template-columns:1fr;}}"
        ".tmt-card{background:var(--dd-card);border:1px solid var(--dd-border);border-radius:12px;"
        "padding:16px 18px;display:flex;flex-direction:column;gap:8px;position:relative;}"
        ".tmt-card.sig{border-color:color-mix(in srgb,var(--dd-danger) 55%,var(--dd-border));"
        "box-shadow:inset 3px 0 0 var(--dd-danger);}"
        ".tmt-top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}"
        ".tmt-name{font-size:15px;font-weight:800;color:var(--dd-text_l);line-height:1.3;}"
        ".tmt-meta{font-size:12px;color:var(--dd-muted);margin-top:2px;}"
        ".tmt-badges{display:flex;flex-wrap:wrap;gap:5px;}"
        ".tmt-b{display:inline-block;font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:999px;"
        "letter-spacing:.02em;border:1px solid transparent;}"
        ".tmt-b.strong{background:color-mix(in srgb,var(--dd-good) 16%,var(--dd-card));color:var(--dd-good);}"
        ".tmt-b.medium{background:color-mix(in srgb,var(--dd-teal) 14%,var(--dd-card));color:var(--dd-teal);}"
        ".tmt-b.weak{background:var(--dd-bg);color:var(--dd-muted);border-color:var(--dd-border);}"
        ".tmt-b.mk{background:var(--dd-bg);color:var(--dd-text_l);border-color:var(--dd-border);}"
        ".tmt-b.sig{background:var(--dd-danger);color:#fff;}"
        ".tmt-age{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:700;"
        "color:var(--dd-text_l);}"
        ".tmt-age.fresh{color:var(--dd-good);}"
        ".tmt-age .q-icon{font-size:15px;}"
        ".tmt-line{font-size:12.5px;color:var(--dd-text_l);line-height:1.5;}"
        ".tmt-line b{font-weight:700;}"
        ".tmt-roles{display:flex;flex-wrap:wrap;gap:5px;}"
        ".tmt-role{font-size:11px;padding:3px 9px;border-radius:7px;background:var(--dd-bg);"
        "border:1px solid var(--dd-border);color:var(--dd-text_l);}"
        ".tmt-sigbox{border-radius:9px;padding:9px 11px;font-size:12px;line-height:1.5;"
        "background:color-mix(in srgb,var(--dd-danger) 7%,var(--dd-card));"
        "border:1px solid color-mix(in srgb,var(--dd-danger) 30%,var(--dd-border));color:var(--dd-text_l);}"
        ".tmt-foot{display:flex;justify-content:space-between;align-items:center;gap:10px;"
        "margin-top:auto;padding-top:8px;border-top:1px solid var(--dd-border);}"
        ".tmt-links{display:flex;flex-wrap:wrap;gap:10px;}"
        ".tmt-links a{font-size:12px;font-weight:600;color:var(--dd-teal);text-decoration:none;}"
        ".tmt-links a:hover{text-decoration:underline;}"
        ".tmt-st{font-size:11.5px;font-weight:700;padding:4px 11px;border-radius:999px;cursor:pointer;"
        "border:1px solid var(--dd-border);background:var(--dd-card);color:var(--dd-muted);"
        "font-family:inherit;white-space:nowrap;}"
        ".tmt-st.working{border-color:var(--dd-teal);color:var(--dd-teal);}"
        ".tmt-st.contacted{border-color:var(--dd-good);color:var(--dd-good);}"
        ".tmt-st.no_fit{border-color:var(--dd-danger);color:var(--dd-danger);}"
        ".tmt-empty{padding:28px;text-align:center;color:var(--dd-muted);font-size:13px;"
        "border:1px dashed var(--dd-border);border-radius:12px;}"
        "</style>", sanitize=False)


def _state_attrs(s):
    for attr, default in (("_tmt_market", ""), ("_tmt_strong", False), ("_tmt_q", ""),
                          ("_tmt_hidden", False), ("_tmt_limit", 60)):
        if not hasattr(s, attr):
            setattr(s, attr, default)


def _card(r, st, today, C, on_status):
    sg = r.get("signal")
    n = days_since(r.get("posted"), today)
    fresh = n is not None and n <= FRESH_DAYS
    with ui.element("div").classes("tmt-card" + (" sig" if sg else "")):
        with ui.element("div").classes("tmt-top"):
            with ui.element("div"):
                ui.label(r["name"]).classes("tmt-name")
                meta = " · ".join(x for x in (r.get("hq"), size_label(r.get("size"))) if x)
                if meta:
                    ui.label(meta).classes("tmt-meta")
            with ui.element("div").classes("tmt-badges").style("justify-content:flex-end;"):
                html = ""
                if sg:
                    html += '<span class="tmt-b sig">Buying signal</span>'
                html += f'<span class="tmt-b {_e(r["tier"])}">{_e(TIER_LABEL.get(r["tier"], ""))}</span>'
                ui.html(html, sanitize=False)
        with ui.element("div").style("display:flex;flex-wrap:wrap;gap:8px;align-items:center;"):
            ui.html(f'<span class="tmt-b mk">{_e(MARKET_LABEL.get(r["market"], ""))}</span>'
                    f'<span class="tmt-b mk">{_e(KIND_LABEL.get(r["kind"], ""))}</span>',
                    sanitize=False)
            with ui.element("span").classes("tmt-age" + (" fresh" if fresh else "")):
                ui.icon("schedule")
                ui.label(age_label(r, today))
        if r.get("ph"):
            ui.html(f'<div class="tmt-line"><b>Filipino staff:</b> {_e(r["ph"])}</div>', sanitize=False)
        if r.get("roles"):
            with ui.element("div").classes("tmt-roles"):
                for role in [x.strip() for x in re.split(r",|;", r["roles"]) if x.strip()][:6]:
                    ui.label(role).classes("tmt-role")
        if r.get("pay"):
            ui.html(f'<div class="tmt-line"><b>Pay:</b> {_e(r["pay"])}</div>', sanitize=False)
        if sg:
            import tm_signals
            sdef = tm_signals.SIGNAL_BY_ID.get(sg.get("signal"), {})
            body = f'<b>{_e(sdef.get("label") or "Signal")}</b>'
            if sg.get("date"):
                body += f' <span style="color:{C["muted"]};">· {_e(sg["date"])}</span>'
            if sg.get("headline"):
                body += f'<div style="margin-top:3px;font-weight:600;">{_e(sg["headline"])}</div>'
            if sg.get("why_now"):
                body += f'<div style="margin-top:3px;"><b>Why it is a buying signal:</b> {_e(sg["why_now"])}</div>'
            if sg.get("source_url") and r.get("kind") != "signal":
                body += (f'<div style="margin-top:3px;"><a href="{_e(sg["source_url"])}" target="_blank" '
                         f'rel="noopener" style="color:var(--dd-teal);font-weight:600;">Signal source</a></div>')
            ui.html(f'<div class="tmt-sigbox">{body}</div>', sanitize=False)
        if r.get("note"):
            ui.html(f'<div class="tmt-line" style="color:{C["muted"]};">{_e(r["note"])}</div>',
                    sanitize=False)
        with ui.element("div").classes("tmt-foot"):
            links = "".join(
                f'<a href="{_e(x["url"])}" target="_blank" rel="noopener">{_e(x["label"])} ↗</a>'
                for x in (r.get("sources") or [])[:4])
            ui.html(f'<div class="tmt-links">{links or "&nbsp;"}</div>', sanitize=False)
            with ui.element("button").classes(f"tmt-st {st}").props(
                    'type="button" title="Click to change status"').on(
                    "click", lambda k=r["key"]: on_status(k)):
                ui.label(STATUS_LABEL.get(st, "New"))


def render_page(s, rf):
    ff = _ff()
    C = ff.C
    email = (getattr(s, "_user_email", "") or "").strip().lower()
    if email:
        try:
            ff._CURRENT_USER_EMAIL.set(email)
        except Exception:
            pass
    _state_attrs(s)
    today = date.today()
    state = load_state()
    status = state["status"]
    rows = all_rows()
    c = counts(rows, status, today)

    def _set_status(k):
        st = load_state()
        st["status"][k] = next_status(st["status"].get(k, "new"))
        if st["status"][k] == "new":
            st["status"].pop(k, None)
        save_state(st)
        rf()

    def _set(attr, val):
        setattr(s, attr, val)
        s._tmt_limit = 60
        rf()

    with ui.element("div").classes("tmt-wrap"):
        _css()
        with ui.element("div").style("margin-bottom:14px;"):
            ui.label("Target List").classes("fd-h1")
            ui.label("US companies that already hire or employ Filipino staff, plus every "
                     "company from your Buying Signals. Buying signals first, then the "
                     "newest postings. Click a card's status to track it."
                     ).classes("fd-sub")

        with ui.element("div").classes("fd-stat-strip").style("margin:0 0 14px;"):
            for val, lbl, col in [
                (c["total"], "Targets", C["text_l"]),
                (c["strong"], "Strong leads", C["good"]),
                (c["fresh"], f"Hiring in the last {FRESH_DAYS} days", C["teal"]),
                (c["signals"], "Buying signals", C["danger"]),
            ]:
                with ui.element("div").classes("fd-stat-cell" + (" zero" if not val else "")):
                    ui.label(str(val)).classes("fd-sn").style(f"color:{col};")
                    ui.label(lbl).classes("fd-sl")

        live = [r for r in rows if status.get(r["key"], "new") != "no_fit"]
        with ui.element("div").classes("tmt-pills"):
            for mk, ml in (("", "All markets"),) + data.MARKETS:
                n = sum(1 for r in live if not mk or r["market"] == mk)
                if mk and not n:
                    continue
                with ui.element("button").classes(
                        "tmt-pill" + (" on" if s._tmt_market == mk else "")).props(
                        'type="button"').on("click", lambda m=mk: _set("_tmt_market", m)):
                    ui.label(ml)
                    ui.label(str(n)).classes("n")

        with ui.element("div").classes("fd-filters").style(
                "margin-bottom:14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;"):
            def _on_q(e):
                s._tmt_q = e.value or ""
                s._tmt_limit = 60
                rf()
            ui.input(placeholder="Search company, city or role", value=s._tmt_q,
                     on_change=_on_q).classes("fd-input").props(
                'dense clearable debounce="300"').style("width:280px;")
            with ui.element("button").classes(
                    "tmt-pill" + (" on" if s._tmt_strong else "")).props('type="button"').on(
                    "click", lambda: _set("_tmt_strong", not s._tmt_strong)):
                ui.icon("star").style("font-size:15px;")
                ui.label("Strong only")
            if c["hidden"] or s._tmt_hidden:
                with ui.element("button").classes(
                        "tmt-pill" + (" on" if s._tmt_hidden else "")).props('type="button"').on(
                        "click", lambda: _set("_tmt_hidden", not s._tmt_hidden)):
                    ui.label("Not a fit")
                    ui.label(str(c["hidden"])).classes("n")

        shown = filter_rows(rows, status, s._tmt_market, s._tmt_strong, s._tmt_q, s._tmt_hidden)
        if not shown:
            ui.label("No targets match. Clear the search or pick another market."
                     ).classes("tmt-empty")
            return
        limit = int(s._tmt_limit or 60)
        with ui.element("div").classes("tmt-grid"):
            for r in shown[:limit]:
                _card(r, status.get(r["key"], "new"), today, C, _set_status)
        if len(shown) > limit:
            with ui.element("div").style("text-align:center;margin:16px 0;"):
                with ui.element("button").classes("fd-gb").style(
                        "padding:9px 20px;font-size:13px;").on(
                        "click", lambda: (setattr(s, "_tmt_limit", limit + 60), rf())):
                    ui.label(f"Show more ({len(shown) - limit} left)")
        ui.label(f"Research from {data.SEED_DATE}. Staff counts are directory estimates; "
                 "check a company before it goes into a campaign.").style(
            f"font-size:11px;color:{C['muted']};display:block;margin-top:14px;")

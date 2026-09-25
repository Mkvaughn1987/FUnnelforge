"""Companies and Pipeline: the two roll-up pages in the sidebar's SALES section.

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

Design: docs/superpowers/specs/2026-09-24-sales-companies-pipeline-design.md
"""
import json
import sys
from datetime import datetime

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
                   "campaigns": set(), "replies": [], "replied_emails": set()}
             for key in companies}

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
        elif status == "failed":
            st["failed"] += 1
            st["last"] = max(st["last"], _norm_ts(item.get("failed_at")))
        elif status == "pending":
            st["pending"] += 1

    for camp in (campaigns or []):
        if str(camp.get("status") or "") == "draft":
            continue
        name = str(camp.get("name") or "").strip()
        if not name:
            continue
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

    client_domains = [str(e.get("domain") or "") for e in (clients or [])
                      if isinstance(e, dict) and e.get("active", True)]
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
        rows.append({
            "key": key,
            "name": ent.get("name") or ent.get("domain") or key.split(":", 1)[-1],
            "domain": ent.get("domain", ""),
            "industry": ent.get("industry", ""),
            "company_size": ent.get("company_size", ""),
            "contacts": ent["contacts"],
            "contact_count": len(ent["contacts"]),
            "campaigns": sorted(st["campaigns"]),
            "sent": st["sent"], "pending": st["pending"], "failed": st["failed"],
            "replies": replies, "reply_count": len(replies),
            "replied_emails": st["replied_emails"],
            "last_activity": st["last"],
            "is_client": is_client,
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


def filter_rollup(rollup, q: str = "", stage: str = ""):
    q = (q or "").strip().lower()
    stage = (stage or "").strip().lower()
    out = []
    for r in rollup:
        if stage and r["stage"] != stage:
            continue
        if q and q not in r["name"].lower() and q not in (r["domain"] or "").lower():
            continue
        out.append(r)
    return out


def public_row(r: dict) -> dict:
    """The connector's view of a company: counts and stage, no contact dump."""
    return {
        "key": r["key"], "name": r["name"], "domain": r["domain"],
        "industry": r["industry"], "company_size": r["company_size"],
        "contacts": r["contact_count"], "campaigns": r["campaigns"],
        "sent": r["sent"], "scheduled": r["pending"], "replies": r["reply_count"],
        "last_activity": r["last_activity"], "is_client": r["is_client"],
        "stage": r["stage"], "stage_basis": r["stage_basis"],
        "next_step": r["next_step"], "note": r["note"],
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
    if any(rec.get(f) for f in RECORD_FIELDS):
        rec["updated_at"] = datetime.now().isoformat(timespec="seconds")
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
    with ui.element("div").style(
            f"background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:10px;padding:28px 24px;text-align:center;margin-top:16px;"):
        ui.label(headline).style(
            f"font-size:14px;font-weight:600;color:{C['text_l']};"
            f"font-family:'Nunito',sans-serif;margin-bottom:4px;")
        ui.label(body).style(f"font-size:12px;color:{C['muted']};")
        if cta_label and cta:
            with ui.element("button").classes("fd-pb").style(
                    "padding:9px 16px;font-size:12px;margin-top:14px;").on("click", cta):
                ui.label(cta_label)


def _go(s, rf, page_key):
    ff = _ff()
    ff._sidebar_nav(s, rf, page_key, ff._sidebar_setup_status())


def p_companies(s, rf):
    ff = _ff()
    C = ff.C
    actor = (getattr(s, "_user_email", "") or "").strip().lower()
    rollup = rollup_for_user(actor)
    q = getattr(s, "_co_q", "") or ""
    stage = getattr(s, "_co_stage", "") or ""
    open_key = getattr(s, "_co_open", "") or ""

    _page_head(s, rf, C, "Companies", "companies",
               "Every company you have a contact at, with what your campaigns "
               "have done there. Counted from your lists, the send queue and "
               "your replies.")

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
            with ui.element("div").classes("fd-stat-cell"):
                ui.label(val).classes("fd-sn").style(f"color:{col};")
                ui.label(lbl).classes("fd-sl")

    # ── Filters ──
    with ui.element("div").style("display:flex;gap:10px;align-items:center;"
                                 "flex-wrap:wrap;margin-bottom:12px;"):
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
        ui.select(options=stage_opts, value=stage, on_change=_on_stage).classes(
            "fd-input").props("dense").style("min-width:160px;font-size:12px;")
        with ui.element("button").classes("fd-gb").style(
                "padding:8px 14px;font-size:12px;").on(
                "click", lambda: _go(s, rf, "pipeline")):
            ui.label("Open the Pipeline board")

    rows = filter_rollup(rollup, q, stage)
    if not rows:
        _empty_card(C, "No companies match", "Try a shorter search or another stage.")
        return
    shown = rows[:200]

    def _toggle(key):
        s._co_open = "" if open_key == key else key
        rf()

    with ui.element("div").style(
            f"border:1px solid {C['border']};border-radius:10px;overflow:hidden;"
            f"background:{C['card']};"):
        with ui.element("table").classes("fd-tbl"):
            with ui.element("thead"):
                with ui.element("tr"):
                    for h in ("Company", "Contacts", "Campaigns", "Sent",
                              "Replies", "Last activity", "Stage"):
                        with ui.element("th"):
                            ui.label(h)
            with ui.element("tbody"):
                for r in shown:
                    is_open = r["key"] == open_key
                    with ui.element("tr"):
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
                            _stage_badge(C, r)
                    if is_open:
                        with ui.element("tr"):
                            with ui.element("td").props('colspan="7"').style(
                                    f"background:{C['surface']};padding:16px 18px;"):
                                _company_detail(s, rf, C, r, actor)
    if len(rows) > len(shown):
        ui.label(f"Showing {len(shown)} of {len(rows)}. Narrow it with the search box.").style(
            f"font-size:11px;color:{C['muted']};margin-top:8px;")


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
                with ui.element("button").classes("fd-gb").style(
                        "padding:8px 14px;font-size:12px;").on(
                        "click", lambda: _go(s, rf, "pipeline")):
                    ui.label("See on the board")
            rec = r["record"]
            if rec.get("updated_at"):
                ui.label(f"Updated {_fmt_when(_norm_ts(rec['updated_at']))}"
                         + (f" by {rec['updated_by']}" if rec.get("updated_by") else "")
                         ).style(f"font-size:11px;color:{C['muted']};margin-top:8px;")


def p_pipeline(s, rf):
    ff = _ff()
    C = ff.C
    actor = (getattr(s, "_user_email", "") or "").strip().lower()
    rollup = rollup_for_user(actor)
    cols = board_columns(rollup)
    show_lost = bool(getattr(s, "_pl_show_lost", False))

    _page_head(s, rf, C, "Pipeline", "pipeline",
               "Every company a campaign has touched, by stage. Prospect, "
               "Contacted and Replied come from what was sent; move a card to "
               "record a meeting, a proposal or a loss. Clients come from the "
               "Clients list.")

    total = sum(c["total"] for c in cols.values())
    if not total:
        _empty_card(C, "Nothing on the board yet",
                    "Companies land here once they are in a campaign. Launch "
                    "one, or open a company and set a stage by hand.",
                    "Go to Companies", lambda: _go(s, rf, "companies"))
        return

    with ui.element("div").classes("fd-stat-strip").style("margin:14px 0 14px;"):
        for k, lbl in STAGES:
            n = cols[k]["total"]
            col = {"client": C["good"], "replied": C["good"],
                   "lost": C["muted"], "prospect": C["muted"]}.get(k, C["teal"])
            with ui.element("div").classes("fd-stat-cell"):
                ui.label(str(n)).classes("fd-sn").style(
                    f"color:{col if n else C['muted']};")
                ui.label(lbl).classes("fd-sl")

    def _open_company(r):
        s._co_open = r["key"]
        s._co_q = ""
        s._co_stage = ""
        _go(s, rf, "companies")

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
                    ui.label(f"+{col['total'] - len(col['rows'])} more on Companies").style(
                        f"font-size:11px;color:{C['muted']};text-align:center;padding:4px 0;")

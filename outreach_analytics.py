"""Outreach Analytics, grouped by campaign type.

Shared by inboxslide (ThriveModal) and DripDrop (Arena). Every number is
counted from records the send path already writes - the send queue (plus its
archive for "All time"), the replies log and the do-not-contact list - and
joined to the saved campaigns only to learn which type each campaign was
built as (Standard Outreach, Quick Intro, Arena 4x4...). Nothing here writes.

The top level is one row per campaign TYPE. Clicking a type opens it: its
totals, one row per email in the sequence (sent, replies, reply rate, and the
emails themselves on click), and the individual campaigns run as that type.

`build_report` is pure so it can be tested without a filesystem; `render`
draws it and takes every app dependency (ui, palette) as an argument, so the
module imports nothing from either app.
"""
import re
from datetime import datetime, timedelta

_STEP_PREFIX = re.compile(r"^\s*(?:step|email)\s*\d+\s*[-–—:.]\s*", re.I)

NEWSLETTER = "_newsletter"
OTHER = "_other"
_GROUP_NAMES = {NEWSLETTER: "Newsletters", OTHER: "Other campaigns"}
_GROUP_COLORS = {NEWSLETTER: "#8B5CF6", OTHER: "#64748B"}

_BOUNCE_HINTS = ("bounce", "undeliverable", "no such user",
                 "recipient not found", "address rejected")
_OPTOUT_HINTS = ("opt-out", "opt out", "optout", "unsubscrib",
                 "remove me", "take me off")
# Steps that are queued for the record but are not emails someone received.
_NON_EMAIL_STEP_TYPES = {"call", "linkedin", "sms", "task_general"}
EMAIL_LIST_CAP = 100


# ── small pure helpers ──────────────────────────────────────────────────────

def _s(val):
    return str(val or "").strip()


def rate(num, den):
    """num/den as a 4dp float; 0.0 when nothing was measured."""
    try:
        num, den = float(num or 0), float(den or 0)
    except (TypeError, ValueError):
        return 0.0
    return round(num / den, 4) if den > 0 else 0.0


def window_cutoff(days, now=None):
    try:
        days = int(days or 0)
    except (TypeError, ValueError):
        return ""
    if days <= 0:
        return ""
    return ((now or datetime.now()) - timedelta(days=days)).isoformat()


def in_window(ts, cutoff):
    """Undated records count in every window: a row that silently drops out
    of a report is an error nobody can see; one counted is one they can."""
    if not cutoff:
        return True
    ts = _s(ts)
    return (not ts) or ts >= cutoff


def queue_ts(item):
    """Sent-at beats failed-at beats scheduled-for."""
    for key in ("sent_at", "failed_at", "send_dt"):
        val = _s((item or {}).get(key))
        if val:
            return val
    return ""


def reply_ts(rec):
    """The reply monitor writes `date`; add_responded() writes `replied_at`."""
    rec = rec or {}
    return _s(rec.get("replied_at")) or _s(rec.get("date"))


def dnc_ts(entry):
    entry = entry or {}
    return _s(entry.get("added_at")) or _s(entry.get("added"))


def dnc_kind(entry):
    entry = entry or {}
    reason = _s(entry.get("reason")).lower()
    source = _s(entry.get("source")).lower()
    if any(h in reason for h in _BOUNCE_HINTS):
        return "bounce"
    if any(h in source for h in _OPTOUT_HINTS) or any(h in reason for h in _OPTOUT_HINTS):
        return "optout"
    return "manual"


def touch_of(item):
    try:
        touch = int((item or {}).get("touch_number") or 0)
    except (TypeError, ValueError):
        touch = 0
    if touch <= 0:
        try:
            touch = int((item or {}).get("_step_idx") or 0) + 1
        except (TypeError, ValueError):
            touch = 1
    return max(touch, 1)


def _is_email_row(item):
    return _s((item or {}).get("step_type")).lower() not in _NON_EMAIL_STEP_TYPES


def campaign_type_of(camp, type_keys):
    """The type a saved campaign was built as. The wizard saves it as
    template_key, the API as aicb_camp_type, the chooser as _chooser_origin."""
    camp = camp or {}
    if camp.get("market_analysis") or camp.get("is_newsletter"):
        return NEWSLETTER
    for m in (camp.get("aicb_camp_type"), camp.get("template_key"),
              camp.get("_chooser_origin")):
        m = _s(m)
        if m and m in type_keys:
            return m
    return OTHER


def merge_queue(live, archive):
    """Live queue plus archive, de-duplicated by id (live wins)."""
    out, seen = [], set()
    for item in list(live or []) + list(archive or []):
        if not isinstance(item, dict):
            continue
        qid = _s(item.get("id"))
        if qid:
            if qid in seen:
                continue
            seen.add(qid)
        out.append(item)
    return out


# ── the report ──────────────────────────────────────────────────────────────

def _blank(extra=None):
    row = {"sent": 0, "pending": 0, "failed": 0, "cancelled": 0,
           "contacts": 0, "replies": 0, "reply_rate": 0.0, "_reached": set()}
    row.update(extra or {})
    return row


def _close(row):
    row["contacts"] = len(row.pop("_reached", set()))
    row["reply_rate"] = rate(row["replies"], row["contacts"])
    return row


def build_report(queue, responded, dnc, campaigns, types, days=None, now=None):
    """Everything the page shows, for one window.

    `types` is [(key, display_name, color)] in the app's own order.
    Returns {"totals", "types": [row], "details": {key: detail}}.

    Reply rate is replies / people reached (not emails sent). A reply is
    credited to the type of the campaign it names, and to the LAST email that
    person was sent in that campaign before replying - the email they were
    answering. A reply with no matching send stays in the type total only."""
    cutoff = window_cutoff(days, now)
    type_keys = {k for k, _n, _c in (types or [])}
    names = {k: n for k, n, _c in (types or [])}
    colors = {k: c for k, _n, c in (types or [])}
    order = {k: i for i, (k, _n, _c) in enumerate(types or [])}

    camp_type = {}
    for camp in (campaigns or []):
        if isinstance(camp, dict) and _s(camp.get("name")):
            camp_type[_s(camp.get("name")).lower()] = campaign_type_of(camp, type_keys)

    def _type_for(name):
        return camp_type.get(_s(name).lower(), OTHER)

    totals = _blank()
    tmap, details = {}, {}

    def _trow(key):
        if key not in tmap:
            tmap[key] = _blank({"key": key,
                                "name": names.get(key) or _GROUP_NAMES.get(key, key),
                                "color": colors.get(key) or _GROUP_COLORS.get(key, "#64748B"),
                                "_camps": set()})
            details[key] = {"steps": {}, "campaigns": {}}
        return tmap[key]

    def _step(key, touch):
        steps = details[key]["steps"]
        if touch not in steps:
            steps[touch] = _blank({"touch": touch, "_labels": {}, "emails": []})
        return steps[touch]

    def _camp(key, name):
        camps = details[key]["campaigns"]
        low = name.lower()
        if low not in camps:
            camps[low] = _blank({"name": name})
        return camps[low]

    # Every send per (campaign, address), regardless of window, so a reply
    # inside the window can find the email it answered even if that email
    # went out before the window opened.
    sends_by = {}
    for item in (queue or []):
        if not isinstance(item, dict) or not _is_email_row(item):
            continue
        name = _s(item.get("campaign"))
        status = _s(item.get("status")).lower()
        if status == "sent" and name:
            addr = _s(item.get("to")).lower()
            if addr:
                sends_by.setdefault((name.lower(), addr), []).append(
                    (queue_ts(item), touch_of(item)))
        if not in_window(queue_ts(item), cutoff):
            continue
        if status not in ("sent", "pending", "failed", "cancelled"):
            continue
        totals[status] += 1
        if not name:
            continue
        key = _type_for(name)
        trow, step, crow = _trow(key), None, None
        trow["_camps"].add(name.lower())
        step = _step(key, touch_of(item))
        crow = _camp(key, name)
        for r in (trow, step, crow):
            r[status] += 1
        # "Step 1 - The Signal" -> "The Signal"; the table numbers rows itself.
        label = _STEP_PREFIX.sub("", _s(item.get("step_name"))) or _s(item.get("step_name"))
        if label:
            step["_labels"][label] = step["_labels"].get(label, 0) + 1
        if status == "sent":
            addr = _s(item.get("to")).lower()
            if addr:
                for r in (totals, trow, step, crow):
                    r["_reached"].add(addr)
            step["emails"].append({
                "to": _s(item.get("to")),
                "to_name": _s(item.get("to_name") or item.get("contact_name")),
                "company": _s(item.get("contact_company")),
                "campaign": name,
                "subject": _s(item.get("subject")),
                "sent_at": queue_ts(item),
                "replied": False,
            })

    replied_keys = set()   # (campaign_lower, addr, touch) credited a reply
    for rec in (responded or []):
        if not isinstance(rec, dict):
            continue
        ts = reply_ts(rec)
        if not in_window(ts, cutoff):
            continue
        totals["replies"] += 1
        name = _s(rec.get("campaign"))
        if not name or name in ("-", " - "):
            continue
        key = _type_for(name)
        trow = _trow(key)
        trow["_camps"].add(name.lower())
        trow["replies"] += 1
        _camp(key, name)["replies"] += 1
        addr = _s(rec.get("email")).lower()
        sends = sends_by.get((name.lower(), addr), [])
        before = [s for s in sends if not ts or not s[0] or s[0] <= ts]
        if before:
            touch = max(before)[1]   # latest send; a tie goes to the later step
            _step(key, touch)["replies"] += 1
            replied_keys.add((name.lower(), addr, touch))

    rows = []
    for key, trow in tmap.items():
        trow["campaigns"] = len(trow.pop("_camps"))
        rows.append(_close(trow))
        det = details[key]
        steps = []
        for touch in sorted(det["steps"]):
            st = det["steps"][touch]
            labels = st.pop("_labels")
            st["label"] = (max(labels.items(), key=lambda kv: kv[1])[0]
                           if labels else f"Email {touch}")
            for em in st["emails"]:
                em["replied"] = (em["campaign"].lower(), em["to"].lower(),
                                 touch) in replied_keys
            st["emails"].sort(key=lambda e: e["sent_at"], reverse=True)
            steps.append(_close(st))
        camps = [_close(c) for c in det["campaigns"].values()]
        camps.sort(key=lambda r: (-r["sent"], -r["replies"], r["name"].lower()))
        details[key] = {"type": trow, "steps": steps, "campaigns": camps}

    def _sort_key(r):
        group_last = 1 if r["key"] in _GROUP_NAMES else 0
        return (group_last, -r["sent"], -r["pending"], order.get(r["key"], 999))
    rows.sort(key=_sort_key)

    optouts = bounces = 0
    for entry in (dnc or []):
        if not isinstance(entry, dict) or not in_window(dnc_ts(entry), cutoff):
            continue
        kind = dnc_kind(entry)
        if kind == "optout":
            optouts += 1
        elif kind == "bounce":
            bounces += 1
    _close(totals)
    totals["optouts"], totals["bounces"] = optouts, bounces
    return {"totals": totals, "types": rows, "details": details}


def campaign_detail(report, key, campaign):
    """The step table for one campaign of a type: recomputed from the type's
    sent-email lists, which already carry the campaign name and reply flag."""
    det = (report or {}).get("details", {}).get(key)
    if not det:
        return []
    low = _s(campaign).lower()
    out = []
    for st in det["steps"]:
        emails = [e for e in st["emails"] if e["campaign"].lower() == low]
        people = {e["to"].lower() for e in emails if e["to"]}
        replies = sum(1 for e in emails if e["replied"])
        out.append({"touch": st["touch"], "label": st["label"],
                    "sent": len(emails), "contacts": len(people),
                    "replies": replies, "reply_rate": rate(replies, len(people)),
                    "pending": None, "cancelled": None, "emails": emails})
    return [r for r in out if r["sent"]]


# ── rendering ───────────────────────────────────────────────────────────────

def _pct(val):
    return f"{(val or 0) * 100:.1f}%"


def _hover(el, C):
    """Row hover without ui.add_css, which would add a style tag per render."""
    return el.props(
        f'onmouseover="this.style.background=\'{C["surface"]}\'" '
        f'onmouseout="this.style.background=\'\'"')


def _fmt_date(ts):
    try:
        return datetime.fromisoformat(_s(ts)[:19]).strftime("%b %d, %Y")
    except Exception:
        return _s(ts)[:10] or "-"


_WINDOWS = [(7, "7 days"), (30, "30 days"), (None, "All time")]
# Tables this narrow read as one block; stretched across a wide monitor the
# numbers sit a screen-width away from the name they belong to.
PAGE_MAX_PX = 1240


def render(ui, C, s, rf, sources, types, help_fn=None):
    """Draw the page. `sources` is a callable(days) -> dict(queue, responded,
    dnc, campaigns); it is called once per render so "All time" can pull the
    archive without the shorter windows paying for it."""
    with ui.element("div").style(f"max-width:{PAGE_MAX_PX}px;width:100%;"):
        _render_page(ui, C, s, rf, sources, types, help_fn)


def _render_page(ui, C, s, rf, sources, types, help_fn):
    days = getattr(s, "_oa_days", 30)
    if days not in (7, 30, None):
        days = 30
    try:
        src = sources(days) or {}
    except Exception:
        src = {}
    report = build_report(src.get("queue"), src.get("responded"), src.get("dnc"),
                          src.get("campaigns"), types, days=days)
    sel = getattr(s, "_oa_type", None)
    if sel and sel not in report["details"]:
        sel = s._oa_type = None

    muted, text = C["muted"], C["text_l"]
    hdr_css = (f"font-size:9px;font-weight:700;color:{muted};"
               f"text-transform:uppercase;letter-spacing:.06em;")
    cell = f"font-size:12px;color:{muted};"
    title_css = (f"font-size:14px;font-weight:700;color:{text};"
                 f"font-family:'Nunito',sans-serif;margin-bottom:8px;")
    card_css = (f"background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:10px;overflow:hidden;margin-bottom:8px;")
    head_row = (f"padding:8px 14px;background:{C['surface']};"
                f"border-bottom:1px solid {C['border']};")
    body_row = f"padding:9px 14px;align-items:center;border-bottom:1px solid {C['border']};"
    window_label = "all time" if days is None else f"the last {days} days"

    def _grid(cols, extra=""):
        return f"display:grid;grid-template-columns:{cols};gap:8px;{extra}"

    def _num(val, color_if=None):
        col = color_if if (val and color_if) else muted
        ui.label("-" if val is None else str(val)).style(f"font-size:12px;color:{col};")

    def _strip(items):
        with ui.element("div").classes("fd-stat-strip").style("margin:14px 0 10px;"):
            for val, lbl, col in items:
                with ui.element("div").classes("fd-stat-cell"):
                    ui.label(val).classes("fd-sn").style(f"color:{col};")
                    ui.label(lbl).classes("fd-sl")

    def _dot(color):
        ui.element("span").style(
            f"display:inline-block;width:10px;height:10px;border-radius:50%;"
            f"background:{color};flex-shrink:0;")

    # ── header + window selector ────────────────────────────────────────
    with ui.element("div").style(
            "display:flex;align-items:flex-start;justify-content:space-between;"
            "gap:16px;margin-bottom:6px;flex-wrap:wrap;"):
        with ui.element("div").style("flex:1;min-width:220px;"):
            with ui.element("div").style("display:flex;align-items:center;"):
                ui.label("Outreach Analytics").classes("fd-h1")
                if help_fn:
                    help_fn()
            ui.label("How your campaigns and newsletters are performing. Click "
                     "a campaign to see who each email went to and who "
                     "replied.").classes("fd-sub")
        with ui.element("div").style("display:flex;gap:8px;flex-shrink:0;"):
            for win, wlbl in _WINDOWS:
                def _pick(win=win):
                    s._oa_days = win
                    s._oa_step = None
                    rf()
                with ui.element("button").classes(
                        "fd-pb" if win == days else "fd-gb").style(
                        "padding:9px 14px;font-size:12px;").on("click", _pick):
                    ui.label(wlbl)

    # ── drill-in: one campaign type ─────────────────────────────────────
    if sel:
        _render_type(ui, C, s, rf, report, sel, window_label, _strip, _grid,
                     _num, _dot, hdr_css, cell, title_css, card_css, head_row,
                     body_row)
        return

    # ── overview ────────────────────────────────────────────────────────
    t = report["totals"]
    _strip([
        (str(t["sent"]), "Emails sent", text),
        (str(t["contacts"]), "People reached", text),
        (str(t["replies"]), "Replies", C["good"] if t["replies"] else muted),
        (_pct(t["reply_rate"]), "Reply rate", C["good"] if t["reply_rate"] else muted),
        (str(t["pending"]), "Scheduled", C["teal"] if t["pending"] else muted),
        (str(t["optouts"]), "Opt-outs", C["warn"] if t["optouts"] else muted),
        (str(t["bounces"]), "Bounces", C["warn"] if t["bounces"] else muted),
    ])
    ui.label(f"Counted over {window_label}. Reply rate is replies divided by "
             f"people reached, not emails sent. Opens and clicks aren't "
             f"tracked, so they aren't shown.").style(
        f"font-size:11px;color:{muted};margin-bottom:18px;")

    if not report["types"]:
        with ui.element("div").style(card_css + "padding:28px 24px;text-align:center;"):
            ui.label("Nothing to report for this window yet.").style(
                f"font-size:14px;font-weight:600;color:{text};margin-bottom:4px;")
            ui.label("Numbers appear here once a campaign has emails queued "
                     "or sent. Try a wider window above.").style(cell)
        return

    def _open(key, step=None, camp=None):
        s._oa_type = key
        s._oa_step = step
        s._oa_camp = camp
        rf()

    def _rate_label(val):
        ui.label(_pct(val)).style(
            f"font-size:12px;color:{C['good'] if val else muted};")

    # ── Campaigns: one card per type, its emails listed right here ──────
    camp_rows = [r for r in report["types"] if r["key"] != NEWSLETTER]
    ui.label("Campaigns").style(title_css)
    if not camp_rows:
        ui.label("No campaign emails in this window.").style(cell + "margin-bottom:18px;")
    cols = "minmax(0,1fr) 44px 52px 56px 66px 12px"
    # Two cards per row; one per row once a card would be too narrow to read.
    pair = ui.element("div").style(
        "display:grid;grid-template-columns:repeat(auto-fit,minmax(min(440px,100%),1fr));"
        "gap:12px;align-items:start;margin-bottom:12px;")
    for row in camp_rows:
        det = report["details"][row["key"]]
        n = row["campaigns"]
        with pair, ui.element("div").style(card_css + "margin-bottom:0;"):
            with _hover(ui.element("div").style(
                    f"display:flex;align-items:center;gap:10px;flex-wrap:wrap;"
                    f"padding:11px 14px;border-bottom:1px solid {C['border']};"
                    f"cursor:pointer;"), C).on(
                    "click", lambda key=row["key"]: _open(key)):
                _dot(row["color"])
                ui.label(row["name"]).style(
                    f"font-size:14px;font-weight:700;color:{text};")
                ui.label(f"{n} campaign{'s' if n != 1 else ''} · {row['sent']} sent"
                         f" · {row['contacts']} people · {row['replies']} "
                         f"repl{'ies' if row['replies'] != 1 else 'y'} "
                         f"({_pct(row['reply_rate'])})"
                         + (f" · {row['pending']} scheduled" if row["pending"] else "")
                         ).style(cell + "flex:1;min-width:200px;")
                ui.label("Details ›").style(
                    f"font-size:12px;font-weight:600;color:{C['teal']};")
            with ui.element("div").style(_grid(cols, head_row)):
                for h in ["Email", "Sent", "Replies", "Rate", "Scheduled", ""]:
                    ui.label(h).style(hdr_css)
            for st in det["steps"]:
                with _hover(ui.element("div").style(
                        _grid(cols, body_row + "cursor:pointer;")), C).on(
                        "click", lambda key=row["key"], t=st["touch"]: _open(key, step=t)):
                    ui.label(f"{st['touch']}. {st['label']}").style(
                        f"font-size:12px;font-weight:600;color:{text};"
                        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;")
                    _num(st["sent"])
                    _num(st["replies"], C["good"])
                    _rate_label(st["reply_rate"])
                    _num(st["pending"], C["teal"])
                    ui.label("›").style(f"font-size:14px;color:{muted};")
            if not det["steps"]:
                ui.label("Replies only; the emails that earned them have aged "
                         "out of this window.").style(cell + "padding:9px 14px;")

    # ── Newsletters: every newsletter on the first screen ───────────────
    ui.label("Newsletters").style(title_css + "margin-top:10px;")
    nl = report["details"].get(NEWSLETTER)
    if not nl or not nl["campaigns"]:
        ui.label("No newsletters sent in this window.").style(cell + "margin-bottom:18px;")
    else:
        cols = "minmax(0,1fr) 56px 64px 64px 76px 76px 18px"
        with ui.element("div").style(card_css + "margin-bottom:12px;"):
            with ui.element("div").style(_grid(cols, head_row)):
                for h in ["Newsletter", "Sent", "People", "Replies",
                          "Reply rate", "Scheduled", ""]:
                    ui.label(h).style(hdr_css)
            for c in nl["campaigns"]:
                with _hover(ui.element("div").style(
                        _grid(cols, body_row + "cursor:pointer;")), C).on(
                        "click", lambda name=c["name"]: _open(NEWSLETTER, camp=name)):
                    with ui.element("div").style(
                            "display:flex;align-items:center;gap:8px;min-width:0;"):
                        _dot(_GROUP_COLORS[NEWSLETTER])
                        ui.label(c["name"]).style(
                            f"font-size:12px;font-weight:600;color:{text};"
                            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;")
                    _num(c["sent"])
                    _num(c["contacts"])
                    _num(c["replies"], C["good"])
                    _rate_label(c["reply_rate"])
                    _num(c["pending"], C["teal"])
                    ui.label("›").style(f"font-size:14px;color:{muted};")
    ui.label("Opt-outs and bounces stay workspace-wide: the do-not-contact list "
             "doesn't record which campaign an address came from.").style(
        f"font-size:11px;color:{muted};margin-bottom:20px;")


def _render_type(ui, C, s, rf, report, key, window_label, _strip, _grid, _num,
                 _dot, hdr_css, cell, title_css, card_css, head_row, body_row):
    det = report["details"][key]
    trow = det["type"]
    muted, text = C["muted"], C["text_l"]
    camp_filter = getattr(s, "_oa_camp", None)
    if camp_filter and not any(c["name"] == camp_filter for c in det["campaigns"]):
        camp_filter = s._oa_camp = None
    steps = campaign_detail(report, key, camp_filter) if camp_filter else det["steps"]
    open_step = getattr(s, "_oa_step", None)

    def _back():
        s._oa_type = None
        s._oa_step = None
        s._oa_camp = None
        rf()

    with ui.element("button").classes("fd-gb").style(
            "padding:6px 12px;font-size:12px;margin:10px 0 4px;").on("click", _back):
        ui.label("← Back to overview")

    with ui.element("div").style("display:flex;align-items:center;gap:10px;margin-top:8px;"):
        _dot(trow["color"])
        ui.label(trow["name"]).style(
            f"font-size:20px;font-weight:800;color:{text};font-family:'Nunito',sans-serif;")
    n = trow["campaigns"]
    ui.label(f"{n} campaign{'s' if n != 1 else ''}, counted over {window_label}."
             ).style(f"font-size:12px;color:{muted};")

    _strip([
        (str(trow["sent"]), "Emails sent", text),
        (str(trow["contacts"]), "People reached", text),
        (str(trow["replies"]), "Replies", C["good"] if trow["replies"] else muted),
        (_pct(trow["reply_rate"]), "Reply rate",
         C["good"] if trow["reply_rate"] else muted),
        (str(trow["pending"]), "Scheduled", C["teal"] if trow["pending"] else muted),
    ])

    # ── emails in the sequence ──────────────────────────────────────────
    with ui.element("div").style(
            "display:flex;align-items:center;gap:10px;margin:14px 0 8px;flex-wrap:wrap;"):
        ui.label("Emails in this campaign type" if not camp_filter
                 else f"Emails in {camp_filter}").style(title_css + "margin-bottom:0;")
        if camp_filter:
            def _clear():
                s._oa_camp = None
                s._oa_step = None
                rf()
            with ui.element("button").classes("fd-gb").style(
                    "padding:3px 10px;font-size:11px;").on("click", _clear):
                ui.label("× Show all campaigns")

    if not steps:
        ui.label("No emails in this window yet.").style(cell + "margin-bottom:16px;")
    else:
        cols = "minmax(0,1fr) 60px 60px 74px 74px 70px 18px"
        with ui.element("div").style(card_css):
            with ui.element("div").style(_grid(cols, head_row)):
                for h in ["Email", "Sent", "Replies", "Reply rate",
                          "Scheduled", "Stopped", ""]:
                    ui.label(h).style(hdr_css)
            for st in steps:
                is_open = open_step == st["touch"]

                def _toggle(touch=st["touch"], was=is_open):
                    s._oa_step = None if was else touch
                    rf()
                with _hover(ui.element("div").style(
                        _grid(cols, body_row + "cursor:pointer;")), C).on("click", _toggle):
                    ui.label(f"{st['touch']}. {st['label']}").style(
                        f"font-size:12px;font-weight:600;color:{text};"
                        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;")
                    _num(st["sent"])
                    _num(st["replies"], C["good"])
                    ui.label(_pct(st["reply_rate"])).style(
                        f"font-size:12px;color:{C['good'] if st['reply_rate'] else muted};")
                    _num(st["pending"], C["teal"])
                    _num(st["cancelled"])
                    ui.label("▾" if is_open else "›").style(
                        f"font-size:14px;color:{muted};")
                if is_open:
                    _render_emails(ui, C, st, hdr_css, cell, body_row, _grid)
            ui.label("A reply is credited to the last email that person was sent "
                 "before replying. Reply rate is replies divided by the people "
                 "that email reached. Stopped = steps cancelled because the "
                 "person replied, opted out or bounced.").style(
            f"font-size:11px;color:{muted};margin-bottom:20px;")

    # ── campaigns run as this type ──────────────────────────────────────
    if det["campaigns"]:
        cols = "minmax(0,1fr) 60px 60px 74px 60px 74px"
        ui.label("Campaigns").style(title_css)
        with ui.element("div").style(card_css):
            with ui.element("div").style(_grid(cols, head_row)):
                for h in ["Campaign", "Sent", "People", "Scheduled",
                          "Replies", "Reply rate"]:
                    ui.label(h).style(hdr_css)
            for c in det["campaigns"]:
                on = c["name"] == camp_filter

                def _pick(name=c["name"], was=on):
                    s._oa_camp = None if was else name
                    s._oa_step = None
                    rf()
                bg = f"background:{C['surface']};" if on else ""
                _crow = ui.element("div").style(
                    _grid(cols, body_row + "cursor:pointer;" + bg))
                if not on:
                    _hover(_crow, C)
                with _crow.on("click", _pick):
                    ui.label(c["name"]).style(
                        f"font-size:12px;font-weight:{700 if on else 500};color:{text};"
                        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;")
                    _num(c["sent"])
                    _num(c["contacts"])
                    _num(c["pending"], C["teal"])
                    _num(c["replies"], C["good"])
                    ui.label(_pct(c["reply_rate"])).style(
                        f"font-size:12px;color:{C['good'] if c['reply_rate'] else muted};")
        ui.label("Click a campaign to see its emails on their own.").style(
            f"font-size:11px;color:{muted};margin-bottom:8px;")


def _render_emails(ui, C, st, hdr_css, cell, body_row, _grid):
    emails = st["emails"]
    muted, text = C["muted"], C["text_l"]
    with ui.element("div").style(
            f"background:{C['surface']};padding:6px 14px 10px 28px;"
            f"border-bottom:1px solid {C['border']};"):
        if not emails:
            ui.label("Nothing has gone out for this email yet; it is still "
                     "scheduled.").style(cell + "padding:6px 0;")
            return
        cols = "minmax(0,1.2fr) minmax(0,1fr) minmax(0,1.6fr) 90px 70px"
        with ui.element("div").style(_grid(cols, "padding:6px 0;")):
            for h in ["To", "Company", "Subject", "Sent", "Replied"]:
                ui.label(h).style(hdr_css)
        for em in emails[:EMAIL_LIST_CAP]:
            with ui.element("div").style(_grid(cols, "padding:5px 0;align-items:center;")):
                with ui.element("div").style("min-width:0;"):
                    ui.label(em["to_name"] or em["to"]).style(
                        f"font-size:12px;color:{text};white-space:nowrap;"
                        f"overflow:hidden;text-overflow:ellipsis;")
                    if em["to_name"]:
                        ui.label(em["to"]).style(
                            f"font-size:10px;color:{muted};white-space:nowrap;"
                            f"overflow:hidden;text-overflow:ellipsis;")
                ui.label(em["company"] or "-").style(
                    cell + "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;")
                ui.label(em["subject"] or "-").style(
                    cell + "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
                ).tooltip(em["subject"] or "")
                ui.label(_fmt_date(em["sent_at"])).style(cell)
                ui.label("Yes" if em["replied"] else "-").style(
                    f"font-size:12px;font-weight:{700 if em['replied'] else 400};"
                    f"color:{C['good'] if em['replied'] else muted};")
        if len(emails) > EMAIL_LIST_CAP:
            ui.label(f"Showing the latest {EMAIL_LIST_CAP} of {len(emails)}.").style(
                f"font-size:11px;color:{muted};padding-top:6px;")

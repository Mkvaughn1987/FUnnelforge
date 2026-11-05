"""Build a Custom Campaign: the page.

The second card in the sidebar's Start a Campaign dialog. The user builds a
campaign one step at a time (email, call or LinkedIn), writes each step or
has AI draft it, can put ThriveModal's candidate profiles and a Sales PDF on
any email after the first, saves it, and reuses it for other companies.
Saving builds a real draft campaign, which then goes to the campaign's own
Choose Contacts / Preview Campaign screens.

Adapted from DripDrop's "Create my own campaign" walkthrough (p_seq_builder
on the DripDrop line). The wording, the AI direction, the PDFs and the
candidate profiles are ThriveModal's; tm_custom_campaign holds the logic.

State lives in one dict, s.tmc_state (see _w), which _reset_wizard_state
clears with the other wizard fields. Saved campaigns are kept in their own
per-user file, not in My Campaign Styles, so the older style pickers and the
connector's style list never show a row they would have AI rewrite.
"""
import asyncio
import copy
import hashlib
import json
import sys
import uuid
from datetime import date, datetime

from nicegui import ui

import tm_custom_campaign as cc

PAGE_KEY = "tm_custom_campaign"
TITLE = "Build a Custom Campaign"
SAVED_FILE = "tm_custom_campaigns.json"

_DRAFT_MODEL = "claude-haiku-4-5-20251001"
# Spotting what is specific to one company decides what a saved campaign
# asks for later, so it gets the stronger model. One call per save. The
# model thinks before it answers and that counts against the limit.
_DETECT_MODEL = "claude-sonnet-5"
_DETECT_MAX_TOKENS = 4000

_TONES = [("consultative", "Consultative"), ("direct", "Direct"),
          ("casual", "Casual"), ("formal", "Formal")]
# Business days after the step before it, for a step just added.
_NEW_STEP_DELAY = {"email": 3, "call": 2, "linkedin": 2}

_DEFAULTS = {
    "step": 1,            # 1 = start, 2 = one step per screen, 3 = save
    "steps": [],
    "cur": 0,             # the step on screen at step 2
    "tone": "consultative",
    "ai_open": "",        # step id whose "Describe it, AI drafts it" box is open
    "add_open": False,    # "add a step after this one" cards showing
    "rm_ask": "",         # step id waiting on "remove it?"
    "restart_ask": False,
    "pdf_open": "",       # step id whose PDF picker is open
    "missed": [],         # what the last build could not add
    "name": "",
    "profiles_n": cc.PROFILES_DEFAULT,
    "building": False,
    "build_err": "",
    "built": {},
    "found": [],          # details AI noticed: [{"text", "name", "on"}]
    "found_key": "",
    "finding": False,
    "find_err": False,
    "vals": {},           # fill-in name -> what it says this time
    "use": {},            # a saved campaign being used again
    "edit_id": "",        # a saved campaign being changed
    "saved_note": "",
    "tried": False,       # Save was pressed with a step unfinished
}

_START_CARDS = [
    ("email", "Email",
     "inboxslide sends it for you, from your own mailbox, on the day it's due."),
    ("call", "Call",
     "A phone call you make yourself. On the day, it shows up in My Day "
     "with your talking points."),
    ("linkedin", "LinkedIn message",
     "A message you send yourself. On the day, it shows up in My Day, "
     "ready to copy."),
]
_STEP_ABOUT = {
    "email_first": ("This is the first email each contact gets. Say who you "
                    "are and why you're writing. inboxslide sends it for "
                    "you, from your own mailbox."),
    "email": ("A follow-up email. inboxslide sends it for you, and only to "
              "contacts who haven't replied yet."),
    "call": ("A phone call you make yourself. On the day, this call shows "
             "up in My Day with the notes you write here."),
    "linkedin": ("A LinkedIn message you send yourself. On the day, it "
                 "shows up in My Day with the message you write here, ready "
                 "to copy."),
}
_BODY_LABELS = {"email": "Your email",
                "call": "What you want to say on the call",
                "linkedin": "Your LinkedIn message"}
_BODY_PLACEHOLDERS = {"email": "Write this email in your own words",
                      "call": "Your talking points or voicemail script",
                      "linkedin": "Your LinkedIn message"}
_AI_ASKS = {"email": "What should this email say?",
            "call": "What do you want to cover on this call?",
            "linkedin": "What should this LinkedIn message say?"}

# Asked in plain words wherever a fill-in needs a value.
_FILLIN_ASKS = {
    "Industry": "Which industry is this campaign for?",
    "Role": "Which role are you offering to fill?",
    "RoleWork": "What work would that role take on?",
    "Location": "Where are these companies?",
    "CurrentClients": "Which current clients do you want to mention?",
    "Competitors": "Which competitors do you want to name?",
}
_FILLIN_HINTS = {
    "Industry": "e.g. freight forwarding",
    "Role": "e.g. dispatcher",
    "RoleWork": "e.g. document follow-up and record updates",
    "Location": "e.g. USA, or Dallas, TX",
    "CurrentClients": "e.g. two freight brokers in Texas",
    "Competitors": "e.g. a local staffing agency",
}

# Chips under each step put a merge field where the cursor is, in the
# subject or the body, without the box losing focus. Quasar hears the input
# event, so the value reaches the server the same way typing does.
_INSERT_JS = """
window.tmcInsert = window.tmcInsert || function(e, token) {
    e.preventDefault();
    const card = e.target.closest('.tmc-step-card');
    if (!card) return;
    let el = document.activeElement;
    const ok = el && card.contains(el) && el.closest('.tmc-fill')
        && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT');
    if (!ok) el = card.querySelector('.tmc-body textarea');
    if (!el) return;
    const at = ok ? el.selectionStart : el.value.length;
    const to = ok ? el.selectionEnd : el.value.length;
    let ins = token;
    if (!ok && el.value && !/\\s$/.test(el.value)) ins = ' ' + token;
    const proto = el.tagName === 'TEXTAREA'
        ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(
        el, el.value.slice(0, at) + ins + el.value.slice(to));
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.focus();
    el.setSelectionRange(at + ins.length, at + ins.length);
};
"""


def _ff():
    """The already-loaded flowdrip_app module (see tm_signals._ff)."""
    for name in ("flowdrip_app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_BASE_DATA_DIR") and hasattr(m, "C"):
            return m
    import flowdrip_app as m  # standalone/test fallback
    return m


def _w(s) -> dict:
    """The walkthrough's state, with every key present."""
    w = getattr(s, "tmc_state", None)
    if not isinstance(w, dict):
        w = {}
        s.tmc_state = w
    for k, v in _DEFAULTS.items():
        if k not in w:
            w[k] = copy.deepcopy(v)
    return w


def open_page(s, rf):
    """Start the walkthrough fresh. The Start a Campaign dialog and the
    Build a Campaign page's Build Your Own card both come through here."""
    ff = _ff()
    try:
        s._nav_history.append(ff._nav_snapshot(s))
    except Exception:
        pass
    ff._reset_wizard_state(s)
    s.loaded_camp = None
    s.hub = "sales"
    s.sp = PAGE_KEY
    rf()


# ── Saved campaigns ───────────────────────────────────────────────────────

def _saved_path():
    return _ff()._resolve_user_root() / SAVED_FILE


def load_saved() -> list:
    """The user's saved custom campaigns, newest first."""
    try:
        p = _saved_path()
        rows = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except Exception:
        rows = []
    rows = [r for r in rows if isinstance(r, dict) and r.get("steps")]
    return sorted(rows, key=lambda r: r.get("created_at") or "", reverse=True)


def _write_saved(rows: list) -> None:
    p = _saved_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    _ff()._atomic_write_text(p, json.dumps(rows, indent=2, default=str))


def save_style(name: str, steps: list, tone: str = "", values: dict = None,
               replace_id: str = "", profiles_n=None) -> str:
    """Save (or replace) a custom campaign with its steps and the fill-ins it
    asks for. Replaces the one being edited (`replace_id`), else one with
    the same name. Returns its id."""
    rows = load_saved()
    row = {
        "id": str(uuid.uuid4()),
        "name": name,
        "created_at": datetime.now().isoformat(),
        "tone": tone or "",
        "steps": cc.style_steps(steps),
        "profiles_n": cc.clamp_profiles(profiles_n),
    }
    for i, old in enumerate(rows):
        if (replace_id and old.get("id") == replace_id) or (
                not replace_id and (old.get("name") or "") == name):
            row["id"] = old.get("id") or row["id"]
            row["created_at"] = old.get("created_at") or row["created_at"]
            # Keep the last-used hints for fill-ins not given a value now.
            values = {**{f.get("name"): f.get("last") or ""
                         for f in old.get("fillins") or []},
                      **{k: v for k, v in (values or {}).items() if v}}
            rows[i] = row
            break
    else:
        rows.append(row)
    row["fillins"] = cc.style_fillins(row["steps"], values)
    _write_saved(rows)
    return row["id"]


def remember_values(style_id: str, values: dict) -> None:
    """After a saved campaign is used, keep what each fill-in said as the
    hint for next time."""
    if not style_id:
        return
    rows = load_saved()
    for row in rows:
        if row.get("id") == style_id:
            old = {f.get("name"): f.get("last") or ""
                   for f in row.get("fillins") or []}
            row["fillins"] = cc.style_fillins(
                row.get("steps") or [],
                {**old, **{k: v for k, v in (values or {}).items() if v}})
            _write_saved(rows)
            return


def delete_saved(style_id: str) -> None:
    _write_saved([r for r in load_saved() if r.get("id") != style_id])


# ── AI jobs ───────────────────────────────────────────────────────────────

def _ai_text(prompt: str, model: str, max_tokens: int, client=None):
    ff = _ff()
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=ff.ANTHROPIC_API_KEY)
    msg = ff._claude_create_with_retry(
        client, model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}])
    return msg, "".join(b.text for b in msg.content if hasattr(b, "text"))


def _clean(raw: str) -> str:
    ff = _ff()
    return ff._tm_aug_wording(ff._strip_dashes(ff._strip_ai_signoff(
        (raw or "").strip())))


def draft_step(steps, i, direction="", tone="", values=None,
               with_subject=False, client=None) -> str:
    """One step written by AI, from the user's direction or, with none, from
    the other steps."""
    _msg, raw = _ai_text(
        cc.draft_prompt(steps, i, direction, tone, values, with_subject),
        _DRAFT_MODEL, 900, client)
    return _clean(raw)


def polish_text(text, step_type, tone="", attach="", client=None) -> str:
    """The user's own text, lightly tidied."""
    _msg, raw = _ai_text(cc.polish_prompt(text, step_type, tone, attach),
                         _DRAFT_MODEL, 900, client)
    return _clean(raw)


def detect_fillins(steps, client=None) -> list:
    """The details in the user's steps that belong to one company or market,
    as [{"text", "name"}]. The model only points at phrases; tm_custom_
    campaign checks each one is really there and does the replacing."""
    msg, raw = _ai_text(cc.detect_prompt(steps), _DETECT_MODEL,
                        _DETECT_MAX_TOKENS, client)
    # A cut-off or empty answer is a failed scan, not "nothing found".
    if getattr(msg, "stop_reason", "") == "max_tokens" or "[" not in raw:
        raise RuntimeError("the answer was cut off")
    return cc.parse_detected(raw, steps)


# ── Building the real campaign ────────────────────────────────────────────

def _unique_camp_name(name: str) -> str:
    """Campaign files are keyed by name, so a second run of a saved campaign
    must not land on (and overwrite) the first one."""
    try:
        taken = {(c.get("name") or "").strip().lower()
                 for c in _ff().load_campaigns()}
    except Exception:
        taken = set()
    if name.lower() not in taken:
        return name
    n = 2
    while f"{name} {n}".lower() in taken:
        n += 1
    return f"{name} {n}"


def attach_extras(emails, steps, values, profiles_n, client) -> list:
    """Add what the app writes at build time: each Sales PDF on its email
    and the candidate profiles on theirs. Returns what could not be added,
    in the user's words; never raises."""
    ff = _ff()
    v = {k: str((values or {}).get(k) or "").strip()
         for k in ("Role", "Location", "Industry")}
    missed = []
    plan = cc.pdf_plan(steps)
    if plan:
        kinds = [k for _i, k in plan]
        try:
            built = ff._tm_build_campaign_pdfs(
                kinds, "", v["Role"], v["Location"] or cc.DEFAULT_LOCATION,
                v["Industry"], client=client) if client is not None else {}
        except Exception as ex:
            print(f"[tm_custom] PDFs failed: {type(ex).__name__}: {ex}", flush=True)
            built = {}
        for i, kind in plan:
            fname = built.get(kind)
            if (not fname and kind == "tm_cost_compare"
                    and "tm_how_it_works" not in kinds
                    and built.get("tm_how_it_works")):
                # No pay data for the role: the builder swaps in How We
                # Work Together so the email still carries a PDF.
                fname = built["tm_how_it_works"]
                missed.append(
                    f"{emails[i]['name']}: there was no pay data for that "
                    f"role, so How We Work Together is attached in place of "
                    f"the Staffing Cost Comparison")
            if fname:
                emails[i]["attachments"] = list(
                    emails[i].get("attachments") or []) + [fname]
            else:
                missed.append(f"{emails[i]['name']}: the "
                              f"{cc.PDF_KINDS[kind]} PDF")
    prof = cc.profile_plan(steps)
    if prof:
        try:
            rounds = [(i, ff._TM_PROFILES_LEAD if r == 0
                       else ff._TM_PROFILES_AGAIN_LEAD, None)
                      for r, i in enumerate(prof)]
            got = ff._tm_add_campaign_profiles(
                client, {"emails": emails}, cc.clamp_profiles(profiles_n),
                v["Role"], v["Industry"], rounds=rounds)
            if not got.get("profiles"):
                missed.append("the candidate profiles")
        except Exception as ex:
            print(f"[tm_custom] profiles failed: {type(ex).__name__}: {ex}",
                  flush=True)
            missed.append("the candidate profiles")
    return missed


def build_campaign(owner: str, name: str, steps: list, style_id: str = "",
                   values: dict = None, profiles_n=None, client=None) -> tuple:
    """(saved draft campaign, what could not be added) from steps that
    already have their fill-ins written in."""
    ff = _ff()
    if client is None and ff.ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.Anthropic(api_key=ff.ANTHROPIC_API_KEY)
    emails = cc.build_emails(steps)
    missed = attach_extras(emails, steps, values, profiles_n, client)
    ff._spread_email_times(emails)
    camp = dict(
        schema=2, name=_unique_camp_name(name),
        template_key=PAGE_KEY, template_name=TITLE,
        start_date=ff._add_business_days(date.today(), 1).isoformat(),
        contacts=[], contact_count=0, contact_emails=[],
        # The fill-ins are already written into the emails; keeping them
        # here too covers a token the user types back in while editing.
        emails=emails, variables=dict(values or {}),
        status="draft", responders=[],
        created_date=date.today().isoformat(),
        _owner_email=owner, tm_custom_style_id=style_id,
    )
    ff.save_campaign(camp)
    return camp, missed


def _start_build(s, rf, name, steps, style_id="", values=None):
    """Build the real campaign off the UI thread, then hand off to its own
    Choose Contacts screen."""
    ff = _ff()
    w = _w(s)
    w["building"], w["build_err"], w["built"], w["missed"] = True, "", {}, []
    rf()
    owner = getattr(s, "_user_email", "") or ""
    n = w["profiles_n"]

    def _run():
        try:
            w["built"], w["missed"] = build_campaign(
                owner, name, steps, style_id, values, n)
        except Exception as e:
            print(f"[tm_custom] build failed: {type(e).__name__}: {e}", flush=True)
            w["build_err"] = ff._friendly_ai_error(e)
        finally:
            w["building"] = False
    ff._run_as_user(owner, _run, name="tm_custom_build_worker")

    async def _poll():
        while w["building"]:
            await asyncio.sleep(1)
        camp, missed = w["built"] or {}, list(w["missed"] or [])
        if camp:
            ff._cache_campaigns.invalidate()
            ff._reset_wizard_state(s)
            s.loaded_camp = camp
            s.loaded_view = "contacts"
            s.loaded_tab = 0
            s.launch_result = None
            s.hub = "sales"
            s.sp = "start_seq"
            s._tab = "custom"
            try:
                ui.notify(f'"{camp.get("name")}" is ready. Pick who it goes to.',
                          type="positive")
                if missed:
                    ui.notify("One thing couldn't be added just now: "
                              + "; ".join(missed) + ". Everything else is "
                              "ready.", type="warning", timeout=14000)
            except Exception:
                pass
        rf()
    asyncio.ensure_future(_poll())


# ── Small pieces of the page ──────────────────────────────────────────────

def _new_step(step_type: str, delay_days: int = 2) -> dict:
    """One blank step. Working fields (ai_prompt, _drafting...) live on the
    step so a move keeps them with it."""
    return {
        "id": uuid.uuid4().hex[:12],
        "type": step_type,
        "delay_days": delay_days,
        "input": "",
        "subject": "",         # emails only
        "voice": cc.VOICE_MINE,
        "pdf": "",             # a Sales PDF kind, emails after the first
        "profiles": False,     # candidate profiles, emails after the first
        "ai_prompt": "",
        "_drafting": False,
        "_draft_error": "",
    }


def _step_by_id(w, sid):
    return next((st for st in w["steps"] or [] if st.get("id") == sid), None)


def _col(step_type: str) -> str:
    C = _ff().C
    return {"email": C["email_col"], "call": C["call_col"],
            "linkedin": C["li"]}.get(step_type, C["teal"])


def _icon(step_type: str) -> str:
    return _ff()._SB_STEP_ICONS.get(step_type, "✉")


def _ask(name: str) -> str:
    return _FILLIN_ASKS.get(name) or (
        f"What should {cc.fillin_label(name)} say this time?")


def _hint(name: str) -> str:
    return _FILLIN_HINTS.get(name, f"{cc.fillin_label(name)} for this campaign")


def _type_card(step_type, title, desc, on_click):
    """One "pick a kind of step" card: its icon, its name and what it does."""
    C = _ff().C
    with ui.element("button").props(f'data-tmc-type="{step_type}"').style(
            f"background:{C['surface']};border:1px solid {C['border']};"
            f"border-radius:10px;padding:14px 16px;text-align:left;"
            f"cursor:pointer;font-family:inherit;display:flex;"
            f"flex-direction:column;gap:8px;").on("click", on_click):
        with ui.element("div").style(
                "display:flex;align-items:center;gap:8px;pointer-events:none;"):
            ui.label(_icon(step_type)).style(
                f"width:26px;height:26px;border-radius:7px;display:flex;"
                f"align-items:center;justify-content:center;font-size:13px;"
                f"font-weight:800;color:#fff;background:{_col(step_type)};")
            ui.label(title).style(
                f"font-size:13px;font-weight:700;color:{C['text_l']};")
        ui.label(desc).style(
            f"font-size:11px;color:{C['muted']};line-height:1.5;"
            f"pointer-events:none;")


def _type_cards(on_pick, plus: bool = False):
    """The three kinds of step, side by side."""
    with ui.element("div").style(
            "display:grid;grid-template-columns:repeat(auto-fit,"
            "minmax(200px,1fr));gap:12px;"):
        for t, title, desc in _START_CARDS:
            _type_card(t, ("＋ " if plus else "") + title, desc,
                       lambda t=t: on_pick(t))


def _round_btn(sym, on_click, off=False, size=26):
    C = _ff().C
    with ui.element("button").style(
            f"width:{size}px;height:{size}px;border-radius:99px;"
            f"border:1px solid {C['border']};background:{C['card']};"
            f"color:{C['text_l']};font-size:{size // 2 + 2}px;font-weight:700;"
            f"font-family:inherit;cursor:pointer;display:flex;"
            f"align-items:center;justify-content:center;flex-shrink:0;"
            f"{'opacity:0.35;pointer-events:none;' if off else ''}"
            ).on("click", on_click):
        ui.label(sym).style("pointer-events:none;line-height:1;")


def _pill(label, selected, on_click, size=11):
    C = _ff().C
    with ui.element("button").style(
            f"padding:5px 12px;font-size:{size}px;border-radius:99px;"
            f"cursor:pointer;font-family:inherit;font-weight:600;"
            f"background:{C['teal'] if selected else C['bg']};"
            f"color:{C['on_teal'] if selected else C['text']};"
            f"border:1px solid {C['teal'] if selected else C['border']};"
            ).on("click", on_click):
        ui.label(label).style("pointer-events:none;")


def _section(title, about=""):
    """A labelled part of a step page, with one line saying what it is."""
    C = _ff().C
    ui.label(title).style(
        f"font-size:13px;font-weight:700;color:{C['text_l']};margin:18px 0 2px;")
    if about:
        ui.label(about).style(
            f"font-size:11px;color:{C['muted']};margin-bottom:8px;"
            f"line-height:1.5;")


def _quiet_link(label, on_click):
    C = _ff().C
    with ui.element("button").style(
            f"background:transparent;border:none;color:{C['muted']};"
            f"font-size:11px;font-family:inherit;cursor:pointer;"
            f"text-decoration:underline;padding:2px 0;").on("click", on_click):
        ui.label(label).style("pointer-events:none;")


def _field_label(text):
    C = _ff().C
    ui.label(text).style(
        f"font-size:12px;font-weight:600;color:{C['text_l']};margin:10px 0 4px;")


def _card_title(text, size=14):
    C = _ff().C
    ui.label(text).style(
        f"font-size:{size}px;font-weight:700;color:{C['text_l']};"
        f"font-family:'Nunito',sans-serif;margin-bottom:4px;")


def _note(text, margin="margin-bottom:12px;"):
    C = _ff().C
    ui.label(text).style(
        f"font-size:11px;color:{C['muted']};line-height:1.5;{margin}")


def _big_button(label, on_click, primary=True, off=False, el_id=""):
    C = _ff().C
    b = ui.element("button").classes("fd-pb" if primary else "fd-gb")
    if el_id:
        b.props(f'id="{el_id}"')
    with b.style(
            ("padding:14px 28px;font-size:15px;" if primary else
             f"padding:10px 28px;font-size:13px;font-weight:600;"
             f"color:{C['text_l']};margin-top:8px;")
            + "width:100%;justify-content:center;display:flex;"
            "border-radius:10px;"
            + ("opacity:0.5;pointer-events:none;" if off else "")
            ).on("click", on_click):
        ui.label(label).style("pointer-events:none;")


def _problem_text(steps, i, values) -> str:
    """Plain words for what step i still needs, or ''."""
    p = cc.step_problem(steps, i, values)
    if not p:
        return ""
    name = cc.step_names(steps)[i]
    if p == "body":
        return f"{name} hasn't been written yet."
    if p == "subject":
        return f"{name} needs a subject line."
    return (f"{name} needs one more detail: "
            f"{cc.fillin_label(p[1]).lower()}. Add it on that step.")


def _fix_delays(w) -> None:
    """After a move, an add or a remove: only the first step is Day 0, and
    only an email after the first keeps a PDF or the profiles."""
    for j, x in enumerate(w["steps"] or []):
        if j > 0 and int(x.get("delay_days", 0) or 0) < 1:
            x["delay_days"] = _NEW_STEP_DELAY.get(x.get("type"), 2)
        if x.get("type") != "email" or cc.is_first_email(w["steps"], j):
            x["pdf"], x["profiles"] = "", False


def _goto(s, rf, i: int) -> None:
    """Show step i from the top of the page, with every side panel shut."""
    w = _w(s)
    w["cur"] = max(0, min(len(w["steps"] or []) - 1, i))
    w["step"] = 2
    w["ai_open"], w["add_open"], w["rm_ask"], w["pdf_open"] = "", False, "", ""
    for x in w["steps"] or []:
        x["_full_ask"] = False
    _ff()._scroll_content_top()
    rf()


def _ai_into_step(s, rf, sid, work, name) -> None:
    """Run one AI job for a step off the UI thread and put its text in that
    step's box, where the user can change it. `work(step)` returns the text;
    an error lands on the step, never over what they wrote."""
    ff = _ff()
    step = _step_by_id(_w(s), sid)
    if step is None or step.get("_drafting"):
        return
    step["_drafting"] = True
    step["_draft_error"] = ""
    rf()

    def _run():
        try:
            text = (work(step) or "").strip()
            if text:
                step["input"] = text
        except Exception as ex:
            step["_draft_error"] = ff._friendly_ai_error(ex)
        finally:
            step["_drafting"] = False
    ff._run_as_user(getattr(s, "_user_email", "") or "", _run, name=name)

    async def _poll():
        while step.get("_drafting"):
            await asyncio.sleep(1)
        rf()
    asyncio.ensure_future(_poll())


# ── The page ──────────────────────────────────────────────────────────────

def render_page(s, rf):
    """Step 1 is the start screen (what the first step should be, plus the
    saved campaigns to reuse); 2 shows one step per screen; 3 names and
    saves it and builds the real draft campaign. A saved campaign being
    used again has its own short screen."""
    ff = _ff()
    C = ff.C
    w = _w(s)
    if not isinstance(w["steps"], list):
        w["steps"] = []
    if w["step"] >= 2 and not w["steps"]:
        w["step"] = 1
    on_step = w["step"] == 2 and not w["use"]
    prev = (cc.step_names(w["steps"])[w["cur"] - 1]
            if on_step and 0 < w["cur"] < len(w["steps"]) else "")

    # Header + back. Back goes one screen back: the step before, then the
    # start screen, then out to Build a Campaign.
    with ui.element("div").style(
            "display:flex;align-items:flex-start;justify-content:space-between;"
            "gap:12px;margin-bottom:14px;max-width:920px;"):
        with ui.element("div"):
            ui.label(TITLE).classes("fd-h1")
            ui.label(
                "Build it one step at a time, save it, and reuse it for any "
                "company. AI helps only where you ask it to."
            ).classes("fd-sub")

        def _back():
            if w["building"]:
                return
            if w["use"]:
                ff._reset_wizard_state(s)
            elif w["step"] >= 3:
                w["step"] = 2
            elif w["step"] == 2:
                if w["cur"] > 0:
                    _goto(s, rf, w["cur"] - 1)
                    return
                w["step"] = 1
            else:
                s.sp = "start_seq"
                s._tab = ""
            rf()
        with ui.element("button").classes("fd-gb").style(
                "padding:6px 14px;font-size:11px;white-space:nowrap;"
                ).on("click", _back):
            ui.label("← Back to Build a Campaign"
                     if w["step"] <= 1 and not w["use"]
                     else (f"← Back to {prev}" if prev else "← Back"))

    if w["use"]:
        with ui.element("div").style("max-width:920px;"):
            _render_use(s, rf)
        return

    # Progress strip. 3 and 4 happen on the campaign's own Choose Contacts /
    # Preview Campaign screens once it is saved and built.
    at = 1 if w["step"] <= 2 else 2
    with ui.element("div").style(
            "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:18px;"
            "max-width:920px;"):
        for i, lbl in enumerate(["1. Write your steps", "2. Save this campaign",
                                 "3. Choose contacts", "4. Preview & launch"], 1):
            active, done = i == at, i < at
            ui.label(lbl).style(
                f"font-size:11px;font-weight:700;padding:4px 10px;"
                f"border-radius:99px;"
                f"background:{C['teal'] if active else C['surface']};"
                f"color:{C['on_teal'] if active else (C['teal'] if done else C['muted'])};"
                f"border:1px solid {C['teal'] if (active or done) else C['border']};")

    with ui.element("div").style("max-width:920px;"):
        if w["step"] <= 1:
            _render_start(s, rf)
        elif w["step"] == 2:
            _render_step(s, rf)
        else:
            _render_save(s, rf)


def _render_start(s, rf):
    """The first screen: what a campaign is, and one question, what the
    first step should be. Saved campaigns to reuse sit underneath."""
    ff = _ff()
    C = ff.C
    w = _w(s)
    steps = w["steps"] or []
    if w["saved_note"]:
        ui.label(f"✓ {w['saved_note']}").style(
            f"font-size:12px;font-weight:600;color:{C['good']};margin-bottom:10px;")

    with ui.element("div").classes("fd-gc").style("margin-bottom:18px;"):
        _card_title("Start your campaign", 16)
        ui.label(
            "A campaign is a short series of steps that go to each contact "
            "you choose: emails, phone calls and LinkedIn messages, a few "
            "days apart. You build it one step at a time. On any email "
            "after the first you can add candidate profiles from our "
            "pipeline or one of the Sales PDFs. Nothing goes out until "
            "you've picked who gets it and looked over every step."
        ).style(f"font-size:12px;color:{C['text']};margin-bottom:16px;"
                f"line-height:1.6;")

        if steps:
            ui.label("You've already started this one").style(
                f"font-size:13px;font-weight:700;color:{C['text_l']};"
                f"margin-bottom:4px;")
            ui.label("  →  ".join(cc.step_names(steps))).style(
                f"font-size:12px;color:{C['text']};margin-bottom:12px;")
            with ui.element("div").style(
                    "display:flex;gap:10px;align-items:center;flex-wrap:wrap;"):
                if w["restart_ask"]:
                    ui.label("Clear these steps and start again?").style(
                        f"font-size:12px;color:{C['text']};")

                    def _restart():
                        ff._reset_wizard_state(s)
                        rf()

                    def _keep():
                        w["restart_ask"] = False
                        rf()
                    with ui.element("button").classes("fd-gb").style(
                            "padding:6px 14px;font-size:12px;").on("click", _restart):
                        ui.label("Yes, start over").style("pointer-events:none;")
                    with ui.element("button").classes("fd-pb").style(
                            "padding:6px 14px;font-size:12px;").on("click", _keep):
                        ui.label("Keep them").style("pointer-events:none;")
                else:
                    with ui.element("button").classes("fd-pb").style(
                            "padding:8px 18px;font-size:13px;"
                            ).on("click", lambda: _goto(s, rf, w["cur"])):
                        ui.label("Keep going →").style("pointer-events:none;")

                    def _ask_restart():
                        w["restart_ask"] = True
                        rf()
                    with ui.element("button").classes("fd-gb").style(
                            "padding:8px 14px;font-size:12px;"
                            ).on("click", _ask_restart):
                        ui.label("Start over").style("pointer-events:none;")
        else:
            ui.label("What should the first step be?").style(
                f"font-size:13px;font-weight:700;color:{C['text_l']};"
                f"margin-bottom:4px;")
            _note("Pick one. Most people start with an email. You add the "
                  "next steps one at a time after this.")

            def _first(t):
                w["steps"] = [_new_step(t, 0)]
                w["saved_note"] = ""
                _goto(s, rf, 0)
            _type_cards(_first)

    _render_saved(s, rf)


def _render_profiles(s, rf, st):
    """Candidate profiles on this email: on or off, and how many the
    campaign shows."""
    ff = _ff()
    C = ff.C
    w = _w(s)
    on = bool(st.get("profiles"))

    def _toggle():
        st["profiles"] = not on
        rf()
    with ui.element("div").props('id="tmc-profiles"').style(
            f"display:flex;align-items:center;gap:10px;flex-wrap:wrap;"
            f"cursor:pointer;background:{C['surface']};border:1px solid "
            f"{C['teal'] if on else C['border']};border-radius:8px;"
            f"padding:8px 12px;").on("click", _toggle):
        ui.label("✓" if on else "").style(
            f"width:18px;height:18px;border-radius:5px;display:flex;"
            f"align-items:center;justify-content:center;font-size:12px;"
            f"font-weight:800;color:{C['on_teal']};"
            f"background:{C['teal'] if on else 'transparent'};"
            f"border:1px solid {C['teal'] if on else C['border']};")
        ui.label("Include candidate profiles in this email").style(
            f"font-size:12px;font-weight:600;color:{C['text_l']};")
    if not on:
        return
    _note("They're written when you save the campaign and set into this "
          "email just before your closing line. Each one shows a title, "
          "years of experience, an estimated hourly rate and a few "
          "highlights, as Candidate A, B, C. No names.",
          "margin:8px 0 6px;")
    with ui.element("div").style(
            "display:flex;gap:8px;align-items:center;flex-wrap:wrap;"):
        ui.label("How many:").style(f"font-size:11px;color:{C['muted']};")
        for n in range(cc.PROFILES_MIN, cc.PROFILES_MAX + 1):
            def _pick(n=n):
                w["profiles_n"] = n
                rf()
            _pill(str(n), cc.clamp_profiles(w["profiles_n"]) == n, _pick)
        ui.label("The same profiles show in every email you add them to."
                 ).style(f"font-size:11px;color:{C['muted']};")


def _render_pdf(s, rf, st):
    """One Sales PDF for this email: a button to pick one, then what it is.
    Never offered on the first email, and each PDF goes out once."""
    ff = _ff()
    C = ff.C
    w = _w(s)
    sid = st["id"]
    kind = st.get("pdf") if st.get("pdf") in cc.PDF_KINDS else ""
    picking = w["pdf_open"] == sid
    names = cc.step_names(w["steps"])
    used = {x.get("pdf"): names[j] for j, x in enumerate(w["steps"])
            if x.get("id") != sid and x.get("pdf") in cc.PDF_KINDS}
    blurbs = getattr(ff, "_TM_CAMPAIGN_PDF_BLURBS", {})

    def _open():
        w["pdf_open"] = "" if picking else sid
        rf()

    if picking:
        _note("Pick one. Each PDF goes out once in a campaign.",
              "margin-bottom:8px;")
        with ui.element("div").props('id="tmc-pdf-picker"').style(
                "display:grid;grid-template-columns:repeat(auto-fit,"
                "minmax(190px,1fr));gap:10px;margin-bottom:8px;"):
            for k, label in cc.PDF_KINDS.items():
                taken = used.get(k, "")

                def _pick(k=k):
                    st["pdf"] = k
                    w["pdf_open"] = ""
                    if not (w["vals"].get("Location") or "").strip():
                        w["vals"]["Location"] = cc.DEFAULT_LOCATION
                    rf()
                with ui.element("button").props(f'data-tmc-pdf="{k}"').style(
                        f"background:{C['surface']};border:1px solid "
                        f"{C['teal'] if k == kind else C['border']};"
                        f"border-radius:10px;padding:12px 14px;"
                        f"text-align:left;font-family:inherit;display:flex;"
                        f"flex-direction:column;gap:6px;"
                        + ("opacity:0.45;pointer-events:none;" if taken
                           else "cursor:pointer;")).on("click", _pick):
                    ui.label(label).style(
                        f"font-size:12px;font-weight:700;color:{C['text_l']};"
                        f"pointer-events:none;")
                    ui.label(f"Already on {taken}." if taken
                             else blurbs.get(k, "")).style(
                        f"font-size:11px;color:{C['muted']};line-height:1.5;"
                        f"pointer-events:none;")
        _quiet_link("Never mind", _open)
        return

    if not kind:
        _note("Send a short branded PDF with this email, written for the "
              "role and industry you name: a cost comparison, a role "
              "blueprint, how we work together and five more.",
              "margin-bottom:8px;")
        with ui.element("button").classes("fd-gb").props(
                'id="tmc-pdf-add"').style(
                f"padding:8px 16px;font-size:12px;font-weight:600;"
                f"color:{C['text_l']};").on("click", _open):
            ui.label("＋ Attach a Sales PDF").style("pointer-events:none;")
        return

    title = cc.PDF_KINDS[kind]
    with ui.element("div").style(
            f"background:{C['surface']};border:1px solid {C['teal']};"
            f"border-radius:8px;padding:8px 12px;margin-bottom:8px;"
            f"display:flex;gap:10px;align-items:center;flex-wrap:wrap;"):
        with ui.element("div").style("flex:1;min-width:180px;"):
            ui.label(f"📎 {title}").style(
                f"font-size:12px;font-weight:700;color:{C['text_l']};")
            ui.label(blurbs.get(kind, "")).style(
                f"font-size:11px;color:{C['muted']};line-height:1.5;")
        with ui.element("button").classes("fd-gb").style(
                "padding:3px 10px;font-size:11px;").on("click", _open):
            ui.label("Change").style("pointer-events:none;")

        def _drop():
            st["pdf"] = ""
            rf()
        with ui.element("button").classes("fd-gb").style(
                "padding:3px 10px;font-size:11px;").on("click", _drop):
            ui.label("Remove").style("pointer-events:none;")
    _note("inboxslide writes this PDF when you save the campaign, for the "
          "role, place and industry you give below. Tip: mention it in "
          f"your email so they know to open it, for example: I attached "
          f"the {title} for your review.", "margin-bottom:0;")


def _render_step(s, rf):
    """One step on the screen at a time: what it is, when it goes out, the
    words, and the three ways AI can help. Everything typed is kept as it is
    typed, so moving between steps never loses it."""
    ff = _ff()
    C = ff.C
    w = _w(s)
    steps = w["steps"] or []
    w["cur"] = max(0, min(len(steps) - 1, int(w["cur"] or 0)))
    _fix_delays(w)
    i = w["cur"]
    st = steps[i]
    sid = st["id"]
    stype = st.get("type", "email")
    names = cc.step_names(steps)
    name = names[i]
    last = i == len(steps) - 1
    full = len(steps) >= cc.MAX_STEPS
    busy = bool(st.get("_drafting"))
    first_email = cc.is_first_email(steps, i)
    delay = int(st.get("delay_days", 0) or 0)
    ui.run_javascript(_INSERT_JS)

    # Where you are: every step so far, in order. Click one to open it.
    with ui.element("div").props('id="tmc-trail"').style(
            "display:flex;align-items:center;gap:6px;flex-wrap:wrap;"
            "margin-bottom:12px;"):
        for j, nm in enumerate(names):
            cur = j == i
            todo = (not cur) and bool(cc.step_problem(steps, j, w["vals"]))
            with ui.element("button").style(
                    f"padding:4px 11px;font-size:11px;font-weight:700;"
                    f"border-radius:99px;cursor:pointer;font-family:inherit;"
                    f"background:{C['teal'] if cur else C['surface']};"
                    f"color:{C['on_teal'] if cur else C['text']};"
                    f"border:1px solid "
                    f"{C['teal'] if cur else (C['warn'] if todo else C['border'])};"
                    ).on("click", lambda j=j: _goto(s, rf, j)):
                ui.label(nm + (" · not finished" if todo else "")).style(
                    "pointer-events:none;")
            if j < len(names) - 1:
                ui.label("→").style(f"font-size:11px;color:{C['muted']};")

    shown = {"names": None}

    def _set(key, value):
        cur_st = _step_by_id(w, sid)
        if cur_st is None:
            return
        cur_st[key] = value or ""
        # A fill-in just typed in or taken out: ask for it (or stop asking)
        # without redrawing the box being typed in.
        idx = next(k for k, x in enumerate(w["steps"]) if x["id"] == sid)
        if cc.step_fillins(w["steps"], idx) != shown["names"]:
            _draw_fills()

    with ui.element("div").classes("fd-gc tmc-step-card").style(
            "margin-bottom:18px;"):
        with ui.element("div").style(
                "display:flex;align-items:center;gap:10px;margin-bottom:6px;"):
            ui.label(_icon(stype)).style(
                f"width:28px;height:28px;border-radius:8px;display:flex;"
                f"align-items:center;justify-content:center;font-size:13px;"
                f"font-weight:800;color:#fff;background:{_col(stype)};")
            ui.label(name).style(
                f"font-size:16px;font-weight:700;color:{C['text_l']};"
                f"font-family:'Nunito',sans-serif;flex:1;")
            ui.label(f"Step {i + 1} of {len(steps)}").style(
                f"font-size:11px;color:{C['muted']};")
        ui.label(_STEP_ABOUT["email_first" if first_email else stype]).style(
            f"font-size:12px;color:{C['text']};line-height:1.6;")
        problem = _problem_text(steps, i, w["vals"]) if w["tried"] else ""
        if problem:
            ui.label(problem).style(
                f"font-size:12px;font-weight:600;color:{C['warn']};margin-top:8px;")

        # ── When it goes out ──
        _section("When it goes out")
        if i == 0:
            ui.label("On the day your campaign starts.").style(
                f"font-size:12px;color:{C['text']};")
        else:
            def _bump_day(d):
                st["delay_days"] = max(1, min(30, int(
                    st.get("delay_days", 0) or 0) + d))
                rf()
            with ui.element("div").style(
                    "display:flex;align-items:center;gap:8px;flex-wrap:wrap;"
                    "margin-top:4px;"):
                _round_btn("−", lambda: _bump_day(-1), off=delay <= 1)
                ui.label(str(delay)).style(
                    f"font-size:15px;font-weight:800;color:{C['text_l']};"
                    f"min-width:20px;text-align:center;")
                _round_btn("+", lambda: _bump_day(1), off=delay >= 30)
                ui.label(
                    f"business day{'s' if delay != 1 else ''} after "
                    f"{names[i - 1]}. Weekends are skipped."
                ).style(f"font-size:12px;color:{C['text']};")

        # ── Candidate profiles and a PDF, on any email after the first ──
        if stype == "email":
            _section("Show candidate profiles? (optional)",
                     "" if first_email else
                     "Typical candidate profiles from our pipeline for the "
                     "role you're offering, so the reader can picture who "
                     "they'd interview.")
            if first_email:
                _note("Your first email goes out on its own. You can add "
                      "candidate profiles and a PDF to any email after "
                      "this one.", "")
            else:
                _render_profiles(s, rf, st)
                _section("Attach a Sales PDF? (optional)")
                _render_pdf(s, rf, st)

        # ── The words ──
        if stype == "email":
            _section(
                "Subject line",
                "What they see in their inbox before they open it."
                if first_email else
                "Leave this empty to send it as a reply to your first "
                "email. Type one to start a new conversation.")
            ui.input(
                value=st.get("subject", ""),
                placeholder=("e.g. More room for the work that matters"
                             if first_email else
                             "Leave empty to reply to your first email"),
                on_change=lambda e: _set("subject", e.value),
            ).props("dense borderless").classes("fd-input tmc-fill")

        _section(_BODY_LABELS.get(stype, "Your message"),
                 "Type it yourself, or let AI help with one of the three "
                 "buttons underneath.")
        ui.textarea(
            value=st.get("input", ""),
            placeholder=_BODY_PLACEHOLDERS.get(stype, "Your message"),
            on_change=lambda e: _set("input", e.value),
        ).props('dense borderless autogrow '
                'input-style="min-height:120px;line-height:1.55"'
                ).classes("fd-input tmc-body tmc-fill")

        # ── The three ways AI helps ──
        full_ask = bool(st.get("_full_ask"))

        def _idx():
            return next(k for k, x in enumerate(w["steps"]) if x["id"] == sid)

        def _open_ai():
            st["_full_ask"] = False
            w["ai_open"] = "" if w["ai_open"] == sid else sid
            rf()

        def _full_draft():
            # One click writes the whole step; a second one is asked for
            # before it goes over something already written.
            if (st.get("input") or "").strip() and not st.get("_full_ask"):
                st["_full_ask"] = True
                w["ai_open"] = ""
                rf()
                return

            def _work(step):
                k = _idx()
                want_subject = (cc.is_first_email(w["steps"], k)
                                and not (step.get("subject") or "").strip())
                out = draft_step(w["steps"], k, "", w["tone"], w["vals"],
                                 with_subject=want_subject)
                subject, body = cc.split_subject(out)
                if subject and body and want_subject:
                    step["subject"] = subject
                return body or out
            st["_full_ask"] = False
            st["_job"] = "draft"
            w["ai_open"] = ""
            _ai_into_step(s, rf, sid, _work, "tmc_full_draft_worker")

        def _polish():
            st["_full_ask"] = False
            if not (st.get("input") or "").strip():
                ui.notify("Write a few words first, then AI can polish "
                          "them.", type="info")
                return

            def _work(step):
                was = step.get("input") or ""
                out = polish_text(
                    was, step.get("type", "email"), w["tone"],
                    attach=cc.PDF_KINDS.get(step.get("pdf") or "", ""))
                # Never trade a merge field or fill-in for nicer wording.
                lost = [t for t in set(cc._TOKEN_RE.findall(was))
                        if "{" + t + "}" not in out]
                return was if lost else out
            st["_job"] = "polish"
            w["ai_open"] = ""
            _ai_into_step(s, rf, sid, _work, "tmc_polish_worker")

        def _draft():
            if not (st.get("ai_prompt") or "").strip():
                ui.notify("Type a sentence about what you want it to say "
                          "first.", type="info")
                return

            def _work(step):
                return draft_step(w["steps"], _idx(), step.get("ai_prompt", ""),
                                  w["tone"], w["vals"])
            st["_job"] = "draft"
            w["ai_open"] = ""
            _ai_into_step(s, rf, sid, _work, "tmc_draft_worker")

        if busy:
            with ui.element("div").style(
                    "display:flex;align-items:center;gap:8px;margin-top:10px;"):
                ui.spinner("dots", size="20px", color=C["teal"])
                ui.label("Writing it for you…" if st.get("_job") == "draft"
                         else "Polishing your wording…").style(
                    f"font-size:12px;color:{C['teal']};")
        else:
            with ui.element("div").props('id="tmc-ai-btns"').style(
                    "display:grid;grid-template-columns:repeat(auto-fit,"
                    "minmax(240px,1fr));gap:12px;margin-top:10px;"):
                for blabel, babout, bfn, bon in (
                        ("✦ Yes, replace what I wrote" if full_ask
                         else "✦ Full AI draft",
                         "This replaces what you wrote in the box above. "
                         "Click again to go ahead." if full_ask else
                         "One click and AI writes the whole thing. You can "
                         "change every word after.",
                         _full_draft, full_ask),
                        ("✦ Describe it, AI drafts it",
                         "Say what it should cover in a sentence or two. You "
                         "can change every word after.",
                         _open_ai, w["ai_open"] == sid),
                        ("✦ Polish with AI",
                         "Already wrote it? AI tidies your wording and "
                         "keeps your meaning.",
                         _polish, False)):
                    with ui.element("div"):
                        with ui.element("button").classes("fd-gb").style(
                                f"padding:8px 14px;font-size:12px;width:100%;"
                                f"font-weight:600;color:{C['text_l']};"
                                f"display:flex;justify-content:center;"
                                f"{'border-color:' + C['teal'] + ';' if bon else ''}"
                                ).on("click", bfn):
                            ui.label(blabel).style("pointer-events:none;")
                        ui.label(babout).style(
                            f"font-size:11px;color:{C['muted']};"
                            f"margin-top:4px;line-height:1.5;")
        if st.get("_draft_error"):
            ui.label(f"⚠ {st['_draft_error']}").style(
                f"font-size:11px;color:{C['danger']};margin-top:6px;")

        if w["ai_open"] == sid and not busy:
            has_text = bool((st.get("input") or "").strip())
            with ui.element("div").props('id="tmc-ai-box"').style(
                    f"background:{C['bg']};border:1px solid "
                    f"{ff._tint(C['teal'], '60')};border-radius:10px;"
                    f"padding:12px 14px;margin-top:10px;"):
                ui.label(_AI_ASKS.get(stype, "What should it say?")).style(
                    f"font-size:12px;font-weight:700;color:{C['text_l']};")
                _note("A sentence or two is plenty. AI writes the full "
                      "message and puts it in the box above, where you can "
                      "change anything.", "margin:2px 0 8px;")
                ui.textarea(
                    value=st.get("ai_prompt", ""),
                    placeholder=cc.AI_HINTS.get(cc.slot_of(steps, i), ""),
                    on_change=lambda e: _set("ai_prompt", e.value),
                ).props('dense borderless autogrow '
                        'input-style="min-height:56px;line-height:1.5"'
                        ).classes("fd-input")
                ui.label("How should it sound?").style(
                    f"font-size:11px;font-weight:600;color:{C['text']};"
                    f"margin:10px 0 6px;")
                with ui.element("div").style(
                        "display:flex;gap:8px;flex-wrap:wrap;"):
                    for tk, tl in _TONES:
                        def _pick_tone(k=tk):
                            w["tone"] = k
                            rf()
                        _pill(tl, w["tone"] == tk, _pick_tone)
                with ui.element("div").style(
                        "display:flex;gap:10px;align-items:center;"
                        "flex-wrap:wrap;margin-top:12px;"):
                    with ui.element("button").classes("fd-pb").style(
                            "padding:8px 18px;font-size:12px;").on("click", _draft):
                        ui.label("Write it again" if has_text
                                 else "Write it for me").style(
                            "pointer-events:none;")
                    with ui.element("button").classes("fd-gb").style(
                            "padding:8px 14px;font-size:12px;").on("click", _open_ai):
                        ui.label("Never mind").style("pointer-events:none;")
                    if has_text:
                        ui.label("This replaces what you wrote in the box "
                                 "above.").style(
                            f"font-size:11px;color:{C['muted']};")

        # ── Details filled in per contact ──
        _section(
            "Add a detail",
            "Click in your message where it should go, then click one. It "
            "shows in curly brackets, like {Company}, and the real thing "
            "is written in when it goes out.")
        with ui.element("div").style(
                "display:flex;gap:6px;align-items:center;flex-wrap:wrap;"
                "margin-bottom:6px;"):
            ui.label("From each contact, filled in for you:").style(
                f"font-size:11px;color:{C['muted']};margin-right:2px;")
            for tok, clabel in (("FirstName", "First name"),
                                ("Company", "Company"),
                                ("JobTitle", "Job title")):
                with ui.element("button").props(
                        f'title="Adds {{{tok}}}"').style(
                        f"padding:3px 9px;font-size:11px;border-radius:99px;"
                        f"cursor:pointer;font-family:inherit;font-weight:600;"
                        f"background:transparent;color:{C['text']};"
                        f"border:1px solid {C['muted']};"
                        ).on("mousedown", js_handler=(
                            f"(e) => window.tmcInsert(e, '{{{tok}}}')")):
                    ui.label(clabel).style("pointer-events:none;")
        _note("The industry, the role, a location and the like: just type "
              "them into your message. When you save, AI points them out "
              "so you can change them the next time you use this campaign.",
              "")

        # Asked the moment this step needs a detail: a PDF or the candidate
        # profiles (role, place, industry), or a {Detail} typed in by hand.
        fill_box = ui.element("div").props('id="tmc-fill-box"')

        def _draw_fills():
            idx = _idx()
            asks = cc.step_fillins(w["steps"], idx)
            shown["names"] = asks
            fill_box.clear()
            if not asks:
                return
            with fill_box:
                with ui.element("div").style(
                        f"background:{C['bg']};border:1px solid "
                        f"{ff._tint(C['teal'], '60')};border-radius:10px;"
                        f"padding:12px 14px;margin-top:12px;"):
                    ui.label("Fill this in for this campaign").style(
                        f"font-size:12px;font-weight:700;color:{C['text_l']};")
                    _note("This step uses details that change from one "
                          "campaign to the next. Say what they are this "
                          "time. You'll be asked again each time you reuse "
                          "this campaign.", "margin-top:2px;")
                    for n in asks:
                        _field_label(_ask(n))
                        ui.input(
                            value=w["vals"].get(n, ""), placeholder=_hint(n),
                            on_change=lambda e, n=n: w["vals"].__setitem__(
                                n, (e.value or "").strip()),
                        ).props("dense borderless").classes("fd-input")
        _draw_fills()

    # ── See it the way they will, before moving on ──
    def _preview():
        em = cc.build_emails(cc.fill(w["steps"], w["vals"]))[i]
        ff._show_step_preview_dialog(
            s, dict(em, script_notes=(w["steps"][i].get("input") or ""),
                    attachments=[]), i)

    _big_button({"email": "Preview this email", "call": "Preview this call",
                 "linkedin": "Preview this LinkedIn message"}.get(
                     stype, "Preview this step"),
                _preview, primary=False, el_id="tmc-preview")
    if st.get("pdf") or st.get("profiles"):
        _note("The preview shows your words. "
              + ("The candidate profiles and the PDF are"
                 if st.get("pdf") and st.get("profiles") else
                 "The PDF is" if st.get("pdf") else
                 "The candidate profiles are")
              + " added when you save, and you see the finished email in "
              "Preview Campaign before anything goes out.",
              "margin:6px 0 10px;text-align:center;")
    else:
        ui.element("div").style("height:10px;")

    # ── What comes next ──
    def _add_after(t):
        if len(w["steps"] or []) >= cc.MAX_STEPS:
            return
        w["steps"].insert(i + 1, _new_step(t, _NEW_STEP_DELAY.get(t, 2)))
        _goto(s, rf, i + 1)

    def _finish():
        for j in range(len(w["steps"] or [])):
            msg = _problem_text(w["steps"], j, w["vals"])
            if msg:
                w["tried"] = True
                ui.notify(msg, type="warning")
                _goto(s, rf, j)
                return
        w["tried"] = False
        w["build_err"] = ""
        w["step"] = 3
        _start_detect(s, rf)
        ff._scroll_content_top()
        rf()

    if last:
        with ui.element("div").classes("fd-gc").style("margin-bottom:14px;"):
            _card_title("What comes next?")
            _note(f"That's {cc.MAX_STEPS} steps, the most one campaign can "
                  f"hold." if full else
                  f"Add the step that follows {name}, or stop here if this "
                  f"is everything.")
            if not full:
                _type_cards(_add_after, plus=True)
        _big_button("That's everything. Save this campaign →", _finish,
                    el_id="tmc-finish")
    else:
        _big_button(f"Next: {names[i + 1]} →",
                    lambda: _goto(s, rf, i + 1), el_id="tmc-next")
        if w["add_open"] and not full:
            with ui.element("div").classes("fd-gc").style("margin-top:12px;"):
                ui.label(f"Add a step right after {name}").style(
                    f"font-size:13px;font-weight:700;color:{C['text_l']};"
                    f"margin-bottom:10px;")
                _type_cards(_add_after, plus=True)

    # Quiet housekeeping for this step.
    def _move(d):
        b = i + d
        if 0 <= b < len(w["steps"]):
            w["steps"][i], w["steps"][b] = w["steps"][b], w["steps"][i]
            w["cur"] = b
        rf()

    def _remove():
        if (st.get("input") or "").strip() and w["rm_ask"] != sid:
            w["rm_ask"] = sid
            rf()
            return
        w["steps"] = [x for x in w["steps"] if x.get("id") != sid]
        _goto(s, rf, min(i, len(w["steps"]) - 1))

    with ui.element("div").style(
            "display:flex;gap:16px;align-items:center;flex-wrap:wrap;"
            "justify-content:center;margin-top:14px;"):
        if w["rm_ask"] == sid:
            ui.label(f"Remove {name} and what you wrote in it?").style(
                f"font-size:12px;color:{C['text']};")
            _quiet_link("Yes, remove it", _remove)

            def _keep():
                w["rm_ask"] = ""
                rf()
            _quiet_link("Keep it", _keep)
        else:
            if not last and not full and not w["add_open"]:
                def _open_add():
                    w["add_open"] = True
                    rf()
                _quiet_link("＋ Add a step after this one", _open_add)
            if i > 0:
                _quiet_link("Move this step earlier", lambda: _move(-1))
            if not last:
                _quiet_link("Move this step later", lambda: _move(1))
            if len(steps) > 1:
                _quiet_link("Remove this step", _remove)


# ── Save ──────────────────────────────────────────────────────────────────

def _steps_key(steps) -> str:
    return hashlib.sha1(json.dumps(
        [[st.get("subject") or "", st.get("input") or ""] for st in steps or []]
    ).encode("utf-8")).hexdigest()


def _start_detect(s, rf) -> None:
    """Look for company-specific details once per version of the steps, so
    stepping back and forward keeps the user's choices."""
    ff = _ff()
    w = _w(s)
    key = _steps_key(w["steps"])
    if w["finding"] or w["found_key"] == key or not ff.ANTHROPIC_API_KEY:
        return
    w["finding"], w["find_err"], w["found_key"], w["found"] = True, False, key, []
    snap = [dict(st) for st in w["steps"]]

    def _run():
        try:
            try:
                hits = detect_fillins(snap)
            except Exception as ex:
                print(f"[tm_custom] fill-in scan retry after "
                      f"{type(ex).__name__}: {ex}", flush=True)
                hits = detect_fillins(snap)
            w["found"] = [dict(f, on=True) for f in hits]
            # A fill-in the user left open, and the same thing written out
            # elsewhere in their steps: start with what they wrote.
            still_open = cc.fillins(snap)
            for f in reversed(w["found"]):
                if f["name"] in still_open and not w["vals"].get(f["name"]):
                    w["vals"][f["name"]] = f["text"]
        except Exception as ex:
            print(f"[tm_custom] fill-in scan failed: {type(ex).__name__}: {ex}",
                  flush=True)
            w["found"], w["find_err"] = [], True
        finally:
            w["finding"] = False
    ff._run_as_user(getattr(s, "_user_email", "") or "", _run,
                    name="tm_custom_detect_worker")

    async def _poll():
        while w["finding"]:
            await asyncio.sleep(1)
        # Edited while the scan ran (Back, change, Next): scan what is
        # there now.
        if w["step"] == 3 and _steps_key(w["steps"]) != w["found_key"]:
            _start_detect(s, rf)
        rf()
    asyncio.ensure_future(_poll())


def _building_row(steps):
    C = _ff().C
    slow = bool(cc.pdf_plan(steps) or cc.profile_plan(steps))
    with ui.element("div").style(
            "display:flex;align-items:center;gap:10px;justify-content:center;"
            "padding:14px;"):
        ui.spinner("dots", size="24px", color=C["teal"])
        ui.label("Building your campaign. Writing the PDFs and candidate "
                 "profiles takes a minute or two…" if slow else
                 "Building your campaign…").style(
            f"font-size:13px;color:{C['teal']};")


def _render_save(s, rf):
    """Name it and save it for reuse. AI reads the steps for what is
    specific to one company or market (industry, role, location...), so
    next time the user is shown those and asked if they want to change
    them."""
    ff = _ff()
    C = ff.C
    w = _w(s)
    steps = w["steps"] or []
    found = w["found"] or []
    on = [f for f in found if f.get("on")]
    typed = cc.fillins(steps)             # asked for on the steps themselves
    asked = cc.fillins(cc.apply_detected(steps, on))

    with ui.element("div").classes("fd-gc").style("margin-bottom:18px;"):
        _card_title("2. Save this campaign")
        _note("Name it and it's yours to reuse for any company or industry. "
              "Next time, you're shown the details that were about this one "
              "and asked if you'd like to change them.", "margin-bottom:6px;")

        _field_label("Campaign name")
        ui.input(
            value=w["name"], placeholder="e.g. Dispatcher intro",
            on_change=lambda e: w.__setitem__("name", (e.value or "").strip()),
        ).props("dense borderless").classes("fd-input")

        ui.label("What might change next time").style(
            f"font-size:11px;font-weight:700;color:{C['muted']};"
            f"text-transform:uppercase;letter-spacing:.06em;margin:18px 0 6px;")
        if w["finding"]:
            with ui.element("div").style(
                    "display:flex;align-items:center;gap:8px;"):
                ui.spinner("dots", size="20px", color=C["teal"])
                ui.label("Reading your steps for anything specific to one "
                         "company or industry…").style(
                    f"font-size:11px;color:{C['teal']};")
        elif w["find_err"]:
            def _look_again():
                w["found_key"] = ""
                _start_detect(s, rf)
                rf()
            with ui.element("div").style(
                    "display:flex;align-items:center;gap:10px;flex-wrap:wrap;"):
                ui.label(
                    "Your steps couldn't be read for company-specific "
                    "wording just now. Look again, or save it as it is and "
                    "it goes out exactly as written every time."
                ).style(f"font-size:12px;color:{C['text']};")
                with ui.element("button").classes("fd-gb").style(
                        "padding:4px 12px;font-size:11px;").on("click", _look_again):
                    ui.label("Look again").style("pointer-events:none;")
        elif not found and not typed:
            ui.label("Nothing in here is tied to one company or industry, "
                     "so it's ready to reuse exactly as written.").style(
                f"font-size:12px;color:{C['text']};")

        if found:
            _note("AI noticed these are about this campaign's companies. "
                  "Next time you use it, you'll see each one and be asked "
                  "if you'd like to change it. Untick any that should "
                  "always stay as written. This campaign still goes out as "
                  "you wrote it.", "margin-bottom:8px;")
            for fi, f in enumerate(found):
                is_on = bool(f.get("on"))
                per_contact = f["name"] in cc.MERGE_FIELDS

                def _toggle(k=fi):
                    w["found"][k]["on"] = not w["found"][k].get("on")
                    rf()
                with ui.element("div").style(
                        f"display:flex;align-items:center;gap:10px;"
                        f"flex-wrap:wrap;cursor:pointer;"
                        f"background:{C['surface']};border:1px solid "
                        f"{C['teal'] if is_on else C['border']};"
                        f"border-radius:8px;padding:8px 12px;margin-bottom:6px;"
                        ).on("click", _toggle):
                    ui.label("✓" if is_on else "").style(
                        f"width:18px;height:18px;border-radius:5px;"
                        f"display:flex;align-items:center;justify-content:center;"
                        f"font-size:12px;font-weight:800;color:{C['on_teal']};"
                        f"background:{C['teal'] if is_on else 'transparent'};"
                        f"border:1px solid {C['teal'] if is_on else C['border']};")
                    ui.label(f"“{f['text']}”").style(
                        f"font-size:12px;color:{C['text_l']};font-weight:600;")
                    ui.label("→").style(f"font-size:12px;color:{C['muted']};")
                    ui.label(cc.fillin_label(f["name"])).style(
                        f"font-size:12px;font-weight:700;color:{C['teal']};")
                    ui.label(
                        ("Filled in from each contact" if per_contact
                         else "You can change it next time") if is_on
                        else "Stays as written"
                    ).style(f"font-size:11px;color:{C['muted']};margin-left:auto;")

        if typed:
            _note("What you filled in for this campaign. You'll be asked "
                  "for these again each time you reuse it.", "margin:8px 0 0;")
            for n in typed:
                _field_label(_ask(n))
                ui.input(
                    value=w["vals"].get(n, ""), placeholder=_hint(n),
                    on_change=lambda e, n=n: w["vals"].__setitem__(
                        n, (e.value or "").strip()),
                ).props("dense borderless").classes("fd-input")

        if asked and not w["finding"]:
            ui.label("Next time you use it, you'll be asked if you'd like "
                     "to change: "
                     + ", ".join(cc.fillin_label(n) for n in asked) + "."
                     ).style(f"font-size:11px;color:{C['text']};margin-top:12px;")
        if w["build_err"]:
            ui.label(f"⚠ {w['build_err']}").style(
                f"font-size:11px;color:{C['danger']};margin-top:8px;")

    if w["building"]:
        _building_row(steps)
        return

    def _save(go: bool):
        if w["building"] or w["finding"]:
            return
        name = (w["name"] or "").strip()
        vals = {n: (w["vals"].get(n) or "").strip()
                for n in cc.fillins(w["steps"])}
        still_open = [cc.fillin_label(n).lower() for n, v in vals.items() if not v]
        if not name:
            w["build_err"] = "Give the campaign a name first."
        elif cc.missing_content(w["steps"]):
            w["build_err"] = "A step is still empty. Go back and finish it."
        elif go and still_open:
            w["build_err"] = ("Fill in " + ", ".join(still_open) + " for this "
                              "campaign, or choose Save it for later.")
        else:
            w["build_err"] = ""
        if w["build_err"]:
            rf()
            return
        picked = [f for f in w["found"] or [] if f.get("on")]
        # Remembered as the hint next time: what each fill-in said this
        # time. A detail found in the user's own sentence is kept in their
        # wording, so it reads right when it is written back in.
        last = {k: v for k, v in vals.items() if v}
        last.update({f["name"]: f["text"] for f in reversed(picked)})
        style_id = save_style(
            name, cc.apply_detected(w["steps"], picked), w["tone"],
            values=last, replace_id=w["edit_id"], profiles_n=w["profiles_n"])
        if not go:
            ff._reset_wizard_state(s)
            _w(s)["saved_note"] = (f'"{name}" is saved. Use it whenever you '
                                   f'need it.')
            rf()
            return
        # This campaign keeps the user's own wording: only a contact's own
        # name or company becomes a merge field, and open fill-ins are
        # written in.
        now = cc.fill(
            cc.apply_detected(
                w["steps"], [f for f in picked if f["name"] in cc.MERGE_FIELDS]),
            vals)
        _start_build(s, rf, name, now, style_id, vals)

    _big_button("Save and choose contacts →", lambda: _save(True),
                off=w["finding"], el_id="tmc-save-go")
    _big_button("Save it for later", lambda: _save(False), primary=False,
                off=w["finding"], el_id="tmc-save-later")


# ── Saved campaigns: the list on the start screen and "use it again" ──────

def _open_use(s, rf, style: dict) -> None:
    """Start a run of a saved campaign: show what it said last time and ask
    if any of it should change, nothing else."""
    _ff()._reset_wizard_state(s)
    w = _w(s)
    w["use"] = dict(style)
    w["vals"] = {f.get("name"): f.get("last") or ""
                 for f in style.get("fillins") or [] if f.get("last")}
    w["profiles_n"] = cc.clamp_profiles(style.get("profiles_n"))
    d = date.today()
    w["name"] = f"{style.get('name') or 'My campaign'} {d:%b} {d.day}"
    s.loaded_camp = None
    s.hub = "sales"
    s.sp = PAGE_KEY
    rf()


def _open_edit(s, rf, style: dict) -> None:
    """Load a saved campaign back into the writer; saving replaces it."""
    _ff()._reset_wizard_state(s)
    w = _w(s)
    # What each fill-in said last time, kept for the PDF's and the profiles'
    # questions and for any fill-in that has no value yet.
    w["vals"] = {f.get("name"): f.get("last") or ""
                 for f in style.get("fillins") or [] if f.get("last")}
    # The user edits their own words, not {Industry}: last time's details
    # are written back in, and saving reads the steps for them again.
    w["steps"] = [
        dict(_new_step(st.get("type", "email"), int(st.get("delay_days") or 0)),
             subject=st.get("subject") or "", input=st.get("input") or "",
             voice=st.get("voice") or cc.VOICE_MINE, pdf=st.get("pdf") or "",
             profiles=bool(st.get("profiles")))
        for st in cc.fill(style.get("steps") or [], w["vals"])]
    w["tone"] = style.get("tone") or w["tone"]
    w["name"] = style.get("name") or ""
    w["edit_id"] = style.get("id") or ""
    w["profiles_n"] = cc.clamp_profiles(style.get("profiles_n"))
    s.sp = PAGE_KEY
    _goto(s, rf, 0)


def _render_saved(s, rf):
    """The start screen's list of saved campaigns: use one again, change
    it, or remove it."""
    C = _ff().C
    rows = load_saved()
    if not rows:
        return
    with ui.element("div").classes("fd-gc").style("margin-bottom:18px;"):
        _card_title("Or use one you saved")
        _note("Use one again for other companies. You're shown the details "
              "from last time, like the industry, the role and the "
              "location, and asked if you'd like to change them.")
        for row in rows:
            asks = cc.fillins(row.get("steps") or [])
            with ui.element("div").style(
                    f"display:flex;align-items:center;gap:10px;flex-wrap:wrap;"
                    f"background:{C['surface']};border:1px solid {C['border']};"
                    f"border-radius:10px;padding:10px 14px;margin-bottom:8px;"):
                with ui.element("div").style("flex:1;min-width:180px;"):
                    ui.label(row.get("name") or "My campaign").style(
                        f"font-size:13px;font-weight:700;color:{C['text_l']};")
                    ui.label(
                        cc.summary(row.get("steps"))
                        + (" · asks about " + ", ".join(
                            cc.fillin_label(n).lower() for n in asks)
                           if asks else "")
                    ).style(f"font-size:11px;color:{C['muted']};")
                with ui.element("button").classes("fd-gb").style(
                        "padding:6px 12px;font-size:11px;"
                        ).on("click", lambda r=row: _open_edit(s, rf, r)):
                    ui.label("Edit").style("pointer-events:none;")

                def _del(sid=row.get("id")):
                    delete_saved(sid)
                    ui.notify("Removed.", type="info")
                    rf()
                with ui.element("button").classes("fd-gb").style(
                        "padding:6px 12px;font-size:11px;").on("click", _del):
                    ui.label("Remove").style("pointer-events:none;")
                with ui.element("button").classes("fd-pb").style(
                        "padding:6px 16px;font-size:12px;"
                        ).on("click", lambda r=row: _open_use(s, rf, r)):
                    ui.label("Use it →").style("pointer-events:none;")


def _render_use(s, rf):
    """A saved campaign, used again: the details are shown as they were last
    time for the user to keep or change, then on to Choose Contacts."""
    ff = _ff()
    C = ff.C
    w = _w(s)
    style = w["use"] or {}
    steps = style.get("steps") or []
    names = cc.fillins(steps)
    last = {f.get("name"): (f.get("last") or "")
            for f in style.get("fillins") or []}
    noticed = [n for n in names if last.get(n)]

    with ui.element("div").classes("fd-gc").style("margin-bottom:18px;"):
        _card_title(f"Use “{style.get('name') or 'My campaign'}”")
        _note(
            "This campaign is about the details below. They're filled in "
            "the way they were last time. Type over what's different this "
            "time and leave the rest. You see every email before it starts."
            if noticed else
            "Fill in what's different this time. Everything else goes out "
            "as you wrote it, and you see every email before it starts."
            if names else
            "Nothing to fill in: this one goes out as you wrote it. You see "
            "every email before it starts.", "margin-bottom:6px;")
        _field_label("Name this campaign")
        ui.input(
            value=w["name"],
            on_change=lambda e: w.__setitem__("name", (e.value or "").strip()),
        ).props("dense borderless").classes("fd-input")
        for n in names:
            _field_label(_ask(n))
            ui.input(
                value=w["vals"].get(n, ""),
                placeholder=(f"Last time: {last[n]}" if last.get(n) else _hint(n)),
                on_change=lambda e, n=n: w["vals"].__setitem__(
                    n, (e.value or "").strip()),
            ).props("dense borderless").classes("fd-input")

        ui.label("What's in it").style(
            f"font-size:11px;font-weight:700;color:{C['muted']};"
            f"text-transform:uppercase;letter-spacing:.06em;margin:18px 0 6px;")
        day = 0
        pdfs, profs = dict(cc.pdf_plan(steps)), set(cc.profile_plan(steps))
        labels = ff._SB_TYPE_LABELS
        for i, st in enumerate(steps):
            stype = st.get("type", "email")
            if i > 0:
                day += int(st.get("delay_days") or 0)
            line = (st.get("subject") or "").strip() or next(
                (ln.strip() for ln in (st.get("input") or "").splitlines()
                 if ln.strip()), "")
            extras = [x for x in (
                f"📎 {cc.PDF_KINDS[pdfs[i]]}" if i in pdfs else "",
                "👤 Candidate profiles" if i in profs else "") if x]
            if extras:
                line = " · ".join(extras + [line])
            with ui.element("div").style(
                    "display:flex;gap:10px;align-items:baseline;padding:3px 0;"):
                ui.label(f"Day {day}").style(
                    f"font-size:11px;color:{C['muted']};width:44px;flex-shrink:0;")
                ui.label(labels.get(stype, stype)).style(
                    f"font-size:11px;font-weight:700;color:{C['text_l']};"
                    f"width:60px;flex-shrink:0;")
                ui.label(line[:110]).style(
                    f"font-size:11px;color:{C['text']};min-width:0;"
                    f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;")
        if w["build_err"]:
            ui.label(f"⚠ {w['build_err']}").style(
                f"font-size:11px;color:{C['danger']};margin-top:8px;")

    if w["building"]:
        _building_row(steps)
        return

    def _go():
        if w["building"]:
            return
        vals = {n: (w["vals"].get(n) or "").strip() for n in names}
        still_open = [cc.fillin_label(n).lower() for n, v in vals.items() if not v]
        if still_open:
            w["build_err"] = "Fill in " + ", ".join(still_open) + " to continue."
            rf()
            return
        remember_values(style.get("id") or "", vals)
        _start_build(
            s, rf, (w["name"] or "").strip() or style.get("name") or "My campaign",
            cc.fill(steps, vals), style.get("id") or "", vals)

    _big_button("Choose contacts →", _go, el_id="tmc-use-go")

"""Build a campaign for ONE company from a Buying Signals card.

The Buying Signals email's "Build a campaign" link used to drop the user on
the AI Prompt menu, which is built for finding many companies. A signal is
about one company, so the link now opens this page (Mike 2026-11-18):

  * the signal card, read back from the user's OWN saved issues - the link
    carries only the issue id and the company name, never the text;
  * the people the user already has at that company, senior titles ticked;
  * "Write the draft campaign": four emails written with the Build a Custom
    Campaign builder, the first opening on the signal, candidate profiles
    on email 2 and a Sales PDF on email 3, saved as a draft with the ticked
    people on it. Nothing sends;
  * "Find people at <company>": the AI Prompt's Build a Campaign for One
    Company run, every box already filled in, for when nobody (or not the
    right person) is in inboxslide yet.

The pure logic (finding the row, matching contacts, the step plan) is at
the top and is what the tests drive; the page is at the bottom.
"""

import asyncio
import re
import sys

from nicegui import ui

import tm_custom_campaign as cc

PAGE_KEY = "tm_signal_campaign"
TITLE = "Build a Campaign for One Company"
STARTER_ID = "one_company"
DEFAULT_LOCATION = "USA"
PROFILES_N = 3
# The page's own state lives on the session under this name; a fresh link
# replaces it, so nothing from one company carries to the next.
STATE_ATTR = "_tsc"


def _ff():
    for name in ("flowdrip_app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_BASE_DATA_DIR") and hasattr(m, "C"):
            return m
    import flowdrip_app as m  # standalone/test fallback
    return m


# ── 1. The signal ─────────────────────────────────────────────────────────

def find_signal(issues, issue_id, company):
    """(row, industry key) for `company` in the user's saved issues, or
    (None, ""). The named issue is tried first; a link from an issue that
    has since rolled off still finds the company in a newer one."""
    want = str(company or "").strip().lower()
    if not want:
        return None, ""
    issues = [i for i in (issues or []) if isinstance(i, dict)]
    first = [i for i in issues if str(i.get("id") or "") == str(issue_id or "")]
    for issue in first + [i for i in issues if i not in first]:
        for sec in issue.get("sections") or []:
            for row in sec.get("companies") or []:
                if str(row.get("company") or "").strip().lower() == want:
                    return dict(row), str(sec.get("industry") or "")
    return None, ""


def link_for(app_url, issue_id, company):
    """The card's "Build a campaign" link."""
    from urllib.parse import urlencode
    q = urlencode({"open": PAGE_KEY, "issue": issue_id or "",
                   "company": company or ""})
    return f"{app_url}/?{q}"


# ── 2. The people already in inboxslide ──────────────────────────────────

# Who signs for offshore staff augmentation: owners and the C-suite,
# partners, VPs, directors, heads of a function, controllers and managing
# or general managers. Matched on whole words so "Director" counts and
# "Directory Assistant" does not.
_SENIOR_RE = re.compile(
    r"\b(owner|co-?owner|founder|co-?founder|president|ceo|coo|cfo|cao|"
    r"chief|partner|principal|vp|svp|evp|vice president|director|head of|"
    r"controller|managing|general manager|administrator|proprietor)\b",
    re.I)


def is_senior(title):
    return bool(_SENIOR_RE.search(str(title or "")))


def _same_company(a, b, norm):
    """True when two company names are the same firm: equal once folded,
    or one is the other with words added ("DHJJ" / "DHJJ CPAs"). The
    shorter one has to be at least two words for the prefix rule, or one
    common word ("Aline") would pull in strangers."""
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short.split()) >= 2 and long_.startswith(short + " ")


def company_contacts(contacts, company, norm):
    """The contacts at `company`, one per email, senior titles first."""
    out, seen = [], set()
    for c in contacts or []:
        email = str(c.get("email") or "").strip().lower()
        if not email or email in seen:
            continue
        if _same_company(c.get("company"), company, norm):
            seen.add(email)
            out.append(c)
    return sorted(out, key=lambda c: (not is_senior(c.get("title")),
                                      str(c.get("last_name") or "").lower()))


def default_picks(people):
    """Emails ticked when the page opens: the senior people, or everyone
    when nobody there has a senior title."""
    senior = [p["email"].strip().lower() for p in people
              if is_senior(p.get("title"))]
    return set(senior or [p["email"].strip().lower() for p in people])


# ── 3. The campaign ───────────────────────────────────────────────────────

def industry_values(industry_key):
    """{"Role", "Location", "Industry"} for the Sales PDF and the candidate
    profiles: the vertical's first job on the Sales Assets list and its
    Sales Assets industry name."""
    import tm_prompts
    for key, label, _aliases, jobs in tm_prompts.INDUSTRY_JOBS:
        if key == industry_key:
            return {"Role": jobs[0] if jobs else "", "Industry": label,
                    "Location": DEFAULT_LOCATION}
    return {"Role": "", "Industry": "", "Location": DEFAULT_LOCATION}


def _signal_facts(row):
    """The signal in plain sentences: the only company facts the AI may
    state, because they came from a sourced news item."""
    parts = [f"The company is {row.get('company')}"
             + (f" in {row['location']}" if row.get("location") else "") + "."]
    if row.get("headline"):
        parts.append(f"The news ({row.get('date') or 'recent'}): "
                     f"{row['headline']}.")
    if row.get("why_now"):
        parts.append(f"Why it matters: {row['why_now']}")
    if row.get("offshore_history"):
        parts.append(f"They already use offshore staff: "
                     f"{row['offshore_history']}")
    return " ".join(parts)


def plan_steps(row, industry_key):
    """(steps, values): four emails over about two weeks. Email 1 opens on
    the signal; 2 carries the candidate profiles; 3 the Sales PDF; 4 is a
    short close. Each step's `ai_prompt` is the direction its draft is
    written from."""
    values = industry_values(industry_key)
    facts = _signal_facts(row)
    role = values["Role"] or "the roles their growth creates"
    offshore = bool(row.get("offshore_history"))
    opener = (row.get("opener") or "").strip()

    def step(delay, direction, pdf="", profiles=False):
        return {"type": "email", "delay_days": delay, "input": "",
                "subject": "", "voice": cc.VOICE_MINE, "pdf": pdf,
                "profiles": profiles, "ai_prompt": direction}

    first = (
        f"{facts} Open on that news in one plain sentence, the way someone "
        f"who read it would"
        + (f", starting from this line and changing it only to fit: "
           f"\"{opener}\"" if opener else "")
        + ". Then say what that growth usually means for the team: more "
        f"{role.lower()} work landing before there are people to cover it. "
        "Say in one sentence that ThriveModal places dedicated offshore "
        "staff for that kind of work"
        + (", and since they already work with offshore staff, ask how that "
           "is going rather than explaining the model" if offshore else "")
        + ". End on one easy question. You may state the news as given; "
        "invent nothing else about the company.")
    second = (
        f"{facts} Follow up on the first email without repeating it. Name "
        f"the {role} work their growth adds and say you put together a few "
        "candidates of the kind you would send them.")
    third = (
        f"{facts} A short note pointing to the attached PDF as something "
        "useful while they plan the next hires. One question at the end.")
    fourth = (
        f"{facts} The last note. Two or three sentences: you will leave it "
        "here, and if the timing is better after the growth settles they "
        "can reply with one word and you will pick it back up.")
    steps = [
        step(0, first),
        step(3, second, profiles=True),
        step(4, third, pdf="tm_how_it_works" if offshore else "tm_role_blueprint"),
        step(5, fourth),
    ]
    for i, st in enumerate(steps):
        st["id"] = f"sig{i + 1}"
    return steps, values


def campaign_name(row):
    return f"{row.get('company') or 'Company'} - buying signal"


def write_steps(steps, values, draft):
    """Write every step in order with `draft(steps, i, direction, values,
    with_subject)` -> text, so each draft sees the ones before it. The
    first email's subject comes off its "Subject:" line."""
    for i, st in enumerate(steps):
        text = draft(steps, i, st.get("ai_prompt") or "", values, i == 0)
        if i == 0:
            subj, text = cc.split_subject(text)
            st["subject"] = subj
        st["input"] = (text or "").strip()
    return steps


def attach_people(camp, people):
    """Put the picked people on the draft, the way Choose Contacts does."""
    people = list(people or [])
    camp["contacts"] = people
    camp["contact_count"] = len(people)
    camp["contact_emails"] = [p.get("email", "") for p in people]
    return camp


def build(owner, row, industry_key, people, client=None):
    """(draft campaign, what could not be added). Uses the Build a Custom
    Campaign builder for the PDF, the profiles and the save."""
    import tm_custom_campaign_page as page
    ff = _ff()
    if client is None and ff.ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.Anthropic(api_key=ff.ANTHROPIC_API_KEY)
    steps, values = plan_steps(row, industry_key)

    def _draft(steps, i, direction, values, with_subject):
        return page.draft_step(steps, i, direction, "consultative", values,
                               with_subject, client=client)
    write_steps(steps, values, _draft)
    empty = [i + 1 for i, st in enumerate(steps) if not st["input"]]
    if empty:
        raise RuntimeError("the AI came back empty on email "
                           + ", ".join(map(str, empty)))
    camp, missed = page.build_campaign(owner, campaign_name(row), steps, "",
                                       values, PROFILES_N, client)
    camp["tm_signal"] = {k: row.get(k, "") for k in
                         ("company", "signal", "headline", "date", "source_url")}
    attach_people(camp, people)
    ff.save_campaign(camp)
    return camp, missed


def ai_prompt_request(row, industry_key):
    """The AI Prompt request for "Find people at <company>": the One Company
    run with the company, the vertical and the signal already written in."""
    import ai_prompts
    import tm_prompts
    st = tm_prompts.STARTER_BY_ID[STARTER_ID]
    req = ai_prompts._req_from_starter(st, tm_prompts.TM)
    label = ""
    for v in tm_prompts.VERTICALS:
        if v["key"] == industry_key:
            label = v["label"]
    why = " ".join(x for x in (
        (f"{row['headline']} ({row['date']})." if row.get("headline") else ""),
        row.get("why_now") or "",
        (f"Already offshore: {row['offshore_history']}"
         if row.get("offshore_history") else ""),
        (f"Source: {row['source_url']}" if row.get("source_url") else ""),
    ) if x)
    vals = {"company": row.get("company") or "", "why_now": why}
    if label:
        vals["vertical"] = label
    req["vals"].update(vals)
    req["filled"] = sorted(set(req.get("filled") or []) | set(vals))
    return req


# ── 4. The page ───────────────────────────────────────────────────────────

def open_from_link(s, issue_id, company):
    """Called by the router for ?open=tm_signal_campaign. Resets the page's
    state for this company; the row itself is read when the page draws."""
    setattr(s, STATE_ATTR, {"issue": str(issue_id or ""),
                            "company": str(company or ""), "picks": None,
                            "building": False, "err": ""})
    s.hub = "sales"
    s.sp = PAGE_KEY


def _state(s):
    w = getattr(s, STATE_ATTR, None)
    if not isinstance(w, dict):
        w = {"issue": "", "company": "", "picks": None, "building": False,
             "err": ""}
        setattr(s, STATE_ATTR, w)
    return w


def _all_contacts(ff):
    contacts = list(ff.load_contacts())
    try:
        for _name, path in ff.list_saved_contact_lists().items():
            contacts += ff.load_contacts(path)
    except Exception:
        pass
    return contacts


def _go_ai_prompt(s, rf, row, industry_key):
    s._aip_req = ai_prompt_request(row, industry_key)
    s._aip_pick = STARTER_ID
    s._aip_prompt = None
    s._aip_back = None
    s._aip_open = None
    s._aip_saving = False
    s._aip_err = ""
    s.hub = "sales"
    s.sp = "tm_prompts"
    rf()


def render_page(s, rf):
    import tm_signals
    ff = _ff()
    C = ff.C
    w = _state(s)
    email = (getattr(s, "_user_email", "") or "").strip().lower()
    if email:
        try:
            ff._CURRENT_USER_EMAIL.set(email)
        except Exception:
            pass
    row, ind = find_signal(tm_signals.load_settings().get("issues"),
                           w["issue"], w["company"])

    def _back():
        s.sp = "tm_signals"
        rf()

    with ui.element("div").style("max-width:820px;"):
        with ui.element("div").style(
                "display:flex;align-items:flex-start;justify-content:"
                "space-between;gap:12px;margin-bottom:14px;"):
            with ui.element("div"):
                ui.label(TITLE).classes("fd-h1")
                ui.label("One company, one campaign that opens on the news. "
                         "Nothing sends from this page.").classes("fd-sub")
            with ui.element("button").classes("fd-gb").style(
                    "padding:6px 14px;font-size:11px;white-space:nowrap;"
                    ).on("click", _back):
                ui.label("← Buying Signals")

        if row is None:
            ui.label(f"That signal for \"{w['company'] or 'this company'}\" "
                     "isn't in your saved Buying Signals any more.").style(
                f"font-size:14px;color:{C['text_l']};display:block;"
                "margin-bottom:10px;")
            with ui.element("button").classes("fd-gb").on(
                    "click", lambda: (setattr(s, "sp", "tm_prompts"), rf())):
                ui.label("Open AI Prompt instead")
            return

        _signal_card(C, row, tm_signals)
        people = company_contacts(_all_contacts(ff), row["company"],
                                  ff._norm_company_name)
        if w["picks"] is None:
            w["picks"] = sorted(default_picks(people))
        _people_card(s, rf, C, w, row, ind, people)


def _signal_card(C, row, tm_signals):
    sig = tm_signals.SIGNAL_BY_ID.get(row.get("signal"), {})
    colour = C["danger"] if sig.get("urgent") else C["teal"]
    with ui.element("div").style(
            f"background:{C['surface']};border:1px solid {C['border']};"
            "border-radius:12px;padding:16px 18px;margin-bottom:16px;"):
        with ui.element("div").style(
                "display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;"):
            ui.label(row["company"]).style(
                f"font-size:16px;font-weight:700;color:{C['text_l']};")
            if row.get("location"):
                ui.label(row["location"]).style(
                    f"font-size:12px;color:{C['muted']};")
        if sig:
            ui.label(sig["label"]).style(
                f"display:inline-block;background:{colour};color:#fff;"
                "font-size:11px;font-weight:700;padding:2px 8px;"
                "border-radius:999px;margin:6px 0;")
        ui.label(row.get("headline") or "").style(
            f"font-size:13px;font-weight:600;color:{C['text_l']};"
            "display:block;margin-bottom:4px;")
        for lbl, key in (("Why it is a buying signal", "why_now"),
                         ("Already offshore", "offshore_history")):
            if row.get(key):
                ui.html(f'<div style="font-size:12px;color:{C["text_l"]};'
                        f'margin-bottom:4px;"><b>{tm_signals._e(lbl)}:</b> '
                        f'{tm_signals._e(row[key])}</div>', sanitize=False)
        if row.get("source_url"):
            ui.link("Source", row["source_url"], new_tab=True).style(
                "font-size:12px;")


def _people_card(s, rf, C, w, row, ind, people):
    ff = _ff()
    company = row["company"]
    with ui.element("div").style(
            f"background:{C['surface']};border:1px solid {C['border']};"
            "border-radius:12px;padding:16px 18px;"):
        ui.label("Who it goes to").style(
            f"font-size:15px;font-weight:700;color:{C['text_l']};"
            "display:block;margin-bottom:4px;")
        if people:
            ui.label(f"The people you already have at {company}. Senior "
                     "titles are ticked; change it how you like.").style(
                f"font-size:12px;color:{C['muted']};display:block;"
                "margin-bottom:10px;")
            for p in people:
                em = p["email"].strip().lower()
                name = " ".join(x for x in (p.get("first_name"),
                                            p.get("last_name")) if x) or em

                def _flip(e, em=em):
                    picks = set(w["picks"] or [])
                    (picks.add if e.value else picks.discard)(em)
                    w["picks"] = sorted(picks)
                ui.checkbox(
                    f"{name} · {p.get('title') or 'no title'} · {em}",
                    value=em in (w["picks"] or []), on_change=_flip,
                ).style(f"font-size:13px;color:{C['text_l']};display:flex;"
                        "width:100%;")
        else:
            ui.label(f"You don't have anyone at {company} in inboxslide yet. "
                     "You can still write the draft and add people at "
                     "launch, or have Claude find the buyers there.").style(
                f"font-size:12px;color:{C['muted']};display:block;"
                "margin-bottom:10px;")

        if w["err"]:
            ui.label(f"That didn't work: {w['err']}").style(
                f"font-size:12px;color:{C['danger']};display:block;"
                "margin-top:8px;")

        with ui.element("div").style(
                "display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;"
                "align-items:center;"):
            if w["building"]:
                ui.spinner(size="sm")
                ui.label("Writing four emails around the news. About a "
                         "minute.").style(f"font-size:12px;color:{C['muted']};")
                return
            primary = ui.element("button").classes(
                "fd-pb" if people else "fd-gb").on(
                "click", lambda: _start_build(s, rf, w, row, ind, people))
            with primary:
                ui.label("Write the draft campaign")
            find = ui.element("button").classes(
                "fd-gb" if people else "fd-pb").on(
                "click", lambda: _go_ai_prompt(s, rf, row, ind))
            with find:
                ui.label(f"Find {'more ' if people else ''}people at "
                         f"{company}")
        ui.label("Four emails over about two weeks: the first opens on the "
                 "news, the second carries candidate profiles, the third a "
                 "Sales PDF. It's saved as a draft for you to read before "
                 "anything goes out.").style(
            f"font-size:11px;color:{C['muted']};display:block;margin-top:10px;")
        if not ff.ANTHROPIC_API_KEY:
            ui.label("AI writing isn't set up on this server, so the draft "
                     "can't be written here. Use Find people instead.").style(
                f"font-size:11px;color:{C['warn']};display:block;"
                "margin-top:4px;")


def _start_build(s, rf, w, row, ind, people):
    ff = _ff()
    if w["building"]:
        return
    picked = set(w["picks"] or [])
    chosen = [p for p in people if p["email"].strip().lower() in picked]
    w.update(building=True, err="", built=None, missed=[])
    rf()
    owner = getattr(s, "_user_email", "") or ""

    def _run():
        try:
            w["built"], w["missed"] = build(owner, row, ind, chosen)
        except Exception as e:
            print(f"[tm_signal_campaign] build failed: {type(e).__name__}: {e}",
                  flush=True)
            w["err"] = ff._friendly_ai_error(e)
        finally:
            w["building"] = False
    ff._run_as_user(owner, _run, name="tm_signal_campaign_worker")

    async def _poll():
        while w["building"]:
            await asyncio.sleep(1)
        camp = w.get("built")
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
                n = len(chosen)
                ui.notify(f'"{camp.get("name")}" is ready as a draft'
                          + (f" with {n} {'person' if n == 1 else 'people'} "
                             "on it." if n else ". Add who it goes to."),
                          type="positive")
                if w.get("missed"):
                    ui.notify("One thing couldn't be added just now: "
                              + "; ".join(w["missed"]) + ".",
                              type="warning", timeout=14000)
            except Exception:
                pass
        rf()
    asyncio.ensure_future(_poll())

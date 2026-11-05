"""Build a Custom Campaign: the user's own steps turned into campaign emails.

inboxslide's version of DripDrop's "Create my own campaign" walkthrough
(own_campaign.py on the DripDrop line), written for what ThriveModal sells:
offshore staff augmentation. The page (tm_custom_campaign_page) comes
through here, so a step the user wrote goes out as typed. Only
{FirstName}/{Company}-style merge fields are filled, and that happens later
at queue time, as for every campaign.

What differs from DripDrop: there is no candidate Pipeline to pick people
from. An email can carry the same candidate profiles every ThriveModal
campaign carries (typical profiles for the target role, placed by code when
the campaign is built), and one of ThriveModal's eight Sales PDFs.

A saved campaign is reused for other companies, so anything specific to one
of them is a {Fill-in} the user is asked for each time (see Fill-ins below).

No AI client, no app state and no nicegui here: the caller hands in `polish`.
"""
import json
import re

VOICE_MINE = "mine"
VOICE_POLISH = "polish"
VOICES = (VOICE_MINE, VOICE_POLISH)

# Step type in the walkthrough -> step_type on a campaign step (flowdrip ST).
_STEP_TYPES = {"email": "email_auto", "call": "call", "linkedin": "linkedin"}
_STEP_NAMES = {"email": "Email", "call": "Call", "linkedin": "LinkedIn"}
MAX_STEPS = 15

FIRST_SUBJECT_FALLBACK = "Quick question, {FirstName}"
DEFAULT_TIME = "9:00 AM"

# ThriveModal's campaign PDFs, in the order campaigns offer them. One can go
# out with any email after the first, each kind once. Must match
# flowdrip_app._TM_CAMPAIGN_PDF_KINDS (tests/test_tm_custom_campaign.py).
PDF_KINDS = {
    "tm_role_blueprint": "Offshore Role Blueprint",
    "tm_cost_compare": "Staffing Cost Comparison",
    "tm_how_it_works": "How We Work Together",
    "tm_myths": "Offshore Myths vs Reality",
    "tm_roles_map": "Roles That Work Offshore",
    "tm_first_90": "First 90 Days Plan",
    "tm_security": "Security and Confidentiality",
    "market_pulse": "Market Pulse",
}
# A PDF is written for a role, a place and an industry; candidate profiles
# for a role and an industry. A step that carries either asks for those
# like any other fill-in.
PDF_FILLINS = ("Role", "Location", "Industry")
PROFILE_FILLINS = ("Role", "Industry")
DEFAULT_LOCATION = "USA"

PROFILES_MIN, PROFILES_MAX, PROFILES_DEFAULT = 3, 5, 3


def clamp_profiles(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = PROFILES_DEFAULT
    return max(PROFILES_MIN, min(PROFILES_MAX, n))


def voice_of(step) -> str:
    v = (step or {}).get("voice") or VOICE_MINE
    return v if v in VOICES else VOICE_MINE


def _type_of(step) -> str:
    t = (step or {}).get("type")
    return t if t in _STEP_TYPES else "email"


def step_names(steps) -> list:
    """'Email 1', 'Call 1', 'Email 2'...: what each step is called on the
    page and in the built campaign."""
    counts, out = {}, []
    for st in steps or []:
        t = _type_of(st)
        counts[t] = counts.get(t, 0) + 1
        out.append(f"{_STEP_NAMES[t]} {counts[t]}")
    return out


def is_first_email(steps, i) -> bool:
    steps = steps or []
    return (_type_of(steps[i]) == "email"
            and not any(_type_of(x) == "email" for x in steps[:i]))


def pdf_plan(steps) -> list:
    """(step index, kind) for each email that carries a PDF. Never the first
    email, only the known kinds, and each kind once (the first email that
    asks for it keeps it)."""
    out, seen_email, used = [], False, set()
    for i, st in enumerate(steps or []):
        st = st or {}
        if _type_of(st) != "email":
            continue
        kind = st.get("pdf")
        if seen_email and kind in PDF_KINDS and kind not in used:
            out.append((i, kind))
            used.add(kind)
        seen_email = True
    return out


def profile_plan(steps) -> list:
    """Step indexes of the emails that carry the candidate profiles. Never
    the first email."""
    out, seen_email = [], False
    for i, st in enumerate(steps or []):
        st = st or {}
        if _type_of(st) != "email":
            continue
        if seen_email and st.get("profiles"):
            out.append(i)
        seen_email = True
    return out


def missing_content(steps) -> list:
    """1-based step numbers that cannot go out yet: no body, or the first
    email with no subject line."""
    return [i + 1 for i in range(len(steps or []))
            if step_problem(steps, i, None, fillins_too=False)]


def step_problem(steps, i, values=None, fillins_too=True):
    """What step i still needs before the campaign can be saved, or None:
    "body" (nothing written), "subject" (the first email has no subject
    line) or ("fillin", name) for a fill-in used here with no value yet."""
    steps = steps or []
    st = steps[i] or {}
    if not (st.get("input") or "").strip():
        return "body"
    if is_first_email(steps, i) and not (st.get("subject") or "").strip():
        return "subject"
    if not fillins_too:
        return None
    values = values or {}
    need = [n for n in step_fillins(steps, i)
            if not str(values.get(n) or "").strip()]
    return ("fillin", need[0]) if need else None


def style_steps(steps) -> list:
    """The saved shape of the walkthrough's steps: only what a later launch
    needs, none of the page's working fields (_drafting, ai_prompt...)."""
    out, pdfs, profs = [], dict(pdf_plan(steps)), set(profile_plan(steps))
    for i, st in enumerate(steps or []):
        st = st or {}
        t = _type_of(st)
        row = {
            "type": t,
            "delay_days": 0 if i == 0 else max(1, int(st.get("delay_days") or 0)),
            "subject": (st.get("subject") or "").strip() if t == "email" else "",
            "input": (st.get("input") or "").strip(),
            "voice": voice_of(st),
        }
        if i in pdfs:
            row["pdf"] = pdfs[i]
        if i in profs:
            row["profiles"] = True
        out.append(row)
    return out


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text_to_html(text: str) -> str:
    """The user's plain text as the HTML a campaign step holds: paragraphs
    split by <br><br>, which is what the profile and PDF placement read."""
    text = re.sub(r"\r\n?", "\n", text or "").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _esc(text).replace("\n", "<br>")


def build_emails(steps, polish=None) -> list:
    """Campaign steps (the dicts save_campaign / queue_campaign_emails read)
    from the walkthrough's or a saved style's steps.

    "My words" text is used as typed. "AI polish" text goes through
    `polish(text, step_type, step_index)` first; if polish is None or
    fails, the user's own text is sent rather than nothing. Candidate
    profiles and PDFs are added afterwards by the caller (profile_plan,
    pdf_plan), because both are written by the app at build time."""
    out, counts, prev_subject = [], {}, ""
    for i, st in enumerate(style_steps(steps)):
        t = st["type"]
        text = st["input"]
        if st["voice"] == VOICE_POLISH and polish is not None and text:
            try:
                polished = (polish(text, t, i) or "").strip()
            except Exception as e:
                print(f"[tm_custom] polish failed on step {i + 1}: {e}", flush=True)
                polished = ""
            # Never trade a merge field or fill-in for nicer wording.
            if polished and all(tok in polished
                                for tok in set(re.findall(r"\{[A-Za-z0-9]+\}", text))):
                text = polished
        subject = ""
        if t == "email":
            subject = st["subject"] or (
                f"Re: {prev_subject}" if prev_subject else FIRST_SUBJECT_FALLBACK)
            if not prev_subject:
                prev_subject = subject
        counts[t] = counts.get(t, 0) + 1
        out.append({
            "name": f"{_STEP_NAMES[t]} {counts[t]}",
            "subject": subject,
            "body": text_to_html(text),
            "step_type": _STEP_TYPES[t],
            "delay_days": st["delay_days"],
            "time": DEFAULT_TIME,
            "touch_number": i + 1,
            "attachments": [],
            "tags": [],
            "script_notes": "",
            "channel": "email" if t == "email" else t,
        })
    return out


# ── What the AI is told ───────────────────────────────────────────────────

# Who is writing and what they sell, for every AI job on the page. Kept to
# what any ThriveModal seller can say; the numbers and the track record are
# the user's to add in their own words.
WHO_WE_ARE = (
    "The sender sells offshore staff augmentation for ThriveModal: "
    "ThriveModal recruits dedicated, full-time professionals in the "
    "Philippines around a specific role. The client interviews and chooses "
    "the candidate, the candidate works the client's hours inside the "
    "client's own systems, and the client's team directs the day-to-day "
    "work. The reader is a U.S. business owner or manager who has not asked "
    "to hear from the sender.")

VOICE_RULES = (
    "- Write as the sender typing a note to one person: first person, "
    "contractions, plain words, a little unsure rather than pushy.\n"
    "- An email is 50 to 110 words after the greeting, in two to four short "
    "paragraphs, and ends on ONE question that is easy to answer.\n"
    "- Say 'offshore staff augmentation', never 'offshore staffing'. Whoever "
    "the client would hire is 'the candidate', never 'the person'.\n"
    "- No em dashes, no exclamation marks, no bullet lists, no hype, and "
    "none of: 'I hope this email finds you well', 'just checking in', "
    "'circling back', 'leverage', 'streamline', 'seamless', 'robust', "
    "'unlock', 'game-changer'.\n")

FACT_RULES = (
    "- Do not invent facts: no savings percentage, dollar amount, hourly "
    "rate, number of placements, client name, certification or guarantee "
    "unless the user's direction or the other steps state it.\n"
    "- Do not invent an industry, a role, a city or a company detail. If "
    "the user's direction or the other steps name one, write it as they "
    "gave it; otherwise word the sentence so it reads well without one.\n"
    "- Leave nothing to fill in later: no [square bracket] placeholders and "
    "nothing in {braces} except the merge fields {FirstName}, {LastName}, "
    "{Company} and {JobTitle}.\n")

# Sample direction shown in the "Describe it, AI drafts it" box, by slot
# (see slot_of). Illustrations of what to type, never sent.
AI_HINTS = {
    "intro_email": (
        "e.g. Introduce myself and say we do offshore staff augmentation. "
        "They may not need anyone right now, but I'd like to connect so "
        "they have someone to call when the back-office work piles up."),
    "followup_email_1": (
        "e.g. Follow up with the cost side: a dedicated candidate in the "
        "Philippines next to a comparable U.S. hire. Offer to run the "
        "numbers on one role."),
    "followup_email_2": (
        "e.g. Describe what one role could take off their team's plate, "
        "like document follow-up and record updates, and ask if that "
        "sounds like the work they're carrying."),
    "closer_email": (
        "e.g. Last note for now. If they've never tried someone overseas I "
        "get the hesitation, and one role is an easy way to find out."),
    "extra_email": (
        "e.g. A short, low-pressure note with one new reason to talk."),
    "call_script": (
        "e.g. Quick intro and voicemail: who I am, that I emailed about "
        "offshore staff augmentation, and one question about where their "
        "team is stretched."),
    "linkedin_message": (
        "e.g. Short connection note: I work with companies in their "
        "industry on offshore staff augmentation and would like to connect."),
}

# Finished sample copy per slot, in ThriveModal's voice, so a draft stays
# grounded even when the user's direction is one line.
REFERENCE_EXAMPLES = {
    "intro_email": (
        "Hi {FirstName},\n\nYou might not need anyone right now, and "
        "that's fine. I thought it was worth connecting anyway, so you "
        "have someone to call when the work starts piling up.\n\nWe do "
        "offshore staff augmentation. ThriveModal recruits dedicated "
        "professionals in the Philippines around a specific role. You "
        "interview and choose the candidate, and they work your hours.\n\n"
        "Would it be worth a quick conversation, even just to network?"),
    "followup_email_1": (
        "Hi {FirstName},\n\nTouching base again, this time with something "
        "more concrete.\n\nWe can price a dedicated Philippines-based role "
        "and put it next to the full cost of a comparable U.S. hire, so "
        "you can see the difference for yourself.\n\nWant me to run the "
        "numbers on one role?"),
    "followup_email_2": (
        "Hi {FirstName},\n\nI've been thinking about what this could look "
        "like on your team.\n\nA starting scope might be chasing missing "
        "documents, updating records and keeping routine requests moving. "
        "Your team still sets the process and makes the calls.\n\nDoes "
        "that sound close to the work you're carrying today?"),
    "closer_email": (
        "Hi {FirstName},\n\nI don't want to keep filling your inbox, so "
        "this is my last note for now.\n\nIf you've never tried someone "
        "overseas, I get the hesitation. One role is an easy way to find "
        "out.\n\nWould you be open to a short conversation about it?"),
    "extra_email": (
        "Hi {FirstName},\n\nHope your week's going well. One more thought "
        "on this, and then I'll leave it with you.\n\nThe first hire is "
        "usually the one that proves it out, so most teams start with a "
        "single role.\n\nWorth a quick call to see if one fits?"),
    "call_script": (
        "Hi {FirstName}, this is [your name] with ThriveModal. I sent you "
        "a note about offshore staff augmentation, where we recruit a "
        "dedicated candidate in the Philippines for a role on your team. "
        "I'm not sure it's on your radar, so I wanted to ask one thing: "
        "where is your team most stretched right now? If now's a bad "
        "time, I'm happy to call back."),
    "linkedin_message": (
        "Hi {FirstName}, I work with companies like {Company} on offshore "
        "staff augmentation: dedicated candidates in the Philippines who "
        "work your hours. No pitch here, I'd just like to connect."),
}


def slot_of(steps, i) -> str:
    """Which AI_HINTS / REFERENCE_EXAMPLES entry step i uses: calls and
    LinkedIn have one each; emails go by their rank among the emails."""
    t = _type_of((steps or [])[i])
    if t == "call":
        return "call_script"
    if t == "linkedin":
        return "linkedin_message"
    rank = sum(1 for x in steps[:i] if _type_of(x) == "email")
    slots = ("intro_email", "followup_email_1", "followup_email_2",
             "closer_email")
    return slots[rank] if rank < len(slots) else "extra_email"


def pdf_note(step, values=None) -> str:
    """What the AI is told when an email carries a Sales PDF: it is attached,
    what it covers, and the email should point to it. "" with no PDF."""
    kind = (step or {}).get("pdf")
    if kind not in PDF_KINDS or _type_of(step) != "email":
        return ""
    v = values or {}
    about = ", ".join(x for x in (
        f"the {v.get('Role')} role" if v.get("Role") else "",
        f"for {v.get('Industry')} companies" if v.get("Industry") else "") if x)
    return (f" A PDF called \"{PDF_KINDS[kind]}\" is attached to this email"
            + (f" (written about {about})" if about else "")
            + ". Mention the attachment in one natural sentence near the end "
            "and say what the reader will find in it. Do not quote figures "
            "from it.")


def profiles_note(step, values=None) -> str:
    """What the AI is told when an email carries the candidate profiles:
    they are set into the email by the app, so the words lead up to them
    and never describe a candidate. "" when it carries none."""
    if not (step or {}).get("profiles") or _type_of(step) != "email":
        return ""
    role = (values or {}).get("Role")
    return (" A short set of candidate profiles from our pipeline"
            + (f" for the {role} role" if role else "")
            + " is added to this email automatically, just before its "
            "closing question. Write one sentence that leads into them, for "
            "example that you wanted to show the kind of candidates you "
            "would put forward. Do not describe any candidate yourself, do "
            "not give a name, a rate or a start date, and do not say a "
            "candidate is available or has been placed.")


def draft_prompt(steps, i, direction: str = "", tone: str = "",
                 values=None, with_subject: bool = False) -> str:
    """The instruction for an AI draft of step i: the whole step from a
    sentence or two of direction, or from the other steps when there is
    none."""
    st = (steps or [])[i] or {}
    t = _type_of(st)
    kind = {"email": "Email", "call": "Call", "linkedin": "LinkedIn"}[t]
    delay = int(st.get("delay_days") or 0)
    when = ("This is the first touch in the campaign." if i == 0 else
            f"This step goes out {delay} business day"
            f"{'s' if delay != 1 else ''} after the step before it.")
    direction = (direction or "").strip() or (
        "Write a complete, ready-to-use message that suits this point in "
        "the campaign and adds something the earlier steps did not say.")
    direction += pdf_note(st, values) + profiles_note(st, values)
    context = draft_context(steps, i)
    return (
        f"You are drafting ONE step of a {tone or 'consultative'} sales "
        f"outreach campaign. Write only this step.\n\n"
        f"{WHO_WE_ARE}\n\n"
        f"STEP TYPE: {kind}\n{when}\n\n"
        f"USER'S DIRECTION FOR THIS STEP: {direction}\n\n"
        + (f"THE OTHER STEPS IN THIS CAMPAIGN (fit in with them, do not "
           f"repeat them):\n{context}\n\n" if context else "")
        + f"REFERENCE EXAMPLE (match this voice and length, but write fresh "
        f"content for THIS step from the direction above):\n"
        f"{REFERENCE_EXAMPLES.get(slot_of(steps, i), '')}\n\n"
        f"RULES:\n{VOICE_RULES}{FACT_RULES}"
        + ("- Email: start with 'Hi {FirstName},'. No signature block and "
           "no sign-off name.\n" if t == "email" else "")
        + ("- Call: a short spoken script or talking points the sender "
           "reads from, not an email.\n" if t == "call" else "")
        + ("- LinkedIn: one short message, under 60 words, no greeting "
           "line break.\n" if t == "linkedin" else "")
        + ("- Open with one line 'Subject: ...' (a plain subject of two to "
           "six words, sentence case), then a blank line, then the body.\n"
           if with_subject and t == "email" else
           "- No subject line.\n")
        + "- Return ONLY the drafted text. No preamble, no markdown, no "
        "explanation.")


def polish_prompt(text: str, step_type: str, tone: str = "",
                  attach: str = "") -> str:
    """The instruction for one "AI polish" step. Light touch: the user's
    meaning, order and length stay; merge fields and fill-ins stay exactly
    as written."""
    kind = {"email": "email body", "call": "phone call script",
            "linkedin": "LinkedIn message"}.get(step_type, "message")
    return (
        f"Lightly polish this salesperson's {kind}. It is their own "
        f"writing, so keep their meaning, their order and roughly their "
        f"length. Fix grammar, tighten wording and make it read naturally"
        + (f" in a {tone} tone" if tone else "") + ".\n\n"
        "Rules:\n"
        "- Keep everything in {braces} exactly as written, braces included: "
        "{FirstName}, {LastName}, {Company}, {JobTitle} and any other, such "
        "as {Industry} or {Role}.\n"
        "- Do not add facts, numbers, names, links or promises that are not "
        "in the text.\n"
        "- Say 'offshore staff augmentation', never 'offshore staffing'.\n"
        "- No subject line, no signature, no sign-off name.\n"
        "- Do not use em dashes.\n"
        + (f"- A PDF ({attach}) is attached to this email. If the text does "
           f"not already point to the attachment, add one short sentence "
           f"saying it is attached.\n" if attach else "") +
        "- Return only the polished text, nothing before or after it.\n\n"
        f"TEXT:\n{text}"
    )


def draft_context(steps, i) -> str:
    """What the other steps already say, so an AI draft of step i fits in
    with them."""
    names, blocks = step_names(steps), []
    for j, st in enumerate(steps or []):
        st = st or {}
        body = (st.get("input") or "").strip()
        if j == i or not body:
            continue
        subject = (st.get("subject") or "").strip()
        blocks.append(f"[{names[j]}]\n"
                      + (f"Subject: {subject}\n" if subject else "")
                      + body[:1500])
    return "\n\n".join(blocks)


def split_subject(text: str) -> tuple:
    """(subject, body) from a draft that opens with a "Subject:" line;
    ("", text) when it does not."""
    text = (text or "").strip()
    m = re.match(r"Subject:[ \t]*(.+?)[ \t]*\r?\n+", text, re.I)
    if not m:
        return "", text
    return m.group(1).strip(), text[m.end():].strip()


# ── Fill-ins: what changes each time a saved campaign is used ────────────
# A saved campaign is meant to be reused for another company or industry, so
# anything specific lives in the text as a {Token}. Per-contact merge fields
# are filled at queue time as always; every other token is a fill-in the
# user is asked for each time they use the campaign.

MERGE_FIELDS = ("FirstName", "LastName", "Company", "CompanyName", "JobTitle")
_TOKEN_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9]*)\}")
_TEXT_FIELDS = ("subject", "input")


def fillin_label(name: str) -> str:
    """'CurrentClients' -> 'Current clients', 'Role2' -> 'Role 2'."""
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Za-z])(?=\d+$)", " ",
                   name or "").split()
    return " ".join([words[0]] + [w.lower() for w in words[1:]]) if words else ""


def clean_fillin_name(raw) -> str:
    """A token name from whatever the model or user called it: letters and
    digits only, CamelCase."""
    parts = re.findall(r"[A-Za-z0-9]+", str(raw or ""))
    name = "".join(p[:1].upper() + p[1:] for p in parts)
    if not name or not name[0].isalpha():
        return ""
    return name[:40]


def _extra_fillins(steps, only=None) -> list:
    """What the PDFs and the candidate profiles on these steps need."""
    out = []
    pdfs, profs = dict(pdf_plan(steps)), set(profile_plan(steps))
    idx = range(len(steps or [])) if only is None else [only]
    if any(i in pdfs for i in idx):
        out += list(PDF_FILLINS)
    if any(i in profs for i in idx):
        out += [n for n in PROFILE_FILLINS if n not in out]
    return out


def fillins(steps) -> list:
    """Fill-in names the steps ask for, in first-seen order: the tokens in
    the text, then what an attached PDF or the candidate profiles need.
    Merge fields are not fill-ins."""
    seen = []
    for st in steps or []:
        for f in _TEXT_FIELDS:
            for name in _TOKEN_RE.findall((st or {}).get(f) or ""):
                if name not in MERGE_FIELDS and name not in seen:
                    seen.append(name)
    return seen + [n for n in _extra_fillins(steps) if n not in seen]


def step_fillins(steps, i) -> list:
    """What step i on its own asks for: its tokens, plus what its PDF or
    its candidate profiles need."""
    seen = []
    for f in _TEXT_FIELDS:
        for name in _TOKEN_RE.findall(((steps or [])[i] or {}).get(f) or ""):
            if name not in MERGE_FIELDS and name not in seen:
                seen.append(name)
    return seen + [n for n in _extra_fillins(steps, only=i) if n not in seen]


def missing_fillins(steps, values) -> list:
    values = values or {}
    return [n for n in fillins(steps) if not str(values.get(n) or "").strip()]


def fill(steps, values) -> list:
    """Copies of the steps with each fill-in that has a value written in.
    Merge fields and fill-ins without a value are left."""
    values = {k: str(v).strip() for k, v in (values or {}).items()
              if k not in MERGE_FIELDS and str(v or "").strip()}

    def _sub(text):
        return _TOKEN_RE.sub(
            lambda m: values.get(m.group(1), m.group(0)), text or "")
    out = []
    for st in steps or []:
        st = dict(st or {})
        for f in _TEXT_FIELDS:
            if st.get(f):
                st[f] = _sub(st[f])
        out.append(st)
    return out


def detect_prompt(steps) -> str:
    """Asks the model which details in the user's steps are specific to one
    company or market, so they can become fill-ins. Exact substrings only:
    the caller replaces text, it never rewrites."""
    blocks = []
    for i, st in enumerate(steps or [], 1):
        st = st or {}
        if (st.get("subject") or "").strip():
            blocks.append(f"[Step {i} subject]\n{st['subject'].strip()}")
        if (st.get("input") or "").strip():
            blocks.append(f"[Step {i}]\n{st['input'].strip()}")
    return (
        "A salesperson wrote the outreach steps below for one set of "
        "prospects. They sell offshore staff augmentation: dedicated "
        "professionals in the Philippines who fill a role on a U.S. "
        "company's team. They want to save the steps as a template to reuse "
        "for other companies and industries. Find the details that are "
        "specific to this one use and would have to change next time.\n\n"
        "Look for: the industry or market, the role or job title being "
        "offered, the work that role would take on, named current or past "
        "clients, named competitors, a city or region, the recipient's own "
        "first name, the recipient's own company.\n\n"
        "Return a JSON array, nothing else. Each item is "
        '{"text": "...", "name": "..."} where:\n'
        "- text is copied EXACTLY from the steps, character for character, "
        "and is the shortest phrase that carries the detail (for a list such "
        'as "invoicing and collections", the whole list is one item). One '
        'detail per item: "dispatchers for HVAC companies in Texas" is '
        "three items, dispatchers, HVAC and Texas.\n"
        "- name is one of Industry, Role, RoleWork, CurrentClients, "
        "Competitors, Location when it fits, FirstName for the recipient's "
        "first name, Company for the recipient's company, otherwise a short "
        "CamelCase name of your own. Two different details get two "
        "different names (two roles: Role and SecondRole); repeat a name "
        "only for the same detail written twice.\n\n"
        "Leave alone: anything already in {braces}, the Philippines, "
        "ThriveModal, the salesperson's own name, phone number or email, "
        "prices and percentages, and general wording that would be true for "
        "any company. If nothing is specific, return [].\n\n"
        + "\n\n".join(blocks)
    )


def _boundary_re(text: str):
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(text) + r"(?![A-Za-z0-9])")


def _occurs(text: str, hay: str) -> bool:
    """Whole-word match outside any existing {token}."""
    return bool(_boundary_re(text).search(
        re.sub(r"\{[^{}]*\}", "\x00", hay or "")))


def parse_detected(raw: str, steps) -> list:
    """The model's answer as a clean list of {"text", "name"}: only phrases
    that really are in the steps, each phrase once, no braces."""
    m = re.search(r"\[.*\]", raw or "", re.S)
    try:
        rows = json.loads(m.group(0)) if m else []
    except Exception:
        rows = []
    hay = "\n".join((st or {}).get(f) or "" for st in steps or []
                    for f in _TEXT_FIELDS)
    out, seen, said = [], set(), {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        text = str(r.get("text") or "").strip()
        name = clean_fillin_name(r.get("name"))
        if (len(text) < 2 or not name or "{" in text or "}" in text
                or text in seen or not _occurs(text, hay)):
            continue
        seen.add(text)
        if name not in MERGE_FIELDS:
            # One fill-in holds one answer. A different detail under a name
            # already taken gets its own (Role, Role2); the same detail
            # worded longer or shorter ("HVAC", "commercial HVAC") shares.
            base, n = name, 1
            while name in said and not any(
                    text.lower() in t or t in text.lower() for t in said[name]):
                n += 1
                name = f"{base}{n}"
            said.setdefault(name, []).append(text.lower())
        out.append({"text": text, "name": name})
    return out[:12]


def apply_detected(steps, found) -> list:
    """Copies of the steps with each found phrase replaced by its {Name}.
    Longest phrase first, whole words only, never inside an existing
    {token}."""
    found = sorted((f for f in found or [] if f.get("text") and f.get("name")),
                   key=lambda f: -len(f["text"]))

    def _sub(text):
        # Split on existing tokens so a phrase is never replaced inside one.
        # \x01...\x02 stand in for the new braces until every phrase is done,
        # so a shorter phrase cannot match inside a token just written.
        parts = re.split(r"(\{[^{}]*\})", text or "")
        for i in range(0, len(parts), 2):
            for f in found:
                chunks = re.split(r"(\x01[^\x02]*\x02)", parts[i])
                for j in range(0, len(chunks), 2):
                    chunks[j] = _boundary_re(f["text"]).sub(
                        "\x01" + f["name"] + "\x02", chunks[j])
                parts[i] = "".join(chunks)
        return "".join(parts).replace("\x01", "{").replace("\x02", "}")
    out = []
    for st in steps or []:
        st = dict(st or {})
        for f in _TEXT_FIELDS:
            if st.get(f):
                st[f] = _sub(st[f])
        out.append(st)
    return out


def style_fillins(steps, values=None) -> list:
    """What a saved campaign asks for next time: each fill-in with its label
    and the value used last (shown as a hint, never sent on its own)."""
    values = values or {}
    return [{"name": n, "label": fillin_label(n),
             "last": str(values.get(n) or "").strip()}
            for n in fillins(steps)]


def summary(steps) -> str:
    """'3 emails · 1 call · 1 LinkedIn' for a saved campaign's row."""
    types = [_type_of(st) for st in steps or []]
    bits = []
    for t, one, many in (("email", "email", "emails"), ("call", "call", "calls"),
                         ("linkedin", "LinkedIn", "LinkedIn")):
        n = types.count(t)
        if n:
            bits.append(f"{n} {one if n == 1 else many}")
    return " · ".join(bits)

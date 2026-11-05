"""Create my own campaign: the user's own steps turned into campaign emails.

The in-app walkthrough (flowdrip_app.p_seq_builder) and the API / MCP
style_id launch both come through here, so a step marked "My words" goes out
exactly as typed on either path. Only {FirstName}/{Company}-style merge
fields are filled, and that happens later at queue time, as for every
campaign. A step marked "AI polish" is passed to the caller's `polish`
function once, at build time, before anything is queued.

A saved campaign is reused for other clients, so anything specific to one
client is a {Fill-in} the user is asked for each time (see Fill-ins below).

No AI client and no app state here: the caller hands in `polish`.
"""
import json
import re

VOICE_MINE = "mine"
VOICE_POLISH = "polish"
VOICES = (VOICE_MINE, VOICE_POLISH)

# Where the candidate list goes in a step. Expanded at build time, never
# polished, so names and Ref #s stay exactly as the Pipeline has them.
CANDIDATES_TOKEN = "{Candidates}"

# Step type in the walkthrough -> step_type on a campaign step (flowdrip ST).
_STEP_TYPES = {"email": "email_auto", "call": "call", "linkedin": "linkedin"}
_STEP_NAMES = {"email": "Email", "call": "Call", "linkedin": "LinkedIn"}

FIRST_SUBJECT_FALLBACK = "Quick question, {FirstName}"

# One of the five main Sales Asset PDFs can go out with any email after the
# first. It is written for a role, a place and an industry, so a step that
# carries one asks for those three like any other fill-in.
PDF_KINDS = {
    "market_pulse": "Market Pulse",
    "interview_guide": "Interview Guide",
    "salary_guide": "Salary Guide",
    "scorecard": "Role Scorecard",
    "why_staffing": "Why Use a Staffing Firm",
}
PDF_FILLINS = ("Role", "Location", "Industry")
DEFAULT_TIME = "8:00 AM"


def voice_of(step) -> str:
    v = (step or {}).get("voice") or VOICE_MINE
    return v if v in VOICES else VOICE_MINE


CANDIDATE_BULLETS = 3


def candidate_block(cards, bullets: bool = True) -> str:
    """Plain-text candidate list for an email: one line per candidate, then
    (with `bullets`) a 3-bullet summary of each. Candidates go by a letter
    and their Ref # ('Candidate A (Ref #1042)'), never a name (Mike,
    2026-11-05): the Ref # is how we find them. A card's `letter` is its
    place in the campaign's list; without one, its place in `cards`."""
    out = []
    for i, c in enumerate(cards or []):
        if not isinstance(c, dict):
            continue
        letter = (c.get("letter") or "").strip() or chr(65 + i)
        label = f"Candidate {letter}"
        ref = (c.get("ref") or "").strip()
        if ref:
            label = f"{label} ({ref})"
        role = (c.get("role") or "").strip()
        lines = [f"{label}, {role}" if role else label]
        if bullets:
            lines += [f"  • {b.strip()}" for b in (c.get("bullets") or [])
                      if isinstance(b, str) and b.strip()][:CANDIDATE_BULLETS]
        out.append("\n".join(lines))
    return "\n\n".join(out)


def uses_candidates(steps) -> bool:
    return any(CANDIDATES_TOKEN in ((st or {}).get("input") or "")
               for st in steps or [])


# ── Candidates written into the message ──────────────────────────────────
# In the walkthrough each candidate's headline and highlights are written
# into the email as plain text, so the user writes around them and can
# change them. These find that text again: to take one candidate out, redo
# the bullets, keep it clear of an AI rewrite, or swap the lot back to
# {Candidates} when the campaign is saved for reuse.

_BULLET_LINE_RE = re.compile(r"^\s*[•·\-\*–]\s*\S")


def _headline_at(line: str, card: dict) -> bool:
    ref = (card.get("ref") or "").strip()
    if ref and ref in line:
        return True
    labels = [(card.get("label") or card.get("alias") or "").strip()]
    if (card.get("letter") or "").strip():
        labels.append(f"Candidate {card['letter'].strip()}")
    return any(lb and re.match(r"\s*" + re.escape(lb) + r"(?=$|[\s,(])", line)
               for lb in labels)


def _candidate_spans(lines, cards) -> list:
    """(first line, line after the last) of each card's headline and the
    bullet lines under it, in the order they sit in the text."""
    spans, taken = [], set()
    for c in cards or []:
        if not isinstance(c, dict):
            continue
        for i, ln in enumerate(lines):
            if i in taken or not _headline_at(ln, c):
                continue
            j = i + 1
            while (j < len(lines) and j not in taken
                   and _BULLET_LINE_RE.match(lines[j])):
                j += 1
            spans.append((i, j))
            taken.update(range(i, j))
            break
    return sorted(spans)


def _tidy(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text or "").strip()


def has_candidates(text: str, cards) -> bool:
    text = text or ""
    return CANDIDATES_TOKEN in text or bool(
        _candidate_spans(text.split("\n"), cards))


def lift_candidates(text: str, cards) -> tuple:
    """(the text with {Candidates} where the candidates were, their text as
    it is written now). Text with no candidate in it comes back as it is."""
    text = text or ""
    lines = text.split("\n")
    spans = _candidate_spans(lines, cards)
    if not spans:
        return text, ""
    block = "\n\n".join("\n".join(lines[a:b]) for a, b in spans)
    drop = {i for a, b in spans for i in range(a, b)}
    out = []
    for i, ln in enumerate(lines):
        if i == spans[0][0] and CANDIDATES_TOKEN not in text:
            out += ["", CANDIDATES_TOKEN, ""]
        if i not in drop:
            out.append(ln)
    return _tidy("\n".join(out)), block


def place_candidates(text: str, block: str) -> str:
    """The reverse of lift_candidates: the candidates' text goes where
    {Candidates} is, or at the end when the token is gone."""
    text = text or ""
    if not block:
        return text
    if CANDIDATES_TOKEN in text:
        head, tail = text.split(CANDIDATES_TOKEN, 1)
        return head + block + tail.replace(CANDIDATES_TOKEN, "")
    return (text.rstrip() + "\n\n" + block).strip()


def add_candidate(text: str, cards, chunk: str) -> str:
    """One more candidate written into the message: under the ones already
    there (`cards`), else where {Candidates} is, else at the end."""
    lines = (text or "").split("\n")
    spans = _candidate_spans(lines, cards)
    if not spans:
        return place_candidates(text, chunk)
    at = spans[-1][1]
    return _tidy("\n".join(lines[:at] + ["", chunk, ""] + lines[at:]))


def drop_candidate(text: str, card) -> str:
    """The message without this candidate's headline and bullets."""
    lines = (text or "").split("\n")
    spans = _candidate_spans(lines, [card])
    if not spans:
        return text or ""
    a, b = spans[0]
    return _tidy("\n".join(lines[:a] + lines[b:]))


def swap_candidate(text: str, card, chunk: str) -> str:
    """This candidate's text replaced by `chunk` (bullets on or off)."""
    lines = (text or "").split("\n")
    spans = _candidate_spans(lines, [card])
    if not spans:
        return text or ""
    a, b = spans[0]
    return "\n".join(lines[:a] + [chunk] + lines[b:])


def reletter(steps, cards) -> None:
    """After a candidate is taken out, the rest are lettered A, B, C... again
    in list order, on the cards and in every step's text (each card's old
    letter finds its headline). Letters only ever move down, so going in
    order never renames a line twice."""
    moves = []
    for i, c in enumerate(cards or []):
        if not isinstance(c, dict):
            continue
        new = chr(65 + i)
        if c.get("letter") and c["letter"] != new:
            moves.append((c["letter"], new))
        c["letter"] = new
    for st in steps or []:
        text = st.get("input") or ""
        for old, new in moves:
            text = re.sub(r"(?m)^(\s*)Candidate " + re.escape(old)
                          + r"(?=$|[\s,(])", r"\g<1>Candidate " + new,
                          text, count=1)
        st["input"] = text


def remove_candidates(text: str, cards) -> str:
    """The message with none of these candidates in it, and no {Candidates}
    spot left behind: an email the user chose to send without them."""
    for c in cards or []:
        text = drop_candidate(text, c)
    return _tidy((text or "").replace(CANDIDATES_TOKEN, ""))


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def body_html(text: str, cards) -> str:
    """An email with candidates in it, as the HTML it goes out as: each
    candidate's headline in bold and their highlights as a real bulleted
    list, so a long bullet wraps under its own words and not under the dot
    (Mike, 2026-11-05). The rest of the text keeps its line breaks. Text
    with no candidate in it comes back as it is."""
    lines = (text or "").split("\n")
    spans = {a: b for a, b in _candidate_spans(lines, cards)}
    if not spans:
        return text or ""
    out, i, after_list = [], 0, False
    while i < len(lines):
        if out and not after_list:
            out.append("<br>")
        after_list = False
        if i in spans:
            head, rows = lines[i].strip(), lines[i + 1:spans[i]]
            # Words in front of the candidate ("Meet Candidate A...") stay plain.
            m = re.search(r"Candidate [A-Z](?=$|[\s,(])", head)
            lead, head = (head[:m.start()], head[m.start():]) if m else ("", head)
            out.append(f"{_esc(lead)}<b>{_esc(head)}</b>")
            if rows:
                items = "".join(
                    '<li style="margin:0 0 4px 0;">'
                    + _esc(re.sub(r"^\s*[•·\-\*–]\s*", "", r)) + "</li>"
                    for r in rows)
                out.append('<ul style="margin:4px 0 0 0;padding-left:22px;">'
                           + items + "</ul>")
                after_list = True
            i = spans[i]
            continue
        out.append(_esc(lines[i]))
        i += 1
    return "".join(out)


def lift_steps(steps, cards) -> list:
    """Copies of the steps as a saved campaign keeps them: these candidates'
    text swapped for {Candidates}, so fresh ones are picked each time."""
    out = []
    for st in steps or []:
        st = dict(st or {})
        st["input"] = lift_candidates(st.get("input") or "", cards)[0]
        out.append(st)
    return out


def first_email_index(steps):
    """Index of the email that should carry the candidate list when the user
    has not placed it: the second email (the first follow-up), else the
    first one, else None."""
    emails = [i for i, st in enumerate(steps or [])
              if (st or {}).get("type", "email") == "email"]
    if not emails:
        return None
    return emails[1] if len(emails) > 1 else emails[0]


def missing_content(steps) -> list:
    """1-based step numbers that cannot go out yet: no body, or the first
    email with no subject line."""
    bad, seen_email = [], False
    for i, st in enumerate(steps or [], 1):
        st = st or {}
        if not (st.get("input") or "").strip():
            bad.append(i)
            continue
        if st.get("type", "email") == "email":
            if not seen_email and not (st.get("subject") or "").strip():
                bad.append(i)
            seen_email = True
    return bad


def step_problem(steps, i, values=None):
    """What step i still needs before the campaign can be saved, or None:
    "body" (nothing written), "subject" (the first email has no subject
    line) or ("fillin", name) for a fill-in used here with no value yet."""
    steps = steps or []
    st = steps[i] or {}
    if not (st.get("input") or "").strip():
        return "body"
    if (st.get("type", "email") == "email"
            and not (st.get("subject") or "").strip()
            and not any((x or {}).get("type", "email") == "email"
                        for x in steps[:i])):
        return "subject"
    values = values or {}
    need = [n for n in step_fillins(steps, i)
            if not str(values.get(n) or "").strip()]
    return ("fillin", need[0]) if need else None


def step_names(steps) -> list:
    """'Email 1', 'Call 1', 'Email 2'...: what each step is called on the
    page and in the built campaign."""
    counts, out = {}, []
    for st in steps or []:
        t = (st or {}).get("type")
        t = t if t in _STEP_TYPES else "email"
        counts[t] = counts.get(t, 0) + 1
        out.append(f"{_STEP_NAMES[t]} {counts[t]}")
    return out


def pdf_plan(steps) -> list:
    """(step index, kind) for each email that carries a PDF. Never the
    first email, and only the five known kinds."""
    out, seen_email = [], False
    for i, st in enumerate(steps or []):
        st = st or {}
        if (st.get("type") or "email") != "email":
            continue
        if seen_email and st.get("pdf") in PDF_KINDS:
            out.append((i, st["pdf"]))
        seen_email = True
    return out


def style_steps(steps) -> list:
    """The saved shape of the walkthrough's steps: only what a later launch
    needs, none of the page's working fields (_drafting, ai_prompt...)."""
    out, pdfs = [], dict(pdf_plan(steps))
    for i, st in enumerate(steps or []):
        st = st or {}
        t = st.get("type") if st.get("type") in _STEP_TYPES else "email"
        out.append({
            "type": t,
            "delay_days": 0 if i == 0 else max(0, int(st.get("delay_days") or 0)),
            "subject": (st.get("subject") or "").strip() if t == "email" else "",
            "input": (st.get("input") or "").strip(),
            "voice": voice_of(st),
        })
        if i in pdfs:
            out[-1]["pdf"] = pdfs[i]
    return out


def build_emails(steps, cards=None, polish=None, cand_bullets=True) -> list:
    """Campaign steps (the dicts save_campaign / queue_campaign_emails read)
    from the walkthrough's or a saved style's steps.

    "My words" text is used as typed. "AI polish" text goes through
    `polish(text, step_type)` first; if polish is None or fails, the
    user's own text is sent rather than nothing. {Candidates} becomes the
    candidate list after polishing (an empty string with no cards)."""
    block = candidate_block(cards, bullets=cand_bullets)
    out, counts, prev_subject = [], {}, ""
    for i, st in enumerate(style_steps(steps)):
        t = st["type"]
        text = st["input"]
        if st["voice"] == VOICE_POLISH and polish is not None and text:
            # Candidates written into the message are kept out of the
            # rewrite and put back as the user left them.
            text, written = lift_candidates(text, cards)
            try:
                polished = (polish(text, t) or "").strip()
            except Exception as e:
                print(f"[own_campaign] polish failed on step {i + 1}: {e}", flush=True)
                polished = ""
            if polished:
                # The model must keep the token; if it dropped it, put the
                # list back at the end rather than lose the candidates.
                if CANDIDATES_TOKEN in text and CANDIDATES_TOKEN not in polished:
                    polished = polished + "\n\n" + CANDIDATES_TOKEN
                text = polished
            if written:
                text = place_candidates(text, written)
        text = text.replace(CANDIDATES_TOKEN, block).strip()
        if t == "email":
            text = body_html(text, cards)

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
            "body": text,
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


def pdf_note(step, values=None) -> str:
    """What the AI is told when an email carries a Sales PDF: it is attached,
    what it covers, and the email should point to it. "" with no PDF."""
    kind = (step or {}).get("pdf")
    if kind not in PDF_KINDS or ((step or {}).get("type") or "email") != "email":
        return ""
    v = values or {}
    about = ", ".join(x for x in (
        f"the {v.get('Role')} role" if v.get("Role") else "",
        f"in {v.get('Location')}" if v.get("Location") else "",
        f"for {v.get('Industry')} companies" if v.get("Industry") else "") if x)
    return (f" A PDF called \"{PDF_KINDS[kind]}\" is attached to this email"
            + (f" (it covers {about})" if about else "")
            + ". Mention the attachment in one natural sentence and make it "
            "the reason the reader should open the email, for example: I've "
            "attached a short " + PDF_KINDS[kind].lower() + ". Do not invent "
            "figures from it.")


def polish_prompt(text: str, step_type: str, tone: str = "",
                  attach: str = "") -> str:
    """The instruction for one "AI polish" step. Light touch: the user's
    meaning, order and length stay; merge fields and {Candidates} stay
    exactly as written."""
    kind = {"email": "email body", "call": "phone call script",
            "linkedin": "LinkedIn message"}.get(step_type, "message")
    return (
        f"Lightly polish this recruiter's {kind}. It is their own writing, so "
        f"keep their meaning, their order and roughly their length. Fix "
        f"grammar, tighten wording and make it read naturally"
        + (f" in a {tone} tone" if tone else "") + ".\n\n"
        "Rules:\n"
        "- Keep everything in {braces} exactly as written, braces included: "
        "{FirstName}, {LastName}, {Company}, {JobTitle}, {Candidates} and "
        "any other, such as {Industry} or {Competitors}.\n"
        "- Do not add facts, numbers, names, links or promises that are not "
        "in the text.\n"
        "- No subject line, no signature, no sign-off name.\n"
        "- Do not use em dashes.\n"
        + (f"- A PDF ({attach}) is attached to this email. If the text does "
           f"not already point to the attachment, add one short sentence "
           f"saying it is attached.\n" if attach else "") +
        "- Return only the polished text, nothing before or after it.\n\n"
        f"TEXT:\n{text}"
    )


# ── Fill-ins: what changes each time a saved campaign is used ────────────
# A saved campaign is meant to be reused for another client or industry, so
# anything client-specific lives in the text as a {Token}. Per-contact merge
# fields are filled at queue time as always; every other token is a fill-in
# the user is asked for each time they use the campaign.

MERGE_FIELDS = ("FirstName", "LastName", "Company", "CompanyName", "JobTitle")
_RESERVED = MERGE_FIELDS + ("Candidates",)
_TOKEN_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9]*)\}")
_TEXT_FIELDS = ("subject", "input")


def fillin_label(name: str) -> str:
    """'CurrentClients' -> 'Current clients', 'Role2' -> 'Role 2'."""
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Za-z])(?=\d+$)", " ",
                   name or "").split()
    return " ".join([words[0]] + [w.lower() for w in words[1:]]) if words else ""


def clean_fillin_name(raw) -> str:
    """A token name from whatever the model or user called it: letters and
    digits only, CamelCase, never Candidates."""
    parts = re.findall(r"[A-Za-z0-9]+", str(raw or ""))
    name = "".join(p[:1].upper() + p[1:] for p in parts)
    if not name or not name[0].isalpha() or name == "Candidates":
        return ""
    return name[:40]


def fillins(steps) -> list:
    """Fill-in names the steps ask for, in first-seen order: the tokens in
    the text, then what an attached PDF needs. Merge fields and
    {Candidates} are not fill-ins."""
    seen = []
    for st in steps or []:
        for f in _TEXT_FIELDS:
            for name in _TOKEN_RE.findall((st or {}).get(f) or ""):
                if name not in _RESERVED and name not in seen:
                    seen.append(name)
    if pdf_plan(steps):
        seen += [n for n in PDF_FILLINS if n not in seen]
    return seen


def step_fillins(steps, i) -> list:
    """What step i on its own asks for: its tokens, plus the PDF's three
    when it carries one."""
    seen = fillins([(steps or [])[i]])
    if i in dict(pdf_plan(steps)):
        seen += [n for n in PDF_FILLINS if n not in seen]
    return seen


def missing_fillins(steps, values) -> list:
    values = values or {}
    return [n for n in fillins(steps) if not str(values.get(n) or "").strip()]


def fill(steps, values) -> list:
    """Copies of the steps with each fill-in that has a value written in.
    Merge fields, {Candidates} and fill-ins without a value are left."""
    values = {k: str(v).strip() for k, v in (values or {}).items()
              if k not in _RESERVED and str(v or "").strip()}

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
    client, so they can become fill-ins. Exact substrings only: the caller
    replaces text, it never rewrites."""
    blocks = []
    for i, st in enumerate(steps or [], 1):
        st = st or {}
        if (st.get("subject") or "").strip():
            blocks.append(f"[Step {i} subject]\n{st['subject'].strip()}")
        if (st.get("input") or "").strip():
            blocks.append(f"[Step {i}]\n{st['input'].strip()}")
    return (
        "A recruiter wrote the outreach steps below for one client. They "
        "want to save them as a template to reuse for other clients and "
        "industries. Find the details that are specific to this one use and "
        "would have to change next time.\n\n"
        "Look for: the industry or market, the roles or job titles being "
        "pitched, named competitors, named current or past clients, a city "
        "or region, the recipient's own first name, the recipient's own "
        "company.\n\n"
        "Return a JSON array, nothing else. Each item is "
        '{"text": "...", "name": "..."} where:\n'
        "- text is copied EXACTLY from the steps, character for character, "
        "and is the shortest phrase that carries the detail (for a list such "
        'as "Trane and Carrier", the whole list is one item). One detail '
        'per item: "HVAC estimators in Denver" is three items, HVAC, '
        "estimators and Denver.\n"
        "- name is one of Industry, Competitors, CurrentClients, Role, "
        "Location when it fits, FirstName for the recipient's first name, "
        "Company for the recipient's company, otherwise a short CamelCase "
        "name of your own. Two different details get two different names "
        "(two roles: Role and SecondRole); repeat a name only for the same "
        "detail written twice.\n\n"
        "Leave alone: anything already in {braces}, the recruiter's own "
        "name, their firm, their phone number or email, and general wording "
        "that would be true for any client. If nothing is specific, return "
        "[].\n\n" + "\n\n".join(blocks)
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


def draft_rules() -> str:
    """Added to the one-step AI draft: the user's details as they gave them,
    nothing made up, no placeholders left to fill."""
    return (
        "- Do not invent an industry, client names, competitor names, a "
        "role or a city. If the user's direction or the other steps name "
        "one, write it as they gave it; otherwise word the sentence so it "
        "reads well without one.\n"
        "- Leave nothing to fill in later: no [square bracket] placeholders "
        "and nothing in {braces} except the merge fields above and "
        "{Candidates}.\n"
        "- If the direction says to pitch or list candidates, put "
        "{Candidates} on its own line where the list goes and do not "
        "describe any candidate yourself.\n")


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

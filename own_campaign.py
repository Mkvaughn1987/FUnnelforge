"""Create my own campaign: the user's own steps turned into campaign emails.

The in-app walkthrough (flowdrip_app.p_seq_builder) and the API / MCP
style_id launch both come through here, so a step marked "My words" goes out
exactly as typed on either path. Only {FirstName}/{Company}-style merge
fields are filled, and that happens later at queue time, as for every
campaign. A step marked "AI polish" is passed to the caller's `polish`
function once, at build time, before anything is queued.

No AI client and no app state here: the caller hands in `polish`.
"""

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
DEFAULT_TIME = "8:00 AM"


def voice_of(step) -> str:
    v = (step or {}).get("voice") or VOICE_MINE
    return v if v in VOICES else VOICE_MINE


def candidate_block(cards) -> str:
    """Plain-text candidate list for an email: one line per candidate, then
    their highlight bullets. Uses the card label ('Travis K.') and Ref #
    exactly as linked; never a real full name."""
    out = []
    for c in cards or []:
        if not isinstance(c, dict):
            continue
        label = (c.get("label") or c.get("alias") or "Candidate").strip()
        ref = (c.get("ref") or "").strip()
        if ref and ref not in label:
            label = f"{label} ({ref})"
        role = (c.get("role") or "").strip()
        lines = [f"{label}, {role}" if role else label]
        lines += [f"  • {b.strip()}" for b in (c.get("bullets") or [])
                  if isinstance(b, str) and b.strip()]
        out.append("\n".join(lines))
    return "\n\n".join(out)


def uses_candidates(steps) -> bool:
    return any(CANDIDATES_TOKEN in ((st or {}).get("input") or "")
               for st in steps or [])


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


def style_steps(steps) -> list:
    """The saved shape of the walkthrough's steps: only what a later launch
    needs, none of the page's working fields (_drafting, ai_prompt...)."""
    out = []
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
    return out


def build_emails(steps, cards=None, polish=None) -> list:
    """Campaign steps (the dicts save_campaign / queue_campaign_emails read)
    from the walkthrough's or a saved style's steps.

    "My words" text is used as typed. "AI polish" text goes through
    `polish(text, step_type)` first; if polish is None or fails, the
    user's own text is sent rather than nothing. {Candidates} becomes the
    candidate list after polishing (an empty string with no cards)."""
    block = candidate_block(cards)
    out, counts, prev_subject = [], {}, ""
    for i, st in enumerate(style_steps(steps)):
        t = st["type"]
        text = st["input"]
        if st["voice"] == VOICE_POLISH and polish is not None and text:
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
        text = text.replace(CANDIDATES_TOKEN, block).strip()

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


def polish_prompt(text: str, step_type: str, tone: str = "") -> str:
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
        "- Keep every merge field exactly as written, braces included: "
        "{FirstName}, {LastName}, {Company}, {JobTitle}, {Candidates}.\n"
        "- Do not add facts, numbers, names, links or promises that are not "
        "in the text.\n"
        "- No subject line, no signature, no sign-off name.\n"
        "- Do not use em dashes.\n"
        "- Return only the polished text, nothing before or after it.\n\n"
        f"TEXT:\n{text}"
    )

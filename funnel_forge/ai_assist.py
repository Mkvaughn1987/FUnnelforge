# ai_assist.py
# ChatGPT (OpenAI) integration for FunnelForge email generation

import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"

AVAILABLE_MODELS = [
    ("gpt-4o-mini", "GPT-4o Mini  (Fast & cheap)"),
    ("gpt-4o", "GPT-4o  (Best quality)"),
    ("gpt-4-turbo", "GPT-4 Turbo  (High quality)"),
]

MODEL_IDS = [m[0] for m in AVAILABLE_MODELS]
MODEL_LABELS = [m[1] for m in AVAILABLE_MODELS]


def _label_to_model(label: str) -> str:
    """Convert a display label back to a model ID."""
    for mid, mlabel in AVAILABLE_MODELS:
        if mlabel == label:
            return mid
    return DEFAULT_MODEL


def call_openai(api_key: str, messages: list, model: str = DEFAULT_MODEL,
                temperature: float = 0.7, max_tokens: int = 2500) -> str:
    """Make a synchronous call to the OpenAI Chat Completions API."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = Request(
        OPENAI_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", body)
        except Exception:
            msg = body
        if e.code == 401:
            raise ValueError("Invalid API key. Check your OpenAI API key in Settings.") from e
        elif e.code == 429:
            raise ValueError("Rate limit exceeded. Wait a moment and try again.") from e
        elif e.code == 402:
            raise ValueError("OpenAI billing issue. Check your account at platform.openai.com.") from e
        else:
            raise ValueError(f"OpenAI error ({e.code}): {msg}") from e
    except URLError as e:
        raise ValueError(f"Network error: {e.reason}. Check your internet connection.") from e


def call_openai_async(api_key: str, messages: list, callback, error_callback,
                      model: str = DEFAULT_MODEL, temperature: float = 0.7):
    """Call OpenAI in a background thread. Calls callback(result) or error_callback(error_msg)."""
    def _run():
        try:
            result = call_openai(api_key, messages, model=model, temperature=temperature)
            callback(result)
        except Exception as e:
            error_callback(str(e))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ── Streaming support ──

def call_openai_stream(api_key: str, messages: list, on_chunk, on_done,
                       on_error, model: str = DEFAULT_MODEL,
                       temperature: float = 0.7, max_tokens: int = 2500):
    """Stream OpenAI response in a background thread.

    on_chunk(text)  — called for each token/chunk of text
    on_done(full)   — called when streaming completes with the full text
    on_error(msg)   — called on error
    """
    def _run():
        full_text = ""
        try:
            payload = json.dumps({
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }).encode("utf-8")

            req = Request(
                OPENAI_API_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urlopen(req, timeout=120) as resp:
                buffer = ""
                while True:
                    chunk = resp.read(1)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="replace")

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        if line == "data: [DONE]":
                            on_done(full_text)
                            return
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_text += content
                                    on_chunk(content)
                            except (json.JSONDecodeError, KeyError, IndexError):
                                pass

                # If we exit the loop without [DONE], still call on_done
                if full_text:
                    on_done(full_text)

        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                err = json.loads(body)
                msg = err.get("error", {}).get("message", body)
            except Exception:
                msg = body
            if e.code == 401:
                on_error("Invalid API key. Check your OpenAI API key in Settings.")
            elif e.code == 429:
                on_error("Rate limit exceeded. Wait a moment and try again.")
            elif e.code == 402:
                on_error("OpenAI billing issue. Check your account at platform.openai.com.")
            else:
                on_error(f"OpenAI error ({e.code}): {msg}")
        except URLError as e:
            on_error(f"Network error: {e.reason}. Check your internet connection.")
        except Exception as e:
            on_error(str(e))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ── Pre-built prompts ──

SYSTEM_PROMPT = (
    "You are an expert sales email copywriter. You write concise, professional, "
    "personalized cold outreach emails for B2B sales. Your emails are direct, "
    "value-focused, and avoid sounding generic or spammy. Keep emails under 150 words "
    "unless asked otherwise. Do not include subject lines unless specifically asked. "
    "Do not include greetings like 'Dear' — use 'Hi {FirstName},' as the greeting. "
    "Use {FirstName}, {LastName}, {Company}, {Title} as merge variables when personalizing."
)

SCHEDULE_PROMPT = (
    "You are an expert B2B sales strategist who specializes in cold email outreach cadences. "
    "You analyze the actual email content to recommend the optimal send schedule — how many "
    "business days between each email and what time of day to send. Consider the tone, "
    "urgency, audience, and progression of the sequence. Your recommendations are backed "
    "by data and best practices for cold outreach."
)

RESEARCH_PROMPT = (
    "You are a B2B sales researcher. Given a company name (and optionally a website URL "
    "or notes), produce a concise company brief for a sales rep. Include:\n"
    "- What the company does (1-2 sentences)\n"
    "- Industry and approximate size\n"
    "- Key decision-makers / typical org structure\n"
    "- Recent news or developments (if known)\n"
    "- Pain points relevant to staffing, recruiting, or workforce solutions\n"
    "- Suggested talking points for outreach\n\n"
    "Keep the brief under 200 words. Be specific and actionable."
)

TOUCHPOINT_PROMPT = (
    "You are an expert B2B sales copywriter who writes across multiple outreach channels. "
    "You adapt your style to the channel — concise for LinkedIn, conversational for phone, "
    "professional for email. You focus on value and personalization. "
    "Use {FirstName}, {LastName}, {Company}, {Title} as merge variables."
)


def _effective(base_prompt: str, custom_context: str = "") -> str:
    """Combine a base system prompt with optional custom training context."""
    if not custom_context:
        return base_prompt
    return f"{base_prompt}\n\n{custom_context}"


def build_write_email_messages(prompt: str, email_position: str = "",
                               sequence_context: str = "", custom_context: str = "") -> list:
    """Build messages for writing a new email from scratch."""
    user_msg = prompt
    if email_position:
        user_msg = f"[This is {email_position} in a multi-email drip sequence.]\n\n{user_msg}"
    if sequence_context:
        user_msg = f"{user_msg}\n\n[Context about previous emails in the sequence: {sequence_context}]"
    return [
        {"role": "system", "content": _effective(SYSTEM_PROMPT, custom_context)},
        {"role": "user", "content": user_msg},
    ]


def build_improve_email_messages(current_body: str, instruction: str = "",
                                 custom_context: str = "") -> list:
    """Build messages for improving/rewriting an existing email."""
    task = instruction if instruction else "Improve this email. Make it more concise, compelling, and professional."
    return [
        {"role": "system", "content": _effective(SYSTEM_PROMPT, custom_context)},
        {"role": "user", "content": f"{task}\n\nCurrent email:\n\n{current_body}"},
    ]


def build_subject_line_messages(email_body: str, count: int = 5,
                                custom_context: str = "") -> list:
    """Build messages for generating subject line options."""
    return [
        {"role": "system", "content": _effective(SYSTEM_PROMPT, custom_context)},
        {"role": "user", "content": (
            f"Generate {count} compelling subject lines for this email. "
            f"Return ONLY the subject lines, one per line, numbered 1-{count}. "
            f"Keep them under 60 characters. Make them specific and curiosity-driving.\n\n"
            f"Email body:\n\n{email_body}"
        )},
    ]


def build_tone_change_messages(current_body: str, tone: str,
                               custom_context: str = "") -> list:
    """Build messages for changing the tone of an email."""
    return [
        {"role": "system", "content": _effective(SYSTEM_PROMPT, custom_context)},
        {"role": "user", "content": (
            f"Rewrite this email with a {tone} tone. Keep the same core message "
            f"and merge variables (like {{FirstName}}, {{Company}}). "
            f"Return ONLY the rewritten email body.\n\n{current_body}"
        )},
    ]


def build_schedule_messages(num_emails: int, context: str,
                            custom_context: str = "") -> list:
    """Build messages for recommending an optimal email schedule based on email content."""
    return [
        {"role": "system", "content": _effective(SCHEDULE_PROMPT, custom_context)},
        {"role": "user", "content": (
            f"I have a {num_emails}-email cold outreach drip sequence. "
            f"Analyze the emails below and recommend the best send schedule.\n\n"
            f"Here are my emails:\n\n{context}\n\n"
            f"Return ONLY a structured schedule in this exact format, one line per email:\n"
            f"Email 1: Day 0, 9:00 AM\n"
            f"Email 2: Day 3, 8:30 AM\n"
            f"Email 3: Day 7, 10:00 AM\n"
            f"...etc\n\n"
            f"Rules:\n"
            f"- Day 0 = the first send date\n"
            f"- Use business days (Mon-Fri only)\n"
            f"- Times should be in HH:MM AM/PM format\n"
            f"- After the schedule, add a blank line then a SHORT explanation (2-3 sentences max) "
            f"of why you chose this cadence based on the email content.\n"
            f"- Do NOT include anything else — no subject lines, no email bodies."
        )},
    ]


def build_sequence_messages(num_emails: int, context: str,
                            custom_context: str = "") -> list:
    """Build messages for generating an entire email sequence."""
    return [
        {"role": "system", "content": _effective(SYSTEM_PROMPT, custom_context)},
        {"role": "user", "content": (
            f"Write a {num_emails}-email cold outreach drip sequence.\n\n"
            f"Context: {context}\n\n"
            f"Return the result as valid JSON in this exact format:\n"
            f'{{"emails": [\n'
            f'  {{"subject": "Subject line here", "body": "Email body here"}},\n'
            f'  {{"subject": "Subject line here", "body": "Email body here"}}\n'
            f"]}}\n\n"
            f"Rules:\n"
            f"- Use merge variables: {{FirstName}}, {{LastName}}, {{Company}}, {{Title}}\n"
            f"- Keep each email under 150 words\n"
            f"- Make each one distinct — different angle, different value prop\n"
            f"- The final email should be a polite breakup/last chance\n"
            f"- Return ONLY the JSON, no markdown fences, no extra text"
        )},
    ]


def build_sequence_messages_legacy(num_emails: int, context: str,
                                   custom_context: str = "") -> list:
    """Build messages for generating a sequence (legacy text format fallback)."""
    return [
        {"role": "system", "content": _effective(SYSTEM_PROMPT, custom_context)},
        {"role": "user", "content": (
            f"Write a {num_emails}-email cold outreach drip sequence.\n\n"
            f"Context: {context}\n\n"
            f"For each email, provide:\n"
            f"- A subject line\n"
            f"- The email body\n\n"
            f"Use merge variables: {{FirstName}}, {{LastName}}, {{Company}}, {{Title}}\n"
            f"Start each email with: --- Email N: [Subject Line] ---\n"
            f"Keep each email under 150 words. Make each one distinct — different angle, "
            f"different value prop. The final email should be a polite breakup/last chance."
        )},
    ]


# ── New: Company Research ──

def build_company_research_messages(company_name: str, website_url: str = "",
                                     notes: str = "", custom_context: str = "") -> list:
    """Build messages for AI company research."""
    user_parts = [f"Research this company for me: {company_name}"]
    if website_url:
        user_parts.append(f"Website: {website_url}")
    if notes:
        user_parts.append(f"Additional notes: {notes}")
    return [
        {"role": "system", "content": _effective(RESEARCH_PROMPT, custom_context)},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


# ── New: Touchpoint Copy (Call Scripts, LinkedIn, Voicemail) ──

def build_call_script_messages(context: str, custom_context: str = "") -> list:
    """Build messages for generating a phone call script."""
    return [
        {"role": "system", "content": _effective(TOUCHPOINT_PROMPT, custom_context)},
        {"role": "user", "content": (
            f"Write a cold call script for a sales rep. Include:\n"
            f"- Opening line (who you are, why you're calling — under 15 seconds)\n"
            f"- Value proposition (1-2 sentences)\n"
            f"- 2-3 discovery questions\n"
            f"- Objection handling for 'not interested' and 'send me info'\n"
            f"- Close / next step ask\n\n"
            f"Context: {context}\n\n"
            f"Keep it conversational, not robotic. Total script under 200 words."
        )},
    ]


def build_linkedin_message_messages(context: str, message_type: str = "connection",
                                     custom_context: str = "") -> list:
    """Build messages for generating LinkedIn messages."""
    if message_type == "connection":
        task = (
            "Write a LinkedIn connection request message. "
            "Must be under 300 characters (LinkedIn limit). "
            "Be personal, reference something specific, no sales pitch."
        )
    elif message_type == "followup":
        task = (
            "Write a LinkedIn follow-up DM after they accepted your connection. "
            "Keep it under 150 words. Be conversational, provide value, "
            "soft ask for a meeting or call."
        )
    else:
        task = (
            "Write a LinkedIn InMail message. Under 200 words. "
            "Professional but not stiff. Lead with value, end with a clear ask."
        )
    return [
        {"role": "system", "content": _effective(TOUCHPOINT_PROMPT, custom_context)},
        {"role": "user", "content": f"{task}\n\nContext: {context}"},
    ]


def build_voicemail_script_messages(context: str, custom_context: str = "") -> list:
    """Build messages for generating a voicemail drop script."""
    return [
        {"role": "system", "content": _effective(TOUCHPOINT_PROMPT, custom_context)},
        {"role": "user", "content": (
            f"Write a voicemail script for a cold outreach call. Rules:\n"
            f"- Must be under 30 seconds when spoken (roughly 75 words)\n"
            f"- State your name, company, and one specific reason for calling\n"
            f"- End with your phone number (use {{Phone}} as placeholder)\n"
            f"- Sound natural, not scripted\n"
            f"- Do NOT ask them to call back — create curiosity instead\n\n"
            f"Context: {context}"
        )},
    ]


# ── JSON parsing helpers ──

def parse_campaign_json(response_text: str) -> list:
    """Parse a JSON campaign response into [(name, subject, body), ...].
    Returns empty list if parsing fails."""
    try:
        # Strip markdown code fences if present
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()

        data = json.loads(text)
        emails = data.get("emails", [])
        result = []
        for i, em in enumerate(emails, 1):
            subject = em.get("subject", "").strip()
            body = em.get("body", "").strip()
            name = f"Email {i}"
            result.append((name, subject, body))
        return result
    except (json.JSONDecodeError, KeyError, TypeError):
        return []

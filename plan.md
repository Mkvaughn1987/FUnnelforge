# FunnelForge AI Enhancement Plan

## Overview
Upgrade the AI system across two tiers: **Quick Wins** (model selector, streaming, regenerate/chat) and **Medium Efforts** (company research, touchpoint copy, JSON-mode parsing).

---

## 1. Model Selector Dropdown
**File: `ai_assist.py`**
- Add `AVAILABLE_MODELS` list: `gpt-4o-mini`, `gpt-4o`, `gpt-4-turbo`
- Add `get_default_model()` / `set_default_model()` that read/write to config

**File: `app.py`**
- Add a model dropdown (`ttk.Combobox`) to the header of AI Assist and AI Campaign dialogs (next to the "API Key" button)
- Selected model passed through to `call_openai_async()` calls
- Persist last-used model in config so it remembers between sessions
- Also add model selector to Train Your AI screen as a global default

---

## 2. Streaming Responses
**File: `ai_assist.py`**
- New function `call_openai_stream()` that sets `"stream": true` in the payload
- Reads SSE chunks from the response, yields each `delta.content` token
- New `call_openai_stream_async()` that runs in a thread and calls `on_chunk(text)` for each token plus `on_done()` at the end

**File: `app.py`**
- AI Assist and AI Campaign preview text widgets update live as chunks arrive
- Result text widget enabled during streaming, disabled after
- "Generate" button shows "Stop" during streaming (cancels the thread)
- Status label shows token count or "Streaming..." during generation

---

## 3. Iterative Chat / Regenerate
**File: `ai_assist.py`**
- No changes needed — message builders already return `list[dict]`, we just keep appending

**File: `app.py` (AI Assist dialog)**
- Add conversation history list `chat_history = []` in the dialog
- After a result comes back, append both the user message and assistant response to `chat_history`
- Add a **"Refine"** text input below the preview — user types "make it shorter", "more casual", etc.
- "Refine" sends the full `chat_history` + new user message to OpenAI (true multi-turn)
- Add **"Regenerate"** button next to Generate — re-sends the same prompt for a fresh take
- Add **"Undo"** button — reverts to previous result in history

---

## 4. AI Company Research (`{CompanyBrief}` token)
**File: `ai_assist.py`**
- New function `build_company_research_messages(company_name, website_url="", notes="")`
- System prompt: "You are a B2B sales researcher. Given a company name, produce a concise brief: what they do, industry, size, recent news, key pain points for staffing/recruiting outreach."
- Returns structured brief text

**File: `app.py`**
- New **"Research Company"** button in the contact/campaign workflow
- Dialog: user enters company name + optional URL/notes
- AI returns a brief, user can edit it, then save
- Brief stored per-contact or per-campaign as `company_brief` field
- New merge token `{CompanyBrief}` available in email templates
- Add `{CompanyBrief}` to the token picker dropdown alongside existing tokens

---

## 5. AI Touchpoint Copy (Call Scripts, LinkedIn, Voicemail)
**File: `ai_assist.py`**
- New prompt builders:
  - `build_call_script_messages(context, custom_context)` — generates a phone call script with opener, value prop, objection handling, close
  - `build_linkedin_message_messages(context, custom_context)` — generates a LinkedIn connection request or DM
  - `build_voicemail_script_messages(context, custom_context)` — generates a 30-second voicemail drop script
- Each uses appropriate system prompt for that channel

**File: `app.py` (AI Assist dialog)**
- Extend action selector with new options: "Call Script", "LinkedIn DM", "Voicemail"
- These generate copy in the preview panel (same flow as existing actions)
- "Insert" puts the text into the email body (for reference/notes) or copies to clipboard
- Future: these tie into the Playbook touchpoint system (Phase 1 from earlier discussion)

---

## 6. JSON-Mode Parsing (Smarter Output)
**File: `ai_assist.py`**
- For `build_sequence_messages()`: add `response_format={"type": "json_object"}` to the API call
- Update prompt to request JSON output: `{"emails": [{"subject": "...", "body": "..."}, ...]}`
- New `parse_campaign_json(response_text)` function — simple `json.loads()` instead of fragile regex
- Keep regex fallback for backward compatibility if JSON parse fails
- Apply same pattern to `build_schedule_messages()` and `build_subject_line_messages()`

**File: `app.py`**
- `_parse_campaign()` tries JSON parse first, falls back to regex
- `_parse_schedule()` tries JSON parse first, falls back to regex
- Much more reliable output handling

---

## Implementation Order
1. **Model selector** — smallest change, immediate value
2. **JSON-mode parsing** — fixes fragile parsing, needed before streaming
3. **Streaming responses** — biggest UX improvement
4. **Regenerate / iterative chat** — builds on streaming
5. **Company research** — new feature, self-contained
6. **Touchpoint copy** — extends AI Assist, builds toward playbook vision

## Files Changed
- `funnel_forge/ai_assist.py` — new functions, streaming, JSON mode
- `funnel_forge/app.py` — UI updates to AI dialogs, new company research dialog
- `funnel_forge/styles.py` — possibly new config keys for model preference

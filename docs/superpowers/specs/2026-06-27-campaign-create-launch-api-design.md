# Campaign Create + Launch API (Phase 1) — Design

**Date:** 2026-06-27
**Status:** Awaiting user review

## Problem

Creating a campaign today means a ~10-minute click-through of the AICB wizard
(pick template → enter company/role/location → enter/generate candidates → AI-generate
emails → add contacts → set dates → launch). The user wants to skip the wizard: POST a
campaign spec (company, domain, candidates, cadence, contacts) and have the server
create **and launch** the campaign in one call — so an external agent ("co-work") can
drive campaigns programmatically.

## Goal

A single authenticated `POST /api/v1/campaigns` that accepts a high-level spec, runs the
**same AI generation the wizard uses** (full parity), creates the campaign in the
calling user's account, launches it (queues the sends), and returns the campaign id +
the resolved schedule.

## Decisions (locked with user, 2026-06-27)

- **Copy source = server AI-generates** (full wizard parity), not caller-supplied copy.
- **Auth = per-user API key.** The key authenticates AND selects the owning account; the
  owner is taken from the key, never from the request body.
- **Cadence = start_date + template delays.** Caller sends one `start_date`; steps fall
  on the template's relative offsets (4×4: emails day 0/3/7/11, call same-day as email 2).
- **Reuse model = extract shared core + rewire the wizard.** One headless generation
  function is the single source of truth; both the wizard and the API call it.
- **Key minting = CLI helper** for v1 (`scripts/mint_api_key.py`); self-serve UI button
  deferred.

## Non-Goals (deferred to later phases)

- Explicit per-step dates (caller-specified date per step).
- Résumé-PDF generation/attachment via the API.
- Custom / "BYOS" (bring-your-own-sequence) campaigns — Phase 1 is templates only.
- Async processing, status polling, webhooks. Phase 1 is a synchronous request.
- Self-serve API-key UI in Settings.
- Rate limiting / quota (note as future hardening).

## Architecture

Four units, almost all in `flowdrip_app.py` (the generation helpers it depends on
— `_DRIPDROP_PLAYBOOK`, `_style_guide_prompt`, `_fetch_cited_market_stats`,
`_claude_create_with_retry`, `_humanize_email_text`, `_wrap_4x4_font`,
`_spread_email_times`, `AICB_CAMPAIGN_TYPES` — are all module-level there).

### 1. Per-user API key store (auth + tenancy)

- Global store file `api_keys.json` under the data root (alongside other server data),
  mapping `sha256(plaintext_key) → {"email": ..., "label": ..., "created": ISO8601}`.
- Plaintext key format: `dd_live_<32+ url-safe random chars>` (via `secrets.token_urlsafe`).
  Stored **hashed** (SHA-256); plaintext is shown once at mint time and never persisted.
- Helpers in `flowdrip_app.py`:
  - `_api_keys_path() -> Path` — resolves the store path.
  - `_hash_api_key(key: str) -> str` — `sha256` hex.
  - `_mint_api_key(email: str, label: str = "") -> str` — generates a key, writes its hash
    → email mapping, returns the plaintext (caller shows it once).
  - `_resolve_api_key(key: str) -> str | None` — returns the owner email for a valid key,
    else `None`. Constant-time comparison is unnecessary because lookup is by hash key,
    but the raw key is never logged.
- CLI: `scripts/mint_api_key.py <email> [label]` imports `flowdrip_app`, calls
  `_mint_api_key`, prints the plaintext once.

### 2. Headless generation function

```python
def generate_aicb_campaign(
    client,                       # Anthropic client
    *,
    camp_type: str,               # e.g. "fourbyfour"
    company: str = "",
    website: str = "",
    niche: str = "",
    industry: str = "",
    roles: list[str] | None = None,
    location: str = "",
    candidate_cards: list[dict] | None = None,
) -> dict:                        # {"synopsis": str, "campaign_name": str, "emails": [step, ...]}
```

Contains the wizard's existing pipeline, lifted out of the NiceGUI handler and
parameterized (no reads of the session object `s`):

1. **Research** — build the niche- or company-mode research prompt (injection-guarded,
   restricted web-search domains) → Haiku → `brief`.
2. **Candidate block** — format `candidate_cards` into the CANDIDATE HIGHLIGHTS block
   (the existing `_cand_block` logic).
3. **Cited stats** — for `fourbyfour`, fetch live cited market stats (existing
   `_fetch_cited_market_stats` / `_format_cited_stats_block`).
4. **Campaign build** — assemble the campaign prompt from the template's `touch_sequence`
   (`AICB_CAMPAIGN_TYPES`) + playbook + style guide → Haiku → JSON `{synopsis,
   campaign_name, emails[]}`.
5. **Post-process** — the existing per-email pass: markdown→HTML, `Hi {FirstName},`
   prefix, sign-off strip, `_humanize_email_text`, `_strip_dashes`, 4×4 font wrap,
   `_spread_email_times`.

Returns the `campaign_data` dict. **Résumé-PDF generation is NOT part of this function**
(it stays in the UI handler and is skipped by the API in Phase 1).

**Wizard rewire:** the existing AICB generation handler is changed to call
`generate_aicb_campaign(...)` with the values it currently derives from `s`, replacing
the inline research+build+post-process block. The handler keeps its UI concerns
(spinner state, the parallel résumé-PDF thread, writing results to `s.aicb_docs`,
error surfacing via `s._aicb_error`).

### 3. The route — `POST /api/v1/campaigns`

Registered like the other raw FastAPI routes (`@app.post(...)` on NiceGUI's `app`).

Request body (JSON):
```json
{
  "template": "fourbyfour",
  "name": "Acme - Plant Manager (optional override)",
  "company": "Acme Manufacturing",
  "website": "acme.com",
  "niche": "food processing",
  "industry": "manufacturing",
  "roles": ["Plant Manager", "Quality Manager"],
  "location": "Windsor, CO",
  "start_date": "2026-07-06",
  "candidates": [
    {"label": "Candidate A", "role": "Plant Manager", "years": 12,
     "bullets": ["...", "..."], "location": "Windsor, CO", "target_salary": "$140k"}
  ],
  "contacts": [
    {"email": "vp@acme.com", "first_name": "Dana", "last_name": "Lee",
     "company": "Acme", "title": "VP Ops"}
  ]
}
```
- `contacts` may instead be supplied as `"contacts_csv": "<raw csv text>"`; the endpoint
  parses it (stdlib `csv`) into the same contact dicts. Column names map via the existing
  `_norm_contact` aliases (`Email/email`, `FirstName/first_name`, …).

Handler steps:
1. Read `Authorization: Bearer <key>` (or `X-API-Key`). `_resolve_api_key` → `email`,
   else `401`.
2. Validate: `template` in `AICB_CAMPAIGN_TYPES` keys (else `400`); at least one of
   `company`/`niche` present (else `400`); valid `start_date` ISO (else `400`);
   `contacts`/`contacts_csv` parse to ≥0 rows.
3. Bind user context: `_CURRENT_USER_EMAIL.set(email)`, `_switch_to_user_paths(email)`.
4. `client = Anthropic(api_key=ANTHROPIC_API_KEY)` (guard: `503` if key unset).
5. `campaign_data = generate_aicb_campaign(client, camp_type=template, ...)`.
6. Assemble `camp` dict:
   - `name` = body `name` or `campaign_data["campaign_name"]`.
   - `emails` = `campaign_data["emails"]`; `synopsis` = `campaign_data["synopsis"]`.
   - `contacts` = parsed contacts.
   - `start_date` = body `start_date`.
   - `aicb_camp_type` = template; `_chooser_origin` = template; `template_key` = template.
   - `variables` = `{CompanyName, TargetRole, Geography, Industry}` from the spec.
   - `_owner_email` = `email` (so `save_campaign`/`queue_campaign_emails` bind correctly
     with no UI session).
7. `save_campaign(camp)` → `queue_campaign_emails(camp)` (returns queued count).
8. `200` JSON:
```json
{
  "campaign_id": "<safe name>",
  "name": "...",
  "steps": 5,
  "contacts_queued": 1,
  "start_date": "2026-07-06",
  "schedule": [
    {"step": 1, "type": "email_auto", "date": "2026-07-06"},
    {"step": 2, "type": "email_auto", "date": "2026-07-09"},
    {"step": 3, "type": "call",       "date": "2026-07-09"},
    {"step": 4, "type": "email_auto", "date": "2026-07-15"},
    {"step": 5, "type": "email_auto", "date": "2026-07-21"}
  ]
}
```
The `schedule` is computed by accumulating each step's `delay_days` over business days
(the same `_add_business_days` logic the scheduler uses), so the caller sees exact dates.

### 4. Inherited send safety

Because launch goes through `queue_campaign_emails`, the API automatically gets:
DNC (email + domain) filtering, opt-out/responded skipping, Active-Clients blocklist,
MX-record validation, and the unfilled-placeholder guard (raises `ValueError` →
endpoint returns `422`). No new safety code needed.

## Data Flow

```
POST /api/v1/campaigns  (Authorization: Bearer dd_live_…)
   │  _resolve_api_key → owner email          (401 if invalid)
   │  validate spec                            (400 on bad template/date)
   │  bind user ctx (_CURRENT_USER_EMAIL / _switch_to_user_paths)
   ▼
generate_aicb_campaign(client, …)  →  {synopsis, campaign_name, emails[]}
   │  (422 if placeholder guard trips; 502 if research empty)
   ▼
assemble camp dict (owner = key’s email)  →  save_campaign  →  queue_campaign_emails
   ▼
200 { campaign_id, steps, contacts_queued, start_date, schedule[] }
```

## Error / Edge Handling

- **Invalid/missing key** → `401`.
- **Unknown template / missing company&niche / bad start_date** → `400` with message.
- **`ANTHROPIC_API_KEY` unset on server** → `503`.
- **Research returns empty brief** → `502 "generation failed, retry"`.
- **Placeholder guard / generation rejected** (`queue_campaign_emails` raises
  `ValueError`) → `422` with the guard message.
- **Zero contacts after DNC/MX filtering** → still `200`, `contacts_queued: 0`, plus a
  `"warning"` field.
- **Generation latency** (~15–40s) → synchronous response; document a 60s client timeout.
  Async/webhooks deferred.
- **Malformed CSV** → `400` naming the parse error.

## Testing

Unit (pure, no live AI / no network):
- `_mint_api_key` + `_resolve_api_key`: mint → resolve returns the email; a wrong/blank
  key → `None`; the plaintext is never written to the store (only its hash).
- Spec validation: missing template / unknown template / bad date → the right `4xx`.
- `contacts_csv` parsing → contact dicts with aliased columns.
- camp-dict assembly: spec → `camp` has `emails`, `start_date`, `aicb_camp_type`,
  `_owner_email`, `variables`.
- `schedule` computation: 4×4 delays `0,3,0,4,4` over business days → expected dates.

Generation function (monkeypatched Anthropic client returning canned JSON, no network):
- Returns a normalized `{synopsis, campaign_name, emails[]}`.
- Post-processing applied: no em/en dashes in bodies; `fourbyfour` bodies are
  Aptos-11px-wrapped; every email body starts with `Hi {FirstName},`.

Route (FastAPI `TestClient`, with `generate_aicb_campaign`, `save_campaign`,
`queue_campaign_emails` monkeypatched):
- No/invalid auth → `401`; valid key → owner is the key's email (NOT any body field).
- Happy path → `save_campaign` and `queue_campaign_emails` called once; response shape
  matches (campaign_id, steps, schedule length).
- `queue_campaign_emails` raising `ValueError` → `422`.

Regression after the wizard rewire — existing suites must still pass:
`tests/test_arena_4x4_voice.py`, `tests/test_arena_4x4_industry_aim.py`,
`tests/test_arena_4x4_cited_stats.py`, `tests/test_strategy_chooser.py`.

Manual: mint a key; `curl` the endpoint with a real 4×4 spec + one safe test contact;
confirm `200` with a 5-step schedule, the campaign appears in the account, and the queue
shows the sends. Then run the wizard once to confirm parity (it still generates 4×4s
identically via the shared function).

## Files Touched

- `flowdrip_app.py`
  - New: `generate_aicb_campaign(...)`; API-key helpers (`_api_keys_path`,
    `_hash_api_key`, `_mint_api_key`, `_resolve_api_key`); `_parse_contacts_csv`;
    schedule helper reuse; `@app.post("/api/v1/campaigns")` route.
  - Modify: the AICB generation handler to call `generate_aicb_campaign` (the rewire).
- `scripts/mint_api_key.py` — new CLI to mint a key for an email.
- `tests/test_campaign_api.py` — new.
- `docs/api/campaigns.md` — new: usage doc the co-work agent follows (endpoint, auth,
  request/response, example `curl`).

## Deployment

Server-side change in `flowdrip_app.py` → ships via `_deploy_zero_downtime.sh` (the same
flowdrip_app.py-only path used for the 4×4 call). `scripts/mint_api_key.py` runs on the
server (where the data root and `flowdrip_app` import resolve). After deploy: mint the
user's key on the server, smoke-test the endpoint with one safe contact, then run the
wizard once to confirm parity.

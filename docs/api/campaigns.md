# Campaign Create + Launch API

Create **and launch** a full AICB campaign (e.g. Arena 4×4) in one call. The
server runs the same AI generation the wizard uses — researches the company/market,
writes every email + the call script in the house voice, then queues the sends.

- **Endpoint:** `POST https://dripdripdrop.ai/api/v1/campaigns`
- **Content-Type:** `application/json`
- **Auth:** `Authorization: Bearer <your-api-key>` (or `X-API-Key: <your-api-key>`)

The API key is tied to one user account. The campaign is always created in **that**
account — the request body cannot target a different user. Keep the key secret; it
can create and launch real outreach.

Get a key: on the server, run `python scripts/mint_api_key.py <your-account-email>`.
The plaintext key is printed once; only its hash is stored.

## Request body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `template` | string | yes | Campaign template key. See **Templates** below. |
| `company` | string | one of `company`/`niche` | Target company name. |
| `niche` | string | one of `company`/`niche` | Market/niche (for market-mode campaigns with no single company). |
| `start_date` | string | no | ISO `YYYY-MM-DD`. Step 1 sends this day; later steps follow the template's day offsets over **business days**. **Omit it** (or pass `"upcoming_monday"`) to let the server pick the **upcoming Monday** — and if today already *is* Monday, it uses **today** (so the campaign sends today at the current time rather than slipping a week). Don't compute the Monday client-side; let the server do it. |
| `website` | string | no | Company website (improves research). |
| `industry` | string | no | Industry key/label. |
| `roles` | string[] | no | Target roles, e.g. `["Plant Manager"]`. |
| `location` | string | no | Geography, e.g. `"Windsor, CO"`. |
| `name` | string | no | Override the campaign name (else auto-named). |
| `candidates` | object[] | no | Candidate slate. Each: `{label, role, bullets[], years?, location?, target_salary?}`. `label` is what recipients see (e.g. `"Candidate A"`). |
| `contacts` | object[] | no* | Recipients. Each: `{email, first_name?, last_name?, company?, title?}`. |
| `contacts_csv` | string | no* | Alternative to `contacts`: raw CSV text with a header row. Columns map from `Email/email`, `FirstName/first_name`, `LastName/last_name`, `Company/company`, `JobTitle/Title/title`. |

\* Provide `contacts` **or** `contacts_csv`. With neither (or if every contact is
filtered out), the campaign is still created but nothing is queued (`contacts_queued: 0`
plus a `warning`).

**Sending safety (always applied):** contacts on your Do-Not-Contact list, opt-outs,
already-responded contacts, the Active-Clients blocklist, and addresses with no valid
mail server are skipped automatically at launch.

## Response — `200 OK`

```json
{
  "campaign_id": "Acme_Manufacturing_-_Plant_Manager_Campaign",
  "name": "Acme Manufacturing - Plant Manager Campaign",
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

## Status codes

| Code | Meaning |
|------|---------|
| `200` | Created + launched. |
| `400` | Invalid body, unknown `template`, missing `company`/`niche`, or bad `start_date`. |
| `401` | Missing/invalid API key. |
| `422` | Generation produced content that failed the safety guard (e.g. an unfilled placeholder). Retry. |
| `502` | Research returned nothing — retry. |
| `503` | AI not configured on the server. |
| `500` | Unexpected error. |

## Templates

`fourbyfour` (Arena 4×4 — 4 emails + a same-day follow-up call), `blitz`,
`talentdrop`, `flood`, `sidequest`, and the other entries in `AICB_CAMPAIGN_TYPES`.
Most use cases want `fourbyfour`.

## Timing

The call is **synchronous** and runs the full research + generation pipeline, so it
typically takes **15–40 seconds**. Use a client timeout of at least **60s**.

## Phase-1 limits

- Templates only (no custom/"BYOS" sequences).
- Cadence is `start_date` + the template's relative offsets (no per-step dates yet).
- No résumé-PDF generation/attachment via the API.
- No async/webhooks — the response returns when the campaign is created + queued.

## Example

```bash
curl -sS -X POST https://dripdripdrop.ai/api/v1/campaigns \
  -H "Authorization: Bearer dd_live_YOURKEY" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "fourbyfour",
    "company": "Acme Manufacturing",
    "website": "acme.com",
    "niche": "food processing",
    "industry": "manufacturing",
    "roles": ["Plant Manager"],
    "location": "Windsor, CO",
    "start_date": "2026-07-06",
    "candidates": [
      {"label": "Candidate A", "role": "Plant Manager",
       "bullets": ["12 yrs in food processing", "PMP, Six Sigma"],
       "location": "Windsor, CO", "target_salary": "$140k"}
    ],
    "contacts": [
      {"email": "vp@acme.com", "first_name": "Dana", "last_name": "Lee",
       "company": "Acme", "title": "VP Operations"}
    ]
  }'
```

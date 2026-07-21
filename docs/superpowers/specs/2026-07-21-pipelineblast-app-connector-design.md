# PipelineBlast in the claude.ai app — DripDrop MCP connector design

**Date:** 2026-07-21
**Status:** Approved (design), pre-implementation
**Goal:** let Mike's partners run the full PipelineBlast BD pipeline from the claude.ai app
(Cowork / chat) on individual Pro/Max accounts — no access to Mike's machine, no shared secrets —
by exposing DripDrop's campaign launch, a shared dedupe master, and a server-side Talent Trekker
load through a custom MCP connector on `dripdripdrop.ai`.

## Why a connector

The claude.ai sandbox is egress-blocked: raw HTTP from a Cowork session cannot reach
`dripdripdrop.ai`. claude.ai **connectors** are exempt — Anthropic's servers make the call. Indeed
and ZoomInfo already run as connectors, so the sourcing phases work in the app today. The three
Mike's-machine-only pieces (per-user API key + XHR launch trick, local `companies_master.csv`,
browser-session Talent Trekker load) are what this design moves server-side.

## Decisions (settled with Mike, 2026-07-21)

1. **Partner campaigns launch from each partner's own DripDrop account** — their sending identity,
   their bench. (The per-user key model already scopes this; OAuth maps a login to the same
   identity.)
2. **Partners are on individual Claude Pro/Max accounts** — no shared workspace. Each partner adds
   the connector and uploads the skill zip themselves; directions must cover full setup.
3. **Partners have their own ZoomInfo seats** — Indeed + ZoomInfo phases stay client-side and
   unchanged.
4. **One shared team dedupe master**, server-side, seeded from Mike's `companies_master.csv`, with
   per-row attribution (`added_by`).
5. **Talent Trekker load moves server-side**, run automatically after each successful launch using
   a stored Frappe token from Mike's TT user.
6. **The MCP server lives inside `flowdrip_app.py`** (not a sidecar) — mounted ASGI app, one
   deploy, in-process reuse of the existing campaign-create path.

## Architecture

```
Partner (claude.ai app, Pro/Max)
  ├─ Indeed connector        → Phase 1: find hiring companies (unchanged)
  ├─ DripDrop connector /mcp → Phase 2: check_companies / record_companies (shared master)
  ├─ ZoomInfo connector      → Phase 3: pull decision-makers (unchanged)
  ├─ DripDrop connector /mcp → Phase 4: launch_arena_5x3 (partner's own account/bench)
  └─ (server-side, automatic) Phase 5: TT-load job per launched campaign
```

### MCP server & mounting

- Streamable-HTTP MCP endpoint at `https://dripdripdrop.ai/mcp`, built with the official MCP
  Python SDK's ASGI app. NiceGUI runs on FastAPI, which mounts sub-apps directly; no new process,
  port, or subdomain.
- Ships in `flowdrip_app.py` behind the existing blue/green deploy. **Deploy caution:** follow the
  single-file recipe in the prod-deploy notes — the deploy script's `EXTRA_FILES` behavior can
  revert live files.

### Auth: OAuth 2.1 for claude.ai custom connectors

- Authorization-code + PKCE with **dynamic client registration** — the flow claude.ai custom
  connectors require. Endpoints: `/oauth/register`, `/oauth/authorize`, `/oauth/token`, plus the
  `/.well-known/oauth-authorization-server` metadata document.
- The authorize page is DripDrop's existing login. Partner signs in once when adding the
  connector and approves; the issued token maps to their DripDrop user id.
- Every tool call executes as the token's user — the same identity the per-user API keys carry —
  so the campaign engine needs **zero changes** for account scoping, sending identity, or bench
  matching.
- Tokens: server-side grant table (user id, client id, refresh token hash, expiry, revoked flag).
  Access tokens short-lived with refresh; revoking a partner = revoking their grant row. Reissuing
  a partner's DripDrop **API key** does not affect connector grants (they are separate
  credentials; the key-reissue-revokes-all-copies gotcha applies only to API keys).

### Connector tools

Four tools; schemas are the contract, so keep them tight.

| tool | purpose | notes |
|---|---|---|
| `check_companies(companies: [{name, city?}])` | Batch dedupe check against the shared master | Returns per company `new` or `already_worked` + status/date/added_by. Loose matching (case/suffix normalization, known-variant catching, "when unsure treat as same") is implemented **server-side** so all clients dedupe identically. |
| `record_companies(rows: [{name, city, type, week_surfaced, status}])` | Append selections / update status | Called right after selection (append-before-campaigns rule preserved) and again as statuses change (`Campaign launched + in TT`, `Selected - skipped (no bench fit): …`, `TT load failed`). Transactional: the second claimant of a company gets `already_worked` back instead of a duplicate row. |
| `launch_arena_5x3(company, roles, start_date, contacts[], enroll_newsletter, industry?, location?, name?)` | Create + launch a 5x3 for the authenticated user | Wraps the existing campaign-create path **in-process** (same code as `POST /api/v1/campaigns`). The schema has **no `candidates[]` field** — the no-slate rule is enforced structurally, not by prompt discipline. Contacts carry `phone_office` and `linkedin` (call-card requirement). Returns `campaign_id` + full schedule, or `{skipped: true, reason}` as a normal (non-error) result. Response includes `newsletter_enrollment` for the skill to verify `matched: true`. |
| `list_newsletters()` | Exact newsletter names | Lets the skill resolve `enroll_newsletter` on the first try instead of failing into the `available` fallback. |

Existing launch-time server behavior (DNC/opt-out/responded/blocklist/dead-domain skips,
server-side bench match, résumé + interview-guide attach, business-day schedule offsets) is
inherited unchanged because the tool calls the same code path.

### Shared dedupe master (server-side)

- **Store:** SQLite table (`bd_companies_master`), not a JSON file — the 133MB
  `scheduled_queue.json` incident is the cautionary tale for append-forever JSON.
- **Schema:** `company, city, type, week_surfaced, date, status, added_by` (authenticated user),
  plus a normalized-name column used for matching.
- **Seed:** one-time import of Mike's `companies_master.csv`; the import is idempotent (re-running
  it does not duplicate rows).
- **Concurrency:** check-and-append runs in a transaction so simultaneous partner runs cannot both
  claim a company.
- **Transition note:** until Mike's local Claude Code runs are switched to these same tools, his
  local CSV and the server master can drift. Plan: switch the local skill to the connector tools
  as a fast-follow; until then, re-import the CSV before inviting partners and treat the server
  master as authoritative from that day forward.

### Server-side Talent Trekker load

- **Trigger:** every successful (non-skipped) launch enqueues a TT-load job on the existing
  scheduled-job infrastructure, carrying the company + the launched contact set.
- **Auth:** Frappe token auth (`Authorization: token api_key:api_secret`) from a token pair
  generated once on Mike's TT user. No browser, no session cookie, no CSRF exposure (the
  cookie-CSRF caveat in the pipeline reference applies to the browser method, not token auth).
- **Job sequence** (ported from the Phase 5 reference): Customer dedupe check (loose match, with
  the different-firm caution à la Brinkmann/Brinkman) → create missing Customer with the standard
  defaults (Direct Hire / Arena Direct Hire / Team Mountain Summit / Source `ZoomInfo`, exact
  case) → create Contacts with `links` to the exact customer name, phones sanitized → verify
  counts by email query.
- **Failure policy:** TT failures never block or unwind a campaign. Retry with backoff; on final
  failure set the company's master status to `TT load failed` and include it in the run summary
  returned to the operator (partner sees it; Mike fixes it).
- **Attribution:** all TT records land under Mike's TT user/branch defaults in v1. Per-partner TT
  credentials are explicitly out of scope (revisit if partners need TT attribution).

### The app-side skill package (`pipelineblast-app`)

- A variant of the existing `pipelineblast` skill, zipped for upload to claude.ai
  (Settings → Capabilities → Skills). Same five-phase structure and prompts.
- **Phase 2** reference rewritten: call `check_companies` / `record_companies`; all local-CSV
  mechanics removed.
- **Phase 4** reference rewritten: call `launch_arena_5x3` (+ `list_newsletters` first); the
  same-origin XHR / Chrome-tab machinery deleted; skip-response and retry semantics kept.
- **Phase 5** reference becomes: confirm the TT results reported per launch; flag `TT load failed`
  rows to Mike.
- **Distribution:** the zip is the unit. Individual accounts have no shared registry, so each
  partner uploads it and version updates mean re-sending the zip. Keep a version line in the
  SKILL.md frontmatter description so a partner can be asked "which version do you have?"

### Errors & edge cases

- **Expired/revoked token** → tools return an auth error with a "reconnect the DripDrop connector
  in Settings → Connectors" message (also in partner directions).
- **`skipped: no bench fit`** → normal outcome: record in master, move on.
- **Content-guard / empty-research failures** (the 422/502 equivalents) → tool result marks them
  retryable; skill retries as today; generation-off (503 equivalent) marked retry-later.
- **No matching newsletter for the run's geo/industry** → skill flags Mike (newsletter creation is
  Mike's side) and holds that run's launches until the newsletter exists — `enroll_newsletter` is
  required by the launch path, same as the existing API.
- **Concurrent runs** → transactional master; second claimant gets `already_worked`.

### Testing

- In-process tool-handler tests following `tests/test_campaign_api.py` patterns: auth-context
  injection, each tool's happy path + auth failure.
- Dedupe matcher table tests: case/suffix variants match; **Brinkmann Constructors vs Brinkman
  Construction stay distinct**; unsure-means-same behavior.
- OAuth flow tests: register → authorize → token → refresh → revoke.
- TT loader tests against a mocked Frappe API, including the retry/`TT load failed` path.
- Baseline against the 8 known pre-existing test failures; do not chase them.
- **Rollout gate:** Mike connects the connector to his own claude.ai account and runs one real
  end-to-end campaign (real launch, real TT load) before any partner is invited.

## Rollout preconditions (not design)

1. Each partner: Claude Pro or Max (custom connectors + skill uploads supported), a DripDrop
   account Mike creates, and their ZoomInfo seat + Indeed connected in claude.ai.
2. One TT `api_key:api_secret` pair generated from Mike's TT user and stored in DripDrop's server
   config.
3. Server master seeded from the current `companies_master.csv` immediately before go-live.

## Out of scope (v1)

- Per-partner Talent Trekker credentials/attribution.
- Newsletter creation from the connector.
- Migrating Mike's local Claude Code runs to the connector tools (fast-follow).
- Any change to campaign content/template mechanics — the 5x3 engine is untouched.

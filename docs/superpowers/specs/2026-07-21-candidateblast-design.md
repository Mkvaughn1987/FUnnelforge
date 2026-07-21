# CandidateBlast — MPC "Find Openings" step — Design Spec

**Date:** 2026-07-21 (revised x3 same day after review)
**Status:** Draft for review
**Author:** Michael Vaughn (with Claude)

## Summary

**CandidateBlast** is an in-app product feature for DripDrop (all users, not a
Claude-session skill): a candidate-first job finder built into the **Start an MPC
Campaign** flow. It revives the retired "Search Jobs" feature (cut 2026-05-22) as the
front half of MPC outreach.

The experience:

1. The user selects **1–3 candidates** (the MPC slate limit) in the pool/ATS and hits
   **Start an MPC Campaign** — exactly as today.
2. A new **"Find Openings"** step appears: a short pre-filled intake (location, industry,
   job titles — parsed from the candidates), then the server searches online for current
   openings.
3. The step presents **10 total options that look good — local AND nationwide together**
   (recently posted, medium-sized companies), each with company, role, location, posted
   date, source, and a short fit rationale.
4. **The user chooses which companies to send to.** Each chosen company gets its own MPC
   campaign draft (candidate slate + résumés, built the same way the MPC builder does
   today).
5. **Contacts arrive automatically via the ZoomInfo bridge**: the app queues the chosen
   companies; a scheduled Claude cloud agent using Mike's ZoomInfo connector pulls each
   company's decision-makers (**Managers and above**) and pushes them back into the app
   as the campaign's contact list. The user reviews the draft — emails + contacts already
   in place — and launches.

No auto-send: the user picks the targets and pulls the trigger. This is the
candidate-first sibling of PipelineBlast (`2026-07-21-pipelineblast-design.md`), but as a
product feature; PipelineBlast remains the automated role-first skill.

## Goals

- From "these are my candidates" to a ranked list of live openings without leaving the app.
- Work for **every DripDrop user** (no Claude Code session, no MCP connectors) — the
  server does the searching via the Claude API.
- Slot into the existing MPC flow without breaking it.

## Non-goals

- Do NOT break or bypass the existing MPC flow — "Find Openings" is an **optional** step;
  users can still go straight to the builder as today.
- Do NOT auto-launch. User-driven sends only (v1) — contacts are pre-loaded by the
  bridge, but the user reviews and hits send.
- NO ZoomInfo Enterprise API integration — contacts come through the **Claude-agent
  bridge** running under Mike's ZoomInfo connector (no new licensing). Direct API
  integration is the v2 upgrade path if licensing is ever added.
- Do NOT modify the live 4x4 / 5x5 / 5x3 sequence content.

## Flow

### 1. Entry

From the pool/ATS multi-select (1–3 candidates) → **Start an MPC Campaign**. The existing
handoff (`_pending_mpc_candidates`, ~flowdrip_app.py L54602) lands on a chooser:

- **Find Openings** (new) — the feature below.
- **Skip — build campaign directly** — today's behavior, unchanged.

### 2. Intake (pre-filled form)

One compact form, defaults parsed from the selected candidates' resume_text/profiles:

- **Location** — candidate's metro (editable).
- **Industry** — target sector(s).
- **Job title(s)** — current/recent titles.
- Seniority or must-haves if the parse is ambiguous.

### 3. Server-side job search

- **How:** the DripDrop server calls the **Claude API with the web search tool** (the app
  already holds `ANTHROPIC_API_KEY` and builds `anthropic.Anthropic` clients). The search
  prompt covers Indeed, ZipRecruiter, and Google Jobs results for the intake titles +
  skills + industry.
- **Scope:** BOTH the intake location and nationwide, in one pass — results are labeled
  local vs nationwide.
- **Recency:** postings from the last **14 days** (default).
- **Company size: medium** — target **100–500 employees**, best-effort from posting and
  public company info (no ZoomInfo server-side; size is advisory, shown per option).
- Runs async with progress UI (searches take tens of seconds; don't block the event loop —
  same pattern as the existing AICB wizard worker).

### 4. Present 10 options

A picker listing **10 total** openings that look good (mix of local + nationwide, ranked
by slate fit). Each option shows: company, role title, location (+ local/nationwide
badge), posted date, source link, estimated size, and a one-line "why this fits your
candidates". Options at companies already in an **active DripDrop sequence** are flagged
(warn, don't hide). If fewer than 10 qualify, show what's real — never pad with weak fits.

### 5. User chooses + drafts created

- The user checks off any subset of the 10 and confirms.
- For each chosen company, the app builds an **MPC campaign draft** through the same
  generation path the MPC builder uses today (`cpc_mode="mpc"`, candidate cards, résumé
  attachments), pre-filled with the company + role from the posting.

### 6. ZoomInfo contact bridge

How the app gets live ZoomInfo contacts without ZoomInfo API licensing:

- **Queue:** on confirm, the app writes one **contact request** per chosen company
  (company name/domain, role context, requesting user, draft campaign id) to a small
  server-side queue, exposed via two new REST endpoints (list pending / post results) on
  the existing API-key auth.
- **Agent:** a **scheduled Claude cloud agent** (every ~15 minutes) with Mike's ZoomInfo
  connector polls the queue. Per request it runs a **targeted, per-company** ZoomInfo
  contact search — decision-makers at **Manager level and above** — enriches emails, and
  posts the results back. Enrichment per chosen company only; never bulk list-building
  (ZoomInfo AUP).
- **Landing:** results come back through the app's existing ZoomInfo-header
  normalization and attach to the draft campaign as its contact list. The draft shows
  contact status: *pending → N contacts loaded*.
- **Advisory bar:** if a company returns **fewer than 5** Managers+, the draft is
  badged ("only N decision-makers found") so the user can swap in a different target —
  the user decides, nothing is auto-dropped.
- The user reviews each draft — emails + contacts in place — and launches. Existing send
  throttle and bounce suppression apply untouched.

## Guardrails

- Fit floor: an option must genuinely fit the slate to be shown; under-10 results stay
  under 10.
- Active-sequence flagging on options (dedup awareness at pick time).
- No auto-send anywhere; the user launches each campaign explicitly.
- 5+ Managers+ advisory badge on thin companies (user swaps targets; nothing auto-drops).
- ZoomInfo pulls are per-chosen-company enrichment under Mike's seat, capped by the
  10-option/pick flow — never bulk extraction.
- Send throttle + bounce suppression inherited at send, untouched.
- Slate is always the user's real candidates (1–3); standing redaction/ethics line applies.

## What exists vs what gets built

Already in place:

- MPC flow + ATS handoff (1–3 slate, `_pending_mpc_candidates`, `cpc_mode="mpc"`).
- Campaign generation with candidate cards + résumé attachment (MPC builder path;
  `generate_aicb_campaign` API from plan 2026-06-27 available if the draft-per-company
  loop wants it).
- Anthropic client usage + async worker pattern in the wizard.

To build (app side in `flowdrip_app.py` unless planning finds otherwise):

1. **Find Openings step UI** — chooser, intake form, progress state, 10-option picker.
2. **Search service** — Claude API web-search call, result parsing/ranking/fit-floor,
   local+nationwide labeling, size estimation, active-sequence flagging.
3. **Draft-per-company creation** — loop the chosen companies into MPC campaign drafts
   with contact status (pending/loaded/thin).
4. **Contact-request queue + REST endpoints** — small server-side queue (keep it pruned;
   remember the scheduled_queue.json bloat lesson), list-pending + post-results
   endpoints on existing API-key auth.
5. **Bridge routine** (not app code) — scheduled Claude cloud agent w/ ZoomInfo
   connector: poll queue → per-company Managers+ pull → enrich → post back.

Follow-up explicitly out of v1: direct ZoomInfo Enterprise API integration (replaces the
bridge if licensing is ever added).

## Testing & rollout

- TDD per task; baseline against the known pre-existing test failures before claiming
  green.
- Web-search calls mocked in tests; one manual live-search verification before deploy.
- Ships single-file via `_deploy_flowdrip_only.sh` per the standing deploy caution
  (rides with the undeployed working-tree drift on `feat/5x3-campaign`). If the ATS
  handoff in `ats.py` needs touching, remember the deploy script's EXTRA_FILES gotcha
  (it can revert live `ats.py`).

## Open questions (resolve during planning)

- Exact insertion point of the chooser (ATS handoff landing vs MPC builder first screen)
  and how existing non-ATS entry points reach Find Openings.
- Web search tool availability/limits on the app's API key + which model tier runs the
  search (cost per search).
- Where the N campaign drafts land for finishing (campaign list? sequential wizard?) —
  pick the least-new-UI option that reads clearly.
- Whether résumé parsing for intake defaults reuses `_extract_resume_text` or the stored
  candidate profile fields suffice.
- **Bridge egress:** verify a scheduled Claude cloud agent can actually reach the
  DripDrop server's REST API — prior finding: the Cowork sandbox is egress-blocked and
  the API had to be called from a connected browser tab. If cloud agents are blocked
  too, fall back to a scheduled local Claude Code run on Mike's machine, or a browser
  step (beware the known unattended per-domain permission stalls).
- Bridge cadence (default ~15 min) + queue retention/pruning rules.
- Bridge auth: which DripDrop API key the agent uses (single-key reissue gotcha — a
  reissue revokes all copies).

## Risks

- **Search quality/latency** — web search returns noisy postings; mitigated by the fit
  floor, recency filter, showing sources, and the user being the final picker.
- **Bridge availability** — contacts depend on a scheduled agent under Mike's accounts;
  if it stalls (egress, connector auth, permission prompts), drafts sit at "contacts
  pending." Mitigations: visible pending status with a manual CSV-upload fallback in the
  draft, and the egress question settled first in planning.
- **Cost** — each Find Openings run is a Claude-API-with-web-search call for all users;
  size the model/token budget during planning.
- **Monolith risk** — `flowdrip_app.py` is 60k lines with duplicate-helper shadowing
  gotchas; new helpers need unique names and tests.
- **Deploy drift** — single-file deploy only; EXTRA_FILES/ats.py reversion gotcha if the
  handoff changes.

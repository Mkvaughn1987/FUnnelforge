# CandidateBlast — Design Spec

**Date:** 2026-07-21 (revised same day after review)
**Status:** Draft for review
**Author:** Michael Vaughn (with Claude)

## Summary

**CandidateBlast** is the candidate-first sibling of PipelineBlast
(`2026-07-21-pipelineblast-design.md`). Where PipelineBlast starts from a
**role + geo + industry** and finds companies for the bench, CandidateBlast starts from
**specific candidates** and finds live openings to market them into:

1. Take 1–3 candidates (résumé files, or picks from the DripDrop pool/ATS). Max 3 — the
   MPC slate limit.
2. Ask a short intake: location, industry, job title(s) — defaults parsed from the résumé,
   user confirms or overrides.
3. Search online for current open jobs (Google, Indeed, ZipRecruiter) **in that location
   first**, recently posted, at **medium-sized companies**. If nothing qualifies locally,
   **prompt the user to open the search nationwide**.
4. Grab the **top 5** companies — each must show **5+ decision-makers (Managers+) in
   ZoomInfo** or it's replaced by the next target — then auto-launch an **MPC campaign**
   at each, enrolling those decision-makers and pitching the supplied candidate slate.

The launch vehicle is the app's **existing "Start an MPC Campaign"** flow (1–3 candidate
slate) — this skill effectively revives the retired "Search Jobs" feature (cut 2026-05-22)
as the front half of MPC outreach, done by Claude online instead of in-app.

It runs **on demand** as a skill. After the intake (and the nationwide prompt if needed),
launch is **fully automatic**, gated by the same guardrails as PipelineBlast.

## Goals

- One short conversation from "here are my candidates" to 5 tailored MPC campaigns in flight.
- Reuse what exists: MPC campaign flow, campaign create/launch API, DripDrop pool. Add no
  new campaign types or sequences.
- Keep unattended launch safe via the established guardrails.

## Non-goals

- Do NOT modify the live 4x4 / 5x5 / 5x3 sequences or the in-app MPC builder UI.
- Do NOT build a scheduled routine (PipelineBlast owns scheduled BD; this is per-candidate,
  on demand).
- Do NOT auto-fill the slate from the bench — the slate is exactly the candidate(s) the
  user supplied (1–3, matching the MPC limit). All real people; standing ethics line
  applies to any redaction.

## Flow

### 1. Candidates in

Two accepted inputs, up to 3 candidates (the MPC slate limit):

- **Résumé file(s)** — PDF/docx paths; parsed to titles held, skills, industries,
  seniority, location.
- **Pool/ATS picks** — names matched against the DripDrop pool (`candidate_pool.json` /
  Top Candidates), using stored resume_text and profile fields. (The in-app selection UI
  already supports multi-select → "Start an MPC Campaign"; the skill mirrors that shape.)

### 2. Intake questions

Before searching, the skill asks a few important questions, pre-filled from the parsed
résumé so answering is confirm-or-correct:

- **Location** — where to search (candidate's metro by default).
- **Industry** — target sector(s).
- **Job title(s)** — what roles to search for (parsed current/recent titles by default).
- Anything ambiguous the parse surfaced (seniority level, must-have constraints).

### 3. Job search (fan-out, unattended)

- **Sources:** Indeed MCP `search_jobs`, ZipRecruiter MCP `search_jobs`, and web search
  for Google Jobs results. MCP-first; no browser automation (known unattended-permission
  stalls).
- **Query:** intake titles + top skills + industry, scoped to the intake **location**.
- **Recency:** postings from the **last 14 days** (default; adjustable per run).
- **Company size: medium.** Default **100–500 employees** (same band the existing BD
  routines use), verified via ZoomInfo company enrichment; adjustable per run.
- **Nationwide fallback:** if zero qualifying openings in the location, **stop and prompt
  the user** to widen to nationwide (or a different geo). Never silently expand.

### 4. Rank + filter

Score each posting for slate fit (title match, skills overlap, industry, seniority).
Then filter:

- Collapse to **one best posting per company**.
- Drop companies outside the **size band** (ZoomInfo enrichment check).
- Drop companies already in an **active DripDrop sequence** (dedup guardrail).
- Drop **bounce-suppressed** domains/contacts.
- Drop anything below the **fit floor** — no junk pitches.

### 5. Pick top 5 + ZoomInfo contacts

- Work down the ranked list. For each candidate company, pull its decision-makers
  (**Manager level and above**) from **ZoomInfo**, mirroring the PipelineBlast skill's
  contact step. Targeted per-company lookups only — enrichment, not list-building, per
  the ZoomInfo AUP.
- **Viability bar: a company qualifies only if ZoomInfo returns 5+ decision-makers
  (Managers+).** Under 5 (or none usable) → drop it, report it, and backfill with the
  next-ranked company until 5 targets qualify or the ranked list runs out. Never guess
  contacts.
- Stop at **5 qualified companies** per run — no per-company approval gate.

### 6. Auto-launch

- Launch one **MPC campaign** per company via the campaign create/launch API, with the
  supplied candidate slate (the same campaign the in-app "Start an MPC Campaign" button
  builds), enrolling **all qualifying decision-makers** (the Managers+ ZoomInfo returned)
  as recipients — multi-threaded into each account, the way the BD routines blanket a
  company.
- Rides the existing send-throttle and bounce-suppression machinery untouched; recipient
  volume (~25+ per full run) is exactly what the throttle exists to pace.

### 7. Notify + kill switch

Every run posts a summary: candidates, intake answers, postings found, the 5 picked
(company, role, decision-maker count, fit score, short rationale), companies dropped at
the 5-contact bar, campaigns launched, anything else skipped and why. Same one-flip kill
switch as PipelineBlast.

## Guardrails (always on — shared with PipelineBlast)

- Fit floor (skip postings the slate doesn't genuinely fit).
- Per-run cap: **5 companies** (each needing 5+ Managers+ in ZoomInfo to qualify).
- Dedup vs. active sequences.
- Respect existing bounce suppression + send throttle.
- Notify + one-flip kill switch.
- Slate is always the user's real candidates; redaction follows the standing ethics line.

## Shared components & build status

Most of the machinery already exists:

- **MPC campaign flow** — live in the app (1–3 candidate slate, ATS handoff at
  ~L54602, `cpc_mode="mpc"`).
- **Arena 5x3** — already built (`fivebythree` in `AICB_CAMPAIGN_TYPES` ~L4193); not used
  here but confirms the family is in place.
- **Campaign create/launch API** — exists (`generate_aicb_campaign` with `camp_type`,
  `candidate_cards`, plan 2026-06-27); CandidateBlast drives launches through it.
- **PipelineBlast skill** — already built; CandidateBlast is written as its sibling and
  should mirror its conventions (dedupe master, run summary shape) where they apply.

CandidateBlast itself is **orchestration only** — a skill, no new app-side components
expected. Verify during planning that the launch API covers the MPC camp type with
candidate cards end to end (see open questions).

## Testing & dry-run

- **Dry-run mode:** everything through ranking, contact lookup, and campaign payload
  construction, then print the launch plan (5 companies, postings, contacts, slate,
  schedule) instead of sending. This is the default for the first end-to-end verification
  run.
- No new app code expected; if API gaps force any, they get their own TDD tasks and
  baseline against the known pre-existing test failures.

## Open questions (resolve during planning)

- Which `camp_type` the MPC path uses through the launch API (`talentdrop` /
  cpc-mode equivalent) and whether the API launches it with candidate cards + résumés
  attached exactly like the in-app button — verify against the 2026-06-27 API plan and
  current code before wiring.
- Résumé-file parsing for non-pool candidates: reuse the app's `_extract_resume_text` /
  `_parse_and_redact_resume`, or parse in-skill.
- ZoomInfo contact-selection details beyond the "Managers+ / 5+ to qualify" rule (which
  titles count as decision-makers, in-geo vs any) — mirror the PipelineBlast skill's
  conventions; confirm they transfer as-is.
- Fit-floor threshold and scoring weights — shared defaults with PipelineBlast, tune once.
- "Medium-sized" band: 100–500 employees is the working default — confirm or adjust.

## Risks

- **Search quality drives everything** — weak intake → weak postings. Mitigated by the
  intake step, fit floor, and the explicit nationwide prompt instead of silent widening.
- **Deliverability** on 5 auto-launched campaigns per run — cap + throttle + suppression.
- **API/UI parity** — if the launch API can't fully reproduce the in-app MPC build
  (résumé attachments, slate handling), scope grows to close that gap; surfaced as the
  first open question so it's settled before build.

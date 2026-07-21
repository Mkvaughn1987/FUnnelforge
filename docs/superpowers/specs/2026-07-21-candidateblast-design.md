# CandidateBlast — Design Spec

**Date:** 2026-07-21
**Status:** Draft for review
**Author:** Michael Vaughn (with Claude)

## Summary

**CandidateBlast** is the candidate-first sibling of PipelineBlast
(`2026-07-21-pipelineblast-design.md`). Where PipelineBlast starts from a
**role + geo + industry** and matches the bench to hiring companies, CandidateBlast starts
from a **specific candidate** and markets that person into live openings:

1. Take a candidate (from the DripDrop pool, or a résumé file for someone new).
2. Find recent job postings the candidate fits (Google, Indeed, ZipRecruiter).
3. Pick the **top 7** companies, fully automatically.
4. Auto-launch a **5x3** campaign at each, with the searched candidate leading the slate.

It runs **on demand** as a skill the user triggers with a candidate in hand. Auto-launch is
**fully automatic from run one**, gated by the same hard guardrails as PipelineBlast.

## Goals

- One command from "here is my candidate" to 7 tailored campaigns in flight.
- Reuse PipelineBlast's components (5x3 campaign, résumé engine, matching engine) rather
  than building parallel machinery — the two skills share one toolbox.
- Keep unattended full-auto safe via the established guardrails.

## Non-goals

- Do NOT modify the live 4x4 or 5x5 sequences.
- Do NOT build a scheduled routine for this (PipelineBlast Component 4 covers scheduled BD;
  CandidateBlast is inherently per-candidate and on demand).
- Do NOT fabricate the lead candidate — the searched candidate is always a real person with
  a real, redacted résumé. Synthesized "Representative profile" fallbacks may only fill the
  B/C slate slots, honestly labeled, per the standing ethics line.

## Flow

### 1. Candidate in

Two accepted inputs:

- **Pool pick** — a name matched against `candidate_pool.json` (the DripDrop Top Candidates
  pool). Uses the stored `resume_text` and profile fields directly.
- **Résumé file** — a PDF/docx path for someone not yet in the pool. Parsed into the same
  profile shape the matcher uses: titles held, skills, industries, seniority, delivery type.
  (Parsing only; importing the person into the pool is out of scope here — the DripDropAPI
  skill already covers that if wanted.)

### 2. Posting search (fan-out, unattended)

- **Sources:** Indeed MCP `search_jobs`, ZipRecruiter MCP `search_jobs`, and web search for
  Google Jobs results. MCP-first; no browser automation (known unattended-permission stalls).
- **Query:** built from the candidate's title(s) and top skills.
- **Recency:** postings from the **last 14 days** (default; adjustable per run).
- **Location: ignored entirely** — match on role/skills nationwide, same posture as
  PipelineBlast's matching. Location is never shown on the redacted résumé anyway.

### 3. Rank + filter

Score each posting for candidate fit (title match, skills overlap, industry, seniority).
Then filter:

- Collapse to **one best posting per company**.
- Drop companies already in an **active DripDrop sequence** (dedup guardrail).
- Drop **bounce-suppressed** domains/contacts.
- Drop anything below the **fit floor** — no junk pitches.

### 4. Pick top 7

Take the top 7 surviving companies by fit score. **No approval gate** — full-auto, same as
PipelineBlast. The per-run cap is 7 companies.

### 5. Slate build (per company)

- **Candidate A = the searched candidate.** Always real; résumé redacted by the shared
  résumé engine (PII + location stripped, employers anonymized uniformly, header
  "Redacted candidate profile").
- **Candidates B and C** come from the matching engine (PipelineBlast Component 2) run
  against that company's posting — the two best bench fits, redacted the same way.
- If fewer than 2 real bench fits clear the floor, fill with synthesized
  **"Representative profile"** cards (honest label, anonymized employer descriptors, never
  real company names, never posed as a real person).

### 6. Launch

- One **5x3** per company (PipelineBlast Component 1), company-targeted through the
  existing campaign create/launch path; the app sources and validates the recipient the
  same way PipelineBlast does (open question shared with that spec).
- Rides the existing send-throttle and bounce-suppression machinery untouched.

### 7. Notify + kill switch

Every run posts a summary: candidate, postings found, the 7 picked (company, role, fit
score, short rationale), campaigns launched, anything skipped and why. Same one-flip kill
switch as PipelineBlast.

## Guardrails (always on — shared with PipelineBlast)

- Fit floor (skip postings the candidate doesn't genuinely fit).
- Per-run cap: **7 companies**.
- Dedup vs. active sequences.
- Respect existing bounce suppression + send throttle.
- Notify + one-flip kill switch.
- Ethics line: lead candidate always real and redacted; synthesized profiles only as
  labeled B/C fillers.

## Shared components & build order

CandidateBlast adds **no new app-side components**. It consumes:

1. **5x3 campaign + résumé engine** — plan already written
   (`plans/2026-07-21-5x3-campaign-and-resume-engine.md`). Build first.
2. **Matching engine** (Component 2) — built as a shared piece both skills call. For
   CandidateBlast it fills slate slots B/C; for PipelineBlast it builds the whole slate.
3. **CandidateBlast skill** (this spec) — orchestration only: parse candidate, fan-out
   search, rank, pick 7, call the shared slate/launch path.
4. **PipelineBlast skill + scheduled routine** — later, reusing all of the above.

Nothing touches the live 4x4/5x5; app changes ship single-file via
`_deploy_flowdrip_only.sh` per the standing deploy caution.

## Testing & dry-run

- **Dry-run mode:** does everything through slate-PDF generation, then prints the launch
  plan (7 companies, postings, slates, schedules) instead of sending. This is the default
  for the first end-to-end verification run.
- App-side behavior (5x3 build, résumé PDFs, attach logic) is covered by the 5x3 plan's
  TDD tasks; this skill adds no app code beyond that plan.
- Baseline against the known pre-existing test failures before claiming green.

## Open questions (resolve during planning)

- Résumé-file parsing for non-pool candidates: reuse `_extract_resume_text` /
  `_parse_and_redact_resume` from the app, or parse in-skill? Decide when planning.
- Fit-floor threshold and scoring weights — shared defaults with PipelineBlast, tune once.
- Recipient sourcing/validation per company — shared open question with PipelineBlast;
  resolve once for both.

## Risks

- **Search quality drives everything** — a weak query surfaces weak postings. Mitigated by
  building queries from parsed titles + skills and by the fit floor.
- **Deliverability** on 7 auto-launched campaigns per run — cap + throttle + suppression.
- **Working-tree drift** — ships from `feat/self-serve-api-keys` alongside the undeployed
  5x5 and 5x3; single-file deploy only.

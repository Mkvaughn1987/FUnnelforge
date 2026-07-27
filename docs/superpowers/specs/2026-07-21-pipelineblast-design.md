# PipelineBlast + 5x3 — Design Spec

**Date:** 2026-07-21
**Status:** Draft for review
**Author:** Michael Vaughn (with Claude)

## Summary

**PipelineBlast** is an automated business-development loop for Arena Direct Hire. The user
supplies a **target role + geo + industry**. The system then:

1. Finds recent job postings from companies hiring that role (hybrid sourcing).
2. Matches Arena's candidate pipeline to each hiring company (location ignored).
3. Generates 3 redacted résumé PDFs per company (best / ~80% / loose fit).
4. Auto-launches a **5x3** email campaign to that company.

It runs **on demand** (as a skill the user triggers) and on a **weekly/biweekly schedule**
(saved targets; nudges the user if none are set). Auto-launch is **fully automatic from run
one**, gated by hard safety guardrails.

The **5x3** is a new, standalone campaign (5 emails, a 3-candidate slate). The existing 4x4
and 5x5 are left byte-identical.

## Goals

- Automate find -> match -> résumé -> launch with no manual step in steady state.
- Produce résumés that read like real résumés (real bench redacted; synthesized fallback
  clearly labeled representative).
- Make unattended full-auto **safe** (guardrails below), not fire-and-forget.

## Non-goals

- Do NOT modify the live 4x4 or 5x5 sequences.
- Do NOT fabricate candidates that wear real company names or pose as specific real people.
- Do NOT use ZoomInfo to *build* cold-outreach lists (enrichment only, per its AUP).

## Component 1 — 5x3 campaign + résumé engine (build first)

**Campaign** (`fivebythree`, cloned from the 5x5 warm/soft solo voice):

| # | Day | Purpose | Attachment |
|---|-----|---------|------------|
| 1 | 0 | Warm intro / market-pulse opener | none |
| 2 | 3 | Candidate slate (3 spotlights) | **3 résumés** |
| 3 | ~6 | Interview Guide value-add | Interview Guide PDF |
| 4 | ~8 | Short bump. Subj "Following up": "did you get a chance to review the résumés... are you the right person on the hiring side, or should I loop in someone else?" | **3 résumés (re-attached)** |
| 5 | ~11 | Soft close / gentle breakup | none |

- Lives as a tuple in `AICB_CAMPAIGN_TYPES`, added to the Arena family set. Résumé placement
  = emails 2 and 4 (`_resume_attach_indices`). All copy de-dashed (app also strips at send).

**Résumé engine** — given a candidate (real pool record OR synthesized card), produce a
polished redacted PDF with sections: Summary, Areas of Expertise (2-col), Professional
Experience (entries = anonymized employer + date range + duty bullets), Selected Projects
(optional), Tools/Software, Education & Certifications.

- **Contact + location stripped.** Employers **anonymized uniformly** across the slate
  (e.g. "Regional civil and environmental engineering firm").
- Header note: **"Redacted candidate profile"** for real candidates;
  **"Representative profile"** for synthesized fallbacks.
- Replaces the thin `_aicb_card_to_resume_text` path **for 5x3 only**. Reference layout:
  the 2026-07-21 sample PDFs (Candidate A/B/C).

## Component 2 — Candidate-matching engine

- **Input:** target company + role (+ industry). **Source:** `candidate_pool.json`.
- **Score** each candidate on role match, sector/industry, skills, delivery type.
  **Location ignored** and never shown.
- **Return** top 3, tiered perfect / ~80% / loose, each with a short fit rationale. Cast a
  wide net (loose fits count).
- **Fit-floor:** if zero candidates clear a minimum threshold for a company, **skip that
  company** (no junk slate). If 1-2 real fits, fill the remainder with **synthesized
  representative profiles** (honest, anonymized).
- Redact real résumés via the Component-1 engine.

## Component 3 — PipelineBlast orchestration (skill)

Inputs: target role, geo, industry.

1. **Posting sweep (hybrid).** Unattended: MCP job search (Indeed / ZipRecruiter) for recent
   postings by role + geo + industry. Interactive only: optional ZoomInfo enrichment
   (company data, contacts).
2. **Match** per company (Component 2) -> 3 candidates.
3. **Generate** 3 résumé PDFs (Component 1).
4. **Auto-launch** a 5x3 to the company's hiring contact.

**Guardrails (always on):**
- Fit-floor (skip companies with no qualifying candidate).
- Per-run cap (max companies/emails per run) — protects the per-account send throttle and
  deliverability.
- Dedup (never re-target a company/contact already in an active sequence).
- Respect existing bounce suppression + send-throttle.
- Notify + one-flip kill switch; every run posts a summary.
- ZoomInfo enrichment-only; recipients sourced from the posting side, compliantly.

## Component 4 — Scheduled routine

- Weekly or biweekly cron routine.
- Runs a **saved target list** (target/geo/industry combos). If none set, **nudge** the user
  rather than running blind.
- Executes PipelineBlast per target, full-auto with guardrails; posts a run summary.

## Open questions (resolve during planning)

- Programmatic 5x3 build + launch path inside `flowdrip_app.py` (how campaigns are created,
  enrolled, and queued) — verify before wiring auto-launch.
- How the recipient (hiring-manager email) is sourced and validated per company.
- CAN-SPAM footer / unsubscribe handling on auto-sent BD mail — confirm existing campaigns
  already satisfy this and 5x3 inherits it.
- Minimum fit-floor score and per-run cap default values.

## Risks

- **Unattended browser-permission stalls** (known from prior BD routines) -> mitigated by
  MCP-first sourcing; browser/ZoomInfo only in interactive runs.
- **Deliverability/reputation** on auto-send -> per-run cap + throttle + suppression.
- **Match quality** on full-auto -> fit-floor + tiering; synthesized fallbacks clearly labeled.
- **Working-tree drift**: this ships from `feat/self-serve-api-keys`; deploy single-file via
  `_deploy_flowdrip_only.sh`. It will ride along with the already-built-but-undeployed 5x5.

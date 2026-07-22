# PipelineBlast JD-Targeting + CandidateBlast Fallback Automation

## Context

Both weekly BD motions currently depend on a human remembering to run them:

- **PipelineBlast** has two scheduled routines (Estimators/Tue, Plant Manager/Thu), each
  targeting a bare role/geo/industry string.
- **CandidateBlast** has no scheduled automation at all — it only runs when Mike (or
  whoever's using the DripDrop account) manually hands over 1-3 candidates in chat.

Goal: get both motions to run reliably, twice a week, without requiring a human to
remember — while still letting a human run them manually whenever they want, with the
automation only picking up the slack.

This spec covers two independent pieces of work that happen to ship together:

1. **PipelineBlast** — expand from 2 to 4 weekly targets, and richen each target from a
   bare role string to a full JD, threading that JD into the server-side bench-matching
   step (Component 2) for better slate quality.
2. **CandidateBlast** — a new 2x/week scheduled fallback that finds recently-added ATS
   candidates nobody has run CandidateBlast for yet, and runs it on their behalf.

These are independent (different code paths, different failure modes) but ship
together because they share a scheduling constraint (see "Contention" below) and were
requested as one unit.

## A. PipelineBlast: 4 weekly targets, JD-driven

### A.1 — Target lineup

Chosen from the live ATS bench (3,739 candidates as of 2026-07-21), picking the two
best-represented role families not already covered by the existing two routines:

| Day | Time | Target | Status | Bench size |
|---|---|---|---|---|
| Mon | 8am MT | Project Manager / Construction / US | **new** | ~158 (PM + Sr PM) |
| Tue | 8am MT | Estimator / Engineering / US | existing | ~33 (Estimator family) |
| Wed | 8am MT | Superintendent / Construction / US | **new** | ~175 (Superintendent variants) |
| Thu | 8am MT | Plant Manager / Manufacturing / US | existing | ~39 |

Same cadence, geography convention (US-wide, per-company in-state ZoomInfo pull), and
company-count-per-run (7 companies/run) as the existing two routines.

### A.2 — Richer target definition (JD block, not a bare string)

Each of the 4 routines' target expands from `{role, geo, industry}` to a structured JD:

```json
{
  "title": "Project Manager",
  "location": "US-wide",
  "industry": "Construction",
  "years_experience": "5+",
  "must_have": ["ground-up commercial construction", "budget/schedule ownership"],
  "nice_to_have": ["OSHA 30", "Procore"]
}
```

This JD block is authored once per routine (as part of its cloud-routine prompt) and
used two ways:

- **Sourcing (unchanged mechanism, richer input):** still drives Phase 1 job-posting
  search and the ZoomInfo title gate exactly as today — no code change, just a more
  detailed prompt per routine so "hiring for this role" filtering is more precise
  (e.g., years-of-experience helps distinguish senior vs. junior postings).
- **Bench-matching (new, see B below):** the JD is also serialized to text and sent as
  `jd_text` on the 5x3 campaign POST, so Component 2's AI scorer judges fit against real
  requirements instead of a bare role/industry string.

## B. Component 2 code change: thread `jd_text` through bench-matching

Today, Component 2 (`flowdrip_app.py`) sources and scores candidates using only a bare
role + industry string:

- `_ats_owner_candidates(owner, role, industry, limit)` → `ats.keyword_search(role or
  industry, owner=owner)`
- `_ai_score_candidates(client, company, role, industry, pool)` → prompt built from role
  + industry only

### Changes

- `_ats_owner_candidates` gains an optional `jd_text: str = None` param. When present,
  source via `ats.jd_search(jd_text, owner=owner)` (already exists — does AI-based JD
  extraction into title/must_have_skills/nice_to_have/seniority, then FTS) instead of
  `ats.keyword_search(role)`. When absent, behavior is byte-identical to today.
- `_ai_score_candidates` gains an optional `jd_text` param; when present, the scoring
  prompt includes the full JD (years of experience, must-haves, nice-to-haves) instead
  of just role + industry, for a more precise 0-100 fit score. When absent, unchanged.
- `jd_text` threads through the full chain, optional at every hop, defaulting to `None`
  everywhere so existing callers (4x4/5x5, and CandidateBlast's pinned-slate flow, which
  never sets it) are byte-identical:
  - `_match_pipeline_to_company(client, company, role, industry, owner=None,
    jd_text=None)`
  - `_api_resolve_5x3_cards(client, spec, owner=None)` — reads `spec.get("jd_text")`
    and passes it through
  - `_api_campaign_core` — no signature change; `jd_text` just flows through `spec`
- New optional `jd_text` field accepted on `POST /api/v1/campaigns` (validated as a
  string if present, no length cap beyond the existing body-size limits).

### Explicitly out of scope

- No change to `_build_slate_cards`, `_pool_record_by_id`, the résumé-build path, or the
  fit-floor constant — `jd_text` only affects *sourcing* and *scoring*, not slate
  assembly or PDF generation.
- No change to the CandidateBlast pinned-slate path (`candidates[]` present → `jd_text`
  is never consulted, matching today's `_api_resolve_5x3_cards` short-circuit).

## C. CandidateBlast: 2x/week fallback safety net

### C.1 — Trigger

Two new scheduled routines:
- **Tue 11am MT** and **Fri 8am MT** — deliberately off the Mon-Thu 8am MT block used by
  PipelineBlast (see "Contention" below).

### C.2 — Per-fire logic

1. **Find candidates:** query the ATS for talents where `created_at` is on/after the
   last fallback check (rolling window — each fire only looks back to its own previous
   fire, roughly 3-4 days given the 2x/week cadence), scoped to Mike's `owner_email`,
   excluding any candidate already present in the tracker file (C.4).
   - Nothing found → log "0 pending, nothing to do" and stop. This is not an error.
2. **Score for résumé-fit quality:** for each pending candidate, AI-score their résumé
   against **their own stated target role** (from their ATS profile) — 0-100, "how
   strong is this person's résumé for the role they're aiming for." This is a
   self-fit/quality signal, distinct from CandidateBlast's own job-opening fit scoring
   (which happens later, inside each run, against real postings).
3. **Filter to the fit floor:** keep only candidates scoring ≥ 70/100 ("amazing" —
   number chosen by me, flagged for sign-off). Anyone below the floor rolls forward
   untouched to the next fire (they stay eligible — not marked processed, not
   discarded).
4. **Batch:** group the qualifying candidates into groups of ≤3 (CandidateBlast's own
   per-run cap).
5. **Cap the fire:** run **at most 3 batches (9 candidates) per fire** — a safety bound
   I proposed, flagged for sign-off, to prevent an unbounded backlog from producing
   unbounded live campaign sends / ZoomInfo spend in a single fire. Any qualifying
   candidates beyond the cap roll forward to the next fire (still eligible, still above
   the fit floor — just deferred, not penalized).
6. **Run:** invoke the CandidateBlast skill once per batch, exactly as if a human had
   handed over that batch of ≤3 candidates in chat. No behavior change inside
   CandidateBlast itself — same phases, same autonomy, same hard rules.
7. **Record:** after each batch's run completes (success, partial, or skip), append
   every candidate in that batch to the tracker file (C.4) with `triggered_by=auto`,
   regardless of whether CandidateBlast found them a fit — once attempted, a candidate
   is not retried by the fallback again. (A human can always re-run someone manually.)

### C.3 — Manual path also writes the tracker

The CandidateBlast skill (`~/.claude/skills/candidateblast/SKILL.md`) gets one new
closing step in its "what done looks like" phase: after any run completes (manually
triggered, from chat), append the candidates on that run's slate to the same tracker
file with `triggered_by=manual`. Without this, the fallback has no way to know a human
already handled someone, and would re-run them.

### C.4 — Tracker file

New file, mirroring the existing dedupe-master convention
(`C:\Users\mkvau\claude\candidateblast\companies_master.csv`):

`C:\Users\mkvau\claude\candidateblast\candidateblast_processed.csv`

Columns: `ats_id, name, run_at, triggered_by` (`triggered_by` ∈ `{manual, auto}`).

This is a append-only log — nothing ever removes a row. "Already processed" = "ats_id
appears in this file," full stop; there's no re-eligibility window.

### C.5 — Fallback window state (separate from the tracker)

The "since the last automated check" window (C.2 step 1) needs its own anchor,
independent of the candidate tracker — the tracker mixes manual and auto rows, and using
a manual run's timestamp as the window anchor would wrongly narrow the next auto fire's
lookback. A small separate state file holds just the last **auto** fire's timestamp:

`C:\Users\mkvau\claude\candidateblast\candidateblast_fallback_state.json` —
`{"last_fire_at": "<ISO timestamp>"}`, overwritten at the end of every fallback fire
(whether or not any candidates qualified).

**Bootstrap case:** if this file doesn't exist yet (the very first fallback fire), default
to a 7-day lookback instead of failing or looking back indefinitely. Every fire after
that uses the rolling window against the previous fire's recorded timestamp.

## D. Contention

Existing constraint (from prior BD-agent work): concurrent scheduled routines fight
over the same Claude-in-Chrome browser session used for DripDrop campaign launches.
The 6 total routines after this change (4 PipelineBlast + 2 CandidateBlast) must never
overlap:

| Day | 8am MT | 11am MT |
|---|---|---|
| Mon | PipelineBlast (PM) | — |
| Tue | PipelineBlast (Estimator) | CandidateBlast fallback |
| Wed | PipelineBlast (Superintendent) | — |
| Thu | PipelineBlast (Plant Mgr) | — |
| Fri | CandidateBlast fallback (8am) | — |

## E. Error handling

- ATS query failure (C.2 step 1) → log and abort the fire cleanly (same as a PipelineBlast
  routine's existing preflight-abort pattern) — never partially process.
- Résumé-fit scoring failure for one candidate (C.2 step 2) → treat as below-floor for
  this fire (skip, roll forward), do not abort the whole fire over one bad score. Mirrors
  `_ai_score_candidates`'s existing "return [] on any failure" fail-soft pattern.
- A batch's CandidateBlast run failing/erroring mid-way → still record the batch's
  candidates as `triggered_by=auto` (an attempt was made; re-running automatically next
  fire risks repeat failures against the same bad input) — a human can re-run manually
  if warranted.
- Tracker file missing/corrupt on read → treat as empty (nobody processed yet) rather
  than aborting; on write, create if absent.

## F. Testing

- **Component 2 `jd_text` threading (flowdrip_app.py):** TDD, same pattern as the
  recent ATS-matching fix — mock `ats.jd_search`/`ats.keyword_search`, verify: (a)
  `jd_text` present → routes to `jd_search`; (b) absent → routes to `keyword_search`,
  byte-identical to pre-change behavior; (c) scoring prompt includes JD content when
  given. Full suite re-run to confirm the existing 5 pre-existing/unrelated failures are
  the only ones (no new regressions).
- **CandidateBlast fallback logic:** this is orchestration inside a scheduled routine's
  prompt/skill instructions, not flowdrip_app.py code — no unit tests in the
  pytest sense. Verification is a live dry-run-style smoke check (mirroring how the
  original CandidateBlast skill was smoke-tested) before the routines go live: seed a
  couple of test candidates with old/new `created_at` values, confirm the fallback picks
  up only the new ones, respects the tracker, and stops correctly when nothing qualifies.

## Open numbers flagged for sign-off (asked once already, restating for the written record)

- Résumé-fit floor for backlog scoring: **70/100**.
- Batch cap per fallback fire: **3 batches / 9 candidates**.

## Out of scope for this spec

- Any change to the PipelineBlast app-connector (partners running via their own claude.ai
  account) — that's a separate, already-spec'd rollout (see
  `2026-07-21-pipelineblast-app-connector-design.md`).
- Any change to CandidateBlast's own job-search / auto-pick / campaign-launch mechanics —
  only *what feeds it and when* changes, not what it does once fed.

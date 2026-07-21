# Arena 5×5 Switch — Design

- **Date:** 2026-07-21
- **Status:** Approved (design), pending implementation plan
- **Related:** `docs/5x5_sequence_setup.md` (5×5 copy/mechanics), `docs/superpowers/plans/2026-07-20-arena-5x5-sequence.md` (5×5 build plan), memory `dripdrop-5x5-sequence`, `dripdrop-campaign-start-date-monday`, `dripdrop-prod-deploy-drift`

## Background

The **Arena 5×5** sequence (a warmer clone of the 4×4 — solo "I" voice, one-candidate spotlight on email 2, candidate aliases, a verbatim day-5 follow-up "bump", and an Interview-Guide PDF on the day-8 email; step delays `0,3,0,0,2,3,4`) was **built in the local working tree on 2026-07-20 but never deployed to prod.** Prod currently has **0** 5×5 campaigns and 115 4×4 campaigns (84 with pending sends).

Mike wants:
1. The **21 not-yet-started** 4×4 campaigns (0 sent, all currently dated 2026-07-21) switched to **full 5×5**.
2. **Going forward, 5×5 becomes the default** for the BD skills/routines; 4×4 is retired from the automated pipeline (kept in code).

Anything **already sending** (the other 63 pending 4×4s) is explicitly **left as-is**.

## Divergence state (critical)

Prod and the local repo have diverged in *both* directions and must not be blind-deployed against each other:

- **Prod `flowdrip_app.py`** = `feat/self-serve-api-keys` baseline **+ the `_next_business_day` start-date fix shipped 2026-07-21 directly to prod.** It does **not** have the 5×5 code or the candidate-bullet-format drift.
- **Local working tree `flowdrip_app.py`** = baseline **+ the 5×5 build + candidate-bullet drift**, but **not** `_next_business_day`.

Therefore a full-file deploy from local would revert today's start-date fix and drag in unreviewed drift. The 5×5 must be ported **surgically**.

## Goals

- Get the 5×5 template live on prod without disturbing the live 4×4 or the `_next_business_day` fix.
- Convert the 21 not-yet-started 4×4 campaigns to full 5×5, pilot-gated, starting sends **2026-07-22**.
- Make 5×5 the default for new campaigns created by the BD skills/routines.

## Non-goals (out of scope)

- The 63 already-started 4×4 campaigns — untouched.
- The **newsletter content-generation** automation change — separate design/spec. (This design only touches newsletter enrollment at the seam noted below.)
- Full reconciliation of the local↔prod divergence beyond what is required to ship 5×5 safely (noted as follow-up, not chased here).

## Approach

### Conversion mechanism (chosen: A)

**A — Re-launch each campaign via the campaign API, called from localhost on the prod server.** For each target campaign: cancel the existing 4×4 pending items, then `POST http://127.0.0.1:8080/api/v1/campaigns` with `template = "fivebyfive"`, reusing the company + contacts (+ candidate slate + `enroll_newsletter`) read from the existing campaign JSON, with `start_date` for the batch = `2026-07-22`.

Rationale: it is the exact path new campaigns will use going forward (so it also validates the "going forward" change), produces clean full-5×5 content, and calling **localhost** sidesteps the browser / Claude-in-Chrome egress problems (the sandbox and external egress can't reach `dripdripdrop.ai`, but the prod box can hit its own port).

Rejected: **B** (script calls generator internals directly — less faithful to the real launch path); **C** (stamp 5×5 overrides onto existing 4×4 copy — does not deliver the *full* 5×5 voice Mike asked for).

## Work breakdown

### 1. Port the 5×5 template to prod (prerequisite)
Surgically apply, onto prod's *current* file, the 5×5 additions from the local working tree:
- the `fivebyfive` tuple in `AICB_CAMPAIGN_TYPES` (under `fourbyfour`),
- `_apply_fivebyfive_overrides` (verbatim bump / interview-guide line / pinned delays `0,3,0,0,2,3,4`) and its call in `_aicb_build_campaign_from_brief`,
- the `_ARENA_SLATE_TYPES = {fourbyfour, fivebyfive}` family set,
- the chooser tile + `elif k == "fivebyfive"` routing,
- the Interview-Guide PDF asset + its `_PDF_KIND_KEYWORDS` mapping (so the PDF attaches by keyword).

Validate with `tests/test_arena_5x5.py` (7 expected pass). Deploy via the safe single-file path (backup prod, server-side `py_compile`/`ast.parse`, health-gated restart, rollback armed) — the same mechanism used for the start-date fix. Re-verify prod's real state first (grep for `_next_business_day`, self-serve keys, etc.) so nothing live is lost.

### 2. Pilot (gate before batch)
Convert **1–2** of the 21 via Approach A. Verify on prod: 5 emails present; day-5 bump text is the verbatim template; **Interview-Guide PDF actually attaches** to the day-8 email; every scheduled date is a weekday; contacts and `enroll_newsletter` preserved. Do not proceed to batch until the pilot renders correctly.

### 3. Convert the remaining 19
Approach A for the rest, `start_date = 2026-07-22`. Back up campaign JSONs + queue first. Verify per campaign (schedule weekday-only, contacts_queued matches, no leftover 4×4 pending items). Expect the known transient `Queue save error (.tmp -> .json)` if a requeue overlaps a scheduler tick — harmless.

### 4. Flip the default to 5×5, retire 4×4
Update the **denver-bd-pipeline** and **regional-bd-pipeline** skills (the `.skill` bundles + any installed copy the routines load) and any routine prompt text so new campaigns launch `fivebyfive`. 4×4 remains defined in code but leaves the automated pipeline. Skills must be **re-imported/installed** for the cloud routines to pick up the change (same propagation caveat as the start-date skill edit).

## Data flow (per converted campaign)

1. Read existing campaign JSON → extract `company`, `contacts[]`, candidate slate, `enroll_newsletter`, `industry`/`location`/`roles` where present.
2. Cancel the campaign's pending 4×4 queue items (bind user context: `_CURRENT_USER_EMAIL.set(owner)` + `_switch_to_user_paths(owner)`; **export `DRIPDROP_DATA_DIR=/opt/dripdrop/data`** so the real queue is used, not the stray `app/DripDrop` path).
3. `POST 127.0.0.1:8080/api/v1/campaigns` with `template=fivebyfive`, `start_date=2026-07-22`, and the extracted fields.
4. Confirm the 200 response: `steps` reflects 5×5, `schedule` all weekdays, `newsletter_enrollment.matched` where applicable.

## Newsletter integration seam
Going-forward 5×5 launches (and these conversions) set `enroll_newsletter`. Today they reuse the campaign's existing list name. **Once the separate newsletter auto-select/create design ships, that logic becomes the source of the `enroll_newsletter` value** (check for an industry+geography list; create a simple `<Geography> <Industry>` list if none fits). This spec does not implement that logic; it only notes that the enroll step is where the two designs meet.

## Risks & mitigations
- **Deploy-drift trap** → surgical port + re-verify prod state before/after; single-file deploy; backup + rollback.
- **Interview-Guide PDF may not attach on prod** → the pilot explicitly checks a real attached PDF before batch.
- **Real outbound email to 21 companies** → pilot-gated; start date pushed to 2026-07-22; per-campaign verification.
- **Wrong queue path on scripted cancel/requeue** → assert `_user_queue_path()` starts with `/opt/dripdrop/data/users/` before any mutation (this bit us on the start-date requeue).
- **API key** for the localhost call must be Mike's per-user prod key → locate/confirm before the batch.

## Acceptance criteria
- Prod serves 5×5 (`_next_business_day` and self-serve features still present; health 200; clean scheduler restart).
- The 21 target campaigns are 5×5 (5 emails + bump + attached Interview-Guide PDF), all sends weekday-only, step-1 on 2026-07-22, contacts/newsletter preserved, no residual 4×4 pending items.
- The 63 already-started campaigns are unchanged.
- The BD skills/routines create `fivebyfive` by default; a fresh test launch produces a 5×5.

## Open items to confirm during planning
- Interview-Guide PDF asset presence + keyword mapping on prod after port.
- Location of Mike's prod per-user API key for the localhost call.
- Exact reachability/response of `POST 127.0.0.1:8080/api/v1/campaigns` on the prod box.

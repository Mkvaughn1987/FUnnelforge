# Arena 4×4 — Same-Day Follow-Up Call — Design

**Date:** 2026-06-27
**Status:** Awaiting user review

## Problem

The Arena 4×4 ("fourbyfour") template is a 4-email BD sequence with no phone
touchpoint. The user wants a follow-up phone call **on the same day as the second
email** ("Top Talent Insights"), so the rep calls while that email is fresh in the
prospect's inbox.

## Goal

Every new Arena 4×4 campaign includes a `step_type:call` touchpoint scheduled the
same day as email 2, with a script that follows up on the insights email and the
candidate slate. Email cadence and all other 4×4 behavior stay unchanged.

## Decisions (locked with user, 2026-06-27)

- **Scope = the template.** All future Arena 4×4 campaigns get the call, not a
  one-off edit to an existing saved campaign.
- **Call purpose = follow up on email + candidates.** Reference the Top Talent
  Insights email and the candidate slate, ask if they saw the profiles,
  quick-qualify hiring timeline. Conversational, not pushy.
- **Label = keep name, update count.** Stays "Arena 4×4" (still 4 emails); the chip
  step count and description reflect the added call.

## How the 4×4 is built (context)

The `fourbyfour` entry in `AICB_CAMPAIGN_TYPES`
([flowdrip_app.py:4084](../../flowdrip_app.py)) is a 7-tuple
`(key, name, duration_label, color, description, best_for, touch_sequence)`. The
`touch_sequence` is prose fed to an AI (Haiku) that returns the actual campaign steps
as JSON (`{"emails":[{...step...}]}` — the array holds all step types, keyed by
`step_type`). Each step carries a **relative** `delay_days` (gap from the previous
step); the scheduler accumulates them and lays steps on business days
([flowdrip_app.py:5577](../../flowdrip_app.py)). `delay_days:0` therefore lands a
step on the same cumulative day as the prior step.

Current 4×4 sequence (all `email_auto`): day 0, +3, +4, +4 → emails on days 0, 3, 7,
11.

## Architecture

Two small edits in `flowdrip_app.py`. No new functions, no schema change, no data
migration.

### 1. Edit the `fourbyfour` template tuple (~L4084)

- **Insert a new Step 3 — Follow-up Call** (`delay_days:0, step_type:call`),
  explicitly marked *same day as the Top Talent Insights email*. Script body
  references the insights email + candidate slate, asks if they reviewed the
  profiles, quick-qualifies hiring timeline; conversational tone.
- **Renumber** old Step 3 → Step 4 and Step 4 → Step 5. Their `delay_days` (4 and 4)
  are unchanged, so the email schedule is identical (days 0, 3, 7, 11); the call
  shares day 3 with email 2.
- **Update the duration label** `"4 steps - 2 weeks"` → `"5 steps - 2 weeks"`.
- **Update the description** to note the same-day call after email 2. Name stays
  "Arena 4×4".

### 2. Relax the delay-rule in the generation prompt (~L35085)

The build prompt currently says *"Never set multiple steps to 0 except the first."*
That fights the call's intentional `delay_days:0`. Reword to permit a `delay_days:0`
step **when the sequence explicitly specifies it** (a same-day touch, e.g. a call
paired with an email). The rule still discourages the model from accidentally
collapsing a schedule to all-zeros; it only allows an intentional same-day step.
Applies to both the template and custom ("byos") paths, but only as a permission.

## Data Flow

```
fourbyfour.touch_sequence (now includes Step 3 call, delay_days:0)
        │  fed to Haiku build prompt (delay-rule now permits explicit 0)
        ▼
campaign_data["emails"] = [email1, email2, call(delay 0), email3, email4]
        │  scheduler accumulates delays: 0, 3, 3, 7, 11 (business days)
        ▼
email2 and the call both land on day 3; call surfaces as a "call" task
```

## Why other 4×4 logic is NOT affected

- **Resume auto-attach** (`_resume_attach_indices`, positional `[1,3]`) is **dead for
  the 4×4**: `_resume_pdfs` stays empty on this path — résumés are built by
  `_aicb_build_redacted_resumes` and surfaced in the picker, not auto-attached
  (comment at [flowdrip_app.py:34953](../../flowdrip_app.py)). No change needed.
- **"All emails same day" guardrail** ([flowdrip_app.py:7807](../../flowdrip_app.py))
  filters to email steps only, so a `delay_days:0` call never trips it, and the four
  emails keep their non-zero delays.
- **Cited-stats block** ([flowdrip_app.py:35045](../../flowdrip_app.py)) and the
  candidate-weaving instructions reference emails by content ("Email 2", "Email 4"),
  not by array index; the AI numbers emails, and the call is not an email.

## Known, accepted behavior (out of scope)

The post-generation loop ([flowdrip_app.py:35115](../../flowdrip_app.py)) prepends
`"Hi {FirstName},"` and wraps the house font on **every** item in the array,
including non-email steps. The new call's script will get that treatment — exactly as
talentdrop's and blitz's call steps already do today. Consistent with existing
behavior, so left unchanged. A `step_type` guard to skip non-email steps is a
possible small improvement but would alter other templates, so it is deliberately not
in scope.

## Error / Edge Handling

- **Model ignores the explicit 0 and bumps the call to day 1** → call lands one day
  after email 2 instead of the same day. Mitigated by the relaxed delay rule plus an
  explicit "SAME DAY" note in the step text. Acceptable degradation (call still
  fires, one day off) rather than a crash.
- **Model omits the call step** → campaign generates as a 4-email sequence (today's
  behavior). No crash.

## Testing

Pure-data / render checks (no live AI):
- The rendered `fourbyfour` `touch_sequence` contains a `step_type:call` with
  `delay_days:0`, positioned after the Step 2 ("Top Talent Insights") email and
  before the Proven Results email.
- The `fourbyfour` duration label reads "5 steps - 2 weeks".
- The generation prompt no longer contains the absolute "Never set multiple steps to
  0 except the first" wording, and contains the same-day permission.

Manual: generate a 4×4; confirm on the schedule that email 2 and the call share a
day, emails still land on days 0/3/7/11, and the call shows as a call task with a
script referencing the insights email and candidates.

## Files Touched

- `flowdrip_app.py` — edit the `fourbyfour` tuple (~L4084: insert call step,
  renumber, update label + description); reword the delay rule in the generation
  prompt (~L35085).
- `tests/test_arena_4x4_same_day_call.py` — new (the render/prompt assertions above).

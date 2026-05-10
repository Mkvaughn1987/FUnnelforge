# Touchpoint Quality Pass — Parked tasks (resume after Phase 2 ships)

**Date parked:** 2026-05-10
**Reason:** User pivoted to Phase 2 (Strategy Chooser + Target-a-Candidate rewrite). Tasks 1-7 of the touchpoint quality pass are SHIPPED and live; Tasks 8-11 are parked.

## What shipped (live on dripdripdrop.ai)

| Commit | Task | What it did |
|---|---|---|
| `f2d6d5c` | Task 1 | Free Flow AICB byos prompt enforces 1 LI at step 2 |
| `86dcee6` | Task 2 | Recruiting Sequence generator includes 1 LI after email 1 |
| `b21aebc` + `8931acd` | Task 3 | Free Flow wizard guardrails + tightened test |
| `e8f44eb` | Task 4 | Victory Card preset LI delay 0 → 1 |
| `9387852` | Task 5 | Per-industry market stats cache (30-day TTL) |
| `31025de` | Task 6 | Call briefing produces 3 style variants |
| `c5b5e06` | Task 7 | Today page call card pill selector + Copy |

User-visible:
- New cold-call openers in Leigh's pitch DNA, 3 trial-able variants per campaign
- Pill selector on each call card; Copy button; backwards-compat fallback for legacy briefings
- Market stats cache silently feeds the variants with real fill-window data (no hallucinated numbers)
- All NEW sequences (Free Flow AICB + Recruiting) include 1 LI at step 2 with delay_days:1
- Free Flow wizard warns (not blocks) when adding 2nd LI or LI before email 1

## What's parked (resume later)

| Plan task | What it would do |
|---|---|
| Task 8 | Voicemail variants generator (user-level, 24h TTL, 3 style variants) |
| Task 9 | Voicemail block at top of Today calls section (above per-campaign cards) |
| Task 10 | LinkedIn 3-variant generator + LI card UI pill selector |
| Task 11 | Final integration check (Phase 0 audit-test re-run) |

The plan file at `docs/superpowers/plans/2026-05-10-touchpoint-quality-pass-plan.md` has full TDD code blocks for all parked tasks. To resume:

1. Re-invoke `superpowers:subagent-driven-development` with that plan path
2. Skip Tasks 1-7 (already done; checkboxes can be marked manually)
3. Start at Task 8

Estimated effort to finish: ~30-60 minutes of subagent-flow time.

## Why parked

The user wants Phase 2 (Strategy Chooser + Target-a-Candidate guided wizard) to take priority. Voicemail-at-top + LI 3-variants are valuable but lower-urgency than reshaping the entry point to all sequences. After Phase 2 ships, finishing the touchpoint pass is a clean ~30-min follow-up.

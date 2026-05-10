# Phase 2 — Resume Note (paused 2026-05-10)

**Branch:** `claude/critical-bug-fixes`
**Status:** Tasks 1-3 of 9 complete. NOT yet deployed. Resume in a fresh session.

---

## What's done in this session

| Task | Commit | What it did |
|---|---|---|
| Spec | `93510d2` | Strategy Chooser + Target-a-Candidate design |
| Plan | `80862e0` | 9-task implementation plan with TDD code blocks |
| Task 1 | `796f0ac` | AppState slots: `_chooser_origin`, `tc_step`, `tc_jd_text`, `tc_jd_filename`, `tc_jd_parsed`, `tc_jd_generating`, `tc_candidates`, `tc_preset`, `tc_generating`, `tc_error` |
| Task 2 | `fb2c5d2` | 5-card Strategy Chooser replaces "Choose a Sequence Type" |
| Task 3 | `1466bc1` | AICB page banner reads `_chooser_origin` and renders Client/Market framing |

**Tests:** 281 passing locally. No regressions.

**Deploy status:** NOT deployed. The Target-a-Candidate card on the new chooser routes to `s.sp = "target_candidate"` but no handler exists yet (Tasks 4-9 build the wizard). Deploying now would expose a card that breaks on click.

## What's left

Tasks 4-9 in [docs/superpowers/plans/2026-05-10-strategy-chooser-target-candidate-plan.md](../plans/2026-05-10-strategy-chooser-target-candidate-plan.md):

- **Task 4** — `p_target_candidate` page handler + 4-step stepper UI scaffold
- **Task 5** — Step 1: JD upload/paste + AI metadata parsing (`_tc_parse_jd` helper)
- **Task 6** — Step 2: CSV candidate upload + preview table
- **Task 7** — Step 3: Sequence preset 4-card grid (1 email / 2 emails 1 day / 3 emails 3 days / Create Your Own)
- **Task 8** — Step 4: AI generation using JD context + handoff to existing email editor
- **Task 9** — Final integration check + Phase 0 audit-test re-run

Estimated effort: ~1-2 hours of subagent-flow time.

## How to resume

In a fresh session:

1. Confirm branch state:
   ```bash
   git log --oneline -10
   # Expect: 1466bc1 banner ; fb2c5d2 chooser ; 796f0ac state ; 80862e0 plan ; 93510d2 spec
   git status --short
   # Expect: M flowdrip_app.py + .claude/settings.local.json (the WIP rename + the editor settings)
   ```

2. Re-stash the WIP rename if present (recommended — see "WIP rename caveat" below):
   ```bash
   git stash push -m "WIP: campaign->sequence rename pre-phase2-resume" -- flowdrip_app.py
   ```

3. Invoke the workflow:
   ```
   Use superpowers:subagent-driven-development with the plan path
   docs/superpowers/plans/2026-05-10-strategy-chooser-target-candidate-plan.md
   Skip Tasks 1-3 (already done — mark checkboxes manually).
   Start at Task 4.
   ```

## WIP rename caveat

`stash@{0}` holds the campaign → sequence terminology rename (~521 lines of `flowdrip_app.py`). When you try to pop it after Phase 2 ships, you will hit a merge conflict because Phase 2 added new code to the file.

Recovery options:
- **(Recommended)** After Phase 2 lands, resolve the conflict manually — most overlaps are unrelated lines that just happen to be near each other. `git stash show -p stash@{0}` shows the diff; pick which side to keep per chunk.
- Drop the stash and redo the rename (it's a global text replacement; takes <5 min with sed or a regex find/replace).
- Pop the stash NOW (before Phase 2 Task 4 starts) and re-stash before each subsequent task — but this gets tedious across 6 more tasks.

Your call when you resume. Don't lose the stash though — it's real work.

## Routing context for Tasks 4-9

The new chooser uses `s.sp = "target_candidate"` to route to the wizard. This is NOT the spec's original `s.screen = "target_candidate"` — the actual codebase pattern is `s.sp` (sub-page). Tasks 4-9 must wire the page-handler dispatch using `s.sp == "target_candidate"`, not `s.screen`. See `flowdrip_app.py:fb2c5d2` for the routing pattern Task 2 used.

Other state/screen patterns confirmed during Tasks 1-3:
- AppState style: `__init__`-based with `self.x: type = default` typed annotations
- Color dict in scope at chooser/AICB: `C` (e.g., `C["teal"]`, `C["ink"]`, `C["muted"]`)
- AICB handler name: `p_ai_campaign` (not `p_aicb`)
- Saved-Sequences route: `s._tab = "saved"`
- Build-from-scratch route: `s._tab = "custom"` + `s.aicb_camp_type = "byos"`

Tasks 4-9 in the plan reference `s.screen` in their code blocks — substitute `s.sp` everywhere.

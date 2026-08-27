# Restore Build Your Own Sequence (step-based builder)

**Date:** 2026-08-27
**Status:** Awaiting approval
**Scope:** Replace the current count/cadence "AI Guided Sequence Builder" (`p_seq_builder`) with the original step-by-step, drag-to-reorder builder shipped 2026-05-23 and reverted ~90 minutes later the same day. Add a save-with-name step after generation, and surface saved reusable styles directly on the "Start a Sequence" chooser page.

## Why

The original step-based builder (blank start, add steps of any type in any order, real drag-and-drop, per-step hint-or-copy input) was built and approved (see `2026-05-23-ai-guided-sequence-builder-design.md`), then swapped same-day for a rigid "pick touch counts per channel + a cadence span" screen. The count-based version is what's live today. The user wants the original step-based builder back, wants it to fully replace the count-based screen (not coexist as a second mode), and wants two related gaps closed along the way:

1. Generated campaigns currently save under an auto-generated timestamp name (`Campaign_MMDDHHMMSS`) instead of the AI's suggested title, with no way to rename — a real bug in `save_campaign()` (it reads `camp["name"]`, but the generator writes `camp["campaign_name"]`).
2. "My Campaign Styles" (a separate, pre-existing feature — lightweight reusable briefs, not full campaigns) is only reachable by digging into the AI Campaign Builder (AICB) wizard's Free Flow sidebar. The user wants saved styles reusable directly from the "Start a Sequence" chooser page.

## Non-goals

- Building a new email editor — the generated sequence still lands in the existing one
- Touching the preset templates (Arena 4×4/5×5/5×3, Target a Company/Market, Find Candidates, MPC) — untouched
- Changing the "My Campaign Styles" data shape (`{id, name, description, created_at}`) — reused as-is
- Multi-language AI copy, A/B variants, send-time optimization — unchanged, out of scope
- Renaming a campaign after it's already saved (the existing static-label header in the email editor stays as-is) — only the *first* save gets a name prompt

## Part 1 — Restore the step-based builder

### Entry point

Unchanged routing: the "Build from scratch" chooser tile (`CHOOSER_OPTIONS` key `"scratch"`) already sets `s.sp = "seq_builder"` (`flowdrip_app.py:18921-18929`). Its description text (`flowdrip_app.py:18776-18779`) already reads *"Add steps (email, LinkedIn, call, SMS, task) in any order, drag to reorder..."* — stale copy left over from the original build that becomes accurate again once this ships. No chooser-tile changes needed.

### Page layout (replaces the current `p_seq_builder` body, `flowdrip_app.py:28221-28525`)

Same structure as the original 2026-05-23 spec:

**Section 1 — Campaign brief**: `Goal of this sequence` (textarea, 2 rows), `Who you're sending to` (input), `Tone` (radio chips: Consultative/Direct/Casual/Formal, default Consultative). All optional — inline copy: *"Skip these and AI will guess from each step's content."*

**Section 2 — Steps**, with a live timeline strip pinned above it:
```
Day 0 ✉  →  Day 2 in  →  Day 4 ☎  →  Day 7 ✉    [4 steps · 7 days · 2 emails · 1 LinkedIn · 1 call]
```
Action row: `[+ Add Email] [+ Add LinkedIn] [+ Add Call] [+ Add SMS] [+ Add Task]` — appends a step card. Each card: drag handle (≡), type badge + cumulative-day chip, per-step day-offset number input (relative to the previous step, clamped ≥0), single textarea (*"What this step should say (or instructions for AI)"*, placeholder rotates by type per the original spec's hint/copy examples), × remove button.

**Generate button**: sticky, `Generate Sequence →`, disabled until ≥1 step. Soft warning banner at 10+ steps, hard block at 15 (Add buttons disabled).

Reused as-is, no changes needed: `_SB_VALID_TYPES` / `_SB_TYPE_LABELS` (`flowdrip_app.py:34229-34231`), `_sb_parse_campaign` (`flowdrip_app.py:34335-34370` — its output shape already matches this flow).

### Drag-and-drop

SortableJS via a single injected `<script>` tag, `onEnd` handler reorders `s.sb_steps` and calls `rf()`. Same rationale as the original spec: works without touching NiceGUI's element tree at runtime, ~20KB, handles touch natively (no arrow-button fallback).

### State model

Replace the current cadence-era AppState fields (`flowdrip_app.py:11547-11569`: `sb_counts`, `sb_span`, `sb_special`) with:

```python
self.sb_goal: str = ""
self.sb_audience: str = ""
self.sb_tone: str = "consultative"   # kept as-is
self.sb_steps: list = []             # [{id, type, delay_days, input}, ...]
self.sb_generating: bool = False     # kept as-is
self.sb_error: str = ""              # kept as-is
```

Persists in `app.storage.user` (unchanged pattern) so a reconnect doesn't wipe a half-built sequence.

### AI prompt (`_sb_build_prompt`, rewrite of `flowdrip_app.py:34254-34332`)

Change the signature from `(tone, counts, span, special="")` to `(tone, goal, audience, steps)`. **Keep** the existing `_DRIPDROP_PLAYBOOK` and `_style_guide_prompt()` injection (added after the original spec was written — this is current, live behavior and must be preserved). Replace the counts/span section of the prompt with the original per-step block:

```
GOAL: {goal}
AUDIENCE: {audience}
TONE: {tone}

STEPS the user defined (in order, with relative day offsets):
  Step 1: EMAIL, Day 0
    User direction or draft: {step.input}
  ...

For each step, decide whether the user's text is INSTRUCTIONS or DRAFTED COPY:
- INSTRUCTIONS: write final copy from scratch.
- DRAFTED COPY: lightly polish (typos, merge fields, tightening) without rewriting voice.

Output JSON: {"campaign_name", "synopsis", "emails": [{"name", "subject", "body", "delay_days", "time", "step_type"}, ...]}
```

Output shape is unchanged from today, so `_sb_parse_campaign` needs no edits.

### Validation

| Rule | Behavior |
|---|---|
| 0 steps + click Generate | Toast: "Add at least one step before generating." |
| Empty step input | Allowed — inline hint: "(empty — AI will improvise)" |
| Day offset < 0 | Clamped to 0 |
| >15 steps | Add buttons disabled; red note at the cap |

## Part 2 — Save-with-name step

Today, clicking Generate silently calls `save_campaign()` and jumps straight to the email editor. `save_campaign()` (`flowdrip_app.py:4897-4946`) reads `camp.get("name")`, which is never set by the generator (it sets `camp["campaign_name"]`) — so every sequence-builder campaign, past and present, saves under an auto-generated `Campaign_MMDDHHMMSS` name instead of the AI's suggested title, and there is no rename UI anywhere downstream.

**New behavior**: after a successful generation, instead of auto-saving and routing immediately, show an inline confirmation card:

- Campaign name field, pre-filled with the AI's `campaign_name`, editable
- Checkbox: **"☆ Also save as a reusable Campaign Style"** (unchecked by default)
- **"Save & Continue →"** button

On save:
1. Write the (possibly edited) name into `camp["name"]` before calling `save_campaign()` — fixes the bug directly at the source rather than patching `save_campaign()`'s fallback logic.
2. If the checkbox is checked, also append `{id: uuid4(), name: <same name>, description: <sb_goal + sb_audience + tone, or the AI's synopsis if the brief fields were left blank>, created_at: now}` to the user's styles via the existing `_load_my_campaign_styles()` / `_save_my_campaign_styles()` pair (`flowdrip_app.py:2209-2228`) — no schema changes.
3. Proceed exactly as today: `_camp["status"]="draft"`, `_camp["created"]=date.today().isoformat()`, `_camp["_owner_email"]`, `s.loaded_camp`/`s.loaded_view="emails"`/`s.loaded_tab=0`, route `s.sp="start_seq"; s._tab="custom"`.

## Part 3 — "My Campaign Styles" on the Start a Sequence chooser

Today, saved styles only appear inside the AICB wizard's Free Flow sidebar (`flowdrip_app.py:36602-36655`), where clicking one sets `s.aicb_camp_type = "byos"`, `s.aicb_byos_desc = <description>`, and stays on the page. That's a separate feature from Part 1/2 above — it reuses briefs to pre-fill AICB's own Free Flow generation, not the step-based builder.

**New behavior**: add a "My Campaign Styles" section to `_sq_pick`'s top-level chooser (`flowdrip_app.py:18785`, inside the `if not s._tab:` block), rendered below the 9 `CHOOSER_OPTIONS` cards.

- **Empty state**: section is omitted entirely if `_load_my_campaign_styles()` returns nothing (matches existing AICB sidebar behavior).
- **Row UI**: reuse the existing ⭐-labeled row styling (name + "✕" delete), dropping the inline "selected / expand description" toggle since clicking here navigates away immediately rather than staying on the page.
- **Click behavior**: matches the existing JD-derived custom-entry pattern (`flowdrip_app.py:38807-38824`) — `s.aicb_camp_type = "byos"`, `s.aicb_byos_desc = <style's saved description>`, `s.sp = "ai_campaign"`, `rf()`. Lands the user on AICB step 1 with Free Flow pre-selected and pre-filled, same entry semantics as every other "reuse" path in the app.
- **Delete**: same "✕ remove" affordance as the existing sidebar list, calling `_save_my_campaign_styles()` with the entry filtered out.

## Files changed

- `flowdrip_app.py` only:
  - AppState fields (~`:11547-11569`): swap cadence fields for `sb_goal`/`sb_audience`/`sb_steps`
  - `_sb_build_prompt` (~`:34254-34332`): new signature, per-step prompt block, keep playbook/style-guide injection
  - `p_seq_builder` (~`:28221-28525`): full rewrite — brief section, step cards, timeline strip, SortableJS drag-and-drop, Generate button, new save-with-name confirmation card
  - `_sq_pick` (~`:18785` on): new "My Campaign Styles" section appended after the `CHOOSER_OPTIONS` loop
  - No changes to `_sb_parse_campaign`, `_SB_VALID_TYPES`/`_SB_TYPE_LABELS`, `save_campaign()`, `_load_my_campaign_styles`/`_save_my_campaign_styles`, or the AICB wizard's own sidebar list

No new modules, no data migration.

## Verification

Manual smoke test on the live server:
1. From the chooser, click "Build from scratch" → land on the step-based builder (not the old count/cadence screen)
2. Fill in goal, audience, tone
3. Add 3 steps (Email + LinkedIn + Call), drag LinkedIn into position 1, confirm day chips renumber
4. One step with a hint, one with drafted copy, one left empty
5. Click Generate → spinner → land on the save-with-name card, pre-filled with the AI's title
6. Edit the name, check "Also save as a reusable Campaign Style", Save & Continue → land in the email editor with the 3 emails matching the structure and the edited name
7. Confirm "My Campaigns" shows the edited name, not a `Campaign_MMDDHHMMSS` timestamp
8. Go back to "Start a Sequence" → confirm the new "My Campaign Styles" section shows the just-saved style
9. Click it → confirm it lands on AICB step 1 with Free Flow selected and the description pre-filled
10. Hard-refresh mid-build (step 3) to confirm the draft persists via `app.storage.user`

## Rollout

- Single commit + zero-downtime deploy (`_deploy_flowdrip_only.sh`, single-file)
- No data migration — existing "My Campaigns" and "My Campaign Styles" entries are untouched by this change
- Verification cases above run on the live server before declaring done

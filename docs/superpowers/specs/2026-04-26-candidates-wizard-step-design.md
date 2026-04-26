# Candidates Wizard Step + Step-2 Auto-populate — 2026-04-26

## Purpose

Surface candidate selection as an explicit step in the AI Campaign Builder (AICB) wizard so users don't accidentally launch a recruiting-style campaign with no candidate data — the failure mode that produced Elizabeth Simonov's preview email shipping with raw `[CANDIDATE NAME]`, `[EXPERIENCE]`, `[KEY STRENGTH]` placeholders on 2026-04-26.

Today AICB has four candidate sources (manual text, uploaded resumes, single resume, web-research auto-gen), all reached through scattered UI affordances on step 2. Most users never find them. The fix: a dedicated step 3 with three clear options — **Pool**, **Auto-generate**, or **Skip** — plus an editable, re-rollable card grid.

While the wizard is being restructured, also add an `✨ Auto-fill industries + locations from website` helper to step 2, so the user enters the company name + URL once and AI fills the rest.

## Scope

**In scope:**
- Insert a new step 3 ("Candidates") between current step 2 (target details) and step 3 (campaign style) — wizard goes from 4 steps to 5.
- Move the **Roles** input from step 2 to step 3.
- Add a `✨ Auto-fill industries + locations from website` button on step 2.
- Add a `✨ Suggest titles` button on step 3's roles section (web-searches the company's career page + recent postings).
- Implement Pool picker (auto-filtered by roles, cap 3), Auto-generate (1–6 candidates, stepper input), and Skip on step 3.
- Render selected/generated candidates as a 2-col × up-to-3-row grid of editable cards, each with ✏️ Edit / 🔄 Re-roll / ✕ Remove controls + a footer "Re-roll all".
- Deprecate the legacy `_render_aicb_candidate_highlights` manual-text input and the `_aicb_cand_text` free-text source code path. The same `_aicb_cand_text` storage variable is reused as the AI prompt's "CANDIDATE HIGHLIGHTS" block, populated by the new card-based UI.
- Extend `_wiz_back_clear_outputs` to clear candidate state when stepping back from step 3 to step 2.

**Explicitly out of scope:**
- The `p_recruiting_campaign` (rc_*) flow at L37453. That's a separate, simpler entry point with its own UI; this spec only changes the AICB (`aicb_*`) wizard.
- The `cf_*` Candidate Finder feature (separate page that adds candidates to the pool from resume + target role).
- Changing how the candidate pool is created or stored — only how it's *consumed* during campaign building.
- Changes to the campaign-style picker (step 4 / former step 3).
- The placeholder-detection guard (`_detect_unfilled_placeholders`) is already deployed and stays as-is.
- Any rework of Pool storage schema or fields.

## Wizard Flow

### Before (4 steps)

| # | Step | Inputs |
|---|---|---|
| 1 | Target type | Company vs Market/Niche |
| 2 | Target details | Company, Website, Industry, Locations, **Roles** |
| 3 | Campaign style | Pick from AICB_CAMPAIGN_TYPES |
| 4 | Review + generate | Confirm and launch |

### After (5 steps)

| # | Step | Inputs / Changes |
|---|---|---|
| 1 | Target type | unchanged |
| 2 | Target details | Company, Website, Industry, Locations. Roles **removed**. New `✨ Auto-fill industries + locations` button. |
| 3 | **Candidates (NEW)** | Roles (with `✨ Suggest titles`) + Pool / Auto-gen / Skip + card grid |
| 4 | Campaign style | unchanged (was step 3) |
| 5 | Review + generate | unchanged (was step 4) |

## Step 2 Changes — Auto-populate

### Button placement
Standalone row directly below the Company + Website inputs, full width within the form column:

```
[ Company name: __________________________ ]
[ Website:      __________________________ ]
[ ✨ Auto-fill industries + locations from website ]
[ Industry: ______ ]   [ Locations: chips... ]
```

Standalone (rather than inline pill next to Website) for first-time discoverability.

### Behavior
- Visible only in "company" mode (`s.aicb_mode == "company"`) — niche/market mode has no website to scrape.
- Disabled until both `aicb_company` and `aicb_website` have non-empty values.
- On click:
  - Calls new AI helper `_aicb_auto_fill_target_details(s, rf)`.
  - Helper uses `web_search_20250305` tool (same pattern as `_aicb_auto_generate_candidates` at L24676).
  - Returns a parsed dict: `{"industries": [str], "locations": [str]}`.
  - Pre-fills `s.aicb_industry` (single string — picks the helper's first / primary industry) and `s.aicb_sel_locations` (list of strings, deduped, capped at 5).
- Loading state: button label swaps to "Searching the website…" with spinner; disabled during call.
- Error state: `ui.notify("Couldn't read the site — fill these in manually", type="warning")`. Does NOT block forward navigation.
- All fields remain freely editable after pre-fill — clicking the button is purely additive convenience.

## Step 3 — Candidates (the new step)

### Section A: Roles *(required, top of page)*

- Chip-style multi-input. User types a role title, presses Enter, chip appears. Click ✕ on a chip to remove.
- Below the input: `✨ Suggest titles` button.
- Click behavior of the suggest button:
  - Calls new helper `_aicb_suggest_role_titles(s, rf)`.
  - Inputs: `aicb_company`, `aicb_website`, `aicb_industry`, plus the existing free-text intent/brief field on step 2.
  - Web-searches the company's careers page and recent job postings.
  - Returns 5–8 specific titles (e.g., "CNC Machinist", "Manufacturing Engineer", "Production Supervisor").
  - Adds them as chips. User can remove any they don't want or add custom ones.
- Validation: `aicb_sel_roles` must be non-empty before the user can advance. The Skip option for candidates does NOT skip role entry — roles drive downstream campaign generation.

### Section B: Candidate source *(below roles)*

Three mutually-exclusive choice cards displayed side-by-side (or stacked on narrow viewports):

| Card | Behavior |
|---|---|
| 📋 **From Pool** | Opens picker filtered to candidates whose `target_role` field has a bidirectional, case-insensitive substring match against any chip in `aicb_sel_roles` (i.e., `chip.lower() in candidate_role.lower()` OR `candidate_role.lower() in chip.lower()`). Multi-select cap 3. Empty pool / no matches → card body shows "No candidates match yet — try Auto-generate, or add to your pool from the Candidate Pool page." |
| ✨ **Auto-generate** | Stepper input (1–6, default 3). On click of the card's "Generate" button: calls existing `_aicb_auto_generate_candidates` (extended to support `count` param, default 3, max 6 — letters A through F instead of A/B/C). |
| ⏭ **Skip** | Sets `s.aicb_cand_source = "skip"`, clears `_aicb_cand_text`, advance enabled. The campaign-style prompt still receives roles + locations as context but no candidate block. |

The user picks ONE source per campaign. Switching from Auto-gen to Pool (or vice versa) clears the previously-generated cards after a confirm dialog ("Discard the 3 candidates you generated?"). Switching either to Skip clears them silently.

### Section C: Candidate cards *(below source picker, after Pool/Auto-gen produces results)*

Layout: CSS grid, 2 columns × up to 3 rows. Single column on viewports < 640 px.

Each card shows:
- Header: candidate label/name (bold) + role/years headline below.
- Body: bullet lines (Location, Experience, Skills, Proficiencies, Certifications, Target Salary).
- Top-right control row: ✏️ ✕ 🔄

Card controls:
- **✏️ Edit** — inline expand-in-place. Each bullet line becomes a `ui.input`; header becomes editable. "Save" collapses the card back to view mode and writes back to `s._aicb_cand_text` (re-serialized as the same plain-text format the existing `_cand_block` consumer reads).
- **🔄 Re-roll** — calls `_aicb_auto_generate_candidates` with `count=1`, replaces just this card's contents. Disabled (or hidden) for Pool-sourced cards (re-roll only makes sense for AI-generated archetypes).
- **✕ Remove** — deletes the card. Decrements the count. If count hits 0, returns to the source-picker view.

Below the grid: **`🔄 Re-roll all`** button — regenerates the full set with the current count. Disabled if source is Pool.

### State persistence (going back/forward)

- Step 3 → step 2 (Back): per the H16 fix pattern, calling `_wiz_back_clear_outputs(s)` should also clear `s._aicb_cand_text` and `s.aicb_cand_source` so changing the company on step 2 doesn't leave stale candidates in step 3.
- Step 3 → step 4 (Next): all candidate state stays intact, available to the campaign-build prompt's `_cand_block` construction.

## State Changes (`AppState`)

### Existing fields (kept, possibly relocated in init order)
- `aicb_company`, `aicb_website`, `aicb_industry`, `aicb_niche`, `aicb_sel_locations`, `aicb_sel_roles`, `aicb_research`, `aicb_docs`
- `_aicb_cand_text` — kept; now populated by the new card UI instead of free-text input
- `aicb_resumes`, `aicb_candidate_resume` — kept, still consumed by `_cand_block` for upload-from-resume flows that aren't part of this spec; the new step 3 UI does not write to them

### New fields
- `aicb_cand_count: int = 3` — stepper value for auto-gen (1–6)
- `aicb_cand_source: str = ""` — one of `"pool"`, `"autogen"`, `"skip"`, or `""` (unset)
- `aicb_cand_cards: list = []` — parsed list of dicts representing each card; structure `{label, role, bullets: [str]}`. The plain-text serialization stored in `_aicb_cand_text` is derived from this list at save time so existing `_cand_block` continues to work without changes.

### Helper renames / extensions
- Extend `_wiz_back_clear_outputs` (the H16 helper) to include `_aicb_cand_text`, `aicb_cand_source`, and `aicb_cand_cards` in its cleared-fields list.
- Extend `_aicb_auto_generate_candidates(s, rf, count: int = 3)` to accept a `count` param (default 3, capped at 6). Letters become A–F. Existing call sites continue to work because the default keeps current behavior.

## New AI Helpers

Three new functions, each modeled on `_aicb_auto_generate_candidates` (background thread, web-search tool, structured-output parsing):

### 1. `_aicb_auto_fill_target_details(s, rf)`
- **Input:** `s.aicb_company`, `s.aicb_website`
- **Output (writes to state):** sets `s.aicb_industry` (single string) and appends to `s.aicb_sel_locations` (deduped list, cap 5).
- **Prompt focus:** "Visit the company's website and recent press; identify their primary industry/sub-industry and the cities/states where they operate or have offices."
- **Failure mode:** notify warning, leave fields empty for manual entry.

### 2. `_aicb_suggest_role_titles(s, rf)`
- **Input:** `s.aicb_company`, `s.aicb_website`, `s.aicb_industry`, brief/intent text
- **Output:** appends 5–8 chips to `s.aicb_sel_roles`, deduped against existing chips.
- **Prompt focus:** "Look at the company's career page and recent LinkedIn job postings. Return specific, recruiter-friendly job titles they're hiring for or have hired for recently."
- **Failure mode:** notify warning, leave roles for manual entry.

### 3. `_aicb_auto_generate_candidates` (extended)
- Existing function at L24676. Extended to take `count: int = 3` parameter, max-capped at 6.
- Letters become `["A", "B", "C", "D", "E", "F"][:count]`.
- Re-roll-single calls this with `count=1` and substitutes the result into the card slot being re-rolled (preserving letters of other cards).

All three reuse the existing `web_search_20250305` tool config, ANTHROPIC_API_KEY, and `_claude_create_with_retry` helper.

## Removed / Deprecated

- The legacy `_render_aicb_candidate_highlights` function and its callers are removed.
- The free-text candidate-highlights textarea on step 2 is removed.
- The "candidate from resume" inline path on step 2 (if any) is left intact for now (resume-driven flows are out of scope) — but it's no longer the primary path.
- `_aicb_cand_text` as a *user-facing* field is gone; it remains as the *internal* serialization format consumed by `_cand_block`.

## Definition of Done

- AICB wizard renders 5 steps cleanly; back/forward navigation works on all transitions.
- Step 2's auto-fill button populates Industry + Locations from a real company website.
- Step 3 renders roles as chips, suggest-titles works, all three source cards work.
- Pool picker filters correctly, caps at 3, handles empty pool.
- Auto-gen produces 1–6 cards rendered in a 2-col grid; each card's ✏️ / ✕ / 🔄 work; Re-roll-all works.
- Skip path advances cleanly with no candidates and the campaign-style prompt receives roles + locations only.
- Going back from step 3 to step 2 clears candidate state via `_wiz_back_clear_outputs`.
- Existing tests still pass (54/54 today).
- New tests cover: card serialization round-trip; `_wiz_back_clear_outputs` clears the new fields; the `count` parameter on `_aicb_auto_generate_candidates` is honored; static check that `_render_aicb_candidate_highlights` is removed.
- Manual UI verification on the live site for the wizard end-to-end.

## Open Decisions / Tradeoffs Called Out

1. **Manual-text path removal.** The current free-text "candidate highlights" textarea is deprecated in favor of editing auto-gen cards. Some recruiters know a candidate cold and want to type fast without an AI loop. Mitigation: clicking ✏️ on an Auto-gen card with N=1 lets them blow away the AI's content and type their own. If this turns out to be too slow, we add a tiny "Type a candidate manually" link below the auto-gen card in a follow-up — opens an empty editable card. **Decision: defer the manual-link affordance unless requested.**

2. **Resume-upload candidate path.** `s.aicb_resumes` and `s.aicb_candidate_resume` continue to populate `_cand_block` from the existing resume-upload flows. Those are not surfaced in the new step 3 UI. **Decision: leave resume flows working but unchanged in this spec.** A follow-up may unify them as a fourth source card.

3. **Pool filter strictness.** "Match by role keyword (case-insensitive substring)" can be too loose ("CNC Machinist" matches "machinist" but also "CNC Service Tech"). Tightening means tokenizing and intersecting word sets. **Decision: ship the loose substring match for v1, listen for complaints, tighten if needed.**

4. **Candidate count default.** Default 3 for auto-gen feels right for most "Splash"-style campaigns. "Talent Drop" historically uses A/B/C also. Higher counts are for "show me everyone available". **Decision: default 3, max 6.**

5. **Auto-fill industries — single vs multi.** The current `aicb_industry` field is a single string; companies often span multiple industries. **Decision: pick the AI's primary industry only; user adds more manually if needed.** Avoids over-engineering for v1.

## Implementation Order

Suggested sequencing for the writing-plans phase:

1. **Extend `_aicb_auto_generate_candidates` to accept `count`.** Smallest change, no UI. Test: count=1 returns one card-shaped block, count=6 returns six with letters A–F.
2. **Add `_aicb_auto_fill_target_details` helper + step-2 button.** Self-contained; doesn't depend on anything else.
3. **Add `_aicb_suggest_role_titles` helper.** Mirror of #2, no UI yet.
4. **Move roles input from step 2 to step 3.** Pure relocation; existing logic.
5. **Build step 3 UI** — roles chips + suggest button + 3 source cards + skip path.
6. **Build candidate-card grid + ✏️ / ✕ / 🔄 controls.**
7. **Wire Pool picker** with role-based filter and cap.
8. **Wire Auto-gen** — stepper, generate button, re-roll-single, re-roll-all.
9. **Update `_wiz_back_clear_outputs`** to clear new candidate state.
10. **Manual UI smoke test** + remove the deprecated `_render_aicb_candidate_highlights`.

## Risks

- **Wizard step renumbering.** Existing code branches on `_wiz_step == 2`, `_wiz_step == 3`, `_wiz_step == 4`. Inserting a new step at position 3 means every `_wiz_step == 3` and `_wiz_step == 4` reference must be reviewed. Implementation plan should include a grep + audit pass.
- **Web-search latency.** Three new web-search calls (auto-fill, suggest-titles, candidate auto-gen) all happen in user-visible flows. Each takes 5–15s. The existing candidate auto-gen already has a spinner state pattern (`_aicb_cand_generating`); the new helpers must follow the same pattern (per-call `_generating` flag + spinner + error handle).
- **Cost.** Three web-search calls per campaign. The existing single auto-gen call costs roughly $0.02 per campaign (Claude haiku + 2 web searches). Three calls per campaign = ~$0.06. Acceptable.
- **Pool filter false negatives.** A user adds "Production Supervisor" candidates to the pool but enters role "Plant Supervisor" — substring match misses. Mitigation: substring is bidirectional (chip in candidate role OR candidate role in chip), and the empty-pool card body suggests "or browse all candidates" expand link as a v2.

## Appendix — File Locations

- AICB wizard render entry: `flowdrip_app.py` `p_ai_campaign` (search by name)
- Existing step branches: search for `_wiz_step ==` and `aicb_wizard_step`
- Existing auto-gen: `_aicb_auto_generate_candidates` at line ~24676
- Candidate pool storage: `_user_candidate_pool_path()`, `load_candidate_pool()`, etc.
- `_cand_block` consumer (campaign-build prompt): around line 26310
- AppState definition: search for `class AppState`
- `_wiz_back_clear_outputs` helper: from H16, near `_reset_wizard_state`

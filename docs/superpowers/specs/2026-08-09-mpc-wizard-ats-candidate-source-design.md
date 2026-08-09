# MPC Wizard: ATS-backed Candidate Source — Design

**Date:** 2026-08-09
**Status:** Awaiting user review

## Problem

The MPC campaign wizard's candidate-source picker (step 3, `_CARDS` in
[flowdrip_app.py:~36246](../../flowdrip_app.py)) offers exactly two sources:

- `"autogen_titles"` — AI fabricates a sample profile from a one-line brief.
- `"pool"` — pulls real candidates from the Top Candidates roster
  (`_render_aicb_pool_picker`, [flowdrip_app.py:~33940](../../flowdrip_app.py)),
  filtered by title-chip substring match.

Top Candidates is by design a small, aging **working roster** — candidates age
out ~3 days after being in a launched sequence ("DripDrop is not an ATS, the
roster stays small so you focus on people you haven't reached yet," in-app copy
at [flowdrip_app.py:~41830](../../flowdrip_app.py)). It currently holds ~18
people. The other ~4,000 real candidates live in the separate ATS/Pipeline
store (`ats.py`, `ats.db`), moved there 2026-06-09 — but the wizard picker never
queries it.

This surfaced live: a PipelineBlast/CandidateBlast Claude-in-Chrome run
title-matched "Heavy Equipment Mechanic / Field Service Tech / Diesel Tech /
Shop Foreman" against the 18-person Top Candidates pool, found nothing, and
fell back to AI-generated fake profiles for a real company — when matching
candidates likely exist in the 4,000-person ATS. User: "It should be checking
the entire database."

## Goal

Add a third candidate source in the wizard that searches the full ATS pool
(team-wide, ~4,000 candidates), producing the same card shape the wizard
already knows how to render and email. Update the browser-automation skill
flows (pipelineblast/candidateblast) to use it before falling back to
AI-generated profiles.

## Non-Goals

- No changes to `ats.py`'s search internals — `keyword_search()` already does
  what's needed (team-wide FTS, AND-then-OR fallback).
- No changes to Top Candidates aging/roster behavior — it keeps its existing
  purpose as a small working list.
- No changes to final email formatting (`_format_candidate_block`) — it already
  re-derives the 3-bullet skill/project/company copy from whatever card it's
  given, regardless of source.
- No new picker UI framework — the new option reuses the existing `_CARDS` /
  card-grid pattern.

## Design

### 1. New wizard source: `"ats"`

Add a third entry to `_CARDS` ([flowdrip_app.py:~36260](../../flowdrip_app.py)):

```python
_CARDS = [
    ("autogen_titles", "✨", "Create profiles with AI", "..."),
    ("pool", "📋", "Pick from my Top Candidates", "..."),
    ("ats", "🔍", "Search my ATS/Pipeline",
     "Search your full candidate database (thousands of profiles) by job "
     "title. Real names, real backgrounds, not limited to your Top "
     "Candidates roster."),
]
```

`_set_cand_mode` needs no change — it already generically resets
`aicb_cand_cards` on any mode switch.

### 2. Picker: `_render_aicb_ats_picker(s, rf)`

New function, structurally mirroring `_render_aicb_pool_picker`
([flowdrip_app.py:~33940](../../flowdrip_app.py)), swapped to query the ATS:

```python
def _render_aicb_ats_picker(s, rf):
    from ats import keyword_search
    role_chips = [r for r in (s.aicb_sel_roles or []) if r.strip()]
    if not role_chips:
        # same "type a role to search" empty state as the pool picker
        ...
        return
    seen_ids, matches = set(), []
    for chip in role_chips:
        for cand in keyword_search(chip, owner=None):
            if cand["id"] not in seen_ids:
                seen_ids.add(cand["id"])
                matches.append(cand)
    # render as selectable cards, cap selection at 3 — identical
    # selection/highlight/cap UX to _render_aicb_pool_picker
```

`keyword_search(chip, owner=None)` is called per role chip (team-wide, not
"mine"-scoped — the whole point is the shared 4,000-candidate pool) and results
are merged de-duped by `id`. `keyword_search` already does AND-then-OR fallback
internally, so a multi-word title that finds nothing on strict AND
automatically retries loosened — no extra fallback logic needed here.

`jd_search` (the AI/Haiku-assisted variant) is deliberately not used — it's
built for messy free-text JD input, but the wizard already supplies clean title
chips, so plain FTS is faster and has one less moving part (no LLM round-trip,
no geocoding).

### 3. Card shape: `_aicb_ats_candidate_bullets(cand)`

New helper analogous to `_aicb_pool_candidate_bullets`
([flowdrip_app.py:~34040](../../flowdrip_app.py)), adapted to the `talents` row's
actual fields (`current_title`, `city`, `state`, `summary` — no `target_role` or
`salary` field in the ATS schema):

```python
def _aicb_ats_candidate_bullets(cand: dict) -> list:
    bullets = []
    loc = ", ".join(p for p in (cand.get("city"), cand.get("state")) if p)
    if loc:
        bullets.append(f"Location: {loc}")
    if cand.get("current_title"):
        bullets.append(f"Target role: {cand['current_title']}")
    summary = (cand.get("summary") or "").strip()
    if summary:
        first = summary.split("\n")[0].split(".")[0][:140]
        if first:
            bullets.append(first)
    return bullets
```

No salary bullet — the ATS doesn't capture a target-salary field the way the
Top Candidates roster does, so it's omitted rather than faked.

Card built as: `{"label": name, "role": current_title, "bullets": [...],
"_ats_id": id}` — same shape contract as the pool picker's cards
(`_pool_id` → `_ats_id`), so `aicb_cand_cards` and every downstream consumer
(email generation, `_format_candidate_block`) need no changes.

### 4. Selection cap

Same cap of 3 as the existing pool picker — that limit is about campaign email
length, not pool size, so it applies unchanged.

### 5. Skill flow update (pipelineblast / candidateblast)

Update `dripdrop-campaign.md` in both skills' references: when Top Candidates
title-matching comes up empty, try "Search my ATS/Pipeline" before falling back
to "Create profiles with AI." Documentation-only change — the browser
automation already knows how to click picker cards generically; it just needs
the new option and its place in the fallback order.

## Data Flow

```
wizard step 3, role chips entered (e.g. "Heavy Equipment Mechanic")
        │
user picks "Search my ATS/Pipeline"
        │
_render_aicb_ats_picker → keyword_search(chip, owner=None) per chip, team-wide
        │  merge + dedupe by id
        ▼
candidate cards rendered, select up to 3
        │  _aicb_ats_candidate_bullets(cand) builds preview bullets
        ▼
s.aicb_cand_cards = [{"label","role","bullets","_ats_id"}, ...]
        │  (identical shape to "pool" mode's cards)
        ▼
existing campaign-generation path (_format_candidate_block etc.) — unchanged
```

Fallback order (documented in the skill flows): Top Candidates → ATS → AI-generated.

## Error / Edge Handling

- **No role chips entered** → same empty state as the pool picker ("type a role
  to search").
- **ATS search also returns nothing** (rare, e.g. a truly novel title) →
  picker shows its existing "no matches" empty state; skill flow falls through
  to AI-generated, same as it does today when Top Candidates is empty — just
  one rung later.
- **`ats.py` unreachable / query error** → `keyword_search` already returns
  `[]` on any exception (see its `except Exception: return []`), so this
  degrades to the "no matches" empty state rather than crashing the wizard.
- **Candidate missing `city`/`state`/`summary`** → bullet builder skips absent
  fields, same defensive pattern as `_aicb_pool_candidate_bullets`.

## Testing

Unit tests (pure functions, no UI):
- `_aicb_ats_candidate_bullets`: full record → 3 bullets; missing city/state →
  location bullet omitted; missing summary → sentence bullet omitted; never
  emits a salary bullet.
- Dedup-by-id across multiple role chips returning overlapping candidates.
- `_CARDS_BY_KEY` includes the new `"ats"` key with correct label/description.

Manual: enter a title with no Top Candidates match (e.g. from the original
4Rivers scenario) → verify "Search my ATS/Pipeline" surfaces real ATS
candidates for those titles; verify selecting 3 and generating a campaign
produces the same email quality/format as the "pool" source.

## Files Touched

- `flowdrip_app.py` — new `_CARDS` entry; new `_render_aicb_ats_picker`; new
  `_aicb_ats_candidate_bullets`; wizard step-3 dispatch to route `"ats"` mode
  to the new picker (mirrors existing `"pool"` dispatch).
- `tests/test_aicb_ats_picker.py` — new.
- `~/.claude/skills/pipelineblast/references/dripdrop-campaign.md` — fallback
  order update.
- `~/.claude/skills/candidateblast/references/dripdrop-campaign.md` — fallback
  order update.

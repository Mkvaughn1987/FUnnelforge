# Newsletter redesign: candidates-led format

**Date:** 2026-05-16
**Owner:** Michael Vaughn
**Status:** Approved (preview reviewed via email; minor source already in tree)

## Problem

The newsletter is becoming a more important surface, and the current format
under-sells what users actually deliver: live, market-priced candidates. The
masthead tagline reads "Market Pulse & City Life," which buries the candidate
spotlights below two ambient sections (Market Update + Around Town) before
the reader sees a single profile. Users also have no way to opt out of the
City Life block when they want a tight, market-only issue.

## Goal

Lead with candidates. Make City Life a deliberate add-on. Tighten the
local-market bullets so they read as niche-specific intel, not generic news.

## Scope

Four changes to the existing newsletter pipeline. No new pages, no new
data files, no schema migration.

### 1. Masthead tagline

- **Old:** Bold "Market Pulse & City Life" + muted subtitle
  "{Industry} Intelligence for {Region}" (two lines)
- **New:** Bold single line "Market Pulse & Top {Industry} Candidates"
- `{Industry}` source: `niche` if set, else `sector` (mirrors prior tagline
  behavior). Title-cased.
- Auto-sizing logic in `_render_newsletter_html` already shrinks long
  taglines to fit one line — no changes needed there.
- Subtitle is dropped entirely (single-line tagline path already exists in
  the renderer; we just stop emitting `\n` in the data).

### 2. Section order

- **Old:** Intro → JOLTS → Market Update → Around Town → Candidate Spotlights
  → Personal corner → CTA
- **New:** Intro → JOLTS → Market Update → **Candidate Spotlights** →
  **Around Town** *(only if City Life enabled)* → Personal corner → CTA
- Implementation: in `_render_newsletter_html`, the Around Town block builds
  its HTML into a local `_around_town_html` string instead of appending
  directly to `sections_html`. After the Candidate Spotlights block emits,
  `sections_html += _around_town_html` runs. This keeps the existing block
  intact (no 90-line move) and makes the swap easy to revert if needed.
- Section tints (the soft per-section background colors) keep their existing
  `_tint(key)` mappings so the visual rhythm doesn't shift.

### 3. Market Update — exactly 3 niche-specific bullets

- **Old:** AI prompt asked for "3-5 bullets, each one sentence"; renderer
  capped at `[:5]`.
- **New:** Prompt asks for "EXACTLY 3 bullets, each one sentence,
  specifically about the {niche or sector} market in {region} (comp moves,
  talent supply, what offers are winning — no generic news)." Renderer caps
  at `[:3]`.
- Section label stays `{City} Update` (e.g. "Denver Update"). The bullets
  being niche-scoped is enough; no header rename.

### 4. City Life toggle in Create Newsletter dialog

- New checkbox in `_create_newsletter_dialog`:
  **"Include City Life section"** (default ON).
  Help tooltip: "Adds 2 local city blurbs (events, food, neighborhood,
  development) under the candidate spotlights. Turn off for a market-only
  newsletter."
- Stored on the campaign as `newsletter_show_city_life: bool` (default
  `True` when the field is missing — backward-compatible with existing
  newsletter campaigns).
- Locked at campaign creation; not editable per-issue (matches the existing
  pattern for `newsletter_spotlight_count`).
- Read in `_generate_newsletter_content_for_step` when building the `show`
  dict passed to `_render_newsletter_html` — only `show_around_town` is
  toggled by this field; every other `show_*` key stays `True`.
- The AI prompt continues to generate `around_town` data either way (cheap,
  and lets users flip the section back on later for the same campaign
  without re-generating).

### 5. Spotlight count: drop "None"

- The new tagline ("Top {Industry} Candidates") would contradict an issue
  with zero candidate cards. The dropdown drops the "None" option.
- New options: `3 per issue` (default) and `6 per issue`. Floored to 3 if
  a stale value somehow leaks in.

## Out of scope

- Per-issue editing of the City Life toggle (campaign-wide only).
- Renaming the "{City} Update" section header.
- Changes to JOLTS, personal corner, CTA, or footer.
- Migration for existing campaigns: legacy campaigns missing
  `newsletter_show_city_life` default to `True` via `dict.get(..., True)`.

## Files touched

- `flowdrip_app.py`
  - `_create_newsletter_dialog` — checkbox UI, drop "None" option, capture
    `newsletter_show_city_life` on the campaign.
  - `_generate_newsletter_content_for_step` — new tagline string, build
    `show` dict from campaign field, pass to renderer.
  - `_render_newsletter_html` — defer Around Town append until after
    Spotlights; cap Market Update at `[:3]`.
  - AI prompt strings inside `_generate_newsletter_content_for_step` —
    "3-5 bullets" → "EXACTLY 3 bullets, niche-specific".

## Validation

- Smoke-check (already passing): renderer hides Around Town when
  `show_around_town=False`; Around Town renders after Spotlights when on;
  market update bullets capped at 3 even when more are supplied.
- Email preview: synthetic Denver/Construction issue rendered + sent to
  `michael.vaughn@arenastaffing.net` for visual review. Approved.
- Existing tests in `tests/test_newsletter_*.py` should continue to pass;
  any that assume the old section order or 5-bullet cap will need updates
  during implementation.

## Rollback

Each change is small and localized. Reverting is a `git revert` of the
implementation commit. The legacy `dict.get("newsletter_show_city_life",
True)` keeps existing campaigns rendering identically if the toggle code
is removed.

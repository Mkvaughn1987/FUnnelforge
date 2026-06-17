# The J Way — Fixed Banner + Simplified Candidate Spotlights

**Date:** 2026-06-17
**Status:** Approved (design), pending banner asset + spec review
**Scope:** The J Way newsletter style only. Full Send is untouched.

## Background

"The J Way" is the plain-text, personal newsletter style (vs the branded
"Full Send"). It is, in practice, an Arena-only format — confirmed: the J Way
style should only ever be offered to Arena users. Three rough edges:

1. The issue editor shows the Unsplash **hero-photo picker** ("Hero photo —
   click a thumbnail to pick", Photo 1/2/3, 🔄 Refresh photos). That picker is
   a Full Send concept; it makes no sense for J Way.
2. J Way currently has **no banner**. Arena wants the branded "ARENA DIRECT
   HIRE / RECRUITMENT RUNDOWN" banner shown on every issue, placed right above
   the Highlights section — so the email opens with the intro note, then the
   banner, then the content.
3. The create dialog's **Candidate Spotlights** block shows everything at once
   (AI recommendations textarea + Pipeline search + count). It reads as "too
   much." Users want to pick one path first.

## Changes

### 1. Remove the hero-photo picker for J Way

- `_render_hero_gallery()` is called unconditionally in the issue-editor modal
  (flowdrip_app.py ~L22975). Gate the call so the gallery only renders when
  `camp.get("newsletter_style") != "j_way"`.
- The "🖼 Change Hero Photo" action in the preview panel (flowdrip_app.py
  ~L45458/L45538) gets the same gate — hidden for J Way issues.
- No hero-variant rotation logic needs to change; it simply goes unused for
  J Way (the body never carries an Unsplash `<img>`).

### 2. Fixed Arena banner above Highlights

- **Asset:** `jway_banner.png` placed in the project root (same location as
  `dripdrop_logo.png`) and added to `_STATIC_ALLOWLIST` (flowdrip_app.py L82).
  Served at `https://dripdripdrop.ai/static/jway_banner.png`. The deploy must
  ship this file to the app root alongside `dripdrop_logo.png`.
- **Render:** in `_jway_render()` (flowdrip_app.py L43712) insert the banner
  `<img>` between the intro paragraph(s) and the Highlights block. Resulting
  order: intro → "If I missed anything…" line → **banner** → Highlights →
  snapshot → key highlights → … → candidates → signoff.
- **Markup:** a single centered, responsive `<img>`:
  `<img src="https://dripdripdrop.ai/static/jway_banner.png" width="600"
  style="display:block;width:100%;max-width:600px;height:auto;border:0;
  margin:6px 0 14px 0;" alt="Arena Direct Hire — Recruitment Rundown" />`
- The banner is part of the generated body HTML, so it appears in the editor
  too (and survives send via the normal body pipeline). It is not user-pickable;
  there are no photo controls on J Way.

### 3. Candidate Spotlights — one fork instead of the stack

In the create dialog (flowdrip_app.py L21971–L22091), replace the always-on
stack with a two-button fork + progressive disclosure:

- A segmented control / two buttons: **✨ Auto-populate with AI** and
  **📋 Choose from Pipeline**. Default selection: Auto-populate with AI.
- **AI path selected:** show only the "Spotlight Recommendations (optional)"
  textarea.
- **Pipeline path selected:** show only the Pipeline search box + chosen-
  candidate chips (the existing `_pipe_search` / `_sel_cands` / `_refresh_chosen`
  machinery, just hidden until this path is chosen). Pipeline path is still
  gated to ATS-allowed users (`_ats_ok`); since J Way is Arena-only this is
  consistent.
- **Both paths:** the "How many per issue" count (3 or 6) stays visible below
  the fork.
- **Save semantics unchanged:** AI path saves `newsletter_spotlight_recommendations`
  with `newsletter_candidates = []`; Pipeline path saves
  `newsletter_candidates = list(_sel_cands.values())`. The downstream
  `_generate_jway_newsletter` already prefers picked candidates over AI when
  `newsletter_candidates` is non-empty — no generator change needed. When the
  AI path is chosen we must NOT carry over any `_sel_cands`, and vice-versa, so
  the two are mutually exclusive at save time based on the active fork.

## Data flow (unchanged contracts)

- `newsletter_style`: `"j_way" | "full_send"` (drives gating in #1 and banner in #2).
- `newsletter_candidates`: list — non-empty ⇒ override AI spotlights (Pipeline path).
- `newsletter_spotlight_recommendations`: free-text AI guidance (AI path).
- `newsletter_spotlight_count`: 3 or 6 (both paths).

## Out of scope / YAGNI

- Per-company configurable banner (J Way is Arena-only; bundled asset is enough).
- Banner upload UI.
- Changing the Full Send hero-photo flow.
- The edit-settings dialog's spotlight fields (the fork is a create-time UX; the
  edit dialog keeps its current simple recommendations + count fields). Revisit
  only if the user asks.

## Testing

- Unit: `_jway_render` output places the banner `<img>` after the intro and
  before the Highlights block, with the correct `/static/jway_banner.png` URL.
- Unit: `jway_banner.png` is in `_STATIC_ALLOWLIST`.
- Behavioral (existing harness style in tests/test_newsletter_*): J Way render
  contains no Unsplash/`/city_image/` hero `<img>`.
- Manual: create a J Way newsletter, confirm editor shows no hero picker, and
  the rendered/preview body shows the banner above Highlights.

# Light Mode Polish — Design

**Date:** 2026-05-04
**Status:** Approved (HTML preview reviewed, user said "looks good")
**Affected file:** `flowdrip_app.py`
**Visual reference:** `docs/superpowers/specs/2026-05-04-light-mode-preview.html`

## Problem

Multiple users have asked for a white background. The app already supports a light theme via the existing `C_LIGHT` palette and a sun/moon toggle, but:

1. **Default for new visitors is dark** ([flowdrip_app.py:7600](flowdrip_app.py#L7600)) — `localStorage.getItem('dd-theme') || 'dark'`.
2. **Several light-mode tokens have weak contrast** — sidebar labels and section headers use `C['muted']` (`#6B7B8D`) which is borderline-AA on white.
3. **Card edges are barely visible** — `C_LIGHT['border']` (`#D8DEE6`) blends into the page background (`#F5F7FA`); cards lack any shadow, so the eye can't see card boundaries on Reports, Candidates, Dashboard, etc.
4. **Newsletter / SlowDrip cards have hardcoded dark hex backgrounds** that don't theme-swap. Three of the five `EVERGREEN_COLORS` entries are dark navy / dark amber / dark cyan, which read as black bricks on white.

## Goal

Light mode looks and feels like a polished light theme — not a half-finished inversion of the dark theme. Approach (chosen during brainstorming): "lifted white cards" — every card-like surface in light mode is a clean white rectangle with a soft drop shadow and visible border. Hue identity comes from accent borders/strips, not background fills. Dark mode is unchanged.

## Design

### 1. Theme default flip

Change one line at [flowdrip_app.py:7600](flowdrip_app.py#L7600):

```js
var t = localStorage.getItem('dd-theme') || 'light';   // was 'dark'
```

Existing users with a saved preference (most current users) are unaffected. New visitors see light by default.

### 2. Light-mode token contrast

Tune three values in `C_LIGHT` ([flowdrip_app.py:2310-2317](flowdrip_app.py#L2310)). All other tokens stay.

| Token | Current | Proposed | Rationale |
|---|---|---|---|
| `muted` | `#6B7B8D` | `#4A5868` | Sidebar labels + `fd-sec` section headers go from ~4.4:1 to ~7.5:1 on white (passes WCAG AAA). |
| `border` | `#D8DEE6` | `#C8D0DA` | Card edges become visible without being heavy. |
| `text` | `#2D3748` | unchanged | Already ~12:1 — fine. |

### 3. Card elevation utility (light mode only)

Add a new CSS rule that targets the existing `.fd-card` and `.fd-bub` classes when light mode is active:

```css
:root[data-theme="light"] .fd-card,
:root[data-theme="light"] .fd-bub {
  box-shadow: 0 1px 2px rgba(15, 23, 42, .04),
              0 1px 3px rgba(15, 23, 42, .06);
}
:root[data-theme="light"] .fd-card:hover {
  box-shadow: 0 2px 4px rgba(15, 23, 42, .06),
              0 4px 8px rgba(15, 23, 42, .08);
}
```

This adds a subtle drop shadow to every card that uses one of those classes. The shadow uses an ink color rather than pure black so it tints with the page palette. Hover state lifts slightly more for affordance. Dark mode receives nothing — its existing `border + dark fill` treatment is already correct.

The shadow strength is intentionally subtle (preview was reviewed and approved). If the deployed result looks under-elevated we can bump the alpha values; this is a single CSS rule.

### 4. Newsletter / SlowDrip card palette

Restructure `EVERGREEN_COLORS` ([flowdrip_app.py:18432](flowdrip_app.py#L18432)) so each of the 5 hues has a dark and a light variant. Code reads CSS variables instead of literal hex.

**The 5 hues (preserved across themes):**

| # | Hue | Dark mode (unchanged) | Light mode (NEW) |
|---|---|---|---|
| 1 | Teal | bg `#0E3A3A`, fg `#1AE3D9`, border `#0F4035` | bg `#FFFFFF`, fg/strip `#0FB8B5`, border `#C8D0DA` |
| 2 | Blue | bg `#0D2540`, fg `#5EADD8`, border `#0F3050` | bg `#FFFFFF`, fg/strip `#1E40AF`, border `#C8D0DA` |
| 3 | Indigo | bg `#1E2560`, fg `#6366F1`, border `#251545` | bg `#FFFFFF`, fg/strip `#4F46E5`, border `#C8D0DA` |
| 4 | Amber | bg `#2D1F00`, fg `#FCD34D`, border `#3D2800` | bg `#FFFFFF`, fg/strip `#B45309`, border `#C8D0DA` |
| 5 | Cyan | bg `#0D1F2A`, fg `#67E8F9`, border `#0F2535` | bg `#FFFFFF`, fg/strip `#0E7490`, border `#C8D0DA` |

**Implementation:** introduce CSS custom properties `--dd-eg-N-bg`, `--dd-eg-N-fg`, `--dd-eg-N-border` for `N` in `1..5`. Define them at `:root` (dark values) and override at `:root[data-theme="light"]` (light values). Replace the Python `EVERGREEN_COLORS` list with var-reference strings, identical to the `C` pattern at [flowdrip_app.py:2320](flowdrip_app.py#L2320):

```python
EVERGREEN_COLORS = [
    (f"var(--dd-eg-{i}-bg)", f"var(--dd-eg-{i}-fg)", f"var(--dd-eg-{i}-border)")
    for i in range(1, 6)
]
```

In light mode every newsletter card becomes a white card with a 4px colored left strip and the title/button in the darkened `fg` hue. Same identity, light treatment.

**Strip color = `fg`, not `border`.** The card's box border (the `border` value, light gray `#C8D0DA`) is the rectangle outline. The colored 4px left strip uses `fg` (the darkened identity hue), matching the existing convention on the SlowDrip page card render at [flowdrip_app.py:20730](flowdrip_app.py#L20730) (`border-left:4px solid {fg}`).

**Newsletters page card render needs a small code addition.** The Newsletters page card at [flowdrip_app.py:20100-20103](flowdrip_app.py#L20100) currently has no left strip — it uses a solid `bg` fill in both modes. As part of this design we add `border-left:4px solid {fg};` to that card's inline style so the identity hue is visible in light mode (where `bg` is now white). This also improves dark-mode consistency since the SlowDrip page already shows colored left strips.

**Per-card enroll button color:** stays per-hue (each card's `+ Enroll` button is the card's identity color). The button uses `background:{fg}` which in light mode resolves to the darkened identity hue — visible on white. User reviewed this in the HTML preview and approved.

### 5. What's NOT in scope

- **Dark mode** — leave alone, it works.
- **Per-account theme persistence** — keep browser-local `localStorage`. Server-side sync can come later.
- **Audit of every ad-hoc inline tint** (e.g., `f"background:{fg}15"` patterns) — fix specific cases if they look wrong post-deploy.
- **Email editor / Quasar overrides** — already have light-mode CSS at [flowdrip_app.py:7812+](flowdrip_app.py#L7812).

## Risks

- **Existing users with saved `dark` preference are unaffected.** No data migration needed.
- **Hardcoded hex elsewhere in the codebase.** Some inline styles use literal hex (e.g., the `fd-pb` button color, the gradient `+ New Newsletter` button). These were not in the screenshots that surfaced as problems, so they stay out of scope. If post-deploy review surfaces specific ones, treat as follow-ups.
- **The `fg` value baked into Python-rendered inline styles for newsletter cards.** Switching `EVERGREEN_COLORS` to CSS-var strings means inline `background:{fg}` produces `background:var(--dd-eg-1-fg)` — works in modern browsers (the entire app already uses this pattern via `C[k]`). No compatibility concerns.

## Test plan

Source-grep tests in `tests/test_light_mode_polish.py`:

- **Default theme is `'light'`** — assert `inject_styles` source contains `|| 'light'` and not `|| 'dark'`.
- **Token bumps applied** — assert `C_LIGHT['muted'] == '#4A5868'`, `C_LIGHT['border'] == '#C8D0DA'`.
- **Card elevation rule present** — assert `inject_styles` source contains `:root[data-theme="light"] .fd-card` and `box-shadow:`.
- **EVERGREEN_COLORS is var-reference based** — assert `EVERGREEN_COLORS[0][0]` starts with `var(--dd-eg-`.
- **All 5 EVERGREEN entries are present** — assert `len(EVERGREEN_COLORS) == 5`.
- **Light-mode CSS vars defined** — assert `inject_styles` source contains `--dd-eg-1-bg` and `--dd-eg-5-fg` for both root and `[data-theme="light"]` blocks.
- **Newsletters card has colored left strip** — assert `inspect.getsource(p_newsletters)` contains `border-left:4px solid` (the new addition).

Manual smoke (via deploy):

- Open dripdripdrop.ai in a fresh incognito window. Should load in light mode.
- Toggle the sun/moon icon — both modes should look polished.
- Visit Newsletters page. All 5 hues visible; cards are white with colored left strips and identity-colored titles + buttons.
- Visit SlowDrip Sequence page. Same per-card treatment.
- Visit Candidates, Reports, Dashboard pages. All cards have visible edges + subtle shadow.
- Toggle back to dark mode on each page — should look identical to the current dark experience.

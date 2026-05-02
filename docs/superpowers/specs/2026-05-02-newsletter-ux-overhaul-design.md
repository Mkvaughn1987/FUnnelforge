# Newsletter UX Overhaul — Design Spec

**Date:** 2026-05-02 (revised same day)
**Status:** Approved (awaiting plan)
**Author:** Brainstormed with Michael Vaughn

## Problem

The newsletter "Refresh & Confirm" flow is confusing in production and asks the user to do work the system can do automatically:

1. The amber "Slow Drip emails sending soon" banner shows newsletter rows with a "🔄 Refresh & Confirm" button. This forces the user to remember to refresh every issue.
2. Clicking "Refresh & Confirm" opens an inline review panel at the **bottom** of a long page. Users don't realize the panel opened or struggle to find their way back.
3. The 5-photo Unsplash carousel exists but is buried inside that hard-to-find panel.
4. Only the **first** newsletter issue auto-generates at creation; later issues sit empty until refreshed.
5. Each monthly issue uses the same hero photo (variant 0) by default — repetitive.
6. The newsletter template footer has large empty rails on either side of the "Meet Your Hiring Partner" block.

## Goals

- **Remove all manual-refresh friction** for the user. Every newsletter auto-refreshes 3 days before send.
- After auto-refresh, **email a preview** to the user's inbox so they can review (and click through to edit if they want).
- Keep an **edit modal** for users who do want to tweak a refreshed issue. The modal saves with a "user-confirmed" flag so the next sweep doesn't overwrite their edits.
- **Auto-rotate the hero photo per issue** (issue N defaults to variant `N % 5`) so each month looks different.
- Auto-generate every issue at creation time (not just the first).
- Add a small monthly **holiday block** to the LEFT rail of the newsletter footer.
- Give newsletters a **dedicated left-nav button** ("📰 Newsletters") in the Sales Hub sidebar, positioned directly above "📊 Reports".

## Non-Goals

- Redesigning the entire newsletter template.
- Changing the AI generation prompt or content structure.
- Changing how recipients are enrolled in newsletters.
- Reminders for slow drips (those keep their existing 7-day amber banner unchanged).

---

## Design

### 1. Remove Newsletter Reminder Banner Rows

The amber "Slow Drip emails sending soon — review and update before they go out" banner stays for **slow drips**, but newsletter rows are filtered out of `get_evergreen_reminders` entirely. There is no longer any "Refresh & Confirm" button anywhere in the UI.

The user's only entry point to edit a newsletter issue is the **"✎ Edit"** button on the newsletter card in the main Newsletters list (replacing the existing "✦ Refresh" button — refreshing is now automatic).

### 2. Auto-refresh — 3 days before send, every newsletter, no opt-in

The existing `_auto_refresh_newsletter_tick` (L35450) already runs every 6 hours and regenerates pending newsletter issues. Changes:

- **Window**: shrink from 5 days → **3 days** before send.
- **Cooldown**: stays 6 days (prevents double-refresh in the same window).
- **Hero variant default**: when the sweep regenerates step N, set `_hero_variant = N % total_variants` so each monthly issue uses a distinct cached Unsplash photo. If the user has already manually set `_hero_variant`, leave it alone.
- **Confirmed steps**: skip any step with `confirmed: true` (user-owned content is never overwritten).
- **`auto_confirmed` flag**: set on every step the sweep regenerates, so the UI can show a small ⓘ "Auto-refreshed" badge.
- **Preview email** (already partially built at L35612): on every successful auto-refresh, send a preview of the refreshed copy to the campaign owner's inbox. Subject becomes friendlier:
  > `Preview: {Newsletter Name} — sends {Mon Day}`

  Body is the rendered newsletter HTML, with a small banner at the top:
  > *Auto-refreshed on {date}. Sends to {N} contacts on {date}. Click [Open in DripDrop](link) to edit.*

  Link points to `https://dripdripdrop.ai/?edit_newsletter={camp_name}` — a deep link that opens the modal directly on page load.

### 3. The Edit Modal

Triggered by the **"✎ Edit"** button on the newsletter card OR by the deep-link query param from the preview email.

**Modal layout (top → bottom):**

| Region | Content |
| --- | --- |
| Header bar | `Edit: {Newsletter Name} — {Issue Month}` on the left, `X` close on the right. |
| Hero photo (640×180) | Image with **◀ ▶ arrows overlaid** on left/right edges (semi-transparent dark circles). `Photo 2 of 5` badge in bottom-right. `↑ Upload your own` link directly below the image. Photographer credit (Unsplash ToS) in tiny text. Initial variant = whatever the auto-refresh chose (issue index modulo 5). |
| Subject | Single editable text field, full width. |
| Body | Editable rich-text area, ~400 px tall, scrolls **inside** the modal (modal itself doesn't scroll the page). |
| Footer bar (sticky) | Left: `Cancel`. Right: primary `✓ Save changes` button. |

**On Save:**
- Save subject, body, hero variant index to the campaign step.
- Mark the step as `confirmed: true`, clear `auto_confirmed`.
- Update any pending queue items so the scheduler sends the user's edited copy.
- Close the modal. Card flips to a green ✓ "Edited — sending {date}" pill.

**On Cancel / X:**
- Close the modal. No state changes (the auto-refreshed content stays as-is and ships).

**While modal is loading via deep link:** if the underlying step's body is still empty (rare race condition where user clicks the email link before the auto-refresh fires), show a "Generating fresh content…" spinner inside the modal until the body appears.

---

### 4. Hero Photo — Auto-Rotation + Easy Manual Swap

The 5-candidate Unsplash batch fetch already exists (`_unsplash_fetch_city_batch`). New behavior:

- **Auto-rotation**: when auto-refresh writes to step N, set `_hero_variant = N % total_variants` (typically 5). This guarantees consecutive monthly issues use different photos automatically. If `_hero_variant` was already set (user touched it), don't overwrite.
- **Inside the modal**: ◀ ▶ arrows overlaid on the photo (replaces the existing separate "Cycle Photo" button). `Photo N of 5` badge in the bottom-right. `↑ Upload your own` link directly below.
- **On the newsletter card**: show the **current hero photo as a thumbnail** (~80×30 px) on the right side of the card. Clicking it opens the same Edit Modal.

**Persistence:** saving the modal locks `_hero_variant` for that issue. The send pipeline reads the same field it does today — no template changes.

---

### 5. Auto-generate All Issues at Creation

- Today: only the first issue auto-generates (`_gen_first_issue` background thread in `_create_newsletter_dialog`).
- Change: when a newsletter is created, kick off background generation for **all N scheduled issues** sequentially (one at a time, ~3-second sleep between issues to be polite to the Anthropic API).
- Failures are logged and skipped; the auto-refresh sweep retries them on its next run.

---

### 6. Dedicated Newsletters Page + Left-Nav Entry

Add a new entry to `SALES_NAV` (`flowdrip_app.py` ~L8385) directly above the existing `("📊", "Reports", "pdf_gen")` line:

```python
("📰", "Newsletters", "newsletters"),
```

Add a new page key `"newsletters"` to the page router (~L40361 area). It calls a new function `p_newsletters(s, rf)` which renders ONLY the newsletter section of the existing Slow Drip Sequence page (no slow drips, no amber banner). Visually it shows:

- Page title: `Newsletters`
- Subtitle: `Auto-refreshed monthly. Edit any issue from the card below.`
- The `+ New Newsletter` button.
- The list of newsletter campaigns (each with hero thumbnail, "Edit" button, "Auto-refreshed" badge if applicable).

Implementation: extract the existing newsletter-list render block from `p_evergreen` into a shared helper `_render_newsletter_list(s, rf, camps)`, called by both `p_evergreen` (for the existing combined view) and the new `p_newsletters` (for the dedicated view).

---

### 7. Monthly Holiday Block

Adds a small block to the **left** of the "Meet Your Hiring Partner" face/quote footer. Right rail stays empty for now (future use).

**Block content (per month):**

- 📅 `{Date}` (e.g., `May 25`)
- **`{Holiday Name}`** (bold, brand-colored)
- One short line of editable text (e.g., *"Honoring those who served. Office closed."*)

**Data source:** Hard-coded curated dictionary in code (one entry per month). Users can override the short line text in their Profile (per-user, optional). If no override, the default ships with the app.

**Curated holiday list (initial):**

| Month | Date | Holiday | Default note |
| --- | --- | --- | --- |
| Jan | 1 | New Year's Day | Wishing you a strong start to the year. |
| Feb | 14 | Valentine's Day | A little appreciation goes a long way. |
| Mar | 17 | St. Patrick's Day | Wishing you a little luck this month. |
| Apr | varies | Easter | Hope you got time with the people who matter. |
| May | 25 | Memorial Day | Honoring those who served. Office closed. |
| Jun | 19 | Juneteenth | Recognizing freedom and progress. |
| Jul | 4 | Independence Day | Wishing you a safe and restful holiday. |
| Aug | 1st Mon | Summer | Enjoying the long days while they last. |
| Sep | 1st Mon | Labor Day | Thank you to everyone keeping the lights on. |
| Oct | 31 | Halloween | Hope your week brings more treats than tricks. |
| Nov | 4th Thu | Thanksgiving | Grateful for the partners and people we work with. |
| Dec | 25 | Christmas | Wishing you peace and rest with your people. |

(Variable dates — Easter, Labor Day, Thanksgiving — computed at render time from the issue's send month.)

**Layout:** the existing single-cell footer becomes a 3-column table: holiday block (LEFT, ~28%) | face + quote (CENTER, ~44%) | empty spacer (RIGHT, ~28%). Email-safe HTML using inline styles.

---

## Components Touched

| Area | File | Change |
| --- | --- | --- |
| Reminder banner — drop newsletters | `flowdrip_app.py` (`get_evergreen_reminders` ~L18237) | Filter out campaigns where `market_analysis: True`. Slow drips unaffected. |
| Newsletter card "Edit" button | `flowdrip_app.py` (~L18874) | Rename "✦ Refresh" → "✎ Edit". Click handler opens modal. |
| Edit modal | `flowdrip_app.py` | New `_edit_newsletter_modal(s, rf, camp, step_idx)` function (after `_create_newsletter_dialog` at ~L18596). |
| Inline panel removal | `flowdrip_app.py` (~L19353–L20020) | Delete the `if _rcamp and _rstep_mode:` block in `p_evergreen` (modal owns the flow). |
| Hero thumbnail on card | `flowdrip_app.py` (~L18874) | Add 80×30 thumbnail before the Edit button. |
| Auto-refreshed badge on card | `flowdrip_app.py` (~L18866) | Render small grey "ⓘ Auto-refreshed" pill if next pending step has `auto_confirmed: true` and not `confirmed: true`. |
| Auto-generate all issues | `flowdrip_app.py` (`_gen_first_issue` ~L18540, new `_gen_all_issues_for_campaign` near `_generate_newsletter_content_for_step` ~L35257) | Loop over all step indices instead of `0`. |
| Auto-refresh window 3 days + hero rotation + `confirmed`/`auto_confirmed` | `flowdrip_app.py` (`_auto_refresh_newsletter_tick` ~L35450) | Window 3 days; default `_hero_variant = step_idx % 5`; skip `confirmed: true`; stamp `auto_confirmed: true`; updated preview email subject. |
| Deep link `?edit_newsletter=...` | `flowdrip_app.py` (page-load handler) | Parse query param, open modal on first render. |
| Holiday data + helper | `flowdrip_app.py` — new `_HOLIDAYS_BY_MONTH` + `_holiday_for_month(year, month, overrides)` near other newsletter helpers | Returns `(date_str, name, note)` or `None`. Handles variable dates. |
| Holiday HTML render | `flowdrip_app.py` (~L35093) | Refactor footer to 3-column table; LEFT cell = holiday block; CENTER = unchanged; RIGHT = empty spacer. |
| Holiday-note overrides | `flowdrip_app.py` Settings panel (~L9799 area) | Add optional `holiday_note_overrides` dict to user config. |
| Newsletters left-nav | `flowdrip_app.py` `SALES_NAV` (~L8385) + page router (~L40361) | New `("📰", "Newsletters", "newsletters")` above Reports; new `p_newsletters(s, rf)` page wired into router. |

## New / Modified Data Fields

Per newsletter step:

- `confirmed: bool` (new) — true when user clicks Save in the modal. Auto-refresh skips these steps.
- `auto_confirmed: bool` (new) — true when the auto-refresh sweep regenerated the step.
- `_hero_variant: int` (existing) — index into the 5 Unsplash candidates. Default behavior changes: auto-refresh sets `step_idx % 5` if not already set.

Per user (Profile):

- `holiday_note_overrides: dict[str, str]` (new, optional) — `{ "MM": "custom note" }`. Empty by default.

## Error Handling

- **Auto-refresh sweep fails**: log to stdout, leave previous draft in place. Next sweep retries. If still failing at send time, the cached draft sends as the safety net.
- **Preview email fails**: log to stdout, do NOT block the auto-refresh write to disk.
- **Generation fails in modal** (rare race via deep link): show error + `Try again` button inside the modal. Do not auto-close.
- **Hero photo cache empty**: fall back to the Wikipedia photo path (existing behavior, unchanged).
- **No holiday for the month** (gap month): render the LEFT block as empty space (no broken layout).
- **Deep link to a campaign the user doesn't own**: silently ignore the query param.

## Testing

- **Reminder banner filtering**: queue a newsletter 2 days out → does NOT appear in the amber banner.
- **Auto-refresh window**: queue a newsletter 4 days out → not refreshed; 3 days out → refreshed.
- **Auto-rotate hero**: regenerate steps 0, 1, 2 → `_hero_variant` is `0, 1, 2` respectively; step 6 = `1` (`6 % 5`).
- **Confirmed skip**: mark a step `confirmed: true` → auto-refresh leaves it alone.
- **Auto-confirmed flag**: regenerate via sweep → step has `auto_confirmed: true`.
- **Auto-generate all**: create 12-issue newsletter → background loop populates every step.
- **Holiday lookup**: each month returns the right `(date, name, note)`. Variable dates match the calendar (e.g. Thanksgiving 2026 = Nov 26).
- **Deep link**: visit `/?edit_newsletter={name}` → modal opens for that newsletter on first render.
- **Live page test** (per project memory `feedback_smoke_check_before_deploy.md`): hit live `/` after deploy, not just `/healthz`.

## Open Questions

None — design fully approved.

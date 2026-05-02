# Newsletter UX Overhaul — Design Spec

**Date:** 2026-05-02
**Status:** Approved (awaiting plan)
**Author:** Brainstormed with Michael Vaughn

## Problem

The newsletter "Refresh & Confirm" flow is confusing in production:

1. Clicking "Refresh & Confirm" opens an inline review panel at the **bottom** of a long page. Users don't realize the panel opened or struggle to find their way back.
2. Reviewing requires scrolling past every campaign card to reach the editor.
3. The 5-photo Unsplash carousel exists but is buried inside that hard-to-find panel.
4. Only the **first** newsletter issue auto-generates at creation; later issues sit empty until the user manually refreshes.
5. If the user ignores the reminder banner, the newsletter sends stale (or empty) content with no fallback.
6. The newsletter template has large empty rails on either side of the "Meet Your Hiring Partner" footer block.

## Goals

- Make the post-refresh review experience focused and obvious.
- Make swapping the hero photo discoverable and one-click.
- Guarantee every scheduled issue has fresh content even if the user never opens the review modal.
- Fill empty space in the newsletter footer with a small monthly holiday block.

## Non-Goals

- Redesigning the entire newsletter template.
- Changing the AI generation prompt or content structure.
- Changing how recipients are enrolled in newsletters.
- Adding a new permissions/roles model.

---

## Design

### 1. Refresh Modal (replaces inline review panel)

Clicking **"Refresh & Confirm"** anywhere (amber reminder banner OR newsletter card) opens a centered modal dialog over a dimmed background.

**Modal layout (top → bottom):**

| Region | Content |
| --- | --- |
| Header bar | `Review: {Newsletter Name} — {Issue Month}` on the left, `X` close on the right. |
| Hero photo (640×180) | Image with **◀ ▶ arrows overlaid** on left/right edges (semi-transparent dark circles). `Photo 2 of 5` badge in bottom-right. `↑ Upload your own` link directly below the image. Photographer credit (Unsplash ToS) in tiny text. |
| Subject | Single editable text field, full width. |
| Body | Editable rich-text area, ~400 px tall, scrolls **inside** the modal (modal itself doesn't scroll the page). |
| Footer bar (sticky) | Left: `Cancel`. Right: primary `✓ Confirm & Schedule` button. |

**Generation states inside the modal:**

- **Generating** — modal opens immediately in a "Generating fresh content…" state with a spinner where the body would be. Hero photo + arrows render as soon as the cached image is available (usually instant). User can swap photos while the body is still being written.
- **Ready** — generation complete; user can edit subject/body, swap photos, confirm.
- **Error** — if generation fails, modal shows the error with a `Try again` button. (Replaces the bug visible in the current screenshot where an Anthropic credit error rendered as raw body text.)

**On Confirm:**
- Save subject, body, hero variant index to the campaign step.
- Mark the step as `confirmed: true` (new field).
- Close the modal.
- The card on the page flips to a green ✓ "Confirmed — sending {date}" pill state (replaces the amber "needs refresh" state).

**On Cancel / X:**
- Save the draft (so partial edits aren't lost) but do **not** mark `confirmed`.
- Close the modal. Card stays in amber "needs refresh" state.

---

### 2. Hero Photo Swapping — Easier & More Visible

The 5-candidate Unsplash batch fetch already exists (`_unsplash_fetch_city_batch`) and the variant index is already stored on the campaign step (`_hero_variant`). No backend changes; UX changes only.

**Inside the modal:**
- ◀ ▶ arrows overlaid on the photo (replaces the existing separate "Cycle Photo" button).
- `Photo N of 5` badge in the bottom-right corner of the image.
- `↑ Upload your own` link directly below the image (replaces the existing more-hidden upload button).

**On the newsletter card** (in the Slow Drip Sequence list, both the amber reminder section and the main newsletter list):
- Show the **current hero photo as a thumbnail** (~80×30 px) on the right side of the card.
- Tiny `Change photo` link below the thumbnail.
- Clicking the thumbnail or the link opens the same Refresh Modal.

**Persistence:** confirming locks `_hero_variant` for that issue. The send pipeline reads the same field it does today — no template/render changes.

---

### 3. Auto-generate, Reminder Threshold, Auto-refresh Fallback

#### 3a. Auto-generate all issues at creation

- Today: only the first issue auto-generates in `_create_newsletter_dialog` via the `[NewsletterAuto]` background thread.
- Change: when a newsletter is created, kick off background generation for **all N scheduled issues** sequentially (one at a time, low priority — sleep briefly between issues to avoid hammering the Anthropic API).
- Generation runs in the same background thread that exists today; the only change is iterating `range(len(steps))` instead of just step 0.
- If a generation call fails for any issue, log it and move on. The auto-refresh fallback (3c) will retry closer to send time.

#### 3b. Reminder threshold change

- Change `get_evergreen_reminders(days_ahead=7)` default from **7** to **5** for newsletter campaigns.
- Slow drips keep their current 7-day threshold (no behavior change for them).
- The amber "Slow Drip emails sending soon" banner now lights up 5 days before a newsletter sends instead of 7.

#### 3c. Auto-refresh fallback

A background sweep runs once per hour (piggybacking on the existing scheduler loop):

1. For every pending newsletter step whose `send_dt` is **≤ 24 hours away**:
2. If the step is **not** marked `confirmed: true`:
   - Re-run `_generate_newsletter_content_for_step` to pull the freshest market data.
   - Keep the user's chosen `_hero_variant` if they touched it; otherwise default to variant 0.
   - Save the regenerated subject/body to the step.
   - Mark the step as `auto_confirmed: true` (distinct from user-confirmed).
3. If generation fails: log the error and leave the previously-cached draft in place. Next hourly sweep will retry. The cached draft sends at scheduled time as the safety net.

**UI indicators:**

- Reminder banner shows a small note: *"Will auto-send fresh content {date} if not confirmed by then."* — so users know the fallback exists and aren't surprised.
- After auto-send, the campaign card shows a subtle ⓘ "Auto-refreshed" badge (small grey label) so the user can see their input wasn't used.

**Why 24h before, not at send time:** Buffer for AI errors. If the API is down, the next hourly sweep retries; if it stays down, the previously-cached draft sends instead of nothing.

---

### 4. Monthly Holiday Block

Adds a small block to the **left** of the "Meet Your Hiring Partner" face/quote footer in the newsletter template. Right rail stays empty for now (future use).

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
| Aug | varies | Summer (no major federal) | Enjoying the long days while they last. |
| Sep | 1st Mon | Labor Day | Thank you to everyone keeping the lights on. |
| Oct | 31 | Halloween | Hope your week brings more treats than tricks. |
| Nov | 4th Thu | Thanksgiving | Grateful for the partners and people we work with. |
| Dec | 25 | Christmas | Wishing you peace and rest with your people. |

(Dates that vary year-to-year — Easter, Labor Day, Thanksgiving — computed at render time from the issue's send month.)

**Layout in the email template:** The footer table currently centers the face/quote. Change it to a 3-column table: holiday block (LEFT, ~30%) | face + quote (CENTER, ~40%) | empty spacer (RIGHT, ~30%). Email-safe HTML using inline styles (consistent with the rest of the template).

---

## Components Touched

| Area | File | Change |
| --- | --- | --- |
| Refresh modal UI | `flowdrip_app.py` | New `_refresh_newsletter_modal(camp, step_idx)` dialog. Replace inline panel render path. |
| Refresh-button click handlers | `flowdrip_app.py` (~L18769, L18879, L19247, L19506) | Replace `s._market_refresh_step = "generating"` + scroll-to-top with `_refresh_newsletter_modal(camp, idx).open()`. |
| Hero photo carousel (modal) | `flowdrip_app.py` (~L19871–L19999) | Move `_cycle_hero_review` / upload into modal layout. Replace separate buttons with overlay arrows + badge. |
| Hero thumbnail on card | `flowdrip_app.py` (newsletter card render in Slow Drip Sequence list) | Add small thumbnail + `Change photo` link. |
| Auto-generate all issues | `flowdrip_app.py` (~L18540–L18570) | In `[NewsletterAuto]` background thread, loop over all steps instead of step 0 only. Sleep ~3 s between issues. |
| Reminder threshold | `flowdrip_app.py` (~L18237, L18679) | Change `get_evergreen_reminders` default to `days_ahead=5` for newsletters (keep 7 for slow drips — split if needed). |
| Auto-refresh sweep | `flowdrip_app.py` (background scheduler) | Hourly check: any pending newsletter step ≤ 24 h away and `confirmed != True` → regenerate + mark `auto_confirmed`. |
| Banner copy | `flowdrip_app.py` (~L18692) | Add the "Will auto-send fresh content {date}" note. |
| `auto_confirmed` badge on card | `flowdrip_app.py` (newsletter card render) | Render small grey ⓘ "Auto-refreshed" pill if step has `auto_confirmed: true`. |
| Holiday block | newsletter HTML template (search: `MEET YOUR HIRING PARTNER`) | Refactor footer to 3-column table, add holiday data dictionary + render. |

## New / Modified Data Fields

Per newsletter step:

- `confirmed: bool` (new) — true when user clicks Confirm in the modal.
- `auto_confirmed: bool` (new) — true when the 24h sweep regenerated and locked the issue.
- `_hero_variant: int` (existing) — index into the 5 Unsplash candidates. Already wired.

Per user (Profile):

- `holiday_note_overrides: dict[str, str]` (new, optional) — user can override default holiday note text per month. Empty by default.

## Error Handling

- **Generation fails in modal**: show error + `Try again` button inside the modal. Do not auto-close. (Fixes the current bug where an Anthropic 400 rendered as body text.)
- **Auto-refresh sweep fails**: log to stdout, leave previous draft in place. Next sweep retries. If still failing at send time, the cached draft sends as the safety net.
- **Hero photo cache empty**: fall back to the Wikipedia photo path (existing behavior, unchanged).
- **No holiday for the month** (gap month): render the LEFT block as empty space (no broken layout).

## Testing

- **Refresh modal**: open it, swap photos all 5 ways, edit subject + body, confirm → step shows `confirmed: true` + green pill. Cancel → draft saved + amber state.
- **Auto-generate**: create a 12-issue newsletter, watch background thread populate all 12 step bodies within a few minutes.
- **Reminder banner**: queue a newsletter 6 days out → no banner. 5 days out → banner appears with "auto-send fresh content" note.
- **Auto-refresh sweep**: queue a newsletter 23 hours out, leave it un-confirmed, run the sweep manually → step gets regenerated and `auto_confirmed: true`. Wait for send → email goes out, card shows "Auto-refreshed" badge.
- **Holiday block**: render newsletter for each month, verify the right holiday appears. Set a user override → custom note replaces default.
- **Live page test** (per project memory `feedback_smoke_check_before_deploy.md`): hit live `/` after deploy, not just `/healthz`.

## Open Questions

None — design fully approved.

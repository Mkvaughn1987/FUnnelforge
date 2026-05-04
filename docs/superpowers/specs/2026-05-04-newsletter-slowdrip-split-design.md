# Newsletter / SlowDrip Page Split — Design

**Date:** 2026-05-04
**Status:** Approved (awaiting spec review)
**Affected files:** `flowdrip_app.py`

## Problem

Newsletters are currently rendered in two places:

1. **Newsletters page** (`p_newsletters`, `flowdrip_app.py:20011`) — read-only management. One `View / Edit` button per card. No way to enroll contacts.
2. **SlowDrip Sequence page** (`p_evergreen`, `flowdrip_app.py:20147`) — splits campaigns into `_slow_drips` and `_newsletters`, renders both. Newsletter cards here have `+ Refresh`, `✦ Create` / `✎ Edit`, `✉ Preview`, and `+ Enroll` buttons.

The two pages look like duplicates but serve different purposes (enrollment hub vs. content hub). The dual presence also forces the `+ New Newsletter` creation button to appear in both places, drifting over time.

## Goal

One home per object: every newsletter action — create, view, edit, refresh, preview, enroll contacts — happens on the **Newsletters page**. The **SlowDrip Sequence page** becomes purely about slow drip campaigns.

## Non-Goals

- No change to the slow drip campaign cards or their behavior.
- No change to newsletter generation logic, the auto-refresh sweep, the deep-link flow (`?edit_newsletter=`), or the `_offer_slow_drip_enroll` reply-popup.
- No change to the View/Edit modal itself (`_edit_newsletter_modal`).
- No change to the Sales Hub or any landing page.

## Design

### 1. SlowDrip Sequence page (`p_evergreen`)

**Remove:**

- The `_newsletters` filter and the second loop that renders newsletter cards (currently `flowdrip_app.py:20712` through end of the newsletter rendering block, ~line 20900).
- The "NEWSLETTERS" section header and the `+ New Newsletter` button (currently `flowdrip_app.py:20697`–`20710`).
- Any newsletter-only branches inside the SlowDrip card rendering loop that are no longer reachable once `_newsletters` is gone — specifically the `_is_newsletter` branch in the action-buttons cluster (`flowdrip_app.py:20418` and the `if _is_newsletter:` block at `:20424`). These can stay technically (slow drip campaigns won't trigger them), but should be removed for clarity since the loop now only iterates slow drips.

**Keep:**

- Slow drip campaign rendering (everything that runs against `_slow_drips`).
- The page intro strip, the help icon, the "Slow Drip Campaigns" heading.
- The top-of-page refresh status banner (newsletters being refreshed via the deep-link or auto-sweep still set `s._market_refresh_camp`; the banner stays useful even if the user is on a different page when refresh starts).

**Add:**

- A single line at the bottom of the page (after the slow drip list, before any close-out element):
  > *"Looking for monthly newsletters? They live on the **Newsletters** page →"*

  The "Newsletters" word is a link that navigates to `/newsletters` (or whatever the existing route is — verify during implementation).

  This is a one-time breadcrumb for users who learned the old layout. Style: muted color, small font, centered, ~16px top margin from the slow drip list.

### 2. Newsletters page (`p_newsletters`)

**Add an `+ Enroll` button** to each newsletter card, placed to the LEFT of the existing `View / Edit` button. Clicking it calls the existing `_enroll_dialog(camp, s, rf)` helper at `flowdrip_app.py:18755` — same dialog the SlowDrip page uses today.

**Visual style:** match the SlowDrip page's `+ Enroll` button — solid background using the card's `fg` color, white text, same padding as `View / Edit`. Use the `fd-pb` class that `_create_newsletter_dialog` uses elsewhere on the page.

**Layout:** the card is currently a flex row with the title/meta block on the left and a single button on the right. The right side becomes a flex container with two buttons (gap: 6px), `+ Enroll` first, `View / Edit` second.

**No other changes** to the Newsletters page card — refresh and preview already happen inside the View/Edit modal, which the user already opens via `View / Edit`.

### 3. PAGE_HELP updates

In the `PAGE_HELP` dict (around `flowdrip_app.py:9220`):

- **`evergreen` entry** (`flowdrip_app.py:9221`–`9233`): drop the bullet that mentions Newsletters at line `9230`. Update the page summary if it currently calls out newsletters.
- **`newsletters` entry** (`flowdrip_app.py:9234`–`9298`): add a new bullet near the top:
  > *("Enrolling contacts", "Click + Enroll on any newsletter card to add contacts from a saved list. Contacts join at the next upcoming issue — they don't receive past issues.")*

### 4. Startup wizard

The startup wizard (around `flowdrip_app.py:1541` per CLAUDE.md, may have moved — verify) describes the SlowDrip page. If it references newsletters there, update the wizard step to direct users to the Newsletters page for newsletter management. If it doesn't mention newsletters, no change.

## Out-of-Scope Items Worth Flagging

- **Reply-popup enrollment (`_offer_slow_drip_enroll`):** Already pulls newsletter campaigns dynamically from the campaign store regardless of where they're created. No change needed.
- **Deep links (`?edit_newsletter=<name>`):** Already handled on `p_newsletters`. No change needed.
- **Background refresh banner:** Stays on `p_evergreen` only because that's where it was wired. Future work: also show it on `p_newsletters` so users see refresh progress on the page they're managing newsletters from. Not in this spec.

## Risks

- **Existing users will look for newsletters on the SlowDrip page first.** Mitigation: the breadcrumb link in §1.
- **Newsletter creation button removed from SlowDrip page.** Users who learned to create newsletters from there will need to navigate to the Newsletters page. The breadcrumb covers this path too — they'll see it, click through, find the `+ New Newsletter` button on the Newsletters page.
- **The `_is_newsletter` action-button branch in `p_evergreen` becomes dead code if not removed.** Pure code-cleanliness risk; no user-facing impact.

## Test plan

- Open SlowDrip Sequence page. Verify only slow drip campaigns are listed. Verify the breadcrumb link to Newsletters appears at the bottom and navigates correctly.
- Open Newsletters page. Verify each card has both `+ Enroll` and `View / Edit` buttons. Click `+ Enroll`, confirm the same enroll dialog opens that used to open from the SlowDrip page. Enroll a contact, confirm the count on the card updates after refresh.
- Open `View / Edit`, confirm the modal still opens, generates content, refreshes, and previews as before.
- Trigger the auto-refresh sweep (or simulate it) and confirm the refresh banner still appears on the SlowDrip page.
- Trigger the reply-popup `_offer_slow_drip_enroll` and confirm newsletters still appear in the picker.
- Open the help popups on both pages and verify the updated copy.

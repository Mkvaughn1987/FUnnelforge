# Newsletter: start-after-campaign + enroll CSV upload & start-month picker

**Date:** 2026-06-03
**App:** DripDrop (`flowdrip_app.py`)
**Status:** Approved design — ready for implementation plan

## Summary

Three related newsletter improvements:

1. **Start after the campaign** — when a user spins up a newsletter from the
   campaign launch card, default its first issue to the first Thursday
   *after* the source campaign's last email (editable smart default).
2. **CSV upload in Enroll Contacts** — let users upload a CSV to enroll
   contacts directly on the newsletter page, not just pick an existing saved
   list.
3. **Start-month picker in Enroll Contacts** — let users choose which monthly
   issue a new enrollee starts from, instead of always the next upcoming one.

---

## Feature 1 — Newsletter starts after the source campaign

### Context

The "📰 Create a Newsletter from this campaign" card lives in the campaign
launch screen (nested render inside `p_responses`). Its click handler
`_spin_up_from_launch` (~`flowdrip_app.py:15826`) builds a `prefill` dict and
opens `_create_newsletter_dialog` (`flowdrip_app.py:21170`).

Today the newsletter's Start Date defaults to `_next_first_thursday()` (next
first Thursday from *today*) — completely independent of the source campaign.
The source campaign on that page is typically **not launched yet**, so its
"last email date" is a projection off its configured `start_date`.

### Behavior

Default the newsletter's first issue to **the first Thursday strictly after
the source campaign's projected last email**, still fully editable.

### Implementation

**A. Project the campaign's last-email date** — in `_spin_up_from_launch`,
compute self-contained off the `camp` object, mirroring the launch preview's
date logic so the projection matches the Sequence timeline the user already
sees:

- `start = date.fromisoformat(camp["start_date"])`, fall back to
  `date.today()` on missing/invalid.
- Walk `camp["emails"]`, accumulating `delay_days`. Each step's send date =
  its `fixed_date` (ISO) if set, else `_add_business_days(start, cumulative)`.
- Track the **maximum** send date = projected last email.
- If the campaign has no steps, leave it unset (fall back to today's behavior).

Pass it through the existing `prefill` dict as a new key:
`prefill["start_after"] = last_email_date.isoformat()`.

**B. Use it as the Start Date default** — in `_create_newsletter_dialog`
(~`flowdrip_app.py:21352`), where `_default_start` is currently
`_next_first_thursday()`:

- Read `prefill.get("start_after")`. If present and parseable, default to
  `_next_first_thursday(last_email_date + timedelta(days=1))`. The `+1 day`
  guarantees the newsletter lands strictly after the campaign wraps and rolls
  to the next month if the last email itself fell on a first Thursday.
- If absent (create-from-scratch flow), keep `_next_first_thursday()`.

**C. Provenance note** — under the Start Date field, only in the prefill case,
add a muted helper line:

> Defaulted to the first Thursday after '{source_campaign_name}' finishes
> (≈ {Mon DD, YYYY}).

`source_campaign_name` is already passed in `prefill["source_campaign_name"]`.

### Reused helpers (all module-level, no new date math)

- `_add_business_days(start, n)` — `flowdrip_app.py:6042`
- `_next_first_thursday(from_date)` — `flowdrip_app.py:6875` (already returns
  the first first-Thursday on/after `from_date`)

### Non-goals

- It is a projection, not a live link. If the user later changes the campaign's
  start date or launch timing, the newsletter's seeded dates do not
  auto-recompute. Acceptable per "smart default, still editable."
- Create-from-scratch newsletter flow is unchanged.

---

## Feature 2 — CSV upload in the Enroll Contacts dialog

### Context

`_enroll_dialog(camp, s, rf)` (`flowdrip_app.py:20672`) currently only lists
saved contact lists (`list_saved_contact_lists()`); a brand-new user with no
saved lists sees a dead-end "No saved contact lists found" message. On Enroll
it reads the chosen CSV, dedups by email, appends to `camp["contacts"]`,
saves, and queues upcoming emails via
`queue_campaign_emails(enroll_camp, start_step=_find_next_evergreen_step(camp))`.

A reusable upload helper already exists:
`_contact_upload_and_name(s, rf, on_done)` (`flowdrip_app.py:18480`) — handles
extension/size validation, `normalize_csv`, saves the list to the user's
contacts dir for reuse, and calls `on_done(load_contacts())` with the parsed
contacts.

### Implementation

**A. Extract a shared enroll routine** — pull the existing Enroll body into
`_do_enroll_contacts(new_contacts, start_step)` inside `_enroll_dialog`:
dedup by lowercased email against `camp["contacts"]` → append → set
`contact_count` → `save_campaign` → `_cache_campaigns.invalidate()` →
`queue_campaign_emails(enroll_camp_with_only_new_contacts, start_step=...)` →
notify → `dlg.close()` → `rf()`. Preserve the existing "no new contacts"
guard.

**B. Add an upload path** — under the saved-list dropdown, render
`_contact_upload_and_name` with a visible "⬆ Upload a new CSV" affordance. Its
`on_done(contacts)` calls `_do_enroll_contacts(contacts, <chosen start_step>)`.
The dropdown path's Enroll button reads the chosen list's CSV (as today) and
calls the same `_do_enroll_contacts`.

**C. Restructure the dialog** into two labeled paths sharing one start-month
picker:
- "Pick a saved list" (existing dropdown + Enroll button)
- "…or upload a new CSV" (upload affordance)

**D. Empty state** — replace "No saved contact lists found…" with
"No saved lists yet — upload a CSV to get started," so the upload path is the
primary affordance for new users.

### Non-goals

- No new CSV parser or column-mapping — reuse `_contact_upload_and_name` /
  `normalize_csv`.
- Uploading makes that list the active contact list (existing helper
  side-effect) — accepted.

---

## Feature 3 — Start-month picker in Enroll Contacts

### Behavior

Add a "Start from which issue" dropdown so a new enrollee can begin at the next
upcoming issue (default, current behavior) or a later month.

### Implementation

- Build options from `camp["emails"]` for issues from the next upcoming index
  (`_find_next_evergreen_step(camp)`) through the last. Label each by its
  `fixed_date` month/year (e.g. "July 2026"); the option value is the email's
  index into `camp["emails"]`.
- Default selection = `_find_next_evergreen_step(camp)`.
- The selected index is the `start_step` passed into `_do_enroll_contacts`
  (and onward to `queue_campaign_emails`).
- Past issues are not listed. If every issue is past
  (`_is_evergreen_completed`), show a disabled/empty state explaining there are
  no upcoming issues to enroll into.

### Reused helpers

- `_find_next_evergreen_step(camp)` — `flowdrip_app.py:20755`
- `_is_evergreen_completed(camp)` — `flowdrip_app.py:20807`

---

## Testing

**Feature 1 (pure date logic — unit-testable):**
- Projected last-email date: delay-only steps; `fixed_date`-only steps; mixed;
  empty `emails`; missing/invalid `start_date`.
- "First Thursday after": last email mid-month; last email *on* a first
  Thursday (must roll to next month); December → January rollover.

**Feature 2:**
- `_do_enroll_contacts`: dedup against existing; honors `start_step`;
  empty-after-dedup guard; queues only the new contacts.
- Upload path enrolls the uploaded contacts via the shared routine.

**Feature 3:**
- Start-month options: next-upcoming default; only upcoming issues listed;
  December rollover label; all-past campaign → empty/disabled state.

---

## Files touched

- `flowdrip_app.py`
  - `_spin_up_from_launch` (~15826) — project last-email date, pass
    `start_after`.
  - `_create_newsletter_dialog` (21170) — honor `start_after` for the Start
    Date default + provenance note.
  - `_enroll_dialog` (20672) — shared `_do_enroll_contacts`, upload path,
    start-month picker, new empty state.
- Tests under `tests/` for the date projection, "first Thursday after,"
  enroll dedup/start_step, and start-month option construction.

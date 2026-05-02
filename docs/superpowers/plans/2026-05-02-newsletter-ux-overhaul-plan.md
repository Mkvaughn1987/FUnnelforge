# Newsletter UX Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the buried inline newsletter "Refresh & Confirm" panel with a focused modal, surface the 5 hero photos with arrow-overlay swapping, auto-generate every issue at creation, change the reminder window to 5 days, respect a new user-`confirmed` flag in the existing auto-refresh sweep, add an "Auto-refreshed" badge, and add a monthly holiday block to the newsletter footer.

**Architecture:** Single-file NiceGUI app (`flowdrip_app.py`, ~42K lines). Server-side generation/scheduling already exists (`_generate_newsletter_content_for_step` at L35257, `_auto_refresh_newsletter_tick` at L35450, scheduler loop at L41955). UI changes use NiceGUI `ui.dialog()`. Tests use the existing `isolated_appdata` + `with_user` pytest fixtures (`tests/conftest.py`); UI render is not unit-testable, so dialog/card changes are verified via the live `/` smoke check post-deploy.

**Tech Stack:** Python 3.12, NiceGUI, Anthropic SDK (`_claude_create_with_retry`), pytest, JSON file storage in per-user dirs under `_BASE_DATA_DIR/users/{slug}/`.

---

## Spec

`docs/superpowers/specs/2026-05-02-newsletter-ux-overhaul-design.md`

## File Structure

All work lands in **`flowdrip_app.py`** (the existing monolithic NiceGUI app — established pattern, don't split). New tests live under **`tests/`**.

| Area | Location | Responsibility |
| --- | --- | --- |
| Modal UI | `flowdrip_app.py` — new `_refresh_newsletter_modal(s, rf, camp, step_idx)` (insert after `_create_newsletter_dialog` at ~L18596) | Single-task focused dialog: hero carousel + subject + body + Confirm/Cancel. |
| Modal trigger sites | `flowdrip_app.py` L18769–L18789, L18877–L18896, L19101–L19115 (inline preview-card refresh), L19247–L19260 | Replace `s._market_refresh_step = "generating"` block with `_refresh_newsletter_modal(...)` call. |
| Inline panel removal | `flowdrip_app.py` L19353–L20020 (the entire `if _rcamp and _rstep_mode:` block in `p_evergreen`) | Delete. Modal owns the flow. |
| Hero thumbnail on card | `flowdrip_app.py` ~L18874 (newsletter card action-buttons region) | Add 80×30 thumbnail + "Change photo" link before the Refresh button. |
| Auto-refreshed badge | `flowdrip_app.py` ~L18866 (newsletter card meta line) | Render small grey "ⓘ Auto-refreshed" pill if any pending step has `auto_confirmed: true`. |
| Auto-generate all issues | `flowdrip_app.py` L18540–L18577 (`_gen_first_issue`) | Loop over all step indices instead of `0`. |
| Reminder threshold | `flowdrip_app.py` L18237–L18280 (`get_evergreen_reminders`) | Switch to per-campaign-type window: 5 days for newsletters, 7 for slow drips. |
| Reminder banner copy | `flowdrip_app.py` L18692–L18693 | Add the "Will auto-send fresh content {date} if not confirmed by then" line under each newsletter row. |
| `confirmed` flag honored | `flowdrip_app.py` `_auto_refresh_newsletter_tick` at L35450 | Skip steps whose `confirmed: true` was set by user. Set `auto_confirmed: true` when sweep regenerates. |
| Holiday data + helper | `flowdrip_app.py` — new module-level `_HOLIDAYS_BY_MONTH` dict + `_holiday_for_month(year, month, override_map)` near the other newsletter helpers (~L34060) | Returns `(date_str, name, note)` or `None`. Handles variable dates (Easter, Labor Day, Thanksgiving). |
| Holiday HTML render | `flowdrip_app.py` ~L35093 (the existing single-cell "Meet Your Hiring Partner" `<tr><td>`) | Refactor to 3-column table; LEFT cell = holiday block; CENTER = unchanged content; RIGHT = empty spacer. |
| Holiday-note user override | `flowdrip_app.py` Profile/Settings panel (search for `newsletter_personal_note`, around L9799) | Add optional `holiday_note_overrides` dict to user config. |
| Tests | `tests/test_newsletter_*.py` (new files) | Pure-helper tests: holiday lookup, confirmed-flag skip, all-issue generation iteration, reminder threshold split. |

---

## Phase 0 — Setup

### Task 0.1: Create worktree branch

- [ ] **Step 1: Confirm clean working tree**

```bash
git status
```

Expected: branch `claude/critical-bug-fixes`, working tree may have untracked files but no unrelated modified files. (Lots of untracked status entries are normal for this repo.)

- [ ] **Step 2: Create implementation branch**

```bash
git checkout -b claude/newsletter-ux-overhaul
```

Expected: switched to a new branch.

---

## Phase 1 — Foundation (data fields + auto-refresh respects user-confirmed)

The existing `_auto_refresh_newsletter_tick` (L35450) already regenerates newsletters within 5 days of send. **Today it overwrites manual user edits** because it doesn't check whether the user has confirmed the issue. Fix that first so the rest of the flow can rely on the contract.

### Task 1.1: Test — `_auto_refresh_newsletter_tick` skips steps marked `confirmed: true`

**Files:**
- Create: `tests/test_newsletter_auto_refresh_skip.py`

- [ ] **Step 1: Write the failing test**

```python
"""User-confirmed newsletter steps must NOT be overwritten by the
6-hour auto-refresh sweep. Without this, manual edits in the modal
get clobbered the next time the scheduler tick runs."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


def test_auto_refresh_skips_confirmed_steps(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    # Build a newsletter campaign whose next pending step is in 2 days and
    # is marked confirmed:true (user clicked Confirm in the modal).
    user_root = with_user
    camp_dir = user_root / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    camp_path = camp_dir / "Test_Newsletter.json"
    confirmed_body = "<p>USER EDITED CONTENT — DO NOT OVERWRITE</p>"
    confirmed_subject = "User-edited subject"
    camp_path.write_text(json.dumps({
        "name": "Test Newsletter",
        "newsletter_name": "Test Newsletter",
        "market_analysis": True,
        "evergreen_only": True,
        "market_sector": "construction",
        "market_region": "Denver, CO",
        "_owner_email": "tester@example.com",
        "emails": [{
            "name": "Issue 1",
            "subject": confirmed_subject,
            "body": confirmed_body,
            "step_type": "email_auto",
            "confirmed": True,
        }],
    }), encoding="utf-8")

    # Pending queue item due in 2 days for that step.
    queue_path = user_root / "scheduled_queue.json"
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None).isoformat()
    queue_path.write_text(json.dumps([{
        "id": "q1",
        "campaign": "Test Newsletter",
        "step_name": "Issue 1",
        "subject": confirmed_subject,
        "to": "lead@example.com",
        "send_dt": soon,
        "status": "pending",
    }]), encoding="utf-8")

    # If the generator runs, the test fails — confirmed steps must skip it.
    sentinel = {"called": False}
    def _generator(_camp, _idx):
        sentinel["called"] = True
        return ("REGEN SUBJECT", "<p>REGEN BODY</p>")
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step", _generator)
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", user_root.parent.parent)

    fa._auto_refresh_newsletter_tick()

    assert sentinel["called"] is False, "Generator was called for a confirmed step"

    saved = json.loads(camp_path.read_text(encoding="utf-8"))
    assert saved["emails"][0]["body"] == confirmed_body
    assert saved["emails"][0]["subject"] == confirmed_subject
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_newsletter_auto_refresh_skip.py -v
```

Expected: FAIL — generator IS called because the existing tick has no `confirmed` check yet.

- [ ] **Step 3: Add `confirmed` skip to `_auto_refresh_newsletter_tick`**

Open `flowdrip_app.py`. Find `_auto_refresh_newsletter_tick` at L35450. The current code resolves `step_idx`, then at L35552 does `step = steps[step_idx]`, then at L35553 begins a `# Cooldown: skip if already refreshed recently` block. Insert the new check between `step = steps[step_idx]` and the cooldown comment:

```python
            step = steps[step_idx]
            # User-confirmed steps are owned by the user. Never overwrite.
            # `confirmed: true` is set by the Refresh modal's Confirm button.
            if step.get("confirmed"):
                continue
            # Cooldown: skip if already refreshed recently
            ...
```

(Show only the first line of the cooldown block as an anchor — leave the rest unchanged.)

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_newsletter_auto_refresh_skip.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_newsletter_auto_refresh_skip.py flowdrip_app.py
git commit -m "feat(newsletter): auto-refresh respects user-confirmed flag"
```

### Task 1.2: Test — `_auto_refresh_newsletter_tick` sets `auto_confirmed: true` after a successful regen

**Files:**
- Create: `tests/test_newsletter_auto_confirmed_flag.py`

- [ ] **Step 1: Write the failing test**

```python
"""When the 6-hour sweep regenerates a newsletter step, it must mark
the step `auto_confirmed: true` so the UI can render the
'ⓘ Auto-refreshed' badge and the user knows their input wasn't used."""
import json
from datetime import datetime, timedelta, timezone


def test_auto_refresh_marks_auto_confirmed(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    user_root = with_user
    camp_dir = user_root / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    camp_path = camp_dir / "Test_Newsletter.json"
    camp_path.write_text(json.dumps({
        "name": "Test Newsletter",
        "newsletter_name": "Test Newsletter",
        "market_analysis": True,
        "evergreen_only": True,
        "market_sector": "construction",
        "market_region": "Denver, CO",
        "_owner_email": "tester@example.com",
        "emails": [{
            "name": "Issue 1",
            "subject": "stale",
            "body": "<p>stale</p>",
            "step_type": "email_auto",
            # No `confirmed` flag — sweep should regenerate.
        }],
    }), encoding="utf-8")

    queue_path = user_root / "scheduled_queue.json"
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None).isoformat()
    queue_path.write_text(json.dumps([{
        "id": "q1",
        "campaign": "Test Newsletter",
        "step_name": "Issue 1",
        "subject": "stale",
        "to": "lead@example.com",
        "send_dt": soon,
        "status": "pending",
    }]), encoding="utf-8")

    monkeypatch.setattr(
        fa, "_generate_newsletter_content_for_step",
        lambda _c, _i: ("FRESH SUBJECT", "<p>FRESH BODY</p>"))
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", user_root.parent.parent)

    fa._auto_refresh_newsletter_tick()

    saved = json.loads(camp_path.read_text(encoding="utf-8"))
    assert saved["emails"][0]["subject"] == "FRESH SUBJECT"
    assert saved["emails"][0]["body"] == "<p>FRESH BODY</p>"
    assert saved["emails"][0]["auto_confirmed"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_newsletter_auto_confirmed_flag.py -v
```

Expected: FAIL — `auto_confirmed` key missing.

- [ ] **Step 3: Set `auto_confirmed: true` after successful regen**

In `_auto_refresh_newsletter_tick`, find this exact block (L35573–L35577):

```python
            # Update the step on the campaign
            steps[step_idx]["subject"] = subj
            steps[step_idx]["body"] = body
            steps[step_idx]["_auto_refreshed_at"] = now_utc.isoformat()
            camp["emails"] = steps
```

Insert the new line right before `camp["emails"] = steps`:

```python
            # Update the step on the campaign
            steps[step_idx]["subject"] = subj
            steps[step_idx]["body"] = body
            steps[step_idx]["_auto_refreshed_at"] = now_utc.isoformat()
            steps[step_idx]["auto_confirmed"] = True
            camp["emails"] = steps
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_newsletter_auto_confirmed_flag.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_newsletter_auto_confirmed_flag.py flowdrip_app.py
git commit -m "feat(newsletter): auto-refresh stamps auto_confirmed=true on success"
```

---

## Phase 2 — Auto-generate all issues at creation

Today only step 0 generates in the background. Make the loop cover every step.

### Task 2.1: Test — newsletter creation triggers generation for every step (not just step 0)

**Files:**
- Create: `tests/test_newsletter_auto_gen_all_issues.py`

- [ ] **Step 1: Write the failing test**

```python
"""When a newsletter is created, the background `_gen_first_issue` thread
should generate content for ALL N scheduled steps, not just step 0.
We test the helper directly (not the dialog) by extracting it into a
named function: `_gen_all_issues_for_campaign(camp_name)`."""
from unittest.mock import MagicMock


def test_gen_all_issues_calls_generator_per_step(
        isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    # Seed a 3-issue newsletter on disk.
    camp = {
        "name": "Big Test NL",
        "newsletter_name": "Big Test NL",
        "market_analysis": True,
        "evergreen_only": True,
        "market_sector": "construction",
        "market_region": "Denver, CO",
        "_owner_email": "tester@example.com",
        "emails": [
            {"name": f"Issue {i}", "subject": "", "body": "",
             "step_type": "email_auto"}
            for i in range(3)
        ],
    }
    fa.save_campaign(camp)

    # Spy on the generator. Returns ("S0","B0"), ("S1","B1"), ("S2","B2").
    calls = []
    def _spy(_camp, idx):
        calls.append(idx)
        return (f"S{idx}", f"B{idx}")
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step", _spy)

    fa._gen_all_issues_for_campaign("Big Test NL")

    # Generator called once per step, in order.
    assert calls == [0, 1, 2]

    # Each step now has the generated subject/body.
    saved = next(c for c in fa.load_campaigns() if c.get("name") == "Big Test NL")
    for i in range(3):
        assert saved["emails"][i]["subject"] == f"S{i}"
        assert saved["emails"][i]["body"] == f"B{i}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_newsletter_auto_gen_all_issues.py -v
```

Expected: FAIL — `_gen_all_issues_for_campaign` does not exist.

- [ ] **Step 3: Add `_gen_all_issues_for_campaign` near `_generate_newsletter_content_for_step` (~L35257)**

Insert immediately after the existing `_generate_newsletter_content_for_step` function (find its closing line, then add):

```python
def _gen_all_issues_for_campaign(camp_name: str) -> None:
    """Generate AI content for every step of the named newsletter campaign.

    Used by the post-create background thread so users have a draft for
    every scheduled month immediately after creating the campaign — not
    just month 0. Steps that already have non-empty bodies are skipped
    (idempotent — safe to re-run). Sleeps briefly between issues to keep
    the Anthropic rate limit happy.
    """
    import time as _time
    fresh = next((c for c in load_campaigns() if c.get("name") == camp_name), None)
    if not fresh or not fresh.get("emails"):
        print(f"[NewsletterAutoAll] campaign not found: {camp_name}", flush=True)
        return
    steps = fresh.get("emails", []) or []
    for idx in range(len(steps)):
        st = steps[idx]
        # Skip steps that already have content (e.g. step 0 generated by
        # the older _gen_first_issue path, or a confirmed manual edit).
        if (st.get("body") or "").strip() and "[AI:" not in (st.get("body") or ""):
            continue
        try:
            subj, body = _generate_newsletter_content_for_step(fresh, idx)
        except Exception as ex:
            print(f"[NewsletterAutoAll] step {idx} error for {camp_name}: {ex}",
                  flush=True)
            continue
        if not subj or not body:
            print(f"[NewsletterAutoAll] step {idx} returned empty for {camp_name}",
                  flush=True)
            continue
        steps[idx]["subject"] = subj
        steps[idx]["body"] = body
        save_campaign(fresh)
        print(f"[NewsletterAutoAll] step {idx} ready for {camp_name}", flush=True)
        _time.sleep(3)  # gentle pacing for Anthropic rate limit
    try:
        _cache_campaigns.invalidate()
    except Exception:
        pass
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_newsletter_auto_gen_all_issues.py -v
```

Expected: PASS.

- [ ] **Step 5: Replace `_gen_first_issue` body with a call to `_gen_all_issues_for_campaign`**

In `flowdrip_app.py`, find `_gen_first_issue` at L18540. Replace its body so the entire function becomes:

```python
            def _gen_first_issue():
                try:
                    _uemail = getattr(s, '_user_email', '') or ''
                    if _uemail:
                        _CURRENT_USER_EMAIL.set(_uemail)
                        _switch_to_user_paths(_uemail)
                    _gen_all_issues_for_campaign(nl_name)
                except Exception as ex:
                    print(f"[NewsletterAuto] error: {ex}", flush=True)
                finally:
                    s._nl_first_gen_done = True
                    try:
                        _cache_campaigns.invalidate()
                    except Exception:
                        pass
```

- [ ] **Step 6: Verify nothing in tests broke**

```bash
pytest tests/test_newsletter_auto_gen_all_issues.py tests/test_newsletter_auto_refresh_skip.py tests/test_newsletter_auto_confirmed_flag.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_newsletter_auto_gen_all_issues.py flowdrip_app.py
git commit -m "feat(newsletter): auto-generate every issue on creation"
```

---

## Phase 3 — Reminder threshold (5 days for newsletters, 7 for slow drips)

### Task 3.1: Test — `get_evergreen_reminders` uses 5-day window for newsletters

**Files:**
- Create: `tests/test_newsletter_reminder_window.py`

- [ ] **Step 1: Write the failing test**

```python
"""Newsletters get a 5-day reminder window. Slow drips keep their 7-day
window. Today both share `days_ahead=7`."""
import json
from datetime import datetime, timedelta


def _seed_camp(user_root, name, market_analysis):
    camp_dir = user_root / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    (camp_dir / f"{name.replace(' ', '_')}.json").write_text(json.dumps({
        "name": name,
        "evergreen_only": True,
        "market_analysis": market_analysis,
        "emails": [{"name": "S1", "step_type": "email_auto"}],
    }), encoding="utf-8")


def _seed_queue(user_root, camp_name, days_out):
    when = (datetime.now() + timedelta(days=days_out)).isoformat()
    qp = user_root / "scheduled_queue.json"
    qp.write_text(json.dumps([{
        "id": "q1", "campaign": camp_name, "step_name": "S1",
        "to": "x@y.com", "send_dt": when, "status": "pending",
    }]), encoding="utf-8")


def test_newsletter_appears_at_5_days_not_at_6(isolated_appdata, with_user):
    import flowdrip_app as fa
    user_root = with_user
    _seed_camp(user_root, "NL Camp", market_analysis=True)
    # 6 days out → outside the 5-day newsletter window → no reminder.
    _seed_queue(user_root, "NL Camp", days_out=6)
    rems = fa.get_evergreen_reminders()
    assert all(r["camp_name"] != "NL Camp" for r in rems), \
        "Newsletter at 6 days should NOT appear (window is 5)"


def test_newsletter_appears_at_5_days(isolated_appdata, with_user):
    import flowdrip_app as fa
    user_root = with_user
    _seed_camp(user_root, "NL Camp", market_analysis=True)
    _seed_queue(user_root, "NL Camp", days_out=5)
    rems = fa.get_evergreen_reminders()
    assert any(r["camp_name"] == "NL Camp" for r in rems), \
        "Newsletter at 5 days should appear"


def test_slow_drip_keeps_7_day_window(isolated_appdata, with_user):
    import flowdrip_app as fa
    user_root = with_user
    _seed_camp(user_root, "Plain SD", market_analysis=False)
    _seed_queue(user_root, "Plain SD", days_out=6)
    rems = fa.get_evergreen_reminders()
    assert any(r["camp_name"] == "Plain SD" for r in rems), \
        "Slow drip at 6 days should still appear (window is 7)"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_newsletter_reminder_window.py -v
```

Expected: FAIL on `test_newsletter_appears_at_5_days_not_at_6` (current code uses 7 days for everything, so a 6-day-out newsletter still appears).

- [ ] **Step 3: Update `get_evergreen_reminders`**

In `flowdrip_app.py` at L18237, find:

```python
def get_evergreen_reminders(days_ahead: int = 7) -> list:
```

Replace the body's per-item filter to apply a tighter window for newsletters. Find this line in the function (around L18264):

```python
        if send_date > cutoff:
            continue
```

Replace it with:

```python
        # Newsletters get a tighter 5-day window so users have a real
        # opportunity to refresh just-in-time content. Slow drips keep
        # the broader 7-day default.
        camp_obj = next((c for c in camps if c.get("name") == cn), None)
        _is_newsletter = bool(camp_obj and camp_obj.get("market_analysis"))
        _eff_cutoff = today + timedelta(days=5) if _is_newsletter else cutoff
        if send_date > _eff_cutoff:
            continue
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_newsletter_reminder_window.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_newsletter_reminder_window.py flowdrip_app.py
git commit -m "feat(newsletter): tighten reminder window to 5 days (slow drips stay 7)"
```

---

## Phase 4 — Holiday data + helper

### Task 4.1: Test — `_holiday_for_month` returns the right holiday for known months

**Files:**
- Create: `tests/test_newsletter_holiday_lookup.py`

- [ ] **Step 1: Write the failing test**

```python
"""The holiday helper returns (date_str, name, note) for any month, with
correct handling of variable dates (Easter, Labor Day, Thanksgiving)."""


def test_fixed_holidays_lookup():
    import flowdrip_app as fa

    # January → New Year's Day Jan 1
    d, name, note = fa._holiday_for_month(2026, 1)
    assert d == "Jan 1"
    assert name == "New Year's Day"
    assert note  # non-empty default

    # July → Independence Day Jul 4
    d, name, _ = fa._holiday_for_month(2026, 7)
    assert d == "Jul 4"
    assert name == "Independence Day"

    # December → Christmas Dec 25
    d, name, _ = fa._holiday_for_month(2026, 12)
    assert (d, name) == ("Dec 25", "Christmas")


def test_thanksgiving_is_fourth_thursday():
    import flowdrip_app as fa
    # 2026: Nov 26 is the 4th Thursday.
    d, name, _ = fa._holiday_for_month(2026, 11)
    assert d == "Nov 26"
    assert name == "Thanksgiving"


def test_labor_day_is_first_monday():
    import flowdrip_app as fa
    # 2026: Sep 7 is the first Monday.
    d, name, _ = fa._holiday_for_month(2026, 9)
    assert d == "Sep 7"
    assert name == "Labor Day"


def test_user_override_replaces_default_note():
    import flowdrip_app as fa
    overrides = {"05": "Closed Mon May 25 — back Tue."}
    d, name, note = fa._holiday_for_month(2026, 5, overrides=overrides)
    assert name == "Memorial Day"
    assert note == "Closed Mon May 25 — back Tue."
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_newsletter_holiday_lookup.py -v
```

Expected: FAIL — `_holiday_for_month` does not exist.

- [ ] **Step 3: Add `_HOLIDAYS_BY_MONTH` and `_holiday_for_month` near other newsletter helpers**

In `flowdrip_app.py`, insert above `_generate_newsletter_content_for_step` (~L35256):

```python
# ── Monthly holiday block (newsletter footer LEFT rail) ────────────────────
# A small block surfaced beside the "Meet Your Hiring Partner" card so the
# footer stops looking lopsided. Hard-coded curated list — keeps it simple
# and predictable. Users can override the note text per month in Profile.
_HOLIDAYS_BY_MONTH: dict = {
    1:  ("New Year's Day",     "Wishing you a strong start to the year."),
    2:  ("Valentine's Day",    "A little appreciation goes a long way."),
    3:  ("St. Patrick's Day",  "Wishing you a little luck this month."),
    4:  ("Easter",             "Hope you got time with the people who matter."),
    5:  ("Memorial Day",       "Honoring those who served. Office closed."),
    6:  ("Juneteenth",         "Recognizing freedom and progress."),
    7:  ("Independence Day",   "Wishing you a safe and restful holiday."),
    8:  ("Summer",             "Enjoying the long days while they last."),
    9:  ("Labor Day",          "Thank you to everyone keeping the lights on."),
    10: ("Halloween",          "Hope your week brings more treats than tricks."),
    11: ("Thanksgiving",       "Grateful for the partners and people we work with."),
    12: ("Christmas",          "Wishing you peace and rest with your people."),
}


def _holiday_for_month(year: int, month: int, overrides: dict | None = None):
    """Return (date_str, name, note) for the named month/year.

    Variable-date holidays (Easter, Labor Day, Thanksgiving) compute the
    correct date for the given year. Fixed-date holidays use a static day.
    `overrides` is the user's `holiday_note_overrides` dict (key = "MM").
    """
    from datetime import date as _date, timedelta as _td
    if month not in _HOLIDAYS_BY_MONTH:
        return None
    name, default_note = _HOLIDAYS_BY_MONTH[month]

    fixed = {
        1: 1, 2: 14, 3: 17, 5: 25, 6: 19, 7: 4, 10: 31, 12: 25,
    }
    if month in fixed:
        d = _date(year, month, fixed[month])
    elif month == 4:  # Easter (computus, simplified Anonymous Gregorian alg.)
        a = year % 19
        b = year // 100
        c = year % 100
        d_ = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d_ - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        em_month = (h + l - 7 * m + 114) // 31
        em_day = ((h + l - 7 * m + 114) % 31) + 1
        d = _date(year, em_month, em_day)
        # Easter often falls in March; if so, fall back to Apr 1 default
        # so the April newsletter always has *something* to show.
        if d.month != 4:
            d = _date(year, 4, 1)
    elif month == 8:  # Summer "fun fact" anchor — first Monday of August.
        d = _date(year, 8, 1)
        while d.weekday() != 0:
            d += _td(days=1)
    elif month == 9:  # Labor Day — first Monday
        d = _date(year, 9, 1)
        while d.weekday() != 0:
            d += _td(days=1)
    elif month == 11:  # Thanksgiving — fourth Thursday
        d = _date(year, 11, 1)
        thursdays = 0
        while True:
            if d.weekday() == 3:
                thursdays += 1
                if thursdays == 4:
                    break
            d += _td(days=1)
    else:
        return None

    note = default_note
    if overrides:
        key = f"{month:02d}"
        if overrides.get(key):
            note = overrides[key]

    date_str = d.strftime("%b %-d") if hasattr(d, "strftime") else f"{d.month}/{d.day}"
    # %-d isn't valid on Windows. Always use a portable format.
    date_str = f"{d.strftime('%b')} {d.day}"
    return (date_str, name, note)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_newsletter_holiday_lookup.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_newsletter_holiday_lookup.py flowdrip_app.py
git commit -m "feat(newsletter): add monthly holiday helper + curated data"
```

---

## Phase 5 — Holiday block in newsletter HTML

### Task 5.1: Refactor "Meet Your Hiring Partner" footer to 3-column table with holiday on LEFT

**Files:**
- Modify: `flowdrip_app.py` ~L35093 (the existing `<tr><td>` that wraps the avatar/note)

- [ ] **Step 1: Read the existing block**

Open `flowdrip_app.py` at L35063 and study the current single-cell render through L35110.

- [ ] **Step 2: Replace the single-cell render with a 3-column layout**

Find this exact block:

```python
        sections_html += f'''
        <tr><td style="padding:18px 40px 10px;background:#FFFFFF;text-align:center;">
          <table cellpadding="0" cellspacing="0" width="100%"
                 style="border-collapse:collapse;text-align:center;">
            <tr><td align="center" style="text-align:center;">
              {_avatar_img}
              <div style="font-family:{_FONT};font-size:10px;font-weight:700;
                   color:{nc["primary"]};text-transform:uppercase;
                   letter-spacing:1.6px;margin:4px 0 6px;">Meet Your Hiring Partner</div>
              <div style="font-family:{_DISPLAY_FONT};font-size:14px;
                   color:{nc["text"]};line-height:1.55;font-style:italic;
                   max-width:460px;margin:0 auto;">
                {_note_body}
              </div>
              {_activity_img}
            </td></tr>
          </table>
        </td></tr>'''
```

Replace it with:

```python
        # Compute the LEFT-rail holiday block for this issue's send month.
        from datetime import date as _date_for_hol
        _send_year = data.get("_send_year") or _date_for_hol.today().year
        _send_month = data.get("_send_month") or _date_for_hol.today().month
        _hol_overrides = (cfg.get("holiday_note_overrides") or {}) if isinstance(cfg, dict) else {}
        _hol = _holiday_for_month(int(_send_year), int(_send_month), overrides=_hol_overrides)
        if _hol:
            _hol_date, _hol_name, _hol_note = _hol
            _hol_html = (
                f'<div style="font-family:{_FONT};font-size:10px;font-weight:700;'
                f'color:{nc["primary"]};text-transform:uppercase;letter-spacing:1.6px;'
                f'margin:0 0 6px;">📅 {_hol_date}</div>'
                f'<div style="font-family:{_DISPLAY_FONT};font-size:18px;font-weight:700;'
                f'color:{nc["primary"]};margin:0 0 8px;">{_hol_name}</div>'
                f'<div style="font-family:{_FONT};font-size:12px;color:{nc["text"]};'
                f'line-height:1.5;font-style:italic;">{_hol_note}</div>'
            )
        else:
            _hol_html = "&nbsp;"

        sections_html += f'''
        <tr><td style="padding:18px 40px 10px;background:#FFFFFF;">
          <table cellpadding="0" cellspacing="0" width="100%"
                 style="border-collapse:collapse;">
            <tr>
              <td valign="top" width="28%" style="padding-right:18px;text-align:left;">
                {_hol_html}
              </td>
              <td valign="top" width="44%" style="text-align:center;">
                {_avatar_img}
                <div style="font-family:{_FONT};font-size:10px;font-weight:700;
                     color:{nc["primary"]};text-transform:uppercase;
                     letter-spacing:1.6px;margin:4px 0 6px;">Meet Your Hiring Partner</div>
                <div style="font-family:{_DISPLAY_FONT};font-size:14px;
                     color:{nc["text"]};line-height:1.55;font-style:italic;">
                  {_note_body}
                </div>
                {_activity_img}
              </td>
              <td valign="top" width="28%">&nbsp;</td>
            </tr>
          </table>
        </td></tr>'''
```

- [ ] **Step 3: Verify the file still imports cleanly**

```bash
python -c "import flowdrip_app"
```

Expected: completes with no traceback (warnings about side effects are fine).

- [ ] **Step 4: Re-run the holiday helper tests**

```bash
pytest tests/test_newsletter_holiday_lookup.py -v
```

Expected: all PASS — render change is independent of the helper.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): 3-column footer with monthly holiday on LEFT"
```

---

## Phase 6 — The Refresh Modal (replaces inline panel)

This is the largest task. Build the modal, wire all four trigger sites, then delete the dead inline panel code.

### Task 6.1: Add the modal function `_refresh_newsletter_modal`

**Files:**
- Modify: `flowdrip_app.py` — insert immediately after `_create_newsletter_dialog` (find its `dlg.open()` line at L18596 and insert after it)

- [ ] **Step 1: Insert the modal function**

```python
def _refresh_newsletter_modal(s, rf, camp: dict, step_idx: int) -> None:
    """Centered modal that owns the 'Refresh & Confirm' flow for one
    newsletter issue. Replaces the old inline panel that lived at the
    bottom of `p_evergreen` and was hard to find.

    Layout:
      Header: 'Review: {name} — {issue}'                X close
      Hero photo (640×180) + ◀ ▶ overlay arrows + 'N of M' + Upload link
      Subject (editable)
      Body (editable rich text)
      Footer: [ Cancel ]                  [ ✓ Confirm & Schedule ]
    """
    steps = camp.get("emails", []) or []
    if step_idx < 0 or step_idx >= len(steps):
        ui.notify("Step not found.", type="warning")
        return
    step = steps[step_idx]
    issue_label = step.get("name") or f"Issue {step_idx + 1}"

    # Mutable state shared with closures.
    state: dict = {
        "subject": step.get("subject", "") or "",
        "body": step.get("body", "") or "",
        "hero_variant": int(step.get("_hero_variant", 0) or 0),
        "is_generating": not (step.get("body") or "").strip()
                          or "[AI:" in (step.get("body") or ""),
        "error": "",
    }

    with ui.dialog() as dlg, ui.card().style(
            f"background:{C['bg']};border:1px solid {C['border']};"
            f"border-radius:14px;padding:0;width:760px;max-width:96vw;"
            f"max-height:92vh;display:flex;flex-direction:column;"):

        # ── Header bar ─────────────────────────────────────────────────
        with ui.element("div").style(
                f"display:flex;align-items:center;justify-content:space-between;"
                f"padding:16px 20px;border-bottom:1px solid {C['border']};"):
            ui.label(f"Review: {camp.get('newsletter_name') or camp.get('name','')} — {issue_label}").style(
                f"font-size:15px;font-weight:700;color:{C['teal']};"
                f"font-family:'Nunito',sans-serif;")
            with ui.element("button").style(
                    "background:transparent;border:none;cursor:pointer;"
                    f"color:{C['muted']};font-size:18px;").on("click", dlg.close):
                ui.label("✕").style("pointer-events:none;")

        # ── Body region (scrolls inside the modal) ──────────────────────
        body_region = ui.element("div").style(
            "padding:16px 20px;overflow-y:auto;flex:1 1 auto;")
        with body_region:
            # Hero photo placeholder — render via re-render closure so
            # arrow clicks update the displayed variant in place.
            hero_holder = ui.element("div").style("position:relative;width:100%;")

            def _render_hero() -> None:
                hero_holder.clear()
                with hero_holder:
                    _slug, _city, _state = _hero_slug_city_state(camp)
                    cache_dir = _hero_cache_dir()
                    total = int(step.get("_hero_total", 5) or 5)
                    idx = state["hero_variant"] % max(1, total)
                    img_path = cache_dir / f"{_slug}.unsplash.{idx}.hero.jpg"
                    if not img_path.exists():
                        # Try to download just-in-time.
                        try:
                            _unsplash_download_variant(_slug, cache_dir, idx)
                        except Exception:
                            pass
                    src_url = f"/static_hero/{_slug}.unsplash.{idx}.hero.jpg"
                    ui.html(
                        f'<img src="{src_url}" style="width:100%;height:180px;'
                        f'object-fit:cover;border-radius:8px;display:block;"/>'
                    )
                    # Overlay: ◀  '2 of 5'  ▶
                    def _prev():
                        state["hero_variant"] = (state["hero_variant"] - 1) % total
                        _render_hero()
                    def _next():
                        state["hero_variant"] = (state["hero_variant"] + 1) % total
                        _render_hero()
                    with ui.element("div").style(
                            "position:absolute;inset:0;display:flex;"
                            "align-items:center;justify-content:space-between;"
                            "padding:0 8px;pointer-events:none;"):
                        with ui.element("button").style(
                                "background:rgba(0,0,0,0.55);color:#fff;"
                                "border:none;border-radius:50%;width:34px;height:34px;"
                                "cursor:pointer;font-size:14px;pointer-events:auto;"
                                ).on("click", _prev):
                            ui.label("◀").style("pointer-events:none;")
                        with ui.element("button").style(
                                "background:rgba(0,0,0,0.55);color:#fff;"
                                "border:none;border-radius:50%;width:34px;height:34px;"
                                "cursor:pointer;font-size:14px;pointer-events:auto;"
                                ).on("click", _next):
                            ui.label("▶").style("pointer-events:none;")
                    ui.html(
                        f'<div style="position:absolute;bottom:8px;right:10px;'
                        f'background:rgba(0,0,0,0.6);color:#fff;font-size:11px;'
                        f'padding:3px 9px;border-radius:99px;font-family:inherit;">'
                        f'Photo {idx + 1} of {total}</div>'
                    )

            _render_hero()

            # Upload link directly under the photo.
            def _on_upload(e):
                _slug, _city, _state = _hero_slug_city_state(camp)
                cache_dir = _hero_cache_dir()
                try:
                    raw = e.content.read()
                    from io import BytesIO
                    from PIL import Image
                    img = Image.open(BytesIO(raw)).convert("RGB")
                    # Crop to 640x180 (same logic the Unsplash path uses).
                    target_w, target_h = 640, 180
                    scale = max(target_w / img.width, target_h / img.height)
                    new_w, new_h = int(img.width * scale), int(img.height * scale)
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                    left = (new_w - target_w) // 2
                    top = (new_h - target_h) // 2
                    img = img.crop((left, top, left + target_w, top + target_h))
                    out = BytesIO(); img.save(out, format="JPEG", quality=86)
                    (cache_dir / f"{_slug}.hero.jpg").write_bytes(out.getvalue())
                    # Clear unsplash cache so the new upload wins
                    for fp in cache_dir.glob(f"{_slug}.unsplash.*.hero.jpg"):
                        try: fp.unlink()
                        except Exception: pass
                    state["hero_variant"] = 0
                    _render_hero()
                    ui.notify("Photo updated.", type="positive")
                except Exception as ex:
                    ui.notify(f"Upload failed: {ex}", type="warning")

            _uploader = ui.upload(on_upload=_on_upload, max_files=1, auto_upload=True
                                  ).props("accept=image/*").style("display:none;")
            with ui.element("div").style("margin:8px 0 14px;"):
                with ui.element("button").style(
                        f"background:transparent;border:none;cursor:pointer;"
                        f"color:{C['teal']};font-size:11px;font-family:inherit;"
                        f"padding:0;").on("click", lambda: _uploader.run_method("pickFiles")):
                    ui.label("↑ Upload your own").style("pointer-events:none;")

            # ── Subject ─────────────────────────────────────────────────
            ui.label("Subject").classes("fd-fl")
            _subj_inp = ui.input(value=state["subject"]).style(
                f"width:100%;background:{C['surface']};border:1px solid {C['border']};"
                f"border-radius:6px;padding:8px 10px;color:{C['text_l']};"
                f"font-family:inherit;margin-bottom:14px;")

            # ── Body ────────────────────────────────────────────────────
            ui.label("Body").classes("fd-fl")
            body_holder = ui.element("div")

            def _render_body():
                body_holder.clear()
                with body_holder:
                    if state["is_generating"]:
                        with ui.element("div").style(
                                f"background:{C['surface']};border:1px dashed {C['border']};"
                                f"border-radius:8px;padding:30px;text-align:center;"
                                f"min-height:380px;display:flex;flex-direction:column;"
                                f"align-items:center;justify-content:center;"):
                            ui.label("Generating fresh content…").style(
                                f"color:{C['teal']};font-size:14px;font-weight:600;"
                                f"margin-bottom:6px;")
                            ui.label("Claude is researching the market. ~15-30 seconds.").style(
                                f"color:{C['muted']};font-size:12px;")
                    elif state["error"]:
                        with ui.element("div").style(
                                f"background:{C['danger']}15;border:1px solid {C['danger']}40;"
                                f"border-radius:8px;padding:18px;"):
                            ui.label("Generation failed").style(
                                f"color:{C['danger']};font-weight:700;margin-bottom:6px;")
                            ui.label(state["error"]).style(
                                f"color:{C['text_l']};font-size:12px;margin-bottom:10px;")
                            with ui.element("button").style(
                                    f"background:{C['teal']};color:#0D1520;"
                                    f"border:none;border-radius:6px;padding:6px 14px;"
                                    f"cursor:pointer;font-family:inherit;").on(
                                    "click", lambda: (_kick_off_generation(), _render_body())):
                                ui.label("Try again").style("pointer-events:none;")
                    else:
                        nonlocal_body[0] = ui.editor(value=state["body"]).style(
                            f"min-height:380px;background:{C['surface']};"
                            f"border:1px solid {C['border']};border-radius:6px;"
                            f"color:{C['text_l']};font-family:inherit;")

            nonlocal_body = [None]  # holder for the ui.editor reference

            def _kick_off_generation():
                state["is_generating"] = True
                state["error"] = ""
                _render_body()

                def _bg():
                    try:
                        if getattr(s, "_user_email", ""):
                            _CURRENT_USER_EMAIL.set(s._user_email)
                            _switch_to_user_paths(s._user_email)
                        subj, body = _generate_newsletter_content_for_step(camp, step_idx)
                        if not subj or not body:
                            state["error"] = "Generator returned empty content."
                        else:
                            state["subject"] = subj
                            state["body"] = body
                    except Exception as ex:
                        state["error"] = str(ex)
                    finally:
                        state["is_generating"] = False
                        # UI updates from threads must happen on the main loop.
                        try:
                            _subj_inp.set_value(state["subject"])
                        except Exception:
                            pass
                        _render_body()

                import threading as _thr
                _thr.Thread(target=_bg, daemon=True).start()

            if state["is_generating"]:
                _kick_off_generation()
            _render_body()

        # ── Footer bar (sticky) ────────────────────────────────────────
        with ui.element("div").style(
                f"display:flex;align-items:center;justify-content:space-between;"
                f"padding:12px 20px;border-top:1px solid {C['border']};"
                f"background:{C['card']};border-radius:0 0 14px 14px;"):
            with ui.element("button").classes("fd-gb").style(
                    "padding:8px 16px;font-size:12px;").on("click", dlg.close):
                ui.label("Cancel")

            def _confirm():
                # Pull latest values from inputs + state.
                step["subject"] = _subj_inp.value or state["subject"]
                step["body"] = (nonlocal_body[0].value
                                if nonlocal_body[0] is not None else state["body"])
                step["_hero_variant"] = state["hero_variant"]
                step["confirmed"] = True
                step["auto_confirmed"] = False  # user just owned it
                save_campaign(camp)
                # Update any pending queue items so the scheduler sends the
                # confirmed copy, not the cached pre-confirm version.
                try:
                    _sync_queue_after_step_edit(
                        camp.get("name", ""),
                        step.get("name", "") or step.get("subject", ""),
                        step["subject"], step["body"])
                except Exception as ex:
                    print(f"[NewsletterModal] queue sync warn: {ex}", flush=True)
                ui.notify("Confirmed. This issue is locked in for send.",
                          type="positive")
                dlg.close()
                rf()

            with ui.element("button").classes("fd-pb").style(
                    "padding:8px 22px;font-size:13px;").on("click", _confirm):
                ui.label("✓ Confirm & Schedule")

    dlg.open()
```

- [ ] **Step 2: Add the helper functions the modal depends on**

The modal references `_hero_slug_city_state`, `_hero_cache_dir`, and `_sync_queue_after_step_edit`. Some exist as inline closures in the old inline-panel code. Promote them to module-level helpers near `_unsplash_fetch_city_batch` (~L34069):

```python
def _hero_cache_dir():
    """Per-app shared dir for cached Unsplash hero images."""
    p = _BASE_DATA_DIR / "newsletter_hero_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hero_slug_city_state(camp: dict) -> tuple:
    """Resolve a normalized slug + (city, state) from the campaign's
    market_region. Used by the modal to find / fetch hero images."""
    region = (camp.get("market_region") or "").strip()
    if "," in region:
        city, state = [x.strip() for x in region.split(",", 1)]
    else:
        city, state = region, ""
    slug = (city + "_" + state).lower().replace(" ", "_") if state else city.lower().replace(" ", "_")
    return slug, city, state


def _sync_queue_after_step_edit(camp_name: str, step_name: str,
                                new_subject: str, new_body: str) -> int:
    """Update any pending queue items for this campaign+step with the
    user's confirmed subject + body. Returns count updated."""
    qp = _user_queue_path()
    if not qp.exists():
        return 0
    try:
        queue = json.loads(qp.read_text(encoding="utf-8"))
    except Exception:
        return 0
    n = 0
    for q in queue:
        if q.get("campaign") != camp_name:
            continue
        if q.get("status") != "pending":
            continue
        if step_name and (q.get("step_name") or "") != step_name:
            continue
        q["subject"] = new_subject
        q["body"] = new_body
        n += 1
    if n:
        qp.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    return n
```

- [ ] **Step 3: Add the static_hero file route if missing**

Search for `static_hero` in the file:

```bash
grep -n "static_hero" flowdrip_app.py
```

If no results, the modal needs a route to serve hero images. Find where other `app.add_static_files` calls live (search for `add_static_files`) and add right after them:

```python
app.add_static_files("/static_hero", str(_BASE_DATA_DIR / "newsletter_hero_cache"))
```

If `static_hero` already exists, skip this step.

- [ ] **Step 4: Verify the file still imports**

```bash
python -c "import flowdrip_app"
```

Expected: no traceback.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): add focused refresh modal (not yet wired)"
```

### Task 6.2: Wire the four trigger sites to call the modal

**Files:**
- Modify: `flowdrip_app.py` L18769–L18789 (reminder banner refresh button)
- Modify: `flowdrip_app.py` L18877–L18896 (newsletter card Refresh button)
- Modify: `flowdrip_app.py` L19101–L19260 (any other inline refresh trigger)

- [ ] **Step 1: Replace reminder-banner trigger**

In `flowdrip_app.py` find the existing `_refresh_inplace` closure inside the reminder banner (starts L18769). Replace its body with a single line:

```python
                        def _refresh_inplace(c=_camp_obj):
                            _next_idx = _find_next_evergreen_step(c)
                            _steps = c.get("emails", []) or []
                            if _next_idx >= len(_steps):
                                ui.notify("All newsletter issues have been sent.",
                                          type="info")
                                return
                            _refresh_newsletter_modal(s, rf, c, _next_idx)
```

- [ ] **Step 2: Replace newsletter-card trigger**

Find the `_refresh` closure inside the newsletter-card render (starts L18877). Replace its body with:

```python
                            def _refresh(c=camp):
                                _next_idx = _find_next_evergreen_step(c)
                                _steps = c.get("emails", []) or []
                                if _next_idx >= len(_steps):
                                    ui.notify("All newsletter issues have been sent.",
                                              type="info")
                                    return
                                _refresh_newsletter_modal(s, rf, c, _next_idx)
```

- [ ] **Step 3: Find and replace any remaining trigger sites**

```bash
grep -n "_market_refresh_step.*generating" flowdrip_app.py
```

For each remaining hit (besides the one inside the modal's body editor render), replace the surrounding click handler body the same way as Steps 1 and 2.

- [ ] **Step 4: Verify the file still imports**

```bash
python -c "import flowdrip_app"
```

Expected: no traceback.

- [ ] **Step 5: Run all newsletter tests**

```bash
pytest tests/test_newsletter_*.py -v
```

Expected: all PASS (modal wiring doesn't change tested behavior, but smoke-checks that we didn't break helpers).

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): wire all refresh buttons to new modal"
```

### Task 6.3: Delete the dead inline panel render

**Files:**
- Modify: `flowdrip_app.py` L19353–L20020 (the `if _rcamp and _rstep_mode:` block in `p_evergreen`)

- [ ] **Step 1: Locate the dead block**

```bash
grep -n "Newsletter refresh flow (triggered by Refresh button on campaign card)" flowdrip_app.py
```

That should land near L19353. The block runs from there to ~L20020 and ends just before the next major comment header in `p_evergreen`.

- [ ] **Step 2: Delete the block**

Open the file, identify the start (the `# ── Newsletter refresh flow…` comment) and the end (the line just before `# ── End refresh flow ──` or the next sibling section). Delete the entire `if _rcamp and _rstep_mode:` branch. Leave a single-line breadcrumb comment in its place:

```python
    # Newsletter refresh now uses _refresh_newsletter_modal() — see L18597.
```

- [ ] **Step 3: Find and remove the now-unreferenced state vars**

```bash
grep -n "_market_refresh_step\|_market_refresh_camp\|_market_refresh_idx\|_market_refresh_body\|_market_refresh_subject\|_market_spotlight_mode\|_market_spotlight_desc\|_market_generation_started" flowdrip_app.py
```

If the only remaining references are AppState defaults (likely a list at app start), delete those defaults. If anything else references them (search again to be sure), leave it alone — investigate before deleting.

- [ ] **Step 4: Verify the file imports and tests pass**

```bash
python -c "import flowdrip_app"
pytest tests/test_newsletter_*.py -v
```

Expected: import OK, all newsletter tests PASS.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "chore(newsletter): delete dead inline refresh panel"
```

---

## Phase 7 — Hero thumbnail + "Auto-refreshed" badge on the card

### Task 7.1: Add hero thumbnail + "Change photo" link to the newsletter card

**Files:**
- Modify: `flowdrip_app.py` ~L18874 (the action-buttons region)

- [ ] **Step 1: Insert thumbnail before the Refresh button**

Find this line (around L18874):

```python
                    with ui.element("div").style(
                            "flex-shrink:0;display:flex;gap:6px;").on("click.stop", lambda: None):
                        # Refresh button for newsletter campaigns
                        if _is_newsletter:
```

Insert directly after `if _is_newsletter:` and BEFORE the `def _refresh(c=camp):`:

```python
                            # Hero thumbnail + Change photo link.
                            try:
                                _slug, _, _ = _hero_slug_city_state(camp)
                                _next_idx_for_thumb = _find_next_evergreen_step(camp)
                                _step_for_thumb = (camp.get("emails", []) or [{}])[
                                    min(_next_idx_for_thumb, max(0, len(camp.get("emails", []) or []) - 1))]
                                _hv = int(_step_for_thumb.get("_hero_variant", 0) or 0)
                                _thumb_url = f"/static_hero/{_slug}.unsplash.{_hv}.hero.jpg"
                            except Exception:
                                _thumb_url = ""
                            if _thumb_url:
                                def _open_for_photo(c=camp):
                                    _idx = _find_next_evergreen_step(c)
                                    _refresh_newsletter_modal(s, rf, c, _idx)
                                with ui.element("div").style(
                                        "display:flex;flex-direction:column;align-items:center;"
                                        "gap:2px;cursor:pointer;").on("click", _open_for_photo):
                                    ui.html(
                                        f'<img src="{_thumb_url}" style="width:80px;height:30px;'
                                        f'object-fit:cover;border-radius:4px;display:block;'
                                        f'pointer-events:none;"/>')
                                    ui.label("Change photo").style(
                                        f"font-size:9px;color:{C['muted']};"
                                        f"pointer-events:none;text-decoration:underline;")
```

- [ ] **Step 2: Verify the file imports**

```bash
python -c "import flowdrip_app"
```

Expected: no traceback.

- [ ] **Step 3: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): show hero thumbnail + 'Change photo' on cards"
```

### Task 7.2: Add "ⓘ Auto-refreshed" badge when the next pending step has `auto_confirmed: true`

**Files:**
- Modify: `flowdrip_app.py` ~L18866 (the meta line of the newsletter card)

- [ ] **Step 1: Insert the badge after the meta label**

Find this line (~L18869):

```python
                            ui.label(_meta).style(
                                f"font-size:11px;color:{C['muted']};pointer-events:none;")
```

Insert directly after it:

```python
                            # Auto-refreshed badge: tell the user the system
                            # generated the next-pending issue without their input.
                            try:
                                _ar_idx = _find_next_evergreen_step(camp)
                                _ar_step = (camp.get("emails", []) or [None])[
                                    _ar_idx if _ar_idx < len(camp.get("emails", []) or []) else 0]
                                _was_auto = bool(_ar_step and _ar_step.get("auto_confirmed")
                                                 and not _ar_step.get("confirmed"))
                            except Exception:
                                _was_auto = False
                            if _was_auto:
                                ui.label("ⓘ Auto-refreshed").style(
                                    f"font-size:10px;color:{C['muted']};"
                                    f"background:{C['surface']};border:1px solid {C['border']};"
                                    f"border-radius:99px;padding:1px 8px;margin-left:8px;"
                                    f"pointer-events:none;")
```

- [ ] **Step 2: Verify the file imports**

```bash
python -c "import flowdrip_app"
```

Expected: no traceback.

- [ ] **Step 3: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): show 'Auto-refreshed' badge on cards when sweep ran"
```

### Task 7.3: Add "Will auto-send fresh content {date}" line to reminder banner rows

**Files:**
- Modify: `flowdrip_app.py` ~L18749 (inside the per-step row in the reminder banner)

- [ ] **Step 1: Insert the auto-send note**

Find this block (~L18749):

```python
                            ui.label(when).style(
                                f"font-size:11px;font-weight:700;color:{when_col};"
                                f"flex-shrink:0;min-width:80px;text-align:right;")
```

Insert AFTER it (still inside the row `with` block):

```python
                            # Auto-send promise (newsletter only). Reassures
                            # users that ignoring this won't send empty content.
                            if _is_newsletter_reminder:
                                ui.label(
                                    f"Will auto-send fresh content {r['send_date'].strftime('%b %d')} if not confirmed."
                                ).style(
                                    f"font-size:10px;font-style:italic;color:{C['muted']};"
                                    f"margin-top:2px;flex-basis:100%;")
```

Note: `_is_newsletter_reminder` is defined further down in the existing code (~L18765). The label needs to be inserted *after* that variable is defined. Move the label insertion to immediately after the `if _is_newsletter_reminder:` branch instead, OR move the `_is_newsletter_reminder` definition above this row.

- [ ] **Step 2: Cleaner alternative — move the `_is_newsletter_reminder` line up**

Re-read L18753–L18768 to confirm the variable's current scope, then move:

```python
                    _camp_obj = next(
                        (c for c in camps if c.get("name") == camp_name), None)
                    _is_newsletter_reminder = bool(
                        _camp_obj and _camp_obj.get("market_analysis"))
```

…to BEFORE the `for r in unique:` loop (~L18719), so it's available inside row rendering. Then insert the auto-send note as in Step 1.

- [ ] **Step 3: Verify the file imports**

```bash
python -c "import flowdrip_app"
```

Expected: no traceback.

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): reminder banner promises 'Will auto-send fresh content'"
```

---

## Phase 8 — User profile field for holiday note overrides

### Task 8.1: Add `holiday_note_overrides` to the Profile/Settings panel

**Files:**
- Modify: `flowdrip_app.py` near L9799 (where `newsletter_personal_note` is wired in Settings)

- [ ] **Step 1: Locate the existing Profile section that wires `newsletter_personal_note`**

```bash
grep -n "newsletter_personal_note" flowdrip_app.py | head -10
```

Find the UI render that exposes that field as a textarea (likely near a Settings dialog).

- [ ] **Step 2: Add a single optional field**

For now, keep it minimal: one collapsible "Holiday note overrides (advanced)" section with a textarea labeled "Override per month (one per line, MM: text)". Save into `cfg["holiday_note_overrides"]` as `{"05": "...", "11": "..."}`.

The render code, inserted after the `newsletter_personal_note` block:

```python
            # Optional: per-month holiday note overrides. Shown collapsed by default.
            with ui.expansion("Holiday note overrides (advanced)").style(
                    f"width:100%;color:{C['muted']};font-size:12px;"):
                ui.label(
                    "One per line, like '05: Closed Mon May 25 — back Tue.'  "
                    "Leave empty for the default. Two-digit month (01–12).").style(
                    f"font-size:11px;color:{C['muted']};margin-bottom:6px;")
                _existing = cfg.get("holiday_note_overrides", {}) or {}
                _initial_text = "\n".join(
                    f"{k}: {v}" for k, v in sorted(_existing.items()))
                _hol_inp = ui.textarea(value=_initial_text,
                    placeholder="05: Office closed May 25\n11: Closed Thu-Fri for Thanksgiving").style(
                    f"width:100%;min-height:100px;background:{C['surface']};"
                    f"border:1px solid {C['border']};border-radius:6px;padding:8px;"
                    f"color:{C['text_l']};font-family:inherit;font-size:12px;")

                def _save_holiday_overrides():
                    parsed: dict = {}
                    for line in (_hol_inp.value or "").splitlines():
                        line = line.strip()
                        if not line or ":" not in line:
                            continue
                        k, v = line.split(":", 1)
                        k = k.strip().zfill(2)
                        if k.isdigit() and 1 <= int(k) <= 12:
                            parsed[k] = v.strip()
                    cfg["holiday_note_overrides"] = parsed
                    save_config(cfg)
                    ui.notify("Holiday overrides saved.", type="positive")

                with ui.element("button").classes("fd-pb").style(
                        "padding:6px 14px;font-size:11px;margin-top:6px;").on(
                        "click", _save_holiday_overrides):
                    ui.label("Save holiday overrides")
```

- [ ] **Step 3: Verify the file imports**

```bash
python -c "import flowdrip_app"
```

Expected: no traceback.

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): per-month holiday note overrides in Settings"
```

---

## Phase 9 — Final verification and deploy

### Task 9.1: Run the full newsletter test suite

- [ ] **Step 1: Run every newsletter-related test**

```bash
pytest tests/test_newsletter_*.py -v
```

Expected: all PASS.

- [ ] **Step 2: Run a fast smoke of the full suite**

```bash
pytest tests/ -x --timeout=30 2>&1 | tail -40
```

Expected: no NEW failures introduced. (The repo may have pre-existing flakes — investigate any failure and confirm it's not caused by this branch.)

- [ ] **Step 3: Static import check**

```bash
python -c "import flowdrip_app; print('OK')"
```

Expected: prints `OK`.

### Task 9.2: Live deploy and smoke check

Per project memory `feedback_zero_downtime_deploy.md` and `feedback_smoke_check_before_deploy.md`:

- [ ] **Step 1: Ask the user before deploying**

The project memory says: 8am–5pm PDT, **ask** "deploy now or end of hour?" after each change. Today is 2026-05-02. Confirm deploy timing before running the deploy script.

- [ ] **Step 2: Deploy with zero-downtime script**

```bash
bash _deploy_zero_downtime.sh
```

Expected: script completes successfully.

- [ ] **Step 3: Live smoke check**

In a browser, hit `https://dripdripdrop.ai/` (NOT just `/healthz` — per memory, healthz can pass while page-render path is broken). Verify:

1. The Slow Drip Sequence page loads.
2. Click `Refresh & Confirm` on a newsletter — modal opens **in the center of the screen**, not below the fold.
3. Inside the modal: hero photo with ◀ ▶ arrows, "Photo N of 5" badge, subject + body editable, footer Confirm button visible.
4. Click ▶ on the photo: image cycles to the next variant.
5. Click `✓ Confirm & Schedule`: modal closes, card shows confirmed state.
6. Reopen the same newsletter: confirmed steps don't re-trigger generation.
7. (Newsletter footer) preview an issue — holiday block appears LEFT of "Meet Your Hiring Partner" face/quote.

- [ ] **Step 4: If anything fails**

Investigate root cause. Do NOT skip the failure or revert the deploy without diagnosis. Report findings to the user before any rollback.

### Task 9.3: Open PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin claude/newsletter-ux-overhaul
```

- [ ] **Step 2: Open the PR**

Use `gh pr create` with a concise title and the spec URL in the body. Title: `Newsletter UX overhaul — modal review + hero swap + auto-refresh + holiday block`.

---

## Risk Notes

- **NiceGUI dialog clicks while a background thread updates state**: `_kick_off_generation` updates `state` from a non-UI thread. NiceGUI is generally tolerant when calls happen via existing element refs, but if the modal feels stuck after a regen, wrap the post-thread render in `ui.timer(0.1, _render_body, once=True)` instead of calling `_render_body()` directly.
- **`_static_hero` route**: if NiceGUI's `app.add_static_files` is restricted by version, the modal may fail to load images. Verify the route exists; if not, fall back to embedding hero images as base64 data-URIs in the `<img>` tag (slower but route-free).
- **Existing `_market_refresh_step` references in tests**: search before deleting. None expected, but verify with `grep -rn "_market_refresh_" tests/`.
- **Holiday `%-d` format**: the spec used `%-d` which is invalid on Windows. The helper sticks to `%b` + `str(day)` for portability.

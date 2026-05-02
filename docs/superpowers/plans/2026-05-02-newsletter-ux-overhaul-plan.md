# Newsletter UX Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop manual newsletter "Refresh & Confirm" entirely. Auto-refresh every newsletter 3 days before send, email a preview to the user's inbox, default each issue to a different hero photo, give them a focused Edit modal accessible from the card or a deep link in the preview email. Add a dedicated "📰 Newsletters" left-nav page. Add a monthly holiday block to the newsletter footer.

**Architecture:** Single-file NiceGUI app (`flowdrip_app.py`, ~42K lines). Server-side generation/scheduling already exists (`_generate_newsletter_content_for_step` at L35257, `_auto_refresh_newsletter_tick` at L35450 — already runs every 6 hours and already sends a preview email at L35612). UI changes use NiceGUI `ui.dialog()`. Tests use the existing `isolated_appdata` + `with_user` pytest fixtures.

**Tech Stack:** Python 3.12, NiceGUI, Anthropic SDK, pytest, JSON file storage in per-user dirs.

---

## Spec

`docs/superpowers/specs/2026-05-02-newsletter-ux-overhaul-design.md`

## File Structure

All work lands in **`flowdrip_app.py`** (the existing monolithic NiceGUI app — established pattern, don't split). New tests live under **`tests/`**.

| Area | Location | Responsibility |
| --- | --- | --- |
| Reminder banner — drop newsletters | `flowdrip_app.py` L18237 (`get_evergreen_reminders`) | Filter out `market_analysis: True` campaigns. |
| Edit modal | `flowdrip_app.py` — new `_edit_newsletter_modal(s, rf, camp, step_idx)` after `_create_newsletter_dialog` (~L18596) | Single-task focused dialog: hero carousel + subject + body + Save/Cancel. |
| Modal trigger sites | `flowdrip_app.py` — newsletter card "✦ Refresh" button (~L18877) renamed to "✎ Edit" | Open modal directly. |
| Inline panel removal | `flowdrip_app.py` L19353–L20020 (`if _rcamp and _rstep_mode:` block) | Delete entirely (modal owns the flow). |
| Hero thumbnail on card | `flowdrip_app.py` ~L18874 | Add 80×30 thumbnail before the Edit button. |
| Auto-refreshed badge on card | `flowdrip_app.py` ~L18866 | Render small grey "ⓘ Auto-refreshed" pill if next pending step has `auto_confirmed: true`. |
| Auto-generate all issues | `flowdrip_app.py` L18540–L18577 (`_gen_first_issue`) + new `_gen_all_issues_for_campaign` near L35257 | Loop over all step indices. |
| Auto-refresh sweep changes | `flowdrip_app.py` L35450–L35650 (`_auto_refresh_newsletter_tick`) | Window 3 days; default `_hero_variant = step_idx % 5`; skip `confirmed`; stamp `auto_confirmed`; updated preview email subject. |
| Deep link `?edit_newsletter=...` | `flowdrip_app.py` page-load handler (search `index()` route) | Parse query, open modal on first render. |
| Holiday data + helper | `flowdrip_app.py` — new `_HOLIDAYS_BY_MONTH` + `_holiday_for_month` near other newsletter helpers | Returns `(date_str, name, note)` or `None`. |
| Holiday HTML render | `flowdrip_app.py` ~L35093 | Refactor footer to 3-column table; LEFT cell = holiday block. |
| Holiday-note overrides | `flowdrip_app.py` Settings (~L9799) | Add `holiday_note_overrides` dict to user config. |
| Newsletters left-nav | `flowdrip_app.py` `SALES_NAV` ~L8385, router ~L40361 | New `("📰", "Newsletters", "newsletters")` above Reports + `p_newsletters(s, rf)` page. |
| Newsletter list extraction | `flowdrip_app.py` `p_evergreen` newsletter section | Extract into `_render_newsletter_list(s, rf, camps)`. |
| Tests | `tests/test_newsletter_*.py` (new files) | Helper-level tests. |

---

## Phase 0 — Setup

### Task 0.1: Branch

- [ ] **Step 1: Confirm clean working tree**

```bash
git status
```

Expected: branch `claude/critical-bug-fixes` (or wherever HEAD is), latest commit is `e9c3bc4 plan: newsletter UX overhaul implementation plan`.

- [ ] **Step 2: Create implementation branch**

```bash
git checkout -b claude/newsletter-ux-overhaul
```

---

## Phase 1 — Foundation: auto-refresh respects user-confirmed + stamps auto_confirmed

### Task 1.1: Test — `_auto_refresh_newsletter_tick` skips `confirmed: true`

**Files:**
- Create: `tests/test_newsletter_auto_refresh_skip.py`

- [ ] **Step 1: Write the failing test**

```python
"""User-confirmed newsletter steps must NOT be overwritten by the
6-hour auto-refresh sweep. Without this, manual edits in the modal
get clobbered the next time the scheduler tick runs."""
import json
from datetime import datetime, timedelta, timezone


def test_auto_refresh_skips_confirmed_steps(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

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

Expected: FAIL — generator IS called.

- [ ] **Step 3: Add `confirmed` skip**

In `flowdrip_app.py`, find this block at L35552–L35553:

```python
            step = steps[step_idx]
            # Cooldown: skip if already refreshed recently
```

Insert the new check between `step = steps[step_idx]` and the cooldown comment:

```python
            step = steps[step_idx]
            # User-confirmed steps are owned by the user. Never overwrite.
            # `confirmed: true` is set when the user clicks Save in the Edit modal.
            if step.get("confirmed"):
                continue
            # Cooldown: skip if already refreshed recently
```

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

### Task 1.2: Test — `_auto_refresh_newsletter_tick` stamps `auto_confirmed: true` after regen

**Files:**
- Create: `tests/test_newsletter_auto_confirmed_flag.py`

- [ ] **Step 1: Write the failing test**

```python
"""When the sweep regenerates a newsletter step, it must mark the step
`auto_confirmed: true` so the UI can render the 'ⓘ Auto-refreshed' badge."""
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
    # Suppress the preview-email side effect (no Outlook/Gmail in tests).
    monkeypatch.setattr(fa, "_send_email_universal",
        lambda **kw: (True, ""))
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

- [ ] **Step 3: Stamp `auto_confirmed: true` after regen**

Find this exact block at L35573–L35577:

```python
            # Update the step on the campaign
            steps[step_idx]["subject"] = subj
            steps[step_idx]["body"] = body
            steps[step_idx]["_auto_refreshed_at"] = now_utc.isoformat()
            camp["emails"] = steps
```

Add `auto_confirmed` directly before `camp["emails"] = steps`:

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

## Phase 2 — Auto-refresh window: 3 days + auto-rotate hero photo per issue

### Task 2.1: Test — auto-refresh window narrows to 3 days

**Files:**
- Create: `tests/test_newsletter_auto_refresh_window.py`

- [ ] **Step 1: Write the failing test**

```python
"""Auto-refresh window changes from 5 days to 3 days. A newsletter
with send 4 days out should NOT be refreshed; one 3 days out SHOULD be."""
import json
from datetime import datetime, timedelta, timezone


def _setup(user_root, days_until_send):
    camp_dir = user_root / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    (camp_dir / "NL.json").write_text(json.dumps({
        "name": "NL",
        "newsletter_name": "NL",
        "market_analysis": True,
        "evergreen_only": True,
        "_owner_email": "tester@example.com",
        "emails": [{"name": "I1", "subject": "old", "body": "<p>old</p>",
                    "step_type": "email_auto"}],
    }), encoding="utf-8")
    soon = (datetime.now(timezone.utc) + timedelta(days=days_until_send)).replace(tzinfo=None).isoformat()
    (user_root / "scheduled_queue.json").write_text(json.dumps([{
        "id": "q1", "campaign": "NL", "step_name": "I1", "subject": "old",
        "to": "x@y.com", "send_dt": soon, "status": "pending",
    }]), encoding="utf-8")


def test_4_days_out_skipped(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    _setup(with_user, days_until_send=4)
    sentinel = {"called": False}
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step",
        lambda *a: (sentinel.update(called=True), ("S", "B"))[1])
    monkeypatch.setattr(fa, "_send_email_universal", lambda **kw: (True, ""))
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", with_user.parent.parent)
    fa._auto_refresh_newsletter_tick()
    assert sentinel["called"] is False


def test_3_days_out_refreshed(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    _setup(with_user, days_until_send=3)
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step",
        lambda *a: ("FRESH", "<p>FRESH</p>"))
    monkeypatch.setattr(fa, "_send_email_universal", lambda **kw: (True, ""))
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", with_user.parent.parent)
    fa._auto_refresh_newsletter_tick()
    saved = json.loads((with_user / "Campaigns" / "NL.json").read_text(encoding="utf-8"))
    assert saved["emails"][0]["subject"] == "FRESH"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_newsletter_auto_refresh_window.py -v
```

Expected: FAIL on `test_4_days_out_skipped` (current 5-day window catches 4 days too).

- [ ] **Step 3: Narrow the window**

In `_auto_refresh_newsletter_tick` at L35468 find:

```python
    refresh_window = _td(days=5)
```

Change to:

```python
    refresh_window = _td(days=3)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_newsletter_auto_refresh_window.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_newsletter_auto_refresh_window.py flowdrip_app.py
git commit -m "feat(newsletter): tighten auto-refresh window to 3 days before send"
```

### Task 2.2: Test — auto-refresh defaults `_hero_variant` to `step_idx % 5`

**Files:**
- Create: `tests/test_newsletter_auto_hero_rotate.py`

- [ ] **Step 1: Write the failing test**

```python
"""Each monthly issue should default to a different hero photo so the
newsletter doesn't look identical month after month. Auto-refresh sets
`_hero_variant = step_idx % 5` if not already set. If the user has
manually set _hero_variant, it must be preserved."""
import json
from datetime import datetime, timedelta, timezone


def _setup_with_steps(user_root, steps):
    camp_dir = user_root / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    (camp_dir / "NL.json").write_text(json.dumps({
        "name": "NL", "newsletter_name": "NL", "market_analysis": True,
        "evergreen_only": True, "_owner_email": "tester@example.com",
        "emails": steps,
    }), encoding="utf-8")
    # Queue: refresh whichever step matches first.
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None).isoformat()
    queue = []
    for i, st in enumerate(steps):
        queue.append({"id": f"q{i}", "campaign": "NL",
                      "step_name": st["name"], "subject": st.get("subject",""),
                      "to": "x@y.com", "send_dt": soon, "status": "pending"})
    (user_root / "scheduled_queue.json").write_text(json.dumps(queue), encoding="utf-8")


def test_hero_variant_defaults_to_step_index_mod_5(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    _setup_with_steps(with_user, [
        {"name": f"I{i}", "subject": "stale", "body": "<p>stale</p>",
         "step_type": "email_auto"} for i in range(7)
    ])
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step",
        lambda c, i: (f"S{i}", f"<p>B{i}</p>"))
    monkeypatch.setattr(fa, "_send_email_universal", lambda **kw: (True, ""))
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", with_user.parent.parent)

    # Run the tick enough times for each step to have a chance.
    # The current sweep refreshes one step per campaign per tick (the next
    # pending one), so loop until all are done.
    for _ in range(10):
        fa._auto_refresh_newsletter_tick()

    saved = json.loads((with_user / "Campaigns" / "NL.json").read_text(encoding="utf-8"))
    # Each refreshed step should have _hero_variant = idx % 5.
    for i, st in enumerate(saved["emails"]):
        if st.get("auto_confirmed"):
            assert st.get("_hero_variant") == i % 5, \
                f"step {i}: expected variant {i % 5}, got {st.get('_hero_variant')}"


def test_hero_variant_user_override_preserved(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    _setup_with_steps(with_user, [
        {"name": "I0", "subject": "stale", "body": "<p>stale</p>",
         "step_type": "email_auto", "_hero_variant": 4},
    ])
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step",
        lambda c, i: ("FRESH", "<p>FRESH</p>"))
    monkeypatch.setattr(fa, "_send_email_universal", lambda **kw: (True, ""))
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", with_user.parent.parent)
    fa._auto_refresh_newsletter_tick()
    saved = json.loads((with_user / "Campaigns" / "NL.json").read_text(encoding="utf-8"))
    # User's variant 4 wins — sweep does not overwrite to 0.
    assert saved["emails"][0]["_hero_variant"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_newsletter_auto_hero_rotate.py -v
```

Expected: both FAIL — `_hero_variant` not being set by the sweep.

- [ ] **Step 3: Set `_hero_variant` default during regen**

In `_auto_refresh_newsletter_tick`, find the block where `auto_confirmed` was just added (L35573–L35578):

```python
            # Update the step on the campaign
            steps[step_idx]["subject"] = subj
            steps[step_idx]["body"] = body
            steps[step_idx]["_auto_refreshed_at"] = now_utc.isoformat()
            steps[step_idx]["auto_confirmed"] = True
            camp["emails"] = steps
```

Insert the variant default between `auto_confirmed` and `camp["emails"]`:

```python
            # Update the step on the campaign
            steps[step_idx]["subject"] = subj
            steps[step_idx]["body"] = body
            steps[step_idx]["_auto_refreshed_at"] = now_utc.isoformat()
            steps[step_idx]["auto_confirmed"] = True
            # Default the hero variant to a different photo per issue so
            # consecutive months don't look identical. User overrides win.
            if "_hero_variant" not in steps[step_idx]:
                steps[step_idx]["_hero_variant"] = step_idx % 5
            camp["emails"] = steps
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_newsletter_auto_hero_rotate.py -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_newsletter_auto_hero_rotate.py flowdrip_app.py
git commit -m "feat(newsletter): auto-rotate hero photo per issue (step_idx % 5)"
```

### Task 2.3: Friendlier preview email subject

**Files:**
- Modify: `flowdrip_app.py` ~L35630

- [ ] **Step 1: Find current subject**

```bash
grep -n "Auto-Refresh Preview" flowdrip_app.py
```

Should find one match at ~L35630.

- [ ] **Step 2: Replace the subject string**

Find:

```python
                    _preview_subj = (f"[Auto-Refresh Preview] {subj}  -  sends "
                                     f"{send_aware.strftime('%b %d')}")
```

Replace with:

```python
                    _preview_subj = (f"Preview: {camp.get('newsletter_name') or camp_name}  -  "
                                     f"sends {send_aware.strftime('%b %d')}")
```

- [ ] **Step 3: Verify import**

```bash
python -c "import flowdrip_app"
```

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "ux(newsletter): friendlier preview-email subject line"
```

---

## Phase 3 — Drop newsletters from the amber reminder banner

### Task 3.1: Test — `get_evergreen_reminders` excludes newsletters

**Files:**
- Create: `tests/test_newsletter_no_amber_banner.py`

- [ ] **Step 1: Write the failing test**

```python
"""Newsletters auto-refresh themselves, so they should NOT appear in the
amber 'Slow Drip emails sending soon' reminder banner. Slow drips still do."""
import json
from datetime import datetime, timedelta


def _seed(user_root, name, market_analysis, days_out):
    camp_dir = user_root / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    (camp_dir / f"{name.replace(' ', '_')}.json").write_text(json.dumps({
        "name": name, "evergreen_only": True,
        "market_analysis": market_analysis,
        "emails": [{"name": "S1", "step_type": "email_auto"}],
    }), encoding="utf-8")
    when = (datetime.now() + timedelta(days=days_out)).isoformat()
    qp = user_root / "scheduled_queue.json"
    existing = []
    if qp.exists():
        existing = json.loads(qp.read_text(encoding="utf-8"))
    existing.append({
        "id": f"q-{name}", "campaign": name, "step_name": "S1",
        "to": "x@y.com", "send_dt": when, "status": "pending",
    })
    qp.write_text(json.dumps(existing), encoding="utf-8")


def test_newsletter_excluded_from_reminders(isolated_appdata, with_user):
    import flowdrip_app as fa
    _seed(with_user, "NL Camp", market_analysis=True, days_out=2)
    rems = fa.get_evergreen_reminders()
    assert all(r["camp_name"] != "NL Camp" for r in rems), \
        "Newsletters must NOT appear in the amber banner"


def test_slow_drip_still_appears(isolated_appdata, with_user):
    import flowdrip_app as fa
    _seed(with_user, "Plain SD", market_analysis=False, days_out=2)
    rems = fa.get_evergreen_reminders()
    assert any(r["camp_name"] == "Plain SD" for r in rems), \
        "Slow drips should still appear in the amber banner"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_newsletter_no_amber_banner.py -v
```

Expected: `test_newsletter_excluded_from_reminders` FAILS — newsletters currently appear.

- [ ] **Step 3: Filter newsletters out of `get_evergreen_reminders`**

In `flowdrip_app.py` at L18241, find:

```python
    eg_names = {c.get("name","") for c in camps if c.get("evergreen_only")}
```

Replace with:

```python
    # Newsletters auto-refresh themselves and email a preview to the user;
    # they don't need a manual-refresh reminder. Filter them out so the
    # amber banner only nags for plain slow drips.
    eg_names = {c.get("name","") for c in camps
                if c.get("evergreen_only") and not c.get("market_analysis")}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_newsletter_no_amber_banner.py -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_newsletter_no_amber_banner.py flowdrip_app.py
git commit -m "feat(newsletter): drop newsletter rows from amber reminder banner"
```

---

## Phase 4 — Auto-generate every issue at creation

### Task 4.1: Test — `_gen_all_issues_for_campaign` generates content for every step

**Files:**
- Create: `tests/test_newsletter_auto_gen_all_issues.py`

- [ ] **Step 1: Write the failing test**

```python
"""When a newsletter is created, the background generator should fill in
ALL N scheduled steps, not just step 0."""


def test_gen_all_issues_calls_generator_per_step(
        isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

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

    calls = []
    def _spy(_camp, idx):
        calls.append(idx)
        return (f"S{idx}", f"B{idx}")
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step", _spy)

    fa._gen_all_issues_for_campaign("Big Test NL")

    assert calls == [0, 1, 2]
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

- [ ] **Step 3: Add `_gen_all_issues_for_campaign`**

In `flowdrip_app.py`, find the closing line of `_generate_newsletter_content_for_step` (search for `def _auto_refresh_newsletter_tick` — insert immediately above it). Add:

```python
def _gen_all_issues_for_campaign(camp_name: str) -> None:
    """Generate AI content for every step of the named newsletter campaign.

    Used by the post-create background thread so users have a draft for
    every scheduled month immediately. Steps that already have non-empty
    bodies are skipped (idempotent — safe to re-run). Sleeps briefly
    between issues to keep the Anthropic rate limit happy.
    """
    import time as _time
    fresh = next((c for c in load_campaigns() if c.get("name") == camp_name), None)
    if not fresh or not fresh.get("emails"):
        print(f"[NewsletterAutoAll] campaign not found: {camp_name}", flush=True)
        return
    steps = fresh.get("emails", []) or []
    for idx in range(len(steps)):
        st = steps[idx]
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
        _time.sleep(3)
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

- [ ] **Step 5: Replace `_gen_first_issue` body**

In `flowdrip_app.py`, find `_gen_first_issue` at L18540. Replace the function body so it becomes:

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

- [ ] **Step 6: Verify all tests still pass**

```bash
pytest tests/test_newsletter_*.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_newsletter_auto_gen_all_issues.py flowdrip_app.py
git commit -m "feat(newsletter): auto-generate every issue on creation"
```

---

## Phase 5 — Holiday helper + render

### Task 5.1: Test — `_holiday_for_month` returns the right holiday

**Files:**
- Create: `tests/test_newsletter_holiday_lookup.py`

- [ ] **Step 1: Write the failing test**

```python
"""Holiday helper returns (date_str, name, note) for any month, with
correct handling of variable dates (Easter, Labor Day, Thanksgiving)."""


def test_fixed_holidays_lookup():
    import flowdrip_app as fa

    d, name, note = fa._holiday_for_month(2026, 1)
    assert d == "Jan 1"
    assert name == "New Year's Day"
    assert note

    d, name, _ = fa._holiday_for_month(2026, 7)
    assert d == "Jul 4"
    assert name == "Independence Day"

    d, name, _ = fa._holiday_for_month(2026, 12)
    assert (d, name) == ("Dec 25", "Christmas")


def test_thanksgiving_is_fourth_thursday():
    import flowdrip_app as fa
    d, name, _ = fa._holiday_for_month(2026, 11)
    assert d == "Nov 26"
    assert name == "Thanksgiving"


def test_labor_day_is_first_monday():
    import flowdrip_app as fa
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

- [ ] **Step 3: Add `_HOLIDAYS_BY_MONTH` and `_holiday_for_month`**

In `flowdrip_app.py`, insert above `_generate_newsletter_content_for_step` (~L35256):

```python
# ── Monthly holiday block (newsletter footer LEFT rail) ────────────────────
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
    """Return (date_str, name, note) for the named month/year. Variable-date
    holidays (Easter, Labor Day, Thanksgiving) compute the correct date for
    the given year. `overrides` is the user's `holiday_note_overrides` dict
    (keys are zero-padded "MM")."""
    from datetime import date as _date, timedelta as _td
    if month not in _HOLIDAYS_BY_MONTH:
        return None
    name, default_note = _HOLIDAYS_BY_MONTH[month]

    fixed = {1: 1, 2: 14, 3: 17, 5: 25, 6: 19, 7: 4, 10: 31, 12: 25}
    if month in fixed:
        d = _date(year, month, fixed[month])
    elif month == 4:  # Easter (Anonymous Gregorian computus)
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
        if d.month != 4:
            d = _date(year, 4, 1)
    elif month == 8:  # Summer anchor — first Monday of August
        d = _date(year, 8, 1)
        while d.weekday() != 0:
            d += _td(days=1)
    elif month == 9:  # Labor Day — first Monday
        d = _date(year, 9, 1)
        while d.weekday() != 0:
            d += _td(days=1)
    elif month == 11:  # Thanksgiving — 4th Thursday
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

### Task 5.2: Refactor "Meet Your Hiring Partner" footer to 3-column with holiday on LEFT

**Files:**
- Modify: `flowdrip_app.py` ~L35093

- [ ] **Step 1: Find the existing single-cell render**

Open `flowdrip_app.py` at L35093. Find this exact block:

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

- [ ] **Step 2: Replace with 3-column layout**

Replace the entire block above with:

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

- [ ] **Step 3: Verify file imports**

```bash
python -c "import flowdrip_app"
```

Expected: no traceback.

- [ ] **Step 4: Re-run holiday tests**

```bash
pytest tests/test_newsletter_holiday_lookup.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): 3-column footer with monthly holiday on LEFT"
```

---

## Phase 6 — Edit Modal (replaces inline panel)

### Task 6.1: Add module-level helpers used by the modal

**Files:**
- Modify: `flowdrip_app.py` near `_unsplash_fetch_city_batch` at ~L34069

- [ ] **Step 1: Insert the helpers**

Find the line `def _unsplash_fetch_city_batch(...)` at L34069. Immediately ABOVE it, insert:

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
    user's edited subject + body. Returns count updated."""
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

- [ ] **Step 2: Add static-files route for hero images**

Search for an existing `add_static_files` call:

```bash
grep -n "add_static_files" flowdrip_app.py
```

If `static_hero` is already there, skip. Otherwise add a new route next to existing static-file registrations:

```python
app.add_static_files("/static_hero", str(_BASE_DATA_DIR / "newsletter_hero_cache"))
```

- [ ] **Step 3: Verify imports**

```bash
python -c "import flowdrip_app"
```

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): add modal helpers (hero slug, cache dir, queue sync)"
```

### Task 6.2: Add the Edit Modal function

**Files:**
- Modify: `flowdrip_app.py` — insert immediately after `_create_newsletter_dialog`'s closing `dlg.open()` line (~L18596)

- [ ] **Step 1: Insert `_edit_newsletter_modal`**

```python
def _edit_newsletter_modal(s, rf, camp: dict, step_idx: int) -> None:
    """Centered modal for editing one auto-refreshed newsletter issue.
    Replaces the old inline panel that lived at the bottom of `p_evergreen`.

    Layout:
      Header:  'Edit: {name} — {issue}'                 X close
      Hero photo (640×180) + ◀ ▶ overlay arrows + 'N of M' + Upload link
      Subject (editable)
      Body (editable rich text)
      Footer:  [ Cancel ]                  [ ✓ Save changes ]
    """
    steps = camp.get("emails", []) or []
    if step_idx < 0 or step_idx >= len(steps):
        ui.notify("Step not found.", type="warning")
        return
    step = steps[step_idx]
    issue_label = step.get("name") or f"Issue {step_idx + 1}"

    state: dict = {
        "subject": step.get("subject", "") or "",
        "body": step.get("body", "") or "",
        "hero_variant": int(step.get("_hero_variant", step_idx % 5) or 0),
        "is_generating": not (step.get("body") or "").strip()
                          or "[AI:" in (step.get("body") or ""),
        "error": "",
    }

    with ui.dialog() as dlg, ui.card().style(
            f"background:{C['bg']};border:1px solid {C['border']};"
            f"border-radius:14px;padding:0;width:760px;max-width:96vw;"
            f"max-height:92vh;display:flex;flex-direction:column;"):

        # Header
        with ui.element("div").style(
                f"display:flex;align-items:center;justify-content:space-between;"
                f"padding:16px 20px;border-bottom:1px solid {C['border']};"):
            ui.label(f"Edit: {camp.get('newsletter_name') or camp.get('name','')} — {issue_label}").style(
                f"font-size:15px;font-weight:700;color:{C['teal']};"
                f"font-family:'Nunito',sans-serif;")
            with ui.element("button").style(
                    "background:transparent;border:none;cursor:pointer;"
                    f"color:{C['muted']};font-size:18px;").on("click", dlg.close):
                ui.label("✕").style("pointer-events:none;")

        # Body region (scrolls)
        body_region = ui.element("div").style(
            "padding:16px 20px;overflow-y:auto;flex:1 1 auto;")
        with body_region:
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
                        try:
                            _unsplash_download_variant(_slug, cache_dir, idx)
                        except Exception:
                            pass
                    src_url = f"/static_hero/{_slug}.unsplash.{idx}.hero.jpg"
                    ui.html(
                        f'<img src="{src_url}" style="width:100%;height:180px;'
                        f'object-fit:cover;border-radius:8px;display:block;"/>'
                    )
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
                        f'padding:3px 9px;border-radius:99px;">'
                        f'Photo {idx + 1} of {total}</div>'
                    )

            _render_hero()

            def _on_upload(e):
                _slug, _city, _state = _hero_slug_city_state(camp)
                cache_dir = _hero_cache_dir()
                try:
                    raw = e.content.read()
                    from io import BytesIO
                    from PIL import Image
                    img = Image.open(BytesIO(raw)).convert("RGB")
                    target_w, target_h = 640, 180
                    scale = max(target_w / img.width, target_h / img.height)
                    new_w, new_h = int(img.width * scale), int(img.height * scale)
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                    left = (new_w - target_w) // 2
                    top = (new_h - target_h) // 2
                    img = img.crop((left, top, left + target_w, top + target_h))
                    out = BytesIO(); img.save(out, format="JPEG", quality=86)
                    (cache_dir / f"{_slug}.hero.jpg").write_bytes(out.getvalue())
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

            ui.label("Subject").classes("fd-fl")
            _subj_inp = ui.input(value=state["subject"]).style(
                f"width:100%;background:{C['surface']};border:1px solid {C['border']};"
                f"border-radius:6px;padding:8px 10px;color:{C['text_l']};"
                f"font-family:inherit;margin-bottom:14px;")

            ui.label("Body").classes("fd-fl")
            body_holder = ui.element("div")
            nonlocal_body = [None]

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
                                    "click", lambda: _kick_off_generation()):
                                ui.label("Try again").style("pointer-events:none;")
                    else:
                        nonlocal_body[0] = ui.editor(value=state["body"]).style(
                            f"min-height:380px;background:{C['surface']};"
                            f"border:1px solid {C['border']};border-radius:6px;"
                            f"color:{C['text_l']};font-family:inherit;")

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

        # Footer (sticky)
        with ui.element("div").style(
                f"display:flex;align-items:center;justify-content:space-between;"
                f"padding:12px 20px;border-top:1px solid {C['border']};"
                f"background:{C['card']};border-radius:0 0 14px 14px;"):
            with ui.element("button").classes("fd-gb").style(
                    "padding:8px 16px;font-size:12px;").on("click", dlg.close):
                ui.label("Cancel")

            def _save():
                step["subject"] = _subj_inp.value or state["subject"]
                step["body"] = (nonlocal_body[0].value
                                if nonlocal_body[0] is not None else state["body"])
                step["_hero_variant"] = state["hero_variant"]
                step["confirmed"] = True
                step["auto_confirmed"] = False
                save_campaign(camp)
                try:
                    _sync_queue_after_step_edit(
                        camp.get("name", ""),
                        step.get("name", "") or step.get("subject", ""),
                        step["subject"], step["body"])
                except Exception as ex:
                    print(f"[NewsletterModal] queue sync warn: {ex}", flush=True)
                ui.notify("Saved. Auto-refresh will leave this issue alone now.",
                          type="positive")
                dlg.close()
                rf()

            with ui.element("button").classes("fd-pb").style(
                    "padding:8px 22px;font-size:13px;").on("click", _save):
                ui.label("✓ Save changes")

    dlg.open()
```

- [ ] **Step 2: Verify file imports**

```bash
python -c "import flowdrip_app"
```

- [ ] **Step 3: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): add focused Edit modal (not yet wired)"
```

### Task 6.3: Rename newsletter card "✦ Refresh" → "✎ Edit" + wire to modal

**Files:**
- Modify: `flowdrip_app.py` ~L18877

- [ ] **Step 1: Find existing closure**

Open `flowdrip_app.py` at L18877. Find the `_refresh` closure inside the newsletter card render.

- [ ] **Step 2: Replace closure body**

Replace the entire `_refresh` closure (and the button label change in the `ui.label` that says `"✦ Refresh"`) with:

```python
                            def _refresh(c=camp):
                                _next_idx = _find_next_evergreen_step(c)
                                _steps = c.get("emails", []) or []
                                if _next_idx >= len(_steps):
                                    ui.notify("All newsletter issues have been sent.",
                                              type="info")
                                    return
                                _edit_newsletter_modal(s, rf, c, _next_idx)
```

And find this label (~L18954):

```python
                                    ui.label("✦ Refresh").style("pointer-events:none;")
```

Replace with:

```python
                                    ui.label("✎ Edit").style("pointer-events:none;")
```

- [ ] **Step 3: Verify imports**

```bash
python -c "import flowdrip_app"
```

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): rename card 'Refresh' to 'Edit', wire to modal"
```

### Task 6.4: Delete the dead inline panel render

**Files:**
- Modify: `flowdrip_app.py` L19353–L20020

- [ ] **Step 1: Find the dead block**

```bash
grep -n "Newsletter refresh flow (triggered by Refresh button on campaign card)" flowdrip_app.py
```

- [ ] **Step 2: Delete the entire `if _rcamp and _rstep_mode:` branch**

Open the file. Identify the block start (the `# ── Newsletter refresh flow…` comment at L19353) and the block end (the line just before the next major sibling section in `p_evergreen`). Delete everything in between, leaving only:

```python
    # Newsletter editing now uses _edit_newsletter_modal() — see L18597.
```

- [ ] **Step 3: Sweep for any orphaned `_market_refresh_*` references**

```bash
grep -n "_market_refresh_step\|_market_refresh_camp\|_market_refresh_idx\|_market_refresh_body\|_market_refresh_subject\|_market_spotlight_mode\|_market_spotlight_desc\|_market_generation_started" flowdrip_app.py
```

For each surviving reference: if it's an AppState default (`__init__`), delete the line. If it's a real reference (besides the modal), investigate before deleting.

- [ ] **Step 4: Verify everything still imports + tests pass**

```bash
python -c "import flowdrip_app"
pytest tests/test_newsletter_*.py -v
```

Expected: import OK, tests PASS.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "chore(newsletter): delete dead inline refresh panel"
```

---

## Phase 7 — Hero thumbnail + Auto-refreshed badge on the card

### Task 7.1: Add 80×30 hero thumbnail with click-to-edit

**Files:**
- Modify: `flowdrip_app.py` ~L18874

- [ ] **Step 1: Insert thumbnail before the Edit button**

Find the action-buttons region (~L18874):

```python
                    with ui.element("div").style(
                            "flex-shrink:0;display:flex;gap:6px;").on("click.stop", lambda: None):
                        # Refresh button for newsletter campaigns
                        if _is_newsletter:
```

Insert directly after `if _is_newsletter:` and BEFORE the `def _refresh(c=camp):`:

```python
                            try:
                                _slug, _, _ = _hero_slug_city_state(camp)
                                _next_idx_for_thumb = _find_next_evergreen_step(camp)
                                _emails_list = camp.get("emails", []) or []
                                _step_for_thumb = _emails_list[
                                    min(_next_idx_for_thumb, max(0, len(_emails_list) - 1))
                                ] if _emails_list else {}
                                _hv = int(_step_for_thumb.get("_hero_variant",
                                                              _next_idx_for_thumb % 5) or 0)
                                _thumb_url = f"/static_hero/{_slug}.unsplash.{_hv}.hero.jpg"
                            except Exception:
                                _thumb_url = ""
                            if _thumb_url:
                                def _open_for_photo(c=camp):
                                    _idx = _find_next_evergreen_step(c)
                                    _edit_newsletter_modal(s, rf, c, _idx)
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

- [ ] **Step 2: Verify imports**

```bash
python -c "import flowdrip_app"
```

- [ ] **Step 3: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): hero thumbnail + 'Change photo' on cards"
```

### Task 7.2: Add "ⓘ Auto-refreshed" badge on cards

**Files:**
- Modify: `flowdrip_app.py` ~L18866

- [ ] **Step 1: Insert badge after the meta label**

Find this line (~L18869):

```python
                            ui.label(_meta).style(
                                f"font-size:11px;color:{C['muted']};pointer-events:none;")
```

Insert directly after it:

```python
                            try:
                                _ar_idx = _find_next_evergreen_step(camp)
                                _ar_emails = camp.get("emails", []) or []
                                _ar_step = (_ar_emails[_ar_idx]
                                            if _ar_idx < len(_ar_emails) else None)
                                _was_auto = bool(_ar_step
                                                 and _ar_step.get("auto_confirmed")
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

- [ ] **Step 2: Verify imports**

```bash
python -c "import flowdrip_app"
```

- [ ] **Step 3: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): 'Auto-refreshed' badge on cards"
```

---

## Phase 8 — Holiday note overrides in Settings

### Task 8.1: Add `holiday_note_overrides` field

**Files:**
- Modify: `flowdrip_app.py` near the `newsletter_personal_note` field in Settings

- [ ] **Step 1: Locate the existing field**

```bash
grep -n "newsletter_personal_note" flowdrip_app.py | head -10
```

Find the textarea render in the Settings/Profile UI (likely near L37748 — `p_company_profile` or similar).

- [ ] **Step 2: Add a collapsed expansion section**

After the `newsletter_personal_note` block:

```python
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

- [ ] **Step 3: Verify imports**

```bash
python -c "import flowdrip_app"
```

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): per-month holiday note overrides in Settings"
```

---

## Phase 9 — Newsletters left-nav button + dedicated page

### Task 9.1: Add `("📰", "Newsletters", "newsletters")` to SALES_NAV

**Files:**
- Modify: `flowdrip_app.py` L8385

- [ ] **Step 1: Insert above the Reports row**

Find this exact block at L8383–L8385:

```python
    # ── Content & Tools ──────────────────────────
    (None, "CONTENT & TOOLS",   None),
    ("📊", "Reports",           "pdf_gen"),
```

Replace with:

```python
    # ── Content & Tools ──────────────────────────
    (None, "CONTENT & TOOLS",   None),
    ("📰", "Newsletters",       "newsletters"),
    ("📊", "Reports",           "pdf_gen"),
```

- [ ] **Step 2: Verify imports**

```bash
python -c "import flowdrip_app"
```

- [ ] **Step 3: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(nav): add Newsletters left-nav button above Reports"
```

### Task 9.2: Add `p_newsletters(s, rf)` page + wire into router

**Files:**
- Modify: `flowdrip_app.py` near `p_evergreen` (~L18599) and the page router (~L40361)

- [ ] **Step 1: Add `p_newsletters` page function**

Insert this new function directly before `def p_evergreen(s, rf):` at ~L18599:

```python
def p_newsletters(s, rf):
    """Dedicated Newsletters page. Shows ONLY newsletter campaigns,
    no slow drips, no amber reminder banner. Same card layout as the
    newsletter section of p_evergreen."""
    _seed_evergreen_campaigns()
    all_camps = load_campaigns()
    camps = [c for c in all_camps
             if _is_evergreen(c) and c.get("market_analysis")]

    with ui.element("div").style("display:flex;align-items:center;"):
        ui.label("Newsletters").classes("fd-h1")
        _show_page_help(s, rf, "evergreen")
    ui.label("Auto-refreshed monthly. Edit any issue from the card below.").classes("fd-sub")

    # New newsletter button
    with ui.element("div").style(
            "display:flex;align-items:center;gap:10px;margin:10px 0 14px;"):
        with ui.element("button").classes("fd-pb").style(
                "padding:8px 18px;font-size:12px;").on(
                "click", lambda: _create_newsletter_dialog(s, rf)):
            ui.label("+ New Newsletter")

    if not camps:
        ui.label("No newsletter campaigns yet.").style(
            f"font-size:12px;color:{C['muted']};padding:8px 0;")
        return

    # Reuse the existing newsletter card render block from p_evergreen.
    # The simplest way is to call into the same code path — for now, we
    # render inline using the same patterns. (A future refactor can extract
    # `_render_newsletter_list(s, rf, camps)` to share with p_evergreen.)
    for i, camp in enumerate(camps):
        bg, fg, border = EVERGREEN_COLORS[i % len(EVERGREEN_COLORS)]
        steps = camp.get("emails", []) or []
        contacts = camp.get("contacts", []) or []
        # Render a simple, focused card for each newsletter — same visual
        # language as p_evergreen's newsletter section.
        with ui.element("div").style(
                f"background:{bg};border:1px solid {border};border-radius:10px;"
                f"padding:14px 18px;margin-bottom:10px;display:flex;"
                f"align-items:center;justify-content:space-between;"):
            with ui.element("div").style("flex:1;min-width:0;"):
                ui.label(camp.get("name", "")).style(
                    f"font-size:14px;font-weight:700;color:{fg};")
                _next_idx = _find_next_evergreen_step(camp)
                _next_step = (steps[_next_idx]
                              if _next_idx < len(steps) else None)
                _meta = (f"{len(steps)} issues · {len(contacts)} enrolled"
                         + (f" · next: {_next_step.get('name','')}"
                            if _next_step else ""))
                ui.label(_meta).style(
                    f"font-size:11px;color:{C['muted']};margin-top:2px;")
                # Auto-refreshed badge
                if _next_step and _next_step.get("auto_confirmed") and not _next_step.get("confirmed"):
                    ui.label("ⓘ Auto-refreshed").style(
                        f"font-size:10px;color:{C['muted']};"
                        f"background:{C['surface']};border:1px solid {C['border']};"
                        f"border-radius:99px;padding:1px 8px;margin-top:4px;"
                        f"display:inline-block;")
            # Edit button
            def _edit(c=camp):
                _idx = _find_next_evergreen_step(c)
                _emails = c.get("emails", []) or []
                if _idx >= len(_emails):
                    ui.notify("All newsletter issues have been sent.", type="info")
                    return
                _edit_newsletter_modal(s, rf, c, _idx)
            with ui.element("button").style(
                    f"padding:6px 16px;font-size:12px;font-weight:700;"
                    f"background:{C['indigo']}18;color:{C['indigo']};"
                    f"border:1px solid {C['indigo']}60;border-radius:8px;"
                    f"cursor:pointer;font-family:inherit;").on("click", _edit):
                ui.label("✎ Edit").style("pointer-events:none;")
```

- [ ] **Step 2: Wire into router**

In `flowdrip_app.py` at the page-dispatch chain (~L40361), find the line:

```python
            elif page == "evergreen":   p_evergreen(s, rf)
```

Add directly after it:

```python
            elif page == "newsletters": p_newsletters(s, rf)
```

(If the line uses different spacing, match the existing style.)

- [ ] **Step 3: Verify imports**

```bash
python -c "import flowdrip_app"
```

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): dedicated Newsletters page wired to left-nav"
```

---

## Phase 10 — Deep link from preview email to Edit modal

### Task 10.1: Route `?edit_newsletter=...` to Newsletters page + open modal

**Files:**
- Modify: `flowdrip_app.py` index `@ui.page("/")` handler (search for `@ui.page("/")` or `def index(`) — sets `s.sp` for first-render routing
- Modify: `flowdrip_app.py` `p_newsletters` (added in Task 9.2) — reads param and opens modal

- [ ] **Step 1: Find the index handler**

```bash
grep -n '@ui.page("/")\|def index(' flowdrip_app.py | head -5
```

Locate where `s.sp` is set for first render (look for the first place `AppState()` or `s.sp = "dashboard"` happens).

- [ ] **Step 2: Add query-param routing in the index handler**

At the very top of the index handler, before any rendering, insert:

```python
    # Deep link from newsletter preview email: ?edit_newsletter=<name>
    # Route the user to the Newsletters page so the modal can open there.
    try:
        from nicegui import context as _ctx
        _qs_initial = dict(_ctx.client.request.query_params)
    except Exception:
        _qs_initial = {}
    if _qs_initial.get("edit_newsletter"):
        s.sp = "newsletters"
        s.hub = "sales"
```

If `_ctx.client.request.query_params` isn't available in this NiceGUI version (check `python -c "from nicegui import context; print(dir(context.client.request))"`), fall back to:

```python
    try:
        _qs_initial = dict(context.client.request.query_params)
    except Exception:
        _qs_initial = {}
```

If neither path works, investigate the running NiceGUI version's docs for the right accessor before committing — do not guess.

- [ ] **Step 3: Add `?edit_newsletter` reader to `p_newsletters`**

In the `p_newsletters` function defined in Task 9.2, before the `for i, camp in enumerate(camps):` loop, insert:

```python
    # Deep link: open the Edit modal for the named campaign on first render.
    if not getattr(s, "_edit_newsletter_handled", False):
        try:
            from nicegui import context as _ctx
            _qs = dict(_ctx.client.request.query_params)
            _target = _qs.get("edit_newsletter", "")
        except Exception:
            _target = ""
        if _target:
            s._edit_newsletter_handled = True
            _target_camp = next((c for c in camps if c.get("name") == _target), None)
            if _target_camp:
                _idx = _find_next_evergreen_step(_target_camp)
                _emails = _target_camp.get("emails", []) or []
                if _idx < len(_emails):
                    ui.timer(0.3, lambda: _edit_newsletter_modal(s, rf, _target_camp, _idx),
                             once=True)
```

- [ ] **Step 3: Update preview email to include the deep link**

In `_auto_refresh_newsletter_tick` at ~L35635, find this block:

```python
                    ok, err = _send_email_universal(
                        to=_inbox,
                        subject=_preview_subj,
                        html_body=body,
                        is_preview=False,
                        _for_user_email=_owner_email,
                    )
```

Wrap `body` with a small "click to edit" banner before sending. Replace the call with:

```python
                    _edit_link = (f"https://dripdripdrop.ai/?edit_newsletter="
                                  f"{camp_name.replace(' ', '+')}")
                    _banner = (
                        f'<div style="background:#FFF8E1;border:1px solid #FFC107;'
                        f'border-radius:6px;padding:10px 14px;margin:0 0 16px;'
                        f'font-family:Arial,sans-serif;font-size:13px;color:#664400;">'
                        f'Auto-refreshed on {now_utc.strftime("%b %d")}. '
                        f'Sends on {send_aware.strftime("%b %d")}. '
                        f'<a href="{_edit_link}" style="color:#0066CC;font-weight:700;">'
                        f'Open in DripDrop to edit →</a>'
                        f'</div>'
                    )
                    ok, err = _send_email_universal(
                        to=_inbox,
                        subject=_preview_subj,
                        html_body=_banner + body,
                        is_preview=False,
                        _for_user_email=_owner_email,
                    )
```

- [ ] **Step 4: Verify imports**

```bash
python -c "import flowdrip_app"
```

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): preview email deep link opens Edit modal"
```

---

## Phase 11 — Final verification and deploy

### Task 11.1: Run the full newsletter test suite

- [ ] **Step 1: Run every newsletter-related test**

```bash
pytest tests/test_newsletter_*.py -v
```

Expected: all PASS.

- [ ] **Step 2: Smoke run the full suite**

```bash
pytest tests/ -x --timeout=30 2>&1 | tail -40
```

Expected: no NEW failures introduced.

- [ ] **Step 3: Static import check**

```bash
python -c "import flowdrip_app; print('OK')"
```

Expected: prints `OK`.

### Task 11.2: Live deploy

The user has explicitly requested deploy after this work is complete (message at 2026-05-02). Per project memory `feedback_zero_downtime_deploy.md`:

- [ ] **Step 1: Deploy with zero-downtime script**

```bash
bash _deploy_zero_downtime.sh
```

Expected: script completes successfully.

- [ ] **Step 2: Live smoke check (per `feedback_smoke_check_before_deploy.md`)**

In a browser, hit `https://dripdripdrop.ai/`. Verify:

1. Sidebar shows new "📰 Newsletters" entry above "📊 Reports".
2. Click it → dedicated Newsletters page opens (no slow drips, no amber banner).
3. Each newsletter card shows hero thumbnail + "✎ Edit" button.
4. Click "✎ Edit" → modal opens centered, dimmed background.
5. Modal: hero photo, ◀ ▶ arrows cycle to other variants, "Photo N of 5" badge, subject + body editable.
6. Click ✓ Save → modal closes, card shows confirmed state.
7. (Slow Drip Sequence page) — newsletter rows no longer appear in amber banner.
8. (Newsletter footer in any preview) — holiday block appears LEFT of "Meet Your Hiring Partner".

- [ ] **Step 3: Open PR**

```bash
git push -u origin claude/newsletter-ux-overhaul
gh pr create --title "Newsletter UX overhaul: auto-refresh + Edit modal + dedicated page + holidays" --body "$(cat <<'EOF'
## Summary
- Drop manual "Refresh & Confirm" — every newsletter auto-refreshes 3 days before send
- New focused Edit modal (replaces buried inline panel)
- Hero photo auto-rotates per issue; manual swap via overlay arrows
- Dedicated "📰 Newsletters" left-nav page above Reports
- Monthly holiday block in newsletter footer
- Preview email has a deep link that opens the Edit modal directly

Spec: docs/superpowers/specs/2026-05-02-newsletter-ux-overhaul-design.md
Plan: docs/superpowers/plans/2026-05-02-newsletter-ux-overhaul-plan.md

## Test plan
- [x] All newsletter pytest tests pass
- [ ] Live smoke test on https://dripdripdrop.ai/

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Risk Notes

- **NiceGUI `ui.editor` from background thread**: `_kick_off_generation` updates state from a non-UI thread. If the modal feels stuck after a regen, wrap the post-thread render in `ui.timer(0.1, _render_body, once=True)`.
- **`/static_hero` route**: if NiceGUI's `app.add_static_files` is restricted by version, fall back to embedding hero images as base64 data-URIs (slower but route-free).
- **Deep-link query param**: `nicegui.context.client.request.query_params` access pattern varies by NiceGUI version. If the import path is wrong, investigate via the running version's docs before working around.
- **Holiday `%-d` format**: `%-d` is invalid on Windows. Helper sticks to `%b` + `str(day)` for portability.
- **Preview email HTML in Outlook/Gmail**: the wrapping `_banner` div uses inline styles for compatibility. Test at least one preview in Outlook to be sure the banner renders cleanly.

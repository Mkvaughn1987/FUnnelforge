# Newsletter start-after-campaign + Enroll CSV upload & start-month picker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Default a campaign-spun newsletter's first issue to after the campaign's last email, and let users enroll newsletter contacts via direct CSV upload while choosing which monthly issue they start from.

**Architecture:** Three pure, unit-testable helpers added at module level in `flowdrip_app.py` (`_campaign_last_send_date`, `_filter_new_enrollees`, `_newsletter_enroll_start_options`), then wired into three existing UI sites (`_spin_up_from_launch`, `_create_newsletter_dialog`, `_enroll_dialog`). UI wiring reuses existing helpers (`_next_first_thursday`, `_contact_upload_and_name`, `queue_campaign_emails`).

**Tech Stack:** Python 3, NiceGUI, pytest. Tests follow the existing pure-function pattern (`import flowdrip_app as fa`, no NiceGUI harness).

**Spec:** `docs/superpowers/specs/2026-06-03-newsletter-start-after-campaign-and-enroll-design.md`

---

## File Structure

- `flowdrip_app.py`
  - **New module-level helpers** (placed immediately after `_add_business_days`, ~line 6050):
    - `_campaign_last_send_date(camp)` — projected last-step send date.
    - `_filter_new_enrollees(camp, contacts)` — dedup incoming contacts vs. already-enrolled.
    - `_newsletter_enroll_start_options(camp)` — `[(step_idx, "Mon YYYY"), ...]` for upcoming issues.
  - **Modify** `_spin_up_from_launch` (~15826) — pass `start_after` in prefill.
  - **Modify** `_create_newsletter_dialog` (21170) — honor `start_after` for the Start Date default + provenance note.
  - **Rewrite** `_enroll_dialog` (20672) — shared enroll routine, start-month picker, CSV upload path, new empty state.
- `tests/test_newsletter_start_after_campaign.py` — new, tests `_campaign_last_send_date`.
- `tests/test_newsletter_enroll_helpers.py` — new, tests `_filter_new_enrollees` + `_newsletter_enroll_start_options`.

Module-level imports already present in `flowdrip_app.py`: `from datetime import date, datetime, timedelta` (line 13). No new imports needed.

---

## Task 1: `_campaign_last_send_date` helper

**Files:**
- Modify: `flowdrip_app.py` (add helper after `_add_business_days`, ~line 6050)
- Test: `tests/test_newsletter_start_after_campaign.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_newsletter_start_after_campaign.py`:

```python
"""Tests for projecting a campaign's last-email date so a newsletter spun
up from that campaign can default its first issue to after the campaign
ends.

Spec: docs/superpowers/specs/2026-06-03-newsletter-start-after-campaign-and-enroll-design.md
"""
from datetime import date
import flowdrip_app as fa


def test_last_send_none_when_no_steps():
    assert fa._campaign_last_send_date({"emails": []}) is None
    assert fa._campaign_last_send_date({}) is None


def test_last_send_uses_fixed_dates():
    camp = {
        "start_date": "2026-06-01",
        "emails": [
            {"fixed_date": "2026-06-04"},
            {"fixed_date": "2026-07-02"},
            {"fixed_date": "2026-06-18"},
        ],
    }
    # Max fixed_date wins regardless of order.
    assert fa._campaign_last_send_date(camp) == date(2026, 7, 2)


def test_last_send_uses_cumulative_business_days_when_no_fixed_date():
    # start Mon 2026-06-01; delays 0,2,3 -> cumulative 0,2,5 business days.
    camp = {
        "start_date": "2026-06-01",
        "emails": [
            {"delay_days": 0},
            {"delay_days": 2},
            {"delay_days": 3},
        ],
    }
    expected = fa._add_business_days(date(2026, 6, 1), 5)
    assert fa._campaign_last_send_date(camp) == expected


def test_last_send_mixed_fixed_and_delay():
    camp = {
        "start_date": "2026-06-01",
        "emails": [
            {"delay_days": 0},
            {"fixed_date": "2026-09-15"},
            {"delay_days": 4},
        ],
    }
    assert fa._campaign_last_send_date(camp) == date(2026, 9, 15)


def test_last_send_falls_back_to_today_on_bad_start_date(monkeypatch):
    camp = {"start_date": "not-a-date", "emails": [{"delay_days": 0}]}
    # delay 0 from today's date -> today.
    assert fa._campaign_last_send_date(camp) == date.today()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_newsletter_start_after_campaign.py -v`
Expected: FAIL — `AttributeError: module 'flowdrip_app' has no attribute '_campaign_last_send_date'`

- [ ] **Step 3: Write minimal implementation**

In `flowdrip_app.py`, immediately after the `_add_business_days` function (ends ~line 6050), add:

```python
def _campaign_last_send_date(camp: dict):
    """Projected send date of the LAST step in `camp`.

    Mirrors the launch preview's date logic: honor a per-step `fixed_date`
    (ISO) when set, otherwise `start_date` + cumulative business-day delay.
    Returns the maximum such date across all steps, or None when the
    campaign has no steps. Used to default a spun-up newsletter's first
    issue to after the source campaign finishes."""
    steps = camp.get("emails", []) or []
    if not steps:
        return None
    try:
        start_dt = date.fromisoformat((camp.get("start_date") or "").strip())
    except Exception:
        start_dt = date.today()
    last = None
    cum = 0
    for st in steps:
        cum += int(st.get("delay_days", 0) or 0)
        fx = (st.get("fixed_date") or "").strip()
        if fx:
            try:
                sd = date.fromisoformat(fx)
            except Exception:
                sd = _add_business_days(start_dt, cum)
        else:
            sd = _add_business_days(start_dt, cum)
        if last is None or sd > last:
            last = sd
    return last
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_newsletter_start_after_campaign.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_newsletter_start_after_campaign.py flowdrip_app.py
git commit -m "feat(newsletter): project campaign last-email date for spin-up start"
```

---

## Task 2: Wire Feature 1 into the UI

**Files:**
- Modify: `flowdrip_app.py` — `_spin_up_from_launch` (~15894–15902) and `_create_newsletter_dialog` (prefill block ~21206 + Start Date block ~21349–21361)

No new unit test — this is NiceGUI wiring over the Task 1 helper. Verified by import smoke + manual check.

- [ ] **Step 1: Pass `start_after` from `_spin_up_from_launch`**

Find this block in `_spin_up_from_launch` (~line 15894):

```python
            _cn = camp.get("name", "Campaign")
            _create_newsletter_dialog(s, rf, prefill={
                "name": f"{_cn} - Monthly Newsletter",
                "sector_key": _sec_key,
                "niche": _niche,
                "region": _region,
                "contacts": camp.get("contacts", []) or [],
                "source_campaign_name": _cn,
            })
```

Replace with:

```python
            _cn = camp.get("name", "Campaign")
            _last_send = _campaign_last_send_date(camp)
            _create_newsletter_dialog(s, rf, prefill={
                "name": f"{_cn} - Monthly Newsletter",
                "sector_key": _sec_key,
                "niche": _niche,
                "region": _region,
                "contacts": camp.get("contacts", []) or [],
                "source_campaign_name": _cn,
                "start_after": _last_send.isoformat() if _last_send else "",
            })
```

- [ ] **Step 2: Read the `start_after` prefill in `_create_newsletter_dialog`**

Find this block near the top of `_create_newsletter_dialog` (~line 21206):

```python
    _pre_source = (prefill.get("source_campaign_name") or "").strip()
```

Replace with:

```python
    _pre_source = (prefill.get("source_campaign_name") or "").strip()
    _pre_start_after = (prefill.get("start_after") or "").strip()
```

- [ ] **Step 3: Use `start_after` for the Start Date default + provenance note**

Find this block (~line 21350):

```python
            with ui.element("div"):
                ui.label("Start Date").classes("fd-fl")
                _default_start_ft = _next_first_thursday()
                _default_start = _default_start_ft.strftime("%Y-%m-%d")
                start_in = ui.input(
                    value=_default_start,
                    placeholder="YYYY-MM-DD",
                ).classes("fd-input")
                ui.label(
                    "Every issue sends on the same day each month."
                ).style(
                    f"font-size:10px;color:{C['muted']};margin-top:4px;")
```

Replace with:

```python
            with ui.element("div"):
                ui.label("Start Date").classes("fd-fl")
                # When spun up from a campaign, default the first issue to the
                # first Thursday AFTER that campaign's projected last email so
                # the newsletter picks up where the campaign leaves off. The
                # +1 day guarantees it lands strictly after the campaign wraps
                # (and rolls to next month if the last email itself fell on a
                # first Thursday). Field stays editable.
                if _pre_start_after:
                    try:
                        _sa_date = date.fromisoformat(_pre_start_after)
                        _default_start_ft = _next_first_thursday(
                            _sa_date + timedelta(days=1))
                    except Exception:
                        _default_start_ft = _next_first_thursday()
                else:
                    _default_start_ft = _next_first_thursday()
                _default_start = _default_start_ft.strftime("%Y-%m-%d")
                start_in = ui.input(
                    value=_default_start,
                    placeholder="YYYY-MM-DD",
                ).classes("fd-input")
                if _pre_start_after and _pre_source:
                    ui.label(
                        f"Defaulted to the first Thursday after "
                        f"'{_pre_source}' finishes "
                        f"({_default_start_ft.strftime('%b %d, %Y')})."
                    ).style(
                        f"font-size:10px;color:{C['muted']};margin-top:4px;")
                else:
                    ui.label(
                        "Every issue sends on the same day each month."
                    ).style(
                        f"font-size:10px;color:{C['muted']};margin-top:4px;")
```

- [ ] **Step 4: Verify import + existing tests still pass**

Run: `python -c "import flowdrip_app"`
Expected: no output, exit 0 (module compiles).

Run: `python -m pytest tests/test_newsletter_start_after_campaign.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): default spin-up start to first Thursday after campaign ends"
```

---

## Task 3: `_filter_new_enrollees` helper

**Files:**
- Modify: `flowdrip_app.py` (add helper after `_campaign_last_send_date`)
- Test: `tests/test_newsletter_enroll_helpers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_newsletter_enroll_helpers.py`:

```python
"""Tests for the Enroll Contacts dialog helpers: dedup of incoming
contacts and the upcoming-issue start-month options.

Spec: docs/superpowers/specs/2026-06-03-newsletter-start-after-campaign-and-enroll-design.md
"""
import flowdrip_app as fa


def test_filter_drops_already_enrolled_and_blank_emails():
    camp = {"contacts": [{"email": "a@x.com"}]}
    incoming = [
        {"email": "A@X.com", "first_name": "Dup"},   # already enrolled (case-insensitive)
        {"email": "", "first_name": "Blank"},         # no email
        {"email": "  b@x.com  ", "first_name": "New"},  # new (whitespace trimmed for match)
    ]
    out = fa._filter_new_enrollees(camp, incoming)
    emails = [c["email"] for c in out]
    assert emails == ["  b@x.com  "]  # original dict kept, not mutated


def test_filter_dedups_within_incoming_batch():
    camp = {"contacts": []}
    incoming = [
        {"email": "c@x.com"},
        {"email": "C@X.com"},  # duplicate within the same upload
    ]
    out = fa._filter_new_enrollees(camp, incoming)
    assert len(out) == 1


def test_filter_empty_when_all_known():
    camp = {"contacts": [{"email": "a@x.com"}, {"email": "b@x.com"}]}
    incoming = [{"email": "a@x.com"}, {"email": "b@x.com"}]
    assert fa._filter_new_enrollees(camp, incoming) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_newsletter_enroll_helpers.py::test_filter_drops_already_enrolled_and_blank_emails -v`
Expected: FAIL — `AttributeError: module 'flowdrip_app' has no attribute '_filter_new_enrollees'`

- [ ] **Step 3: Write minimal implementation**

In `flowdrip_app.py`, immediately after `_campaign_last_send_date`, add:

```python
def _filter_new_enrollees(camp: dict, contacts: list) -> list:
    """Return the contacts from `contacts` that are NOT already enrolled in
    `camp` and have a non-blank email. Dedups case-insensitively against the
    campaign's existing contacts AND within the incoming batch. Returned
    dicts are the originals (not copied/mutated)."""
    existing = {(c.get("email", "") or "").lower().strip()
                for c in camp.get("contacts", [])}
    new = []
    for c in contacts:
        email = (c.get("email", "") or "").strip().lower()
        if not email or email in existing:
            continue
        new.append(c)
        existing.add(email)
    return new
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_newsletter_enroll_helpers.py -v`
Expected: PASS (3 passed — the start-option tests come in Task 4)

- [ ] **Step 5: Commit**

```bash
git add tests/test_newsletter_enroll_helpers.py flowdrip_app.py
git commit -m "feat(newsletter): _filter_new_enrollees dedup helper for enrollment"
```

---

## Task 4: `_newsletter_enroll_start_options` helper

**Files:**
- Modify: `flowdrip_app.py` (add helper after `_filter_new_enrollees`)
- Test: `tests/test_newsletter_enroll_helpers.py` (append)

Note: this helper calls `_find_next_evergreen_step(camp)` (defined at `flowdrip_app.py:20755`). Module-level functions resolve at call time, so definition order does not matter.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_newsletter_enroll_helpers.py`:

```python
from datetime import date, timedelta


def _future_iso(days):
    return (date.today() + timedelta(days=days)).isoformat()


def test_start_options_empty_when_no_steps():
    assert fa._newsletter_enroll_start_options({"emails": []}) == []


def test_start_options_list_upcoming_only_with_month_labels():
    # One past issue, two future issues. Only the future ones are offered.
    past = (date.today() - timedelta(days=40))
    fut1 = (date.today() + timedelta(days=20))
    fut2 = (date.today() + timedelta(days=50))
    camp = {
        "start_date": date.today().isoformat(),
        "emails": [
            {"name": "I0", "fixed_date": past.isoformat()},
            {"name": "I1", "fixed_date": fut1.isoformat()},
            {"name": "I2", "fixed_date": fut2.isoformat()},
        ],
    }
    opts = fa._newsletter_enroll_start_options(camp)
    # Indices preserved (1 and 2), labels are "Month YYYY".
    assert [idx for idx, _ in opts] == [1, 2]
    assert opts[0][1] == fut1.strftime("%B %Y")
    assert opts[1][1] == fut2.strftime("%B %Y")


def test_start_options_empty_when_all_past():
    past1 = (date.today() - timedelta(days=60)).isoformat()
    past2 = (date.today() - timedelta(days=30)).isoformat()
    camp = {
        "start_date": (date.today() - timedelta(days=90)).isoformat(),
        "emails": [
            {"name": "I0", "fixed_date": past1},
            {"name": "I1", "fixed_date": past2},
        ],
    }
    assert fa._newsletter_enroll_start_options(camp) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_newsletter_enroll_helpers.py::test_start_options_empty_when_no_steps -v`
Expected: FAIL — `AttributeError: module 'flowdrip_app' has no attribute '_newsletter_enroll_start_options'`

- [ ] **Step 3: Write minimal implementation**

In `flowdrip_app.py`, immediately after `_filter_new_enrollees`, add:

```python
def _newsletter_enroll_start_options(camp: dict):
    """Return [(step_index, 'Month YYYY'), ...] for every issue from the
    next upcoming step through the last. Empty when the campaign has no
    steps or every issue has already sent. The step_index is the position
    in camp['emails'] — used as `start_step` for queue_campaign_emails so a
    new enrollee can begin at this month or a later one."""
    steps = camp.get("emails", []) or []
    if not steps:
        return []
    start_idx = _find_next_evergreen_step(camp)
    out = []
    for idx in range(start_idx, len(steps)):
        fx = (steps[idx].get("fixed_date") or "").strip()
        try:
            lbl = date.fromisoformat(fx).strftime("%B %Y")
        except Exception:
            lbl = steps[idx].get("name", "") or f"Issue {idx + 1}"
        out.append((idx, lbl))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_newsletter_enroll_helpers.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_newsletter_enroll_helpers.py flowdrip_app.py
git commit -m "feat(newsletter): _newsletter_enroll_start_options for start-month picker"
```

---

## Task 5: Rewrite `_enroll_dialog` (upload + start-month picker)

**Files:**
- Modify: `flowdrip_app.py` — replace the whole `_enroll_dialog` function body (`20672`–`20742`)

No new unit test — NiceGUI dialog wiring over the Task 3/4 helpers. The dedup, start-option, and queue logic are already covered. Verified by import smoke + manual check.

- [ ] **Step 1: Replace the `_enroll_dialog` function**

Find the entire current function (from `def _enroll_dialog(camp, s, rf):` at line 20672 through `dlg.open()` at line 20742) and replace it with:

```python
def _enroll_dialog(camp, s, rf):
    """Enroll contacts into an evergreen/newsletter campaign.

    Two ways to supply contacts:
      1. Pick an existing saved contact list.
      2. Upload a new CSV right here (reuses _contact_upload_and_name, which
         validates, normalizes, and saves the list for reuse).

    A "Start from which issue" picker controls which monthly issue the new
    enrollees begin at (default: the next upcoming issue)."""
    saved = list_saved_contact_lists()
    start_opts = _newsletter_enroll_start_options(camp)
    dlg_state = {}

    def _selected_start_step():
        w = dlg_state.get("start_widget")
        try:
            if w is not None:
                return int(w.value)
        except Exception:
            pass
        return start_opts[0][0] if start_opts else 0

    with ui.dialog() as dlg, ui.card().style(
            f"min-width:420px;background:{C['card']};border:1px solid {C['border']};padding:24px;"):
        ui.label("Enroll Contacts").style(
            f"font-size:16px;font-weight:700;color:{C['text_l']};margin-bottom:4px;")
        ui.label(f"Into: {camp.get('name', '')}").style(
            f"font-size:12px;color:{C['teal']};margin-bottom:16px;")

        # No upcoming issues -> nothing to enroll into.
        if not start_opts:
            ui.label("This newsletter has no upcoming issues left — every "
                     "scheduled issue has already sent. Add more months "
                     "before enrolling new contacts.").style(
                f"font-size:13px;color:{C['muted']};margin-bottom:16px;")
            with ui.element("div").style("display:flex;justify-content:flex-end;"):
                with ui.element("button").classes("fd-gb").style(
                        "padding:6px 16px;font-size:12px;").on("click", dlg.close):
                    ui.label("Close")
            dlg.open()
            return

        # Shared enroll routine — both the saved-list and upload paths use it.
        def _do_enroll_contacts(incoming, start_step):
            new_contacts = _filter_new_enrollees(camp, incoming)
            if not new_contacts:
                ui.notify("No new contacts to enroll (all already enrolled "
                          "or no emails found).", type="info")
                return
            camp.setdefault("contacts", []).extend(new_contacts)
            camp["contact_count"] = len(camp["contacts"])
            save_campaign(camp)
            _cache_campaigns.invalidate()
            enroll_camp = dict(camp)
            enroll_camp["contacts"] = new_contacts  # queue only the new ones
            queued = queue_campaign_emails(enroll_camp, start_step=start_step)
            dlg.close()
            ui.notify(f"Enrolled {len(new_contacts)} contacts - {queued} "
                      f"emails queued!", type="positive", timeout=4000)
            rf()

        # ── Start-from-which-issue picker ────────────────────────────────
        ui.label("Start from which issue").classes("fd-fl")
        _start_options = {idx: lbl for idx, lbl in start_opts}
        dlg_state["start_widget"] = ui.select(
            options=_start_options, value=start_opts[0][0]
        ).classes("fd-input").style("margin-bottom:16px;")

        # ── Path 1: pick a saved list ────────────────────────────────────
        ui.label("Pick a saved contact list").classes("fd-fl")
        if not saved:
            ui.label("No saved lists yet — upload a CSV below to get started.").style(
                f"font-size:12px;color:{C['muted']};margin-bottom:12px;")
        else:
            options = list(saved.keys())
            sel = ui.select(options=options, value=options[0] if options else "").classes("fd-input").style(
                "margin-bottom:12px;")
            dlg_state["sel_widget"] = sel

            def _enroll_from_saved():
                sel_widget = dlg_state.get("sel_widget")
                list_name = sel_widget.value if sel_widget else ""
                csv_path = saved.get(list_name, "")
                if not csv_path or not Path(csv_path).exists():
                    ui.notify("Contact list not found.", type="warning"); return
                rows, _ = safe_read_csv_rows(csv_path)
                incoming = [dict(
                    email=(r.get("Email", r.get("email", "")) or "").strip(),
                    first_name=r.get("FirstName", r.get("first_name", "")),
                    last_name=r.get("LastName", r.get("last_name", "")),
                    company=r.get("Company", r.get("company", "")),
                    title=r.get("JobTitle", r.get("title", "")),
                ) for r in rows]
                _do_enroll_contacts(incoming, _selected_start_step())

            with ui.element("button").classes("fd-pb").style(
                    "padding:6px 16px;font-size:12px;margin-bottom:16px;"
                    ).on("click", _enroll_from_saved):
                ui.label("Enroll from list")

        # ── Path 2: upload a new CSV ─────────────────────────────────────
        ui.element("div").style(
            f"height:1px;background:{C['border']};margin:4px 0 12px;")
        ui.label("…or upload a new CSV").classes("fd-fl")
        ui.label("Validated, saved for reuse, and enrolled into the issue "
                 "selected above.").style(
            f"font-size:11px;color:{C['muted']};margin-bottom:8px;")

        def _on_uploaded(contacts):
            _do_enroll_contacts(contacts, _selected_start_step())

        # _contact_upload_and_name renders a hidden uploader and returns it;
        # a visible button triggers it via pickFiles() (same pattern as the
        # Contacts page importer).
        _upload_el = _contact_upload_and_name(s, rf, _on_uploaded)
        with ui.element("button").classes("fd-pb").style(
                "padding:6px 16px;font-size:12px;margin-bottom:8px;"
                ).on("click", lambda: _upload_el.run_method("pickFiles")):
            ui.label("⬆ Upload CSV")

        with ui.element("div").style(
                "display:flex;gap:8px;justify-content:flex-end;margin-top:8px;"):
            with ui.element("button").classes("fd-gb").style(
                    "padding:6px 16px;font-size:12px;").on("click", dlg.close):
                ui.label("Close")
    dlg.open()
```

- [ ] **Step 2: Verify import compiles**

Run: `python -c "import flowdrip_app"`
Expected: no output, exit 0.

- [ ] **Step 3: Run the full new test suite**

Run: `python -m pytest tests/test_newsletter_start_after_campaign.py tests/test_newsletter_enroll_helpers.py -v`
Expected: PASS (11 passed total).

- [ ] **Step 4: Run the broader suite to check for regressions**

Run: `python -m pytest tests/ -q`
Expected: no new failures introduced by these changes (pre-existing failures, if any, unchanged).

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(newsletter): enroll via CSV upload + choose start issue month"
```

---

## Final verification

- [ ] **Manual smoke (live):** After deploy, open a newsletter → ⚙/Enroll. Confirm: (a) "Start from which issue" lists upcoming months, (b) "Enroll from list" works, (c) "⬆ Upload CSV" opens a file picker, names the list, and enrolls. Then on a campaign launch screen, click "📰 Create a Newsletter from this campaign" and confirm the Start Date defaults to a first Thursday after the campaign's last email, with the provenance note.
- [ ] **Deploy** per project policy: `bash _deploy_zero_downtime.sh`, then verify live `/` (not just `/healthz`) renders.

---

## Self-Review notes

- **Spec coverage:** Feature 1 → Tasks 1–2. Feature 2 (CSV upload) → Task 5 (upload path) using Task 3 dedup. Feature 3 (start-month) → Task 4 + Task 5 picker. Empty-state for new users (Feature 2) and all-past campaign (Feature 3) → Task 5. ✓
- **No placeholders:** every code step shows full code; commands have expected output. ✓
- **Type/name consistency:** `_campaign_last_send_date`, `_filter_new_enrollees`, `_newsletter_enroll_start_options`, `_do_enroll_contacts`, `_selected_start_step`, prefill key `start_after`, `dlg_state["start_widget"]`/`["sel_widget"]` used consistently across tasks. ✓

# Arena 4×4: J Way Newsletter Handoff — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep 4×4 contacts nurtured on "The J Way" newsletter — non-responders auto-enroll when they finish the sequence, and responders can be added manually from the responded list to an existing newsletter or a new J Way one.

**Architecture:** Four pure/near-pure helpers in `flowdrip_app.py` (a graduate gate, a J Way newsletter dict builder, a find-or-create wrapper, and a dedupe enroll worker), wired into two call sites: a manual "Add to newsletter" action on the responded/Responses list (Slice 1) and an auto-handoff hook in the send scheduler (Slice 2). The pure helpers are TDD'd; the two call sites are edits verified by import smoke plus described manual checks.

**Tech Stack:** Python 3, `pytest`, NiceGUI app (`flowdrip_app.py`).

Spec: `docs/superpowers/specs/2026-06-17-arena-4x4-jway-handoff-design.md`

---

## Existing integration points (verified)
- Enroll into a newsletter today: `enroll_contact_in_evergreen(contact, camp)` (~L21615) does `camp.setdefault("contacts", []).append(contact)` then `camp["contact_count"] = len([c for c in camp["contacts"] if not c.get("removed")])`. Contact dict shape: `{"Email":..., "FirstName":..., "LastName":...}`.
- Newsletter dict shape + monthly schedule: built inline in `_create_newsletter_dialog` (~L22259-22319) using `_monthly_same_day(count, start_from)` -> list of `date`. J Way flag: `newsletter_style == "j_way"`, plus `market_analysis=True`.
- Scheduler mark-sent: `_server_scheduler_tick` (~L51877-51883) sets `item["status"]="sent"`. Queue items carry `campaign` (name) and `_step_idx` (0-based).
- Loaders: `load_campaigns()` (~L4483), `save_campaign(camp)` (~L4566), `load_responded()` (~L5046), `load_dnc()` (~L5265) / `is_on_dnc(email)` (~L5318), `load_config()` (~L7897).

## File Structure
- Modify: `flowdrip_app.py`
  - Add 4 helpers near the other campaign helpers (after `save_campaign`, ~L4600): `_is_4x4_graduate`, `_build_jway_handoff_newsletter`, `_get_or_create_jway_handoff_newsletter`, `_enroll_contact_in_newsletter`.
  - Slice 1 call site: "Add to newsletter" action on the responded list in `p_responses` (~L13797 / near the existing responder-enroll at ~L21530).
  - Slice 2 call site: auto-handoff in `_server_scheduler_tick` right after mark-sent (~L51883).
- Test: `tests/test_arena_4x4_handoff.py` (new)

---

# SLICE 1 — pure helpers + manual responder path

## Task 1: `_is_4x4_graduate` — the auto-path gate

**Files:**
- Modify: `flowdrip_app.py` (after `save_campaign`, ~L4600)
- Test: `tests/test_arena_4x4_handoff.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_arena_4x4_handoff.py`:

```python
"""4x4 -> J Way newsletter handoff helpers.

Spec: docs/superpowers/specs/2026-06-17-arena-4x4-jway-handoff-design.md
Plan: docs/superpowers/plans/2026-06-17-arena-4x4-jway-handoff.md
"""
import flowdrip_app as fa


CAMP_4X4 = {"name": "Acme 4x4", "aicb_camp_type": "fourbyfour"}
CAMP_OTHER = {"name": "Acme Blitz", "aicb_camp_type": "blitz"}


def _gate(camp, email, responded=(), enrolled=(), dnc=()):
    return fa._is_4x4_graduate(
        {"Email": email}, camp,
        responded_emails=set(responded),
        enrolled_emails=set(enrolled),
        dnc_emails=set(dnc),
    )


def test_clean_non_responder_is_a_graduate():
    assert _gate(CAMP_4X4, "ceo@acme.com") is True


def test_responder_excluded():
    assert _gate(CAMP_4X4, "ceo@acme.com",
                 responded=["ceo@acme.com"]) is False


def test_already_enrolled_excluded():
    assert _gate(CAMP_4X4, "ceo@acme.com",
                 enrolled=["ceo@acme.com"]) is False


def test_dnc_excluded():
    assert _gate(CAMP_4X4, "ceo@acme.com", dnc=["ceo@acme.com"]) is False


def test_non_4x4_campaign_excluded():
    assert _gate(CAMP_OTHER, "ceo@acme.com") is False


def test_matching_is_case_insensitive():
    assert _gate(CAMP_4X4, "CEO@Acme.com",
                 responded=["ceo@acme.com"]) is False


def test_blank_email_excluded():
    assert _gate(CAMP_4X4, "") is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_arena_4x4_handoff.py -q`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_is_4x4_graduate'`

- [ ] **Step 3: Implement `_is_4x4_graduate`**

Add after `save_campaign` (~L4600):

```python
def _is_4x4_graduate(contact, camp, responded_emails, enrolled_emails,
                     dnc_emails):
    """True only when a contact should be AUTO-enrolled in the J Way
    handoff newsletter: the campaign is a 4x4, and the contact replied to
    nothing, is not on the DNC list, and is not already enrolled.

    The three *_emails args are sets of lowercased email strings (the
    caller pre-loads responded.json / DNC / the newsletter's contacts so
    this stays a pure, testable function).
    """
    if (camp or {}).get("aicb_camp_type", "").strip() != "fourbyfour":
        return False
    email = str((contact or {}).get("Email")
                or (contact or {}).get("email") or "").strip().lower()
    if not email:
        return False
    if email in responded_emails:
        return False
    if email in dnc_emails:
        return False
    if email in enrolled_emails:
        return False
    return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_arena_4x4_handoff.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_arena_4x4_handoff.py flowdrip_app.py
git commit -m "feat(4x4): add _is_4x4_graduate handoff gate"
```

---

## Task 2: `_build_jway_handoff_newsletter` — pure newsletter dict builder

**Files:**
- Modify: `flowdrip_app.py` (after `_is_4x4_graduate`)
- Test: `tests/test_arena_4x4_handoff.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_arena_4x4_handoff.py`:

```python
import datetime as _dt


def test_build_jway_newsletter_has_required_keys():
    camp = fa._build_jway_handoff_newsletter(
        name="Acme J Way Note", sector="construction",
        region="Phoenix, AZ", niche="", start_from=_dt.date(2026, 7, 1),
        count=12)
    assert camp["newsletter_style"] == "j_way"
    assert camp["market_analysis"] is True
    assert camp["name"] == "Acme J Way Note"
    assert camp["market_sector"] == "construction"
    assert camp["market_region"] == "Phoenix, AZ"
    assert camp["template_key"] == "evergreen"
    assert camp["status"] == "active"
    assert camp["contacts"] == []
    assert camp["contact_count"] == 0
    assert camp.get("handoff_default") is True


def test_build_jway_newsletter_makes_monthly_emails():
    camp = fa._build_jway_handoff_newsletter(
        name="N", sector="s", region="r", niche="", count=3,
        start_from=_dt.date(2026, 7, 1))
    assert len(camp["emails"]) == 3
    for em in camp["emails"]:
        assert em["step_type"] == "email_auto"
        assert em["fixed_date"]          # ISO date string present
        assert em["body"] == ""          # filled by auto-refresh before send
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_arena_4x4_handoff.py -k jway_newsletter -q`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_build_jway_handoff_newsletter'`

- [ ] **Step 3: Implement `_build_jway_handoff_newsletter`**

Add after `_is_4x4_graduate`. Mirrors the dict built in `_create_newsletter_dialog` (~L22287) but headless and tagged `handoff_default=True`:

```python
def _build_jway_handoff_newsletter(name, sector, region, niche,
                                   start_from, count=12):
    """Build a valid J Way newsletter campaign dict (no disk write).

    Mirrors the dict assembled in _create_newsletter_dialog but headless,
    tagged handoff_default=True so the auto path can find it again. Emails
    are empty monthly placeholders; the auto-refresh scheduler fills each
    issue's body before it sends.
    """
    count = max(1, min(60, int(count)))
    sends = _monthly_same_day(count, start_from)
    emails = []
    for td in sends:
        month_label = td.strftime("%B %Y")
        emails.append({
            "name": f"{month_label} {name}",
            "subject": f"{name} {month_label}",
            "body": "",
            "fixed_date": td.isoformat(),
            "delay_days": 0,
            "time": "9:00 AM",
            "step_type": "email_auto",
        })
    return dict(
        schema=2,
        name=name,
        template_key="evergreen",
        template_name="Slow Drip",
        evergreen_only=True,
        market_analysis=True,
        newsletter_name=name,
        newsletter_style="j_way",
        newsletter_candidates=[],
        market_sector=sector,
        market_niche=niche,
        market_region=region,
        newsletter_spotlight_count=3,
        newsletter_spotlight_recommendations="",
        newsletter_show_city_life=False,
        start_date=start_from.isoformat(),
        contacts=[],
        contact_count=0,
        emails=emails,
        variables={},
        status="active",
        responders=[],
        created_date=start_from.isoformat(),
        handoff_default=True,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_arena_4x4_handoff.py -k jway_newsletter -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_arena_4x4_handoff.py flowdrip_app.py
git commit -m "feat(4x4): add _build_jway_handoff_newsletter dict builder"
```

---

## Task 3: `_enroll_contact_in_newsletter` — dedupe enroll worker

**Files:**
- Modify: `flowdrip_app.py` (after `_build_jway_handoff_newsletter`)
- Test: `tests/test_arena_4x4_handoff.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_arena_4x4_handoff.py`:

```python
def test_enroll_adds_new_contact():
    camp = {"contacts": []}
    added = fa._enroll_contact_in_newsletter(
        camp, {"Email": "ceo@acme.com", "FirstName": "Dana"})
    assert added is True
    assert camp["contact_count"] == 1
    assert camp["contacts"][0]["Email"] == "ceo@acme.com"


def test_enroll_dedupes_existing_contact():
    camp = {"contacts": [{"Email": "ceo@acme.com"}], "contact_count": 1}
    added = fa._enroll_contact_in_newsletter(
        camp, {"Email": "CEO@acme.com", "FirstName": "Dana"})
    assert added is False
    assert camp["contact_count"] == 1
    assert len(camp["contacts"]) == 1


def test_enroll_blank_email_is_noop():
    camp = {"contacts": []}
    assert fa._enroll_contact_in_newsletter(camp, {"Email": ""}) is False
    assert camp["contacts"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_arena_4x4_handoff.py -k enroll -q`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_enroll_contact_in_newsletter'`

- [ ] **Step 3: Implement `_enroll_contact_in_newsletter`**

Add after `_build_jway_handoff_newsletter`. Mirrors the append at ~L21615 but dedupes first and writes no disk (callers `save_campaign`):

```python
def _enroll_contact_in_newsletter(newsletter_camp, contact):
    """Add `contact` to `newsletter_camp['contacts']`, deduped by email
    (case-insensitive, checking both 'Email' and 'email' keys). Updates
    contact_count. Returns True if added, False if blank or already there.
    Mutates the dict in place; the caller is responsible for save_campaign.
    """
    def _em(c):
        return str((c or {}).get("Email") or (c or {}).get("email")
                   or "").strip().lower()

    email = _em(contact)
    if not email:
        return False
    contacts = newsletter_camp.setdefault("contacts", [])
    if any(_em(c) == email for c in contacts):
        return False
    contacts.append(contact)
    newsletter_camp["contact_count"] = len(
        [c for c in contacts if not c.get("removed")])
    return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_arena_4x4_handoff.py -k enroll -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_arena_4x4_handoff.py flowdrip_app.py
git commit -m "feat(4x4): add _enroll_contact_in_newsletter dedupe worker"
```

---

## Task 4: `_get_or_create_jway_handoff_newsletter` — find-or-create wrapper

**Files:**
- Modify: `flowdrip_app.py` (after `_enroll_contact_in_newsletter`)

This wrapper does disk I/O (`load_campaigns` / `save_campaign`) so it is not
unit-tested directly; its pure core (`_build_jway_handoff_newsletter`) is
already covered by Task 2. Verified by import smoke.

- [ ] **Step 1: Implement the wrapper**

Add after `_enroll_contact_in_newsletter`:

```python
def _get_or_create_jway_handoff_newsletter():
    """Return the designated J Way handoff newsletter, creating it if it
    does not exist. Identified by handoff_default=True. Seeds sector/region
    from the user's saved config. Returns the campaign dict (already saved
    when freshly created).
    """
    for c in load_campaigns():
        if c.get("handoff_default") and (
                c.get("newsletter_style") or "").strip() == "j_way":
            return c
    cfg = load_config()
    sector = (cfg.get("company_industry") or cfg.get("market_sector")
              or "the market").strip() or "the market"
    region = (cfg.get("market_region") or cfg.get("company_address")
              or "the United States").strip() or "the United States"
    company = (cfg.get("company_name") or "Our").strip() or "Our"
    name = f"{company} Market Note"
    # Avoid clashing with an existing campaign name.
    existing = {c.get("name", "") for c in load_campaigns()}
    if name in existing:
        name = f"{name} (Handoff)"
    camp = _build_jway_handoff_newsletter(
        name=name, sector=sector, region=region, niche="",
        start_from=date.today(), count=12)
    save_campaign(camp)
    return camp
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `python -c "import flowdrip_app; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(4x4): add _get_or_create_jway_handoff_newsletter wrapper"
```

---

## Task 5: Manual path — "Add to newsletter" on the responded list

**Files:**
- Modify: `flowdrip_app.py` (responded list in `p_responses`, ~L13797; reuse the enroll dialog pattern at `_offer_slow_drip_enroll` ~L21530)

The responded list already renders each responder. Add a per-row "Add to
newsletter" button that opens a small picker: every existing newsletter
(campaigns with `market_analysis=True`) plus a "New J Way note" option.
Existing choice -> `enroll_contact_in_evergreen`; New choice ->
`_get_or_create_jway_handoff_newsletter` then `_enroll_contact_in_newsletter`
+ `save_campaign`.

- [ ] **Step 1: Add the picker helper**

Add near `_offer_slow_drip_enroll` (~L21530):

```python
def _offer_newsletter_enroll(to_email, name):
    """Per-contact picker (used from the responded list): add this person
    to an existing newsletter, or to a new J Way handoff note."""
    contact = {"Email": to_email,
               "FirstName": (name or "").split()[0] if name else "",
               "LastName": " ".join((name or "").split()[1:]) if name else ""}
    newsletters = [c for c in load_campaigns() if c.get("market_analysis")]

    with ui.dialog() as dlg, ui.card():
        ui.label("Add to newsletter").style("font-weight:600;")
        opts = {c["name"]: c["name"] for c in newsletters}
        opts["__new_jway__"] = "✍️ New J Way note"
        sel = ui.select(options=opts,
                        value=next(iter(opts), "__new_jway__")).style(
            "min-width:260px;")

        def _do():
            pick = sel.value
            if pick == "__new_jway__":
                camp = _get_or_create_jway_handoff_newsletter()
            else:
                camp = next((c for c in load_campaigns()
                             if c.get("name") == pick), None)
            if not camp:
                ui.notify("Newsletter not found.", type="warning"); return
            added = _enroll_contact_in_newsletter(camp, contact)
            if added:
                save_campaign(camp)
                ui.notify(f"Added {to_email} to {camp['name']}.",
                          type="positive")
            else:
                ui.notify(f"{to_email} is already on {camp['name']}.",
                          type="info")
            dlg.close()

        with ui.row():
            ui.button("Add", on_click=_do).props("color=primary")
            ui.button("Cancel", on_click=dlg.close).props("flat")
    dlg.open()
```

- [ ] **Step 2: Wire a button into the responded list**

In `p_responses` (~L13797), inside the per-responder row rendering, add an
"Add to newsletter" button alongside the existing actions. Use the
responder's email and name fields already in scope for that row (the row
builds them from the responded entry; match the existing variable names,
e.g. `_email` / `_name`):

```python
                            ui.button(
                                "Add to newsletter",
                                on_click=lambda e=None, em=_email, nm=_name:
                                    _offer_newsletter_enroll(em, nm)).props(
                                "flat dense").style("font-size:12px;")
```

- [ ] **Step 3: Verify the module imports cleanly**

Run: `python -c "import flowdrip_app; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Run the full handoff test file**

Run: `python -m pytest tests/test_arena_4x4_handoff.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: Manual verification (described)**

Deploy, open the Responses page, click "Add to newsletter" on a responder,
pick an existing newsletter or "New J Way note", confirm the toast and that
the contact appears on that newsletter's enrolled list.

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(4x4): manual 'Add to newsletter' from the responded list"
```

---

# SLICE 2 — auto handoff in the scheduler

## Task 6: Auto-enroll non-responders when the last 4×4 email sends

**Files:**
- Modify: `flowdrip_app.py` (`_server_scheduler_tick` ~L51877-51883; add `_maybe_handoff_4x4_graduate` near the other helpers ~L4600)

- [ ] **Step 1: Add the auto-handoff helper**

Add after `_get_or_create_jway_handoff_newsletter`:

```python
def _maybe_handoff_4x4_graduate(item):
    """Called right after a queue email is marked sent. If the item was the
    FINAL email step of a 4x4 campaign and the recipient is a clean
    non-responder, auto-enroll them in the J Way handoff newsletter.

    Best-effort: any failure is logged and swallowed so it never blocks
    the scheduler.
    """
    try:
        camp = next((c for c in load_campaigns()
                     if c.get("name") == item.get("campaign")), None)
        if not camp or camp.get("aicb_camp_type", "") != "fourbyfour":
            return
        emails = camp.get("emails") or []
        if not emails:
            return
        # Only on the final email step of the sequence.
        if int(item.get("_step_idx", -1)) != len(emails) - 1:
            return
        to_email = str(item.get("to") or "").strip()
        if not to_email:
            return
        responded = {str(x.get("email", "")).strip().lower()
                     for x in load_responded()}
        dnc = {str(e).strip().lower() for e in load_dnc()}
        nl = _get_or_create_jway_handoff_newsletter()
        enrolled = {str((c.get("Email") or c.get("email") or "")).strip().lower()
                    for c in (nl.get("contacts") or [])}
        contact = {"Email": to_email, "FirstName": "", "LastName": ""}
        if not _is_4x4_graduate(contact, camp, responded, enrolled, dnc):
            return
        if _enroll_contact_in_newsletter(nl, contact):
            save_campaign(nl)
            print(f"[4x4Handoff] enrolled {to_email} in {nl['name']}",
                  flush=True)
    except Exception as ex:
        print(f"[4x4Handoff] failed: {ex}", flush=True)
```

- [ ] **Step 2: Call it from the scheduler after mark-sent**

In `_server_scheduler_tick` (~L51881), find:
```python
                if ok:
                    item["status"] = "sent"
                    item["sent_at"] = datetime.now().isoformat()
                    total_sent += 1
```
Replace with:
```python
                if ok:
                    item["status"] = "sent"
                    item["sent_at"] = datetime.now().isoformat()
                    total_sent += 1
                    _maybe_handoff_4x4_graduate(item)
```

- [ ] **Step 3: Verify the module imports cleanly**

Run: `python -c "import flowdrip_app; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Run the full handoff test file**

Run: `python -m pytest tests/test_arena_4x4_handoff.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(4x4): auto-enroll non-responders in J Way newsletter on completion"
```

---

## Final verification

- [ ] **Run all 4×4 test files + a neighbor**

Run: `python -m pytest tests/test_arena_4x4_handoff.py tests/test_arena_4x4_cited_stats.py tests/test_arena_4x4_voice.py tests/test_sb_helpers.py -q`
Expected: all PASS.

- [ ] **Import smoke**

Run: `python -c "import flowdrip_app; print('ok')"`
Expected: `ok`

---

## Self-Review (completed by plan author)

- **Spec coverage:** Path A auto gate -> Task 1; J Way builder (zero-config target) -> Task 2; dedupe enroll -> Task 3; find-or-create -> Task 4; Path B manual picker (existing-or-new) -> Task 5; scheduler completion hook -> Task 6. Guards (non-responder/DNC/dedupe) live in Tasks 1+3 and are applied in Task 6. Error handling (swallow + log) in Tasks 4+6. Build order matches the spec's two slices. All spec sections mapped.
- **Verified-fact note:** queue-item key for the recipient is `to`, campaign name is `campaign`, step index is `_step_idx`; newsletter enrolled list is `contacts` with `contact_count`; these were confirmed by reconnaissance before writing.
- **Placeholder scan:** none; every code step shows complete code. The two UI/scheduler edits (Tasks 5 Step 2, 6 Step 2) reference existing in-scope variables (`_email`/`_name` in the responded row; the `if ok:` block in the scheduler) and are verified by import smoke + described manual check rather than unit tests, consistent with the codebase keeping logic in pure helpers.
- **Type consistency:** `_is_4x4_graduate(contact, camp, responded_emails, enrolled_emails, dnc_emails)`, `_build_jway_handoff_newsletter(name, sector, region, niche, start_from, count)`, `_enroll_contact_in_newsletter(newsletter_camp, contact) -> bool`, `_get_or_create_jway_handoff_newsletter()`, `_maybe_handoff_4x4_graduate(item)` referenced identically across tasks.

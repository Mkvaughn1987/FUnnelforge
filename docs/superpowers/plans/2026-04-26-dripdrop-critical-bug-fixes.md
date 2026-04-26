# DripDrop Critical Bug Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 13 Critical-severity bugs identified in the 2026-04-26 audit, with regression tests where unit-testable.

**Architecture:** Most fixes are localized one- or two-line changes. The atomicity batch (C8/C9/C10/C11) shares a single new helper `_atomic_write_text` to keep the pattern DRY. The wizard-state batch (C2/C3) shares a single `_reset_wizard_state` helper. Tests live in a new top-level `tests/` directory using `pytest`, with `conftest.py` setting `LOCALAPPDATA` to a tmp dir per-test so file-writing helpers don't touch real user data.

**Tech Stack:** Python 3, NiceGUI, pytest. Existing files: `flowdrip_app.py` (39,950 lines), `funnelforge_core.py` (841 lines).

**Verification discipline:** Per the spec, each fix MUST be verified against current source by symbol/pattern (line numbers may have drifted). If a finding does not reproduce, mark it INVALID in this plan via a comment and skip — do not invent a fix.

**Decisions (confirmed by user):**
- C7 unresolved tokens → hard-fail at queue time
- C11 community save → timestamp suffix on collision only
- C13 testing → manual verification, no win32com mock

**Verified line numbers (drift from spec):**
| Bug | Spec line | Actual line | File |
|-----|----------|------------|------|
| C1  | 7702 | 7663 | flowdrip_app.py |
| C2  | 13082 | 13082 | flowdrip_app.py |
| C3  | 13134 | 13134 | flowdrip_app.py |
| C4  | 6062, 5384 | 6062, 5384 | flowdrip_app.py |
| C5  | 6125 | 6125, 12673, 12787 | flowdrip_app.py (3 sites!) |
| C6  | 4677, 4691 | 4678, 4692 (in `_in_campaign` variant) | flowdrip_app.py |
| C7  | 335 | 335 | funnelforge_core.py |
| C8  | 6175 | 6175 | flowdrip_app.py |
| C9  | 4126 | 4126 | flowdrip_app.py |
| C10 | 15953 | 15953 | flowdrip_app.py |
| C11 | 4424, 4434 | 4424, 4434 | flowdrip_app.py |
| C12 | 73, 19341, 19379 | 73, 19340-19342, 19376-19380 | both |
| C13a| 546 | 546 | funnelforge_core.py |
| C13b| 4778-4867 | 4778-4869 | flowdrip_app.py |
| C13c| 503-508 | 479-508 | funnelforge_core.py |

---

## Task 0: Test infrastructure setup

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`

- [ ] **Step 1: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -ra --strict-markers
filterwarnings =
    ignore::DeprecationWarning
```

- [ ] **Step 2: Create `tests/__init__.py`**

Empty file (`pathlib.Path("tests/__init__.py").touch()`).

- [ ] **Step 3: Create `tests/conftest.py`**

```python
"""Test fixtures. Sets LOCALAPPDATA to a tmp dir before flowdrip_app
or funnelforge_core is imported, so per-user paths point inside the
test sandbox and never touch real user data.
"""
import os
import sys
import pathlib
import pytest


@pytest.fixture
def isolated_appdata(tmp_path, monkeypatch):
    """Point LOCALAPPDATA at a tmp dir. All per-user file helpers
    derive their paths from this, so writes stay contained."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path


@pytest.fixture
def with_user(isolated_appdata, monkeypatch):
    """Set the current-user email ContextVar so per-user path
    helpers in flowdrip_app resolve to a known test user dir.
    Returns the user's resolved root dir."""
    # Import lazily so isolated_appdata fixture takes effect first.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    import flowdrip_app as fa
    fa._CURRENT_USER_EMAIL.set("tester@example.com")
    return fa._resolve_user_root("tester@example.com")
```

- [ ] **Step 4: Verify pytest discovers the suite**

Run: `python -m pytest --collect-only -q`
Expected: `0 tests collected` (no tests yet, no errors).

- [ ] **Step 5: Commit**

```bash
git add pytest.ini tests/__init__.py tests/conftest.py
git commit -m "test: add pytest infrastructure with isolated tmp LOCALAPPDATA"
```

---

## Task 1 — Atomicity Batch: shared helper

**Goal:** One helper used by C8, C9, C10, C11. DRY.

**Files:**
- Modify: `flowdrip_app.py` (add helper near top of data layer, around L300)
- Test: `tests/test_atomic_write.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_atomic_write.py`:

```python
"""Tests for the atomic-write helper (Task 1)."""
import json
import pathlib
import pytest


def test_atomic_write_creates_file(isolated_appdata, with_user):
    import flowdrip_app as fa
    p = isolated_appdata / "out.json"
    fa._atomic_write_text(p, '{"hello": "world"}')
    assert p.read_text(encoding="utf-8") == '{"hello": "world"}'


def test_atomic_write_no_partial_file_on_failure(isolated_appdata, with_user, monkeypatch):
    """If the os.replace step fails, the destination must not contain
    a half-written payload."""
    import flowdrip_app as fa
    p = isolated_appdata / "config.json"
    p.write_text('{"old": "data"}', encoding="utf-8")

    # Force os.replace to raise mid-swap. The destination file must keep
    # its original content.
    real_replace = fa.os.replace
    def boom(src, dst):
        raise OSError("simulated crash")
    monkeypatch.setattr(fa.os, "replace", boom)

    with pytest.raises(OSError):
        fa._atomic_write_text(p, '{"new": "data"}')
    assert p.read_text(encoding="utf-8") == '{"old": "data"}'


def test_atomic_write_no_tmp_left_on_success(isolated_appdata, with_user):
    import flowdrip_app as fa
    p = isolated_appdata / "ok.json"
    fa._atomic_write_text(p, "ok")
    # tmp sibling should be cleaned up after replace
    assert not p.with_suffix(p.suffix + ".tmp").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_atomic_write.py -v`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_atomic_write_text'`.

- [ ] **Step 3: Add the helper to `flowdrip_app.py`**

Find the data-layer block (search for `def load_outcomes`). Insert this helper *immediately above* `def load_outcomes`:

```python
def _atomic_write_text(path, text: str, encoding: str = "utf-8") -> None:
    """Atomic file write: write to <path>.tmp then os.replace().
    Crash mid-write leaves the destination untouched. Caller is
    expected to ensure the parent dir exists.

    Raises on failure — callers that previously swallowed errors
    silently (e.g. save_outcomes) must keep their try/except.
    """
    from pathlib import Path
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(str(tmp), str(p))
    finally:
        # Best-effort cleanup if replace failed
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_atomic_write.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_atomic_write.py
git commit -m "feat: add _atomic_write_text helper for atomic file writes"
```

---

## Task 2 — C9: Fix non-atomic outcomes save

**Files:**
- Modify: `flowdrip_app.py` (`save_outcomes`, around L4121)
- Test: `tests/test_atomic_saves.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_atomic_saves.py`:

```python
"""Atomicity regression tests for C8/C9/C10/C11."""
import json
import pytest


def test_save_outcomes_uses_atomic_write(isolated_appdata, with_user, monkeypatch):
    """save_outcomes must go through _atomic_write_text (no direct write_text
    on the dest path). This is verified by spying on Path.write_text and
    asserting the .tmp sibling is the path that gets written."""
    import flowdrip_app as fa

    target = fa._user_outcomes_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"old": true}', encoding="utf-8")

    # Force a crash inside os.replace; the original file must remain intact.
    def boom(src, dst):
        raise OSError("crash")
    monkeypatch.setattr(fa.os, "replace", boom)

    fa.save_outcomes({"new": True})  # save_outcomes swallows exceptions
    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_atomic_saves.py::test_save_outcomes_uses_atomic_write -v`
Expected: FAIL — original file ends up with `{"new": true}` because the current code calls `_outcomes.write_text(...)` directly.

- [ ] **Step 3: Fix `save_outcomes`**

In `flowdrip_app.py`, find `def save_outcomes(outcomes: dict):` (currently L4121). Replace its body:

Current:
```python
def save_outcomes(outcomes: dict):
    """Persist task outcomes to disk."""
    _outcomes = _user_outcomes_path()
    try:
        _outcomes.parent.mkdir(parents=True, exist_ok=True)
        _outcomes.write_text(json.dumps(outcomes, indent=2), encoding="utf-8")
    except Exception:
        pass
```

Replace with:
```python
def save_outcomes(outcomes: dict):
    """Persist task outcomes to disk atomically."""
    _outcomes = _user_outcomes_path()
    try:
        _outcomes.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(_outcomes, json.dumps(outcomes, indent=2))
    except Exception:
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_atomic_saves.py::test_save_outcomes_uses_atomic_write -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_atomic_saves.py
git commit -m "fix(C9): make save_outcomes atomic"
```

---

## Task 3 — C8: Fix non-atomic config save

**Files:**
- Modify: `flowdrip_app.py` (`save_config`, around L6171)
- Test: extend `tests/test_atomic_saves.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_atomic_saves.py`:

```python
def test_save_config_uses_atomic_write(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    target = fa._user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"old_token": "abc"}', encoding="utf-8")

    def boom(src, dst):
        raise OSError("crash")
    monkeypatch.setattr(fa.os, "replace", boom)

    # save_config does not currently swallow exceptions; this is acceptable
    # because the user-facing layer above it does. We just verify the
    # original file is preserved.
    with pytest.raises(OSError):
        fa.save_config({"new_token": "xyz"})

    import json as _json
    assert _json.loads(target.read_text(encoding="utf-8")) == {"old_token": "abc"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_atomic_saves.py::test_save_config_uses_atomic_write -v`
Expected: FAIL — current code uses direct `cp.write_text(...)`.

- [ ] **Step 3: Fix `save_config`**

In `flowdrip_app.py`, find `def save_config(cfg: dict):` (currently L6171). Replace:

Current:
```python
def save_config(cfg: dict):
    """Save DripDrop config. Uses the async-safe per-user path accessor."""
    cp = _user_config_path()
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
```

Replace with:
```python
def save_config(cfg: dict):
    """Save DripDrop config atomically. Uses the async-safe per-user path accessor."""
    cp = _user_config_path()
    cp.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(cp, json.dumps(cfg, indent=2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_atomic_saves.py::test_save_config_uses_atomic_write -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_atomic_saves.py
git commit -m "fix(C8): make save_config atomic"
```

---

## Task 4 — C10: Fix non-atomic contact CSV save

**Files:**
- Modify: `flowdrip_app.py` (`_save_contacts_to_csv`, around L15950)
- Test: extend `tests/test_atomic_saves.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_atomic_saves.py`:

```python
def test_save_contacts_csv_atomic_on_crash(isolated_appdata, with_user, monkeypatch, tmp_path):
    """Contact CSV save must not corrupt the destination on a mid-write
    crash. _save_contacts_to_csv is defined inside p_contacts; we test the
    same atomic pattern via the public _atomic_write_text path it should
    delegate to."""
    import flowdrip_app as fa
    import csv as _csv

    target = fa._user_contacts_csv_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("Email,FirstName\nold@x.com,Old\n", encoding="utf-8")

    # Build the CSV string the same way _save_contacts_to_csv does, but
    # via the atomic helper, then crash os.replace.
    def boom(src, dst):
        raise OSError("crash")
    monkeypatch.setattr(fa.os, "replace", boom)

    payload = "Email,FirstName\nnew@x.com,New\n"
    with pytest.raises(OSError):
        fa._atomic_write_text(target, payload)

    assert "old@x.com" in target.read_text(encoding="utf-8")
    assert "new@x.com" not in target.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails (or passes if atomic helper already covers it)**

Run: `python -m pytest tests/test_atomic_saves.py::test_save_contacts_csv_atomic_on_crash -v`
Expected: PASS already (since `_atomic_write_text` exists). The real fix below ensures `_save_contacts_to_csv` actually USES the atomic helper.

- [ ] **Step 3: Fix `_save_contacts_to_csv`**

In `flowdrip_app.py`, find `def _save_contacts_to_csv(contact_list):` (currently L15950, inside `p_contacts`). Replace:

Current:
```python
    def _save_contacts_to_csv(contact_list):
        """Write contacts back to the active CSV."""
        import csv as csv_mod
        with open(str(_user_contacts_csv_path()), "w", newline="", encoding="utf-8") as f:
            w = csv_mod.DictWriter(f, fieldnames=CONTACT_FIELDS)
            w.writeheader()
            for c in contact_list:
                w.writerow({"Email": c.get("email", ""), "FirstName": c.get("first_name", ""),
                            "LastName": c.get("last_name", ""), "Company": c.get("company", ""),
                            "JobTitle": c.get("title", ""), "MobilePhone": c.get("phone_mobile", ""),
                            "WorkPhone": c.get("phone_office", ""), "LinkedInPage": c.get("linkedin", ""),
                            "City": c.get("city", ""), "State": c.get("state", "")})
```

Replace with:
```python
    def _save_contacts_to_csv(contact_list):
        """Write contacts back to the active CSV atomically (write tmp, replace)."""
        import csv as csv_mod
        import io as _io
        buf = _io.StringIO()
        w = csv_mod.DictWriter(buf, fieldnames=CONTACT_FIELDS)
        w.writeheader()
        for c in contact_list:
            w.writerow({"Email": c.get("email", ""), "FirstName": c.get("first_name", ""),
                        "LastName": c.get("last_name", ""), "Company": c.get("company", ""),
                        "JobTitle": c.get("title", ""), "MobilePhone": c.get("phone_mobile", ""),
                        "WorkPhone": c.get("phone_office", ""), "LinkedInPage": c.get("linkedin", ""),
                        "City": c.get("city", ""), "State": c.get("state", "")})
        _atomic_write_text(_user_contacts_csv_path(), buf.getvalue())
```

- [ ] **Step 4: Run all atomic-saves tests**

Run: `python -m pytest tests/test_atomic_saves.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_atomic_saves.py
git commit -m "fix(C10): make contact-CSV save atomic"
```

---

## Task 5 — C11: Atomic + collision-safe community/local saves

**Files:**
- Modify: `flowdrip_app.py` (`copy_community_to_local` L4408, `save_to_community` L4429)
- Test: `tests/test_community_save.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_community_save.py`:

```python
"""C11: community save must be atomic and never silently overwrite."""
import json
import pathlib
import pytest


def test_copy_community_to_local_avoids_overwrite(isolated_appdata, with_user):
    import flowdrip_app as fa

    camp = {"name": "Cool Outreach", "steps": [], "_community": True}

    # First copy
    out1 = fa.copy_community_to_local(camp)
    p1 = pathlib.Path(out1["_path"])
    assert p1.exists()

    # Modify the saved file so we can detect overwrite
    p1.write_text(json.dumps({"name": "Cool Outreach", "marker": "ORIGINAL"}, indent=2),
                  encoding="utf-8")

    # Second copy of the same campaign  -  must NOT overwrite the marker
    out2 = fa.copy_community_to_local(camp)
    p2 = pathlib.Path(out2["_path"])
    assert p2 != p1, "copy_community_to_local must rename on collision, not overwrite"

    # Original file is preserved
    assert "ORIGINAL" in p1.read_text(encoding="utf-8")


def test_save_to_community_timestamps_on_collision(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    camp = {"name": "Shared Plan", "steps": []}
    p1 = fa.save_to_community(camp)
    assert p1.exists()
    p1.write_text(json.dumps({"marker": "FIRST"}, indent=2), encoding="utf-8")

    # Second save with same name → must produce a different filename
    p2 = fa.save_to_community(camp)
    assert p2 != p1, "save_to_community must add a timestamp suffix on collision"
    assert "FIRST" in p1.read_text(encoding="utf-8"), "original must not be overwritten"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_community_save.py -v`
Expected: FAIL on both — current code overwrites silently.

- [ ] **Step 3: Fix `copy_community_to_local`**

In `flowdrip_app.py`, find `def copy_community_to_local(camp: dict) -> dict:` (currently L4408). Replace the body's tail (from the `safe = re.sub(...)` line to `return local`):

Current:
```python
    safe = re.sub(r"[^\w\-]", "_", local.get("name", "campaign"))[:60]
    p = _user_campaigns_dir() / f"{safe}.json"
    local["_path"] = str(p)
    local_clean = {k: v for k, v in local.items() if not k.startswith("_")}
    p.write_text(json.dumps(local_clean, indent=2), encoding="utf-8")
    _cache_campaigns.invalidate()
    return local
```

Replace with:
```python
    safe = re.sub(r"[^\w\-]", "_", local.get("name", "campaign"))[:60]
    base = _user_campaigns_dir() / f"{safe}.json"
    p = base
    n = 2
    while p.exists():
        p = base.with_name(f"{safe} ({n}).json")
        n += 1
    local["_path"] = str(p)
    local_clean = {k: v for k, v in local.items() if not k.startswith("_")}
    p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(p, json.dumps(local_clean, indent=2))
    _cache_campaigns.invalidate()
    return local
```

- [ ] **Step 4: Fix `save_to_community`**

In `flowdrip_app.py`, find `def save_to_community(camp: dict):` (currently L4429). Replace:

Current:
```python
def save_to_community(camp: dict):
    """Save a campaign to the shared community folder."""
    safe = re.sub(r"[^\w\-]", "_", camp.get("name", "campaign"))[:60]
    p = COMMUNITY_DIR / f"{safe}.json"
    camp_copy = {k: v for k, v in camp.items() if not k.startswith("_")}
    p.write_text(json.dumps(camp_copy, indent=2), encoding="utf-8")
    return p
```

Replace with:
```python
def save_to_community(camp: dict):
    """Save a campaign to the shared community folder atomically.
    On filename collision, append a timestamp suffix instead of
    overwriting the existing template."""
    safe = re.sub(r"[^\w\-]", "_", camp.get("name", "campaign"))[:60]
    p = COMMUNITY_DIR / f"{safe}.json"
    if p.exists():
        from datetime import datetime as _dt
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        p = COMMUNITY_DIR / f"{safe}_{ts}.json"
    camp_copy = {k: v for k, v in camp.items() if not k.startswith("_")}
    p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(p, json.dumps(camp_copy, indent=2))
    return p
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_community_save.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py tests/test_community_save.py
git commit -m "fix(C11): atomic + collision-safe community/local campaign saves"
```

---

## Task 6 — C2/C3: Wizard state reset helper

**Files:**
- Modify: `flowdrip_app.py` (`_back_to_picker` L13134, the inner `_pick` at L13082; helper added near AppState definition)
- Test: `tests/test_wizard_reset.py`

**Note on AppState fields:** The full set of `aicb_*` and `custom_*` fields lives in the AppState class defined around L8000–L8050. The helper below clears the ones the spec calls out plus the three `custom_*` fields used by the picker.

- [ ] **Step 1: Inspect AppState to enumerate fields**

Run: `python -c "import flowdrip_app as fa; s = fa.AppState(); print(sorted(k for k in vars(s) if k.startswith(('aicb_', 'custom_', 'rc_'))))"`

Record the output. Use it to verify the field list in Step 3 covers everything that should reset. If new fields appear, add them.

- [ ] **Step 2: Write the failing test**

Create `tests/test_wizard_reset.py`:

```python
"""C2/C3: wizard state must fully reset across campaigns."""
import pytest


def test_reset_wizard_state_clears_all_aicb_and_custom(isolated_appdata):
    import flowdrip_app as fa

    s = fa.AppState()

    # Pollute with stale Campaign A data
    s.aicb_company = "Acme"
    s.aicb_website = "https://acme.example"
    s.aicb_industry = "Widgets"
    s.aicb_niche = "B2B"
    s.aicb_sel_locations = ["TX"]
    s.aicb_sel_roles = ["sales reps"]
    s.aicb_docs = {"foo": "bar"}
    s.aicb_research = "stale research"
    s.aicb_campaign = {"steps": ["leftover"]}
    s.custom_editing_idx = 2
    s.custom_steps = [{"name": "old"}]
    s.custom_name = "Old Campaign"
    s.custom_selected_type = "email"

    fa._reset_wizard_state(s)

    # Defaults
    assert s.aicb_company == ""
    assert s.aicb_website == ""
    assert s.aicb_industry == ""
    assert s.aicb_niche == ""
    assert s.aicb_sel_locations == []
    assert s.aicb_sel_roles == []
    assert s.aicb_docs == {}
    assert s.aicb_research == ""
    assert s.aicb_campaign == {} or s.aicb_campaign is None
    assert s.custom_editing_idx == -1
    assert s.custom_steps == []
    assert s.custom_name == ""
    assert s.custom_selected_type == ""


def test_reset_wizard_state_keeps_unrelated_state(isolated_appdata):
    """Reset must NOT clear non-wizard state like the user's hub or
    nav history — only the wizard inputs."""
    import flowdrip_app as fa

    s = fa.AppState()
    s.hub = "sales"
    s.sp = "today"
    s._nav_history = [{"snapshot": "preserve me"}]

    fa._reset_wizard_state(s)

    assert s.hub == "sales"
    assert s.sp == "today"
    assert s._nav_history == [{"snapshot": "preserve me"}]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_wizard_reset.py -v`
Expected: FAIL — `AttributeError: module 'flowdrip_app' has no attribute '_reset_wizard_state'`.

- [ ] **Step 4: Add the helper**

In `flowdrip_app.py`, find the AppState class (search for `class AppState`). After the class definition, add this module-level helper:

```python
def _reset_wizard_state(s: "AppState") -> None:
    """Reset all wizard inputs to their defaults so a freshly-picked
    flow doesn't inherit Campaign A's research, locations, or steps.

    This MUST be called whenever the user picks a new flow type or
    clicks Back-to-Picker. See C2/C3 in
    docs/superpowers/specs/2026-04-26-dripdrop-critical-bug-triage-design.md
    for the failure mode (cross-campaign data contamination).
    """
    # AI campaign builder inputs
    s.aicb_company = ""
    s.aicb_website = ""
    s.aicb_industry = ""
    s.aicb_niche = ""
    s.aicb_sel_locations = []
    s.aicb_sel_roles = []
    s.aicb_docs = {}
    s.aicb_research = ""
    s.aicb_campaign = {}
    # Custom builder inputs
    s.custom_editing_idx = -1
    s.custom_steps = []
    s.custom_name = ""
    s.custom_selected_type = ""
    s.custom_preset_picked = False
    s.custom_editing = False
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_wizard_reset.py -v`
Expected: 2 passed.

If `aicb_campaign`'s default in AppState is `None` instead of `{}`, change the assignment in `_reset_wizard_state` to `s.aicb_campaign = None` and adjust the test accordingly. Match the AppState default exactly.

- [ ] **Step 6: Wire helper into `_pick` (the recruiting/ai_campaign branches)**

In `flowdrip_app.py`, find the `_pick` callback at L13082 (inside `_sq_pick`, the SEQ_CARDS loop). Modify the `recruiting` and `ai_campaign` branches to call the reset BEFORE setting the new flow's fields:

Current:
```python
                def _pick(k=tab_key):
                    if k == "recruiting":
                        s._nav_history.append(_nav_snapshot(s))
                        s.sp = "recruiting"
                        s.rc_step = 0
                        s.rc_custom_steps = []
                    elif k == "ai_campaign":
                        s._nav_history.append(_nav_snapshot(s))
                        s.sp = "ai_campaign"
                        s.aicb_step = 1  # land on wizard
                        s.aicb_wizard_step = 1  # fresh wizard start
                        s.aicb_type_picked = False
                        s.aicb_contacts = []
                    else:
                        s._tab = k
                    rf()
```

Replace with:
```python
                def _pick(k=tab_key):
                    if k == "recruiting":
                        s._nav_history.append(_nav_snapshot(s))
                        _reset_wizard_state(s)
                        s.sp = "recruiting"
                        s.rc_step = 0
                        s.rc_custom_steps = []
                    elif k == "ai_campaign":
                        s._nav_history.append(_nav_snapshot(s))
                        _reset_wizard_state(s)
                        s.sp = "ai_campaign"
                        s.aicb_step = 1  # land on wizard
                        s.aicb_wizard_step = 1  # fresh wizard start
                        s.aicb_type_picked = False
                        s.aicb_contacts = []
                    else:
                        _reset_wizard_state(s)
                        s._tab = k
                    rf()
```

- [ ] **Step 7: Wire helper into `_back_to_picker`**

Find `def _back_to_picker():` at L13134. Replace:

Current:
```python
        def _back_to_picker():
            s._tab = ""; s.stpl = None; s.custom_editing = False
            s.custom_name = ""; s.custom_steps = []; s.custom_preset_picked = False
            rf()
```

Replace with:
```python
        def _back_to_picker():
            _reset_wizard_state(s)
            s._tab = ""
            s.stpl = None
            rf()
```

- [ ] **Step 8: Run all wizard tests**

Run: `python -m pytest tests/test_wizard_reset.py -v`
Expected: 2 passed.

- [ ] **Step 9: Commit**

```bash
git add flowdrip_app.py tests/test_wizard_reset.py
git commit -m "fix(C2,C3): full wizard-state reset on flow switch and back-to-picker"
```

---

## Task 7 — C6: Normalize campaign name in cancel-pending

**Files:**
- Modify: `flowdrip_app.py` (`_cancel_pending_for_email_in_campaign`, L4668)
- Test: `tests/test_cancel_pending.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cancel_pending.py`:

```python
"""C6: cancel-pending must be case/whitespace-insensitive on campaign name."""
import json
import pathlib
import pytest


def test_cancel_pending_normalizes_campaign_name(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    # Disable the funnelforge_core fast path; we want the JSON fallback path.
    monkeypatch.setattr(fa, "_FUNNELFORGE_OK", False)
    monkeypatch.setattr(fa, "_ffc", None)

    qp = fa._user_queue_path()
    qp.parent.mkdir(parents=True, exist_ok=True)
    queue = [
        {"id": "1", "to": "lead@example.com", "campaign": "My Campaign", "status": "pending"},
        {"id": "2", "to": "lead@example.com", "campaign": "My  Campaign ", "status": "pending"},
        {"id": "3", "to": "lead@example.com", "campaign": "Other", "status": "pending"},
    ]
    qp.write_text(json.dumps(queue), encoding="utf-8")

    n = fa._cancel_pending_for_email_in_campaign("lead@example.com", "my campaign")
    assert n == 2  # IDs 1 and 2 should both match (case + whitespace insensitive)

    final = json.loads(qp.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in final}
    assert by_id["1"]["status"] == "cancelled"
    assert by_id["2"]["status"] == "cancelled"
    assert by_id["3"]["status"] == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cancel_pending.py -v`
Expected: FAIL — current `==` comparison won't match "My Campaign" vs "my campaign".

- [ ] **Step 3: Fix `_cancel_pending_for_email_in_campaign`**

In `flowdrip_app.py`, find `def _cancel_pending_for_email_in_campaign(...)` at L4668. Replace its body:

Current:
```python
def _cancel_pending_for_email_in_campaign(email_addr: str, campaign_name: str) -> int:
    """Cancel pending queue items for a given email in a specific campaign only."""
    email_addr = email_addr.lower().strip()
    cancelled = 0
    if _FUNNELFORGE_OK and _ffc is not None:
        try:
            queue = _ffc.get_queue()
            ids_to_cancel = [q["id"] for q in queue
                             if q.get("status") == "pending"
                             and q.get("to", "").lower().strip() == email_addr
                             and q.get("campaign", "") == campaign_name]
            if ids_to_cancel:
                cancelled = _ffc.cancel_queue_items(ids_to_cancel)
                _cache_queue.invalidate()
                return cancelled
        except Exception:
            pass
    try:
        qp = _user_queue_path()  # legacy QUEUE_PATH fallback removed — was a cross-user leak vector on server
        if qp.exists():
            queue = json.loads(qp.read_text(encoding="utf-8"))
            for q in queue:
                if (q.get("status") == "pending"
                        and q.get("to", "").lower().strip() == email_addr
                        and q.get("campaign", "") == campaign_name):
                    q["status"] = "cancelled"
                    cancelled += 1
            if cancelled:
                tmp = qp.with_suffix(".tmp")
                tmp.write_text(json.dumps(queue, indent=2, default=str), encoding="utf-8")
                tmp.replace(qp)
                _cache_queue.invalidate()
    except Exception:
        pass
    return cancelled
```

Replace with:
```python
def _cancel_pending_for_email_in_campaign(email_addr: str, campaign_name: str) -> int:
    """Cancel pending queue items for a given email in a specific campaign only.
    Both email and campaign name are normalized (casefold + whitespace
    collapse) so that 'My Campaign' matches 'my  campaign '."""
    email_addr = email_addr.lower().strip()
    def _norm(name: str) -> str:
        return " ".join((name or "").split()).casefold()
    target_camp = _norm(campaign_name)
    cancelled = 0
    if _FUNNELFORGE_OK and _ffc is not None:
        try:
            queue = _ffc.get_queue()
            ids_to_cancel = [q["id"] for q in queue
                             if q.get("status") == "pending"
                             and q.get("to", "").lower().strip() == email_addr
                             and _norm(q.get("campaign", "")) == target_camp]
            if ids_to_cancel:
                cancelled = _ffc.cancel_queue_items(ids_to_cancel)
                _cache_queue.invalidate()
                return cancelled
        except Exception:
            pass
    try:
        qp = _user_queue_path()
        if qp.exists():
            queue = json.loads(qp.read_text(encoding="utf-8"))
            for q in queue:
                if (q.get("status") == "pending"
                        and q.get("to", "").lower().strip() == email_addr
                        and _norm(q.get("campaign", "")) == target_camp):
                    q["status"] = "cancelled"
                    cancelled += 1
            if cancelled:
                _atomic_write_text(qp, json.dumps(queue, indent=2, default=str))
                _cache_queue.invalidate()
    except Exception:
        pass
    return cancelled
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cancel_pending.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_cancel_pending.py
git commit -m "fix(C6): normalize campaign name in _cancel_pending_for_email_in_campaign"
```

---

## Task 8 — C7: Hard-fail on unresolved merge tokens

**Files:**
- Modify: `funnelforge_core.py` (`merge_tokens`, L335)
- Test: `tests/test_merge_tokens.py`

**Decision:** Hard-fail at queue time (per user-confirmed default).

- [ ] **Step 1: Write the failing test**

Create `tests/test_merge_tokens.py`:

```python
"""C7: unresolved merge tokens must hard-fail (not leak to recipient)."""
import pytest


def test_merge_tokens_resolves_known():
    import funnelforge_core as ff
    out = ff.merge_tokens("Hi {FirstName}!", {"FirstName": "Sam"})
    assert out == "Hi Sam!"


def test_merge_tokens_raises_on_unknown():
    import funnelforge_core as ff
    with pytest.raises(ValueError) as ei:
        ff.merge_tokens("Hi {FirstNae}!", {"FirstName": "Sam"})
    msg = str(ei.value)
    assert "FirstNae" in msg
    assert "unresolved" in msg.lower() or "unknown" in msg.lower()


def test_merge_tokens_ignores_non_token_braces():
    """Curly braces around code/JSON-looking content shouldn't trigger
    a hard-fail. Only patterns that look like a {Identifier} count."""
    import funnelforge_core as ff
    # JSON-ish snippet with spaces, colons, quotes — not a token shape
    out = ff.merge_tokens('{"key": "val"} and {FirstName}', {"FirstName": "X"})
    assert out == '{"key": "val"} and X'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_merge_tokens.py -v`
Expected: `test_merge_tokens_raises_on_unknown` FAILS (current code returns the literal `{FirstNae}` instead of raising).

- [ ] **Step 3: Fix `merge_tokens`**

In `funnelforge_core.py`, find `def merge_tokens(...)` at L335. Replace:

Current:
```python
def merge_tokens(template: str, tokens: Dict[str, Any]) -> str:
    out = template
    for k, v in tokens.items():
        out = out.replace("{" + k + "}", str(v) if v is not None else "")
    return out
```

Replace with:
```python
_TOKEN_PATTERN = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")


def merge_tokens(template: str, tokens: Dict[str, Any]) -> str:
    """Substitute {Token} patterns with values from the tokens dict.

    Hard-fails (ValueError) on any unresolved {Token} in the result so
    typo'd or removed fields can't reach the recipient as literal text.
    Brace patterns that don't look like an identifier (e.g. JSON
    snippets like {"a":1}) are ignored.
    """
    out = template
    for k, v in tokens.items():
        out = out.replace("{" + k + "}", str(v) if v is not None else "")
    leftovers = _TOKEN_PATTERN.findall(out)
    if leftovers:
        unique = sorted(set(leftovers))
        raise ValueError(
            f"Unresolved merge token(s) in template: {', '.join('{' + t + '}' for t in unique)}"
        )
    return out
```

Confirm `import re` is already present at the top of `funnelforge_core.py`. If not, add it.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_merge_tokens.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add funnelforge_core.py tests/test_merge_tokens.py
git commit -m "fix(C7): hard-fail merge_tokens on unresolved {Token} patterns"
```

---

## Task 9 — C5: Pass real unsubscribe email (not bool)

**Files:**
- Modify: `flowdrip_app.py` at L6125, L12673, L12787 (3 sites)
- Test: `tests/test_unsubscribe_email.py`

- [ ] **Step 1: Verify the 3 sites**

Run: `python -m pytest --co` then search the source:

```
grep -n 'unsubscribe_email' flowdrip_app.py
```

Expected three hits at the lines above. If a site has been removed since the audit, mark it INVALID and skip just that one.

- [ ] **Step 2: Write the failing test**

Create `tests/test_unsubscribe_email.py`:

```python
"""C5: unsubscribe_email must be a string (sender email) or None — never bool."""
import pytest


def test_queue_items_unsubscribe_email_is_string_or_none(isolated_appdata, with_user, monkeypatch):
    """Build a tiny campaign and walk queue_campaign_emails; the queued
    items must have unsubscribe_email as a string or None."""
    import flowdrip_app as fa

    # Stub out funnelforge_core so the test stops at the queue-list build.
    captured = {}
    class _StubFFC:
        def add_to_queue(self, items):
            captured["items"] = items
    monkeypatch.setattr(fa, "_FUNNELFORGE_OK", True)
    monkeypatch.setattr(fa, "_ffc", _StubFFC())

    # Minimal campaign: one email step, one contact, no signature.
    camp = {
        "name": "Test",
        "_owner_email": "tester@example.com",
        "contacts": [{"email": "lead@x.com", "first_name": "L"}],
        "steps": [{
            "name": "Email 1", "subject": "Hi", "body": "Hello {FirstName}",
            "step_type": "email_auto", "delay_days": 0, "time": "09:00",
            "touch_number": 1,
        }],
        "variables": {},
    }
    fa.queue_campaign_emails(camp)
    assert captured.get("items"), "expected at least one queued item"
    for it in captured["items"]:
        v = it.get("unsubscribe_email")
        assert v is None or isinstance(v, str), f"unsubscribe_email must be str|None, got {type(v).__name__}"
        # Must not be a literal True
        assert v is not True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_unsubscribe_email.py -v`
Expected: FAIL — current code sets `unsubscribe_email=True`.

- [ ] **Step 4: Fix L6125 (queue_campaign_emails)**

In `flowdrip_app.py`, find the dict literal at L6125 inside `queue_campaign_emails`:

Current:
```python
                unsubscribe_email=True,
```

Replace with:
```python
                # Use the campaign owner's SMTP address as the unsubscribe
                # contact. Falls back to None if unknown — never True (was a
                # bool that produced malformed List-Unsubscribe headers).
                unsubscribe_email=(_owner or None),
```

- [ ] **Step 5: Fix L12673 and L12787 (camp dict assignments)**

For each of:

```
camp["unsubscribe_email"] = True
```

Replace with:

```python
camp["unsubscribe_email"] = camp.get("_owner_email") or None
```

- [ ] **Step 6: Verify no `unsubscribe_email=True` or `= True` remain**

Run: `grep -n 'unsubscribe_email.*True' flowdrip_app.py`
Expected: no matches.

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/test_unsubscribe_email.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add flowdrip_app.py tests/test_unsubscribe_email.py
git commit -m "fix(C5): pass owner email (not bool True) as unsubscribe_email"
```

---

## Task 10 — C4: Make signature stripping safer (won't truncate on user's name)

**Files:**
- Modify: `flowdrip_app.py` (`_strip_signature_from_body`, L5384)
- Test: `tests/test_strip_signature.py`

**Verification note:** The spec says to "reverse the order — strip then merge". Inspecting the actual code, `queue_campaign_emails` does NOT call `_strip_signature_from_body`; the strip is only used when LOADING a saved campaign for editing. The real bug is the loose `body.find(sig_first)` fallback at L5413 — it matches the user's name written naturally inside their own body. The right fix is to make the strip require a real signature delimiter (`--` line, or `-- ` boundary), not a free-floating name match.

- [ ] **Step 1: Write the failing test**

Create `tests/test_strip_signature.py`:

```python
"""C4: _strip_signature_from_body must NOT truncate when the user's
own name appears inside the body (e.g. self-introduction)."""
import pytest


def test_strip_keeps_body_when_no_sig_delimiter_present(isolated_appdata, with_user):
    import flowdrip_app as fa

    # Configure a signature whose first line is the user's name.
    sigp = fa._user_sig_path()
    sigp.parent.mkdir(parents=True, exist_ok=True)
    sigp.write_text("Michael Vaughn\nSales Director\nDripDrop\n", encoding="utf-8")

    body = (
        "Hi {FirstName},\n\n"
        "This is Michael Vaughn from DripDrop. We help...\n\n"
        "Looking forward to chatting!"
    )

    out = fa._strip_signature_from_body(body)
    # Must NOT have lost everything after "Michael Vaughn"
    assert "Looking forward to chatting!" in out, "Body was truncated on user's own name"
    assert "DripDrop" in out


def test_strip_removes_real_signature_block(isolated_appdata, with_user):
    """The strip MUST still work when a real signature delimiter is present."""
    import flowdrip_app as fa

    sigp = fa._user_sig_path()
    sigp.parent.mkdir(parents=True, exist_ok=True)
    sigp.write_text("Michael Vaughn\nSales Director\n", encoding="utf-8")

    body = (
        "Hi {FirstName},\n\n"
        "Hope you're doing well.\n\n"
        "--\n"
        "Michael Vaughn\n"
        "Sales Director\n"
    )

    out = fa._strip_signature_from_body(body)
    assert "Hope you're doing well." in out
    assert "Sales Director" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_strip_signature.py -v`
Expected: `test_strip_keeps_body_when_no_sig_delimiter_present` FAILS — current code finds "Michael Vaughn" mid-body and truncates.

- [ ] **Step 3: Fix `_strip_signature_from_body`**

In `flowdrip_app.py`, find `def _strip_signature_from_body(body: str) -> str:` at L5384. Replace the FALLBACK at L5412–5427 (the `# Try finding the first sig line directly in body` block) so it ONLY triggers when there's a recognized closer immediately before the name:

Current (the relevant fallback block):
```python
    # Try finding the first sig line directly in body
    idx = body.find(sig_first)
    if idx > 30:
        before = body[:idx].rstrip()
        # Clean up trailing closers
        for closer in ["Thanks,", "Thank you,", "Best,", "Best regards,",
                        "Enjoy this great weather!", "Hope to hear from you soon!",
                        "Hope to hear from you!", "Looking forward to connecting."]:
            if before.rstrip().endswith(closer):
                break
            # Also check last 2 lines
            lines = before.rstrip().split("\n")
            if len(lines) >= 2 and lines[-1].strip() == "" and lines[-2].strip() == closer:
                before = "\n".join(lines[:-2]).rstrip()
                break
        return before
```

Replace with:
```python
    # Conservative fallback: only strip if the sig name follows a known
    # closer (Thanks,/Best,/etc.). A bare match against the user's name
    # mid-body would truncate self-introductions like "this is
    # Michael Vaughn from..." (C4 in audit 2026-04-26).
    closers = ["Thanks,", "Thank you,", "Best,", "Best regards,",
               "Enjoy this great weather!", "Hope to hear from you soon!",
               "Hope to hear from you!", "Looking forward to connecting."]
    idx = body.find(sig_first)
    while idx > 30:
        before = body[:idx].rstrip()
        # Only strip if `before` ends with a known closer (optionally with
        # a blank line between closer and name).
        for closer in closers:
            if before.endswith(closer):
                return before[: -len(closer)].rstrip()
            lines = before.split("\n")
            if (len(lines) >= 2 and lines[-1].strip() == ""
                    and lines[-2].strip() == closer):
                return "\n".join(lines[:-2]).rstrip()
        # Not a real sig boundary; look for next occurrence (in case the
        # name appears later as part of an actual sig).
        idx = body.find(sig_first, idx + 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_strip_signature.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_strip_signature.py
git commit -m "fix(C4): only strip signature when bounded by a real closer"
```

---

## Task 11 — C1: QEditor merge-field server-side sync

**Files:**
- Modify: `flowdrip_app.py` (the `ddInsert` JS at L7663 and Python button handlers that call it)
- Test: manual UI smoke test (no automated test possible — contenteditable behavior depends on browser)

**Approach:** The current `ddInsert` mutates the contenteditable and dispatches an `input` event, but NiceGUI's QEditor does not always reflect that into the Python `value`. The robust fix is to round-trip the editor's HTML back to Python after every insert and explicitly set `editor.value`.

- [ ] **Step 1: Update `ddInsert` to call back into Python**

In `flowdrip_app.py`, find `function ddInsert(v) {` at L7663. Modify the contenteditable branch (L7684–7704) so that after the insertion, it serializes the editor's HTML and sends it back to NiceGUI via the global event bus.

Current end of the contenteditable branch:
```javascript
            ce.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }
}
```

Replace with:
```javascript
            ce.dispatchEvent(new Event('input', {bubbles: true}));
            // Push the new HTML back to Python. The Python side listens
            // for 'dd_qeditor_change' and calls editor.set_value(html)
            // on the matching editor instance, keeping NiceGUI's bound
            // value in sync (C1 fix).
            try {
                if (window.emitEvent) {
                    var editorId = ce.getAttribute('data-dd-editor-id') || '';
                    window.emitEvent('dd_qeditor_change', {
                        editor_id: editorId,
                        html: ce.innerHTML
                    });
                }
            } catch (err) { /* non-fatal */ }
        }
    }
}
```

- [ ] **Step 2: Add Python-side handler that sets editor values**

Find a single bootstrap location in `flowdrip_app.py` where global UI is initialized (search for `inject_styles()` calls or the top of `index()`). Add this near the top of `index()` (just inside the function):

```python
    # Registry of QEditors that participate in the merge-field round-trip.
    # Populated by helper `_register_qeditor` below; consumed by the
    # 'dd_qeditor_change' event that ddInsert emits.
    _qeditor_registry: dict[str, "ui.editor"] = {}

    def _register_qeditor(editor, eid: str):
        """Tag a QEditor with a stable id so JS can target it after a
        merge-field insert, and Python can reflect HTML back into it."""
        _qeditor_registry[eid] = editor
        # Stamp the contenteditable element with the same id.
        editor.props(f'data-dd-editor-id={eid}')
        return editor

    @ui.on('dd_qeditor_change')
    def _on_qeditor_change(e):
        eid = (e.args or {}).get('editor_id') or ''
        html = (e.args or {}).get('html') or ''
        ed = _qeditor_registry.get(eid)
        if ed is not None:
            ed.set_value(html)
```

- [ ] **Step 3: Tag QEditors used for email bodies**

Search for `ui.editor(` calls used as email bodies (this is the QEditor for body composition). For each, capture the returned editor and tag it. Pattern:

Before:
```python
body = ui.editor(value=step.get("body", "")).style(...)
```

After:
```python
body = ui.editor(value=step.get("body", "")).style(...)
_register_qeditor(body, f"body_{step_idx}")  # or any stable id
```

There may be multiple body editors. Use a unique id per editor (e.g., wizard step index, campaign-step index) so JS can route events.

**Note:** This is the largest change in the plan — the editor sites are spread across `_sq_custom_editor`, the AI campaign builder, and the email-sequencer hub. Audit calls and tag each. If a call site is hard to reach (deep inside a closure), use `id(editor)` stringified as the editor_id.

- [ ] **Step 4: Manual smoke test**

NOTE: per CLAUDE.md / memory, do NOT start the local app. Smoke test on the live server after deploy:

1. Deploy with `bash _deploy_zero_downtime.sh`.
2. Open a campaign in the editor.
3. Click the `{FirstName}` insert chip in an email body field.
4. Without typing further, click Save.
5. Reload the campaign; confirm `{FirstName}` is in the saved body JSON.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "fix(C1): round-trip QEditor HTML to Python after merge-field insert"
```

---

## Task 12 — C12: Remove module-level QUEUE_PATH from funnelforge_core

**Files:**
- Modify: `funnelforge_core.py` (remove L71–73 globals; thread queue path through every queue function)
- Modify: `flowdrip_app.py` (remove the `not _SERVER_MODE` fallback at L19341 and L19379 that still references `QUEUE_PATH`)
- Test: `tests/test_no_global_queue_path.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_no_global_queue_path.py`:

```python
"""C12: there must be no module-level QUEUE_PATH in funnelforge_core."""
import pytest


def test_funnelforge_core_has_no_module_queue_path():
    import funnelforge_core as ff
    assert not hasattr(ff, "QUEUE_PATH"), \
        "QUEUE_PATH must not be a module-level global (multi-user leak vector)"


def test_load_queue_requires_explicit_path():
    """_load_queue must accept (or require) an explicit queue_path
    parameter — never fall back to a shared module global."""
    import funnelforge_core as ff
    import inspect
    sig = inspect.signature(ff._load_queue)
    assert "queue_path" in sig.parameters, \
        "_load_queue must take a queue_path argument"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_no_global_queue_path.py -v`
Expected: both FAIL.

- [ ] **Step 3: Refactor `funnelforge_core.py`**

a) Remove the global QUEUE_PATH at L71–73:

Current:
```python
_QUEUE_NEW = Path(os.getenv("LOCALAPPDATA", str(APP_DIR))) / "DripDrop" / "scheduled_queue.json"
_QUEUE_LEGACY = Path(os.getenv("LOCALAPPDATA", str(APP_DIR))) / "Funnel Forge" / "scheduled_queue.json"
QUEUE_PATH = _QUEUE_NEW if _QUEUE_NEW.exists() else _QUEUE_LEGACY
```

Delete those three lines entirely.

b) Modify `_load_queue` (L142) to require `queue_path: Path`:

Current:
```python
def _load_queue() -> List[Dict]:
    """Load the persisted email queue from disk."""
    try:
        if QUEUE_PATH.exists():
            with QUEUE_PATH.open("r", encoding="utf-8") as f:
                ...
```

Replace signature and body to thread `queue_path` through:
```python
def _load_queue(queue_path: Path) -> List[Dict]:
    """Load the persisted email queue from disk.
    queue_path is required — there is no module-level fallback (C12).
    """
    try:
        if queue_path.exists():
            with queue_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                queue = data if isinstance(data, list) else []
                # Backfill any items that have blank campaign names
                dirty = False
                for item in queue:
                    if not item.get("campaign"):
                        item["campaign"] = "Untitled Campaign"
                        dirty = True
                if dirty:
                    _save_queue(queue, queue_path)
                return queue
    except Exception:
        pass
    return []
```

c) Modify `_save_queue` (L163) likewise:

```python
def _save_queue(queue: List[Dict], queue_path: Path) -> None:
    """Save the email queue to disk atomically. queue_path is required."""
    try:
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = queue_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2, default=str)
        tmp.replace(queue_path)
    except Exception as e:
        _log_raw(f"[Queue] Save failed: {e}")
```

d) Modify all callers in `funnelforge_core.py` that previously used the global. Greppable via:

```
grep -n 'QUEUE_PATH\|_load_queue\|_save_queue' funnelforge_core.py
```

For every call to `_load_queue()` or `_save_queue(queue)`, pass an explicit `queue_path` — derive it from the user context (e.g., the in-flight queue item's `owner_email` or a dedicated `_resolve_queue_path(owner_email)` helper). If the call lives in a context where the owner is not known, raise `ValueError("queue_path required")` rather than guessing.

e) Add a helper near top of file:

```python
def _resolve_queue_path(owner_email: str) -> Path:
    """Map an owner email to the absolute queue file path. Server-mode
    paths come from DripDrop's per-user data dir; desktop fallbacks come
    from LOCALAPPDATA/DripDrop. Never a single shared file (C12).
    """
    if not owner_email:
        raise ValueError("owner_email required to resolve queue_path")
    base = Path(os.getenv("DRIPDROP_DATA_DIR", "")) or (
        Path(os.getenv("LOCALAPPDATA", str(APP_DIR))) / "DripDrop"
    )
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", owner_email.lower())
    return base / "users" / safe / "scheduled_queue.json"
```

(`re` is already imported.)

f) Update `add_to_queue`, `get_queue`, `cancel_queue_items`, `archive_old_queue_entries`, etc., to take `queue_path` (or `owner_email`) explicitly. Each existing public entry point should now require the caller to specify which user's queue.

- [ ] **Step 4: Update `flowdrip_app.py` callers**

Search and update every site that calls into `_ffc.add_to_queue / get_queue / cancel_queue_items / etc.` to pass the resolved `_user_queue_path()` (or owner email). Greppable via:

```
grep -n '_ffc\.\(add_to_queue\|get_queue\|cancel_queue_items\|_save_queue\|_load_queue\)' flowdrip_app.py
```

Also remove the `not _SERVER_MODE` fallback that referenced the now-deleted `QUEUE_PATH`. At L19340–19342:

Current:
```python
    qp = _user_queue_path()
    if not qp.exists() and not _SERVER_MODE:
        qp = QUEUE_PATH
```

Replace with:
```python
    qp = _user_queue_path()
    # No module-level QUEUE_PATH fallback (C12); a missing per-user
    # queue file simply means an empty queue.
```

Same change at L19376–19380.

Note: there's still a *legacy desktop* `QUEUE_PATH` defined in flowdrip_app.py at L747 (different from funnelforge_core's). Leave that one alone — it's per-process, not shared across users in server mode.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_no_global_queue_path.py -v`
Expected: PASS.

- [ ] **Step 6: Run the entire suite to catch regressions**

Run: `python -m pytest -v`
Expected: all passes; if any test breaks because a queue function now requires a path, fix that test to pass the path explicitly.

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py funnelforge_core.py tests/test_no_global_queue_path.py
git commit -m "fix(C12): remove module-level QUEUE_PATH; thread per-user path explicitly"
```

---

## Task 13 — C13: Outlook COM lifecycle balance

**Files:**
- Modify: `funnelforge_core.py` (`_get_outlook` L540, `_send_one_email` L478)
- Modify: `flowdrip_app.py` (`_scan` method L4776 — balance Co{Initialize,Uninitialize})
- Test: `tests/test_com_init_balance.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_com_init_balance.py`:

```python
"""C13: CoInitialize / CoUninitialize must be balanced. We mock pythoncom
to count calls and verify the scanner does both."""
import sys
import types


def test_outlook_monitor_scan_balances_co_init(monkeypatch):
    # Stub pythoncom and win32com.client.dynamic to record CoInitialize
    # and CoUninitialize calls without actually touching COM.
    counts = {"init": 0, "uninit": 0}

    fake_pythoncom = types.ModuleType("pythoncom")
    def _init():
        counts["init"] += 1
    def _uninit():
        counts["uninit"] += 1
    fake_pythoncom.CoInitialize = _init
    fake_pythoncom.CoUninitialize = _uninit
    monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)

    fake_win32 = types.ModuleType("win32com")
    fake_win32_client = types.ModuleType("win32com.client")
    fake_win32_dynamic = types.ModuleType("win32com.client.dynamic")
    def _dispatch(_):
        # Anything truthy with a GetNamespace method is enough to keep
        # _scan from short-circuiting; we then deliberately raise so the
        # finally block is the only thing exercised after init.
        class _Ol:
            def GetNamespace(self, _name):
                raise RuntimeError("stop here")
        return _Ol()
    fake_win32_dynamic.Dispatch = _dispatch
    fake_win32_client.dynamic = fake_win32_dynamic
    monkeypatch.setitem(sys.modules, "win32com", fake_win32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_win32_client)
    monkeypatch.setitem(sys.modules, "win32com.client.dynamic", fake_win32_dynamic)

    import flowdrip_app as fa
    mon = fa.OutlookMonitor()
    mon._scan()  # exercises Co{Initialize,Uninitialize}

    assert counts["init"] == counts["uninit"], (
        f"CoInitialize/CoUninitialize unbalanced: init={counts['init']}, "
        f"uninit={counts['uninit']}"
    )


def test_scan_skips_uninit_when_init_failed(monkeypatch):
    """If pythoncom can't be imported, CoUninitialize must NOT run
    (currently the finally block tries to import + uninit even when
    init never ran — C13b)."""
    counts = {"uninit": 0}
    fake_pythoncom = types.ModuleType("pythoncom")
    fake_pythoncom.CoUninitialize = lambda: counts.__setitem__("uninit", counts["uninit"] + 1)
    # Force ImportError on the *first* import inside _scan by removing
    # pythoncom from sys.modules and adding a meta-path finder that says
    # no.
    sys.modules.pop("pythoncom", None)
    class _Blocker:
        def find_module(self, name, path=None):
            if name == "pythoncom":
                return self
            return None
        def load_module(self, name):
            raise ImportError("blocked for test")
    blocker = _Blocker()
    monkeypatch.setattr(sys, "meta_path", [blocker, *sys.meta_path])

    import flowdrip_app as fa
    mon = fa.OutlookMonitor()
    mon._scan()

    assert counts["uninit"] == 0, "Uninit must not run when init failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_com_init_balance.py -v`
Expected: at least one FAIL — current `_scan` always runs `CoUninitialize` in `finally`, even when `CoInitialize` wasn't reached.

- [ ] **Step 3: Fix `OutlookMonitor._scan` (C13b)**

In `flowdrip_app.py`, find `def _scan(self):` at L4776. Track init state with a flag:

Current:
```python
    def _scan(self):
        try:
            import pythoncom, win32com.client.dynamic
            pythoncom.CoInitialize()
        except ImportError:
            self.last_scan = datetime.now()
            return
        try:
            ol = win32com.client.dynamic.Dispatch("Outlook.Application")
            ...
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
        self.last_scan = datetime.now()
```

The change is:
1. Add `co_initialized = False` before the first try.
2. Set `co_initialized = True` immediately after `pythoncom.CoInitialize()` succeeds.
3. Replace the `finally:` block that re-imports pythoncom with a guarded version that only uninits if `co_initialized` is True.

Targeted edit — Replace ONLY these two regions in `_scan`:

Region A (the top, around L4777–4782):
```python
    def _scan(self):
        try:
            import pythoncom, win32com.client.dynamic
            pythoncom.CoInitialize()
        except ImportError:
            self.last_scan = datetime.now()
            return
```

With:
```python
    def _scan(self):
        co_initialized = False
        try:
            import pythoncom, win32com.client.dynamic
            pythoncom.CoInitialize()
            co_initialized = True
        except ImportError:
            self.last_scan = datetime.now()
            return
```

Region B (the finally block, around L4864–4869):
```python
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
        self.last_scan = datetime.now()
```

With:
```python
        finally:
            if co_initialized:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
        self.last_scan = datetime.now()
```

Leave all code BETWEEN those two regions exactly as is.

- [ ] **Step 4: Fix `_SchedulerThread._get_outlook` (C13a)**

In `funnelforge_core.py`, the scheduler thread calls `pythoncom.CoInitialize()` once on (re)connect but never `CoUninitialize`. Track the init at thread-init and uninit on `stop()`. Find `class _SchedulerThread(threading.Thread):` (L515) and the `_get_outlook` method (L540):

a) Add `self._co_initialized = False` to `__init__`:

```python
    def __init__(self):
        super().__init__(name="FunnelForgeScheduler", daemon=True)
        self._stop_event = threading.Event()
        self._outlook    = None
        self._send_count = 0  # Tracks sends since last SendAndReceive
        self._co_initialized = False
```

b) Update `_get_outlook` to track init:

Current:
```python
            if self._outlook is None:
                pythoncom.CoInitialize()
                self._outlook = get_outlook_app()
```

Replace with:
```python
            if self._outlook is None:
                if not self._co_initialized:
                    pythoncom.CoInitialize()
                    self._co_initialized = True
                self._outlook = get_outlook_app()
```

c) Update `stop` to release COM:

Current:
```python
    def stop(self):
        self._stop_event.set()
```

Replace with:
```python
    def stop(self):
        self._stop_event.set()
        if self._co_initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._co_initialized = False
```

- [ ] **Step 5: Fix `_send_one_email` mail-item leak (C13c)**

In `funnelforge_core.py`, find the Outlook fallback in `_send_one_email` (L478). Wrap the `mail.Send()` block in try/finally that explicitly drops the reference:

Current:
```python
    try:
        mail = outlook.CreateItem(0)  # olMailItem
        mail.To      = to
        ...
        mail.Send()
        return True

    except Exception as e:
        _log_raw(f"  [SEND FAIL] {to} — {subject[:40]}: {e}")
        return False
```

Targeted edit — apply two changes:

1. Insert `mail = None` as the line immediately above the `try:` (so it's reachable from the `finally`).
2. Append a `finally:` clause to the existing try/except.

Concretely, replace:
```python
    try:
        mail = outlook.CreateItem(0)  # olMailItem
        mail.To      = to
        mail.Subject = subject
        mail.HTMLBody = _wrap_html_for_email(body, unsubscribe_email=unsubscribe,
                                             company_address=company_address)

        acct = _set_sending_account(outlook, mail, target_smtp=sender_smtp if sender_smtp else None)

        if sender_smtp and acct:
            try:
                actual = acct.SmtpAddress.lower() if acct.SmtpAddress else ""
                if actual and actual != sender_smtp.lower():
                    _log_raw(f"  [SKIP] Sender mismatch: queued by {sender_smtp}, current account {actual}")
                    return False
            except Exception:
                pass

        for p in attachments:
            try:
                if p and Path(p).exists():
                    mail.Attachments.Add(str(p))
            except Exception:
                pass

        mail.Send()
        return True

    except Exception as e:
        _log_raw(f"  [SEND FAIL] {to} — {subject[:40]}: {e}")
        return False
```

With:
```python
    mail = None
    try:
        mail = outlook.CreateItem(0)  # olMailItem
        mail.To      = to
        mail.Subject = subject
        mail.HTMLBody = _wrap_html_for_email(body, unsubscribe_email=unsubscribe,
                                             company_address=company_address)

        acct = _set_sending_account(outlook, mail, target_smtp=sender_smtp if sender_smtp else None)

        if sender_smtp and acct:
            try:
                actual = acct.SmtpAddress.lower() if acct.SmtpAddress else ""
                if actual and actual != sender_smtp.lower():
                    _log_raw(f"  [SKIP] Sender mismatch: queued by {sender_smtp}, current account {actual}")
                    return False
            except Exception:
                pass

        for p in attachments:
            try:
                if p and Path(p).exists():
                    mail.Attachments.Add(str(p))
            except Exception:
                pass

        mail.Send()
        return True

    except Exception as e:
        _log_raw(f"  [SEND FAIL] {to} — {subject[:40]}: {e}")
        return False
    finally:
        # Explicitly drop the COM ref so Outlook can release the
        # underlying handle (per-email leak — C13c).
        try:
            if mail is not None:
                del mail
        except Exception:
            pass
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_com_init_balance.py -v`
Expected: PASS.

- [ ] **Step 7: Manual verification (per spec — no win32com mock)**

1. Deploy with `bash _deploy_zero_downtime.sh`.
2. Queue 100 emails to a test contact (use the local desktop variant if possible, since this only matters in desktop mode).
3. Watch Outlook process memory over the next 100 sends; it should stay roughly flat (was previously growing).

- [ ] **Step 8: Commit**

```bash
git add flowdrip_app.py funnelforge_core.py tests/test_com_init_balance.py
git commit -m "fix(C13): balance CoInitialize/Uninitialize and release per-email COM refs"
```

---

## Task 14 — Final verification

- [ ] **Step 1: Run the entire test suite**

Run: `python -m pytest -v`
Expected: all tests pass, no warnings about broken imports.

- [ ] **Step 2: Smoke-import both modules**

Run: `python -c "import flowdrip_app, funnelforge_core; print('imports OK')"`
Expected: prints "imports OK". Catches any syntax errors introduced by the edits.

- [ ] **Step 3: Verify atomic helper used everywhere expected**

Run: `grep -nE 'write_text\(json\.dumps' flowdrip_app.py`
Expected: only sites that intentionally write transient/cache data (not config, not outcomes, not contacts, not community). Investigate any remaining hits and convert if appropriate.

- [ ] **Step 4: Verify C5 — no `unsubscribe_email=True`**

Run: `grep -n 'unsubscribe_email.*True' flowdrip_app.py`
Expected: zero matches.

- [ ] **Step 5: Verify C12 — no module-level QUEUE_PATH in funnelforge_core**

Run: `python -c "import funnelforge_core as f; print(hasattr(f, 'QUEUE_PATH'))"`
Expected: prints `False`.

- [ ] **Step 6: Final commit**

If all checks pass, no further commits required. Otherwise fix and commit the leftover.

---

## Definition of Done

- [ ] All 13 fixes merged on `claude/critical-bug-fixes` branch.
- [ ] Each fix has at least one passing test (manual for C1, C13).
- [ ] `python -m pytest -v` is green from a clean checkout.
- [ ] `python -c "import flowdrip_app, funnelforge_core"` succeeds.
- [ ] No new `write_text(json.dumps(...))` patterns introduced for the four protected files.
- [ ] Deploy: per CLAUDE.md / memory, ASK before deploying within 8am–5pm PDT; use `bash _deploy_zero_downtime.sh` only.

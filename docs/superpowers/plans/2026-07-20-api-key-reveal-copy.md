# API Key Reveal & Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every user reveal and copy their own full DripDrop API key at any time from the API Access card, instead of losing it after the one-time mint dialog.

**Architecture:** Store the key plaintext in `api_keys.json` at mint (hash stays the auth lookup, so nothing about authentication changes). Surface it through `_user_api_key_status`, and render a masked field with Reveal/Hide + Copy on the Profile → Personal Info card. A one-off backfill enables Mike's existing key without regeneration; other legacy keys show a "regenerate once" note.

**Tech Stack:** Python, NiceGUI, pytest. Single file `flowdrip_app.py` (~60k lines) + `tests/`.

Spec: `docs/superpowers/specs/2026-07-20-api-key-reveal-copy-design.md`
Branch: `feat/self-serve-api-keys`

---

## File Structure

- **Modify** `flowdrip_app.py`
  - `_mint_api_key` (`4871-4885`) — store `"key"` in the record.
  - `_user_api_key_status` (`4896-4910`) — return `"key"`.
  - New helper `_mask_api_key(key)` near the other API-key helpers (after `_user_api_key_status`, ~`4911`).
  - API Access card render (`50221-50243`) — reveal/copy UI.
- **Modify** `tests/test_api_key_selfserve.py` — fix the exact-keys assertion; add coverage for stored/returned plaintext, legacy blank, and masking.
- **Create** `scripts/backfill_api_key_plaintext.py` — one-off migration (Mike's key only).
- **Create** `tests/test_api_key_backfill.py` — test the migration's core function.

---

## Task 1: `_mask_api_key` helper

**Files:**
- Modify: `flowdrip_app.py` (add helper after `_user_api_key_status`, ~line 4911)
- Test: `tests/test_api_key_selfserve.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_key_selfserve.py`:

```python
def test_mask_api_key_hides_middle_keeps_ends():
    masked = fa._mask_api_key("dd_live_ABCDEFGHIJKLmnop3gAU")
    assert masked.startswith("dd_live_")
    assert masked.endswith("3gAU")
    assert "•" in masked
    assert "ABCDEFGH" not in masked      # middle is not leaked


def test_mask_api_key_empty_is_empty():
    assert fa._mask_api_key("") == ""
    assert fa._mask_api_key(None) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_key_selfserve.py::test_mask_api_key_hides_middle_keeps_ends tests/test_api_key_selfserve.py::test_mask_api_key_empty_is_empty -v`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_mask_api_key'`

- [ ] **Step 3: Write minimal implementation**

Insert after `_user_api_key_status` (after line 4910), before `_revoke_api_keys`:

```python
def _mask_api_key(key: str) -> str:
    """Masked display form: the 'dd_live_' prefix + bullets + last 4 chars.
    Returns '' for empty/None so callers can treat legacy (unstored) keys
    as 'nothing to reveal'."""
    if not key:
        return ""
    return key[:8] + ("•" * 8) + key[-4:]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_key_selfserve.py::test_mask_api_key_hides_middle_keeps_ends tests/test_api_key_selfserve.py::test_mask_api_key_empty_is_empty -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_api_key_selfserve.py
git commit -m "feat: add _mask_api_key helper for masked key display"
```

---

## Task 2: Store plaintext at mint and return it in status

**Files:**
- Modify: `flowdrip_app.py:4871-4885` (`_mint_api_key`), `flowdrip_app.py:4896-4910` (`_user_api_key_status`)
- Test: `tests/test_api_key_selfserve.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_key_selfserve.py`:

```python
def test_mint_stores_plaintext_key(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    rec = fa._load_api_keys()[fa._hash_api_key(key)]
    assert rec["key"] == key                       # plaintext persisted
    assert fa._hash_api_key(rec["key"]) in fa._load_api_keys()  # hashes back


def test_status_returns_plaintext_key(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    st = fa._user_api_key_status("rep@arena.com")
    assert st["key"] == key


def test_status_key_blank_for_legacy_record(tmp_path, monkeypatch):
    store = _isolate_keys(tmp_path, monkeypatch)
    # Simulate a pre-change record: hash + last4, no "key" field.
    legacy = "dd_live_LEGACYnoPlaintextStored9999wxyz"
    import json as _json
    store.write_text(_json.dumps({
        fa._hash_api_key(legacy): {
            "email": "old@arena.com", "label": "", "created": "2026-01-01T00:00:00",
            "last4": legacy[-4:],
        }
    }), encoding="utf-8")
    st = fa._user_api_key_status("old@arena.com")
    assert st["key"] == ""                          # nothing to reveal
    assert st["last4"] == legacy[-4:]
```

- [ ] **Step 2: Update the existing exact-keys assertion (it will otherwise break)**

In `tests/test_api_key_selfserve.py`, in `test_status_returns_newest_for_email`, change the final assertion:

```python
    assert set(st) == {"created", "last4", "label", "key"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_api_key_selfserve.py -v`
Expected: `test_mint_stores_plaintext_key` FAILS (`KeyError: 'key'`), `test_status_returns_plaintext_key` FAILS (`KeyError: 'key'`), `test_status_key_blank_for_legacy_record` FAILS (`KeyError: 'key'`).

- [ ] **Step 4: Implement — store the key at mint**

In `flowdrip_app.py`, edit `_mint_api_key` (the dict written at `4875-4880`) to add the `key` field:

```python
    data[_hash_api_key(key)] = {
        "email": (email or "").strip().lower(),
        "label": label or "",
        "created": datetime.now().isoformat(),
        "last4": key[-4:],
        "key": key,
    }
```

- [ ] **Step 5: Implement — return the key in status**

In `flowdrip_app.py`, edit the return dict of `_user_api_key_status` (`4906-4910`) to include `key` (defaulting to `""` for legacy records):

```python
    return {
        "created": newest.get("created", ""),
        "last4": newest.get("last4", ""),
        "label": newest.get("label", ""),
        "key": newest.get("key", ""),
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_key_selfserve.py -v`
Expected: PASS (all tests in the file, including the updated `test_status_returns_newest_for_email`).

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py tests/test_api_key_selfserve.py
git commit -m "feat: persist API key plaintext at mint, expose via status"
```

---

## Task 3: Card UI — reveal & copy

**Files:**
- Modify: `flowdrip_app.py:50221-50243` (the `if _api_status:` branch of the API Access card)

No unit test — this is NiceGUI render code; verification is `py_compile` + manual. The maskable/testable logic lives in `_mask_api_key` (Task 1).

- [ ] **Step 1: Replace the `if _api_status:` block**

In `flowdrip_app.py`, replace the current `if _api_status:` branch (lines `50221-50235`, ending just before `else:`) with:

```python
                    if _api_status:
                        ui.label(
                            f"Active key · created "
                            f"{_fmt_created(_api_status['created'])}").style(
                            f"font-size:12px;color:{C['muted']};"
                            f"margin-bottom:8px;")
                        if _api_status.get("key"):
                            _revealed = getattr(s, "_api_key_revealed", False)
                            _shown = (_api_status["key"] if _revealed
                                      else _mask_api_key(_api_status["key"]))
                            ui.input(value=_shown).props("readonly").classes(
                                "fd-input").style(
                                "font-family:monospace;margin-bottom:8px;")

                            def _toggle_reveal():
                                s._api_key_revealed = not getattr(
                                    s, "_api_key_revealed", False)
                                rf()

                            def _copy_key(k=_api_status["key"]):
                                ui.run_javascript(
                                    "navigator.clipboard.writeText("
                                    + json.dumps(k) + ")")
                                ui.notify("API key copied", type="positive")

                            with ui.element("div").style(
                                    "display:flex;gap:8px;margin-bottom:10px;"):
                                with ui.element("button").classes("fd-gb").style(
                                        "padding:7px 14px;font-size:12px;").on(
                                        "click", _toggle_reveal):
                                    ui.label("🙈 Hide" if _revealed
                                             else "👁 Reveal")
                                with ui.element("button").classes("fd-pb").style(
                                        "padding:7px 16px;font-size:12px;").on(
                                        "click", _copy_key):
                                    ui.label("📋 Copy API Key")
                        else:
                            ui.label(
                                f"dd_live_…{_api_status['last4'] or '••••'} · "
                                f"Regenerate once to enable copy.").style(
                                f"font-size:12px;color:{C['muted']};"
                                f"margin-bottom:10px;")
                        with ui.element("button").style(
                                f"display:inline-flex;align-items:center;gap:6px;"
                                f"padding:8px 16px;font-size:12px;font-weight:700;"
                                f"background:transparent;color:{C['muted']};"
                                f"border:1px solid {C['border']};border-radius:8px;"
                                f"cursor:pointer;font-family:inherit;").on(
                                "click", _regenerate_key):
                            ui.label("♻️ Regenerate Key")
```

(The `else:` branch that renders "No API key yet." + Generate button at `50236-50243` is unchanged.)

- [ ] **Step 2: Verify the file still compiles**

Run: `python -m py_compile flowdrip_app.py`
Expected: no output, exit 0.

- [ ] **Step 3: Manual smoke (local run)**

Run the app locally per repo notes, open Profile → Personal Info → API Access:
- With no key: "No API key yet." + Generate (unchanged).
- Generate a key → dialog Copy still works → after Done, card shows masked `dd_live_••••••••<last4>`, **👁 Reveal** unmasks, **📋 Copy API Key** copies the full key (paste to confirm).
Expected: reveal toggles; pasted value equals the full `dd_live_…` key.

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat: reveal + copy API key on the API Access card"
```

---

## Task 4: Backfill migration (Mike's key only)

**Files:**
- Create: `scripts/backfill_api_key_plaintext.py`
- Test: `tests/test_api_key_backfill.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_key_backfill.py`:

```python
import json
import importlib.util
from pathlib import Path

import flowdrip_app as fa

_spec = importlib.util.spec_from_file_location(
    "backfill_api_key_plaintext",
    Path(__file__).resolve().parents[1] / "scripts" / "backfill_api_key_plaintext.py",
)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


def test_backfill_sets_key_on_matching_record(tmp_path, monkeypatch):
    store = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: store)
    plaintext = "dd_live_realKeyPlaintextValue1234abcd3gAU"
    store.write_text(json.dumps({
        fa._hash_api_key(plaintext): {
            "email": "mike@arena.com", "label": "", "created": "2026-07-17T00:00:00",
            "last4": plaintext[-4:],
        }
    }), encoding="utf-8")
    changed = backfill.backfill(plaintext)
    assert changed is True
    assert fa._load_api_keys()[fa._hash_api_key(plaintext)]["key"] == plaintext


def test_backfill_noop_when_hash_absent(tmp_path, monkeypatch):
    store = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: store)
    store.write_text(json.dumps({"someotherhash": {"email": "x@y.com"}}),
                     encoding="utf-8")
    assert backfill.backfill("dd_live_notInTheStoreAtAll0000zzzz") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_key_backfill.py -v`
Expected: FAIL (`FileNotFoundError` / module load error — script does not exist yet).

- [ ] **Step 3: Create the migration script**

Create `scripts/backfill_api_key_plaintext.py`:

```python
"""One-off: write a known plaintext API key into its existing api_keys.json
record's `key` field (enables reveal+copy without regenerating).

Usage on the server:
    python3 scripts/backfill_api_key_plaintext.py dd_live_xxxxxxxx
The key is matched by sha256, so a wrong key simply no-ops. Backs up the
store to api_keys.json.bak before writing (atomic replace).
"""
import json
import sys

import flowdrip_app as fa


def backfill(plaintext: str) -> bool:
    """Set record['key']=plaintext for the record whose hash matches. Returns
    True if a record was updated, False if the hash is not present."""
    data = fa._load_api_keys()
    h = fa._hash_api_key(plaintext)
    if h not in data:
        return False
    data[h]["key"] = plaintext
    p = fa._api_keys_path()
    p.with_suffix(".json.bak").write_text(
        json.dumps(fa._load_api_keys(), indent=2), encoding="utf-8")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: backfill_api_key_plaintext.py <dd_live_key>")
        raise SystemExit(2)
    ok = backfill(sys.argv[1])
    print("updated" if ok else "no matching record (no-op)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_key_backfill.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_api_key_plaintext.py tests/test_api_key_backfill.py
git commit -m "feat: backfill script to enable reveal on an existing key"
```

---

## Task 5: Full-suite baseline + deploy prep

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite and compare to the known baseline**

Run: `python -m pytest tests/ -q`
Expected: The only failures are the **8 known pre-existing** failures (unrelated to API keys). Every `test_api_key_selfserve.py` and `test_api_key_backfill.py` test passes. If any *new* failure appears in an API-key test, fix before proceeding.

- [ ] **Step 2: Confirm compile once more**

Run: `python -m py_compile flowdrip_app.py`
Expected: exit 0.

- [ ] **Step 3: Deploy checklist (do NOT run blindly — confirm live service first)**

1. Determine the live service: `ssh -i ~/.ssh/dripdrop root@134.199.237.206 'systemctl is-active dripdrop dripdrop-green'` — **blue (`dripdrop`, 8080) is currently live** (pair flipped 2026-07-17); deploy to whichever is active.
2. Single-file swap of `flowdrip_app.py` (gzip-stream upload + `python3 -m py_compile` on server + restart the live service). Do NOT use `_deploy_zero_downtime.sh` (prod-drift: it also pushes `ats.py`).
3. Backup then run the backfill for Mike's key on the server:
   `cp /opt/dripdrop/data/api_keys.json /opt/dripdrop/data/api_keys.json.$(date +%s).bak`
   then `python3 scripts/backfill_api_key_plaintext.py <the dd_live_…3gAU key>` from the app dir with the env sourced.
4. Verify in the UI: Mike's card shows Reveal/Copy immediately; a teammate with a legacy key shows the "Regenerate once" note.

- [ ] **Step 4: Final commit / branch state**

The feature branch `feat/self-serve-api-keys` now carries all changes. Do not merge/deploy without the user's go-ahead.

---

## Self-Review

- **Spec coverage:** store-at-mint (Task 2) ✓; status returns key (Task 2) ✓; card reveal+copy (Task 3) ✓; legacy note (Task 3) ✓; Mike backfill (Task 4) ✓; non-destructive (no revoke anywhere) ✓; tests incl. legacy-blank (Task 2) ✓; plaintext-at-rest decision (implemented, no encryption) ✓; deploy notes (Task 5) ✓.
- **Placeholder scan:** none — all steps carry concrete code/commands.
- **Type consistency:** `_mask_api_key` (Task 1) used in Task 3; status `key` field (Task 2) read in Task 3 and returned by `backfill()` path; `backfill(plaintext)->bool` defined Task 4, tested Task 4. Consistent.

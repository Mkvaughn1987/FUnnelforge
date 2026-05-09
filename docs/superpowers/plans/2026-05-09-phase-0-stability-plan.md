# Phase 0 — Stability and Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore Candidate Pool to working state, harden the systemic ContextVar-doesn't-propagate-to-threads bug via a `_run_as_user` helper, add basic exception logging, and re-enable the Candidates sidebar entry.

**Architecture:** Add a `_run_as_user(email, target)` thread-spawn helper that pre-binds the user's email into the thread's `_CURRENT_USER_EMAIL` ContextVar and calls `_switch_to_user_paths()` before invoking the target callable. Migrate every `threading.Thread(target=...)` site that performs per-user reads/writes. Install `sys.excepthook` and `threading.excepthook` to write exception tracebacks to a daily-rotating file at `_BASE_DATA_DIR/logs/errors.log`.

**Tech Stack:** Python 3.12, NiceGUI, pytest, `threading`, `logging.handlers.TimedRotatingFileHandler`, `contextvars.ContextVar`.

**Spec:** [docs/superpowers/specs/2026-05-09-phase-0-stability-design.md](../specs/2026-05-09-phase-0-stability-design.md)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `flowdrip_app.py` | Modify | Add `_run_as_user` helper near L880; add logging setup near L860; add `_log_exception` helper; migrate thread sites; add `/diagnostics` route; uncomment sidebar at L8561; replace 7 `traceback.print_exc()` sites |
| `tests/test_run_as_user_helper.py` | Create | Unit tests for the new helper |
| `tests/test_individual_candidate_add_user_binding.py` | Create | Behavioral test for the candidate-finder Search flow fix |
| `tests/test_error_log_writes.py` | Create | Verify excepthooks write to errors.log |
| `tests/test_audit_no_raw_per_user_threads.py` | Create | Static-analysis regression net for the bug class |
| `tests/test_bulk_import_user_binding.py` | Modify | Update assertions to match new `_run_as_user` pattern |

---

## Task 1: ~~Add `threading` to top-level imports~~ — NO-OP

**Status:** Skipped. Verification on 2026-05-09 found `threading` is already imported at `flowdrip_app.py:12` as part of the comma-separated import line (`import asyncio, copy, csv, json, os, re, threading, time, uuid`). The earlier audit's `^import threading` grep missed comma-imported modules. No action required; `_run_as_user` can reference `threading.Thread` and `threading.excepthook` directly.

---

## Task 2: Add `_run_as_user` helper (TDD)

**Files:**
- Create: `tests/test_run_as_user_helper.py`
- Modify: `flowdrip_app.py` (insert after `_switch_to_user_paths` definition; landed at L1728)

- [ ] **Step 1: Locate where the helper goes**

Run: `grep -n "^def _switch_to_user_paths" flowdrip_app.py`

Expected: One hit at L1703. The helper goes immediately after this function ends (note the actual end line; it's roughly L1745-1760).

- [ ] **Step 2: Write the failing tests**

Create `tests/test_run_as_user_helper.py`:

```python
"""Tests for _run_as_user — the thread-spawn wrapper that pre-binds
the per-user ContextVar so worker threads don't fall through the
LEAK_GUARD path in _resolve_user_root().

Background: Python ContextVars don't propagate into threading.Thread
workers. Without this helper, every per-user write inside a thread
silently lands in _BASE_DATA_DIR/<file>.json (a shared cross-user
file) instead of the per-user dir.
"""
import threading
import time


def test_helper_exists_and_returns_thread():
    import flowdrip_app as fa
    assert hasattr(fa, "_run_as_user"), "_run_as_user must be defined"
    captured = {"v": None}
    def _t():
        captured["v"] = "ran"
    th = fa._run_as_user("user@example.com", _t)
    assert isinstance(th, threading.Thread)
    th.join(timeout=2.0)
    assert captured["v"] == "ran", "target callable must execute"


def test_worker_sees_bound_user_in_contextvar():
    """Inside the worker, _CURRENT_USER_EMAIL.get() must equal the
    email passed to _run_as_user, even though ContextVars normally
    don't propagate across threading.Thread boundaries."""
    import flowdrip_app as fa
    seen = {"email": None}
    def _t():
        seen["email"] = fa._CURRENT_USER_EMAIL.get()
    th = fa._run_as_user("alice@example.com", _t)
    th.join(timeout=2.0)
    assert seen["email"] == "alice@example.com"


def test_worker_resolves_per_user_path_not_base_dir(monkeypatch):
    """The whole point of this helper: per-user path accessors inside
    the worker must resolve to /…/users/<safe_email>/, not the base
    data dir (which is the cross-user leak vector).

    We monkeypatch _SERVER_MODE=True to exercise production-mode path
    resolution from a desktop dev machine. In real production this
    flag is True automatically (set during app init when the
    DRIPDROP_DATA_DIR env var is detected)."""
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_SERVER_MODE", True)
    seen = {"path": None}
    def _t():
        seen["path"] = fa._user_candidate_pool_path()
    th = fa._run_as_user("bob@example.com", _t)
    th.join(timeout=2.0)
    p = str(seen["path"])
    assert "users" in p and "bob_at_example_com" in p, (
        f"Expected per-user path, got {p!r}"
    )


def test_empty_email_falls_through_without_crashing():
    """If no email is provided, the worker still runs (no crash) but
    the LEAK_GUARD path inside _resolve_user_root will fire and log
    a stack trace. That's the correct behavior — failing closed by
    crashing would break code that legitimately doesn't have a user
    bound (e.g. some pre-auth flows)."""
    import flowdrip_app as fa
    ran = {"v": False}
    def _t():
        ran["v"] = True
    th = fa._run_as_user("", _t)
    th.join(timeout=2.0)
    assert ran["v"] is True


def test_thread_name_defaults_to_target_name():
    """threading.excepthook receives the Thread object; thread names
    must be informative for log diagnosis. Default to target.__name__
    so a worker called `_bulk_import_worker` shows up in errors.log
    with that name, not the useless default `Thread-N`."""
    import flowdrip_app as fa
    seen = {"name": None}
    def _bulk_import_worker():
        seen["name"] = threading.current_thread().name
    th = fa._run_as_user("c@example.com", _bulk_import_worker)
    th.join(timeout=2.0)
    assert seen["name"] == "_bulk_import_worker"
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `pytest tests/test_run_as_user_helper.py -v`

Expected: All 5 tests FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_run_as_user'`.

- [ ] **Step 4: Implement the helper**

Find the end of `_switch_to_user_paths` in `flowdrip_app.py` (starts at L1703). Immediately after the closing of that function, add:

```python
def _run_as_user(email, target, name=None, daemon=True):
    """Spawn a thread that's pre-bound to `email` for per-user path resolution.

    Use this anywhere a worker thread will read or write per-user state.
    System threads (schedulers, monitors) should keep using threading.Thread
    directly — they don't have a single owning user.

    Why: Python ContextVars don't propagate into threading.Thread workers,
    so _CURRENT_USER_EMAIL.get() returns "" inside the worker and
    _resolve_user_root() falls back via LEAK_GUARD to _BASE_DATA_DIR — a
    cross-user shared file. This helper sets the ContextVar inside the
    worker before target() runs.
    """
    captured = (email or "").strip()
    def _wrapper():
        if captured:
            try:
                _CURRENT_USER_EMAIL.set(captured)
                _switch_to_user_paths(captured)
            except Exception as ex:
                print(f"[run_as_user] bind failed for {captured}: {ex}",
                      flush=True)
        target()
    t = threading.Thread(
        target=_wrapper, daemon=daemon,
        name=name or getattr(target, "__name__", "user_worker"),
    )
    t.start()
    return t
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `pytest tests/test_run_as_user_helper.py -v`

Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_run_as_user_helper.py flowdrip_app.py
git commit -m "feat(threads): add _run_as_user helper to bind ContextVar in worker threads

Centralizes the per-user binding pattern that was added inline to
_bulk_import_resumes in 427c2f4. Future per-user-write threads call
this helper instead of duplicating the binding boilerplate."
```

---

## Task 3: Migrate `_bulk_import_resumes._worker` to `_run_as_user`; update existing test

**Files:**
- Modify: `flowdrip_app.py:32095-32238` (the `_bulk_import_resumes` function)
- Modify: `tests/test_bulk_import_user_binding.py` (assertions need to match new pattern)

- [ ] **Step 1: Read current state of `_bulk_import_resumes`**

Run: `sed -n '32088,32240p' flowdrip_app.py`

Expected: See the inline `_user_email_for_worker` capture (L32104-32108), the worker signature with `_user=_user_email_for_worker` (L32118), the inline `_CURRENT_USER_EMAIL.set` + `_switch_to_user_paths` block (L32125-32134), and the `threading.Thread(target=_worker, daemon=True).start()` call (L32238).

- [ ] **Step 2: Replace the inline binding with `_run_as_user`**

In `flowdrip_app.py`, modify `_bulk_import_resumes`:

A) Delete lines L32104-32108 (the `_user_email_for_worker` capture comment block + variable). Replace with one line:

```python
        _user_email_for_worker = getattr(s, "_user_email", "") or ""
```

(Keep that one line; we still need to capture it before spawning, so the value travels into the thread closure correctly.)

B) Change the worker signature back from `def _worker(_path=str(tmp), _name=fname, _user=_user_email_for_worker):` to:

```python
        def _worker(_path=str(tmp), _name=fname):
```

C) Delete the inline binding block inside `_worker` (L32125-32134 — the `if _user: try: _CURRENT_USER_EMAIL.set(_user); _switch_to_user_paths(_user) except…` block, plus its preceding comment).

D) Change the spawn line at L32238 from:

```python
        threading.Thread(target=_worker, daemon=daemon).start()
```

(or whichever exact form is there — confirm with the sed output above) to:

```python
        _run_as_user(_user_email_for_worker, _worker, name="_bulk_import_worker")
```

- [ ] **Step 3: Update `tests/test_bulk_import_user_binding.py` to assert the new pattern**

Replace the entire file with:

```python
"""Bulk resume import bg thread must bind the user before writing.

Background:
- _bulk_import_resumes._worker runs as a thread spawned via _run_as_user
- Without binding, ContextVars don't propagate and _user_candidate_pool_path()
  falls back to _BASE_DATA_DIR via LEAK_GUARD, writing to a cross-user file
- Multiple users reported uploads "doing nothing" pre-fix
- Fix is centralized in the _run_as_user helper as of 2026-05-09
"""
import inspect


def test_bulk_import_captures_user_email_outside_thread():
    """The async _on_bulk_upload handler must read s._user_email
    while still in the async task context, BEFORE spawning the thread.
    ContextVars are valid here; once we cross into the thread, we lose
    them."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._bulk_import_resumes)
    assert "_user_email" in src and "getattr(s, " in src, (
        "_bulk_import_resumes must capture s._user_email in the async "
        "task before spawning the worker thread"
    )


def test_bulk_import_worker_uses_run_as_user_helper():
    """The worker must be spawned via _run_as_user so the per-user
    ContextVar gets bound inside the thread before any per-user write.
    Spawning via raw threading.Thread bypasses the binding and the
    write leaks to the shared file."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._bulk_import_resumes)
    assert "_run_as_user(" in src, (
        "Worker must be spawned via _run_as_user, not raw threading.Thread, "
        "so per-user paths resolve correctly inside the thread"
    )


def test_bulk_import_does_not_use_raw_threading_thread():
    """Defensive: the old raw threading.Thread(target=_worker) call
    leaked writes to the shared file. If someone reverts to it, this
    test fails."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._bulk_import_resumes)
    assert "threading.Thread(target=_worker" not in src, (
        "Raw threading.Thread(target=_worker, …) bypasses _run_as_user "
        "binding and leaks per-user writes to the shared file"
    )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/test_bulk_import_user_binding.py tests/test_run_as_user_helper.py -v`

Expected: All tests in both files PASS.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_bulk_import_user_binding.py
git commit -m "refactor(candidates): migrate bulk-import worker to _run_as_user

Replaces the inline user-binding boilerplate added in 427c2f4 with a
call to the centralized _run_as_user helper. Test rewritten to
assert on helper usage instead of inline pattern."
```

---

## Task 4: Migrate candidate-finder Search `_run` to `_run_as_user` (the second known bug)

**Files:**
- Create: `tests/test_individual_candidate_add_user_binding.py`
- Modify: `flowdrip_app.py:33366` (and the surrounding ~30-line `_run` function)

- [ ] **Step 1: Locate the broken thread spawn**

Run: `sed -n '33260,33370p' flowdrip_app.py`

Expected: See the candidate-finder Search flow's `_run` function (it's an inner function inside the search button handler), and the line at L33366: `threading.Thread(target=_run, daemon=True).start()`.

- [ ] **Step 2: Write the failing test**

Create `tests/test_individual_candidate_add_user_binding.py`:

```python
"""The candidate-finder Search flow's bg thread (Add New Candidate)
must bind the user before calling add_candidate_to_pool.

Same root cause as bulk import: ContextVars don't propagate into
threading.Thread, so add_candidate_to_pool -> save_candidate_pool ->
_user_candidate_pool_path() -> _resolve_user_root() falls back to
_BASE_DATA_DIR (cross-user shared file).

Before this fix: clicking '+ Add New Candidate' on an empty pool
appeared to do nothing — write went to the shared file, the page
read from the per-user file (correctly empty).

After this fix: the spawn site uses _run_as_user, so the worker
sees the right user inside the thread.
"""
import inspect
import re


def test_candidate_finder_search_uses_run_as_user():
    """The candidate-finder page handler that owns the Search flow
    must spawn its bg search thread via _run_as_user, not raw
    threading.Thread."""
    import flowdrip_app as fa
    # The Search flow lives inside p_candidate_finder; we walk the
    # source for the spawn site that calls add_candidate_to_pool.
    src = inspect.getsource(fa.p_candidate_finder)
    # The _run worker calls add_candidate_to_pool — find that block
    # and verify the spawn nearby uses _run_as_user.
    assert "add_candidate_to_pool(" in src, (
        "p_candidate_finder is expected to contain the Search _run "
        "worker that calls add_candidate_to_pool"
    )
    # Defensive: the old raw spawn must not be present
    assert "threading.Thread(target=_run, daemon=True).start()" not in src, (
        "Raw threading.Thread(target=_run) bypasses _run_as_user "
        "binding and leaks per-user writes to the shared file. Use "
        "_run_as_user(s._user_email, _run, name='cf_search_worker') "
        "instead."
    )
    assert "_run_as_user(" in src, (
        "p_candidate_finder must use _run_as_user to spawn the Search "
        "flow's worker thread, so add_candidate_to_pool writes to the "
        "per-user file."
    )
```

- [ ] **Step 3: Run test, verify it fails**

Run: `pytest tests/test_individual_candidate_add_user_binding.py -v`

Expected: The third assertion FAILS — `_run_as_user(` is not in `p_candidate_finder` source yet (the second assertion may also fail since the raw spawn IS still there).

- [ ] **Step 4: Migrate the spawn**

In `flowdrip_app.py`, change L33366 from:

```python
                threading.Thread(target=_run, daemon=True).start()
```

to:

```python
                _run_as_user(s._user_email, _run, name="cf_search_worker")
```

- [ ] **Step 5: Run test, verify it passes**

Run: `pytest tests/test_individual_candidate_add_user_binding.py -v`

Expected: PASS.

- [ ] **Step 6: Run the full bulk-import + helper + new test together**

Run: `pytest tests/test_run_as_user_helper.py tests/test_bulk_import_user_binding.py tests/test_individual_candidate_add_user_binding.py -v`

Expected: All tests across all three files PASS.

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py tests/test_individual_candidate_add_user_binding.py
git commit -m "fix(candidates): individual Add New Candidate now binds user before write

Same root cause as the bulk-import bug fixed in 427c2f4: the
candidate-finder Search flow's bg thread spawned via raw
threading.Thread, so add_candidate_to_pool wrote to the shared
cross-user file instead of the per-user file.

Migrates the spawn site to _run_as_user. Test mirrors the existing
bulk-import binding test."
```

---

## Task 5: Set up exception logging infrastructure (file handler + excepthooks + helper)

**Files:**
- Create: `tests/test_error_log_writes.py`
- Modify: `flowdrip_app.py` near L860 (after `_BASE_DATA_DIR` is defined, before `_resolve_user_root`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_error_log_writes.py`:

```python
"""Exception logging: uncaught worker exceptions must end up in
_BASE_DATA_DIR/logs/errors.log so production bug reports include
tracebacks without requiring SSH into the server.
"""
import importlib
import os
import sys
import time
from pathlib import Path


def test_log_exception_helper_exists():
    import flowdrip_app as fa
    assert hasattr(fa, "_log_exception"), "_log_exception helper must exist"


def test_log_exception_writes_to_errors_log(tmp_path, monkeypatch):
    """_log_exception(exc, context) must write a line to errors.log
    containing the bound user (if any), the context string, and the
    traceback."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # Re-import to pick up the new BASE_DATA_DIR
    if "flowdrip_app" in sys.modules:
        del sys.modules["flowdrip_app"]
    import flowdrip_app as fa
    fa._CURRENT_USER_EMAIL.set("logtest@example.com")
    try:
        raise ValueError("synthetic test error")
    except ValueError as e:
        fa._log_exception(e, context="test_callsite")
    # Flush handlers so the file is written
    for h in fa._err_log.handlers:
        h.flush()
    log_file = fa._LOG_DIR / "errors.log"
    assert log_file.exists(), f"errors.log should exist at {log_file}"
    contents = log_file.read_text(encoding="utf-8")
    assert "logtest@example.com" in contents
    assert "test_callsite" in contents
    assert "ValueError" in contents and "synthetic test error" in contents


def test_threading_excepthook_writes_traceback(tmp_path, monkeypatch):
    """Uncaught exceptions in worker threads must be caught by
    threading.excepthook and routed to errors.log."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if "flowdrip_app" in sys.modules:
        del sys.modules["flowdrip_app"]
    import flowdrip_app as fa
    def _crash():
        raise RuntimeError("worker boom")
    th = fa._run_as_user("crashtest@example.com", _crash, name="crash_worker")
    th.join(timeout=2.0)
    for h in fa._err_log.handlers:
        h.flush()
    log_file = fa._LOG_DIR / "errors.log"
    assert log_file.exists()
    contents = log_file.read_text(encoding="utf-8")
    assert "crash_worker" in contents
    assert "RuntimeError" in contents and "worker boom" in contents
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/test_error_log_writes.py -v`

Expected: All 3 tests FAIL with `AttributeError` or similar — none of `_log_exception`, `_err_log`, `_LOG_DIR` exist yet.

- [ ] **Step 3: Locate the install point**

Run: `grep -n "^_BASE_DATA_DIR = _user_data_dir" flowdrip_app.py`

Expected: One hit at L862. The logging block goes immediately after this line and before `def _resolve_user_root` at L883.

- [ ] **Step 4: Add the logging infrastructure**

Insert into `flowdrip_app.py` immediately after L862 (the `_BASE_DATA_DIR = _user_data_dir()` line) and before the `def _resolve_user_root` definition:

```python
# ── Exception logging to a rotating file ─────────────────────────────────
# Setup writes uncaught exceptions (main thread + worker threads) to a
# daily-rotating file at _BASE_DATA_DIR/logs/errors.log so production
# bug reports include tracebacks without requiring SSH into the server.
# Best-effort: if setup fails (permissions, disk full), the app still
# starts and exceptions still go to stdout via the existing prints.
import logging.handlers as _logging_handlers
import traceback as _traceback

_LOG_DIR = _BASE_DATA_DIR / "logs"
_err_log = _logging.getLogger("dripdrop.errors")
_err_log.setLevel(_logging.ERROR)
_err_log.propagate = False  # don't double-log to stdout/journal

try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _err_log_handler = _logging_handlers.TimedRotatingFileHandler(
        str(_LOG_DIR / "errors.log"),
        when="midnight", backupCount=14, encoding="utf-8",
    )
    _err_log_handler.setFormatter(_logging.Formatter(
        "%(asctime)s | %(message)s"
    ))
    _err_log.addHandler(_err_log_handler)
except Exception as _ex:
    # Logging setup is best-effort; never block app startup on it.
    print(f"[errors.log] setup failed: {_ex}", flush=True)


def _log_exception(exc, context: str = ""):
    """Write a single exception entry to errors.log. Includes the
    bound user (if any), a context string identifying the callsite,
    and the formatted traceback."""
    user = ""
    try:
        user = _CURRENT_USER_EMAIL.get() or ""
    except Exception:
        pass
    try:
        tb = "".join(_traceback.format_exception(
            type(exc), exc, exc.__traceback__,
        ))
    except Exception:
        tb = repr(exc)
    try:
        _err_log.error("user=%s context=%s\n%s", user, context, tb)
    except Exception as _ex:
        print(f"[errors.log] write failed: {_ex}", flush=True)


def _install_excepthooks():
    """Wire sys.excepthook (main thread) and threading.excepthook
    (worker threads) so uncaught exceptions land in errors.log."""
    _prev_sys = sys.excepthook
    def _sys_hook(exc_type, exc, tb):
        try:
            _log_exception(exc, context="sys.excepthook")
        except Exception:
            pass
        try:
            _prev_sys(exc_type, exc, tb)
        except Exception:
            pass
    sys.excepthook = _sys_hook

    _prev_thr = threading.excepthook
    def _thr_hook(args):
        try:
            tname = getattr(args.thread, "name", "?")
            _log_exception(args.exc_value, context=f"threading.excepthook thread={tname}")
        except Exception:
            pass
        try:
            _prev_thr(args)
        except Exception:
            pass
    threading.excepthook = _thr_hook


_install_excepthooks()
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `pytest tests/test_error_log_writes.py -v`

Expected: All 3 tests PASS.

- [ ] **Step 6: Run the full test suite to confirm no regressions**

Run: `pytest tests/test_run_as_user_helper.py tests/test_bulk_import_user_binding.py tests/test_individual_candidate_add_user_binding.py tests/test_error_log_writes.py -v`

Expected: All tests across all four files PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_error_log_writes.py flowdrip_app.py
git commit -m "feat(logging): add rotating errors.log + sys/threading excepthooks

Uncaught exceptions on the main thread and in worker threads now
land in _BASE_DATA_DIR/logs/errors.log (daily rotation, 14-day
retention). Bug reports can include tracebacks without SSH access.

Adds _log_exception(exc, context) helper for explicit handled-but-
logged exception sites (the existing 7 traceback.print_exc callers
get migrated in the next commit)."
```

---

## Task 6: Replace 7 `traceback.print_exc()` callsites with `_log_exception`

**Files:**
- Modify: `flowdrip_app.py` at lines 13537, 33361, 38446, 38485, 39163, 40199, 40407

- [ ] **Step 1: Confirm the 7 sites still match**

Run: `grep -n "traceback.print_exc" flowdrip_app.py`

Expected: 7 matches at the line numbers listed above (or near them — line numbers may have drifted slightly from earlier edits).

- [ ] **Step 2: Replace each callsite**

For each of the 7 sites, replace the `traceback.print_exc()` call with `_log_exception(<exc_var>, context="<descriptive_label>")`. The exception variable is named in the surrounding `except Exception as <name>:` clause; use that name. Keep the existing `print(f"[…] error: {e}")` line — it's the developer-facing journalctl noise we agreed to keep.

Specific edits (use Edit tool with the surrounding context to disambiguate):

**Site 1 — L13537** `[PDF] Inline generation error`
- Old: `import traceback; traceback.print_exc()`
- New: `_log_exception(e, context="pdf.inline_generation")`

**Site 2 — L33360-33361** `[CF] ERROR`
- Old:
  ```python
                          import traceback
                          print(f"[CF] ERROR: {e}")
                          traceback.print_exc()
  ```
- New:
  ```python
                          print(f"[CF] ERROR: {e}")
                          _log_exception(e, context="candidate_finder.search")
  ```

**Site 3 — L38446** `[Newsletter] Render FAILED`
- Old: `import traceback; traceback.print_exc()`
- New: `_log_exception(ex, context="newsletter.render")`

**Site 4 — L38485** `[Newsletter] Preview send error`
- Old: `import traceback; traceback.print_exc()`
- New: `_log_exception(ex, context="newsletter.preview_send")`

**Site 5 — L39163** `[MarketIntel] THREAD ERROR`
- Old: `traceback.print_exc()` (note: `import traceback` is at the top of the function here, not inline)
- New: `_log_exception(e, context="market_intel.thread")`

**Site 6 — L40199** `[ProfilePhoto] unexpected error`
- Old: `traceback.print_exc()` (note: `import traceback` is on a preceding line in the same except block)
- New: `_log_exception(ex, context="profile_photo.upload")`

**Site 7 — L40407** `[NewsletterAvatar] upload error`
- Old: `import traceback; traceback.print_exc()`
- New: `_log_exception(ex, context="newsletter_avatar.upload")`

- [ ] **Step 3: Verify no `traceback.print_exc` calls remain (except in comments/docstrings)**

Run: `grep -n "traceback.print_exc" flowdrip_app.py`

Expected: No matches, or only matches inside comment/docstring lines.

- [ ] **Step 4: Verify the file still parses**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0, no output.

- [ ] **Step 5: Run the existing test suite**

Run: `pytest tests/test_error_log_writes.py tests/test_run_as_user_helper.py -v`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py
git commit -m "refactor(logging): route 7 handled-but-logged exceptions to errors.log

Replaces the 7 traceback.print_exc() callsites with _log_exception()
so handled exceptions also persist to the rotating file. The
developer-facing print(f\"[…] error: {e}\") lines are kept — they're
the existing journalctl noise pattern, separately useful."
```

---

## Task 7: Add `/diagnostics` admin endpoint

**Files:**
- Modify: `flowdrip_app.py` (add a new `@ui.page("/diagnostics")` route near other admin routes)

- [ ] **Step 1: Find a good location for the route**

Run: `grep -n "@ui.page" flowdrip_app.py | head -20`

Expected: Lists existing `@ui.page("/path")` decorators. Pick a location near the end of the route block (before main entry / launch logic). Note the line number.

- [ ] **Step 2: Add the diagnostics route**

Add the following to `flowdrip_app.py` immediately after the last `@ui.page` route declaration:

```python
@ui.page("/diagnostics")
def diagnostics_page():
    """Admin diagnostics: tail of errors.log + last error timestamp.
    Requires login. Intended for users to copy-paste into bug reports
    so we don't need SSH access to debug their issue."""
    # Auth gate: only logged-in users see the page; anonymous gets a
    # bare "log in first" prompt.
    try:
        email = (app.storage.user.get("email") or "").strip()
    except Exception:
        email = ""
    if not email:
        ui.label("Log in to view diagnostics.").style("padding:24px;")
        return

    log_file = _LOG_DIR / "errors.log"
    if not log_file.exists():
        ui.label("No errors logged yet.").style("padding:24px;")
        return

    try:
        # Read last 100 lines (cheap for an error log; rotates daily)
        lines = log_file.read_text(encoding="utf-8").splitlines()
        tail = lines[-100:]
        last_ts = ""
        for line in reversed(tail):
            # Each entry starts with a timestamp from the formatter
            # "%(asctime)s | …" — extract first " | " split's left side.
            if " | " in line:
                last_ts = line.split(" | ", 1)[0]
                break
    except Exception as ex:
        ui.label(f"Failed to read errors.log: {ex}").style("padding:24px;")
        return

    ui.label("DripDrop Diagnostics").style(
        "font-size:18px;font-weight:700;padding:16px 24px 4px;")
    ui.label(f"Last error: {last_ts or '(none in tail)'}").style(
        "padding:0 24px 12px;color:#666;font-size:12px;")
    ui.html(
        "<pre style='background:#f6f6f6;padding:16px 24px;font-size:11px;"
        "white-space:pre-wrap;word-break:break-all;'>"
        + "\n".join(tail).replace("<", "&lt;").replace(">", "&gt;")
        + "</pre>"
    )
```

- [ ] **Step 3: Verify the file still parses**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0, no output.

- [ ] **Step 4: Smoke-test the route registration**

Run: `python -c "import flowdrip_app; print('OK')"`

Expected: `OK` printed (no import errors).

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(diagnostics): add /diagnostics admin endpoint for errors.log tail

Logged-in users can hit /diagnostics to see the last 100 lines of
errors.log and copy-paste into bug reports. Faster than SSH-ing
into prod to grep journalctl."
```

---

## Task 8: Audit and migrate remaining per-user-write thread sites

**Files:**
- Modify: `flowdrip_app.py` (multiple sites — each gets either migration to `_run_as_user` or a one-line "system thread" comment)

- [ ] **Step 1: List all `threading.Thread(target=` sites**

Run: `grep -n "threading.Thread(target=\|_thr.Thread(target=\|_thr2.Thread(target=\|_th.Thread(target=\|_thr_pdf.Thread(target=" flowdrip_app.py`

Expected: ~50 hits. Save the list to `audit_threads.tmp` for reference: `grep -n "threading.Thread(target=\|_thr.Thread(target=\|_thr2.Thread(target=\|_th.Thread(target=\|_thr_pdf.Thread(target=" flowdrip_app.py > audit_threads.tmp`.

- [ ] **Step 2: Classify each hit**

For each line in `audit_threads.tmp`, read ~30 lines of surrounding context and classify:

- **Per-user write** — the worker calls any of: `save_candidate_pool`, `save_dnc`, `add_candidate_to_pool`, `update_candidate_in_pool`, `remove_candidate_from_pool`, `_save_*` helpers, or anything that uses a `_user_*_path()` accessor for writing. → **MIGRATE** to `_run_as_user`.
- **System thread** — `ServerEmailScheduler` (~L44184), `ServerReplyMonitor` (~L44617), Outlook background scanners. No single owning user. → **LEAVE**, add `# system thread — no user binding` comment.
- **Read-only** — worker only reads or computes, never writes per-user state. → **LEAVE**, no comment needed.

Write the classification into a temporary checklist file `audit_threads_classified.tmp` with one line per site:
```
LINE_NUM | CLASSIFICATION | NEAREST_HELPER_OR_FUNCTION_NAME
```

Example:
```
6843  | per-user-write | _bg_save_dnc inside add_to_dnc_form
44184 | system         | ServerEmailScheduler
12203 | read-only      | _bg_check_oom_status
```

- [ ] **Step 3: Migrate each per-user-write site**

For each `per-user-write` line in the classification file, edit `flowdrip_app.py` to replace the spawn call with `_run_as_user`. The pattern is:

Old:
```python
threading.Thread(target=<fn>, daemon=True).start()
```

New:
```python
_run_as_user(s._user_email, <fn>, name="<descriptive_name>")
```

- If the surrounding scope has `s` (the AppState), use `s._user_email`.
- If the scope captures the user differently (some callsites use a captured local, some use `app.storage.user`), preserve that capture and pass the resolved email.
- Pick `name=` matching the inner function's role (`_bg_save_dnc`, `_market_intel_worker`, etc.) so threading.excepthook entries are diagnosable.

Commit in batches of ~5-10 sites with descriptive messages, e.g.:
```bash
git commit -m "refactor(threads): migrate DNC save + reply scan workers to _run_as_user"
```

- [ ] **Step 4: Add the system-thread comment to system sites**

For each `system` line, add a one-line comment immediately above the `threading.Thread(...)` spawn:

```python
# system thread — no user binding (app-level scheduler/monitor)
threading.Thread(target=<fn>, daemon=True, name="ServerEmailScheduler").start()
```

(Add `name=...` if not already present, since named threads are easier to diagnose in errors.log.)

- [ ] **Step 5: Run all tests after each batch**

Run: `pytest tests/ -q`

Expected: All tests pass after each batch commit. If any fail, revert that batch and investigate before continuing.

- [ ] **Step 6: Verify the file still parses**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0.

- [ ] **Step 7: Delete the temp files**

Run: `rm audit_threads.tmp audit_threads_classified.tmp`

- [ ] **Step 8: Final commit (if any sites remain uncommitted)**

```bash
git add flowdrip_app.py
git commit -m "refactor(threads): finish per-user-write thread migration audit"
```

---

## Task 9: Add `test_audit_no_raw_per_user_threads.py` regression test

**Files:**
- Create: `tests/test_audit_no_raw_per_user_threads.py`

- [ ] **Step 1: Write the test**

Create `tests/test_audit_no_raw_per_user_threads.py`:

```python
"""Regression net: any new threading.Thread(target=...) in flowdrip_app.py
that touches per-user state must use _run_as_user instead.

This test scans the source file for raw thread spawns and walks
~50 lines forward looking for per-user-write helpers. If found
without an intervening _run_as_user, the test fails — preventing
the next instance of the cross-user leak bug from shipping.

System threads (schedulers, monitors) are allowlisted by name.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILE = REPO_ROOT / "flowdrip_app.py"

# Functions / patterns that indicate a per-user write is happening
PER_USER_WRITE_MARKERS = [
    "save_candidate_pool",
    "save_dnc",
    "add_candidate_to_pool",
    "update_candidate_in_pool",
    "remove_candidate_from_pool",
    "_user_candidate_pool_path",
    "_user_pdf_dir",
    "_user_dnc_path",
    "_user_queue_path",
    "_user_config_path",
    "_user_signature_path",
    "_user_templates_dir",
    "_user_campaigns_dir",
    "_user_clients_path",
    "_user_newsletters_dir",
]

# Thread names that are known system-level (no user binding required)
SYSTEM_THREAD_NAMES = {
    "ServerEmailScheduler",
    "ServerReplyMonitor",
}

# Raw thread-spawn patterns we want to catch
SPAWN_PATTERNS = [
    re.compile(r"threading\.Thread\(target="),
    re.compile(r"_thr\.Thread\(target="),
    re.compile(r"_thr2\.Thread\(target="),
    re.compile(r"_th\.Thread\(target="),
    re.compile(r"_thr_pdf\.Thread\(target="),
]

LOOKAHEAD_LINES = 50


def _is_system_thread(spawn_line: str) -> bool:
    """A spawn is system-level if its name= argument is in the allowlist."""
    m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', spawn_line)
    if not m:
        return False
    return m.group(1) in SYSTEM_THREAD_NAMES


def test_no_raw_thread_writes_per_user_state():
    """For each raw threading.Thread(target=...) spawn in
    flowdrip_app.py, walk ~50 lines forward and verify either:
      (a) The thread name is in the system-thread allowlist, OR
      (b) No per-user write marker appears in the lookahead window
    Otherwise the spawn is a leak vector — use _run_as_user instead.
    """
    src = SOURCE_FILE.read_text(encoding="utf-8").splitlines()
    leaks = []
    for i, line in enumerate(src):
        if not any(p.search(line) for p in SPAWN_PATTERNS):
            continue
        if _is_system_thread(line):
            continue
        window = "\n".join(src[i : i + LOOKAHEAD_LINES])
        for marker in PER_USER_WRITE_MARKERS:
            if marker in window:
                leaks.append(
                    f"  L{i+1}: {line.strip()[:80]}\n"
                    f"    → forward window contains {marker!r}; "
                    f"migrate to _run_as_user(...) or add a system-thread "
                    f"name from SYSTEM_THREAD_NAMES."
                )
                break
    assert not leaks, (
        "Found raw threading.Thread spawns that do per-user writes "
        "without _run_as_user binding. Each is a cross-user leak vector:\n"
        + "\n".join(leaks)
    )
```

- [ ] **Step 2: Run the test, verify it passes**

Run: `pytest tests/test_audit_no_raw_per_user_threads.py -v`

Expected: PASS. (If it fails, the failure message lists the specific sites that need migration; fix them and re-run.)

- [ ] **Step 3: Run the full Phase 0 test suite**

Run: `pytest tests/test_run_as_user_helper.py tests/test_bulk_import_user_binding.py tests/test_individual_candidate_add_user_binding.py tests/test_error_log_writes.py tests/test_audit_no_raw_per_user_threads.py -v`

Expected: All tests across all five files PASS.

- [ ] **Step 4: Run the full project test suite**

Run: `pytest tests/ -q`

Expected: All tests PASS. Investigate any failures before proceeding.

- [ ] **Step 5: Commit**

```bash
git add tests/test_audit_no_raw_per_user_threads.py
git commit -m "test(threads): add regression net for raw threading.Thread per-user writes

Static-analysis test that scans flowdrip_app.py for any raw
threading.Thread(target=...) spawn followed by a per-user-write
helper within 50 lines. Catches future instances of the
cross-user leak bug at test time, before they ship."
```

---

## Task 10: Uncomment Candidates sidebar entry

**Files:**
- Modify: `flowdrip_app.py:8561` (and the surrounding 4 lines of explanatory comment)

- [ ] **Step 1: Read the current state of the sidebar block**

Run: `sed -n '8558,8572p' flowdrip_app.py`

Expected: Shows the SALES_NAV list with the Candidates entry commented out and a 4-line "hidden 2026-05-08" comment block above it.

- [ ] **Step 2: Restore the entry; remove the explanatory comment**

In `flowdrip_app.py`, replace the 5-line block:

```python
    # Candidates entry hidden 2026-05-08 while the upload + view bugs
    # are investigated. Page handler p_candidate_finder and the
    # candidate_finder route stay in place — the top-nav 'Candidate
    # Pool' pill still navigates there for users with deep links.
    # ("🔍", "Candidates",        "candidate_finder"),
```

with the single line:

```python
    ("🔍", "Candidates",        "candidate_finder"),
```

- [ ] **Step 3: Verify the file still parses**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0.

- [ ] **Step 4: Run the full test suite one more time**

Run: `pytest tests/ -q`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "ui(sidebar): restore Candidates entry now that upload + view bugs are fixed

Both root causes addressed:
- Bulk import bg thread binds user via _run_as_user (was 427c2f4)
- Individual Add New Candidate bg thread also migrated
- Audit + regression test prevent the same class of bug
  re-appearing from any other thread spawn site"
```

---

## Task 11: Cutover (manual steps — no code changes)

**Files:** None modified locally; production state changes.

- [ ] **Step 1: Confirm with user before any production action**

Per memory `feedback_auto_deploy.md`: ask the user "Deploy now or end of hour?" before running the deploy script. Do NOT auto-deploy.

- [ ] **Step 2: Backup the orphaned shared candidate_pool.json on production**

Run:

```bash
ssh -i ~/.ssh/dripdrop root@134.199.237.206 \
  "cp /opt/dripdrop/data/candidate_pool.json \
      /opt/dripdrop/data/_orphan_candidate_pool_backup_$(date +%Y%m%d).json && \
   ls -la /opt/dripdrop/data/_orphan_*"
```

Expected: One new file `_orphan_candidate_pool_backup_20260509.json` listed (size ~96KB). The original `/opt/dripdrop/data/candidate_pool.json` is untouched.

- [ ] **Step 3: Deploy with zero-downtime script**

Per memory `feedback_zero_downtime_deploy.md`: never plain `systemctl restart dripdrop` — that drops user sessions.

Run:

```bash
bash _deploy_zero_downtime.sh
```

Expected: Script completes without error; `systemctl is-active dripdrop` returns `active`.

- [ ] **Step 4: Smoke-check the live site**

Per memory `feedback_smoke_check_before_deploy.md`: `/healthz` is not the real signal; the live `/` page render is.

Run:

```bash
curl -s -o /dev/null -w "live /: %{http_code} in %{time_total}s\n" https://dripdripdrop.ai/
curl -s -o /dev/null -w "live /healthz: %{http_code}\n" https://dripdripdrop.ai/healthz
```

Expected: Both return `200`.

- [ ] **Step 5: Manual validation — fresh test user**

Open a browser. Log into dripdripdrop.ai as a fresh test user (newly-registered account, OR an existing account whose `/opt/dripdrop/data/users/<safe_email>/candidate_pool.json` does not yet exist so any new write is unambiguously attributable).

Confirm the Candidates entry is now visible in the sidebar.

- [ ] **Step 6: Manual validation — individual add**

Sidebar → Candidates → "+ Add New Candidate" → upload a single PDF resume → fill in target role/location → run Find Matching Jobs. Confirm the candidate appears in the per-user pool after the search completes.

- [ ] **Step 7: Manual validation — bulk import**

Click "Bulk Import Resumes" → select 3 PDFs → wait for the toast confirming "Imported 3 of 3 resumes." → confirm all 3 appear in the per-user pool list.

- [ ] **Step 8: SSH validation — files landed in the right place**

Run:

```bash
ssh -i ~/.ssh/dripdrop root@134.199.237.206 \
  "ls -la /opt/dripdrop/data/users/<safe_email_of_test_user>/candidate_pool.json && \
   echo '---' && \
   stat -c '%y %n' /opt/dripdrop/data/candidate_pool.json /opt/dripdrop/data/_orphan_candidate_pool_backup_*.json"
```

Expected:
- Per-user file exists and contains the 4 newly-added candidates (1 individual + 3 bulk)
- The shared `/opt/dripdrop/data/candidate_pool.json` mtime is unchanged from the pre-deploy backup time
- The orphan backup file is intact

If the shared file's mtime advanced, a fix regressed — investigate immediately.

- [ ] **Step 9: SSH validation — errors.log is healthy**

Run:

```bash
ssh -i ~/.ssh/dripdrop root@134.199.237.206 \
  "ls -la /opt/dripdrop/data/logs/ 2>&1 && \
   tail -50 /opt/dripdrop/data/logs/errors.log 2>&1 | head -100"
```

Expected:
- `logs/` directory exists with `errors.log` (possibly empty)
- Tail shows no entries from the past few minutes related to the test user's activity (clean run = no fix regressions)

- [ ] **Step 10: Hit /diagnostics in the browser to smoke-test it**

Open https://dripdripdrop.ai/diagnostics in the test user's logged-in browser session.

Expected: Page renders showing "DripDrop Diagnostics" header, the "Last error" timestamp (or "(none in tail)"), and the (possibly empty) errors.log tail.

- [ ] **Step 11: If anything failed, hotfix or revert**

If validation step 6, 7, or 8 fails (write went to shared file, page is broken, sidebar doesn't render): immediately re-hide the Candidates sidebar entry (revert Task 10's commit) and re-deploy. Investigate the failure, add a test that catches it, fix, re-validate, re-deploy.

- [ ] **Step 12: Mark Phase 0 complete**

Notify the user that Phase 0 is shipped and validated. Recommend kicking off Phase 1 (Strategy Chooser) brainstorm in a fresh session.

---

## Self-review checklist

- **Spec coverage:**
  - Goal (restore Candidate Pool, harden the bug class, add logging, restore sidebar) → covered by Tasks 2-10
  - Non-goals respected (no print refactor, no resolution-order changes, no orphan deletion) → confirmed in task scopes
  - Architecture (`_run_as_user` helper, migration, audit) → Tasks 2, 3, 4, 8
  - Logging design (file handler, excepthooks, helper, /diagnostics) → Tasks 5, 6, 7
  - Tests (4 new test files, 1 updated) → Tasks 2, 3, 4, 5, 9
  - Manual validation (5 SSH/browser steps) → Task 11 steps 5-10
  - Cutover (orphan backup, deploy, sidebar restore) → Task 11 steps 2-4 + Task 10
  - Risks mitigated (audit test catches future regressions, file-handler wrapped in try/except) → Tasks 5, 9
- **Placeholder scan:** No TBDs, TODOs, or vague directions. All code blocks complete.
- **Type consistency:** `_run_as_user(email, target, name=None, daemon=True)` signature consistent across helper definition (Task 2), migration calls (Tasks 3, 4, 8), test invocations (Tasks 2, 5).
- **Open items:** Task 8 step 2 produces a per-site classification list that's worth keeping as a record. Plan instructs deleting the temp files at step 7 — if you want a permanent record, save the classification into a comment block in `flowdrip_app.py` near `_run_as_user` instead of deleting.

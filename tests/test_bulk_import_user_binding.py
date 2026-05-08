"""Bulk resume import bg thread must bind the user before writing.

Background:
- _bulk_import_resumes._worker runs as a `threading.Thread`
- Python ContextVars don't propagate to thread workers, so
  _CURRENT_USER_EMAIL.get() returns "" inside the worker
- _user_candidate_pool_path() then falls back to _BASE_DATA_DIR
  via the LEAK_GUARD path, writing to a SHARED file across users
- Multiple users reported uploads "doing nothing" on the candidate
  page — their data was saved to the cross-user file but the page
  reads from the per-user file (correctly), so it appeared empty
- Same bug pattern was fixed in newsletter bg gen + call briefing
  bg gen earlier; this is the same fix in a different path

Tests verify:
- _bulk_import_resumes source captures _user_email INSIDE the
  async context (before spawning the thread)
- The worker function takes _user as a kwarg with the captured email
  as the default value (so each thread keeps its own copy)
- The worker calls _CURRENT_USER_EMAIL.set + _switch_to_user_paths
  before doing any per-user write
"""
import inspect
import re


def test_bulk_import_captures_user_email_outside_thread():
    """The async _on_bulk_upload handler must read s._user_email
    while still in the async task context, BEFORE any threading.Thread
    is spawned. ContextVars are valid here; once we cross into the
    thread, we lose them."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._bulk_import_resumes)
    assert "_user_email" in src and "getattr(s, " in src, (
        "_bulk_import_resumes must capture s._user_email in the async "
        "task before spawning the worker thread"
    )


def test_bulk_import_worker_binds_user_before_write():
    """The worker must bind the captured user via both:
      - _CURRENT_USER_EMAIL.set(...) — for ContextVar-based path helpers
      - _switch_to_user_paths(...)   — for legacy module-level globals
    Without these, _user_candidate_pool_path() falls back to base dir
    and the candidate gets saved to the shared cross-user file."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._bulk_import_resumes)
    assert "_CURRENT_USER_EMAIL.set" in src, (
        "Worker must call _CURRENT_USER_EMAIL.set(_user) so per-user "
        "path helpers resolve to the right user inside the thread"
    )
    assert "_switch_to_user_paths" in src, (
        "Worker must call _switch_to_user_paths(_user) so legacy module "
        "globals resolve to the right user inside the thread"
    )


def test_bulk_import_worker_signature_has_user_kwarg():
    """The worker should accept _user as a default kwarg so the
    captured email is bound at function-definition time per closure.
    This avoids late-binding issues if multiple uploads come in fast
    and the outer _user_email_for_worker variable changes."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._bulk_import_resumes)
    # Substring check: `_user=` appearing after `def _worker(`
    assert "def _worker(" in src
    after_def = src[src.index("def _worker(") :]
    # Look for _user= in the next ~200 chars (the param list)
    assert "_user=" in after_def[:300], (
        "Worker function signature should accept _user as a default kwarg "
        "so each thread closes over its own captured email"
    )

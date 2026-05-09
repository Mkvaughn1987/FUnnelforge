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

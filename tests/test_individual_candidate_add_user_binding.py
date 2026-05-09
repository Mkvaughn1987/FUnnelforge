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


def test_candidate_finder_search_uses_run_as_user():
    """The candidate-finder page handler that owns the Search flow
    must spawn its bg search thread via _run_as_user, not raw
    threading.Thread."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_candidate_finder)
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

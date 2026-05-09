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

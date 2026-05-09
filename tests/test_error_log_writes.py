"""Exception logging: uncaught worker exceptions must end up in
_BASE_DATA_DIR/logs/errors.log so production bug reports include
tracebacks without requiring SSH into the server.
"""
import sys


def test_log_exception_helper_exists():
    import flowdrip_app as fa
    assert hasattr(fa, "_log_exception"), "_log_exception helper must exist"


def test_log_exception_writes_to_errors_log(tmp_path, monkeypatch):
    """_log_exception(exc, context) must write a line to errors.log
    containing the bound user (if any), the context string, and the
    traceback."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if "flowdrip_app" in sys.modules:
        del sys.modules["flowdrip_app"]
    import flowdrip_app as fa
    fa._CURRENT_USER_EMAIL.set("logtest@example.com")
    try:
        raise ValueError("synthetic test error")
    except ValueError as e:
        fa._log_exception(e, context="test_callsite")
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

"""C12: there must be no module-level QUEUE_PATH in funnelforge_core."""
import inspect
import pytest


def test_funnelforge_core_has_no_module_queue_path():
    import funnelforge_core as ff
    assert not hasattr(ff, "QUEUE_PATH"), \
        "QUEUE_PATH must not be a module-level global (multi-user leak vector)"


def test_load_queue_requires_explicit_path():
    """_load_queue must accept (or require) an explicit queue_path
    parameter — never fall back to a shared module global."""
    import funnelforge_core as ff
    sig = inspect.signature(ff._load_queue)
    assert "queue_path" in sig.parameters, \
        "_load_queue must take a queue_path argument"


def test_save_queue_requires_explicit_path():
    import funnelforge_core as ff
    sig = inspect.signature(ff._save_queue)
    assert "queue_path" in sig.parameters

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

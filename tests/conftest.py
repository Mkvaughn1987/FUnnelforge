# WARNING FOR FUTURE TEST AUTHORS:
# NEVER `import flowdrip_app` at the top level of a test file.
# Top-level imports run at pytest collection time, BEFORE any fixture
# has a chance to set LOCALAPPDATA, which freezes all module-level path
# constants (_BASE_DATA_DIR, USER_DIR, etc.) against the real user's
# %LOCALAPPDATA%. Always import flowdrip_app inside a fixture or test
# function body, so the isolated_appdata fixture runs first.
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
    Returns the user's resolved root dir.

    The ContextVar is reset in teardown so tests that exercise the
    empty-user code path are not affected by tests that use this
    fixture.
    """
    # Import lazily so isolated_appdata fixture takes effect first.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    import flowdrip_app as fa

    # --- Fix: reset ContextVar after the test (Critical) ---
    token = fa._CURRENT_USER_EMAIL.set("tester@example.com")

    # --- Fix: patch module-level frozen path constants (Important) ---
    # These are bound once at import time from LOCALAPPDATA; subsequent
    # tests that change LOCALAPPDATA get a new tmp_path but these still
    # point at the first test's directory without explicit patching.
    new_base = pathlib.Path(isolated_appdata) / "DripDrop"
    new_base.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(fa, "_BASE_DATA_DIR", new_base)
    monkeypatch.setattr(fa, "USER_DIR", new_base)
    monkeypatch.setattr(fa, "CAMPAIGNS_DIR", new_base / "Campaigns")
    monkeypatch.setattr(fa, "CONTACTS_DIR", new_base / "Contacts")
    monkeypatch.setattr(fa, "CONTACTS_CSV", new_base / "Contacts" / "contacts.csv")
    monkeypatch.setattr(fa, "RESPONDED_JSON", new_base / "Campaigns" / "responded.json")
    monkeypatch.setattr(fa, "PDF_DIR", new_base / "PDFs")
    monkeypatch.setattr(fa, "CONFIG_PATH", new_base / "dripdrop_config.json")
    monkeypatch.setattr(fa, "SIGNATURE_PATH", new_base / "signature.txt")
    monkeypatch.setattr(fa, "OUTCOMES_PATH", new_base / "task_outcomes.json")
    monkeypatch.setattr(fa, "QUEUE_PATH_NEW", new_base / "scheduled_queue.json")
    monkeypatch.setattr(fa, "QUEUE_ARCHIVE_PATH", new_base / "scheduled_queue_archive.json")
    monkeypatch.setattr(fa, "DNC_PATH", new_base / "dnc_list.json")
    monkeypatch.setattr(fa, "CANDIDATE_POOL_PATH", new_base / "candidate_pool.json")
    monkeypatch.setattr(fa, "USERS_DB_PATH", new_base / "users.json")

    user_root = fa._resolve_user_root("tester@example.com")

    yield user_root

    # Teardown: reset ContextVar so later tests start with the default "".
    fa._CURRENT_USER_EMAIL.reset(token)

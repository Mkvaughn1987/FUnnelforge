"""Atomicity regression tests for C8/C9/C10/C11."""
import json
import pytest


def test_save_outcomes_uses_atomic_write(isolated_appdata, with_user, monkeypatch):
    """save_outcomes must go through _atomic_write_text. Verified by
    forcing os.replace to raise and asserting the original file is intact."""
    import flowdrip_app as fa

    target = fa._user_outcomes_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"old": true}', encoding="utf-8")

    def boom(src, dst):
        raise OSError("crash")
    monkeypatch.setattr(fa.os, "replace", boom)

    fa.save_outcomes({"new": True})  # save_outcomes swallows exceptions
    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}


def test_save_config_uses_atomic_write(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    target = fa._user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"old_token": "abc"}', encoding="utf-8")

    def boom(src, dst):
        raise OSError("crash")
    monkeypatch.setattr(fa.os, "replace", boom)

    with pytest.raises(OSError):
        fa.save_config({"new_token": "xyz"})

    import json as _json
    assert _json.loads(target.read_text(encoding="utf-8")) == {"old_token": "abc"}


def test_save_contacts_csv_atomic_on_crash(isolated_appdata, with_user, monkeypatch):
    """The atomic write helper itself: write a CSV-shaped payload, force
    os.replace to crash, original file must remain intact."""
    import flowdrip_app as fa

    target = fa._user_contacts_csv_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("Email,FirstName\nold@x.com,Old\n", encoding="utf-8")

    def boom(src, dst):
        raise OSError("crash")
    monkeypatch.setattr(fa.os, "replace", boom)

    payload = "Email,FirstName\nnew@x.com,New\n"
    with pytest.raises(OSError):
        fa._atomic_write_text(target, payload)

    assert "old@x.com" in target.read_text(encoding="utf-8")
    assert "new@x.com" not in target.read_text(encoding="utf-8")

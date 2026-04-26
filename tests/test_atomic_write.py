"""Tests for the atomic-write helper (Task 1)."""
import json
import pathlib
import pytest


def test_atomic_write_creates_file(isolated_appdata, with_user):
    import flowdrip_app as fa
    p = isolated_appdata / "out.json"
    fa._atomic_write_text(p, '{"hello": "world"}')
    assert p.read_text(encoding="utf-8") == '{"hello": "world"}'


def test_atomic_write_no_partial_file_on_failure(isolated_appdata, with_user, monkeypatch):
    """If the os.replace step fails, the destination must not contain
    a half-written payload."""
    import flowdrip_app as fa
    p = isolated_appdata / "config.json"
    p.write_text('{"old": "data"}', encoding="utf-8")

    # Force os.replace to raise mid-swap. The destination file must keep
    # its original content.
    real_replace = fa.os.replace
    def boom(src, dst):
        raise OSError("simulated crash")
    monkeypatch.setattr(fa.os, "replace", boom)

    with pytest.raises(OSError):
        fa._atomic_write_text(p, '{"new": "data"}')
    assert p.read_text(encoding="utf-8") == '{"old": "data"}'


def test_atomic_write_no_tmp_left_on_success(isolated_appdata, with_user):
    import flowdrip_app as fa
    p = isolated_appdata / "ok.json"
    fa._atomic_write_text(p, "ok")
    # tmp sibling should be cleaned up after replace
    assert not p.with_suffix(p.suffix + ".tmp").exists()

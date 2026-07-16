"""Self-serve API key helpers.

Spec: docs/superpowers/specs/2026-07-15-self-serve-api-keys-design.md
Plan: docs/superpowers/plans/2026-07-15-self-serve-api-keys.md
"""
import flowdrip_app as fa


def _isolate_keys(tmp_path, monkeypatch):
    store = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: store)
    return store


def test_mint_persists_last4(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    rec = fa._load_api_keys()[fa._hash_api_key(key)]
    assert rec["last4"] == key[-4:]
    assert len(rec["last4"]) == 4


def test_status_none_when_no_key(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    assert fa._user_api_key_status("nobody@arena.com") is None
    assert fa._user_api_key_status("") is None


def test_status_returns_newest_for_email(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    fa._mint_api_key("rep@arena.com", label="old")
    newer = fa._mint_api_key("rep@arena.com", label="new")
    fa._mint_api_key("other@arena.com", label="unrelated")
    st = fa._user_api_key_status("REP@arena.com")  # case-insensitive
    assert st is not None
    assert st["last4"] == newer[-4:]
    assert st["label"] == "new"
    assert set(st) == {"created", "last4", "label"}


def test_revoke_removes_only_target_email(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    doomed = fa._mint_api_key("rep@arena.com")
    keep = fa._mint_api_key("other@arena.com")
    n = fa._revoke_api_keys("rep@arena.com")
    assert n == 1
    assert fa._resolve_api_key(doomed) is None            # revoked
    assert fa._resolve_api_key(keep) == "other@arena.com"  # untouched


def test_revoke_counts_all_for_email(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    fa._mint_api_key("rep@arena.com")
    fa._mint_api_key("rep@arena.com")
    assert fa._revoke_api_keys("REP@arena.com") == 2
    assert fa._user_api_key_status("rep@arena.com") is None


def test_revoke_empty_email_is_zero(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    assert fa._revoke_api_keys("") == 0

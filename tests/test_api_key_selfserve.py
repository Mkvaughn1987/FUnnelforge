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
    assert set(st) == {"created", "last4", "label", "key"}


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


def test_mask_api_key_hides_middle_keeps_ends():
    masked = fa._mask_api_key("dd_live_ABCDEFGHIJKLmnop3gAU")
    assert masked.startswith("dd_live_")
    assert masked.endswith("3gAU")
    assert "•" in masked
    assert "ABCDEFGH" not in masked      # middle is not leaked


def test_mask_api_key_empty_is_empty():
    assert fa._mask_api_key("") == ""
    assert fa._mask_api_key(None) == ""


def test_mint_stores_plaintext_key(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    rec = fa._load_api_keys()[fa._hash_api_key(key)]
    assert rec["key"] == key                       # plaintext persisted
    assert fa._hash_api_key(rec["key"]) in fa._load_api_keys()  # hashes back


def test_status_returns_plaintext_key(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    st = fa._user_api_key_status("rep@arena.com")
    assert st["key"] == key


def test_status_key_blank_for_legacy_record(tmp_path, monkeypatch):
    store = _isolate_keys(tmp_path, monkeypatch)
    # Simulate a pre-change record: hash + last4, no "key" field.
    legacy = "dd_live_LEGACYnoPlaintextStored9999wxyz"
    import json as _json
    store.write_text(_json.dumps({
        fa._hash_api_key(legacy): {
            "email": "old@arena.com", "label": "", "created": "2026-01-01T00:00:00",
            "last4": legacy[-4:],
        }
    }), encoding="utf-8")
    st = fa._user_api_key_status("old@arena.com")
    assert st["key"] == ""                          # nothing to reveal
    assert st["last4"] == legacy[-4:]

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

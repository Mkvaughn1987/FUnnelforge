"""Campaign create+launch API — Phase 1.

Spec: docs/superpowers/specs/2026-06-27-campaign-create-launch-api-design.md
Plan: docs/superpowers/plans/2026-06-27-campaign-create-launch-api.md
"""
import flowdrip_app as fa


def _isolate_keys(tmp_path, monkeypatch):
    """Point the API-key store at a temp file so tests never touch real data."""
    store = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: store)
    return store


# ── API key mint / resolve ─────────────────────────────────────────
def test_mint_then_resolve_returns_email(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com", label="cowork")
    assert key.startswith("dd_live_")
    assert fa._resolve_api_key(key) == "rep@arena.com"


def test_resolve_unknown_key_is_none(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    fa._mint_api_key("rep@arena.com")
    assert fa._resolve_api_key("dd_live_bogus") is None
    assert fa._resolve_api_key("") is None
    assert fa._resolve_api_key(None) is None


def test_plaintext_key_never_stored(tmp_path, monkeypatch):
    store = _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    raw = store.read_text(encoding="utf-8")
    assert key not in raw            # only the hash is persisted
    assert fa._hash_api_key(key) in raw

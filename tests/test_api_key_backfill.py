import json
import importlib.util
from pathlib import Path

import flowdrip_app as fa

_spec = importlib.util.spec_from_file_location(
    "backfill_api_key_plaintext",
    Path(__file__).resolve().parents[1] / "scripts" / "backfill_api_key_plaintext.py",
)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


def test_backfill_sets_key_on_matching_record(tmp_path, monkeypatch):
    store = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: store)
    plaintext = "dd_live_realKeyPlaintextValue1234abcd3gAU"
    store.write_text(json.dumps({
        fa._hash_api_key(plaintext): {
            "email": "mike@arena.com", "label": "", "created": "2026-07-17T00:00:00",
            "last4": plaintext[-4:],
        }
    }), encoding="utf-8")
    changed = backfill.backfill(plaintext)
    assert changed is True
    assert fa._load_api_keys()[fa._hash_api_key(plaintext)]["key"] == plaintext


def test_backfill_noop_when_hash_absent(tmp_path, monkeypatch):
    store = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: store)
    store.write_text(json.dumps({"someotherhash": {"email": "x@y.com"}}),
                     encoding="utf-8")
    assert backfill.backfill("dd_live_notInTheStoreAtAll0000zzzz") is False

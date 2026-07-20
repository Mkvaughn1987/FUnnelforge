"""One-off: write a known plaintext API key into its existing api_keys.json
record's `key` field (enables reveal+copy without regenerating).

Usage on the server:
    python3 scripts/backfill_api_key_plaintext.py dd_live_xxxxxxxx
The key is matched by sha256, so a wrong key simply no-ops. Backs up the
store to api_keys.json.bak before writing (atomic replace).
"""
import json
import sys

import flowdrip_app as fa


def backfill(plaintext: str) -> bool:
    """Set record['key']=plaintext for the record whose hash matches. Returns
    True if a record was updated, False if the hash is not present."""
    data = fa._load_api_keys()
    h = fa._hash_api_key(plaintext)
    if h not in data:
        return False
    data[h]["key"] = plaintext
    p = fa._api_keys_path()
    p.with_suffix(".json.bak").write_text(
        json.dumps(fa._load_api_keys(), indent=2), encoding="utf-8")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: backfill_api_key_plaintext.py <dd_live_key>")
        raise SystemExit(2)
    ok = backfill(sys.argv[1])
    print("updated" if ok else "no matching record (no-op)")

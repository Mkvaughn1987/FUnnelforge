"""Flat JSON-backed record stores for the OAuth layer.

Mirrors flowdrip_app.py's api_keys.json pattern: one JSON object per file,
keyed by id, written via tmp-file-then-replace so a crash mid-write never
corrupts the store.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class JsonStore:
    """A single flat {key: record} JSON file, safe for concurrent access
    within one process (the OAuth server is single-process)."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read().get(key)

    def put(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            data = self._read()
            data[key] = value
            self._write(data)

    def delete(self, key: str) -> None:
        with self._lock:
            data = self._read()
            if key in data:
                del data[key]
                self._write(data)

    def purge_expired(self, expires_field: str = "expires_at") -> None:
        """Drop any record whose expiry timestamp has passed. Refresh tokens
        (no expires_at) are left alone."""
        with self._lock:
            data = self._read()
            now = time.time()
            live = {
                k: v for k, v in data.items()
                if v.get(expires_field) is None or v[expires_field] > now
            }
            if len(live) != len(data):
                self._write(live)


def oauth_store_dir(data_dir: Path) -> Path:
    return data_dir / "mcp_oauth"

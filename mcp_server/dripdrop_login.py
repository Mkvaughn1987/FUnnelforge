"""DripDrop login verification, duplicated from flowdrip_app.py's
`_hash_password`/`_verify_password`/`_load_users`/`_authenticate_user`
(flowdrip_app.py:2330-2386) rather than imported, since importing the
60k-line app module here would trigger its NiceGUI app-level side effects.

Reads the same users.json (same DRIPDROP_DATA_DIR) the main app writes, so
any DripDrop account can log in here with no separate credential system.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _users_path(data_dir: Path) -> Path:
    return data_dir / "users.json"


def _load_users(data_dir: Path) -> dict:
    path = _users_path(data_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _verify_password(password: str, stored: str) -> bool:
    if ":" not in stored:
        return False
    salt, hashed = stored.split(":", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == hashed


def authenticate(data_dir: Path, email: str, password: str) -> bool:
    """True if email/password match an existing DripDrop account."""
    email = (email or "").lower().strip()
    if not email or not password:
        return False
    users = _load_users(data_dir)
    record = users.get(email)
    if not record:
        return False
    return _verify_password(password, record.get("password", ""))

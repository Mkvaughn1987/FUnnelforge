"""Talks to DripDrop's real /api/v1/* routes (flowdrip_app.py:5511-5754) on
behalf of an authenticated connector user.

Each MCP tool call arrives with only an email (the OAuth access token's
`subject` - see auth_provider.py / dripdrop_mcp.py). DripDrop's API itself
authenticates by per-user key (Authorization: Bearer <key> or X-API-Key), so
this module resolves email -> that user's own DripDrop API key by reading
the same api_keys.json flowdrip_app.py writes (keyed by sha256(key), not by
email - see `_user_api_key_status` at flowdrip_app.py:5042), then forwards
the request with that key attached. The user never types or sees the key;
they only ever authenticated as themselves via DripDrop's own login form
(dripdrop_login.py) during the connector's OAuth handshake.

Runs on the same droplet as the DripDrop app, so it talks to it over
loopback (DRIPDROP_API_BASE_URL, default http://127.0.0.1:8080) rather than
through the public Cloudflare-fronted domain - see the
dripdrop-local-session-api-headers memory for why that matters (Cloudflare
503s same-origin-only POSTs that arrive without Origin/Referer/UA; sending
those headers anyway makes this safe even if DRIPDROP_API_BASE_URL is ever
pointed at the public domain instead).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

DEFAULT_API_BASE_URL = "http://127.0.0.1:8080"
PUBLIC_ORIGIN = "https://dripdripdrop.ai"


class NoApiKeyError(Exception):
    """Raised when the authenticated DripDrop user has no API key on file."""


class DripDropApiError(Exception):
    """Raised when DripDrop's API itself returns an error response."""

    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self.body = body
        super().__init__(f"DripDrop API returned {status_code}: {body}")


def _api_keys_path(data_dir: Path) -> Path:
    return data_dir / "api_keys.json"


def _load_api_keys(data_dir: Path) -> dict:
    path = _api_keys_path(data_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_user_api_key(data_dir: Path, email: str) -> str:
    """Mirror of flowdrip_app.py's `_user_api_key_status`: the newest live
    key belonging to `email`, by plaintext value. Raises NoApiKeyError if the
    user hasn't generated a DripDrop API key yet (Settings -> API key in the
    app)."""
    target = (email or "").strip().lower()
    if not target:
        raise NoApiKeyError("no authenticated email")
    records = [
        r for r in _load_api_keys(data_dir).values()
        if (r.get("email") or "").strip().lower() == target
    ]
    if not records:
        raise NoApiKeyError(
            f"{email} has no DripDrop API key yet - generate one in the "
            "DripDrop app under Settings -> API key, then try again."
        )
    newest = max(records, key=lambda r: r.get("created", ""))
    key = newest.get("key", "")
    if not key:
        raise NoApiKeyError(
            f"{email}'s DripDrop API key was created before plaintext "
            "storage was added and can't be recovered - generate a new one "
            "in the DripDrop app under Settings -> API key."
        )
    return key


class DripDropClient:
    """One instance per tool call: resolves the caller's key, then makes a
    single request against DripDrop's real API."""

    def __init__(self, data_dir: Path, email: str, base_url: str | None = None):
        self.base_url = (base_url or os.environ.get("DRIPDROP_API_BASE_URL")
                          or DEFAULT_API_BASE_URL).rstrip("/")
        self.api_key = resolve_user_api_key(data_dir, email)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Origin": PUBLIC_ORIGIN,
            "Referer": f"{PUBLIC_ORIGIN}/",
            "User-Agent": "dripdrop-mcp-connector/1.0",
        }

    async def _raise_for_error(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise DripDropApiError(resp.status_code, body)

    async def create_campaign(self, spec: dict) -> dict:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/campaigns",
                json=spec,
                headers={**self._headers(), "Content-Type": "application/json"},
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def import_candidates(self, files: list[tuple[str, bytes]]) -> dict:
        upload_fields = [
            ("files", (fname, content)) for fname, content in files
        ]
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/candidates/import",
                files=upload_fields,
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def candidates_count(self) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/candidates/count",
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def candidates_search(self, q: str = "", status: str = "", limit: int = 20) -> dict:
        params: dict[str, str] = {}
        if q:
            params["q"] = q
        if status:
            params["status"] = status
        if limit:
            params["limit"] = str(limit)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/candidates/search",
                params=params,
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def campaign_types(self) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/campaign_types",
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def my_campaign_styles(self) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/campaign_styles",
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

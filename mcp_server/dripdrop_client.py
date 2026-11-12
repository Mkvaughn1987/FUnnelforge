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

    async def import_candidate_records(self, records: list[dict]) -> dict:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/candidates/records",
                json={"records": records},
                headers={**self._headers(), "Content-Type": "application/json"},
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

    async def campaigns_list(self) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/campaigns",
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def campaign_get(self, campaign_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/campaigns/{campaign_id}",
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def team_contacts(self, query: str, limit: int = 50) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/team_contacts",
                params={"q": query, "limit": limit},
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def skip_check(self, companies: list) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/skip_check",
                json={"companies": companies},
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def sales_runs_pending(self) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/sales_runs/pending",
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def sales_run_update(self, run_id: str, patch: dict) -> dict:
        # Generous timeout: posting 'sourced' is what kicks the server-side
        # build off, and it normalises every company and contact first.
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/sales_runs/{run_id}",
                json=patch,
                headers={**self._headers(), "Content-Type": "application/json"},
            )
        await self._raise_for_error(resp)
        return resp.json()

    # -- DD connector A: shared pages (2026-11-12) --------------------------
    # One method per /api/v1/dd/* page route; the structure tests pair each
    # MCP tool with one of these and each of these with a route.

    async def _conn_a_get(self, path: str, params: dict | None = None,
                          timeout: float = 60.0) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/dd/{path}",
                params={k: v for k, v in (params or {}).items() if v not in ("", None)},
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def _conn_a_post(self, path: str, body: dict, timeout: float = 60.0) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/dd/{path}",
                json=body,
                headers={**self._headers(), "Content-Type": "application/json"},
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def my_day(self, day: str = "") -> dict:
        return await self._conn_a_get("tasks", {"date": day})

    async def task_done(self, body: dict) -> dict:
        return await self._conn_a_post("tasks/done", body)

    async def call_briefing(self, body: dict) -> dict:
        # Writing a briefing runs a web search.
        return await self._conn_a_post("tasks/briefing", body, timeout=180.0)

    async def replies(self, action: str = "list", email: str = "") -> dict:
        if action == "list":
            return await self._conn_a_get("replies")
        # scan reads the inbox and draft calls the AI; both take a while.
        return await self._conn_a_post("replies", {"action": action, "email": email},
                                       timeout=180.0 if action in ("scan", "draft") else 60.0)

    async def contacts(self, list_name: str = "", q: str = "", limit: int = 50) -> dict:
        return await self._conn_a_get("contacts/search",
                                      {"list": list_name, "q": q, "limit": limit})

    async def import_contacts(self, contacts: list, list_name: str) -> dict:
        return await self._conn_a_post("contacts", {"contacts": contacts, "list": list_name},
                                       timeout=120.0)

    async def contact_lists(self, body: dict) -> dict:
        return await self._conn_a_post("contact_lists", body)

    async def campaign_contacts(self, body: dict) -> dict:
        # Adding queues every new contact's emails server-side.
        return await self._conn_a_post("campaigns/contacts", body, timeout=180.0)

    async def campaign_action(self, body: dict) -> dict:
        # launch queues every email; resume re-queues them.
        return await self._conn_a_post("campaigns/action", body, timeout=300.0)

    async def campaign_edit(self, body: dict) -> dict:
        # ai_rewrite / remember_style call the AI; a running campaign is
        # re-queued after the save.
        return await self._conn_a_post("campaigns/edit", body, timeout=180.0)

    async def send_preview(self, body: dict) -> dict:
        return await self._conn_a_post("send_preview", body, timeout=90.0)

    async def newsletters(self) -> dict:
        return await self._conn_a_get("newsletters")

    async def newsletter_create(self, body: dict) -> dict:
        return await self._conn_a_post("newsletters", body)

    async def newsletter_issue(self, body: dict) -> dict:
        # One AI-written issue, with web research.
        return await self._conn_a_post("newsletters/issue", body, timeout=300.0)

    async def newsletter_edit(self, body: dict) -> dict:
        return await self._conn_a_post("newsletters/edit", body)

    async def analytics(self, days: int = 0, campaign: str = "") -> dict:
        return await self._conn_a_get("analytics", {"days": days or "", "campaign": campaign},
                                      timeout=120.0)

    async def settings(self, update: dict | None = None) -> dict:
        if not update:
            return await self._conn_a_get("settings")
        return await self._conn_a_post("settings", update)

    async def mailboxes(self) -> dict:
        return await self._conn_a_get("mailboxes")

    async def dnc(self, body: dict | None = None, q: str = "") -> dict:
        if not body:
            return await self._conn_a_get("dnc", {"q": q})
        return await self._conn_a_post("dnc", body, timeout=120.0)

    async def campaign_styles(self, body: dict) -> dict:
        return await self._conn_a_post("campaign_styles", body)

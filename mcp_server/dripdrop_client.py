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
# Origin/Referer stamped on loopback API calls so Cloudflare-shaped request
# checks pass. Must be THIS instance's public origin — a white-label instance
# sending Arena's origin is misidentifying itself. Defaults to Arena's, so
# leaving it unset is a no-op there.
PUBLIC_ORIGIN = (os.environ.get("DRIPDROP_PUBLIC_ORIGIN")
                 or "https://dripdripdrop.ai").rstrip("/")


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
        # ThriveModal campaigns also build their Sales Assets PDFs in the call.
        async with httpx.AsyncClient(timeout=240.0) as client:
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

    # -- ThriveModal -------------------------------------------------------
    # One method per route. A tool without one of these is a tool that 404s at
    # call time with nothing in the code to show it would (see candidates_search,
    # 2026-08-27), which is why the test suite pairs them structurally.

    async def tm_import_contacts(self, records: list, list_name: str = "") -> dict:
        # Generous timeout: a pull can carry a few hundred records and the
        # server merges them into the saved list before answering.
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/tm/contacts",
                json={"records": records, "list": list_name},
                headers={**self._headers(), "Content-Type": "application/json"},
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def tm_audiences(self) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/tm/audiences",
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def tm_audience_preview(self, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/tm/audience_preview",
                json=body or {},
                headers={**self._headers(), "Content-Type": "application/json"},
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def tm_analytics(self, days: int = 0, campaign: str = "") -> dict:
        params = {}
        if days:
            params["days"] = str(days)
        if campaign:
            params["campaign"] = campaign
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/tm/analytics",
                params=params,
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def tm_mailboxes(self) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/tm/mailboxes",
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def tm_campaign_pdfs(self, body: dict) -> dict:
        # Building a PDF is an AI call per kind (run in parallel server-side).
        async with httpx.AsyncClient(timeout=240.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/tm/campaign_pdfs",
                json=body,
                headers={**self._headers(), "Content-Type": "application/json"},
            )
        await self._raise_for_error(resp)
        return resp.json()

    # -- ThriveModal: the rest of the app (2026-09-21) ---------------------

    async def _tm_get(self, path: str, params: dict | None = None,
                      timeout: float = 60.0) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/tm/{path}",
                params={k: v for k, v in (params or {}).items() if v not in ("", None)},
                headers=self._headers(),
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def _tm_post(self, path: str, body: dict, timeout: float = 60.0) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/tm/{path}",
                json=body,
                headers={**self._headers(), "Content-Type": "application/json"},
            )
        await self._raise_for_error(resp)
        return resp.json()

    async def tm_my_day(self, day: str = "") -> dict:
        return await self._tm_get("tasks", {"date": day})

    async def tm_task_done(self, body: dict) -> dict:
        return await self._tm_post("tasks/done", body)

    async def tm_replies(self, action: str = "list", email: str = "") -> dict:
        if action == "list":
            return await self._tm_get("replies")
        # scan reads the inbox and draft calls the AI; both take a while.
        return await self._tm_post("replies", {"action": action, "email": email},
                                   timeout=180.0 if action in ("scan", "draft") else 60.0)

    async def tm_contacts(self, list_name: str = "", q: str = "", limit: int = 50) -> dict:
        return await self._tm_get("contacts/search",
                                  {"list": list_name, "q": q, "limit": limit})

    async def tm_campaign_contacts(self, body: dict) -> dict:
        # Adding queues every new contact's emails server-side.
        return await self._tm_post("campaigns/contacts", body, timeout=180.0)

    async def tm_campaign_action(self, body: dict) -> dict:
        return await self._tm_post("campaigns/action", body, timeout=120.0)

    async def tm_send_preview(self, body: dict) -> dict:
        return await self._tm_post("send_preview", body, timeout=90.0)

    async def tm_newsletters(self) -> dict:
        return await self._tm_get("newsletters")

    async def tm_newsletter_create(self, body: dict) -> dict:
        return await self._tm_post("newsletters", body)

    async def tm_newsletter_issue(self, body: dict) -> dict:
        # One AI-written issue, with web research.
        return await self._tm_post("newsletters/issue", body, timeout=300.0)

    async def tm_sales_assets(self, body: dict | None = None) -> dict:
        if not body:
            return await self._tm_get("sales_assets")
        # A custom PDF is two AI calls (outline, then fill).
        return await self._tm_post("sales_assets", body, timeout=300.0)

    async def tm_saved_prompts(self, prompt_id: str = "") -> dict:
        return await self._tm_get("saved_prompts", {"id": prompt_id})

    async def tm_clients(self, body: dict | None = None) -> dict:
        if not body:
            return await self._tm_get("clients")
        return await self._tm_post("clients", body)

    async def tm_settings(self, update: dict | None = None) -> dict:
        if not update:
            return await self._tm_get("settings")
        return await self._tm_post("settings", update)

    async def tm_dnc(self, body: dict | None = None, q: str = "") -> dict:
        if not body:
            return await self._tm_get("dnc", {"q": q})
        return await self._tm_post("dnc", body, timeout=120.0)

    # ── connector group A (2026-09-21) begin ──
    # ── connector group A end ──


    # ── connector group B (2026-09-21) begin ──
    # ── connector group B end ──


    # ── connector group C (2026-09-21) begin ──
    # ── connector group C end ──


    # ── connector group D (2026-09-21) begin ──
    async def tm_call_briefing(self, body: dict) -> dict:
        # Writing a briefing runs a web search.
        return await self._tm_post("tasks/briefing", body, timeout=180.0)

    async def tm_newsletter_edit(self, body: dict) -> dict:
        return await self._tm_post("newsletters/edit", body)

    async def tm_pdf_edit(self, body: dict) -> dict:
        # revise is one AI call plus a re-render.
        return await self._tm_post("pdfs/edit", body, timeout=180.0)
    # ── connector group D end ──

"""mcp_server/dripdrop_client.py: the HTTP layer between MCP tools and
DripDrop's real /api/v1/candidates/* routes.

The MCP tool functions in dripdrop_mcp.py are thin pass-throughs (resolve
email -> call the matching DripDropClient method); the actual logic worth
pinning lives here:
  - resolve_user_api_key: email -> newest live key, NoApiKeyError cases.
  - candidates_search/candidates_get/candidates_match: correct query params
    / JSON bodies against the full ATS Talent Pool routes (no more/no less
    than what's set), and the required Origin/Referer/UA headers (needed to
    avoid Cloudflare 503s on same-origin-only routes - see the
    dripdrop-local-session-api-headers memory).
  - DripDropApiError propagation on non-2xx responses (JSON and non-JSON
    bodies alike).

No real network I/O: httpx.AsyncClient is monkeypatched onto a
httpx.MockTransport that inspects the outgoing request and returns a canned
response.
"""
import asyncio
import json

import httpx
import pytest

from mcp_server import dripdrop_client as dc


def _capture(monkeypatch, handler):
    """Patch dripdrop_client's httpx.AsyncClient so every request it makes
    is routed through `handler` instead of the network."""
    captured = []

    def wrapped_handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler(request)

    real_async_client = httpx.AsyncClient

    class _MockedAsyncClient(real_async_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(wrapped_handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(dc.httpx, "AsyncClient", _MockedAsyncClient)
    return captured


def _keys_file(tmp_path, records: dict):
    path = tmp_path / "api_keys.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


# ── resolve_user_api_key ────────────────────────────────────────────────

def test_resolve_key_no_file_raises(tmp_path):
    with pytest.raises(dc.NoApiKeyError):
        dc.resolve_user_api_key(tmp_path, "rep@arena.com")


def test_resolve_key_no_matching_email_raises(tmp_path):
    _keys_file(tmp_path, {
        "hash1": {"email": "someoneelse@arena.com", "key": "k1", "created": "2026-01-01"},
    })
    with pytest.raises(dc.NoApiKeyError):
        dc.resolve_user_api_key(tmp_path, "rep@arena.com")


def test_resolve_key_blank_email_raises(tmp_path):
    with pytest.raises(dc.NoApiKeyError):
        dc.resolve_user_api_key(tmp_path, "")


def test_resolve_key_legacy_no_plaintext_raises(tmp_path):
    _keys_file(tmp_path, {
        "hash1": {"email": "rep@arena.com", "key": "", "created": "2026-01-01"},
    })
    with pytest.raises(dc.NoApiKeyError):
        dc.resolve_user_api_key(tmp_path, "rep@arena.com")


def test_resolve_key_picks_newest_and_is_case_insensitive(tmp_path):
    _keys_file(tmp_path, {
        "hash1": {"email": "rep@arena.com", "key": "old-key", "created": "2026-01-01"},
        "hash2": {"email": "rep@arena.com", "key": "new-key", "created": "2026-06-01"},
    })
    assert dc.resolve_user_api_key(tmp_path, "REP@Arena.com") == "new-key"


# ── DripDropClient plumbing ─────────────────────────────────────────────

def _client(tmp_path, monkeypatch):
    _keys_file(tmp_path, {
        "hash1": {"email": "rep@arena.com", "key": "test-key", "created": "2026-01-01"},
    })
    return dc.DripDropClient(tmp_path, "rep@arena.com")


def test_headers_include_bearer_and_origin(tmp_path):
    client = _client(tmp_path, None)
    headers = client._headers()
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["Origin"] == dc.PUBLIC_ORIGIN
    assert headers["Referer"] == f"{dc.PUBLIC_ORIGIN}/"
    assert "User-Agent" in headers


def test_candidates_search_only_sends_set_params(tmp_path, monkeypatch):
    captured = _capture(monkeypatch, lambda req: httpx.Response(200, json={"results": []}))
    client = _client(tmp_path, monkeypatch)
    asyncio.run(client.candidates_search(q="cnc machinist"))
    req = captured[0]
    assert req.method == "GET"
    assert req.url.path == "/api/v1/candidates/search"
    params = dict(httpx.QueryParams(req.url.query))
    assert params == {"q": "cnc machinist", "limit": "20"}


def test_candidates_search_browse_mode_with_filters_and_cursor(tmp_path, monkeypatch):
    captured = _capture(monkeypatch, lambda req: httpx.Response(200, json={"results": []}))
    client = _client(tmp_path, monkeypatch)
    asyncio.run(client.candidates_search(
        state="CO", city="Denver", has_email=False,
        added_after="2026-01-01", limit=50, cursor=1234,
    ))
    params = dict(httpx.QueryParams(captured[0].url.query))
    assert params == {
        "state": "CO", "city": "Denver", "has_email": "false",
        "added_after": "2026-01-01", "limit": "50", "cursor": "1234",
    }


def test_candidates_get_hits_path(tmp_path, monkeypatch):
    captured = _capture(monkeypatch, lambda req: httpx.Response(200, json={"id": "ats_5"}))
    client = _client(tmp_path, monkeypatch)
    result = asyncio.run(client.candidates_get("ats_5"))
    assert captured[0].url.path == "/api/v1/candidates/ats_5"
    assert result == {"id": "ats_5"}


def test_candidates_match_builds_full_body(tmp_path, monkeypatch):
    captured = _capture(monkeypatch, lambda req: httpx.Response(200, json={"results": []}))
    client = _client(tmp_path, monkeypatch)
    asyncio.run(client.candidates_match(
        "Need a CNC machinist", title="CNC Machinist", location="Denver, CO",
        radius_miles=25.0, min_score=60, limit=10, cursor=7,
    ))
    req = captured[0]
    assert req.method == "POST"
    assert req.url.path == "/api/v1/candidates/match"
    body = json.loads(req.content)
    assert body == {
        "job_description": "Need a CNC machinist",
        "title": "CNC Machinist",
        "location": "Denver, CO",
        "radius_miles": 25.0,
        "min_score": 60,
        "limit": 10,
        "cursor": 7,
    }


def test_candidates_match_minimal_body_only_has_job_description(tmp_path, monkeypatch):
    captured = _capture(monkeypatch, lambda req: httpx.Response(200, json={"results": []}))
    client = _client(tmp_path, monkeypatch)
    asyncio.run(client.candidates_match("Need a welder"))
    body = json.loads(captured[0].content)
    assert body == {"job_description": "Need a welder", "limit": 20}


# ── error propagation ────────────────────────────────────────────────────

def test_json_error_response_raises_with_parsed_body(tmp_path, monkeypatch):
    _capture(monkeypatch, lambda req: httpx.Response(404, json={"error": "not found"}))
    client = _client(tmp_path, monkeypatch)
    with pytest.raises(dc.DripDropApiError) as exc_info:
        asyncio.run(client.candidates_get("ats_999"))
    assert exc_info.value.status_code == 404
    assert exc_info.value.body == {"error": "not found"}


def test_non_json_error_response_raises_with_text_body(tmp_path, monkeypatch):
    _capture(monkeypatch, lambda req: httpx.Response(503, text="upstream unavailable"))
    client = _client(tmp_path, monkeypatch)
    with pytest.raises(dc.DripDropApiError) as exc_info:
        asyncio.run(client.candidates_search(q="cnc"))
    assert exc_info.value.status_code == 503
    assert "upstream unavailable" in exc_info.value.body

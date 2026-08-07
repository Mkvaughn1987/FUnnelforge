# DripDrop MCP Connector — Design

## Problem

Teammates (Mike, Leigh, others) drive DripDrop campaign launches from claude.ai
(interactive Cowork sessions and headless/scheduled routines). The only way to
authenticate DripDrop's `/api/v1/campaigns` and `/api/v1/candidates/import`
today is a per-user API key, and Claude has a hard, non-negotiable safety rule
against taking a credential that arrived via chat/conversational context and
placing it into a request it composes. This makes the API effectively
unusable from claude.ai without a workaround (driving the authenticated UI by
element clicks, or hand-copying a key into a file for a local shell to read).

Neither workaround is durable, and neither works for a truly headless
scheduled run (no browser tab, no live session — see
`dripdrop-headless-cloud-network-wall` memory).

## Goal

A DripDrop **MCP connector**: each user authorizes it once via claude.ai
Settings → Connectors, using DripDrop's own login (email + password) as the
consent screen. No key is ever typed into chat. Works identically for
interactive Cowork sessions and headless scheduled routines, because the
credential is established once at connector-setup time and Claude stores
(and auto-refreshes) the resulting token afterward.

## Key finding that shaped this design

Claude's `static_headers` connector auth (paste a fixed API key into the
connector's own settings) is **organization-wide** — one admin enters one
shared credential for everyone. It is *not* a per-user "each teammate pastes
their own key" mechanism. Real per-user auth for a remote connector requires
OAuth (`oauth_dcr` — Dynamic Client Registration — "supported out of the box"
per Claude's connector docs). DripDrop already has the right building block
for the consent screen: its email/password login, checked against the same
`users.json` the main app's `login_page` (`flowdrip_app.py:53370`) uses —
re-implemented as a small standalone check (`dripdrop_login.authenticate`)
rather than reusing that page directly, since the page itself is wired to
NiceGUI's `app.storage.user` session and this connector needs a plain
request/response login form instead (see Architecture below).

## Architecture

A new, **separate, small server** — not added to `flowdrip_app.py` (60k+
lines already; keep this isolated and independently testable). Built on the
official MCP Python SDK's `mcp.server.mcpserver.server.MCPServer`, which —
given an `auth_server_provider` implementing `OAuthAuthorizationServerProvider`
— auto-generates the OAuth wire protocol: `/.well-known/oauth-authorization-server`,
`/.well-known/oauth-protected-resource`, `/authorize`, `/token`, `/register`
(DCR), PKCE validation, and the 401/`WWW-Authenticate` handshake on
unauthenticated tool calls. We only implement the provider's storage methods
(`authorize`, `load_authorization_code`, `exchange_authorization_code`,
`load_refresh_token`, `exchange_refresh_token`, `load_access_token`,
`revoke_token`, plus DCR's `get_client`/`register_client`) and the three
tools.

**New file:** `mcp_server/dripdrop_mcp.py` (own directory, own small module —
`auth_provider.py` for the OAuth provider, `dripdrop_client.py` for the
localhost forwarding calls, `dripdrop_mcp.py` for tool definitions + entry
point).

**Auth flow:**
1. Claude hits `/authorize` with a PKCE challenge. The provider stashes the
   pending OAuth request (client_id, redirect_uri, code_challenge, state,
   scopes, resource) under a short-lived `login_token` nonce, and redirects
   the browser to this connector's own `/login?login_token=...` page — a
   small standalone HTML form served by the connector itself, not DripDrop's
   main-app login page.
2. User logs in with their normal DripDrop email/password (same account,
   checked against the same `users.json` — no new credential system), via
   `dripdrop_login.authenticate()`.
3. On success, the provider mints a one-time `code`, maps it to the user's
   email, and redirects back to Claude's callback.
4. `/token` (`grant_type=authorization_code`) validates the PKCE verifier and
   the code, then mints an opaque `access_token` (+ `refresh_token`) mapped to
   that email. Tokens are **not** the user's DripDrop API key itself — just an
   opaque pointer to their email, resolved live on every tool call (see
   below). Refresh tokens rotate on use (public client, per MCP auth spec).
5. Token/code/client records persist as flat JSON files (atomic tmp+replace,
   matching the existing `_mint_api_key` pattern) under
   `$DRIPDROP_DATA_DIR/mcp_oauth/` on the same droplet — short-lived codes
   expire in ~2 min, access tokens in ~1 hour, refresh tokens don't expire
   until revoked.

**Tool calls → DripDrop API:**
Each tool call carries a bearer access token. The server resolves
`access_token → email` from its own token store, then reads
`api_keys.json` directly (same file `flowdrip_app.py` already writes via
`_mint_api_key`/`_load_api_keys` — same host, same `DRIPDROP_DATA_DIR`) to
find that email's **current live** DripDrop API key, and forwards the request
to `http://127.0.0.1:8080/api/v1/...` with `Authorization: Bearer <key>` set
to that key (the same header form `/api/v1/*` already accepts — see
`_resolve_api_key`). Key resolution happens fresh on every call rather than
being baked into the OAuth token, so:
- Regenerating your key in DripDrop Profile naturally revokes MCP connector
  access too (consistent with existing "regenerate kills every copy"
  semantics — no special-casing needed).
- A user who has never generated a DripDrop API key gets a clear tool-error
  (`{"error": "<email> has no DripDrop API key yet - generate one in the
  DripDrop app under Settings -> API key, then try again."}`) instead of a
  silent failure.

Calling over `127.0.0.1` sidesteps the Cloudflare WAF entirely, but the
client still sends `Origin`/`Referer`/`User-Agent` defensively (see
`dripdrop-local-session-api-headers` memory) so it stays safe even if
`DRIPDROP_API_BASE_URL` is ever pointed at the public domain instead.

**Tools exposed** (all three real endpoints confirmed present at `flowdrip_app.py:5511/5601/5628`):

| Tool | Wraps | Notes |
|---|---|---|
| `create_campaign` | `POST /api/v1/campaigns` | Full spec passthrough: `template`, `company`/`niche`, `website`, `industry`, `roles[]`, `location`, `candidates[]` (5x3 pinning), `contacts[]`/`contacts_csv`, `start_date`, `name`, `enroll_newsletter`. Returns the same JSON (`campaign_id`, `steps`, `contacts_queued`, `schedule`, etc.). |
| `import_candidates` | `POST /api/v1/candidates/import` | Tool input is `files: [{filename, content_base64}, ...]`. The connector base64-decodes each entry server-side and re-encodes as a real `multipart/form-data` body with repeated `files` fields — matching what the endpoint already expects — before forwarding. Returns the same `{requested, added, updated, skipped, results[]}` shape. |
| `candidates_count` | `GET /api/v1/candidates/count` | Read-only sanity/dry-run check — `{active, placed, on_hold, total}`. Confirms the connector is authorized before a real send. |

No other DripDrop surface is exposed. This isn't a general DripDrop API
proxy — just the two write actions Cowork agents need plus one read-only
smoke-test tool.

**Hosting:** same droplet (`134.199.237.206`), new subdomain
`mcp.dripdripdrop.ai`, new Caddy site block reverse-proxying to a new local
port (`8090`), new systemd unit `dripdrop-mcp.service` (mirrors
`dripdrop.service`'s shape — `EnvironmentFile=/opt/dripdrop/.env`,
`DRIPDROP_DATA_DIR=/opt/dripdrop/data`, `Restart=always`). Independent
process from the blue/green `dripdrop`/`dripdrop-green` app — an MCP server
crash or redeploy never affects the main app or vice versa.

## Explicitly out of scope

- No changes to `flowdrip_app.py` beyond what's already merged (the
  same-origin session-cookie fallback for `/api/v1/campaigns`,
  `_resolve_campaign_owner`) — that fix ships as-is, independently, since it
  helps a different case (live browser tab, no key at all) and this design
  doesn't touch or depend on it.
- No changes to the two unrelated in-progress edits already sitting in that
  file's working tree (soft-bounce threshold tuning, jway signoff line) —
  not touched, not bundled into any commit this work makes.
- No general-purpose DripDrop API proxy — only the 3 tools above.
- No enterprise/org-wide SSO integration — plain per-user OAuth against
  DripDrop's own login is sufficient at this team's scale.

## Rollout

Each teammate: claude.ai → Settings → Connectors → Add custom connector →
`https://mcp.dripdripdrop.ai/mcp` → redirected to the connector's own login
form → log in with their existing DripDrop account → connected. From then on,
both interactive and
scheduled/headless Cowork sessions can call the 3 tools with no key ever
appearing in chat. The `pipelineblast`/`candidateblast`/`DripDropAPI` skills'
current "raw key in a file" instructions get superseded by "use the DripDrop
MCP connector tools if available" — documentation follow-up, not part of this
build.

## Testing plan

- Unit-style: exercise the OAuth provider's storage methods directly
  (mint code → exchange → resolve token → refresh → rotate) against a temp
  data dir.
- Manual end-to-end: run the server locally against local DripDrop
  (`localhost:8080`), add it as a connector in a test claude.ai session,
  complete the login redirect, call `candidates_count` (safe, read-only)
  to confirm the whole chain resolves the right key.
- `create_campaign` / `import_candidates` are real-send-capable — smoke-test
  with a throwaway/test recipient, not a live list, before calling this
  deploy-ready.

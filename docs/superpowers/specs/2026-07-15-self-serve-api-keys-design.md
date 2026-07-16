# Self-Serve API Keys — Design

**Date:** 2026-07-15
**App:** DripDrop web app (`flowdrip_app.py`, NiceGUI)
**Status:** Approved, ready for implementation plan

## Problem

Today, a user's API key can only be minted by an operator running
`scripts/mint_api_key.py <email>` over SSH on the production server. Every request
(e.g. "make a key for Leigh Walker") requires Mike's manual intervention. We want
users to self-serve their own key from the app.

## Constraint that shapes the design

The server stores only `sha256(key) -> {email, label, created}` (see
`_mint_api_key`, ~L4871). The plaintext key is shown **once** at mint time and is
unrecoverable afterward. Therefore a "show me my existing key" button is
impossible — the UI can only **generate a fresh key and reveal it once** (same
model as GitHub / Stripe / OpenAI).

## Decisions

- **One key per user.** Users are expected to keep and reuse their key. The UI
  discourages needless regeneration.
- **Regenerate replaces.** Generating again permanently revokes the old key (after
  a confirm), then mints and reveals a new one. At most one active key per user.
- **Every logged-in user** can self-serve, on their own profile. Safe because the
  API only ever acts on the key owner's own account — a key's blast radius is that
  user's own campaigns.
- **Placement:** an "API Access" card on the My Profile page, directly below the
  existing Change Password action (~L49685), reusing the button→dialog pattern.

## Backend changes (`flowdrip_app.py`, near the API-key helpers ~L4851–4892)

1. **`_mint_api_key` — also persist `last4`.** Store the last 4 chars of the
   plaintext key in the record so the status line can render `dd_live_…VJJo`. The
   last 4 chars of a random token are not sensitive. Record becomes
   `{email, label, created, last4}`. Keys minted before this change lack `last4`
   and render as `••••`.
2. **`_user_api_key_status(email) -> dict | None`.** Scan `_load_api_keys()` for
   records whose `email` matches (case-insensitive, stripped); return the newest
   as `{created, last4, label}`, or `None` if the user has no key.
3. **`_revoke_api_keys(email) -> int`.** Atomically remove every hash owned by the
   email (same `tmp`-write-then-`replace` pattern as `_mint_api_key`); return the
   count removed. Used by regenerate.

The running web process reads/writes the same `api_keys.json` that the campaign
API auth (`_resolve_api_key`) reads, so a newly generated key is valid
**immediately** — no service restart.

## UI changes (My Profile page, new card below Change Password)

- **Status line:** `Active key · created Jul 15, 2026 · dd_live_…VJJo`, or
  `No API key yet`.
- **Primary button:** `Generate API key` when none exists, else `Regenerate`.
- **Reveal dialog** (once, immediately after minting):
  - Read-only, selectable field containing the full `dd_live_…` key.
  - **Copy** button via `navigator.clipboard.writeText`; if the clipboard API is
    unavailable (non-HTTPS/older browser), field stays selectable and the button
    shows a "Press Ctrl+C" fallback notify.
  - Bold warning: "You won't be able to see this key again — store it now."
  - 2-line usage snippet: `POST https://dripdripdrop.ai/api/v1/campaigns` and the
    `Authorization: Bearer <key>` header.
- **Regenerate flow:** confirm dialog ("This permanently disables your current key
  — anything using it will stop working. Continue?") → `_revoke_api_keys(email)` →
  `_mint_api_key(email)` → reveal dialog.
- Minting always uses `app.storage.user["email"]` — a user can only mint for
  themselves.

## Errors / edge cases

- Not authenticated → the profile page is already behind auth; no extra guard.
- Clipboard blocked → manual-copy fallback (above).
- Concurrent double-click on Generate → disable the button while the mint runs.
  The read-modify-write on the JSON is the same pattern existing code already
  uses; acceptable at this scale. Known low-risk limitation — no locking added.

## Testing (mirror `tests/test_campaign_api.py` style)

- `_mint_api_key` persists `last4` and it equals the plaintext's last 4 chars.
- `_revoke_api_keys` removes only the target email's hashes, leaves others intact,
  and returns the correct count.
- `_user_api_key_status` returns the newest record for an email, `None` when the
  user has no key, and matches case-insensitively.
- Minted key still resolves via `_resolve_api_key` (end-to-end mint→resolve).

## Out of scope (YAGNI)

- Multiple named keys per user.
- API usage stats / dashboards.
- A dedicated `/api` route and nav entry (easy upgrade path from this card later).

## Deployment note

Changes ship in `flowdrip_app.py`. Deploy is the existing
`scp flowdrip_app.py root@134.199.237.206:/opt/dripdrop/app/` +
`systemctl restart dripdrop` flow — **only on Mike's explicit go-ahead**, not
automatically.

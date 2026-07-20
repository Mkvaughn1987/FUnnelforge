# API Key Reveal & Copy — Design

**Date:** 2026-07-20
**Status:** Approved (Approach A, plaintext-at-rest, non-destructive migration)

## Problem

Each user (Mike + teammates) gets a per-user DripDrop API key that authorizes the
campaign create+launch API. The key's plaintext is shown **once**, in a reveal dialog at
mint time, then discarded — the server stores only `sha256(key)` + `last4`. After the
dialog is dismissed there is no way to see or copy the key again. The only recovery is
**Regenerate**, which revokes the old key and breaks anything using it. This is the root
cause of the recurring "can't find / dead key" churn and the scattered stale-key files.

Users need to **retrieve and copy their own key at any time** from the UI.

## Goal

On the API Access card (Profile → Personal Info), when a key exists, let the user reveal
and copy the **full** key without regenerating it.

## Non-Goals

- No multi-key-per-user management, labels UI, or key rotation scheduling.
- No encryption-at-rest (see Security decision).
- No mass regeneration of existing teammate keys (non-destructive migration).
- No change to how the API authenticates callers (still hash lookup).

## Current State (as-is)

- `api_keys.json`: `sha256(key) -> {email, label, created, last4}`. Plaintext never stored.
  (`flowdrip_app.py:4847-4924`)
- `_mint_api_key(email, label)` — generates `dd_live_ + token_urlsafe(32)`, stores hash
  record, returns plaintext once.
- `_user_api_key_status(email)` — returns `{created, last4, label}` (no plaintext).
- `_resolve_api_key(key)` — hash lookup → owner email. **Auth depends only on the hash.**
- API Access card UI: `flowdrip_app.py:50117-50243`. Reveal dialog with existing **Copy**
  button at `50148-50165`. Card is under the Personal Info profile section (available to
  all users; `_hide_if("personal")` is section-visibility, not an account gate).

## Design (Approach A)

### 1. Store plaintext at mint
`_mint_api_key` adds `"key": <plaintext>` to the record written to `api_keys.json`.
The `sha256(key)` remains the dict key, so `_resolve_api_key` and all auth are unchanged.

### 2. Return plaintext in status
`_user_api_key_status` includes `key` (full plaintext, or `""` when the stored record has
no `key` field — i.e. a legacy key minted before this change).

### 3. Card UI — reveal & copy
When `_api_status` exists and `_api_status["key"]` is non-empty, render the key in a
monospace, readonly field **masked by default** (`dd_live_••••••••<last4>`) with:
- **👁 Reveal / Hide** toggle (client-side; unmask the field).
- **📋 Copy API Key** button, reusing the clipboard helper pattern at `50148`.

When a key exists but `_api_status["key"]` is empty (legacy key), show a small muted note:
"Regenerate once to enable copy" instead of the reveal/copy controls. Regenerate button
stays in both cases.

### 4. Migration — non-destructive
- Legacy keys (no stored plaintext) cannot be shown; they display the note above and
  become copyable after the user regenerates once.
- **Mike's own key** is backfilled: a one-off script writes the known live plaintext
  (`dd_live_…3gAU`, from `dripdrop_key.txt`) into its existing record's `key` field,
  matched by `sha256`. No regeneration, nothing breaks. This is the ONLY key touched.
- Teammates' live keys are left alone.

### 5. Tests (`tests/test_*api*`)
- `_mint_api_key` stores `key` and the stored `key` hashes to the record's dict key.
- `_user_api_key_status` round-trips the plaintext for a fresh key.
- `_user_api_key_status` returns `key == ""` for a legacy record with no `key` field.
- `_resolve_api_key` still resolves owner by hash (regression).
Baseline against the 8 known pre-existing test failures.

## Security decision — plaintext, not encrypted

Storing the key plaintext in `api_keys.json` does not open a new class of exposure: the
same root-owned data dir already stores `smtp_password` and OAuth access/refresh tokens in
the clear (`dripdrop_config.json`). Encryption-at-rest (deriving a key from
`DRIPDROP_SECRET`) buys little while those neighbors are plaintext, and adds maintenance
surface. Rejected for this app. (Would be reconsidered if the app went multi-tenant.)

## Deployment

Single-file swap of `flowdrip_app.py` (gzip-stream upload + server `py_compile` + restart
the **live** service). Do NOT use `_deploy_zero_downtime.sh` (prod-drift: it also pushes
`ats.py`). Confirm which of blue (`dripdrop`, 8080) / green (`dripdrop-green`, 8081) is
live at deploy time — the pair flipped on 2026-07-17, blue is currently live. Backfill
migration runs once on the server against the live `api_keys.json`.

## Risks

- Plaintext key readable by anyone with data-dir/root access (accepted; consistent with
  existing secrets).
- Migration edits the shared `api_keys.json` — back it up first, atomic `os.replace`,
  and run when no mint/regenerate is racing.

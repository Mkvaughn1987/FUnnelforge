# Transient Send-Error Opt-Out Fix

**Date:** 2026-05-26
**Status:** Awaiting approval
**Scope:** Stop the server scheduler from permanently opting-out contacts (and cancelling their campaigns) when a send fails for a *transient* reason. Only clearly-permanent delivery failures should auto-opt-out. Plus a one-time migration to un-block contacts already wrongly blocked.

## Why

The Opt-Out List was filling with entries like `"Bounced: MS Graph send failed: Graph API error: HTTP 500"`. HTTP 500 is a transient Microsoft Graph server error — it does **not** mean the recipient address is bad. The scheduler's failure handler ([flowdrip_app.py:49669](../../../flowdrip_app.py#L49669)) treated **any** send failure as a bounce: it marked the email failed, cancelled all the contact's remaining campaign emails ("bounce protection"), and added the address to the user's DNC (opt-out) list. Valid contacts got permanently blocked because Graph hiccupped at send time.

Key insight: Graph's `sendMail` returns HTTP 202 on *acceptance*, not delivery. A genuinely invalid recipient almost always bounces back **asynchronously** as a Non-Delivery Report (NDR), which the reply monitor already detects and handles correctly ([flowdrip_app.py:50099](../../../flowdrip_app.py#L50099)). So the scheduler's synchronous failure path rarely sees a true permanent bounce — it mostly sees transient errors. Blanket-blocking on it is wrong.

## Goal

1. Classify each send error as **permanent** or **transient**.
2. Transient → retry up to 3 times, then mark the email failed. Never cancel the campaign, never opt-out the contact.
3. Permanent → keep today's behavior (mark failed, cancel siblings, add to DNC).
4. One-time migration: remove DNC entries that were created by transient errors so wrongly-blocked contacts can receive campaigns again.

## Non-goals

- Exponential backoff. A 60s tick × 3 attempts (~3 min) is enough for a typical 500 blip. Retries reuse the existing tick cadence.
- Changing the NDR bounce detector ([50099](../../../flowdrip_app.py#L50099)) — it correctly blocks real async bounces and is untouched.
- Changing the manual "retry failed" path (`retry_failed`, [flowdrip_app.py:4495](../../../flowdrip_app.py#L4495)) or any UI.
- Distinguishing transient sub-types (rate-limit vs server-error vs token). They all retry the same way.

## Component 1 — `_classify_send_error(err: str) -> str`

New module-level **pure function**. Returns `"permanent"` or `"transient"`. Lives next to the scheduler helpers in `flowdrip_app.py`.

```python
_PERMANENT_SEND_MARKERS = (
    "errorinvalidrecipients",
    "invalidrecipients",
    "recipientnotfound",
    "recipient not found",
    "mailbox not found",
    "mailbox unavailable",
    "mailbox does not exist",
    "no such user",
    "address rejected",
    "550",
    "551",
    "553",
    "5.1.1",
)

def _classify_send_error(err: str) -> str:
    """Classify a send-failure string as 'permanent' or 'transient'.

    Permanent = the recipient address is bad and retrying won't help
    (invalid recipient, mailbox not found, SMTP 55x). These should
    opt-out the contact and cancel their campaign.

    Transient = a server / network / auth hiccup that says nothing
    about the recipient (HTTP 500/502/503/504, 429 throttling,
    timeouts, expired/revoked tokens, "No email provider configured").
    These should be retried, never opt-out the contact.

    Unknown errors default to TRANSIENT — it's far safer to retry an
    email than to wrongly opt-out a valid contact.
    """
    e = (err or "").lower()
    for marker in _PERMANENT_SEND_MARKERS:
        if marker in e:
            return "permanent"
    return "transient"
```

**Edge note:** `"550"` / `"551"` etc. are matched as plain substrings. A transient error string is very unlikely to contain a bare `"550"`, and the HTTP transient codes we care about (500/502/503/504) do not contain `"550"`. Acceptable.

## Component 2 — rewrite the scheduler failure branch

In `_server_scheduler_tick`, the `else:` branch after a failed `_server_send_one` (currently [flowdrip_app.py:49669-49705](../../../flowdrip_app.py#L49669)) becomes:

```python
else:
    cls = _classify_send_error(err)
    if cls == "transient":
        _rc = int(item.get("retry_count", 0)) + 1
        item["retry_count"] = _rc
        item["last_transient_error"] = err[:200]
        if _rc >= _MAX_SEND_RETRIES:   # _MAX_SEND_RETRIES = 3
            item["status"] = "failed"
            item["failed_at"] = datetime.now().isoformat()
            item["error"] = f"Gave up after {_rc} transient failures: {err[:160]}"
            total_failed += 1
            print(f"[ServerSend] ✗ {item.get('to')}: gave up after "
                  f"{_rc} transient attempts: {err}", flush=True)
        else:
            # Leave status == "pending" so this item is due again next
            # tick (~60s). No campaign cancel, no DNC — the contact is
            # not at fault.
            print(f"[ServerSend] ↻ {item.get('to')}: transient fail "
                  f"(attempt {_rc}/{_MAX_SEND_RETRIES}), will retry: {err}", flush=True)
        changed = True
        time.sleep(_SERVER_INTER_EMAIL_PAUSE)
        continue   # skip the permanent-bounce handling below

    # cls == "permanent" — real bad address. Keep existing behavior:
    item["status"] = "failed"
    item["failed_at"] = datetime.now().isoformat()
    item["error"] = err[:200]
    total_failed += 1
    print(f"[ServerSend] ✗ {item.get('to')}: {err}", flush=True)
    # ...existing bounce-protection sibling cancel + DNC add, unchanged...
```

Notes:
- `_MAX_SEND_RETRIES = 3` defined as a module constant next to `_SERVER_SEND_INTERVAL`.
- A retried item stays `"pending"` with its original `send_dt` (already in the past), so it's naturally re-attempted on the next tick. No `send_dt` mutation.
- The daily-send-limit accounting counts `status == "sent"`, so retries of a not-yet-sent item don't consume budget incorrectly.
- Bounce-protection (sibling cancel) and DNC add happen **only** on the permanent branch.

## Component 3 — one-time un-block migration

Standalone script `_unblock_transient_optouts.py` at repo root (sibling of the existing `_deploy_*` / `_full_audit.py` scripts). **Not imported by the app** — run once on the server.

Pure predicate (testable, also importable from tests):

```python
def _is_transient_optout_reason(reason: str) -> bool:
    """True if a DNC entry was created by a transient send failure
    (so it should be un-blocked). Matches the reason strings the
    scheduler wrote: "Bounced: MS Graph send failed: ..." and
    "Bounced: Gmail send failed: ...". Does NOT match real bounces
    ("Bounced (NDR): ...") or opt-out replies ("Auto-detected ...")."""
    r = (reason or "").strip().lower()
    return (r.startswith("bounced: ms graph send failed")
            or r.startswith("bounced: gmail send failed"))
```

Script behavior:
- Resolve the users root: `/opt/dripdrop/data/users` (override via argv[1] for local testing).
- For each `*/dnc_list.json`: load, partition entries by `_is_transient_optout_reason(entry.get("reason",""))`, write back the kept entries (atomic temp-file replace), print `user — removed N: <emails>`.
- Print a grand total at the end.
- Read-only dry-run by default; `--apply` performs the writes. (Safety: see what will change before changing it.)

Decision (per brainstorm): remove **all** `"Bounced: …send failed"` entries. Any genuinely-bad address among them will simply re-block on its next send attempt — via the new permanent classifier if synchronous, or via the NDR detector if asynchronous.

## Component 4 — tests (TDD)

`tests/test_send_error_classifier.py`:
- `_classify_send_error` → `"transient"` for: `"MS Graph send failed: Graph API error: HTTP 500"`, `"...HTTP 503"`, `"...HTTP 429"`, `"Gmail send failed: timed out"`, `"Microsoft connection expired or consent revoked..."`, `"No email provider configured..."`, `""` (empty), `"some unrecognized error"`.
- `_classify_send_error` → `"permanent"` for: `"Graph API error: ErrorInvalidRecipients"`, `"550 5.1.1 mailbox not found"`, `"RecipientNotFound"`, `"...address rejected..."`.
- `_is_transient_optout_reason` → `True` for `"Bounced: MS Graph send failed: Graph API error: HTTP 500"` and `"Bounced: Gmail send failed: ..."`; `False` for `"Bounced (NDR): Undeliverable: ..."`, `"Auto-detected opt-out from reply"`, `""`.

(The scheduler-branch rewrite itself isn't directly unit-tested — it's UI/loop glue. The two pure helpers carry the logic and are fully covered.)

## Files changed

- `flowdrip_app.py` — add `_MAX_SEND_RETRIES` constant, `_PERMANENT_SEND_MARKERS`, `_classify_send_error`; rewrite the failure branch in `_server_scheduler_tick`.
- `_unblock_transient_optouts.py` — new one-time migration script (repo root).
- `tests/test_send_error_classifier.py` — new tests.

## Rollout

1. Land code + tests, deploy via `_deploy_zero_downtime.sh`.
2. Run `python _unblock_transient_optouts.py /opt/dripdrop/data/users` (dry-run) on the server, eyeball the report, then `--apply`.
3. Verify the Opt-Out List no longer shows the wrongly-blocked addresses and confirm new transient failures retry instead of blocking (watch journal for `↻ ... will retry`).

## Verification

- Unit tests pass (`pytest tests/test_send_error_classifier.py`).
- Live: simulate or wait for a transient failure; confirm journal shows `↻ ... transient fail (attempt n/3), will retry` and the contact is NOT added to DNC.
- Migration dry-run report matches expectations before `--apply`; after apply, the previously-blocked contacts are gone from the Opt-Out List.

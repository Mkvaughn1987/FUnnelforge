# Transient Send-Error Opt-Out Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the server email scheduler from permanently opting-out contacts (and cancelling their campaigns) when a send fails for a transient reason; retry transient failures instead, and un-block contacts already wrongly blocked.

**Architecture:** Add a pure `_classify_send_error()` helper that labels each send-failure string `"permanent"` or `"transient"`. Rewrite the scheduler's failure branch so transient errors retry up to 3 times (then mark failed, no cancel/no DNC) while permanent errors keep today's cancel + DNC behavior. A standalone one-time migration script removes the DNC entries that transient errors wrongly created.

**Tech Stack:** Python 3.11, NiceGUI app (`flowdrip_app.py`), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-26-transient-send-error-optout-fix-design.md`

---

## File Structure

- `flowdrip_app.py` — add module constants `_MAX_SEND_RETRIES`, `_PERMANENT_SEND_MARKERS` and pure function `_classify_send_error()` next to the scheduler config (~line 49435–49437); rewrite the failure branch of `_server_scheduler_tick` (currently lines 49669–49705).
- `_unblock_transient_optouts.py` — NEW repo-root one-time migration script. Holds the pure predicate `_is_transient_optout_reason()` plus a `main()` that walks the users dir, dry-run by default, `--apply` to write.
- `tests/test_send_error_classifier.py` — NEW unit tests for `_classify_send_error` (imported from `flowdrip_app`) and `_is_transient_optout_reason` (imported from `_unblock_transient_optouts`).

---

## Task 1: Send-error classifier + constants

**Files:**
- Modify: `flowdrip_app.py:49435-49437` (insert constants + function right after `_SERVER_INTER_EMAIL_PAUSE`)
- Test: `tests/test_send_error_classifier.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_send_error_classifier.py`:

```python
"""Unit tests for the send-error classifier and the transient-optout
predicate used by the 2026-05-26 opt-out fix.

Spec: docs/superpowers/specs/2026-05-26-transient-send-error-optout-fix-design.md

Why this matters: the server scheduler used to opt-out a contact on
ANY send failure, so a transient Graph HTTP 500 permanently blocked
valid addresses. _classify_send_error draws the line between "retry"
and "really block".
"""
import flowdrip_app as fa


def test_transient_http_server_errors():
    """5xx server errors say nothing about the recipient — retry."""
    for err in (
        "MS Graph send failed: Graph API error: HTTP 500",
        "MS Graph send failed: Graph API error: HTTP 502",
        "Gmail send failed: Graph API error: HTTP 503",
        "MS Graph send failed: Graph API error: HTTP 504",
    ):
        assert fa._classify_send_error(err) == "transient", err


def test_transient_rate_limit_timeout_and_auth():
    """429 throttling, timeouts, token/provider problems are transient."""
    for err in (
        "MS Graph send failed: Graph API error: HTTP 429",
        "Gmail send failed: timed out",
        "MS Graph send failed: ReadTimeout",
        "Microsoft connection expired or consent revoked. Reconnect in Email & AI Setup.",
        "No email provider configured  -  connect Microsoft or Gmail in Email & AI Setup.",
    ):
        assert fa._classify_send_error(err) == "transient", err


def test_unknown_and_empty_default_to_transient():
    """Defaulting unknown errors to transient means we never wrongly
    opt-out a valid contact on an unrecognized error string."""
    assert fa._classify_send_error("some unrecognized error") == "transient"
    assert fa._classify_send_error("") == "transient"
    assert fa._classify_send_error(None) == "transient"


def test_permanent_invalid_recipient_markers():
    """Recipient-is-bad signals SHOULD block."""
    for err in (
        "MS Graph send failed: Graph API error: ErrorInvalidRecipients",
        "Graph API error: RecipientNotFound",
        "550 5.1.1 mailbox not found",
        "SMTP 553 mailbox unavailable",
        "Delivery failed: address rejected",
        "Gmail send failed: no such user here",
    ):
        assert fa._classify_send_error(err) == "permanent", err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_send_error_classifier.py -v`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_classify_send_error'`

- [ ] **Step 3: Write the constants + function**

In `flowdrip_app.py`, immediately AFTER line 49436 (`_SERVER_INTER_EMAIL_PAUSE = 2  # seconds between individual emails`) and BEFORE the blank lines preceding `def _resolve_body_from_campaign`, insert:

```python
_MAX_SEND_RETRIES = 3  # transient send failures retried this many times before giving up

# Substrings (lowercased) that mean the RECIPIENT address is bad and
# retrying won't help — these SHOULD opt-out the contact + cancel their
# campaign. Everything else is treated as transient (server/network/auth
# hiccup) and retried. See _classify_send_error.
_PERMANENT_SEND_MARKERS = (
    "errorinvalidrecipients",
    "invalidrecipients",
    "recipientnotfound",
    "recipient not found",
    "mailbox not found",
    "mailbox unavailable",
    "does not exist",
    "no such user",
    "address rejected",
    "550",
    "551",
    "553",
    "5.1.1",
    "5.1.10",
)


def _classify_send_error(err: str) -> str:
    """Classify a send-failure string as 'permanent' or 'transient'.

    Permanent = the recipient address is bad and retrying won't help
    (invalid recipient, mailbox not found, SMTP 55x). Caller should
    opt-out the contact and cancel their campaign.

    Transient = a server / network / auth hiccup that says nothing
    about the recipient (HTTP 500/502/503/504, 429 throttling,
    timeouts, expired/revoked tokens, "No email provider configured").
    Caller should retry, never opt-out the contact.

    Unknown errors default to TRANSIENT — it's far safer to retry an
    email than to wrongly opt-out a valid contact.
    """
    e = (err or "").lower()
    for marker in _PERMANENT_SEND_MARKERS:
        if marker in e:
            return "permanent"
    return "transient"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_send_error_classifier.py -v`
Expected: PASS (4 tests in this file so far — the predicate tests come in Task 3)

- [ ] **Step 5: Syntax-check the app file**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py tests/test_send_error_classifier.py
git commit -m "feat(send): classify send errors as permanent vs transient"
```

---

## Task 2: Rewrite the scheduler failure branch

**Files:**
- Modify: `flowdrip_app.py:49669-49705` (the `else:` branch after a failed `_server_send_one`)

This task has no new unit test — the branch is loop/IO glue inside `_server_scheduler_tick`. The logic it depends on (`_classify_send_error`) is fully tested in Task 1. Verification is the syntax check plus a manual reading against the spec.

- [ ] **Step 1: Replace the failure branch**

In `flowdrip_app.py`, the current code (lines 49669–49707) is:

```python
            else:
                item["status"] = "failed"
                item["failed_at"] = datetime.now().isoformat()
                item["error"] = err[:200]
                total_failed += 1
                print(f"[ServerSend] ✗ {item.get('to')}: {err}", flush=True)
                # ── Bounce protection: cancel all remaining pending emails
                # for this contact in this campaign. Sending to a known-bad
                # address again tanks sender reputation.
                _bounce_to = item.get("to", "").lower().strip()
                _bounce_camp = item.get("campaign", "")
                if _bounce_to and _bounce_camp:
                    _cancelled = 0
                    for other in queue:
                        if (other.get("status") == "pending"
                                and other.get("to", "").lower().strip() == _bounce_to
                                and other.get("campaign", "") == _bounce_camp
                                and other is not item):
                            other["status"] = "cancelled"
                            other["cancelled_at"] = datetime.now().isoformat()
                            other["cancel_reason"] = "bounce_protection"
                            _cancelled += 1
                    if _cancelled:
                        print(f"[ServerSend] Bounce protect: cancelled {_cancelled} pending email(s) for {_bounce_to} in '{_bounce_camp}'", flush=True)
                    # Add bounced address to user's DNC list
                    try:
                        _dnc_path = user_dir / "dnc_list.json"
                        _dnc = []
                        if _dnc_path.exists():
                            try: _dnc = json.loads(_dnc_path.read_text(encoding="utf-8"))
                            except Exception: _dnc = []
                        if not any(d.get("email", "").lower() == _bounce_to for d in _dnc):
                            _dnc.append({"email": _bounce_to, "added": datetime.now().isoformat(), "reason": f"Bounced: {err[:100]}"})
                            _dnc_path.write_text(json.dumps(_dnc, indent=2), encoding="utf-8")
                            print(f"[ServerSend] Added {_bounce_to} to DNC (bounce)", flush=True)
                    except Exception as dnc_err:
                        print(f"[ServerSend] DNC write error: {dnc_err}", flush=True)
            changed = True
            time.sleep(_SERVER_INTER_EMAIL_PAUSE)
```

Replace ONLY the `else:` block (lines 49669–49705) — i.e. everything from `            else:` down to and including the `print(f"[ServerSend] DNC write error: {dnc_err}", flush=True)` line — with the following. Leave the trailing `            changed = True` / `            time.sleep(_SERVER_INTER_EMAIL_PAUSE)` two lines exactly as they are (do not duplicate them):

```python
            else:
                # Decide whether this failure means the address is bad
                # (permanent → opt-out + cancel) or just a server/network/
                # auth hiccup (transient → retry up to _MAX_SEND_RETRIES).
                # Real invalid-recipient bounces mostly arrive later as
                # NDRs, which the reply monitor handles separately.
                if _classify_send_error(err) == "transient":
                    _rc = int(item.get("retry_count", 0)) + 1
                    item["retry_count"] = _rc
                    item["last_transient_error"] = err[:200]
                    if _rc >= _MAX_SEND_RETRIES:
                        item["status"] = "failed"
                        item["failed_at"] = datetime.now().isoformat()
                        item["error"] = f"Gave up after {_rc} transient failures: {err[:160]}"
                        total_failed += 1
                        print(f"[ServerSend] ✗ {item.get('to')}: gave up after "
                              f"{_rc} transient attempts: {err}", flush=True)
                    else:
                        # Stay "pending" so this item is due again next tick
                        # (~60s). No campaign cancel, no DNC — the contact is
                        # not at fault.
                        print(f"[ServerSend] ↻ {item.get('to')}: transient fail "
                              f"(attempt {_rc}/{_MAX_SEND_RETRIES}), will retry: {err}",
                              flush=True)
                    changed = True
                    time.sleep(_SERVER_INTER_EMAIL_PAUSE)
                    continue

                # Permanent failure — the address is bad. Mark failed,
                # cancel the contact's remaining campaign emails, and
                # opt them out so we never hit the bad address again.
                item["status"] = "failed"
                item["failed_at"] = datetime.now().isoformat()
                item["error"] = err[:200]
                total_failed += 1
                print(f"[ServerSend] ✗ {item.get('to')}: {err}", flush=True)
                # ── Bounce protection: cancel all remaining pending emails
                # for this contact in this campaign. Sending to a known-bad
                # address again tanks sender reputation.
                _bounce_to = item.get("to", "").lower().strip()
                _bounce_camp = item.get("campaign", "")
                if _bounce_to and _bounce_camp:
                    _cancelled = 0
                    for other in queue:
                        if (other.get("status") == "pending"
                                and other.get("to", "").lower().strip() == _bounce_to
                                and other.get("campaign", "") == _bounce_camp
                                and other is not item):
                            other["status"] = "cancelled"
                            other["cancelled_at"] = datetime.now().isoformat()
                            other["cancel_reason"] = "bounce_protection"
                            _cancelled += 1
                    if _cancelled:
                        print(f"[ServerSend] Bounce protect: cancelled {_cancelled} pending email(s) for {_bounce_to} in '{_bounce_camp}'", flush=True)
                    # Add bounced address to user's DNC list
                    try:
                        _dnc_path = user_dir / "dnc_list.json"
                        _dnc = []
                        if _dnc_path.exists():
                            try: _dnc = json.loads(_dnc_path.read_text(encoding="utf-8"))
                            except Exception: _dnc = []
                        if not any(d.get("email", "").lower() == _bounce_to for d in _dnc):
                            _dnc.append({"email": _bounce_to, "added": datetime.now().isoformat(), "reason": f"Bounced: {err[:100]}"})
                            _dnc_path.write_text(json.dumps(_dnc, indent=2), encoding="utf-8")
                            print(f"[ServerSend] Added {_bounce_to} to DNC (bounce)", flush=True)
                    except Exception as dnc_err:
                        print(f"[ServerSend] DNC write error: {dnc_err}", flush=True)
```

Important about control flow: the transient branch ends with `changed = True` / `time.sleep(_SERVER_INTER_EMAIL_PAUSE)` / `continue`, which jumps to the next `item`. The permanent branch falls through to the loop's existing trailing `changed = True` / `time.sleep(_SERVER_INTER_EMAIL_PAUSE)` (the two lines after the old block). Do not add a second copy of those two trailing lines for the permanent path.

- [ ] **Step 2: Syntax-check the app file**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Confirm the classifier tests still pass (regression guard)**

Run: `python -m pytest tests/test_send_error_classifier.py -v`
Expected: PASS

- [ ] **Step 4: Read the diff against the spec**

Run: `git diff flowdrip_app.py`
Confirm by eye:
- Transient path: increments `retry_count`, sets `last_transient_error`, stays `pending` until `>= 3`, then `failed`. NO sibling-cancel, NO DNC append. Ends with `continue`.
- Permanent path: unchanged cancel + DNC logic.
- The trailing `changed = True` / `time.sleep(...)` appears exactly once after the `else` block.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "fix(send): retry transient send failures instead of opting-out the contact"
```

---

## Task 3: One-time un-block migration script

**Files:**
- Create: `_unblock_transient_optouts.py` (repo root)
- Test: `tests/test_send_error_classifier.py` (append predicate tests)

- [ ] **Step 1: Write the failing predicate test**

Append to `tests/test_send_error_classifier.py`:

```python
import _unblock_transient_optouts as ubt


def test_predicate_matches_transient_send_failures():
    """Entries the scheduler wrote for transient send failures should
    be un-blocked. The stored reason is f"Bounced: {err[:100]}" where
    err began "MS Graph send failed" / "Gmail send failed"."""
    assert ubt._is_transient_optout_reason(
        "Bounced: MS Graph send failed: Graph API error: HTTP 500") is True
    assert ubt._is_transient_optout_reason(
        "Bounced: Gmail send failed: timed out") is True


def test_predicate_preserves_real_bounces_and_optouts():
    """Real NDR bounces and reply-driven opt-outs must NOT be removed."""
    assert ubt._is_transient_optout_reason(
        "Bounced (NDR): Undeliverable: Scorecard for ACME") is False
    assert ubt._is_transient_optout_reason(
        "Auto-detected opt-out from reply") is False
    assert ubt._is_transient_optout_reason("Manual") is False
    assert ubt._is_transient_optout_reason("") is False
    assert ubt._is_transient_optout_reason(None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_send_error_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '_unblock_transient_optouts'`

- [ ] **Step 3: Create the migration script**

Create `_unblock_transient_optouts.py`:

```python
#!/usr/bin/env python3
"""One-time migration: un-block contacts that were wrongly opted-out by
TRANSIENT send failures (e.g. "Bounced: MS Graph send failed: Graph API
error: HTTP 500"). Those are not real bounces — the recipient address is
fine; Graph/Gmail just hiccupped at send time.

Real NDR bounces ("Bounced (NDR): ...") and reply-driven opt-outs
("Auto-detected opt-out from reply") are preserved.

Usage:
    python _unblock_transient_optouts.py [USERS_DIR]            # dry-run
    python _unblock_transient_optouts.py [USERS_DIR] --apply    # write

USERS_DIR defaults to /opt/dripdrop/data/users (the live server layout).
Pass a local path as the first arg when testing.

Spec: docs/superpowers/specs/2026-05-26-transient-send-error-optout-fix-design.md
"""
import json
import sys
from pathlib import Path

DEFAULT_USERS_DIR = "/opt/dripdrop/data/users"


def _is_transient_optout_reason(reason: str) -> bool:
    """True if a DNC entry was created by a transient send failure and
    should be un-blocked. Matches the scheduler's stored reason strings:
    "Bounced: MS Graph send failed: ..." and "Bounced: Gmail send failed: ...".
    Does NOT match real bounces ("Bounced (NDR): ...") or opt-out replies."""
    r = (reason or "").strip().lower()
    return (r.startswith("bounced: ms graph send failed")
            or r.startswith("bounced: gmail send failed"))


def _process_user(dnc_path: Path, apply: bool) -> list:
    """Return the list of removed entries for one user's dnc_list.json.
    Writes the kept entries back only when apply=True."""
    try:
        entries = json.loads(dnc_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ! skip {dnc_path}: unreadable ({e})")
        return []
    if not isinstance(entries, list):
        return []
    removed = [e for e in entries
               if _is_transient_optout_reason(e.get("reason", ""))]
    if removed and apply:
        kept = [e for e in entries
                if not _is_transient_optout_reason(e.get("reason", ""))]
        tmp = dnc_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(kept, indent=2), encoding="utf-8")
        tmp.replace(dnc_path)
    return removed


def main(argv) -> int:
    args = [a for a in argv if not a.startswith("--")]
    apply = "--apply" in argv
    users_dir = Path(args[0]) if args else Path(DEFAULT_USERS_DIR)
    if not users_dir.exists():
        print(f"Users dir not found: {users_dir}")
        return 1

    mode = "APPLY (writing changes)" if apply else "DRY-RUN (no changes)"
    print(f"Un-block transient opt-outs — {mode}")
    print(f"Scanning: {users_dir}\n")

    total_removed = 0
    for user_dir in sorted(users_dir.iterdir()):
        if not user_dir.is_dir():
            continue
        dnc_path = user_dir / "dnc_list.json"
        if not dnc_path.exists():
            continue
        removed = _process_user(dnc_path, apply)
        if removed:
            total_removed += len(removed)
            emails = ", ".join(e.get("email", "?") for e in removed)
            print(f"{user_dir.name} — removed {len(removed)}: {emails}")

    print(f"\nTotal entries {'removed' if apply else 'to remove'}: {total_removed}")
    if not apply and total_removed:
        print("Re-run with --apply to write the changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_send_error_classifier.py -v`
Expected: PASS (all classifier + predicate tests)

- [ ] **Step 5: Smoke-test the script against a temp fixture**

Run:

```bash
python - <<'PY'
import json, tempfile, subprocess, sys
from pathlib import Path
root = Path(tempfile.mkdtemp())
u = root / "alice@example.com"; u.mkdir()
(u / "dnc_list.json").write_text(json.dumps([
    {"email": "good@vance.com", "reason": "Bounced: MS Graph send failed: Graph API error: HTTP 500"},
    {"email": "bad@x.com", "reason": "Bounced (NDR): Undeliverable: Scorecard"},
    {"email": "optout@y.com", "reason": "Auto-detected opt-out from reply"},
]), encoding="utf-8")
# dry-run
print("--- DRY RUN ---")
subprocess.run([sys.executable, "_unblock_transient_optouts.py", str(root)])
# apply
print("--- APPLY ---")
subprocess.run([sys.executable, "_unblock_transient_optouts.py", str(root), "--apply"])
left = json.loads((u / "dnc_list.json").read_text())
assert {e["email"] for e in left} == {"bad@x.com", "optout@y.com"}, left
print("OK — only the transient entry removed")
PY
```

Expected: dry-run reports `removed 1: good@vance.com`, apply removes it, final assert prints `OK — only the transient entry removed`.

- [ ] **Step 6: Commit**

```bash
git add _unblock_transient_optouts.py tests/test_send_error_classifier.py
git commit -m "feat(migration): one-time un-block of transient-error opt-outs"
```

---

## Task 4: Full test sweep + final commit

**Files:** none (verification only)

- [ ] **Step 1: Run the new test file**

Run: `python -m pytest tests/test_send_error_classifier.py -v`
Expected: PASS (all tests)

- [ ] **Step 2: Run the broader suite to check for regressions**

Run: `python -m pytest tests/ -q --tb=line`
Expected: No NEW failures vs. the known-failing baseline. (Pre-existing failures unrelated to this change: `test_newsletter_cta_single_button.py` (3), `test_newsletter_masthead_fallback.py` (1). Anything else failing is a regression to fix.)

- [ ] **Step 3: Final syntax check**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

(No commit here unless Steps 1–3 surfaced a fix.)

---

## Deployment (post-implementation, performed by the controller — not a plan step)

1. Deploy the app change via `bash _deploy_zero_downtime.sh`; verify `https://dripdripdrop.ai/` returns HTTP 200.
2. Copy the migration script to the server and dry-run it:
   `scp -i ~/.ssh/dripdrop _unblock_transient_optouts.py root@134.199.237.206:/tmp/`
   `ssh -i ~/.ssh/dripdrop root@134.199.237.206 "cd /opt/dripdrop/app && python /tmp/_unblock_transient_optouts.py /opt/dripdrop/data/users"`
3. Eyeball the dry-run report, then re-run with `--apply`.
4. Confirm the Opt-Out List no longer shows the wrongly-blocked addresses, and watch the journal for `↻ ... will retry` on the next transient failure.

---

## Self-Review

**Spec coverage:**
- Component 1 (`_classify_send_error` + markers + `_MAX_SEND_RETRIES`) → Task 1 ✓
- Component 2 (rewrite scheduler failure branch, retry 3× then fail, permanent keeps cancel+DNC) → Task 2 ✓
- Component 3 (one-time migration, `_is_transient_optout_reason`, dry-run/`--apply`, walks users dir, removes all "…send failed") → Task 3 ✓
- Component 4 (tests for both pure helpers) → Tasks 1 & 3 ✓
- Rollout/verification → Deployment section ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". All code blocks complete.

**Type/name consistency:** `_classify_send_error` returns `"permanent"`/`"transient"` — used identically in Task 2. `_MAX_SEND_RETRIES` (3) defined in Task 1, consumed in Task 2. `_is_transient_optout_reason` defined in Task 3 script, imported in Task 3 tests. `retry_count` / `last_transient_error` item keys consistent within Task 2.

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
        # Exact strings _server_send_one returns when tokens are
        # expired/revoked or no provider is connected (flowdrip_app.py
        # ~49609-49614). These must classify transient — they say
        # nothing about the recipient.
        "Microsoft and Gmail connections both expired or revoked. Reconnect in Email & AI Setup.",
        "Microsoft connection expired or consent revoked. Reconnect Microsoft in Email & AI Setup.",
        "Gmail connection expired or consent revoked. Reconnect Gmail in Email & AI Setup.",
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
        "SMTP error: mailbox does not exist",
    ):
        assert fa._classify_send_error(err) == "permanent", err


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

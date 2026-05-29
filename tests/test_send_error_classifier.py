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

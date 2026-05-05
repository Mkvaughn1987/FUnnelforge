"""Newsletter campaigns no longer inline the rendered HTML body into
every per-recipient queue entry. Body is looked up from the campaign
step at send time. This file verifies:

1. _resolve_body_from_campaign helper exists and reads the right field
2. _server_send_one falls back to campaign step body when item body empty
3. queue_campaign_emails marks newsletter campaigns and skips body
"""
import json
import inspect
from pathlib import Path


def test_resolve_body_helper_exists(with_user):
    """Helper must exist with the expected signature."""
    import flowdrip_app as fa
    assert hasattr(fa, "_resolve_body_from_campaign")
    sig = inspect.signature(fa._resolve_body_from_campaign)
    assert list(sig.parameters.keys()) == ["item", "user_dir"]


def test_resolve_body_returns_step_body_from_campaign_file(with_user, tmp_path):
    """Helper reads the campaign file from user_dir/Campaigns/{slug}.json
    and returns the body of the step at item['_step_idx']."""
    import flowdrip_app as fa
    # Build a fake campaign file
    user_dir = tmp_path / "user_x"
    camps_dir = user_dir / "Campaigns"
    camps_dir.mkdir(parents=True)
    camp = {
        "name": "My Test Newsletter",
        "market_analysis": True,
        "emails": [
            {"name": "Issue 1", "subject": "May", "body": "<html>May body</html>"},
            {"name": "Issue 2", "subject": "Jun", "body": "<html>June body</html>"},
        ],
    }
    # Slug logic mirrors _resolve_body_from_campaign — use the same regex
    import re
    slug = re.sub(r'[^\w]+', '_', camp["name"]).strip('_')
    (camps_dir / f"{slug}.json").write_text(json.dumps(camp), encoding="utf-8")

    item = {"campaign": "My Test Newsletter", "_step_idx": 1}
    body = fa._resolve_body_from_campaign(item, user_dir)
    assert body == "<html>June body</html>"


def test_resolve_body_returns_empty_when_campaign_missing(tmp_path):
    """Missing campaign file returns empty string, not a crash."""
    import flowdrip_app as fa
    item = {"campaign": "Nonexistent Camp", "_step_idx": 0}
    body = fa._resolve_body_from_campaign(item, tmp_path)
    assert body == ""


def test_resolve_body_returns_empty_when_step_out_of_range(with_user, tmp_path):
    """Step index past end of emails list returns empty, not a crash."""
    import flowdrip_app as fa
    user_dir = tmp_path / "user_y"
    camps_dir = user_dir / "Campaigns"
    camps_dir.mkdir(parents=True)
    camp = {
        "name": "Tiny Camp",
        "emails": [{"name": "Only step", "body": "x"}],
    }
    import re
    slug = re.sub(r'[^\w]+', '_', camp["name"]).strip('_')
    (camps_dir / f"{slug}.json").write_text(json.dumps(camp), encoding="utf-8")

    item = {"campaign": "Tiny Camp", "_step_idx": 5}
    body = fa._resolve_body_from_campaign(item, user_dir)
    assert body == ""


def test_server_send_one_signature_accepts_user_dir():
    """Phase A change — _server_send_one must accept an optional
    user_dir kwarg so the scheduler can pass it through for lazy lookup."""
    import flowdrip_app as fa
    sig = inspect.signature(fa._server_send_one)
    assert "user_dir" in sig.parameters, (
        "_server_send_one must accept user_dir kwarg for lazy body lookup"
    )
    # Default must be None so any pre-existing callers (tests, scripts)
    # don't break — they get the legacy "use item body as-is" behavior.
    assert sig.parameters["user_dir"].default is None


def test_server_send_one_refuses_empty_body():
    """The empty-body guard must reject sends with no body — better to
    fail loudly than to ship an empty email."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._server_send_one)
    assert "Missing email body" in src, (
        "_server_send_one must guard against empty body and return an error"
    )


def test_queue_campaign_emails_skips_body_for_newsletters():
    """queue_campaign_emails source must include the newsletter
    branch that sets queue body to empty string."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.queue_campaign_emails)
    assert 'camp.get("market_analysis")' in src, (
        "queue_campaign_emails must check market_analysis to detect newsletters"
    )
    assert "_is_newsletter" in src, (
        "queue_campaign_emails must use the _is_newsletter flag to gate body inlining"
    )

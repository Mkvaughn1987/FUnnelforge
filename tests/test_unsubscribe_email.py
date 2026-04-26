"""C5: unsubscribe_email must be a string (sender email) or None — never bool."""
import pytest


def test_queue_items_unsubscribe_email_is_string_or_none(isolated_appdata, with_user, monkeypatch):
    """Build a tiny campaign and walk queue_campaign_emails; the queued
    items must have unsubscribe_email as a string or None."""
    import flowdrip_app as fa

    captured = {}
    class _StubFFC:
        def add_to_queue(self, items):
            captured["items"] = items
    monkeypatch.setattr(fa, "_FUNNELFORGE_OK", True)
    monkeypatch.setattr(fa, "_ffc", _StubFFC())

    # Stub out helpers that do file I/O or need real context
    monkeypatch.setattr(fa, "load_dnc", lambda: [])
    monkeypatch.setattr(fa, "load_responded", lambda: [])
    monkeypatch.setattr(fa, "load_client_blocklist", lambda: [])
    monkeypatch.setattr(fa, "_load_company_profile", lambda: {})
    monkeypatch.setattr(fa, "_load_signature_text", lambda: "")
    # Pass MX validation for test contacts
    monkeypatch.setattr(fa, "validate_contact_emails", lambda contacts: (contacts, []))

    camp = {
        "name": "Test",
        "_owner_email": "tester@example.com",
        "contacts": [{"email": "lead@x.com", "first_name": "L"}],
        # queue_campaign_emails reads from "emails" key, not "steps"
        "emails": [{
            "name": "Email 1", "subject": "Hi", "body": "Hello {FirstName}",
            "step_type": "email_auto", "delay_days": 0, "time": "09:00",
            "touch_number": 1,
        }],
        "variables": {},
    }
    fa.queue_campaign_emails(camp)
    assert captured.get("items"), "expected at least one queued item"
    for it in captured["items"]:
        v = it.get("unsubscribe_email")
        assert v is None or isinstance(v, str), f"unsubscribe_email must be str|None, got {type(v).__name__}"
        assert v is not True

"""When the sweep regenerates a newsletter step, it must mark the step
`auto_confirmed: true` so the UI can render the 'ⓘ Auto-refreshed' badge."""
import json
from datetime import datetime, timedelta, timezone


def test_auto_refresh_marks_auto_confirmed(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    user_root = with_user
    camp_dir = user_root / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    camp_path = camp_dir / "Test_Newsletter.json"
    camp_path.write_text(json.dumps({
        "name": "Test Newsletter",
        "newsletter_name": "Test Newsletter",
        "market_analysis": True,
        "evergreen_only": True,
        "market_sector": "construction",
        "market_region": "Denver, CO",
        "_owner_email": "tester@example.com",
        "emails": [{
            "name": "Issue 1",
            "subject": "stale",
            "body": "<p>stale</p>",
            "step_type": "email_auto",
        }],
    }), encoding="utf-8")

    queue_path = user_root / "scheduled_queue.json"
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None).isoformat()
    queue_path.write_text(json.dumps([{
        "id": "q1",
        "campaign": "Test Newsletter",
        "step_name": "Issue 1",
        "subject": "stale",
        "to": "lead@example.com",
        "send_dt": soon,
        "status": "pending",
    }]), encoding="utf-8")

    monkeypatch.setattr(
        fa, "_generate_newsletter_content_for_step",
        lambda _c, _i: ("FRESH SUBJECT", "<p>FRESH BODY</p>"))
    monkeypatch.setattr(fa, "_send_email_universal",
        lambda **kw: (True, ""))
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", user_root.parent.parent)

    fa._auto_refresh_newsletter_tick()

    saved = json.loads(camp_path.read_text(encoding="utf-8"))
    assert saved["emails"][0]["subject"] == "FRESH SUBJECT"
    assert saved["emails"][0]["body"] == "<p>FRESH BODY</p>"
    assert saved["emails"][0]["auto_confirmed"] is True

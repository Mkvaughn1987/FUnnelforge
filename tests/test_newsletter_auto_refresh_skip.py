"""User-confirmed newsletter steps must NOT be overwritten by the
6-hour auto-refresh sweep. Without this, manual edits in the modal
get clobbered the next time the scheduler tick runs."""
import json
from datetime import datetime, timedelta, timezone


def test_auto_refresh_skips_confirmed_steps(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    user_root = with_user
    camp_dir = user_root / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    camp_path = camp_dir / "Test_Newsletter.json"
    confirmed_body = "<p>USER EDITED CONTENT — DO NOT OVERWRITE</p>"
    confirmed_subject = "User-edited subject"
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
            "subject": confirmed_subject,
            "body": confirmed_body,
            "step_type": "email_auto",
            "confirmed": True,
        }],
    }), encoding="utf-8")

    queue_path = user_root / "scheduled_queue.json"
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None).isoformat()
    queue_path.write_text(json.dumps([{
        "id": "q1",
        "campaign": "Test Newsletter",
        "step_name": "Issue 1",
        "subject": confirmed_subject,
        "to": "lead@example.com",
        "send_dt": soon,
        "status": "pending",
    }]), encoding="utf-8")

    sentinel = {"called": False}
    def _generator(_camp, _idx):
        sentinel["called"] = True
        return ("REGEN SUBJECT", "<p>REGEN BODY</p>")
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step", _generator)
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", user_root.parent.parent)

    fa._auto_refresh_newsletter_tick()

    assert sentinel["called"] is False, "Generator was called for a confirmed step"
    saved = json.loads(camp_path.read_text(encoding="utf-8"))
    assert saved["emails"][0]["body"] == confirmed_body
    assert saved["emails"][0]["subject"] == confirmed_subject

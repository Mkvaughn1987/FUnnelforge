"""Auto-refresh window changes from 5 days to 3 days. A newsletter
with send 4 days out should NOT be refreshed; one 3 days out SHOULD be."""
import json
from datetime import datetime, timedelta, timezone


def _setup(user_root, days_until_send):
    camp_dir = user_root / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    (camp_dir / "NL.json").write_text(json.dumps({
        "name": "NL",
        "newsletter_name": "NL",
        "market_analysis": True,
        "evergreen_only": True,
        "_owner_email": "tester@example.com",
        "emails": [{"name": "I1", "subject": "old", "body": "<p>old</p>",
                    "step_type": "email_auto"}],
    }), encoding="utf-8")
    soon = (datetime.now(timezone.utc) + timedelta(days=days_until_send)).replace(tzinfo=None).isoformat()
    (user_root / "scheduled_queue.json").write_text(json.dumps([{
        "id": "q1", "campaign": "NL", "step_name": "I1", "subject": "old",
        "to": "x@y.com", "send_dt": soon, "status": "pending",
    }]), encoding="utf-8")


def test_4_days_out_skipped(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    _setup(with_user, days_until_send=4)
    sentinel = {"called": False}
    def _gen(*a):
        sentinel["called"] = True
        return ("S", "B")
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step", _gen)
    monkeypatch.setattr(fa, "_send_email_universal", lambda **kw: (True, ""))
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", with_user.parent.parent)
    fa._auto_refresh_newsletter_tick()
    assert sentinel["called"] is False


def test_3_days_out_refreshed(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    _setup(with_user, days_until_send=3)
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step",
        lambda *a: ("FRESH", "<p>FRESH</p>"))
    monkeypatch.setattr(fa, "_send_email_universal", lambda **kw: (True, ""))
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", with_user.parent.parent)
    fa._auto_refresh_newsletter_tick()
    saved = json.loads((with_user / "Campaigns" / "NL.json").read_text(encoding="utf-8"))
    assert saved["emails"][0]["subject"] == "FRESH"

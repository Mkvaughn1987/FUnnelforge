"""Dashboard task-queue regression (2026-07-24): build_drip_tasks() only
ever surfaced the earliest-in-sequence due manual step for a contact. A
campaign template of Email -> LinkedIn -> Call means any contact whose
LinkedIn touch went un-actioned would permanently hide their later, more
urgent Call touch from the dashboard -- even once the call's own due date
had independently passed. Luke had 375 scheduled calls and zero visible on
his dashboard because ~129 stale LinkedIn touches were blocking every one
of them. Calls must win when both are simultaneously due for one contact.
"""
import json
from datetime import date, timedelta


def _write_campaign(fa, name, start_date, steps, contacts):
    campaigns_dir = fa._user_campaigns_dir()
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    path = campaigns_dir / f"{name}.json"
    path.write_text(json.dumps({
        "name": name,
        "status": "active",
        "start_date": start_date,
        "emails": steps,
        "contacts": contacts,
    }), encoding="utf-8")
    return path


def test_overdue_call_surfaces_over_stale_linkedin_touch(isolated_appdata, with_user):
    import flowdrip_app as fa

    # Sequence: Email (day 0) -> LinkedIn (day 1) -> Call (day 2). Start the
    # campaign 5 days ago so BOTH the LinkedIn and Call touches are overdue,
    # and neither has been marked complete.
    start = (date.today() - timedelta(days=5)).isoformat()
    steps = [
        {"touch_number": 1, "step_type": fa.ST.EMAIL_AUTO, "delay_days": 0, "name": "Email 1"},
        {"touch_number": 2, "step_type": fa.ST.LINKEDIN, "delay_days": 1, "name": "LinkedIn 1"},
        {"touch_number": 3, "step_type": fa.ST.CALL, "delay_days": 1, "name": "Call 1"},
    ]
    contacts = [{"email": "prospect@example.com", "first_name": "Pat", "last_name": "Prospect",
                 "company": "Acme", "title": "VP Ops", "phone_mobile": "555-0100"}]
    _write_campaign(fa, "Stuck Pipeline Campaign", start, steps, contacts)
    fa._cache_campaigns.invalidate()

    tasks = fa.build_drip_tasks(target_date=date.today())

    assert len(tasks) == 1, f"Expected exactly one task for this contact, got {tasks}"
    assert tasks[0]["channel"] == "call", (
        f"Call touch should win over the stale LinkedIn touch, got channel={tasks[0]['channel']!r}"
    )


def test_linkedin_still_shows_when_call_not_yet_due(isolated_appdata, with_user):
    """Sanity check the fix doesn't just always prefer calls -- if the call
    step genuinely isn't due yet, the earlier LinkedIn touch should still
    surface as normal."""
    import flowdrip_app as fa

    start = date.today().isoformat()
    steps = [
        {"touch_number": 1, "step_type": fa.ST.EMAIL_AUTO, "delay_days": 0, "name": "Email 1"},
        {"touch_number": 2, "step_type": fa.ST.LINKEDIN, "delay_days": 0, "name": "LinkedIn 1"},
        {"touch_number": 3, "step_type": fa.ST.CALL, "delay_days": 10, "name": "Call 1"},
    ]
    contacts = [{"email": "prospect2@example.com", "first_name": "Sam", "last_name": "Second",
                 "company": "Beta Co", "title": "Director"}]
    _write_campaign(fa, "Fresh Pipeline Campaign", start, steps, contacts)
    fa._cache_campaigns.invalidate()

    tasks = fa.build_drip_tasks(target_date=date.today())

    assert len(tasks) == 1
    assert tasks[0]["channel"] == "li"

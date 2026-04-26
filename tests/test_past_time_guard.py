"""H1 regression: when the past-time guard's timezone lookup fails,
the original code logged the error and just gave up — letting the email
fire at a moment already in the past (e.g. campaign launched 7:24 PM
with step time 2:30 PM, all emails went out 1 minute later).

The fix adds a naive (no-tz) fallback so we still protect against
shipping obviously past send times even when zoneinfo is unhappy."""
from datetime import date, datetime, timedelta


def test_roll_forward_when_send_is_past_today(isolated_appdata, with_user):
    """The user launched a campaign for 'today at 2 PM' but it's already
    7 PM. The guard must roll forward to the next business day."""
    import flowdrip_app as fa

    today = date.today()
    rolled, msg = fa._roll_past_send_forward(
        send_date=today, hour=2, minute=30, tz_name="America/Los_Angeles"
    )
    # If we ran this test before 2:30 AM Pacific, today might still be future.
    # Otherwise it should be rolled at least one day forward.
    now = datetime.now()
    if datetime(today.year, today.month, today.day, 2, 30) < now:
        assert rolled > today, "Past send time should have rolled to a future date"
        assert msg, "Roll should produce a status message"


def test_no_roll_when_send_is_future(isolated_appdata, with_user):
    import flowdrip_app as fa
    next_week = date.today() + timedelta(days=7)
    rolled, msg = fa._roll_past_send_forward(
        send_date=next_week, hour=14, minute=30, tz_name="America/Los_Angeles"
    )
    assert rolled == next_week, "Future send should not be rolled"


def test_naive_fallback_when_tz_unknown(isolated_appdata, with_user):
    """If the timezone string is bogus, ZoneInfo raises. The guard must
    fall back to a naive comparison so we still don't ship past times."""
    import flowdrip_app as fa

    today = date.today()
    rolled, msg = fa._roll_past_send_forward(
        send_date=today, hour=0, minute=1,
        tz_name="Mars/Olympus_Mons",  # invalid, ZoneInfo will raise
    )
    # 00:01 is in the past for any time of day after midnight; should be rolled.
    now = datetime.now()
    if datetime(today.year, today.month, today.day, 0, 1) < now:
        assert rolled > today, "Naive fallback must still roll past times forward"
        assert msg and "tz error" in msg.lower(), (
            f"Status message should indicate tz error and naive fallback used; got {msg!r}"
        )

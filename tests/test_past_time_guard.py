"""Past-time guard semantics:

H1 (older bug): when the past-time guard's timezone lookup fails,
the original code logged the error and gave up — letting the email
fire at a moment already in the past (e.g. campaign launched 7:24 PM
with step time 2:30 PM, all emails went out 1 minute later).
The fix added a naive (no-tz) fallback so we still protect against
shipping obviously past send times even when zoneinfo is unhappy.

H2 (newer bug, 2026-05-06): the past-time guard was too aggressive.
When a user picked TODAY at 9 AM but launched at 10 AM, the guard
rolled the WHOLE DAY forward to tomorrow — silently shifting the
user's date pick by a calendar day. Multiple users reported their
campaigns "pushing it a day out". Fix: only roll the day forward
if the PICKED DATE itself is in the past. If today's time-of-day
has passed but the day is still today (or future), preserve the
date — the per-contact jitter and the scheduler's "is due now?"
check together fire the email shortly after launch on the same day.
"""
from datetime import date, datetime, timedelta


def test_today_with_past_time_preserves_date(isolated_appdata, with_user):
    """H2: user picked today at 2 AM but it's now afternoon. Date must
    stay TODAY — don't shift to tomorrow. The campaign will fire
    shortly after launch on the user's chosen day."""
    import flowdrip_app as fa
    today = date.today()
    # 2:00 AM is in the past for any time of day after 2:00 AM.
    rolled, msg = fa._roll_past_send_forward(
        send_date=today, hour=2, minute=0, tz_name="America/Los_Angeles"
    )
    # Skip the assertion if we happen to run this test before 2 AM local —
    # in that window the time isn't past yet.
    now = datetime.now()
    if now.hour > 2 or (now.hour == 2 and now.minute > 0):
        assert rolled == today, (
            f"Today's date must be preserved when only the time has passed; "
            f"got rolled to {rolled.isoformat()}"
        )
        assert msg and "preserves" in msg.lower(), (
            f"Status message should explain the date was preserved; got {msg!r}"
        )


def test_yesterday_rolls_forward_to_next_business_day(isolated_appdata, with_user):
    """If the user somehow queued a date that's strictly in the past
    (yesterday or earlier), we must roll forward to the next business
    day. That's the only case where the day shifts."""
    import flowdrip_app as fa
    yesterday = date.today() - timedelta(days=1)
    rolled, msg = fa._roll_past_send_forward(
        send_date=yesterday, hour=9, minute=0, tz_name="America/Los_Angeles"
    )
    assert rolled > yesterday, (
        f"Yesterday must roll forward; got {rolled.isoformat()}"
    )
    assert msg and "rolled" in msg.lower(), (
        f"Status message should indicate the roll; got {msg!r}"
    )


def test_no_roll_when_send_is_future(isolated_appdata, with_user):
    """A clearly future send is left alone."""
    import flowdrip_app as fa
    next_week = date.today() + timedelta(days=7)
    rolled, msg = fa._roll_past_send_forward(
        send_date=next_week, hour=14, minute=30, tz_name="America/Los_Angeles"
    )
    assert rolled == next_week, "Future send should not be rolled"


def test_today_with_future_time_no_roll(isolated_appdata, with_user):
    """User picked today at 11:59 PM. Date stays today, no roll
    (regardless of local clock — 23:59 is the last minute of the day
    so even at 23:58:59 we wouldn't roll)."""
    import flowdrip_app as fa
    today = date.today()
    rolled, msg = fa._roll_past_send_forward(
        send_date=today, hour=23, minute=59, tz_name="America/Los_Angeles"
    )
    # If we run this in the very last second of the day this could
    # actually be past; otherwise it's future and no roll.
    now = datetime.now()
    if now.hour < 23 or (now.hour == 23 and now.minute < 59):
        assert rolled == today, "Future time today should not be rolled"
        # No status message expected when no action is taken.


def test_naive_fallback_today_preserves_date(isolated_appdata, with_user):
    """H1+H2: if the timezone string is bogus, fall back to naive
    comparison. SAME day-preservation logic — only roll if picked
    date is itself in the past."""
    import flowdrip_app as fa
    today = date.today()
    # 00:01 is in the past for any time of day after midnight.
    rolled, msg = fa._roll_past_send_forward(
        send_date=today, hour=0, minute=1,
        tz_name="Mars/Olympus_Mons",  # invalid, ZoneInfo will raise
    )
    now = datetime.now()
    if now.hour > 0 or (now.hour == 0 and now.minute > 1):
        # Today's time-of-day is past, but day stays today.
        assert rolled == today, (
            f"Naive fallback must preserve today's date; got {rolled.isoformat()}"
        )
        assert msg and "tz error" in msg.lower() and "preserves" in msg.lower(), (
            f"Status message should indicate tz error AND date-preservation; got {msg!r}"
        )


def test_naive_fallback_yesterday_rolls(isolated_appdata, with_user):
    """Naive fallback path also rolls when the picked DATE is strictly
    in the past — matches the tz-aware path's behavior."""
    import flowdrip_app as fa
    yesterday = date.today() - timedelta(days=1)
    rolled, msg = fa._roll_past_send_forward(
        send_date=yesterday, hour=9, minute=0,
        tz_name="Mars/Olympus_Mons",  # invalid → naive fallback
    )
    assert rolled > yesterday, "Naive fallback must roll past dates forward"
    assert msg and "tz error" in msg.lower() and "rolled" in msg.lower(), (
        f"Status message should indicate tz error AND roll; got {msg!r}"
    )

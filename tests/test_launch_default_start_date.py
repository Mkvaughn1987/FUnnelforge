"""Launch dialog must default the campaign start date to TODAY, not TOMORROW.

Bug history:
- 2026-04-25 incident: Elizabeth's James Fisher campaign launched at 7:24 PM
  with step 1 time=2:30 PM. Original code had no past-time guard, so all 7
  emails fired one minute later. Workaround: default launch start to TOMORROW.
- 2026-05-08 commit aca2963: added _roll_past_send_forward that preserves
  today's date when only the time-of-day has passed (per-contact jitter +
  scheduler tick handle the actual fire time). Original silent-fire bug
  resolved at the source.
- 2026-05-10: users reporting "campaign goes out 1-2 days later than I
  picked." Root cause: the TOMORROW default became a stale workaround that
  systematically shifts all sends +1 day from the wizard preview (which
  uses date.today() as start). Weekend amplifies to +2.

This test asserts that launch defaults to today now that the underlying
silent-fire bug is fixed.
"""
import inspect


def test_launch_dialog_defaults_start_date_to_today_not_tomorrow():
    """The 'Start sending on' picker in the launch dialog must default
    to date.today().isoformat(), NOT date.today() + timedelta(days=1).

    The TOMORROW workaround was added in early 2026 to dodge a
    silent-fire bug in the past-time guard. That bug was fixed in
    aca2963 (2026-05-08); the workaround now causes a systematic
    +1 day shift between what the wizard preview shows and what the
    queue actually emits.
    """
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    # Locate the launch dialog block by its unique marker
    assert "Start sending on" in src, (
        "Expected to find the launch dialog's 'Start sending on' picker"
    )
    idx = src.index("Start sending on")
    # Walk backward ~400 chars to find the _default_start assignment
    window = src[max(idx - 800, 0): idx + 400]
    # The assignment must be date.today().isoformat() — NOT today + 1 day
    assert "_default_start = date.today().isoformat()" in window or \
           "_default_start = (date.today()).isoformat()" in window, (
        "Launch dialog must default 'Start sending on' to date.today() "
        "(today). Currently it defaults to date.today() + timedelta(days=1) "
        "(tomorrow), which causes the systematic +1 day shift users have "
        "reported. The past-time guard at _roll_past_send_forward (fixed "
        "in commit aca2963) preserves today's date when only the time-of-"
        "day has passed, so the TOMORROW workaround is no longer needed."
    )


def test_three_emails_3days_preset_uses_relative_gaps_not_absolute_offsets():
    """Phase 2 wizard preset 'three_emails_3days' was incorrectly using
    delay_days=[0, 1, 2] which the queue cumulatively sums to [0, 1, 3]
    (because cumulative_delay += step.delay_days for each step).

    The user expects 'one per day for 3 days' = day 0, day 1, day 2.
    With cumulative summing, that requires RELATIVE gaps [0, 1, 1], not
    absolute offsets [0, 1, 2].

    Same bug class as the existing presets (Blitz/Talent Drop) — those
    correctly encode relative deltas. The Phase 2 preset broke from
    that convention.
    """
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_generate)
    # The preset must produce 3 sends with relative gaps [0, 1, 1]
    # (which sum cumulatively to [0, 1, 2] = days 0, 1, 2). Look for
    # the delay_days values in the steps_meta block.
    # The fix changes "delay_days": 2 to "delay_days": 1 in the third
    # entry of the three_emails_3days branch.
    assert "three_emails_3days" in src
    # Slice out the three_emails_3days branch
    marker = 'tc_preset == "three_emails_3days"'
    if marker not in src:
        # Try alternate quoting
        marker = "tc_preset == 'three_emails_3days'"
    assert marker in src, (
        "Expected to find the three_emails_3days branch in _tc_render_step_generate"
    )
    branch_idx = src.index(marker)
    branch_window = src[branch_idx: branch_idx + 600]
    # The third step's delay_days must be 1 (relative gap), NOT 2 (absolute offset)
    # Count occurrences of "delay_days": 2 in the window — should be 0
    # because in the relative-gap encoding no individual step delays by 2
    # (they're each +1 from the previous).
    assert '"delay_days": 2' not in branch_window, (
        "three_emails_3days preset must use RELATIVE gaps. The third "
        "step should be delay_days=1 (1 day after step 2), not "
        "delay_days=2 (which the queue cumulatively sums to day 3, not "
        "day 2). The existing AICB presets (Blitz/Talent Drop) all use "
        "relative gaps; this preset must match."
    )

"""p_today_combined must auto-refresh while AI background generation
is running on call-briefing / LinkedIn-message cards. Verified via
source-grep: the function should include a ui.timer that polls the
two inflight sets and uses once=True to avoid recurring-timer storm."""
import inspect


def test_p_today_combined_includes_inflight_poll_timer():
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_today_combined)
    assert "_call_briefing_gen_inflight" in src, (
        "p_today_combined must reference _call_briefing_gen_inflight "
        "to detect completion of AI bg generation"
    )
    assert "_li_message_gen_inflight" in src, (
        "p_today_combined must reference _li_message_gen_inflight "
        "to detect completion of AI bg generation"
    )
    assert "ui.timer(" in src, (
        "p_today_combined must schedule a ui.timer for the auto-refresh poll"
    )


def test_p_today_combined_poll_uses_once_true():
    """The poll timer must use once=True. Plain recurring timers would
    accumulate across re-renders and re-create the original storm."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_today_combined)
    assert "once=True" in src, (
        "p_today_combined's auto-refresh timer must use once=True "
        "to avoid stacking recurring timers across renders"
    )


def test_p_today_combined_snapshots_inflight_for_completion_detection():
    """The poll must compare a snapshot of inflight names taken at
    render time against the current inflight names — set difference
    detects which jobs completed since render started."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_today_combined)
    assert "frozenset(" in src, (
        "p_today_combined must snapshot inflight names with frozenset() "
        "so set difference can detect completed jobs"
    )

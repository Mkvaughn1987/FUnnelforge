"""5.7.x spam/policy soft bounces suppress after 2 distinct NDRs, others after 3."""
import flowdrip_app as fa


def test_threshold_by_status_code():
    assert fa._soft_bounce_threshold_for("5.7.1") == 2
    assert fa._soft_bounce_threshold_for(" 5.7.606 ") == 2
    assert fa._soft_bounce_threshold_for("5.2.2") == 3
    assert fa._soft_bounce_threshold_for("4.4.1") == 3
    assert fa._soft_bounce_threshold_for("") == 3
    assert fa._soft_bounce_threshold_for(None) == 3


def test_policy_bounce_suppresses_on_the_second_distinct_ndr():
    tracker = {}
    th = fa._soft_bounce_threshold_for("5.7.1")
    assert fa._record_soft_bounce(tracker, "a@x.com", "m1", "5.7.1", th) is False
    assert fa._record_soft_bounce(tracker, "a@x.com", "m1", "5.7.1", th) is False  # same NDR
    assert fa._record_soft_bounce(tracker, "a@x.com", "m2", "5.7.1", th) is True


def test_other_soft_bounce_still_needs_three():
    tracker = {}
    th = fa._soft_bounce_threshold_for("5.2.2")
    assert not fa._record_soft_bounce(tracker, "b@x.com", "m1", "5.2.2", th)
    assert not fa._record_soft_bounce(tracker, "b@x.com", "m2", "5.2.2", th)
    assert fa._record_soft_bounce(tracker, "b@x.com", "m3", "5.2.2", th)


def test_reply_monitor_passes_the_code_specific_threshold():
    import inspect
    src = inspect.getsource(fa._server_reply_monitor_tick)
    assert "_soft_bounce_threshold_for(_status)" in src

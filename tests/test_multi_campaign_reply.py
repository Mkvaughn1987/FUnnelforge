"""H6 regression: when a single contact replies and is enrolled in
N campaigns, only the FIRST campaign was queued for the "new replies"
notification — the user would never see the reply attributed to the
other campaigns even though those campaigns were correctly cancelled.

Fix: the in-memory notification queue (`self._new`) appends one entry
per enrolled campaign, so the responses page shows the reply against
each affected campaign.

The persistence layer (`add_responded`) intentionally dedups by email —
that's a global "this person responded" record and is not changed."""
import pathlib


def test_outlook_monitor_appends_to_new_per_campaign():
    """The reply-handler block should append to self._new inside the
    per-campaign loop, not once outside it with first_info."""
    import flowdrip_app as fa
    text = pathlib.Path(fa.__file__).read_text(encoding="utf-8")

    # Locate the OutlookMonitor reply block. It runs from the line that
    # matches `first_info = infos[0]` to the next `count += 1`.
    start_marker = "first_info = infos[0]"
    end_marker = "count += 1"
    start = text.find(start_marker)
    assert start != -1, "Couldn't find first_info marker; file structure changed"
    end = text.find(end_marker, start)
    assert end != -1, "Couldn't find end marker for reply block"
    block = text[start:end]

    # The pre-fix bug: self._new.append(... campaign=first_info["campaign"]).
    # The fix: campaign=info["campaign"] inside a for-loop over infos.
    assert 'campaign=first_info["campaign"]' not in block and \
           "campaign=first_info['campaign']" not in block, (
        "OutlookMonitor still queues notification with first_info — multi-"
        "campaign replies won't show on each affected campaign (H6)."
    )
    # And the per-info form must be present.
    assert 'campaign=info["campaign"]' in block or \
           "campaign=info['campaign']" in block, (
        "Reply notification should use info['campaign'] inside the "
        "per-campaign loop (H6)."
    )

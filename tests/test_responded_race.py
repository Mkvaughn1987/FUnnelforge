"""H7 regression: OutlookMonitor builds a `responded` set once at the
start of every scan. If the same sender sends two replies within one
scan window (5 minutes), both passed the `sender not in responded`
check because the local set was never updated as items were processed.

The fix updates the local set after each successful reply handling so
within-scan duplicates are caught."""
import pathlib


def test_responded_set_updated_within_scan_loop():
    """Static check: the in-memory responded set must be updated
    during the scan loop, not just at the start."""
    import flowdrip_app as fa
    text = pathlib.Path(fa.__file__).read_text(encoding="utf-8")

    # Locate the reply block (same approach as the H6 test).
    start = text.find("first_info = infos[0]")
    end = text.find("count += 1", start)
    assert start != -1 and end != -1, "Couldn't locate reply block"
    block = text[start:end]

    # The fix adds `responded.add(sender)` somewhere in the reply
    # handler after processing.
    assert "responded.add(sender)" in block, (
        "OutlookMonitor doesn't update the local `responded` set during "
        "the scan loop — same-sender double-replies in one scan window "
        "will be processed twice (H7)."
    )

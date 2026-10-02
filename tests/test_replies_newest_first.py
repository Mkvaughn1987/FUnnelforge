"""Replies page lists the newest reply first and shows its date."""
import inspect

import flowdrip_app as fa


def test_replies_sorted_newest_first_by_either_date_key():
    src = inspect.getsource(fa.p_responses)
    assert 'sorted(load_responded(),' in src
    assert 'r.get("replied_at") or r.get("date")' in src
    assert "reverse=True" in src


def test_reply_card_date_falls_back_to_monitor_date():
    src = inspect.getsource(fa.p_responses)
    assert 'rec.get("replied_at") or rec.get("date")' in src

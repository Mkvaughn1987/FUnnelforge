"""Tests for projecting a campaign's last-email date so a newsletter spun
up from that campaign can default its first issue to after the campaign
ends.

Spec: docs/superpowers/specs/2026-06-03-newsletter-start-after-campaign-and-enroll-design.md
"""
from datetime import date
import flowdrip_app as fa


def test_last_send_none_when_no_steps():
    assert fa._campaign_last_send_date({"emails": []}) is None
    assert fa._campaign_last_send_date({}) is None


def test_last_send_uses_fixed_dates():
    camp = {
        "start_date": "2026-06-01",
        "emails": [
            {"fixed_date": "2026-06-04"},
            {"fixed_date": "2026-07-02"},
            {"fixed_date": "2026-06-18"},
        ],
    }
    # Max fixed_date wins regardless of order.
    assert fa._campaign_last_send_date(camp) == date(2026, 7, 2)


def test_last_send_uses_cumulative_business_days_when_no_fixed_date():
    # start Mon 2026-06-01; delays 0,2,3 -> cumulative 0,2,5 business days.
    camp = {
        "start_date": "2026-06-01",
        "emails": [
            {"delay_days": 0},
            {"delay_days": 2},
            {"delay_days": 3},
        ],
    }
    expected = fa._add_business_days(date(2026, 6, 1), 5)
    assert fa._campaign_last_send_date(camp) == expected


def test_last_send_mixed_fixed_and_delay():
    camp = {
        "start_date": "2026-06-01",
        "emails": [
            {"delay_days": 0},
            {"fixed_date": "2026-09-15"},
            {"delay_days": 4},
        ],
    }
    assert fa._campaign_last_send_date(camp) == date(2026, 9, 15)


def test_last_send_falls_back_to_today_on_bad_start_date(monkeypatch):
    camp = {"start_date": "not-a-date", "emails": [{"delay_days": 0}]}
    # delay 0 from today's date -> today.
    assert fa._campaign_last_send_date(camp) == date.today()

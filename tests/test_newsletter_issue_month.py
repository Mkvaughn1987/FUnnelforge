"""Each newsletter issue is written for the month it sends, not the month
it was generated in (inboxslide 2026-09-18: all 12 issues read "October
2026" because they were generated on the same day)."""
from datetime import date

import flowdrip_app as fa


def test_issue_month_comes_from_its_send_date():
    today = date(2026, 9, 18)
    assert fa._nl_issue_year_month({"fixed_date": "2026-10-01"}, today) == (2026, 10)
    assert fa._nl_issue_year_month({"fixed_date": "2027-03-01"}, today) == (2027, 3)
    assert fa._nl_issue_year_month({"fixed_date": "2026-11-20T09:00"}, today) == (2026, 11)


def test_no_send_date_keeps_the_mid_month_rollover():
    assert fa._nl_issue_year_month({}, date(2026, 9, 18)) == (2026, 10)
    assert fa._nl_issue_year_month({"fixed_date": ""}, date(2026, 9, 3)) == (2026, 9)
    assert fa._nl_issue_year_month({"fixed_date": "bad"}, date(2026, 12, 20)) == (2027, 1)
    assert fa._nl_issue_year_month(None, date(2026, 12, 2)) == (2026, 12)

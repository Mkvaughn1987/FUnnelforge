"""Sanity coverage for the rewritten _holidays_for_month helper.
Detailed multi-holiday cases live in test_holidays_for_month_api.py."""


def test_returns_list_not_tuple():
    import flowdrip_app as fa
    result = fa._holidays_for_month(2026, 7)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0][0] == 4
    assert result[0][1] == "Independence Day"


def test_overrides_still_supported():
    import flowdrip_app as fa
    overrides = {"05": "Closed Mon May 25 — back Tue."}
    hols = fa._holidays_for_month(2026, 5, overrides=overrides)
    assert all(h[2] == "Closed Mon May 25 — back Tue." for h in hols)

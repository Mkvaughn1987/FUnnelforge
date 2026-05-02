"""Holiday helper returns (date_str, name, note) for any month, with
correct handling of variable dates (Easter, Labor Day, Thanksgiving)."""


def test_fixed_holidays_lookup():
    import flowdrip_app as fa

    d, name, note = fa._holiday_for_month(2026, 1)
    assert d == "Jan 1"
    assert name == "New Year's Day"
    assert note

    d, name, _ = fa._holiday_for_month(2026, 7)
    assert d == "Jul 4"
    assert name == "Independence Day"

    d, name, _ = fa._holiday_for_month(2026, 12)
    assert (d, name) == ("Dec 25", "Christmas")


def test_thanksgiving_is_fourth_thursday():
    import flowdrip_app as fa
    d, name, _ = fa._holiday_for_month(2026, 11)
    assert d == "Nov 26"
    assert name == "Thanksgiving"


def test_labor_day_is_first_monday():
    import flowdrip_app as fa
    d, name, _ = fa._holiday_for_month(2026, 9)
    assert d == "Sep 7"
    assert name == "Labor Day"


def test_user_override_replaces_default_note():
    import flowdrip_app as fa
    overrides = {"05": "Closed Mon May 25 — back Tue."}
    d, name, note = fa._holiday_for_month(2026, 5, overrides=overrides)
    assert name == "Memorial Day"
    assert note == "Closed Mon May 25 — back Tue."

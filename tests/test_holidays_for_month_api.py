"""New multi-holiday lookup. Returns a list of (day_int, name, note)
sorted by day. Empty list if the month has no holidays."""


def test_may_returns_two_holidays_in_order():
    import flowdrip_app as fa
    hols = fa._holidays_for_month(2026, 5)
    assert [(h[0], h[1]) for h in hols] == [
        (10, "Mother's Day"),
        (25, "Memorial Day"),
    ]


def test_january_returns_two_holidays():
    import flowdrip_app as fa
    hols = fa._holidays_for_month(2026, 1)
    days = [(h[0], h[1]) for h in hols]
    assert (1, "New Year's Day") in days
    assert (19, "MLK Day") in days  # 3rd Monday of Jan 2026
    assert days == sorted(days)


def test_august_has_no_holidays():
    import flowdrip_app as fa
    assert fa._holidays_for_month(2026, 8) == []


def test_easter_2026_is_april_5():
    import flowdrip_app as fa
    hols = fa._holidays_for_month(2026, 4)
    assert hols == [(5, "Easter", hols[0][2])]


def test_thanksgiving_2026_is_nov_26():
    import flowdrip_app as fa
    hols = fa._holidays_for_month(2026, 11)
    assert [(h[0], h[1]) for h in hols] == [(26, "Thanksgiving")]


def test_per_holiday_override_replaces_default_note():
    import flowdrip_app as fa
    overrides = {"05-memorial-day": "Closed Mon May 25 — back Tue."}
    hols = fa._holidays_for_month(2026, 5, overrides=overrides)
    by_name = {h[1]: h[2] for h in hols}
    assert by_name["Memorial Day"] == "Closed Mon May 25 — back Tue."
    # Mother's Day note is untouched (default).
    assert by_name["Mother's Day"]


def test_legacy_month_override_applies_to_all_holidays_in_month():
    import flowdrip_app as fa
    overrides = {"05": "Have a great month."}
    hols = fa._holidays_for_month(2026, 5, overrides=overrides)
    assert all(h[2] == "Have a great month." for h in hols)


def test_empty_string_override_is_respected_not_treated_as_unset():
    """An explicit empty string in overrides should clear the note,
    not fall through to the month-wide override or the default note."""
    import flowdrip_app as fa
    overrides = {
        "05-memorial-day": "",
        "05": "Have a great month.",  # legacy month-wide fallback
    }
    hols = fa._holidays_for_month(2026, 5, overrides=overrides)
    by_name = {h[1]: h[2] for h in hols}
    assert by_name["Memorial Day"] == ""  # explicit empty wins
    assert by_name["Mother's Day"] == "Have a great month."  # falls through to month-wide


def test_missing_key_falls_through_unchanged():
    """Sanity: pre-existing fall-through behavior for keys that aren't present
    still works after the chained-or fix."""
    import flowdrip_app as fa
    hols = fa._holidays_for_month(2026, 5, overrides={"05": "Month note."})
    assert all(h[2] == "Month note." for h in hols)

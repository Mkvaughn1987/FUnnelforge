"""Calendar HTML structure for the newsletter footer left rail."""


def test_renders_month_header_and_grid():
    import flowdrip_app as fa
    html = fa._render_holiday_calendar(2026, 5, [
        (10, "Mother's Day", ""),
        (25, "Memorial Day", ""),
    ])
    assert "May 2026" in html
    # Expect a 7-column header row with day-of-week letters.
    assert "<table" in html and "</table>" in html
    # All days of May 2026 must appear in the grid.
    for day in range(1, 32):
        assert f">{day}<" in html


def test_highlights_holiday_days():
    import flowdrip_app as fa
    html = fa._render_holiday_calendar(2026, 5, [
        (10, "Mother's Day", ""),
        (25, "Memorial Day", ""),
    ])
    # Highlighted cells use a distinct color block. The cells for days 10
    # and 25 must contain a fill color or border-radius style. We assert
    # the marker class/attribute that the renderer emits.
    assert 'data-pc-day="10"' in html
    assert 'data-pc-day="25"' in html
    # Non-highlight days should NOT carry the marker.
    assert 'data-pc-day="11"' not in html


def test_legend_lists_holidays_in_day_order():
    import flowdrip_app as fa
    html = fa._render_holiday_calendar(2026, 5, [
        (25, "Memorial Day", ""),
        (10, "Mother's Day", ""),
    ])
    pos_mom = html.index("Mother's Day")
    pos_mem = html.index("Memorial Day")
    assert pos_mom < pos_mem  # legend sorted ascending by day
    assert ">10<" in html
    assert ">25<" in html


def test_empty_holidays_renders_grid_without_legend():
    import flowdrip_app as fa
    html = fa._render_holiday_calendar(2026, 8, [])
    assert "August 2026" in html
    assert "<table" in html
    # Legend block should be absent when there are no holidays.
    assert "data-pc-legend" not in html


def test_html_escapes_holiday_names():
    import flowdrip_app as fa
    html = fa._render_holiday_calendar(2026, 5, [
        (10, "<Mom> & 'Day'", ""),
    ])
    assert "<Mom>" not in html  # should be escaped
    assert "&lt;Mom&gt;" in html
    assert "&amp;" in html


def test_render_newsletter_html_includes_calendar_for_send_month():
    import flowdrip_app as fa
    html = fa._render_newsletter_html({
        "company": "Acme",
        "newsletter_name": "The Test Times",
        "tagline": "",
        "location": "Denver, CO",
        "website": "",
        "date": "May 2026",
        "intro_text": "",
        "top_news": [],
        "around_town": [],
        "market_update": "",
        "spotlights": [],
        "contact_name": "Jane Doe",
        "contact_email": "jane@example.com",
        "contact_phone": "",
        "cta_text": "Let's Talk",
        "cta_url": "#",
        "_send_year": 2026,
        "_send_month": 5,
    })
    assert "May 2026" in html
    assert 'data-pc-day="10"' in html
    assert 'data-pc-day="25"' in html

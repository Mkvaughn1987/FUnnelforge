"""Personal Corner mode dispatch — empty / note / photo."""


def test_empty_mode_returns_nbsp():
    import flowdrip_app as fa
    out = fa._render_corner_inner({
        "personal_corner_mode": "",
        "personal_corner_note": "",
        "personal_corner_caption": "",
        "personal_corner_photo_b64": "",
    })
    assert out == "&nbsp;"


def test_note_mode_renders_label_and_italic_body():
    import flowdrip_app as fa
    out = fa._render_corner_inner({
        "personal_corner_mode": "note",
        "personal_corner_note": "May feels like the deep breath.",
        "personal_corner_caption": "",
        "personal_corner_photo_b64": "",
    })
    assert "ON MY MIND" in out
    assert "May feels like the deep breath." in out
    assert "italic" in out


def test_photo_mode_renders_img_and_caption():
    import flowdrip_app as fa
    out = fa._render_corner_inner({
        "personal_corner_mode": "photo",
        "personal_corner_note": "",
        "personal_corner_caption": "Coors Field opener.",
        "personal_corner_photo_b64": "AAAA",
    })
    assert "OUTSIDE THE OFFICE" in out
    assert 'src="data:image/jpeg;base64,AAAA"' in out
    assert "Coors Field opener." in out


def test_note_mode_with_empty_text_falls_back_to_nbsp():
    import flowdrip_app as fa
    assert fa._render_corner_inner({
        "personal_corner_mode": "note",
        "personal_corner_note": "   ",
        "personal_corner_caption": "",
        "personal_corner_photo_b64": "",
    }) == "&nbsp;"


def test_photo_mode_without_photo_falls_back_to_nbsp():
    import flowdrip_app as fa
    assert fa._render_corner_inner({
        "personal_corner_mode": "photo",
        "personal_corner_note": "",
        "personal_corner_caption": "lol",
        "personal_corner_photo_b64": "",
    }) == "&nbsp;"


def test_note_text_is_html_escaped():
    import flowdrip_app as fa
    out = fa._render_corner_inner({
        "personal_corner_mode": "note",
        "personal_corner_note": "<script>alert(1)</script>",
        "personal_corner_caption": "",
        "personal_corner_photo_b64": "",
    })
    assert "<script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


def test_caption_is_html_escaped():
    import flowdrip_app as fa
    out = fa._render_corner_inner({
        "personal_corner_mode": "photo",
        "personal_corner_note": "",
        "personal_corner_caption": "<bad>",
        "personal_corner_photo_b64": "AAAA",
    })
    assert "<bad>" not in out
    assert "&lt;bad&gt;" in out


def _minimal_nl_data(**overrides):
    base = {
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
        "personal_corner_mode": "",
        "personal_corner_note": "",
        "personal_corner_caption": "",
        "personal_corner_photo_b64": "",
    }
    base.update(overrides)
    return base


def test_rendered_body_has_pc_marker_pair():
    import flowdrip_app as fa
    html = fa._render_newsletter_html(_minimal_nl_data())
    assert '<span data-pc="start"></span>' in html
    assert '<span data-pc="end"></span>' in html
    # Empty mode → markers wrap an &nbsp; placeholder.
    assert '<span data-pc="start"></span>&nbsp;<span data-pc="end"></span>' in html


def test_rendered_body_with_note_mode_shows_note():
    import flowdrip_app as fa
    html = fa._render_newsletter_html(_minimal_nl_data(
        personal_corner_mode="note",
        personal_corner_note="Hello world.",
    ))
    assert "ON MY MIND" in html
    assert "Hello world." in html


def test_pc_markers_survive_strip_dashes():
    """_strip_dashes runs at the end of _render_newsletter_html and
    turns '--' into ' - '. Span markers must survive that pass."""
    import flowdrip_app as fa
    html = fa._render_newsletter_html(_minimal_nl_data(
        personal_corner_mode="note",
        personal_corner_note="Hello world.",
    ))
    # Old comment-based markers would have been mangled to '<! - pc-start - >'.
    # Span-based markers contain no '--' so survive unchanged.
    assert '<span data-pc="start"></span>' in html
    assert '<span data-pc="end"></span>' in html
    # Sanity: the corner content is also intact between the markers.
    start_idx = html.index('<span data-pc="start"></span>')
    end_idx = html.index('<span data-pc="end"></span>')
    between = html[start_idx:end_idx]
    assert "Hello world." in between
    assert "ON MY MIND" in between

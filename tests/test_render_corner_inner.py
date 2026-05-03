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

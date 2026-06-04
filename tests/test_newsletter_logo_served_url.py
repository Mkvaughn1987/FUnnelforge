"""The masthead Arena logo must be served by URL, not embedded as a
base64 data URI.

2026-06-04: a customer's sent newsletter showed the logo cut off / broken
in Outlook desktop. Outlook's Word rendering engine does NOT render
`data:image/*` <img> sources, so the base64 logo broke while the URL-based
hero rendered fine. The logo now goes through _email_img_src('logo'),
which in server mode returns an https://dripdripdrop.ai/email_img/logo/...
URL (same mechanism the hero already used).
"""


def test_masthead_logo_uses_served_url_in_server_mode(
        with_user, tmp_path, monkeypatch):
    import flowdrip_app as fa
    from PIL import Image

    logo = tmp_path / "company_logo.png"
    Image.new("RGB", (300, 80), (10, 20, 30)).save(logo)

    monkeypatch.setattr(fa, "_SERVER_MODE", True)
    monkeypatch.setattr(fa, "_get_company_logo_path", lambda: str(logo))

    data = {
        "company": "Arena", "newsletter_name": "Test Report",
        "date": "June 2026", "intro_text": "x", "top_news": [],
        "around_town": [], "market_update": "", "spotlights": [],
        "contact_name": "A", "contact_email": "a@b.com",
        "cta_text": "", "cta_url": "",
        "personal_corner_mode": "", "personal_corner_note": "",
    }
    html = fa._render_newsletter_html(data)

    assert "https://dripdripdrop.ai/email_img/logo/" in html, (
        "masthead logo must be a served URL in server mode"
    )
    assert "data:image/png;base64," not in html, (
        "masthead logo must NOT be a base64 data URI (Outlook can't render it)"
    )


def test_masthead_logo_inline_in_desktop_mode(
        with_user, tmp_path, monkeypatch):
    """Desktop mode has no web host, so the logo falls back to an inline
    data URI (local preview still works)."""
    import flowdrip_app as fa
    from PIL import Image

    logo = tmp_path / "company_logo.png"
    Image.new("RGB", (300, 80), (10, 20, 30)).save(logo)

    monkeypatch.setattr(fa, "_SERVER_MODE", False)
    monkeypatch.setattr(fa, "_get_company_logo_path", lambda: str(logo))

    data = {
        "company": "Arena", "newsletter_name": "Test Report",
        "date": "June 2026", "intro_text": "x", "top_news": [],
        "around_town": [], "market_update": "", "spotlights": [],
        "contact_name": "A", "contact_email": "a@b.com",
        "cta_text": "", "cta_url": "",
        "personal_corner_mode": "", "personal_corner_note": "",
    }
    html = fa._render_newsletter_html(data)
    assert "data:image/png;base64," in html, (
        "desktop mode should inline the logo so local preview renders"
    )

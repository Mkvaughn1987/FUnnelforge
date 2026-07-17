"""The J Way newsletter banner: fixed Arena 'Recruitment Rundown' image,
allowlisted for /static/ serving and rendered above the Highlights block.

Spec: docs/superpowers/specs/2026-06-17-jway-banner-and-spotlight-fork-design.md
"""
import flowdrip_app as fa


def test_banner_is_static_allowlisted():
    """The banner must be servable via /static/ — otherwise the email's
    <img src="https://dripdripdrop.ai/static/jway_banner.png"> 404s."""
    assert "jway_banner.png" in fa._STATIC_ALLOWLIST


def _sample_doc():
    return {
        "intro": "Quick market note for July.",
        "highlights_label": "Highlights (May 2026)",
        "highlights": ["173,000 nonfarm jobs added", "Unemployment 4.0%"],
        "candidates": [],
        "signoff": "Thanks!",
    }


def test_banner_img_present_with_static_url():
    html = fa._jway_render(_sample_doc(), "Jeff")
    assert "/static/jway_banner.png" in html
    assert "https://dripdripdrop.ai/static/jway_banner.png" in html


def test_banner_appears_after_intro_and_before_highlights():
    html = fa._jway_render(_sample_doc(), "Jeff")
    intro_pos = html.index("Quick market note")
    banner_pos = html.index("jway_banner.png")
    highlights_pos = html.index("Highlights (May 2026)")
    assert intro_pos < banner_pos < highlights_pos, (
        "banner must sit between the intro email text and the Highlights block")


def test_no_unsplash_hero_in_jway_body():
    """J Way bodies never carry an Unsplash/city hero image."""
    html = fa._jway_render(_sample_doc(), "Jeff")
    assert "/city_image/" not in html


def test_jway_greets_with_firstname_merge_token():
    """The J Way must open with the personalized 'Hi {FirstName},' merge
    token so the send-time substitution (flowdrip_app L7926) fills in each
    contact's name — not a generic 'Hi there.' the AI invents."""
    html = fa._jway_render(_sample_doc(), "Jeff")
    assert "Hi {FirstName}," in html
    # Greeting must be the first text the reader sees (before the intro).
    assert html.index("Hi {FirstName},") < html.index("Quick market note")


def test_jway_body_wrapped_in_light_paper_background():
    """The body hard-codes dark text (#222), so it MUST sit on an explicit
    white background — otherwise it renders dark-on-dark and is unreadable
    in DripDrop's dark editor canvas (reported 2026-06-22)."""
    html = fa._jway_render(_sample_doc(), "Jeff")
    low = html.lower()
    assert ("background:#ffffff" in low or "background:#fff" in low
            or "background-color:#ffffff" in low), (
        "J Way body must wrap its dark text in a white 'paper' container")


def test_jway_banner_asset_exists_on_disk():
    """The allowlist + <img> are useless without the actual PNG: the design
    shipped 'pending banner asset' and the file was never created, so
    /static/jway_banner.png 404'd in every issue (reported 2026-06-22)."""
    import os
    banner = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "jway_banner.png")
    assert os.path.isfile(banner), f"missing banner asset: {banner}"

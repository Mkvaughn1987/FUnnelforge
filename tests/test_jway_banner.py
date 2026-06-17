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

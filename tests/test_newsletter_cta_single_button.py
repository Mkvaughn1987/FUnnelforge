"""Newsletter CTA must render exactly ONE call-to-action, never the old
dual-button VML trick.

History:
  1. Originally the renderer used a dual-branch conditional-comment trick:
       <!--[if mso]>...VML <v:roundrect>...<![endif]-->
       <!--[if !mso]><!-- -->...modern <a>...<!--<![endif]-->
     Gmail unreliably parsed the [if mso] block, so many users saw BOTH
     buttons side-by-side at the bottom of every newsletter.
  2. That was replaced with a single bulletproof <td bgcolor> pill button.
  3. 2026-05-11: the pill button was dropped entirely — it failed to
     render in Outlook desktop (the Word engine stripped the bgcolor /
     gradient, leaving white text on a white pill = invisible). The CTA is
     now a soft inline text link ("... Email me"), which renders identically
     everywhere because it depends on no styled background.

These tests lock in the current design — a single text-link CTA — and
guard against any return of the dual VML/mso button (the original bug).
"""
import inspect


def _render_simple_newsletter_html() -> str:
    """Helper: render the newsletter HTML with minimum required data
    so we can inspect the CTA output."""
    import flowdrip_app as fa
    data = {
        "company": "Acme Recruiting",
        "newsletter_name": "The Test Report",
        "tagline": "",
        "website": "",
        "date": "May 2026",
        "intro_text": "Test intro.",
        "top_news": [],
        "around_town": [],
        "market_update": "",
        "spotlights": [],
        "contact_name": "Test User",
        "contact_email": "test@example.com",
        "contact_phone": "",
        "cta_text": "Let's Talk",
        "cta_url": "mailto:test@example.com",
        "personal_corner_mode": "",
        "personal_corner_note": "",
    }
    return fa._render_newsletter_html(data)


def test_no_mso_conditional_comments_in_render():
    """The newsletter render must never reintroduce the dual-button VML /
    [if mso] trick that caused Gmail to show two buttons. Grep the whole
    render source — these markers must not appear anywhere."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_newsletter_html)
    assert "[if mso]" not in src, (
        "newsletter render must not use [if mso] conditional comments — "
        "Gmail doesn't reliably hide them and users see two buttons"
    )
    assert "[if !mso]" not in src, (
        "newsletter render must not use [if !mso] conditional comments either"
    )
    assert "v:roundrect" not in src, (
        "newsletter render must not use VML <v:roundrect> — the soft text "
        "link replaces the VML button entirely"
    )


def test_rendered_newsletter_has_single_cta_link():
    """End-to-end: the CTA renders as exactly ONE inline text link
    ("Email me"), not a duplicated button."""
    html = _render_simple_newsletter_html()
    assert html.count(">Email me</a>") == 1, (
        "Expected exactly one 'Email me' CTA link in the rendered HTML. "
        "More than one would mean the dual-render bug is back; zero means "
        "the CTA stopped rendering."
    )
    assert "v:roundrect" not in html, "rendered HTML must not contain VML buttons"
    assert "[if mso]" not in html, "rendered HTML must not contain [if mso] blocks"


def test_cta_is_text_link_not_pill_button():
    """The CTA is a soft inline text link, not a styled pill button. It
    hyperlinks to cta_url and renders as underlined text. Guards against a
    silent regression back to the Outlook-fragile bgcolor pill."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_newsletter_html)
    cta_start = src.index('if _show("show_cta")')
    cta_block = src[cta_start: cta_start + 800]
    assert 'href="{cta_url}"' in cta_block, (
        "CTA must hyperlink to cta_url"
    )
    assert "text-decoration:underline" in cta_block, (
        "CTA should render as an underlined text link, not a filled button"
    )
    assert "bgcolor=" not in cta_block, (
        "CTA must not use a bgcolor pill — it renders invisibly in Outlook "
        "desktop (the reason the pill was dropped 2026-05-11)"
    )

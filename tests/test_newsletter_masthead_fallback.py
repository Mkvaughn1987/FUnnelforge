"""When a newsletter campaign has no newsletter_name AND no market_sector,
the rendered masthead used to literally say "Newsletter" — a customer
got an issue last night with that ugly header. The fallback chain now:
newsletter_name → sector + " Report" → camp.name → "Newsletter".

The CTA went through several iterations to survive Outlook: a CSS
gradient pill (Outlook stripped it → invisible white-on-white), then a
solid bgcolor pill (Outlook desktop still stripped it). As of 2026-05-11
the CTA is a plain underlined text link that depends on no background at
all, so it renders the same in every client.
"""
import inspect


def test_nl_name_falls_back_to_camp_name_before_literal_newsletter():
    """The fallback chain in _generate_newsletter_content_for_step must
    use camp.name before falling back to literal 'Newsletter'."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_newsletter_content_for_step)
    # The fallback chain checks camp.get("name") before defaulting to "Newsletter".
    assert "camp.get(\"name\")" in src, (
        "Newsletter generator must include camp.get('name') in its fallback "
        "chain so campaigns without a newsletter_name don't show a generic "
        "'Newsletter' header in customer inboxes"
    )


def test_cta_is_outlook_safe_text_link():
    """The CTA must not depend on a background-color / gradient pill, which
    Outlook desktop strips (white-on-white = invisible). As of 2026-05-11
    it is a plain underlined text link that renders the same in every
    client."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_newsletter_html)
    cta_start = src.index('if _show("show_cta")')
    cta_block = src[cta_start: cta_start + 800]
    assert "background-color:" not in cta_block, (
        "CTA must not use a background-color pill — Outlook desktop strips "
        "it, leaving an invisible white-on-white button"
    )
    assert "linear-gradient" not in cta_block, (
        "CTA must not use a gradient pill — Outlook strips it"
    )
    assert "text-decoration:underline" in cta_block, (
        "CTA should be a visible underlined text link in all clients"
    )

"""When a newsletter campaign has no newsletter_name AND no market_sector,
the rendered masthead used to literally say "Newsletter" — a customer
got an issue last night with that ugly header. The fallback chain now:
newsletter_name → sector + " Report" → camp.name → "Newsletter".

The CTA button used to render with only a CSS gradient background.
Outlook strips unsupported gradients, leaving white text on a white
pill (invisible). Now there's a solid background-color BEFORE the
gradient so the solid color survives gradient stripping.
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


def test_cta_button_has_solid_background_color_for_outlook():
    """CTA pill must have a solid background-color that survives Outlook's
    gradient stripping. Without it, the pill renders as white-text-on-white."""
    import flowdrip_app as fa
    # The CTA HTML is in _render_newsletter_html. Source-grep for the
    # background-color line that comes before the linear-gradient.
    src = inspect.getsource(fa._render_newsletter_html)
    assert "background-color:" in src, (
        "CTA button must declare a solid background-color so Outlook has "
        "something to render when it strips the linear-gradient"
    )
    # Check that it appears BEFORE background:linear-gradient in source order
    bg_color_pos = src.find("background-color:")
    bg_grad_pos = src.find("background:linear-gradient")
    assert 0 <= bg_color_pos < bg_grad_pos, (
        "background-color must appear BEFORE background:linear-gradient so "
        "the gradient (when honored) clobbers it, but when the gradient is "
        "stripped (Outlook) the solid color remains"
    )

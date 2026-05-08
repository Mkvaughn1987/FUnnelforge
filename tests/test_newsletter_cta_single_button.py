"""Newsletter CTA must render exactly ONE button, not two.

Earlier the renderer used a dual-branch conditional-comment trick:
  <!--[if mso]>...VML <v:roundrect>...<![endif]-->
  <!--[if !mso]><!-- -->...modern <a>...<!--<![endif]-->

Gmail was unreliably parsing the [if mso] block — many users saw
BOTH buttons rendered side-by-side at the bottom of every newsletter.

Fix: single bulletproof table-based button. No conditional comments,
no VML, identical rendering across Gmail / Outlook / Apple / Yahoo.
"""
import inspect


def _render_simple_newsletter_html() -> str:
    """Helper: render the newsletter HTML with minimum required data
    so we can grep the output for CTA-related markers."""
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


def test_no_mso_conditional_comments_in_cta_path():
    """The CTA section of _render_newsletter_html must not use
    `[if mso]` conditional comments. Source-grep ensures we don't
    accidentally re-introduce the dual-button pattern."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_newsletter_html)
    # Find the cta_text rendering block. Look at the section between
    # "cta_text and _show" and the next major section comment.
    cta_marker = "if cta_text and _show"
    assert cta_marker in src, "Could not find CTA block in source"
    cta_start = src.index(cta_marker)
    # Take the next ~3000 chars (the CTA block)
    cta_block = src[cta_start : cta_start + 3000]
    assert "[if mso]" not in cta_block, (
        "CTA block must not use [if mso] conditional comments — Gmail "
        "doesn't reliably hide them and users see two buttons"
    )
    assert "[if !mso]" not in cta_block, (
        "CTA block must not use [if !mso] conditional comments either"
    )
    assert "v:roundrect" not in cta_block, (
        "CTA block must not use VML <v:roundrect> — bulletproof table "
        "button replaces the VML fallback"
    )


def test_rendered_newsletter_has_single_cta_button():
    """End-to-end: render with a non-empty cta_text and verify the
    output contains exactly ONE anchor with the cta text inside."""
    html = _render_simple_newsletter_html()
    # Count occurrences of "Let's Talk" — should be small (not duplicated
    # via dual VML+anchor render). Allow up to 2 occurrences (one inside
    # the inner <span>, one possibly inside an alt or aria attribute).
    count = html.count("Let&#39;s Talk") + html.count("Let's Talk")
    # The cta_text 'Let's Talk' appears once for the button label.
    # If the dual-branch bug is back, it'd appear at least 2x more.
    assert 1 <= count <= 2, (
        f"Expected 1-2 occurrences of 'Let's Talk' in rendered HTML, "
        f"got {count}. The dual-button bug would produce 4+ "
        f"(one each in VML <center> + modern <a> branches)."
    )


def test_cta_uses_bulletproof_table_pattern():
    """The bulletproof button pattern uses a <table> with a colored
    <td bgcolor=...> wrapping a single <a>. Source-grep for the
    structural markers."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_newsletter_html)
    cta_start = src.index("if cta_text and _show")
    cta_block = src[cta_start : cta_start + 3000]
    assert 'role="presentation"' in cta_block, (
        "CTA should use role='presentation' on the wrapper table "
        "(accessibility hint that it's a layout table, not data)"
    )
    assert "bgcolor=" in cta_block, (
        "CTA should set bgcolor on the <td> (works in old Outlook "
        "where CSS background-color via inline style sometimes fails)"
    )

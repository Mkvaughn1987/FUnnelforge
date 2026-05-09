"""_strip_dashes must NOT mangle HTML comment markers.

Bug history: _strip_dashes('<!--[if mso]>') used to return
'<! - [if mso]>' because its '--' → ' - ' rule matched the dashes
inside HTML comment open/close markers. Result: every newsletter
sent through queue_campaign_emails had its conditional comments
broken, so Outlook AND Gmail both rendered the VML branch + the
modern <a> branch — users saw TWO CTA buttons side-by-side at the
bottom of every newsletter.

The fix: negative lookbehind '(?<!<!)' rejects '--' inside '<!--',
negative lookahead '(?!>)' rejects '--' inside '-->'.
"""


def test_strip_dashes_preserves_html_comment_open():
    import flowdrip_app as fa
    assert fa._strip_dashes("<!--[if mso]>") == "<!--[if mso]>"


def test_strip_dashes_preserves_html_comment_close():
    import flowdrip_app as fa
    assert fa._strip_dashes("<![endif]-->") == "<![endif]-->"


def test_strip_dashes_preserves_full_mso_comment_block():
    """End-to-end: the full Outlook conditional comment block must
    pass through unchanged. Earlier this got mangled into
    '<! - [if mso]>...<![endif] - >' which broke the conditional."""
    import flowdrip_app as fa
    block = "<!--[if mso]><v:roundrect>x</v:roundrect><![endif]-->"
    assert fa._strip_dashes(block) == block


def test_strip_dashes_preserves_downlevel_revealed_marker():
    """The non-MSO opener '<!--[if !mso]><!-- -->' is the trickiest —
    contains both a comment opener AND closer in close proximity."""
    import flowdrip_app as fa
    marker = "<!--[if !mso]><!-- -->"
    assert fa._strip_dashes(marker) == marker


def test_strip_dashes_still_swaps_em_and_en_dashes():
    """The function's primary job — replacing typographic dashes —
    must still work for normal prose."""
    import flowdrip_app as fa
    assert "—" not in fa._strip_dashes("Real em—dash here")
    assert "–" not in fa._strip_dashes("Real en–dash here")


def test_strip_dashes_still_swaps_double_hyphen_in_prose():
    """ASCII '--' in normal prose still becomes ' - ' (the original
    behavior). Only HTML comment context is exempt."""
    import flowdrip_app as fa
    # 'foo--bar' in prose should still get the dash swap.
    out = fa._strip_dashes("foo--bar")
    assert "--" not in out
    # Should contain " - " somewhere
    assert "-" in out

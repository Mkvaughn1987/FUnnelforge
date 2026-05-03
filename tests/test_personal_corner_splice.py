"""Splice replaces the inner content between span data-pc='start'/'end' markers.
If markers are absent, the body is returned unchanged."""

PC_BODY_WITH_MARKERS = """\
<html>...
<td valign="top" width="28%" style="padding-left:18px;">
<span data-pc="start"></span>&nbsp;<span data-pc="end"></span>
</td>
...</html>
"""


def test_splice_replaces_inner_content():
    import flowdrip_app as fa
    new_inner = '<div>NEW</div>'
    result = fa._splice_corner_into_body(PC_BODY_WITH_MARKERS, new_inner)
    assert '<span data-pc="start"></span><div>NEW</div><span data-pc="end"></span>' in result
    # The original placeholder &nbsp; must not appear inside the marker pair.
    between = result.split('data-pc="start"></span>', 1)[1].split('<span data-pc="end"', 1)[0]
    assert "&nbsp;" not in between


def test_splice_only_replaces_first_match():
    import flowdrip_app as fa
    body = (
        '<span data-pc="start"></span>A<span data-pc="end"></span>'
        '<span data-pc="start"></span>B<span data-pc="end"></span>'
    )
    result = fa._splice_corner_into_body(body, "X")
    assert result == (
        '<span data-pc="start"></span>X<span data-pc="end"></span>'
        '<span data-pc="start"></span>B<span data-pc="end"></span>'
    )


def test_splice_no_markers_returns_body_unchanged():
    import flowdrip_app as fa
    body = "<html>no markers here</html>"
    assert fa._splice_corner_into_body(body, "<div>X</div>") == body


def test_splice_handles_multiline_inner():
    import flowdrip_app as fa
    body = '<span data-pc="start"></span>old\nlines<span data-pc="end"></span>'
    result = fa._splice_corner_into_body(body, "new\nstuff")
    assert '<span data-pc="start"></span>new\nstuff<span data-pc="end"></span>' in result


def test_splice_handles_empty_body():
    import flowdrip_app as fa
    assert fa._splice_corner_into_body("", "X") == ""
    assert fa._splice_corner_into_body(None, "X") in ("", None)

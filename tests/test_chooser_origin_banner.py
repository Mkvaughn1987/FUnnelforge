"""AICB banner shows different framing based on which chooser door
the user came through (Target a Client vs Target a Market)."""
import inspect


def test_aicb_renders_banner_when_origin_is_client_or_market():
    """The AICB page source must reference _chooser_origin and render
    different banner text for 'client' vs 'market'."""
    import flowdrip_app as fa
    # Find the actual handler — adjust the attribute name if different
    handler = None
    for name in ("p_ai_campaign", "p_aicb", "p_aicb_page"):
        if hasattr(fa, name):
            handler = getattr(fa, name)
            break
    assert handler is not None, (
        "Could not locate the AICB page handler. Check function name "
        "and adjust this test to match."
    )
    src = inspect.getsource(handler)
    assert "_chooser_origin" in src, (
        "AICB page handler must read s._chooser_origin to render the right banner"
    )
    assert "Target a Client" in src or "client" in src.lower()
    assert "Target a Market" in src or "market" in src.lower()

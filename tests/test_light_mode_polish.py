"""Verify the light-mode polish refactor.

All tests are source-grep / value-check style — UI rendering needs a
real NiceGUI client context, so we assert structural markers exist in
the relevant function source instead of running the renders.
"""
import inspect


def test_default_theme_is_light():
    """First-visit users must land in light mode. Existing users with
    a saved 'dd-theme' in localStorage are unaffected (the JS still
    reads the saved value first).

    We assert specifically against the boot-script line that reads
    localStorage at page load. The toggle function (ddToggleTheme) has
    a separate `|| 'dark'` fallback that represents 'no data-theme
    attribute means dark' — that's structurally correct for the
    toggle and unrelated to the default-on-first-visit behavior."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.inject_styles)
    assert "localStorage.getItem('dd-theme') || 'light'" in src, (
        "Boot script must default to 'light' for new visitors "
        "(localStorage.getItem('dd-theme') || 'light')"
    )
    assert "localStorage.getItem('dd-theme') || 'dark'" not in src, (
        "Boot script still has the old 'dark' default — should be 'light' now"
    )


def test_muted_token_bumped_for_contrast():
    """C_LIGHT['muted'] is used by sidebar labels and section headers
    (fd-sec). Old value #6B7B8D was borderline-AA on white. Bump to
    #4A5868 for ~7.5:1 contrast (passes WCAG AAA)."""
    import flowdrip_app as fa
    assert fa.C_LIGHT["muted"] == "#4A5868", (
        f"Expected C_LIGHT['muted'] == '#4A5868', got {fa.C_LIGHT['muted']!r}"
    )


def test_border_token_bumped_for_visibility():
    """C_LIGHT['border'] defines card edge color. Old #D8DEE6 blends
    into the page bg #F5F7FA. Bump to #C8D0DA so card edges are
    visible without being heavy."""
    import flowdrip_app as fa
    assert fa.C_LIGHT["border"] == "#C8D0DA", (
        f"Expected C_LIGHT['border'] == '#C8D0DA', got {fa.C_LIGHT['border']!r}"
    )

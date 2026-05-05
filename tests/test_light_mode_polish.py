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

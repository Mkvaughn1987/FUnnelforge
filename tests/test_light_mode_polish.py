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


def test_card_elevation_rule_present_in_light_mode():
    """Light mode adds a subtle drop-shadow + visible border to .fd-card
    and .fd-bub. Dark mode is untouched. The rule must scope to
    [data-theme='light'] and target both card class names."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.inject_styles)
    assert ":root[data-theme=\"light\"] .fd-card" in src, (
        "inject_styles must include a .fd-card rule scoped to "
        ":root[data-theme=\"light\"]"
    )
    assert ":root[data-theme=\"light\"] .fd-bub" in src, (
        "inject_styles must include a .fd-bub rule scoped to "
        ":root[data-theme=\"light\"]"
    )
    assert "box-shadow" in src, (
        "Card elevation rule must use box-shadow"
    )


def test_evergreen_colors_uses_css_var_references():
    """EVERGREEN_COLORS entries must be CSS var references (not literal
    hex), so they swap with the theme. Each entry is a (bg, fg, border)
    tuple — all three should reference --dd-eg-N-* vars."""
    import flowdrip_app as fa
    bg0, fg0, border0 = fa.EVERGREEN_COLORS[0]
    assert bg0.startswith("var(--dd-eg-"), (
        f"EVERGREEN_COLORS[0] bg must reference a CSS var, got {bg0!r}"
    )
    assert fg0.startswith("var(--dd-eg-"), (
        f"EVERGREEN_COLORS[0] fg must reference a CSS var, got {fg0!r}"
    )
    assert border0.startswith("var(--dd-eg-"), (
        f"EVERGREEN_COLORS[0] border must reference a CSS var, got {border0!r}"
    )


def test_evergreen_colors_has_5_entries():
    """The 5-hue palette identity is part of the design (matches the
    visual preview). If this drops to 4 or expands to 6, the spec
    needs revisiting."""
    import flowdrip_app as fa
    assert len(fa.EVERGREEN_COLORS) == 5


def test_evergreen_css_vars_defined_for_both_themes():
    """All 15 EG vars (5 hues * 3 channels) must be defined in EG_DARK
    and EG_LIGHT inside inject_styles. Source-grep against the dict
    key literals (the runtime formatting prepends '--dd-' to each key)."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.inject_styles)
    # Both EG_DARK and EG_LIGHT must contain entries for every hue + channel.
    assert "EG_DARK" in src, "inject_styles must define EG_DARK palette"
    assert "EG_LIGHT" in src, "inject_styles must define EG_LIGHT palette"
    for key in ('"eg-1-bg"', '"eg-1-fg"', '"eg-1-border"',
                '"eg-5-bg"', '"eg-5-fg"', '"eg-5-border"'):
        assert src.count(key) >= 2, (
            f"{key} must appear at least twice in inject_styles "
            f"(once in EG_DARK, once in EG_LIGHT)"
        )
    # The formatting line that turns dict keys into --dd-* CSS vars
    # must be present (this is what produces --dd-eg-1-bg etc. at runtime).
    assert "f\"  --dd-{k}:{v};\"" in src, (
        "inject_styles must format dict keys as --dd-{k}:{v}; CSS vars"
    )


def test_newsletters_card_has_left_strip():
    """p_newsletters card render must include border-left:4px solid
    so the identity hue shows as a colored strip on the white card
    in light mode."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_newsletters)
    assert "border-left:4px solid" in src, (
        "p_newsletters card render must include "
        "'border-left:4px solid {fg};' for the colored identity strip"
    )

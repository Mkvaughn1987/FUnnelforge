"""The step-preview dialog paints the email body on a white card.

The app's dark theme sets a light `color` on <body>, and an email body is
plain HTML that almost never declares a color of its own (the 4x4/5x3
wrapper only sets font-family + font-size). So unless the white card pins a
dark text color itself, the email inherits the theme's light text and
renders invisible -- a blank white box. Guard the pinned color, and that it
actually contrasts against the card it sits on.
"""
import re
import sys
import pathlib

import pytest


def _decl(style: str, prop: str) -> str:
    m = re.search(rf"(?:^|;)\s*{prop}\s*:\s*([^;]+)", style)
    return m.group(1).strip() if m else ""


def _rel_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    ch = []
    for i in (0, 2, 4):
        v = int(h[i:i + 2], 16) / 255
        ch.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = ch
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    a, b = _rel_luminance(fg), _rel_luminance(bg)
    lo, hi = sorted((a, b))
    return (hi + 0.05) / (lo + 0.05)


@pytest.fixture
def fa(isolated_appdata):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    import flowdrip_app
    return flowdrip_app


def test_preview_card_pins_its_own_text_color(fa):
    style = fa._STEP_PREVIEW_BODY_STYLE
    bg = _decl(style, "background")
    fg = _decl(style, "color")
    assert bg, "preview card must declare a background"
    assert fg, (
        "preview card must declare an explicit text color -- without it the "
        "email body inherits the dark theme's light text and disappears"
    )
    assert _contrast(fg, bg) >= 7.0, (
        f"preview text {fg} on {bg} is only "
        f"{_contrast(fg, bg):.2f}:1 -- unreadable"
    )


def test_dialog_uses_the_shared_preview_card_style(fa):
    import inspect
    src = inspect.getsource(fa._show_step_preview_dialog)
    assert "_STEP_PREVIEW_BODY_STYLE" in src, (
        "the dialog must use the shared style constant, not a re-inlined "
        "one that can drop the text color again"
    )
    assert "background:#ffffff" not in src, (
        "found a re-inlined white card in the dialog -- use "
        "_STEP_PREVIEW_BODY_STYLE instead"
    )

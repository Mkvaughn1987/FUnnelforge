"""A ThriveModal objective tile already picks the campaign style, so the
wizard must not ask again: the tile locks the style and the wizard's lock
check has to honour the TM keys, not just the Arena 4x4."""
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "flowdrip_app.py").read_text(
    encoding="utf-8")


def _lock_expr():
    m = re.search(r"\n        _style_locked = \((.*?)\n        \)\n", SRC, re.S)
    assert m, "wizard _style_locked expression not found"
    return m.group(1)


def test_lock_check_accepts_tm_objectives():
    assert "_TM_TYPE_KEYS" in _lock_expr()


def test_lock_check_still_accepts_arena_4x4():
    assert '"fourbyfour"' in _lock_expr()


def test_tm_tile_sets_the_lock():
    # Every TM tile (and Help me choose) opens the wizard through this helper.
    i = SRC.index("def _tm_start_objective(s, k):")
    block = SRC[i:SRC.index("_TM_STEP_ICON = ", i)]
    assert "s.aicb_style_locked = True" in block
    assert "s.aicb_camp_type = k" in block

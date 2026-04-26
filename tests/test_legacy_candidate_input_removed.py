"""The legacy _render_aicb_candidate_highlights free-text input is
deprecated by the new step 3 candidate card UI."""
import pathlib


def test_render_aicb_candidate_highlights_removed():
    src = pathlib.Path(__file__).resolve().parent.parent / "flowdrip_app.py"
    text = src.read_text(encoding="utf-8")
    assert "def _render_aicb_candidate_highlights" not in text, (
        "Legacy free-text candidate input function still defined — "
        "should be removed in favor of step 3 card UI."
    )
    assert "_render_aicb_candidate_highlights(" not in text, (
        "A caller of the legacy function still exists — it should "
        "be removed (the step 3 card UI replaces it)."
    )

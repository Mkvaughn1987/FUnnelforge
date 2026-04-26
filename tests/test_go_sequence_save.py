"""H14 regression: _go_sequence's broken locals() check prevented
subject/body from being saved before navigating to the sequence step."""
import pathlib


def test_go_sequence_no_broken_locals_check():
    """The original code wrote `if 'subj_inp' in locals()` inside
    _go_sequence. locals() inside that nested function returns the
    nested function's own locals, never the enclosing p_emails_build
    scope, so the check was always False and the save was skipped.

    Verify the broken pattern is no longer in the source."""
    src = pathlib.Path(__file__).resolve().parent.parent / "flowdrip_app.py"
    text = src.read_text(encoding="utf-8")
    assert "'subj_inp' in locals()" not in text, (
        "_go_sequence's broken locals() check still present — "
        "subject is not saved before navigating to sequence step (H14)"
    )
    assert "'body_area' in locals()" not in text, (
        "_go_sequence's broken locals() check still present — "
        "body is not saved before navigating to sequence step (H14)"
    )

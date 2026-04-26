"""C1 regression test: every ui.editor() call site must be paired with
s._register_qeditor() so the merge-field round-trip (JS DOM insert →
'dd_qeditor_change' event → Python set_value()) works. An unregistered
editor silently drops merge-field inserts."""
import pathlib
import re


def test_every_ui_editor_is_followed_by_register_qeditor():
    """For each `ui.editor(` call in flowdrip_app.py, the next ~5 lines
    should contain `_register_qeditor`. If a new editor is added without
    the registration call, the merge-field button silently fails for
    that editor."""
    src = pathlib.Path(__file__).resolve().parent.parent / "flowdrip_app.py"
    text = src.read_text(encoding="utf-8")
    lines = text.split("\n")

    editor_lines = [i for i, line in enumerate(lines) if re.search(r"\bui\.editor\(", line)]

    # The C1 fix at index() also defines `def _register_qeditor` — that
    # line includes "ui.editor" only as a doc reference; skip it.
    skipped = []
    for ln in editor_lines:
        # Look ahead up to 6 lines for the registration call.
        window = "\n".join(lines[ln : ln + 6])
        if "_register_qeditor" not in window:
            skipped.append((ln + 1, lines[ln].strip()))

    assert not skipped, (
        "These ui.editor() call sites are missing a paired "
        "_register_qeditor — merge-field inserts will silently drop "
        "for these editors (C1 regression):\n  "
        + "\n  ".join(f"line {n}: {src!r}" for n, src in skipped)
    )

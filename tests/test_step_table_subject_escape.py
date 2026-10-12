"""Campaign detail step table: subjects must not be HTML-escaped before ui.label.

ui.label escapes text itself, so pre-escaping with esc() rendered an
apostrophe in a subject ("Still Think This One's Worth a Look") as the
literal text "&#39;" in the Email column. The stored subject and the sent
email were fine; only this table was wrong.
"""
import re
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "flowdrip_app.py"


def _step_table_name_line():
    src = _SRC.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^[ \t]*_sname_e = (.*)$", src, re.M)
    assert m, "_sname_e assignment not found in flowdrip_app.py"
    return m.group(1)


def test_step_table_subject_is_not_pre_escaped():
    rhs = _step_table_name_line()
    assert "esc(" not in rhs, (
        "step table subject is HTML-escaped before ui.label, which escapes "
        f"again and shows &#39; for apostrophes: {rhs}"
    )


def test_step_table_subject_goes_to_ui_label():
    src = _SRC.read_text(encoding="utf-8", errors="replace")
    assert "ui.label(_sname_e)" in src

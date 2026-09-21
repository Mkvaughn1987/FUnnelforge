"""A section heading over a long table must not push the whole table to a
new page (the b6584fa keepWithNext regression left half of page 1 blank)."""
import pytest

fitz = pytest.importorskip("fitz")

from funnel_forge.arena_pdfs import build_custom_pdf

_LONG = ("Track and trace work on open loads. Carrier follow up calls and "
         "emails, location updates, ETA confirmations, documentation "
         "requests. Process returned documents and bills of lading. ") * 2


def _doc(tmp_path, n_rows):
    rows = [["Time", "Activity", "System", "Reporting"]]
    rows += [[f"{7+i}:00 AM", _LONG, "Your TMS, carrier portals, email",
              "Load status updated in real time in your TMS"]
             for i in range(n_rows)]
    out = tmp_path / "day.pdf"
    build_custom_pdf(str(out), {
        "title": "ThriveModal Offshore Logistics Coordinator Day",
        "intro": "Your offshore coordinator works inside your operation.",
        "sections": [
            {"heading": "How It Works", "type": "paragraph",
             "items": ["Your coordinator arrives on your schedule. " * 12]},
            {"heading": "Sample Daily Workflow", "type": "table",
             "items": rows},
        ],
    })
    return [p.get_text() for p in fitz.open(str(out))]


def test_long_table_starts_on_same_page_as_intro(tmp_path):
    pages = _doc(tmp_path, n_rows=8)
    assert len(pages) >= 2
    assert "Sample Daily Workflow" in pages[0]
    assert "7:00 AM" in pages[0]          # first data row stays with heading


def test_header_row_repeats_on_continuation_page(tmp_path):
    pages = _doc(tmp_path, n_rows=8)
    assert "Activity" in pages[1]


def test_paragraph_sections_render_as_bullets_when_asked(tmp_path):
    out = tmp_path / "b.pdf"
    build_custom_pdf(str(out), {
        "title": "Cost of Empty Seats", "paragraphs_as_bullets": True,
        "sections": [{"heading": "The Weekly Cost", "type": "paragraph",
                      "items": ["The U.S. median is $47,000. The seat is empty. "
                                "Your team absorbs it."]}],
    })
    text = fitz.open(str(out))[0].get_text()
    assert text.count("\u2022") == 3
    assert "The U.S. median is $47,000." in text


def test_paragraph_sections_stay_paragraphs_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("DRIPDROP_BRAND_DOC_FIRM", raising=False)
    out = tmp_path / "p.pdf"
    build_custom_pdf(str(out), {
        "title": "X", "sections": [{"heading": "H", "type": "paragraph",
                                    "items": ["One. Two. Three."]}]})
    assert "\u2022" not in fitz.open(str(out))[0].get_text()

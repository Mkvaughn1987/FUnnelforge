"""PDF Title/Author metadata is what the browser tab shows. Unset,
ReportLab writes "untitled" / "anonymous" on every prospect-facing PDF."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "funnel_forge"))
import arena_pdfs as ap  # noqa: E402


def _meta(path):
    raw = Path(path).read_bytes().decode("latin-1")
    title = re.search(r"/Title \(([^)]*)\)", raw).group(1)
    author = re.search(r"/Author \(([^)]*)\)", raw).group(1)
    return title, author


def test_custom_pdf_title_and_author(tmp_path):
    out = tmp_path / "c.pdf"
    ap.build_custom_pdf(str(out), {
        "title": "Staffing Cost Comparison - Yellow Diamond Logistics",
        "badge": "STAFFING COST COMPARISON",
        "prepared_by": "Thrivemodal",
        "date": "September 21, 2026",
        "sections": [{"heading": "Roles", "type": "bullets", "items": ["x"]}],
    })
    title, author = _meta(out)
    assert title == "Staffing Cost Comparison - Yellow Diamond Logistics"
    assert author == "Thrivemodal"


def test_no_preparer_never_says_anonymous(tmp_path):
    out = tmp_path / "c.pdf"
    ap.build_custom_pdf(str(out), {
        "title": "Why Work With Us",
        "sections": [{"heading": "A", "type": "paragraph", "items": ["b"]}],
    })
    title, author = _meta(out)
    assert title == "Why Work With Us"
    assert author != "anonymous" and title != "untitled"

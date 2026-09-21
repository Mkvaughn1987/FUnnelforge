"""Every inboxslide PDF is held to 1.5 pages of bullets (Mike, 2026-09-21).
Arena keeps its full-page paragraphs.

The renderer enforces it on whatever the AI returns, and every AI prompt
asks for it so the model doesn't write text that then gets cut.
"""
import copy
import sys
from pathlib import Path

import flowdrip_app as fa

sys.path.insert(0, str(Path(fa.__file__).resolve().parent / "funnel_forge"))
import arena_pdfs as ap  # noqa: E402

_S = ("Warehouse wages in Houston rose 6 percent this year as new distribution "
      "centers opened. Employers now compete with Amazon for the same labor pool.")


def _bloated():
    tbl = [["Position", "Experience", "Base", "Total", "Tier"]] + \
          [["Logistics Coordinator", "5+ years", "$62,000", "$70,000", "Upper"]] * 7
    return {
        "title": "T", "badge": "B", "intro": _S, "paragraphs_as_bullets": True,
        "sections": [
            {"heading": "Overview", "type": "paragraph", "items": [" ".join([_S] * 3)]},
            {"heading": "Table", "type": "table", "items": tbl},
            {"heading": "Trends", "type": "bullets", "items": [_S] * 8},
            {"heading": "Q&A", "type": "qa",
             "items": [{"q": "Why now?", "a": _S}] * 6},
            {"heading": "More", "type": "bullets", "items": [_S] * 6},
            {"heading": "Even more", "type": "bullets", "items": [_S] * 6},
        ],
        "cta": "Call?",
    }


def test_bloated_pdf_is_capped_at_one_and_a_half_pages(tmp_path):
    d = _bloated()
    ap.build_custom_pdf(str(tmp_path / "x.pdf"), d)
    pages, fill = ap._measure_custom(copy.deepcopy(d))
    assert pages == 1 or (pages == 2 and fill <= ap._MAX_LAST_PAGE_FILL)


def test_paragraphs_become_bullets_and_d_is_updated_in_place(tmp_path):
    d = _bloated()
    ap.build_custom_pdf(str(tmp_path / "x.pdf"), d)
    # In place, so the editor sidecar saved from the same dict matches.
    assert all(s["type"] != "paragraph" for s in d["sections"])
    assert d["sections"][0]["type"] == "bullets"


def test_short_pdf_is_untouched(tmp_path):
    d = {"title": "T", "badge": "B", "intro": "One line.", "paragraphs_as_bullets": True,
         "sections": [{"heading": "A", "type": "bullets", "items": ["One.", "Two."]},
                      {"heading": "B", "type": "qa", "items": [{"q": "Q?", "a": "A."}]}]}
    before = copy.deepcopy(d)
    ap.build_custom_pdf(str(tmp_path / "x.pdf"), d)
    assert d == before


def test_arena_is_not_capped(tmp_path, monkeypatch):
    monkeypatch.delenv("DRIPDROP_BRAND_DOC_FIRM", raising=False)
    d = _bloated()
    del d["paragraphs_as_bullets"]
    before = copy.deepcopy(d)
    ap.build_custom_pdf(str(tmp_path / "x.pdf"), d)
    assert d == before


def test_clean_breaks():
    # A bullet never splits one line per page, a question stays with its
    # answer, and a table repeats its header row on the next page.
    assert ap.bullet_item("x").style.allowWidows == 0
    assert ap.bullet_item("x").style.allowOrphans == 0
    assert ap.alt_table([["a"], ["b"]], [100]).repeatRows == 1


def test_every_ai_pdf_prompt_asks_for_the_cap(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    for kind in ("market_pulse", "salary_guide", "interview_guide", "scorecard",
                 "why_staffing", "roi_case", "case_study", "tenure_snapshot",
                 "tm_role_blueprint", "tm_how_it_works"):
        p = fa._rich_pdf_prompt(kind, {"company": "Acme", "positions": "AP Clerk",
                                       "location": "Houston, TX"})
        assert p.endswith(fa._PDF_LENGTH_RULES), kind
        assert "Fill the page" not in p, kind
    assert "1.5 pages" in fa._PDF_LENGTH_RULES


def test_arena_prompts_are_unchanged(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    p = fa._rich_pdf_prompt("market_pulse", {"company": "Acme"})
    assert fa._PDF_LENGTH_RULES not in p
    assert "Fill the page" in p


def test_blueprint_clamp_keeps_it_short():
    d = {"sections": [{"heading": "Responsibilities", "type": "bullets",
                       "items": ["One. Two."] * 9}], "intro": "A. B.", "cta": "C. D."}
    fa._clamp_tm_blueprint(d)
    assert d["sections"][0]["items"] == ["One."] * 5
    assert d["intro"] == "A." and d["cta"] == "C."

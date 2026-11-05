"""Every inboxslide PDF is held to two pages of bullets (Mike, 2026-11-05:
"too simple... go into detail"; 1.5 pages from 2026-09-21 until then).
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


def test_bloated_pdf_is_capped_at_two_pages(tmp_path):
    d = _bloated()
    for sec in d["sections"]:      # enough to run past two pages
        if sec["type"] in ("bullets", "qa"):
            sec["items"] = sec["items"] * 3
    ap.build_custom_pdf(str(tmp_path / "x.pdf"), d)
    pages, fill = ap._measure_custom(copy.deepcopy(d))
    assert pages == 1 or (pages == 2 and fill <= ap._MAX_LAST_PAGE_FILL)


def test_a_closing_line_alone_on_page_two_is_pulled_back(tmp_path):
    """Grow a bulleted doc until it just spills a 'Next Step' onto page
    two; the build trims a bullet instead of leaving that page nearly
    empty, and never touches a 'keep' table."""
    tbl = [["Role", "Ours", "Theirs"]] + [["Sourcer", "$20", "$58"]] * 5 + \
          [["All 5 roles", "$85", "$245"]]
    for n in range(4, 40):
        d = {"title": "T", "badge": "B", "intro": _S, "paragraphs_as_bullets": True,
             "sections": [{"heading": "Table", "type": "table", "items": tbl,
                           "keep": True},
                          {"heading": "Trends", "type": "bullets", "items": [_S] * n}],
             "cta": "Reply to this email to see this with your own figures."}
        pages, fill = ap._measure_custom(copy.deepcopy(d))
        if pages == 2 and fill < ap._MIN_LAST_PAGE_FILL:
            break
    else:
        raise AssertionError("could not build a doc that spills one line")
    ap.build_custom_pdf(str(tmp_path / "x.pdf"), d)
    pages, fill = ap._measure_custom(copy.deepcopy(d))
    assert pages == 1
    assert d["sections"][0]["items"] == tbl       # totals row kept
    assert len(d["sections"][1]["items"]) < n


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
    assert "two pages" in fa._PDF_LENGTH_RULES
    assert "1.5 pages" not in fa._PDF_LENGTH_RULES


def test_arena_prompts_are_unchanged(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    p = fa._rich_pdf_prompt("market_pulse", {"company": "Acme"})
    assert fa._PDF_LENGTH_RULES not in p
    assert "Fill the page" in p


def test_blueprint_clamp_keeps_it_to_two_sentences_and_the_caps():
    d = {"sections": [{"heading": "Responsibilities", "type": "bullets",
                       "items": ["One. Two. Three."] * 9}],
         "intro": "A. B. C.", "cta": "C. D. E."}
    fa._clamp_tm_blueprint(d)
    assert d["sections"][0]["items"] == ["One. Two."] * 6
    assert d["intro"] == "A. B." and d["cta"] == "C. D."
    # The 2026-11-05 shape: six responsibilities and a five-row profile.
    d = {"sections": [
        {"heading": "Core Responsibilities", "type": "table",
         "items": [["a", "b", "c"]] * 12},
        {"heading": "Candidate Profile", "type": "table",
         "items": [["a", "b"]] * 12}] + [
        {"heading": f"S{i}", "type": "bullets", "items": ["x."]} for i in range(9)]}
    fa._clamp_tm_blueprint(d)
    assert len(d["sections"]) == 8
    assert len(d["sections"][0]["items"]) == 7
    assert len(d["sections"][1]["items"]) == 6


def test_candidate_standard_sits_under_the_title_and_is_never_trimmed(tmp_path):
    """Mike, 2026-11-05: every PDF opens with the standard every candidate
    meets. The box renders above the intro and the length trim leaves it."""
    d = _bloated()
    for sec in d["sections"]:
        if sec["type"] in ("bullets", "qa"):
            sec["items"] = sec["items"] * 3
    box = {"heading": "Our Candidate Standard", "type": "callout", "keep": True,
           "items": ["Fully vetted: screened against your role.",
                     "Fluent, professional English: written and spoken.",
                     "Degreed and certified: for the role."]}
    d["sections"].insert(2, dict(box))
    ap.build_custom_pdf(str(tmp_path / "x.pdf"), d)
    kept = [s for s in d["sections"] if s["type"] == "callout"]
    assert kept == [box]
    _doc, story = ap._custom_doc_story(str(tmp_path / "y.pdf"), d)
    tables = [i for i, f in enumerate(story) if f.__class__.__name__ == "Table"]
    intro = next(i for i, f in enumerate(story)
                 if getattr(getattr(f, "style", None), "name", "") == "intro")
    assert tables and tables[0] < intro          # box first, then the intro
    assert len(tables) == 2                      # drawn once, not again in place


def test_a_keep_section_is_never_dropped(tmp_path):
    d = {"title": "T", "badge": "B", "paragraphs_as_bullets": True,
         "sections": [{"heading": f"S{i}", "type": "bullets", "items": [_S] * 12}
                      for i in range(8)]
         + [{"heading": "Basis of Calculation", "type": "bullets",
             "items": [_S, _S], "keep": True}]}
    ap.build_custom_pdf(str(tmp_path / "x.pdf"), d)
    assert d["sections"][-1]["heading"] == "Basis of Calculation"
    assert len(d["sections"][-1]["items"]) == 2
    pages, _fill = ap._measure_custom(copy.deepcopy(d))
    assert pages <= 2


def test_grouped_table_bands_rows_together():
    rows = [["Role", "Years", "Ours", "U.S."]] + [["r", "y", "$1", "$2"]] * 6
    t = ap.alt_table(rows, [100] * 4, group=3)
    cmds = [c for c in t._bkgrndcmds if c[0] == "ROWBACKGROUNDS"]
    assert cmds and len(cmds[0][3]) == 6         # three white, three tinted
    assert ap.alt_table(rows, [100] * 4).repeatRows == 1

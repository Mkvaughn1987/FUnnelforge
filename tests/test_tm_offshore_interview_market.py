"""ThriveModal Market Pulse is about offshore Filipino staffing (Mike,
2026-10-07: "no more construction"), and ThriveModal PDFs are written by
Fable. Arena keeps its own prompts and Haiku. (The ThriveModal Interview
Guide built here on 2026-10-07 was retired the same day; its prompt branch
stays so saved PDFs re-render.)"""
import flowdrip_app as fa

CTX = {"company": "Acme Freight", "primary_industry": "Logistics",
       "positions": "AP Clerk", "location": "Houston, TX"}


def _tm(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)


def test_tm_market_pulse_is_about_offshore(monkeypatch):
    _tm(monkeypatch)
    p = fa._rich_pdf_prompt("market_pulse", CTX)
    assert "offshore" in p.lower() and "Philippines" in p
    assert "Compensation Benchmarks" not in p
    assert "THRIVEMODAL PLAYBOOK" in p
    assert p.endswith(fa._PDF_LENGTH_RULES)


def test_no_construction_anywhere_in_tm_prompts(monkeypatch):
    _tm(monkeypatch)
    for kind in ("market_pulse", "interview_guide", "tm_role_blueprint",
                 "tm_how_it_works"):
        # The playbook's industry list (appended after) may name construction
        # as a buyer market; the document instructions themselves must not.
        p = fa._rich_pdf_prompt(kind, CTX).split("THRIVEMODAL PLAYBOOK")[0]
        assert "construction" not in p.lower(), kind
        assert "jobsite" not in p.lower(), kind


def test_tm_market_pulse_title_is_fixed(monkeypatch):
    _tm(monkeypatch)
    d = {"title": "Houston Construction Market Pulse", "sections": []}
    fa._tm_fix_pdf_labels("market_pulse", CTX, d)
    assert d["title"] == "Offshore Staffing Market Pulse - Acme Freight"


def test_arena_interview_guide_and_market_pulse_unchanged(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    p = fa._rich_pdf_prompt("interview_guide", CTX)
    assert "Must-Ask Questions" in p and "Filipino" not in p
    assert "THRIVEMODAL PLAYBOOK" not in p
    p = fa._rich_pdf_prompt("market_pulse", CTX)
    assert "Compensation Benchmarks" in p


def test_tm_pdf_kinds_are_written_by_fable(monkeypatch):
    """Mike, 2026-10-07: "run it through fable". Arena PDFs stay on Haiku."""
    _tm(monkeypatch)
    seen = []

    class _Msg:
        # Fable puts a thinking block (no .text) ahead of the text block.
        content = [type("Th", (), {"type": "thinking", "thinking": ""})(),
                   type("T", (), {"type": "text",
                                  "text": '{"title":"t","sections":[]}'})()]

    def fake(client, **kw):
        seen.append((kw["model"], kw["max_tokens"]))
        return _Msg()

    monkeypatch.setattr(fa, "_claude_create_with_retry", fake)
    d = fa._generate_rich_pdf_data(None, "market_pulse", dict(CTX))
    assert d["title"] == "Offshore Staffing Market Pulse - Acme Freight"
    fa._generate_rich_pdf_data(None, "tm_role_blueprint", dict(CTX))
    assert seen == [(fa._TM_PDF_MODEL, 8000)] * 2
    assert fa._TM_PDF_MODEL.startswith("claude-fable")

    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    seen.clear()
    fa._generate_rich_pdf_data(None, "market_pulse", dict(CTX))
    assert seen == [("claude-haiku-4-5-20251001", 2400)]


def test_tm_campaign_market_pulse_copy_mentions_offshore():
    assert "offshore" in fa._TM_CAMPAIGN_PDF_BLURBS["market_pulse"].lower()
    lines = {k: line for k, _l, line in fa._TM_CAMPAIGN_PDF_KINDS}
    assert "sources and dates" not in lines["market_pulse"]

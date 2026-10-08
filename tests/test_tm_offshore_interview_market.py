"""ThriveModal Interview Guide + Market Pulse are about offshore Filipino
staffing (Mike, 2026-10-07: "no more construction"). Arena keeps its own."""
import flowdrip_app as fa

CTX = {"company": "Acme Freight", "primary_industry": "Logistics",
       "positions": "AP Clerk", "location": "Houston, TX"}


def _tm(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)


def test_tm_interview_guide_is_for_filipino_candidates(monkeypatch):
    _tm(monkeypatch)
    p = fa._rich_pdf_prompt("interview_guide", CTX)
    assert "Philippines" in p and "Filipino" in p
    assert "shift" in p.lower() and "internet" in p.lower()
    assert "THRIVEMODAL PLAYBOOK" in p          # playbook rules ride along
    assert "nationality" in p.lower()           # no stereotypes rule
    assert p.endswith(fa._PDF_LENGTH_RULES)


def test_tm_market_pulse_is_about_offshore(monkeypatch):
    _tm(monkeypatch)
    p = fa._rich_pdf_prompt("market_pulse", CTX)
    assert "offshore" in p.lower() and "Philippines" in p
    assert "Compensation Benchmarks" not in p
    assert "THRIVEMODAL PLAYBOOK" in p


def test_no_construction_anywhere_in_tm_prompts(monkeypatch):
    _tm(monkeypatch)
    for kind in ("interview_guide", "market_pulse", "tm_role_blueprint",
                 "tm_how_it_works"):
        # The playbook's industry list (appended after) may name construction
        # as a buyer market; the document instructions themselves must not.
        p = fa._rich_pdf_prompt(kind, CTX).split("THRIVEMODAL PLAYBOOK")[0]
        assert "construction" not in p.lower(), kind
        assert "jobsite" not in p.lower(), kind


def test_tm_titles_are_fixed(monkeypatch):
    _tm(monkeypatch)
    for kind, label in (("interview_guide", "Interviewing Filipino Candidates"),
                        ("market_pulse", "Offshore Staffing Market Pulse")):
        d = {"title": "Houston Construction Interview Guide", "sections": []}
        fa._tm_fix_pdf_labels(kind, CTX, d)
        assert d["title"] == f"{label} - Acme Freight"


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
    d = fa._generate_rich_pdf_data(None, "interview_guide", dict(CTX))
    assert d["title"] == "Interviewing Filipino Candidates - Acme Freight"
    fa._generate_rich_pdf_data(None, "tm_role_blueprint", dict(CTX))
    assert seen == [(fa._TM_PDF_MODEL, 8000)] * 2
    assert fa._TM_PDF_MODEL.startswith("claude-fable")

    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    seen.clear()
    fa._generate_rich_pdf_data(None, "interview_guide", dict(CTX))
    assert seen == [("claude-haiku-4-5-20251001", 2400)]


def test_tm_campaign_blurbs_mention_offshore():
    blurbs = fa._TM_CAMPAIGN_PDF_BLURBS
    assert "Filipino" in blurbs["interview_guide"]
    assert "offshore" in blurbs["market_pulse"].lower()
    lines = {k: line for k, _l, line in fa._TM_CAMPAIGN_PDF_KINDS}
    assert "Philippines" in lines["interview_guide"]
    assert "sources and dates" not in lines["market_pulse"]

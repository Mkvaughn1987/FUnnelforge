"""Sales Assets intelligence pass (2026-10-06 audit).

Covers: per-kind research routing + source filtering, the fast-path
fallback, Why Staffing locked to approved firm facts, honesty rules on
every kind, fixed badges, one comp table per batch, the salary-cell
formatter, and the renderer fixes (duplicate CTA header, footer
dedupe, Sources line). No network: the Anthropic client is faked.
"""
import json
import sys
import pathlib
import types

import pytest


@pytest.fixture
def fa(with_user):
    import flowdrip_app as _fa
    return _fa


@pytest.fixture
def ap():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "funnel_forge"))
    import arena_pdfs as _ap
    return _ap


CTX = {
    "company": "RK Industries",
    "primary_industry": "Construction",
    "secondary_industries": [],
    "positions": "Journeyman Electrician",
    "location": "Denver, CO",
    "exp_level": "",
    "prepared_by_company": "Arena Direct Hire",
}


def _payload(sources=None, badge="WHATEVER"):
    return {
        "title": "Denver Construction Salary Guide",
        "badge": badge,
        "intro": "Intro.",
        "sections": [
            {"heading": "Salary Benchmarks", "type": "table", "items": [
                ["Position", "Experience Level", "Base Salary Range", "Total Comp", "Source"],
                ["Journeyman Electrician", "Mid", "64,500 to 72,000", "$70K-$80K", "BLS OEWS 2024"],
            ]},
            {"heading": "Want to learn more?", "type": "bullets", "items": ["Call us."]},
        ],
        "cta": "Book a 12-minute call.",
        "sources": sources or [],
    }


class _Block:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _Msg:
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = None


class _FakeClient:
    """Records every messages.create call and replays canned replies."""
    def __init__(self, replies):
        self.calls = []
        self._replies = list(replies)
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        r = self._replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _research_reply(payload):
    return _Msg([
        _Block("text", text="Let me look this up."),
        _Block("server_tool_use", name="web_search"),
        _Block("web_search_tool_result", content=[
            _Block("web_search_result", url="https://www.bls.gov/oes/current/oes472111.htm", title="BLS"),
        ]),
        _Block("text", text=json.dumps(payload)),
    ])


# ── routing ────────────────────────────────────────────────────────────

def test_data_kind_uses_research_model_with_web_search_and_keeps_real_sources(fa):
    payload = _payload(sources=[
        {"name": "BLS OEWS, Electricians, Colorado", "url": "https://bls.gov/oes/x", "as_of": "May 2024"},
        {"name": "Made-up Survey", "url": "https://fake-survey.example/report", "as_of": "2026"},
    ])
    client = _FakeClient([_research_reply(payload)])
    data = fa._generate_rich_pdf_data(client, "salary_guide", dict(CTX, website="https://www.rkind.com/about"))

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["model"] == fa._PDF_RESEARCH_MODEL
    tool = call["tools"][0]
    assert tool["type"] == "web_search_20260209"
    assert "rkind.com" in tool["allowed_domains"]
    assert "salary.com" in tool["allowed_domains"]
    assert "bizjournals.com" not in tool["allowed_domains"]
    # Only the source whose host the search returned survives.
    assert [s["name"] for s in data["sources"]] == ["BLS OEWS, Electricians, Colorado"]
    assert data["badge"] == "SALARY GUIDE"


def test_research_failure_falls_back_to_fast_model_without_sources(fa):
    client = _FakeClient([
        RuntimeError("boom"),
        _Msg([_Block("text", text=json.dumps(_payload(sources=[{"name": "x", "url": "https://bls.gov"}])))]),
    ])
    data = fa._generate_rich_pdf_data(client, "market_pulse", CTX)
    assert client.calls[1]["model"] == fa._PDF_FAST_MODEL
    assert "tools" not in client.calls[1]
    assert data["sources"] == []          # fast path cannot cite
    assert data["badge"] == "MARKET PULSE"


def test_judgment_kind_skips_research(fa):
    client = _FakeClient([_Msg([_Block("text", text=json.dumps(_payload()))])])
    data = fa._generate_rich_pdf_data(client, "scorecard", CTX)
    assert len(client.calls) == 1
    assert client.calls[0]["model"] == fa._PDF_FAST_MODEL
    assert data["badge"] == "ROLE SCORECARD"


def test_uncrawlable_company_site_is_dropped_and_retried(fa):
    err = RuntimeError("The following domains are not accessible to our user agent: ['rkind.com']")
    client = _FakeClient([err, _research_reply(_payload())])
    fa._generate_rich_pdf_data(client, "tenure_snapshot", dict(CTX, website="rkind.com"))
    assert "rkind.com" in client.calls[0]["tools"][0]["allowed_domains"]
    assert "rkind.com" not in client.calls[1]["tools"][0]["allowed_domains"]


def test_final_text_ignores_chatter_between_searches(fa):
    # Braces in the "thinking out loud" text must not be parsed as the JSON.
    reply = _research_reply(_payload())
    reply.content.insert(0, _Block("text", text="r = {not json}"))
    client = _FakeClient([reply])
    data = fa._generate_rich_pdf_data(client, "salary_guide", CTX)
    assert data["title"] == "Denver Construction Salary Guide"


# ── normalization ──────────────────────────────────────────────────────

def test_finalize_drops_duplicate_cta_section_and_formats_salaries(fa):
    data = fa._finalize_pdf_data("salary_guide", _payload())
    headings = [s["heading"] for s in data["sections"]]
    assert "Want to learn more?" not in headings
    row = data["sections"][0]["items"][1]
    assert row[2] == "$64,500 - $72,000"
    assert row[3] == "$70,000 - $80,000"


@pytest.mark.parametrize("cell,expected", [
    ("48000 - 58000", "$48,000 - $58,000"),
    ("64,500 to 72,000", "$64,500 - $72,000"),
    ("95k - 125k", "$95,000 - $125,000"),
    ("$95K-$120K", "$95,000 - $120,000"),
    ("95-120k", "$95,000 - $120,000"),
    ("$88,000 - $102,000 (est.)", "$88,000 - $102,000 (est.)"),
    ("95k", "$95,000"),
    ("1-5 yrs", "1-5 yrs"),
    ("12-15", "12-15"),
    ("$32 - $38/hr", "$32 - $38/hr"),
    ("BLS OEWS 2024", "BLS OEWS 2024"),
])
def test_format_salary_cell(fa, cell, expected):
    assert fa._format_salary_cell(cell) == expected


def test_share_comp_table_makes_market_pulse_match_salary_guide(fa):
    sg = fa._finalize_pdf_data("salary_guide", _payload(
        sources=[{"name": "BLS OEWS", "url": "https://bls.gov/x", "as_of": "May 2024"}]))
    mp = {"sections": [
        {"heading": "Market Overview", "type": "paragraph", "items": ["..."]},
        {"heading": "Pay Snapshot", "type": "table", "items": [
            ["Position", "Experience Level", "Base Salary Range", "Source"],
            ["Journeyman Electrician", "Mid", "$78,000 - $98,000", "est."],
        ]},
    ], "sources": []}
    assert fa._share_comp_table(mp, sg) is True
    assert mp["sections"][1]["items"] == sg["sections"][0]["items"]
    assert mp["sections"][1]["items"] is not sg["sections"][0]["items"]
    assert mp["sources"][0]["name"] == "BLS OEWS"


# ── prompts ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["market_pulse", "salary_guide", "interview_guide",
                                  "scorecard", "tenure_snapshot", "why_staffing"])
def test_every_kind_carries_honesty_rules(fa, kind):
    p = fa._rich_pdf_prompt(kind, CTX)
    assert "HONESTY" in p
    assert "Never make negative or speculative claims about a named company" in p
    assert "(est.)" in p
    assert "Use REAL numbers" not in p


def test_why_staffing_uses_firm_name_and_approved_terms_only(fa):
    p = fa._rich_pdf_prompt("why_staffing", CTX)
    assert "Arena Direct Hire" in p
    assert fa._4X4_VALUE_PROPS in p
    assert "Do NOT state a guarantee length in days, a fee percentage" in p
    assert "no-fee-until-start, outcome-based pricing" not in p
    assert "'your staffing partner'" in p  # only in the "never say this" instruction


def test_why_staffing_falls_back_to_configured_company_name(fa, monkeypatch):
    monkeypatch.setattr(fa, "_get_company_name", lambda: "Arena Direct Hire")
    ctx = {k: v for k, v in CTX.items() if k != "prepared_by_company"}
    assert "With Arena Direct Hire" in fa._rich_pdf_prompt("why_staffing", ctx)


def test_market_pulse_is_not_a_salary_guide(fa):
    p = fa._rich_pdf_prompt("market_pulse", CTX)
    assert "Market Pulse / Salary Guide" not in p
    assert "Optional 5th heading 'Want to learn more?'" not in p
    assert "Do NOT quote salary dollar figures anywhere" in p


def test_tenure_snapshot_drops_invented_talent_pool_counts(fa):
    p = fa._rich_pdf_prompt("tenure_snapshot", CTX)
    assert "'Talent Pool'" not in p
    assert "Do not invent" in p


def test_dead_curated_pipeline_removed(fa):
    for name in ("_generate_curated_pdf_data", "_PDF_RESEARCH_SYSTEM",
                 "_CURATED_PDF_PROMPT_FNS", "_pdf_prompt_market_pulse"):
        assert not hasattr(fa, name), name


def test_site_domain_normalization(fa):
    assert fa._pdf_site_domain("https://www.RKind.com/about?x=1") == "rkind.com"
    assert fa._pdf_site_domain("rkind.com") == "rkind.com"
    assert fa._pdf_site_domain("not a site") == ""
    assert fa._pdf_site_domain("localhost") == ""


# ── renderer ───────────────────────────────────────────────────────────

def _pdf_text(path):
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)


def test_renderer_no_duplicate_cta_header_and_sources_line(ap, tmp_path):
    out = tmp_path / "x.pdf"
    d = _payload(sources=[{"name": "BLS OEWS, Electricians & Helpers", "as_of": "May 2024"}])
    d.update(prepared_by="Arena Direct Hire", prepared_email="", date="October 6, 2026")
    ap.build_custom_pdf(str(out), d)
    txt = _pdf_text(out)
    assert txt.count("Want to learn more?") == 1
    assert "Sources: BLS OEWS, Electricians & Helpers (May 2024)" in txt
    assert "Arena Direct Hire | Arena Direct Hire" not in txt


def test_renderer_footer_keeps_real_sender(ap, tmp_path):
    out = tmp_path / "y.pdf"
    d = _payload()
    d.update(prepared_by="Mike Vaughn", prepared_email="mike@arena.net")
    ap.build_custom_pdf(str(out), d)
    assert "Arena Direct Hire | Mike Vaughn | mike@arena.net" in _pdf_text(out)


def test_sources_line_empty_when_nothing_to_cite(ap):
    assert ap.sources_line([]) == ""
    assert ap.sources_line(None) == ""
    assert ap.sources_line([{"name": ""}]) == ""

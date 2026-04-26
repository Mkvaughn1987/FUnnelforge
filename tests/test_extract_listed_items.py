"""Tolerant list parser for AI responses. Replaces strict bullet-only
parsing that silently dropped numbered/bolded/plain title lists,
causing the 'Suggest titles' button to look broken on 2026-04-26."""


def test_extract_dashed_bullets():
    import flowdrip_app as fa
    text = "TITLES:\n- CNC Machinist\n- Mill Operator\n- Production Lead"
    out = fa._extract_listed_items(text, section_header="TITLES")
    assert out == ["CNC Machinist", "Mill Operator", "Production Lead"]


def test_extract_numbered_list():
    import flowdrip_app as fa
    text = "TITLES:\n1. CNC Machinist\n2. Mill Operator\n3) Production Lead"
    out = fa._extract_listed_items(text, section_header="TITLES")
    assert "CNC Machinist" in out
    assert "Mill Operator" in out
    assert "Production Lead" in out


def test_extract_strips_markdown_bold():
    import flowdrip_app as fa
    text = "TITLES:\n- **CNC Machinist**\n- *Mill Operator*"
    out = fa._extract_listed_items(text, section_header="TITLES")
    assert "CNC Machinist" in out


def test_extract_strips_trailing_parenthetical():
    import flowdrip_app as fa
    text = "TITLES:\n- CNC Machinist (5+ years experience)\n- Mill Operator (entry level)"
    out = fa._extract_listed_items(text, section_header="TITLES")
    assert "CNC Machinist" in out
    assert "Mill Operator" in out


def test_extract_strips_em_dash_descriptor():
    import flowdrip_app as fa
    text = "TITLES:\n- CNC Machinist — operating mills and lathes\n- Mill Operator – production"
    out = fa._extract_listed_items(text, section_header="TITLES")
    assert "CNC Machinist" in out
    assert "Mill Operator" in out


def test_extract_skips_preamble_before_header():
    import flowdrip_app as fa
    text = (
        "Based on my web research, here are the titles I found:\n\n"
        "TITLES:\n"
        "- CNC Machinist\n"
        "- Mill Operator"
    )
    out = fa._extract_listed_items(text, section_header="TITLES")
    assert out == ["CNC Machinist", "Mill Operator"]


def test_extract_stops_at_next_header():
    import flowdrip_app as fa
    text = (
        "INDUSTRIES:\n"
        "- Manufacturing\n"
        "- Aerospace\n\n"
        "LOCATIONS:\n"
        "- Denver, CO\n"
        "- Boulder, CO"
    )
    industries = fa._extract_listed_items(text, section_header="INDUSTRIES")
    assert industries == ["Manufacturing", "Aerospace"]
    locations = fa._extract_listed_items(text, section_header="LOCATIONS")
    assert locations == ["Denver, CO", "Boulder, CO"]


def test_extract_falls_back_to_whole_text_when_no_header():
    """If the AI skipped the section header, scan the whole text."""
    import flowdrip_app as fa
    text = "- CNC Machinist\n- Mill Operator"
    out = fa._extract_listed_items(text)
    assert out == ["CNC Machinist", "Mill Operator"]


def test_extract_dedups_case_insensitive():
    import flowdrip_app as fa
    text = "TITLES:\n- CNC Machinist\n- cnc machinist\n- Mill Operator"
    out = fa._extract_listed_items(text, section_header="TITLES")
    assert len(out) == 2  # duplicate removed
    assert "CNC Machinist" in out


def test_extract_skips_empty_and_long_lines():
    import flowdrip_app as fa
    text = (
        "TITLES:\n"
        "- CNC Machinist\n"
        "\n"
        "- This is a very long sentence that describes the role in detail and goes on and on and on for many words.\n"
        "- Mill Operator"
    )
    out = fa._extract_listed_items(text, section_header="TITLES")
    assert "CNC Machinist" in out
    assert "Mill Operator" in out
    assert len(out) == 2


def test_extract_returns_empty_for_empty_input():
    import flowdrip_app as fa
    assert fa._extract_listed_items("") == []
    assert fa._extract_listed_items(None) == []


def test_extract_rejects_colon_lines():
    """Real titles don't contain colons; instructional text often does
    (e.g. '**LinkedIn Recruiter**: Filter by company and posting date').
    Lines with colons must be rejected so they don't pollute the
    Suggest Titles output."""
    import flowdrip_app as fa
    text = (
        "TITLES:\n"
        "- LinkedIn Recruiter: Filter by company and posting date\n"
        "- CNC Machinist\n"
        "- Note: search the careers page for openings"
    )
    out = fa._extract_listed_items(text, section_header="TITLES")
    assert out == ["CNC Machinist"]


def test_extract_rejects_instruction_phrases():
    import flowdrip_app as fa
    text = (
        "TITLES:\n"
        "- Filter by company name\n"
        "- Search for engineering roles\n"
        "- CNC Machinist\n"
        "- Click the careers link\n"
        "- Mill Operator"
    )
    out = fa._extract_listed_items(text, section_header="TITLES")
    assert "CNC Machinist" in out
    assert "Mill Operator" in out
    assert all("filter" not in t.lower() for t in out)
    assert all("click" not in t.lower() for t in out)


# ── _parse_string_list_from_ai (JSON-first) ──

def test_parse_string_list_json_array():
    import flowdrip_app as fa
    text = '["CNC Machinist", "Mill Operator", "Production Lead"]'
    assert fa._parse_string_list_from_ai(text) == [
        "CNC Machinist", "Mill Operator", "Production Lead"
    ]


def test_parse_string_list_json_with_preamble():
    """Claude often wraps JSON in prose. Parser must extract it."""
    import flowdrip_app as fa
    text = (
        "Based on my research, here are the titles:\n\n"
        '["CNC Machinist", "Mill Operator"]\n\n'
        "Let me know if you need more."
    )
    assert fa._parse_string_list_from_ai(text) == ["CNC Machinist", "Mill Operator"]


def test_parse_string_list_falls_back_to_text():
    """If no JSON array found, fall back to bullet/numbered parser."""
    import flowdrip_app as fa
    text = "TITLES:\n- CNC Machinist\n- Mill Operator"
    assert fa._parse_string_list_from_ai(text) == ["CNC Machinist", "Mill Operator"]


def test_parse_string_list_dedup_case_insensitive():
    import flowdrip_app as fa
    text = '["CNC Machinist", "cnc machinist", "Mill Operator"]'
    out = fa._parse_string_list_from_ai(text)
    assert len(out) == 2
    assert "CNC Machinist" in out

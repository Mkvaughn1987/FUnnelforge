"""Strip job-offer-style suffixes from candidate salary_ask values."""


def test_plain_range_passes_through_unchanged():
    import flowdrip_app as fa
    assert fa._sanitize_candidate_salary_ask("$140K - $165K") == "$140K - $165K"
    assert fa._sanitize_candidate_salary_ask("$55/hr - $62/hr") == "$55/hr - $62/hr"
    assert fa._sanitize_candidate_salary_ask("Open") == "Open"
    assert fa._sanitize_candidate_salary_ask("") == ""


def test_strips_paren_plus_bonus():
    import flowdrip_app as fa
    # The exact string from the user's screenshot.
    out = fa._sanitize_candidate_salary_ask("$55/hr - $62/hr (plus $8k annual bonus)")
    assert out == "$55/hr - $62/hr"


def test_strips_paren_eligible_clause():
    import flowdrip_app as fa
    out = fa._sanitize_candidate_salary_ask("$120K - $140K (eligible for stock)")
    assert out == "$120K - $140K"


def test_strips_plus_bonus_no_parens():
    import flowdrip_app as fa
    out = fa._sanitize_candidate_salary_ask("$140K-$165K + bonus")
    assert out == "$140K-$165K"
    out = fa._sanitize_candidate_salary_ask("$120K - $140K + benefits")
    assert out == "$120K - $140K"


def test_strips_ote_suffix():
    import flowdrip_app as fa
    out = fa._sanitize_candidate_salary_ask("$95K - $115K OTE $135K")
    assert out == "$95K - $115K"
    out = fa._sanitize_candidate_salary_ask("$95K, OTE: $130K")
    assert out == "$95K"


def test_strips_plus_dollar_bonus_without_parens():
    import flowdrip_app as fa
    out = fa._sanitize_candidate_salary_ask("$80K plus $5k bonus")
    assert out == "$80K"
    out = fa._sanitize_candidate_salary_ask("$80K, plus benefits")
    assert out == "$80K"


def test_strips_trailing_commas_and_whitespace():
    import flowdrip_app as fa
    out = fa._sanitize_candidate_salary_ask("$140K-$165K,")
    assert out == "$140K-$165K"
    out = fa._sanitize_candidate_salary_ask("$140K-$165K   ")
    assert out == "$140K-$165K"


def test_handles_none_input():
    import flowdrip_app as fa
    # The renderer passes "" via .strip() so None never reaches here in
    # production, but defend against it anyway.
    assert fa._sanitize_candidate_salary_ask(None) is None or \
           fa._sanitize_candidate_salary_ask(None) == ""

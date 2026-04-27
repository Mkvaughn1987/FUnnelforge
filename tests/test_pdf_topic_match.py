"""Regression: PDFs were being attached sequentially to email steps
(PDF #5 in _AICB_PDF_KINDS → 5th email step) regardless of topic.
Result: a 'Comp Snapshot' email got the Interview Guide PDF instead
of the Salary Guide PDF. (User report 2026-04-26.)

The new attach pass scores each email's subject+body against per-kind
keyword lists and assigns greedily so each kind goes to its best-
matching email."""


def test_match_salary_for_comp_snapshot_subject():
    import flowdrip_app as fa
    kind = fa._match_pdf_kind_for_email(
        subject="Wichita Aerospace Comp Snapshot - April 2026",
        body="I put together a quick salary and comp snapshot for Wichita aerospace roles.",
    )
    assert kind == "salary_guide", (
        f"Email about 'Comp Snapshot' / 'salary' should match salary_guide; got {kind!r}"
    )


def test_match_interview_for_interview_subject():
    import flowdrip_app as fa
    kind = fa._match_pdf_kind_for_email(
        subject="Interview Framework for Aerospace Engineers",
        body="Here's an interview guide with must-ask screening questions.",
    )
    assert kind == "interview_guide"


def test_match_scorecard_for_evaluation():
    import flowdrip_app as fa
    kind = fa._match_pdf_kind_for_email(
        subject="What we look for in this role",
        body="Here's the scorecard with 90-day outcomes and competencies to evaluate.",
    )
    assert kind == "scorecard"


def test_match_tenure_for_retention():
    import flowdrip_app as fa
    kind = fa._match_pdf_kind_for_email(
        subject="Tenure trends for aerospace engineers",
        body="Median tenure data with retention insights.",
    )
    assert kind == "tenure_snapshot"


def test_match_market_pulse_for_demand_trend():
    import flowdrip_app as fa
    kind = fa._match_pdf_kind_for_email(
        subject="Aerospace talent window",
        body="Market data shows demand trend for engineering roles.",
    )
    assert kind == "market_pulse"


def test_no_match_for_unrelated_email():
    """Plain check-in emails with no PDF topic keywords get no PDF."""
    import flowdrip_app as fa
    kind = fa._match_pdf_kind_for_email(
        subject="Quick check-in",
        body="Just wanted to follow up. Any news on the timing? Talk soon.",
    )
    assert kind == "", (
        f"Email with no PDF-related keywords should match no kind; got {kind!r}"
    )


def test_no_match_for_intro_email():
    """First-touch intro emails ('Hi, here's a candidate') don't get PDFs."""
    import flowdrip_app as fa
    kind = fa._match_pdf_kind_for_email(
        subject="Quick intro - Senior Mechanical Engineer available",
        body="I have a strong candidate I'd like to put on your radar.",
    )
    assert kind == ""


# ── Direct ranking test: comp snapshot beats interview ────────────────

def test_comp_snapshot_beats_interview_for_salary_email():
    """Regression: the user's specific bug. An email with subject
    'Wichita Aerospace Comp Snapshot' and body about salary should
    score HIGHER for salary_guide than for any other kind."""
    import flowdrip_app as fa
    text = (" Wichita Aerospace Comp Snapshot - April 2026 "
            "I put together a quick salary and comp snapshot for "
            "Wichita aerospace roles. Comp ranges based on placements. ")
    text = text.lower()
    scores = {}
    for kind, kws in fa._PDF_KIND_KEYWORDS.items():
        scores[kind] = sum(1 for kw in kws if kw in text)
    # salary_guide must be the strict winner over interview_guide
    assert scores["salary_guide"] > scores["interview_guide"], (
        f"salary_guide ({scores['salary_guide']}) should beat "
        f"interview_guide ({scores['interview_guide']}) for a comp-snapshot "
        f"email. Full scores: {scores}"
    )


def test_keyword_keys_match_pdf_kinds():
    """Static check: every key in _PDF_KIND_KEYWORDS must correspond
    to a real kind in _AICB_PDF_KINDS so the attach loop wires up."""
    import flowdrip_app as fa
    kind_ids = {row[0] for row in fa._AICB_PDF_KINDS}
    for k in fa._PDF_KIND_KEYWORDS:
        assert k in kind_ids, (
            f"_PDF_KIND_KEYWORDS has '{k}' but _AICB_PDF_KINDS doesn't define it"
        )


# ── Free Flow restrict: only attach PDFs the template asked for ────

def test_extract_requested_kinds_returns_only_mentioned():
    """User's Free Flow says 'include market pulse and salary guide'.
    Only those two kinds should be eligible for attach."""
    import flowdrip_app as fa
    desc = (
        "6 emails, 2.5 weeks - 2 cold calls - 1 linked in add second day\n"
        "first email - Intro, market talk\n"
        "second - candidates - include market pulse\n"
        "third - light candidates - include salary guide\n"
        "fourth - dont send candidates but remind them I did\n"
    )
    kinds = fa._extract_requested_pdf_kinds(desc)
    assert kinds == {"market_pulse", "salary_guide"}, (
        f"Expected only market_pulse + salary_guide; got {kinds!r}"
    )


def test_extract_requested_kinds_empty_when_no_pdfs_mentioned():
    """Free Flow that doesn't mention any PDFs → empty set → no attach."""
    import flowdrip_app as fa
    desc = "5 emails over 2 weeks. Mix of LinkedIn touches and a final breakup."
    kinds = fa._extract_requested_pdf_kinds(desc)
    assert kinds == set(), f"Got {kinds!r}"


def test_extract_requested_kinds_returns_none_for_blank():
    """Blank/None template = no restriction (preset campaign path)."""
    import flowdrip_app as fa
    assert fa._extract_requested_pdf_kinds("") is None
    assert fa._extract_requested_pdf_kinds(None) is None


def test_extract_requested_kinds_recognizes_variant_phrasing():
    """Synonyms / variants the user might type should be caught."""
    import flowdrip_app as fa
    # 'Comp snapshot' ≠ 'salary guide' but is a salary_guide alias
    assert "salary_guide" in fa._extract_requested_pdf_kinds(
        "Email 3: comp snapshot for the role"
    )
    # 'tenure data' is a tenure_snapshot alias
    assert "tenure_snapshot" in fa._extract_requested_pdf_kinds(
        "include tenure data on email 4"
    )
    # 'interview kit' aliases interview_guide
    assert "interview_guide" in fa._extract_requested_pdf_kinds(
        "Email 6: send the interview kit"
    )

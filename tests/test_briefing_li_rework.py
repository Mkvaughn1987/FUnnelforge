"""Verify the call briefing + LinkedIn message content rework.

Briefing pivots from generic talking points to company-specific
intel (open jobs + recent news from web search) plus the existing
candidate spotlights extracted from the email body. The LI message
becomes a short follow-up to the email already sent.

Tests are source-grep / structural — actual AI calls are not exercised
here (they'd require a live ANTHROPIC_API_KEY and slow web search).
"""
import inspect


def test_first_contact_company_helper_exists():
    """Helper used by the briefing render and generator to figure out
    which company the briefing should be about."""
    import flowdrip_app as fa
    assert hasattr(fa, "_first_contact_company")
    # Returns empty string for empty / missing contacts.
    assert fa._first_contact_company({}) == ""
    assert fa._first_contact_company({"contacts": []}) == ""
    # Reads the Company / company field on the first contact.
    assert fa._first_contact_company(
        {"contacts": [{"Company": "Brannan Companies"}]}
    ) == "Brannan Companies"
    assert fa._first_contact_company(
        {"contacts": [{"company": "Acme"}]}
    ) == "Acme"
    # Skips empty entries until it finds one.
    assert fa._first_contact_company(
        {"contacts": [{"Company": ""}, {"Company": "Real Co"}]}
    ) == "Real Co"


def test_call_briefing_generator_has_force_refresh_param():
    """The Refresh button in the UI passes force_refresh=True to bypass
    the cache. The signature must support this."""
    import flowdrip_app as fa
    sig = inspect.signature(fa._generate_call_briefing_for_campaign)
    assert "force_refresh" in sig.parameters
    # Default must be False so existing callers keep cache-on-hit behavior.
    assert sig.parameters["force_refresh"].default is False


def test_call_briefing_generator_uses_web_search():
    """Open jobs + news come from real web search (not hallucination).
    The generator must pass the safe web_search tool to Claude."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_call_briefing_for_campaign)
    assert "_safe_web_search_tool" in src, (
        "_generate_call_briefing_for_campaign must use the web_search "
        "tool for open jobs + news lookup"
    )


def test_call_briefing_schema_has_all_sections():
    """The briefing dict includes:
      - open_jobs / news (web-search)
      - company_overview / hq / offices (web-search, added in v6)
      - candidates (extracted from email body or inferred from sector)
      - talking_points (3-5 punchy bullets — restored from original)
      - conversation_flow (v6: opener only; kept for the variants[0] sync)
    """
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_call_briefing_for_campaign)
    for key in ('"open_jobs"', '"news"', '"candidates"',
                '"talking_points"', '"conversation_flow"',
                '"company_overview"', '"hq"', '"offices"'):
        assert key in src, (
            f"Briefing schema must include {key} key"
        )


def test_call_briefing_has_schema_version():
    """Old cached briefings (before the conversation_flow + talking_points
    additions) must auto-regenerate. The cache check gates on _schema_version."""
    import flowdrip_app as fa
    assert hasattr(fa, "_CALL_BRIEFING_SCHEMA_VERSION")
    assert isinstance(fa._CALL_BRIEFING_SCHEMA_VERSION, int)
    assert fa._CALL_BRIEFING_SCHEMA_VERSION >= 2


def test_render_call_briefing_card_shows_company_overview_sections():
    """Render must surface the company overview sections and talking points.

    Schema v6 (2026-07-16) replaced the opener/discovery/pitch/close
    walkthrough with a grounded company overview (what they do, HQ, other
    offices). This test previously asserted the walkthrough; it now pins
    the block that took its place.
    """
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_call_briefing_card)
    assert "Company overview" in src, (
        "Render must include the company overview header"
    )
    for label in ("Headquarters", "Other offices", "Talking points"):
        assert label in src, (
            f"Render must include the '{label}' section label"
        )


def test_render_call_briefing_card_has_no_walkthrough():
    """Regression guard for the v6 removal.

    The walkthrough rendered off cached discovery/pitch/close keys, so
    leaving the render block in place would keep resurrecting it for any
    briefing that still carries them.
    """
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_call_briefing_card)
    assert "Walk through the call" not in src, (
        "The call walkthrough was removed in schema v6 — the company "
        "overview replaces it"
    )
    for label in ("Discovery questions", "Pitch", "Close"):
        assert label not in src, (
            f"'{label}' is part of the removed v6 walkthrough"
        )


def test_render_call_briefing_card_shows_company_and_refresh():
    """The render function must surface the company name in the header
    and provide a Refresh button. Source-grep for both."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_call_briefing_card)
    assert "_first_contact_company" in src or "company_name" in src, (
        "Render must derive the company name to display in the header"
    )
    assert "Refresh" in src, (
        "Render must include a Refresh button label"
    )
    assert "force_refresh=True" in src, (
        "Refresh button handler must pass force_refresh=True to the "
        "generator (otherwise it'd just return the cached briefing)"
    )


def test_li_message_template_references_email_followup():
    """LI message generator's prompt must instruct Claude to write an
    email follow-up (not a generic outreach). Old template wrote a
    'concrete reason to connect tied to the sector' — that's gone."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_li_message_for_campaign)
    # New template explicitly references the email already sent.
    assert "ALREADY SENT" in src or "follows up" in src, (
        "LI prompt must instruct Claude to follow up on an email "
        "the recruiter already sent"
    )
    # Brief intro mentions sender firm.
    assert "_get_company_name" in src, (
        "LI generator must look up the sender's firm name for the "
        "brief intro line"
    )

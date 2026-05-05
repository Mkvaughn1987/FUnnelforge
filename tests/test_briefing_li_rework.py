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


def test_call_briefing_schema_has_jobs_and_news():
    """The new briefing dict includes open_jobs + news + candidates.
    Old schema had talking_points + candidates. Verify the new keys
    are referenced in the generator source."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_call_briefing_for_campaign)
    assert '"open_jobs"' in src, (
        "Briefing schema must include 'open_jobs' key"
    )
    assert '"news"' in src, (
        "Briefing schema must include 'news' key"
    )
    assert '"candidates"' in src, (
        "Briefing schema must still include 'candidates' key (kept per user request)"
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

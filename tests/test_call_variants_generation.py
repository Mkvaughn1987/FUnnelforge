"""Cold-call variants generation.

The call briefing for each campaign now includes 3 style variants —
Project-Anchored / Market-Data / Brief Diagnostic — so the user can
pick which one matches the moment. Storage shape adds a new
`variants` field on the briefing dict; the legacy
`conversation_flow.opener` field is retained as variant 1's content
for backwards compatibility with old campaigns.
"""
import inspect


def test_call_variants_in_schema_version():
    """The schema version constant must be bumped so old briefings
    auto-regenerate on first view."""
    import flowdrip_app as fa
    assert hasattr(fa, "_CALL_BRIEFING_SCHEMA_VERSION")
    assert fa._CALL_BRIEFING_SCHEMA_VERSION >= 3, (
        "Schema version must be >= 3 to invalidate v2 cached briefings "
        "that don't have the new variants field"
    )


def test_call_briefing_prompt_asks_for_three_variants():
    """The prompt must explicitly instruct the AI to produce three
    distinct style variants in the response."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_call_briefing_for_campaign)
    assert "project_anchored" in src.lower() or "project-anchored" in src.lower()
    assert "market_data" in src.lower() or "market-data" in src.lower()
    assert "brief_diagnostic" in src.lower() or "brief-diagnostic" in src.lower() or "diagnostic" in src.lower()
    assert "cold call" in src.lower() and ("researched" in src.lower() or "diagnostic" in src.lower())


def test_call_briefing_returns_variants_field():
    """The returned dict must include a `variants` field (list of 3)
    in addition to the existing fields (open_jobs, news, etc.)."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_call_briefing_for_campaign)
    assert '"variants"' in src or "'variants'" in src, (
        "_generate_call_briefing_for_campaign must populate "
        "result['variants'] = [{'style': '...', 'script': '...'}, x3]"
    )

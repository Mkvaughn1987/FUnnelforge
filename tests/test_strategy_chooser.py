"""Strategy Chooser — 5 starting places with inline descriptive copy.

The new chooser replaces the legacy "Choose a Sequence Type" page.
Each card shows a title + 1-sentence description visible without
clicking. Clicking a card sets s.aicb_camp_type + s._chooser_origin
and routes to the appropriate downstream page.
"""
import inspect


def test_chooser_renders_5_options():
    """The chooser source must reference all 5 starting place titles."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    # 'Target a Client' renamed to 'Target a Company' on 2026-05-10 per
    # user feedback (terminology preference). Accept either to keep the
    # test robust across the rename.
    assert "Target a Company" in src or "Target a Client" in src
    assert "Target a Market" in src
    assert "Target a Candidate" in src
    assert "Saved Campaigns" in src or "Saved Sequences" in src
    assert "Build from scratch" in src or "Build from Scratch" in src


def test_chooser_has_descriptive_copy_for_each_option():
    """Each card needs a one-sentence description so users can pick
    without clicking. Test for the presence of distinguishing copy."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    assert "specific company" in src.lower() or "single client" in src.lower() or "single named company" in src.lower()
    assert "industry" in src.lower() or "market" in src.lower()
    assert "job description" in src.lower() or "candidate outreach" in src.lower() or "guided wizard" in src.lower()


def test_chooser_sets_origin_on_client_card():
    """Clicking Target a Client must set s._chooser_origin to 'client'.
    Source-introspection: look for the assignment near the click handler."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    assert '_chooser_origin = "client"' in src or "_chooser_origin = 'client'" in src
    assert '_chooser_origin = "market"' in src or "_chooser_origin = 'market'" in src

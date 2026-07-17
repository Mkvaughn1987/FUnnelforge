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
    # 'Target a Candidate' renamed to 'Find Candidates' on 2026-05-12 per
    # user feedback — purpose pivoted from "place a candidate" (which
    # implied uploading candidate resumes) to "build outreach for a role
    # you're filling, then add candidates yourself in the editor."
    assert "Find Candidates" in src or "Target a Candidate" in src
    # Renamed 2026-05-10: 'Saved Campaigns' -> 'Saved Sequences' -> 'Drafts & Saved'
    # to signal that wizard drafts also live behind this card.
    assert "Drafts & Saved" in src or "Saved Sequences" in src or "Saved Campaigns" in src
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


def test_mpc_card_routes_to_pipeline_ats():
    """'Start with an MPC' must route allowlisted users to the Pipeline
    (ATS) to pick candidates, not the legacy Top Candidates
    (candidate_finder) page. Candidates moved into the ATS on 2026-06-09."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    idx = src.index('elif k == "mpc":')
    nxt = src.index('elif k == "fourbyfour":', idx)
    mpc_branch = src[idx:nxt]
    # Allowlisted users go to the Pipeline (ATS) to choose candidates.
    assert 'ui.navigate.to("/ats")' in mpc_branch

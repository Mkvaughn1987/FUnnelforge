"""H16 regression: _wiz_back must clear computed outputs (research,
generated campaign, generated docs) when stepping back through the
AI campaign wizard, so a forward re-run regenerates from current inputs
instead of replaying stale data from the prior pass."""


def test_wiz_back_clears_research(isolated_appdata, with_user):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme Corp"
    s.aicb_research = {"company": "Acme", "blurb": "old data"}

    fa._wiz_back_clear_outputs(s)

    assert s.aicb_company == "Acme Corp", "Inputs must be preserved"
    assert s.aicb_research is None, "Research output must be cleared"


def test_wiz_back_clears_generated_campaign_and_docs(isolated_appdata, with_user):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_campaign = {"steps": [{"subject": "stale"}]}
    s.aicb_docs = {"resume_v1": "stale doc"}
    s.aicb_generating = True
    s.aicb_gen_steps = ["stale step"]

    fa._wiz_back_clear_outputs(s)

    assert s.aicb_campaign is None
    assert s.aicb_docs == {}
    assert s.aicb_generating is False
    assert s.aicb_gen_steps == []


def test_wiz_back_keeps_user_inputs(isolated_appdata, with_user):
    """Going back should not erase inputs the user typed — they want to
    see what they entered so they can edit it."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_website = "acme.com"
    s.aicb_niche = "manufacturing"
    s.aicb_industry = "industrial"
    s.aicb_sel_locations = ["Texas", "Ohio"]
    s.aicb_sel_roles = ["VP Sales", "Director"]
    s.aicb_camp_type = "byos"

    fa._wiz_back_clear_outputs(s)

    assert s.aicb_company == "Acme"
    assert s.aicb_website == "acme.com"
    assert s.aicb_niche == "manufacturing"
    assert s.aicb_industry == "industrial"
    assert s.aicb_sel_locations == ["Texas", "Ohio"]
    assert s.aicb_sel_roles == ["VP Sales", "Director"]
    assert s.aicb_camp_type == "byos"

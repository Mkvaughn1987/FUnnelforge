"""When the user steps back from the new step 3 (Candidates),
_wiz_back_clear_outputs must clear candidate-specific state so a fresh
forward pass regenerates instead of replaying stale data."""


def test_wiz_back_clears_candidate_state(isolated_appdata, with_user):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_cand_count = 5
    s.aicb_cand_source = "autogen"
    s.aicb_cand_cards = [{"label": "Candidate A", "role": "x", "bullets": []}]
    s._aicb_cand_text = "Candidate A: ..."

    fa._wiz_back_clear_outputs(s)

    fresh = fa.AppState()
    assert s.aicb_cand_count == fresh.aicb_cand_count
    assert s.aicb_cand_source == fresh.aicb_cand_source
    assert s.aicb_cand_cards == fresh.aicb_cand_cards
    assert s._aicb_cand_text == fresh._aicb_cand_text


def test_wiz_back_keeps_inputs(isolated_appdata, with_user):
    """Inputs (company, roles, industry) are preserved on back."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_industry = "Mfg"
    s.aicb_sel_roles = ["Machinist"]
    s.aicb_sel_locations = ["Denver, CO"]

    fa._wiz_back_clear_outputs(s)

    assert s.aicb_company == "Acme"
    assert s.aicb_industry == "Mfg"
    assert s.aicb_sel_roles == ["Machinist"]
    assert s.aicb_sel_locations == ["Denver, CO"]

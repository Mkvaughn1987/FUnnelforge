"""Arena 5x3 campaign + resume engine (PipelineBlast Component 1).
Import flowdrip_app lazily inside each test (per tests/conftest.py)."""


def _get(fa, key):
    for t in fa.AICB_CAMPAIGN_TYPES:
        if t[0] == key:
            return t
    return None


def test_fivebythree_registered_after_fivebyfive():
    import flowdrip_app as fa
    keys = [t[0] for t in fa.AICB_CAMPAIGN_TYPES]
    assert "fivebythree" in keys
    assert keys.index("fivebythree") == keys.index("fivebyfive") + 1
    t = _get(fa, "fivebythree")
    assert t[1] == "Arena 5×3"
    assert t[2] == "5 steps - 2 weeks"


def test_fivebythree_prompt_has_five_steps():
    import flowdrip_app as fa
    prompt = _get(fa, "fivebythree")[6]
    positions = [prompt.find(f"Step {n} -") for n in range(1, 6)]
    assert all(p != -1 for p in positions), positions
    assert positions == sorted(positions)
    assert "Step 6 -" not in prompt


def test_fivebythree_in_slate_family():
    import flowdrip_app as fa
    assert "fivebythree" in fa._ARENA_SLATE_TYPES
    assert fa._camp_is_4x4({"aicb_camp_type": "fivebythree"}) is True
    assert fa._resume_attach_indices("fivebythree", 5) == [1, 3]

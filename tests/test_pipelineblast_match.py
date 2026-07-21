"""PipelineBlast Component 2 — candidate matching engine.
Import flowdrip_app lazily inside each test (tests/conftest.py)."""


def test_pool_card_bullets_no_location_excludes_location():
    import flowdrip_app as fa
    cand = {"target_role": "Project Engineer", "location": "Oakland, CA",
            "summary": "Civil PE with QC focus. Ten years.", "salary": "$120k"}
    bullets = fa._pool_card_bullets_no_location(cand)
    joined = " ".join(bullets).lower()
    assert "oakland" not in joined
    assert "location" not in joined
    assert any("project engineer" in b.lower() for b in bullets)


def test_synthesize_fill_card_shape():
    import flowdrip_app as fa
    card = fa._synthesize_fill_card("Project Manager", "Candidate C")
    assert card["label"] == "Candidate C"
    assert card["role"] == "Project Manager"
    assert isinstance(card["bullets"], list) and len(card["bullets"]) >= 2
    assert "_pool_id" not in card               # fills are not real candidates
    assert all("Project Manager".lower() in b.lower() or len(b) > 0 for b in card["bullets"])

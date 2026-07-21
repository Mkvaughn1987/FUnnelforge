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


class _StubMsg:
    def __init__(self, text): self.content = [type("B", (), {"text": text})()]

class _StubClient:
    def __init__(self, payload): self._payload = payload
    @property
    def messages(self):
        outer = self
        class _M:
            def create(self, **kw): return _StubMsg(outer._payload)
        return _M()


def _sample_pool():
    return [
        {"id": "c1", "target_role": "Healthcare Project Manager", "resume_text": "OSHPD PM"},
        {"id": "c2", "target_role": "Construction Estimator", "resume_text": "bridges"},
    ]


def test_ai_score_candidates_parses_and_sorts():
    import flowdrip_app as fa
    payload = ('[{"id":"c2","score":40,"reason":"wrong sector"},'
               '{"id":"c1","score":92,"reason":"exact healthcare PM"}]')
    scored = fa._ai_score_candidates(_StubClient(payload), "Swinerton",
                                     "Healthcare Project Manager", "Construction",
                                     _sample_pool())
    assert [s["id"] for s in scored] == ["c1", "c2"]   # sorted desc by score
    assert scored[0]["score"] == 92


def test_ai_score_candidates_empty_on_failure():
    import flowdrip_app as fa
    scored = fa._ai_score_candidates(_StubClient("not json"), "X", "Y", "Z", _sample_pool())
    assert scored == []


def _pool3():
    return [
        {"id": "c1", "target_role": "Healthcare PM", "summary": "OSHPD PM"},
        {"id": "c2", "target_role": "Estimator", "summary": "Bridges"},
        {"id": "c3", "target_role": "Superintendent", "summary": "Field"},
    ]


def test_build_slate_all_real_when_three_clear_floor():
    import flowdrip_app as fa
    scored = [{"id": "c1", "score": 90, "reason": ""},
              {"id": "c2", "score": 70, "reason": ""},
              {"id": "c3", "score": 55, "reason": ""}]
    cards = fa._build_slate_cards(_pool3(), scored, "Healthcare PM")
    assert [c["label"] for c in cards] == ["Candidate A", "Candidate B", "Candidate C"]
    assert [c["_pool_id"] for c in cards] == ["c1", "c2", "c3"]   # tier order = score order


def test_build_slate_fills_when_shortfall():
    import flowdrip_app as fa
    scored = [{"id": "c1", "score": 90, "reason": ""},
              {"id": "c2", "score": 20, "reason": ""},   # below floor
              {"id": "c3", "score": 10, "reason": ""}]   # below floor
    cards = fa._build_slate_cards(_pool3(), scored, "Healthcare PM")
    assert len(cards) == 3
    assert cards[0]["_pool_id"] == "c1"
    assert "_pool_id" not in cards[1] and "_pool_id" not in cards[2]  # fills
    assert cards[1]["label"] == "Candidate B"


def test_build_slate_empty_when_none_clear_floor():
    import flowdrip_app as fa
    scored = [{"id": "c1", "score": 20, "reason": ""},
              {"id": "c2", "score": 10, "reason": ""}]
    cards = fa._build_slate_cards(_pool3(), scored, "Healthcare PM")
    assert cards == []   # skip this company


def test_match_pipeline_to_company_end_to_end(monkeypatch):
    import flowdrip_app as fa
    pool = [{"id": "c1", "target_role": "Healthcare PM", "summary": "OSHPD PM",
             "resume_text": "healthcare"},
            {"id": "c2", "target_role": "Estimator", "summary": "Bridges",
             "resume_text": "civil"}]
    monkeypatch.setattr(fa, "load_candidate_pool", lambda: pool)
    payload = ('[{"id":"c1","score":88,"reason":"healthcare PM"},'
               '{"id":"c2","score":30,"reason":"wrong sector"}]')
    cards = fa._match_pipeline_to_company(_StubClient(payload), "Swinerton",
                                          "Healthcare PM", "Construction")
    assert len(cards) == 3
    assert cards[0]["_pool_id"] == "c1"           # real top match
    assert "_pool_id" not in cards[2]             # filled (only 1 cleared floor)


def test_match_pipeline_skips_when_no_fit(monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "load_candidate_pool",
                        lambda: [{"id": "c1", "target_role": "Chef", "resume_text": "food"}])
    payload = '[{"id":"c1","score":5,"reason":"unrelated"}]'
    cards = fa._match_pipeline_to_company(_StubClient(payload), "Acme",
                                          "Healthcare PM", "Construction")
    assert cards == []


def test_api_resolve_uses_provided_candidates():
    import flowdrip_app as fa
    spec = {"candidates": [{"label": "Candidate A", "role": "PM", "bullets": ["x"]}]}
    cards, skip = fa._api_resolve_5x3_cards(_StubClient("[]"), spec)
    assert skip is None
    assert cards == spec["candidates"]         # passthrough, no matching


def test_api_resolve_matches_when_absent(monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "load_candidate_pool",
                        lambda: [{"id": "c1", "target_role": "PM", "resume_text": "x"}])
    cards, skip = fa._api_resolve_5x3_cards(
        _StubClient('[{"id":"c1","score":90,"reason":"fit"}]'),
        {"company": "Acme", "roles": ["Project Manager"], "industry": "Construction"})
    assert skip is None
    assert len(cards) == 3 and cards[0]["_pool_id"] == "c1"


def test_api_resolve_skips_when_no_fit(monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "load_candidate_pool",
                        lambda: [{"id": "c1", "target_role": "Chef", "resume_text": "x"}])
    cards, skip = fa._api_resolve_5x3_cards(
        _StubClient('[{"id":"c1","score":5,"reason":"no"}]'),
        {"company": "Acme", "roles": ["Project Manager"], "industry": "Construction"})
    assert cards == [] and skip                 # skip reason set

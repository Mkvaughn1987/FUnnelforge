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

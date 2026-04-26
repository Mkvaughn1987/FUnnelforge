"""_aicb_auto_generate_candidates must support a count param 1-6 with
letter labels A-F. Mocks the AI call so we test the parsing/letter logic
without burning API credit."""
from unittest.mock import MagicMock


def _fake_ai_response(letters: list) -> MagicMock:
    """Construct a mock AI response that emits N candidate blocks."""
    body = "\n\n".join(
        f"Candidate {L}: Role Title, 5+ yrs at Acme\n"
        f"• Location: Denver, CO\n"
        f"• Experience: 5+ years\n"
        f"• Skills: Skill1, Skill2"
        for L in letters
    )
    msg = MagicMock()
    block = MagicMock()
    block.text = body
    msg.content = [block]
    return msg


def _wait_until(predicate, timeout=5.0):
    """Spin until predicate() returns True or timeout. The auto-gen
    function runs in a background thread, so tests need to wait."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _wait_for_thread(s, timeout=5.0):
    """Wait until the auto-gen thread has cleared its _aicb_cand_generating
    flag. More reliable than waiting for text to be non-empty (the thread
    sets the flag back to False in its finally block, so this is a
    universal 'done' signal)."""
    return _wait_until(
        lambda: hasattr(s, "_aicb_cand_generating") and not s._aicb_cand_generating,
        timeout=timeout,
    )


def test_auto_generate_count_default_3(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_sel_roles = ["Machinist"]
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_ai_response(["A", "B", "C"]),
    )
    fa._aicb_auto_generate_candidates(s, lambda: None)
    _wait_for_thread(s)
    assert s._aicb_cand_text.count("Candidate A") == 1
    assert s._aicb_cand_text.count("Candidate B") == 1
    assert s._aicb_cand_text.count("Candidate C") == 1
    assert "Candidate D" not in s._aicb_cand_text


def test_auto_generate_count_6(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_sel_roles = ["Machinist"]
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_ai_response(["A", "B", "C", "D", "E", "F"]),
    )
    fa._aicb_auto_generate_candidates(s, lambda: None, count=6)
    _wait_for_thread(s)
    for L in ["A", "B", "C", "D", "E", "F"]:
        assert f"Candidate {L}" in s._aicb_cand_text


def test_auto_generate_count_clamps_to_6(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_sel_roles = ["Machinist"]
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_ai_response(["A", "B", "C", "D", "E", "F"]),
    )
    fa._aicb_auto_generate_candidates(s, lambda: None, count=99)
    _wait_for_thread(s)
    for L in ["A", "B", "C", "D", "E", "F"]:
        assert f"Candidate {L}" in s._aicb_cand_text

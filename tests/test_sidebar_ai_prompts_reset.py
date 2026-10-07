"""Clicking AI Prompt(s) in the sidebar always lands on the job picker."""
import types

import pytest


@pytest.fixture
def fa(monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_nav_snapshot", lambda s: {})
    return fa


def _mid_job():
    return types.SimpleNamespace(
        _nav_history=[], hub="sales", sp="dashboard",
        _aip_req={"routine": "x", "step": "emails"}, _aip_prompt="text",
        _aip_back=None, _aip_pick="x", _aip_from_saved=True)


@pytest.mark.parametrize("key", ["ai_prompts", "tm_prompts"])
def test_sidebar_click_resets_to_job_picker(fa, key):
    s = _mid_job()
    fa._sidebar_nav(s, lambda: None, key, {})
    assert s._aip_req is None and s._aip_prompt is None
    assert s._aip_pick == "" and s._aip_from_saved is False


def test_other_pages_leave_the_job_alone(fa):
    s = _mid_job()
    fa._sidebar_nav(s, lambda: None, "contacts", {})
    assert s._aip_req == {"routine": "x", "step": "emails"}


def test_use_it_from_saved_prompts_keeps_what_it_loaded(fa):
    s = _mid_job()
    fa._sidebar_nav(s, lambda: None, "tm_prompts", {}, keep_state=True)
    assert s._aip_req == {"routine": "x", "step": "emails"}
    assert s._aip_from_saved is True

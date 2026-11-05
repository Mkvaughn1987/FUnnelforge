"""Start a Campaign: one sidebar button, two ways in.

DripDrop folded Start with AI and Create my own campaign into one Start a
Campaign button whose dialog shows both (2026-11-04). inboxslide takes the
same button and dialog in its own terms: Build an AI Campaign opens AI Prompt,
and Build a Custom Campaign opens the walkthrough written for ThriveModal
(tests/test_tm_custom_campaign.py)."""
import inspect
import types

import pytest


def test_sidebar_has_one_start_a_campaign_button():
    import flowdrip_app as fa
    side = inspect.getsource(fa._sidebar_v2)
    assert "ui.label(START_CAMPAIGN_TITLE)" in side
    assert "_start_campaign_dialog(s, rf, _setup)" in side
    assert 'ui.label("Start with AI")' not in side
    # Workspaces with no AI Prompt page keep the plain New Campaign button.
    assert 'ui.label("New Campaign")' in side
    assert fa.START_CAMPAIGN_TITLE == "Start a Campaign"


def test_dialog_offers_ai_then_build_and_neither_is_recommended():
    import flowdrip_app as fa
    opts = fa.START_CAMPAIGN_OPTIONS
    assert [o["key"] for o in opts] == ["ai", "build"]
    # Mike's names for the two cards (2026-11-05).
    assert opts[0]["title"] == "Build an AI Campaign"
    assert opts[1]["title"] == "Build a Custom Campaign"
    assert [o["cta"] for o in opts] == ["Build an AI campaign",
                                        "Build a custom campaign"]
    for o in opts:
        assert o["icon"] in fa._SIDEBAR_ICONS, o["icon"]
        assert o["desc"] and o["points"] and o["cta"]
        assert "tag" not in o and "Recommended" not in str(o)
    # inboxslide's words, not DripDrop's.
    blob = str(opts)
    assert "DripDrop" not in blob or fa.BRAND == "DripDrop"
    assert "ChatGPT" not in blob and "Pipeline" not in blob
    assert "candidate profiles and a Sales PDF" in blob


def test_dialog_cards_navigate_like_their_sidebar_entries():
    import flowdrip_app as fa
    dlg = inspect.getsource(fa._start_campaign_dialog)
    # AI goes through the sidebar navigator (landing view); Custom opens
    # its walkthrough behind the same setup gate.
    assert "_sidebar_nav(s, rf, _ai_prompts_key(), setup, fresh=True)" in dlg
    assert "_open_custom_campaign(s, rf, setup)" in dlg
    assert "dlg.close()" in dlg
    assert "START_CAMPAIGN_OPTIONS" in dlg


@pytest.mark.parametrize("key", ["tm_prompts", "start_seq"])
def test_either_destination_opens_on_its_landing_view(monkeypatch, key):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_nav_snapshot", lambda s: {})
    s = types.SimpleNamespace(
        _nav_history=[], hub="sales", sp="dashboard", _tab="saved",
        _aip_req={"routine": "x"}, _aip_prompt="text", _aip_back=None,
        _aip_pick="x", _aip_from_saved=True,
        loaded_camp=None, custom_steps=[], custom_name="")
    fa._sidebar_nav(s, lambda: None, key, {"ready": True}, fresh=True)
    assert s.sp == key
    if key == "tm_prompts":
        assert s._aip_req is None and s._aip_pick == ""
    else:
        assert s._tab == "" and s.sq == 1


def test_dialog_styles_ship_with_the_sidebar_css():
    import flowdrip_app as fa
    css = fa._sidebar_layout_css()
    for cls in ("grid", "card", "head", "ico", "title", "desc", "pts", "pt", "go"):
        assert f".fd-side-start-{cls}" in css, cls
    dlg = inspect.getsource(fa._start_campaign_dialog)
    # Never a hex alpha appended to a var() colour.
    assert "_tint(C['teal'],'40')" in dlg


def test_tour_step_names_the_button_and_both_ways():
    import flowdrip_app as fa
    src = inspect.getsource(fa.index)
    i = src.index('"title": "Start a Campaign"')
    step = src[i:i + 500]
    assert "Build an AI" in step and "Build a Custom" in step
    assert "Campaigns > Templates" not in src

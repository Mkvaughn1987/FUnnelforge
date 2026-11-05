"""Start a Campaign: one sidebar button, two ways in.

DripDrop folded Start with AI and Create my own campaign into one Start a
Campaign button whose dialog shows both (2026-11-04). inboxslide takes the
same button and dialog in its own terms: Start with AI opens AI Prompt, and
the second card is Build a Campaign, the chooser Campaigns > Build a Campaign
already opens."""
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
    assert opts[0]["title"] == "Start with AI"
    # The card is named after the page it opens and the row that opens it.
    assert opts[1]["title"] == fa.SIDEBAR_CAMPAIGNS[0][1] == "Build a Campaign"
    for o in opts:
        assert o["icon"] in fa._SIDEBAR_ICONS, o["icon"]
        assert o["desc"] and o["points"] and o["cta"]
        assert "tag" not in o and "Recommended" not in str(o)
    # inboxslide's words, not DripDrop's.
    blob = str(opts)
    assert "DripDrop" not in blob or fa.BRAND == "DripDrop"
    assert "ChatGPT" not in blob and "candidates" not in blob.lower()


def test_dialog_cards_navigate_like_their_sidebar_entries():
    import flowdrip_app as fa
    dlg = inspect.getsource(fa._start_campaign_dialog)
    assert "_ai_prompts_key()" in dlg and '"start_seq"' in dlg
    # Through the sidebar navigator: setup gate, wizard reset, landing view.
    assert "_sidebar_nav(" in dlg and "setup, fresh=True" in dlg
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
    assert "Start with" in step and "Build a Campaign" in step
    assert "Campaigns > Templates" not in src

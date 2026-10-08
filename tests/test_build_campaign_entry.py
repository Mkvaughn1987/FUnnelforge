"""Build a Campaign: the hand-built path is a first-class entry point.

Start with AI is the sidebar CTA on inboxslide, so the only way to build a
campaign without AI used to be the Campaigns > Templates sub-row, which
nobody read as "build a campaign". Now it is named that, sits first under
Campaigns like DripDrop's New Campaign, and is offered next to every
"with AI" button and on the AI Prompt landing page."""
import inspect
import types

import ai_prompts as aip
import tm_prompts as tm


def test_build_a_campaign_is_first_campaigns_subrow():
    import flowdrip_app as fa
    assert fa.SIDEBAR_CAMPAIGNS[0] == ("plus", "Build a Campaign", "new")
    assert [r[1] for r in fa.SIDEBAR_CAMPAIGNS] == [
        "Build a Campaign", "Active", "Completed", "Drafts"]
    # Templates pointed at the same chooser; one row, one name.
    assert "Templates" not in [r[1] for r in fa.SIDEBAR_CAMPAIGNS]


def test_chooser_and_wizard_light_build_a_campaign():
    import flowdrip_app as fa

    def st(sp, tab="", done=False):
        return types.SimpleNamespace(hub="sales", sp=sp, ep="", _tab=tab,
                                     _mgr_show_completed=done)
    assert fa._sidebar_campaign_view(st("start_seq")) == "new"
    assert fa._sidebar_active(st("start_seq")) == "campaigns"
    src = inspect.getsource(fa._sidebar_v2)
    # A wizard page (past the chooser) lights the row it started from.
    assert '_view = "new" if _wiz' in src
    # The sidebar's view dispatcher sends "new" to the chooser.
    src = inspect.getsource(fa._sidebar_v2)
    assert '_go("start_seq")' in src


def test_chooser_page_is_titled_build_a_campaign_in_sidebar_layout():
    import flowdrip_app as fa
    assert fa._build_campaign_title() in ("Build a Campaign", "New Campaign")
    src = inspect.getsource(fa._build_campaign_title)
    assert "_SIDEBAR_LAYOUT" in src and "Build a Campaign" in src
    assert "_build_campaign_title()" in inspect.getsource(fa.p_seq)
    assert "_build_campaign_title()" in inspect.getsource(fa._sidebar_page_title)


def test_campaigns_page_offers_build_next_to_ai():
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_seq_mgr)
    # Header row and the empty state both pair the two ways to start.
    assert src.count("_build_campaign_button(s, rf)") == 2
    bsrc = inspect.getsource(fa._build_campaign_button)
    assert '"start_seq"' in bsrc and "Build a campaign" in bsrc
    # Goes through the sidebar navigator so the setup gate and the
    # wizard reset apply, the same as the sidebar row.
    assert "_sidebar_nav(" in bsrc and "_sidebar_setup_status()" in bsrc
    assert "fresh=True" in bsrc


def test_build_button_style_is_scoped_outline_variant():
    import flowdrip_app as fa
    css = fa._sidebar_layout_css()
    assert ".fd-main .fd-aistart-btn.alt{" in css


def test_ai_prompt_landing_offers_hand_build():
    assert tm.TM.build_page == "start_seq"
    assert tm.TM.build_label == "Build a campaign"
    # DripDrop's catalogue is untouched: no link unless a catalogue asks.
    assert aip.ARENA.build_page == ""
    src = inspect.getsource(aip._hand_build_link)
    assert "build_page" in src and "_sidebar_nav(" in src
    assert "_hand_build_link(" in inspect.getsource(aip.render_page)

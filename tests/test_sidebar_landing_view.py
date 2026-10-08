"""A sidebar click opens the page on its landing view, wherever the user
was inside it; in-page jumps that preset a selection keep it."""
import types

import pytest


@pytest.fixture
def fa(monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_nav_snapshot", lambda s: {})
    return fa


def _state(**kw):
    base = dict(_nav_history=[], hub="sales", sp="dashboard", expanded=set())
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_sales_assets_click_goes_back_to_the_picker(fa):
    s = _state(_pdf_stage="form", _pdf_selected=["market_pulse"],
               _pdf_custom_intent=True, _pdf_custom_stage="gallery",
               _pdf_result="x.pdf", _pdf_company="Acme")
    fa._sidebar_nav(s, lambda: None, "pdf_gen", {}, fresh=True)
    assert s._pdf_stage == "pick" and s._pdf_selected == []
    assert s._pdf_custom_stage == "closed" and s._pdf_result == ""
    assert s._pdf_company == "Acme"          # typed form data is kept


def test_every_landing_table_page_resets(fa):
    for k, pairs in fa._PAGE_LANDING.items():
        s = _state(**{a: "dirty" for a, _ in pairs})
        fa._sidebar_nav(s, lambda: None, k, {}, fresh=True)
        for a, v in pairs:
            assert getattr(s, a) == v, (k, a)


def test_landing_lists_are_fresh_copies(fa):
    s = _state()
    fa._reset_page_view(s, "pdf_gen")
    s._pdf_selected.append("x")
    assert dict(fa._PAGE_LANDING["pdf_gen"])["_pdf_selected"] == []


def test_in_page_jump_keeps_its_preset(fa):
    s = _state(_co_open="acme", _co_view="table", _co_stage="", _co_q="")
    fa._sidebar_nav(s, lambda: None, "companies", {}, came_from="sales_dashboard")
    assert s._co_open == "acme"


def test_ai_prompt_fresh_click_lands_on_pick_a_job(fa):
    s = _state(_aip_req={"routine": "x"}, _aip_prompt="t", _aip_back=None,
               _aip_pick="x", _aip_from_saved=True)
    fa._sidebar_nav(s, lambda: None, "tm_prompts", {}, fresh=True)
    assert s._aip_req is None and s._aip_pick == ""


def test_contacts_closes_a_saved_list_copy_only(fa, tmp_path, monkeypatch):
    active = tmp_path / "contacts.csv"
    saved = tmp_path / "Leads.csv"
    monkeypatch.setattr(fa, "_user_contacts_csv_path", lambda: active)
    monkeypatch.setattr(fa, "list_saved_contact_lists", lambda: {"Leads": str(saved)})

    saved.write_text("Email\na@x.com\n"); active.write_text("Email\na@x.com\n")
    s = _state(expanded={"contact_0", "other"})
    fa._sidebar_nav(s, lambda: None, "contacts", {}, fresh=True)
    assert not active.exists() and saved.exists()
    assert s.expanded == {"other"}

    active.write_text("Email\nunsaved@x.com\n")   # not a copy of any list
    fa._sidebar_nav(s, lambda: None, "contacts", {}, fresh=True)
    assert active.exists()

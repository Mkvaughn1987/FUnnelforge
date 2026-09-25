"""Target Positions has its own "Autofill with AI" button on the inboxslide
Target details step. It researches the positions the company is hiring
for right now that fit offshore; with no company filled in it researches
the industry instead. It never drops a position the user already ticked
or typed, and it runs on its own flags so the company Autofill's spinner
is untouched."""
import inspect
import threading
from unittest.mock import MagicMock

import flowdrip_app as fa


class _SyncThread:
    def __init__(self, target=None, daemon=None, **kw):
        self._t = target

    def start(self):
        self._t()


def _msg(text):
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def _run(monkeypatch, s, replies):
    monkeypatch.setattr(threading, "Thread", _SyncThread)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "sk-test")
    calls = []

    def _fake(client, **kw):
        calls.append(kw)
        r = replies[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return _msg(r)

    monkeypatch.setattr(fa, "_claude_create_with_retry", _fake)
    monkeypatch.setattr(fa, "_safe_web_search_tool",
                        lambda max_uses=1: {"max_uses": max_uses})
    renders = []
    fa._tm_autofill_positions(s, lambda: renders.append(1))
    return calls, renders


# ── pure helpers ─────────────────────────────────────────────────────────

def test_merge_keeps_user_ticks_first_then_ai_picks_to_cap():
    out = fa._tm_merge_role_picks(
        ["Bookkeeper", " "],
        ["Dispatcher", "bookkeeper", "AP/AR Specialist", "Data Entry Specialist",
         "Customer Service Representative", "Logistics Coordinator", "Extra"])
    assert out == ["Bookkeeper", "Dispatcher", "AP/AR Specialist",
                   "Data Entry Specialist", "Customer Service Representative",
                   "Logistics Coordinator"]
    assert len(out) == fa._TM_ROLE_MAX


def test_merge_with_nothing_ticked_is_the_ai_order():
    assert fa._tm_merge_role_picks([], ["Dispatcher", "AP/AR Specialist"]) == [
        "Dispatcher", "AP/AR Specialist"]
    assert fa._tm_merge_role_picks(None, None) == []


def test_target_reads_live_company_box_then_state_then_industry():
    s = fa.AppState()
    assert fa._tm_positions_autofill_target(s) == {}
    s.aicb_primary_industry = "Trucking & Logistics"
    assert fa._tm_positions_autofill_target(s) == {
        "company": "", "website": "", "industry": "Trucking & Logistics"}
    s.aicb_company = "Acme"
    s.aicb_website = "acme.com"
    box = MagicMock()
    box.value = "  Acme Freight  "
    s._aicb_step2_refs = {"company": box}
    assert fa._tm_positions_autofill_target(s) == {
        "company": "Acme Freight", "website": "acme.com",
        "industry": "Trucking & Logistics"}


def test_target_falls_back_to_legacy_industry_key_label():
    s = fa.AppState()
    key = next(iter(fa.AICB_INDUSTRIES))
    s.aicb_industry = key
    t = fa._tm_positions_autofill_target(s)
    assert t["industry"] == (fa.AICB_INDUSTRIES[key].get("label") or key)


# ── prompt ───────────────────────────────────────────────────────────────

def test_industry_only_prompt_when_no_company():
    p = fa._tm_offshore_roles_prompt("", "", "Home Services")
    assert p.startswith("Industry:")
    assert "Home Services" in p
    assert "companies in this industry are hiring for RIGHT NOW" in p
    assert "offshore staff augmentation" in p
    assert "open_roles" in p and "offshore_pick" in p
    assert "never return an error" in p
    assert "Company:" not in p


def test_company_prompt_unchanged_when_company_known():
    p = fa._tm_offshore_roles_prompt("Acme", "acme.com", "Home Services")
    assert p.startswith("Company:")
    assert "careers page" in p
    p2 = fa._tm_offshore_roles_prompt("", "acme.com", "")
    assert p2.startswith("Company:")  # a domain alone still names a company


# ── the button's background run ──────────────────────────────────────────

def test_company_run_fills_chips_and_ticks_after_user_picks(monkeypatch):
    s = fa.AppState()
    s.aicb_company = "Yellow Diamond Logistics"
    s.aicb_website = "ydlogistics.com"
    s.aicb_sel_roles = ["Bookkeeper"]
    calls, renders = _run(monkeypatch, s, [
        '{"open_roles":["CDL Driver","Dispatcher","AP/AR Specialist"],'
        '"offshore_pick":["Dispatcher","AP/AR Specialist"]}'])
    assert len(calls) == 1
    assert "Yellow Diamond Logistics" in calls[0]["messages"][0]["content"]
    assert calls[0]["tools"][0]["max_uses"] == 3
    assert s._tm_open_roles == ["CDL Driver", "Dispatcher", "AP/AR Specialist"]
    assert s.aicb_sel_roles == ["Bookkeeper", "Dispatcher", "AP/AR Specialist"]
    assert s._tm_roles_running is False
    assert s._tm_roles_err == ""
    assert renders  # spinner render kicked off


def test_industry_run_when_no_company(monkeypatch):
    s = fa.AppState()
    s.aicb_primary_industry = "Home Services"
    calls, _ = _run(monkeypatch, s, [
        '{"open_roles":["HVAC Technician","Dispatcher","Customer Service '
        'Representative"],"offshore_pick":["Dispatcher","Customer Service '
        'Representative"]}'])
    prompt = calls[0]["messages"][0]["content"]
    assert prompt.startswith("Industry:")
    assert "Home Services" in prompt
    assert s.aicb_sel_roles == ["Dispatcher", "Customer Service Representative"]
    assert s._tm_open_roles == ["HVAC Technician", "Dispatcher",
                                "Customer Service Representative"]
    assert s.aicb_company == ""


def test_live_company_box_is_committed_before_the_search(monkeypatch):
    s = fa.AppState()
    box = MagicMock()
    box.value = "Acme Freight"
    s._aicb_step2_refs = {"company": box}
    calls, _ = _run(monkeypatch, s, ['{"offshore_pick":["Dispatcher"]}'])
    assert s.aicb_company == "Acme Freight"
    assert "Acme Freight" in calls[0]["messages"][0]["content"]


def test_failed_search_keeps_user_ticks_and_shows_error(monkeypatch):
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_sel_roles = ["Bookkeeper"]
    s._tm_open_roles = ["Bookkeeper"]
    _run(monkeypatch, s, [RuntimeError("boom")])
    # _tm_research_offshore_roles swallows the exception and returns
    # empties; the button reports that nothing came back.
    assert s.aicb_sel_roles == ["Bookkeeper"]
    assert s._tm_open_roles == ["Bookkeeper"]
    assert "No positions found" in s._tm_roles_err
    assert s._tm_roles_running is False


def test_nothing_to_search_is_a_toast_not_a_call(monkeypatch):
    s = fa.AppState()
    notes = []
    monkeypatch.setattr(fa.ui, "notify", lambda *a, **k: notes.append(a[0]))
    monkeypatch.setattr(fa, "_claude_create_with_retry",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    fa._tm_autofill_positions(s, lambda: None)
    assert notes and "pick an industry" in notes[0]
    assert not getattr(s, "_tm_roles_running", False)


def test_button_has_its_own_flags_not_the_company_autofills():
    src = inspect.getsource(fa._tm_autofill_positions)
    assert "_tm_roles_running" in src and "_aicb_qs_running" not in src


# ── picker wiring (source greps) ─────────────────────────────────────────

def test_picker_renders_button_spinner_and_error():
    src = inspect.getsource(fa._render_tm_positions_picker)
    assert '"✨ Autofill with AI"' in src
    assert "_tm_autofill_positions(s, rf)" in src
    assert "Searching for positions hiring now that fit " in src
    assert "offshore…" in src
    assert "ui.timer(1.5, _pos_poll)" in src
    assert "_tm_roles_err" in src
    assert "Autofill with AI finds the positions this company, or " in src
    assert "its industry, is hiring for right now that fit offshore." in src

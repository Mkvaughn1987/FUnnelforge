"""Autofill (company mode) on ThriveModal also researches the company and
fills Target Positions with the roles it would most likely staff offshore.
The role research is a second call, so a failed role search never costs
the company details. Arena's company lookup is unchanged."""
import threading
from unittest.mock import MagicMock

import flowdrip_app as fa

LOOKUP = ('{"company":"Yellow Diamond Logistics","website":"ydlogistics.com",'
          '"industry":"","location":"Ontario, CA"}')


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


def _run_extract(monkeypatch, tm: bool, replies: list):
    monkeypatch.setattr(fa, "_SALES_MODE", tm)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda *a, **k: tm)
    monkeypatch.setattr(threading, "Thread", _SyncThread)
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
    s = fa.AppState()
    s.aicb_sel_roles = []
    fa._aicb_ai_extract(s, "ydlogistics.com", "company", lambda: None)
    return s, calls


def test_thrivemodal_autofill_fills_offshore_roles(monkeypatch):
    roles = ('{"roles":["Dispatcher","Logistics Coordinator","dispatcher",'
             '"AP/AR Specialist","Customer Service Representative",'
             '"Data Entry Specialist","Extra"]}')
    s, calls = _run_extract(monkeypatch, True, [LOOKUP, roles])
    assert s._aicb_qs_err == ""
    assert s.aicb_company == "Yellow Diamond Logistics"
    assert s.aicb_sel_roles == ["Dispatcher", "Logistics Coordinator",
                                "AP/AR Specialist",
                                "Customer Service Representative",
                                "Data Entry Specialist"]
    assert s.aicb_sel_locations == ["Nationwide"]
    # First call is the untouched company lookup.
    assert "offshore" not in calls[0]["messages"][0]["content"]
    prompt = calls[1]["messages"][0]["content"]
    assert "Yellow Diamond Logistics" in prompt
    assert "offshore staff augmentation" in prompt
    assert "Dispatcher / freight operations support" in prompt  # catalog
    assert calls[1]["tools"][0]["max_uses"] == 3


def test_failed_role_search_keeps_company_details(monkeypatch):
    s, _ = _run_extract(monkeypatch, True, [LOOKUP, RuntimeError("boom")])
    assert s._aicb_qs_err == ""
    assert s.aicb_company == "Yellow Diamond Logistics"
    assert s.aicb_sel_roles == []


def test_arena_autofill_unchanged(monkeypatch):
    s, calls = _run_extract(monkeypatch, False, [LOOKUP])
    assert len(calls) == 1
    assert "offshore" not in calls[0]["messages"][0]["content"]
    assert calls[0]["max_tokens"] == 600
    assert calls[0]["tools"][0]["max_uses"] == 2
    assert s.aicb_sel_roles == []


def test_catalog_titles_still_match_benchmarks():
    # The example titles the prompt suggests must map to a cost benchmark,
    # so the first Target Position gets the right wage on the PDFs.
    for title in ("Dispatcher", "AP/AR Specialist", "Logistics Coordinator"):
        assert fa._tm_match_benchmark(title), title


def test_domain_not_found_still_researches_roles(monkeypatch):
    # The lookup sometimes gives up on a small company's domain. The domain
    # is still real: keep it and research roles from it.
    s, calls = _run_extract(monkeypatch, True, [
        '{"error":"not found"}', '{"roles":["Dispatcher"]}'])
    assert s._aicb_qs_err == ""
    assert s.aicb_website == "ydlogistics.com"
    assert s.aicb_sel_roles == ["Dispatcher"]
    assert "ydlogistics.com" in calls[1]["messages"][0]["content"]


def test_name_not_found_is_still_an_error(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", False)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda *a, **k: False)
    monkeypatch.setattr(threading, "Thread", _SyncThread)
    monkeypatch.setattr(fa, "_claude_create_with_retry",
                        lambda client, **kw: _msg('{"error":"not found"}'))
    monkeypatch.setattr(fa, "_safe_web_search_tool", lambda max_uses=1: {})
    s = fa.AppState()
    fa._aicb_ai_extract(s, "Some Unknown Co", "company", lambda: None)
    assert "not found" in s._aicb_qs_err

"""Company Profile > Auto-fill from your website.

The button used to run the lookup in a bare thread and call ui.notify/rf
from it; NiceGUI has no slot there, so the worker died right after a
SUCCESSFUL lookup and the form never showed the import (Kyle, 2026-09-21).
It also brings up the ThriveModal playbook: empty Sales Playbook sections
are staged with their defaults for review before Save."""
import inspect
from types import SimpleNamespace

import flowdrip_app as fa

TM_CFG = {"workspace_playbook": fa.PLAYBOOK_THRIVEMODAL}
KEYS = [k for k, _l, _h, _d in fa.THRIVEMODAL_PLAYBOOK_FIELDS]
DEFAULTS = {k: d for k, _l, _h, d in fa.THRIVEMODAL_PLAYBOOK_FIELDS}


def _profile_src():
    return inspect.getsource(fa)


def test_autofill_click_is_awaited_not_a_bare_thread():
    src = _profile_src()
    i = src.index("Auto-fill from your website")
    block = src[i:i + 5000]
    assert "async def _do_autofill" in block
    assert "run_in_executor(None, _run)" in block
    assert "company_autofill_worker" not in block


def test_empty_sections_are_staged_with_defaults(monkeypatch):
    monkeypatch.setattr(fa, "_LOCKED_PLAYBOOK", fa.PLAYBOOK_THRIVEMODAL)
    cfg = dict(TM_CFG, **{k: "" for k in KEYS})
    cfg[KEYS[0]] = "my own text"
    s = SimpleNamespace()
    n = fa._tm_playbook_autofill_stage(s, cfg)
    staged = s._cp_autofill_pb_pending
    assert KEYS[0] not in staged
    assert n == len(staged) and n >= 1
    for k, v in staged.items():
        assert v == DEFAULTS[k]


def test_untouched_workspace_stages_nothing(monkeypatch):
    # Absent keys already resolve to the defaults; nothing to stage.
    monkeypatch.setattr(fa, "_LOCKED_PLAYBOOK", fa.PLAYBOOK_THRIVEMODAL)
    s = SimpleNamespace(_cp_autofill_pb_pending={"stale": "x"})
    assert fa._tm_playbook_autofill_stage(s, dict(TM_CFG)) == 0
    assert s._cp_autofill_pb_pending == {}


def test_arena_workspace_stages_nothing(monkeypatch):
    monkeypatch.setattr(fa, "_LOCKED_PLAYBOOK", "")
    s = SimpleNamespace()
    cfg = {"workspace_playbook": fa.PLAYBOOK_ARENA, **{k: "" for k in KEYS}}
    assert fa._tm_playbook_autofill_stage(s, cfg) == 0

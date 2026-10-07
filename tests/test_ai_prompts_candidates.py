"""The candidate block on every AI Prompts run that carries a slate
(Mike, 2026-10-06).

Up to 3 per company, filled in screen order: the people picked from the
Pipeline (only where they fit), then DripDrop's best Pipeline matches, then
AI candidates. "Just use AI candidates" is the shortcut for the last alone.
The MPC run keeps its own picker.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ai_prompts_catalogue import _stub_nicegui  # noqa: E402

RUNS = ["slate_campaign", "staff_signal_hunt", "staff_lookalikes",
        "staff_agency_displace"]
JANE = "Jane Doe - Estimator, Denver CO (Ref #1042)"
BOB = "Bob Roe - Superintendent, Boulder CO (Ref #77)"
CY = "Cy Poe - PM, Golden CO (Ref #9)"


@pytest.fixture(scope="module")
def mods():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_prompts
    import staffing_prompts
    return ai_prompts, staffing_prompts


def _prompt(mods, routine, **vals):
    aip, sp = mods
    r = sp.STAFFING.routine_by_key[routine]
    v = aip.defaults_for(r)
    v.update(vals)
    return " ".join(aip.build_prompt({"routine": routine, "vals": v},
                                     sp.STAFFING).split())


@pytest.mark.parametrize("routine", RUNS)
def test_every_slate_run_has_the_block(mods, routine):
    aip, sp = mods
    fb = sp.STAFFING.routine_by_key[routine]["field_by_key"]
    assert fb["cand_picks"]["type"] == "people"
    assert fb["cand_match"]["default"] is True
    assert fb["cand_ai"]["default"] is True
    assert not fb["cand_picks"]["ask"]


def test_mpc_keeps_its_own_picker(mods):
    aip, sp = mods
    fb = sp.STAFFING.routine_by_key["mpc_campaign"]["field_by_key"]
    assert "cand_picks" not in fb and fb["candidates"]["type"] == "people"


def test_present_candidates_lost_the_old_questions(mods):
    aip, _sp = mods
    fb = aip.ARENA.routine_by_key["slate_campaign"]["field_by_key"]
    assert "slate_size" not in fb and "ai_fallback" not in fb


@pytest.mark.parametrize("routine", RUNS)
def test_defaults_match_then_ai(mods, routine):
    p = _prompt(mods, routine)
    assert "Now the candidates: up to 3 per company" in p
    assert "First, fill the open spots at each company with the best fits" in p
    assert "Then fill every spot still open with an AI candidate" in p
    assert '"_pool_id": the id from candidates_search' in p
    assert '"_synthetic": true' in p
    assert "which were Pipeline matches and which were AI candidates" in p
    assert "candidates_search" in p.split("TOOLS")[1]
    assert "{" not in p.replace('{"label"', "")


@pytest.mark.parametrize("routine", RUNS)
def test_picks_go_only_where_they_fit(mods, routine):
    p = _prompt(mods, routine, cand_picks="; ".join([JANE, BOB]))
    assert "First, the people I picked from my Pipeline: %s; %s." % (
        JANE, BOB) in p
    assert "leave them off the companies they don't fit" in p
    assert "Then fill the open spots" in p
    assert ("which were people I picked, which were Pipeline matches and "
            "which were AI candidates") in p


@pytest.mark.parametrize("routine", RUNS)
def test_ai_only_never_searches_the_pipeline(mods, routine):
    p = _prompt(mods, routine, cand_picks="", cand_match=False, cand_ai=True)
    assert "First, fill all 3 spots at each company with an AI candidate" in p
    assert "candidates_search" not in p
    assert "_pool_id" not in p and '"_synthetic": true' in p
    assert "In your read-back, say for every company" not in p


@pytest.mark.parametrize("routine", RUNS)
def test_picks_only_sends_light_rather_than_inventing(mods, routine):
    p = _prompt(mods, routine, cand_picks=JANE, cand_match=False,
                cand_ai=False)
    assert "Do not invent anyone to fill the slate" in p
    assert "AI candidate" not in p and "_synthetic" not in p


@pytest.mark.parametrize("routine", RUNS)
def test_nothing_on_means_no_candidates(mods, routine):
    p = _prompt(mods, routine, cand_picks="", cand_match=False,
                cand_ai=False)
    assert "Now the candidates" not in p
    assert "leave the candidates argument out" in p
    assert "candidates_search" not in p


def test_three_picks_fill_every_spot(mods):
    p = _prompt(mods, "staff_signal_hunt",
                cand_picks="; ".join([JANE, BOB, CY]))
    assert "the people I picked" in p
    assert "best fits from my DripDrop Pipeline" not in p
    assert "AI candidate" not in p


def test_staffing_show_step_mentions_the_candidates(mods):
    assert "the candidates going to each one," in _prompt(
        mods, "staff_agency_displace")
    assert "the candidates going to each one," not in _prompt(
        mods, "staff_agency_displace", cand_match=False, cand_ai=False)


def test_lookalike_keeps_its_source_company(mods):
    p = _prompt(mods, "staff_lookalikes", seed="acmemechanical.com")
    assert "Set source_company" in p and "Now the candidates" in p


@pytest.mark.parametrize("old,want", [
    ("Have DripDrop's AI build the rest", True),
    ("Send fewer - real bench people only", False)])
def test_old_present_candidates_setups_carry_over(mods, old, want):
    aip, _sp = mods
    vals = {"ai_fallback": old, "slate_size": "3"}
    aip._migrate_candidates(vals)
    assert vals["cand_ai"] is want
    p = " ".join(aip.build_prompt({"routine": "slate_campaign",
                                   "vals": {"ai_fallback": old}}).split())
    assert ("AI candidate" in p) is want


def test_migration_never_overrides_a_new_answer(mods):
    aip, _sp = mods
    vals = {"ai_fallback": "Send fewer - real bench people only",
            "cand_ai": True}
    aip._migrate_candidates(vals)
    assert vals["cand_ai"] is True


# ── The screen ────────────────────────────────────────────────────────────

class _El:
    """Enough of a NiceGUI element to record what the block does."""

    def __init__(self, *a, **k):
        self.text = a[0] if a and isinstance(a[0], str) else ""
        self.value = k.get("value")
        self.enabled = True
        self.visible = True
        self.on_change = k.get("on_change")

    def __getattr__(self, _n):
        return lambda *a, **k: self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def set_text(self, t):
        self.text = t

    def disable(self):
        self.enabled = False

    def enable(self):
        self.enabled = True

    def set_visibility(self, v):
        self.visible = v


class _UI:
    def __init__(self):
        self.made = []

    def __getattr__(self, name):
        def make(*a, **k):
            el = _El(*a, **k)
            el.kind = name
            self.made.append(el)
            return el
        return make


def _render(aip, monkeypatch, vals, people=()):
    ui = _UI()
    btns = {}
    monkeypatch.setattr(aip, "ui", ui)
    monkeypatch.setattr(aip, "_btn",
                        lambda label, fn, **k: btns.__setitem__(label, fn))
    monkeypatch.setattr(aip, "_aip_owner", lambda s: "me@x.com")
    monkeypatch.setattr(aip, "_pipeline_people", lambda o: list(people))
    redraws = []
    r = aip.ARENA.routine_by_key["slate_campaign"]
    C = {"muted": "#999", "text_l": "#111"}
    aip._candidates_block(object(), lambda: redraws.append(1), C, r, vals)
    boxes = [e for e in ui.made if e.kind == "checkbox"]
    return ui, boxes, btns, redraws


def test_block_greys_the_boxes_at_three_picks(mods, monkeypatch):
    aip, _sp = mods
    vals = {"cand_picks": "; ".join([JANE, BOB, CY])}
    ui, boxes, _b, _r = _render(aip, monkeypatch, vals, [JANE, BOB, CY])
    assert len(boxes) == 2 and not any(b.enabled for b in boxes)
    full = [e for e in ui.made if e.text.startswith("Your 3 spots are full")]
    assert full and full[0].visible
    assert any(e.text == "3 of 3" for e in ui.made)


def test_block_frees_the_boxes_under_three(mods, monkeypatch):
    aip, _sp = mods
    ui, boxes, _b, _r = _render(aip, monkeypatch, {"cand_picks": JANE},
                                [JANE])
    assert all(b.enabled for b in boxes)
    full = [e for e in ui.made if e.text.startswith("Your 3 spots are full")]
    assert not full[0].visible


def test_picking_updates_the_count_in_place(mods, monkeypatch):
    aip, _sp = mods
    vals = {"cand_picks": ""}
    ui, boxes, _b, redraws = _render(aip, monkeypatch, vals, [JANE, BOB, CY])
    sel = [e for e in ui.made if e.kind == "select"][0]
    sel.on_change(type("E", (), {"value": [JANE, BOB, CY]})())
    assert vals["cand_picks"] == "; ".join([JANE, BOB, CY])
    assert not any(b.enabled for b in boxes)
    assert not redraws


def test_just_use_ai_candidates(mods, monkeypatch):
    aip, _sp = mods
    vals = {"cand_picks": JANE, "cand_match": True, "cand_ai": False}
    _ui, _boxes, btns, redraws = _render(aip, monkeypatch, vals, [JANE])
    btns["Just use AI candidates"]()
    assert vals == {"cand_picks": "", "cand_match": False, "cand_ai": True}
    assert redraws

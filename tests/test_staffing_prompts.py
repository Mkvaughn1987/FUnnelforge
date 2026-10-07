"""DripDrop's staffing catalogue for the AI Prompts page (staffing_prompts.py)
and the v10 schedule rules ported into the shared engine.

What is pinned: the eight markets (the Arena Running Campaigns industries,
Mike 2026-10-07) and the signals on each, every new run opening filled in
for the market picked, that a setup saved against an old market label
still opens, that
the old Arena runs still write what they wrote, that nothing in these
prompts names an assistant (they are pasted into Claude or ChatGPT), that
nothing reads WARN notices, and that a schedule question settled by an
earlier answer is not asked.
"""
import inspect
import sys
import types
from contextvars import ContextVar
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_tm_prompts import (  # noqa: E402  (shared stubs)
    _Colours, _fake_anthropic, _fake_ff, _render_all_views, _Session,
    _stub_nicegui)


@pytest.fixture(scope="module")
def mods():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_prompts
    import staffing_prompts
    return ai_prompts, staffing_prompts


@pytest.fixture
def aip(mods):
    return mods[0]


@pytest.fixture
def sp(mods):
    return mods[1]


def _flat(p):
    return " ".join(p.split())


def _req(aip, sp, key, **vals):
    r = sp.STAFFING.routine_by_key[key]
    v = aip.defaults_for(r)
    v.update(vals)
    req = {"routine": key, "vals": v, "summary": "", "detail": []}
    aip.run_prefill(r, req, sp.STAFFING)
    return r, req


# ── The markets and the signals ───────────────────────────────────────────

MARKETS = ["General Contracting", "Mechanical Contracting",
           "Electrical Contracting", "Civil & Engineering",
           "Healthcare Construction", "Data Center / Mission Critical",
           "Heavy Equipment & Rental", "Manufacturing"]


def test_markets_in_order_and_every_one_is_a_running_campaigns_industry(sp):
    # Mike 2026-10-07: the AI Prompts market list follows the Arena Running
    # Campaigns industry filter, so a campaign built here lands in its bucket.
    import team_campaigns as tc
    assert sp.VERTICAL_LABELS == MARKETS
    assert sp.DEFAULT_VERTICAL == "General Contracting"
    for label in sp.VERTICAL_LABELS:
        assert label in tc.INDUSTRY_CHOICES, label


def test_old_market_labels_open_on_the_row_that_replaced_them(sp):
    assert sp.vertical_for("Construction")["key"] == "gc"
    assert sp.vertical_for("construction")["key"] == "gc"
    assert sp.vertical_for("Trades & building services")["key"] == "mechanical"
    assert sp.vertical_for("Engineering / AEC")["key"] == "civil"
    assert sp.vertical_for("aec")["key"] == "civil"
    assert sp.vertical_for("electrical")["key"] == "electrical"
    assert sp.vertical_for("")["key"] == "gc"


def test_every_market_changes_the_whole_page(sp):
    # Each market carries its own band, buyers, roles, signals, opening
    # question and agency terms: picking one redraws every box below it.
    seen = {k: set() for k in ("buyers", "roles", "question")}
    for v in sp.VERTICALS:
        for k in seen:
            assert v[k].strip(), (v["key"], k)
            seen[k].add(v[k])
        assert v["signals"] and v["terms"] and v["band"], v["key"]
    for k, vals in seen.items():
        assert len(vals) == len(sp.VERTICALS), k


def test_signal_counts_match_the_approved_list(sp):
    assert len(sp.UNIVERSAL_SIGNALS) == 8
    got = {v["key"]: len(v["signals"]) for v in sp.VERTICALS}
    assert got == {"gc": 5, "mechanical": 6, "electrical": 6, "civil": 6,
                   "healthcare_construction": 5, "data_center": 5,
                   "equipment": 5, "manufacturing": 5}


def test_every_signal_has_a_why_and_ids_are_unique_per_menu(sp):
    for v in sp.VERTICALS:
        for menu_of in (sp.signal_menu, sp.term_menu):
            menu = menu_of(v)
            ids = [s["id"] for s in menu]
            assert len(ids) == len(set(ids)), v["key"]
            for s in menu:
                assert s["label"].strip() and s["why"].strip(), s


def test_recommended_universal_ids_exist(sp):
    have = {s["id"] for s in sp.UNIVERSAL_SIGNALS}
    for v in sp.VERTICALS:
        assert set(v["also"]) <= have, v["key"]


def test_no_warn_anywhere(sp):
    # Mike 2026-10-01: "Dont use the WARN".
    src = inspect.getsource(sp)
    assert "WARN" not in src.replace("WARNING", "")
    for v in sp.VERTICALS:
        assert "states" not in v


# ── The runs ──────────────────────────────────────────────────────────────

# The four market runs. Find Candidates (staff_find_candidates) has no
# market row: it is covered in tests/test_find_candidates_prompt.py.
NEW = ["staff_signal_hunt", "staff_lookalikes", "staff_agency_displace",
       "staff_account"]


def test_new_runs_come_first_then_every_arena_run(aip, sp):
    keys = [r["key"] for r in sp.STAFFING.routines]
    assert keys[:5] == NEW + ["staff_find_candidates"]
    assert keys[5:] == [r["key"] for r in aip.ARENA.routines]
    starters = [st["id"] for st in sp.STAFFING.starters]
    # "Research one account" came off the picker (Mike 2026-10-02); its
    # routine stays so saved setups still open. Same for "Win Business from
    # Competing Agencies" (Mike 2026-10-06). MPC leads the Arena cards, and
    # Find Candidates sits right after it (Mike 2026-10-06).
    assert starters[:4] == ["staff_signal", "staff_lookalike", "mpc",
                            "staff_find_candidates"]
    assert "staff_account" not in starters
    assert "staff_agency" not in starters
    arena = [st["id"] for st in aip.ARENA.starters]
    assert starters[2:3] + starters[4:] == arena
    for st in sp.STAFFING.starters:
        assert st.get("icon"), st["id"]
        assert st["routine"] in sp.STAFFING.routine_by_key


def test_arena_itself_is_untouched(aip, sp):
    assert aip.ARENA.prefill is None and aip.ARENA.recommend is None
    assert len(aip.ARENA.routines) == len(sp.STAFFING.routines) - 5
    assert sp.STAFFING.setups_file == aip.ARENA.setups_file


@pytest.mark.parametrize("key", NEW)
@pytest.mark.parametrize("vertical", MARKETS)
def test_every_run_builds_for_every_market(aip, sp, key, vertical):
    _r, req = _req(aip, sp, key, vertical=vertical, location="Colorado",
                   seed="acme.com", company="Acme Mechanical")
    p = aip.build_prompt(req, sp.STAFFING)
    assert "{" not in p.replace("{\"label\"", ""), p
    flat = _flat(p)
    assert "Market guide for %s" % vertical in flat
    v = sp.vertical_for(vertical)
    assert v["buyers"] in flat
    assert v["question"] in flat
    if key != "staff_account":
        band = sp._rec_for(sp.STAFFING.routine_by_key[key], v,
                           "company_size", "band")
        assert v["roles"] in flat and band in flat
        # The campaigns are tagged with the market, so Arena Running
        # Campaigns files them under it without reading the free text.
        assert 'industry_category "%s" on every one' % vertical in flat
    if key == "staff_signal_hunt":
        for s in v["signals"]:
            assert s["label"] in flat, (vertical, s["id"])
    if key == "staff_agency_displace":
        for t in v["terms"]:
            assert t["label"] in flat, (vertical, t["id"])
        assert "my DripDrop connector" in flat


def test_signal_hunt_carries_the_ticked_signals_only(aip, sp):
    r, req = _req(aip, sp, "staff_signal_hunt", vertical="Manufacturing",
                  location="Utah")
    flat = _flat(aip.build_prompt(req, sp.STAFFING))
    assert "a plant manager or production manager opening" in flat
    # Unticked by default.
    assert "hiring a recruiter or talent acquisition person" not in flat
    # The guide does not recite the full list above the picked one.
    assert "Signals worth acting on" not in flat


def test_cleared_signals_mean_any_live_hiring(aip, sp):
    r, req = _req(aip, sp, "staff_signal_hunt", location="Utah")
    req["vals"]["signals"] = ""
    flat = _flat(aip.build_prompt(req, sp.STAFFING))
    assert "any live hiring of these roles counts" in flat


def test_missing_signals_get_the_recommendation(aip, sp):
    r = sp.STAFFING.routine_by_key["staff_signal_hunt"]
    vals = {"vertical": "Construction", "location": "Denver"}
    p = _flat(aip.build_prompt({"routine": r["key"], "vals": vals},
                               sp.STAFFING))
    assert "a superintendent or project manager opening" in p


def test_agency_run_searches_agency_terms(aip, sp):
    r, req = _req(aip, sp, "staff_agency_displace",
                  vertical="Engineering / AEC", location="Arizona")
    flat = _flat(aip.build_prompt(req, sp.STAFFING))
    assert "engineering search firm" in flat
    assert "never names the other agency" in flat
    req["vals"]["search_terms"] = ""
    flat = _flat(aip.build_prompt(req, sp.STAFFING))
    assert sp._CHECKS_EMPTY["search_terms"] in flat


def test_agency_run_takes_any_size(aip, sp):
    r, req = _req(aip, sp, "staff_agency_displace",
                  vertical="Construction", location="Charlotte")
    assert req["vals"]["company_size"] == sp.ANY_SIZE
    flat = _flat(aip.build_prompt(req, sp.STAFFING))
    assert "never drop a company for being too big" in flat
    assert "25 to 1000 people" not in flat
    # A saved setup still holding the market's band is moved off it.
    req["vals"]["company_size"] = "25 to 1000 people"
    aip.run_prefill(r, req, sp.STAFFING)
    assert req["vals"]["company_size"] == sp.ANY_SIZE
    # A band someone typed is kept and honoured.
    req["vals"]["company_size"] = "50 to 300 people"
    aip.run_prefill(r, req, sp.STAFFING)
    flat = _flat(aip.build_prompt(req, sp.STAFFING))
    assert "of about 50 to 300 people" in flat
    # The other runs keep the market's band.
    _r, sig = _req(aip, sp, "staff_signal_hunt", vertical="Construction")
    assert sig["vals"]["company_size"] == "25 to 1000 people"


def test_location_is_asked_not_invented(aip, sp):
    r, req = _req(aip, sp, "staff_signal_hunt")
    assert req["vals"]["location"] == ""
    assert "Where" in aip._open_questions(r, req["vals"])


# ── Prefill ───────────────────────────────────────────────────────────────

def test_prefill_fills_and_follows_the_vertical(aip, sp):
    r, req = _req(aip, sp, "staff_signal_hunt",
                  vertical="General Contracting")
    vals = req["vals"]
    c = sp.vertical_for("General Contracting")
    t = sp.vertical_for("Mechanical Contracting")
    assert vals["who_to_reach"] == c["buyers"]
    assert vals["signals"] == ", ".join(sp.signal_ids(c))
    vals["vertical"] = t["label"]
    aip.run_prefill(r, req, sp.STAFFING)
    assert vals["who_to_reach"] == t["buyers"]
    assert vals["signals"] == ", ".join(sp.signal_ids(t))


def test_prefill_never_overwrites_a_typed_answer(aip, sp):
    r, req = _req(aip, sp, "staff_signal_hunt")
    req["vals"]["roles"] = "tower crane operators"
    req["vals"]["vertical"] = "Manufacturing"
    aip.run_prefill(r, req, sp.STAFFING)
    assert req["vals"]["roles"] == "tower crane operators"


def test_old_arena_runs_ignore_the_staffing_hooks(aip, sp):
    r = sp.STAFFING.routine_by_key["slate_campaign"]
    vals = aip.defaults_for(r)
    assert sp.prefill_staffing(r, vals) == {}
    assert sp.checklist_staffing(r, vals, "signals") == []


def test_old_arena_prompts_only_gain_the_two_rules(aip, sp):
    for r in aip.ARENA.routines:
        req = {"routine": r["key"], "vals": aip.defaults_for(r)}
        old = aip.build_prompt(req, aip.ARENA)
        new = aip.build_prompt(req, sp.STAFFING)
        head = old.split("HOW I WANT YOU TO WORK")[0]
        assert new.startswith(head), r["key"]
        assert "Never invent a fill rate" in _flat(new)


# ── Works in Claude or ChatGPT ────────────────────────────────────────────

def test_no_prompt_names_an_assistant(aip, sp):
    for r in sp.STAFFING.routines:
        _r, req = _req(aip, sp, r["key"], location="Denver", seed="a.com",
                       company="Acme", what="x", candidates="Jo",
                       target_company="GCs", search_for="supers",
                       where="Downloads", topic="Denver", who="list",
                       company_niche="GCs")
        req["vals"]["repeat_on"] = True
        p = aip.build_prompt(req, sp.STAFFING)
        for name in ("Claude", "ChatGPT", "GPT"):
            assert name not in p, (r["key"], name)


def test_screen_copy_offers_both(sp):
    assert "ChatGPT" in sp.STAFFING.result_copy
    assert "Claude" in sp.STAFFING.result_copy
    assert sp.STAFFING.assistant == "the AI"


def test_old_let_claude_choose_answer_still_works(aip, sp):
    r = sp.STAFFING.routine_by_key["staff_signal_hunt"]
    for seq in ("Let Claude choose", "Let the AI choose"):
        got = aip._template_clause(r, {"sequence": seq}, sp.STAFFING)
        assert got.startswith("whichever template"), seq


# ── Recommend ─────────────────────────────────────────────────────────────

def test_recommend_filters_ids_and_searches_without_warn(sp, monkeypatch):
    ff = _fake_ff('{"signals": "estimator, NOPE, reposted", '
                  '"roles": "supers", "why": "w"}')
    monkeypatch.setitem(sys.modules, "flowdrip_app", ff)
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic())
    r = sp.STAFFING.routine_by_key["staff_signal_hunt"]
    out, why = sp.recommend_staffing(
        r, {"vertical": "Construction", "location": "Denver"},
        ["signals", "roles"])
    assert out == {"signals": "estimator, reposted", "roles": "supers"}
    assert why == "w"
    tool = ff.sent["tools"][0]
    assert tool["allowed_domains"] == ["indeed.com"]
    # The territory they typed reaches the ask as context.
    assert "Where: Denver" in ff.sent["messages"][0]["content"]


def test_every_recommend_key_is_a_real_box(sp):
    for r in sp.ROUTINES:
        for k in r.get("recommend") or ():
            assert k in r["field_by_key"], (r["key"], k)
            assert k in sp._RECOMMENDABLE, (r["key"], k)
            assert k != "location", r["key"]


# ── The page ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("starter", ["staff_signal", "staff_lookalike",
                                     "linkedin"])
def test_page_renders_every_view(aip, sp, tmp_path, monkeypatch, starter):
    s = _render_all_views(aip, aip.p_ai_prompts, sp.STAFFING, tmp_path,
                          monkeypatch, starter)
    assert "DripDrop" in s._aip_prompt


# ── v10 schedule rules in the engine ──────────────────────────────────────

def _sched(aip, **vals):
    r = aip.ARENA.routine_by_key["slate_campaign"]
    v = aip.defaults_for(r)
    v.update(vals)
    shown = {f["key"] for f in r["fields"]
             if f["section"] == "repeat" and aip._visible(r, v, f)}
    return r, v, shown


def test_nothing_about_the_schedule_until_it_is_on(aip):
    _r, _v, shown = _sched(aip)
    assert shown == {"repeat_on"}


def test_every_day_asks_no_day(aip):
    r, v, shown = _sched(aip, repeat_on=True, repeat_every="Every day")
    assert "repeat_day" not in shown and "repeat_days" not in shown
    assert aip._repeat_when(r, v) == "every day"


def test_every_other_day_asks_which_days(aip):
    r, v, shown = _sched(aip, repeat_on=True,
                         repeat_every="Every other day",
                         repeat_days="Tuesday, Thursday")
    assert "repeat_days" in shown and "repeat_day" not in shown
    assert aip._repeat_when(r, v) == "every other day (Tuesday and Thursday)"


def test_once_a_week_asks_one_day(aip):
    r, v, shown = _sched(aip, repeat_on=True, repeat_every="Once a week",
                         repeat_day="Friday")
    assert "repeat_day" in shown and "repeat_days" not in shown
    assert aip._repeat_when(r, v) == "once a week on Friday"


def test_legacy_cadences_migrate(aip):
    for old, new in [("Every week", "Once a week"),
                     ("Every weekday", "Every day")]:
        v = {"repeat_every": old}
        aip._migrate_cadence(v)
        assert v["repeat_every"] == new
    r, v, _ = _sched(aip, repeat_on=True, repeat_every="Every weekday")
    assert aip._repeat_when(r, v) == "every day"
    r, v, _ = _sched(aip, repeat_on=True, repeat_every="Every month")
    assert aip._repeat_when(r, v) == "every month on Monday"

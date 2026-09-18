"""The ThriveModal catalogue for the AI Prompt page (tm_prompts.py).

The engine is shared with Arena's AI Prompts page; these tests pin what is
different about the inboxslide page: the routines, the recommended
targeting the verticals table fills in, the claims discipline in the
standing rules, and that the page renders under a stubbed nicegui.
"""
import json
import pathlib
import sys
import types
from contextvars import ContextVar
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ai_prompts_golden.json"


def _stub_nicegui():
    if "nicegui" in sys.modules:
        return
    try:
        import nicegui  # noqa: F401  (the real one, if installed)
        return
    except Exception:
        pass
    ng = types.ModuleType("nicegui")

    class _Any:
        def __getattr__(self, _n):
            return _Any()

        def __call__(self, *a, **k):
            return _Any()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            return iter(())

    ng.ui = _Any()
    sys.modules["nicegui"] = ng


@pytest.fixture(scope="module")
def mods():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_prompts
    import tm_prompts
    return ai_prompts, tm_prompts


@pytest.fixture
def tm(mods):
    return mods[1]


@pytest.fixture
def aip(mods):
    return mods[0]


def _defaults(aip, r):
    return aip.defaults_for(r)


def _flat(p):
    """The engine wraps prose at ~74 columns; compare on one line."""
    return " ".join(p.split())


def _section(p, start, end):
    """Text of one prompt section, flattened."""
    i = p.index(start)
    j = p.index(end, i) if end in p[i:] else len(p)
    return _flat(p[i:j])


# ── Shape ────────────────────────────────────────────────────────────────

def test_every_routine_has_fields_steps_and_a_starter(tm):
    keys = [r["key"] for r in tm.ROUTINES]
    assert keys == ["tm_signal_hunt", "tm_lookalikes", "tm_displacement",
                    "tm_cost_pressure", "tm_seasonal", "tm_audience",
                    "tm_account", "other"]
    for r in tm.ROUTINES:
        assert r["fields"], r["key"]
        assert r["steps"], r["key"]
        assert "field_by_key" in r
        assert "repeat_on" in r["field_by_key"]
        assert "unattended" in r["field_by_key"]
    assert {st["routine"] for st in tm.STARTERS} == set(keys)
    assert tm.STARTERS[-1]["id"] == "other"
    assert tm.TM.default_routine in tm.ROUTINE_BY_KEY


def test_catalogue_is_inboxslide_not_dripdrop(tm):
    c = tm.TM
    assert c.product == "inboxslide"
    assert c.connector == "inboxslide connector"
    assert c.setups_file == "tm_prompt_setups.json"
    assert c.page_title == "AI Prompt"
    assert c.derive_extra is tm._derive_tm
    assert c.result_extra is None
    assert "DripDrop" not in c.page_sub and "DripDrop" not in c.result_copy


def test_sequences_map_to_the_offered_thrivemodal_campaign_types(tm):
    assert set(tm.TEMPLATE_KEY.values()) == {
        "tm_conversation", "tm_fivebyseven", "tm_threebythree",
        "tm_fivethreeli", "tm_stay_in_touch", "tm_twelveweek"}
    for label in tm.TEMPLATE_KEY:
        assert label in tm.SEQUENCES
    assert tm.SEQUENCES[-2:] == ["One of my saved styles", "Let Claude choose"]
    assert tm.TM.default_template == "tm_conversation"


def test_verticals_are_ordered_core_first_then_exploratory(tm):
    keys = [v["key"] for v in tm.VERTICALS]
    assert keys[:7] == ["logistics", "freight_forwarding", "accounting",
                        "property_management", "healthcare_admin",
                        "home_care", "general"]
    core = [v for v in tm.VERTICALS if not v["exploratory"]]
    expl = [v for v in tm.VERTICALS if v["exploratory"]]
    assert len(core) == 7 and expl
    assert tm.VERTICALS.index(expl[0]) > tm.VERTICALS.index(core[-1])
    assert "construction_aec" in {v["key"] for v in expl}
    need = {"key", "label", "band", "buyers", "roles", "triggers",
            "workload", "question", "tells", "season", "exploratory"}
    for v in tm.VERTICALS:
        assert need <= set(v), v["key"]
        assert all(v[k] for k in need - {"exploratory"}), v["key"]


def test_vertical_lookup_tolerates_keys_and_loose_labels(tm):
    assert tm.vertical_for("Logistics / 3PL")["key"] == "logistics"
    assert tm.vertical_for("accounting")["key"] == "accounting"
    assert tm.vertical_for("home care")["key"] == "home_care"
    assert tm.vertical_for("")["key"] == "logistics"
    assert tm.vertical_for("Nothing like this")["key"] == "logistics"


# ── Prompts ──────────────────────────────────────────────────────────────

def test_every_routine_builds_with_its_defaults_and_names_inboxslide(tm, aip):
    for r in tm.ROUTINES:
        p = tm.build_prompt({"routine": r["key"], "vals": _defaults(aip, r),
                             "summary": r["blurb"]})
        assert "DripDrop" not in p, r["key"]
        assert "{" not in p and "}" not in p, r["key"]
        assert "HOW TO DO IT" in p and "HOW I WANT YOU TO WORK" in p
        if r["tools"]:
            assert "using my inboxslide connector." in p
            assert "Use my inboxslide connector: " in p
        else:
            assert "I need you to do this for me.\n" in p
            assert "TOOLS" not in p


def test_steps_and_rules_never_quote_a_price_or_a_percentage(tm):
    for r in tm.ROUTINES:
        for st in r["steps"]:
            assert "$" not in st and "%" not in st, r["key"]
    for rule in tm.STANDING_RULES:
        assert "$" not in rule and "%" not in rule
    for v in tm.VERTICALS:
        for k in ("buyers", "roles", "triggers", "workload", "question",
                  "tells", "season"):
            assert "$" not in v[k] and "%" not in v[k], (v["key"], k)


def test_standing_rules_carry_the_claims_discipline(tm):
    rules = "\n".join(tm.STANDING_RULES).lower()
    for phrase in ("wait for me to say go", "quote the literal error",
                   "thrivemodal.com", "employer of record",
                   "no upfront or placement fee", "month to month",
                   "lifetime free replacement", "video pre-screens",
                   "up to sixty to seventy percent", "ceiling, not a promise",
                   "never say guaranteed savings", "one person is not",
                   "knichel logistics", "travel byrds", "not prospects",
                   "accents", "union shops", "under thirty days",
                   "under ninety", "zoominfo connector", "tm_mailboxes"):
        assert phrase in rules, phrase
    # Rule one is the one solo mode swaps out, so it must be the gate.
    assert "wait for me to say go" in tm.STANDING_RULES[0]
    assert tm.TM.unattended_rule == tm.UNATTENDED_RULE


def test_blank_targeting_is_filled_from_the_picked_vertical(tm, aip):
    r = tm.ROUTINE_BY_KEY["tm_signal_hunt"]
    vals = _defaults(aip, r)
    vals["vertical"] = "Accounting / CAS firms"
    p = tm.build_prompt({"routine": "tm_signal_hunt", "vals": vals,
                         "summary": "x"})
    acc = tm.vertical_for("Accounting / CAS firms")
    flat = _flat(p)
    assert "Vertical guide for Accounting / CAS firms" in flat
    assert acc["question"] in flat
    assert "Karbon" in p
    # The details table shows the recommendation the steps were written with.
    assert "How big a company:" in p and "10 to 200 people" in p
    assert "Managing Partner" in p
    assert "exploratory" not in p.lower()


def test_typed_targeting_beats_the_recommendation(tm, aip):
    r = tm.ROUTINE_BY_KEY["tm_signal_hunt"]
    vals = _defaults(aip, r)
    vals["company_size"] = "fifty to eighty people"
    vals["who_to_reach"] = "the CFO only"
    p = tm.build_prompt({"routine": "tm_signal_hunt", "vals": vals,
                         "summary": "x"})
    assert "fifty to eighty people" in p
    assert "the CFO only" in p
    assert "20 to 500 people" not in p


def test_exploratory_vertical_is_flagged_as_a_test(tm, aip):
    r = tm.ROUTINE_BY_KEY["tm_signal_hunt"]
    vals = _defaults(aip, r)
    vals["vertical"] = "Construction / AEC"
    p = tm.build_prompt({"routine": "tm_signal_hunt", "vals": vals,
                         "summary": "x"})
    flat = _flat(p)
    assert "This vertical is exploratory" in flat
    assert "ten to fifteen companies" in flat


def test_signal_hunt_prompt_wires_the_campaign_build(tm, aip):
    r = tm.ROUTINE_BY_KEY["tm_signal_hunt"]
    p = tm.build_prompt({"routine": "tm_signal_hunt",
                         "vals": _defaults(aip, r), "summary": "x"})
    assert 'template "tm_conversation"' in p
    assert "call tm_mailboxes" in p
    assert "create_campaign" in p
    assert "contacts argument" in p
    assert "never more than five" in p
    assert "Posted in the last 30 days".lower() in p.lower()
    assert "Use my inboxslide connector: campaign_types, my_campaign_styles, " \
           "tm_mailboxes, campaigns_list, create_campaign." in _flat(p)
    # Research notes are not a create_campaign argument.
    assert "notes" not in p.split("create_campaign")[1][:400].lower()


def test_lookalikes_default_to_knichel_and_never_name_it_in_emails(tm, aip):
    r = tm.ROUTINE_BY_KEY["tm_lookalikes"]
    p = tm.build_prompt({"routine": "tm_lookalikes",
                         "vals": _defaults(aip, r), "summary": "x"})
    assert "find_similar_companies with knichellogistics.com" in _flat(p)
    assert 'template "tm_conversation"' in p
    assert "40 companies" in p


def test_account_research_sends_nothing(tm, aip):
    r = tm.ROUTINE_BY_KEY["tm_account"]
    vals = _defaults(aip, r)
    vals["company"] = "Acme Freight"
    p = tm.build_prompt({"routine": "tm_account", "vals": vals,
                         "summary": "x"})
    # The steps never build anything; only the standing rules mention the tool.
    steps = _section(p, "HOW TO DO IT", "HOW I WANT YOU TO WORK")
    assert "create_campaign" not in steps
    assert "TOOLS" not in p
    assert "Do not draft the outreach emails" in steps
    assert "Acme Freight" in p


def test_audience_routine_uses_the_audience_tools(tm, aip):
    r = tm.ROUTINE_BY_KEY["tm_audience"]
    vals = _defaults(aip, r)
    vals["audience"] = "Denver property managers"
    p = tm.build_prompt({"routine": "tm_audience", "vals": vals,
                         "summary": "x"})
    assert "Call tm_audiences" in p
    assert "tm_audience_preview" in p
    assert "Denver property managers" in p
    assert "batches of that size" in _flat(p)


def test_solo_mode_swaps_the_gate_rule(tm, aip):
    r = tm.ROUTINE_BY_KEY["tm_signal_hunt"]
    vals = _defaults(aip, r)
    vals["unattended"] = aip.UNATTENDED[1]
    p = tm.build_prompt({"routine": "tm_signal_hunt", "vals": vals,
                         "summary": "x"})
    flat = _flat(p)
    assert tm.UNATTENDED_RULE in flat
    assert tm.STANDING_RULES[0] not in flat
    assert "call tm_mailboxes" in flat


def test_arena_golden_is_untouched_by_the_hook(aip):
    """Loading tm_prompts must not move Arena's output by a byte."""
    with open(FIXTURE, encoding="utf-8") as fh:
        cases = json.load(fh)
    for case in cases:
        assert aip.build_prompt(case["req"], aip.ARENA) == case["prompt"], \
            case["name"]


# ── Page render ──────────────────────────────────────────────────────────

class _Colours(dict):
    def __missing__(self, k):
        return "#000000"


def _fake_flowdrip(tmp_path):
    m = types.ModuleType("flowdrip_app")
    m._BASE_DATA_DIR = tmp_path
    m.C = _Colours()
    m._resolve_user_root = lambda: tmp_path / "user"
    m._CURRENT_USER_EMAIL = ContextVar("_CURRENT_USER_EMAIL", default="")
    return m


class _Session:
    _user_email = "mike@example.com"


def _render_all_views(aip, page, cat, tmp_path, monkeypatch, starter_id):
    monkeypatch.setitem(sys.modules, "flowdrip_app", _fake_flowdrip(tmp_path))
    rf = lambda: None  # noqa: E731
    s = _Session()
    page(s, rf)                                  # ask
    assert aip._CAT is cat
    aip._CAT = cat
    s._aip_req = aip._req_from_starter(cat.starter_by_id[starter_id])
    page(s, rf)                                  # confirm
    s._aip_prompt = aip.build_prompt(s._aip_req, cat)
    page(s, rf)                                  # result
    assert aip._setups_path() == tmp_path / "user" / cat.setups_file
    return s


def test_p_tm_prompts_renders_ask_confirm_and_result(aip, tm, tmp_path,
                                                     monkeypatch):
    s = _render_all_views(aip, tm.p_tm_prompts, tm.TM, tmp_path, monkeypatch,
                          "signal")
    assert s._aip_req["routine"] == "tm_signal_hunt"
    assert s._aip_req["vals"]["vertical"] == "Logistics / 3PL"
    assert "inboxslide" in s._aip_prompt and "DripDrop" not in s._aip_prompt
    aip._CAT = aip.ARENA


def test_p_ai_prompts_still_renders_arena(aip, tmp_path, monkeypatch):
    s = _render_all_views(aip, aip.p_ai_prompts, aip.ARENA, tmp_path,
                          monkeypatch, aip.ARENA.starters[0]["id"])
    assert "DripDrop" in s._aip_prompt
    assert aip._setups_path().name == "ai_prompt_setups.json"


def test_page_binding_is_the_catalogue_passed(aip, tm, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "flowdrip_app", _fake_flowdrip(tmp_path))
    tm.p_tm_prompts(_Session(), lambda: None)
    assert aip._CAT is tm.TM
    aip.p_ai_prompts(_Session(), lambda: None)
    assert aip._CAT is aip.ARENA

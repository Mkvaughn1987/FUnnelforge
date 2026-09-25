"""The ThriveModal catalogue for the AI Prompt page (tm_prompts.py).

The engine is shared with Arena's AI Prompts page; these tests pin what is
different about the inboxslide page: the routines, the recommended
targeting the verticals table fills in, the claims discipline in the
standing rules, and that the page renders under a stubbed nicegui.
"""
import json
import pathlib
import re
import sys
import types
from contextvars import ContextVar
from datetime import date
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
        "tm_fivebyseven", "tm_threebythree", "tm_conversation",
        "tm_hiring_signal", "tm_twelveweek", "tm_stay_in_touch",
        "tm_reengage", "tm_meeting_followup"}
    for label in tm.TEMPLATE_KEY:
        assert label in tm.SEQUENCES
    assert tm.SEQUENCES[-2:] == ["One of my saved styles", "Let Claude choose"]
    assert tm.TM.default_template == "tm_fivebyseven"
    assert tm.DEFAULT_SEQUENCE == "Standard Outreach"


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
    # A hiring signal defaults to the They're Hiring sequence.
    assert 'template "tm_hiring_signal"' in p
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
    assert 'template "tm_fivebyseven"' in p
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


# ── Recommend these for me ────────────────────────
#
# The seasonal run is the one whose answers depend on the date, so it is
# the one that can have them worked out. Everything below pins what the
# model is told and what is done with what it says back.


class _Colours(dict):
    def __missing__(self, k):
        return "#000000"


_CITE_RE = re.compile(r"[\(\[<]\s*/?\s*cite\b[^>\)\]\n]{0,300}?[>\)\]]",
                      re.IGNORECASE)


def _real_strip_cite_tags(text):
    """What flowdrip_app._strip_cite_tags does, to the extent these tests
    depend on it: the markup goes, the wrapped text stays."""
    return _CITE_RE.sub("", text or "").strip()


class _Reply:
    def __init__(self, text):
        self.content = [types.SimpleNamespace(text=text)]


def _fake_ff(reply, key="sk-ant-test"):
    """flowdrip_app as recommend_tm needs it, recording the call."""
    m = types.ModuleType("flowdrip_app")
    m._BASE_DATA_DIR = pathlib.Path(".")
    m.C = _Colours()
    m.ANTHROPIC_API_KEY = key
    m.sent = {}
    m._injection_guarded_system = lambda base: "GUARD " + base
    m._WARN_SEARCH_DOMAINS = ["dol.gov", "edd.ca.gov"]
    m._safe_web_search_tool = lambda max_uses=3, extra_domains=(): {
        "type": "web_search_20250305", "name": "web_search",
        "max_uses": max_uses,
        "allowed_domains": ["indeed.com"] + list(extra_domains)}
    # The real one off flowdrip_app; the leak it prevents is the point.
    m._strip_cite_tags = _real_strip_cite_tags

    def _create(client, **kw):
        m.sent.update(kw)
        if isinstance(reply, Exception):
            raise reply
        return _Reply(reply)

    m._claude_create_with_retry = _create
    return m


def _fake_anthropic():
    a = types.ModuleType("anthropic")
    a.Anthropic = lambda api_key=None: types.SimpleNamespace(key=api_key)
    return a


def _recommend(tm, monkeypatch, reply, vals=None, key="sk-ant-test",
               routine="tm_seasonal", keys=None):
    ff = _fake_ff(reply, key)
    monkeypatch.setitem(sys.modules, "flowdrip_app", ff)
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic())
    r = tm.ROUTINE_BY_KEY[routine]
    got = tm.recommend_tm(
        r, dict(vals or {"vertical": "Accounting / CAS firms"}), keys)
    return got, ff


def test_every_run_that_can_be_recommended_for_declares_its_keys(tm):
    got = {r["key"]: list(r.get("recommend") or ()) for r in tm.ROUTINES}
    assert got == {
        "tm_signal_hunt": ["location", "company_size", "roles",
                           "who_to_reach", "triggers"],
        "tm_lookalikes": ["location", "company_size", "roles",
                          "who_to_reach"],
        "tm_displacement": ["location", "company_size", "roles",
                            "who_to_reach", "search_terms"],
        "tm_cost_pressure": ["states", "lookback", "location",
                             "company_size", "roles", "who_to_reach"],
        "tm_seasonal": ["season_note", "location", "company_size", "roles",
                        "who_to_reach"],
        # Nothing to recommend: the audience is the name of the user's own
        # saved list, the account run starts from a company they name, and
        # "other" is them describing a job in their own words.
        "tm_audience": [],
        "tm_account": ["who_to_reach"],
        "other": [],
    }
    for r in tm.ROUTINES:
        for k in r.get("recommend") or ():
            # Every key named is a real question on that run, or the button
            # would fill a box the screen never renders.
            assert k in r["field_by_key"], (r["key"], k)
            assert k in tm._RECOMMENDABLE, (r["key"], k)


def test_each_run_is_asked_only_for_its_own_keys(tm, monkeypatch):
    for r in tm.ROUTINES:
        want = list(r.get("recommend") or ())
        if not want:
            continue
        _, ff = _recommend(tm, monkeypatch, "{}", routine=r["key"])
        sent = ff.sent["messages"][0]["content"]
        for k in tm._RECOMMENDABLE:
            assert (("%s:" % k) in sent) == (k in want), (r["key"], k)
        # The run says which run it is, so the answers fit it.
        assert r["name"] in sent


def test_what_they_already_answered_goes_in_as_context(tm, monkeypatch):
    _, ff = _recommend(
        tm, monkeypatch, "{}", routine="tm_lookalikes",
        vals={"vertical": "Accounting / CAS firms",
              "seed": "Knichel Logistics", "location": "Texas"},
        keys=["company_size", "roles", "who_to_reach"])
    sent = ff.sent["messages"][0]["content"]
    # location was not asked for this time, so it is context, not a question.
    assert "<already_answered>" in sent
    assert "Texas" in sent and "Knichel Logistics" in sent
    assert "location: where" not in sent


def test_the_ask_carries_todays_date_and_the_vertical_row(tm, monkeypatch):
    (out, why), ff = _recommend(
        tm, monkeypatch,
        '{"season_note": "s", "company_size": "c", "roles": "r", '
        '"who_to_reach": "w", "why": "because"}',
        {"vertical": "Accounting / CAS firms", "location": "Texas"})
    sent = " ".join(ff.sent["messages"][0]["content"].split())
    v = tm.VERTICAL_BY_LABEL["Accounting / CAS firms"]
    assert date.today().strftime("%d %B %Y") in sent
    assert v["label"] in sent and " ".join(v["season"].split()) in sent
    assert " ".join(v["buyers"].split()) in sent
    # location is one of the answers this run asks for now, so it is a
    # question here rather than context.
    assert "location: where in the United States to work" in sent
    # The row is the ground truth; the date is what it cannot know.
    assert "ground truth" in sent
    assert "cannot know is today's date or which run this is" in sent
    # Claims discipline rides along, same as the standing rules.
    assert "Never invent a client count" in sent
    assert ff.sent["system"].startswith("GUARD ")
    assert out == {"season_note": "s", "company_size": "c", "roles": "r",
                   "who_to_reach": "w"}
    assert "Run a seasonal push" in sent
    assert why == "because"


def test_an_exploratory_vertical_says_so(tm, monkeypatch):
    expl = next(v for v in tm.VERTICALS if v["exploratory"])
    _, ff = _recommend(tm, monkeypatch, '{"season_note": "s"}',
                       {"vertical": expl["label"]})
    assert "exploratory" in ff.sent["messages"][0]["content"]
    _, ff = _recommend(tm, monkeypatch, '{"season_note": "s"}',
                       {"vertical": "Accounting / CAS firms"})
    assert "exploratory" not in ff.sent["messages"][0]["content"]


def test_stray_keys_and_unusable_shapes_are_dropped(tm, monkeypatch):
    (out, why), _ = _recommend(
        tm, monkeypatch,
        'here you go ```json\n{"season_note": "  a   b  ", '
        '"roles": ["a", "b"], "company_size": null, "who_to_reach": true, '
        '"newsletter": "hijacked", "why": "w"}\n``` hope that helps')
    assert out == {"season_note": "a b"}
    assert why == "w"


def test_nothing_usable_comes_back_as_an_empty_answer(tm, monkeypatch):
    (out, why), _ = _recommend(tm, monkeypatch, '{"why": "no idea"}')
    assert out == {} and why == "no idea"
    with pytest.raises(RuntimeError):
        _recommend(tm, monkeypatch, "I could not work that out, sorry.")
    with pytest.raises(RuntimeError):
        _recommend(tm, monkeypatch, '{"season_note": "s"}', key="")


def test_the_button_is_awaited_not_run_in_a_bare_thread(aip):
    """ui.notify and rf() need the page's slot context, which a thread has
    none of, so a threaded worker dies on its own success notify (0f8b435)."""
    import inspect
    block = inspect.getsource(aip._aip_recommend)
    assert "async def _go" in block
    assert "run_in_executor" in block
    assert "threading" not in block and "Thread(" not in block


def test_a_failed_recommendation_still_falls_back_to_the_table(tm, aip):
    """The button is a shortcut, not a dependency: a blank box still picks
    up the vertical's own recommendation when the prompt is built."""
    r = tm.ROUTINE_BY_KEY["tm_seasonal"]
    vals = aip.defaults_for(r)
    vals["vertical"] = "Accounting / CAS firms"
    for k in r["recommend"]:
        vals[k] = ""
    req = {"routine": r["key"], "vals": vals, "detail": [], "filled": []}
    v = tm.VERTICAL_BY_LABEL["Accounting / CAS firms"]
    assert _flat(v["season"]) in _flat(tm.build_prompt(req))


def test_a_box_you_typed_in_yourself_is_never_overwritten(aip, tm):
    """Pressing the button must not quietly replace an answer someone
    chose. Boxes it filled itself are fair game again, so pressing twice
    re-recommends rather than doing nothing."""
    import inspect
    block = inspect.getsource(aip._aip_recommend)
    assert "_untouched" in block and "rec_wrote" in block

    r = tm.ROUTINE_BY_KEY["tm_seasonal"]
    vals = aip.defaults_for(r)
    req = {"routine": r["key"], "vals": vals, "detail": [], "filled": []}

    def _fill(k):
        cur = str(vals.get(k) or "").strip()
        default = str(r["field_by_key"][k].get("default") or "").strip()
        return (not cur or cur == default
                or k in set(req.get("rec_wrote") or ()))

    # Untouched to start: blank season_note, default location.
    assert _fill("season_note") and _fill("location")
    vals["location"] = "Texas and the Southeast"      # their own answer
    assert not _fill("location")
    req["rec_wrote"] = ["location"]                   # ...unless we wrote it
    assert _fill("location")


def test_the_call_can_search_and_reaches_the_warn_sites(tm, monkeypatch):
    """Picking which states' WARN notices to read is a question about what
    has actually been filed, so the call gets search - widened to the
    state labour departments, which the general allowlist has none of."""
    _, ff = _recommend(tm, monkeypatch, "{}", routine="tm_cost_pressure")
    tool = ff.sent["tools"][0]
    assert tool["name"] == "web_search"
    assert "dol.gov" in tool["allowed_domains"]
    assert "indeed.com" in tool["allowed_domains"]   # the base list survives
    sent = ff.sent["messages"][0]["content"]
    assert "states is the one to search for" in sent
    assert "could not see live notices" in sent      # and says so if blind
    assert "No URLs, no source names" in sent
    assert "web search" in ff.sent["system"]


def test_citation_markup_never_reaches_a_form_box(tm, monkeypatch):
    """Web-search citations leaked into newsletters as visible markup once.
    These answers go straight into inputs, so they come off here."""
    reply = json.dumps({
        "season_note": '(cite index="4-1">Busy season starts in '
                       'January(/cite)',
        "why": '<cite index="2-1">peak</cite> is near',
    })
    (out, why), _ = _recommend(tm, monkeypatch, reply)
    assert out["season_note"] == "Busy season starts in January"
    assert why == "peak is near"
    assert "cite" not in out["season_note"] and "cite" not in why


def test_arena_has_no_recommend_hook(aip, tm):
    assert aip.ARENA.recommend is None
    assert tm.TM.recommend is tm.recommend_tm
    for r in aip.ARENA.routines:
        assert not r.get("recommend"), r["key"]


# ── Page render ──────────────────────────────────────────────────────────

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


def test_saved_prompt_opens_straight_on_the_built_prompt():
    # Saved Prompts "Open" (2026-09-19): load the saved answers and build
    # the prompt in one go; "Edit answers" loads them without building.
    import ai_prompts as e
    import tm_prompts as t
    from types import SimpleNamespace as NS
    e._CAT = t.TM
    r = t.TM.routine_by_key[t.TM.default_routine]
    row = {"id": "x", "name": "Dallas CPAs", "routine": r["key"],
           "vals": dict(e.defaults_for(r), bogus_old_key="dropped")}
    s = NS()
    e._open_setup(s, row, built=True)
    assert s._aip_req["title"] == "Dallas CPAs"
    assert "bogus_old_key" not in s._aip_req["vals"]
    assert s._aip_prompt == e.build_prompt(s._aip_req)
    e._open_setup(s, row)
    assert s._aip_prompt is None
    assert hasattr(t, "p_tm_saved_prompts")

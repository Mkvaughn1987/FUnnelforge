"""Create Your Own on the inboxslide AI Prompt (Mike 2026-10-08): the user
builds the campaign step by step, picks a PDF and candidate profiles per
email, and the prompt hands those exact steps to create_campaign as
template "tm_custom", which writes them in that order."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_ai_prompts_catalogue import _stub_nicegui  # noqa: E402


@pytest.fixture(scope="module")
def mods():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_prompts
    import tm_prompts
    return ai_prompts, tm_prompts


@pytest.fixture(scope="module")
def fa():
    import flowdrip_app
    return flowdrip_app


# ── The page side ─────────────────────────────────────────────────────────

def test_card_is_offered_before_let_claude_choose(mods):
    _aip, tm = mods
    assert tm.SEQUENCES[-2:] == ["Create Your Own", "Let Claude choose"]
    info = tm.SEQUENCE_INFO["Create Your Own"]
    assert info["tag"] == "You build it" and info["builder"]
    assert "Create Your Own" not in tm.TEMPLATE_KEY


def test_pdf_menu_is_the_apps_pdf_list(mods, fa):
    _aip, tm = mods
    assert tm.CUSTOM_PDFS == [(k, lab) for k, lab, _l
                              in fa._TM_CAMPAIGN_PDF_KINDS]


def test_profile_counts_are_three_to_six(mods, fa):
    _aip, tm = mods
    assert tm.CUSTOM_PROFILES == ["3", "4", "5", "6"]
    assert fa.TM_CUSTOM_PROFILES_MAX == 6
    assert fa._clamp_ai_profiles(9, fa.TM_CUSTOM_PROFILES_MAX) == 6
    # The ready-made types keep their cap of five.
    assert fa._clamp_ai_profiles(6) == 5


def test_recommended_lineup_is_valid_for_the_server(mods, fa):
    _aip, tm = mods
    steps, err = fa._tm_custom_steps(tm.CUSTOM_DEFAULT_STEPS)
    assert err == "" and len(steps) == 7
    assert [s["type"] for s in steps] == [
        "email", "email", "linkedin", "email", "call", "email", "email"]
    assert {s["pdf"] for s in steps if s["pdf"]} == {
        "tm_cost_compare", "tm_how_it_works"}
    assert [i for i, s in enumerate(steps) if s["profiles"]] == [5]
    # Every angle a step can take is a real recommendation, not blank.
    for kind, angles in tm.CUSTOM_ANGLES.items():
        assert angles and all(w.strip() for _lab, w in angles), kind


def test_cleaner_makes_any_half_edited_list_valid(mods, fa):
    _aip, tm = mods
    messy = {"custom_steps": [
        {"type": "call", "day": 5, "what": "  hi  ", "pdf": "tm_myths",
         "profiles": True},
        {"type": "email", "day": 0, "what": "two", "pdf": "tm_myths",
         "profiles": True},
        {"type": "linkedin", "day": "x", "pdf": "tm_security",
         "profiles": True},
        {"type": "email", "day": 3, "pdf": "tm_myths"},
        {"type": "bogus", "day": 999, "pdf": "nope"},
    ]}
    steps = tm.custom_steps(messy)
    assert steps[0] == {"type": "email", "day": 1, "what": "hi", "pdf": "",
                        "profiles": False}
    assert steps[1]["pdf"] == "tm_myths" and steps[1]["profiles"]
    assert steps[2]["pdf"] == "" and not steps[2]["profiles"]
    assert steps[3]["pdf"] == ""  # that PDF already rides on step 2
    assert steps[4] == {"type": "email", "day": 130, "what": "", "pdf": "",
                        "profiles": False}
    assert fa._tm_custom_steps(steps)[1] == ""
    # Nothing usable: the recommended lineup.
    assert tm.custom_steps({}) == tm.CUSTOM_DEFAULT_STEPS
    assert len(tm.custom_steps({"custom_steps": [{}] * 20})) == 12


def test_prompt_hands_the_steps_to_create_campaign(mods):
    aip, tm = mods
    r = tm.ROUTINE_BY_KEY["tm_signal_hunt"]
    vals = aip.defaults_for(r)
    vals["sequence"] = "Create Your Own"
    vals["custom_steps"] = [
        {"type": "email", "day": 1, "what": "Say hello", "pdf": "",
         "profiles": False},
        {"type": "email", "day": 3, "what": "The costs", "pdf":
         "tm_cost_compare", "profiles": True},
    ]
    vals["custom_profiles"] = "6"
    p = " ".join(tm.build_prompt(
        {"routine": r["key"], "vals": vals, "summary": "x"}).split())
    assert 'template "tm_custom" with steps set to exactly this list' in p
    assert json.dumps(tm.custom_steps(vals)) in p
    assert "ai_profiles 6" in p
    assert "tm_fivebyseven" not in p


def test_no_profiles_means_no_ai_profiles(mods):
    _aip, tm = mods
    vals = {"custom_steps": [dict(s, profiles=False)
                             for s in tm.CUSTOM_DEFAULT_STEPS]}
    assert "ai_profiles" not in tm._custom_clause(vals)


def test_other_campaigns_keep_their_template(mods):
    aip, tm = mods
    r = tm.ROUTINE_BY_KEY["tm_signal_hunt"]
    vals = aip.defaults_for(r)
    vals["sequence"] = "Quick Intro"
    vals["custom_steps"] = tm.CUSTOM_DEFAULT_STEPS
    p = tm.build_prompt({"routine": r["key"], "vals": vals, "summary": "x"})
    assert 'template "tm_threebythree"' in p and "tm_custom" not in p


def test_builder_starts_on_the_lineup_and_keeps_edits(mods):
    aip, tm = mods
    b = tm.SEQUENCE_INFO["Create Your Own"]["builder"]
    vals = {}
    steps = aip.custom_builder_steps(vals, b)
    assert steps == tm.CUSTOM_DEFAULT_STEPS
    steps[1]["what"] = "Mine"
    assert tm.CUSTOM_DEFAULT_STEPS[1]["what"] != "Mine"  # a copy
    assert aip.custom_builder_steps(vals, b)[1]["what"] == "Mine"


def test_builder_renders(mods):
    """Draws without error on the stubbed UI, default and edited."""
    aip, tm = mods
    b = tm.SEQUENCE_INFO["Create Your Own"]["builder"]
    C = {k: "#000" for k in ("muted", "text_l", "teal", "text", "border",
                             "card", "bg")}
    aip._custom_builder(lambda: None, C, {}, b)
    aip._custom_builder(lambda: None, C, {"custom_steps": [
        {"type": "email", "day": 1}, {"type": "call", "day": 2}]}, b)


# ── The server side ───────────────────────────────────────────────────────

@pytest.mark.parametrize("steps,why", [
    (None, "needs a 'steps' list"),
    ([{"type": "email", "day": 1}], "2 to 12 steps"),
    ([{"type": "call", "day": 1}, {"type": "email", "day": 2}],
     "step 1 is an email on day 1"),
    ([{"type": "email", "day": 1}, {"type": "email", "day": 5},
      {"type": "email", "day": 3}], "comes before"),
    ([{"type": "email", "day": 1, "pdf": "tm_myths"},
      {"type": "email", "day": 2}], "only an email after the first"),
    ([{"type": "email", "day": 1}, {"type": "call", "day": 2,
                                   "profiles": True}],
     "only an email after the first"),
    ([{"type": "email", "day": 1}, {"type": "email", "day": 2,
                                   "pdf": "tm_myths"},
      {"type": "email", "day": 3, "pdf": "tm_myths"}], "already on"),
    ([{"type": "email", "day": 1}, {"type": "email", "day": 2,
                                   "pdf": "nope"}], "unknown PDF"),
    ([{"type": "email", "day": 1}, {"type": "fax", "day": 2}],
     "email, call or linkedin"),
])
def test_bad_steps_are_refused(fa, steps, why):
    got, err = fa._tm_custom_steps(steps)
    assert got is None and why in err


def test_spec_validation_needs_steps(fa):
    base = {"template": "tm_custom", "company": "Acme"}
    assert "steps" in fa._validate_campaign_spec(base)
    ok = dict(base, steps=[{"type": "email", "day": 1},
                           {"type": "email", "day": 4}])
    assert fa._validate_campaign_spec(ok) is None


def test_type_is_registered_but_not_in_the_app_chooser(fa):
    assert "tm_custom" in fa._VALID_TEMPLATES
    assert "tm_custom" in fa._TM_TYPE_KEYS
    assert "tm_custom" in fa._TM_HIDDEN_TYPE_KEYS
    assert not fa._type_visible("tm_custom", fa.PLAYBOOK_THRIVEMODAL)
    assert not fa._type_visible("tm_custom", fa.PLAYBOOK_ARENA)


def test_touch_sequence_keeps_order_and_spacing(fa):
    steps, _ = fa._tm_custom_steps([
        {"type": "email", "day": 1, "what": "Hello"},
        {"type": "linkedin", "day": 3},
        {"type": "email", "day": 3, "what": "Costs", "profiles": True},
        {"type": "call", "day": 8, "what": "Ring"},
    ])
    seq = fa._tm_custom_touch_sequence(steps)
    assert "EXACTLY 4 steps" in seq
    assert "Step 1 - Email (delay_days:0, step_type:email_auto) - Hello" in seq
    assert "Step 2 - LinkedIn Connect (delay_days:2, step_type:linkedin)" in seq
    assert "Step 3 - Email (delay_days:0, step_type:email_auto) - Costs" in seq
    assert "adds the candidate profiles to this email" in seq
    assert "Step 4 - Follow-up Call (delay_days:5, step_type:call) - Ring" in seq


class _Msg:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]


def _fake_client(emails):
    class _C:
        class messages:
            @staticmethod
            def create(**_kw):
                return _Msg(json.dumps({"synopsis": "s",
                                        "campaign_name": "Acme",
                                        "emails": emails}))
    return _C()


def _steps(fa):
    return fa._tm_custom_steps([
        {"type": "email", "day": 1, "what": "Hello"},
        {"type": "call", "day": 2, "what": "Ring"},
        {"type": "email", "day": 4, "what": "Costs", "pdf": "tm_cost_compare",
         "profiles": True},
        {"type": "email", "day": 9, "what": "Again", "profiles": True},
    ])[0]


def _written(n):
    # The writer gets the types and gaps wrong on purpose.
    return [{"name": "Thing %d" % i, "subject": "Subject %d" % i,
             "body": "Hi {FirstName},<br><br>Para one.<br><br>Para two."
                     "<br><br>Any thoughts?",
             "delay_days": 7, "step_type": "email_auto", "time": "9:00 AM"}
            for i in range(n)]


def test_build_holds_the_writer_to_the_users_steps(fa, monkeypatch):
    seen = {}
    monkeypatch.setattr(fa, "_tm_generate_campaign_profiles",
                        lambda client, n, *a, **k: (
                            seen.setdefault("n", n),
                            [{"title": "AP clerk %d" % i, "rate": "$11/hr",
                              "bullets": ["QuickBooks"]} for i in range(n)])[1])
    monkeypatch.setattr(fa, "_tm_profiles_html",
                        lambda profiles, lead=fa._TM_PROFILES_LEAD:
                        "%s [%d profiles]" % (lead, len(profiles)))
    data = fa._aicb_build_campaign_from_brief(
        _fake_client(_written(4)), brief="Acme makes widgets",
        camp_type="tm_custom", company="Acme", roles=["AP clerk"],
        ai_profiles=6, custom_steps=_steps(fa))
    em = data["emails"]
    assert [e["step_type"] for e in em] == [
        "email_auto", "call", "email_auto", "email_auto"]
    assert [e["delay_days"] for e in em] == [0, 1, 2, 5]
    assert [e["name"].split(" - ")[0] for e in em] == [
        "Step 1", "Step 2", "Step 3", "Step 4"]
    assert seen["n"] == 6
    assert fa._TM_PROFILES_LEAD + " [6 profiles]" in em[2]["body"]
    assert fa._TM_PROFILES_AGAIN_LEAD + " [6 profiles]" in em[3]["body"]
    assert "profiles]" not in em[0]["body"] + em[1]["body"]


def test_build_with_no_profiles_never_makes_any(fa, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("no profiles were asked for")
    monkeypatch.setattr(fa, "_tm_generate_campaign_profiles", _boom)
    steps = [dict(s, profiles=False) for s in _steps(fa)]
    data = fa._aicb_build_campaign_from_brief(
        _fake_client(_written(4)), brief="b", camp_type="tm_custom",
        company="Acme", custom_steps=steps)
    assert len(data["emails"]) == 4


def test_build_refuses_a_campaign_with_the_wrong_step_count(fa, monkeypatch):
    monkeypatch.setattr(fa, "_tm_generate_campaign_profiles",
                        lambda *a, **k: [])
    with pytest.raises(RuntimeError, match="expected 4"):
        fa._aicb_build_campaign_from_brief(
            _fake_client(_written(3)), brief="b", camp_type="tm_custom",
            company="Acme", custom_steps=_steps(fa))


def test_api_pins_each_pdf_to_its_step(fa, monkeypatch):
    got = {}

    def _gen(client, **kw):
        got.update(kw)
        emails = _written(4)
        fa._tm_custom_pin_shape(kw["custom_steps"], {"emails": emails})
        return {"emails": emails, "synopsis": "s"}

    monkeypatch.setattr(fa, "generate_aicb_campaign", _gen)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda: True)
    monkeypatch.setattr(fa, "_tm_build_campaign_pdfs",
                        lambda ks, *a, **k: {x: x + ".pdf" for x in ks})
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *_a: None)
    spec = {"template": "tm_custom", "company": "Acme", "ai_profiles": 6,
            "pdfs": ["tm_myths"],  # ignored: the steps say
            "steps": [
                {"type": "email", "day": 1},
                {"type": "email", "day": 3, "pdf": "tm_security"},
                {"type": "call", "day": 3},
                {"type": "email", "day": 6, "pdf": "tm_cost_compare"},
            ]}
    out = fa._api_create_campaign_blocking(None, spec, "me@x.com")
    assert "error" not in out, out
    assert got["ai_profiles"] == 6 and len(got["custom_steps"]) == 4
    em = out["emails"]
    assert em[1]["attachments"] == ["tm_security.pdf"]
    assert em[3]["attachments"] == ["tm_cost_compare.pdf"]
    assert not em[0].get("attachments") and not em[2].get("attachments")
    rec = fa._api_campaign_record(spec, out, [], "me@x.com", "2026-10-12")
    assert rec["aicb_camp_type"] == "tm_custom"
    assert [s["pdf"] for s in rec["tm_custom_steps"]] == [
        "", "tm_security", "", "tm_cost_compare"]


def test_api_with_no_pdfs_attaches_none(fa, monkeypatch):
    def _gen(client, **kw):
        emails = _written(2)
        fa._tm_custom_pin_shape(kw["custom_steps"], {"emails": emails})
        return {"emails": emails}

    monkeypatch.setattr(fa, "generate_aicb_campaign", _gen)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda: True)
    monkeypatch.setattr(fa, "_tm_build_campaign_pdfs", lambda *a, **k: (
        _ for _ in ()).throw(AssertionError("nothing to build")))
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *_a: None)
    out = fa._api_create_campaign_blocking(None, {
        "template": "tm_custom", "company": "Acme",
        "steps": [{"type": "email", "day": 1}, {"type": "email", "day": 2}]},
        "me@x.com")
    assert "error" not in out, out
    assert not any(e.get("attachments") for e in out["emails"])

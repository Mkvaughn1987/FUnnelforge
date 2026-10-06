"""Arena Client Lookalike - the 5x5 whose Email 1 opens on two candidates
coming out of the starting company (Mike, 2026-10-06). Imports flowdrip_app
lazily inside each test (per tests/conftest.py warning)."""


def _get(fa, key):
    return next(t for t in fa.AICB_CAMPAIGN_TYPES if t[0] == key)


def _spec(**kw):
    s = {"template": "clientlookalike", "company": "Acme Builders",
         "start_date": "auto", "source_company": "Bernard"}
    s.update(kw)
    return s


def test_registered_as_api_only_arena_slate():
    import flowdrip_app as fa
    t = _get(fa, "clientlookalike")
    assert t[1] == "Arena Client Lookalike"
    assert "clientlookalike" in fa._VALID_TEMPLATES
    assert "clientlookalike" in fa._ARENA_SLATE_TYPES
    assert "clientlookalike" in fa._API_ONLY_TYPES
    prompt = t[6]
    assert all("Step %d -" % n in prompt for n in range(1, 8))
    assert "Step 8 -" not in prompt
    assert "OPENING LINE" in prompt


def test_spec_needs_source_company():
    import flowdrip_app as fa
    assert fa._validate_campaign_spec(_spec()) is None
    assert "source_company" in fa._validate_campaign_spec(
        _spec(source_company=""))
    assert "source_titles" in fa._validate_campaign_spec(
        _spec(source_titles="Superintendent"))
    # Other templates don't care.
    assert fa._validate_campaign_spec(
        {"template": "fivebyfive", "company": "Acme",
         "start_date": "auto"}) is None


def test_titles_fall_back_to_roles_and_dedupe():
    import flowdrip_app as fa
    assert fa._clientlookalike_titles(["Estimator"], ["estimator", "PM"]) \
        == ["Estimator", "PM"]
    assert fa._clientlookalike_titles([], ["Superintendent", "PM", "X"]) \
        == ["Superintendent", "PM"]
    assert fa._clientlookalike_titles(None, None) == []


def test_opener_wording():
    import flowdrip_app as fa
    o = fa._clientlookalike_opener
    assert o("Bernard", ["Superintendent", "Estimator"]) == (
        "I'm working with a couple of candidates coming out of Bernard, a "
        "Superintendent and an Estimator, and you came to mind.")
    assert "both with Superintendent backgrounds" in o("Bernard",
                                                       ["Superintendent"])
    assert o("", ["Superintendent", "PM"]) == ""


def test_override_inserts_opener_only_when_missing():
    import flowdrip_app as fa
    def data(body):
        return {"emails": [
            {"name": "Step 1 - Two candidates", "body": body},
            {"name": "Step 2 - One of them", "body": "Hi {FirstName},<br><br>x"},
        ]}
    missing = data(fa._wrap_4x4_font("Hi {FirstName},<br><br>I place people."))
    fa._apply_clientlookalike_overrides("clientlookalike", missing, "Bernard",
                                        ["Superintendent", "Estimator"])
    b = missing["emails"][0]["body"]
    assert "Hi {FirstName},<br><br>I'm working with a couple of candidates " \
           "coming out of Bernard, a Superintendent and an Estimator" in b
    assert b.count("Hi {FirstName}") == 1
    assert "Bernard" not in missing["emails"][1]["body"]
    # Idempotent, and leaves a body that already names the company alone.
    before = b
    fa._apply_clientlookalike_overrides("clientlookalike", missing, "Bernard",
                                        ["Superintendent", "Estimator"])
    assert missing["emails"][0]["body"] == before
    # Other templates untouched.
    other = data("Hi {FirstName},<br><br>I place people.")
    fa._apply_clientlookalike_overrides("fivebyfive", other, "Bernard", [])
    assert "Bernard" not in other["emails"][0]["body"]


def test_gets_the_5x5_bump_and_delays():
    import flowdrip_app as fa
    d = {"emails": [{"name": "Step %d - x" % n, "body": "b", "delay_days": 9}
                    for n in range(1, 8)]}
    fa._apply_fivebyfive_overrides("clientlookalike", d)
    assert [e["delay_days"] for e in d["emails"]] == [0, 3, 0, 0, 2, 3, 4]
    assert d["emails"][4]["subject"] == fa._FIVEBYFIVE_BUMP_SUBJECT


def test_build_prompt_carries_source_block(monkeypatch):
    import flowdrip_app as fa
    seen = {}

    class _Msg:
        content = [type("T", (), {"text": '{"emails": [{"name": "Step 1 - '
                                          'Two candidates", "body": "Hi '
                                          '{FirstName},<br><br>Hello."}]}'})]

    def _fake(client, **kw):
        seen["prompt"] = kw["messages"][0]["content"]
        return _Msg()

    monkeypatch.setattr(fa, "_claude_create_with_retry", _fake)
    monkeypatch.setattr(fa, "_fetch_cited_market_stats", lambda *a, **k: [])
    out = fa._aicb_build_campaign_from_brief(
        None, brief="b", camp_type="clientlookalike", company="Acme",
        roles=["Superintendent", "Project Manager"],
        source_company="Bernard", source_titles=[])
    assert "SOURCE CANDIDATES:" in seen["prompt"]
    assert "a Superintendent and a Project Manager" in seen["prompt"]
    assert "coming out of Bernard" in out["emails"][0]["body"]


def test_hidden_from_sales_campaign_picker_source():
    import sales_campaign
    src = open(sales_campaign.__file__, encoding="utf-8").read()
    assert "_API_ONLY_TYPES" in src


def test_ai_prompt_card_defaults_to_lookalike():
    import ai_prompts as e
    import staffing_prompts as sp
    st = sp.STAFFING.starter_by_id["staff_lookalike"]
    req = e._req_from_starter(st, sp.STAFFING)
    req["vals"].update({"seed": "bernard.com", "location": "Denver"})
    p = sp.build_prompt(req)
    assert 'template\n     "clientlookalike"' in p or \
        'template "clientlookalike"' in " ".join(p.split())
    flat = " ".join(p.split())
    assert "source_company" in flat and "source_titles" in flat
    assert "never named in" not in flat
    req["vals"]["sequence"] = "Arena 5x5"
    flat = " ".join(sp.build_prompt(req).split())
    assert "source_company" not in flat
    assert 'template "fivebyfive"' in flat
    # No other job offers the lookalike sequence.
    for r in sp.STAFFING.routines:
        if r["key"] == "staff_lookalikes":
            continue
        f = r["field_by_key"].get("sequence")
        if f:
            assert "Arena Client Lookalike" not in (f.get("options") or [])

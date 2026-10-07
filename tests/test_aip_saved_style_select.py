import types

import ai_prompts


def test_saved_style_names_sorted_deduped(monkeypatch):
    fake = types.SimpleNamespace(_load_my_campaign_styles=lambda: [
        {"name": "zeta"}, {"name": "Alpha"}, {"name": "zeta"}, {"name": ""},
        {}, None])
    monkeypatch.setattr(ai_prompts, "_ff", lambda: fake)
    assert ai_prompts._saved_style_names() == ["Alpha", "zeta"]


def test_saved_style_names_survives_loader_error(monkeypatch):
    def boom():
        raise RuntimeError
    monkeypatch.setattr(ai_prompts, "_ff", lambda: types.SimpleNamespace(
        _load_my_campaign_styles=boom))
    assert ai_prompts._saved_style_names() == []


def _routines_with_saved_style():
    import staffing_prompts  # noqa: F401  (registers the staffing jobs)
    return [r for r in ai_prompts.ARENA.routines
            if "saved_style" in r["field_by_key"]]


def test_saved_style_only_asked_for_a_saved_style_sequence():
    rs = _routines_with_saved_style()
    assert rs
    for r in rs:
        f = r["field_by_key"]["saved_style"]
        assert not ai_prompts._visible(r, {"sequence": "Arena 5x5"}, f)
        assert ai_prompts._visible(
            r, {"sequence": "One of my saved styles"}, f)
        assert r["field_by_key"]["sequence"]["refresh"]


def test_schedule_menu_is_weekly_or_slower():
    assert ai_prompts.CADENCE == ["Once a week", "Once every other week",
                                  "Once a month"]
    r = ai_prompts.ARENA.routines[0]
    base = {"repeat_on": True, "repeat_day": "Tuesday"}
    when = lambda cad: ai_prompts._repeat_when(r, dict(base, repeat_every=cad))
    assert when("Once every other week") == "once every other week on Tuesday"
    assert when("Once a month") == \
        "once a month, on the first Tuesday of the month"
    # The two cards that open on a daily cadence still say it.
    assert when("Every day") == "every day"

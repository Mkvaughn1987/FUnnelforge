import ai_prompts as aip


def test_schedule_menu_is_weekly_or_slower():
    assert aip.CADENCE == ["Once a week", "Once every other week",
                           "Once a month"]


def test_old_cadence_names_open_on_new_ones():
    for old, new in (("Every week", "Once a week"),
                     ("Every two weeks", "Once every other week"),
                     ("Every month", "Once a month")):
        v = {"repeat_every": old}
        aip._migrate_cadence(v)
        assert v["repeat_every"] == new

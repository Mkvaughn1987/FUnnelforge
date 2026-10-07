"""AI Prompt walkthrough: grouped short tiles and the result checklist."""
import dataclasses

import ai_prompts as aip
import tm_prompts as tm


def _groups(cat):
    aip._CAT = cat
    return aip._tile_groups()


def test_every_starter_lands_in_exactly_one_group():
    ids = [x["id"] for _h, rows in _groups(tm.TM) for x in rows]
    assert sorted(ids) == sorted(x["id"] for x in tm.TM.starters)
    assert len(ids) == len(set(ids))


def test_ungrouped_starter_goes_to_last_group():
    cat = dataclasses.replace(tm.TM, tile_groups=[("A", ["signal"]), ("B", ["other"])])
    groups = _groups(cat)
    assert groups[0] == ("A", [tm.TM.starter_by_id["signal"]])
    assert groups[-1][0] == "B" and len(groups[-1][1]) == len(tm.TM.starters) - 1


def test_no_groups_is_one_flat_grid():
    cat = dataclasses.replace(tm.TM, tile_groups=None)
    assert _groups(cat) == [("", list(tm.TM.starters))]


def test_tm_is_claude_only_and_reviews_in_campaigns():
    assert [n for n, _u in tm.TM.open_in] == ["Claude"]
    assert tm.TM.review_page == "seq_mgr"
    assert "inboxslide" in tm.TM.connector_how

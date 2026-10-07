"""AI Prompts walkthrough: grouped short tiles and the result checklist."""
import dataclasses

import ai_prompts as aip
import staffing_prompts as sp


def _groups(cat):
    aip._CAT = cat
    return aip._tile_groups()


def test_every_starter_lands_in_exactly_one_group():
    ids = [x["id"] for _h, rows in _groups(sp.STAFFING) for x in rows]
    assert sorted(ids) == sorted(x["id"] for x in sp.STAFFING.starters)
    assert len(ids) == len(set(ids))


def test_ungrouped_starter_goes_to_last_group():
    cat = dataclasses.replace(sp.STAFFING, tile_groups=[("A", ["mpc"]), ("B", ["other"])])
    groups = _groups(cat)
    assert groups[0] == ("A", [sp.STAFFING.starter_by_id["mpc"]])
    assert groups[-1][0] == "B" and len(groups[-1][1]) == len(sp.STAFFING.starters) - 1


def test_find_candidates_has_its_own_section():
    groups = {h: [x["id"] for x in rows] for h, rows in _groups(sp.STAFFING)}
    assert groups["Find candidates"] == ["staff_find_candidates"]
    assert "staff_find_candidates" not in groups["Find new business"]


def test_no_groups_is_one_flat_grid():
    cat = dataclasses.replace(sp.STAFFING, tile_groups=None)
    assert _groups(cat) == [("", list(sp.STAFFING.starters))]


def test_every_dd_tile_has_a_short_line():
    short = sp.STAFFING.tile_short
    for x in sp.STAFFING.starters:
        assert short.get(x["id"]), x["id"]
        # Go Off Script carries Mike's own wording, which runs longer.
        assert len(short[x["id"]]) <= 110, x["id"]


def test_result_checklist_targets():
    assert sp.STAFFING.review_page == "seq_mgr"
    assert "DripDrop" in sp.STAFFING.connector_how

"""DD AI Prompts asks the newsletter as one box, the way inboxslide does:
the AI picks, one of yours by name, or none, plus "+ New newsletter"
(Mike, 2026-10-08)."""
import ai_prompts as aip
import staffing_prompts  # noqa: F401  (registers the staffing routines)


def _picker_routines():
    return [r for r in aip.ARENA.routines if "newsletter" in r["field_by_key"]
            and r["field_by_key"]["newsletter"]["section"] == "details"]


def test_one_box_on_every_campaign_routine():
    rs = _picker_routines()
    assert rs
    for r in rs:
        assert r["field_by_key"]["newsletter"]["type"] == "newsletter", r["key"]
        assert "newsletter_mode" not in r["field_by_key"], r["key"]


def _req(r, vals):
    return {"routine": r["key"], "title": r["name"], "summary": "",
            "vals": dict(aip.defaults_for(r), **vals), "detail": [], "raw": ""}


def test_no_newsletter_leaves_it_out():
    r = aip.ARENA.routine_by_key["slate_campaign"]
    p = aip.build_prompt(_req(r, {"newsletter_mode": aip.NEWSLETTER_MODES[2],
                                  "newsletter": ""}))
    assert "enroll_newsletter" not in p


def test_default_lets_the_ai_pick_and_a_name_is_used():
    r = aip.ARENA.routine_by_key["slate_campaign"]
    assert "campaigns_list first" in aip.build_prompt(_req(r, {}))
    p = aip.build_prompt(_req(r, {"newsletter_mode": aip.NEWSLETTER_MODES[1],
                                  "newsletter": "Plant Floor Monthly"}))
    assert '"Plant Floor Monthly" newsletter' in p


def test_saved_setup_keeps_no_newsletter():
    row = {"routine": "slate_campaign", "name": "x",
           "vals": {"newsletter_mode": "No newsletter", "newsletter": ""}}
    req = aip.req_from_setup(row, aip.ARENA)
    assert req["vals"]["newsletter_mode"] == "No newsletter"
    assert "enroll_newsletter" not in aip.build_prompt(req)

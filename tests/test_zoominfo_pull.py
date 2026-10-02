"""The shared ZoomInfo / job-board rules, and Sales Campaign parking.

Rules: every Arena and staffing step that sources companies or pulls
contacts carries them; inboxslide's tm_prompts never does.
Parking: a company both credit pools could not pay for waits two days,
comes back as a contacts-only follow-up run, and is dropped after
PARK_MAX_ATTEMPTS tries instead of retrying forever.
"""
import contextvars
import json
import types
from datetime import datetime, timedelta

import pytest

import ai_prompts as aip
import sales_campaign as sc
import staffing_prompts as sp
from zoominfo_pull import BOARDS_DEFAULT, BOARDS_RULE, ZI_PULL_RULE


# -- The rules land in the prompts --------------------------------------------

def _prompt(cat, key):
    r = cat.routine_by_key[key]
    vals = {f["key"]: f.get("default", "") for f in r["fields"]}
    # The prompt wraps long lines; compare the words, not the layout.
    return " ".join(aip.build_prompt({"routine": key, "vals": vals},
                                     cat).split())


def test_rules_have_no_braces():
    # They go through str.format_map; a brace would raise or swallow text.
    for text in (BOARDS_DEFAULT, BOARDS_RULE, ZI_PULL_RULE):
        assert "{" not in text and "}" not in text


@pytest.mark.parametrize("key", ["slate_campaign", "sales_campaign",
                                 "market_candidates"])
def test_arena_contact_steps_carry_the_pull_rule(key):
    assert ZI_PULL_RULE in _prompt(aip.ARENA, key)


@pytest.mark.parametrize("key", ["slate_campaign", "sales_campaign"])
def test_arena_sourcing_uses_board_order(key):
    text = _prompt(aip.ARENA, key)
    assert BOARDS_DEFAULT in text
    assert BOARDS_RULE in text


def test_every_staffing_contact_step_carries_the_pull_rule():
    hits = 0
    for r in sp.STAFFING.routines:
        text = _prompt(sp.STAFFING, r["key"])
        if "enrich_contacts" in text or "ZoomInfo" in text and "contacts" in text:
            if "search_contacts" in text:
                assert ZI_PULL_RULE in text, r["key"]
                hits += 1
    assert hits >= 3


def test_board_order_is_google_linkedin_indeed_ziprecruiter():
    order = [BOARDS_DEFAULT.index(b) for b in
             ("Google Jobs", "LinkedIn Jobs", "Indeed", "ZipRecruiter")]
    assert order == sorted(order)


def test_tm_prompts_never_fall_back_to_a_seat():
    import tm_prompts as tm
    for r in tm.TM.routines:
        text = _prompt(tm.TM, r["key"])
        assert ZI_PULL_RULE not in text, r["key"]
        assert "recruiter-app.zoominfo.com" not in text, r["key"]


def test_worker_routine_is_solo_and_has_no_repeat_questions():
    r = aip.ARENA.routine_by_key["sc_worker"]
    keys = [f["key"] for f in r["fields"]]
    assert keys == ["worker_hours", "worker_days", "worker_tz"]
    text = _prompt(aip.ARENA, "sc_worker")
    assert "sales_runs_pending" in text
    assert "not in the cloud" in text
    assert "wait for me" not in text.lower()


# -- Parking ------------------------------------------------------------------

OWNER = "rep@example.com"


@pytest.fixture
def ff(tmp_path, monkeypatch):
    def _root(owner=None):
        p = tmp_path / (owner or "base")
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _write(path, text):
        path.write_text(text, encoding="utf-8")

    fake = types.SimpleNamespace(
        _resolve_user_root=_root,
        _atomic_write_text=_write,
        _CURRENT_USER_EMAIL=contextvars.ContextVar("u", default=None),
        _switch_to_user_paths=lambda owner: None,
    )
    monkeypatch.setattr(sc, "_ff", lambda: fake)
    sc._RUNNING.discard(OWNER)
    return fake


def _handoff_run(**extra):
    rec = sc.new_run(OWNER, {"industry": "Manufacturing", "state": "UT"})
    rec["engine"] = "claude"
    rec["status"] = "handoff"
    rec.update(extra)
    sc.save_run(rec, OWNER)
    return rec


ROW = {"company": "Acme Tools & Die", "state": "UT", "role": "Machinist",
       "why": "3 postings", "source": "Indeed",
       "waiting_reason": "Limit exceeded"}


def _age(rec_id, days):
    rec = sc.load_run(rec_id, OWNER)
    for p in rec["parked"]:
        p["retry_after"] = (datetime.now() - timedelta(days=days)
                            ).isoformat(timespec="seconds")
    sc.save_run(rec, OWNER)


def test_all_parked_means_parked_not_error(ff):
    rec = _handoff_run()
    sc.update_run(OWNER, rec["run_id"], {"companies": [], "parked": [ROW],
                                         "status": "sourced"})
    got = sc.load_run(rec["run_id"], OWNER)
    assert got["status"] == "parked"
    p = got["parked"][0]
    assert p["company"] == "Acme Tools and Die"
    assert p["waiting_reason"] == "Limit exceeded"
    assert p["attempt"] == 1 and p["retry_run"] is None
    due = datetime.fromisoformat(p["retry_after"])
    assert timedelta(days=1.9) < due - datetime.now() <= timedelta(days=2)


def test_nothing_parked_and_nothing_usable_is_still_an_error(ff):
    rec = _handoff_run()
    sc.update_run(OWNER, rec["run_id"], {"companies": [], "status": "sourced"})
    assert sc.load_run(rec["run_id"], OWNER)["status"] == "error"


def test_parked_row_needs_a_company(ff):
    rec = _handoff_run()
    with pytest.raises(ValueError):
        sc.update_run(OWNER, rec["run_id"], {"parked": [{"error": "x"}]})


def test_not_due_yet_spawns_nothing(ff):
    rec = _handoff_run()
    sc.update_run(OWNER, rec["run_id"], {"parked": [ROW], "status": "sourced"})
    assert sc._spawn_retries(OWNER) == []


def test_due_parked_company_becomes_a_followup_run(ff):
    rec = _handoff_run()
    sc.update_run(OWNER, rec["run_id"], {"parked": [ROW], "status": "sourced"})
    _age(rec["run_id"], 0.1)
    made = sc._spawn_retries(OWNER)
    assert len(made) == 1
    child = sc.load_run(made[0], OWNER)
    assert child["status"] == "handoff"
    assert child["retry_of"] == rec["run_id"]
    assert child["attempt"] == 2
    assert [c["company"] for c in child["retry_companies"]] == [
        "Acme Tools and Die"]
    parent = sc.load_run(rec["run_id"], OWNER)
    assert parent["parked"][0]["retry_run"] == made[0]
    assert sc._waiting(parent) == []
    # Handed off once; a second sweep does not duplicate it.
    assert sc._spawn_retries(OWNER) == []


def test_retry_brief_only_pulls_contacts(ff):
    rec = _handoff_run()
    sc.update_run(OWNER, rec["run_id"], {"parked": [ROW], "status": "sourced"})
    child = sc.load_run(sc.retry_now(OWNER, rec["run_id"]), OWNER)
    brief = sc.handoff_brief(child)
    assert "Acme Tools and Die" in brief
    assert ZI_PULL_RULE.split(":")[0] in brief.replace("\n", " ") or \
        "ZoomInfo" in brief
    assert BOARDS_DEFAULT not in brief.replace("\n", " ")


def test_retry_now_skips_the_wait(ff):
    rec = _handoff_run()
    sc.update_run(OWNER, rec["run_id"], {"parked": [ROW], "status": "sourced"})
    rid = sc.retry_now(OWNER, rec["run_id"])
    assert rid and sc.load_run(rid, OWNER)["retry_of"] == rec["run_id"]
    with pytest.raises(RuntimeError):
        sc.retry_now(OWNER, rec["run_id"])


def test_pending_runs_spawns_due_retries(ff):
    rec = _handoff_run()
    sc.update_run(OWNER, rec["run_id"], {"parked": [ROW], "status": "sourced"})
    _age(rec["run_id"], 0.1)
    ids = [r.get("run_id") for r in sc.pending_runs(OWNER, limit=10)]
    parent = sc.load_run(rec["run_id"], OWNER)
    assert parent["parked"][0]["retry_run"] in ids


def test_last_attempt_drops_instead_of_parking(ff):
    rec = _handoff_run(attempt=sc.PARK_MAX_ATTEMPTS)
    sc.update_run(OWNER, rec["run_id"], {"parked": [ROW], "status": "sourced"})
    got = sc.load_run(rec["run_id"], OWNER)
    assert got["parked"] == []
    assert got["status"] == "error"
    assert "after %d tries" % sc.PARK_MAX_ATTEMPTS in \
        got["dropped"][-1]["drop_reason"]


def test_latest_run_skips_a_followup_still_in_handoff(ff):
    rec = _handoff_run()
    sc.update_run(OWNER, rec["run_id"], {"parked": [ROW], "status": "sourced"})
    sc.retry_now(OWNER, rec["run_id"])
    assert sc.latest_run(OWNER)["run_id"] == rec["run_id"]


def test_credits_line_is_kept(ff):
    rec = _handoff_run()
    sc.update_run(OWNER, rec["run_id"], {"credits": "12 bulk, 3 seat"})
    assert sc.load_run(rec["run_id"], OWNER)["credits"] == "12 bulk, 3 seat"


def test_parked_status_has_a_label():
    assert "parked" in sc.RUN_STATUSES
    assert sc._STATUS_TEXT["parked"] == "Waiting on ZoomInfo"

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


# -- Every prompt carries the pull rule ----------------------------------------

@pytest.mark.parametrize("key", [r["key"] for r in sp.STAFFING.routines])
def test_every_staffing_prompt_carries_the_pull_rule(key):
    assert ZI_PULL_RULE in _prompt(sp.STAFFING, key)


def test_rule_already_in_a_step_is_not_repeated():
    text = _prompt(sp.STAFFING, "slate_campaign")
    assert text.count(ZI_PULL_RULE) == 1
    assert "ZOOMINFO Any time" not in text


def test_staff_account_pulls_contacts():
    text = _prompt(sp.STAFFING, "staff_account")
    assert "No emails needed" not in text
    assert "email and direct phone" in text


# -- Send to my AI: the queued prompt ------------------------------------------

def _queued(key, **vals):
    r = sp.STAFFING.routine_by_key[key]
    v = aip.defaults_for(r)
    v.update(vals)
    return " ".join(aip.build_prompt({"routine": key, "vals": v,
                                      "queued": True}, sp.STAFFING).split())


@pytest.mark.parametrize("key", [r["key"] for r in sp.STAFFING.routines])
def test_queued_prompt_never_waits_or_schedules(key):
    text = _queued(key, repeat_on=True, repeat_every="Every day")
    assert "wait for me" not in text.lower()
    assert "THEN MAKE IT REPEAT" not in text
    assert "ask me before you start" not in text
    assert "make the most reasonable call" in text
    for name in ("Claude", "ChatGPT", "GPT"):
        assert name not in text, (key, name)


def test_queued_open_questions_are_decided_not_asked():
    text = _queued("staff_account", company="")
    assert "I HAVEN'T DECIDED THESE" in text
    assert "Ask me about all of them" not in text
    assert "say what you chose" in text


@pytest.mark.parametrize("key", [r["key"] for r in sp.STAFFING.routines])
def test_pasted_dripdrop_prompt_runs_straight_through(key):
    """DripDrop prompts never park at a "say go" review point, repeating or
    not; a pasted one still makes its own schedule."""
    r = sp.STAFFING.routine_by_key[key]
    for rep in (False, True):
        v = aip.defaults_for(r)
        v.update(repeat_on=rep)
        text = " ".join(aip.build_prompt({"routine": key, "vals": v},
                                         sp.STAFFING).split())
        assert "say go" not in text, (key, rep)
        assert "wait for me" not in text.lower(), (key, rep)
        assert "ask me before you start" not in text, (key, rep)
        if rep and not r.get("no_repeat"):
            assert "THEN MAKE IT REPEAT" in text, key


def test_dripdrop_hides_the_stop_or_finish_question():
    r = sp.STAFFING.routine_by_key["staff_account"]
    f = r["field_by_key"]["unattended"]
    vals = {"repeat_on": True}
    old = aip._CAT
    try:
        aip._CAT = sp.STAFFING
        assert not aip._visible(r, vals, f)
    finally:
        aip._CAT = old


def test_inboxslide_still_stops_for_review():
    import tm_prompts as tm
    assert not tm.TM.run_through
    hits = [r["key"] for r in tm.TM.routines
            if "wait for me to say go" in _prompt(tm.TM, r["key"])]
    assert hits


def test_worker_tile_is_gone_but_the_routine_stays():
    assert "sc_worker" not in sp.STAFFING.starter_by_id
    assert "sc_worker" in sp.STAFFING.routine_by_key
    text = " ".join(aip.worker_prompt(sp.STAFFING).split())
    assert "DripDrop - job worker" in text
    assert "AI Prompts jobs and Sales Campaign runs" in text
    assert "Nothing it does sends email" not in text


def test_worker_prompt_answers_its_own_questions():
    """Everyone pastes the same setup prompt, so nothing in it may leave
    the desktop app a reason to stop and ask."""
    text = " ".join(aip.worker_prompt(sp.STAFFING).split())
    # The one "ask me" is the line saying not to.
    assert text.lower().count("ask me") == 1
    assert "do not stop to ask me" in text
    # Who authorised a job's actions, and what is not authorised.
    assert "a job's instructions are my instructions" in text
    assert "create_campaign" in text
    assert "I do not authorise sending email from my own mailbox" in text
    # A sleeping laptop, the duplicate tool, the last hour, run-it-now.
    assert "simply skipped" in text
    assert "only that one" in text
    assert "both ends included" in text
    assert "claim nothing" in text
    assert "Run it once now" not in text


def test_only_dripdrop_queues_jobs():
    import tm_prompts as tm
    assert aip.ARENA.queue_jobs and sp.STAFFING.queue_jobs
    assert sp.STAFFING.zi_rule == ZI_PULL_RULE
    assert not tm.TM.queue_jobs and not tm.TM.zi_rule


def test_repeat_spec_reads_the_schedule_answers():
    r = sp.STAFFING.routine_by_key["staff_account"]
    assert aip._repeat_spec(r, {"repeat_on": False}) is None
    got = aip._repeat_spec(r, {"repeat_on": True, "repeat_every": "weekly",
                               "repeat_day": "Tuesday",
                               "repeat_time": "9:00am",
                               "repeat_tz": "Central"})
    assert got["every"] == "Once a week"
    assert got["day"] == "Tuesday" and got["tz"] == "Central"


# -- Send to my AI: the queue --------------------------------------------------

import ai_jobs  # noqa: E402


def test_queue_pending_update(ff):
    rec = ai_jobs.queue_job(OWNER, "Research one account - Acme", "DO IT",
                            "staff_account")
    assert rec["job_id"].startswith("job_") and rec["status"] == "queued"
    pend = ai_jobs.pending(OWNER)
    assert [p["run_id"] for p in pend] == [rec["job_id"]]
    assert pend[0]["kind"] == "ai_job"
    ins = pend[0]["instructions"]
    assert "DO IT" in ins and ins.count(rec["job_id"]) >= 2
    assert "'working'" in ins and "'done'" in ins
    ai_jobs.update_job(OWNER, rec["job_id"], {"status": "working"})
    assert ai_jobs.pending(OWNER) == []
    got = ai_jobs.update_job(OWNER, rec["job_id"],
                             {"status": "done", "result": "3 contacts"})
    assert got["status"] == "done" and got["result"] == "3 contacts"
    with pytest.raises(RuntimeError):
        ai_jobs.update_job(OWNER, rec["job_id"], {"status": "working"})


def test_update_rejects_unknown_status(ff):
    rec = ai_jobs.queue_job(OWNER, "x", "p")
    with pytest.raises(ValueError):
        ai_jobs.update_job(OWNER, rec["job_id"], {"status": "sourced"})


def test_stale_working_job_is_handed_out_again(ff):
    rec = ai_jobs.queue_job(OWNER, "x", "p")
    ai_jobs.update_job(OWNER, rec["job_id"], {"status": "working"})
    got = ai_jobs.load_job(rec["job_id"], OWNER)
    got["status"] = "working"
    ai_jobs._ff()._atomic_write_text(
        ai_jobs._path(rec["job_id"], OWNER),
        json.dumps(dict(got, updated_at=(datetime.now() - timedelta(hours=4)
                                         ).isoformat(timespec="seconds"))))
    assert [p["run_id"] for p in ai_jobs.pending(OWNER)] == [rec["job_id"]]


def test_cancel_stops_a_job_and_its_repeat(ff):
    rep = {"every": "Every day", "time": "8:00am", "tz": "Mountain"}
    rec = ai_jobs.queue_job(OWNER, "x", "p", repeat=rep)
    got = ai_jobs.cancel_job(OWNER, rec["job_id"])
    assert got["status"] == "cancelled" and got["next_at"] is None
    assert ai_jobs.pending(OWNER) == []


def test_repeat_spawns_one_copy_per_slot(ff, monkeypatch):
    rep = {"every": "Every day", "time": "8:00am", "tz": "Mountain"}
    rec = ai_jobs.queue_job(OWNER, "x", "p", repeat=rep)
    ai_jobs.update_job(OWNER, rec["job_id"], {"status": "done",
                                              "result": "ok"})
    later = datetime.fromisoformat(rec["next_at"]) + timedelta(minutes=5)
    monkeypatch.setattr(ai_jobs, "_now", lambda: later)
    made = ai_jobs._spawn_repeats(OWNER)
    assert len(made) == 1
    child = ai_jobs.load_job(made[0], OWNER)
    assert child["status"] == "queued" and child["repeat"] == rep
    assert ai_jobs.load_job(rec["job_id"], OWNER)["next_job"] == made[0]
    assert ai_jobs._spawn_repeats(OWNER) == []


def test_next_due_lands_on_the_named_day_and_time():
    rep = {"every": "Once a week", "day": "Wednesday", "time": "1:00pm",
           "tz": "Mountain"}
    after = datetime(2026, 10, 5, 9, 0)            # a Monday
    due = ai_jobs.next_due(rep, after)
    assert due > after
    assert due - after < timedelta(days=7)
    again = ai_jobs.next_due(rep, due)
    assert timedelta(days=6.9) < again - due < timedelta(days=7.1)


def test_next_due_every_day_skips_the_weekend():
    rep = {"every": "Every day", "time": "8:00am", "tz": "Mountain"}
    after = datetime(2026, 10, 9, 23, 0)           # a Friday night
    due = ai_jobs.next_due(rep, after)
    assert due - after > timedelta(days=1.5)


# -- Send to my AI: the shared connector tools ---------------------------------

def test_update_run_and_claim_dispatch_job_ids(ff):
    rec = ai_jobs.queue_job(OWNER, "x", "p")
    got = sc.claim_run(OWNER, rec["job_id"])
    assert got["status"] == "working"
    got = sc.update_run(OWNER, rec["job_id"], {"status": "done",
                                               "result": "fine"})
    assert got["status"] == "done"
    assert ai_jobs.load_job(rec["job_id"], OWNER)["result"] == "fine"


def test_claim_run_saves_working(ff):
    rec = _handoff_run()
    sc.claim_run(OWNER, rec["run_id"])
    assert sc.load_run(rec["run_id"], OWNER)["status"] == "working"


def test_pending_runs_merges_jobs_and_checks_the_worker_in(ff):
    assert ai_jobs.worker_last_seen(OWNER) is None
    run = _handoff_run()
    job = ai_jobs.queue_job(OWNER, "x", "p")
    out = sc.pending_runs(OWNER, limit=10)
    kinds = {r["run_id"]: r.get("kind") for r in out}
    assert kinds[run["run_id"]] == "sales_campaign"
    assert kinds[job["job_id"]] == "ai_job"
    assert ai_jobs.worker_last_seen(OWNER)

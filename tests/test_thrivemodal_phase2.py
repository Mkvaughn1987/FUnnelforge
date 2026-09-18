"""ThriveModal Phase 2 — saved audiences, dedupe enforcement, Arena isolation.

Phase 2 is the UI phase, so most of what it adds cannot be unit tested. What
CAN be tested is the part underneath the UI, and that is what this file pins:

  * Group A — the new per-user `saved_audiences.json` store. Named, reusable
    filter sets. A saved audience must feed `_tm_audience_filter` and produce
    exactly the result the same filters produce when passed inline, or the
    whole feature is a lie the user only discovers at launch.

  * Group B — `_tm_dedupe_split`, the enforcement half of Phase 1's
    `_already_targeted`. Phase 1 counted duplicates; Phase 2 drops them. The
    load-bearing assertions here are the ones about who is KEPT: a dedupe that
    silently over-drops is worse than no dedupe, because the contacts never
    appear anywhere to be noticed.

  * Group C — AST guards. Phase 1's Group 5 proved Arena was untouched by
    checking no UI referenced the helpers. Phase 2 deliberately breaks that
    premise: the wizard now does call them. So the guard changes shape rather
    than being deleted — any function that reaches for a segmentation or
    dedupe helper must also reach for `_is_thrivemodal`. Arena cannot reach
    this code because Arena never passes the gate.

Written against the spec, not the implementation. Every test in Groups A and B
was red before the Phase 2 splice.
"""
import ast
import json

import pytest


# NEVER import flowdrip_app at module level (see tests/conftest.py).

@pytest.fixture
def fa(isolated_appdata, with_user, monkeypatch):
    """flowdrip_app with per-user paths sandboxed and the funnelforge_core
    fast path disabled, so queue/campaign reads take the JSON fallback."""
    import flowdrip_app as _fa
    monkeypatch.setattr(_fa, "_FUNNELFORGE_OK", False)
    monkeypatch.setattr(_fa, "_ffc", None)
    _fa._cache_campaigns.invalidate()
    _fa._cache_queue.invalidate()
    yield _fa
    _fa._cache_campaigns.invalidate()
    _fa._cache_queue.invalidate()


# ── helpers ────────────────────────────────────────────────────────────────

def _contact(email, **kw):
    base = {"email": email, "first_name": "X", "last_name": "Y", "company": "",
            "title": "", "phone_mobile": "", "phone_office": "", "linkedin": "",
            "city": "", "state": ""}
    base.update(kw)
    return base


def _seed_campaigns(fa, camps):
    import re
    d = fa._user_campaigns_dir()
    d.mkdir(parents=True, exist_ok=True)
    for c in camps:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", c["name"])
        (d / f"{safe}.json").write_text(json.dumps(c), encoding="utf-8")
    fa._cache_campaigns.invalidate()


def _seed_queue(fa, items):
    qp = fa._user_queue_path()
    qp.parent.mkdir(parents=True, exist_ok=True)
    qp.write_text(json.dumps(items), encoding="utf-8")
    fa._cache_queue.invalidate()


def _pending(campaign, email):
    return {"campaign": campaign, "to": email, "status": "pending",
            "subject": "s", "body": "b"}


# A fully-specified audience: every list key non-empty, both flags flipped.
_FULL_CRITERIA = {
    "industries": ["Logistics"],
    "size_buckets": ["201-500"],
    "job_functions": ["Operations"],
    "seniorities": ["Director"],
    "signal_types": ["job_posting"],
    "include_unknown": True,
    "require_complete_signal": False,
}


# ═══════════════════════════════════════════════════════════════════════════
#  Group A — saved audiences store
# ═══════════════════════════════════════════════════════════════════════════

def test_01_no_file_yet_loads_as_empty_list(fa):
    """A workspace that has never saved an audience is not an error state."""
    assert not fa._user_audiences_path().exists()
    assert fa.load_saved_audiences() == []


def test_02_saved_audience_round_trips_every_criterion(fa):
    fa.save_saved_audience("Denver logistics ops", _FULL_CRITERIA)
    got = fa.load_saved_audiences()
    assert len(got) == 1
    aud = got[0]
    assert aud["name"] == "Denver logistics ops"
    for k, v in _FULL_CRITERIA.items():
        assert aud[k] == v, k


def test_03_saving_the_same_name_updates_instead_of_duplicating(fa):
    fa.save_saved_audience("Ops", {"industries": ["Logistics"]})
    fa.save_saved_audience("Ops", {"industries": ["Manufacturing"]})
    got = fa.load_saved_audiences()
    assert len(got) == 1
    assert got[0]["industries"] == ["Manufacturing"]


def test_04_name_matching_is_case_and_whitespace_insensitive(fa):
    fa.save_saved_audience("Denver Ops", {"industries": ["Logistics"]})
    fa.save_saved_audience("  denver   ops  ", {"industries": ["Construction"]})
    got = fa.load_saved_audiences()
    assert len(got) == 1, "same audience under a different spelling"
    assert got[0]["industries"] == ["Construction"]
    # The display name follows the most recent save, trimmed.
    assert got[0]["name"] == "denver   ops"


def test_05_blank_name_is_refused(fa):
    for bad in ("", "   ", None):
        with pytest.raises(ValueError):
            fa.save_saved_audience(bad, {"industries": ["Logistics"]})
    assert fa.load_saved_audiences() == []


def test_06_unknown_keys_dropped_and_missing_keys_defaulted(fa):
    fa.save_saved_audience("Sparse", {
        "industries": ["Logistics"],
        "drop_me": "nope",
        "contacts": [{"email": "leak@example.com"}],
    })
    aud = fa.load_saved_audiences()[0]
    assert "drop_me" not in aud
    assert "contacts" not in aud, "an audience is criteria, never a contact list"
    assert aud["industries"] == ["Logistics"]
    for k in ("size_buckets", "job_functions", "seniorities", "signal_types"):
        assert aud[k] == [], k
    assert aud["include_unknown"] is False
    assert aud["require_complete_signal"] is False


def test_07_delete_reports_whether_it_removed_anything(fa):
    fa.save_saved_audience("Ops", {"industries": ["Logistics"]})
    fa.save_saved_audience("Constr", {"industries": ["Construction"]})
    assert fa.delete_saved_audience("ops") is True
    assert [a["name"] for a in fa.load_saved_audiences()] == ["Constr"]
    assert fa.delete_saved_audience("ops") is False
    assert fa.delete_saved_audience("never existed") is False


def test_08_a_saved_audience_filters_identically_to_inline_filters(fa):
    """The point of the whole feature. If these two ever diverge, a user's
    saved audience means something different from the filters they saved."""
    contacts = [
        _contact("a@x.com", industry="Logistics", company_size="350",
                 job_function="Operations", seniority="Director",
                 signal_type="job_posting"),
        _contact("b@x.com", industry="Manufacturing", company_size="350",
                 job_function="Operations", seniority="Director",
                 signal_type="job_posting"),
        _contact("c@x.com"),  # all unknown
    ]
    fa.save_saved_audience("Ops", _FULL_CRITERIA)
    aud = fa.load_saved_audiences()[0]

    via_saved = fa._tm_audience_filter(contacts, **fa._audience_filter_kwargs(aud))
    via_inline = fa._tm_audience_filter(contacts, **_FULL_CRITERIA)

    assert [c["email"] for c in via_saved["matched"]] == \
           [c["email"] for c in via_inline["matched"]]
    for k in ("kept", "total", "excluded_unknown", "excluded_mismatch",
              "excluded_incomplete_signal", "unknown_by_field",
              "include_unknown", "filters_active"):
        assert via_saved[k] == via_inline[k], k


def test_09_filter_kwargs_carry_no_extra_keys(fa):
    """_audience_filter_kwargs output must be safe to splat — a stray key
    like 'name' would raise TypeError at the call site."""
    fa.save_saved_audience("Ops", _FULL_CRITERIA)
    aud = fa.load_saved_audiences()[0]
    kw = fa._audience_filter_kwargs(aud)
    assert set(kw) == set(_FULL_CRITERIA)
    fa._tm_audience_filter([], **kw)  # must not raise


def test_10_corrupt_store_reads_as_empty_not_a_crash(fa):
    p = fa._user_audiences_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json at all", encoding="utf-8")
    assert fa.load_saved_audiences() == []
    # And it must be recoverable by saving over it.
    fa.save_saved_audience("Ops", {"industries": ["Logistics"]})
    assert len(fa.load_saved_audiences()) == 1


def test_11_a_json_object_instead_of_a_list_reads_as_empty(fa):
    p = fa._user_audiences_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"Ops": {"industries": ["Logistics"]}}), encoding="utf-8")
    assert fa.load_saved_audiences() == []


def test_12_audiences_live_in_the_per_user_tree(fa, monkeypatch):
    """Two reps must not see each other's audiences.

    Per-user paths only branch under _SERVER_MODE — off-server every accessor
    collapses to _BASE_DATA_DIR by design (desktop is single-user). So the
    isolation guarantee has to be asserted with that flag on, which is how it
    runs in production."""
    assert fa._user_audiences_path().name == "saved_audiences.json"
    assert fa._user_audiences_path().parent == fa._resolve_user_root()

    monkeypatch.setattr(fa, "_SERVER_MODE", True)
    mine = fa._CURRENT_USER_EMAIL.get()
    assert mine, "with_user must have bound a user"
    fa.save_saved_audience("Mine", {"industries": ["Logistics"]})

    fa._CURRENT_USER_EMAIL.set("someone.else@example.com")
    try:
        assert fa.load_saved_audiences() == [], "another rep sees my audiences"
        fa.save_saved_audience("Theirs", {"industries": ["Construction"]})
        assert [a["name"] for a in fa.load_saved_audiences()] == ["Theirs"]
    finally:
        fa._CURRENT_USER_EMAIL.set(mine)

    assert [a["name"] for a in fa.load_saved_audiences()] == ["Mine"]


# ═══════════════════════════════════════════════════════════════════════════
#  Group B — cross-campaign dedupe enforcement
# ═══════════════════════════════════════════════════════════════════════════

def test_13_a_contact_pending_elsewhere_is_skipped_and_the_campaign_named(fa):
    _seed_campaigns(fa, [{"name": "Q3 Logistics", "status": "active"}])
    _seed_queue(fa, [_pending("Q3 Logistics", "dupe@x.com")])
    contacts = [_contact("dupe@x.com"), _contact("fresh@x.com")]

    res = fa._tm_dedupe_split(contacts)

    assert [c["email"] for c in res["kept"]] == ["fresh@x.com"]
    assert [c["email"] for c in res["skipped"]] == ["dupe@x.com"]
    assert res["count"] == 1
    assert res["duplicates"]["dupe@x.com"] == ["Q3 Logistics"]
    assert res["campaigns"] == ["Q3 Logistics"]
    assert res["scope"] == "workspace"


def test_14_the_current_campaign_does_not_count_against_itself(fa):
    """Re-entering the wizard on a campaign must not dedupe out its own
    contacts — that would empty the list on every edit."""
    _seed_campaigns(fa, [{"name": "Mine", "status": "active"}])
    _seed_queue(fa, [_pending("Mine", "a@x.com")])
    res = fa._tm_dedupe_split([_contact("a@x.com")], exclude_campaign="Mine")
    assert [c["email"] for c in res["kept"]] == ["a@x.com"]
    assert res["skipped"] == []
    assert res["count"] == 0


def test_15_cancelled_and_draft_campaigns_do_not_block(fa):
    _seed_campaigns(fa, [{"name": "Killed", "status": "cancelled"},
                         {"name": "Unsent", "status": "draft"}])
    _seed_queue(fa, [_pending("Killed", "a@x.com"), _pending("Unsent", "b@x.com")])
    res = fa._tm_dedupe_split([_contact("a@x.com"), _contact("b@x.com")])
    assert [c["email"] for c in res["kept"]] == ["a@x.com", "b@x.com"]
    assert res["count"] == 0


def test_16_a_finished_send_is_not_a_duplicate(fa):
    """Only PENDING mail is an active enrolment. Someone a finished campaign
    already mailed is a person we may legitimately approach again."""
    _seed_campaigns(fa, [{"name": "Done", "status": "active"}])
    _seed_queue(fa, [
        {"campaign": "Done", "to": "sent@x.com", "status": "sent"},
        {"campaign": "Done", "to": "cancelled@x.com", "status": "cancelled"},
    ])
    res = fa._tm_dedupe_split([_contact("sent@x.com"), _contact("cancelled@x.com")])
    assert len(res["kept"]) == 2
    assert res["count"] == 0


def test_17_dedupe_is_case_insensitive_on_email(fa):
    _seed_campaigns(fa, [{"name": "Q3", "status": "active"}])
    _seed_queue(fa, [_pending("Q3", "Dupe@X.COM")])
    res = fa._tm_dedupe_split([_contact("dupe@x.com")])
    assert res["skipped"] and res["skipped"][0]["email"] == "dupe@x.com"
    assert res["kept"] == []


def test_18_no_duplicates_keeps_everyone_in_input_order(fa):
    _seed_campaigns(fa, [{"name": "Q3", "status": "active"}])
    _seed_queue(fa, [_pending("Q3", "nobody@x.com")])
    emails = [f"c{i}@x.com" for i in range(6)]
    res = fa._tm_dedupe_split([_contact(e) for e in emails])
    assert [c["email"] for c in res["kept"]] == emails
    assert res["skipped"] == []
    assert res["count"] == 0
    assert res["campaigns"] == []


def test_19_an_empty_workspace_keeps_everyone(fa):
    """No campaigns, no queue, no file — the answer is 'all of them'."""
    res = fa._tm_dedupe_split([_contact("a@x.com"), _contact("b@x.com")])
    assert len(res["kept"]) == 2
    assert res["count"] == 0


def test_20_a_contact_with_no_email_is_kept_never_silently_dropped(fa):
    _seed_campaigns(fa, [{"name": "Q3", "status": "active"}])
    _seed_queue(fa, [_pending("Q3", "dupe@x.com")])
    contacts = [_contact(""), _contact("dupe@x.com"), _contact("fresh@x.com")]
    res = fa._tm_dedupe_split(contacts)
    assert [c["email"] for c in res["kept"]] == ["", "fresh@x.com"]
    assert len(res["kept"]) + len(res["skipped"]) == len(contacts)


def test_21_kept_plus_skipped_always_accounts_for_every_contact(fa):
    """The invariant that makes the count in the UI trustworthy."""
    _seed_campaigns(fa, [{"name": "A", "status": "active"},
                         {"name": "B", "status": "cancelled"}])
    _seed_queue(fa, [_pending("A", "one@x.com"), _pending("A", "two@x.com"),
                     _pending("B", "three@x.com")])
    contacts = [_contact(e) for e in
                ("one@x.com", "two@x.com", "three@x.com", "four@x.com", "")]
    res = fa._tm_dedupe_split(contacts)
    assert len(res["kept"]) + len(res["skipped"]) == 5
    assert res["count"] == len(res["skipped"]) == 2
    assert res["checked"] == 4, "four distinct non-blank emails were checked"


def test_22_a_contact_in_two_campaigns_names_both(fa):
    _seed_campaigns(fa, [{"name": "Alpha", "status": "active"},
                         {"name": "Beta", "status": "active"}])
    _seed_queue(fa, [_pending("Alpha", "a@x.com"), _pending("Beta", "a@x.com")])
    res = fa._tm_dedupe_split([_contact("a@x.com")])
    assert res["duplicates"]["a@x.com"] == ["Alpha", "Beta"]
    assert res["campaigns"] == ["Alpha", "Beta"]


def test_23_dedupe_split_agrees_with_already_targeted(fa):
    """_tm_dedupe_split is the enforcement wrapper around Phase 1's report.
    It may not invent its own opinion about who is enrolled."""
    _seed_campaigns(fa, [{"name": "Q3", "status": "active"}])
    _seed_queue(fa, [_pending("Q3", "a@x.com"), _pending("Q3", "b@x.com")])
    contacts = [_contact("a@x.com"), _contact("c@x.com")]
    split = fa._tm_dedupe_split(contacts)
    report = fa._already_targeted([c["email"] for c in contacts])
    assert split["duplicates"] == report["duplicates"]
    assert split["count"] == report["count"]
    assert split["checked"] == report["checked"]
    assert split["campaigns"] == report["campaigns"]


# ═══════════════════════════════════════════════════════════════════════════
#  Group C — Arena isolation, at the AST level
# ═══════════════════════════════════════════════════════════════════════════

# Helpers that must never run for an Arena workspace. Phase 1 kept them away
# from Arena by having no callers at all; Phase 2 wires them into the wizard,
# so from here the guard is the gate itself.
_TM_GATED_NAMES = {
    "_tm_audience_filter",
    "_audience_summary_line",
    "_tm_dedupe_split",
    "_company_index",
    "load_saved_audiences",
    "save_saved_audience",
    "delete_saved_audience",
}

# Definitions that form the internal chain between those helpers, plus the
# storage layer they sit on. These are reached only THROUGH a gated caller,
# so requiring each to re-check the gate would be noise.
_CHAIN_EXEMPT = _TM_GATED_NAMES | {
    "_audience_filter_kwargs",
    "_normalise_audience",
    "_user_audiences_path",
    "_recheck_enrolment_duplicates",
    "_already_targeted",
    "_active_enrolments",
}

# Pure-logic helpers: no UI may be built inside them, so they stay testable
# and reusable from the API/MCP surface later.
_PURE_NAMES = {
    "_tm_dedupe_split", "_normalise_audience", "_audience_filter_kwargs",
    "load_saved_audiences", "save_saved_audience", "delete_saved_audience",
    "_user_audiences_path",
}


@pytest.fixture(scope="module")
def app_tree():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent /
           "flowdrip_app.py").read_text(encoding="utf-8")
    return ast.parse(src)


def _top_level_functions(tree):
    """{name: node} for module-level defs only — nested defs are reported
    against their enclosing function, which is the unit that carries the gate."""
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _referenced_names(node):
    return ({n.id for n in ast.walk(node) if isinstance(n, ast.Name)} |
            {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)})


def test_24_every_caller_of_a_gated_helper_also_checks_the_gate(app_tree):
    """Arena's protection in one assertion. A function that reaches for
    segmentation or dedupe must reach for _is_thrivemodal in the same body."""
    offenders = []
    for name, node in _top_level_functions(app_tree).items():
        if name in _CHAIN_EXEMPT:
            continue
        refs = _referenced_names(node)
        reached = refs & _TM_GATED_NAMES
        if reached and not (refs & {"_is_thrivemodal", "_LOCKED_PLAYBOOK",
                                    "_workspace_playbook", "_campaign_playbook"}):
            offenders.append((name, sorted(reached)))
    assert offenders == [], (
        "ungated segmentation/dedupe callers — Arena can reach these: "
        f"{offenders}")


def test_25_the_pure_helpers_build_no_ui(app_tree):
    fns = _top_level_functions(app_tree)
    for name in sorted(_PURE_NAMES):
        assert name in fns, f"{name} is not defined at module level"
        body = ast.dump(fns[name])
        assert "'ui'" not in body, f"{name} builds UI; it must stay pure"
        assert "notify" not in body, f"{name} notifies; it must stay pure"


def test_26_dedupe_enforcement_never_touches_the_sender_or_queue_writers(app_tree):
    """Phase 2 drops contacts at enrolment. It must not reach into the send
    path — the queue-path scope contradiction the handoff resolved stays
    resolved, and sender behaviour is unchanged."""
    import re as _re
    pat = _re.compile(r"(^|_)(send|sender|smtp|deliver)(_|$)")
    for name, node in _top_level_functions(app_tree).items():
        if not pat.search(name):
            continue
        reached = _referenced_names(node) & _TM_GATED_NAMES
        assert not reached, f"{name} (send path) reaches {sorted(reached)}"


def test_27_saved_audiences_is_not_written_by_any_campaign_writer(app_tree):
    """A saved audience is a filter, not campaign state. Nothing in the
    campaign save path may write it, or an audience edit could restamp a
    saved campaign."""
    fns = _top_level_functions(app_tree)
    for name in ("save_campaign", "_campaign_regen_block"):
        if name not in fns:
            continue
        refs = _referenced_names(fns[name])
        assert "save_saved_audience" not in refs, name
        assert "_user_audiences_path" not in refs, name

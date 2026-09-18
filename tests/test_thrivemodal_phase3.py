"""ThriveModal Phase 3 — outreach analytics, from the data that already exists.

Phase 3 adds a reporting page to the two sidebar rows that have always been
wired to None. It adds NO storage: every number comes from the queue, the
responded log and the DNC list, which the app already writes on the send path.

What the tests pin, and why each one is load-bearing:

  * Group A — the window and classification primitives. A date window that
    silently drops undated records would under-report sends, and an opt-out
    rate that counted bounces as opt-outs would tell the user their copy is
    being rejected when in fact their list is stale. Both are worse than no
    analytics, because a wrong number still gets acted on.

  * Group B — `_tm_outreach_stats`. The one rule that matters more than any
    count: a rate is only reported when its numerator and denominator come
    from the same scope. Opt-outs and bounces live on the DNC list, which
    records no campaign, so a campaign-scoped call must refuse to attribute
    them rather than quietly showing workspace totals under a campaign name.

  * Group C/D — the per-campaign and per-step breakdowns, which are the only
    parts a user acts on ("step 3 is where everyone cancels").

  * Group E — Arena isolation. Same shape as Phase 2: anything reaching an
    analytics helper must reach `_is_thrivemodal` in the same body, the page
    renders nothing off-playbook, and the whole feature reads without writing.

There is no open or click tracking anywhere in this app, so no test here
asserts an open rate — and the page must not invent one.

Written against the spec, not the implementation. Every test in Groups A-D
was red before the Phase 3 splice.
"""
import ast
import copy
import json
from datetime import datetime, timedelta

import pytest


# NEVER import flowdrip_app at module level (see tests/conftest.py).

@pytest.fixture
def fa(isolated_appdata, with_user, monkeypatch):
    """flowdrip_app with per-user paths sandboxed and the funnelforge_core
    fast path disabled, so queue reads take the JSON fallback."""
    import flowdrip_app as _fa
    monkeypatch.setattr(_fa, "_FUNNELFORGE_OK", False)
    monkeypatch.setattr(_fa, "_ffc", None)
    _fa._cache_campaigns.invalidate()
    _fa._cache_queue.invalidate()
    _fa._cache_responded.invalidate()
    yield _fa
    _fa._cache_campaigns.invalidate()
    _fa._cache_queue.invalidate()
    _fa._cache_responded.invalidate()


# ── helpers ────────────────────────────────────────────────────────────────

def _iso(days_ago=0, hours_ago=0):
    return (datetime.now() - timedelta(days=days_ago, hours=hours_ago)
            ).isoformat(timespec="seconds")


def _sent(campaign, email, days_ago=1, touch=1, step_name="Email 1"):
    return {"campaign": campaign, "to": email, "status": "sent",
            "sent_at": _iso(days_ago), "send_dt": _iso(days_ago),
            "touch_number": touch, "step_name": step_name}


def _pending(campaign, email, days_ahead=2, touch=2, step_name="Email 2"):
    return {"campaign": campaign, "to": email, "status": "pending",
            "send_dt": (datetime.now() + timedelta(days=days_ahead)
                        ).isoformat(timespec="seconds"),
            "touch_number": touch, "step_name": step_name}


def _cancelled(campaign, email, days_ago=1, touch=3, step_name="Email 3"):
    return {"campaign": campaign, "to": email, "status": "cancelled",
            "send_dt": _iso(days_ago), "touch_number": touch,
            "step_name": step_name}


def _failed(campaign, email, days_ago=1, touch=1):
    return {"campaign": campaign, "to": email, "status": "failed",
            "failed_at": _iso(days_ago), "send_dt": _iso(days_ago),
            "touch_number": touch, "step_name": "Email 1"}


def _reply(campaign, email, days_ago=1):
    return {"email": email, "name": "X Y", "campaign": campaign,
            "touch": " - ", "subject": "re:", "replied_at": _iso(days_ago)}


def _dnc_optout(email, days_ago=1):
    return {"email": email, "name": "", "company": "",
            "reason": "Auto-detected opt-out", "source": "auto-opt-out",
            "added_at": _iso(days_ago)}


def _dnc_bounce(email, days_ago=1):
    # The send path writes this shape directly — note "added", not "added_at".
    return {"email": email, "added": _iso(days_ago),
            "reason": "Bounced: 550 5.1.1 recipient not found"}


def _dnc_manual(email, days_ago=1):
    return {"email": email, "name": "", "company": "", "reason": "Manual",
            "source": "manual", "added_at": _iso(days_ago)}


class _StubState:
    """Enough AppState surface for the page's early return."""
    def __init__(self):
        self.sp = "tm_analytics"
        self.hub = "sales"
        self._user_email = "user@example.com"


# ═══════════════════════════════════════════════════════════════════════════
#  Group A — window + classification primitives
# ═══════════════════════════════════════════════════════════════════════════

def test_01_queue_timestamp_prefers_what_actually_happened(fa):
    """A sent email is dated by when it was sent, not when it was scheduled;
    otherwise a re-queued campaign reports sends on the wrong day."""
    assert fa._tm_queue_ts({"sent_at": "2026-09-10T08:00:00",
                            "send_dt": "2026-09-01T08:00:00"}) == "2026-09-10T08:00:00"
    assert fa._tm_queue_ts({"failed_at": "2026-09-11T08:00:00",
                            "send_dt": "2026-09-01T08:00:00"}) == "2026-09-11T08:00:00"
    assert fa._tm_queue_ts({"send_dt": "2026-09-01T08:00:00"}) == "2026-09-01T08:00:00"
    assert fa._tm_queue_ts({}) == ""


def test_02_all_time_has_no_cutoff(fa):
    assert fa._tm_window_cutoff(None) == ""
    assert fa._tm_window_cutoff(0) == ""


def test_03_a_window_cutoff_is_days_back_from_now(fa):
    cutoff = fa._tm_window_cutoff(7)
    parsed = datetime.fromisoformat(cutoff)
    delta = datetime.now() - parsed
    assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)


def test_04_undated_records_are_inside_every_window(fa):
    """We cannot date them, and a record that vanishes from a report is one
    nobody notices is missing. Counting it is the conservative error."""
    cutoff = fa._tm_window_cutoff(7)
    assert fa._tm_in_window("", cutoff) is True
    assert fa._tm_in_window(None, cutoff) is True
    assert fa._tm_in_window(_iso(1), cutoff) is True
    assert fa._tm_in_window(_iso(30), cutoff) is False
    # No cutoff = everything.
    assert fa._tm_in_window(_iso(3650), "") is True


def test_05_dnc_entries_are_classified_by_what_put_them_there(fa):
    """Bounces and opt-outs both land on the DNC list and mean opposite
    things: a bad address versus a rejected message."""
    assert fa._tm_dnc_kind(_dnc_bounce("a@x.com")) == "bounce"
    assert fa._tm_dnc_kind(_dnc_optout("b@x.com")) == "optout"
    assert fa._tm_dnc_kind(_dnc_manual("c@x.com")) == "manual"
    assert fa._tm_dnc_kind({"email": "d@x.com",
                            "reason": "Unsubscribed via link"}) == "optout"
    assert fa._tm_dnc_kind({}) == "manual"


# ═══════════════════════════════════════════════════════════════════════════
#  Group B — _tm_outreach_stats
# ═══════════════════════════════════════════════════════════════════════════

def test_06_empty_everything_is_a_valid_report_not_a_crash(fa):
    st = fa._tm_outreach_stats([], [], [])
    for k in ("sent", "failed", "pending", "cancelled", "contacts",
              "campaigns", "replies", "optouts", "bounces"):
        assert st[k] == 0, k
    for k in ("reply_rate", "optout_rate", "bounce_rate"):
        assert st[k] == 0.0, k
    assert fa._tm_outreach_stats(None, None, None)["sent"] == 0


def test_07_each_queue_status_lands_in_its_own_bucket(fa):
    q = [_sent("A", "a@x.com"), _sent("A", "b@x.com"),
         _pending("A", "a@x.com"), _cancelled("A", "c@x.com"),
         _failed("A", "d@x.com"), {"campaign": "A", "to": "e@x.com",
                                   "status": "skipped", "send_dt": _iso(1)}]
    st = fa._tm_outreach_stats(q, [], [])
    assert st["sent"] == 2
    assert st["pending"] == 1
    assert st["cancelled"] == 1
    assert st["failed"] == 1


def test_08_contacts_reached_counts_people_not_emails(fa):
    """Three sends to one person is one person. The reply-rate denominator
    has to be people or the rate is meaningless for a 5-step sequence."""
    q = [_sent("A", "a@x.com", touch=1), _sent("A", "A@X.com", touch=2),
         _sent("A", "b@x.com", touch=1), _pending("A", "c@x.com")]
    st = fa._tm_outreach_stats(q, [], [])
    assert st["contacts"] == 2, "case-insensitive, and pending is not reached"


def test_09_scheduled_mail_is_counted_even_though_it_is_in_the_future(fa):
    """Pending sends are dated ahead of now; a naive window would drop them
    and the page would say a live campaign has nothing queued."""
    q = [_sent("A", "a@x.com", days_ago=1), _pending("A", "a@x.com", days_ahead=5)]
    st = fa._tm_outreach_stats(q, [], [], days=7)
    assert st["pending"] == 1
    assert st["sent"] == 1


def test_10_replies_come_from_the_responded_log_and_rate_is_per_contact(fa):
    q = [_sent("A", "a@x.com"), _sent("A", "b@x.com"),
         _sent("A", "c@x.com"), _sent("A", "d@x.com")]
    st = fa._tm_outreach_stats(q, [_reply("A", "a@x.com")], [])
    assert st["replies"] == 1
    assert st["contacts"] == 4
    assert st["reply_rate"] == pytest.approx(0.25)


def test_11_rates_are_zero_when_nobody_was_reached(fa):
    """No division by zero, and no 100% reply rate off a single reply to a
    campaign whose sends fall outside the window."""
    st = fa._tm_outreach_stats([_pending("A", "a@x.com")], [_reply("A", "z@x.com")], [])
    assert st["contacts"] == 0
    assert st["reply_rate"] == 0.0


def test_12_optouts_and_bounces_are_counted_separately(fa):
    q = [_sent("A", f"{c}@x.com") for c in "abcdefghij"]
    dnc = [_dnc_optout("a@x.com"), _dnc_bounce("b@x.com"),
           _dnc_bounce("c@x.com"), _dnc_manual("d@x.com")]
    st = fa._tm_outreach_stats(q, [], dnc)
    assert st["contacts"] == 10
    assert st["optouts"] == 1
    assert st["bounces"] == 2
    assert st["optout_rate"] == pytest.approx(0.1)
    assert st["bounce_rate"] == pytest.approx(0.2)


def test_13_a_campaign_filter_scopes_the_queue_and_the_replies(fa):
    q = [_sent("A", "a@x.com"), _sent("B", "b@x.com"), _pending("B", "c@x.com")]
    resp = [_reply("A", "a@x.com"), _reply("B", "b@x.com")]
    st = fa._tm_outreach_stats(q, resp, [], campaign="B")
    assert st["sent"] == 1
    assert st["pending"] == 1
    assert st["contacts"] == 1
    assert st["replies"] == 1
    assert st["campaign"] == "B"


def test_14_a_campaign_filter_refuses_to_attribute_optouts_and_bounces(fa):
    """The DNC list records no campaign. Showing workspace opt-outs under one
    campaign's name would invent attribution the data cannot support, so the
    campaign view reports none and says so."""
    q = [_sent("A", "a@x.com"), _sent("B", "b@x.com")]
    dnc = [_dnc_optout("a@x.com"), _dnc_bounce("b@x.com")]
    st = fa._tm_outreach_stats(q, [], dnc, campaign="B")
    assert st["dnc_counted"] is False
    assert st["optouts"] == 0
    assert st["bounces"] == 0
    assert st["optout_rate"] == 0.0
    assert st["bounce_rate"] == 0.0
    # Unscoped, the same data does count.
    assert fa._tm_outreach_stats(q, [], dnc)["dnc_counted"] is True


def test_15_the_window_trims_sends_replies_and_dnc_alike(fa):
    q = [_sent("A", "a@x.com", days_ago=2), _sent("A", "b@x.com", days_ago=40)]
    resp = [_reply("A", "a@x.com", days_ago=2), _reply("A", "b@x.com", days_ago=40)]
    dnc = [_dnc_optout("a@x.com", days_ago=2), _dnc_optout("b@x.com", days_ago=40)]
    st = fa._tm_outreach_stats(q, resp, dnc, days=7)
    assert (st["sent"], st["replies"], st["optouts"]) == (1, 1, 1)
    allt = fa._tm_outreach_stats(q, resp, dnc, days=None)
    assert (allt["sent"], allt["replies"], allt["optouts"]) == (2, 2, 2)


def test_16_campaign_count_is_campaigns_with_activity(fa):
    q = [_sent("A", "a@x.com"), _pending("B", "b@x.com"),
         {"to": "c@x.com", "status": "sent", "sent_at": _iso(1)}]
    st = fa._tm_outreach_stats(q, [], [])
    assert st["campaigns"] == 2, "an unnamed queue item is not a campaign"
    assert st["sent"] == 2, "but its send still happened"


def test_17_reporting_never_mutates_what_it_was_given(fa):
    """The page passes live cached lists straight in. A report that edited
    them would corrupt the queue cache for every other page in the render."""
    q = [_sent("A", "a@x.com"), _pending("A", "b@x.com")]
    resp = [_reply("A", "a@x.com")]
    dnc = [_dnc_optout("a@x.com")]
    before = copy.deepcopy((q, resp, dnc))
    fa._tm_outreach_stats(q, resp, dnc, days=30)
    fa._tm_campaign_analytics(q, resp, days=30)
    fa._tm_step_analytics(q, days=30)
    assert (q, resp, dnc) == before


def test_18_window_days_is_reported_back(fa):
    """The page prints the window beside the numbers; it reads it from the
    result so the label can never disagree with the data."""
    assert fa._tm_outreach_stats([], [], [], days=7)["window_days"] == 7
    assert fa._tm_outreach_stats([], [], [], days=None)["window_days"] is None


# ═══════════════════════════════════════════════════════════════════════════
#  Group C — per-campaign rows
# ═══════════════════════════════════════════════════════════════════════════

def test_19_one_row_per_campaign_busiest_first(fa):
    q = [_sent("Alpha", "a@x.com"), _sent("Alpha", "b@x.com"),
         _sent("Beta", "c@x.com"), _pending("Beta", "d@x.com"),
         _sent("Gamma", "e@x.com"), _sent("Gamma", "f@x.com"),
         _sent("Gamma", "g@x.com")]
    rows = fa._tm_campaign_analytics(q, [], days=None)
    assert [r["name"] for r in rows] == ["Gamma", "Alpha", "Beta"]


def test_20_campaign_rows_carry_their_own_counts_and_rate(fa):
    q = [_sent("Alpha", "a@x.com", touch=1), _sent("Alpha", "a@x.com", touch=2),
         _sent("Alpha", "b@x.com"), _pending("Alpha", "c@x.com"),
         _failed("Alpha", "d@x.com"), _cancelled("Alpha", "b@x.com")]
    rows = fa._tm_campaign_analytics(q, [_reply("Alpha", "a@x.com")], days=None)
    assert len(rows) == 1
    r = rows[0]
    assert r["sent"] == 3
    assert r["contacts"] == 2
    assert r["pending"] == 1
    assert r["failed"] == 1
    assert r["cancelled"] == 1
    assert r["replies"] == 1
    assert r["reply_rate"] == pytest.approx(0.5)


def test_21_a_campaign_that_has_only_been_scheduled_still_gets_a_row(fa):
    """It launched. Hiding it until the first send makes the page look broken
    in the window between launching and the first morning's send."""
    rows = fa._tm_campaign_analytics([_pending("Alpha", "a@x.com")], [], days=None)
    assert len(rows) == 1
    assert rows[0]["sent"] == 0
    assert rows[0]["pending"] == 1
    assert rows[0]["reply_rate"] == 0.0


def test_22_unnamed_queue_items_do_not_become_a_blank_row(fa):
    q = [{"to": "a@x.com", "status": "sent", "sent_at": _iso(1)},
         {"campaign": "  ", "to": "b@x.com", "status": "sent", "sent_at": _iso(1)},
         _sent("Alpha", "c@x.com")]
    rows = fa._tm_campaign_analytics(q, [], days=None)
    assert [r["name"] for r in rows] == ["Alpha"]


def test_23_replies_for_a_campaign_with_no_queue_rows_are_not_lost(fa):
    """Queue entries are archived after 30 days but responded records are
    kept, so a reply can outlive its send. It still belongs to the campaign."""
    rows = fa._tm_campaign_analytics([_sent("Alpha", "a@x.com")],
                                     [_reply("Alpha", "a@x.com"),
                                      _reply("Beta", "b@x.com")], days=None)
    by_name = {r["name"]: r for r in rows}
    assert by_name["Beta"]["replies"] == 1
    assert by_name["Beta"]["sent"] == 0
    assert by_name["Beta"]["reply_rate"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  Group D — per-step rows
# ═══════════════════════════════════════════════════════════════════════════

def test_24_step_rows_are_in_sequence_order(fa):
    q = [_sent("A", "a@x.com", touch=3, step_name="Email 3"),
         _sent("A", "b@x.com", touch=1, step_name="Email 1"),
         _pending("A", "c@x.com", touch=2, step_name="Email 2")]
    rows = fa._tm_step_analytics(q, days=None)
    assert [r["touch"] for r in rows] == [1, 2, 3]


def test_25_step_rows_show_where_a_sequence_stops(fa):
    """Cancelled-at-step is the signal worth having: it is what a reply, an
    opt-out or a bounce does to the rest of someone's sequence."""
    q = [_sent("A", "a@x.com", touch=1), _sent("A", "b@x.com", touch=1),
         _sent("A", "a@x.com", touch=2),
         _cancelled("A", "b@x.com", touch=2),
         _pending("A", "a@x.com", touch=3),
         _cancelled("A", "b@x.com", touch=3)]
    rows = {r["touch"]: r for r in fa._tm_step_analytics(q, days=None)}
    assert (rows[1]["sent"], rows[1]["cancelled"]) == (2, 0)
    assert (rows[2]["sent"], rows[2]["cancelled"]) == (1, 1)
    assert (rows[3]["pending"], rows[3]["cancelled"]) == (1, 1)


def test_26_step_rows_carry_a_label(fa):
    rows = fa._tm_step_analytics(
        [_sent("A", "a@x.com", touch=2, step_name="Case study")], days=None)
    assert rows[0]["label"] == "Case study"


def test_27_a_queue_item_with_no_touch_number_is_step_one(fa):
    """Older queue entries predate touch_number. They are still sends."""
    rows = fa._tm_step_analytics(
        [{"campaign": "A", "to": "a@x.com", "status": "sent",
          "sent_at": _iso(1)}], days=None)
    assert len(rows) == 1
    assert rows[0]["touch"] == 1
    assert rows[0]["sent"] == 1


# ═══════════════════════════════════════════════════════════════════════════
#  Group E — Arena isolation and read-only-ness
# ═══════════════════════════════════════════════════════════════════════════

_TM_ANALYTICS_NAMES = {
    "_tm_outreach_stats",
    "_tm_campaign_analytics",
    "_tm_step_analytics",
    "_tm_analytics_sources",
    "p_tm_analytics",
}

# Reached only through a gated caller; re-checking the gate in each would be
# noise, and they are pure enough to be reused by the API/MCP surface later.
_ANALYTICS_CHAIN_EXEMPT = _TM_ANALYTICS_NAMES | {
    "_tm_queue_ts", "_tm_window_cutoff", "_tm_in_window", "_tm_dnc_kind",
    "_tm_rate",
}

_ANALYTICS_PURE_NAMES = {
    "_tm_outreach_stats", "_tm_campaign_analytics", "_tm_step_analytics",
    "_tm_queue_ts", "_tm_window_cutoff", "_tm_in_window", "_tm_dnc_kind",
    "_tm_rate",
}


@pytest.fixture(scope="module")
def app_tree():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent /
           "flowdrip_app.py").read_text(encoding="utf-8")
    return ast.parse(src)


def _top_level_functions(tree):
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _referenced_names(node):
    return ({n.id for n in ast.walk(node) if isinstance(n, ast.Name)} |
            {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)})


def test_28_the_analytics_page_checks_the_gate_itself(app_tree):
    fns = _top_level_functions(app_tree)
    assert "p_tm_analytics" in fns
    assert "_is_thrivemodal" in _referenced_names(fns["p_tm_analytics"])


def test_29_every_caller_of_an_analytics_helper_also_checks_the_gate(app_tree):
    offenders = []
    for name, node in _top_level_functions(app_tree).items():
        if name in _ANALYTICS_CHAIN_EXEMPT:
            continue
        refs = _referenced_names(node)
        reached = refs & _TM_ANALYTICS_NAMES
        if reached and not (refs & {"_is_thrivemodal", "_LOCKED_PLAYBOOK",
                                    "_workspace_playbook"}):
            offenders.append((name, sorted(reached)))
    assert offenders == [], (
        f"ungated analytics callers — Arena can reach these: {offenders}")


def test_30_the_analytics_helpers_build_no_ui(app_tree):
    fns = _top_level_functions(app_tree)
    for name in sorted(_ANALYTICS_PURE_NAMES):
        assert name in fns, f"{name} is not defined at module level"
        body = ast.dump(fns[name])
        assert "'ui'" not in body, f"{name} builds UI; it must stay pure"
        assert "notify" not in body, f"{name} notifies; it must stay pure"


def test_31_analytics_writes_nothing(app_tree):
    """A reporting page is read-only. Nothing here may save a campaign, edit
    the queue, or add to the DNC list — the numbers are evidence, not state."""
    writers = {"save_campaign", "save_dnc", "add_to_dnc", "save_responded",
               "_save_queue", "save_queue", "_atomic_write_text",
               "_atomic_write_csv_text", "archive_old_queue_entries",
               "save_saved_audience", "delete_saved_audience"}
    fns = _top_level_functions(app_tree)
    for name in sorted(_TM_ANALYTICS_NAMES | _ANALYTICS_PURE_NAMES):
        if name not in fns:
            continue
        hit = _referenced_names(fns[name]) & writers
        assert not hit, f"{name} writes: {sorted(hit)}"


def test_32_the_analytics_row_stays_hidden_for_arena(fa, monkeypatch):
    """The sidebar row is wired to None for everyone; ThriveModal is the only
    playbook that resolves it to a page."""
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    assert fa._tm_nav_page_key("analytics", None) is None
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    assert fa._tm_nav_page_key("analytics", None) == "tm_analytics"


def test_33_an_existing_destination_is_never_rewritten(fa, monkeypatch):
    """Row resolution must be additive. If it could change a page key that
    already exists, one typo would send an Arena user to the wrong page."""
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    for _sec, rows in fa.SIDEBAR_NAV:
        for row_key, _lbl, page_key in rows:
            if page_key:
                assert fa._tm_nav_page_key(row_key, page_key) == page_key


def test_34_the_page_renders_nothing_off_playbook(fa, monkeypatch):
    """Belt and braces for the row test: even reached directly by URL or a
    stale session, the page builds no UI for a non-ThriveModal workspace."""
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    assert fa.p_tm_analytics(_StubState(), lambda: None) is None


def test_35_the_page_is_routed_and_titled(fa):
    assert fa.SIDEBAR_PAGE_ROW.get("tm_analytics") == "analytics"
    assert fa.SIDEBAR_TITLES.get("tm_analytics")
    import pathlib
    src = (pathlib.Path(fa.__file__).resolve().parent / "flowdrip_app.py"
           ).read_text(encoding="utf-8")
    assert 'page == "tm_analytics"' in src, "the router has no route to the page"


def test_36_sources_come_from_the_existing_stores_only(fa, app_tree):
    """Phase 3 adds no storage. The loader reads the queue, the responded log
    and the DNC list, and nothing else."""
    fns = _top_level_functions(app_tree)
    assert "_tm_analytics_sources" in fns
    refs = _referenced_names(fns["_tm_analytics_sources"])
    assert {"_load_queue", "load_responded", "load_dnc"} <= refs
    qp = fa._user_queue_path()
    qp.parent.mkdir(parents=True, exist_ok=True)
    qp.write_text(json.dumps([_sent("A", "a@x.com")]), encoding="utf-8")
    fa._cache_queue.invalidate()
    src = fa._tm_analytics_sources()
    assert [i["to"] for i in src["queue"]] == ["a@x.com"]
    assert src["responded"] == []
    assert src["dnc"] == []

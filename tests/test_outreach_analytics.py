"""Outreach Analytics grouped by campaign type (outreach_analytics.py)."""
import ast
import pathlib
from datetime import datetime, timedelta

import outreach_analytics as oa

NOW = datetime(2026, 10, 2, 12, 0, 0)
TYPES = [("tm_fivebyseven", "Standard Outreach", "#0EA5E9"),
         ("tm_threebythree", "Quick Intro", "#EF4444")]


def _iso(days_ago, hours=0):
    return (NOW - timedelta(days=days_ago, hours=hours)).isoformat()


def _q(camp, to, touch, status="sent", days_ago=1, label=None, **kw):
    row = {"id": f"{camp}::{to}::{touch}", "campaign": camp, "to": to,
           "touch_number": touch, "status": status,
           "step_name": label or f"Step {touch}", "subject": f"S{touch}",
           "to_name": to.split("@")[0].title(), "contact_company": "Acme"}
    if status == "sent":
        row["sent_at"] = _iso(days_ago)
    else:
        row["send_dt"] = _iso(-days_ago if status == "pending" else days_ago)
    row.update(kw)
    return row


CAMPS = [
    {"name": "Fusion Transport", "template_key": "tm_fivebyseven"},
    {"name": "R2 Logistics", "aicb_camp_type": "tm_fivebyseven"},
    {"name": "Big List", "_chooser_origin": "tm_threebythree"},
    {"name": "Offshore News", "market_analysis": {"x": 1}},
    {"name": "Hand built"},
]


def _report(queue, responded=(), dnc=(), days=None):
    return oa.build_report(queue, list(responded), list(dnc), CAMPS, TYPES,
                           days=days, now=NOW)


def test_campaigns_roll_up_under_their_type():
    q = [_q("Fusion Transport", "a@x.com", 1), _q("Fusion Transport", "b@x.com", 1),
         _q("R2 Logistics", "c@y.com", 1), _q("Big List", "d@z.com", 1),
         _q("R2 Logistics", "c@y.com", 2, status="pending")]
    rep = _report(q)
    rows = {r["key"]: r for r in rep["types"]}
    std = rows["tm_fivebyseven"]
    assert std["name"] == "Standard Outreach"
    assert (std["campaigns"], std["sent"], std["contacts"], std["pending"]) == (2, 3, 3, 1)
    assert rows["tm_threebythree"]["sent"] == 1
    assert rep["types"][0]["key"] == "tm_fivebyseven"   # busiest first


def test_newsletters_and_untyped_campaigns_get_their_own_groups_last():
    q = [_q("Offshore News", "a@x.com", 1), _q("Hand built", "b@x.com", 1),
         _q("Unknown name", "c@x.com", 1), _q("Big List", "d@x.com", 1)]
    keys = [r["key"] for r in _report(q)["types"]]
    assert keys[0] == "tm_threebythree"
    assert set(keys[1:]) == {oa.NEWSLETTER, oa.OTHER}
    other = next(r for r in _report(q)["types"] if r["key"] == oa.OTHER)
    assert other["campaigns"] == 2 and other["name"] == "Other campaigns"


def test_reply_is_credited_to_the_last_email_before_it():
    q = [_q("Fusion Transport", "a@x.com", 1, days_ago=6),
         _q("Fusion Transport", "a@x.com", 2, days_ago=3),
         _q("Fusion Transport", "b@x.com", 1, days_ago=6),
         _q("Fusion Transport", "a@x.com", 5, days_ago=0.1)]   # after the reply
    resp = [{"email": "A@x.com", "campaign": "Fusion Transport", "date": _iso(2)}]
    det = _report(q, resp)["details"]["tm_fivebyseven"]
    steps = {s["touch"]: s for s in det["steps"]}
    assert steps[1]["replies"] == 0 and steps[2]["replies"] == 1
    assert steps[5]["replies"] == 0
    assert steps[2]["reply_rate"] == 1.0
    assert steps[1]["reply_rate"] == 0.0
    assert [e["replied"] for e in steps[2]["emails"]] == [True]
    assert det["type"]["replies"] == 1
    assert det["type"]["reply_rate"] == 0.5   # 1 reply / 2 people


def test_reply_dates_from_both_writers_respect_the_window():
    q = [_q("Fusion Transport", "a@x.com", 1, days_ago=40),
         _q("Fusion Transport", "b@x.com", 1, days_ago=2)]
    resp = [{"email": "a@x.com", "campaign": "Fusion Transport", "date": _iso(35)},
            {"email": "b@x.com", "campaign": "Fusion Transport", "replied_at": _iso(1)}]
    rep = _report(q, resp, days=30)
    assert rep["totals"]["sent"] == 1
    assert rep["totals"]["replies"] == 1
    step = rep["details"]["tm_fivebyseven"]["steps"][0]
    assert step["replies"] == 1   # earlier send still found for attribution


def test_call_and_linkedin_rows_are_not_counted_as_emails():
    q = [_q("Fusion Transport", "a@x.com", 1),
         _q("Fusion Transport", "a@x.com", 3, step_type="call"),
         _q("Fusion Transport", "a@x.com", 4, step_type="linkedin")]
    rep = _report(q)
    assert rep["totals"]["sent"] == 1
    assert [s["touch"] for s in rep["details"]["tm_fivebyseven"]["steps"]] == [1]


def test_step_label_is_the_most_common_name():
    q = [_q("Fusion Transport", "a@x.com", 1, label="Capacity"),
         _q("R2 Logistics", "b@x.com", 1, label="Capacity"),
         _q("R2 Logistics", "c@x.com", 1, label="Custom")]
    step = _report(q)["details"]["tm_fivebyseven"]["steps"][0]
    assert step["label"] == "Capacity"
    assert len(step["emails"]) == 3


def test_step_number_prefix_is_dropped_from_the_label():
    q = [_q("Fusion Transport", "a@x.com", 1, label="Step 1 - The Signal"),
         _q("Fusion Transport", "a@x.com", 2, label="Email 2")]
    steps = _report(q)["details"]["tm_fivebyseven"]["steps"]
    assert [s["label"] for s in steps] == ["The Signal", "Email 2"]


def test_campaign_filter_narrows_the_step_table():
    q = [_q("Fusion Transport", "a@x.com", 1), _q("R2 Logistics", "b@x.com", 1),
         _q("R2 Logistics", "b@x.com", 2)]
    resp = [{"email": "b@x.com", "campaign": "R2 Logistics", "date": _iso(0.5)}]
    rep = _report(q, resp)
    rows = oa.campaign_detail(rep, "tm_fivebyseven", "R2 Logistics")
    assert [(r["touch"], r["sent"], r["replies"]) for r in rows] == [(1, 1, 0), (2, 1, 1)]
    camps = {c["name"]: c for c in rep["details"]["tm_fivebyseven"]["campaigns"]}
    assert camps["R2 Logistics"]["replies"] == 1 and camps["Fusion Transport"]["replies"] == 0


def test_totals_count_dnc_and_merge_dedupes_archive():
    live = [_q("Fusion Transport", "a@x.com", 1)]
    archive = [_q("Fusion Transport", "a@x.com", 1), _q("Fusion Transport", "z@x.com", 1)]
    merged = oa.merge_queue(live, archive)
    assert len(merged) == 2
    dnc = [{"email": "q@x.com", "reason": "Bounced: no such user", "added": _iso(1)},
           {"email": "r@x.com", "source": "auto-opt-out", "added_at": _iso(1)}]
    t = _report(merged, dnc=dnc)["totals"]
    assert (t["sent"], t["bounces"], t["optouts"]) == (2, 1, 1)


def test_empty_inputs_are_safe():
    rep = oa.build_report(None, None, None, None, TYPES)
    assert rep["types"] == [] and rep["totals"]["sent"] == 0


def test_module_writes_nothing_and_imports_no_app():
    src = (pathlib.Path(oa.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                for a in n.names} | {n.module for n in ast.walk(tree)
                                     if isinstance(n, ast.ImportFrom)}
    assert "flowdrip_app" not in imported and "nicegui" not in imported
    import re
    for bad in (r"(?<![\w.])open\(", r"write_text", r"\bsave_", r"json\.dump"):
        assert not re.search(bad, src), bad

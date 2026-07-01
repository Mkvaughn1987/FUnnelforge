"""Unit tests for PER-CAMPAIGN deliverability pacing.

Spec: change the server scheduler's send pacing from per-ACCOUNT (one email
per gap for the whole mailbox) to per-CAMPAIGN (each campaign trickles one
email per gap, but different campaigns may fire in the same tick). This stops
one large campaign from starving the others via head-of-line blocking.

`_select_due_per_campaign` is the pure decision function so the policy is
testable without touching files, the network, or wall-clock time.
"""
import flowdrip_app as fa


def _items(*specs):
    """specs: (campaign, id) pairs -> pending queue items in priority order."""
    return [{"campaign": c, "id": i, "status": "pending"} for c, i in specs]


_NOJIT = lambda g: 0  # deterministic: no jitter


def test_parallel_across_campaigns_one_each():
    """Different campaigns fire in the SAME tick; one email per campaign."""
    due = _items(("A", "a1"), ("A", "a2"), ("B", "b1"), ("C", "c1"))
    gate = {}
    sel = fa._select_due_per_campaign(due, 1000.0, 30, gate, 10, jitter=_NOJIT)
    assert [x["id"] for x in sel] == ["a1", "b1", "c1"]      # a2 held (one/camp)
    assert gate == {"A": 1030.0, "B": 1030.0, "C": 1030.0}   # each gated +gap


def test_campaign_gate_blocks_until_gap_elapses():
    """A campaign that sent recently is skipped until its gap has passed."""
    due = _items(("A", "a1"))
    gate = {"A": 1020.0}
    assert fa._select_due_per_campaign(due, 1000.0, 30, gate, 10, jitter=_NOJIT) == []
    sel = fa._select_due_per_campaign(due, 1020.0, 30, gate, 10, jitter=_NOJIT)
    assert [x["id"] for x in sel] == ["a1"]


def test_budget_caps_total_and_leaves_rest_eligible():
    """remaining_budget caps the tick; un-picked campaigns stay eligible."""
    due = _items(("A", "a1"), ("B", "b1"), ("C", "c1"))
    gate = {}
    sel = fa._select_due_per_campaign(due, 1000.0, 30, gate, 2, jitter=_NOJIT)
    assert [x["id"] for x in sel] == ["a1", "b1"]
    assert "C" not in gate          # C never gated -> eligible next tick


def test_gap_zero_disables_pacing():
    """gap<=0 sends everything (up to budget) and never touches the gate."""
    due = _items(("A", "a1"), ("A", "a2"), ("B", "b1"))
    gate = {}
    sel = fa._select_due_per_campaign(due, 1000.0, 0, gate, 10, jitter=_NOJIT)
    assert [x["id"] for x in sel] == ["a1", "a2", "b1"]
    assert gate == {}


def test_zero_budget_sends_nothing():
    assert fa._select_due_per_campaign(_items(("A", "a1")), 1000.0, 30, {}, 0) == []


def test_jitter_applied_on_top_of_gap():
    """next-eligible = now + gap + jitter(gap)."""
    due = _items(("A", "a1"))
    gate = {}
    fa._select_due_per_campaign(due, 1000.0, 30, gate, 10, jitter=lambda g: g)  # +100%
    assert gate["A"] == 1000.0 + 30 + 30

"""Arena 4x4 — same-day follow-up call after email 2.

Spec: docs/superpowers/specs/2026-06-27-arena-4x4-same-day-call-design.md
Plan: docs/superpowers/plans/2026-06-27-arena-4x4-same-day-call.md
"""
import inspect
import flowdrip_app as fa


def _fourbyfour():
    """Return the fourbyfour tuple from AICB_CAMPAIGN_TYPES."""
    for entry in fa.AICB_CAMPAIGN_TYPES:
        if entry[0] == "fourbyfour":
            return entry
    raise AssertionError("fourbyfour entry not found in AICB_CAMPAIGN_TYPES")


# ── touch_sequence: the same-day call ──────────────────────────────
def test_4x4_sequence_has_same_day_followup_call():
    seq = _fourbyfour()[6]
    assert "step_type:call" in seq
    # The call must be a same-day touch (delay_days:0 alongside email 2).
    assert "delay_days:0, step_type:call" in seq


def test_4x4_call_sits_between_email_2_and_proven_results():
    seq = _fourbyfour()[6]
    pos_insights = seq.index("Top Talent Insights")
    pos_call = seq.index("step_type:call")
    pos_proven = seq.index("Proven Results")
    assert pos_insights < pos_call < pos_proven


def test_4x4_emails_keep_their_cadence():
    # The four email steps still carry delays 0, 3, 4, 4 (unchanged).
    seq = _fourbyfour()[6]
    assert "Introducing Available Talent (delay_days:0, step_type:email_auto)" in seq
    assert "Top Talent Insights (delay_days:3, step_type:email_auto)" in seq
    assert "Proven Results (delay_days:4, step_type:email_auto)" in seq
    assert "Market Trends & Final Note (delay_days:4, step_type:email_auto)" in seq


# ── chip label ─────────────────────────────────────────────────────
def test_4x4_label_reflects_five_steps():
    assert _fourbyfour()[2] == "5 steps - 2 weeks"


def test_4x4_name_unchanged():
    assert _fourbyfour()[1] == "Arena 4×4"


# ── generation prompt: same-day 0 permitted ────────────────────────
def test_generation_prompt_drops_absolute_no_zero_rule():
    src = inspect.getsource(fa)
    assert "Never set multiple steps to 0 except the first" not in src


def test_generation_prompt_permits_explicit_same_day_zero():
    src = inspect.getsource(fa)
    assert "intentional same-day touch" in src

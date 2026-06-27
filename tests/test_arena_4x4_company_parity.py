"""Arena 4x4 company-path parity helpers.

Spec: docs/superpowers/specs/2026-06-27-arena-4x4-company-path-parity-design.md
Plan: docs/superpowers/plans/2026-06-27-arena-4x4-company-path-parity.md
"""
import flowdrip_app as fa


# ── _aicb_force_market_for_4x4 ─────────────────────────────────────
def test_4x4_with_company_forces_market_mode():
    # Company set, no niche -> default would be company mode (False);
    # 4x4 must flip to market mode and fill niche from the industry label.
    is_niche, niche = fa._aicb_force_market_for_4x4(
        "fourbyfour", False, "", "Construction", "Project Manager")
    assert is_niche is True
    assert niche == "Construction"


def test_4x4_niche_fallback_chain_uses_roles_then_default():
    # No industry label -> fall back to roles.
    _, niche = fa._aicb_force_market_for_4x4(
        "fourbyfour", False, "", "", "Estimator")
    assert niche == "Estimator"
    # No industry label and no roles -> generic default.
    _, niche2 = fa._aicb_force_market_for_4x4(
        "fourbyfour", False, "", "", "")
    assert niche2 == "your market"


def test_4x4_keeps_existing_niche():
    is_niche, niche = fa._aicb_force_market_for_4x4(
        "fourbyfour", True, "Solar EPC", "Energy", "Engineer")
    assert is_niche is True
    assert niche == "Solar EPC"


def test_non_4x4_is_unchanged():
    # A different campaign type with a company stays in company mode.
    is_niche, niche = fa._aicb_force_market_for_4x4(
        "talentdrop", False, "", "Construction", "Project Manager")
    assert is_niche is False
    assert niche == ""


# ── _aicb_candidate_weave_block ────────────────────────────────────
def test_4x4_weave_block_puts_candidates_on_every_email():
    txt = fa._aicb_candidate_weave_block("fourbyfour")
    # All four emails referenced, including 1 and 3 (the ones the generic
    # rule skipped).
    for n in ("Email 1", "Email 2", "Email 3", "Email 4"):
        assert n in txt
    # The generic "every other email" / "skip Email 1" language is gone.
    assert "EVERY OTHER email" not in txt
    assert "NOT Email 1" not in txt
    assert "WITHOUT candidates" not in txt


def test_non_4x4_weave_block_keeps_every_other_email():
    txt = fa._aicb_candidate_weave_block("talentdrop")
    assert "EVERY OTHER email" in txt
    assert "NOT Email 1" in txt

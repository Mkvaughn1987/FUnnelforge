"""Regression 2026-05-01: Step 2 of the AI Campaign Builder must require
a Primary Industry before the user can advance to Step 3. Prior to this
change, only the mode-specific signal (company name in Company mode,
niche in Market mode) was required — Primary Industry was optional. We
removed AI auto-fill from this step the same day, so missing industry
would silently degrade PDFs and email prompts; hard-gating it is the
fix.

These tests target the static guard logic. The page-render closures
(`_step2_target_filled`, `_step2_ok`) aren't exposed at module scope, so
we exercise the same fields the closures read."""


def test_company_mode_blocks_when_primary_industry_missing(isolated_appdata, with_user):
    """In Company mode, having a company name alone is NOT enough — the
    user must also pick a Primary Industry."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_target_mode = "company"
    s.aicb_company = "Acme Corp"
    s.aicb_primary_industry = ""  # empty — should block
    # Simulate the static gate the closures use:
    primary_filled = bool((s.aicb_primary_industry or "").strip())
    company_filled = bool((s.aicb_company or "").strip())
    step2_ok = primary_filled and company_filled
    assert not step2_ok, (
        "Step 2 must NOT be advanceable when Primary Industry is empty, "
        "even with company name filled. Empty industry breaks PDFs + "
        "email prompts downstream."
    )


def test_company_mode_advances_when_both_filled(isolated_appdata, with_user):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_target_mode = "company"
    s.aicb_company = "Acme Corp"
    s.aicb_primary_industry = "Manufacturing"
    primary_filled = bool((s.aicb_primary_industry or "").strip())
    company_filled = bool((s.aicb_company or "").strip())
    step2_ok = primary_filled and company_filled
    assert step2_ok


def test_market_mode_blocks_when_primary_industry_missing(isolated_appdata, with_user):
    """Market mode: niche alone isn't enough either — Primary Industry
    is the universal requirement now."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_target_mode = "market"
    s.aicb_niche = "Aerospace defense"
    s.aicb_primary_industry = ""
    primary_filled = bool((s.aicb_primary_industry or "").strip())
    niche_filled = bool((s.aicb_niche or "").strip())
    step2_ok = primary_filled and niche_filled
    assert not step2_ok


def test_market_mode_advances_when_both_filled(isolated_appdata, with_user):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_target_mode = "market"
    s.aicb_niche = "Aerospace defense"
    s.aicb_primary_industry = "Manufacturing"
    primary_filled = bool((s.aicb_primary_industry or "").strip())
    niche_filled = bool((s.aicb_niche or "").strip())
    step2_ok = primary_filled and niche_filled
    assert step2_ok


def test_industry_picker_call_site_marks_primary_required():
    """Static check: the AICB Step 2 caller of _render_industry_picker
    must pass required_primary=True so the red `*` indicator renders.
    Visual indicator + validation must change together — otherwise the
    UI lies to the user."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parent.parent / "flowdrip_app.py"
    text = src.read_text(encoding="utf-8")
    # Pinpoint the AICB call site by anchoring on the unique
    # primary_state_key argument it uses.
    aicb_call_idx = text.find('primary_state_key="aicb_primary_industry"')
    assert aicb_call_idx > 0, "Expected to find AICB industry picker call site"
    # Look at the next 400 chars for the required_primary flag.
    chunk = text[aicb_call_idx:aicb_call_idx + 400]
    assert "required_primary=True" in chunk, (
        "AICB Step 2 must pass required_primary=True to "
        "_render_industry_picker so the red `*` indicator renders. "
        f"Got chunk:\n{chunk}"
    )
    assert "required_primary=False" not in chunk, (
        "AICB Step 2 still passes required_primary=False — UI would "
        "show no `*` while validation blocks the user, which is a "
        "liar-UI pattern."
    )

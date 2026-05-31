"""Pure-function tests for the contacts-first AICB wizard restructure.

Spec: docs/superpowers/specs/2026-05-31-contacts-first-aicb-wizard-design.md

These helpers live in flowdrip_app.py's UI layer but are broken out
as pure functions so the wizard logic stays testable without a
NiceGUI harness. The wizard step count grew from 5 to 6 when we
inserted Upload + Confirm between Target type and Candidates.
"""
import flowdrip_app as fa


def test_clamp_valid_steps():
    """Valid step numbers (1..6) pass through unchanged."""
    for n in (1, 2, 3, 4, 5, 6):
        assert fa._aicb_clamp_wizard_step(n) == n


def test_clamp_invalid_falls_back_to_one():
    """Anything outside 1..6 falls back to 1 — same defensive default
    as the pre-restructure clamp at line 16823."""
    for bad in (0, -1, 7, 99, None, "two", ""):
        assert fa._aicb_clamp_wizard_step(bad) == 1


def test_is_multi_company_true_when_company_empty_and_niche_filled():
    """The AI extractor returns empty 'company' + populated 'niche'
    when it sees multiple companies in the contact list. That's the
    signal that drives the Target-a-Company multi-company banner."""
    assert fa._aicb_is_multi_company({
        "company": "",
        "niche": "Colorado Manufacturing",
    }) is True
    assert fa._aicb_is_multi_company({
        "company": "   ",
        "niche": "Denver Healthcare Construction",
    }) is True


def test_is_multi_company_false_when_company_present():
    """A single-company CSV makes the extractor return a company name.
    Banner should NOT show."""
    assert fa._aicb_is_multi_company({
        "company": "Acme Corp",
        "niche": "",
    }) is False
    assert fa._aicb_is_multi_company({
        "company": "Acme Corp",
        "niche": "Manufacturing",  # both set: still single-company
    }) is False


def test_is_multi_company_false_when_niche_also_empty():
    """If both are empty, AI failed to identify anything — not a
    multi-company signal. Banner stays hidden; user fills manually."""
    assert fa._aicb_is_multi_company({"company": "", "niche": ""}) is False
    assert fa._aicb_is_multi_company({}) is False
    assert fa._aicb_is_multi_company(None) is False


def test_appstate_has_step2_mode_default_upload():
    """Fresh AppState must initialize aicb_step2_mode = 'upload' so the
    new wizard branches into the Upload UI by default."""
    s = fa.AppState()
    assert s.aicb_step2_mode == "upload"


def test_appstate_step2_mode_in_persisted_fields():
    """A WS reconnect mid-wizard must restore whichever sub-mode the
    user was on (upload vs manual). Otherwise reconnecting mid-manual
    bounces them back to Upload."""
    assert "aicb_step2_mode" in fa._AICB_PERSISTED_FIELDS

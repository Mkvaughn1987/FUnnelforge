"""Regression: p_pdf_gen state init must be resilient to partial _pdf_* state.

Bug (2026-07-16): the email editor's "Create Your Own (15+)" button
(_open_custom_pdf) sets s._pdf_company (and a few siblings) WITHOUT setting
the newer s._pdf_website. p_pdf_gen's init was all-or-nothing —
`if not hasattr(s, '_pdf_company')` — so once _pdf_company existed the whole
block was skipped and the PDF form crashed reading s._pdf_website:
    AttributeError: 'AppState' object has no attribute '_pdf_website'
_ensure_pdf_state() must initialize each attribute independently.
"""
import flowdrip_app as fa


class _FakeState:
    """Minimal stand-in — _ensure_pdf_state only uses hasattr/setattr."""
    pass


def test_ensure_pdf_state_fills_missing_website_when_company_preset():
    # Reproduces the email-editor path: _pdf_company set, _pdf_website absent.
    s = _FakeState()
    s._pdf_company = "Acme"
    fa._ensure_pdf_state(s)
    assert s._pdf_website == ""       # previously missing -> AttributeError
    assert s._pdf_company == "Acme"   # preserved, not clobbered


def test_ensure_pdf_state_sets_all_defaults_on_blank():
    s = _FakeState()
    fa._ensure_pdf_state(s)
    assert s._pdf_company == ""
    assert s._pdf_role == ""
    assert s._pdf_location == ""
    assert s._pdf_industry == ""
    assert s._pdf_website == ""
    assert s._pdf_exp_level == ""
    assert s._pdf_generating is False
    assert s._pdf_result == ""


def test_ensure_pdf_state_preserves_existing_values():
    s = _FakeState()
    s._pdf_company = "Acme"
    s._pdf_website = "acme.com"
    s._pdf_generating = True
    fa._ensure_pdf_state(s)
    assert s._pdf_company == "Acme"
    assert s._pdf_website == "acme.com"
    assert s._pdf_generating is True

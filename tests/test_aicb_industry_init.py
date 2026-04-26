"""Regression: a fresh AppState must have aicb_primary_industry and
aicb_secondary_industries available without AttributeError. The page
render reads them unconditionally; before this fix, a brand-new wizard
session crashed the entire AI Campaign page when the user picked a
target type (Company/Market) on step 1 — server log showed:

  AttributeError: 'AppState' object has no attribute 'aicb_primary_industry'
  File "flowdrip_app.py", line 26575, in p_ai_campaign
      _new_pkey = _industry_key_for_label_or_key(s.aicb_primary_industry or "")
"""


def test_appstate_init_has_industry_picker_fields(isolated_appdata, with_user):
    import flowdrip_app as fa
    s = fa.AppState()
    # Must exist as attributes (not just lazy-init in render)
    assert hasattr(s, "aicb_primary_industry"), (
        "AppState must initialize aicb_primary_industry — page render "
        "reads this unconditionally and crashed on fresh sessions."
    )
    assert hasattr(s, "aicb_secondary_industries")
    # Defaults must be falsy/empty so the existing 'or ""' / 'or []'
    # patterns at the read site degrade cleanly.
    assert not s.aicb_primary_industry
    assert s.aicb_secondary_industries == []


def test_industry_read_uses_getattr_guard():
    """Belt-and-suspenders: the read site at line ~26575 must use
    getattr() rather than direct attribute access. AppState init is the
    primary defense; this static check ensures we don't regress if a
    future refactor removes the init field."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parent.parent / "flowdrip_app.py"
    text = src.read_text(encoding="utf-8")
    # The exact unsafe pattern that crashed the page:
    bad = "_industry_key_for_label_or_key(s.aicb_primary_industry"
    assert bad not in text, (
        f"Direct read of s.aicb_primary_industry at the industry-picker "
        f"sync site is unsafe — use getattr(s, 'aicb_primary_industry', '')"
    )

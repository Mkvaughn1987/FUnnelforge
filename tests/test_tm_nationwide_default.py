"""ThriveModal locations default to USA (offshore staff serve any US
company); Arena keeps whatever was found."""
import inspect
import flowdrip_app as fa


def test_default_locations_usa_on_thrivemodal(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda *a, **k: True)
    assert fa._TM_NATIONWIDE == "USA"
    assert fa._default_locations(["Ontario, CA"]) == ["USA"]
    assert fa._default_locations([]) == ["USA"]
    assert fa._tm_default_location() == "USA"


def test_default_locations_untouched_elsewhere(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda *a, **k: False)
    assert fa._default_locations(["Denver, CO"]) == ["Denver, CO"]
    assert fa._default_locations([]) == []
    assert fa._tm_default_location() == ""


def test_nationwide_words_mean_national_wage():
    for w in ("USA", "Nationwide", "Nationwide US", "United States", "US",
              "anywhere in the United States"):
        assert fa._is_nationwide(w), w
    assert not fa._is_nationwide("Chicago, IL")
    src = inspect.getsource(fa._tm_lookup_local_salary)
    assert "if _is_nationwide(location):" in src


def test_every_autofill_site_goes_through_the_default():
    src = inspect.getsource(fa)
    assert src.count("_default_locations(") >= 7   # def + 6 auto-fill sites
    assert '_pre_region = (_TM_NATIONWIDE if _tm_nationwide()' in src
    assert "across the U.S.' if _is_nationwide(region)" in src


def test_single_value_location_fields_start_as_usa():
    """Sales Assets form (fresh, after Clear, and from the email editor's
    Create Your Own), the Market Watch picker and the newsletter API."""
    src = inspect.getsource(fa.p_pdf_gen)
    assert "if not s._pdf_location:\n        s._pdf_location = _tm_default_location()" in src
    assert 's._pdf_location = _tm_default_location()' in src   # Clear button
    assert 'placeholder=(_TM_NATIONWIDE if _tm_nationwide() else "City, State")' in src
    whole = inspect.getsource(fa)
    assert "s._pdf_location = _pl or _tm_default_location()" in whole
    assert whole.count("s.mi_w_location = _tm_default_location()") == 2
    assert 'or "Nationwide"' not in whole
    assert "or _TM_NATIONWIDE" in whole   # newsletter API region default


def test_region_picker_does_not_tag_usa_as_custom():
    src = inspect.getsource(fa._render_region_picker)
    assert '_lbl = v if v == _TM_NATIONWIDE else f"{v} (custom)"' in src

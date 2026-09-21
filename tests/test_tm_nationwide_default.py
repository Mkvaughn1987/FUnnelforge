"""ThriveModal locations default to Nationwide (offshore roles); Arena keeps
whatever was found."""
import inspect
import flowdrip_app as fa


def test_default_locations_nationwide_on_thrivemodal(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda *a, **k: True)
    assert fa._default_locations(["Ontario, CA"]) == ["Nationwide"]
    assert fa._default_locations([]) == ["Nationwide"]


def test_default_locations_untouched_elsewhere(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda *a, **k: False)
    assert fa._default_locations(["Denver, CO"]) == ["Denver, CO"]
    assert fa._default_locations([]) == []


def test_nationwide_words_mean_national_wage():
    for w in ("Nationwide", "United States", "US", "anywhere in the United States"):
        assert fa._is_nationwide(w), w
    assert not fa._is_nationwide("Chicago, IL")
    src = inspect.getsource(fa._tm_lookup_local_salary)
    assert "if _is_nationwide(location):" in src


def test_every_autofill_site_goes_through_the_default():
    src = inspect.getsource(fa)
    assert src.count("_default_locations(") >= 7   # def + 6 auto-fill sites
    assert '_pre_region = (_TM_NATIONWIDE if _tm_nationwide()' in src
    assert "across the U.S.' if _is_nationwide(region)" in src

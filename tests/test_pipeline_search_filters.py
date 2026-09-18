"""Pipeline search filter bar: location + radius, added-within, pipeline scope.

Covers the ats.py side of the upgraded Pipeline search — `_geo_filter`,
`_added_since`, and the new `location` / `radius_mi` / `added_within_days`
arguments on `keyword_search` and `jd_search`.

Most tests set candidate lat/lng explicitly and stub the origin geocode, so
they don't depend on `us_geo.csv` (a prod data file that lives in
DRIPDROP_DATA_DIR and is not in the repo). The one test that exercises real
city-level geocoding skips itself when that dataset isn't present.
"""
import sqlite3
import sys
import time

import pytest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS talents (
  id INTEGER PRIMARY KEY,
  first_name TEXT, last_name TEXT, email TEXT, phone TEXT,
  city TEXT, state TEXT, current_title TEXT, current_employer TEXT,
  years_experience TEXT, seniority TEXT, skills TEXT, summary TEXT,
  status TEXT DEFAULT 'Candidate', source_file TEXT, resume_text TEXT,
  added_by TEXT, created_at TEXT, updated_at TEXT,
  owner_email TEXT DEFAULT '', notes TEXT DEFAULT '', work_history TEXT DEFAULT '',
  lat REAL, lng REAL
);
CREATE VIRTUAL TABLE IF NOT EXISTS talents_fts USING fts5(
  first_name, last_name, current_title, current_employer, skills,
  summary, city, state, resume_text, content='talents', content_rowid='id'
);
"""

# A stand-in origin; candidates below are placed at known offsets from it.
_ORIGIN = (33.7357, -117.7672)          # Irvine, CA
_NEAR = (33.7455, -117.8677)            # Santa Ana, CA   ~5 mi
_MID = (34.0522, -118.2437)             # Los Angeles, CA ~32 mi
_FAR = (32.7157, -117.1611)             # San Diego, CA   ~79 mi


def _ago(days):
    return time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(time.time() - days * 86400))


@pytest.fixture
def ats_mod(tmp_path, monkeypatch):
    db = tmp_path / "ats.db"
    con = sqlite3.connect(str(db))
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    monkeypatch.setenv("ATS_DB_PATH", str(db))
    if "ats" in sys.modules:
        del sys.modules["ats"]
    import ats
    return ats


def _seed(ats, name, city, state, coords, days_ago=0, owner="mike@arenastaffing.net",
          title="Project Manager", skills="OSHA, scheduling"):
    """Insert one candidate into talents + the external-content FTS index."""
    con = sqlite3.connect(str(ats._db_path()))
    lat, lng = (coords if coords else (None, None))
    cur = con.execute(
        "INSERT INTO talents(first_name,last_name,city,state,current_title,"
        "current_employer,skills,summary,resume_text,owner_email,created_at,"
        "updated_at,lat,lng) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, "Test", city, state, title, "Acme", skills, "Summary.",
         f"{title} resume text", owner, _ago(days_ago), _ago(days_ago), lat, lng))
    rid = cur.lastrowid
    con.execute(
        "INSERT INTO talents_fts(rowid,first_name,last_name,current_title,"
        "current_employer,skills,summary,city,state,resume_text) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (rid, name, "Test", title, "Acme", skills, "Summary.", city, state,
         f"{title} resume text"))
    con.commit()
    con.close()
    return rid


def _names(rows):
    return sorted(r["first_name"] for r in rows)


# ── _added_since ──────────────────────────────────────────────────────────
def test_added_since_returns_none_without_days(ats_mod):
    assert ats_mod._added_since(None) is None
    assert ats_mod._added_since(0) is None


def test_added_since_matches_created_at_format(ats_mod):
    got = ats_mod._added_since(30)
    # Must be lexicographically comparable with talents.created_at.
    time.strptime(got, "%Y-%m-%dT%H:%M:%S")
    assert ats_mod._added_since(30) < ats_mod._added_since(7)


# ── _geo_filter ───────────────────────────────────────────────────────────
def test_geo_filter_without_origin_is_a_passthrough(ats_mod):
    rows = [{"city": "Irvine", "state": "CA"}]
    out, hidden = ats_mod._geo_filter(rows, None, 25)
    assert out == rows and hidden == 0
    assert "_distance_mi" not in rows[0]


def test_geo_filter_annotates_but_keeps_all_when_no_radius(ats_mod):
    rows = [{"lat": _NEAR[0], "lng": _NEAR[1]}, {"lat": _FAR[0], "lng": _FAR[1]}]
    out, hidden = ats_mod._geo_filter(rows, _ORIGIN, None)
    assert len(out) == 2 and hidden == 0
    assert out[0]["_distance_mi"] < out[1]["_distance_mi"]


def test_geo_filter_drops_outside_radius(ats_mod):
    rows = [{"lat": _NEAR[0], "lng": _NEAR[1]}, {"lat": _MID[0], "lng": _MID[1]},
            {"lat": _FAR[0], "lng": _FAR[1]}]
    out, hidden = ats_mod._geo_filter(rows, _ORIGIN, 25)
    assert len(out) == 1 and hidden == 0
    out50, _ = ats_mod._geo_filter(
        [{"lat": _NEAR[0], "lng": _NEAR[1]}, {"lat": _MID[0], "lng": _MID[1]},
         {"lat": _FAR[0], "lng": _FAR[1]}], _ORIGIN, 50)
    assert len(out50) == 2


def test_geo_filter_counts_unlocatable_separately_from_out_of_range(ats_mod):
    """A candidate with no usable location is *hidden*, not 'far away' — the
    UI reports that count so the pool doesn't just look empty."""
    rows = [{"lat": _NEAR[0], "lng": _NEAR[1]},
            {"lat": _FAR[0], "lng": _FAR[1]},
            {"lat": None, "lng": None, "city": "", "state": ""}]
    out, hidden = ats_mod._geo_filter(rows, _ORIGIN, 25)
    assert len(out) == 1
    assert hidden == 1


# ── keyword_search ────────────────────────────────────────────────────────
def test_keyword_search_still_returns_a_plain_list_by_default(ats_mod):
    """Existing callers (pipelines, the MCP search route) pass no new args and
    must keep getting a bare list back."""
    _seed(ats_mod, "Alice", "Irvine", "CA", _NEAR)
    out = ats_mod.keyword_search("project manager")
    assert isinstance(out, list)
    assert _names(out) == ["Alice"]


def test_keyword_search_with_meta_returns_tuple(ats_mod):
    _seed(ats_mod, "Alice", "Irvine", "CA", _NEAR)
    rows, meta = ats_mod.keyword_search("project manager", with_meta=True)
    assert _names(rows) == ["Alice"]
    assert meta["hidden_no_location"] == 0
    assert meta["bad_location"] == ""


def test_keyword_search_radius_narrows_results(ats_mod, monkeypatch):
    monkeypatch.setattr(ats_mod, "geocode_text", lambda s: _ORIGIN)
    _seed(ats_mod, "Near", "Santa Ana", "CA", _NEAR)
    _seed(ats_mod, "Mid", "Los Angeles", "CA", _MID)
    _seed(ats_mod, "Far", "San Diego", "CA", _FAR)

    assert _names(ats_mod.keyword_search(
        "project manager", location="Irvine, CA", radius_mi=25)) == ["Near"]
    assert _names(ats_mod.keyword_search(
        "project manager", location="Irvine, CA", radius_mi=50)) == ["Mid", "Near"]
    # No radius => location only annotates distance, nothing is dropped.
    assert _names(ats_mod.keyword_search(
        "project manager", location="Irvine, CA")) == ["Far", "Mid", "Near"]


def test_keyword_search_unlocatable_candidate_is_reported_not_silently_dropped(
        ats_mod, monkeypatch):
    monkeypatch.setattr(ats_mod, "geocode_text", lambda s: _ORIGIN)
    _seed(ats_mod, "Near", "Santa Ana", "CA", _NEAR)
    _seed(ats_mod, "Nowhere", "", "", None)
    rows, meta = ats_mod.keyword_search(
        "project manager", location="Irvine, CA", radius_mi=25, with_meta=True)
    assert _names(rows) == ["Near"]
    assert meta["hidden_no_location"] == 1


def test_keyword_search_ungeocodable_location_warns_instead_of_filtering(ats_mod):
    """A bare city can't be geocoded. Returning nothing would look like an
    empty pool, so we return everything and flag the bad input."""
    _seed(ats_mod, "Near", "Santa Ana", "CA", _NEAR)
    _seed(ats_mod, "Far", "San Diego", "CA", _FAR)
    rows, meta = ats_mod.keyword_search(
        "project manager", location="Irvine", radius_mi=25, with_meta=True)
    assert _names(rows) == ["Far", "Near"]
    assert meta["bad_location"] == "Irvine"
    assert meta["origin"] is None


def test_keyword_search_added_within_days_excludes_older_rows(ats_mod):
    _seed(ats_mod, "Fresh", "Irvine", "CA", _NEAR, days_ago=3)
    _seed(ats_mod, "Stale", "Irvine", "CA", _NEAR, days_ago=200)
    assert _names(ats_mod.keyword_search("project manager",
                                         added_within_days=30)) == ["Fresh"]
    assert _names(ats_mod.keyword_search("project manager",
                                         added_within_days=365)) == ["Fresh", "Stale"]
    assert _names(ats_mod.keyword_search("project manager")) == ["Fresh", "Stale"]


def test_keyword_search_owner_scope_still_applies_alongside_new_filters(ats_mod):
    _seed(ats_mod, "Mine", "Irvine", "CA", _NEAR, owner="mike@arenastaffing.net")
    _seed(ats_mod, "Theirs", "Irvine", "CA", _NEAR, owner="liz@arenastaffing.net")
    assert _names(ats_mod.keyword_search("project manager")) == ["Mine", "Theirs"]
    assert _names(ats_mod.keyword_search(
        "project manager", owner="mike@arenastaffing.net",
        added_within_days=30)) == ["Mine"]


def test_keyword_search_filters_apply_before_the_limit_is_taken(ats_mod, monkeypatch):
    """The radius filter runs in Python, so the SQL page has to be widened
    first — otherwise limit=N would return fewer than N in-range candidates."""
    monkeypatch.setattr(ats_mod, "geocode_text", lambda s: _ORIGIN)
    for i in range(20):
        _seed(ats_mod, f"Far{i:02d}", "San Diego", "CA", _FAR)
    for i in range(3):
        _seed(ats_mod, f"Near{i:02d}", "Santa Ana", "CA", _NEAR)
    rows = ats_mod.keyword_search("project manager", limit=5,
                                  location="Irvine, CA", radius_mi=25)
    assert len(rows) == 3
    assert all(r["first_name"].startswith("Near") for r in rows)


# ── jd_search ─────────────────────────────────────────────────────────────
def test_jd_search_explicit_location_overrides_the_parsed_one(ats_mod, monkeypatch):
    """Today a JD with no parseable location silently loses the radius filter.
    An explicit location from the filter bar has to win."""
    monkeypatch.setattr(ats_mod, "jd_extract", lambda t: {
        "title": "Project Manager", "must_have_skills": ["OSHA"],
        "nice_to_have": [], "location": "", "seniority": "Senior"})
    _seed(ats_mod, "Near", "Santa Ana", "CA", _NEAR)
    _seed(ats_mod, "Far", "San Diego", "CA", _FAR)

    crit, rows, terms = ats_mod.jd_search("Need a PM.", location="Irvine, CA",
                                          radius_mi=25)
    assert crit["_origin"] is not None
    assert crit["_location_used"] == "Irvine, CA"
    assert _names(rows) == ["Near"]


def test_jd_search_falls_back_to_parsed_location(ats_mod, monkeypatch):
    monkeypatch.setattr(ats_mod, "jd_extract", lambda t: {
        "title": "Project Manager", "must_have_skills": ["OSHA"],
        "nice_to_have": [], "location": "Irvine, CA", "seniority": "Senior"})
    _seed(ats_mod, "Near", "Santa Ana", "CA", _NEAR)
    _seed(ats_mod, "Far", "San Diego", "CA", _FAR)

    crit, rows, _ = ats_mod.jd_search("Need a PM in Irvine.", radius_mi=25)
    assert crit["_location_used"] == "Irvine, CA"
    assert _names(rows) == ["Near"]


def test_jd_search_flags_an_ungeocodable_override(ats_mod, monkeypatch):
    monkeypatch.setattr(ats_mod, "jd_extract", lambda t: {
        "title": "Project Manager", "must_have_skills": ["OSHA"],
        "nice_to_have": [], "location": "", "seniority": "Senior"})
    _seed(ats_mod, "Near", "Santa Ana", "CA", _NEAR)
    crit, rows, _ = ats_mod.jd_search("Need a PM.", location="Irvine", radius_mi=25)
    assert crit["_bad_location"] == "Irvine"
    assert _names(rows) == ["Near"]          # unfiltered, not empty


def test_jd_search_added_within_days_applies(ats_mod, monkeypatch):
    monkeypatch.setattr(ats_mod, "jd_extract", lambda t: {
        "title": "Project Manager", "must_have_skills": ["OSHA"],
        "nice_to_have": [], "location": "", "seniority": "Senior"})
    _seed(ats_mod, "Fresh", "Irvine", "CA", _NEAR, days_ago=3)
    _seed(ats_mod, "Stale", "Irvine", "CA", _NEAR, days_ago=200)
    _, rows, _ = ats_mod.jd_search("Need a PM.", added_within_days=30)
    assert _names(rows) == ["Fresh"]


# ── real geo dataset (prod parity) ────────────────────────────────────────
def test_real_city_geocoding_discriminates_25_from_50_miles(ats_mod):
    """Guards the assumption the whole radius feature rests on: that city-level
    coordinates are available. Without us_geo.csv every lookup collapses to a
    state centroid and 25mi/50mi become the same filter."""
    if not ats_mod._load_geo():
        pytest.skip("us_geo.csv not present (prod data file, not in the repo)")
    origin = ats_mod.geocode_text("Irvine, CA")
    d_near = ats_mod.candidate_distance({"city": "Santa Ana", "state": "CA"}, origin)
    d_mid = ats_mod.candidate_distance({"city": "Los Angeles", "state": "CA"}, origin)
    d_far = ats_mod.candidate_distance({"city": "San Diego", "state": "CA"}, origin)
    assert d_near < 25 < d_mid < 50 < d_far

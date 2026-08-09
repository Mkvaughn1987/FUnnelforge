"""Unit tests for _aicb_ats_candidate_bullets (flowdrip_app.py:34059),
the bullet-line builder for the ATS/Pipeline candidate-source picker.

Mirrors _aicb_pool_candidate_bullets but adapted to the ats.py talents
schema (current_title/city/state/summary -- no target_role or salary
field), so it must never emit a salary bullet and must tolerate any
subset of missing fields the way keyword_search() rows can arrive.
"""


FULL_RECORD = {
    "id": 42,
    "name": "Jordan Reyes",
    "current_title": "CNC Machinist",
    "city": "Grand Rapids",
    "state": "MI",
    "summary": "10+ years of precision milling and GD&T experience. Led "
               "tooling upgrades at two plants.",
}


def test_bullets_full_record(isolated_appdata, with_user):
    import flowdrip_app as fa
    bullets = fa._aicb_ats_candidate_bullets(FULL_RECORD)
    assert bullets == [
        "Location: Grand Rapids, MI",
        "Target role: CNC Machinist",
        "10+ years of precision milling and GD&T experience",
    ]


def test_bullets_missing_city_and_state_omits_location(isolated_appdata, with_user):
    import flowdrip_app as fa
    cand = dict(FULL_RECORD)
    cand["city"] = ""
    cand["state"] = ""
    bullets = fa._aicb_ats_candidate_bullets(cand)
    assert not any(b.startswith("Location:") for b in bullets)
    assert bullets == [
        "Target role: CNC Machinist",
        "10+ years of precision milling and GD&T experience",
    ]


def test_bullets_city_only_still_forms_location(isolated_appdata, with_user):
    import flowdrip_app as fa
    cand = dict(FULL_RECORD)
    cand["state"] = ""
    bullets = fa._aicb_ats_candidate_bullets(cand)
    assert bullets[0] == "Location: Grand Rapids"


def test_bullets_state_only_still_forms_location(isolated_appdata, with_user):
    import flowdrip_app as fa
    cand = dict(FULL_RECORD)
    cand["city"] = ""
    bullets = fa._aicb_ats_candidate_bullets(cand)
    assert bullets[0] == "Location: MI"


def test_bullets_missing_current_title_omits_role_bullet(isolated_appdata, with_user):
    import flowdrip_app as fa
    cand = dict(FULL_RECORD)
    cand["current_title"] = ""
    bullets = fa._aicb_ats_candidate_bullets(cand)
    assert not any(b.startswith("Target role:") for b in bullets)


def test_bullets_missing_summary_omits_third_bullet(isolated_appdata, with_user):
    import flowdrip_app as fa
    cand = dict(FULL_RECORD)
    cand["summary"] = ""
    bullets = fa._aicb_ats_candidate_bullets(cand)
    assert bullets == [
        "Location: Grand Rapids, MI",
        "Target role: CNC Machinist",
    ]


def test_bullets_summary_trimmed_to_first_sentence_and_140_chars(isolated_appdata, with_user):
    import flowdrip_app as fa
    cand = dict(FULL_RECORD)
    cand["summary"] = "x" * 200 + ". second sentence."
    bullets = fa._aicb_ats_candidate_bullets(cand)
    assert bullets[-1] == "x" * 140


def test_bullets_never_emits_salary(isolated_appdata, with_user):
    """The ATS schema has no target-salary field the way the Top
    Candidates pool does -- a stray 'salary' key on the row (e.g. from
    a future schema change or a caller reusing a pool-shaped dict)
    must not leak a salary bullet."""
    import flowdrip_app as fa
    cand = dict(FULL_RECORD)
    cand["salary"] = "$95,000"
    bullets = fa._aicb_ats_candidate_bullets(cand)
    assert not any("salary" in b.lower() or "$95,000" in b for b in bullets)


def test_bullets_empty_record_returns_empty_list(isolated_appdata, with_user):
    import flowdrip_app as fa
    assert fa._aicb_ats_candidate_bullets({}) == []


def test_bullets_none_valued_fields_treated_as_missing(isolated_appdata, with_user):
    import flowdrip_app as fa
    cand = {
        "current_title": None,
        "city": None,
        "state": None,
        "summary": None,
    }
    assert fa._aicb_ats_candidate_bullets(cand) == []

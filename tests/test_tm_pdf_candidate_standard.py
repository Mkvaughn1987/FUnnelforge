"""Mike, 2026-11-05: "These PDFs are too simple... I want them to think we
are experts in the industry... each pdf at the top to include all of our
candidates are properly vetted, English and certified and degreed".

Every ThriveModal PDF opens with the candidate standard, the prompts ask for
industry depth, and the cost sheet prices each role at three experience
levels. Arena's PDFs are untouched.
"""
import json

import flowdrip_app as fa

CTX = {"company": "Acme Freight", "primary_industry": "Logistics",
       "positions": "Dispatcher", "location": "Houston, TX"}
TM_KINDS = ("tm_role_blueprint", "tm_how_it_works", "tm_myths", "tm_roles_map",
            "tm_first_90", "tm_security", "market_pulse")


def _tm(monkeypatch, on=True):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: on)


class _Msg:
    content = [type("T", (), {"type": "text", "text": json.dumps({
        "title": "t", "intro": "i", "cta": "c",
        "sections": [{"heading": "Overview", "type": "bullets",
                      "items": ["One.", "Two."]}]})})()]


def test_the_standard_says_vetted_english_degreed_and_certified():
    box = fa._tm_candidate_standard()
    assert box["type"] == "callout" and box["keep"]
    text = " ".join(box["items"])
    for word in ("Fully vetted", "Fluent, professional English",
                 "Degreed and certified", "video pre-screen"):
        assert word in text, word
    # Never a claim the playbook forbids.
    for word in ("native", "perfect", "background check", "Filipino"):
        assert word not in text, word
    assert "every Dispatcher candidate holds" in " ".join(
        fa._tm_candidate_standard("Dispatcher")["items"])
    # A list of roles is not one seat.
    assert "every candidate holds" in " ".join(
        fa._tm_candidate_standard("Dispatcher, Biller")["items"])


def test_the_standard_is_first_and_never_twice():
    secs = fa._tm_with_standard(
        [{"heading": "A", "type": "bullets", "items": ["x"]},
         fa._tm_candidate_standard()])
    assert [s["type"] for s in secs] == ["callout", "bullets"]
    assert fa._tm_with_standard(secs) == secs
    assert fa._tm_with_standard(None)[0]["type"] == "callout"


def test_every_tm_pdf_opens_with_the_standard(monkeypatch):
    _tm(monkeypatch)
    monkeypatch.setattr(fa, "_claude_create_with_retry", lambda c, **kw: _Msg())
    for kind in TM_KINDS:
        d = fa._generate_rich_pdf_data(None, kind, dict(CTX))
        assert d["sections"][0]["heading"] == fa._TM_STANDARD_HEADING, kind
        assert [s["type"] for s in d["sections"]].count("callout") == 1, kind
        assert d["sections"][1]["heading"] == "Overview", kind


def test_arena_pdfs_get_no_standard(monkeypatch):
    _tm(monkeypatch, on=False)
    monkeypatch.setattr(fa, "_claude_create_with_retry", lambda c, **kw: _Msg())
    d = fa._generate_rich_pdf_data(None, "market_pulse", dict(CTX))
    assert all(s["type"] != "callout" for s in d["sections"])


def test_single_role_cost_sheet_opens_with_the_standard():
    d = fa._tm_auto_cost_pdf_data("Acme", "Bookkeeper", "", None)
    assert d["sections"][0]["type"] == "callout"
    # No salary: a note to the seller, with nothing to sell on it.
    d = fa._tm_auto_cost_pdf_data("Acme", "Superintendent", "", None)
    assert d["sections"] == []


def test_every_tm_prompt_asks_for_industry_depth_and_two_pages(monkeypatch):
    _tm(monkeypatch)
    for kind in TM_KINDS:
        p = fa._rich_pdf_prompt(kind, dict(CTX))
        assert fa._TM_PDF_DEPTH_RULES in p, kind
        assert p.endswith(fa._PDF_LENGTH_RULES), kind
        assert "one-pager" not in p.split("THRIVEMODAL PLAYBOOK")[0], kind
        assert "max 20 words" not in p and "max 24 words" not in p, kind
    rules = fa._TM_PDF_DEPTH_RULES
    for word in ("INDUSTRY DEPTH", "OUR CANDIDATE STANDARD",
                 "fluent, professional English", "degree", "certifications",
                 "name the category instead of guessing"):
        assert word in rules, word
    # The standard never widens into what the playbook forbids.
    assert "Never 'native' or 'perfect'" in rules
    assert "does not license a background-check claim" in rules


def test_arena_prompts_carry_no_depth_rules(monkeypatch):
    _tm(monkeypatch, on=False)
    p = fa._rich_pdf_prompt("market_pulse", dict(CTX))
    assert fa._TM_PDF_DEPTH_RULES not in p
    assert "OUR CANDIDATE STANDARD" not in p


def test_blueprint_names_the_degree_certification_and_software(monkeypatch):
    _tm(monkeypatch)
    p = fa._rich_pdf_prompt("tm_role_blueprint", dict(CTX))
    assert "'Candidate Profile'" in p and "'Core Responsibilities'" in p
    assert "Degree; Certifications; Experience; Software" in p
    assert "write the category instead of guessing" in p


def test_how_we_work_explains_the_vetting(monkeypatch):
    _tm(monkeypatch)
    p = fa._rich_pdf_prompt("tm_how_it_works", dict(CTX))
    assert "'How Every Candidate Is Vetted'" in p
    assert "['Stage','What Happens','Owner','What You Receive']" in p.replace("\n", "")
    assert "Do NOT add a duration column" in p


def test_role_profiles_cover_every_role_the_cost_sheet_can_name():
    import tm_prompts
    names = {r.lower() for roles in fa._TM_VERTICAL_COST_ROLES.values()
             for r in roles} | {r.lower() for r in fa._TM_STAFFING_COST_ROLES}
    # ...and every title the Sales Assets Jobs drop-down offers.
    names |= {t.lower() for row in tm_prompts.INDUSTRY_JOBS for t in row[-1]}
    assert names <= set(fa._TM_ROLE_PROFILES), names - set(fa._TM_ROLE_PROFILES)
    for role, cells in fa._TM_ROLE_PROFILES.items():
        assert len(cells) == 3 and all(c.strip() for c in cells), role
        # Degrees and credentials, never a compliance claim of ours.
        assert not any(w in " ".join(cells) for w in ("SOC 2", "ISO 27001",
                                                      "HIPAA")), role
    assert fa._tm_role_profile_rows(["Zookeeper"]) == []
    rows = fa._tm_role_profile_rows(["Estimator", "Zookeeper"])
    assert [r[0] for r in rows] == ["Role", "Estimator"]


def test_cost_sheet_uses_one_mid_range_rate_per_role(monkeypatch):
    """Mike, 2026-11-05: "Dont worry about years of experience anymore. Use
    the mid range for money"."""
    def local(client, roles, location):
        return {r: {"salary": 60000.0, "basis": "median",
                    "area": "United States",
                    "occupation": f"Occ {i} (SOC 11-111{i})",
                    "source": "BLS OEWS May 2025", "url": "https://www.bls.gov/x"}
                for i, r in enumerate(roles)}
    monkeypatch.setattr(fa, "_tm_bls_local_salaries", local)
    _tm(monkeypatch)
    d = fa._tm_multi_cost_pdf_data(None, "Acme", "Bookkeeper", "", "Accounting")
    p = d["_worksheet"][0]
    assert "bands" not in p and p["base"] == 60000.0
    assert abs(p["tm"] / p["domestic"] - 0.35) < 0.01
    how = " ".join(next(s for s in d["sections"]
                        if s["heading"] == "Basis of Calculation")["items"])
    assert "BLS median wage" in how and "percentile" not in how


def test_bls_lookup_asks_for_the_median_only(monkeypatch):
    asked = []

    def medians(ids):
        asked.append(list(ids))
        return {sid: (61000.0, "2025") for sid in ids if sid.startswith("OEUN")}
    monkeypatch.setattr(fa, "_tm_bls_annual_medians", medians)
    lk = fa._tm_bls_local_salaries(None, ["Bookkeeper"], "")["Bookkeeper"]
    assert lk["salary"] == 61000.0 and set(lk) >= {"area", "occupation", "url"}
    assert "_series" not in lk and "p25" not in lk
    assert len(asked) == 1 and all(s.endswith("13") for s in asked[0])


def test_every_saved_role_sells_skills_software_and_credentials():
    """The titles the Jobs drop-down and the cost sheet name are the ones
    that matter most: each has a degree, a full skill list and software."""
    import tm_prompts
    names = {t.lower() for row in tm_prompts.INDUSTRY_JOBS for t in row[-1]}
    for name in sorted(names):
        creds, skills, software = fa._TM_ROLE_PROFILES[name]
        assert creds.startswith(("Bachelor", "BS ")), name
        assert len(skills.split(",")) >= 5, (name, skills)
        assert 2 <= len(software.split(",")) <= 5, (name, software)
        assert len(skills) <= 135 and len(software) <= 62, name


def test_work_attributes_are_approved_service_terms():
    items = fa._tm_work_attributes_section()["items"]
    text = " ".join(items)
    for word in ("any U.S. time zone", "full-time", "Dedicated to your business",
                 "fluent, professional English", "Reports to your manager",
                 "workstation and IT"):
        assert word in text, word
    for word in ("native", "perfect", "24/7", "Filipino"):
        assert word not in text, word


def test_create_your_own_pdf_gets_the_standard_and_depth():
    import inspect
    src = inspect.getsource(fa._custom_pdf_build)
    assert "_TM_PDF_DEPTH_RULES" in src and "_tm_with_standard(" in src
    out = inspect.getsource(fa._custom_pdf_outline)
    assert "The PDF runs to two pages" in out
    assert "must fit in 1.5 pages" not in out


def test_core_tables_are_never_trimmed(monkeypatch):
    """First live build, 2026-11-05: the two-page trim cut the Engagement
    Process to three stages and the 90-Day Plan to week four."""
    _tm(monkeypatch)
    data = {"sections": [
        {"heading": "Engagement Process", "type": "table", "items": [["a"]] * 7},
        {"heading": "90-Day Plan", "type": "table", "items": [["a"]] * 6},
        {"heading": "Role Data Access", "type": "table", "items": [["a"]] * 5},
        {"heading": "Engagement Process", "type": "bullets", "items": ["x"]}]}
    fa._tm_keep_core_tables(data)
    assert [bool(s.get("keep")) for s in data["sections"]] == [
        True, True, False, False]

    class _Long:
        content = [type("T", (), {"type": "text", "text": json.dumps({
            "title": "t", "intro": "i", "cta": "c", "sections": [
                {"heading": "Engagement Process", "type": "table",
                 "items": [["Stage", "What Happens", "Owner", "What You Receive"]]
                 + [["Stage", "We do the thing", "Shared", "A document"]] * 6}]})})()]
    monkeypatch.setattr(fa, "_claude_create_with_retry", lambda c, **kw: _Long())
    d = fa._generate_rich_pdf_data(None, "tm_how_it_works", dict(CTX))
    table = next(s for s in d["sections"] if s["type"] == "table")
    assert table["keep"] and len(table["items"]) == 7


def test_length_rules_keep_the_writing_inside_two_pages():
    r = fa._PDF_LENGTH_RULES
    assert "28 words or fewer" in r and "12 words or fewer" in r
    assert "at most 3 pairs" in r and "never past them" in r


def test_a_typed_title_finds_its_profile_by_keyword():
    assert fa._tm_role_profile("Architect")[2].startswith("Revit")
    assert fa._tm_role_profile("Senior Estimator") == fa._TM_ROLE_PROFILES["estimator"]
    assert fa._tm_role_profile("BIM Manager")[1].startswith("BIM models")
    assert fa._tm_role_profile("CPA") == fa._TM_ROLE_PROFILES["staff accountant"]
    # The longest keyword wins: an executive assistant is not "administrative".
    assert (fa._tm_role_profile("Executive Assistant")
            == fa._TM_ROLE_PROFILES["executive assistant"])
    assert fa._tm_role_profile("Zookeeper") is None
    for kw, val in fa._TM_ROLE_PROFILE_ALIASES:
        assert isinstance(val, tuple) or val in fa._TM_ROLE_PROFILES, kw
    rows = fa._tm_role_profile_rows(["Architect", "Zookeeper"])
    assert [r[0] for r in rows] == ["Role", "Architect"]

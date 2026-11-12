"""contact_recommend: pure ranking of Arena Sales Contacts for candidates."""
import contact_recommend as cr


def _row(company, industry, state, contacts, key=None, replied=0):
    return {"company": company, "key": key or company.lower(), "industry": industry,
            "state": state, "contacts": contacts, "replied": replied}


def _c(name, title, city="", replied=""):
    return {"name": name, "title": title, "city": city, "replied": replied}


SUPER = {"label": "Pat S. (Ref #7)", "title": "Senior Superintendent",
         "skills": "commercial construction", "city": "Denver", "state": "Colorado",
         "employer": "Hensel Phelps"}


def test_industry_from_text():
    assert cr.industry_of_text("HVAC Project Manager") == "Mechanical Contracting"
    assert cr.industry_of_text("Staff Accountant", "CPA") == "Accounting & Finance"


def test_ranks_industry_and_state_then_picks_the_decision_maker():
    rows = [
        _row("Far GC", "General Contracting", "TX", [_c("A", "Project Manager")]),
        _row("Near GC", "General Contracting", "CO",
             [_c("B", "Office Manager"), _c("C", "VP Construction", city="Denver")]),
        _row("Bank", "Accounting & Finance", "CO", [_c("D", "Controller")]),
    ]
    out = cr.recommend(rows, [SUPER])
    names = [r["company"] for r in out["recommendations"]]
    assert names[0] == "Near GC"
    assert out["recommendations"][0]["people"][0]["contact"]["name"] == "C"
    assert "contact in the same city" in out["recommendations"][0]["why"]


def test_never_pitches_the_candidate_to_their_own_employer():
    rows = [_row("Hensel Phelps Construction Co", "General Contracting", "CO",
                 [_c("E", "President")])]
    assert cr.recommend(rows, [SUPER])["recommendations"] == []


def test_skip_and_flags_and_filters():
    rows = [_row("One", "General Contracting", "CO", [_c("A", "Owner")], key="one.com"),
            _row("Two", "General Contracting", "CO", [_c("B", "Owner")], key="two.com"),
            _row("Three", "General Contracting", "UT", [_c("C", "Owner")], key="three.com")]
    out = cr.recommend(rows, [SUPER], skip={"one.com"},
                       flags={"two.com": ["Current Client"]}, state="CO")
    assert [r["company"] for r in out["recommendations"]] == ["Two"]
    assert out["recommendations"][0]["flags"] == ["Current Client"]
    assert out["skipped_worked_recently"] == 1


def test_several_candidates_report_who_fits():
    acct = {"label": "Acct", "title": "Senior Accountant", "skills": "CPA", "state": "NY"}
    rows = [_row("Bank", "Accounting & Finance", "NY", [_c("D", "CFO")])]
    rec = cr.recommend(rows, [SUPER, acct])["recommendations"][0]
    assert rec["best_fit"] == "Acct" and rec["fits"] == ["Acct"]

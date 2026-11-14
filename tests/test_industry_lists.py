"""Sales instances file every company under an industry as it is added
(Upload CSV, Add One Contact) into a "TM - <Industry>" list that is added
to, never replaced (2026-11-14)."""
import sales_pages as sp


def test_choices_lead_with_target_markets_and_end_with_other():
    ch = sp.industry_choices()
    assert ch[:6] == list(sp.INDUSTRY_PRIORITY)
    assert ch[-1] == sp.INDUSTRY_OTHER
    assert len(ch) == len(set(ch))
    assert "Professional Services & HR" in ch and "Heavy Equipment & Rental" in ch


def test_list_name_follows_industry():
    assert sp.industry_list_name("Logistics & Freight") == "TM - Logistics & Freight"
    assert sp.industry_list_name("") == "TM - Other"


def test_new_headlines_match():
    assert sp.industry_label("Heavy Equipment & Rental") == "Heavy Equipment & Rental"
    assert sp.industry_label("Human Resources") == "Professional Services & HR"
    assert sp.industry_label("Acme HR Partners") == "Professional Services & HR"
    assert sp.industry_label("Wheeler Accountants") == "Accounting & Finance"
    # Existing headlines still win where they matched before.
    assert sp.industry_label("Heavy Civil Contractor") == "Construction"
    assert sp.industry_label("Staffing & Recruiting") == "Staffing & Recruiting"
    assert sp.company_industry("Civil & Engineering", "X") == "Civil & Infrastructure"


def _point_contacts_dir(monkeypatch, tmp_path):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_user_contacts_dir", lambda: tmp_path)
    return fa


def test_file_into_list_adds_tags_and_never_replaces(monkeypatch, tmp_path):
    fa = _point_contacts_dir(monkeypatch, tmp_path)
    a, _ = fa._single_contact_record("Ann", "Lee", "ann@lund.com", "Allen Lund Company")
    path, added, skipped = fa._file_into_industry_list([a], "Logistics & Freight")
    assert path.name == "TM - Logistics & Freight.csv"
    assert (added, skipped) == (1, 0)

    b, _ = fa._single_contact_record("Bob", "Ng", "bob@bridge.com", "Bridge Logistics")
    dupe, _ = fa._single_contact_record("Ann", "Lee", "ANN@lund.com", "Allen Lund Company")
    path, added, skipped = fa._file_into_industry_list([b, dupe], "Logistics & Freight")
    assert (added, skipped) == (1, 1)

    rows = fa.load_contacts(str(path))
    assert [r["email"] for r in rows] == ["ann@lund.com", "bob@bridge.com"]
    assert {r["industry"] for r in rows} == {"Logistics & Freight"}
    # The list it saves is what the Contacts page and Companies page read.
    assert fa.list_saved_contact_lists()["TM - Logistics & Freight"] == str(path)


def test_file_into_list_keeps_a_contacts_own_industry(monkeypatch, tmp_path):
    fa = _point_contacts_dir(monkeypatch, tmp_path)
    c, _ = fa._single_contact_record(email="c@hosp.org", company="City Hospital")
    c["industry"] = "Healthcare"
    path, _, _ = fa._file_into_industry_list([c], "Accounting & Finance")
    assert fa.load_contacts(str(path))[0]["industry"] == "Healthcare"


def test_custom_list_name_is_respected(monkeypatch, tmp_path):
    fa = _point_contacts_dir(monkeypatch, tmp_path)
    c, _ = fa._single_contact_record(email="d@acme.com", company="Acme")
    path, _, _ = fa._file_into_industry_list([c], "Manufacturing", list_name="Denver / Q1 push")
    assert path.name == "Denver  Q1 push.csv"
    assert fa.load_contacts(str(path))[0]["industry"] == "Manufacturing"

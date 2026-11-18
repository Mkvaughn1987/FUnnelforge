"""Contacts page: filter an open list by email / phone, and group saved
lists by industry (2026-11-17)."""
import flowdrip_app as fa


def _c(email="", mob="", office="", li=""):
    return dict(email=email, phone_mobile=mob, phone_office=office, linkedin=li)


def test_filter_match():
    em_only = _c(email="a@x.com")
    mob_only = _c(mob="555")
    office_and_email = _c(email="b@x.com", office="555")
    m = fa._ct_filter_match
    assert m(em_only, "email") and not m(em_only, "phone")
    assert m(mob_only, "mobile") and m(mob_only, "phone") and m(mob_only, "phone_only")
    assert not m(mob_only, "email") and not m(mob_only, "both")
    assert m(office_and_email, "both") and not m(office_and_email, "mobile")
    assert not m(office_and_email, "phone_only")
    assert m(_c(li="in/x"), "linkedin") and not m(em_only, "linkedin")
    assert all(m(c, "all") for c in (em_only, mob_only, office_and_email))


def test_filter_keys_unique():
    keys = [k for k, _l, _x in fa._CT_FILTERS]
    assert keys[0] == "all" and len(keys) == len(set(keys))


def test_list_industry_majority_and_blank(tmp_path):
    p = tmp_path / "Arena - Mechanical Contracting.csv"
    p.write_text("Email,FirstName,Industry\na@x.com,A,Construction\n"
                 "b@x.com,B,Construction\nc@x.com,C,Manufacturing\nd@x.com,D,\n",
                 encoding="utf-8")
    assert fa._list_industry(p) == "Construction"
    q = tmp_path / "plain.csv"
    q.write_text("Email,FirstName\na@x.com,A\n", encoding="utf-8")
    assert fa._list_industry(q) == ""
    assert fa._list_industry(tmp_path / "missing.csv") == ""


def test_unique_list_name():
    assert fa._unique_list_name("X - with mobile", []) == "X - with mobile"
    assert fa._unique_list_name("X - with mobile", ["X_-_with_mobile"]) == "X - with mobile (2)"
    assert fa._unique_list_name("A", ["a", "A (2)"]) == "A (3)"

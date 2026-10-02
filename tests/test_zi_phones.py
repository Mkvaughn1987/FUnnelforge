"""ZoomInfo pulls keep both numbers on file: the mobile and the work line.

Every contact Claude pulls out of ZoomInfo should reach the campaign record
with phone_mobile and phone_office set, whichever spelling the pull used.
"""
import sales_campaign as sc
from zoominfo_pull import ZI_PHONES_RULE, ZI_PULL_RULE


def test_pull_rule_asks_for_both_numbers():
    assert ZI_PHONES_RULE in ZI_PULL_RULE
    for word in ("mobilePhone", "phone_mobile", "phone_office",
                 "DisallowedOutputFields"):
        assert word in ZI_PULL_RULE
    assert "{" not in ZI_PULL_RULE and "}" not in ZI_PULL_RULE


def test_handoff_brief_shows_both_phone_keys():
    brief = sc.handoff_brief({"run_id": "sc_x", "target": {"roles": ["PM"]}})
    assert '"phone_mobile"' in brief and '"phone_office"' in brief
    assert "mobilePhone" in brief          # the shared pull rule rides along


def test_company_row_folds_every_phone_spelling():
    row = sc._norm_company_row({"company": "Acme", "contacts": [
        {"email": "a.b@acme.com", "first_name": "A", "last_name": "Bee",
         "mobilePhone": "(480) 694-5643", "phone": "303-555-1000"},
        {"email": "c.d@acme.com", "first_name": "C", "last_name": "Dee",
         "phone_mobile": "720-555-1", "phone_office": "720-555-2"},
        {"email": "e.f@acme.com", "first_name": "E", "last_name": "Eff",
         "companyPhone": "303-555-9999"},
    ]})
    by = {c["email"]: c for c in row["contacts"]}
    assert by["a.b@acme.com"]["phone_mobile"] == "(480) 694-5643"
    assert by["a.b@acme.com"]["phone_office"] == "303-555-1000"
    assert by["c.d@acme.com"]["phone_mobile"] == "720-555-1"
    assert by["c.d@acme.com"]["phone_office"] == "720-555-2"
    assert by["e.f@acme.com"]["phone_office"] == "303-555-9999"
    assert not by["e.f@acme.com"].get("phone_mobile")


def test_launch_payload_carries_both_numbers():
    p = sc._contact_payload({"email": "a@x.com", "phone_mobile": "1",
                             "phone_office": "2", "person_id": "99"})
    assert p["phone_mobile"] == "1" and p["phone_office"] == "2"
    assert "person_id" not in p


def test_api_contacts_fold_phone_spellings(with_user):
    import flowdrip_app as fa
    c = fa._api_contact_phones({"email": "a@x.com", "mobile": "1",
                                "phone": "2"})
    assert c["phone_mobile"] == "1" and c["phone_office"] == "2"
    # Already-correct keys win over aliases.
    c = fa._api_contact_phones({"email": "a@x.com", "phone_mobile": "9",
                                "mobile": "1"})
    assert c["phone_mobile"] == "9"
    assert fa._api_contact_phones("not a dict") == "not a dict"

"""ZoomInfo pulls keep both numbers on file: the mobile and the work line."""


def test_tm_contacts_step_asks_for_both_numbers():
    import tm_prompts
    step = tm_prompts._CONTACTS_STEP
    for word in ("mobilePhone", "phone_mobile", "phone_office"):
        assert word in step


def test_api_contacts_fold_phone_spellings(with_user):
    import flowdrip_app as fa
    c = fa._api_contact_phones({"email": "a@x.com", "mobile": "1",
                                "phone": "2"})
    assert c["phone_mobile"] == "1" and c["phone_office"] == "2"
    c = fa._api_contact_phones({"email": "a@x.com", "phone_mobile": "9",
                                "mobile": "1"})
    assert c["phone_mobile"] == "9"
    assert fa._api_contact_phones("not a dict") == "not a dict"


def test_contacts_step_falls_back_to_company_main_line():
    import tm_prompts
    step = tm_prompts._CONTACTS_STEP
    assert "main line in phone_office" in step and "company_phone" in step


def test_launch_fills_main_line_and_refuses_blank_numbers(with_user):
    import flowdrip_app as fa
    spec = {"template": "thrive_standard", "company": "Acme"}
    people = [{"email": "a@acme.com", "first_name": "Ann", "last_name": "Lee",
               "phone_mobile": "720-555-1"},
              {"email": "b@acme.com", "first_name": "Bo", "last_name": "Ray"}]
    err = fa._api_require_phones(spec, [dict(c) for c in people])
    assert err and "Bo Ray" in err and "Ann Lee" not in err
    assert "company_phone" in err

    filled = [dict(c) for c in people]
    assert fa._api_require_phones(dict(spec, company_phone="(303) 555-0100"),
                                  filled) is None
    assert filled[0].get("phone_office", "") == ""      # own number kept
    assert filled[1]["phone_office"] == "(303) 555-0100"

    assert fa._api_require_phones(dict(spec, no_phone_ok=True),
                                  [dict(c) for c in people]) is None
    # findcandidates emails candidates, not companies: no call cards.
    assert fa._api_require_phones({"template": "findcandidates"},
                                  [dict(people[1])]) is None

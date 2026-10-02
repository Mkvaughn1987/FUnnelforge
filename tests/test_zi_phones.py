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

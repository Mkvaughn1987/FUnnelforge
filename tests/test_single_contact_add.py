"""Choose Contacts: "Add One Contact" builds one record and appends it."""


def test_record_needs_valid_email():
    import flowdrip_app as fa
    rec, err = fa._single_contact_record(first="Ann")
    assert rec is None and err
    rec, err = fa._single_contact_record(email="not-an-email")
    assert rec is None and err


def test_record_matches_load_contacts_shape():
    import flowdrip_app as fa
    rec, err = fa._single_contact_record(
        " Ann ", "Lee", " ann@acme.com ", "Acme", "Ops Manager", "555-1212")
    assert err == ""
    assert rec["email"] == "ann@acme.com"
    assert rec["first_name"] == "Ann" and rec["last_name"] == "Lee"
    assert rec["company"] == "Acme" and rec["title"] == "Ops Manager"
    assert rec["phone_office"] == "555-1212"
    for k in ("phone_mobile", "linkedin", "city", "state"):
        assert k in rec


def test_append_keeps_existing_and_blocks_duplicates():
    import flowdrip_app as fa
    rec, _ = fa._single_contact_record(email="ann@acme.com")
    existing = [{"email": "bob@acme.com"}]
    new_list, err = fa._append_single_contact(existing, rec)
    assert err == "" and [c["email"] for c in new_list] == ["bob@acme.com", "ann@acme.com"]
    assert existing == [{"email": "bob@acme.com"}]  # not mutated

    dupe, _ = fa._single_contact_record(email="ANN@acme.com")
    same, err = fa._append_single_contact(new_list, dupe)
    assert err and len(same) == 2

    first, err = fa._append_single_contact(None, rec)
    assert err == "" and len(first) == 1

"""Everyone a campaign runs to lands on the Contacts page.

Contacts uploaded in the app were already a saved list; contacts that came
from Claude (create_campaign), Add One Contact or an add to a running
campaign were never written anywhere the page reads.
"""
import inspect

import pytest


# NEVER import flowdrip_app at module level (see tests/conftest.py).

@pytest.fixture
def fa(isolated_appdata, with_user):
    import flowdrip_app as _fa
    return _fa


def _camp(name="Acme Outreach", contacts=None):
    return {"name": name, "contacts": contacts if contacts is not None else [
        {"email": "Jane@Acme.com", "first_name": "Jane", "last_name": "Doe",
         "company": "Acme", "title": "CFO"},
        {"Email": "bob@acme.com", "FirstName": "Bob", "Company": "Acme"},
    ]}


def _list(fa, name):
    path = fa.list_saved_contact_lists()[name]
    return fa._parse_contacts_csv(open(path, encoding="utf-8").read())


def test_new_contacts_go_into_a_list_named_after_the_campaign(fa):
    assert fa._record_campaign_contacts(_camp()) == 2
    assert "Acme Outreach" in fa.list_saved_contact_lists()
    rows = _list(fa, "Acme Outreach")
    assert {r["email"].lower() for r in rows} == {"jane@acme.com", "bob@acme.com"}
    bob = next(r for r in rows if r["email"].lower() == "bob@acme.com")
    assert bob["first_name"] == "Bob" and bob["company"] == "Acme"


def test_contacts_already_in_a_saved_list_are_not_duplicated(fa):
    fa._tm_zi_save_contacts([{"email": "jane@acme.com", "first_name": "Jane"}],
                            "Uploaded list")
    assert fa._record_campaign_contacts(_camp()) == 1
    assert [r["email"] for r in _list(fa, "Acme Outreach")] == ["bob@acme.com"]


def test_a_fully_known_campaign_creates_no_list(fa):
    fa._tm_zi_save_contacts([{"email": "jane@acme.com"}, {"email": "bob@acme.com"}],
                            "Uploaded list")
    assert fa._record_campaign_contacts(_camp()) == 0
    assert "Acme Outreach" not in fa.list_saved_contact_lists()


def test_rerunning_is_a_no_op_and_later_adds_append(fa):
    fa._record_campaign_contacts(_camp())
    assert fa._record_campaign_contacts(_camp()) == 0
    more = _camp(contacts=[{"email": "amy@acme.com", "first_name": "Amy"}])
    assert fa._record_campaign_contacts(more) == 1
    assert len(_list(fa, "Acme Outreach")) == 3


def test_removed_blank_and_bad_emails_are_skipped(fa):
    camp = _camp(contacts=[{"email": "gone@acme.com", "removed": True},
                           {"email": ""}, {"email": "not-an-email"}, "junk"])
    assert fa._record_campaign_contacts(camp) == 0
    assert fa.list_saved_contact_lists() == {}


def test_a_name_with_only_punctuation_still_gets_its_own_list(fa):
    fa._record_campaign_contacts(_camp(name="!!!"))
    assert "Campaign contacts" in fa.list_saved_contact_lists()
    assert not fa._user_contacts_csv_path().exists()


def test_the_queue_records_contacts_before_anything_else_can_skip_them(fa):
    src = inspect.getsource(fa.queue_campaign_emails)
    assert "_record_campaign_contacts(camp)" in src
    assert src.index("_record_campaign_contacts(camp)") < src.index("load_dnc()")

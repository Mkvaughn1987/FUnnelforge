"""Tests for the Enroll Contacts dialog helpers: dedup of incoming
contacts and the upcoming-issue start-month options.

Spec: docs/superpowers/specs/2026-06-03-newsletter-start-after-campaign-and-enroll-design.md
"""
import flowdrip_app as fa


def test_filter_drops_already_enrolled_and_blank_emails():
    camp = {"contacts": [{"email": "a@x.com"}]}
    incoming = [
        {"email": "A@X.com", "first_name": "Dup"},   # already enrolled (case-insensitive)
        {"email": "", "first_name": "Blank"},         # no email
        {"email": "  b@x.com  ", "first_name": "New"},  # new (whitespace trimmed for match)
    ]
    out = fa._filter_new_enrollees(camp, incoming)
    emails = [c["email"] for c in out]
    assert emails == ["  b@x.com  "]  # original dict kept, not mutated


def test_filter_dedups_within_incoming_batch():
    camp = {"contacts": []}
    incoming = [
        {"email": "c@x.com"},
        {"email": "C@X.com"},  # duplicate within the same upload
    ]
    out = fa._filter_new_enrollees(camp, incoming)
    assert len(out) == 1


def test_filter_empty_when_all_known():
    camp = {"contacts": [{"email": "a@x.com"}, {"email": "b@x.com"}]}
    incoming = [{"email": "a@x.com"}, {"email": "b@x.com"}]
    assert fa._filter_new_enrollees(camp, incoming) == []


from datetime import date, timedelta


def _future_iso(days):
    return (date.today() + timedelta(days=days)).isoformat()


def test_start_options_empty_when_no_steps():
    assert fa._newsletter_enroll_start_options({"emails": []}) == []


def test_start_options_list_upcoming_only_with_month_labels():
    # One past issue, two future issues. Only the future ones are offered.
    past = (date.today() - timedelta(days=40))
    fut1 = (date.today() + timedelta(days=20))
    fut2 = (date.today() + timedelta(days=50))
    camp = {
        "start_date": date.today().isoformat(),
        "emails": [
            {"name": "I0", "fixed_date": past.isoformat()},
            {"name": "I1", "fixed_date": fut1.isoformat()},
            {"name": "I2", "fixed_date": fut2.isoformat()},
        ],
    }
    opts = fa._newsletter_enroll_start_options(camp)
    # Indices preserved (1 and 2), labels are "Month YYYY".
    assert [idx for idx, _ in opts] == [1, 2]
    assert opts[0][1] == fut1.strftime("%B %Y")
    assert opts[1][1] == fut2.strftime("%B %Y")


def test_start_options_empty_when_all_past():
    past1 = (date.today() - timedelta(days=60)).isoformat()
    past2 = (date.today() - timedelta(days=30)).isoformat()
    camp = {
        "start_date": (date.today() - timedelta(days=90)).isoformat(),
        "emails": [
            {"name": "I0", "fixed_date": past1},
            {"name": "I1", "fixed_date": past2},
        ],
    }
    assert fa._newsletter_enroll_start_options(camp) == []

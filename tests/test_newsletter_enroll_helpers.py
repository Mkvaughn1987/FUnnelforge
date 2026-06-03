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

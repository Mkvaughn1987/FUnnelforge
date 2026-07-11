"""Campaign API `enroll_newsletter` field — the helper that drops the same
contacts into a named newsletter / Slow Drip after the campaign launches.

Spec: one authenticated POST can both launch an Arena 4x4 AND enroll its
contacts into an evergreen newsletter (e.g. "Recruitment Rundown - Package
Manufacturing"), which is otherwise a launch-page-only action.
"""
import flowdrip_app as fa


def test_enroll_newsletter_matches_case_insensitively_and_enrolls(monkeypatch):
    nl = {"name": "Recruitment Rundown - Package Manufacturing",
          "evergreen_only": True}
    other = {"name": "Some 4x4 Campaign", "aicb_camp_type": "fourbyfour"}
    monkeypatch.setattr(fa, "load_campaigns", lambda: [other, nl])

    seen = []

    def _fake_enroll(ct, camp):
        seen.append((ct["email"], camp["name"]))
        return "enrolled"
    monkeypatch.setattr(fa, "enroll_contact_in_evergreen", _fake_enroll)

    contacts = [{"email": "a@x.com"}, {"email": "b@x.com"}]
    # Requested name differs in case/spacing from the stored name.
    out = fa._api_enroll_newsletter(
        "  recruitment rundown - package manufacturing  ", contacts)

    assert out["matched"] is True
    assert out["newsletter"] == "Recruitment Rundown - Package Manufacturing"
    assert out["enrolled"] == 2
    assert out["results"] == {"enrolled": 2}
    # Only the evergreen newsletter was targeted, never the 4x4 campaign.
    assert seen == [("a@x.com", "Recruitment Rundown - Package Manufacturing"),
                    ("b@x.com", "Recruitment Rundown - Package Manufacturing")]


def test_enroll_newsletter_no_match_lists_available(monkeypatch):
    nl = {"name": "Recruitment Rundown - Package Manufacturing",
          "evergreen_only": True}
    monkeypatch.setattr(fa, "load_campaigns", lambda: [nl])
    monkeypatch.setattr(fa, "enroll_contact_in_evergreen",
                        lambda ct, camp: "enrolled")

    out = fa._api_enroll_newsletter("Nonexistent Newsletter",
                                    [{"email": "a@x.com"}])

    assert out["matched"] is False
    assert out["enrolled"] == 0
    assert "Recruitment Rundown - Package Manufacturing" in out["available"]


def test_enroll_newsletter_only_targets_evergreen(monkeypatch):
    # A non-evergreen campaign with the same name must NOT be treated as the
    # newsletter (enroll_contact_in_evergreen only accepts evergreen camps).
    same_name_regular = {"name": "Recruitment Rundown - Package Manufacturing"}
    monkeypatch.setattr(fa, "load_campaigns", lambda: [same_name_regular])
    monkeypatch.setattr(fa, "enroll_contact_in_evergreen",
                        lambda ct, camp: "enrolled")

    out = fa._api_enroll_newsletter(
        "Recruitment Rundown - Package Manufacturing", [{"email": "a@x.com"}])

    assert out["matched"] is False
    assert out["enrolled"] == 0


def test_enroll_newsletter_counts_skips(monkeypatch):
    nl = {"name": "NL", "evergreen_only": True}
    monkeypatch.setattr(fa, "load_campaigns", lambda: [nl])

    def _fake_enroll(ct, camp):
        return "skipped_dnc" if ct["email"] == "d@x.com" else "enrolled"
    monkeypatch.setattr(fa, "enroll_contact_in_evergreen", _fake_enroll)

    out = fa._api_enroll_newsletter(
        "NL", [{"email": "a@x.com"}, {"email": "d@x.com"}])

    assert out["matched"] is True
    assert out["enrolled"] == 1
    assert out["results"] == {"enrolled": 1, "skipped_dnc": 1}

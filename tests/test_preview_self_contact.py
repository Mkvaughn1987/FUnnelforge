"""Preview emails must merge the USER's own identity, not the first
contact in the list.

Bug: previews used load_contacts()[0], so the greeting showed an
arbitrary contact's name ("random names") or the literal "[FirstName]"
fallback when that contact had no first name. Previews go to the user to
review, so they should read "Hi <you>,".
"""


class _FakeState:
    def __init__(self, name=""):
        self._user_name = name


def test_uses_signature_first_line_for_name(with_user):
    import flowdrip_app as fa
    fa._user_sig_path().write_text(
        "Lindsay Arcari\nRecruitment Consultant\nArena Direct Hire\n",
        encoding="utf-8",
    )
    pc = fa._preview_self_contact()
    assert pc["first_name"] == "Lindsay"
    assert pc["last_name"] == "Arcari"


def test_profile_name_overrides_signature(with_user):
    import flowdrip_app as fa
    fa._user_sig_path().write_text("Lindsay Arcari\n", encoding="utf-8")
    pc = fa._preview_self_contact(_FakeState("Michael Vaughn"))
    assert pc["first_name"] == "Michael"
    assert pc["last_name"] == "Vaughn"


def test_falls_back_to_there_when_no_identity(with_user):
    import flowdrip_app as fa
    # No signature written, no profile name.
    pc = fa._preview_self_contact()
    assert pc["first_name"] == "there"
    assert "last_name" not in pc  # unknown -> caller's "[LastName]" default shows


def test_single_word_name_has_no_last_name(with_user):
    import flowdrip_app as fa
    fa._user_sig_path().write_text("Lindsay\n", encoding="utf-8")
    pc = fa._preview_self_contact()
    assert pc["first_name"] == "Lindsay"
    assert "last_name" not in pc

"""The LinkedIn connect on the cost email's day is a follow-up to two
unanswered emails, never a note that assumes a conversation happened
(Mike, 2026-10-08)."""
import flowdrip_app as fa

REG = {t[0]: t for t in fa.AICB_CAMPAIGN_TYPES}


def _step(key, n):
    return next(l for l in REG[key][6].split("\n")
                if l.startswith(f"Step {n} - "))


def test_standard_outreach_and_priority_push_share_the_followup_note():
    for key in ("tm_fivebyseven", "tm_conversation"):
        line = _step(key, 4)
        assert "step_type:linkedin" in line
        assert "SAME DAY as Steps 2 and 3" in line
        assert fa._TM_LI_FOLLOWUP_NOTE in line


def test_the_note_says_what_mike_asked_for():
    note = fa._TM_LI_FOLLOWUP_NOTE
    assert "never assume a reply, a call or a conversation happened" in note
    assert "emailed a couple of times and wanted to connect here as well" in note
    assert "placing qualified Filipino professionals" in note
    assert "name the industry from the BRIEF" in note
    assert "thought they might be a resource" in note
    assert "UNDER 300 characters" in note
    assert "no pitch, no link, no figures" in note

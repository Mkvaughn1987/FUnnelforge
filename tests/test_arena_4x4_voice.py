"""Anti-AI voice helpers for the Arena 4x4 campaign.

Spec: docs/superpowers/specs/2026-06-11-arena-4x4-anti-ai-voice-design.md
Plan: docs/superpowers/plans/2026-06-11-arena-4x4-anti-ai-voice.md
"""
import flowdrip_app as fa


# ── _humanize_email_text: dash repair ──────────────────────────────
def test_lone_em_dash_becomes_sentence_break():
    src = "best talent is passively looking — most never see a posting"
    out = fa._humanize_email_text(src)
    assert "—" not in out
    assert " - " not in out
    assert out == "best talent is passively looking. Most never see a posting"


def test_paired_em_dashes_become_commas():
    src = "our team — all ex-recruiters — handles the search"
    out = fa._humanize_email_text(src)
    assert "—" not in out
    assert out == "our team, all ex-recruiters, handles the search"


def test_numeric_en_dash_range_becomes_to():
    src = "base lands around $130K–$150K for senior PMs"
    out = fa._humanize_email_text(src)
    assert "–" not in out
    assert "$130K to $150K" in out


def test_no_spaced_hyphen_dash_survives():
    src = "two things shifted — comp reset and notice periods stretched"
    out = fa._humanize_email_text(src)
    assert " - " not in out


# ── _humanize_email_text: cliche opener removal ────────────────────
def test_cliche_opener_sentence_removed():
    src = ("Hi {FirstName},<br><br>I hope this email finds you well."
           "<br><br>47 days is the current fill window.")
    out = fa._humanize_email_text(src)
    assert "i hope this email finds you well" not in out.lower()
    assert out == ("Hi {FirstName},<br><br>47 days is the current "
                   "fill window.")


def test_ordinary_text_unchanged():
    src = "Hi {FirstName},<br><br>Saw the Wyoming buildout announcement."
    assert fa._humanize_email_text(src) == src


def test_non_string_passthrough():
    assert fa._humanize_email_text(None) is None
    assert fa._humanize_email_text(123) == 123


# ── _DRIPDROP_PLAYBOOK hardening ───────────────────────────────────
def test_playbook_drops_spaced_hyphen_dash_fallback():
    # The old text offered '" - "' as an acceptable dash substitute,
    # which is itself an AI tell. It must be gone.
    assert 'periods, or " - "' not in fa._DRIPDROP_PLAYBOOK


def test_playbook_bans_ai_tell_vocabulary():
    for word in ("streamline", "leverage", "delve", "furthermore",
                 "seamless"):
        assert word in fa._DRIPDROP_PLAYBOOK

"""H/Critical regression: AI-generated campaign emails sometimes ship
with bracketed UPPERCASE placeholders the AI was instructed to leave for
the user to fill in (e.g. [CANDIDATE NAME], [EXPERIENCE], [KEY STRENGTH]).
Without this guard those placeholders go straight to recipients as raw
text — Elizabeth Simonov preview incident, 2026-04-26.

The guard:
  1. Detects bracketed UPPERCASE tokens that look like AI scaffolding.
  2. queue_campaign_emails refuses to queue if any are present.
  3. The campaign-template prompts no longer instruct the AI to use them.
"""
import pathlib
import pytest


# ── Helper-level tests ───────────────────────────────────────────────

def test_detect_uppercase_placeholders(isolated_appdata, with_user):
    import flowdrip_app as fa
    body = (
        "Hi {FirstName},\n\n"
        "[CANDIDATE NAME] background:\n"
        "• [EXPERIENCE] years hands-on CNC\n"
        "• [KEY STRENGTH] - demonstrated ability\n"
    )
    result = fa._detect_unfilled_placeholders(body)
    assert "[CANDIDATE NAME]" in result
    assert "[EXPERIENCE]" in result
    assert "[KEY STRENGTH]" in result


def test_detect_dedups_repeats(isolated_appdata, with_user):
    import flowdrip_app as fa
    text = "[CANDIDATE NAME] in step 1 and again [CANDIDATE NAME] later"
    result = fa._detect_unfilled_placeholders(text)
    assert result == ["[CANDIDATE NAME]"], (
        f"Should dedup repeated placeholders; got {result!r}"
    )


def test_detect_skips_lowercase_brackets(isolated_appdata, with_user):
    """Lowercase / mixed-case bracketed text is too easy to false-positive
    on legitimate body content (e.g. '[edited]' in a forwarded message).
    Only catch the AI's UPPERCASE convention."""
    import flowdrip_app as fa
    text = "[click here] for [more info] about [our website]"
    assert fa._detect_unfilled_placeholders(text) == []


def test_detect_skips_dates_and_numbers(isolated_appdata, with_user):
    """Bracketed digits/dates aren't AI placeholders."""
    import flowdrip_app as fa
    text = "Posted [2026-04-26] in [section 4.2.1]"
    assert fa._detect_unfilled_placeholders(text) == []


def test_detect_clean_body_returns_empty(isolated_appdata, with_user):
    import flowdrip_app as fa
    body = (
        "Hi {FirstName},\n\n"
        "Quick intro - I work with precision manufacturing teams.\n"
        "Ramon has 12 years in CNC, available in 3 weeks.\n"
    )
    assert fa._detect_unfilled_placeholders(body) == []


# ── Integration: queue_campaign_emails refuses placeholder bodies ────

def test_queue_blocks_on_unfilled_placeholders(isolated_appdata, with_user):
    """queue_campaign_emails must raise rather than ship a campaign
    whose body still contains uppercase bracketed placeholders."""
    import flowdrip_app as fa

    camp = {
        "schema": 2,
        "name": "Bad Campaign",
        "start_date": "2099-01-01",
        "contacts": [{"email": "test@example.com", "first_name": "Test"}],
        "emails": [{
            "step_type": "email_auto",
            "subject": "Quick intro",
            "body": "Hi {FirstName},\n\n[CANDIDATE NAME] has [EXPERIENCE] years.",
            "delay_days": 0,
            "time": "9:00 AM",
        }],
        "responders": [],
    }

    with pytest.raises(ValueError) as exc:
        fa.queue_campaign_emails(camp)
    msg = str(exc.value).lower()
    assert "placeholder" in msg
    assert "[candidate name]" in msg or "candidate" in msg


# ── Integration: campaign-template prompts no longer instruct
#    "Use placeholders ..." ────────────────────────────────────────────

def test_campaign_templates_no_longer_promote_placeholders():
    """Static check: AICB_CAMPAIGN_TYPES touch_sequences must not
    instruct the AI to use [CANDIDATE NAME]/etc. placeholders."""
    src = pathlib.Path(__file__).resolve().parent.parent / "flowdrip_app.py"
    text = src.read_text(encoding="utf-8")

    # Find the AICB_CAMPAIGN_TYPES list (between its declaration and the
    # closing bracket of the list).
    start = text.find("AICB_CAMPAIGN_TYPES")
    assert start != -1, "Couldn't find AICB_CAMPAIGN_TYPES"
    # Conservative end: limit search to ~200 lines after.
    end = text.find("\n]", start)
    assert end != -1
    block = text[start:end]

    # Phrases that contradicted the candidate-data injection and caused
    # the bug:
    bad = [
        "Use placeholders [CANDIDATE",
        "Use placeholders for user to fill in",
        "Use placeholders for the user to fill in",
    ]
    for phrase in bad:
        assert phrase not in block, (
            f"AICB_CAMPAIGN_TYPES still contains {phrase!r} — the AI will "
            "be told to leave [CANDIDATE NAME]/etc. placeholders even "
            "though candidate data is being injected separately."
        )

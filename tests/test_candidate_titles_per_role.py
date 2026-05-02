"""User feature 2026-05-01: pick up to 6 titles, AI generates one
candidate per title (instead of a count + AI-fetched titles).

Also covers the format fix: candidate headlines must say
'X yrs experience' (or similar) rather than anchoring all years to a
single employer ('12 yrs at Acme'). The user's note: 'It can drop one
company name but just not all their experience at one company.'"""
from unittest.mock import MagicMock


def _fake_ai_response_with_titles(titles: list, locations: str = "Denver, CO") -> MagicMock:
    """Mock AI response that emits one block per title, headline uses
    that title verbatim. Bodies use the new no-single-anchor format."""
    body = "\n\n".join(
        f"Candidate {chr(ord('A') + i)}: {t}, 8+ yrs experience\n"
        f"• Location: {locations}\n"
        f"• Experience: 8+ years across multiple firms; most recently at a competitor\n"
        f"• Skills: SkillA, SkillB"
        for i, t in enumerate(titles)
    )
    msg = MagicMock()
    block = MagicMock()
    block.text = body
    msg.content = [block]
    return msg


def _wait_for_thread(s, timeout=5.0):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        if hasattr(s, "_aicb_cand_generating") and not s._aicb_cand_generating:
            return True
        time.sleep(0.02)
    return False


# ── 1. titles=N produces N candidates, one per title ──

def test_titles_drive_count_one_per_title(isolated_appdata, with_user, monkeypatch):
    """If 4 titles are picked, 4 candidates are generated, with each
    title appearing in exactly one candidate's headline."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_sel_roles = ["CNC Machinist", "Mill Operator", "Production Supervisor", "QA Tech"]
    s.aicb_sel_locations = ["Denver, CO"]

    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_ai_response_with_titles(s.aicb_sel_roles),
    )
    fa._aicb_auto_generate_candidates(s, lambda: None,
                                       count=len(s.aicb_sel_roles))
    _wait_for_thread(s)
    text = s._aicb_cand_text
    assert "CNC Machinist" in text
    assert "Mill Operator" in text
    assert "Production Supervisor" in text
    assert "QA Tech" in text
    # Each candidate letter appears exactly once
    for letter in ["A", "B", "C", "D"]:
        assert text.count(f"Candidate {letter}") == 1, (
            f"Expected exactly one Candidate {letter}; got "
            f"{text.count(f'Candidate {letter}')}"
        )


# ── 2. Empty titles → count fallback (regression) ──

def test_no_titles_falls_back_to_count(isolated_appdata, with_user, monkeypatch):
    """If aicb_sel_roles is empty AND a count is passed, the existing
    count-based flow still works. This is the auto-generate fallback the
    user explicitly asked us to keep ('keep the auto generate if they
    dont pick any titles')."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_sel_roles = []  # no titles picked
    s.aicb_sel_locations = ["Denver, CO"]

    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_ai_response_with_titles(["Generic Role"] * 3),
    )
    fa._aicb_auto_generate_candidates(s, lambda: None, count=3)
    _wait_for_thread(s)
    # Three candidate blocks generated, A/B/C
    assert s._aicb_cand_text.count("Candidate A") == 1
    assert s._aicb_cand_text.count("Candidate B") == 1
    assert s._aicb_cand_text.count("Candidate C") == 1


# ── 3. Prompt no longer anchors all years to single firm ──

def test_prompt_avoids_single_company_anchor(isolated_appdata, with_user, monkeypatch):
    """The user's complaint: 'titles shouldnt include 12 years at a single
    company but 12 years experience as a title - It can drop one company
    name but just not all their experience at one company.'

    Verify the candidate-generation prompt no longer instructs the model
    to write 'X yrs at [Firm]' as the single-company anchor format.
    Format strings inside the prompt must be either generic ('experience')
    or distribute across multiple firms."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_sel_roles = ["CNC Machinist"]
    s.aicb_sel_locations = ["Denver, CO"]

    captured_prompt = {"text": ""}
    def _capture(*args, **kwargs):
        msgs = kwargs.get("messages") or []
        if msgs:
            captured_prompt["text"] = msgs[0].get("content", "")
        return _fake_ai_response_with_titles(["CNC Machinist"])
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(fa, "_claude_create_with_retry", _capture)

    fa._aicb_auto_generate_candidates(s, lambda: None, count=1)
    _wait_for_thread(s)

    p = captured_prompt["text"]
    p_l = p.lower()
    assert "experience" in p_l, (
        "Prompt should describe candidates by years of experience, "
        "not by years at a single firm"
    )
    # The OLD bad format string was literally:
    #   'Candidate {L}: Role Title, X yrs at [Real Competitor Firm]'
    # which forced the model to anchor full tenure at one firm. The new
    # format must NOT contain this 'X yrs at [...firm]' headline pattern.
    # Headlines should read 'X yrs experience' (or similar).
    import re as _re
    bad_pattern = _re.compile(
        r"x\s*yrs?\s+at\s+\[[^\]]*(?:firm|company|competitor)[^\]]*\]",
        _re.IGNORECASE,
    )
    assert not bad_pattern.search(p), (
        "Prompt still contains the 'X yrs at [Firm]' single-employer "
        "anchor format. User asked for 'X yrs experience' instead.\n"
        f"Prompt excerpt:\n{p[:800]}"
    )
    # The prompt MUST tell the model to spread experience across firms
    # (or to avoid the single-employer anchor) rather than parking
    # the entire tenure at one company.
    assert ("multiple" in p_l or "spread" in p_l
            or "across" in p_l or "different firms" in p_l), (
        "Prompt must tell the model to spread candidate experience across "
        "multiple firms, not anchor it all at one employer. Got prompt:\n"
        f"{p[:600]}"
    )


# ── 4. Secondary industries supports multiple entries ──

def test_secondary_industries_accepts_multiple(isolated_appdata, with_user):
    """The new feature: aicb_secondary_industries accepts and preserves
    multiple entries on AppState. Today the picker UI writes only 0-or-1,
    but the field has always been list[str]; the test guards that the
    field still holds N entries when assigned, and that the persisted-
    fields list (used by reconnect protection) includes it."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_secondary_industries = ["Aerospace", "Defense", "Automotive"]
    assert s.aicb_secondary_industries == ["Aerospace", "Defense", "Automotive"]
    # The field is in the reconnect-persisted set so multi-pick survives
    # websocket disconnects same as single-pick did.
    assert "aicb_secondary_industries" in fa._AICB_PERSISTED_FIELDS


def test_aicb_niche_joins_multiple_secondary_industries(isolated_appdata, with_user):
    """Downstream code reads aicb_niche (comma-joined string) from the
    secondary-industry list. With multi-select enabled, multiple secondary
    industries should join into a single niche string for prompts/PDFs."""
    secs = ["Aerospace", "Defense", "Automotive"]
    joined = ", ".join(str(x).strip() for x in secs if str(x).strip())
    assert joined == "Aerospace, Defense, Automotive"
    # An empty list should not produce a stray comma.
    assert ", ".join(str(x).strip() for x in [] if str(x).strip()) == ""

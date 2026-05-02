"""Regression: hitting 'Generate N candidates' with picked titles must
populate `aicb_cand_cards` so the UI can render them. Pre-fix, the
spinner cleared but `aicb_cand_cards` stayed empty — user saw nothing
happen. Caused by the `_gen_titles` path passing `rf` directly without
the `_on_done` parse step that `_reroll_titles` had."""
from unittest.mock import MagicMock
import time


def test_generate_with_picked_titles_populates_cards(
        isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_niche = ""
    s.aicb_sel_locations = ["Denver, CO"]
    s.aicb_sel_roles = ["Project Manager", "Field Manager"]
    s._aicb_cand_text = ""
    s.aicb_cand_cards = []

    # Fake the AI response so we don't hit the real API.
    fake_text = (
        "Candidate A: Project Manager, 10+ yrs experience\n"
        "• Location: Denver, CO\n"
        "• Experience: spread across 3 firms\n"
        "• Skills: scheduling; budgeting\n"
        "• Proficiencies: MS Project, Procore\n"
        "• Certifications: PMP\n"
        "• Target Salary: $110-130K\n\n"
        "Candidate B: Field Manager, 8+ yrs experience\n"
        "• Location: Denver, CO\n"
        "• Experience: foreman → super track\n"
        "• Skills: crew leadership; QA\n"
        "• Proficiencies: Bluebeam, Procore\n"
        "• Certifications: OSHA 30\n"
        "• Target Salary: $95-115K\n"
    )

    def _fake_run(state, count: int = 3):
        state._aicb_cand_text = fake_text
    monkeypatch.setattr(fa, "_aicb_generate_candidates_run", _fake_run)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")

    rf = MagicMock()
    fa._aicb_auto_generate_candidates(s, rf, count=2)

    # The wrapper kicks a daemon thread; give it a brief moment to finish.
    for _ in range(50):
        if not s._aicb_cand_generating:
            break
        time.sleep(0.05)

    assert s._aicb_cand_generating is False, "spinner should have cleared"
    assert s.aicb_cand_cards, \
        f"aicb_cand_cards must be populated. Got: {s.aicb_cand_cards!r}"
    assert len(s.aicb_cand_cards) >= 2
    rf.assert_called()

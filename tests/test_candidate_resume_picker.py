"""Pure-function tests for the candidate résumé picker.

Spec: docs/superpowers/specs/2026-06-22-candidate-resume-picker-design.md
"""
import flowdrip_app as fa


def test_is_redacted_resume_pdf():
    assert fa._is_redacted_resume_pdf("Resume_Candidate_A_Redacted.pdf") is True
    assert fa._is_redacted_resume_pdf("resume_jane_doe_redacted.PDF") is True
    assert fa._is_redacted_resume_pdf("Market_Pulse_Acme.pdf") is False
    assert fa._is_redacted_resume_pdf("Salary_Guide_Denver.pdf") is False
    assert fa._is_redacted_resume_pdf("") is False


def test_redacted_resume_label():
    # Resume_<slug>_Redacted.pdf -> friendly, spaces restored.
    assert fa._redacted_resume_label("Resume_Candidate_A_Redacted.pdf") == "Candidate A"
    assert fa._redacted_resume_label("Resume_Jane_Doe_Redacted.pdf") == "Jane Doe"
    # Non-résumé / unparseable -> raw filename fallback.
    assert fa._redacted_resume_label("Market_Pulse_Acme.pdf") == "Market_Pulse_Acme.pdf"


def test_step_features_candidates_autogen_labels():
    step = {"step_type": "email_auto",
            "body": "Hi {FirstName},<br><br>Two profiles.<br>"
                    "<b>Candidate A, Manufacturing Manager</b><br>"
                    "• 12 years running blending plants"}
    assert fa._step_features_candidates(step) is True


def test_step_features_candidates_real_name_profile():
    # No "Candidate X" label, but a bold header right before a bullet block.
    step = {"step_type": "email_auto",
            "body": "Hi {FirstName},<br><br>"
                    "<b>Jane Doe, Engineering Manager</b><br>"
                    "• 10 years process automation<br>• PE licensed"}
    assert fa._step_features_candidates(step) is True


def test_step_features_candidates_market_email_is_false():
    step = {"step_type": "email_auto",
            "body": "Hi {FirstName},<br><br>The ag-inputs talent market is "
                    "tight; active searches surface mid-tier talent."}
    assert fa._step_features_candidates(step) is False


def test_step_features_candidates_non_email_is_false():
    step = {"step_type": "linkedin",
            "body": "<b>Candidate A, Manufacturing Manager</b><br>• 12 years"}
    assert fa._step_features_candidates(step) is False

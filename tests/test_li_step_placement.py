"""LinkedIn touchpoint placement enforcement.

Every NEW sequence (AICB Free Flow, Recruiting Sequence) must include
exactly ONE LinkedIn step, positioned immediately after the first
email (step 2, delay_days:1). The Free Flow wizard step-add UI must
warn if the user tries to add a second LI or place LI before email 1.

Existing saved campaigns are NOT migrated (per 2026-05-10 audit
findings).
"""
import inspect


def test_aicb_byos_prompt_enforces_one_li_at_step_2():
    """The AICB Free Flow (byos) prompt must explicitly require
    exactly one LinkedIn step at position 2 with delay_days:1.
    Without this hard constraint, the AI free-styles LI placement."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    assert "The user wants a CUSTOM sequence" in src, (
        "Expected to find the AICB byos prompt in flowdrip_app.py"
    )
    idx = src.index("The user wants a CUSTOM sequence")
    window = src[idx : idx + 1200]
    assert "exactly ONE LinkedIn" in window or "exactly one linkedin" in window.lower(), (
        "Free Flow AICB prompt must explicitly require exactly ONE "
        "LinkedIn step. Add a hard constraint like 'Include EXACTLY "
        "ONE LinkedIn step at position 2 (delay_days:1).'"
    )
    assert "step 2" in window.lower() or "position 2" in window.lower() or "after the first email" in window.lower(), (
        "Free Flow AICB prompt must specify the LI step's position "
        "(step 2 / position 2 / after the first email)"
    )


def test_recruiting_sequence_prompt_includes_li_after_email_1():
    """The Recruiting Campaigns page generator currently builds
    email-only sequences. Per the 2026-05-10 directive, every NEW
    sequence (including recruiting-flow ones) should include exactly
    one LinkedIn step at position 2."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    assert "Recruiting" in src, "Expected to find recruiting-sequence builder source"
    idx_candidates = [i for i in range(len(src)) if src[i:i+20] == "Return ONLY valid JS"]
    found_li_in_recruiting = False
    for idx in idx_candidates:
        window = src[idx : idx + 800]
        before = src[max(idx - 2000, 0) : idx]
        if ("recruiting" in before.lower() or "Recruiting" in before) and '"step_type":"linkedin"' in window:
            found_li_in_recruiting = True
            break
    assert found_li_in_recruiting, (
        "The Recruiting Sequence generator's JSON example must include "
        "a step with \"step_type\":\"linkedin\" at position 2. Current "
        "prompt generates email-only sequences."
    )


def test_step_add_handler_has_li_guardrails():
    """The Free Flow step-add UI must warn (via ui.notify) if the user
    tries to add a second LinkedIn step or place a LinkedIn step
    before any email. These are SOFT enforcement (warnings, not hard
    blocks) — the user is explicitly building a custom sequence and
    can override.

    Body extraction note: _confirm_add_step is nested inside outer
    closures at deep indentation, so the body ends at the next
    same-indentation `def ` line OR a fixed 4000-char ceiling,
    whichever comes first. Without the ceiling the body would extend
    180KB+ into unrelated code and the assertions would always pass
    against incidental occurrences elsewhere.
    """
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    assert "_confirm_add_step" in src, (
        "Expected _confirm_add_step handler in flowdrip_app.py"
    )
    idx = src.index("def _confirm_add_step")
    # Detect the indent of the def itself
    line_start = src.rfind("\n", 0, idx) + 1
    def_indent = idx - line_start
    # Walk forward looking for the next `def ` at the same or shallower
    # indentation, with a hard 4000-char ceiling (the function is small).
    end = idx + 4000
    cursor = idx + 1
    next_def_pat = "\n" + " " * def_indent + "def "
    next_def = src.find(next_def_pat, cursor)
    if next_def != -1 and next_def < end:
        end = next_def
    # Also stop at the next dedented-to-shallower-level definition
    for shallower in range(0, def_indent, 4):
        pat = "\n" + " " * shallower + "def "
        candidate = src.find(pat, cursor)
        if candidate != -1 and candidate < end:
            end = candidate
    body = src[idx:end]
    # Assertions on the now-bounded body
    assert "linkedin" in body.lower(), (
        "_confirm_add_step body must reference 'linkedin' (the step "
        "type the guardrails check for)"
    )
    assert "ui.notify" in body, (
        "_confirm_add_step must call ui.notify when adding a 2nd "
        "LinkedIn or placing LI before email 1"
    )
    # The body should mention BOTH guardrail conditions
    assert ("existing_li" in body or "already have" in body.lower()), (
        "Guardrail for 2nd LinkedIn step must be present"
    )
    assert ("existing_emails" in body or "before" in body.lower()), (
        "Guardrail for LI-before-email-1 must be present"
    )

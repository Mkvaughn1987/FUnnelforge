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

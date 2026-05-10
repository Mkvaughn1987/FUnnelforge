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

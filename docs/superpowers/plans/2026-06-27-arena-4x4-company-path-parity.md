# Arena 4×4 Company-Path Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Arena 4×4 produce identical email content wherever it is picked (entry tile or "search by company" style picker), and always list the candidate slate on every email.

**Architecture:** Extract two pure, module-level helpers in `flowdrip_app.py` — one that forces market framing for the `fourbyfour` campaign type, one that returns the candidate placement/angle instructions (every email for 4×4, every other email otherwise). Call them from the AICB wizard `_run` generation closure. Pure helpers make the buried closure logic unit-testable in the existing `tests/test_arena_4x4_*.py` style.

**Tech Stack:** Python, pytest. Tests import `flowdrip_app as fa` and call module-level functions. Run from the project root (`C:\Users\mkvau\OneDrive\Documents\Sales\Python\FunnelForge`).

**Spec:** `docs/superpowers/specs/2026-06-27-arena-4x4-company-path-parity-design.md`

---

## File Structure

- `flowdrip_app.py` — add two module-level helpers near the other Arena 4×4 generation helpers (just above `_4x4_email_prompt`, ~line 48187); wire them into the AICB `_run` closure (framing at ~line 34834, candidate block at ~line 34985).
- `tests/test_arena_4x4_company_parity.py` — new test file covering both helpers.

---

### Task 1: Add the `_aicb_force_market_for_4x4` helper (forces market framing)

**Files:**
- Modify: `flowdrip_app.py` (add helper above `_4x4_email_prompt`, ~line 48187)
- Test: `tests/test_arena_4x4_company_parity.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_arena_4x4_company_parity.py`:

```python
"""Arena 4x4 company-path parity helpers.

Spec: docs/superpowers/specs/2026-06-27-arena-4x4-company-path-parity-design.md
Plan: docs/superpowers/plans/2026-06-27-arena-4x4-company-path-parity.md
"""
import flowdrip_app as fa


# ── _aicb_force_market_for_4x4 ─────────────────────────────────────
def test_4x4_with_company_forces_market_mode():
    # Company set, no niche -> default would be company mode (False);
    # 4x4 must flip to market mode and fill niche from the industry label.
    is_niche, niche = fa._aicb_force_market_for_4x4(
        "fourbyfour", False, "", "Construction", "Project Manager")
    assert is_niche is True
    assert niche == "Construction"


def test_4x4_niche_fallback_chain_uses_roles_then_default():
    # No industry label -> fall back to roles.
    _, niche = fa._aicb_force_market_for_4x4(
        "fourbyfour", False, "", "", "Estimator")
    assert niche == "Estimator"
    # No industry label and no roles -> generic default.
    _, niche2 = fa._aicb_force_market_for_4x4(
        "fourbyfour", False, "", "", "")
    assert niche2 == "your market"


def test_4x4_keeps_existing_niche():
    is_niche, niche = fa._aicb_force_market_for_4x4(
        "fourbyfour", True, "Solar EPC", "Energy", "Engineer")
    assert is_niche is True
    assert niche == "Solar EPC"


def test_non_4x4_is_unchanged():
    # A different campaign type with a company stays in company mode.
    is_niche, niche = fa._aicb_force_market_for_4x4(
        "talentdrop", False, "", "Construction", "Project Manager")
    assert is_niche is False
    assert niche == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_arena_4x4_company_parity.py -v`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_aicb_force_market_for_4x4'`

- [ ] **Step 3: Write minimal implementation**

In `flowdrip_app.py`, immediately above the `def _4x4_email_prompt(` line (~48187), add:

```python
def _aicb_force_market_for_4x4(camp_type, is_niche_mode, niche_str,
                               ind_label, roles_str):
    """Arena 4×4 is always a market/slate play regardless of how it was
    reached (entry tile or "search by company" style picker), so its emails
    must come out identical wherever it is picked. For the ``fourbyfour``
    type only, force market framing and guarantee a non-empty niche so the
    market research brief is never blank when the user arrived via the
    company tile without choosing a niche. Pure — no AI call, no state."""
    if (camp_type or "").strip() == "fourbyfour":
        is_niche_mode = True
        if not (niche_str or "").strip():
            niche_str = (ind_label or roles_str or "your market").strip()
    return is_niche_mode, niche_str


```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_arena_4x4_company_parity.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_arena_4x4_company_parity.py
git commit -m "Add _aicb_force_market_for_4x4 helper for 4x4 framing parity"
```

---

### Task 2: Add the `_aicb_candidate_weave_block` helper (every email for 4×4)

**Files:**
- Modify: `flowdrip_app.py` (add helper directly below the helper from Task 1, ~line 48187)
- Test: `tests/test_arena_4x4_company_parity.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_arena_4x4_company_parity.py`:

```python
# ── _aicb_candidate_weave_block ────────────────────────────────────
def test_4x4_weave_block_puts_candidates_on_every_email():
    txt = fa._aicb_candidate_weave_block("fourbyfour")
    # All four emails referenced, including 1 and 3 (the ones the generic
    # rule skipped).
    for n in ("Email 1", "Email 2", "Email 3", "Email 4"):
        assert n in txt
    # The generic "every other email" / "skip Email 1" language is gone.
    assert "EVERY OTHER email" not in txt
    assert "NOT Email 1" not in txt
    assert "WITHOUT candidates" not in txt


def test_non_4x4_weave_block_keeps_every_other_email():
    txt = fa._aicb_candidate_weave_block("talentdrop")
    assert "EVERY OTHER email" in txt
    assert "NOT Email 1" in txt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_arena_4x4_company_parity.py -v`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_aicb_candidate_weave_block'`

- [ ] **Step 3: Write minimal implementation**

In `flowdrip_app.py`, directly below `_aicb_force_market_for_4x4` (added in Task 1), add:

```python
def _aicb_candidate_weave_block(camp_type):
    """Placement + angle instructions for the candidate-highlights block.
    Arena 4×4 lists the slate on EVERY email (its spec promises "candidate
    highlights on every email"); every other campaign type weaves candidates
    into every other email starting from Email 2. Pure — returns prompt text
    only. Caller splices this between the count preamble and the label rules."""
    if (camp_type or "").strip() == "fourbyfour":
        return (
            'Include ALL candidates on EVERY email (Email 1, 2, 3, and 4). '
            'Each time you feature them, use a DIFFERENT angle:\n'
            '  - Email 1: Introduction & current availability — 3 bullets per candidate\n'
            '  - Email 2: Experience & qualifications — 3 bullets per candidate\n'
            '  - Email 3: Why they fit this role/market — 3 bullets per candidate\n'
            '  - Email 4: Availability & urgency (competing interest, closing window) — 3 bullets per candidate\n'
            'Do NOT leave any email without the candidate slate.\n'
        )
    return (
        'Weave candidates into EVERY OTHER email '
        'starting from Email 2 (NOT Email 1). Each '
        'time you feature them, use a DIFFERENT angle:\n'
        '  - Email 2: Experience & qualifications — 3 bullets per candidate\n'
        '  - Email 4: Why they fit THIS company — 3 bullets per candidate\n'
        '  - Email 6+: Availability & urgency (competing interest, closing window)\n'
        'Emails WITHOUT candidates (1, 3, 5, etc.) — '
        'focus on market insights, value props, or '
        'data only.\n'
    )


```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_arena_4x4_company_parity.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_arena_4x4_company_parity.py
git commit -m "Add _aicb_candidate_weave_block helper (4x4 candidates on every email)"
```

---

### Task 3: Wire `_aicb_force_market_for_4x4` into the AICB `_run` closure

**Files:**
- Modify: `flowdrip_app.py:34832-34834`

- [ ] **Step 1: Apply the edit**

Find this block (~line 34832, inside the wizard `_run` closure, after `roles_str`/`ind_label` are already defined earlier in the closure):

```python
                        niche_str = s.aicb_niche or ""
                        is_niche_mode = bool(niche_str) and not company
                        is_both = bool(company) and bool(niche_str)
```

Replace it with:

```python
                        niche_str = s.aicb_niche or ""
                        is_niche_mode = bool(niche_str) and not company
                        is_both = bool(company) and bool(niche_str)
                        # Arena 4×4 is always a market/slate play regardless of
                        # entry point, so its emails come out identical wherever
                        # it is picked. Force market framing (brief, style_note,
                        # and "MARKET BRIEF" label all key off is_niche_mode)
                        # and guarantee a non-empty niche for the brief.
                        is_niche_mode, niche_str = _aicb_force_market_for_4x4(
                            s.aicb_camp_type, is_niche_mode, niche_str,
                            ind_label, roles_str)
```

- [ ] **Step 2: Verify the module still imports (syntax check)**

Run: `python -c "import flowdrip_app"`
Expected: no output, exit code 0 (no `SyntaxError`).

- [ ] **Step 3: Run the parity tests + the existing 4×4 suite**

Run: `python -m pytest tests/test_arena_4x4_company_parity.py tests/test_arena_4x4_voice.py tests/test_arena_4x4_industry_aim.py tests/test_arena_4x4_cited_stats.py -v`
Expected: all PASS (no regressions in the existing 4×4 tests).

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "Force market framing for Arena 4x4 in AICB generation"
```

---

### Task 4: Wire `_aicb_candidate_weave_block` into the `_cand_block`

**Files:**
- Modify: `flowdrip_app.py` (inside the `if _cand_text:` branch, ~line 34985)

- [ ] **Step 1: Apply the edit**

Find this run of lines inside the `if _cand_text:` block (~line 34984, part of the `_cand_block = ( ... )` f-string concatenation):

```python
                                f'a clean candidate profile with 3 bullet '
                                f'points.\n'
                                f'Weave candidates into EVERY OTHER email '
                                f'starting from Email 2 (NOT Email 1). Each '
                                f'time you feature them, use a DIFFERENT angle:\n'
                                f'  - Email 2: Experience & qualifications — 3 bullets per candidate\n'
                                f'  - Email 4: Why they fit THIS company — 3 bullets per candidate\n'
                                f'  - Email 6+: Availability & urgency (competing interest, closing window)\n'
                                f'Emails WITHOUT candidates (1, 3, 5, etc.) — '
                                f'focus on market insights, value props, or '
                                f'data only.\n'
                                f'When email subjects or body text references '
```

Replace it with:

```python
                                f'a clean candidate profile with 3 bullet '
                                f'points.\n'
                                + _aicb_candidate_weave_block(s.aicb_camp_type) +
                                f'When email subjects or body text references '
```

(The surrounding lines are adjacent string literals; inserting `+ helper(...) +` between them keeps the concatenation valid.)

- [ ] **Step 2: Verify the module still imports (syntax check)**

Run: `python -c "import flowdrip_app"`
Expected: no output, exit code 0 (no `SyntaxError`).

- [ ] **Step 3: Run the full parity + 4×4 suite**

Run: `python -m pytest tests/test_arena_4x4_company_parity.py tests/test_arena_4x4_voice.py tests/test_arena_4x4_industry_aim.py tests/test_arena_4x4_cited_stats.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "Arena 4x4: list candidate slate on every email in AICB generation"
```

---

### Task 5: Full-suite regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the whole test suite**

Run: `python -m pytest -q`
Expected: all tests pass (or only pre-existing, unrelated failures — note any in the commit/PR if they exist before this work).

- [ ] **Step 2: Confirm no stray references**

Run: `python -c "import flowdrip_app as fa; print(fa._aicb_force_market_for_4x4('fourbyfour', False, '', 'Construction', 'PM')); print('EVERY OTHER email' not in fa._aicb_candidate_weave_block('fourbyfour'))"`
Expected output:
```
(True, 'Construction')
True
```

---

## Notes for the implementer

- `ind_label` (~line 34779) and `roles_str` (~line 34780) are defined earlier in the same `_run` closure, before the Task 3 edit site — they are in scope.
- Do **not** touch the `elif s.aicb_resumes:` / `elif s.aicb_candidate_resume:` candidate branches; Arena 4×4 uses the `if _cand_text:` branch (auto-generated/pool candidates). They are out of scope per the spec.
- Campaign **name** and **PDF target** are intentionally left mode-driven (email-only parity, per the spec's "Emails only" decision). Do not change them.
- The dedicated `_4x4_generate_emails` / Candidate Finder (CPC) path is out of scope.

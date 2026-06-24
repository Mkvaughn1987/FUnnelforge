# Candidate Résumé Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On candidate emails, surface the per-candidate redacted résumés in the attachment area with View (preview in new tab) and Attach buttons — never auto-attached.

**Architecture:** Three small pure helpers in `flowdrip_app.py` (`_is_redacted_resume_pdf`, `_redacted_resume_label`, `_step_features_candidates`) drive a new "Candidate résumés" render block inside the existing email-editor attachment area. The generic "reuse a generated PDF" dropdown is filtered to exclude résumés so nothing is offered twice. Detection of candidate emails is by body content, so no campaign migration is needed.

**Tech Stack:** Python, NiceGUI, pytest. Existing secure `/pdfs/{filename}` per-user route handles preview.

**Spec:** docs/superpowers/specs/2026-06-22-candidate-resume-picker-design.md

---

### Task 1: `_is_redacted_resume_pdf` helper

**Files:**
- Modify: `flowdrip_app.py` (add helper near `_save_redacted_pdf`, ~L30608)
- Test: `tests/test_candidate_resume_picker.py` (create)

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_candidate_resume_picker.py::test_is_redacted_resume_pdf -v`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_is_redacted_resume_pdf'`

- [ ] **Step 3: Write minimal implementation** (add just above `def _save_redacted_pdf`)

```python
def _is_redacted_resume_pdf(filename: str) -> bool:
    """True for the redacted-résumé PDFs that _save_redacted_pdf writes
    (Resume_<Candidate>_Redacted.pdf). Used to (a) pull them into the
    dedicated Candidate Résumés picker and (b) exclude them from the
    generic 'reuse a generated PDF' dropdown so they aren't offered twice."""
    n = (filename or "").lower()
    return n.startswith("resume_") and n.endswith("_redacted.pdf")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_candidate_resume_picker.py::test_is_redacted_resume_pdf -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_candidate_resume_picker.py flowdrip_app.py
git commit -m "feat(resume-picker): add _is_redacted_resume_pdf helper"
```

---

### Task 2: `_redacted_resume_label` helper

**Files:**
- Modify: `flowdrip_app.py` (add helper directly below `_is_redacted_resume_pdf`)
- Test: `tests/test_candidate_resume_picker.py`

- [ ] **Step 1: Write the failing test**

```python
def test_redacted_resume_label():
    # Resume_<slug>_Redacted.pdf -> friendly, spaces restored.
    assert fa._redacted_resume_label("Resume_Candidate_A_Redacted.pdf") == "Candidate A"
    assert fa._redacted_resume_label("Resume_Jane_Doe_Redacted.pdf") == "Jane Doe"
    # Non-résumé / unparseable -> raw filename fallback.
    assert fa._redacted_resume_label("Market_Pulse_Acme.pdf") == "Market_Pulse_Acme.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_candidate_resume_picker.py::test_redacted_resume_label -v`
Expected: FAIL with `AttributeError: ... has no attribute '_redacted_resume_label'`

- [ ] **Step 3: Write minimal implementation**

```python
def _redacted_resume_label(filename: str) -> str:
    """Friendly display name for a redacted résumé file:
    'Resume_Candidate_A_Redacted.pdf' -> 'Candidate A'. Falls back to the
    raw filename for anything that isn't a redacted résumé."""
    if not _is_redacted_resume_pdf(filename):
        return filename
    core = filename[len("Resume_"):-len("_Redacted.pdf")]
    return core.replace("_", " ").strip() or filename
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_candidate_resume_picker.py::test_redacted_resume_label -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_candidate_resume_picker.py flowdrip_app.py
git commit -m "feat(resume-picker): add _redacted_resume_label helper"
```

---

### Task 3: `_step_features_candidates` detector

**Files:**
- Modify: `flowdrip_app.py` (add helper below `_redacted_resume_label`)
- Test: `tests/test_candidate_resume_picker.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_candidate_resume_picker.py -k step_features -v`
Expected: FAIL with `AttributeError: ... has no attribute '_step_features_candidates'`

- [ ] **Step 3: Write minimal implementation**

```python
def _step_features_candidates(step) -> bool:
    """True if an email step's body contains candidate-profile content.
    Covers autogen labels ('Candidate A/B/C') and real-name profiles
    (a bold header immediately followed by a bullet). Drives whether the
    Candidate Résumés picker shows on this step (candidate emails only)."""
    if not isinstance(step, dict):
        return False
    if step.get("step_type", "") not in (ST.EMAIL_AUTO, ST.EMAIL_MANUAL, ""):
        return False
    body = step.get("body", "") or ""
    if re.search(r"Candidate [A-Z]\b", body):
        return True
    # Real-name profile: a bold header within ~80 chars of a "•" bullet.
    return bool(re.search(r"<(?:b|strong)>.{0,80}?</(?:b|strong)>.{0,80}?•",
                          body, re.IGNORECASE | re.DOTALL))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_candidate_resume_picker.py -k step_features -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_candidate_resume_picker.py flowdrip_app.py
git commit -m "feat(resume-picker): add _step_features_candidates detector"
```

---

### Task 4: Exclude résumés from the generic reuse dropdown

**Files:**
- Modify: `flowdrip_app.py:15433`

- [ ] **Step 1: Edit `_reusable_pdfs` to drop redacted résumés**

Find (`flowdrip_app.py:15432-15433`):

```python
                    available_pdfs = sorted(_user_pdf_dir().glob("*.pdf")) if _user_pdf_dir().exists() else []
                    _reusable_pdfs = [p for p in available_pdfs if p.name not in step_atts]
```

Replace with:

```python
                    available_pdfs = sorted(_user_pdf_dir().glob("*.pdf")) if _user_pdf_dir().exists() else []
                    # Redacted résumés get their own picker (below) on candidate
                    # emails, so keep them out of the generic dropdown — no file
                    # should be offered in two places at once.
                    _reusable_pdfs = [p for p in available_pdfs
                                      if p.name not in step_atts
                                      and not _is_redacted_resume_pdf(p.name)]
```

- [ ] **Step 2: Smoke-check import still works**

Run: `python -c "import flowdrip_app"`
Expected: no output, exit 0

- [ ] **Step 3: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(resume-picker): keep résumés out of the generic reuse dropdown"
```

---

### Task 5: Render the "Candidate résumés" picker on candidate emails

**Files:**
- Modify: `flowdrip_app.py` (insert after the reuse-dropdown block at ~L15455, inside the same attachment `with` area)

- [ ] **Step 1: Insert the picker block**

Find the end of the reuse-dropdown block (`flowdrip_app.py:15446-15455`):

```python
                    # Secondary: pick from already-generated PDFs (collapsed by default)
                    if _reusable_pdfs:
                        _att_options = {"": f"Or reuse a generated PDF ({len(_reusable_pdfs)} available)...",
                                        **{p.name: p.name for p in _reusable_pdfs}}
                        def _add_att(e, idx=active):
                            if e.value:
                                steps[idx].setdefault("attachments", []).append(e.value)
                                rf()
                        ui.select(options=_att_options, value="", on_change=_add_att).style(
                            "width:100%;font-size:12px;margin-top:8px;")
```

Insert immediately AFTER it (same indentation level):

```python
                    # Candidate Résumés — only on candidate emails (the email
                    # actually features candidate profiles). Lists the redacted
                    # résumés in the user's PDF folder not yet attached to this
                    # step, each with View (preview in a new tab) + Attach. Never
                    # auto-attached. See spec 2026-06-22-candidate-resume-picker.
                    _resume_files = [p for p in available_pdfs
                                     if _is_redacted_resume_pdf(p.name)
                                     and p.name not in step_atts]
                    if _resume_files and _step_features_candidates(steps[active]):
                        ui.label("Candidate résumés").style(
                            f"font-size:11px;font-weight:700;color:{C['muted']};"
                            f"margin-top:12px;text-transform:uppercase;"
                            f"letter-spacing:0.5px;")
                        for _rp in _resume_files:
                            with ui.element("div").style(
                                    "display:flex;align-items:center;gap:10px;"
                                    f"padding:7px 12px;margin-top:6px;"
                                    f"background:{C['card']};"
                                    f"border:1px solid {C['email_col']}30;"
                                    "border-radius:8px;"):
                                ui.label("📄").style("font-size:15px;")
                                ui.label(_redacted_resume_label(_rp.name)).style(
                                    f"font-size:12px;font-weight:500;"
                                    f"color:{C['email_col']};flex:1;")
                                with ui.link(target=f"/pdfs/{_rp.name}",
                                             new_tab=True).style(
                                        "text-decoration:none;font-size:11px;"
                                        f"color:{C['muted']};white-space:nowrap;"):
                                    ui.label("👁 View")
                                def _attach_resume(name=_rp.name, idx=active):
                                    steps[idx].setdefault(
                                        "attachments", []).append(name)
                                    try:
                                        save_campaign(camp)
                                    except Exception as _ex:
                                        print(f"[Attach] save_campaign failed: {_ex}",
                                              flush=True)
                                    rf()
                                with ui.element("button").style(
                                        f"background:{C['email_col']};color:{C['bg']};"
                                        "border:none;border-radius:6px;padding:4px 12px;"
                                        "font-size:11px;font-weight:700;cursor:pointer;"
                                        "font-family:inherit;white-space:nowrap;"
                                        ).on("click", _attach_resume):
                                    ui.label("＋ Attach")
```

- [ ] **Step 2: Smoke-check import**

Run: `python -c "import flowdrip_app"`
Expected: no output, exit 0

- [ ] **Step 3: Full test run**

Run: `python -m pytest tests/test_candidate_resume_picker.py -v`
Expected: PASS (all)

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(resume-picker): render Candidate Résumés view+attach picker on candidate emails"
```

---

### Task 6: Deploy & verify live

- [ ] **Step 1: Deploy** (per project policy — zero-downtime)

Run: `bash _deploy_zero_downtime.sh`
Expected: deploy completes; live `/` returns 200.

- [ ] **Step 2: Manual verification**

Generate (or open) a 4x4. On **Email 2** (candidate email): the "Candidate
résumés" section lists each redacted résumé with 👁 View + ＋ Attach. View opens
the PDF in a new tab. Attach moves it into the normal attachment chip list above
and removes it from the picker. On **Email 1** (market email): no section appears.

---

## Notes for the implementer

- `ST` is the step-type constants object already imported in `flowdrip_app.py`
  (`ST.EMAIL_AUTO`, `ST.EMAIL_MANUAL`). `re` is already imported. `C` is the theme
  color dict; `_user_pdf_dir`, `save_campaign`, `camp`, `steps`, `active`,
  `step_atts`, `rf`, and `available_pdfs` are all already in scope at the
  insertion point (Task 5).
- The picker reuses the existing secure `/pdfs/{filename}` route — do NOT add a
  new route; that route already scopes to the requesting user's folder.

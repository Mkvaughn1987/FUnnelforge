# Contacts-First AICB Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the AICB wizard so that picking Target a Company or Target a Market lands the user on a new **Step 2 — Upload contact list**; AI infers company/market details from the CSV; user reviews on a new **Step 3 — Confirm details** before continuing.

**Architecture:** All changes are in `flowdrip_app.py` inside the `p_ai_campaign` wizard renderer. A new sub-mode field `aicb_step2_mode` ("upload" | "manual") gates which UI Step 2 shows, and the existing website+Autofill page becomes the `"manual"` fallback reachable via a `No CSV yet?` link. Existing AI infrastructure (`_analyze_contacts_with_ai`, `_on_upload`, `_normalize_rows`, `safe_read_csv_rows`, all field pickers) is reused — not duplicated. Two pure helpers (`_aicb_clamp_wizard_step`, `_aicb_is_multi_company`) get TDD coverage.

**Tech Stack:** Python 3.11, NiceGUI 3.9, Anthropic Claude SDK, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-31-contacts-first-aicb-wizard-design.md`

---

## File Structure

- `flowdrip_app.py` — only file modified. Specific touch points:
  - `AppState.__init__` — one new field.
  - `_AICB_PERSISTED_FIELDS` — one new entry.
  - Two new module-level pure helpers (`_aicb_clamp_wizard_step`, `_aicb_is_multi_company`) placed next to `_aicb_apply_extracted` (~line 28980).
  - Wizard step clamping at `~line 16823` and `~line 30825`.
  - Top + bottom Next/Back handlers (`~30883-30907`, `~30958-30976`).
  - Step-pill list at `~line 30986`.
  - Step-render switch (`_show_step1`..`_show_step5` at `~31033-31037`).
  - Inline step 2 (Target Details) rendering — wrapped in a sub-mode branch.
  - New Step 3 (Confirm) inline renderer block.
  - Final-step setters (`s.aicb_wizard_step = 5` at `~30976`, `~32143`).
- `tests/test_aicb_wizard_helpers.py` — NEW, covers the two pure helpers.

---

## Task 1: Pure helpers + AppState field + persistence

**Files:**
- Modify: `flowdrip_app.py` (add helpers near line 28980; add field in `AppState.__init__` ~9462; add to `_AICB_PERSISTED_FIELDS` ~9801)
- Test: `tests/test_aicb_wizard_helpers.py` (NEW)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_aicb_wizard_helpers.py`:

```python
"""Pure-function tests for the contacts-first AICB wizard restructure.

Spec: docs/superpowers/specs/2026-05-31-contacts-first-aicb-wizard-design.md

These helpers live in flowdrip_app.py's UI layer but are broken out
as pure functions so the wizard logic stays testable without a
NiceGUI harness. The wizard step count grew from 5 to 6 when we
inserted Upload + Confirm between Target type and Candidates.
"""
import flowdrip_app as fa


def test_clamp_valid_steps():
    """Valid step numbers (1..6) pass through unchanged."""
    for n in (1, 2, 3, 4, 5, 6):
        assert fa._aicb_clamp_wizard_step(n) == n


def test_clamp_invalid_falls_back_to_one():
    """Anything outside 1..6 falls back to 1 — same defensive default
    as the pre-restructure clamp at line 16823."""
    for bad in (0, -1, 7, 99, None, "two", ""):
        assert fa._aicb_clamp_wizard_step(bad) == 1


def test_is_multi_company_true_when_company_empty_and_niche_filled():
    """The AI extractor returns empty 'company' + populated 'niche'
    when it sees multiple companies in the contact list. That's the
    signal that drives the Target-a-Company multi-company banner."""
    assert fa._aicb_is_multi_company({
        "company": "",
        "niche": "Colorado Manufacturing",
    }) is True
    assert fa._aicb_is_multi_company({
        "company": "   ",
        "niche": "Denver Healthcare Construction",
    }) is True


def test_is_multi_company_false_when_company_present():
    """A single-company CSV makes the extractor return a company name.
    Banner should NOT show."""
    assert fa._aicb_is_multi_company({
        "company": "Acme Corp",
        "niche": "",
    }) is False
    assert fa._aicb_is_multi_company({
        "company": "Acme Corp",
        "niche": "Manufacturing",  # both set: still single-company
    }) is False


def test_is_multi_company_false_when_niche_also_empty():
    """If both are empty, AI failed to identify anything — not a
    multi-company signal. Banner stays hidden; user fills manually."""
    assert fa._aicb_is_multi_company({"company": "", "niche": ""}) is False
    assert fa._aicb_is_multi_company({}) is False
    assert fa._aicb_is_multi_company(None) is False


def test_appstate_has_step2_mode_default_upload():
    """Fresh AppState must initialize aicb_step2_mode = 'upload' so the
    new wizard branches into the Upload UI by default. Without this
    default, Step 2 would render nothing and break the wizard."""
    s = fa.AppState()
    assert s.aicb_step2_mode == "upload"


def test_appstate_step2_mode_in_persisted_fields():
    """A WS reconnect mid-wizard must restore whichever sub-mode the
    user was on (upload vs manual). Otherwise reconnecting mid-manual
    bounces them back to Upload."""
    assert "aicb_step2_mode" in fa._AICB_PERSISTED_FIELDS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_aicb_wizard_helpers.py -v`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_aicb_clamp_wizard_step'` (and similar for the other helpers / field).

- [ ] **Step 3: Add the new AppState field**

Use Grep to locate `self.aicb_wizard_step = 1` (around line 9462). Use Edit to insert AFTER that line (and after `self.aicb_wizard_mode = "wizard"`):

```python
        # Sub-mode for Step 2 of the wizard, 2026-05-31:
        #   "upload" — show the new Upload Contact List UI (default).
        #   "manual" — show the legacy website + Autofill UI (reachable
        #              via the "No CSV yet? Enter details manually →"
        #              link on the Upload screen).
        self.aicb_step2_mode = "upload"
```

- [ ] **Step 4: Add the field to `_AICB_PERSISTED_FIELDS`**

Grep for `_AICB_PERSISTED_FIELDS = (` (around line 9801). Read the tuple, then use Edit to add `"aicb_step2_mode",` to the AICB-block section. Find the line `"aicb_target_mode",` (the closely related target-mode flag) and insert immediately after it:

```python
    "aicb_target_mode",
    "aicb_step2_mode",
```

- [ ] **Step 5: Add the two pure helpers**

Grep for `def _aicb_apply_extracted` to find a good neighbor location. Use Edit to insert ABOVE that function (so the helpers come before the code that uses them):

```python
def _aicb_clamp_wizard_step(n) -> int:
    """Coerce a wizard-step value to a valid 1..6 step number.

    Bumped from 1..5 → 1..6 when Upload + Confirm were inserted between
    Target type and Candidates (2026-05-31). Anything invalid falls
    back to step 1, the safe wizard entry point — matches the pre-
    restructure defensive behavior.
    """
    try:
        v = int(n)
    except (TypeError, ValueError):
        return 1
    return v if v in (1, 2, 3, 4, 5, 6) else 1


def _aicb_is_multi_company(extractor_result: dict) -> bool:
    """True if AI's contact-list analysis indicates multiple companies.

    Used in Target-a-Company mode to surface a "switch to Target a
    Market?" banner on the Confirm step. The shape comes from
    _analyze_contacts_with_ai's JSON: empty `company` + non-empty
    `niche` means the model couldn't pick a single account because
    the list spans multiple. Both empty means AI couldn't identify
    anything — that's NOT multi-company, just unidentified.
    """
    if not isinstance(extractor_result, dict):
        return False
    company = (extractor_result.get("company") or "").strip()
    niche = (extractor_result.get("niche") or "").strip()
    return (not company) and bool(niche)
```

- [ ] **Step 6: Update the two existing clamp sites to use the helper**

Grep for `s.aicb_wizard_step = _ws if _ws in (1, 2, 3, 4, 5) else 1` (around line 16823). Use Edit to replace those two lines:

```python
                _ws = int(getattr(s, "aicb_wizard_step", 1) or 1)
                s.aicb_wizard_step = _ws if _ws in (1, 2, 3, 4, 5) else 1
```

with:

```python
                s.aicb_wizard_step = _aicb_clamp_wizard_step(
                    getattr(s, "aicb_wizard_step", 1))
```

Then grep for `if _wiz_step not in (1, 2, 3, 4, 5):` (around line 30825). Replace the two-line block:

```python
        _wiz_step = int(getattr(s, "aicb_wizard_step", 1) or 1)
        if _wiz_step not in (1, 2, 3, 4, 5):
            _wiz_step = 1
```

with:

```python
        _wiz_step = _aicb_clamp_wizard_step(
            getattr(s, "aicb_wizard_step", 1))
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_aicb_wizard_helpers.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 8: Syntax check**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add flowdrip_app.py tests/test_aicb_wizard_helpers.py
git commit -m "feat(aicb): add wizard helpers + aicb_step2_mode for contacts-first wizard"
```

---

## Task 2: Renumber existing wizard steps 3→4, 4→5, 5→6

After this task the wizard internally accepts steps 1..6 with the OLD steps 3/4/5 sitting at 4/5/6. Steps 2 and 3 (Upload, Confirm) will be empty/passthrough until Tasks 3-5 fill them in — that's intentional. The user can still complete a campaign via the legacy manual flow throughout because Task 6 will set `aicb_step2_mode = "manual"` as a fallback during this transition. **However, this commit leaves the wizard temporarily broken (Step 2 has no renderer yet); don't deploy between tasks.**

**Files:**
- Modify: `flowdrip_app.py` — Next handler at `~30907`, top validator branches at `~30868-30881`, bottom validator at `~30898-30906`, step-pill list at `~30986`, render-branch flags at `~31033-31037`, final-step setters at `~30976` and `~32143`.

- [ ] **Step 1: Update the step-pill list**

Grep for `(3, "Candidates"),` to locate the list around line 30986. Read the surrounding lines, then use Edit to replace:

```python
            _steps = [
                (1, "Target type"),
                (2, "Target details"),
                (3, "Candidates"),
                (4, "Campaign style"),
                (5, "Review & generate"),
            ]
```

with:

```python
            _steps = [
                (1, "Target type"),    # pre-set by chooser; never the active pill in practice
                (2, "Upload"),         # NEW 2026-05-31 — Upload contact list
                (3, "Confirm"),        # NEW 2026-05-31 — Confirm AI-inferred details
                (4, "Candidates"),
                (5, "Campaign style"),
                (6, "Review & generate"),
            ]
```

- [ ] **Step 2: Bump the Next-handler advance cap**

Grep for `s.aicb_wizard_step = min(5, _wiz_step + 1)` (around line 30907). Read the surrounding `_top_wiz_next` block, then use Edit to replace ONLY the assignment line:

```python
            s.aicb_wizard_step = min(5, _wiz_step + 1)
```

with:

```python
            s.aicb_wizard_step = min(6, _wiz_step + 1)
```

- [ ] **Step 3: Renumber the top-validator branches for Candidates / Style**

Grep for `elif _wiz_mode == "wizard" and _wiz_step == 3:` (around line 30872). Read the context, then use Edit to update the step numbers in this block:

```python
        elif _wiz_mode == "wizard" and _wiz_step == 3:
            # Step 3 (Candidates): just need a source picked. Roles are
            # auto-fetched by the Auto-generate flow and derived from
            # picks in the Pool flow; manual entry was removed
            # 2026-04-26.
            _top_next_ok = bool(getattr(s, "aicb_cand_source", ""))
        elif _wiz_mode == "wizard" and _wiz_step == 4:
            _top_next_ok = bool((getattr(s, "aicb_camp_type", "") or "").strip())
```

becomes:

```python
        elif _wiz_mode == "wizard" and _wiz_step == 3:
            # Step 3 (Confirm details): user reviews AI-pre-filled
            # company/market info. Required: Primary Industry + either
            # company (company mode) or niche/secondary (market mode).
            _top_next_ok = _step2_target_filled()
        elif _wiz_mode == "wizard" and _wiz_step == 4:
            # Step 4 (Candidates): just need a source picked.
            _top_next_ok = bool(getattr(s, "aicb_cand_source", ""))
        elif _wiz_mode == "wizard" and _wiz_step == 5:
            _top_next_ok = bool((getattr(s, "aicb_camp_type", "") or "").strip())
```

(Note: Step 3 reuses the existing `_step2_target_filled()` validator because Confirm validates the same fields the old Target Details step did.)

- [ ] **Step 4: Renumber the bottom-validator branches**

Grep for `elif _wiz_step == 3:` (around line 30898 — the bottom Next handler, inside `_top_wiz_next`). Read the block, then use Edit to replace:

```python
            elif _wiz_step == 3:
                if not getattr(s, "aicb_cand_source", ""):
                    ui.notify("Pick how to add candidates first.",
                              type="warning")
                    return
            elif _wiz_step == 4:
                if not (getattr(s, "aicb_camp_type", "") or "").strip():
                    ui.notify("Pick a sequence style.", type="warning")
                    return
```

with:

```python
            elif _wiz_step == 3:
                # Confirm step: validate same fields as old Target Details
                if not _step2_target_filled():
                    _m = getattr(s, "aicb_target_mode", "company") or "company"
                    if not _step2_primary_industry_filled():
                        ui.notify("Pick a Primary Industry.", type="warning")
                    elif _m == "company" and not (s.aicb_company or "").strip():
                        ui.notify("Enter a company name.", type="warning")
                    else:
                        ui.notify("Pick a sub-niche or secondary industry.", type="warning")
                    return
            elif _wiz_step == 4:
                if not getattr(s, "aicb_cand_source", ""):
                    ui.notify("Pick how to add candidates first.",
                              type="warning")
                    return
            elif _wiz_step == 5:
                if not (getattr(s, "aicb_camp_type", "") or "").strip():
                    ui.notify("Pick a sequence style.", type="warning")
                    return
```

- [ ] **Step 5: Renumber render-branch flags**

Grep for `_show_step1 = _wiz_mode == "expanded" or _wiz_step == 1` (around line 31033). Read the 5-flag block, then use Edit to replace:

```python
        _show_step1 = _wiz_mode == "expanded" or _wiz_step == 1  # target type chooser
        _show_step2 = _wiz_mode == "expanded" or _wiz_step == 2  # target details form
        _show_step3 = _wiz_mode == "expanded" or _wiz_step == 3  # candidates (NEW)
        _show_step4 = _wiz_mode == "expanded" or _wiz_step == 4  # campaign style
        _show_step5 = _wiz_mode == "expanded" or _wiz_step == 5  # review + generate
```

with:

```python
        _show_step1 = _wiz_mode == "expanded" or _wiz_step == 1  # target type chooser
        _show_step2 = _wiz_mode == "expanded" or _wiz_step == 2  # NEW: Upload contact list
        _show_step3 = _wiz_mode == "expanded" or _wiz_step == 3  # NEW: Confirm AI-inferred details
        _show_step4 = _wiz_mode == "expanded" or _wiz_step == 4  # candidates (was step 3)
        _show_step5 = _wiz_mode == "expanded" or _wiz_step == 5  # campaign style (was step 4)
        _show_step6 = _wiz_mode == "expanded" or _wiz_step == 6  # review + generate (was step 5)
```

- [ ] **Step 6: Update the existing render-branch checks for Candidates / Style / Review**

The render branches in `p_ai_campaign` that key off `_show_step3`, `_show_step4`, `_show_step5` currently render Candidates / Campaign Style / Review respectively. After the renumber, those branches should read `_show_step4`, `_show_step5`, `_show_step6`.

Grep for `_show_step3` and `_show_step4` and `_show_step5` to find every usage. Update each occurrence INSIDE `p_ai_campaign` that renders Candidates → use `_show_step4`. Campaign Style → use `_show_step5`. Review → use `_show_step6`.

For each replacement: read 3 lines of context to confirm which step the block renders, then use Edit with a context-rich `old_string` so the right occurrence is targeted (each `_show_stepN` usage appears once).

Example: a block that begins with `if _show_step3:` and contains `Candidates` should be replaced so the `if` reads `if _show_step4:`. Same shape for Style and Review.

- [ ] **Step 7: Bump the final-step setters**

Grep for `s.aicb_wizard_step = 5` (finds the two assignments at ~30976 and ~32143). Read each context. Each one currently jumps to the final Review step (Generate handler / explicit advance). Use Edit on each:

```python
                    s.aicb_wizard_step = 5
```

becomes:

```python
                    s.aicb_wizard_step = 6
```

(Both occurrences. If `Edit` rejects due to non-uniqueness, supply more context — the surrounding lines differ.)

- [ ] **Step 8: Syntax check**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 9: Confirm helper tests still pass**

Run: `python -m pytest tests/test_aicb_wizard_helpers.py -v`
Expected: PASS (regression guard — the helpers should be unaffected).

- [ ] **Step 10: Commit**

```bash
git add flowdrip_app.py
git commit -m "refactor(aicb): renumber wizard steps 3-5 to 4-6 to make room for upload+confirm"
```

---

## Task 3: Step 2 sub-mode dispatch + manual fallback

Wires `aicb_step2_mode` into the renderer: when `"manual"`, render the existing Target Details (website + Autofill) UI; when `"upload"`, render a placeholder ("Upload UI coming in Task 4"). After this task the wizard is reachable via both sub-modes; Task 4 fills the upload UI in.

**Files:**
- Modify: `flowdrip_app.py` — wrap the existing `if _show_step2:` Target Details block in a sub-mode branch.

- [ ] **Step 1: Find the existing Step 2 render block**

Grep for `ui.label("Target Details").style(` (around line 31402). Read 6 lines before and 6 lines after to identify the start of the `if _show_step2:` block. Note the exact line numbers and indentation.

- [ ] **Step 2: Wrap Step 2's body with a sub-mode branch**

Use Edit to insert ABOVE the `ui.label("Target Details")` line (still inside `if _show_step2:`), a sub-mode guard. The cleanest insertion point is right after `if _show_step2:` opens its body — call the new sub-mode helper line first:

Specifically, change the structure from:

```python
            if _show_step2:
                # ... existing Target Details rendering ...
                ui.label("Target Details").style(
                    ...
                )
                # ... rest of the existing block ...
```

to:

```python
            if _show_step2:
                _step2_mode = getattr(s, "aicb_step2_mode", "upload") or "upload"
                if _step2_mode == "upload":
                    _render_step2_upload(s, rf)
                else:
                    # Manual fallback path (aicb_step2_mode == "manual") —
                    # reaches the existing website + Autofill UI.
                    ui.label("Target Details").style(
                        ...
                    )
                    # ... rest of the existing block ...
```

Concretely:
- Use Read on the exact lines from Step 1 to capture the existing `if _show_step2:` body.
- Use Edit with `old_string` = `            if _show_step2:` and `new_string`:

```python
            if _show_step2:
                _step2_mode = getattr(s, "aicb_step2_mode", "upload") or "upload"
                if _step2_mode == "upload":
                    _render_step2_upload(s, rf)
                else:
```

This inserts the sub-mode guard above the existing body. Because the original body was at a certain indent (e.g. 16 spaces inside `if _show_step2:`), increase its indent by 4 spaces to live inside `else:`. The cleanest mechanical way: don't try to re-indent the whole body in one Edit; instead use a Python script to add 4 spaces of indent to each line from the original Target-Details block.

If a precise multi-line Edit is impractical (the block is long), insert the sub-mode dispatch and a single-line `pass` stub above the existing Target Details body, then in a follow-up Edit indent the existing body inside `else:`. Either way, the end state is: `else:` followed by the original Target Details body, each line shifted right by 4 spaces.

- [ ] **Step 3: Define a stub `_render_step2_upload`**

Grep for `def _aicb_apply_extracted` (Task 1 inserted helpers above it). Use Edit to insert ABOVE `def _aicb_apply_extracted` (so the stub is module-level, callable from `p_ai_campaign`):

```python
def _render_step2_upload(s, rf):
    """Step 2 — Upload contact list (placeholder; filled in Task 4).

    Renders a temporary message so the wizard remains navigable while
    the rest of the contacts-first migration lands."""
    from nicegui import ui as _ui  # local import for clarity in this stub
    _ui.label("Upload step coming next — switch to manual entry for now.").style(
        "font-size:13px;color:#8FA3C8;margin-bottom:10px;")
    def _go_manual():
        s.aicb_step2_mode = "manual"
        rf()
    with _ui.element("button").classes("fd-gb").style(
            "padding:8px 16px;font-size:12px;").on("click", _go_manual):
        _ui.label("No CSV yet? Enter details manually →").style(
            "pointer-events:none;")
```

(The stub stays in place until Task 4 replaces it with the real upload UI; the `_go_manual` handler is the same one the real UI uses, so we keep it.)

- [ ] **Step 4: Make the Back button on the manual sub-mode return to Upload**

Grep for the existing Back button on Step 2 (likely in the same block as the inline target-details rendering). When pressed in manual sub-mode, it should reset `aicb_step2_mode` to `"upload"` instead of decrementing the wizard step.

Find a Step 2 Back handler — likely in the bottom-of-wizard nav. If it exists with logic like `s.aicb_wizard_step = max(1, _wiz_step - 1)`, update it to first check sub-mode:

```python
            def _wiz_back():
                if _wiz_step == 2 and getattr(s, "aicb_step2_mode", "upload") == "manual":
                    s.aicb_step2_mode = "upload"
                    rf()
                    return
                s.aicb_wizard_step = max(1, _wiz_step - 1)
                rf()
```

If the existing Back handler is shaped differently, adapt the same intent: in manual sub-mode on step 2, Back goes to the Upload screen (sub-mode flip), not Step 1. Grep for `_wiz_back` or `aicb_wizard_step = max(1` to locate it.

- [ ] **Step 5: Syntax check**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 6: Confirm helper tests still pass**

Run: `python -m pytest tests/test_aicb_wizard_helpers.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(aicb): branch step 2 on aicb_step2_mode (upload vs manual)"
```

---

## Task 4: Step 2 Upload UI — drop zone, analyze, auto-advance

Replaces the Task-3 stub with the real Upload UI. Drop zone uses the same building blocks as the existing chooser-page upload widget at ~line 30734.

**Files:**
- Modify: `flowdrip_app.py` — replace the `_render_step2_upload` stub from Task 3 with the full implementation.

- [ ] **Step 1: Replace `_render_step2_upload` with the full implementation**

Grep for `def _render_step2_upload(s, rf):` (defined in Task 3). Use Edit to replace the entire stub function with:

```python
def _render_step2_upload(s, rf):
    """Step 2 — Upload contact list. Drop a CSV; AI extracts company /
    market / industry / location / roles in the background; wizard
    advances to Step 3 (Confirm) when extraction returns.

    Reuses _on_upload-style file handling (size cap, sanitized path,
    safe_read_csv_rows, _normalize_rows) and the existing
    _analyze_contacts_with_ai background helper. No new AI work — just
    wiring.
    """
    from nicegui import ui as _ui
    import asyncio as _asyncio
    import threading as _threading

    # Header
    _ui.label("Upload your contact list").style(
        "font-size:18px;font-weight:700;color:#F0F8FF;"
        "font-family:'Nunito',sans-serif;margin-bottom:4px;")
    _ui.label(
        "Drop a CSV of the contacts you want to reach out to. AI reads "
        "the list and figures out the company / market, industry, and "
        "locations for you."
    ).style(
        "font-size:12.5px;color:#8FA3C8;line-height:1.55;"
        "margin-bottom:16px;max-width:680px;")

    # Spinner state during analysis
    if getattr(s, "_aicb_upload_analyzing", False):
        with _ui.element("div").classes("fd-gc").style(
                "background:rgba(26,227,217,0.06);"
                "border:1px solid rgba(26,227,217,0.25);"
                "text-align:center;padding:28px;margin-bottom:14px;"):
            _ui.spinner("dots", size="42px", color="#1AE3D9")
            _ui.label(
                "Analyzing your contacts…"
            ).style(
                "font-size:13px;font-weight:600;color:#1AE3D9;"
                "margin-top:10px;")
            _ui.label(
                f"{len(s.aicb_contacts or [])} contacts loaded · "
                "extracting industry, locations, and roles."
            ).style(
                "font-size:11px;color:#8FA3C8;margin-top:4px;")
        # Poll for completion — when bg thread flips the flag, jump to step 3.
        async def _poll():
            while getattr(s, "_aicb_upload_analyzing", False):
                await _asyncio.sleep(1.5)
            s.aicb_wizard_step = 3
            rf()
        _asyncio.ensure_future(_poll())
        return

    # Drop zone
    async def _on_step2_upload(e):
        try:
            content = await e.file.read()
        except Exception:
            _ui.notify("Upload failed.", type="negative"); return
        if not content:
            _ui.notify("Empty CSV file.", type="warning"); return
        if len(content) > _MAX_CSV_BYTES:
            _ui.notify("CSV too large (50 MB max).", type="negative"); return
        tmp = _safe_attachment_path(
            f"_aicb_upload_{e.file.name or 'contacts.csv'}",
            _user_pdf_dir(), _ALLOWED_CSV_EXTS, fallback="contacts",
        )
        if tmp is None:
            _ui.notify("Upload must be a .csv, .tsv, or .txt file.",
                       type="negative")
            return
        tmp.write_bytes(content)
        raw_rows, _warnings = safe_read_csv_rows(str(tmp))
        if not raw_rows:
            _ui.notify("No contacts found in this file.", type="warning")
            return
        rows = _normalize_rows(raw_rows)
        s.aicb_contacts = rows
        s._aicb_upload_analyzing = True
        _ui.notify(f"Loaded {len(rows)} contacts — analyzing…",
                   type="info")

        def _run_analysis():
            try:
                _analyze_contacts_with_ai(rows)
            finally:
                s._aicb_upload_analyzing = False

        _threading.Thread(target=_run_analysis, daemon=True).start()
        rf()

    with _ui.element("div").style(
            "border:1.5px dashed #2E3D7A;border-radius:10px;"
            "padding:28px 22px;text-align:center;background:#243264;"
            "margin-bottom:12px;"):
        _ui.upload(on_upload=_on_step2_upload, auto_upload=True,
                   label="Click to browse, or drop a CSV here").style(
            "max-width:520px;margin:0 auto;")
        _ui.label(
            "Accepted: .csv, .tsv, .txt — up to 50 MB."
        ).style(
            "font-size:11px;color:#8FA3C8;margin-top:8px;")

    # Fallback link
    def _go_manual():
        s.aicb_step2_mode = "manual"
        rf()
    with _ui.element("div").style(
            "text-align:center;margin-top:6px;"):
        with _ui.element("span").style(
                "cursor:pointer;font-size:12px;color:#1AE3D9;"
                "text-decoration:underline;"
                ).on("click", _go_manual):
            _ui.label("No CSV yet? Enter details manually →")
```

- [ ] **Step 2: Add the `_aicb_upload_analyzing` flag to `AppState` defaults**

Grep for `self.aicb_step2_mode = "upload"` (from Task 1). Use Edit to insert after it:

```python
        # Transient flag set while the Step-2 upload analyzer is running.
        # Not persisted — every reconnect re-renders the spinner state
        # from scratch.
        self._aicb_upload_analyzing = False
```

- [ ] **Step 3: Syntax check**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Manual smoke test against the live AppState reset**

There's no automated test for this UI block. Sanity check that the renderer is module-level and callable:

```bash
python -c "
import flowdrip_app as fa
assert callable(fa._render_step2_upload), 'renderer must be a function'
s = fa.AppState()
assert s.aicb_step2_mode == 'upload'
assert s._aicb_upload_analyzing is False
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(aicb): Step 2 Upload UI — drop CSV, AI extracts, auto-advance to Confirm"
```

---

## Task 5: Step 3 Confirm renderer + multi-company banner

Renders Step 3 with the AI-pre-filled, editable form and the Target-a-Company multi-company guard banner.

**Files:**
- Modify: `flowdrip_app.py` — wire a new `if _show_step3:` block that calls a new `_render_step3_confirm` helper.

- [ ] **Step 1: Define `_render_step3_confirm`**

Grep for `def _render_step2_upload` (from Task 4). Use Edit to insert IMMEDIATELY AFTER its closing brace, a new helper:

```python
def _render_step3_confirm(s, rf):
    """Step 3 — Confirm AI-inferred campaign details.

    Shows the AI-pre-filled fields the Step-2 analyzer wrote
    (industry / locations / roles / company OR niche). User edits
    in place; clicking Next advances to Step 4 (Candidates).

    In Target-a-Company mode, if the analyzer signaled a multi-company
    list (via _aicb_is_multi_company), a yellow banner offers to
    switch to Target-a-Market or continue with a chosen primary
    company.
    """
    from nicegui import ui as _ui
    teal = "#1AE3D9"
    muted = "#8FA3C8"
    warn = "#F59E0B"
    text_l = "#F0F8FF"
    surface = "#243264"
    border = "#2E3D7A"
    mode = getattr(s, "aicb_target_mode", "company") or "company"

    # Header
    _ui.label("Confirm campaign details").style(
        f"font-size:18px;font-weight:700;color:{text_l};"
        f"font-family:'Nunito',sans-serif;margin-bottom:4px;")
    _ui.label(
        "AI pulled these from your contact list. Tweak anything that "
        "looks off, then click Next."
    ).style(
        f"font-size:12.5px;color:{muted};line-height:1.55;"
        f"margin-bottom:14px;max-width:680px;")

    # Stats strip: contact count + re-upload + re-run AI extraction
    _n = len(getattr(s, "aicb_contacts", []) or [])
    with _ui.element("div").style(
            f"display:flex;align-items:center;gap:14px;flex-wrap:wrap;"
            f"font-size:12px;color:{muted};margin-bottom:14px;"):
        _ui.label(f"📋 {_n} contacts loaded")
        def _back_to_upload():
            s.aicb_wizard_step = 2
            s.aicb_step2_mode = "upload"
            rf()
        with _ui.element("span").style(
                f"cursor:pointer;color:{teal};text-decoration:underline;"
                ).on("click", _back_to_upload):
            _ui.label("re-upload")
        def _rerun_ai():
            rows = list(getattr(s, "aicb_contacts", []) or [])
            if not rows:
                _ui.notify("No contacts loaded — re-upload first.",
                           type="warning")
                return
            s._aicb_upload_analyzing = True
            import threading as _t
            def _run():
                try: _analyze_contacts_with_ai(rows)
                finally: s._aicb_upload_analyzing = False
            _t.Thread(target=_run, daemon=True).start()
            s.aicb_wizard_step = 2
            rf()
        with _ui.element("span").style(
                f"cursor:pointer;color:{teal};text-decoration:underline;"
                ).on("click", _rerun_ai):
            _ui.label("re-run AI extraction")

    # Multi-company guard (Target-a-Company mode only)
    _extracted = {
        "company": getattr(s, "aicb_company", "") or "",
        "niche":   getattr(s, "aicb_niche", "") or "",
    }
    if mode == "company" and _aicb_is_multi_company(_extracted):
        with _ui.element("div").style(
                f"background:{warn}15;border:1px solid {warn}55;"
                f"border-radius:8px;padding:14px 16px;margin-bottom:18px;"):
            _ui.label(
                "⚠ Looks like this list has multiple companies."
            ).style(
                f"font-size:13px;font-weight:700;color:{warn};")
            _ui.label(
                "Target a Company is built for one named account. Want "
                "to switch the campaign type, or pick a primary company "
                "to focus on?"
            ).style(
                f"font-size:11.5px;color:{text_l};margin-top:4px;"
                f"line-height:1.55;")
            with _ui.element("div").style(
                    "display:flex;gap:10px;margin-top:10px;flex-wrap:wrap;"):
                def _switch_to_market():
                    s.aicb_target_mode = "market"
                    rf()
                def _continue_company():
                    # Banner suppressed once the user starts typing a
                    # company name — handled implicitly because
                    # _aicb_is_multi_company returns False as soon as
                    # company is non-empty.
                    s.aicb_company = ""  # nudge the user to type one
                    rf()
                with _ui.element("button").classes("fd-pb").style(
                        "padding:6px 14px;font-size:12px;"
                        ).on("click", _switch_to_market):
                    _ui.label("Switch to Target a Market")
                with _ui.element("button").classes("fd-gb").style(
                        "padding:6px 14px;font-size:12px;"
                        ).on("click", _continue_company):
                    _ui.label("Continue with a primary company")

    # Editable form — mirrors the existing Target Details fields so
    # downstream code keeps reading the same state slots.
    if mode == "company":
        _ui.label("Company").classes("fd-fl")
        _co_in = _ui.input(
            value=getattr(s, "aicb_company", "") or "",
            placeholder="e.g. Acme Corp",
        ).classes("fd-input").style("width:100%;margin-bottom:10px;")
        _co_in.on("blur", lambda: setattr(
            s, "aicb_company", (_co_in.value or "").strip()))

        _ui.label("Website").classes("fd-fl")
        _web_in = _ui.input(
            value=getattr(s, "aicb_website", "") or "",
            placeholder="e.g. acmecorp.com",
        ).classes("fd-input").style("width:100%;margin-bottom:12px;")
        _web_in.on("blur", lambda: setattr(
            s, "aicb_website", (_web_in.value or "").strip()))
    else:
        # market mode
        _ui.label("Niche / market").classes("fd-fl")
        _ui.label(
            "Short description AI uses when writing emails (e.g. "
            "\"Colorado Manufacturing\", \"Denver Healthcare Construction\")."
        ).style(
            f"font-size:10px;color:{muted};margin-bottom:4px;margin-top:-2px;")
        _ni_in = _ui.input(
            value=getattr(s, "aicb_niche", "") or "",
            placeholder="e.g. Colorado Manufacturing",
        ).classes("fd-input").style("width:100%;margin-bottom:12px;")
        _ni_in.on("blur", lambda: setattr(
            s, "aicb_niche", (_ni_in.value or "").strip()))

    # Industry picker (reuses existing helper)
    if not hasattr(s, "aicb_secondary_industries"):
        s.aicb_secondary_industries = []
    _render_industry_picker(
        s, rf,
        primary_state_key="aicb_primary_industry",
        secondary_state_key="aicb_secondary_industries",
        container_style="margin-bottom:12px;",
        label_primary="Primary Industry",
        label_secondary="Secondary Industry",
        required_primary=True,
    )

    # Locations (chip picker — same control used on the manual page).
    # The location picker lives in p_ai_campaign as an inline render;
    # reuse via the existing _render_location_picker if available,
    # otherwise call the inline rendering inside p_ai_campaign. The
    # Confirm step does NOT re-implement chip pickers — it shares
    # them, OR (if extraction isn't tractable) renders the same
    # state-bound `_ui.select` / `_ui.input` controls bound to
    # s.aicb_sel_locations / s.aicb_sel_roles.
    _ui.label("Locations").classes("fd-fl")
    _loc_csv = ", ".join(getattr(s, "aicb_sel_locations", []) or [])
    _loc_in = _ui.input(
        value=_loc_csv,
        placeholder="e.g. Denver, CO; Boulder, CO",
    ).classes("fd-input").style("width:100%;margin-bottom:12px;")
    _loc_in.on("blur", lambda: setattr(
        s, "aicb_sel_locations",
        [x.strip() for x in (_loc_in.value or "").split(",") if x.strip()]))

    _ui.label("Roles").classes("fd-fl")
    _role_csv = ", ".join(getattr(s, "aicb_sel_roles", []) or [])
    _role_in = _ui.input(
        value=_role_csv,
        placeholder="e.g. Project Manager, Estimator",
    ).classes("fd-input").style("width:100%;margin-bottom:12px;")
    _role_in.on("blur", lambda: setattr(
        s, "aicb_sel_roles",
        [x.strip() for x in (_role_in.value or "").split(",") if x.strip()][:6]))
```

(Note: the Locations and Roles fields above use lightweight comma-separated inputs that bind to the same state slots the existing chip pickers use. If `_render_industry_picker` doesn't accept the keyword args shown, look at the existing call site (grep for `_render_industry_picker(` and use the SAME call shape — copy verbatim from the existing manual-mode invocation. Don't invent a new signature.)

- [ ] **Step 2: Wire `_show_step3` to call the new renderer**

Grep for `_show_step3 = _wiz_mode == "expanded" or _wiz_step == 3` (set in Task 2). Then grep for any existing `if _show_step3:` block — should be the renumbered Candidates branch from Task 2 — and confirm it now reads `if _show_step4:`. If it does, Step 3 currently has no renderer.

Find the natural location for Step 3 between the wrapped `if _show_step2:` block (Task 3) and the `if _show_step4:` block (renumbered Candidates). Use Edit to insert:

```python
            if _show_step3:
                _render_step3_confirm(s, rf)
```

at the right indentation (matching the surrounding `_show_stepN` block indents).

- [ ] **Step 3: Syntax check**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Confirm helper tests still pass**

Run: `python -m pytest tests/test_aicb_wizard_helpers.py -v`
Expected: PASS.

- [ ] **Step 5: Smoke test the renderer is callable**

```bash
python -c "
import flowdrip_app as fa
assert callable(fa._render_step3_confirm)
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(aicb): Step 3 Confirm — editable AI-inferred details + multi-company banner"
```

---

## Task 6: Full test sweep + manual verification

**Files:** none (verification only)

- [ ] **Step 1: Helper tests**

Run: `python -m pytest tests/test_aicb_wizard_helpers.py -v`
Expected: PASS (all 7).

- [ ] **Step 2: Full suite — regression check**

Run: `python -m pytest tests/ -q --tb=line`
Expected: No NEW failures vs. the baseline. Pre-existing failures unrelated to this work: `test_newsletter_cta_single_button.py` (3), `test_newsletter_masthead_fallback.py` (1). Anything else failing is a regression to fix.

- [ ] **Step 3: AST + import smoke**

```bash
python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read()); print('AST OK')"
python -c "import flowdrip_app as fa; assert fa._aicb_clamp_wizard_step(3) == 3; assert fa._aicb_is_multi_company({'company':'','niche':'X'}); print('IMPORT OK')"
```

Expected: `AST OK` then `IMPORT OK`.

- [ ] **Step 4: No commit unless one of the previous steps surfaced a fix**

If Steps 1-3 passed without fixes: nothing to commit at this task.

---

## Deployment (controller does this — not a plan step)

1. `bash _deploy_zero_downtime.sh` from the repo root; verify `https://dripdripdrop.ai/` returns HTTP 200 (real `/`, not just `/healthz`).
2. Manual smoke on live:
   - Click Target a Company → Upload screen renders. Drop a single-company CSV → spinner → Confirm screen pre-fills correctly. Tweak Industry → Next → Candidates step appears.
   - Click Target a Market → upload multi-company CSV → Confirm renders with Niche pre-filled; Company/Website hidden.
   - Target a Company + multi-company CSV → yellow banner appears. Click Switch to Target a Market → re-renders in market mode.
   - From Upload, click "No CSV yet? Enter details manually →" → existing website + Autofill UI renders. Type a URL, click Autofill → industry/locations populate. Next → Confirm step. Continue through Candidates / Style / Review.

---

## Self-Review

**Spec coverage:**
- Component 1 (`aicb_step2_mode` + persistence) → Task 1 ✓
- Step renumbering 1..5 → 1..6 (validator, Next/Back, header pills, render flags) → Task 2 ✓
- Step 2 sub-mode dispatch (upload vs manual fallback) → Task 3 ✓
- Step 2 Upload UI (drop zone, AI analyze, auto-advance) → Task 4 ✓
- Step 3 Confirm renderer (editable AI inferences, multi-company banner) → Task 5 ✓
- Manual fallback path reuses today's website+Autofill UI → Task 3 (the wrapper) + already-existing code (no change) ✓
- Pure helpers TDD-covered → Task 1 ✓
- Find Candidates / MPC untouched → not in any task (correct — out of scope) ✓
- Verification cases → Task 6 + Deployment section ✓

**Placeholder scan:** No TBD / TODO / "handle edge cases" / "similar to". Every code block is complete or directs the implementer to grep a specific anchor + edit verbatim. The one judgment call (extracting the existing Target Details body into the `else:` branch in Task 3) is explicit about acceptable strategies.

**Type/name consistency:**
- `_aicb_clamp_wizard_step(n) -> int` defined in Task 1, used by Tasks 2 (renumber clamp sites).
- `_aicb_is_multi_company(dict) -> bool` defined in Task 1, used in Task 5 (banner gate).
- `aicb_step2_mode` field defined in Task 1, branched on in Tasks 3 & 4.
- `_render_step2_upload(s, rf)` stubbed in Task 3, replaced in Task 4.
- `_render_step3_confirm(s, rf)` defined and wired in Task 5.
- `_aicb_upload_analyzing` set in Task 4's `_on_step2_upload`, polled in the spinner branch — same name throughout.
- Step numbers consistent: Upload=2, Confirm=3, Candidates=4, Style=5, Review=6 — every task uses the new numbering.

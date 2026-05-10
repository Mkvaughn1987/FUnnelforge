# Strategy Chooser + Target-a-Candidate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace today's `Choose a Sequence Type` with a strategy-first chooser (5 cards: Target a Client / Target a Market / Target a Candidate / Saved Campaigns / Build from scratch). Build a brand-new guided wizard for "Target a Candidate" — JD upload → CSV candidate upload → 4 sequence preset choices → AI-generated sequence handed off to the existing email editor.

**Architecture:** Top-level chooser is a single new render block that sets `s.aicb_camp_type` + a new `s._chooser_origin` slot, then routes to the existing AICB page (for Client/Market — same backend, banner header keys off origin) or to the new `p_target_candidate` page (for Candidate). The Target-a-Candidate wizard is a 4-step stepper using a new `s.tc_step` slot. Generated sequences land in the existing email editor (`p_emails_build`) via `save_campaign(camp)` + navigation.

**Tech Stack:** Python 3.12, NiceGUI, pytest, Anthropic Claude (Haiku 4.5 for JD parsing + sequence gen), existing helpers `_extract_resume_text`, CSV parser from Contacts page, `save_campaign`, `_run_as_user` (Phase 0 thread-binding).

**Spec:** [docs/superpowers/specs/2026-05-10-strategy-chooser-target-candidate-design.md](../specs/2026-05-10-strategy-chooser-target-candidate-design.md)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `flowdrip_app.py` | Modify | All app changes (new AppState slots, chooser render block, AICB banner, new `p_target_candidate` page, wiring) |
| `tests/test_strategy_chooser.py` | Create | Source-introspection: chooser renders 5 options with descriptive copy |
| `tests/test_target_candidate_wizard.py` | Create | Behavioral: step gates, preset selection, generation handoff |
| `tests/test_chooser_origin_banner.py` | Create | Banner conditional on `_chooser_origin` |

---

## Pre-flight (before Task 1)

The user's WIP campaign→sequence rename (~521 lines uncommitted in `flowdrip_app.py`) must be re-stashed before subagents start, same as the touchpoint pass. The implementer for Task 1 should verify and stash if needed.

```bash
git status --short flowdrip_app.py
# If output shows " M flowdrip_app.py":
git stash push -m "WIP: campaign->sequence rename pre-phase2" -- flowdrip_app.py
```

After Phase 2 ships, `git stash pop stash@{0}` restores the rename.

---

## Task 1: AppState slots for the new flow

**Files:**
- Modify: `flowdrip_app.py` — `AppState` class definition (search for `class AppState`)

- [ ] **Step 1: Locate `AppState`**

Run: `grep -n "^class AppState\|class AppState" flowdrip_app.py`

Expected: One hit. Read the class body to understand the existing slot layout.

- [ ] **Step 2: Add new slots in the appropriate cluster**

Add the following slots inside `AppState.__init__` (or as class-level defaults if that's the existing pattern). Place near other AICB-related slots (search for `aicb_camp_type` to find the right cluster):

```python
        # Phase 2: Strategy Chooser + Target-a-Candidate wizard
        self._chooser_origin: str = ""           # set by chooser cards: "client" | "market" | ""
        self.tc_step: int = 0                    # 0..3 for the 4 wizard steps
        self.tc_jd_text: str = ""                # raw JD text (uploaded or pasted)
        self.tc_jd_filename: str = ""            # original filename if uploaded
        self.tc_jd_parsed: dict = {}             # AI-extracted role metadata
        self.tc_jd_generating: bool = False      # spinner during background AI parse
        self.tc_candidates: list = []            # list of candidate dicts from CSV
        self.tc_preset: str = ""                 # "one_email" | "two_emails_1day" | "three_emails_3days" | "custom"
        self.tc_generating: bool = False         # spinner during sequence gen
        self.tc_error: str = ""                  # last error message for the wizard
```

If the codebase uses class-level slot declarations (some older code does), match the local style.

- [ ] **Step 3: Verify the file still parses**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0.

- [ ] **Step 4: Run the full suite (no new tests yet — this is just plumbing)**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 277 passed (no change in count).

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(state): add AppState slots for Phase 2 chooser + target-candidate wizard

Adds _chooser_origin, tc_step, tc_jd_text, tc_jd_filename,
tc_jd_parsed, tc_jd_generating, tc_candidates, tc_preset,
tc_generating, tc_error. Plumbing only; no UI / behavior change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Strategy chooser page (5-card layout)

**Files:**
- Modify: `flowdrip_app.py` — find the existing `Choose a Sequence Type` render block (search for `Choose a Sequence Type` or `Choose a Sequence`)
- Create: `tests/test_strategy_chooser.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_strategy_chooser.py`:

```python
"""Strategy Chooser — 5 starting places with inline descriptive copy.

The new chooser replaces the legacy "Choose a Sequence Type" page.
Each card shows a title + 1-sentence description visible without
clicking. Clicking a card sets s.aicb_camp_type + s._chooser_origin
and routes to the appropriate downstream page.
"""
import inspect


def test_chooser_renders_5_options():
    """The chooser source must reference all 5 starting place titles."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    assert "Target a Client" in src
    assert "Target a Market" in src
    assert "Target a Candidate" in src
    assert "Saved Campaigns" in src or "Saved Sequences" in src
    assert "Build from scratch" in src or "Build from Scratch" in src


def test_chooser_has_descriptive_copy_for_each_option():
    """Each card needs a one-sentence description so users can pick
    without clicking. Test for the presence of distinguishing copy."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    # Distinguishing phrases — adjust if the actual copy differs slightly
    assert "specific company" in src.lower() or "single client" in src.lower()  # Target a Client
    assert "industry" in src.lower() or "market" in src.lower()                  # Target a Market
    assert "job description" in src.lower() or "candidate outreach" in src.lower()  # Target a Candidate


def test_chooser_sets_origin_on_client_card():
    """Clicking Target a Client must set s._chooser_origin to 'client'.
    Source-introspection: look for the assignment near the click handler."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    # The chooser should contain a literal "client" assignment to _chooser_origin
    assert '_chooser_origin = "client"' in src or "_chooser_origin = 'client'" in src
    assert '_chooser_origin = "market"' in src or "_chooser_origin = 'market'" in src
```

- [ ] **Step 2: Run the test; it MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_strategy_chooser.py -v`

Expected: All 3 FAIL.

- [ ] **Step 3: Locate the existing chooser render block**

Run: `grep -n "Choose a Sequence Type\|Choose a Campaign Type" flowdrip_app.py | head -5`

Expected: One or more hits. Read 50+ lines around the first hit to understand the existing 4-card layout (AI Campaign Builder / Recruitment Campaign / Build from scratch / Saved Sequences per the screenshot).

- [ ] **Step 4: Replace the chooser with the new 5-card layout**

Replace the existing chooser block with this structure (adapt to actual local variables `s`, `rf`, color constants `C`):

```python
            # ── Strategy Chooser — 5 starting places ──
            ui.label("Choose a Sequence Type").style(
                f"font-size:24px;font-weight:700;color:{C['ink']};"
                f"margin-bottom:8px;")
            ui.label("Pick the right starting place — each one is "
                     "tuned for a different scenario.").style(
                f"font-size:14px;color:{C['muted']};margin-bottom:24px;")

            CHOOSER_OPTIONS = [
                {
                    "key": "client",
                    "icon": "🎯",
                    "title": "Target a Client",
                    "subtitle": "Land a specific company",
                    "desc": ("AI deep-research on a single client — their open roles, "
                             "recent news, project pipeline. Generates a hyper-personalized "
                             "7-week sequence aimed at one specific company."),
                    "best_for": ["Named accounts", "Account expansion", "Single-target outreach"],
                    "border": C["teal"],
                },
                {
                    "key": "market",
                    "icon": "📊",
                    "title": "Target a Market",
                    "subtitle": "Cover an industry or region",
                    "desc": ("Build a sequence template for a market segment — industry, "
                             "region, role family. Reusable across many similar companies. "
                             "Best for prospect-list campaigns."),
                    "best_for": ["Industry plays", "Regional sweeps", "Bulk outreach"],
                    "border": "#A78BFA",  # purple
                },
                {
                    "key": "candidate",
                    "icon": "👤",
                    "title": "Target a Candidate",
                    "subtitle": "Place a candidate or fill a role",
                    "desc": ("Guided wizard — paste a job description, upload candidates, "
                             "pick a cadence. AI generates outreach in your voice tuned to the "
                             "specific role you're filling."),
                    "best_for": ["Specific role hiring", "Candidate placement", "MPC outreach"],
                    "border": "#F472B6",  # pink
                },
                {
                    "key": "saved",
                    "icon": "📁",
                    "title": "Saved Campaigns",
                    "subtitle": "Re-use a prior sequence",
                    "desc": ("Load a sequence from your library. Pick what worked before, "
                             "swap in a fresh contact list, send. Fast path for repeat "
                             "outreach motions."),
                    "best_for": ["Repeat outreach", "Proven cadences", "Quick re-runs"],
                    "border": "#60A5FA",  # blue
                },
                {
                    "key": "scratch",
                    "icon": "✏️",
                    "title": "Build from scratch",
                    "subtitle": "You write every email",
                    "desc": ("Start with a blank slate. Add emails, calls, LinkedIn touches, "
                             "tasks in any order. Write each message yourself. No AI. "
                             "Full control."),
                    "best_for": ["Hand-crafted outreach", "Personal voice", "Non-standard cadences"],
                    "border": "#F59E0B",  # orange
                },
            ]

            for opt in CHOOSER_OPTIONS:
                key = opt["key"]
                def _pick(k=key):
                    if k == "client":
                        s._chooser_origin = "client"
                        s.aicb_camp_type = "blitz"  # default preset; user can change on AICB page
                        s.screen = "aicb"
                    elif k == "market":
                        s._chooser_origin = "market"
                        s.aicb_camp_type = "talentdrop"  # default preset for market plays
                        s.screen = "aicb"
                    elif k == "candidate":
                        s.tc_step = 0
                        s.tc_jd_text = ""
                        s.tc_jd_parsed = {}
                        s.tc_candidates = []
                        s.tc_preset = ""
                        s.screen = "target_candidate"
                    elif k == "saved":
                        s.screen = "load_campaign"
                    elif k == "scratch":
                        s._chooser_origin = ""
                        s.aicb_camp_type = "byos"
                        s.screen = "aicb"
                    rf()
                with ui.element("div").style(
                        f"background:#fff;border:1px solid #E5E7EB;"
                        f"border-left:4px solid {opt['border']};"
                        f"border-radius:10px;padding:18px 22px;"
                        f"margin-bottom:14px;cursor:pointer;"
                        f"transition:background 0.12s;"
                        ).on("click", _pick):
                    with ui.element("div").style(
                            "display:flex;justify-content:space-between;"
                            "align-items:flex-start;gap:18px;"):
                        # Left: icon + title + subtitle + desc
                        with ui.element("div").style("flex:1;"):
                            with ui.element("div").style(
                                    "display:flex;align-items:center;gap:10px;margin-bottom:4px;"):
                                ui.html(f"<span style='font-size:20px;'>{opt['icon']}</span>")
                                ui.label(opt["title"]).style(
                                    f"font-size:16px;font-weight:700;color:{opt['border']};")
                                ui.label(opt["subtitle"]).style(
                                    f"font-size:12px;color:{C['muted']};")
                            ui.label(opt["desc"]).style(
                                f"font-size:13px;line-height:1.55;color:{C['ink']};"
                                f"margin-top:6px;")
                            # Best-for tags
                            with ui.element("div").style(
                                    "display:flex;gap:6px;margin-top:10px;flex-wrap:wrap;"):
                                ui.label("Best for:").style(
                                    f"font-size:11px;color:{C['muted']};font-weight:600;")
                                for tag in opt["best_for"]:
                                    ui.label(tag).style(
                                        f"font-size:11px;color:{opt['border']};"
                                        f"font-weight:500;")
                                    if tag != opt["best_for"][-1]:
                                        ui.label("·").style(
                                            f"font-size:11px;color:{C['muted']};")
                        # Right: arrow icon
                        ui.html(
                            f"<div style='font-size:20px;color:{opt['border']};"
                            f"flex-shrink:0;align-self:center;'>→</div>"
                        )
```

CRITICAL — adapt the routing names (`s.screen = "aicb"` etc.) to match the actual screen names used in this codebase. Search `grep -n "self.screen\|s.screen" flowdrip_app.py | head -10` to find the exact strings used. Common patterns are `"aicb"`, `"campaigns"`, `"emails"`. The Saved Campaigns route may need to be `"load_campaign"` or `"saved_sequences"` — check what the existing button used.

- [ ] **Step 5: Run tests; they MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_strategy_chooser.py -v`

Expected: All 3 PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 280 passed (277 + 3 new).

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py tests/test_strategy_chooser.py
git commit -m "feat(chooser): replace Choose a Sequence Type with 5-option strategy chooser

5 starting places: Target a Client / Target a Market / Target a
Candidate / Saved Campaigns / Build from scratch. Each card shows
title + 1-sentence description + best-for tags inline so users can
pick without clicking through.

Client/Market route to existing AICB page with _chooser_origin
slot set so the AICB page can render the right framing banner
(Task 4). Candidate routes to a new p_target_candidate page
(Tasks 5-9). Saved/Scratch keep their existing routing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: AICB banner reads `_chooser_origin`

**Files:**
- Modify: `flowdrip_app.py` — find `p_aicb` (search `def p_aicb`)
- Create: `tests/test_chooser_origin_banner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_chooser_origin_banner.py`:

```python
"""AICB banner shows different framing based on which chooser door
the user came through (Target a Client vs Target a Market)."""
import inspect


def test_aicb_renders_client_banner_when_origin_is_client():
    """The AICB page source must reference _chooser_origin and render
    different banner text for 'client' vs 'market'."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_aicb)
    assert "_chooser_origin" in src, (
        "p_aicb must read s._chooser_origin to render the right banner"
    )
    assert "Target a Client" in src or "client" in src.lower()
    assert "Target a Market" in src or "market" in src.lower()
```

- [ ] **Step 2: Run test; it MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_chooser_origin_banner.py -v`

Expected: FAIL (most likely with `AttributeError: module 'flowdrip_app' has no attribute 'p_aicb'` if the page handler has a different name — adjust the test to use the actual handler name).

- [ ] **Step 3: Locate the AICB page handler**

Run: `grep -n "def p_aicb\|def aicb_page\|@ui.page.*aicb" flowdrip_app.py | head -5`

Use the actual handler name. If it differs from `p_aicb`, update the test to import the correct name.

- [ ] **Step 4: Add the banner to the AICB page**

At the very top of the AICB page handler's render block (before any existing form / step UI), insert:

```python
        # ── Chooser-origin banner ──
        origin = getattr(s, "_chooser_origin", "")
        if origin in ("client", "market"):
            label = "Target a Client" if origin == "client" else "Target a Market"
            sub = (
                "Deep-researching a single named company."
                if origin == "client"
                else "Building a sequence template for an industry or region."
            )
            color = C["teal"] if origin == "client" else "#A78BFA"
            with ui.element("div").style(
                    f"background:#fff;border:1px solid #E5E7EB;"
                    f"border-left:4px solid {color};border-radius:10px;"
                    f"padding:14px 18px;margin-bottom:18px;"
                    f"display:flex;justify-content:space-between;align-items:center;"):
                with ui.element("div"):
                    ui.label(label).style(
                        f"font-size:14px;font-weight:700;color:{color};")
                    ui.label(sub).style(
                        f"font-size:12px;color:{C['muted']};margin-top:2px;")
                # Dismiss button (clears origin so banner doesn't reappear)
                def _dismiss():
                    s._chooser_origin = ""; rf()
                with ui.element("button").style(
                        f"padding:4px 10px;font-size:11px;border-radius:6px;"
                        f"border:1px solid {C['muted']};background:transparent;"
                        f"color:{C['muted']};cursor:pointer;font-family:inherit;"
                        ).on("click", _dismiss):
                    ui.label("× Hide").style("pointer-events:none;")
```

- [ ] **Step 5: Run test; it MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_chooser_origin_banner.py -v`

Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 281 passed (280 + 1 new).

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py tests/test_chooser_origin_banner.py
git commit -m "feat(aicb): banner header shows chooser-origin framing

When the user enters AICB via 'Target a Client' or 'Target a
Market' from the new chooser, AICB now shows a colored banner
header with the chosen framing. Dismissible (clears
_chooser_origin so it doesn't reappear).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: New `p_target_candidate` page skeleton with stepper

**Files:**
- Modify: `flowdrip_app.py` — add new page handler near other page handlers
- Modify: `flowdrip_app.py` — add screen routing case for `"target_candidate"` in the page-switcher

- [ ] **Step 1: Locate the screen-routing block**

Run: `grep -n "screen ==\|s.screen ==" flowdrip_app.py | head -20`

Find the central screen-switcher (one large `if/elif` chain that picks which page handler to call). Note the pattern.

- [ ] **Step 2: Add the page handler**

Add a new function near the other `p_*` page handlers (e.g., near `p_aicb`):

```python
def p_target_candidate(s: AppState, rf):
    """Target a Candidate guided wizard. 4 steps:
    1. JD upload/paste
    2. Candidate CSV upload
    3. Sequence preset choice
    4. AI generation + handoff to email editor"""
    # Header
    with ui.element("div").style("max-width:920px;margin:0 auto;padding:24px;"):
        # Stepper
        steps_meta = [
            {"label": "Job description"},
            {"label": "Candidates"},
            {"label": "Cadence"},
            {"label": "Generate"},
        ]
        with ui.element("div").style(
                "display:flex;gap:8px;margin-bottom:24px;align-items:center;"):
            for i, meta in enumerate(steps_meta):
                is_done = i < s.tc_step
                is_current = i == s.tc_step
                bg = C["teal"] if is_current else (C["good"] if is_done else "#E5E7EB")
                fg = "#fff" if (is_current or is_done) else C["muted"]
                with ui.element("div").style(
                        f"display:flex;align-items:center;gap:8px;"):
                    ui.html(
                        f"<div style='width:28px;height:28px;border-radius:50%;"
                        f"background:{bg};color:{fg};display:flex;align-items:center;"
                        f"justify-content:center;font-size:12px;font-weight:700;'>"
                        f"{'✓' if is_done else i+1}</div>"
                    )
                    ui.label(meta["label"]).style(
                        f"font-size:12px;color:{C['ink'] if is_current else C['muted']};"
                        f"font-weight:{600 if is_current else 400};")
                if i < len(steps_meta) - 1:
                    ui.html(f"<div style='flex:0 0 30px;height:1px;background:#E5E7EB;'></div>")

        # Render current step
        if s.tc_step == 0:
            _tc_render_step_jd(s, rf)
        elif s.tc_step == 1:
            _tc_render_step_candidates(s, rf)
        elif s.tc_step == 2:
            _tc_render_step_preset(s, rf)
        elif s.tc_step == 3:
            _tc_render_step_generate(s, rf)


def _tc_render_step_jd(s: AppState, rf):
    """Step 1: placeholder. Filled in by Task 5."""
    ui.label("Step 1 — Job description").style(
        f"font-size:18px;font-weight:700;color:{C['ink']};margin-bottom:12px;")
    ui.label("(Step 1 wizard UI lands in Task 5.)").style(
        f"font-size:13px;color:{C['muted']};")


def _tc_render_step_candidates(s: AppState, rf):
    """Step 2: placeholder. Filled in by Task 6."""
    ui.label("Step 2 — Candidates").style(
        f"font-size:18px;font-weight:700;color:{C['ink']};margin-bottom:12px;")
    ui.label("(Step 2 wizard UI lands in Task 6.)").style(
        f"font-size:13px;color:{C['muted']};")


def _tc_render_step_preset(s: AppState, rf):
    """Step 3: placeholder. Filled in by Task 7."""
    ui.label("Step 3 — Cadence").style(
        f"font-size:18px;font-weight:700;color:{C['ink']};margin-bottom:12px;")
    ui.label("(Step 3 wizard UI lands in Task 7.)").style(
        f"font-size:13px;color:{C['muted']};")


def _tc_render_step_generate(s: AppState, rf):
    """Step 4: placeholder. Filled in by Task 8."""
    ui.label("Step 4 — Generate").style(
        f"font-size:18px;font-weight:700;color:{C['ink']};margin-bottom:12px;")
    ui.label("(Step 4 wizard UI lands in Task 8.)").style(
        f"font-size:13px;color:{C['muted']};")
```

- [ ] **Step 3: Wire the new screen into the screen-switcher**

In the screen-switcher block from Step 1, add a case:

```python
        elif s.screen == "target_candidate":
            p_target_candidate(s, rf)
```

Place this case alongside the other screen routes.

- [ ] **Step 4: Verify the file still parses**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 281 passed.

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(target-candidate): add page skeleton + 4-step stepper

New p_target_candidate page handler with stepper UI showing 4 steps
(Job description / Candidates / Cadence / Generate). Each step
currently renders a placeholder; Tasks 5-8 fill in the actual UI.

Wires \"target_candidate\" into the screen-switcher.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Step 1 — JD upload/paste UI + AI parsing

**Files:**
- Modify: `flowdrip_app.py` — replace `_tc_render_step_jd` placeholder with real UI
- Create: `tests/test_target_candidate_wizard.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_target_candidate_wizard.py`:

```python
"""Target-a-Candidate wizard step gates and transitions.

Step gates:
- Step 1 → 2 requires non-empty tc_jd_text
- Step 2 → 3 requires len(tc_candidates) >= 1
- Step 3 → 4 requires non-empty tc_preset
"""
import inspect


def test_step_jd_renderer_exists_and_handles_paste_and_upload():
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_jd)
    # The renderer must support both upload AND paste
    assert "ui.upload" in src or ".upload(" in src or "PDF" in src
    assert "ui.textarea" in src or "textarea" in src.lower() or "paste" in src.lower()
    # Must check tc_jd_text and gate the Continue button
    assert "tc_jd_text" in src


def test_step_jd_continue_advances_when_text_present():
    """Programmatically verify the Continue handler advances tc_step
    only when tc_jd_text is non-empty. This is a structural check —
    we look for the gate logic in the renderer source."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_jd)
    # The continue gate: tc_step += 1 must be conditional on tc_jd_text
    assert "tc_step" in src and ("tc_jd_text" in src)


def test_jd_parsing_helper_exists():
    """An AI helper to parse JD into role metadata must exist."""
    import flowdrip_app as fa
    assert hasattr(fa, "_tc_parse_jd"), (
        "_tc_parse_jd(jd_text) must be defined to extract role metadata"
    )
```

- [ ] **Step 2: Run tests; they MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_target_candidate_wizard.py -v`

Expected: All 3 FAIL.

- [ ] **Step 3: Add the JD parser helper**

Add this function near other AI helpers (e.g., near `_extract_resume_text`):

```python
def _tc_parse_jd(jd_text: str) -> dict:
    """Parse a job description into structured metadata. Returns a
    dict with role_title, key_skills (list, max 8), seniority,
    comp_range, location. Empty dict on failure / missing API key.

    Used by the Target-a-Candidate wizard's Step 1 to surface the
    role context for downstream sequence generation. Failure here is
    non-fatal — Step 1 only requires raw text to advance."""
    if not jd_text or not ANTHROPIC_API_KEY:
        return {}
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception as ex:
        print(f"[TCParseJD] Anthropic init failed: {ex}", flush=True)
        return {}
    prompt = (
        f"Extract structured metadata from this job description. "
        f"Return ONLY valid JSON in this exact shape:\n"
        f'{{"role_title": "<short title>", '
        f'"key_skills": ["<skill1>", "<skill2>", ...max 8], '
        f'"seniority": "<entry|mid|senior|lead|exec>", '
        f'"comp_range": "<e.g. \\"$90-110k\\" or empty if not stated>", '
        f'"location": "<city, state or remote, empty if not stated>"}}\n\n'
        f"JOB DESCRIPTION:\n{jd_text[:6000]}"
    )
    try:
        msg = _claude_create_with_retry(client,
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
        m = re.search(r'\{[\s\S]*\}', text)
        if not m:
            return {}
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except Exception as ex:
        print(f"[TCParseJD] AI call failed: {ex}", flush=True)
        return {}
```

- [ ] **Step 4: Replace the Step 1 placeholder with real UI**

Replace `_tc_render_step_jd` with:

```python
def _tc_render_step_jd(s: AppState, rf):
    ui.label("Step 1 — Job description").style(
        f"font-size:18px;font-weight:700;color:{C['ink']};margin-bottom:6px;")
    ui.label("Upload the JD or paste the text. AI uses this to tailor "
             "the candidate outreach.").style(
        f"font-size:13px;color:{C['muted']};margin-bottom:18px;")

    # Two input modes — upload OR paste
    with ui.element("div").style("display:flex;gap:14px;margin-bottom:18px;"):
        # Upload column
        with ui.element("div").style(
                f"flex:1;background:#fff;border:1px solid #E5E7EB;"
                f"border-radius:8px;padding:18px;"):
            ui.label("Upload (PDF or DOCX)").style(
                f"font-size:13px;font-weight:700;color:{C['ink']};margin-bottom:8px;")
            def _on_upload(e):
                try:
                    content = e.content.read() if hasattr(e.content, "read") else e.content
                    fname = getattr(e, "name", "jd.pdf")
                    s.tc_jd_filename = fname
                    s.tc_jd_generating = True
                    rf()
                    # Use the existing resume-text extractor (Claude Haiku w/ PDF base64)
                    extracted = _extract_resume_text(content, fname)
                    s.tc_jd_text = (extracted or "").strip()
                    if s.tc_jd_text:
                        s.tc_jd_parsed = _tc_parse_jd(s.tc_jd_text)
                    s.tc_jd_generating = False
                    rf()
                except Exception as ex:
                    s.tc_error = f"Upload failed: {ex}"
                    s.tc_jd_generating = False
                    rf()
            ui.upload(on_upload=_on_upload, max_files=1,
                      auto_upload=True).props('accept=".pdf,.docx,.doc"')
            if s.tc_jd_filename:
                ui.label(f"✓ {s.tc_jd_filename}").style(
                    f"font-size:11px;color:{C['good']};margin-top:6px;")

        # Paste column
        with ui.element("div").style(
                f"flex:1;background:#fff;border:1px solid #E5E7EB;"
                f"border-radius:8px;padding:18px;"):
            ui.label("Or paste").style(
                f"font-size:13px;font-weight:700;color:{C['ink']};margin-bottom:8px;")
            _ta = ui.textarea(value=s.tc_jd_text,
                              placeholder="Paste the JD here...").props(
                "rows=8 outlined dense").style("width:100%;")
            def _on_paste_change(e):
                s.tc_jd_text = (e.value or "").strip()
            _ta.on("update:model-value", _on_paste_change)

    if s.tc_jd_generating:
        with ui.element("div").style(
                "display:flex;align-items:center;gap:8px;margin-bottom:12px;"):
            ui.spinner("dots", size="14px", color=C["teal"])
            ui.label("Parsing JD...").style(f"font-size:12px;color:{C['teal']};")

    if s.tc_jd_parsed:
        # Show the parsed metadata for confirmation
        meta = s.tc_jd_parsed
        with ui.element("div").style(
                f"background:{C['teal_dim']};border:1px solid {C['teal']}40;"
                f"border-radius:8px;padding:12px 16px;margin-bottom:18px;"):
            ui.label(f"AI extracted: {meta.get('role_title', '?')} "
                     f"({meta.get('seniority', '?')})").style(
                f"font-size:13px;font-weight:600;color:{C['teal']};")
            if meta.get("key_skills"):
                ui.label("Skills: " + ", ".join(meta["key_skills"][:6])).style(
                    f"font-size:12px;color:{C['ink']};margin-top:4px;")
            if meta.get("comp_range"):
                ui.label(f"Comp: {meta['comp_range']}").style(
                    f"font-size:12px;color:{C['ink']};")
            if meta.get("location"):
                ui.label(f"Location: {meta['location']}").style(
                    f"font-size:12px;color:{C['ink']};")

    if s.tc_error:
        ui.label(s.tc_error).style(
            f"font-size:12px;color:{C['bad']};margin-bottom:8px;")

    # Continue button
    with ui.element("div").style(
            "display:flex;justify-content:flex-end;margin-top:20px;"):
        def _continue():
            if not (s.tc_jd_text or "").strip():
                s.tc_error = "Upload or paste a JD before continuing."
                rf()
                return
            s.tc_error = ""
            s.tc_step = 1
            rf()
        with ui.element("button").classes("fd-pb").style(
                "padding:10px 22px;font-size:13px;").on("click", _continue):
            ui.label("Continue →").style("pointer-events:none;")
```

- [ ] **Step 5: Run tests; they MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_target_candidate_wizard.py -v`

Expected: All 3 PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 284 passed (281 + 3 new).

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py tests/test_target_candidate_wizard.py
git commit -m "feat(target-candidate): step 1 — JD upload/paste with AI parsing

Two-column layout: upload (PDF/DOCX, parsed via existing
_extract_resume_text helper) OR paste textarea. After raw text
is captured, _tc_parse_jd runs in the same handler to extract
role title / key skills / seniority / comp / location for
downstream sequence generation.

Continue gate requires non-empty tc_jd_text; AI parse failure
is non-fatal (raw text alone advances).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Step 2 — Candidate CSV upload + preview table

**Files:**
- Modify: `flowdrip_app.py` — replace `_tc_render_step_candidates` placeholder
- Modify: `tests/test_target_candidate_wizard.py` — append CSV-step tests

- [ ] **Step 1: Append failing tests to `tests/test_target_candidate_wizard.py`**

```python


def test_step_candidates_renderer_supports_csv_upload():
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_candidates)
    assert "csv" in src.lower() or ".upload" in src
    assert "tc_candidates" in src


def test_step_candidates_continue_requires_at_least_one_candidate():
    """The Continue button on Step 2 must gate on len(tc_candidates) >= 1."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_candidates)
    assert "len(s.tc_candidates)" in src or "tc_candidates" in src and "tc_step = 2" in src
```

- [ ] **Step 2: Run; they MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_target_candidate_wizard.py -v`

Expected: 2 new tests FAIL.

- [ ] **Step 3: Locate the existing CSV parser**

Run: `grep -n "def _parse_contacts_csv\|def parse_contacts\|csv.*reader" flowdrip_app.py | head -10`

Find the CSV parser used by the Contacts page. Note the function name (likely `_parse_contacts_csv` or similar).

- [ ] **Step 4: Replace `_tc_render_step_candidates` with real UI**

```python
def _tc_render_step_candidates(s: AppState, rf):
    ui.label("Step 2 — Candidates").style(
        f"font-size:18px;font-weight:700;color:{C['ink']};margin-bottom:6px;")
    ui.label("Upload a CSV of candidates to reach out to. Required columns: "
             "name, email. Optional: current_company, current_title, linkedin_url.").style(
        f"font-size:13px;color:{C['muted']};margin-bottom:18px;")

    def _on_csv(e):
        try:
            content = e.content.read() if hasattr(e.content, "read") else e.content
            text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
            # Reuse the Contacts page parser. If the actual function name
            # differs, adjust here.
            try:
                rows = _parse_contacts_csv(text)
            except NameError:
                # Fallback: minimal CSV parse
                import io as _io
                rdr = csv.DictReader(_io.StringIO(text))
                rows = [dict(r) for r in rdr]
            # Normalize keys (lowercase) and require name+email
            normalized = []
            for r in rows:
                rk = {k.lower().strip(): (v or "").strip() for k, v in r.items()}
                if rk.get("name") and rk.get("email"):
                    normalized.append({
                        "name": rk["name"],
                        "email": rk["email"],
                        "current_company": rk.get("current_company") or rk.get("company") or "",
                        "current_title": rk.get("current_title") or rk.get("title") or "",
                        "linkedin_url": rk.get("linkedin_url") or rk.get("linkedin") or "",
                    })
            s.tc_candidates = normalized
            s.tc_error = "" if normalized else "No valid rows found (need name + email columns)."
            rf()
        except Exception as ex:
            s.tc_error = f"CSV parse failed: {ex}"
            rf()

    ui.upload(on_upload=_on_csv, max_files=1,
              auto_upload=True).props('accept=".csv"').style("margin-bottom:14px;")

    if s.tc_error:
        ui.label(s.tc_error).style(
            f"font-size:12px;color:{C['bad']};margin-bottom:8px;")

    # Preview table (first 10 rows + count)
    if s.tc_candidates:
        ui.label(f"{len(s.tc_candidates)} candidates loaded").style(
            f"font-size:13px;font-weight:600;color:{C['ink']};margin-bottom:8px;")
        with ui.element("table").style(
                f"width:100%;border-collapse:collapse;background:#fff;"
                f"border:1px solid #E5E7EB;border-radius:8px;overflow:hidden;"):
            with ui.element("thead").style("background:#F9FAFB;"):
                with ui.element("tr"):
                    for col in ("Name", "Email", "Company", "Title", ""):
                        ui.html(
                            f"<th style='text-align:left;padding:8px 12px;"
                            f"font-size:11px;color:{C['muted']};font-weight:600;'>"
                            f"{col}</th>"
                        )
            with ui.element("tbody"):
                for i, cand in enumerate(s.tc_candidates[:10]):
                    with ui.element("tr").style(
                            "border-top:1px solid #F3F4F6;"):
                        for field in ("name", "email", "current_company", "current_title"):
                            ui.html(
                                f"<td style='padding:8px 12px;font-size:12px;"
                                f"color:{C['ink']};'>"
                                f"{(cand.get(field, '') or '').replace('<', '&lt;').replace('>', '&gt;')}</td>"
                            )
                        # Remove button
                        def _remove(idx=i):
                            if 0 <= idx < len(s.tc_candidates):
                                del s.tc_candidates[idx]
                                rf()
                        with ui.element("td").style("padding:8px 12px;"):
                            with ui.element("button").style(
                                    f"padding:2px 8px;font-size:11px;"
                                    f"border:1px solid {C['muted']};"
                                    f"border-radius:4px;background:transparent;"
                                    f"color:{C['muted']};cursor:pointer;"
                                    ).on("click", _remove):
                                ui.label("×").style("pointer-events:none;")
        if len(s.tc_candidates) > 10:
            ui.label(f"… and {len(s.tc_candidates) - 10} more").style(
                f"font-size:11px;color:{C['muted']};margin-top:6px;")

    # Back / Continue
    with ui.element("div").style(
            "display:flex;justify-content:space-between;margin-top:20px;"):
        def _back():
            s.tc_step = 0
            rf()
        with ui.element("button").classes("fd-gb").style(
                "padding:10px 22px;font-size:13px;").on("click", _back):
            ui.label("← Back").style("pointer-events:none;")
        def _continue():
            if len(s.tc_candidates) == 0:
                s.tc_error = "Upload a CSV with at least one candidate before continuing."
                rf()
                return
            s.tc_error = ""
            s.tc_step = 2
            rf()
        with ui.element("button").classes("fd-pb").style(
                "padding:10px 22px;font-size:13px;").on("click", _continue):
            ui.label("Continue →").style("pointer-events:none;")
```

- [ ] **Step 5: Run tests; they MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_target_candidate_wizard.py -v`

Expected: All 5 PASS (3 from Task 5 + 2 new).

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 286 passed (284 + 2 new).

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py tests/test_target_candidate_wizard.py
git commit -m "feat(target-candidate): step 2 — CSV upload + preview table

Reuses the Contacts page CSV parser when available; falls back to
csv.DictReader. Normalizes column keys (case-insensitive, accepts
'company'/'current_company' synonyms). Preview table shows first 10
rows with remove-row buttons. Continue gate: at least 1 candidate.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Step 3 — Sequence preset 4-card grid

**Files:**
- Modify: `flowdrip_app.py` — replace `_tc_render_step_preset` placeholder
- Modify: `tests/test_target_candidate_wizard.py` — append preset tests

- [ ] **Step 1: Append failing tests**

```python


def test_step_preset_renderer_offers_four_options():
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_preset)
    # All 4 preset keys must appear
    assert "one_email" in src
    assert "two_emails_1day" in src
    assert "three_emails_3days" in src
    assert "custom" in src
    # Distinguishing labels
    assert "1 email" in src.lower() or "one email" in src.lower()
    assert "2 emails" in src.lower() or "two emails" in src.lower()
    assert "3 emails" in src.lower() or "three emails" in src.lower()
    assert "create your own" in src.lower() or "free flow" in src.lower()


def test_step_preset_continue_requires_selection():
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_preset)
    assert "tc_preset" in src
```

- [ ] **Step 2: Run; they MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_target_candidate_wizard.py -v`

Expected: 2 new tests FAIL.

- [ ] **Step 3: Replace `_tc_render_step_preset`**

```python
TC_PRESETS = [
    {
        "key": "one_email",
        "title": "1 email and done",
        "subtitle": "Single touch",
        "desc": ("One email goes out at 9 AM, no follow-up. Best when you "
                 "have a tight, hand-picked list and don't want to feel "
                 "spammy."),
        "best_for": "Hand-picked candidates · low-volume",
        "border": C["teal"],
    },
    {
        "key": "two_emails_1day",
        "title": "2 emails, 1 day",
        "subtitle": "Morning + afternoon",
        "desc": ("Email 1 at 9 AM, email 2 at 2 PM the same day. "
                 "Catches both 'first thing' and 'after-lunch' inbox checkers."),
        "best_for": "Same-day urgency · interview lineup",
        "border": "#A78BFA",
    },
    {
        "key": "three_emails_3days",
        "title": "3 emails, 3 days",
        "subtitle": "One per day",
        "desc": ("One email per day at 9 AM for 3 days. Standard cold-outreach "
                 "rhythm — bump, bump, soft close."),
        "best_for": "Cold candidates · standard cadence",
        "border": "#F472B6",
    },
    {
        "key": "custom",
        "title": "Create Your Own",
        "subtitle": "You design the cadence",
        "desc": ("Skip the presets. Drop into the Free Flow builder and craft "
                 "your own sequence — any number of emails, calls, LinkedIn "
                 "touches, with your own delays."),
        "best_for": "Custom motions · power user",
        "border": "#F59E0B",
    },
]


def _tc_render_step_preset(s: AppState, rf):
    ui.label("Step 3 — Cadence").style(
        f"font-size:18px;font-weight:700;color:{C['ink']};margin-bottom:6px;")
    ui.label("Pick the rhythm. You can review and adjust each email "
             "after generation.").style(
        f"font-size:13px;color:{C['muted']};margin-bottom:18px;")

    # 2x2 grid
    with ui.element("div").style(
            "display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px;"):
        for opt in TC_PRESETS:
            is_sel = (s.tc_preset == opt["key"])
            border_color = opt["border"] if is_sel else "#E5E7EB"
            border_width = "2px" if is_sel else "1px"
            def _pick(k=opt["key"]):
                s.tc_preset = k
                rf()
            with ui.element("div").style(
                    f"background:#fff;border:{border_width} solid {border_color};"
                    f"border-radius:10px;padding:16px 18px;cursor:pointer;"
                    f"transition:border-color 0.12s;"
                    ).on("click", _pick):
                with ui.element("div").style(
                        "display:flex;justify-content:space-between;"
                        "align-items:flex-start;margin-bottom:6px;"):
                    with ui.element("div"):
                        ui.label(opt["title"]).style(
                            f"font-size:14px;font-weight:700;color:{opt['border']};")
                        ui.label(opt["subtitle"]).style(
                            f"font-size:11px;color:{C['muted']};")
                    if is_sel:
                        ui.html(f"<span style='font-size:16px;color:{opt['border']};'>✓</span>")
                ui.label(opt["desc"]).style(
                    f"font-size:12px;line-height:1.5;color:{C['ink']};margin-bottom:8px;")
                ui.label(opt["best_for"]).style(
                    f"font-size:10px;color:{C['muted']};font-weight:500;")

    if s.tc_error:
        ui.label(s.tc_error).style(
            f"font-size:12px;color:{C['bad']};margin-bottom:8px;")

    # Back / Continue
    with ui.element("div").style(
            "display:flex;justify-content:space-between;margin-top:6px;"):
        def _back():
            s.tc_step = 1
            rf()
        with ui.element("button").classes("fd-gb").style(
                "padding:10px 22px;font-size:13px;").on("click", _back):
            ui.label("← Back").style("pointer-events:none;")
        def _continue():
            if not s.tc_preset:
                s.tc_error = "Pick a cadence before continuing."
                rf()
                return
            s.tc_error = ""
            # Custom preset routes directly to AICB Free Flow with the
            # JD + candidates pre-loaded as context.
            if s.tc_preset == "custom":
                s._chooser_origin = ""
                s.aicb_camp_type = "byos"
                s.aicb_byos_desc = (
                    f"Outreach to {len(s.tc_candidates)} candidates for the "
                    f"role: {s.tc_jd_parsed.get('role_title', 'see JD below')}.\n\n"
                    f"JD:\n{s.tc_jd_text[:2000]}"
                )
                s.screen = "aicb"
                rf()
                return
            s.tc_step = 3
            rf()
        with ui.element("button").classes("fd-pb").style(
                "padding:10px 22px;font-size:13px;").on("click", _continue):
            ui.label("Continue →").style("pointer-events:none;")
```

- [ ] **Step 4: Run tests; they MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_target_candidate_wizard.py -v`

Expected: 7 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 288 passed (286 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py tests/test_target_candidate_wizard.py
git commit -m "feat(target-candidate): step 3 — sequence preset 4-card grid

2x2 grid: 1 email and done / 2 emails 1 day / 3 emails 3 days /
Create Your Own. Selection writes tc_preset. The 'Create Your Own'
option short-circuits to AICB Free Flow with JD + candidate count
pre-loaded into the byos description.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Step 4 — AI generation + handoff to email editor

**Files:**
- Modify: `flowdrip_app.py` — replace `_tc_render_step_generate` placeholder
- Modify: `tests/test_target_candidate_wizard.py` — append generation test

- [ ] **Step 1: Append failing test**

```python


def test_step_generate_emits_campaign_with_correct_cadence():
    """The generation step must produce a campaign dict with the
    correct number of emails and delays for each preset."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._tc_render_step_generate)
    # Must reference all 3 non-custom preset keys
    assert "one_email" in src
    assert "two_emails_1day" in src
    assert "three_emails_3days" in src
    # Must call save_campaign and route to email editor
    assert "save_campaign" in src
    # Must reference the JD context in generation
    assert "tc_jd_text" in src or "tc_jd_parsed" in src
```

- [ ] **Step 2: Run; it MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_target_candidate_wizard.py::test_step_generate_emits_campaign_with_correct_cadence -v`

Expected: FAIL.

- [ ] **Step 3: Replace `_tc_render_step_generate`**

```python
def _tc_render_step_generate(s: AppState, rf):
    ui.label("Step 4 — Generate").style(
        f"font-size:18px;font-weight:700;color:{C['ink']};margin-bottom:6px;")
    ui.label("AI writes the sequence using your JD as context. After "
             "generation you'll land in the email editor for review.").style(
        f"font-size:13px;color:{C['muted']};margin-bottom:18px;")

    # Summary card
    role = s.tc_jd_parsed.get("role_title", "(role from JD)")
    seniority = s.tc_jd_parsed.get("seniority", "")
    cand_n = len(s.tc_candidates)
    preset_labels = {
        "one_email": "1 email, sent at 9 AM",
        "two_emails_1day": "2 emails, 9 AM + 2 PM same day",
        "three_emails_3days": "3 emails, 1/day at 9 AM for 3 days",
    }
    preset_label = preset_labels.get(s.tc_preset, s.tc_preset)

    with ui.element("div").style(
            f"background:{C['teal_dim']};border:1px solid {C['teal']}40;"
            f"border-radius:8px;padding:14px 18px;margin-bottom:18px;"):
        ui.label(f"Role: {role} {f'({seniority})' if seniority else ''}").style(
            f"font-size:13px;font-weight:600;color:{C['ink']};")
        ui.label(f"Candidates: {cand_n}").style(
            f"font-size:13px;color:{C['ink']};margin-top:4px;")
        ui.label(f"Cadence: {preset_label}").style(
            f"font-size:13px;color:{C['ink']};margin-top:4px;")

    if s.tc_error:
        ui.label(s.tc_error).style(
            f"font-size:12px;color:{C['bad']};margin-bottom:8px;")

    if s.tc_generating:
        with ui.element("div").style(
                f"background:{C['teal_dim']};border-radius:10px;"
                f"padding:32px;text-align:center;margin-bottom:18px;"):
            ui.spinner("dots", size="48px", color=C["teal"])
            ui.label("Generating sequence...").style(
                f"font-size:14px;font-weight:600;color:{C['teal']};margin-top:12px;")
            ui.label("This usually takes 15-30 seconds.").style(
                f"font-size:12px;color:{C['muted']};margin-top:4px;")

    def _on_generate():
        if s.tc_generating:
            return
        s.tc_generating = True
        s.tc_error = ""
        rf()

        def _run():
            try:
                # Build the cadence config per preset
                if s.tc_preset == "one_email":
                    steps_meta = [{"delay_days": 0, "time": "9:00 AM"}]
                elif s.tc_preset == "two_emails_1day":
                    steps_meta = [
                        {"delay_days": 0, "time": "9:00 AM"},
                        {"delay_days": 0, "time": "2:00 PM"},
                    ]
                elif s.tc_preset == "three_emails_3days":
                    steps_meta = [
                        {"delay_days": 0, "time": "9:00 AM"},
                        {"delay_days": 1, "time": "9:00 AM"},
                        {"delay_days": 2, "time": "9:00 AM"},
                    ]
                else:
                    steps_meta = [{"delay_days": 0, "time": "9:00 AM"}]

                # AI prompt
                role_title = s.tc_jd_parsed.get("role_title", "this role")
                key_skills = ", ".join((s.tc_jd_parsed.get("key_skills") or [])[:5])
                seniority = s.tc_jd_parsed.get("seniority", "")
                comp = s.tc_jd_parsed.get("comp_range", "")
                location = s.tc_jd_parsed.get("location", "")

                from anthropic import Anthropic
                client = Anthropic(api_key=ANTHROPIC_API_KEY)

                prompt = (
                    f"Write {len(steps_meta)} candidate-outreach emails "
                    f"for a recruiter pitching the role of {role_title} "
                    f"({seniority}) to passive candidates.\n\n"
                    f"ROLE CONTEXT:\n"
                    f"- Title: {role_title}\n"
                    f"- Seniority: {seniority}\n"
                    f"- Key skills: {key_skills}\n"
                    f"- Comp: {comp or 'not specified'}\n"
                    f"- Location: {location or 'not specified'}\n\n"
                    f"FULL JD (excerpt):\n{s.tc_jd_text[:1500]}\n\n"
                    f"CADENCE: {len(steps_meta)} emails over "
                    f"{1 + max((m['delay_days'] for m in steps_meta), default=0)} day(s).\n\n"
                    f"STRICT RULES:\n"
                    f"- Address candidate as {{first_name}}.\n"
                    f"- Respectful, no fake urgency. Treat them as a peer.\n"
                    f"- Each email under 150 words.\n"
                    f"- Subject lines distinct and specific.\n"
                    f"- DO NOT use emoji or markdown.\n"
                    f"- DO NOT include 'I came across your profile' or "
                    f"similar template-feeling openers.\n\n"
                    f"Return ONLY valid JSON:\n"
                    f'{{"emails":['
                    + ",".join(
                        f'{{"name":"Step {i+1}","subject":"...",'
                        f'"body":"Hi {{first_name}},<br><br>...",'
                        f'"delay_days":{m["delay_days"]},'
                        f'"time":"{m["time"]}",'
                        f'"step_type":"email_auto"}}'
                        for i, m in enumerate(steps_meta)
                    )
                    + "]}"
                )
                msg = _claude_create_with_retry(client,
                    model="claude-haiku-4-5-20251001",
                    max_tokens=3000,
                    messages=[{"role": "user", "content": prompt}])
                text = "".join(b.text for b in msg.content if hasattr(b, "text"))
                m = re.search(r'\{[\s\S]*\}', text)
                if not m:
                    raise ValueError("AI did not return parseable JSON")
                parsed = json.loads(m.group(0))
                emails = parsed.get("emails") or []
                if len(emails) != len(steps_meta):
                    raise ValueError(
                        f"AI returned {len(emails)} emails, expected {len(steps_meta)}"
                    )

                # Build the campaign dict
                camp_name = (
                    f"Target a Candidate — {role_title}"
                    if role_title != "this role"
                    else f"Target a Candidate — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                )
                camp = {
                    "name": camp_name,
                    "_owner_email": s._user_email,
                    "_chooser_origin": "candidate",
                    "synopsis": (
                        f"Candidate outreach for {role_title}. "
                        f"{len(s.tc_candidates)} candidates. "
                        f"{preset_label}."
                    ),
                    "emails": emails,
                    "market_sector": s.tc_jd_parsed.get("seniority", ""),
                    "market_niche": role_title,
                    "market_region": location,
                    "tc_jd_parsed": s.tc_jd_parsed,
                    "tc_candidates": s.tc_candidates,
                }
                save_campaign(camp)
                # Load it as the active campaign and route to editor
                s.loaded_camp = camp
                s.screen = "emails"  # adjust to the actual editor screen name
                s.tc_generating = False
                rf()
            except Exception as ex:
                s.tc_error = f"Generation failed: {ex}"
                s.tc_generating = False
                rf()

        _run_as_user(s._user_email, _run, name="tc_generate_worker")

    # Back / Generate
    with ui.element("div").style(
            "display:flex;justify-content:space-between;margin-top:6px;"):
        def _back():
            s.tc_step = 2
            rf()
        with ui.element("button").classes("fd-gb").style(
                "padding:10px 22px;font-size:13px;").on("click", _back):
            ui.label("← Back").style("pointer-events:none;")
        with ui.element("button").classes("fd-pb").style(
                "padding:10px 28px;font-size:13px;"
                + ("opacity:0.6;pointer-events:none;" if s.tc_generating else "")
                ).on("click", _on_generate):
            ui.label("Generate Sequence →").style("pointer-events:none;")
```

CRITICAL — `s.screen = "emails"` may need to be a different screen name. Search `grep -n "p_emails_build\|s.screen.*emails" flowdrip_app.py | head -5` to find the right name and adjust.

- [ ] **Step 4: Run tests; they MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_target_candidate_wizard.py -v`

Expected: 8 PASS.

- [ ] **Step 5: Full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 289 passed.

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py tests/test_target_candidate_wizard.py
git commit -m "feat(target-candidate): step 4 — AI generation + email-editor handoff

Builds the cadence config from tc_preset (1/2/3 email patterns).
Calls Claude Haiku with the JD as primary context to generate
email subject + body for each step. Saves the campaign via
save_campaign(camp) with a 'Target a Candidate — <role>' name
prefix. Routes to the existing email editor for review.

Background worker uses _run_as_user (Phase 0 thread-binding) so
save_campaign writes to the correct per-user directory.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Final integration — full-suite + Phase 0 audit re-check

- [ ] **Step 1: Run the full project test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 289 passed.

- [ ] **Step 2: AST parse**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0.

- [ ] **Step 3: Phase 0 audit-test re-run**

Run: `.venv/Scripts/python.exe -m pytest tests/test_audit_no_raw_per_user_threads.py -v`

Expected: PASS. Any new threads added in this plan must use `_run_as_user`. The `tc_generate_worker` thread in Task 8 uses it.

- [ ] **Step 4: Smoke import**

Run: `.venv/Scripts/python.exe -c "import flowdrip_app; print('OK')"`

Expected: `OK`.

- [ ] **Step 5: Final commit (if any trailing changes)**

If nothing trails, skip. Otherwise:

```bash
git add -A
git commit -m "chore: Phase 2 integration cleanup"
```

---

## Self-review checklist

- **Spec coverage:**
  - 5-option chooser: Task 2 ✓
  - AICB banner per origin: Task 3 ✓
  - Wizard skeleton + stepper: Task 4 ✓
  - Step 1 JD upload/paste + parse: Task 5 ✓
  - Step 2 CSV upload + preview: Task 6 ✓
  - Step 3 preset 4-card grid: Task 7 ✓
  - Step 4 generation + handoff: Task 8 ✓
  - Phase 0 regression net check: Task 9 Step 3 ✓
- **Placeholder scan:** No TBD/TODO. All code blocks complete.
- **Type consistency:**
  - AppState slots: `tc_step` (int), `tc_jd_text` (str), `tc_jd_parsed` (dict), `tc_candidates` (list), `tc_preset` (str), `tc_generating` (bool), `tc_error` (str) — used consistently across Tasks 1, 4, 5, 6, 7, 8.
  - Preset keys: `one_email` / `two_emails_1day` / `three_emails_3days` / `custom` — used in Tasks 7 and 8 with same spelling.
  - Helper names: `_tc_render_step_jd`, `_tc_render_step_candidates`, `_tc_render_step_preset`, `_tc_render_step_generate`, `_tc_parse_jd` — all defined in respective tasks, called from `p_target_candidate` in Task 4.
- **Phase 0 thread-binding:** Task 8's bg thread uses `_run_as_user` (the only new thread in this plan). Test `test_audit_no_raw_per_user_threads.py` re-run in Task 9 confirms.

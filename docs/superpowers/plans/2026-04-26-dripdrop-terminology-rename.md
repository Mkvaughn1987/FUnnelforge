# DripDrop Terminology Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace internal jargon with industry-standard terminology across the DripDrop UI (per spec at `docs/superpowers/specs/2026-04-26-dripdrop-terminology-rename-design.md`), kill the legacy topbar hub-toggle, and consolidate Settings into a tabbed page.

**Architecture:** All work in `flowdrip_app.py` (~40K lines). Per-page commits for the cascade phase so any regression is reverted in isolation. Brand string `"DripDrop"` is protected — never modified. JSON keys, file paths, function names, and Python variable names are not touched.

**Tech Stack:** Python, NiceGUI, pytest. Existing test infrastructure at `tests/` is reused (no new test infra needed).

**Verified counts (snapshot at plan-write time):**
- 113 `ui.label("...campaign...")` occurrences
- 12 `ui.notify("...campaign...")` occurrences
- ~10 `Slow Drip` user-visible string occurrences (excluding `template_name="Slow Drip"` data strings)
- ~6 `Today's Drip` / `Tomorrow's Drop` occurrences

**Key file locations (approximate; verify by grep before editing):**
| Region | Lines | Contents |
|---|---|---|
| `SALES_NAV` constant | L8046–8068 | Sidebar nav for the Sales hub |
| `EMAILS_NAV` constant | L8071–8079 | Legacy hub nav (DELETE in Phase 3) |
| `PAGE_HELP` dictionary | L8507–8514 | Help popup map: page-key → display name |
| Page title configs | L8675–8780 | Page-config dicts with `"title"` strings |
| Topbar pills | L9056 (`Manage Campaigns`), nearby | Hub-toggle UI (DELETE in Phase 3) |
| `template_name` data strings | L16865–19410 | DO NOT MODIFY — these are JSON data, not display |

**Branch:** continue on `claude/critical-bug-fixes` (already has the spec committed). All commits land on this branch.

---

## Task 0: Pre-flight verification

**Files:** none (verification only)

- [ ] **Step 1: Confirm working tree is clean and on the right branch**

```bash
git status --short flowdrip_app.py funnelforge_core.py
git rev-parse --abbrev-ref HEAD
```

Expected: no staged/unstaged changes on those two files; branch is `claude/critical-bug-fixes`.

- [ ] **Step 2: Confirm baseline test suite passes**

```bash
python -m pytest tests/ -q
```

Expected: 23 passed (or whatever the current count is — ALL must pass).

- [ ] **Step 3: Verify line numbers in the plan are still close**

```
grep -n '^SALES_NAV\s*=\|^EMAILS_NAV\s*=' flowdrip_app.py
```

Expected: matches near L8046 and L8071. If significantly off, the engineer should adjust by symbol name, not line number.

If anything in Steps 1-3 doesn't match, STOP and report. No commits in this task.

---

## Task 1: Phase 1 — Sidebar renames (SALES_NAV)

**Files:** Modify `flowdrip_app.py` at the `SALES_NAV` constant (L8046–8068).

**Goal:** Update the sidebar labels per the spec. Page keys (the third tuple element) STAY THE SAME — only the human-readable label (second element) changes.

- [ ] **Step 1: Read the current constant**

Read lines 8046-8068 of `flowdrip_app.py` so the engineer has the exact starting state.

- [ ] **Step 2: Replace SALES_NAV literal**

Find the existing SALES_NAV literal (Grep `^SALES_NAV\s*=` for the line number). Replace the entire literal with this updated version:

```python
SALES_NAV = [
    # ── Home ─────────────────────────────────────
    (None, "HOME",              None),
    ("⬡",  "Dashboard",        "dashboard"),
    ("◎",  "Replies",           "responses"),
    # ── Sequences ────────────────────────────────
    (None, "SEQUENCES",         None),
    ("▷",  "Sequences",         "start_seq"),
    ("≡",  "Contacts",          "contacts"),
    ("🚫", "Opt-Out List",     "dnc"),
    ("🛡", "Existing Customers", "active_clients"),
    # ── Content & Tools ──────────────────────────
    (None, "CONTENT & TOOLS",   None),
    ("📊", "Reports",           "pdf_gen"),
    ("🔍", "Candidates",        "candidate_finder"),
    # ── Settings ─────────────────────────────────
    (None, "SETTINGS",          None),
    ("◆",  "My Profile",       "company_profile"),
    ("👥", "Team",              "team_settings"),
    ("✦",  "Settings",          "ai_settings"),
]
```

Note the section header "CAMPAIGNS" → "SEQUENCES".

- [ ] **Step 3: Smoke-import the module**

Run: `python -c "import flowdrip_app; print('OK')"`
Expected: prints "OK" with no errors.

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: all tests still pass.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "rename(ux): update SALES_NAV sidebar labels to industry-standard terms"
```

---

## Task 2: Page H1 / page-title renames

**Files:** Modify `flowdrip_app.py` at multiple page-title `ui.label(...).classes("fd-h1")` calls.

**Goal:** Each page renders a top-level header via `ui.label("X").classes("fd-h1")`. Update each to match the new sidebar labels.

**Specific replacements (verify each by Grep before editing):**

| Current | New |
|---|---|
| `ui.label("Campaign Radar").classes("fd-h1")` (L10421) | `ui.label("Replies").classes("fd-h1")` |
| `ui.label("Start a Campaign").classes("fd-h1")` (L13102) | `ui.label("Sequences").classes("fd-h1")` |
| `ui.label("Active Campaigns").classes("fd-h1")` (L16321) | `ui.label("Active Sequences").classes("fd-h1")` |
| `ui.label("Contact Lists").classes("fd-h1")` (L16054) | `ui.label("Contacts").classes("fd-h1")` |
| `ui.label("Manage Campaigns").classes("fd-h1")` (L20846) | (page being deleted in Phase 3 — leave for now, or pre-rename to `"Sequences"` since the page redirects to the sequence list) |
| `ui.label("Active Clients").classes("fd-h1")` (L21969) | `ui.label("Existing Customers").classes("fd-h1")` |
| `ui.label("PDF Generator").classes("fd-h1")` (L27420) | `ui.label("Reports").classes("fd-h1")` |
| `ui.label("Candidate Pool").classes("fd-h1")` (L29586, L30041, L30061) | `ui.label("Candidates").classes("fd-h1")` |
| `ui.label("Email & AI Setup").classes("fd-h1")` (L30450) | `ui.label("Settings").classes("fd-h1")` |
| `ui.label("Team Settings").classes("fd-h1")` (L36545) | `ui.label("Team").classes("fd-h1")` |

- [ ] **Step 1: Apply each rename via Grep+Edit**

For each row, run a Grep to confirm the exact string match exists, then use Edit with the exact `old_string` and `new_string`.

Example for the first row:
```
Edit:
  old_string: ui.label("Campaign Radar").classes("fd-h1")
  new_string: ui.label("Replies").classes("fd-h1")
```

If a string from the table is NOT found by Grep, mark it INVALID in the engineer's notes (it was already renamed) and skip — do not invent a fix.

- [ ] **Step 2: After all renames in this task, verify count**

```
grep -nE 'ui\.label\("(Campaign Radar|Start a Campaign|Active Campaigns|Contact Lists|Active Clients|PDF Generator|Candidate Pool|Email & AI Setup|Team Settings)"\)' flowdrip_app.py
```

Expected: zero matches (the old strings should be gone).

- [ ] **Step 3: Smoke import + tests**

```bash
python -c "import flowdrip_app; print('OK')"
python -m pytest tests/ -q
```

Expected: imports OK, all tests pass.

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "rename(ux): update page H1 labels to match new sidebar terminology"
```

---

## Task 3: PAGE_HELP dictionary + page-title configs

**Files:** Modify `flowdrip_app.py` at the help dictionary (L8507–8514) and page-config blocks (L8675–8780).

**Goal:** The help-popup system uses a dictionary mapping `page_key → "Display Name"`. The page-config blocks have a `"title"` field for each page. Both must reflect the new names.

- [ ] **Step 1: Update the `PAGE_HELP` dictionary literal**

Find the dict starting around L8507 (Grep `"dashboard": "Dashboard", "drip"`). Replace these key-value pairs (only the values change; the keys stay):

| Key | Old value | New value |
|---|---|---|
| `"drip"` | `"Today's Drip"` | `"Today"` |
| `"responses"` | `"Campaign Radar"` | `"Replies"` |
| `"start_seq"` | `"Start a Campaign"` | `"Sequences"` |
| `"contacts"` | `"Contact Lists"` | `"Contacts"` |
| `"active_camps"` | `"Active Campaigns"` | `"Active Sequences"` |
| `"evergreen"` | `"Slow Drip"` | `"Always-On Sequence"` |
| `"evergreen_create"` | `"Slow Drip"` | `"Always-On Sequence"` |
| `"seq_mgr"` | `"Manage Campaigns"` | `"Sequences"` (page becomes redundant; redirects to Sequences in Phase 3) |
| `"e_responses"` | `"Campaign Radar"` | `"Replies"` |

(There may be other keys not listed. Leave them. Do not rename `"signature": "Email Signature"` — Settings tabs absorb this in Phase 4.)

- [ ] **Step 2: Update page-config `"title"` fields**

Find each page-config block (Grep `"title": "Start a Campaign"`, etc.) and update each `"title"` value. List of changes:

| File line | Old `"title"` | New `"title"` |
|---|---|---|
| L8685 | `"Start a Campaign"` | `"Sequences"` |
| L8696 | `"Manage Campaigns"` | `"Sequences"` |
| L8717 | `"Candidate Pool"` | `"Candidates"` |
| L8729 | `"Contact Lists"` | `"Contacts"` |
| L8738 | `"PDF Generator"` | `"Reports"` |
| L8771 | `"Email & AI Setup"` | `"Settings"` |
| L8780 | `"Campaign Radar"` | `"Replies"` |

- [ ] **Step 3: Verify and commit**

```bash
python -c "import flowdrip_app; print('OK')"
python -m pytest tests/ -q
git add flowdrip_app.py
git commit -m "rename(ux): update PAGE_HELP dict + page-config titles"
```

Expected: imports OK, tests pass.

---

## Task 4: Dashboard "Today's Drip" / "Tomorrow's Drop" stat tabs

**Files:** Modify `flowdrip_app.py` at L9646 (the pills tuple) and L19943 (the Today's Drip group label).

**Goal:** The dashboard shows stat tabs labeled "Today's Drip" and "Tomorrow's Drop". Plain English: "Today" and "Tomorrow".

- [ ] **Step 1: Update the pills tuple at L9646**

Grep `pills = \[\("today",`. Find the line, expected match:
```python
pills = [("today", "Today's Drip"), ("tomorrow", "Tomorrow's Drop")]
```

Replace with:
```python
pills = [("today", "Today"), ("tomorrow", "Tomorrow")]
```

- [ ] **Step 2: Update the standalone label at L19943**

Grep `ui\.label\("Today's Drip"\)`. Expected match:
```python
                        ui.label("Today's Drip")
```

Replace with:
```python
                        ui.label("Today")
```

- [ ] **Step 3: Update the help-text label at L8681**

Grep `"Tomorrow's Drop"` — find the help-text tuple at L8681. Expected match:
```python
            ("Tomorrow's Drop", "Preview what's coming tomorrow so you can plan ahead."),
```

Replace with:
```python
            ("Tomorrow", "Preview what's coming tomorrow so you can plan ahead."),
```

- [ ] **Step 4: Verify and commit**

```bash
grep -nE "Today's Drip|Tomorrow's Drop" flowdrip_app.py
# Expected: zero matches except possibly in unrelated contexts (if any remain, address them).
python -c "import flowdrip_app; print('OK')"
python -m pytest tests/ -q
git add flowdrip_app.py
git commit -m "rename(ux): Today's Drip → Today, Tomorrow's Drop → Tomorrow on dashboard"
```

---

## Task 5: "Slow Drip" / "Evergreen" → "Always-On Sequence" (display only)

**Files:** Modify `flowdrip_app.py` at user-visible "Slow Drip" labels.

**Goal:** Rename the recurring-campaign feature from "Slow Drip" to "Always-On Sequence" in user-visible UI. **Critical:** `template_name="Slow Drip"` strings (L16865–19410) are JSON data values, NOT display strings. These DO NOT change. Only `ui.label(...)`, group headers, table columns, and similar display-only strings change.

**Replacements (verify each by Grep first):**

| Line | Old | New |
|---|---|---|
| L9058 | `ui.label("Slow Drip")` | `ui.label("Always-On Sequence")` |
| L9737 | `ui.label("Slow Drip").style(` | `ui.label("Always-On Sequence").style(` |
| L19872 | `_group_header("Slow Drip", len(_slow_drip), C["indigo"])` | `_group_header("Always-On Sequence", len(_slow_drip), C["indigo"])` |
| L21592 | `for _hdr in ["Contact", "Company", "Progress", "Status", "Remove", "Slow Drip"]:` | `for _hdr in ["Contact", "Company", "Progress", "Status", "Remove", "Always-On"]:` (column header — abbreviated to fit, since it's a table col) |

- [ ] **Step 1: Apply each via Grep + Edit**

For each row, Grep to verify the match exists, then Edit. If not found, skip that row (already renamed).

- [ ] **Step 2: Confirm `template_name="Slow Drip"` values were NOT changed**

```bash
grep -nc 'template_name="Slow Drip"' flowdrip_app.py
```

Expected: count > 0 (these are data values that stay).

- [ ] **Step 3: Verify and commit**

```bash
grep -nE 'ui\.label\("Slow Drip"\)|"Slow Drip"\)\.style' flowdrip_app.py
# Expected: zero matches.
python -c "import flowdrip_app; print('OK')"
python -m pytest tests/ -q
git add flowdrip_app.py
git commit -m 'rename(ux): "Slow Drip" → "Always-On Sequence" in display only (data strings unchanged)'
```

---

## Task 6: "Build My Own Campaign" → "Build from scratch"

**Files:** Modify `flowdrip_app.py` at L13169, L13233, L13822 (and any other instances Grep finds).

**Goal:** The sequence-type picker has a card titled "Build My Own Campaign". Rename to "Build from scratch" — clearer for non-pros.

- [ ] **Step 1: Find all occurrences**

```
grep -n '"Build My Own Campaign"' flowdrip_app.py
```

Expected matches at L13169, L13233, L13822, possibly more.

- [ ] **Step 2: Replace each via Edit**

For the picker tuple at L13169:

```
Edit:
  old_string: ("custom",        "Build My Own Campaign",  "✏️", "#F59E0B",
  new_string: ("custom",        "Build from scratch",     "✏️", "#F59E0B",
```

For the label_map at L13233:

```
Edit:
  old_string: "custom":    "Build My Own Campaign",
  new_string: "custom":    "Build from scratch",
```

For the H1-style label at L13822:

```
Edit:
  old_string: ui.label("Build My Own Campaign").style(
  new_string: ui.label("Build from scratch").style(
```

For any remaining instances Grep surfaces, apply the same transform.

- [ ] **Step 3: Update the inline comments that reference this name**

Comments at L13155 and L14336 reference the old name. Update for consistency:

```
Edit at L13155:
  old_string: # "Custom Campaign" renamed to "Build My Own Campaign" — the card
  new_string: # "Custom Campaign" renamed to "Build from scratch" — the card

Edit at L14336:
  old_string: # flow — "Build My Own Campaign" is fully manual.
  new_string: # flow — "Build from scratch" is fully manual.
```

- [ ] **Step 4: Verify and commit**

```bash
grep -nE 'Build My Own Campaign' flowdrip_app.py
# Expected: zero matches.
python -c "import flowdrip_app; print('OK')"
python -m pytest tests/ -q
git add flowdrip_app.py
git commit -m 'rename(ux): "Build My Own Campaign" → "Build from scratch"'
```

---

## Task 7: "Saved Campaigns" → "Saved Sequences"

**Files:** Modify `flowdrip_app.py` at L13175 (picker tuple) and L13234 (label_map).

- [ ] **Step 1: Update picker tuple at L13175**

```
Edit:
  old_string: ("saved",         "Saved Campaigns",  "📂", "#60A5FA",
  new_string: ("saved",         "Saved Sequences",  "📂", "#60A5FA",
```

- [ ] **Step 2: Update label_map at L13234**

```
Edit:
  old_string: "saved":     "Saved Campaigns",
  new_string: "saved":     "Saved Sequences",
```

- [ ] **Step 3: Look for any other "Saved Campaigns"**

```
grep -n '"Saved Campaigns"' flowdrip_app.py
```

Replace any remaining instances using Edit.

- [ ] **Step 4: Verify and commit**

```bash
grep -n '"Saved Campaigns"' flowdrip_app.py
# Expected: zero matches.
python -m pytest tests/ -q
git add flowdrip_app.py
git commit -m 'rename(ux): Saved Campaigns → Saved Sequences in picker'
```

---

## Task 8: Active Campaigns secondary header (L19800)

**Files:** Modify `flowdrip_app.py` at L19800.

- [ ] **Step 1: Update the additional Active Campaigns label**

```
Edit:
  old_string: ui.label("Active Campaigns").style(
  new_string: ui.label("Active Sequences").style(
```

- [ ] **Step 2: Verify and commit**

```bash
grep -nE 'ui\.label\("Active Campaigns"\)' flowdrip_app.py
# Expected: zero matches.
python -m pytest tests/ -q
git add flowdrip_app.py
git commit -m 'rename(ux): remaining Active Campaigns → Active Sequences instances'
```

---

## Task 9: ui.notify() and toast cascade (Campaign → Sequence)

**Files:** Modify `flowdrip_app.py` at every `ui.notify(...)` containing the word "campaign".

**Goal:** All toast notifications that say "Campaign saved!", "Campaign sent!", "Campaign deleted!", etc. become "Sequence saved!", "Sequence sent!", etc.

- [ ] **Step 1: Generate the exhaustive find list**

```
grep -nE 'ui\.notify\([^)]*[Cc]ampaign' flowdrip_app.py
```

Expected: ~12 matches. For each match, transform per these rules:
- `"Campaign saved"` → `"Sequence saved"`
- `"Campaign sent"` → `"Sequence sent"`
- `"Campaign deleted"` → `"Sequence deleted"`
- `"Campaign created"` → `"Sequence created"`
- `"Campaign launched"` → `"Sequence launched"`
- `"Campaign paused"` → `"Sequence paused"`
- `"campaign"` (lowercase, mid-sentence) → `"sequence"` (preserve case)
- Any "campaigns" (plural) → "sequences"

**Critical:** When transforming, the case-insensitive substring `Campaign` is replaced with the matching case-preserved `Sequence`. But:
- DO NOT modify the literal string `"DripDrop"` (it doesn't contain "campaign" so this isn't a risk in this task, but stay alert).
- DO NOT modify any string in a context like `q.get("campaign", "")` (that's a JSON key access — the dict key is `"campaign"`, must stay).

- [ ] **Step 2: Apply each transform via Edit**

Use exact `old_string`/`new_string` pairs. If the match line has surrounding code, copy enough context to make the `old_string` unique.

- [ ] **Step 3: Verify**

```bash
grep -nE 'ui\.notify\([^)]*[Cc]ampaign' flowdrip_app.py
# Expected: zero matches.
python -m pytest tests/ -q
```

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m 'rename(ux): toast notifications Campaign → Sequence'
```

---

## Task 10: ui.label() Campaign cascade (the bulk of the work)

**Files:** Modify `flowdrip_app.py` at every `ui.label(...)` containing user-visible "campaign" / "Campaign" outside of the targeted page H1 labels (Task 2) and other already-handled spots.

**Goal:** The general cascade — buttons, helper text, modal titles, section headers that say "Campaign" become "Sequence". This is the largest single task; expect ~80–100 individual edits.

**Critical exclusions (do NOT modify):**
- The string `"DripDrop"` itself (doesn't contain "campaign", but be vigilant).
- JSON dict keys like `q.get("campaign", "")`, `camp.get("campaign", ...)`, `data["campaign"]` — these are data lookups.
- Variable names: `campaign_name`, `camp`, `_camp`, etc. — internal Python identifiers.
- Function names: `queue_campaign_emails`, `_cancel_pending_for_email_in_campaign`, etc.
- File paths: `campaigns/` directory, `*.json` filenames.
- Comments — leave alone unless the comment becomes misleading (use judgment).
- The comments at L13155 / L14336 which refer to "Custom Campaign" — those name a feature being renamed; update them per Task 6.

**Inclusions (DO modify):**
- `ui.label("X campaign Y")` — display text.
- `ui.label("X campaigns Y")` — plural display text.
- HTML strings inside `ui.html(...)` calls if they contain user-visible "campaign" wording.
- String values in dicts that are CLEARLY display labels (e.g., `{"label": "Save Campaign", "key": "save"}`).

- [ ] **Step 1: Generate the find list**

```
grep -nE 'ui\.label\([^)]*[Cc]ampaign' flowdrip_app.py
```

Expected: ~113 matches. Save the output for tracking.

- [ ] **Step 2: For each match, decide and apply**

For each match, decide:
- A) Already handled by Tasks 2–8 (skip).
- B) Display string with "Campaign" → replace with "Sequence" preserving case.
- C) Display string with "campaigns" → replace with "sequences".
- D) Edge case (e.g., quoted brand reference, comment text) → leave alone, note in commit message.

For the bulk B/C cases, apply via Edit with exact `old_string`/`new_string`. To keep commits manageable, group ~20-30 edits per commit by page region. Suggested grouping:
- Commit 10a: Sequence picker page (L13000–14400 region)
- Commit 10b: Active Sequences / Manage Sequences pages (L16000–22000 region)
- Commit 10c: Smaller/scattered instances (the rest)

- [ ] **Step 3: After EACH commit in this task**

```bash
python -c "import flowdrip_app; print('OK')"
python -m pytest tests/ -q
```

- [ ] **Step 4: Final verification**

```bash
grep -nE 'ui\.label\([^)]*\bCampaign\b' flowdrip_app.py
```

Expected: only intentional remainders (e.g., a label that genuinely says the word "Campaign" in the generic English sense, not as a feature name). The engineer should review each remaining hit and confirm intentional.

- [ ] **Step 5: Brand-name guard**

```bash
grep -nc 'DripDrop' flowdrip_app.py
```

Compare to the count from BEFORE the task (run the same grep at the start of Task 10 and save the count). The two numbers MUST be equal — no `"DripDrop"` strings were modified.

---

## Task 11: Wizard sub-steps "Sequence" → "Timing"

**Files:** Modify `flowdrip_app.py` at the wizard breadcrumb sidebar that appears when a user is inside a build flow.

**Goal:** The wizard shows sub-steps "Emails / Sequence / Contacts / Launch" in the sidebar. The middle one ("Sequence") needs to be "Timing" since "Sequence" as a sub-step inside a "+ New Sequence" wizard reads recursively.

- [ ] **Step 1: Find the wizard breadcrumb code**

```
grep -nE '"Sequence"\s*,|sequence_step_label|wizard_steps' flowdrip_app.py
```

Look for the breadcrumb labels — likely a list/tuple of step names like `["Emails", "Sequence", "Contacts", "Launch"]` or similar. The exact location will be in the wizard or sequence-builder render code (search around `_seq_wizard_header` or `_sq_custom_builder` if those still exist).

- [ ] **Step 2: Update the step label**

When found, replace the literal `"Sequence"` (in this specific wizard-breadcrumb context) with `"Timing"`. Be careful: `"Sequence"` may appear elsewhere as a section header — only replace the wizard-breadcrumb instance.

If the engineer can't unambiguously identify the wizard breadcrumb in the code, mark this task as DONE_WITH_CONCERNS and report — the cascade in Task 10 may have already handled it via the page rename to "Sequences" (with "s"), in which case the singular `"Sequence"` for the sub-step is the only remaining one.

- [ ] **Step 3: Verify and commit**

```bash
python -c "import flowdrip_app; print('OK')"
python -m pytest tests/ -q
git add flowdrip_app.py
git commit -m 'rename(ux): wizard sub-step "Sequence" → "Timing"'
```

---

## Task 12: Drip-as-noun cleanup (excluding "DripDrop")

**Files:** Modify `flowdrip_app.py` at every user-visible occurrence of `"drip"` (singular), `"Drip"` (capitalized), `"drips"`, `"Drips"`, `"Drip Plan"`, `"Drip Schedule"`, etc.

**Goal:** Eliminate "drip" as a feature noun. The brand "DripDrop" stays.

- [ ] **Step 1: Find candidates**

```
grep -nE '"[^"]*\bDrip\b[^"]*"' flowdrip_app.py | grep -v DripDrop
```

This finds every double-quoted string containing the word "Drip" as a separate token, EXCLUDING any line that contains "DripDrop". Review each match:

- "Drip Plan" / "Drip Schedule" → "Send Schedule"
- "Drip Campaign" / "drip campaign" → "Sequence" / "sequence"
- "drip" (mid-sentence, lowercase) → "outreach" / "send" / drop, depending on context

- [ ] **Step 2: Apply transforms via Edit**

For each match, decide the appropriate transform based on context. Apply via Edit with exact strings.

- [ ] **Step 3: Brand-name guard**

```bash
DRIP_DROP_COUNT=$(grep -c 'DripDrop' flowdrip_app.py)
echo "DripDrop count: $DRIP_DROP_COUNT"
```

Confirm this count equals the count before Task 12 began. Any difference means a brand-name reference was accidentally modified — REVERT and redo.

- [ ] **Step 4: Verify and commit**

```bash
python -c "import flowdrip_app; print('OK')"
python -m pytest tests/ -q
git add flowdrip_app.py
git commit -m 'rename(ux): drop "drip" as a feature noun (brand name preserved)'
```

---

## Task 13: Phase 4 — Settings tabs (DONE BEFORE Task 14 to keep Signature accessible)

**Sequence note:** The spec lists Phase 3 (kill hub) before Phase 4 (Settings tabs), but in execution we MUST do Settings tabs first. Reason: killing the hub deletes the legacy Signature page; if Settings tabs aren't built yet, users have no Signature page in the gap. Build Settings tabs first → then kill the hub safely.

**Files:** Modify `flowdrip_app.py` to consolidate the AI/Email Setup page (`p_ai_settings`) and the Signature page into a single tabbed Settings page.

- [ ] **Step 1: Find the existing page renderers**

Grep for `def p_ai_settings(` and `def p_signature(` (or similar). Read each to understand what they render today.

- [ ] **Step 2: Refactor `p_ai_settings` into a tabbed shell**

Wrap the existing `p_ai_settings` body in NiceGUI's `ui.tabs()` / `ui.tab_panels()` structure:

```python
def p_ai_settings(s, rf):
    ui.label("Settings").classes("fd-h1")
    with ui.tabs().classes("fd-tabs") as tabs:
        ui.tab("email", label="Email Provider")
        ui.tab("ai", label="AI")
        ui.tab("signature", label="Signature")
    with ui.tab_panels(tabs, value="email").classes("fd-tab-panels"):
        with ui.tab_panel("email"):
            _render_email_provider_panel(s, rf)
        with ui.tab_panel("ai"):
            _render_ai_panel(s, rf)
        with ui.tab_panel("signature"):
            _render_signature_panel(s, rf)
```

- [ ] **Step 3: Extract panel render functions**

Move the existing logic from `p_ai_settings`'s body into two helper functions:
- `_render_email_provider_panel(s, rf)` — the email-account / SMTP setup portion.
- `_render_ai_panel(s, rf)` — the Anthropic API key portion.

Move the existing logic from `p_signature`'s body into `_render_signature_panel(s, rf)`.

The engineer must preserve all existing controls and behaviors. This is not a redesign — just a reorganization.

**Important:** Leave `p_signature` intact for now. The hub-kill task (Task 14) will remove its routing. If we delete it now, the legacy hub page route will crash.

- [ ] **Step 4: Smoke import + tests**

```bash
python -c "import flowdrip_app; print('OK')"
python -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "refactor(ux): consolidate AI/Email Setup + Signature into tabbed Settings page"
```

---

## Task 14: Phase 3 — Kill the legacy hub

**Files:** Modify `flowdrip_app.py`:
- Delete `EMAILS_NAV` constant (L8071–8079).
- Modify `topbar()` function (around L1652) to remove the two hub-toggle pills.
- Modify `AppState.__init__` to drop `self.hub` and `self.ep`.
- Modify `render_page()` (around L7464) to drop the `s.hub == "emails"` branch.
- Find every reference to `s.hub`, `s.ep`, `EMAILS_NAV`, page keys `emails_build`, `sequence`, `prev_launch`, `e_responses`, `e_signature` and clean up.

This is structural — more than a string replace.

- [ ] **Step 1: Pre-flight grep — find all references**

```bash
grep -nE 's\.hub|s\.ep|EMAILS_NAV|"emails_build"|"e_responses"|"e_signature"|"prev_launch"' flowdrip_app.py | wc -l
```

Save the count for comparison.

```bash
grep -nE 's\.hub|s\.ep|EMAILS_NAV|"emails_build"|"e_responses"|"e_signature"|"prev_launch"' flowdrip_app.py > /tmp/hub_refs_before.txt
wc -l /tmp/hub_refs_before.txt
```

Expected: 105+ references. Review each in the engineer's notes — categorize as DELETE, REDIRECT, or PRESERVE.

- [ ] **Step 2: Delete the EMAILS_NAV constant**

In `flowdrip_app.py`, delete the entire EMAILS_NAV literal (L8071–8079). This is a clean delete of the constant and its surrounding comment block. Find with `grep -n '^EMAILS_NAV\s*=' flowdrip_app.py`.

- [ ] **Step 3: Update the `topbar()` function**

Find `def topbar(` (Grep). Read the function to understand the hub-toggle UI. Remove the two pill buttons ("Sales Hub" and "Manage Campaigns") that render the hub toggle. Replace with a logo-only topbar — just the DripDrop logo + the user avatar/menu.

The engineer should preserve any non-hub-related topbar elements (logo, user menu, settings button if present, etc.). Only the two hub pills are removed.

After this edit, `s.hub` should NOT be referenced inside `topbar()`.

- [ ] **Step 4: Simplify AppState**

Find `class AppState:` (Grep). Locate `self.hub = "sales"` and `self.ep = "emails_home"` in `__init__`. Delete those two lines.

Also find any methods on AppState that use `self.hub` or `self.ep` — delete or update them.

- [ ] **Step 5: Update `render_page()`**

Find `def render_page(` (Grep). Read the function. Remove any branch like `if s.hub == "emails": ...` — only the Sales Hub branch remains. Simplify accordingly.

- [ ] **Step 6: Sweep remaining references**

For each reference from Step 1's saved list, decide:
- A) `s.hub` reads → can delete the read or always assume "sales".
- B) `s.hub = "..."` writes → delete the assignment.
- C) `s.ep` reads/writes → delete.
- D) Page-key references like `"emails_build"`, `"e_responses"`, etc. — delete the surrounding code if it routes to those pages, OR redirect to the Sales Hub equivalent (e.g., `"e_responses"` → `"responses"`).

Update each via Edit. This may take 30+ small edits across the file.

- [ ] **Step 6.5: Remove the now-orphaned `p_signature` function**

After the legacy hub is killed and Settings tabs absorb signature content, the standalone `p_signature` function (if it exists at all — search via Grep `def p_signature(`) is unreferenced. Delete the function body. If Grep doesn't find it, skip — it may have been inlined into the email sequencer hub.

Verify no callers remain:
```bash
grep -n 'p_signature\b' flowdrip_app.py
```
Expected: zero hits.

- [ ] **Step 7: Smoke import + tests**

```bash
python -c "import flowdrip_app; print('OK')"
python -m pytest tests/ -q
```

Expected: imports OK, all tests pass.

- [ ] **Step 8: Verify all references gone**

```bash
grep -nE 's\.hub|s\.ep|EMAILS_NAV|"emails_build"|"e_responses"|"e_signature"|"prev_launch"' flowdrip_app.py
```

Expected: zero matches (or only matches in comments referring to the historical state).

- [ ] **Step 9: Commit**

```bash
git add flowdrip_app.py
git commit -m 'refactor(ux): kill legacy Email Sequencer hub; remove topbar pills + EMAILS_NAV'
```

---

## Task 15: Final verification — full grep audit

**Files:** Read-only audit of `flowdrip_app.py`.

- [ ] **Step 1: Audit for leftover "Campaign" instances**

```bash
grep -nE 'ui\.label\([^)]*[Cc]ampaign|ui\.notify\([^)]*[Cc]ampaign' flowdrip_app.py | wc -l
```

Expected: small number (ideally 0). Any remaining hits should be reviewed and decided per the cascade rules from Task 10.

- [ ] **Step 2: Audit for leftover "drip" / "Drip"**

```bash
grep -nE '"[^"]*\bDrip\b[^"]*"' flowdrip_app.py | grep -v DripDrop | wc -l
```

Expected: 0 (or only hits inside comments).

- [ ] **Step 3: Audit brand name preservation**

```bash
grep -c 'DripDrop' flowdrip_app.py
```

Compare to the count from before Task 1. The number MUST equal the original.

- [ ] **Step 4: Audit hub removal**

```bash
grep -nE '\bs\.hub\b|\bs\.ep\b|EMAILS_NAV' flowdrip_app.py
```

Expected: 0 hits.

- [ ] **Step 5: Confirm tests still pass**

```bash
python -m pytest tests/ -v
```

Expected: ALL pass (23 + however many were added during the cascade tasks).

- [ ] **Step 6: Confirm imports**

```bash
python -c "import flowdrip_app, funnelforge_core; print('OK')"
```

Expected: prints OK.

- [ ] **Step 7: If anything fails, address before declaring done**

If Step 4's grep finds residual hub references, fix them in a small commit. If tests fail, fix before continuing. Do NOT proceed to deploy with red tests.

If everything passes, commit a no-op marker:

```bash
git commit --allow-empty -m "ux-rename: final audit complete; ready for live smoke test"
```

---

## Task 16: Phase 5 — Live smoke test on dripdripdrop.ai

**Files:** No file changes. Live deploy + manual verification.

**Per the 2026-04-26 lesson:** static `import flowdrip_app` and `pytest` succeeded but the page render path crashed at runtime. ALWAYS render `/` against a live process before declaring done.

- [ ] **Step 1: Per memory rule — ASK BEFORE DEPLOYING in 8am–5pm PDT window**

If during 8am–5pm PDT, ASK the user "deploy now or end of hour?" and wait. Outside that window, auto-deploy.

If user says "deploy now" or it's outside the window, proceed.

- [ ] **Step 2: Deploy**

```bash
bash _deploy_zero_downtime.sh
```

Expected output: `https check: HTTP 200 in <0.5s`.

- [ ] **Step 3: Pull live page render against `/`**

```bash
ssh -i "$HOME/.ssh/dripdrop" -o ConnectTimeout=30 root@134.199.237.206 \
  "curl -s -o /dev/null -w 'index HTTP %{http_code}, %{time_total}s\n' https://dripdripdrop.ai/"
```

Expected: `index HTTP 200, <0.3s`.

- [ ] **Step 4: Pull recent logs and check for errors**

```bash
ssh -i "$HOME/.ssh/dripdrop" -o ConnectTimeout=30 root@134.199.237.206 \
  "journalctl -u dripdrop --since '5 minutes ago' --no-pager | grep -iE 'error|traceback|nonetype' | head -30"
```

Expected: no output (or only benign warnings).

- [ ] **Step 5: User-driven smoke test (manual)**

Ask the user to open dripdripdrop.ai and verify each renamed page loads without 500:
1. Dashboard — confirm "Today" / "Tomorrow" stat tabs.
2. Replies — confirm sidebar shows "Replies" not "Campaign Radar".
3. Sequences — confirm picker shows "+ New Sequence", "Build from scratch".
4. Active Sequences — open and confirm the page header reads "Active Sequences".
5. Existing Customers — confirm renamed.
6. Reports — confirm renamed.
7. Candidates — confirm renamed.
8. Settings — confirm 3 tabs: Email Provider, AI, Signature.
9. Topbar — confirm NO hub-toggle pills (just logo + user menu).

If any page 500s or shows a partial rename: roll back per Task 17. Otherwise declare done.

---

## Task 17: Rollback procedure (if needed)

**Files:** No file changes. Emergency procedure only.

**Use this only if Task 16 surfaces a runtime issue that's user-blocking on the live site.**

- [ ] **Step 1: Identify the breaking commit (if isolatable)**

```bash
git log --oneline 927c24d..HEAD
```

Identify the commit that introduced the regression. If it's the latest, `git revert HEAD` may suffice. If it's older or the rollback is too complex, deploy from baseline.

- [ ] **Step 2: Roll back the live site**

Either:
A) If you can git-revert the offending commit cleanly:
```bash
git revert <bad-sha>
bash _deploy_zero_downtime.sh
```

B) Or roll back to the last known-good commit via temporary checkout:
```bash
git checkout <good-sha> -- flowdrip_app.py
bash _deploy_zero_downtime.sh
git checkout HEAD -- flowdrip_app.py  # restore working tree
```

- [ ] **Step 3: Verify rollback**

```bash
ssh -i "$HOME/.ssh/dripdrop" root@134.199.237.206 \
  "curl -s -o /dev/null -w 'index HTTP %{http_code}\n' https://dripdripdrop.ai/"
```

Expected: HTTP 200.

- [ ] **Step 4: Diagnose, fix forward, re-deploy**

Investigate the failure (live logs + reproduce locally if possible). Once fixed, re-deploy.

---

## Definition of Done

- [ ] All renames in the spec table land on the `claude/critical-bug-fixes` branch.
- [ ] Task 16 smoke test on dripdripdrop.ai is clean — every renamed page loads, every renamed button works, no 500s in logs.
- [ ] `python -m pytest tests/ -v` passes from a clean checkout.
- [ ] `grep -c 'DripDrop' flowdrip_app.py` matches the pre-Task-1 count exactly (brand name unmolested).
- [ ] `grep -nE '\bs\.hub\b|\bs\.ep\b|EMAILS_NAV' flowdrip_app.py` returns zero hits.
- [ ] `grep -nE 'ui\.label\([^)]*[Cc]ampaign' flowdrip_app.py` returns only intentional remainders, each reviewed by the engineer.
- [ ] Settings page has 3 tabs: Email Provider, AI, Signature.
- [ ] Sidebar shows the new SALES_NAV labels exactly as in Task 1.
- [ ] Topbar shows logo + user menu only (no hub-toggle pills).
- [ ] No data files were modified (`campaigns/*.json`, `scheduled_queue.json`, `signature.txt`, etc. on disk are byte-for-byte identical before/after).

## Risks Reminder

- **Per-page commits in Task 10** are critical. Do not consolidate all 113 cascade renames into one commit.
- **Brand-name guard** must run after every commit in Tasks 9–12. A single careless transform can rewrite "DripDrop" and silently brand-rename the product.
- **`template_name="Slow Drip"`** strings in Task 5 are JSON data, NOT display. Do not change them.
- **Live page-render check** (Task 16 Step 3) is non-negotiable per the 2026-04-26 outage. `pytest` + `import` are not enough.

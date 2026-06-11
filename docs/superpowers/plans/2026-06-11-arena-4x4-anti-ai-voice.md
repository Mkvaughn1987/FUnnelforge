# Arena 4×4: Anti-AI Voice + Redacted Resumes on Email 2 & 4 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Arena 4×4 emails read like a recruiter wrote them (no em dashes, no spaced-hyphen tell, no cliché openers, no AI-tell vocabulary) and attach redacted resume PDFs to Email 2 and Email 4.

**Architecture:** Three small, surgical changes to `flowdrip_app.py`. (1) A new pure function `_humanize_email_text` repairs dashes and strips cliché openers, hooked into the existing AICB email post-process loop. (2) Tighten the shared `_DRIPDROP_PLAYBOOK` prompt so the model stops emitting the spaced-hyphen dash and AI-tell words. (3) A new pure helper `_resume_attach_indices` reroutes redacted-resume PDFs to Email 2 and Email 4 for the 4×4. Cadence/timing is untouched.

**Tech Stack:** Python 3, `pytest`, NiceGUI app (`flowdrip_app.py`), Anthropic SDK (generation prompt only).

Spec: `docs/superpowers/specs/2026-06-11-arena-4x4-anti-ai-voice-design.md`

---

## File Structure

- Modify: `flowdrip_app.py`
  - Add `_CLICHE_OPENERS` tuple + `_humanize_email_text()` near the other text scrubbers (just below `_strip_dashes`, ~L6782).
  - Add `_resume_attach_indices()` pure helper near the same scrubber area (~L6782).
  - Edit `_DRIPDROP_PLAYBOOK` text (~L8137 and the "NEVER DO THESE" block ~L8144).
  - Hook `_humanize_email_text` into the email post-process loop (~L8659 / current L33659-33661).
  - Replace the redacted-PDF attach loop body (current L33697-33708) to use `_resume_attach_indices`.
- Test: `tests/test_arena_4x4_voice.py` (new)

Note: `_humanize_email_text` runs in the shared AICB post-process loop, so it cleans **all** AICB-generated campaigns, not only the 4×4. This is intentional and strictly better (it only removes dashes and known cliché openers, both already forbidden by the playbook for every type). The resume rerouting is gated to `fourbyfour` so other campaign types keep their current behavior.

---

## Task 1: `_humanize_email_text` — dash repair + cliché-opener removal

**Files:**
- Modify: `flowdrip_app.py` (add after `_strip_dashes`, ~L6782)
- Test: `tests/test_arena_4x4_voice.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_arena_4x4_voice.py`:

```python
"""Anti-AI voice helpers for the Arena 4x4 campaign.

Spec: docs/superpowers/specs/2026-06-11-arena-4x4-anti-ai-voice-design.md
Plan: docs/superpowers/plans/2026-06-11-arena-4x4-anti-ai-voice.md
"""
import flowdrip_app as fa


# ── _humanize_email_text: dash repair ──────────────────────────────
def test_lone_em_dash_becomes_sentence_break():
    src = "best talent is passively looking — most never see a posting"
    out = fa._humanize_email_text(src)
    assert "—" not in out
    assert " - " not in out
    assert out == "best talent is passively looking. Most never see a posting"


def test_paired_em_dashes_become_commas():
    src = "our team — all ex-recruiters — handles the search"
    out = fa._humanize_email_text(src)
    assert "—" not in out
    assert out == "our team, all ex-recruiters, handles the search"


def test_numeric_en_dash_range_becomes_to():
    src = "base lands around $130K–$150K for senior PMs"
    out = fa._humanize_email_text(src)
    assert "–" not in out
    assert "$130K to $150K" in out


def test_no_spaced_hyphen_dash_survives():
    src = "two things shifted — comp reset and notice periods stretched"
    out = fa._humanize_email_text(src)
    assert " - " not in out


# ── _humanize_email_text: cliche opener removal ────────────────────
def test_cliche_opener_sentence_removed():
    src = ("Hi {FirstName},<br><br>I hope this email finds you well."
           "<br><br>47 days is the current fill window.")
    out = fa._humanize_email_text(src)
    assert "i hope this email finds you well" not in out.lower()
    assert out == ("Hi {FirstName},<br><br>47 days is the current "
                   "fill window.")


def test_ordinary_text_unchanged():
    src = "Hi {FirstName},<br><br>Saw the Wyoming buildout announcement."
    assert fa._humanize_email_text(src) == src


def test_non_string_passthrough():
    assert fa._humanize_email_text(None) is None
    assert fa._humanize_email_text(123) == 123
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_arena_4x4_voice.py -q`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_humanize_email_text'`

- [ ] **Step 3: Implement `_humanize_email_text`**

Add directly after the end of `_strip_dashes` (after current L6781), before `def _sanitize_candidate_salary_ask`:

```python
# Cliche throat-clearing openers the playbook forbids but the model
# occasionally still emits. Lowercase, no trailing punctuation.
_CLICHE_OPENERS = (
    "i hope this email finds you well",
    "i hope this message finds you well",
    "i hope this finds you well",
    "i hope all is well",
    "i hope you are doing well",
    "i hope you're doing well",
    "i hope you are having a great week",
    "i hope you're having a great week",
    "i hope you had a great weekend",
    "hope this finds you well",
    "hope you are well",
    "hope all is well",
)


def _humanize_email_text(text):
    """Make AI-generated email copy read like a person wrote it.

    Two conservative passes, safe on any generated subject/body:
      1. Dash repair, so no spaced-hyphen "AI tell" ever survives:
         a lone em dash becomes a sentence break (period + capitalized
         next word); a matched pair of em dashes becomes parenthetical
         commas; a numeric en-dash range becomes "to"; any other en dash
         becomes a comma.
      2. Cliche-opener removal: delete a known throat-clearing opener
         sentence ("I hope this email finds you well.") if it slipped
         through, then tidy the surrounding <br> breaks.

    Does NOT rewrite wording mid-sentence, so it cannot break grammar.
    Non-strings pass through unchanged.
    """
    if not isinstance(text, str) or not text:
        return text
    import re as _re

    def _fix_line(line):
        # numeric en-dash range -> "to"
        line = _re.sub(r'(\d)\s*–\s*(\d)', r'\1 to \2', line)
        # matched pair of em dashes (parenthetical) -> commas
        if line.count('—') == 2:
            line = _re.sub(r'\s*—\s*', ', ', line)
        # lone/odd em dash before a lowercase word -> ". " + capitalize
        line = _re.sub(r'\s*[—―]\s*([a-z])',
                       lambda m: '. ' + m.group(1).upper(), line)
        # any remaining em dash (before number/symbol) -> sentence break
        line = _re.sub(r'\s*[—―]\s*', '. ', line)
        # remaining en dash between non-digits -> comma
        line = _re.sub(r'\s*–\s*', ', ', line)
        return line

    # Split on <br> so HTML breaks are preserved and pair-detection stays
    # local to a single line.
    parts = _re.split(r'(<br\s*/?>)', text)
    parts = [p if p.lower().startswith('<br') else _fix_line(p)
             for p in parts]
    s = ''.join(parts)

    # Remove a cliche opener sentence if present.
    low = s.lower()
    for _op in _CLICHE_OPENERS:
        idx = low.find(_op)
        if idx == -1:
            continue
        end = s.find('.', idx)
        end = (end + 1) if end != -1 else (idx + len(_op))
        s = s[:idx] + s[end:]
        low = s.lower()

    # Tidy: collapse 3+ consecutive <br> left by removal, squeeze spaces.
    s = _re.sub(r'(?:\s*<br\s*/?>\s*){3,}', '<br><br>', s)
    s = _re.sub(r'  +', ' ', s)
    s = _re.sub(r'\s+\.', '.', s)
    return s.strip()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_arena_4x4_voice.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_arena_4x4_voice.py flowdrip_app.py
git commit -m "feat(4x4): add _humanize_email_text dash + cliche-opener scrubber"
```

---

## Task 2: Tighten `_DRIPDROP_PLAYBOOK` (kill spaced-hyphen fallback + ban AI-tell words)

**Files:**
- Modify: `flowdrip_app.py` (~L8137 and the "NEVER DO THESE" block ~L8144)
- Test: `tests/test_arena_4x4_voice.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_arena_4x4_voice.py`:

```python
# ── _DRIPDROP_PLAYBOOK hardening ───────────────────────────────────
def test_playbook_drops_spaced_hyphen_dash_fallback():
    # The old text offered '" - "' as an acceptable dash substitute,
    # which is itself an AI tell. It must be gone.
    assert 'periods, or " - "' not in fa._DRIPDROP_PLAYBOOK


def test_playbook_bans_ai_tell_vocabulary():
    for word in ("streamline", "leverage", "delve", "furthermore",
                 "seamless"):
        assert word in fa._DRIPDROP_PLAYBOOK
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_arena_4x4_voice.py -k playbook -q`
Expected: FAIL (`test_playbook_drops_spaced_hyphen_dash_fallback` fails because the string is still present; `test_playbook_bans_ai_tell_vocabulary` fails because the words are not yet listed)

- [ ] **Step 3: Edit the playbook text**

Edit A — replace the spaced-hyphen fallback (current L8137-8138):

Old:
```
- NEVER use em dashes or en dashes. Use commas, periods, or " - "
  (space hyphen space). This is the #1 most important formatting rule.
```
New:
```
- NEVER use em dashes or en dashes. Replace each one with a comma or a
  period. NEVER substitute a spaced hyphen " - " for a dash. A " - "
  standing in for a dash reads as templated AI copy. This is the #1
  most important formatting rule.
```

Edit B — add an AI-tell vocabulary ban. Insert immediately after the
line `- Never say "circle back", "touch base", "synergies", "moving the needle"` (current L8144):

```
- Never use AI-tell vocabulary: streamline, leverage, elevate, delve,
  robust, seamless, unlock, spearhead, "in today's market", "fast-paced",
  "it's worth noting", moreover, furthermore, "navigate the landscape",
  "that being said". Use the plain words a busy recruiter would type.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_arena_4x4_voice.py -k playbook -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_arena_4x4_voice.py
git commit -m "feat(playbook): forbid spaced-hyphen dash fallback + ban AI-tell words"
```

---

## Task 3: Hook `_humanize_email_text` into the AICB email post-process loop

**Files:**
- Modify: `flowdrip_app.py` (current L33659-33661, inside the `for _em in campaign_data.get("emails", [])` loop)

This wires the Task 1 function into generation. The loop currently applies
`_strip_dashes` (which converts dashes to the " - " tell). We humanize
first, then keep `_strip_dashes` as a harmless final safety net.

- [ ] **Step 1: Apply the edit**

Old (current L33659-33661):
```python
                                # Strip ALL em/en dashes from body AND subject
                                _b = _strip_dashes(_b)
                                _s = _strip_dashes(_s)
```
New:
```python
                                # Humanize first: smart dash repair (no
                                # spaced-hyphen tell) + cliche-opener removal.
                                _b = _humanize_email_text(_b)
                                _s = _humanize_email_text(_s)
                                # _strip_dashes is now a no-op safety net for
                                # any stray dash the humanizer missed.
                                _b = _strip_dashes(_b)
                                _s = _strip_dashes(_s)
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `python -c "import flowdrip_app"`
Expected: no output, exit 0 (no SyntaxError)

- [ ] **Step 3: Run the full new test file + a smoke of the suite**

Run: `python -m pytest tests/test_arena_4x4_voice.py -q`
Expected: PASS (9 passed)

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(4x4): humanize generated email copy before save"
```

---

## Task 4: Route redacted resume PDFs to Email 2 & 4 for the 4×4

**Files:**
- Modify: `flowdrip_app.py` (add `_resume_attach_indices` near `_strip_dashes` ~L6782; replace attach loop body at current L33697-33708)
- Test: `tests/test_arena_4x4_voice.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_arena_4x4_voice.py`:

```python
# ── _resume_attach_indices: PDF placement ──────────────────────────
def test_4x4_resumes_target_email_2_and_4():
    # 4x4 has 4 emails (indices 0..3). Resumes go on Email 2 and 4.
    assert fa._resume_attach_indices("fourbyfour", 4) == [1, 3]


def test_non_4x4_keeps_legacy_email_1_and_3():
    assert fa._resume_attach_indices("talentdrop", 4) == [0, 2]


def test_attach_indices_clamped_to_email_count():
    # Never return an index past the available emails.
    assert fa._resume_attach_indices("fourbyfour", 2) == [1]
    assert fa._resume_attach_indices("talentdrop", 1) == [0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_arena_4x4_voice.py -k attach -q`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_resume_attach_indices'`

- [ ] **Step 3: Implement `_resume_attach_indices`**

Add after `_humanize_email_text` (~L6782):

```python
def _resume_attach_indices(camp_type, n_emails):
    """Email indices (0-based) that should carry redacted resume PDFs.

    Arena 4x4 places them on Email 2 and Email 4 (indices 1 and 3) so the
    resumes sit beside the candidate-heavy touches. Every other campaign
    keeps the legacy Email 1 and Email 3 placement (indices 0 and 2).
    Indices past the available email count are dropped.
    """
    targets = [1, 3] if camp_type == "fourbyfour" else [0, 2]
    return [i for i in targets if i < n_emails]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_arena_4x4_voice.py -k attach -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Wire the helper into the attach loop**

Replace the attach loop body (current L33697-33708):

Old:
```python
                            # Attach redacted resume PDFs to early email steps
                            if _resume_pdfs and campaign_data.get("emails"):
                                ri = 0
                                for ei, em in enumerate(campaign_data["emails"]):
                                    if ri >= len(_resume_pdfs):
                                        break
                                    if ei == 0:  # attach to first email (candidate intro)
                                        em.setdefault("attachments", []).append(_resume_pdfs[ri])
                                        ri += 1
                                    elif ei == 2 and ri < len(_resume_pdfs):
                                        # attach remaining to 3rd email
                                        em.setdefault("attachments", []).append(_resume_pdfs[ri])
                                        ri += 1
```
New:
```python
                            # Attach redacted resume PDFs. 4x4 -> Email 2 & 4
                            # (indices 1, 3); other types -> Email 1 & 3.
                            if _resume_pdfs and campaign_data.get("emails"):
                                _emails = campaign_data["emails"]
                                _targets = _resume_attach_indices(
                                    (s.aicb_camp_type or "").strip(),
                                    len(_emails))
                                ri = 0
                                for ei in _targets:
                                    if ri >= len(_resume_pdfs):
                                        break
                                    _emails[ei].setdefault(
                                        "attachments", []).append(
                                        _resume_pdfs[ri])
                                    ri += 1
```

- [ ] **Step 6: Verify import + full test file**

Run: `python -c "import flowdrip_app"` then `python -m pytest tests/test_arena_4x4_voice.py -q`
Expected: import clean; PASS (12 passed)

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py tests/test_arena_4x4_voice.py
git commit -m "feat(4x4): attach redacted resumes to Email 2 and Email 4"
```

---

## Final verification

- [ ] **Run the new suite + the touched neighbors**

Run: `python -m pytest tests/test_arena_4x4_voice.py tests/test_sb_helpers.py -q`
Expected: all PASS.

- [ ] **Import smoke**

Run: `python -c "import flowdrip_app; print('ok')"`
Expected: `ok`

---

## Self-Review (completed by plan author)

- **Spec coverage:** Layer A (voice guard) -> Task 2 tightens the shared playbook already injected into the 4×4 prompt. Layer B (humanizer) -> Tasks 1 + 3. Layer C (leave `_strip_dashes` global behavior alone) -> respected; `_strip_dashes` is unchanged and only runs as a safety net after the humanizer. Piece 2 (resumes on Email 2 & 4) -> Task 4. Cadence untouched -> no task changes timing. All covered.
- **Placeholder scan:** none; every step has concrete code/commands.
- **Type consistency:** `_humanize_email_text(text)`, `_resume_attach_indices(camp_type, n_emails)`, `_CLICHE_OPENERS`, `_DRIPDROP_PLAYBOOK` referenced identically across tasks.

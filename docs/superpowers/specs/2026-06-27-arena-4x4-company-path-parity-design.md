# Arena 4×4 — Company-Path Parity & Candidates-On-Every-Email

**Date:** 2026-06-27
**File touched:** `flowdrip_app.py` (AICB generation in the wizard `_run` closure)
**Status:** Approved design

## Problem

Arena 4×4 can be reached through two entry points that both run through the
AI Campaign Builder (AICB):

1. **Arena 4×4 entry tile** (main chooser) — sets
   `aicb_camp_type="fourbyfour"`, `aicb_target_mode="market"`,
   `aicb_style_locked=True`. The user supplies a niche/industry, no company.
2. **"Search by company" tile → campaign-style picker → Arena 4×4** — sets
   `aicb_target_mode="company"`; a company is captured via Autofill.

Both paths generate from the **same** catalog sequence
(`AICB_CAMPAIGN_TYPES["fourbyfour"]`, the `touch_sequence`), the same
candidate-highlights block, and the same BLS stats block. Yet the emails come
out different, and the company path is missing candidates on some emails.

### Cause 1 — mode-driven framing divergence

The emails are framed off a single computed flag:

```python
is_niche_mode = bool(niche_str) and not company   # ~line 34833
```

- Entry tile → no company, has niche → `is_niche_mode = True` → **market**
  framing.
- Search-by-company → company set → `is_niche_mode = False` → **company**
  framing.

`is_niche_mode` drives three things in the email content:

- **Research brief** — market brief (~34836) vs. company-specific brief (~34855).
- **`style_note`** — "position as market specialist" (~34940) vs. "reference
  the company's specific projects" (~34944).
- **Brief label** in the campaign prompt — `MARKET BRIEF` vs. `COMPANY BRIEF`
  (~35061).

So the same campaign style produces market-positioned emails from one tile and
company-positioned emails from the other.

### Cause 2 — candidates not on every email

The shared candidate-instruction block (`_cand_block`, ~34976–35006) tells the
model:

> "Weave candidates into EVERY OTHER email starting from Email 2 (NOT Email 1)
> … Emails WITHOUT candidates (1, 3, 5, etc.) — focus on market insights…"

For a 4-email Arena 4×4 this yields candidates on emails 2 and 4 only — missing
on 1 and 3. But Arena 4×4 is specified as **"Candidate highlights on every
email"** (catalog line 4087) and its step text asks for the slate on all four
steps. The generic "every other email" rule overrides the 4×4 requirement.
This affects **both** AICB entry points.

## Decision

Arena 4×4 is, by design, a market/slate play — "market a 4–5 candidate slate to
companies hiring your role," not a single-company deep dive (cf. the dedicated
generator's own comment at ~48199–48201). Therefore it should always behave as
the market-framed, candidates-on-every-email version, regardless of how it was
reached.

Scope per user decision: **email subjects + bodies only**. The saved campaign
**name** and the generated **PDF target** keep their existing mode-driven
behavior (the company path may still name the campaign after the searched
company). No re-prompting the user.

## Approach (chosen)

Three surgical changes in the AICB `_run` generation closure, each gated on
`(s.aicb_camp_type or "").strip() == "fourbyfour"`. Nothing outside the 4×4
branch changes, so all other campaign types keep their current behavior.

### Change 1 — force market framing for 4×4

Immediately after `is_niche_mode` is computed (~34833):

```python
# Arena 4×4 is always a market/slate play regardless of entry point
# (entry tile or "search by company" style picker). Force market
# framing so the emails are identical wherever it is picked.
if (s.aicb_camp_type or "").strip() == "fourbyfour":
    is_niche_mode = True
    if not niche_str:
        niche_str = (ind_label or roles_str or "your market").strip()
```

Because the research brief, `style_note`, and brief label all key off
`is_niche_mode`, this one flip aligns all three with the entry-tile output. The
`niche_str` fallback guarantees the market brief is not empty when the user came
in via the company tile without picking a niche.

### Change 2 — candidates on every email for 4×4

In the `_cand_block` construction (the `if _cand_text:` branch, ~34976–35006),
emit a 4×4-specific instruction instead of the "every other email" text:

- Include all candidates on **every** email (Email 1, 2, 3, 4).
- Use a different angle each time (e.g. Email 1: intro/availability;
  Email 2: experience & qualifications; Email 3: why they fit the market/role;
  Email 4: availability & urgency).
- Keep the existing rules about using exact labels, including all candidates,
  no bracketed placeholders, and count wording.

Non-4×4 campaigns keep the existing "every other email starting from Email 2"
instruction unchanged.

### Change 3 — no regressions

Both changes live behind the `fourbyfour` check. Quick Sprint, Candidate-Led
Pitch, High-Volume Push, etc. retain their current framing and candidate
cadence. The candidate `elif` branches (`s.aicb_resumes`,
`s.aicb_candidate_resume`) are not the path 4×4 uses, so they are left as-is.

## Testing

Follow the existing pure/string-level style of `tests/test_arena_4x4_*.py`.

- **Framing test:** with `aicb_camp_type="fourbyfour"` and a company set, the
  generation still selects the market research brief and the `MARKET BRIEF`
  label / market `style_note`. With a non-4×4 type and a company set, it still
  selects the company brief (guards against regression).
- **Candidate-block test:** for 4×4, the built `_cand_block` instructs inclusion
  on every email (no "every other email" / "NOT Email 1" language); for a
  non-4×4 type, the "every other email" language is retained.

Where the existing branch logic is buried inside the wizard `_run` closure and
hard to call directly, the test will exercise the smallest extractable seam
(e.g. a small helper for the candidate-block text and/or the framing decision)
introduced during implementation, keeping the change unit-testable without
standing up the UI.

## Out of scope

- The dedicated `_4x4_generate_emails` / Candidate Finder (CPC) path — not part
  of this change.
- Campaign name and PDF-target parity (explicitly deferred).
- Any change to the 4-step structure, delays, BLS stats block, or signatures.

# Candidate Résumé Picker (View + Attach) — Design

**Date:** 2026-06-22
**Status:** Awaiting user review

## Problem

When an Arena 4x4 (and other candidate-placement campaigns) generates, the system
builds one **redacted résumé PDF per candidate card** and saves it to the user's
PDF folder (`_aicb_build_redacted_resumes` → `Resume_<Candidate>_Redacted.pdf`).
As of the 2026-06-19 design change these are **no longer auto-attached** to Email
2 & 4 — the rationale was to let the user choose placement.

The fallout: the résumés are only reachable through the generic
"Or reuse a generated PDF" dropdown ([flowdrip_app.py:15447](../../flowdrip_app.py)),
mixed in with Market Pulse / Scorecard / Salary Guide PDFs, with no way to **view**
a résumé before attaching it. From the user's seat, the redacted résumés
"disappeared."

## Goal

On the **candidate emails only**, surface the redacted résumés in the attachment
area — where the rest of the attachments live — with the ability to **view each
résumé before attaching**. Keep them **not auto-attached**.

## Non-Goals

- No change to résumé generation (`_aicb_build_redacted_resumes` keeps saving to
  the PDF folder exactly as today).
- No auto-attach. The user attaches manually.
- No change to the non-candidate emails (1, 3, 5…) or to non-candidate PDFs.

## Design

### 1. "Candidate email" detection — `_step_features_candidates(step)`

A new pure helper, render-time, no migration:

```python
def _step_features_candidates(step) -> bool:
    """True if an email step's body contains candidate-profile content.
    Detects both autogen labels ("Candidate A/B/C") and real-name profiles
    (a bold header immediately followed by a bullet list)."""
```

Rule (body = `step.get("body","")`, only for email step types):
- Matches `Candidate [A-Z]\b` (autogen labels), **OR**
- Contains a `<b>…</b>` (or `<strong>`) header within ~80 chars of a `•` bullet
  (real-name profile blocks like the screenshot: **"Candidate B, Engineering
  Manager"** followed by `• …` bullets).

Chosen over index-parity / `_resume_attach_indices` because it reflects what the
email actually contains, works for 4-touch and 6+-touch variants, and needs no
build-time tagging or migration of saved campaigns.

### 2. Render the picker in the attachment area

In the email editor's attachment block ([flowdrip_app.py:15431-15455](../../flowdrip_app.py)),
after the "＋ Upload Attachment" row and **only when** `_step_features_candidates(steps[active])`
is true, render a labeled **"Candidate résumés"** section.

Source list: `Resume_*_Redacted.pdf` files in `_user_pdf_dir()` that are **not
already attached to this step**. Each renders as one compact row:

```
📄 Candidate A — Manufacturing Manager      [ 👁 View ]  [ ＋ Attach ]
```

- **👁 View** → `ui.link(target=f"/pdfs/{name}", new_tab=True)` — the existing
  secure per-user route ([flowdrip_app.py:15256](../../flowdrip_app.py)). Opens the
  PDF in a new tab for preview before attaching.
- **＋ Attach** → `steps[active].setdefault("attachments", []).append(name)`,
  `save_campaign(camp)`, then `rf()`. After attach it leaves the picker (it's now
  in the step's `attachments`) and appears in the normal attachment chip list
  above, which already has View + remove ✕.

Display label: derive a friendly name from the filename
(`Resume_Candidate_A_Redacted.pdf` → "Candidate A"); fall back to the raw filename.

### 3. De-duplicate the generic dropdown

In `_reusable_pdfs` ([flowdrip_app.py:15433](../../flowdrip_app.py)), exclude
`Resume_*_Redacted.pdf` so a résumé is never offered in two places at once — the
generic dropdown keeps the non-résumé PDFs; the new section owns résumés.

## Data Flow

```
generation (unchanged) → Resume_*_Redacted.pdf saved to _user_pdf_dir()
        │
editor render of a candidate email step
        │  _step_features_candidates(step) == True
        ▼
"Candidate résumés" section lists folder's Resume_*_Redacted.pdf not yet attached
        │  user clicks 👁 View → /pdfs/{name} new tab (preview)
        │  user clicks ＋ Attach → step.attachments += name; save; rerender
        ▼
résumé moves to the normal attachment chip list (View + remove already there)
```

## Error / Edge Handling

- **No résumés in folder** → section renders nothing (no empty header).
- **Non-candidate email** → section not rendered at all (scope = candidate emails only).
- **Résumé file deleted off disk after listing** → the existing `/pdfs/{name}` route
  404s on View; Attach still references the name and the normal chip list already
  shows the "file missing" warning state for absent attachments.
- **Real-name profiles** → covered by the bold-header-near-bullet branch of the
  detector.

## Testing

Unit tests (pure functions, no UI):
- `_step_features_candidates`: true for `Candidate A`-label body; true for a
  bold-header + bullet real-name body; false for a market-insight body with no
  candidate block; false for non-email step types.
- Résumé filename → display-label derivation.
- `_reusable_pdfs` excludes `Resume_*_Redacted.pdf`.

Manual: generate a 4x4, open Email 2 → résumés listed with View/Attach; View opens
the PDF; Attach moves it to the chip list and out of the picker; Email 1 shows no
section.

## Files Touched

- `flowdrip_app.py` — new helper `_step_features_candidates`; résumé-label helper;
  attachment-area render block (~L15431); `_reusable_pdfs` filter (~L15433).
- `tests/test_candidate_resume_picker.py` — new.

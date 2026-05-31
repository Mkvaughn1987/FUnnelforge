# Contacts-First AICB Wizard

**Date:** 2026-05-31
**Status:** Approved
**Scope:** Restructure the AI Campaign Builder (AICB) wizard for the **Target a Company** and **Target a Market** tiles so that the very next step after picking a tile is **Upload contact list**. AI reads the uploaded CSV and pre-fills the market/company details for the user to confirm. The other two strategy tiles (Find Candidates, Start with an MPC) are **not** changed.

## Why

Today, picking Target a Company or Target a Market lands the user on a "Target Details" screen where they type a website and click **Autofill with AI** — which then web-searches the company. Users almost always already have a CSV of the contacts they're going after. Asking them to type a URL when the CSV they're about to upload contains the same information (and more) is friction. Reversing the order — *upload first, AI infers details from the contacts* — matches the way recruiters actually start: "I have a list, build me a campaign."

The AI extractor that does this already exists at [flowdrip_app.py:30686](../../../flowdrip_app.py#L30686) — `_analyze_contacts_with_ai` returns company / niche / industry / location / roles / website from a contact sample and explicitly handles single-vs-multi-company lists. This spec is mostly **wiring**, not new AI.

## Goal

1. After clicking Target a Company or Target a Market in the chooser, the user lands on a new **Upload Contact List** step.
2. AI extracts the campaign's market/company details from the CSV.
3. The user sees a **Confirm Details** screen with the AI-inferences pre-filled and editable.
4. The rest of the wizard (Candidates → Campaign Style → Review) is unchanged.
5. The current website + Autofill flow stays accessible as a **`No CSV yet? Enter details manually →`** fallback link, so users without a CSV ready aren't blocked.
6. The CSV uploaded at Step 2 is also the campaign's recipient list — no second upload later.

## Non-goals

- Find Candidates (`target_candidate` wizard) and Start with an MPC: unchanged.
- The AI extractor itself: unchanged.
- The Candidates / Campaign Style / Review screens: unchanged.
- Pricing, marketing copy outside the two new screens, the expanded (legacy non-wizard) mode.
- Auto-deduping against the user's opt-out list at upload time (that already happens downstream).

## New step structure

Internal `aicb_wizard_step` grows from `1..5` to `1..6`. The chooser pre-sets the target type, so the user only ever sees the 5 non-type steps.

| `aicb_wizard_step` | Step name | Status |
|---|---|---|
| 1 | Target type | pre-set by chooser, hidden (today's behavior) |
| **2 (NEW)** | **Upload contact list** | Drop a CSV. `No CSV yet? Enter details manually →` link below. |
| **3 (NEW)** | **Confirm details** | AI-pre-filled, editable form. |
| 4 | Candidates | unchanged (today's Step 3) |
| 5 | Campaign style | unchanged (today's Step 4) |
| 6 | Review & generate | unchanged (today's Step 5) |

Code that hard-codes step numbers — the validator at [flowdrip_app.py:16822-16823](../../../flowdrip_app.py#L16822) (`_ws if _ws in (1, 2, 3, 4, 5) else 1`), Next/Back handlers, the step-pill header — updates from `1..5` to `1..6`.

The chooser tile click handlers ([flowdrip_app.py:16662, 16676](../../../flowdrip_app.py#L16662)) currently set `s.aicb_wizard_step = 2`. They keep doing that — the page rendered at step 2 just becomes the new Upload screen.

## Component 1 — Step 2: Upload contact list

Reuses the existing upload widget (`_on_upload`, `_normalize_rows`, `safe_read_csv_rows`) so we don't fork file-handling logic. The widget already enforces the 50 MB cap, sanitizes filenames, and accepts `.csv` / `.tsv` / `.txt`.

Layout:

```
2. Upload your contact list
Drop a CSV with the contacts you want to reach out to. AI reads
the list and figures out the company / market, industry, and
locations for you.

  [ drag-and-drop zone — Click to browse, or drop a CSV here ]

   Accepted: .csv, .tsv, .txt — up to 50 MB.

No CSV yet? Enter details manually →
```

Behavior:

1. User drops a file → `_on_upload` runs:
   - Reads bytes (capped).
   - Writes to a sanitized tmp path.
   - Parses with `safe_read_csv_rows`.
   - Normalizes rows with `_normalize_rows`.
   - Stores in `s.aicb_contacts`.
2. UI swaps to **"Analyzing your contacts…"** spinner.
3. Background thread runs `_analyze_contacts_with_ai(rows)` (already exists). It writes `aicb_company`, `aicb_niche`, `aicb_industry`, `aicb_sel_locations`, `aicb_sel_roles`, `aicb_website` onto AppState.
4. On completion, `rf()` re-renders. We set `s.aicb_wizard_step = 3` and the Confirm screen renders.
5. If analysis errors out (`_friendly_ai_error`), still advance to Step 3 with whatever fields got populated; show an inline note: *"AI extraction partial — please fill in the missing fields."* Don't block.

The fallback link (`No CSV yet? Enter details manually →`) navigates to the existing website+Autofill UI by routing to a new wizard sub-step (or a small flag, see "Implementation notes"). The rest of the wizard from there is unchanged.

## Component 2 — Step 3: Confirm details

Header strip showing what came in:

```
3. Confirm campaign details
87 contacts loaded · re-upload  ·  re-run AI extraction
```

Pre-filled, editable form. Field set differs by `aicb_target_mode`:

**Target-a-Company:**
- Company name (text input, pre-filled from AI)
- Website (text input, pre-filled from AI)
- Primary industry (existing picker)
- Secondary industries (existing picker)
- Locations (chip picker)
- Roles (chip picker)

**Target-a-Market:**
- Niche / market description (text input, pre-filled from AI)
- (Company and Website hidden)
- Primary industry (existing picker)
- Secondary industries (existing picker)
- Locations (chip picker)
- Roles (chip picker)

Reuses the same pickers used today on the website+Autofill page — `_render_industry_picker`, the locations/roles chip pickers. **Don't duplicate UI**; render the same components against the same state fields.

Validation: Primary industry required to advance. Company name required in Target-a-Company mode. Niche required in Target-a-Market mode.

`Back` returns to Step 2 (Upload). `Next` advances to Step 4 (Candidates).

### Multi-company guard (Target-a-Company mode only)

The AI extractor returns `company=""` and a populated `niche` when it sees multiple companies in the CSV. In Target-a-Company mode, this triggers a yellow banner at the top of Step 3, above the form:

```
⚠ Looks like this list has multiple companies. Target-a-Company is
  built for one named account.

  [ Switch to Target a Market ]   [ Continue with a primary company ]
```

- `[ Switch to Target a Market ]` sets `s.aicb_target_mode = "market"` and re-renders Step 3 in market mode. The niche field appears pre-filled; company / website hide.
- `[ Continue with a primary company ]` leaves mode = company; the company field is blank and the user types the company they want to focus on.

Banner only shows when `aicb_target_mode == "company"` AND AI returned no `company` AND a non-empty `niche`.

### Re-run AI extraction

The header has a small `re-run AI extraction` link. Clicking it re-invokes `_analyze_contacts_with_ai(s.aicb_contacts)` on the already-loaded rows, then re-renders. Useful when the user edited a field, decided the inference was bad, and wants AI to try again from the source data.

## Pipeline: contacts ARE the send list (upload path)

When the user takes the **upload** path, `s.aicb_contacts` is populated at Step 2 and piped through to campaign generation. No second upload later — those uploaded contacts ARE the campaign's recipients.

When the user takes the **manual** fallback path, `s.aicb_contacts` stays empty at wizard time. Contacts get added later via the existing post-campaign Contacts page — same as today's flow. No change to that path.

In both paths, the downstream Candidates step (sample profiles featured in email bodies — distinct concept) and Review step are unaffected.

When the user enters Step 2 from the chooser, `s.aicb_contacts` is reset to `[]` so a stale list from a prior campaign doesn't leak through. (The chooser tile click handlers already do this at [16665, 16678](../../../flowdrip_app.py#L16665).)

## Manual-entry fallback path

The current "Target Details" page (website + Autofill button) is preserved as the fallback rendered when the user clicks **`No CSV yet? Enter details manually →`** on Step 2. Implementation options (decided in the plan, not here):

- **Sub-flag approach (recommended):** keep `aicb_wizard_step = 2`, add `s.aicb_step2_mode = "upload" | "manual"`. When set to `"manual"`, render the existing website+Autofill UI in place of the new Upload UI. `Back` from manual sets `aicb_step2_mode = "upload"` to return to the upload screen.
- **Sub-step approach:** introduce `aicb_wizard_step = "2m"` (or `2.5`). More invasive; the validator/router would need to grow.

Either way, completing the manual flow lands on Step 3 (Confirm) the same way Upload does — the autofill already writes the same state fields.

## Wizard step-pill header

The header bar showing **"1 Target type · 2 Target Details · 3 Candidates · 4 Campaign Style · 5 Review"** updates to:

```
Upload  ·  Confirm  ·  Candidates  ·  Style  ·  Review
```

(Five visible pills because Target Type is still pre-set and hidden, same as today.)

## State changes

New / changed fields on `AppState` (additive — no rename):

- `aicb_step2_mode: str = "upload"` — `"upload"` (new default) or `"manual"` (fallback path active).
- Existing fields keep their meanings: `aicb_contacts`, `aicb_company`, `aicb_niche`, `aicb_industry`, `aicb_primary_industry`, `aicb_secondary_industries`, `aicb_website`, `aicb_sel_locations`, `aicb_sel_roles`, `aicb_target_mode`, `aicb_wizard_step`.

Persistence: `aicb_step2_mode` joins `_AICB_PERSISTED_FIELDS` at [flowdrip_app.py:9801](../../../flowdrip_app.py#L9801) so a WS reconnect mid-flow keeps the user on whichever sub-mode they were on.

## Files changed

- `flowdrip_app.py` — the only file touched. Specifically:
  - The validator at ~16822 (1..5 → 1..6).
  - The wizard's Next/Back handlers (step-number arithmetic and labels).
  - The step-pill header row.
  - New Step 2 (Upload) renderer — extracted from / shared with the existing chooser-page upload widget at ~30734.
  - New Step 3 (Confirm) renderer — reuses pickers from the current Target Details page.
  - The current Target Details page rewires to render only when `aicb_step2_mode == "manual"`.
  - `AppState.__init__` (one new field).
  - `_AICB_PERSISTED_FIELDS` (one new entry).

## Verification

Manual smoke:

1. Click Target a Company → lands on Upload screen.
2. Drop a single-company CSV → spinner → Confirm screen with Company / Website / Industry / Location / Roles pre-filled. Tweak Industry → Next → Candidates step appears.
3. Click Target a Market → upload a multi-company CSV → Confirm screen pre-fills Niche; Company/Website hidden.
4. Click Target a Company → upload a multi-company CSV → yellow multi-company banner appears. Click "Switch to Target a Market" → form re-renders in market mode with niche filled.
5. From Upload, click "No CSV yet? Enter details manually →" → existing website+Autofill page renders inside Step 2 (sub-mode `"manual"`). Type a URL, click Autofill → industry/locations populate. Next advances to Step 3 (Confirm) — same destination as the Upload path, just no contact list loaded. Continue through Candidates / Style / Review; contacts get added later via the post-campaign Contacts page (today's behavior).
6. Reconnect the browser mid-Confirm → user lands back on Confirm with the same data (persistence works).

Automated:

- New pure-function tests for: any helper extracted to detect "multi-company list" from the AI extractor's return shape (if we extract one), and any helper that decides whether the multi-company banner should render.
- Existing tests in `tests/test_strategy_chooser.py` and `tests/test_target_candidate_wizard.py` must still pass (Find Candidates / MPC flows are unchanged).

## Rollout

Single commit + zero-downtime deploy. No data migration — `aicb_contacts` is per-session AppState; the new `aicb_step2_mode` defaults to `"upload"` for everyone. The old Target Details page code is preserved (renders under the manual sub-mode), so any in-flight wizard draft restored from `_aicb_state` still finds a working renderer.

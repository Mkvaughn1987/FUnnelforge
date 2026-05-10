# Phase 2 — Strategy Chooser + Target-a-Candidate guided wizard

**Status:** design approved 2026-05-10
**Branch:** `claude/critical-bug-fixes` (continuing the post-Phase-0 line)
**Owner:** Mike

---

## Goal

Replace today's `Choose a Sequence Type` page with a strategy-first chooser that frames every sequence start in the user's mental model ("what am I trying to do today?"). Five starting places. Inline descriptive copy so users understand each option without clicking. Within that, a complete rewrite of the existing Recruitment Campaign as a stepped, guided wizard ("Target a Candidate") with explicit JD upload, candidate CSV upload, and 4 preset cadences.

## Non-goals

- **No fork of the AICB backend.** Target-a-Client and Target-a-Market are *wrappers* around today's AICB page with different pre-fill / framing copy. Same backend code path.
- **No new sequence engine.** All 5 entry points still emit JSON v1 schema and flow through the existing `_render_emails_screen` / send infrastructure.
- **No changes to Saved Campaigns or Build from scratch beyond renaming.** Those entry points keep their current behavior.
- **No automatic-send feature.** After the Target-a-Candidate wizard generates the sequence, the user lands in the existing email editor for review; nothing fires until they hit Send.
- **No JD parser refactor.** AI extraction of role/skills from the JD reuses today's `_extract_resume_text` / candidate-finder pattern (Claude Haiku with PDF-base64 input). No new parser library.

---

## Architecture

### Top-level chooser

Replace the current `Choose a Sequence Type` UI block with a 5-option chooser. Each option is a card showing:

- An icon
- Title (e.g., "Target a Client")
- A 1-sentence description visible without clicking
- A "Best for: ..." footer line (3 short tags)

Clicking a card sets `s.aicb_camp_type` (existing AppState slot) and routes to the appropriate downstream page.

| Option | Routes to | Pre-fill / framing |
|---|---|---|
| Target a Client | existing AICB page (`p_aicb`) | sets `s.aicb_byos_desc = ""`, sets `s._chooser_origin = "client"`, banner reads "Target a Client" |
| Target a Market | existing AICB page (`p_aicb`) | sets `s.aicb_byos_desc = ""`, sets `s._chooser_origin = "market"`, banner reads "Target a Market" |
| Target a Candidate | NEW page `p_target_candidate` | starts the guided wizard at step 1 |
| Saved Campaigns | existing `Load Campaign` flow | unchanged |
| Build from scratch | existing AICB Free Flow / byos | sets `s.aicb_camp_type = "byos"`, routes to AICB |

The `_chooser_origin` value drives a top-of-page banner on the AICB page so users know which entry door they came through. AICB's existing form, AI calls, and JSON output are untouched.

### Target a Candidate wizard

A new page `p_target_candidate` with a 4-step stepper. Each step is a card with a header showing progress (e.g., "Step 2 of 4"), a Back button, and a Next/Continue button.

**Step 1 — Job Description**

- Two input modes: **Upload** (PDF/DOCX) or **Paste** (textarea).
- On upload: parse via existing `_extract_resume_text` (Claude Haiku, base64 PDF). On paste: use textarea content directly.
- Store parsed text in `s.tc_jd_text` (new AppState slot).
- AI extraction step (silent, runs in background): pulls `role_title`, `key_skills` (list, max 8), `seniority`, `comp_range` (if mentioned), `location` (if mentioned). Stored in `s.tc_jd_parsed` as a dict.
- Continue requires non-empty `tc_jd_text` (AI parse can fail; the raw text is enough to proceed).

**Step 2 — Candidates**

- CSV upload using the same parser as the Contacts page (`_parse_contacts_csv` or whichever helper that file uses).
- Required columns: `name`, `email`. Optional: `current_company`, `current_title`, `linkedin_url`.
- Show preview table (first 10 rows) + total count.
- Store parsed candidate list in `s.tc_candidates` as a list of dicts.
- Allow remove-row from preview.
- Continue requires `len(s.tc_candidates) >= 1`.

**Step 3 — Sequence preset**

Four cards in a 2x2 grid:

1. **1 email and done** — single email, sends on confirm, no follow-up. `delay_days:0, time:"9:00 AM"`.
2. **2 emails, 1 day** — email 1 at 9:00 AM, email 2 at 2:00 PM, same day. `delay_days:[0,0], time:["9:00 AM","2:00 PM"]`.
3. **3 emails, 3 days** — one email per day at 9:00 AM for 3 days. `delay_days:[0,1,2], time:["9:00 AM","9:00 AM","9:00 AM"]`.
4. **Create Your Own** — routes to today's Free Flow / byos AICB experience (rebadged). User builds custom sequence.

User clicks one. Selection stored in `s.tc_preset` (string: `one_email`, `two_emails_1day`, `three_emails_3days`, `custom`).

**Step 4 — Generate + handoff**

- AI generates sequence body content using the parsed JD as primary context. Prompt structure:
  - Recruiter is pitching the role described in `tc_jd_parsed`
  - To passive candidates from `tc_candidates`
  - Cadence per `tc_preset`
  - Tone: respectful, no fake urgency, concise
- Generated emails dropped into a temporary campaign object with `_owner_email`, `name = f"Target a Candidate — {role_title}"`, `emails = [...generated steps...]`.
- Save the campaign via `save_campaign(camp)`.
- Route to existing email editor (`p_emails_build` or whatever the editor's page name is). User reviews, edits if needed, then hits Send through the existing flow.

### Schema

No JSON v1 schema change. The campaign emitted by the wizard conforms to existing schema; only `name` prefixing distinguishes it from other campaigns.

New AppState slots (all initialize to empty in `AppState.__init__`):
- `tc_jd_text: str = ""` — raw JD text (uploaded file content or pasted)
- `tc_jd_parsed: dict = {}` — AI-extracted role metadata
- `tc_candidates: list = []` — list of candidate dicts from CSV
- `tc_preset: str = ""` — selected preset key
- `tc_step: int = 0` — current wizard step (0..3)
- `_chooser_origin: str = ""` — set by chooser to inform AICB banner

---

## Tests

1. **`tests/test_strategy_chooser_renders_5_options.py`** — assert the new chooser page contains all 5 entry points by name + descriptive copy. Source-introspection style consistent with the rest of the test suite.

2. **`tests/test_target_candidate_wizard_steps.py`** — behavioral tests:
   - Step 1 advance fails if `tc_jd_text` empty
   - Step 2 advance fails if `tc_candidates` empty
   - Step 3 stores correct preset key for each card click
   - Step 4 generates a campaign and persists it via `save_campaign`

3. **`tests/test_chooser_origin_banner_on_aicb.py`** — assert the AICB page reads `s._chooser_origin` and renders the appropriate banner ("Target a Client" or "Target a Market").

4. **`tests/test_target_candidate_presets_have_correct_cadence.py`** — assert each preset's cadence (delay_days + times) matches the spec.

5. **`tests/test_jd_parsing_extracts_role_metadata.py`** — assert the JD parser populates `tc_jd_parsed` with at least `role_title` and `key_skills`. Mock the AI call.

---

## Manual validation (post-deploy)

1. Open https://dripdripdrop.ai → log in → Start a Sequence
2. Confirm new chooser shows 5 cards with descriptive copy visible without clicking
3. Click "Target a Client" → confirm AICB page loads with "Target a Client" banner
4. Back, click "Target a Market" → confirm banner now reads "Target a Market"
5. Back, click "Target a Candidate" → confirm wizard step 1 loads
6. Upload a sample JD PDF → confirm AI extracts role title + skills (visible in Step 1's confirmation)
7. Continue → upload a small CSV (name,email,current_company) → confirm preview table shows 3-5 rows
8. Continue → pick "2 emails, 1 day" → continue
9. Confirm AI generates 2 emails using the JD context, lands in the email editor
10. Confirm the saved campaign has the correct name format and cadence

---

## Cutover

Standard zero-downtime deploy via `bash _deploy_zero_downtime.sh`. No migration of existing campaigns required (this is purely an entry-point + new-flow addition).

---

## Decisions locked during brainstorming

| # | Question | Choice |
|---|---|---|
| 1 | Build from scratch survives Phase 2? | Yes, kept as 5th top-level option |
| 2 | Client vs Market page separation | Wrapper pre-fill (same AICB page, different framing) |
| 3 | JD usage downstream | Primary context for AI sequence generation |
| 4 | Candidate list source | CSV upload (same parser as Contacts) |
| 5 | Sequence preset cadence | Per spec: 1-and-done, 2 emails 1 day morning+afternoon, 3 emails 3 days |
| 6 | Post-generation handoff | Drop into existing email editor |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| AI JD parsing returns garbage | Medium | Step 1 advance only requires raw text, not parsed dict; user can proceed even if parse fails |
| CSV uploads with weird encodings | Medium | Reuse existing Contacts CSV parser (already battle-tested per memory `feedback_csv_encoding`) |
| Generated sequence quality is poor for 1-and-done | Low-Medium | Single email gets the most prompt attention; the cadence is itself a constraint (force brevity) |
| Wrapper banner makes AICB feel cluttered | Low | Banner is dismissible; user can close it after first view |
| Existing AICB users don't notice the new chooser | Low | Old "AI Campaign Builder" entry point is REMOVED — they'll see the new chooser by default |
| The 4 new presets have hidden interactions with the queue scheduler | Medium | Tests assert cadence at the JSON-emit layer; smoke check post-deploy verifies a real send fires correctly |

## Estimated effort

5-7 days of focused work, ~14-16 implementation tasks.

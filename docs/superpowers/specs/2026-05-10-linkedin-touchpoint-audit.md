# LinkedIn Touchpoint Audit

Date: 2026-05-10

## Goal of the audit

Per user request: every sequence should have exactly one LinkedIn touchpoint, positioned immediately after the first email (i.e., `email_1 → linkedin → email_2 → ...`). This audit catalogs current state across the 4 sequence sources before any code change.

---

## Source 1 — AICB Campaign Builder

### AICB_CAMPAIGN_TYPES inventory

All non-Free-Flow presets encode their sequence as a literal step-by-step string passed directly into the Claude prompt. Every preset currently places exactly one LinkedIn step at Step 2, immediately after the first email.

| Campaign type | LI count in description | LI position(s) | Notes |
|---|---|---|---|
| blitz / The Splash | 1 | Step 2 (after email 1, delay_days:1) | Correct pattern |
| talentdrop / The Talent Drop | 1 | Step 2 (after email 1, delay_days:1) | Correct pattern |
| flood / The Surge | 1 | Step 2 (after email 1, delay_days:1) | Correct pattern; description only encodes 8 steps despite "10 steps" label |
| sidequest / The Current | 1 | Step 2 (after email 1, delay_days:2) | Correct pattern |
| fullstream / The Waterfall | 1 | Step 2 (after email 1, delay_days:2) | Correct pattern |
| victorycard / The Victory Card | 1 | Step 2 (after email 1, delay_days:0) | Structurally correct (after email 1) but LI fires same day as email 1, not the day after |
| byos / Free Flow | 0 | N/A — user writes their own description | No LI constraint enforced by the preset |

### AICB generation prompt

The AICB generation prompt (flowdrip_app.py ~L29489–29528) assembles the campaign prompt dynamically. For preset campaign types, it injects the `touch_sequence` string verbatim and instructs Claude to follow it exactly:

```
'Then write a campaign following this EXACT sequence:\n'
f'{touch_sequence}\n\n'
```

For Free Flow (byos), the prompt instead says:

```
'The user wants a CUSTOM sequence. Here is their description:\n'
f'{s.aicb_byos_desc}\n\n'
'Design the sequence based on their instructions. Use step_type values: '
'email_auto, linkedin, call, task_general. Set appropriate delay_days.\n\n'
```

The JSON example in the prompt shows a LinkedIn step at position 2 with `delay_days:2`, which gently nudges the model toward that pattern — but it is not a hard constraint:

```
'Return ONLY valid JSON:\n'
'{"synopsis":"...","campaign_name":"...",'
'"emails":[{"week":1,"name":"Step 1 - ...",'
'"subject":"...","body":"Hi {FirstName},<br><br>...",'
'"delay_days":0,"time":"9:00 AM","step_type":"email_auto"},'
'{"week":1,"name":"Step 2 - ...",'
'"subject":"...","body":"Hi {FirstName},<br><br>...",'
'"delay_days":2,"time":"10:00 AM","step_type":"linkedin"},...]}'
```

**Constraint on LI placement:** None explicit in the prompt text. For preset campaign types, correct placement is enforced by the `touch_sequence` string. For Free Flow (byos), placement is entirely up to the AI.

There is also a separate "Recruiting Sequence" generator (~L41896–41985) used when the Recruiting Campaigns page builds a sequence. That prompt (L41901–41924) contains no LinkedIn steps at all in its JSON example and no LI placement instructions — it generates email-only sequences.

---

## Source 2 — Preset library

The preset library is the same set as Source 1 — all presets live inside `AICB_CAMPAIGN_TYPES` (flowdrip_app.py L3447–3588). There is no separate preset definition file. The table in Source 1 covers all preset types.

The hardcoded `FULL_STREAM_MONTHS` block (~L3623+) is a Python data structure (not an AICB prompt string) used for the legacy "Full Stream" display. It also places LinkedIn at touch 2 immediately after the intro email (touch 1), with `delay_days:2` (flowdrip_app.py ~L3630–3632). This is correct.

---

## Source 3 — Saved campaigns (user's local machine)

Scanned: `C:\Users\mkvau\AppData\Local\DripDrop\Campaigns\` — 110 JSON files, 109 parseable (1 skipped: `responded.json` — no `emails`/`steps` array).

| Category | Count | Example campaign names |
|---|---|---|
| 0 LinkedIn touches | 42 | `Holiday_Campaign.json`, `Default 7 Email Campaign.json`, `Austin_Engineering_-_Engineer_Campaign.json` |
| 1 LI after email 1, step 2 (CORRECT) | 53 | `Aerospace_CNC_Machine_Manufacturing_-_CNC_Machinist_Campaign.json`, `Barnes_Aerospace___Ogden_Division___CNC_Machinist___2nd_Shif.json`, `JE_Dunn_Construction_-_Project_Manager_Campaign.json` |
| 1 LI but wrong position | 7 | `Data_Center_Construction_-_Superintendent___PM_Hiring_Campai.json` (LI at step 8, 6 emails before), `TT.json` (LI at step 4, 3 emails before), `CNC-Denv.json` (LI at step 2, but 0 emails before — LI is first) |
| 2+ LI touches | 7 | `4Rivers_-_Heavy_Equipment_Mechanic_Campaign.json` (3 LI: steps 2, 8, 15), `Aerospace_Manufacturing_-_CNC_Machinist_Campaign.json` (3 LI: steps 2, 8, 10), `Anthony_Machine_-_CNC_Machinist_Campaign.json` (2 LI: steps 2, 8) |

**Total campaigns scanned: 109**

Notes on the wrong-position campaigns:
- `CNC-Denv.json`, `Custom_Campaign.json`, `Envirotech_OKC.json`, `LI_Check.json`, `WY.json` — LI is at step 1 or step 2 with no email before it (LI fires first, before any email).
- `TT.json` — LI at step 4, after 3 emails.
- `Data_Center_Construction_...` — LI at step 8, after 6 emails (deeply buried).

Notes on the multiple-LI campaigns:
- All 7 have LI at step 2 (correct first touch) plus additional LI steps deeper in the sequence (steps 6–15). The secondary LI steps appear to be remnants from longer "Full Stream"-style sequences that were generated when no placement rule existed.

---

## Source 4 — Free Flow wizard

### Grep results

Relevant matches for "free flow" / "byos" / "wizard" in `flowdrip_app.py`:

- L3583: `("byos", "Free Flow", "You design it", "#F59E0B", ...)` — campaign type definition
- L8840: `self.aicb_camp_type = "byos"` — Free Flow is the default campaign type on app start
- L8841: `self.aicb_byos_desc = ""` — user's custom description string
- L9464: "Pick a preset ... or build a Free Flow — any mix of emails, calls, and LinkedIn touches."
- L13140–13238: **Step-add panel** — the UI component that lets users insert any step type at any position

### Step-add UI handler

**File:line:** `flowdrip_app.py:13139–13238`

The "Add Step" panel (`STEP_OPTIONS`) presents five step types to choose from: Email, Phone Call, LinkedIn, SMS, Task. The user picks a type and then picks an insertion position ("Beginning" or "After step N"). There is **no enforcement** of LinkedIn count or placement:

- Multiple LinkedIn steps can be added — there is no guard that checks whether a LinkedIn step already exists.
- LinkedIn can be inserted at any position, including before the first email.
- No warning is shown if the user places LI out of sequence or adds a second LI.

The confirmation handler (`_confirm_add_step`, L13207–13232) inserts the step and renumbers the sequence but contains no validation logic related to LinkedIn placement.

---

## Summary of gaps

- **Source 1 (AICB presets):** All 6 named presets correctly encode "1 LI at Step 2." The gap is Free Flow (byos) — the AI prompt provides only a soft example hint; there is no hard rule preventing the AI from adding LI at the wrong position or adding multiple LI steps.
- **Source 3 (Saved campaigns):** 56 of 109 campaigns (51%) need migration: 42 have zero LinkedIn touches and 7 have multiple LI steps. The 7 wrong-position campaigns are a smaller but noteworthy group where LI either fires before any email or is buried deep in the sequence.
- **Source 4 (Free Flow wizard):** The step-add UI has no guardrails — users can freely add LinkedIn at any position and add as many as they want. This is the root cause of both the wrong-position and multiple-LI categories in saved campaigns.

---

## Migration risk for existing saved campaigns

- **Zero-LI campaigns (42 files) are relatively safe to auto-migrate** — inserting a LinkedIn step at position 2 requires only a splice operation on the `emails` array. However, many of these (e.g., `Holiday_Campaign.json`, `Candidate_-_Start_Date_Follow-Up.json`, `4_touch__3_day_recruitment__MV_.json`) are candidate-facing or holiday sequences where a LinkedIn connect step would be inappropriate. A content-type filter or an opt-in prompt would be safer than a blanket auto-insert.
- **Multiple-LI campaigns (7 files) carry the highest migration risk** — removing secondary LI steps means deleting content the user may have customized (connection messages, DM scripts). These should be surfaced individually for manual review rather than auto-fixed.
- **Wrong-position campaigns (7 files) are moderate risk** — moving the LI step is a position change, not a deletion, but renumbering downstream steps could shift scheduled send dates if campaigns are already live or queued.

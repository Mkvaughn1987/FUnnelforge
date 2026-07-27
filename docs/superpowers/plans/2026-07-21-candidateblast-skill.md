# CandidateBlast Companion Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the CandidateBlast Claude skill — candidate-first job finding + MPC-style campaign launch for Mike's sessions — proving the search/rank/launch path before the in-app build.

**Architecture:** A skill at `~/.claude/skills/candidateblast/` mirroring the `pipelineblast` skill's shape (SKILL.md + per-phase references). Zero app changes: the live campaign API (`POST /api/v1/campaigns`, template `fivebythree`) already accepts a pinned `candidates[]` slate `{label, role, bullets[], years?, target_salary?}` and attaches server-generated redacted résumés. Phases: intake (1–3 candidates → anonymized cards) → job search (Indeed/ZipRecruiter MCP + web search; local + nationwide; 10 options) → Mike picks → ZoomInfo Managers+ contacts (Talent headless-preview method from pipelineblast) → per-company campaign POST from a connected dripdripdrop.ai browser tab.

**Tech Stack:** Claude skill (markdown), MCP connectors (Indeed, ZipRecruiter, ZoomInfo enrichment), Claude-in-Chrome (ZoomInfo Talent reveals + DripDrop API calls), DripDrop campaign API.

**Out of scope (separate plans):** Plan B — in-app "Find Openings" step (UI, server-side search, drafts). Plan C — contact-request queue + scheduled bridge agent. Plan C must resolve: the proven ZoomInfo email-reveal method needs a **browser session** (Talent tab), which a cloud bridge agent may not have — verify the ZoomInfo MCP connector can return work emails, or the bridge falls back to a local scheduled run.

---

### Task 1: Skill scaffold — SKILL.md

**Files:**
- Create: `C:\Users\mkvau\.claude\skills\candidateblast\SKILL.md`

- [ ] **Step 1: Read the writing-skills conventions**

Invoke the `superpowers:writing-skills` skill and keep its checklist in mind (frontmatter description = triggers + capability, references read per-phase, no secrets in the skill).

- [ ] **Step 2: Write SKILL.md**

Frontmatter `name: candidateblast`; description must cover triggers: "run CandidateBlast", "find openings for <candidate>", "market <candidate> out", "start an MPC from <candidates>", "who's hiring for <candidate>". Body content:

```markdown
# CandidateBlast — candidate-first job finder + campaign launcher

Mike hands you 1–3 candidates; you find live openings they fit and launch a per-company
DripDrop campaign pitching that exact slate. This is the mirror of pipelineblast (which
starts from a role/geo/industry and lets the server match the bench): **CandidateBlast
always pins the slate** — the campaign POST includes `candidates[]`, never omits it.

## Inputs (required — do not guess)
- **1–3 candidates** (max 3): résumé files, pasted résumé text, or names Mike says are in
  his DripDrop pool. If more than 3 are given, ask which 3.
- **Intake confirm** (one message, pre-filled from the résumés, Mike confirms/corrects):
  location to search first, industry, target job title(s).

## Phases (read each reference when you start that phase)
1. **Candidate intake → anonymized cards** → `references/candidate-intake.md`
2. **Job search → 10 options** (local + nationwide, recent, medium-sized) →
   `references/job-search.md`
3. **Mike picks the targets** — present the 10 in chat (company, role, location + badge,
   posted date, source link, size, one-line fit). STOP and wait for his picks. Never
   auto-launch.
4. **Pull Managers+ contacts per chosen company** → `references/zoominfo-contacts.md`
5. **Launch one campaign per chosen company** (template `fivebythree`, WITH
   `candidates[]`) → `references/dripdrop-campaign.md`

## Hard rules
- **Max 3 candidates; the slate is exactly who Mike gave you** — no bench filling, no
  synthesized candidates, no `candidates[]` omission.
- **Local first, nationwide labeled:** search both, but if the local side is empty say so
  explicitly; never silently go nationwide-only.
- **Mike picks; you never choose the send targets.**
- **<5 Managers+ at a company = advisory** — tell Mike ("only N decision-makers found"),
  let him decide to keep or swap; don't auto-drop.
- Redaction ethics: cards carry real skills/duties/dates but **no names, no employer
  names, no contact info, no location**. Labels are "Candidate A/B/C".
- Live sends are real — reuse pipelineblast's dedupe master before pitching a company
  already worked, and report skips honestly.

## End-of-run summary
Candidates (labels only), intake used, options shown (10 w/ local/nationwide split),
Mike's picks, per company: contacts pulled + campaign_id + schedule (all weekdays) or the
skip/error reason, and the dedupe-master update.
```

- [ ] **Step 3: Verify frontmatter + structure against the writing-skills checklist** (description contains concrete trigger phrases; references exist or are created by Tasks 2–5).

### Task 2: references/candidate-intake.md

**Files:**
- Create: `C:\Users\mkvau\.claude\skills\candidateblast\references\candidate-intake.md`

- [ ] **Step 1: Write the reference**

Content (complete):

```markdown
# Phase 1 — Candidates in → anonymized cards

**Goal:** turn 1–3 candidates into (a) an intake profile for searching and (b) the exact
`candidates[]` cards the campaign POST will pin.

## Accepting candidates
- Résumé files (PDF/docx) → read them. Pasted text → use as-is.
- A name only ("use Cashion from my pool") → look in
  `%LOCALAPPDATA%\DripDrop\candidate_pool.json` (fields incl. `resume_text`). If the name
  isn't there, ask Mike for the résumé — never invent a profile.

## Build the intake profile (drives Phase 2 search)
From each résumé pull: current/recent titles, top skills/tools, industries worked,
seniority (years), home metro. Merge across the slate (union of titles/skills; the
search location defaults to the FIRST candidate's metro — confirm with Mike).
Present ONE intake message: "Searching for **<titles>** in **<location>** (+ nationwide),
industry **<industry>** — confirm or correct." Wait for the reply.

## Build the candidates[] cards (used verbatim in Phase 5)
Each card: `{label, role, bullets[], years?, target_salary?}` — schema from
`docs/api/campaigns.md` (FunnelForge repo).
- `label`: "Candidate A" / "B" / "C" (recipients see this — NEVER the real name).
- `role`: their strongest current title.
- `bullets`: 4–6, real substance, redacted: years + industry ("12 yrs food-processing
  plant leadership"), skills/tools (name real software), certs, quantified wins.
  **Anonymize employers uniformly** ("national beverage-packaging manufacturer") — no
  real company names, no candidate name, no city, no phone/email.
- `years` from the résumé; `target_salary` only if Mike gave one. **Omit `location`.**
Show Mike the finished cards before Phase 2 (they ride every campaign; cheap to fix now).
```

- [ ] **Step 2: Cross-check the card schema** against `docs/api/campaigns.md` line ~31 in the FunnelForge repo (`{label, role, bullets[], years?, location?, target_salary?}`) — the reference must match exactly (minus the deliberately omitted `location`).

### Task 3: references/job-search.md

**Files:**
- Create: `C:\Users\mkvau\.claude\skills\candidateblast\references\job-search.md`

- [ ] **Step 1: Write the reference**

Content (complete):

```markdown
# Phase 2 — Job search → 10 options

**Goal:** find current openings the slate genuinely fits; present 10 (local + nationwide).

## Sources (MCP-first; no browser needed here)
- Indeed MCP `search_jobs` and ZipRecruiter MCP `search_jobs` — query = intake titles
  (+ close variants), location = intake metro for the local pass, then no/major-market
  location for the nationwide pass.
- Web search for Google Jobs coverage: `"<title>" job posting <metro>` and nationwide
  variants. Prefer postings on the employer's own site or a major board.

## Filters
- **Recency:** posted within **14 days** (stale postings waste sends).
- **Size — medium:** target **100–500 employees**. Verify best-effort via ZoomInfo MCP
  company enrichment (employee count); if unverifiable, use posting/site signals and mark
  size "est."
- **One posting per company** (keep the best-fit one).
- **Dedupe:** drop companies in pipelineblast's `companies_master.csv` as already worked;
  flag (don't hide) anything Mike says has an active sequence.
- **Fit floor:** the slate must plausibly place — title family matches AND
  industry/skills overlap. If under 10 survive, show fewer; NEVER pad with weak fits.

## Ranking & presentation
Score by title match > skills overlap > industry match > recency. Present exactly one
chat list, best first, numbered 1–10, each line: **Company — Role** (Location,
`LOCAL`/`NATIONWIDE` badge) · posted date · ~size · source link · one-line "why this fits
the slate". State the local/nationwide split ("4 local, 6 nationwide"). If local = 0,
say so explicitly and ask Mike before proceeding with a nationwide-only list.
Then STOP: "Which should I pitch? (numbers)". Wait.
```

- [ ] **Step 2: Verify tool names** — confirm the MCP tools referenced exist in the session (`mcp__claude_ai_Indeed__search_jobs`, `mcp__claude_ai_ZipRecruiter__search_jobs`, ZoomInfo enrichment tools) via ToolSearch; correct the reference if any names differ.

### Task 4: references/zoominfo-contacts.md

**Files:**
- Create: `C:\Users\mkvau\.claude\skills\candidateblast\references\zoominfo-contacts.md`

- [ ] **Step 1: Copy the proven method, change only what differs**

Start from `C:\Users\mkvau\.claude\skills\pipelineblast\references\zoominfo-contacts.md` (headless Talent preview-API method, phone capture, CSV columns, browser gotchas, UI fallback, human-export fallback — keep ALL of it verbatim). Make exactly these changes:

1. **Geo rule replaced:** contacts are located at/near **the company's own location from
   the posting** (state-level), because CandidateBlast targets wherever the job is — there
   is no "run geography". Keep it a hard rule (no random-state contacts), sourced per
   company instead of per run.
2. **Title gate replaced:** decision-makers at **Manager level and above** who own the
   hiring for the posted role (department head, ops/production/GM, owner/president,
   HR/TA leadership). Keep the 20-contact cap and business-email requirement.
3. **Add the 5+ advisory:** if a company yields **fewer than 5** Managers+, report
   "only N decision-makers found at <company>" and let Mike keep or swap the target.
   Do not auto-drop (contrast with pipelineblast's auto-skip at 0 — keep that: 0 usable
   contacts still means skip).
4. Header/goal line: per **chosen** company (Mike's picks from Phase 3), not per sourced
   company.

- [ ] **Step 2: Diff-check** — re-read both files side by side; everything except those four changes must match pipelineblast's version (it encodes hard-won browser gotchas — don't paraphrase them).

### Task 5: references/dripdrop-campaign.md

**Files:**
- Create: `C:\Users\mkvau\.claude\skills\candidateblast\references\dripdrop-campaign.md`

- [ ] **Step 1: Copy the proven method, change only what differs**

Start from `C:\Users\mkvau\.claude\skills\pipelineblast\references\dripdrop-campaign.md` (endpoint/auth, browser-tab sync-XHR call pattern, start_date/business-day behavior, contacts[] mapping w/ Phone→phone_office + LinkedIn, error/retry table, what's-automatic list, UI-wizard fallback — keep ALL of it). Make exactly these changes:

1. **`candidates[]` rule INVERTED (the defining difference):** ALWAYS send `candidates[]`
   = the Phase 1 cards. Never omit it — omission triggers the server's bench match, which
   is pipelineblast's behavior, not ours. The server generates + attaches the redacted
   résumé PDFs for the pinned cards (emails 2 & 4, interview guide email 3) — do not
   attach anything manually.
2. **Skip response reframed:** `{"skipped": true}` should NOT occur when `candidates[]`
   is supplied (the fit-floor skip is a bench-match outcome). If it ever comes back,
   STOP and show Mike — it means the server ignored the pinned slate (a bug to report),
   not a normal skip.
3. **`roles`** = the posted role from the chosen posting (personalizes to the opening).
   `company`/`industry`/`location` from the posting. `name` e.g.
   `"CandidateBlast — <Company> — <Role>"`.
4. **`enroll_newsletter`:** optional for CandidateBlast. If a newsletter matches the
   company's industry/region, enroll (verify `newsletter_enrollment.matched`); if none
   fits, launch without and note it in the summary — do not block the run.
5. Title/framing: "per chosen company", campaign = the MPC-style candidate pitch.

- [ ] **Step 2: Diff-check** against the pipelineblast original — only the five changes above may differ.

### Task 6: Dry-run verification (no sends)

- [ ] **Step 1: Fresh-session dry run**

In a new Claude session, invoke `candidateblast` with a real candidate (e.g. the Project Engineer test picks from the 5x3 samples) and the instruction "DRY RUN — stop before any campaign POST and before any ZoomInfo reveal; show me the artifacts instead."

- [ ] **Step 2: Check the artifacts**

Expected: correct intake message; anonymized cards (no names/employers/locations — read every bullet); a 10-option list with local/nationwide badges, recency ≤14 days, sizes, real source links, no padding below the fit floor; a paused "which should I pitch?" prompt; and (after picking) a printed would-be POST payload with `template: "fivebythree"`, pinned `candidates[]`, next-business-day `start_date`. Fix the skill files for any miss and re-run.

- [ ] **Step 3: Commit the plan checkboxes / any spec addenda in the FunnelForge repo**

```bash
git add docs/superpowers/plans/2026-07-21-candidateblast-skill.md
git commit -m "docs: CandidateBlast skill dry-run verified"
```

### Task 7: Live smoke test (Mike-gated)

- [ ] **Step 1: Get explicit go-ahead** — one company, chosen by Mike, ideally with a contact list Mike controls or trusts. Real emails will send.

- [ ] **Step 2: Run Phase 4 + 5 for that one company** — confirm: 200 with `campaign_id`, `steps: 5`, schedule all weekdays, dashboard shows the campaign with 3 résumé PDFs attached to emails 2 & 4 bearing "Candidate A/B/C" labels (not real names), contacts queued matches the CSV.

- [ ] **Step 3: Record results + update dedupe master** — company into `companies_master.csv`; note any deviation in the skill references; report the summary shape from SKILL.md.

---

## Self-review notes

- Spec coverage: skill deliverable (spec §"What gets built" item 6) fully covered; items 1–5 (in-app + bridge) explicitly deferred to Plans B/C with the bridge's browser-session risk carried forward.
- The 10-option, user-picks, 14-day, 100–500, Managers+, 5+-advisory, no-auto-send, redaction rules all trace to the approved spec.
- No placeholders: every reference file's content or exact copy-with-delta instructions are in the tasks.

# CandidateBlast — fully autonomous mode — Design Spec

**Date:** 2026-07-21
**Status:** Approved (design), pre-implementation
**Goal:** modify the existing `candidateblast` Claude Code skill (`.claude/skills/candidateblast/`)
so a run goes from "1–3 named candidates" to "campaigns launched" with no human checkpoint along the
way — replacing today's two stop-and-wait points with fixed, pre-agreed auto-selection rules.

## Why

CandidateBlast already does the whole motion end-to-end (candidate intake → job search → ZoomInfo
contacts → campaign launch) inside a single Claude session — no in-app "bridge" architecture needed,
since ZoomInfo runs live via Claude-in-Chrome in the same run. The only thing standing between "ask
for it" and "fully hands-off" is two deliberate stop points: confirming the search intake, and
picking which of the 10 sourced companies to actually pursue. This spec replaces both with fixed
rules agreed on 2026-07-21, so the skill can be invoked once and run straight through.

## Decisions (settled with Mike, 2026-07-21)

1. **Replace the default behavior** — no dual-mode, no flag. `.claude/skills/candidateblast/` is
   edited in place; every future "run CandidateBlast for X" runs fully autonomously.
2. **Auto-select the top 3** of the 10 ranked job options (existing ranking: title match > skills
   overlap > industry match > recency), still gated by the existing fit floor — a run can yield
   fewer than 3 launches if fewer than 3 options genuinely fit; never padded.
3. **Auto-skip below 3 Managers+ ZoomInfo contacts** at a chosen company (tightened from the current
   advisory-at-5 rule). No backfill from the ranked list — a skipped pick is not replaced, so a run
   can end with fewer than 3 launched campaigns.
4. **Trigger stays on-demand only** — invoked the same way as today; no scheduled/standing routine.

## What changes, file by file

All five files live under `.claude/skills/candidateblast/`.

### `SKILL.md`
- Rewrite the "Phases" list: Phase 3 changes from "Mike picks the targets — present the 10 in chat
  ... STOP and wait for his picks. Never auto-launch." to "Agent auto-selects the top 3 by fit score
  (existing ranking + fit floor) — no human pick."
- Hard rules section: remove "Mike picks; you never choose the send targets." Replace with the
  auto-select rule (top 3, fit-floor gated, no backfill on skip). Everything else in this section
  (max 3 candidates/exactly who Mike gave you, local-first-nationwide-labeled, `<3 Managers+` =
  auto-skip [updated from the advisory-at-5 wording], redaction ethics, live-sends-are-real caution)
  stays, with the contact-count number updated.
- "What done looks like" section: keep, but strengthen the framing — since nothing is gated mid-run,
  this summary is the *only* place Mike sees what happened. Explicitly call out: which of the 10 were
  auto-picked and why (fit rationale), any auto-skips and their reason (thin contacts, zero-local
  fallback, anomalous server response), and confirmation the dedupe master was updated.

### `references/candidate-intake.md`
- Remove "Then STOP and wait for Mike's reply before any searching." The single intake message
  (search parameters + finished cards) is still built and still shown to Mike as a status message,
  but the run proceeds immediately into Phase 2 rather than waiting for a reply.
- The search location still defaults to the first candidate's home metro — this default is now
  applied automatically instead of being offered for correction.
- **Unchanged (explicitly kept):** if a named pool candidate isn't found, or two names are
  ambiguous, the skill still stops and asks Mike. This is a data-integrity guardrail (never invent
  or approximate a candidate profile), not a judgment call about targets — it is out of scope for
  "remove the human checkpoint" and must not be touched.

### `references/job-search.md`
- Replace the "Then STOP: 'Which should I pitch? (numbers)'. Wait." step with: after ranking and
  presenting the 10 as a status message (for visibility, not for a reply), auto-select the **top 3**
  by the existing score order (title match > skills overlap > industry match > recency), subject to
  the existing fit floor (a run can select fewer than 3; never pad with weak fits).
- The "if local = 0, ask Mike before proceeding nationwide-only" rule becomes: proceed
  nationwide-only automatically, and state that explicitly in the run's status output / end-of-run
  summary instead of asking.
- The "Handoff" section (append picked companies to `companies_master.csv` at pick time, before
  pulling contacts or launching) is unchanged — "pick time" now means "auto-pick time."

### `references/zoominfo-contacts.md`
- Change the quality-gate rule: **"fewer than 5 Managers+ is an ADVISORY, not a drop... let Mike
  decide"** becomes **"fewer than 3 Managers+ is an auto-skip"** — skip launching at that company,
  mark the dedupe master with a skip status (e.g. `Selected - N contacts (skipped, thin)`), report it
  in the end-of-run summary, and move on. No backfill: a skip is not replaced by the next-ranked
  option.
- The existing "0 usable contacts = auto-skip" rule is now redundant with the new `<3` rule (0 < 3)
  and can be removed/folded into it — one threshold, not two.
- Everything else (Manager-level gate looser than pipelineblast's Director/VP, per-company state
  sourced from the posting, 20-contact cap, phone-priority logic) is unchanged.

### `references/dripdrop-campaign.md`
- Mechanically unchanged: `candidates[]` is always sent, never omitted; newsletter enrollment logic
  is already autonomous (launch without one and note it, never block or ask).
- The one existing "STOP and show Mike" case — a `{"skipped": true, ...}` response, meaning the
  server ignored the pinned slate — changes from "stop and show Mike" (impossible with no one
  present mid-run) to: skip that company, and flag it prominently as an **anomaly** (not a normal
  skip) in the end-of-run summary, since it indicates a server-side bug worth Mike's attention after
  the fact, not a routine outcome.

## What stays completely the same

Max 3 candidates (exactly who Mike gave you, no bench-filling, no synthesized candidates); dedupe
against `companies_master.csv` before pitching; redaction/anonymization rules (labels only, no real
names/employers/locations in cards); the 5x3 campaign mechanics (server writes emails, attaches
résumés for the pinned cards, business-day scheduling); send-throttle and bounce-suppression
inheritance at send time. Trigger phrasing is unchanged — invoked exactly as today.

## Testing / rollout

This is a documentation-only change (markdown skill files, no application code), so there is no
automated test suite to run. Verification is one **supervised trial run** before treating it as
routine: invoke it for a real candidate (e.g. Ed Cisneros, from the DripDrop screenshot that prompted
this change), watch it run start-to-finish without intervening, and review the end-of-run summary
plus the actual launched campaigns in DripDrop before relying on it unattended going forward.

## Risks

- **No human review of send targets** — the core tradeoff of this whole change. Mitigated by keeping
  the fit floor (never pad with weak fits), the tightened thin-contact auto-skip, and requiring a
  supervised first run before trusting it unattended.
- **Silent bad defaults** — removing the intake-confirmation stop means a misparsed search location
  or title could run through an entire cycle (real ZoomInfo pulls, real sends) before anyone notices.
  Mitigated by the end-of-run summary always stating the parameters actually used, so a bad run is
  caught right after, even if not before.
- **Server-side anomaly (pinned slate ignored)** — now surfaces only in the after-the-fact summary
  rather than blocking in real time; acceptable since it's a rare, already-flagged-as-a-bug case, not
  a routine decision point.

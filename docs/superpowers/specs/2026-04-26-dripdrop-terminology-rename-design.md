# DripDrop Terminology Rename — 2026-04-26

## Purpose

Replace internal jargon and stale terminology in the DripDrop UI with industry-standard sales-tool vocabulary so non-technical users (sales reps, founders, small-business owners coming from Apollo / Outreach / Hubspot) can understand the app immediately.

The app has accumulated naming through three rebrands (Funnel Forge → FlowDrip → DripDrop) and two competing metaphors ("Campaign" + "Sequence", "Drip" + everything else). This project picks one vocabulary, removes the other, and harmonizes labels app-wide.

## Scope

**In scope:**
- User-visible string changes in `flowdrip_app.py`: sidebar nav items, page titles, section headers, button labels, toast notifications, modal titles, dialog headers.
- Two structural changes: kill the legacy Email Sequencer hub; consolidate the AI/Email Setup + Signature pages into a single tabbed Settings page.
- Live smoke test of every renamed page before declaring done.

**Explicitly out of scope:**
- Visual redesign (colors, fonts, spacing, components — staying as-is).
- Internal code refactor (variable names, function names, file paths, JSON keys all stay).
- Data migrations (existing saved campaign / queue / config JSON files are untouched).
- Help text / onboarding flow rewrites (separate project if pursued later).
- Translating to other languages.
- Renaming the product itself ("DripDrop" stays everywhere it appears as a brand name).

## Verification Discipline

Before implementing any rename:
1. Open the file at the cited symbol/pattern and confirm the term still exists as described (the file changes daily; treat the line numbers in this spec as approximate).
2. If the term has already been renamed in current source, mark it `INVALID` in the implementation plan and skip — don't double-rename.
3. Whenever touching a string that contains both the brand name "DripDrop" and a target word, **never** rewrite the brand. The brand name is protected; only the surrounding label changes.

## The Decisions

### Sidebar renames (Sales Hub — `SALES_NAV` constant)

| Current label | New label | Notes |
|---|---|---|
| Dashboard | **Dashboard** | Unchanged |
| Campaign Radar | **Replies** | Match every other sales tool's term for the reply-tracking page |
| Start a Campaign | **Sequences** | Page becomes a list of all sequences with a "+ New Sequence" button instead of a build-flow entry |
| Contact Lists | **Contacts** | Drop redundant "Lists" — the page IS a list |
| Opt-Out List | **Opt-Out List** | Unchanged — already industry-standard |
| Active Clients | **Existing Customers** | Removes confusion with "Active Sequences" |
| PDF Generator | **Reports** | Clearer purpose; matches enterprise SaaS conventions |
| Candidate Pool | **Candidates** | Drop "Pool" jargon |
| My Profile | **My Profile** | Unchanged |
| Team Settings | **Team** | Drop "Settings" — redundant with the section header above |
| Email & AI Setup | **Settings** | Becomes a tabbed page (see structural change B below) |

The legacy Email Sequencer hub (`EMAILS_NAV`) is removed entirely (see structural change A below).

### Vocabulary cascade — applied across every page, button, dialog

| Old word/phrase | New word/phrase | Where it appears |
|---|---|---|
| Campaign *(noun)* | **Sequence** | Page titles, button labels, toasts ("Sequence saved!"), modal titles, section headers, save dialogs, microcopy |
| drip *(noun)* | **Sequence** / **outreach** / dropped | "Drip schedule" → "Send schedule"; "Today's Drip" → "Today" / "Dashboard"; "drip campaign" → "sequence" |
| Slow Drip / Evergreen | **Always-On Sequence** | The recurring/always-on campaign feature |
| Build My Own Campaign | **Build from scratch** | Picker option for blank-start sequences |
| Active Campaigns | **Active Sequences** | Sequence list page header, dashboards |
| Saved Campaigns | **Saved Sequences** | Sequence list page header |
| Campaign Wizard | **New Sequence** | Any leftover headers from the old build-flow naming |
| Drip Plan / Drip Schedule | **Send Schedule** | Wherever the per-step send timing is shown |
| Today's Drip *(stat tab on Dashboard)* | **Today** | Stat tab counter on the home dashboard |
| Tomorrow's Drop *(stat tab on Dashboard)* | **Tomorrow** | Stat tab counter on the home dashboard |
| *(wizard sidebar breadcrumb)* Emails / Sequence / Contacts / Launch | Emails / **Timing** / Contacts / Launch | "Sequence" as a sub-step inside a "+ New Sequence" wizard reads recursively; "Timing" matches what that step actually does (configures send cadence) |

### Cascade — illustrative (non-exhaustive)

The implementation plan will generate the exhaustive list (likely 80–150 individual edits). Examples that will be auto-renamed by following the rules above:

| Currently says | Will say |
|---|---|
| "Save Campaign" *(button)* | "Save Sequence" |
| "Campaign saved!" *(toast)* | "Sequence saved!" |
| "Campaign sent!" | "Sequence sent!" |
| "Pause Campaign" | "Pause Sequence" |
| "Delete Campaign" | "Delete Sequence" |
| "Loading campaigns…" | "Loading sequences…" |

### Brand-name protection (firm)

- The string "DripDrop" is **never** swapped — appears in topbar logo text, browser title bar, login screen, footer, system emails, etc.
- The string "drip" as a standalone substring (NOT part of "DripDrop") IS replaced.
- Implementer must use case-sensitive find-and-replace and explicitly skip any context where "DripDrop" appears as a single token.

## Structural Changes (more than just renaming)

### A. Kill the entire topbar hub-toggle (both pills)

The current topbar shows two pills: "Sales Hub" (active, teal) and "Manage Campaigns" (inactive). These are a hub toggle. Once the alt-hub is killed there's nothing to toggle to, so both pills are removed entirely. The DripDrop logo on the left is sufficient identity; users don't need a pill telling them they're in the app they just signed into.

**Concrete changes:**
- Remove BOTH topbar pills ("Sales Hub" and "Manage Campaigns") in the `topbar()` function. No replacement label — just the logo and the user avatar/menu.
- Delete the `EMAILS_NAV` constant in `flowdrip_app.py` (currently around L8071).
- Simplify `AppState`: drop `s.hub` and `s.ep`. Only `s.sp` (the page key) remains.
- Find every code path that references `s.hub == "emails"`, `s.hub == "sales"`, or routes to a `s.ep` page; either delete those paths or redirect to the corresponding `SALES_NAV` page (now the only page set).
- The Signature page (currently `e_signature` in the legacy hub) moves into the new Settings page as a tab (see B).
- The legacy `Emails`, `Sequence`, `Preview & Launch` pages are removed — these are duplicates of pages already inside the new "+ New Sequence" build flow.
- The legacy `Campaign Radar` (`e_responses`) is just a duplicate of the Replies page; remove the legacy page.

### B. Consolidate Settings into a tabbed page

The current "Email & AI Setup" page (`p_ai_settings`) and the legacy Signature page (`e_signature`) merge into one new tabbed page named **"Settings"**.

**Tabs (in order):**
1. **Email Provider** — current contents of "Email & AI Setup" excluding the AI portion
2. **AI** — current AI/Anthropic API configuration UI
3. **Signature** — absorbed from the killed legacy hub; same edit-and-save controls

Tab switching is in-page (no nav change). Each tab calls into the existing render logic from the source page, just wrapped in a tab container.

## Implementation Order

Phase ordering is by blast radius — smallest changes first so any regression is contained.

1. **Phase 1 — Sidebar renames.** Update the `SALES_NAV` list literal. Lowest risk, biggest visible impact. ~30 minutes. One commit.

2. **Phase 2 — Vocabulary cascade.** Find-and-replace across `ui.label(...)`, `ui.notify(...)`, button labels, modal titles, page subtitles. Carefully — case-sensitive, must skip the brand string and JSON keys. ~80–150 individual edits. **Multiple commits, one per page** so each commit is reviewable and revertable in isolation. Group by page: Sequences page, Replies page, Settings page, Existing Customers page, Reports page, Candidates page, Dashboard.

3. **Phase 3 — Kill the legacy hub.** Delete `EMAILS_NAV`, remove topbar toggle, simplify AppState, clean up references to `s.hub == "emails"` and `s.ep`. One focused commit.

4. **Phase 4 — Settings tabs.** Wrap the existing AI/Signature page contents in a tab component. One commit.

5. **Phase 5 — Live smoke test on dripdripdrop.ai.** Open every renamed page, eyeball it, click into each major flow, confirm nothing crashed. Per the lesson from the 2026-04-26 signup outage — never declare done from `pytest` alone.

## Risk Profile

- **Low** for Phases 1, 4 (additive, easily reversible).
- **Medium** for Phase 2 — risk is missing a string and ending up with mixed terminology, or accidentally renaming a wrong substring (e.g., "DripDrop" → "SequenceSequence", or a JSON key getting touched). Per-page commits + per-page smoke test mitigates.
- **Medium** for Phase 3 — risk is leaving a dangling reference to a removed page key (`emails_build`, `sequence`, `prev_launch`, `e_responses`, `e_signature`, `s.hub`, `s.ep`) that crashes on click. Pre-flight grep and removal mitigates.

## Mitigations

- **Phase 2 find-and-replace discipline:**
  - Generate the exhaustive find-list FIRST. Confirm visually.
  - Explicitly EXCLUDE: JSON keys (anything inside `json.loads`, `json.dumps`, `dict literals` that are saved to disk), the `"DripDrop"` brand string, internal Python variable names, function names, file paths.
  - Per-page commits so a wrong rename can be reverted without losing the rest.
- **Phase 3 hub removal:**
  - Grep for every `s.hub`, `s.ep`, `EMAILS_NAV`, `emails_build`, `sequence`, `prev_launch`, `e_responses`, `e_signature` reference BEFORE deletion.
  - Replace each with either the Sales Hub equivalent or a deletion.
  - Run the full pytest suite after the change.
- **Brand-name protection:**
  - Add an automated guard: a grep at the end of Phase 2 that asserts no `"DripDrop"` string was modified. If any was, fail.

## Data Layer — confirming no risk

This project does **not** touch:
- Saved campaign JSON files (`campaigns/*.json`). Same `"campaign"`, `"steps"`, `"contacts"` keys inside.
- The email queue file (`scheduled_queue.json`). Same `"campaign": "<name>"` key per item.
- Outlook integration, contacts CSV, signature.txt, Anthropic API config.
- User accounts, sessions, or auth.
- Page URLs (NiceGUI is server-state — bookmarks remain valid because there are no per-page URLs to bookmark).

In-flight scheduled sends, active sequences, and current sessions all continue uninterrupted across the deploy. The zero-downtime deploy script preserves WebSocket sessions per existing comments in `_deploy_zero_downtime.sh`.

## Definition of Done

- All renames in the table land on the `claude/terminology-rename` (or similar) branch.
- Phase 5 smoke test on dripdripdrop.ai is clean — every renamed page loads, every renamed button works.
- `python -m pytest tests/ -v` is green from a clean checkout.
- `grep -n '\bcampaign\b' flowdrip_app.py | grep ui\.` returns only intentional remainders (e.g., text that genuinely says "Campaign" in a help blurb that's intentionally calling out a generic term).
- `grep -n 'Drip Drop\|drip-drop\|DripDrop' flowdrip_app.py` shows the brand name is intact and unmolested.
- The legacy `EMAILS_NAV` constant is gone; `s.hub` and `s.ep` no longer exist on AppState.
- Settings page has 3 tabs: Email Provider, AI, Signature.
- Deploy: per CLAUDE.md / memory, ASK before deploying within 8am–5pm PDT; use `bash _deploy_zero_downtime.sh` only.
- Per the 2026-04-26 lesson: do a real `/` page-render check on dripdripdrop.ai after deploy, not just `/healthz`.

## Risks / Open Questions

- **Help articles / sales materials / demo videos:** any external content that references "Campaign" or "Slow Drip" becomes out of date the moment this ships. Not a code risk; a content-staleness risk. Worth a mental scan before deploy.
- **User muscle memory:** existing daily users see new labels the next time they log in. They'll be briefly confused for a day. Acceptable cost; the alternative is permanent jargon.
- **Possible additional terms surfaced during implementation:** the 80–150 string scan may surface terms not predicted by this spec (e.g., specific button labels with non-obvious phrasings). The implementer should flag these and decide per the rules above (industry-standard preferred, plain English when industry-standard is jargon, brand name protected).

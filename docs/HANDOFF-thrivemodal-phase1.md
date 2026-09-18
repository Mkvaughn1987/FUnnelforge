# HANDOFF — ThriveModal outbound sales on inboxslide (Phase 1)

Cold-start doc. Read this first; it replaces re-inspecting the codebase.
Written 2026-09-16 after a full read-only inspection. No files were changed.

---

## 0. Where things stand

**Phases 0-6 are all done and committed on `feat/thrivemodal-phase1`.** Both
open decisions below were answered yes: Phase 0 was merged first (`1f64461`),
and the four segmentation fields shipped as proposed.

| Phase | What | Commit | Tests |
|---|---|---|---|
| 0 | merge `main`, re-baseline | `1f64461` | — |
| 1 | firmographic data layer | `2f81b14` | 25 |
| 2 | saved audiences + dedupe gate | `c767f19` | 27 |
| 3 | outreach analytics page | `8df34eb` | 36 |
| 4 | vertical knowledge pack | `9c99f88` | 40 |
| 5 | multi-mailbox + warmup (closes R8) | `e21e36a` | 53 |
| 6 | ZoomInfo record ingest + MCP surface | this commit | 116 |

`flowdrip_app.py` is **62,452 lines**. Suite: **1036 passed / 17 failed /
1 skipped** — the failure LIST is byte-identical to
`_session_artifacts/2026-09-16/FINAL_FAILURES.txt`. Baseline against that
list, never the count.

Nothing is deployed. Deployment remains a separate step and needs Mike.

Sections 3 and 6 below still describe the pre-build state in places; the line
numbers throughout are stale, so always re-grep.

---

## 1. Ground truth about this repo

- Real repo: `C:\Users\mkvau\OneDrive\Documents\Sales\Python\FunnelForge`, branch `feat/whitelabel-instance`.
  - **Decoy — do NOT use:** `C:\Users\mkvau\Arena Staffing\...\CodeTransfer\FunnelForge` (unrelated Next.js "FlowDrop").
  - Worktrees under `C:\Users\mkvau\ff-wt\*` share this repo's `.git`.
- `flowdrip_app.py` is **60,430 lines / 3.3 MB** and is the entire web app. **Never read it in full.** Use `grep -n` + `sed -n`.
- **`CLAUDE.md` is STALE** — it documents the retired tkinter desktop app. Its navigation map is useless here.
- Stack: NiceGUI on FastAPI/uvicorn. **No SQL database** — per-user JSON/CSV filestore under `DRIPDROP_DATA_DIR`.
- AI = Anthropic. Sender on inboxslide = **Gmail OAuth** (live).
- Duplicate `def`s silently shadow in this file. Name new helpers distinctly.
- Test baseline: baseline against the known-failure **LIST**, not the count (it drifts 5 to 8 to 15).

## 2. The playbook model (the core concept)

Three tiers, resolved in this order:

1. `_LOCKED_PLAYBOOK` — env `DRIPDROP_PLAYBOOK`. Pins the whole box to one playbook.
2. Campaign **TYPE** — `_TM_TYPE_KEYS` vs `_RECRUITING_TYPE_KEYS` / `_SALES_TYPE_KEYS`.
3. Workspace setting — config key `workspace_playbook`.

Separate instance flag: `DRIPDROP_ATS_ENABLED` gives `_SALES_MODE = not _ATS_ENABLED` (hides Pipeline/ATS).

**app.inboxslide.ai is already pinned**: `DRIPDROP_ATS_ENABLED=0` + `DRIPDROP_PLAYBOOK=thrivemodal`
(see `deploy/env.inboxslide.example`). Arena and inboxslide run the SAME repo and the SAME
`flowdrip_app.py`, separated only by env vars — never by deleting code.

### Does changing a playbook affect saved campaigns? NO.

1. Campaign copy is stored text in the campaign's own JSON. Nothing regenerates it.
2. `save_campaign` stamps `_playbook` only when `_path` is absent (brand-new campaigns only) — `flowdrip_app.py:6158`.
3. `_active_playbook_text` resolves campaign TYPE before the workspace setting.

**Caveat specific to inboxslide:** because the box is pinned, `_LOCKED_PLAYBOOK` short-circuits
`_active_playbook_text` and `_campaign_playbook`, so any *new generation* there comes out in the
ThriveModal voice regardless of stamp or type. Deliberate and tested
(`test_locked_instance_forces_old_campaigns_onto_the_locked_playbook`). It never rewrites saved bytes.

---

## 3. Line map — flowdrip_app.py

| Area | Lines |
|---|---|
| ATS gate / workspace playbook / instance lock | 411 / 441 / 460 |
| `_TM_DEF_*` constants + `THRIVEMODAL_PLAYBOOK_FIELDS` | 460-975 |
| Paths and config / per-user isolation / path accessors | 1810 / 1841 / 2219 |
| Role helpers (user / tenant_admin / super_admin) | 2583 |
| Team-shared Active Clients blocklist | 2723-3024 |
| Auth / password reset / invite codes | 3265 / 3329 / 3558 |
| SendGrid+SMTP / MS Graph / Gmail OAuth | 3780 / 3788 / 3796 |
| Step types (`ST.*`) | 4090 |
| `_ARENA_SLATE_TYPES` | 5045 |
| Six ThriveModal objective definitions | ~5390-5560 |
| Type key sets / `_type_visible` | 5575 / 5589 |
| `ms()` step builder | 5632 |
| `load_contacts` | 5856 |
| `save_campaign` (playbook stamping at 6158) | 6136 |
| `_parse_contacts_csv` | 6313 |
| Prompt assembly — sole `_active_playbook_text` call site | 6621 |
| The 4 API routes | 6736 / 6826 / 6853 / 6915 |
| `add_responded` | 7482 |
| DNC load/save/add/remove | 7679-7721 |
| NDR + bounce classification | 7732-7910 |
| `is_on_dnc` | 7912 |
| `CONTACT_FIELDS` / CSV normalization | 8132 / 8170 |
| `_is_ooo_reply` / opt-out keywords | 8353 / 8374 |
| `_add_business_days` | 8906 |
| Arena 5x5 hand-authored touches | 9594 |
| **ThriveModal post-generation overrides** (`_TM_STEP_SHAPE`, scrubbers) | 9685-9974 |
| US holidays | 10166 |
| `queue_campaign_emails` — suppression + responded + MX filtering | 10330-10420 |
| Playbook resolution fns (`_workspace_playbook` etc.) | 10790-10870 |
| Timezone helpers | 10875 |
| `_active_playbook_text` (definition) | 11808 |
| Prompt-injection defenses / XSS sanitization / upload safety | 11839 / 11977 / 12173 |
| Sidebar nav (**PERFORMANCE rows are `None` stubs**) | 13438-13462 |
| Weekday-only drip day tabs | 16820 |
| Chooser tiles | 21601-21656 |
| Step 3 Choose Contacts | 23495 |
| `enroll_contact_in_evergreen` | 26080 |
| `_SALES_MODE` UI branches | 26648-27080 |
| Queue archiving / queue tile counts | 29764 / 33087 |
| `tm_cost_compare` | 33562 / 34586 |
| AI Guided Sequence Builder | 37557 |
| PDF kind filtering | 42540-42586 |
| CPC target-list helpers (ZoomInfo/XLSX parsing) | 43272 |
| Daily-send-limit UI | 47718-47765 |
| Market-intel company_size / employee_count prompts | 53054-53140 |
| 4x4 generation | 53950 |
| Routing / login / OAuth callbacks / landing / main | 57290-58886 |
| Deliverability pacing / daily limit enforcement | 59196 / 59584 |
| Scheduler leader election | 59803 |
| Reply monitor | 59888-60315 |

---

## 4. Data model (files, not tables)

```
$DRIPDROP_DATA_DIR/
├── users.json                          Users
├── teams/<safe_domain>/client_blocklist.json   domain suppression (team)
└── users/<escaped_email>/
    ├── dripdrop_config.json            Workspace + Business + settings + OAuth tokens
    ├── Campaigns/<Name>.json           Campaign + steps + embedded contacts
    ├── Campaigns/responded.json        Replies
    ├── Contacts/contacts.csv           Contacts (10 fixed columns)
    ├── dnc_list.json                   Suppression ("@domain" = whole domain)
    ├── soft_bounce_tracker.json        3 distinct NDRs = suppress
    ├── scheduled_queue.json            Messages
    ├── scheduled_queue_archive.json
    ├── reply_scan_audit.json           last 500 scans
    ├── campaign_styles.json            saved Templates
    ├── candidate_pool.json, task_outcomes.json, market_intel*.json
    └── PDFs/, Newsletters/, signature.txt, wizard_draft.json
```

`CONTACT_FIELDS = ["Email","FirstName","LastName","Company","JobTitle","MobilePhone","WorkPhone","LinkedInPage","City","State"]`

- 1 user = 1 workspace = 1 business.
- **There is no Company entity.** Company is a string column on a contact.
- No industry / company-size / seniority / hiring-signal fields exist anywhere as stored data.

---

## 5. What already ships for ThriveModal (do not rebuild)

Committed and tested on `feat/whitelabel-instance`:

- Three-tier playbook separation; 11 editable approved-content fields (`tm_business`, `tm_services`,
  `tm_industries`, `tm_problems`, `tm_differentiators`, `tm_proof`, `tm_pricing`, `tm_voice`,
  `tm_ctas`, `tm_sales_motion`, `tm_forbidden`) on the Company Profile page.
- Six candidate-free sales objectives: `tm_conversation` (7 steps, 5 emails), `tm_hiring_signal` (4),
  `tm_meeting_followup` (4), `tm_reengage` (4), `tm_stay_in_touch` (5), `tm_grow_client` (4), plus `byos`.
- `_type_visible()` hides the wrong shapes per playbook **without removing registry entries**.
- All of Mike's compliance rules are already the shipped defaults: recruiting-first PH staffing,
  "the client interviews and chooses the person", explicit DO-NOT-SAY list (no "Guaranteed 50% savings",
  no "same employee for half price"), no EOR/employer/payroll/benefits/compliance claims unless confirmed.
  `_TM_DEF_PROOF` currently reads "There is currently no approved ThriveModal customer proof."
- Blank pricing/proof renders an explicit "do not invent" notice into the prompt.
- Post-generation scrubbers drop lines promising un-attached files or non-existent newsletters.
- `tm_cost_compare` — arithmetic only, **never reaches a model**; self-labels as incomplete.
- Business-day scheduling, US holiday skip, per-user timezone delivery.
- Domain suppression (2 mechanisms), unsubscribe + `List-Unsubscribe`, hard/soft bounce handling,
  reply detection (Graph + Gmail, 5-min poll, checkpointed), auto-stop after reply.
- `tests/test_thrivemodal_playbook.py` — 783 lines, ~70 tests.

## 6. What is genuinely missing

1. **Campaign analytics** — sidebar rows `sales_dash` and `analytics` are wired to `None` (13461-13462).
2. **Company records + firmographics** — no entity, no industry/size/seniority/signal fields.
3. **Cross-campaign duplicate-contact prevention** — dedupe is per-campaign only.
4. **Construction/AEC and general offshore-staffing template sets.**
5. ~~In-app ZoomInfo ingest beyond CSV/XLSX (exports parse fine today).~~ **CLOSED by Phase 6.** See below.
6. Multi-mailbox sending + per-mailbox limits/warmup (one mailbox per user today).
7. `_campaign_playbook()` is dead code — tested, never called.

---

## 7. Risks

- **R1 (blocker):** `main` is NOT an ancestor of `feat/whitelabel-instance`. 36 commits on `main` are
  missing here — AI Prompts page, in-app Sales Campaign page, records ingest, dark-theme dropdown fix,
  pipeline search filters, and all of main's MCP tooling. `git diff --stat main...HEAD` = 36 files,
  +10,559 / -651. Live MCP exposes 11 tools; this branch's `mcp_server/dripdrop_mcp.py` defines 4.
- **R2:** Arena + inboxslide share one repo and one app file. Every edit ships to Arena.
- **R3:** Duplicate helper names silently shadow.
- **R5:** Extending `CONTACT_FIELDS` changes the CSV header on every write path, including Arena's.
- **R6:** Arena's prod has a history of undocumented hotfixes. Verify prod file hashes (LF-normalised) before deploying.
- ~~**R8:** One Gmail mailbox, no warmup — deliverability caps bite before the 250/day config cap.~~
  **CLOSED by Phase 5 (`e21e36a`).** Mailboxes live in a per-user `tm_mailboxes.json`; each
  gets its own config file of the existing shape, so there is still exactly one sending path.
  A new mailbox ramps from 10/day to its full cap over its warmup window. The account-wide
  `daily_send_limit` stays a ceiling over the sum — warmup only ever lowers it.

---

## 8. Proposed phases

- **Phase 0** — merge `main` into `feat/whitelabel-instance`; verify prod hashes; re-baseline tests.
- **Phase 1** — company/contact data model + the four segmentation fields (below).
- **Phase 2** — targeting/segmentation UI, saved audiences, enforce cross-campaign dedupe.
- **Phase 3** — analytics page (sources already exist: queue + responded + dnc; no new storage).
- **Phase 4** — construction/AEC + general offshore templates via `ms()` / `AICB_CAMPAIGN_TYPES` / `_TM_STEP_SHAPE`.
- ~~**Phase 5** — multi-mailbox + warmup.~~ **Done, `e21e36a`.** 53 tests.
- ~~**Phase 6** — ZoomInfo ingest path + MCP coverage for new entities.~~ **Done.** 116 tests.

### Phase 6, as built

Two gaps, one phase.

**The ingest gap.** A ZoomInfo *CSV export* and a ZoomInfo *live record* are
different shapes, and only the export was ever handled. Phase 1's column
aliases cover the export's display headers; nothing covered the live record,
which is nested, camel-cased, and wraps firmographics in a `company` block.
So every contact arriving by the live path reached the Phase 2 filter, the
Phase 3 analytics and the Phase 4 vertical picker with blank targeting fields.
`_tm_zi_value` / `_tm_zi_company` / `_tm_zi_domain` / `_tm_zi_seniority` /
`_tm_zi_company_size` / `_tm_zi_signal` / `_tm_zi_contact` / `_tm_zi_ingest` /
`_tm_zi_merge` / `_tm_zi_list_path` / `_tm_zi_contacts_on_file` /
`_tm_zi_save_contacts` are the one translation point between the two.

Three decisions worth keeping:

- **`sales_campaign.py` is deliberately NOT retrofitted.** Its `_flatten`
  discards every firmographic, and fixing it there would have been the obvious
  move. But `_contact_csv_fieldnames` is DATA-driven: the moment any contact
  carries targeting data, the file widens from ten columns to twenty. Arena
  shares that sourcing module, so populating firmographics in it would widen
  **Arena's** `contacts.csv` on every sales run. That is risk R2 and it breaks
  "preserve all existing Arena workflows". ThriveModal got its own gated door
  instead. `test_76` pins `_flatten` as unchanged.
- **Seniority is canonicalised at ingest.** ZoomInfo is not consistent with
  itself ("C Level Exec" / "C-Level" / "CXO"), and the audience panel builds
  each dropdown's options FROM the values present in the loaded list — so the
  ingest's vocabulary *becomes* the filter's vocabulary. Without this, two
  pulls a month apart offer the user two options that each match half the list.
  An unrecognised level passes through rather than being dropped.
- **Headcount is stored raw, not pre-bucketed.** `_size_bucket` already runs at
  filter time and display time and reads `420` and `"201 - 500"` alike, so
  bucketing at ingest would lose precision for nothing. A value `_size_bucket`
  cannot read is stored blank, because it would otherwise appear in the size
  dropdown as an option matching nobody.

A pull is merged, not appended: an overlapping pull must ENRICH the contacts
already saved, not duplicate them — the duplicate would be the copy carrying
the firmographics, so the campaign would enrol the empty one. A blank incoming
value never erases a stored one.

**The MCP gap.** The chain is four layers — `@mcp.tool` → a `DripDropClient`
method → an HTTP route on `flowdrip_app.py` → the logic — and a tool shipped
without its route 404s at call time (`candidates_search`, 2026-08-27). Phases
1-5 added entities with no MCP surface at all. Five tools now exist end to end:
`tm_import_contacts`, `tm_audiences`, `tm_audience_preview`, `tm_analytics`,
`tm_mailboxes`, on `POST /api/v1/tm/contacts`, `GET /api/v1/tm/audiences`,
`POST /api/v1/tm/audience_preview`, `GET /api/v1/tm/analytics`,
`GET /api/v1/tm/mailboxes`. `test_63` pins tool↔method pairing structurally.

Route shape, which matters: `_tm_api_owner(request)` is a **single** auth door
rather than the ~15-line preamble copied five times, and `test_67c` pins that
`owner` is assigned exactly once, from that door — a caller must never be able
to name the account it writes to. Each route then binds the owner's paths
**before** calling `_is_thrivemodal()`, because the gate reads the workspace
config and that is not resolved until the paths are bound. An Arena key gets
**404, not 403**: telling a key that an endpoint exists but is not for them
leaks the other product's surface.

### Phase 1 scope (proposed, NOT approved)

In scope:

1. Append 4 optional columns to `CONTACT_FIELDS`: `Industry`, `CompanySize`, `Seniority`, `HiringSignal`. Append only, never reorder.
2. Extend CSV header aliases so ZoomInfo's native column names map automatically.
3. `_company_index(contacts)` — company-keyed **derived view**, computed at read time. No new storage file.
4. `_tm_audience_filter(contacts, *, industries, size_buckets, seniorities, signals)` — pure, unit-testable.
5. `_already_targeted(email)` — cross-campaign duplicate scan. Phase 1 shows a warning count only; enforcement is Phase 2.
6. Everything gated behind `_is_thrivemodal()` / `_LOCKED_PLAYBOOK`, so Arena is untouched.

Out of scope: filter UI, analytics, vertical templates, multi-mailbox, ZoomInfo API, MCP changes,
any change to generation prompts, playbook copy, queue, sender, reply or bounce paths.

Preserved: no restamping, no LinkedIn automation/scraping, no invented proof/pricing/statistics/claims.
Phase 1 touches data shape only — not one word of outbound copy.

### Files Phase 1 would modify

| File | Change |
|---|---|
| `flowdrip_app.py:8132` | append 4 columns to `CONTACT_FIELDS` |
| `flowdrip_app.py:8170-8250` | `normalize_contacts_csv` writes them; `_normalize_rows` gains aliases |
| `flowdrip_app.py:5856` | `load_contacts` tolerates missing columns |
| `flowdrip_app.py:10395` | `_norm_contact` carries the new keys through |
| `flowdrip_app.py:43278` | `_CPC_HDR_*` alias tuples |
| `flowdrip_app.py:6313` | `_parse_contacts_csv` passes new columns |
| new block near `flowdrip_app.py:43272` | `_company_index`, `_tm_audience_filter`, `_already_targeted` (distinct names — R3) |
| `flowdrip_app.py:23495` | Step 3 read-only preview counts, TM-gated |
| `tests/test_thrivemodal_targeting.py` | NEW |

No migration — there is no schema to migrate.

### Tests Phase 1 requires

New file `tests/test_thrivemodal_targeting.py`, 25 tests in five groups:

- **CSV back-compat (1-5):** 10-column CSV still loads with new fields empty; 14-column round-trips;
  first ten headers byte-identical to today; ZoomInfo headers map; unknown columns still ignored.
- **Company index (6-9):** same-company contacts collapse; case/whitespace-insensitive keying;
  contact with no company retained but unindexed; conflicting industry resolves deterministically.
- **Audience filter (10-16):** industry filter; size-bucket boundaries exact; seniority case-insensitive
  and substring-safe (VP vs SVP); signal filter; combined filters AND; empty filter returns everything;
  filtering a legacy 10-column list returns everything, not nothing.
- **Duplicate guard (17-20):** finds and names the other campaign; case-insensitive email;
  current-campaign-only contacts not flagged; removed/completed contacts do not count.
- **Arena isolation — critical (21-25):** no segmentation controls render under Arena;
  `load_contacts` output byte-identical for a 10-column CSV; 4x4/5x5/5x3 queue identical items
  (golden file); `_type_visible` unchanged for every registry key under both playbooks;
  no `_playbook` stamp written or altered anywhere in the diff.

Regression suites that must stay green: `test_thrivemodal_playbook.py`, `test_campaign_api.py`,
`test_candidate_import_api.py`, `test_arena_5x5.py`, `test_5x3.py`, `test_ndr_parsing.py`,
`test_the_roundup.py` — against the known-failure LIST.

---

## 9. Standing constraints from Mike

- Preserve all existing Arena workflows.
- Do not restamp or rewrite saved campaigns.
- No LinkedIn automation or scraping.
- Never invent customer proof, pricing, savings guarantees, placement statistics,
  compliance certifications, or service terms.
- ThriveModal = recruiting-first offshore staffing, dedicated Philippines-based professionals.
- The client interviews and selects the person.
- Do not call ThriveModal the legal employer, EOR, payroll, benefits, or compliance provider
  unless confirmed in application settings.
- "Often approximately 50% less than comparable U.S. headcount" is allowed; guaranteeing 50% is not.
- Use existing architecture and conventions. Do not create a separate application.

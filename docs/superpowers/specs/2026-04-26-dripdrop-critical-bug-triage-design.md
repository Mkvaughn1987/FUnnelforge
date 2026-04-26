# DripDrop Critical Bug Triage — 2026-04-26

## Purpose

Triage and fix the **13 Critical-severity findings** surfaced by a parallel multi-agent code audit on 2026-04-26 across `flowdrip_app.py` (39,950 lines) and `funnelforge_core.py` (841 lines).

The audit covered five categories: multi-user safety, email send/queue correctness, Outlook integration, data integrity, and UI/state. This spec covers only the issues rated Critical. The 16 High-severity and 18 Medium-severity findings are deferred to follow-up specs.

The 13 Critical findings consolidate into **10 fix tasks** (C1–C10), because two tasks bundle closely-related sub-findings:
- **C8 (community)** bundles two findings: `copy_community_to_local` overwrite + `save_to_community` non-atomic.
- **C10 (Outlook COM)** bundles three findings: scheduler thread CoUninitialize, ImportError CoInit/CoUninit mismatch, and per-email Mail leak.

## Scope

**In scope:**
- Diagnose, verify (against current source), and fix the 13 Critical findings listed below.
- Add minimal targeted tests where the failure mode is testable without Outlook (atomicity, cancel-pending normalization candidates, wizard-state reset).
- Where a bug is a latent risk (e.g., the global `QUEUE_PATH` is currently unreachable in server mode), harden the guard so it cannot silently regress.

**Explicitly out of scope:**
- The 16 High-severity findings (separate spec; user has agreed to revisit after this lands).
- The 18 Medium-severity findings (later).
- Refreshing `CLAUDE.md`'s navigation map (the file has grown from ~7.5K to ~40K lines; do this in a separate doc-only PR).
- Refactoring large functions for clarity unless the refactor is the fix.
- Adding new features or UX changes.

## Verification Discipline

Each finding below was reported by an audit agent reading the source. Before implementing any fix, the implementer MUST:

1. Open the file at the cited line(s) and confirm the bug exists as described.
2. If the line numbers are off (the file changes frequently), search by symbol/pattern rather than trusting the number.
3. If the bug does not reproduce or the agent misread the code, mark it `INVALID` in the implementation plan and skip — do not invent a fix for a non-bug.

This is non-negotiable. The audit was wide, not deep.

## The 10 Critical Fix Tasks

Each entry: **ID** · file:line · short title · what · why it matters · fix direction · test strategy.

---

### C1 — QEditor merge-field inserts silently dropped
- **Where:** `flowdrip_app.py:7702` (`ddInsert` JS helper inside `inject_styles`)
- **What:** The `ddInsert` JS function manipulates the QEditor contenteditable DOM and dispatches an `input` event, but NiceGUI's QEditor binding does not sync contenteditable changes back to the Python-side `value` property on `input` events alone.
- **Why it matters:** User clicks a merge-field button, sees `{FirstName}` appear in the editor, but on Save/Next the Python side reads the old (pre-insert) body. Email sends without the merge variable. CLAUDE.md explicitly warns about this pattern; the bug is still live.
- **Fix direction:** From the Python button handler, after `run_javascript("ddInsert(...)")`, explicitly read the editor's HTML back via JS and call `editor.set_value(...)` server-side. Or replace the JS-DOM insertion path with a pure Python callback that sets `editor.value = current + token`.
- **Test:** Manual UI test — insert variable, click Save without further typing, reload campaign, confirm token is in saved JSON. (Hard to unit-test the contenteditable directly; integration smoke test acceptable.)

### C2 — Custom-tab re-entry doesn't reset wizard state → cross-campaign data contamination
- **Where:** `flowdrip_app.py:13154–13155` (the Critical site) with related fix in the `_pick` callback at `13082–13097`
- **What:** When the user is in the custom-campaign builder, navigates back to the flow picker, then re-selects "custom" without going through `_back_to_picker`, the `_pick` callback does not clear `s.custom_steps`, `s.custom_editing`, or `s.custom_name`. Stale form fields and step data from the previous campaign remain visible.
- **Why it matters:** Real cross-campaign contamination. User finishes Campaign A, starts B, the builder shows A's steps. If the user doesn't notice, B is sent with A's content.
- **Fix direction:** In the `_pick` callback at L13082–13097, when entering the "custom" tab, explicitly reset `s.custom_steps=[]`, `s.custom_editing=False`, `s.custom_name=""`, and `s.custom_editing_idx` to its sentinel — matching the reset already in `_back_to_picker` (L13136). Best practice: extract a single `_reset_custom_state(s)` helper and call it from both sites.
- **Note:** A broader wizard-state reset (clearing `aicb_*` fields between flows) was flagged at High severity and is out of scope for this spec; it goes into the Highs spec.
- **Test:** State-level — set `s.custom_steps=[step1, step2]`, simulate `_pick("custom")`, assert empty. Manual: build campaign A, finish, re-enter custom flow, assert blank builder.

### C3 — Merge substitution runs before signature stripping → body truncation
- **Where:** `flowdrip_app.py:6062–6070` (merge substitution) vs. `_strip_signature_from_body` at `flowdrip_app.py:5384`, both called from the queue path
- **What:** Merge variables are substituted into the body before the signature-strip function runs. If the resolved value (e.g., the user's own name "Michael Vaughn") appears inside the body (e.g., "Hi {FirstName}, this is Michael Vaughn from..."), the strip's pattern matches the wrong location and truncates the user's intended message.
- **Why it matters:** Recipient receives a partial email — the actual pitch is cut off, only the trailing signature visible. Looks broken.
- **Fix direction:** Reverse the order. Call `_strip_signature_from_body()` against the *template* body (clean string match against the literal signature) first, then run merge substitution. Update the queue construction in `flowdrip_app.py:6062–6095` accordingly.
- **Test:** Unit test — body containing the user's signature first-name + a `{FirstName}` token resolving to the same name, run through the pipeline, assert no truncation.

### C4 — `unsubscribe_email=True` passed as boolean
- **Where:** `flowdrip_app.py:6125` (queue item construction)
- **What:** Sets `"unsubscribe_email": True` on every queued item. Downstream `funnelforge_core._wrap_html_for_email()` and `_list_unsub_mailto` expect a string email or `None`. Passing a bool produces malformed `List-Unsubscribe` headers (or silent type errors caught and swallowed).
- **Why it matters:** Gmail one-click unsubscribe and other clients may show malformed headers, hurt deliverability, and break compliance. Could also push messages to Spam more often.
- **Fix direction:** Pass either the actual unsubscribe address (preferred — derive from sender SMTP or a config setting) or `None`. Remove the `True` literal entirely. Verify `_list_unsub_mailto` handles `None` gracefully.
- **Test:** Unit test — call queue path, assert header is a valid `mailto:` URI or absent.

### C5 — Non-atomic config write
- **Where:** `flowdrip_app.py:6175` (`save_config`)
- **What:** Writes directly with `.write_text()` instead of temp-file + atomic rename. Mid-write crash corrupts the config.
- **Why it matters:** User loses email provider tokens, timezone, and campaign settings. App may fail to start or re-prompt setup.
- **Fix direction:** Standard pattern — write to `<path>.tmp` sibling, `os.replace()` to destination. Wrap in try/except and log on failure.
- **Test:** Unit test — write, raise mid-write (mock `write_text` to throw after partial write), assert original file is intact.

### C6 — Non-atomic outcomes save
- **Where:** `flowdrip_app.py:4126` (`save_outcomes`)
- **What:** Same pattern as C5 — direct `.write_text()`.
- **Why it matters:** Task outcomes (AI generation success/failure, PDF exports) silently lost. `load_outcomes()` returns `{}` on parse error, masking corruption.
- **Fix direction:** Same atomic-write pattern as C5.
- **Test:** Same as C5.

### C7 — Non-atomic contact CSV save
- **Where:** `flowdrip_app.py:15953` (`_save_contacts_to_csv`)
- **What:** `open(path, "w")` writes the entire contact CSV in place. Crash mid-write nukes the contact database.
- **Why it matters:** Catastrophic — total loss of contact data with no recovery. Highest-impact data-loss path in the app.
- **Fix direction:** Write to `<path>.tmp`, then `os.replace()`. Consider also writing a `.bak` of the previous file before replace, kept for one generation.
- **Test:** Unit test — write, raise mid-write, assert original intact.

### C8 — Community campaign save: non-atomic AND silent overwrite (bundled)
Two related Critical findings, fixed together:

- **C8a** `flowdrip_app.py:4424` — `copy_community_to_local()` uses direct `p.write_text()` and silently overwrites if a local campaign with the same name already exists.
- **C8b** `flowdrip_app.py:4434` — `save_to_community()` uses direct `p.write_text()`, no collision check (two users uploading templates with the same name silently overwrite).

- **Why it matters:** Both can cause silent loss of user (or community) data. Plus the non-atomic write can corrupt during the save.
- **Fix direction:** Use the same atomic-write pattern as C5/C6/C7. Add collision policy: for local-copy, prompt to rename or auto-suffix (e.g., `Name (2).json`); for community-save, append timestamp on collision (`name_20260426_120000.json`).
- **Decision needed from user:** for community save, append timestamp on every save (versioning) or only on collision? **Default: only on collision.**
- **Test:** Unit — collision case asserts no overwrite; atomicity test mirrors C5.

### C9 — Latent global `QUEUE_PATH` in `funnelforge_core`
- **Where:** `funnelforge_core.py:71–73` and the legacy fallbacks at `flowdrip_app.py:19341–19342`, `19379–19380`
- **What:** `funnelforge_core` defines a single module-level `QUEUE_PATH`. Server mode currently disables this code path (line ~2132 of `flowdrip_app.py`), so it's not reachable today. But the fallback in `_load_queue` and `archive_old_queue_entries` still references it under `not _SERVER_MODE`.
- **Why it matters:** If the server-mode guard ever breaks or is removed (refactor, condition flipped), every user's queue collapses into one file → cross-user mail mixing, the worst possible failure for a multi-user product. Same root cause as the 2026-04-20 signature leak incident.
- **Fix direction:** Remove the global `QUEUE_PATH` entirely. Make every queue accessor require an explicit user-resolved path argument. Tests should fail loudly if anything tries to use a module-level fallback.
- **Test:** Static check — grep that `QUEUE_PATH` is no longer module-scoped. Runtime — assert that load/save without an explicit path raises.

### C10 — Outlook COM lifecycle bugs (3 sub-issues, bundled)
This is a single fix area with three related leaks; bundled because the fix touches the same COM-init helper code.

- **C10a** `funnelforge_core.py:546` — Scheduler thread calls `pythoncom.CoInitialize()` on each (re)connect but never `CoUninitialize()`. Reference counts and Outlook handles leak.
- **C10b** `flowdrip_app.py:4778–4867` — On `ImportError` of `pythoncom`, the early-return path skips `CoInitialize`, but the `finally` block still attempts `CoUninitialize`. Unbalanced.
- **C10c** `funnelforge_core.py:503–508` — `mail = outlook.CreateItem(0)` is never explicitly released or `del`'d. Per-email COM leak.

- **Why it matters:** Slow degradation. Outlook process memory grows under volume; eventually the COM stack stalls, sends start failing, the user has to restart Outlook (sometimes the whole machine).
- **Fix direction:** Track init state with a flag; only call `CoUninitialize` if `CoInitialize` succeeded. Wrap `_send_one_email` in try/finally with `del mail` (or `pythoncom.CoFreeUnusedLibraries()` periodically). Standard pywin32 hygiene.
- **Test:** Hard to unit-test directly. Manual: queue 100 sends, watch Outlook memory; should stay flat. Add a basic init/uninit balance test by mocking `pythoncom`.

---

## Cross-cutting Decisions Needed Before Implementation

1. **C8 (community save):** timestamp every save (versioning) or only on collision? **Default: only on collision.**
2. **C10 testing:** rely on manual Outlook-memory verification, or mock `win32com` in tests? **Default: manual is fine; mocking is high-effort, low-value.**

## Implementation Order

Suggested sequencing for the writing-plans phase:

1. **Atomicity batch (C5, C6, C7, C8)** — same pattern (atomic temp-file write), low risk, big win, easy to test. Land first.
2. **Send-correctness batch (C3, C4)** — touches the queue path. C3 changes pipeline order; C4 is a literal swap.
3. **C2 (custom-tab reset)** — small, isolated state fix.
4. **C1 (QEditor sync)** — needs UI verification, more careful. Standalone.
5. **C9 (QUEUE_PATH removal)** — isolated refactor; verify nothing else depends on the module global.
6. **C10 (COM lifecycle)** — isolated; can land any time.

## Definition of Done

- All 13 findings (across the 10 fix tasks) merged on a feature branch.
- Each fix verified against current source before implementation (per Verification Discipline above).
- New tests added where the failure mode is unit-testable.
- App runs locally without regressions on the standard wizard flow (build → contacts → review → launch).
- Deployment: per CLAUDE.md / memory, use `bash _deploy_zero_downtime.sh` only; ask the user before deploying within 8am–5pm PDT.
- No fix introduces backwards-compat shims or dead-code paths.

## Risks

- **Line numbers will drift.** Audit was on a snapshot; the file gets edited daily. The implementer must search by symbol/pattern, not trust the line number.
- **Some Criticals are interconnected.** C3 changes the queue pipeline; verify C4 still applies cleanly afterward. Group related commits.
- **C10 and C1 are hard to test in CI.** Plan for manual verification time.
- **CLAUDE.md is stale** (claims 7,537 lines; real is 39,950). The implementer should not over-trust the navigation map; treat it as approximate.

## Appendix — Audit Provenance

- Method: 5 parallel audit agents dispatched 2026-04-26, one per category (multi-user safety, send/queue, Outlook, data integrity, UI/state). Severity threshold: Critical/High/Medium.
- Total findings before dedup: ~54. After dedup: 47 (13 Critical, 16 High, 18 Medium).
- This spec covers all 13 Critical findings, organized into 10 fix tasks.
- The 16 High findings are deferred to a follow-up spec, decided once these Criticals are merged and stable.

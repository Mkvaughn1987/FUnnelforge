DripDrop Critical Bug Triage — 2026-04-26

## Purpose

Triage and fix the 13 Critical-severity bugs surfaced by a parallel multi-agent code audit on 2026-04-26 across `flowdrip_app.py` (39,950 lines) and `funnelforge_core.py` (841 lines).

The audit covered five categories: multi-user safety, email send/queue correctness, Outlook integration, data integrity, and UI/state. This spec covers only the 13 issues rated Critical. The 29 High-severity findings are deferred to a follow-up spec after this one ships.

## Scope

**In scope:**
- Diagnose, verify (against current source), and fix the 13 Critical bugs listed below.
- Add minimal targeted tests where the failure mode is testable without Outlook (atomicity, merge-token leftovers, cancel-pending normalization, wizard-state reset).
- Where a bug is a latent risk (e.g., the global `QUEUE_PATH` is currently unreachable in server mode), harden the guard so it cannot silently regress.

**Explicitly out of scope:**
- The 29 High-severity findings (separate spec).
- The 18 Medium-severity findings (later).
- Refreshing `CLAUDE.md`'s navigation map and line references (the file has grown from ~7.5K to ~40K lines; do this in a separate doc-only PR).
- Refactoring large functions for clarity unless the refactor is the fix.
- Adding new features or UX changes.

## Verification Discipline

Each finding below was reported by an audit agent reading the source. Before implementing any fix, the implementer MUST:

1. Open the file at the cited line(s) and confirm the bug exists as described.
2. If the line numbers are off (the file changes frequently), search for the symbol/pattern instead.
3. If the bug does not reproduce or the agent misread the code, mark it `INVALID` in the implementation plan and skip — do not invent a fix for a non-bug.

This is non-negotiable. The audit was wide, not deep.

## The 13 Critical Bugs

Each entry: **ID** · file:line · short title · what · why it matters · fix direction · test strategy.

---

### C1 — QEditor merge-field inserts silently dropped
- **Where:** `flowdrip_app.py:7702` (`ddInsert` JS helper, `inject_styles`)
- **What:** The `ddInsert` JS function manipulates the QEditor contenteditable DOM and dispatches an `input` event, but NiceGUI's QEditor binding does not sync contenteditable changes back to the Python-side `value` property on `input` events alone.
- **Why it matters:** User clicks a merge-field button, sees `{FirstName}` appear in the editor, but on Save/Next the Python side reads the old (pre-insert) body. Email sends without the merge variable. CLAUDE.md explicitly warns about this pattern; the bug is still live.
- **Fix direction:** From the Python button handler, after `run_javascript("ddInsert(...)")`, explicitly read the editor's HTML back via JS and call `editor.set_value(...)` server-side. Or replace the JS-DOM insertion path with a pure Python callback that sets `editor.value = current + token`.
- **Test:** Manual UI test — insert variable, click Save without further typing, reload campaign, confirm token is in saved JSON. (Hard to unit-test the contenteditable directly; integration smoke test acceptable.)

### C2 — Wizard state cross-pollutes across campaigns (flow picker)
- **Where:** `flowdrip_app.py:13082–13097` and `13134–13148` (flow `_pick` callback and `_back_to_picker`)
- **What:** When a user picks a new flow type ("recruiting", "ai_campaign", or returns to "custom"), only a subset of wizard state is reset. Fields like `aicb_company`, `aicb_website`, `aicb_industry`, `aicb_niche`, `aicb_sel_locations`, `aicb_sel_roles`, `aicb_docs`, `aicb_research`, `aicb_campaign`, and `custom_editing_idx` persist from the previous campaign.
- **Why it matters:** User finishes Campaign A (Acme Corp, Texas, sales reps), starts Campaign B for a different client. Wizard pre-populates with Acme's research, locations, generated docs. If the user doesn't notice, Campaign B is sent with wrong company data baked in. Real cross-campaign data contamination.
- **Fix direction:** Define a single helper `_reset_wizard_state(s)` that clears every `aicb_*` and `custom_*` field to its default. Call it from both `_pick` (any new flow) and `_back_to_picker`. Audit the `AppState` definition (~L1381) to enumerate the full set.
- **Test:** State-level test — set fields manually, call `_reset_wizard_state`, assert all default. Manual: build campaign A, finish, start B, assert all fields blank.

### C3 — `custom_editing_idx` not reset → out-of-bounds access on re-entry
- **Where:** `flowdrip_app.py:13134–13148` (`_back_to_picker`)
- **What:** `_back_to_picker` resets `s.custom_steps=[]` but not `s.custom_editing_idx`. If user was editing step 2 (`custom_editing_idx=2`), goes back, picks custom again, the builder tries to render step 2 of an empty list.
- **Why it matters:** Page crash or blank/erroneous edit form on re-entry. Can lose draft work.
- **Fix direction:** Add `s.custom_editing_idx = -1` (or whatever the initial sentinel is) to `_back_to_picker`. Consolidate with C2's `_reset_wizard_state` helper.
- **Test:** State-level — set `custom_editing_idx=2`, call `_back_to_picker`, assert `-1`.

### C4 — Merge substitution runs before signature stripping → body truncation
- **Where:** `flowdrip_app.py:6062–6070` (merge substitution) vs. signature strip at `_strip_signature_from_body` (`L5384`) called later in queue path
- **What:** Merge variables are substituted into the body before `_strip_signature_from_body()` runs. If the resolved name (e.g., "Michael Vaughn") appears inside the user's body (e.g., "Hi {FirstName}, this is Michael Vaughn from..."), the strip pattern matches the wrong location and truncates the user's intended message.
- **Why it matters:** Recipient receives a partial email — body cut off, only the trailing signature visible. Looks broken; loses the actual pitch.
- **Fix direction:** Reverse the order. Strip signature from the *template* body first (clean string match against the literal signature), then run merge substitution. Update `queue_campaign_emails` (L974) accordingly.
- **Test:** Unit test — body containing the user's own name + a merge token, run through the pipeline, assert no truncation.

### C5 — `unsubscribe_email=True` passed as boolean
- **Where:** `flowdrip_app.py:6125` (queue item construction)
- **What:** Sets `"unsubscribe_email": True` on every queued item. Downstream `funnelforge_core._wrap_html_for_email()` and `_list_unsub_mailto` expect a string email or `None`. Passing a bool produces malformed `List-Unsubscribe` headers (or silent type errors caught and swallowed).
- **Why it matters:** Gmail one-click unsubscribe and other clients may show malformed headers, hurt deliverability, and break compliance. The user's emails may also land in Spam more often.
- **Fix direction:** Either pass the actual unsubscribe address (preferred — derive from sender SMTP or a config setting) or `None`. Remove the `True` literal entirely. Verify `_list_unsub_mailto` handles `None` gracefully.
- **Test:** Unit test — call queue path, assert header is a valid `mailto:` URI or absent.

### C6 — Cancel-pending campaign name not normalized
- **Where:** `flowdrip_app.py:4677–4678` and `4691–4692` (`_cancel_pending_for_email`)
- **What:** Email is normalized via `.lower().strip()` for the comparison key, but `q.get("campaign", "") == campaign_name` is compared raw. A campaign queued as "My Campaign" will not match a cancel request for "my campaign".
- **Why it matters:** When a contact replies (or opts out) and the system tries to cancel pending sends, casing/whitespace mismatch leaves emails in the queue. The contact gets the next drip after they explicitly opted out — credibility and CAN-SPAM risk.
- **Fix direction:** Normalize both sides: `q.get("campaign", "").strip().casefold() == (campaign_name or "").strip().casefold()`.
- **Test:** Unit test — queue items with mixed-case campaign names, call cancel with a different case, assert all matching items removed.

### C7 — `merge_tokens()` lets unresolved `{Token}` reach the recipient
- **Where:** `funnelforge_core.py:335–339` (`merge_tokens`)
- **What:** `merge_tokens()` does naïve `str.replace` per known field. Templates with typos (`{FirstNae}`), removed legacy fields (`{LegacyField}`), or unsupported fields go out *as literal text*.
- **Why it matters:** Recipient sees "Hi {FirstNae}, here's your offer" — looks unprofessional, immediately marks the sender as careless or as a poorly-configured spammer.
- **Fix direction:** After all known tokens are substituted, scan for any remaining `{[A-Za-z][A-Za-z0-9_ ]*}` pattern. Either (a) hard-fail at queue time if found (preferred for sender hygiene), or (b) replace with empty string and log a warning. Decide with user before implementing.
- **Decision needed from user:** hard-fail at queue time, or silent strip + warn? (Default recommendation: hard-fail.)
- **Test:** Unit test — body with unknown `{Foo}`, assert configured behavior.

### C8 — Non-atomic config write
- **Where:** `flowdrip_app.py:6175` (`save_config`)
- **What:** Writes directly with `.write_text()` instead of temp-file + atomic rename. Mid-write crash corrupts the config.
- **Why it matters:** User loses email provider tokens, timezone, campaign settings. App may fail to start or re-prompt setup.
- **Fix direction:** Standard pattern — write to `.tmp` sibling, `os.replace()` to destination. Wrap in try/except and log on failure.
- **Test:** Unit test — write, kill mid-write (simulate by raising in the middle), assert original file is intact.

### C9 — Non-atomic outcomes save
- **Where:** `flowdrip_app.py:4126` (`save_outcomes`)
- **What:** Same pattern as C8 — direct `.write_text()`.
- **Why it matters:** Task outcomes (AI generation success/failure, PDF exports) silently lost. `load_outcomes()` returns `{}` on parse error, masking corruption.
- **Fix direction:** Same atomic-write pattern as C8.
- **Test:** Same as C8.

### C10 — Non-atomic contact CSV save
- **Where:** `flowdrip_app.py:15953` (`_save_contacts_to_csv`)
- **What:** `open(path, "w")` writes the entire contact CSV in place. Crash mid-write nukes the contact database.
- **Why it matters:** Catastrophic — total loss of contact data with no recovery. Highest-impact data-loss path in the app.
- **Fix direction:** Write to `<path>.tmp`, then `os.replace()`. Consider also writing a `.bak` of the previous file before replace, kept for one generation.
- **Test:** Unit test — write, raise mid-write, assert original intact.

### C11 — Community save non-atomic and silently overwrites
- **Where:** `flowdrip_app.py:4424` (`copy_community_to_local`) and `4434` (`save_to_community`)
- **What:** Both use direct `p.write_text()`. Neither checks for filename collision (user's local campaign of the same name, or another user's existing community template).
- **Why it matters:** Two issues bundled: (a) silent overwrite destroys existing campaigns, (b) non-atomic write can corrupt during the save.
- **Fix direction:** Atomic write + collision policy. For local copy: prompt to rename or apply auto-suffix (e.g., `Name (2).json`). For community save: timestamp suffix on collision (`name_20260426_120000.json`).
- **Decision needed from user:** for community, append timestamp on every save (versioning) or only on collision?
- **Test:** Unit — collision case asserts no overwrite; atomicity test mirrors C8.

### C12 — Latent global `QUEUE_PATH` in `funnelforge_core`
- **Where:** `funnelforge_core.py:71–73` and the legacy fallbacks at `flowdrip_app.py:19341–19342`, `19379–19380`
- **What:** `funnelforge_core` defines a single module-level `QUEUE_PATH`. Server mode currently disables this path (line ~2132 of `flowdrip_app.py`), so it's not reachable today. But the fallback in `_load_queue` and `archive_old_queue_entries` still references it under `not _SERVER_MODE`.
- **Why it matters:** If the server-mode guard ever breaks or is removed (refactor, condition flipped), every user's queue collapses into one file → cross-user mail mixing, the worst possible failure for a multi-user product. The same root cause as the 2026-04-20 signature leak incident.
- **Fix direction:** Remove the global `QUEUE_PATH` entirely. Make every queue accessor require an explicit user-resolved path argument. Tests should fail loudly if anything tries to use a module-level fallback.
- **Test:** Static check — grep that `QUEUE_PATH` is no longer module-scoped. Runtime — assert that load/save without an explicit path raises.

### C13 — Outlook COM lifecycle bugs (3 sub-issues)
This is a single fix area with three related leaks; bundling because the fix touches the same COM-init helper code.

- **C13a** `funnelforge_core.py:546` — Scheduler thread calls `pythoncom.CoInitialize()` on each (re)connect but never `CoUninitialize()`. Reference counts and Outlook handles leak.
- **C13b** `flowdrip_app.py:4778–4867` — On `ImportError` of `pythoncom`, the early-return path skips `CoInitialize`, but the `finally` block still attempts `CoUninitialize`. Unbalanced.
- **C13c** `funnelforge_core.py:503–508` — `mail = outlook.CreateItem(0)` is never explicitly released or `del`'d. Per-email COM leak.

- **Why it matters:** Slow degradation. Outlook process memory grows under volume; eventually the COM stack stalls, sends start failing, user has to restart Outlook (sometimes the whole machine).
- **Fix direction:** Track init state with a flag; only call `CoUninitialize` if `CoInitialize` succeeded. Wrap `_send_one_email` in try/finally with `del mail` (or `pythoncom.CoFreeUnusedLibraries()` periodically). Standard pywin32 hygiene.
- **Test:** Hard to unit-test directly. Manual: queue 100 sends, watch Outlook memory; should stay flat. Add a basic init/uninit balance test by mocking `pythoncom`.

---

## Cross-cutting Decisions Needed Before Implementation

1. **C7 (unresolved tokens):** hard-fail at queue time, or silent strip + warn? Default: hard-fail.
2. **C11 (community save):** timestamp every save (versioning) or only on collision? Default: only on collision.
3. **C13 testing:** are we OK relying on manual Outlook-memory verification, or do we need to mock `win32com` in tests? Default: manual is fine; mocking is high-effort, low-value.

## Implementation Order

Suggested sequencing for the writing-plans phase:

1. **Atomicity batch (C8, C9, C10, C11)** — same pattern, low risk, big win, easy to test. Land first.
2. **State/wizard batch (C2, C3)** — closely related, shared helper.
3. **Send-correctness batch (C4, C5, C6, C7)** — touches the queue path. C4 and C7 may interact.
4. **C1 (QEditor)** — needs UI verification, more careful. Standalone.
5. **C12 (QUEUE_PATH removal)** — isolated refactor; verify nothing else depends on the module global.
6. **C13 (COM lifecycle)** — isolated; can land any time.

## Definition of Done

- All 13 fixes merged on a feature branch.
- Each fix verified against the source before implementation (per Verification Discipline above).
- New tests added where the failure mode is unit-testable.
- The app runs locally without regressions on the standard wizard flow (build → contacts → review → launch).
- Deployment: per CLAUDE.md / memory, use `bash _deploy_zero_downtime.sh` only; ask the user before deploying within 8am–5pm PDT.
- No fix introduces backwards-compat shims or dead-code paths.

## Risks

- **Line numbers will drift.** Audit was on a snapshot; the file gets edited daily. The implementer must search by symbol/pattern, not trust the line number.
- **Some Criticals are interconnected** (C2/C3, C4/C7). Fixing them in isolation can hide regressions; group commits accordingly.
- **C13 and C1 are hard to test in CI.** Plan for manual verification time.
- **CLAUDE.md is stale** (claims 7,537 lines; real is 39,950). The implementer should not over-trust the navigation map; treat it as approximate.

## Appendix — Audit Provenance

- Method: 5 parallel audit agents dispatched 2026-04-26, one per category (multi-user safety, send/queue, Outlook, data integrity, UI/state). Severity threshold: Critical/High/Medium.
- Total findings before dedup: ~54. After dedup: 47 (13 Critical, 16 High, 18 Medium).
- This spec covers Criticals only. Highs deferred to a follow-up spec, decided once these 13 are merged and stable.

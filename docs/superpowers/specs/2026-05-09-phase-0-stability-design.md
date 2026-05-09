# Phase 0 — Stability and bug fixes

**Status:** design approved 2026-05-09
**Branch:** `claude/critical-bug-fixes`
**Owner:** Mike

---

## Goal

Restore Candidate Pool to a working state for all users, harden the systemic class-of-bug behind both Candidate Pool failures (per-user writes from background threads silently leaking to a shared file), add basic exception logging so future bug reports include tracebacks, and re-enable the Candidates sidebar entry.

## Non-goals

- No refactor of the 230 existing tagged `print(...)` calls in `flowdrip_app.py`.
- No structured logger migration (debug/info/warn tiers, format conventions, etc.).
- No changes to the resolution order in `_resolve_user_root()`.
- No touching the orphaned 96KB shared `candidate_pool.json` beyond a timestamped backup.
- **No candidate-retention policy.** TTLs and lifecycle rules are deferred to Phase 3 (MPC workflow). Suggested input for that phase: lower the doc's proposed 90-day TTL to ~30 days + auto-delete-on-placement, but that is Phase 3's call, not Phase 0's.

---

## Background — what's already in flight

- `427c2f4 fix(candidates): bulk import bg thread now binds user before writing` — partial fix for the bulk-import path, with `tests/test_bulk_import_user_binding.py`. Not yet validated post-deploy.
- `e565ae8 ui(sidebar): hide Candidates entry while upload + view bugs investigated` — single-line comment-out of the sidebar entry at `flowdrip_app.py:8561`. Top-nav "Candidate Pool" pill and the route handler stay live.
- An orphaned 96KB `/opt/dripdrop/data/candidate_pool.json` exists on the production server, populated by per-user writes that leaked to the shared root before the bulk-import fix. Records have no `_owner_email` field, so attribution back to specific users is not mechanically possible.

## Root cause (recap)

Python `ContextVar` does not propagate into `threading.Thread` workers. The bulk-import worker called `_user_candidate_pool_path()` → `_resolve_user_root()` → `_CURRENT_USER_EMAIL.get()` → `""` → `LEAK_GUARD` fallback → `_BASE_DATA_DIR/candidate_pool.json` (the shared file).

The candidate-finder Search flow at `flowdrip_app.py:33366` spawns a `threading.Thread` that calls `add_candidate_to_pool(cand)` with the same shape, never patched. `~50 other` `threading.Thread(target=...)` sites exist in `flowdrip_app.py`; each is a candidate for the same bug if it does any per-user write.

The `_resolve_user_root()` helper at `flowdrip_app.py:883` already documents this exact failure mode (Leigh's 2026-04-24 incident with avatar uploads). The session-cookie fallback added in response covers handlers running in fresh async tasks but does **not** help threads — `app.storage.user` is not available in a thread context. The systemic fix has to happen at the thread spawn site.

---

## Architecture

### `_run_as_user` helper

Add near the existing per-user path helpers (around `flowdrip_app.py:880-940`):

```python
def _run_as_user(email, target, name=None, daemon=True):
    """Spawn a thread that's pre-bound to `email` for per-user path resolution.

    Use this anywhere a worker thread will read or write per-user state.
    System threads (schedulers, monitors) should keep using threading.Thread
    directly — they don't have a single owning user.
    """
    captured = (email or "").strip()
    def _wrapper():
        if captured:
            try:
                _CURRENT_USER_EMAIL.set(captured)
                _switch_to_user_paths(captured)
            except Exception as ex:
                print(f"[run_as_user] bind failed for {captured}: {ex}", flush=True)
        target()
    t = threading.Thread(target=_wrapper, daemon=daemon, name=name or target.__name__)
    t.start()
    return t
```

### Migration

Replace `threading.Thread(target=fn, daemon=True).start()` → `_run_as_user(s._user_email, fn)` at every per-user-write site. The two known-broken priorities:

| Site | Current | Action |
|---|---|---|
| `flowdrip_app.py:32238` | `_bulk_import_resumes._worker` (already patched inline by `427c2f4`) | Replace inline binding with `_run_as_user`; deletes ~14 lines |
| `flowdrip_app.py:33366` | candidate-finder Search `_run` | Migrate; this is the second known bug |

Plus ~28 additional per-user-write sites identified by the audit (see below).

System threads stay on raw `threading.Thread`:

- `ServerEmailScheduler` — `flowdrip_app.py:44184`
- `ServerReplyMonitor` — `flowdrip_app.py:44617`
- Outlook scanners and similar app-level background workers

Each system-thread site gets a one-line comment marking it as intentional.

### Audit method

Grep `threading.Thread(target=` across `flowdrip_app.py`. For each hit:

1. **Per-user write path** — touches `_user_*_path()`, `save_candidate_pool`, `save_dnc`, `add_candidate_to_pool`, etc. → migrate to `_run_as_user`.
2. **System thread** — no user concept (schedulers, monitors). → keep raw, comment why.
3. **Read-only or stateless** — neither writes nor reads per-user data. → keep raw.

Output a checklist in this spec on completion (or in the implementation plan), recording the classification of every site.

### Logging

**Files:**

- `_BASE_DATA_DIR / "logs" / "errors.log"` — daily rotation, 14-day retention
- Resolves to `%LOCALAPPDATA%\DripDrop\logs\errors.log` on Windows desktop, `/opt/dripdrop/data/logs/errors.log` on production

**Setup (one block near app init, ~`flowdrip_app.py:860`):**

```python
import logging, logging.handlers
_LOG_DIR = _BASE_DATA_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_err_log = _logging.getLogger("dripdrop.errors")
_err_log.setLevel(_logging.ERROR)
_err_log.addHandler(_logging.handlers.TimedRotatingFileHandler(
    _LOG_DIR / "errors.log", when="midnight", backupCount=14, encoding="utf-8"
))
_err_log.propagate = False
```

**Hooks:**

- `sys.excepthook` — uncaught main-thread exceptions
- `threading.excepthook` — uncaught worker-thread exceptions; uses `args.thread.name` for traceability (which is why `_run_as_user` sets `name=target.__name__`)

**Helper:**

```python
def _log_exception(exc, context: str = ""):
    user = ""
    try: user = _CURRENT_USER_EMAIL.get() or ""
    except Exception: pass
    _err_log.error("user=%s context=%s\n%s", user, context,
                   "".join(traceback.format_exception(exc)))
```

Replace the existing 7 `traceback.print_exc()` callsites with `_log_exception(e, context="<callsite>")`.

**Bug-report ergonomics:**

Add a `/diagnostics` endpoint (server mode only, requires login) returning the last 100 lines of `errors.log` plus the most-recent error timestamp. When users report bugs, ask them to hit `/diagnostics` and paste the output — faster than SSH-ing into prod. This is admin tooling; no unit test, manually verified during cutover by hitting the URL once.

**Out of scope:** the 230+ tagged `print(f"[…]")` calls. They keep going to stdout/journalctl, untouched.

---

## Tests (TDD — red, then green)

1. **`tests/test_run_as_user_helper.py`** — Unit tests for the new helper:
   - Worker thread sees `_CURRENT_USER_EMAIL.get() == email` even when spawned from an empty-ContextVar context
   - `_user_candidate_pool_path()` inside the worker resolves to per-user path, not `_BASE_DATA_DIR`
   - Empty/None email → worker still runs; LEAK_GUARD warning fires (correct behavior)
   - Exception inside `target()` doesn't crash the wrapper; bubbles to `threading.excepthook`

2. **`tests/test_individual_candidate_add_user_binding.py`** — Mirrors `test_bulk_import_user_binding.py`. Simulates the candidate-finder Search `_run` flow ending in `add_candidate_to_pool`, asserts the file write lands in the per-user path.

3. **`tests/test_error_log_writes.py`** — Trigger an exception in a worker; assert the rotating file gets a line containing user, traceback, and thread name.

4. **`tests/test_audit_no_raw_per_user_threads.py`** — Static check: scan `flowdrip_app.py` for `threading.Thread(target=` followed (within ~50 lines) by any `_user_*_path()` call. Allowlist system-thread sites by name. **This is the regression net for the whole class of bug** — future leaks of the same shape get caught at test time.

The existing `tests/test_bulk_import_user_binding.py` should still pass after migrating bulk-import to `_run_as_user`.

## Manual validation (post-deploy)

Per memory `feedback_smoke_check_before_deploy.md`: static `import flowdrip_app` doesn't catch render-path errors. Treat the live site as the real signal. Specifically:

1. Log into dripdripdrop.ai as a fresh test user — either a newly-registered account, or an existing account whose `/opt/dripdrop/data/users/<safe_email>/candidate_pool.json` file does not yet exist (so any new write is unambiguously attributable).
2. Sidebar → Candidates → "+ Add New Candidate" → upload a single PDF → confirm it appears in the per-user pool.
3. Click "Bulk Import Resumes" → upload 3 PDFs → confirm all 3 appear in the per-user pool.
4. SSH check: `ls -la /opt/dripdrop/data/users/<safe_email>/candidate_pool.json` exists; `/opt/dripdrop/data/candidate_pool.json` mtime is unchanged from the pre-deploy backup.
5. SSH check: `tail /opt/dripdrop/data/logs/errors.log` — empty or only pre-existing/unrelated errors.

Step 4 is the critical one. If anything writes to the shared file post-deploy, a fix regressed.

---

## Cutover

### Orphan backup (one-time, before Phase 0 ships)

```bash
ssh -i ~/.ssh/dripdrop root@134.199.237.206 \
  "cp /opt/dripdrop/data/candidate_pool.json \
      /opt/dripdrop/data/_orphan_candidate_pool_backup_$(date +%Y%m%d).json && \
   ls -la /opt/dripdrop/data/_orphan_*"
```

Original untouched; backup timestamped. No data destroyed; reconciliation can happen later if desired.

### Sidebar restore

`flowdrip_app.py:8561` — uncomment the `("🔍", "Candidates", "candidate_finder"),` line. Drop the 4-line "hidden 2026-05-08" comment block. Same PR as the fixes per Q5.

### Deploy

Single deploy via `bash _deploy_zero_downtime.sh` per memory `feedback_zero_downtime_deploy.md`. Smoke check is the manual validation above; `/healthz` is not the real signal.

---

## Order of work

1. Backup orphan file on production (one shell command).
2. Add `_run_as_user` helper + unit tests (red → green).
3. Migrate the two known-broken sites; `tests/test_individual_candidate_add_user_binding.py` (red → green).
4. Add logging infrastructure (file handler, excepthooks, `_log_exception` helper) + tests; replace the 7 `traceback.print_exc()` sites.
5. Add `/diagnostics` endpoint (admin tooling, no unit test; smoke-test by hitting the URL).
6. Audit + migrate remaining ~28 per-user thread sites; record classification per site.
7. Add `tests/test_audit_no_raw_per_user_threads.py` regression test.
8. Uncomment Candidates sidebar entry.
9. Deploy via `_deploy_zero_downtime.sh`.
10. Manual validation per "Manual validation (post-deploy)".

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Migrating ~30 threads breaks one of them | Medium | TDD: tests first; audit test catches missed sites |
| `_run_as_user` ordering changes a startup behavior some caller depends on | Low | Helper `.start()`s and returns the Thread (matches old `Thread(...).start()` semantics) |
| Logging file handler can't write (permission/disk) | Low | Wrap setup in try/except; falls back silently to existing stdout prints |
| Sidebar restore exposes a Candidates flow we didn't audit | Low-Medium | Manual validation steps 2 + 3 cover the two known entry points |
| Future thread spawn bypasses `_run_as_user` | Medium | `test_audit_no_raw_per_user_threads.py` is exactly this guard |

## Estimated effort

3-5 days of focused work. Lower end of the doc's 1-2 week Phase 0 estimate, since the bulk-import fix already exists as a template.

---

## Decisions locked during brainstorming

| # | Question | Choice |
|---|---|---|
| 1 | Fix scope | Patch + harden the pattern (helper + audit) |
| 2 | Audit scope | Candidate Pool + cross-user write paths |
| 3 | Logging scope | Exceptions + tracebacks only |
| 4 | Orphaned 96KB file | Backup + leave in place |
| 5 | Sidebar timing | Same PR as the fixes |
| 6 | Pattern shape | `_run_as_user` wrapper |
| 7 | Retention/TTL | Deferred to Phase 3 |

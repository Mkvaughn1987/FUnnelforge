# Phase 0 follow-up — module-init leak audit

**Status:** finding-only. No work scoped yet.
**Surfaced by:** Phase 0 deploy on 2026-05-09 — the new `errors.log` + LEAK_GUARD logging fired 4 times within seconds of the first boot.
**Related:** [Phase 0 spec](2026-05-09-phase-0-stability-design.md) and [Phase 0 plan](../plans/2026-05-09-phase-0-stability-plan.md)

---

## What this is

Phase 0's Task 8 audited every `threading.Thread(target=...)` site in `flowdrip_app.py` for cross-user-leak patterns. That audit was complete for its scope (16 sites migrated, 1 gated, 31 left as system/read-only).

But there's a **second class of cross-user leak** that Task 8 didn't cover: **module-load-time calls to per-user path helpers.** When `flowdrip_app.py` is imported, code at module scope runs before any user is bound. Any module-scope call to `_user_*_path()` / `_user_*_dir()` falls through `_resolve_user_root()` → LEAK_GUARD → `_BASE_DATA_DIR` (the shared cross-user root).

Three sites surfaced on the Phase 0 deploy and were hotfixed in the same session:

| Commit | Site | Fix |
|---|---|---|
| `4745bf3` | `flowdrip_app.py:44682` — `archive_old_queue_entries(days=30)` called in `if __name__ == "__main__":` | Gated with `if not _SERVER_MODE` |
| `31ed365` | `flowdrip_app.py:2156` — `for _d in [_user_campaigns_dir(), _user_contacts_dir(), _user_pdf_dir()]: _d.mkdir(...)` at module scope | Gated with `if not _SERVER_MODE` |
| `351ade0` | `flowdrip_app.py:2154` — `COMMUNITY_DIR = _find_community_dir()` at module scope; the function falls back to `_user_dir() / "Community"` when the OneDrive primary path doesn't exist | Server-mode branch returns `_BASE_DATA_DIR / "Community"` directly |

These were latent bugs that had been silently leaking to shared base-dir paths since the codebase first ran in server mode (months ago). The orphaned `/opt/dripdrop/data/candidate_pool.LEAKED_BACKUP.20260508_014511.json` (96340 bytes from May 7) is direct evidence — Candidates were leaking via the bulk-import thread (now fixed in `9d5addf`), but the module-init pattern is the OTHER vector that could have produced similar shared files for `Campaigns/`, `Contacts/`, `PDFs/`, and `Community/`.

## Why Task 8's audit didn't catch these

Task 8 grepped for `threading.Thread(target=...)` patterns. Module-init code:
- Doesn't spawn threads
- Runs at import time, in the main thread
- Has no `_run_as_user` wrapper option (the helper assumes a request context with a captured user)

The fix surface is different: module-init code either has to be **gated** by environment (server vs. desktop) or **lifted** out of module scope into a per-request hook.

## What a broader audit should cover

For a future session, search `flowdrip_app.py` for all of:

1. **Module-scope expressions** — anything not inside a `def`/`class` that calls `_user_*` helpers. The grep used in this session was:
   ```bash
   grep -nE "^[^ \t#].*_user_[a-z_]+\(" flowdrip_app.py
   ```
   Returns three hits today (lines 840, 862, 2156 — first two are `_user_data_dir()` which is the BASE dir and correct).

2. **`__main__` block** at file end — `if __name__ in {"__main__", "__mp_main__"}:` contains boot logic. Anything in there that calls `_user_*` helpers needs the same gate.

3. **Class `__init__` for module-instantiated singletons** — `outlook_monitor = OutlookMonitor()` and `pool_scanner = CandidatePoolScanner()` are instantiated at module init. Their `__init__` methods run synchronously before any user is bound. Both are currently safe (they only set instance attributes), but worth checking when adding new singletons.

4. **Module-level decorator side effects** — `@ui.page("/path")` registrations don't trigger per-user paths today, but custom decorators that pre-compute paths would.

## Recommended fix pattern

For server-mode-aware module-init code, the gate is straightforward:

```python
if not _SERVER_MODE:
    # do the per-user thing at boot
```

For functionality that genuinely needs a per-user iteration in server mode (e.g., archive every user's queue, not just one), the pattern is:

```python
if _SERVER_MODE:
    for user_dir in (_BASE_DATA_DIR / "users").iterdir():
        # iterate explicitly, bind ContextVar per iteration
        ...
else:
    # desktop single-user path
    ...
```

This is essentially what `ServerEmailScheduler` and `ServerReplyMonitor` do today.

## When to do this

Low urgency. The 3 known sites are fixed. New module-init code is rare. A 30-minute focused audit pass during a future Phase 1+ session would close the loop and could be paired with a static-analysis test similar to `test_audit_no_raw_per_user_threads.py` — scan for module-scope `_user_*` calls and assert they're either inside a `_SERVER_MODE` gate or in an explicit allowlist.

## Acceptance criteria for closing this finding

- All module-scope calls to per-user path helpers in `flowdrip_app.py` are either gated by `_SERVER_MODE` or replaced with explicit per-user iteration
- A regression test (e.g., `tests/test_audit_no_module_init_per_user_calls.py`) prevents regression
- A second deploy boot shows zero LEAK_GUARD warnings (the current state, post-hotfixes)

# RESUME — ThriveModal Phase 1 (splice applied; tests pending — updated 2026-09-17)

Cold-start companion to `docs/HANDOFF-thrivemodal-phase1.md`. That doc is the spec;
this one is only "where we stopped and what to type next".

## State right now

- Branch: `integration/phase0-main-into-whitelabel` (Phase 0 merge `1f64461`, already done).
- **The Phase 1 splice E1-E7 IS APPLIED** to the working tree (verified 2026-09-17).
  An earlier bash-heredoc attempt failed, but `_session_artifacts/2026-09-16/apply_phase1_splice.py`
  was then written as a Python file and ran clean. `flowdrip_app.py` went 59,460 -> 60,129 lines,
  parses (AST OK), and carries every marker: block at 9061/9075, `tgt_map` (E2),
  `_contacts_csv_text` at 8388 (E3) and 25310 (E7), `_tgt_map` (E6a).
- The change is **uncommitted** (`M flowdrip_app.py`). HEAD still holds the pre-splice file,
  so `git checkout -- flowdrip_app.py` is the rollback.
- Nothing deployed. No campaign data touched.
- **Not yet done:** the tests. That is the next action, not the splice.

## Preserved artifacts

Everything from the session scratchpad was copied to `_session_artifacts/2026-09-16/`
(untracked, 16 MB). Do not delete without reading this list:

| File | What it is |
|---|---|
| `targeting_block.py` | **The Phase 1 helper block, 641 lines, AST-clean.** Already spliced in (E1). Must contain exactly one `_CONTACT_COLMAP_SNAKE`. |
| `funnelforge-all-refs-20260916.bundle` | Safety bundle of every ref, incl. the 23 unpushed `main` commits. |
| `arena-prod-snapshot/` | Arena production files pulled off `134.199.237.206`. |
| `arena-drift-manifest.txt` + `manifest.sh` | Drift inventory and the LF-normalised-hash detector. |
| `BASELINE_FAILURES.txt` / `POSTMERGE_FAILURES.txt` / `FINAL_FAILURES.txt` | Test baselines. Compare by **name**, not count. |
| `ats_*.py`, `prod_arena_ats.py` | The three `ats.py` variants for the parked reconciliation. |

## Test baseline

17 failed / 739 passed / 1 skipped on this branch. Track the **list** in
`FINAL_FAILURES.txt`, never the number — 9 of the failures are orphan tests for
functions that were never implemented, so the count drifts on its own.

Run with `.venv/Scripts/python.exe -m pytest`; prefix `PYTHONIOENCODING=utf-8`
when output may contain non-ASCII (Windows cp1252 will otherwise raise).

## Do NOT re-run apply_phase1_splice.py

It is not idempotent, and it fails destructively partway through. Verified by replaying it
against a copy of the current tree on 2026-09-17:

1. It re-runs the block repair and writes a **second** `_CONTACT_COLMAP_SNAKE` into
   `_session_artifacts/2026-09-16/targeting_block.py`, in place. That file is **untracked**,
   so git cannot restore it — this is the one loss that is not free.
2. It overwrites `flowdrip_app.before-phase1.py` with the already-spliced file. Harmless as it
   stands: that backup is byte-identical to `HEAD:flowdrip_app.py` (`863ed78`), so git is the
   real rollback. Do not start relying on the file instead.
3. It then dies at E3 (`span(): substring not found`), after step 2 has already landed.

To redo the splice from scratch: `git checkout -- flowdrip_app.py`, restore a clean
single-`_CONTACT_COLMAP_SNAKE` `targeting_block.py`, then run the script once.

## The splice, for reference (already applied)

Seven exact-string edits, all applied. Kept here so the intent is reviewable and so a
redo does not have to be re-derived. Patch via a **Python file**, never a bash heredoc —
it failed twice on this block.

`flowdrip_app.py` is pure LF; open it with `newline=""` and assert no `\r\n`
before patching. Assert `src.count(old) == 1` on every replacement.

| # | Where | Change |
|---|---|---|
| E1 | before `def list_saved_contact_lists():` | insert the 641-line block |
| E2 | `normalize_csv` | add `tgt_map = _targeting_header_map(headers)` after `norm_map` |
| E3 | `normalize_csv` writer | buffer `out_rows`, `_contacts_csv_text`, `_atomic_write_csv_text` |
| E4 | `_normalize_rows` | `tgt_map` + `rec.update(_extract_targeting(r, tgt_map, snake=False))` |
| E5 | `load_contacts` | hold the `DictReader`, map headers once, `snake=True` |
| E6 | `_parse_contacts_csv` | `_tgt_map` before the loop; set only non-blank values |
| E7 | `_save_contacts_to_csv` | `_contacts_csv_text` + `_atomic_write_csv_text` |

Re-grep every anchor first. The line numbers in the handoff doc are stale post-merge,
and so are any in this file.

**Resolved (2026-09-17):** an earlier handoff flagged E7's `_CONTACT_COLMAP_SNAKE` as
possibly missing. It is not a problem, and it was never meant to pre-exist. The splice
script builds the dict itself and injects it into the block immediately before
`def _contacts_csv_text`, so E1 carries it into `flowdrip_app.py` ahead of E7's use of it.
It now sits at `flowdrip_app.py:9061`, used once at `:25310`. Nothing to add.

## Next action: the tests

`py_compile` already passes. Write
`tests/test_thrivemodal_targeting.py` (25 tests, five groups — CSV back-compat,
company index, audience filter, duplicate guard, **Arena isolation**), and diff
the suite against `FINAL_FAILURES.txt`.

## Two decisions already made, so they don't get relitigated

**The CSV header is data-driven, not playbook-gated.** `_contact_csv_fieldnames(rows)`
emits the ten targeting columns only when some row actually carries a targeting value.
An Arena file with no firmographics stays byte-identical at ten columns; a ThriveModal
file widens to twenty; readers tolerate both. Gating on the workspace playbook instead
would make the same file write differently depending on a setting, which is the failure
mode this avoids.

**The queue path is not touched.** `_norm_contact` still emits its eight keys, so
`scheduled_queue.json` stays byte-identical and sender behavior is unchanged. The queue
boundary *is* the resolution to the scope contradiction — targeting never crosses it.
A test should assert this rather than leaving it as a convention.

## Still open

- Phase 1 splice + tests (above).
- Phases 2-4: targeting UI and saved audiences; analytics (audit attribution first,
  mark unavailable historical metrics as unavailable); vertical templates for
  logistics / accounting / property management.
- Phases 5-6 deferred by Mike (multi-mailbox, further integrations).
- **Parked:** the Arena production/repository drift fix. Inventory is complete in
  `arena-drift-manifest.txt`; the work itself has not started.

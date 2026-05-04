# Today Page Auto-Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-update the call briefing and LinkedIn message cards on the Today page within ~5s of background AI generation completing, without triggering a refresh storm.

**Architecture:** Single page-level `ui.timer` chain in `p_today_combined`. Snapshots inflight campaign-name set on render. One-shot timer polls every 5s; calls `rf()` exactly once when any snapshotted job completes; re-arms otherwise.

**Tech Stack:** Python 3, NiceGUI, pytest.

**Spec:** `docs/superpowers/specs/2026-05-04-today-page-auto-refresh-design.md`

---

## File Structure

**Modified:**
- `flowdrip_app.py` — one block added near the top of `p_today_combined` (around L10650-L10660, right after the existing `_ai_script_timer_scheduled = [False]` placeholder).

**Created:**
- `tests/test_today_auto_refresh.py` — three source-grep tests verifying the timer setup is present and shaped correctly.

No new modules. No changes to bg threads. No changes to per-card render functions.

---

## Task 1: Add auto-refresh timer chain to `p_today_combined`

**Files:**
- Modify: `flowdrip_app.py` — `p_today_combined` (function starts at L10639)
- Test: `tests/test_today_auto_refresh.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_today_auto_refresh.py` with this content:

```python
"""p_today_combined must auto-refresh while AI background generation
is running on call-briefing / LinkedIn-message cards. Verified via
source-grep: the function should include a ui.timer that polls the
two inflight sets and uses once=True to avoid recurring-timer storm."""
import inspect


def test_p_today_combined_includes_inflight_poll_timer():
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_today_combined)
    assert "_call_briefing_gen_inflight" in src, (
        "p_today_combined must reference _call_briefing_gen_inflight "
        "to detect completion of AI bg generation"
    )
    assert "_li_message_gen_inflight" in src, (
        "p_today_combined must reference _li_message_gen_inflight "
        "to detect completion of AI bg generation"
    )
    assert "ui.timer(" in src, (
        "p_today_combined must schedule a ui.timer for the auto-refresh poll"
    )


def test_p_today_combined_poll_uses_once_true():
    """The poll timer must use once=True. Plain recurring timers would
    accumulate across re-renders and re-create the original storm."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_today_combined)
    # Find the ui.timer line nearest the inflight-set references
    assert "once=True" in src, (
        "p_today_combined's auto-refresh timer must use once=True "
        "to avoid stacking recurring timers across renders"
    )


def test_p_today_combined_snapshots_inflight_for_completion_detection():
    """The poll must compare a snapshot of inflight names taken at
    render time against the current inflight names — set difference
    detects which jobs completed since render started."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_today_combined)
    assert "frozenset(" in src, (
        "p_today_combined must snapshot inflight names with frozenset() "
        "so set difference can detect completed jobs"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_today_auto_refresh.py -v`

Expected: All 3 tests FAIL — `_call_briefing_gen_inflight not in src`, `_li_message_gen_inflight not in src`, `frozenset( not in src` (the existing function doesn't reference these).

(`ui.timer(` and `once=True` may already appear in `p_today_combined` for unrelated reasons. If those two specific tests pass before implementation, that's fine — the other assertions still drive the change.)

- [ ] **Step 3: Add the timer chain**

In `flowdrip_app.py`, find this existing block at the top of `p_today_combined` (around L10650):

```python
    # Closure-mutable flag so we schedule at most one refresh timer per page
    # render even if multiple AI script panels are mid-generation.
    _ai_script_timer_scheduled = [False]
```

Note: the `_ai_script_timer_scheduled` flag is dead code (no other code reads or writes it). LEAVE IT ALONE for this task — removing it is out of scope and risks regressions. Just add the new block right after it.

Insert this block immediately after the `_ai_script_timer_scheduled = [False]` line (same indentation, 4 spaces):

```python
    # Auto-refresh timer for AI generation cards (call briefing + LI message).
    # Each card's bg thread populates camp['call_briefing'] / camp['linkedin_message']
    # then removes the camp name from the appropriate inflight set. We snapshot
    # the union of inflight names at render time, then poll every 5s with a
    # one-shot self-rearming timer. When any snapshotted job completes, fire
    # rf() exactly once and let the next render decide whether to keep polling.
    #
    # Why a snapshot + set-difference: counting completions by length alone
    # misses the case where one job completes and another starts in the same
    # tick window (count unchanged but a snapshotted job is gone).
    #
    # Why once=True + re-arm: a plain recurring ui.timer would accumulate
    # across re-renders, recreating the historical "refresh storm" the
    # comment in _render_call_briefing_card warns about.
    _origin_inflight = (
        frozenset(getattr(s, '_call_briefing_gen_inflight', set()) or set())
        | frozenset(getattr(s, '_li_message_gen_inflight', set()) or set())
    )
    if _origin_inflight:
        def _poll_ai_gen():
            still = (
                frozenset(getattr(s, '_call_briefing_gen_inflight', set()) or set())
                | frozenset(getattr(s, '_li_message_gen_inflight', set()) or set())
            )
            if _origin_inflight - still:
                # At least one snapshotted job completed — refresh once.
                try:
                    rf()
                except Exception as ex:
                    print(f"[TodayAutoRefresh] rf error: {ex}", flush=True)
                return
            if _origin_inflight & still:
                # Still waiting on at least one — keep polling.
                ui.timer(5.0, _poll_ai_gen, once=True)
        ui.timer(5.0, _poll_ai_gen, once=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_today_auto_refresh.py -v`

Expected: All 3 tests PASS.

- [ ] **Step 5: Smoke-import check**

Run: `python -c "import flowdrip_app; print('OK')"`

Expected: prints `OK`.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -x -q`

Expected: all tests pass (was 207 before this change; now 210 with the 3 new tests).

- [ ] **Step 7: Commit**

```bash
git add tests/test_today_auto_refresh.py flowdrip_app.py
git commit -m "$(printf 'feat(today): auto-refresh AI-generating cards within 5s\n\nCall briefing and LinkedIn message cards used to require a manual\npage refresh after their bg AI thread finished. Added a page-level\nui.timer poll that detects completion via snapshot + set-difference\nand fires rf() at most once per tick window. Avoids the historical\nrefresh storm that the existing comment in _render_call_briefing_card\nwarns about.')"
```

---

## Task 2: Manual smoke test + deploy

This task does NOT auto-execute — the implementer agent must report results to the user.

- [ ] **Step 1: Per memory `feedback_no_local_run.md`, do NOT start the local app.** Skip directly to the deploy step.

- [ ] **Step 2: Per memory `feedback_auto_deploy.md`, check the time.** It's currently late evening / early morning Pacific (outside 8am-5pm) — auto-deploy is permitted. If a future iteration runs this in business hours, ask "deploy now or end of hour?" first.

- [ ] **Step 3: Run zero-downtime deploy**

Run: `bash _deploy_zero_downtime.sh`

Per memory `feedback_zero_downtime_deploy.md`: never use plain `systemctl restart dripdrop`.

- [ ] **Step 4: Smoke-check live `/`**

Per memory `feedback_smoke_check_before_deploy.md`: hit live `/` to confirm full-page render, not just `/healthz`.

Run: `curl -sS -o /dev/null -w "status: %{http_code} | size: %{size_download}\n" https://dripdripdrop.ai/`

Expected: status 200, non-trivial size (~30k+).

- [ ] **Step 5: Tell the user to verify**

Tell the user: "Deployed. To test: open the Today page on dripdripdrop.ai with a fresh campaign that hasn't yet generated its call briefing or LI message. Watch the spinner — it should swap for actual content within ~5s of generation completing, no manual refresh needed."

---

## Self-Review Notes

Spec coverage:
- §"Algorithm" → Task 1 Step 3 (the inserted block matches the spec algorithm exactly)
- §"Why this avoids the refresh storm" → Comment block inside the inserted code references this
- §"Test plan" source-grep tests → Task 1 Step 1 (3 tests)
- §"Test plan" manual smoke → Task 2

Type/symbol consistency:
- `s._call_briefing_gen_inflight` confirmed to exist — initialized in `_render_call_briefing_card` ([flowdrip_app.py:10440](flowdrip_app.py#L10440))
- `s._li_message_gen_inflight` confirmed to exist — initialized in `_render_li_message_card` ([flowdrip_app.py:10551](flowdrip_app.py#L10551))
- `ui.timer(interval, callback, once=True)` is the established NiceGUI pattern in this codebase (15+ existing uses)
- `rf()` is the standard refresh callable already passed into `p_today_combined`

Placeholder scan: no TBD/TODO. All code blocks are complete. All grep targets are concrete strings. The `_ai_script_timer_scheduled` dead-code observation is noted but explicitly out of scope (call out, leave alone).

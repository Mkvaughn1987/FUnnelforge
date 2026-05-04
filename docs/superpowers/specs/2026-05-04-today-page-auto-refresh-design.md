# Today Page — Auto-Refresh Generating Cards

**Date:** 2026-05-04
**Status:** Approved (design discussed inline; user said "yes")
**Affected file:** `flowdrip_app.py`

## Problem

Two cards on the Today page generate AI content in a background thread:

- `_render_call_briefing_card` ([flowdrip_app.py:10426](flowdrip_app.py#L10426)) — call briefing (talking points + candidate spotlights)
- `_render_li_message_card` ([flowdrip_app.py:10536](flowdrip_app.py#L10536)) — LinkedIn connection message

While generating, both render: *"✨ Generating in the background — refresh in ~30s to see it."* The user has to manually refresh to see the result.

Historical context (from comment at [flowdrip_app.py:10465-10470](flowdrip_app.py#L10465-L10470)): an earlier version called `rf()` from each background thread on completion. With multiple campaigns each spawning two bg threads (call + LI), completions stacked up within ~30s and the user perceived the resulting cluster of `rf()` calls as "random refreshing."

## Goal

Cards auto-update within ~5 seconds of completion, without the refresh storm. The user should never have to manually refresh.

## Design

Add a single page-level `ui.timer` setup at the top of `p_today_combined` ([flowdrip_app.py:10639](flowdrip_app.py#L10639)) that polls the two inflight sets and calls `rf()` at most once per tick if anything completed.

### Algorithm

On every page render:

1. Snapshot the union of currently-inflight campaign names from both sets:
   ```python
   _origin = (frozenset(getattr(s, '_call_briefing_gen_inflight', set()) or set())
              | frozenset(getattr(s, '_li_message_gen_inflight', set()) or set()))
   ```

2. If `_origin` is empty, do nothing (no work to wait on; skip the timer entirely).

3. If `_origin` is non-empty, schedule a single one-shot timer that:
   - Re-snapshots the union of inflight names
   - If `_origin - still_inflight` is non-empty (some original job completed), call `rf()` and return without re-arming. The next render handles re-arming.
   - Else if any original job is still inflight, re-arm with another one-shot timer

```python
def _poll():
    still = (frozenset(getattr(s, '_call_briefing_gen_inflight', set()) or set())
             | frozenset(getattr(s, '_li_message_gen_inflight', set()) or set()))
    if _origin - still:
        rf()
        return
    if _origin & still:
        ui.timer(5.0, _poll, once=True)

if _origin:
    ui.timer(5.0, _poll, once=True)
```

### Why this avoids the refresh storm

- **One timer chain per render.** Each render creates at most one `_poll` chain, regardless of how many cards are mid-generation.
- **One `rf()` per tick window.** Even if 5 jobs all complete in the same 5-second window, the next tick fires `rf()` exactly once.
- **Self-terminating.** When all original jobs complete, the chain calls `rf()` once and stops. Next render will start a new chain only if new work has been kicked off.

### Why polling instead of bg-thread `rf()`

The bg threads can't call `rf()` directly without risking the storm — many threads completing in close succession trigger many UI rebuilds. Polling decouples completion from rendering: many completions get bundled into one tick.

### Tradeoff

Up to ~5 seconds of perceived delay vs. instant. Could shrink the interval to 2–3s if the perceived lag is annoying — each tick is cheap (two `len()` checks on small sets, one set difference). Picking 5s as a reasonable default.

## Non-Goals

- No change to the bg-thread completion handlers (the comment about removing `rf()` there stays valid).
- No change to the `is_inflight` check inside the per-card render functions — they still show the spinner when generating, the cached content when done.
- No `ui.refreshable`-based partial refresh. Full-page `rf()` is the established pattern in this codebase.
- No new state variables on `AppState`. Reuses the existing inflight sets.

## Risks

- **Old timer chain doesn't immediately stop on user navigation.** NiceGUI cleans up timers when the client disconnects or navigates. A `once=True` timer with no re-arm is naturally short-lived (one tick max). Worst case: one stray tick fires after navigation; the inflight check is cheap and the `rf()` won't render anything useful. No user-visible impact.
- **Race between bg thread setting cache and timer reading set.** Both happen on the main asyncio loop or via `inflight.discard()`. Python set mutation is GIL-protected. The condition `_origin - still` is a snapshot read; if a new job starts during the tick, it doesn't affect this chain's exit decision (we only care about the `_origin` snapshot).

## Test plan

Source-grep tests in `tests/test_today_auto_refresh.py`:

- `p_today_combined` source includes a `ui.timer(` call.
- `p_today_combined` source references both `_call_briefing_gen_inflight` and `_li_message_gen_inflight` (the new poll function).
- The poll function uses `once=True` (avoids accidental recurring-timer storm).
- The poll function compares snapshot vs current to detect completion (verified by source-grep for `frozenset(` or similar marker).

Manual smoke (via deploy):
- Open Today page with a campaign whose call briefing or LI message has not been generated yet.
- Watch the spinner. Within ~5s of generation completing, the spinner should swap for the actual content without a manual refresh.
- Open multiple campaigns simultaneously; confirm the page does not refresh more than once per ~5s tick window even if multiple jobs complete close together.

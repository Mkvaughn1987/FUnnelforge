# Send Window Randomization — Implementation Plan

## What It Does
Instead of sending all emails for a given step at the exact same time (e.g., all 100 contacts get Email 1 at 9:00 AM), randomize each contact's send time across a window (e.g., 8:00 AM – 10:30 AM). Also enforce a hard cap of **20 emails per minute** to prevent burst detection.

## Architecture

The schedule table currently has a "Send time" column with a single time per email step (e.g., "9:00 AM"). That time is the same for all contacts. The randomization happens at **send time in the core**, not in the UI — so:

- **UI stays the same** — user picks a single time per email step (this becomes the "window start")
- **New UI element** — a "Send Window" card below the Preset Sequences card with:
  - A checkbox: "Randomize send times across a window" (default: ON)
  - A label explaining: "Each contact receives emails at a slightly different time within the window to improve deliverability"
  - Window duration dropdown: "30 min", "1 hour", "1.5 hours", "2 hours", "2.5 hours" (default: "1.5 hours")
  - Throttle info label: "Max 20 emails per minute"
- **Core change** — `_send_sequence_for_contact` in `funnelforge_core.py` gets a `send_window_minutes` parameter. For each email step, it offsets the time by a random 0 to `send_window_minutes` minutes. The 20/min throttle is enforced by spacing contacts at least 3 seconds apart.

## Files to Change

### 1. `funnel_forge/app.py`

**a) Add state variable** (~line 1278, near existing window vars):
```python
self.send_window_enabled_var = tk.BooleanVar(value=True)
self.send_window_duration_var = tk.StringVar(value="1.5 hours")
```

**b) Add Send Window card** — new method `_build_send_window_card(parent, row=2)`:
- Card with checkbox "Randomize send times" + duration dropdown
- Helper text explaining the feature
- Called from `_build_sequence_screen` and `_build_sequence_tab` after preset card

**c) Update `_run_sequence`** (~line 17822):
- Read `send_window_enabled_var` and `send_window_duration_var`
- Convert duration string to minutes (30, 60, 90, 120, 150)
- Pass `send_window_minutes` to `run_4drip()` as new parameter

**d) Update save/load config** — persist the send window settings in template/config JSON

### 2. `funnelforge_core.py`

**a) Update `run_funnelforge`** and `run_4drip` signatures:
- Add `send_window_minutes: int = 0` parameter
- Pass it through to `_send_sequence_for_contact`

**b) Update `_send_sequence_for_contact`**:
- Accept `send_window_minutes` parameter
- For each email: if `send_window_minutes > 0`, add `random.randint(0, send_window_minutes)` minutes to the send time
- Enforce 20/min throttle: after every email, call `time.sleep(3)` (20 per minute = 1 every 3 seconds)

**c) Update the loop in `run_funnelforge`** (line 804):
- Add a 3-second `time.sleep()` between contacts to enforce 20/min
- This happens naturally since each contact triggers Outlook COM calls, but we add an explicit floor

### 3. `funnel_forge/styles.py`
- No changes needed

## Throttle Math
- 20 emails/minute = 1 email every 3 seconds
- For 100 contacts × 1 email step = 100 emails → ~5 minutes to process
- The Outlook COM calls already take ~1-2 seconds each, so the 3-second sleep adds minimal overhead

## Save/Load
- `send_window_enabled` and `send_window_duration` saved to `funnelforge_config.json`
- Also saved/loaded with templates so each template can have its own window setting

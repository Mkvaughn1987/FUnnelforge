# Dashboard: replace "Top Candidates" widget with a Pipeline stat card

## Problem

The home dashboard's "Job Match status" card showed the small per-user
"Top Candidates" pool (`candidate_pool.json`, ~18 active candidates): a
scanner status line, new-match callouts, and a per-candidate list with
match counts. That pool is a legacy, per-user roster feature — it does not
reflect the shared Pipeline (ATS) database (3,865 candidates across the
team), which is where candidate sourcing actually happens today for most
campaign types.

## Scope

Dashboard card only. The "Top Candidates" roster/pool subsystem itself
(`candidate_pool.json`, `load_candidate_pool()`/`save_candidate_pool()`,
`pool_scanner`, the full roster page at `candidate_finder`) is untouched —
still used by Arena 4x4/5x5 and the standalone roster page. Only the
dashboard's card is being replaced.

## Design

Replace the "Job Match status" card (`flowdrip_app.py`, previously lines
27122-27199, plus its `_dash_pool`/`_dash_active_pool` setup at
26908-26911) with a small "Pipeline" stat card, styled identically to its
sibling dashboard cards ("N total responses", "N tasks today"):

- Header row: "Pipeline" label + a "View" button that navigates to
  `/ats` (same navigation used by the topbar Pipeline link and the MPC
  chooser — `ui.navigate.to("/ats")`, not `nav_go`, since `/ats` is its
  own NiceGUI page route).
- Two stat lines below, matching the muted 11px style used by the other
  cards' list rows:
  - `"{total:,} candidates in Pipeline"` — `ats.total_count()`, the full
    shared database.
  - `"{mine:,} added by you"` — `ats.total_count(owner=email)`, scoped to
    the current user via `_CURRENT_USER_EMAIL.get()`.

`ats.total_count(owner=None)` already exists (`ats.py:792`) and its
docstring already anticipates this exact use ("per-user when owner is
given (the dashboard tile)"). `ats` is imported locally inside the
dashboard render function, matching the codebase's existing convention of
never importing `ats` at module top level in `flowdrip_app.py`.

No new state, no scanner, no per-candidate rows — this card is read-only
navigation plus two counts.

## Out of scope / not done here

- Removing or changing the "Top Candidates" roster page or pool storage.
- Changing how Arena 4x4/5x5 source candidates (by design, they use the
  pool — separate from this card).
- Any change to `ats.py` itself.

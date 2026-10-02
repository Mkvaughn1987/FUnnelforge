# ZoomInfo Bulk → seat fallback, board order, and the Sales Campaign worker

Date: 2026-10-02. Approved in conversation with Mike. DripDrop (Arena) only;
inboxslide is untouched.

## Problem

- Every DripDrop AI Prompts run and the Sales Campaign hand-off brief say
  "pull the buying centre out of ZoomInfo" and nothing more. When the
  connector's Bulk Credits run dry, `enrich_contacts` fails on quota and the
  run stops, even though the user's own ZoomInfo Talent seat (a separate,
  larger pool) would have worked. PipelineBlast/CandidateBlast already know
  this fallback; the prompts DripDrop hands everyone do not.
- Job-board order is Google → ZipRecruiter → LinkedIn (Indeed "sparingly").
  Wanted: Google Jobs → LinkedIn Jobs → Indeed → ZipRecruiter, search all
  four, then pick the best targets from the pooled results.
- Sales Campaign runs only move when someone pastes a phrase into Claude.
  Wanted: a per-user hourly Claude desktop task that works them.
- The Sales Campaign page renders nothing unless the user has saved ZoomInfo
  REST API credentials, which the Claude hand-off does not use. Only Mike can
  use the page today.

## Design

### 1. One rule block, in the AI Prompts code (`zoominfo_pull.py`)

Pure text, no imports from the app. Used by `ai_prompts.py` (Arena runs),
`staffing_prompts.py` (staffing runs) and `sales_campaign.handoff_brief`.

- `BOARDS_DEFAULT` = "Google Jobs first, then LinkedIn Jobs, then Indeed,
  then ZipRecruiter".
- `BOARDS_RULE`: Google bot check → never solve it, say it was skipped.
  Search every board either way; pool the results; a company posting on more
  than one board is a stronger signal; pick the best targets from the pool.
- `ZI_PULL_RULE`: connector first (search_companies → search_contacts,
  free → enrich_contacts in batches of 10, Bulk Credits). A quota / "Limit
  exceeded" error is not a failure: switch to the user's own seat by driving
  their logged-in recruiter-app.zoominfo.com tab in Chrome (candidate search
  + per-person preview, monthly view credits). Never type a password; a
  logged-out Talent tab is reported, not worked around. If both are out,
  keep the company as *waiting on ZoomInfo* with the literal error and carry
  on with the rest. Say which pool paid for each contact.

Placement: appended to every contact-pulling step (Arena `slate_campaign`,
`sales_campaign`, `market_candidates`; staffing `_CONTACTS_STEP`). The
`boards` field default and the bot-check sentence change in every sourcing
step. Inboxslide's `tm_prompts.py` is not touched.

### 2. Parked companies on the server (`sales_campaign.py`)

- `sales_run_update` accepts `parked` (list of company rows, each with
  `waiting_reason`) and `credits` (free-text line, e.g. "Bulk: 34 then Limit
  exceeded. Seat: 41."). Stored on the run.
- On `sourced`: if nothing is above the contact floor but something is
  parked, the run ends `parked` (new terminal status, "Waiting on ZoomInfo")
  instead of `error`.
- Each parked row gets `retry_after` = now + 2 days and `attempt` (1-based,
  carried from the parent).
- `pending_runs` first spawns follow-up runs: for every parked row past
  `retry_after` and not yet spawned, group by parent run into one new
  `handoff` run (`retry_of`, `retry_companies`, same target). A row whose
  attempt is already 3 is marked `dropped: ZoomInfo out` instead.
- A follow-up's brief says: do not re-source; pull contacts for exactly
  these companies, same rules, post back as usual. Its contacts then go
  through the normal build → review → launch path, so a second batch is
  always held at review.
- "Retry now" on the page sets `retry_after` to now and spawns immediately.
- `latest_run` prefers a run sitting at review over a newer one, so a
  follow-up never hides a review the user has not acted on.

### 3. Sales Campaign page

- Usable without REST API credentials. The credentials panel moves behind
  the "ZoomInfo settings" button for everyone.
- Parked companies are listed under "Waiting on ZoomInfo" with the error,
  the retry date and a "Retry now" button, on the review, summary and
  `parked` screens.
- Credit line shown on review.

### 4. AI Prompts: "Work my Sales Campaigns automatically"

New ARENA routine + starter `sc_worker`. Fields: hours (default 7am–6pm),
days (default weekdays), time zone (default Mountain). The prompt has Claude
desktop create an hourly scheduled task "DripDrop - Sales Campaign worker"
whose body is: call `sales_runs_pending`; for each run, claim it and follow
its `instructions` exactly; if none, end quietly.

### 5. ZoomInfo setup pop-up

Dialog listing the four one-time steps (connectors on in Claude desktop;
log in to recruiter-app.zoominfo.com; in Claude in Chrome set "Always allow"
for recruiter-app.zoominfo.com, google.com and linkedin.com, as copy chips;
run the worker setup). Shown when the user opens the worker starter, and on
Sales Campaign "Start" until they tick "I've done this". Ack stored per user
in config (`sales_campaign.zi_setup_ack`).

### 6. Connector

`sales_run_update` docstring documents `parked` and `credits`. Restart
`dripdrop-mcp` on deploy.

## Testing

Unit tests: rule block present in every Arena/staffing contact step and
absent from inboxslide; board order; parked → follow-up spawn, attempt cap,
retry-now, `parked` terminal status, `latest_run` preference; golden
fixtures regenerated. Full suite green (baseline 0). Then one supervised
live run with Mike.

## Deploy

Files: `zoominfo_pull.py` (new), `ai_prompts.py`, `staffing_prompts.py`,
`sales_campaign.py`, `mcp_server/dripdrop_mcp.py`. Prod base is `bdbf5bd`
plus the AI Prompts files from `d0e6921`; drift-check every file before
upload, restart green → blue → mcp.

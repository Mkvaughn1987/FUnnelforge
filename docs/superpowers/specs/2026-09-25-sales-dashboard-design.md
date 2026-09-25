# Sales Dashboard: where the business is, by company

Date: 2026-09-25. Branch: `feat/sales-dashboard` (off
`feat/whitelabel-instance` 6bddcb6). Scope: the inboxslide sidebar layout
only. Arena's classic nav is untouched. Follows
`2026-09-24-sales-companies-pipeline-design.md`, which left the Sales
Dashboard row in the nav model with no page.

## Why

Outreach Analytics answers "what did the emails do": sent, people reached,
reply rate, by campaign, by step. Nothing answers "where is the business":
how many companies reached each stage, what moved this week, and which
companies are waiting on a rep. The Pipeline board shows the current state
but not conversion, movement or neglect. The Sales Dashboard is that page.

It reads the same company roll-up Companies and Pipeline use. Nothing is
estimated; every number is a count over rows the user can open.

## Page (`sales_dashboard`, sidebar row `sales_dash` under PERFORMANCE)

1. **Header** with the page help and a window picker: 7 days / 30 days /
   All time (default 30), the same buttons Outreach Analytics uses.
   Stored on the session as `_sd_days`.

2. **Funnel.** For each stage Prospect through Client, the number of board
   companies at that stage *or beyond* (Lost is excluded from every step),
   drawn as CSS bars scaled to the widest step, with the step-to-step
   conversion beneath each (Contacted over Prospect, Replied over
   Contacted, and so on). Beside it: Lost count and a win rate of Client
   over Client plus Lost. Uses the resolved stage, so a rep's manual stage
   is respected. The funnel is not windowed: it is the state of the book.

3. **This window**, five tiles, each a count with the companies behind it:
   - Newly contacted: first send inside the window.
   - New replies: first reply inside the window.
   - Moved to Meeting or Proposal: a stage-history entry inside the window
     with one of those stages.
   - Won: on the Clients list with `added_at` inside the window.
   - Lost: a stage-history entry inside the window with stage lost.
   Clicking a tile lists its companies below (name, stage, last activity),
   each opening the company on Companies. Stored as `_sd_pick`.

4. **Needs a hand**, three lists, eight rows each then
   "+N more on Companies", each row opening the company on Companies:
   - Replies waiting: stage Replied by the data, no manual stage, no next
     step. Someone answered and nobody has said what happens next.
   - Stale next steps: a next step whose record was last touched more than
     14 days ago.
   - Going quiet: Meeting or Proposal with no send or reply in 30 days, or
     none ever.
   These are not windowed either; neglect is neglect whatever the picker
   says.

5. **Empty state** when no company is on the board yet, pointing at
   Companies.

## Stage history

`save_pipeline_record` gains one behaviour: when the stage it writes
differs from the stage the record had, it appends
`{"stage": <new or "">, "at": <iso seconds>, "by": <actor>}` to the
record's `history` list (capped at 50, oldest dropped). A record with no
manual fields left is still deleted, history and all, as before. Old
records without a history keep working: the Moved and Lost tiles fall back
to the record's `updated_at` when there is no history and the current
stage is a manual one, so a company moved before this change still shows
once.

## Roll-up additions

`company_rollup` rows gain `first_sent`, `first_reply` (ISO strings, ""
when none) and `client_since` (the earliest `added_at` among the active
Clients entries the company matched, "" when unknown). Nothing existing
changes.

## Pure function

`dashboard_stats(rollup, days, now=None)` in `sales_pages.py` returns

```
{"days": 30,
 "funnel": [{"key": "prospect", "label": "Prospect", "count": 40, "rate": None},
            {"key": "contacted", ..., "rate": 0.85}, ...],   # rate vs previous step
 "lost": 3, "win_rate": 0.4,
 "window": {"contacted": [rows], "replied": [rows], "moved": [rows],
            "won": [rows], "lost": [rows]},
 "attention": {"replies_waiting": [rows], "stale_next_steps": [rows],
               "going_quiet": [rows]}}
```

Rows are the roll-up dicts, sorted by last activity, newest first. The
funnel and the attention lists ignore `days`. `now` is injectable for
tests. Window membership uses the same lexicographic ISO comparison the
analytics page uses; an undated record is inside every window.

## Wiring

- `SIDEBAR_NAV`: `("sales_dash", "Sales Dashboard", "sales_dashboard")`.
- `SIDEBAR_PAGE_ROW`: `sales_dashboard -> sales_dash`.
- `SIDEBAR_TITLES`: `sales_dashboard -> "Sales Dashboard"`.
- Router: the `companies` / `pipeline` branch also takes `sales_dashboard`
  and calls `sales_pages.p_sales_dashboard`.
- `PAGE_HELP["sales_dashboard"]`.
- Connector: `GET /api/v1/tm/sales_dashboard?days=7|30|all` returns the
  dict above with rows through `public_row`; MCP tool `tm_sales_dashboard`
  (read-only). The MCP service is restarted by hand after deploy.

## Tests

- `tests/test_sales_dashboard.py`: funnel counts and rates; Lost excluded
  and win rate; the five window tiles including the legacy `updated_at`
  fallback; the three attention lists; history append on stage change and
  not on a note edit; cap; the wiring (sidebar row, page-row map, title,
  help, router, route, MCP tool).
- `tests/test_sidebar_layout.py`: Sales Dashboard moves from the unwired
  list to the wired one; `sales_dashboard` joins the known router keys.
- `tests/test_sales_pages.py`: the router assertion string widens.

## Out of scope

Per-rep breakdowns. Charts over time. Editable company records.

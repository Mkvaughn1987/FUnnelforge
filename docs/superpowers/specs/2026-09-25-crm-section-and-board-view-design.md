# CRM section, and the Pipeline board as a view of Companies

Date: 2026-09-25. Branch: `feat/sales-dashboard` (after
`2026-09-25-sales-dashboard-design.md`). Scope: the inboxslide sidebar
layout only. Arena's classic nav is untouched.

## Why

Mike asked to move the SALES section down the sidebar and rename it, and
questioned whether the Pipeline page was needed at all, since Companies
already filters by stage and the new Sales Dashboard carries the counts.

A look at the tools the market uses settled all three:

- **Name.** HubSpot, Instantly and Smartlead label the group of contacts,
  companies and deals **CRM**. HubSpot's separate "Sales" menu holds
  sequences, the sales workspace and sales analytics, which is our
  CAMPAIGNS section. Attio says "Records". Nobody labels records "Sales".
- **Position.** HubSpot puts CRM right after Home. Campaign-first tools
  (Instantly, Smartlead, Attio) lead with campaigns and inbox and put the
  CRM below them. inboxslide is campaign-first, so CRM sits below CONTENT,
  above PERFORMANCE. None of them put records below reporting.
- **Board.** Every one of them has a single deals page and the kanban is a
  view toggle on it: Apollo's Deals switches table / kanban, Close's
  Pipeline View lives under Opportunities, Pipedrive's Deals has pipeline
  and list views, Smartlead's Smart Funnel is a kanban whose system columns
  (New Lead, Email Sent, Reply Received) are our derived Prospect,
  Contacted, Replied. Nobody has a list page and a separate board page of
  the same objects.

## Sidebar after this change

| Section | Rows |
|---|---|
| HOME | Overview, My Day, Replies |
| CAMPAIGNS | Campaigns (sub-rows), Newsletters |
| CONTENT | Sales Assets, AI Prompt, Saved Prompts |
| CRM | Companies, Contacts, Clients |
| PERFORMANCE | Sales Dashboard, Outreach Analytics |

The Pipeline row, page key, title, help entry and router branch are gone.

## Companies page

- A **Table | Board** toggle in the filter bar (`s._co_view`, default
  table). The stage filter shows in Table only; the search box applies to
  both.
- **Table**: the stage picker now sits in the Stage column of every row,
  so a move is one click without expanding the row. When a rep's manual
  stage is below what the data says, a small "data says replied" line
  shows under the picker (the badge's old hint). The expanded card keeps
  its picker, next step and note; "See on the board" switches the view.
- **Board**: the old Pipeline body without its page head and count strip
  (the Sales Dashboard funnel has the counts). Clicking a card name opens
  that company in the table. "+N more in the table" switches to the table
  filtered to that stage. Empty state points at the Table view.

## Sales Dashboard

Each funnel bar opens Companies in Table view filtered to exactly that
stage.

## Unchanged

Pipeline records, `sales_pipeline.json`, stage history, the connector
routes `GET/POST /api/v1/tm/pipeline` and `GET /api/v1/tm/companies`, the
MCP tools `tm_pipeline` / `tm_companies`, and the Sales Dashboard numbers.

## Tests

- `tests/test_sidebar_layout.py`: section order HOME, CAMPAIGNS, CONTENT,
  CRM, PERFORMANCE; CRM rows; no Pipeline row or page-row entry; router
  string.
- `tests/test_sales_pages.py`: Companies is routed, titled and helped;
  no `p_pipeline`; `p_companies` has the board view and the in-row
  picker; router string.
- `tests/test_sales_dashboard.py`: funnel click-through present.
- Render smoke and a route walkthrough with a test client (scratch
  script, not in the suite).

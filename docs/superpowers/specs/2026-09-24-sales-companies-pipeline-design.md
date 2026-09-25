# Sales section: Companies + Pipeline pages, and an honest sidebar

Date: 2026-09-24. Branch: `feat/sales-companies-pipeline` (off
`feat/whitelabel-instance` 8f63a6c). Scope: the inboxslide sidebar layout
only (`DRIPDROP_NAV_LAYOUT=sidebar`). Arena's classic nav (`SALES_NAV`) is
untouched.

## Why

The 2026-09-16 sidebar was designed around a CRM information architecture
(Companies / Contacts / Pipeline / Clients, Sales Dashboard) that was never
built. Rows with no page are skipped at render time, so what the user sees
is a SALES section holding only Contacts (a campaign audience list) and
Clients (a suppression list), an OUTREACH section that files the Newsletter
*send* under "Content Library" next to a prompt-writing tool, and a
WORKSPACE section that holds the follow-through on campaigns (My Day,
Replies). Every surviving row is a campaign-engine row wearing a CRM label.

Mike's call: keep SALES, build the two missing pages, and regroup the rest.

## Sidebar after this change

| Section | Rows | Notes |
|---|---|---|
| HOME | Overview, My Day, Replies | Was WORKSPACE. The workspace selector sits directly above, so the old label stuttered. |
| SALES | Companies, Contacts, Pipeline, Clients | Companies and Pipeline are new pages. Clients stays: it is the list of won accounts and the terminal Pipeline stage. |
| CAMPAIGNS | Campaigns (Active / Completed / Drafts / Templates sub-rows), Newsletters | Was OUTREACH. Newsletters is a running send, so it lives with campaigns. |
| CONTENT | Sales Assets, AI Prompt, Saved Prompts | Content Library goes away as a parent row; the three pages become top-level rows one click closer. AI Prompt and Saved Prompts are ThriveModal-only and resolve through the existing additive `_tm_nav_page_key` table. |
| PERFORMANCE | Outreach Analytics | Unchanged. Sales Dashboard stays in the model with no page and stays hidden; the Pipeline page carries a stage-count strip that covers the need for now. |

Settings, Admin and the profile button are unchanged. Do Not Contact stays
under Settings.

The page header's Content Library tabs (Newsletters / Sales Assets) go
away because the sidebar rows now do that job. The Campaigns sub-rows are
unchanged. The "new" crumb reads "Campaigns" instead of "Outreach".

## Companies page (`companies`)

A read-time roll-up of every contact the user has, grouped by employer.
No company file is written. Grouping reuses `_company_index`, which keys
on `company_id`, then a verified `CompanyDomain`, then the normalised
company name, and refuses to guess from email domains (see its docstring).
Contacts with no company at all are counted in a footnote, not shown.

Sources, all already on disk:

- `contacts.csv` and every saved list (`list_saved_contact_lists`), plus the
  contacts embedded in each campaign record (people who were enrolled from
  a list that has since been replaced still show up).
- The send queue: sent / scheduled counts and the last send date per
  company, joined through an email -> company map built from the contacts.
- The responded log: reply count and the latest reply per company.
- The Clients blocklist: a company whose verified domain, or any contact
  email domain, is on the active blocklist is a client.
- The pipeline records (below): stage, note, next step.

Each row: company, contacts, campaigns (count, names on hover), sent,
scheduled, replies, last activity, stage. Search box filters on company
name and domain; a stage filter narrows to one stage. Sorted by last
activity, newest first, companies with no activity last, alphabetical.

Clicking a row expands it inline: the contacts (name, title, email, and
whether they replied), the campaigns that touched them, the latest reply
snippet, and the pipeline card (stage picker, next step, note). Saving the
card writes the pipeline record. One row open at a time.

Empty state: no contacts yet, with a button to the Contacts page.

## Pipeline page (`pipeline`)

The same company roll-up as a board. Stages, in order:

| Stage | How a company gets here |
|---|---|
| Prospect | In a campaign, or has a pipeline record, but nothing sent yet. |
| Contacted | At least one email sent. |
| Replied | At least one reply in the responded log. |
| Meeting | Manual. |
| Proposal | Manual. |
| Client | On the Clients blocklist. Always wins; the blocklist is the source of truth for won business. |
| Lost | Manual. |

Resolution: Client if on the blocklist; otherwise the manual stage if a
record has one; otherwise the derived stage. A manual stage set below the
derived one (say a rep marks "Prospect" on a company that has replied) is
kept, because it is the rep's word, and the card shows a small "replied"
hint so the mismatch is visible.

The board shows companies that have been in at least one campaign or have
a pipeline record. Companies that only exist as rows in an uploaded list
stay on the Companies page; a board with 800 untouched prospects is noise.
Each column caps at 40 cards with a "+N more on Companies" line. Lost is a
collapsed column showing a count until opened.

Card: company name, contacts count, last activity, reply count, stage
picker (moving a card writes the record), and the next step if set.
A count strip across the top shows companies per stage.

Manual records live in the team's shared dir, next to the Clients
blocklist: `teams/<domain>/sales_pipeline.json`, a dict keyed by company
key:

```json
{"name:acme corp": {"name": "Acme Corp", "stage": "meeting",
  "next_step": "Send proposal", "note": "Talked to Dana 9/22",
  "updated_at": "2026-09-24T10:12:00", "updated_by": "mike@thrivemodal.com"}}
```

Writes are atomic (tmp + replace), the same as the blocklist. Team scope
matches Clients: a company won or lost is a team fact, not a per-user one.

## Module layout

New file `sales_pages.py`, lazy-imported from the router like
`ai_prompts.py`, so a broken module takes out two pages, not the app.
It reaches app helpers through the same `_ff()` accessor.

Pure, filesystem-free, unit-tested:

- `company_rollup(contacts, campaigns, queue, responded, clients, records)`
  -> list of company dicts with the counts above and `stage`,
  `stage_basis` ("client" / "manual" / "derived").
- `derived_stage(company)` and `resolve_stage(company, record, is_client)`.
- `board_companies(rollup)`: the subset the Pipeline shows.

Storage: `load_pipeline(email)`, `save_pipeline_record(key, fields, actor)`.

UI: `p_companies(s, rf)`, `p_pipeline(s, rf)`.

## flowdrip_app.py changes

- `SIDEBAR_NAV`: the table above. `SIDEBAR_LIBRARY` removed.
  `_TM_NAV_PAGES` gains `ai_prompt -> tm_prompts`,
  `saved_prompts -> tm_saved_prompts`.
- `SIDEBAR_PAGE_ROW`: `companies -> companies`, `pipeline -> pipeline`,
  `newsletters -> newsletters`, `pdf_gen -> assets`,
  `tm_prompts -> ai_prompt`, `tm_saved_prompts -> saved_prompts`.
- `SIDEBAR_TITLES`: Companies, Pipeline, Newsletters, Sales Assets,
  AI Prompt, Saved Prompts.
- `_sidebar_v2`: the Content Library sub-row block goes; nothing else.
- `_page_header_v2`: the Content Library tabs go; the "new" crumb reads
  Campaigns.
- Router: `companies` and `pipeline` lazy-import `sales_pages`.
- `PAGE_HELP` entries for both pages (title, summary, next action, sections)
  so the `?` help works.
- Connector: `GET /api/v1/tm/companies` (the roll-up, with `q` and `stage`
  filters) and `GET/POST /api/v1/tm/pipeline` (board, and
  `{"key", "stage", "next_step", "note"}` to move a card), plus MCP tools
  `tm_companies` and `tm_pipeline`. The MCP service is restarted by hand
  after deploy (the deploy script does not do it).

## Tests

- `tests/test_sales_pages.py`: roll-up counts from fixture data, stage
  derivation and resolution (client beats manual beats derived), board
  subset rule, pipeline save/load round-trip under a tmp team dir, the
  router and nav wiring (source grep).
- `tests/test_sidebar_layout.py`: Companies and Pipeline are now wired;
  only Sales Dashboard remains unwired; the page-row map reflects the new
  rows; the router knows every wired key.
- Existing ThriveModal phase-3 nav tests keep passing (the additive rule
  for `_tm_nav_page_key` is unchanged).

## Out of scope

Sales Dashboard page. Companies as editable records (industry, size,
owner). Per-user pipelines. Open/click tracking (does not exist anywhere).

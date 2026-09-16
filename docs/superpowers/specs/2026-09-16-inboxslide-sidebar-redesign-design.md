# inboxslide sidebar redesign — design and audit

Date: 2026-09-16. Branch: `feat/whitelabel-instance`. Scope: navigation and
layout only, for the inboxslide instance (ThriveModal). Arena is untouched.

## Switch

`DRIPDROP_NAV_LAYOUT` — `classic` (default, Arena) or `sidebar` (inboxslide).
`DRIPDROP_WORKSPACE_NAME` — label in the workspace selector; falls back to the
tenant Company Profile name, then the team domain, then the brand name.

Both keys are carried by `deploy/sync_brand_env.py` (prefixes `DRIPDROP_NAV_`
and `DRIPDROP_WORKSPACE_`) and set in `deploy/env.inboxslide.example`.
When unset, `topbar()`, `sidebar()` and the shell in `index()` run the
classic code paths unchanged.

## What the sidebar layout renders

Full-height 240px sidebar (`_sidebar_v2`):

- Logo (click goes Home), workspace selector with a menu to Company Profile,
  Team and Do Not Contact, and a full-width **+ New Campaign** button.
- WORKSPACE: Overview (`dashboard`), My Day (`drip`), Replies (`responses`).
- SALES: Contacts (`contacts`), Clients (`active_clients`).
- OUTREACH: Campaigns (`seq_mgr`), Content Library (`newsletters`).
- Bottom: Admin (only when `_is_admin`), Settings (expands to Email & AI
  Setup, Company Profile, Team, Signature, Timezone, Do Not Contact when a
  settings page is open), and the profile button with My Profile, Signature,
  Email & AI Setup and Logout.
- Badges: My Day shows open tasks due today, red when any is overdue.
  Settings shows an amber "Setup" pill while the first-run setup is
  incomplete. No other badges.
- Icons are inline outline SVGs (Lucide shapes, 1.75 stroke), labels 14px,
  rows 40px, section labels 11px uppercase muted, one pale-green active
  state (`teal_dim` background, `teal` text).

Compact 56px page header (`_page_header_v2`):

- Section crumb + page title (from `SIDEBAR_TITLES`).
- Contextual actions: on Campaigns, status tabs Active / Completed / Saved /
  Templates; on Content Library, Newsletters / Sales Assets; on Contacts, a
  Do Not Contact shortcut; on Do Not Contact, a Contacts shortcut.
- Quick-find search over campaign names and contact name / company / email.
  A campaign result opens it in Campaigns (or the Saved tab for drafts); a
  contact result opens the Contacts page (the contacts page has no filter
  state to pre-fill, see below).
- Theme toggle, same control as the classic top bar.

Navigation goes through `_sidebar_nav`, which mirrors the classic sidebar's
`_go`: setup gate on New Campaign, back-history snapshot, draft auto-save
and wizard reset when starting a campaign, Saved-tab shortcut. Routes, page
keys and permission checks are unchanged. The onboarding tour selectors
(`avatar`, `nav-start_seq`, `nav-dashboard`, `nav-contacts`,
`nav-ai_settings`) are preserved.

## Consolidations

- Current Campaigns + Saved Campaigns → **Campaigns** with header tabs.
  Active / Completed toggle `s._mgr_show_completed` on `seq_mgr`; Saved is
  the existing `start_seq` + `_tab="saved"` view.
- **Templates** opens the existing campaign-type chooser (4x4, 5x3, AI
  builder, from scratch). The dormant `_tab == "templates"` rendering in
  `start_seq` (recruiting-flavoured nurture sequences, nothing sets it) stays
  dormant.
- Newsletters + Sales Assets (`pdf_gen`) → **Content Library** with header tabs.
- Team, Company Profile, Email & AI Setup, Signature, Timezone, Do Not
  Contact → **Settings**. Do Not Contact is also one click from the
  workspace menu and from the Contacts header.
- Hub pills (Sales / Emails / Today) are gone; every destination lives in
  the Sales hub. The Emails-hub pages are aliases of Sales pages
  (`e_contacts`, `e_responses`, `e_signature`) and map to the same rows.

## Requested destinations NOT wired (no page exists)

The nav model lists them with `page_key=None`; the sidebar skips them and
skips a section when it has no renderable rows, so nothing empty is shown.

| Requested | Status |
|---|---|
| SALES → Companies | No company-level page exists. Contacts have a `company` field but there is no roll-up. Separate work. |
| SALES → Pipeline | The only Pipeline is the recruiting ATS (`/ats`), off here via `DRIPDROP_ATS_ENABLED=0`. A sales opportunity pipeline does not exist. Separate work. |
| PERFORMANCE → Sales Dashboard | No page. Separate work. The section is omitted entirely. |
| PERFORMANCE → Outreach Analytics | No page. Separate work. |
| Replies unread badge | Responses are not tracked as read/unread, so no honest count exists. No badge. |
| "sales opportunities" metric | The dashboard's "candidates in Pipeline" card counts ATS candidates. There is no sales-opportunity data to replace it with, so the card is now gated on `_ATS_ENABLED` (hidden on inboxslide) rather than relabelled. |
| Contact search pre-filter | `p_contacts` has no search/filter state, so a quick-find contact result lands on the Contacts page without filtering. |

## Other copy change

Clients page subtitle reads "so we don't accidentally pitch our own clients"
when `DRIPDROP_BRAND_COPY=sales`; Arena's "recruit from" wording is kept
otherwise.

## Verification

- `ast.parse` on `flowdrip_app.py`.
- Subprocess smoke: import with `DRIPDROP_NAV_LAYOUT=sidebar`, render
  `_sidebar_v2` + `_page_header_v2` for every page key, exercise
  `_sidebar_nav` for Campaigns, Saved and New Campaign; import with the
  variable unset and confirm `_SIDEBAR_LAYOUT` is False.
- `tests/test_sidebar_layout.py` (source-grep style).

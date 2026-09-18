# ThriveModal "AI Prompt" tab and research fold-in

Date: 2026-09-17
Branch: `feat/whitelabel-instance` (inboxslide instance only)

## Goal

Give the inboxslide (ThriveModal) instance an **AI Prompt** page under Content
Library. The user picks what they want done, accepts or overrides recommended
targeting defaults, and gets a paste-ready prompt for an AI assistant that is
connected to inboxslide through the MCP connector. The prompt tells the
assistant how to find prospects, which claims it may make, and which inboxslide
tools to call to create the outreach.

At the same time, fold the two ThriveModal research documents (ChatGPT
"client acquisition research and AI targeting playbook" and Claude
"Sales Intel Brief", both dated 2026-09-17) into the playbook defaults,
the vertical pack, the OneDrive sales PDFs, and persistent memory.

## Decisions already made

1. **Align to what thrivemodal.com states.** Savings are stated as "up to
   60 to 70 percent, fully burdened" and treated as an upper bound, never a
   promise. ThriveModal is the employer of record and handles HR, compliance,
   payroll and IT setup. No upfront or placement fee, month to month, no
   cancellation fee, lifetime free replacement, bi-weekly invoicing, three or
   more vetted candidates per role with video pre-screens, start in about ten
   days, account executive reply within 24 hours, NDAs, dedicated staff,
   isolated workstations, VPN, and the ThriveCore support layer.
   "Zero Risk Consultation" is the name of the CTA, not a literal claim.
2. **Keep the guardrails both documents agree on.** Never quote a monthly
   rate. Never invent client counts, retention, certifications or results.
   One person is not 24/7 coverage. Knichel Logistics and The Travel Byrds
   are proof references, not prospects. No national stereotypes.
3. **Vertical order** becomes logistics, accounting, property management,
   healthcare administration, home care, then general. Construction / AEC
   stays as a block but is demoted to exploratory and sorts after the core
   verticals.
4. **Approach 1 for the page.** Reuse the Arena AI Prompts engine
   (`ai_prompts.py`) by lifting its catalogue into a swappable object with
   Arena as the default, and add `tm_prompts.py` that supplies the
   ThriveModal catalogue. Arena's page keeps its catalogue and behaves
   identically.

## Architecture

### `ai_prompts.py` (engine, shared)

- New `Catalogue` dataclass holding everything that is product specific:
  `routines`, `routine_by_key`, `default_routine`, `standing_rules`,
  `unattended_rule`, `starters`, `starter_by_id`, `sequences`,
  `template_key`, `default_sequence`, `setups_file`, `product`,
  `connector`, `assistant`, page title, page sub copy, result copy, and an
  optional `result_extra(r, C)` hook for the extra card the Arena page shows
  for the Sales Campaign routine.
- `finalize_routines(routines)` appends `COMMON_FIELDS`, builds
  `field_by_key`, and returns `routine_by_key`.
- `ARENA = Catalogue(...)` is built from the existing module globals, and the
  globals stay as aliases so every existing import and test keeps working.
- A module-level `_CAT` binding holds the active catalogue. `p_ai_prompts`
  sets it to `ARENA`; `p_tm_prompts` in `tm_prompts.py` sets it to the
  ThriveModal catalogue before dispatching. `build_prompt(req, cat=None)`
  takes an optional catalogue for tests and defaults to `_CAT`.
- Every place that read `ROUTINES`, `ROUTINE_BY_KEY`, `DEFAULT_ROUTINE`,
  `STANDING_RULES`, `UNATTENDED_RULE`, `STARTERS`, `STARTER_BY_ID`,
  `SEQUENCES`, `TEMPLATE_KEY`, the setups file name or the "DripDrop"
  strings in page copy reads it from the catalogue instead.
- Session state attribute prefix stays `_aip_*`; the two pages are never
  open in the same session because the instance is pinned to one playbook.

### `tm_prompts.py` (ThriveModal catalogue)

- `VERTICALS`: an ordered data table, one entry per vertical, each with
  key, label, band (recommended size band), buyers, roles, triggers,
  first workload, discovery question, software tells, seasonality, and
  an `exploratory` flag. Core: logistics / 3PL, freight forwarding,
  accounting / CAS, property management, healthcare administration,
  home care, general back office. Exploratory: construction / AEC,
  marketing agencies, travel, e-commerce, HVAC / home services,
  distributors, professional services.
- Routines (each with recommended defaults the user can override):
  - `tm_signal_hunt`: hiring-signal hunt, builds `tm_hiring_signal`
    campaigns (default).
  - `tm_lookalikes`: Knichel lookalikes through the ZoomInfo connector.
  - `tm_displacement`: companies already offshore with another provider.
  - `tm_cost_pressure`: WARN / layoff / cost-pressure scan.
  - `tm_seasonal`: seasonal push for one vertical.
  - `tm_audience`: work a saved inboxslide audience into a campaign.
  - `tm_account`: one-account deep dive, research only.
  - `other`: free text.
- Steps name the inboxslide MCP tools (`tm_import_contacts`,
  `tm_audiences`, `tm_audience_preview`, `campaign_types`,
  `my_campaign_styles`, `create_campaign`, `campaigns_list`,
  `tm_mailboxes`) and the ZoomInfo connector.
- Standing rules: claims discipline (the six website terms, no price, no
  invented proof, one person is not 24/7), check `tm_mailboxes` before
  creating campaigns, ZoomInfo seat caveat, disqualifiers, freshness
  windows (vacancies within 30 days, announcements within 90).
- Setups file `tm_prompt_setups.json`; product name "inboxslide";
  page title "AI Prompt".
- `p_tm_prompts(s, rf)` binds the catalogue and calls the engine page.

### `flowdrip_app.py` wiring

- New `_SIDEBAR_ICONS["sparkle"]` glyph.
- `SIDEBAR_LIBRARY` gains `("sparkle", "AI Prompt", "tm_prompts")` only
  when `_is_thrivemodal()` at render time, so Arena never shows it. The
  static table keeps the third row so the sidebar tests can assert on it;
  the render loop skips it for Arena.
- `SIDEBAR_PAGE_ROW["tm_prompts"] = "library"`,
  `SIDEBAR_TITLES["tm_prompts"] = "Content Library"`.
- Route: `elif page == "tm_prompts":` lazy-imports `tm_prompts` and calls
  `p_tm_prompts(s, rf)` with the same try/except fallback label pattern the
  Arena route uses.

### Playbook and vertical pack content

- `_TM_DEF_BUSINESS`, `_TM_DEF_SERVICES`, `_TM_DEF_INDUSTRIES`,
  `_TM_DEF_PROBLEMS`, `_TM_DEF_DIFFERENTIATORS`, `_TM_DEF_PROOF`,
  `_TM_DEF_PRICING`, `_TM_DEF_VOICE`, `_TM_DEF_CTAS`,
  `_TM_DEF_SALES_MOTION`, `_TM_DEF_FORBIDDEN` rewritten to the website
  aligned position. The forbidden list keeps every claim the tests
  require (guarantee, time to fill, bench, newsletter, attachment, prior
  conversation) and drops the bans on "zero risk" as a CTA name and on
  employer of record.
- `_TM_VERTICALS` reordered with new blocks for logistics, accounting,
  property management, healthcare administration and home care. Each
  block carries the five required headings and no digits, prices,
  percentages, guarantees or named customers. Construction / AEC keeps
  its block and sorts after the core verticals; `general_offshore` stays
  last.
- `_TM_VERTICAL_KEYWORDS` extended. The software-engineering guard stays.
  "Healthcare", "Financial Services" and "Real Estate" now resolve to a
  vertical, so the phase 4 "unrelated industries" test moves to labels
  that still resolve to general.

## Testing

- `tests/test_ai_prompts_catalogue.py`: Arena `build_prompt` output for a
  representative request is byte-identical before and after the refactor
  (golden captured from the pre-refactor module); module aliases still
  exist; `p_ai_prompts` renders under a stubbed `nicegui`.
- `tests/test_tm_prompts.py`: every routine has fields, steps format with
  defaults, no step or rule quotes a price or a percentage as a promise,
  the prompt names inboxslide and never DripDrop, `p_tm_prompts` renders
  ask, confirm and result views under a stubbed `nicegui`, the setups file
  is the ThriveModal one.
- `tests/test_sidebar_layout.py`: third sub-row present with an icon,
  `SIDEBAR_PAGE_ROW["tm_prompts"] == "library"`, and the row is skipped
  for Arena.
- `tests/test_thrivemodal_phase4.py` and `test_thrivemodal_playbook.py`
  updated for the new vertical order and the website-aligned wording.
- pytest compared against the baseline failure list, not the count.

## Out of scope

- Deploying (Mike runs `bash ~/bin/deploy-inboxslide.sh`).
- Any change to Arena's AI Prompts behaviour or copy.
- A calendar link in CTAs (none is published; the CTA stays the Zero Risk
  Consultation form).

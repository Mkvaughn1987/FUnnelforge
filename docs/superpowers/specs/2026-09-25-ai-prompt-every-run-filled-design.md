# AI Prompt: every run opens filled in

Date: 2026-09-25. Instance: inboxslide (ThriveModal). Files: `tm_prompts.py`, `ai_prompts.py`, `flowdrip_app.py`, `tests/test_tm_prompts.py`.

## Why

The hiring-signal run was the only one of the eight where every box was written for the vertical picked: its signals menu, roles, size and buyers are all authored per vertical. The other five prospecting runs borrowed roles, size and buyers from the vertical but kept one fixed string for their own boxes. Displacement searched "Manila, Cebu, Philippines..." for every vertical, cost pressure read the same seven states, lookalikes started from Knichel's website even for accounting, and "Where" said "anywhere in the United States" on every run. The three runs whose first box is the user's own data (saved audience, one account, create your own) opened empty.

Mike: "use Fable to go into each of the AI Sales Prompts and fill them out to the best extent, like the first one." Chosen approach: author the answers now and bake them in, no live call on open.

## What changed

### 1. Every vertical row authors the run-specific answers

Each of the 14 `VERTICALS` rows gains:

- `location`: where the market concentrates, as places, with a short parenthetical reason. Written to read inside "companies in {location} of about {company_size}". Four verticals with no geography say "anywhere in the United States".
- `seed`: one real company website for the lookalike run. Knichel stays the logistics seed. `general` has none, so that run keeps asking.
- `terms`: one to three offshore tells specific to the vertical (its desk with a Philippines location, its software), each with a why-line.
- `states`: six to eight states whose WARN feed matters for that market, each with a why-line.

`_FROM_VERTICAL` now also copies `location` and `seed`, so prefill and the build-time fallback treat them exactly like roles and size. Location's field default is blank so prefill writes it.

### 2. Two more tick lists on the same engine as the signals list

- Displacement: "What to search for" is a `checks` field. The menu is the vertical's own terms first, then `UNIVERSAL_TERMS` (Philippines/Manila/Cebu, offshore team, US hours, VA, BPO, remote open abroad). All ticked to start. An "Anything else to search for" box follows; its text is appended to the prompt's search sentence.
- Cost pressure: "Which states' WARN notices to read" is a `checks` field off the row's states. All ticked to start.
- `CHECKS` maps each tick-list key to (menu, ids, prose). `checklist_tm`, `prefill_tm`, `_derive_tm` and `recommend_tm` iterate it, so the signals behaviour (staleness on vertical change, ids-only recommendation, menu travelling with the ask) applies to all three.
- Missing and empty stay different: no key gets the recommendation; an emptied list widens the search and the prompt says so (`_CHECKS_EMPTY`).

### 3. Dropdowns off the user's own data

- New engine field type `pick`: a `ui.select` with `with_input` and `new_value_mode="add-unique"`, options from `PICK_OPTIONS[source]()`, set by the host app. No options means a plain input. `pick_first=True` fills a blank box with the first option in `run_prefill`.
- Audience run: `audience` is a pick from `audiences` with `pick_first`. Account run: `company` is a pick from `companies`, not pre-chosen.
- App: `_tm_pick_options()` binds `audiences` to `load_saved_audiences()` and `companies` to `_tm_company_names()` (the `_company_index` roll-up over `load_contacts()`, name-sorted). Bound on the page render and in `_tm_api_prompt_engine()` for the connector.
- `describe_runs` reports a pick as text with `options` and `any_text: true`. `apply_answers` accepts any text.

### 4. Ready-made jobs on "Create your own"

`F(..., chips=[...])` renders clickable chips above a box. `OWN_JOBS` holds six: who replied this week, companies with no campaign yet, tomorrow's call list, revive finished campaigns, draft this month's newsletter, clean my contact list. Clicking one writes `what` and `done_when`; both stay editable.

Arena declares no pick, chips or source on any field; its golden fixture is unchanged.

## Tests

`tests/test_tm_prompts.py` gains eleven tests: every vertical authors the four new keys with unique ids and a website-shaped seed; universal terms on every menu; the two new tick lists are checks off the picked vertical; prefill fills and refills location, seed, terms, states and never a typed box; ticked labels and extra terms reach the prompt; missing versus empty; build-time fallback and the general seed gap; menus travel with the recommendation ask and answers come back as ids in menu order; picks and their connector shape; chips; the widgets render under the stubbed UI. One existing assertion gained `location` in the prefilled set.

## Deploy

Branch `feat/tm-prompts-filled` from `ebdd5a9` in a fresh worktree. `~/bin/deploy-inboxslide.sh` on the box, then restart `dripdrop-mcp` by hand (the deploy script never does, and `describe_runs` changed shape), then import `tm_prompts` on the box with a stubbed `nicegui`.

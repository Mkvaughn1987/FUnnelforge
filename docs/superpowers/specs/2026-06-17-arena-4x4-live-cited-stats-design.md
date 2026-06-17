# Arena 4×4: Live Cited Market Stats for Email 2 & 4

Date: 2026-06-17
Status: Approved (design)

## Goal
Replace the model's recalled (hallucination-prone) market numbers in the
Arena 4×4 with real, sourced figures pulled by a live web search at build
time, and present each with a clean "Source: ..." attribution in Email 2
(Top Talent Insights) and Email 4 (Market Trends).

## Background
The 4×4 is the `fourbyfour` preset in `AICB_CAMPAIGN_TYPES`. Its prompt
currently tells the model to "include 3-4 real market facts ... never
fabricate", relying on the model's own memory. That is the exact
hallucination risk this feature removes.

The app already has a domain-locked web-search tool
(`_safe_web_search_tool`, ~L8447) with an allowlist (`_WEB_SEARCH_DOMAINS`,
~L8434) covering bls.gov, indeed.com, glassdoor.com, linkedin.com, and
census.gov. A cached stats helper `_market_stats_for_industry` (~L1033)
exists but stores no source label and is not wired into the 4×4. The user
chose a LIVE per-campaign search (not the cache) for freshness and
role/location specificity.

## Scope

### New components (all in `flowdrip_app.py`)
- `_cited_stats_prompt(role, location, industry) -> str` (pure): builds the
  web-search prompt. Asks for 3-5 current US hiring-market facts relevant
  to the role/location/industry, each with a concrete number and a clean
  source label (publisher + year). Includes an explicit no-fabrication
  rule and the exact JSON return shape.
- `_parse_cited_stats(text) -> list` (pure): parses the model's text into a
  validated list of `{"fact": str, "source": str}`. Strips ```json fences.
  Drops any entry missing a non-empty `fact` OR a non-empty `source`, so an
  uncited number can never reach an email. Returns `[]` on junk/non-JSON.
- `_format_cited_stats_block(stats) -> str` (pure): renders the
  prompt-injection block. Non-empty: a "VERIFIED MARKET STATS (use ONLY
  these, each closed with 'Source: <source>', invent no other numbers)"
  header followed by each "fact (Source: source)" line. Empty: an
  instruction to write Email 2 and Email 4 with qualitative market
  observations and NO specific figures.
- `_fetch_cited_market_stats(role, location, industry) -> list`: orchestrates
  one `_safe_web_search_tool` call via `_claude_create_with_retry`, then
  `_parse_cited_stats`. Returns `[]` on any failure (no API key, search
  error, parse failure) so the campaign build never blocks or crashes.

### Wiring
- In the 4×4 build path (the AICB campaign worker), only when
  `(s.aicb_camp_type or "").strip() == "fourbyfour"`, call
  `_fetch_cited_market_stats(...)` before the `campaign_prompt` is
  assembled. Derive role from the first selected role / `cpc_ad_role`,
  location from `cpc_ad_location` / company, industry from the niche /
  research brief (best-available values at the call site).
- Inject `_format_cited_stats_block(stats)`, wrapped via `_wrap_untrusted`
  (web results are untrusted), into `campaign_prompt`.
- Add `payscale.com` to `_WEB_SEARCH_DOMAINS` for comp data. (Do NOT add
  known ClaudeBot-blocked publishers per the existing warning comment.)

### Rendering / anti-AI consistency
Generated emails continue through `_humanize_email_text` + `_strip_dashes`,
so the stat and "Source:" lines remain dash-free and human. Source labels
must not contain em/en dashes (the parser will scrub them via existing
helpers if needed).

## Data flow
1. 4×4 build starts → research runs as today.
2. If 4×4: `_fetch_cited_market_stats(role, location, industry)` →
   `[{fact, source}, ...]` (or `[]`).
3. `_format_cited_stats_block(stats)` → prompt block, wrapped untrusted,
   appended into `campaign_prompt`.
4. Model writes Email 2 + Email 4 using only those facts, each with its
   "Source:" line; other emails unaffected.
5. Post-process humanizer/scrubber run as today.

## Error handling
- Any failure in the fetch path returns `[]`. The empty-state block then
  forbids numbers, so the emails degrade to qualitative observations with
  zero fabrication. Build proceeds.
- Validation in `_parse_cited_stats` guarantees every surfaced fact carries
  a source.

## Testing
- `_cited_stats_prompt`: output contains the role, location, industry, the
  JSON shape token (`"fact"` and `"source"`), and a no-fabrication phrase.
- `_parse_cited_stats`:
  - valid JSON list of `{fact, source}` → same cleaned list.
  - entry with empty `fact` or missing `source` → dropped.
  - response wrapped in ```json fences → parsed.
  - non-JSON / empty string → `[]`.
- `_format_cited_stats_block`:
  - non-empty list → contains each fact, each source, and "use ONLY these".
  - empty list → contains the "no specific figures" instruction and no
    "Source:" header.
- `_WEB_SEARCH_DOMAINS` includes `payscale.com`.

## Out of scope
- Caching the live results (per the chosen approach).
- Applying cited stats to non-4×4 campaign types.
- Salary/comp deep-sourcing beyond the single search call.
- Hyperlinked citations (plain "Source: <publisher>, <year>" text only).

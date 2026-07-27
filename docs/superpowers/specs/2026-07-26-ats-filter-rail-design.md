# Pipeline (ATS) filter rail — design

## Problem

The Pipeline tab's Candidates search already behaves like a real ATS under the
hood — keyword search, "Match a Job Description" AI matching, distance/radius
search, and AI fit-scoring are all live in `_view_candidates` / `ats.py`. What
it's missing is a way to narrow a result set by facet, the way any modern ATS
search does. An unfinished static mockup (`_preview_ats_redesign.html`) shows
the target direction: a left-hand filter rail with checkbox facets and live
counts, sitting next to the existing candidate list and résumé preview.

## Scope (v1)

Two facets: **Role family** and **Industry**. Both are derived from data
already computed cleanly today (`_role_family(title)`, `_industry_of(title,
skills)`) — no new AI extraction, no schema changes, no backfill required.

Explicitly out of scope for v1 (may be later phases): Seniority (needs
normalization first — free-text field with near-duplicate values like
`Mid-Level`/`mid-level`), Skills (free-text, needs tokenization), Last-updated
facet, and any visual redesign of the candidate rows or résumé pane — those
stay exactly as they are today.

## Layout & placement

`_view_candidates`'s existing flex row (`list flex:0 0 600px` + `résumé
flex:1`) gains a new sibling column inserted first:

```
[ rail  flex:0 0 200px ] [ list  flex:0 0 600px ] [ résumé  flex:1 ]
```

The rail matches the other two columns' sizing pattern (`height:{_pane_h}`,
`overflow-y:auto`) so it scrolls independently. It only renders when `rows`
is non-empty — same guard the list itself uses — so it's absent on the
empty-state screens (no results, empty tearsheet, etc).

## Facet computation

Both facet groups are computed once per render pass, over `rows` **before**
the new facet filter is applied (i.e., after search/scope/email-only
filtering, but before facet narrowing). This is a `collections.Counter` over
`_role_family(r["current_title"])` and `_industry_of(r["current_title"],
r["skills"])` for each row. Counts reflect "what selecting this would give
you," not a shrinking total as more facets are picked — matching the
mockup's count-badge style (`142`, `311`, etc).

Each group renders as a checkbox list sorted by count descending. Groups
with only one distinct value are still shown — no hide-if-trivial logic,
keeps behavior predictable and simple.

## State & filtering semantics

Two new keys on the existing page state dict:

- `st["facet_role"]` — a `set()` of selected role-family values
- `st["facet_industry"]` — a `set()` of selected industry values

An empty set means "no filter on that facet." Clicking a checkbox toggles
membership in the corresponding set and calls `refresh()`.

Filtering logic is standard faceted search: **OR within a group** (selecting
"Sales" and "Engineering" under Role family matches either), **AND across
groups** (if both Role family and Industry have selections, a candidate must
match both). This is a pure Python filter step applied to `rows` immediately
before the existing `_candidate_rows(C, st, refresh, rows, terms)` call —
`_candidate_rows` itself is not modified.

## Interaction with existing modes

The rail is agnostic to how `rows` was populated — it works identically
whether `rows` came from `recent()`, `keyword_search`, or `jd_search`. It
also applies inside tearsheet view, filtering the tearsheet's member list
the same way.

Facet selections reset (both sets cleared back to empty) whenever a *new*
search is run — a new keyword query, a new JD match, or a scope/tearsheet
change — so stale facets from a previous search can't silently hide results
from a new one. This mirrors the existing reset behavior for `st["preview"]`.

## Testing

The facet-count computation and the facet-filter function are both pure
functions (rows + selections in, filtered rows / counts out) — testable
without touching NiceGUI rendering, consistent with how `_role_family` and
`_industry_of` are already tested today. No new SQL/FTS code paths are
introduced, so no database-level tests are needed.

## Non-goals

- No changes to `keyword_search`, `jd_search`, `score_results`, or any FTS
  query — filtering happens entirely in Python over already-fetched rows.
- No changes to `_candidate_rows` or `_resume_preview` rendering.
- No lat/lng backfill, no seniority normalization — those are prerequisites
  for later facets, not this pass.

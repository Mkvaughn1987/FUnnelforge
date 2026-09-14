# Candidate alias + Ref # (find the real person behind a spotlight)

Date: 2026-09-14 · Status: approved (Mike, "Approve as written")

## Problem

5x3/5x5 spotlights anonymize candidates as "Aaron M." / "Ben T." / "Carlos R.",
derived from the slot letter. The same alias is reused for different people in
every campaign, pinned (MCP/Cowork) cards have no link to a Pipeline record,
Cowork candidates are never imported, and every build overwrites a shared
`Resume_Candidate_A_Redacted.pdf`. When a client replies "tell me more about
Aaron M." nobody can tell who that is without grepping transcripts.

## Decisions

- Each real candidate gets a **unique, stable alias** plus a **Ref #**.
- Candidates on a card that are not yet in the Pipeline are **auto-added**.
- Synthetic fill cards (`_synthetic`) stay as they are, with no ref.

## Design

### 1. Identity (ats.py)
- New column `talents.client_alias TEXT`; unique index on
  `(owner_email, client_alias)` (partial: non-null only).
- `ensure_client_alias(tid)` returns the stored alias, or mints one: a curated
  first name + random last initial ("Trent K."), retried until unique for the
  owner, never the candidate's real first name. Stable once minted.
- Ref # = the talent id, rendered `Ref #1042`.
- `upsert_card_record(record, owner, added_by)` -> talent id. Dedupes by
  `external_id`, then `_find_owner_dup` (email, then name+state); otherwise
  inserts via the same path as `ingest_records`.

### 2. Card linking (flowdrip_app.py)
`_link_candidate_cards(cards, owner)` runs before generation in
`_api_create_campaign_blocking` (API + MCP) and in the wizard's generation
path. Per card:
- `_pool_id` / `_ats_id` -> load that record.
- identity (name + email or phone) -> `upsert_card_record`, get id.
- `_synthetic` -> unchanged, no ref.
- real card with neither -> passes through unchanged (no ref); the API response
  lists it in `candidate_warnings`. (Changed from the approved 400 during
  build: CandidateBlast and the denver-construction-bd-weekly routine send
  pre-anonymized cards, and a 400 would have stopped those campaigns.)
- a bad `_pool_id` or an identity that can't be added -> 400 on the API/MCP;
  the wizard and sales runs pass that card through instead.
Linked cards get `alias` and `ref`; real name/contact fields are stripped
before the prompt is built. Accounts without Pipeline access are untouched:
nothing is linked, added or rejected.

### 3. Prompts
Both fivebyfive and fivebythree GLOBAL VOICE blocks: use the card's alias
verbatim, written `Trent K. (Ref #1042)` on first mention in each email. The
"use the real first name if the highlights provide one" rule is removed.
A post-generation pass (`_ensure_candidate_refs_in_emails`) inserts
` (Ref #N)` after the first alias mention in an email if the model dropped it.
Cards without a ref keep today's slot-alias behaviour.

### 4. Lookup
- Saved campaign JSON gets `candidate_refs: [{slot, alias, ref, talent_id}]`.
- Campaign detail page (`p_seq_mgr`) shows a "Candidates" panel above the email
  sequence: alias · Ref # · real name, clickable through to the record.
- `ats.keyword_search` recognises `1042`, `#1042`, `ref 1042`, `Ref #1042` and
  exact aliases; matches are prepended to FTS results, deduped by id. This
  covers the Pipeline page, API, MCP and pickers.

### 5. PDFs
Header `Trent K. · Ref #1042`; filename `Resume_Ref1042_Redacted.pdf`. Unique
per person, which also fixes the shared-filename overwrite.

### 6. Existing campaigns
No rewrite of sent or queued emails.

### 7. Skills / MCP
`create_campaign` docstring and the CandidateBlast / PipelineBlast skills send
identity fields (`name`, `email`/`phone`, `resume_text`, optional
`external_id`) on each card.

## Tests
Alias uniqueness + stability; the four card-linking branches incl. dedupe on
repeat use; ref post-pass; search by ref and by alias; unique PDF filenames.
Baseline: 15 pre-existing failures.

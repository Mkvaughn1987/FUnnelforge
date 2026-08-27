# MCP: Pipeline-wide candidates + campaign styles discovery

Date: 2026-08-27
Branch: `feat/mcp-pipeline-and-campaign-styles` (worktree off `main` @ `ed8c3a6a`)

## Summary

Two independent, additive-to-the-API changes to the DripDrop MCP connector:

1. **Retire "Top Candidates."** Delete the legacy per-user `candidate_pool.json`
   feature entirely and repoint every candidate-related API route (and the MCP
   tools built on them) at the existing ATS/Pipeline system (`ats.py`,
   `talents` table), which already supports team-wide (all-users) queries.
2. **Campaign styles discovery.** Add two new read-only MCP tools so a caller
   can see what campaign styles exist before calling `create_campaign`: the
   10 built-in templates, and their own saved custom "My Campaign Styles."

## Feature 1: Top Candidates → Pipeline

### Decisions (confirmed with user)

- Full removal now, not a deprecation window.
- Pool data is disposable — no migration of pool-only candidates into `ats.db`.
- No new tenant/scoping column. Reuse the existing `_ats_allowed(email)`
  allowlist gate (currently UI-only) at the API layer instead of building
  real per-tenant scoping. Team-wide search stays team-wide for allowed users,
  same as the in-app "Search my ATS/Pipeline" picker already behaves today.

### API changes (`flowdrip_app.py`)

- `GET /api/v1/candidates/search?q=&limit=` — **new** route. Auth via
  `_resolve_api_key`, then `_ats_allowed(caller_email)` gate (403 if not
  allowed). Calls `ats.keyword_search(q, owner=None, limit=limit)`. Returns
  the same JSON shape `candidates_search` (MCP tool) already promises today
  (id, name, role, status, etc. per `ats.py` row → dict mapping) — this route
  is genuinely new since the old `candidates_search` client method targeted a
  route that never existed server-side (dead code, confirmed during
  investigation).
- `GET /api/v1/candidates/count` — repoint from pool count to
  `{"total": ats.total_count(owner=None)}`. Add `_ats_allowed` gate. Dropping
  the old active/placed/on_hold buckets: verified `ats.py`'s `talents` table
  has no such status concept (its `status` column just defaults to
  `"Candidate"` and isn't bucketed anywhere in `ats.py`) — inventing buckets
  that don't reflect real data would be worse than a flat total.
- `POST /api/v1/candidates/import` — repoint from the pool-writing
  `_import_one_resume`/`add_candidate_to_pool` path to
  `ats.ingest_resumes(files=[(filename, bytes), ...], owner_email=<caller's
  email>, added_by=<caller's email>)`, called directly on the uploaded bytes
  (verified `ingest_resumes` takes `(filename, bytes)` tuples in memory — no
  temp file needed, simpler than today's write-to-disk-then-parse flow). Add
  `_ats_allowed` gate. Map the returned `stats`/`file_results` (added/merged/
  dup/junk/scanned/error, per-file status) into the existing response shape
  (`requested`, `added`, `updated`, `skipped`, `results`) — `merged`+`dup`
  count as `updated`/`skipped` respectively to preserve the response
  contract external callers already depend on. Ingested candidates land
  owned by the importing caller; existing per-owner dedup/merge semantics in
  `ats.ingest_resumes` apply unchanged.

### Deletions (`flowdrip_app.py`)

- `load_candidate_pool`, `save_candidate_pool`, `add_candidate_to_pool`,
  `update_candidate_in_pool`, `remove_candidate_from_pool`.
- `_import_one_resume` — pool-specific (docstring: "append it to the CURRENT
  user's candidate pool"), shared only by the "Bulk Import Resumes" UI
  worker (part of the deleted `p_candidate_finder` page) and the old
  `/api/v1/candidates/import` implementation. Becomes fully dead once both
  callers are gone.
- `p_candidate_finder` page (the "Top Candidates" UI page) and its route
  registration/nav entry.
- `_render_aicb_pool_picker` and the wizard's "pool" card; the wizard keeps
  only the existing "🔍 Search my ATS/Pipeline" card
  (`_render_aicb_ats_picker`) as its sole candidate picker.
- Manual 5×3 slate builder's pool-based "add candidate" dialog
  (`cpc_candidates`) — repointed to call the ATS picker instead of
  `load_candidate_pool()`.
- Orphaned `candidate_pool.json` files are left on disk untouched (no
  migration, no cleanup job — disposable per the confirmed decision).

Anything already ATS-backed is left alone: `_pool_record_by_id` (already
migrated, per its own docstring, to `ats.get_one`), `_api_resolve_5x3_cards`,
`_match_pipeline_to_company`, `_ats_owner_candidates`, `_build_slate_cards`.

### MCP changes (`mcp_server/dripdrop_mcp.py`, `mcp_server/dripdrop_client.py`)

- `candidates_search(q, status, limit)` — description updated to describe the
  team-wide Pipeline/ATS instead of "Top Candidates pool"; client method
  repointed at the new `GET /api/v1/candidates/search`.
- `candidates_count()` — description updated; unchanged route path
  (`/api/v1/candidates/count`), now backed by ATS counts.
- `import_candidates(files)` — description updated to say candidates are
  ingested into the shared Pipeline, owned by the caller.

### Downstream consumer

- `~/.claude/skills/candidateblast/references/candidate-intake.md` (lines
  12-31) currently reads `%LOCALAPPDATA%\DripDrop\candidate_pool.json`
  directly off disk to resolve a candidate name into résumé text. This bypass
  breaks once the pool is deleted. Update it to call the `candidates_search`
  MCP tool (search by name) against the Pipeline instead.

### Testing

- Delete/adapt tests that assert on pool CRUD functions or the
  `p_candidate_finder` page.
- New tests for `GET /api/v1/candidates/search`: allowed caller gets
  team-wide results; disallowed caller gets 403; empty query behaves
  sanely (matches existing `keyword_search` contract).
- New/updated tests for `/api/v1/candidates/count` (ATS-backed counts) and
  `/api/v1/candidates/import` (owner-scoped ingest via `ats.ingest_resumes`,
  gated by `_ats_allowed`).
- Per repo convention: test raw `@app.get/@app.post` handlers by mounting
  just that function on a bare `Starlette(routes=[...])`, never
  `TestClient(fa.app)` directly (poisons the whole suite via NiceGUI
  lifespan).

## Feature 2: Campaign styles discovery

Two new read-only MCP tools, no changes to `create_campaign` itself (wiring a
custom BYOS description into `create_campaign` is a separate, pre-existing
gap and explicitly out of scope here).

### API changes (`flowdrip_app.py`)

- `GET /api/v1/campaign_types` — **new** route. Auth via `_resolve_api_key`
  only (no `_ats_allowed` gate — these are global, non-sensitive built-in
  template definitions, same as what any logged-in user already sees in the
  wizard). Serializes `AICB_CAMPAIGN_TYPES` to JSON: for each of the 10
  entries, `{key, display_name, description, best_for}` (drop internal-only
  fields — `meta`, `color`, `step_script` — that don't serialize meaningfully
  or shouldn't be exposed as API surface).
- `GET /api/v1/campaign_styles` — **new** route. Auth via `_resolve_api_key`.
  `_load_my_campaign_styles()` takes no args and reads from whichever user's
  paths are currently bound — so the route must bind tenancy first
  (`_CURRENT_USER_EMAIL.set(owner)` + `_switch_to_user_paths(owner)`, the
  exact pattern the existing `/api/v1/candidates/count` route already uses)
  before calling it. Returns the caller's own saved custom BYOS style
  records (`{id, name, description, created_at}`), never another user's.

### MCP changes

- `campaign_types()` — new tool, no args, lists the 10 built-in campaign
  styles/templates with their keys and descriptions (so a caller knows what
  `template` values `create_campaign` accepts and what each does).
- `my_campaign_styles()` — new tool, no args, lists the calling user's own
  saved custom "My Campaign Styles" (BYOS descriptions).
- Corresponding client methods added to `dripdrop_client.py` following the
  existing `resolve_user_api_key` → HTTP GET pattern used by
  `candidates_count`.

### Testing

- New tests for both routes: `campaign_types` returns exactly the 10 known
  keys with non-empty descriptions; `campaign_styles` returns only the
  calling user's own saved styles (not another user's), and an empty list
  for a user with none saved.

## Out of scope

- Wiring a custom BYOS description into `create_campaign`'s `byos` template
  path (pre-existing gap, separate work).
- Real per-tenant data scoping/column on `ats.py`'s `talents` table (relying
  on the existing `_ats_allowed` gate instead, per confirmed decision).
- Migrating any existing pool-only candidate data into `ats.db`.
- Updating the DripDropAPI skill's own documentation — flagged as a
  worthwhile follow-up but not required for this change to be correct;
  will update opportunistically if time allows during implementation.

## Rollout

- Implement on this worktree/branch with TDD, run the full suite, compare
  the failing set against the established baseline (`606 passed, 6 failed`
  as of this branch's creation — the 6 are pre-existing/unrelated: 5 known
  flaky tests plus `test_5x3.py::test_build_resumes_from_cards_5x3_representative`,
  a pre-existing PDF-text-content mismatch unrelated to candidate storage).
- Deploy per the established scoped single-file deploy playbook (backup,
  git-blob-hash verification, blue/green flip). Given the current known
  **prod drift** on `flowdrip_app.py` (prod is running an uncommitted
  dashboard-activity-panel WIP hunk not present in any git commit as of
  2026-08-27), the deploy step must re-verify prod's actual live file content
  before pushing — not assume `main`/this branch matches prod — and patch
  prod's real running content rather than overwriting it with a clean
  git-branch version, per the corrected recipe in the deploy-drift memory.
- Restart `dripdrop-mcp.service` after the MCP-side files are deployed (no
  dedicated deploy script exists for that service; manual scp + backup +
  restart, per prior MCP deploys).

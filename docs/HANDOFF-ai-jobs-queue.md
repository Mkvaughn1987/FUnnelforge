# HANDOFF: "Send to my AI" job queue + ZoomInfo rule in every prompt

Paused 2026-10-02 mid-build. Worktree `C:\Users\mkvau\ff-wt\zi-fallback`, branch `feat/zoominfo-fallback-worker`.

## Already live on DripDrop prod (commit 9020964, deployed 2026-10-02)
- ZoomInfo pull rule: connector Bulk Credits first, then the user's Talent seat (recruiter-app.zoominfo.com in Chrome). Board order: Google Jobs, LinkedIn Jobs, Indeed, ZipRecruiter.
- Sales Campaign parking: retry every 2 days, dropped after 4 tries.
- AI Prompts tile "Work my Sales Campaigns automatically" (routine `sc_worker`) and the one-time setup pop-up.
- See memory `dripdrop-zoominfo-fallback-worker.md`.

## What Mike asked for next (approved: "Queue it, no pasting")
1. **Every AI Prompts job is worked automatically.**
   - The result screen gets a primary **Send to my AI** button; Copy stays as a secondary button.
   - Send queues the job in DripDrop, the user's hourly worker picks it up, runs it unattended and posts the result back.
   - The separate `sc_worker` tile goes away. Its setup prompt lives in the pop-up and in a "Your AI" panel at the top of step 1.
2. **Every prompt carries the ZoomInfo pull rule.**
   - Today these lack it: `staff_account`, `linkedin_touches`, `other`, plus the hidden routines `campaign_report`, `find_candidates`, `load_candidates`, `research` and `launch_campaign`.

## Done, uncommitted
- **`ai_jobs.py` (NEW, written):**
  - Per-user store under `<user root>/AIJobs/`.
  - Functions: `queue_job(owner, title, prompt, routine, repeat)`, `pending(owner)`, `update_job`, `cancel_job`, `list_jobs`.
  - Repeats: DripDrop queues the next copy itself via `next_due` / `_spawn_repeats`, using a tz map.
  - `touch_worker` / `worker_last_seen` back the check-in.
  - The `POST_BACK` block is appended to each job's instructions and tells the AI to call `sales_run_update` with `run_id` = `job_...`.
- **`sales_campaign.py` (edited):**
  - `_run_summary` adds `"kind": "sales_campaign"`.
  - `pending_runs` calls `ai_jobs.touch_worker`, then appends `ai_jobs.pending(owner)[:10]`.
  - `claim_run` and `update_run` dispatch any `job_` run_id to `ai_jobs.update_job`.
  - Bug fix: `claim_run` never saved the "working" status; it now calls `save_run`.
  - Result: no `flowdrip_app.py` or `dripdrop_client.py` change is needed. The existing `sales_runs_pending` / `sales_run_update` routes and MCP tools carry the jobs.

## Still to do
1. **`ai_prompts.py` edits** (the scripted edit failed on a bash heredoc quote; write the script with the Write tool instead):
   - `Catalogue` gets two fields: `zi_rule: str = ""` and `queue_jobs: bool = False`. `ARENA` sets `zi_rule=ZI_PULL_RULE, queue_jobs=True`. STAFFING inherits them through `dataclasses.replace`; tm_prompts stays off.
   - **`build_prompt`, queued mode** (`queued = bool(req.get("queued"))`):
     - Forces `solo`.
     - Open questions become "make the most reasonable call and say what you chose".
     - Skips the "THEN MAKE IT REPEAT" section.
     - The final ambiguity line becomes "make the most reasonable call".
   - **`build_prompt`, ZoomInfo section:** after the steps, if `cat.zi_rule` is not already in the whitespace-normalised text, add a "ZOOMINFO" section: "Any time this job needs a person - the right people at a company, or someone's email or phone number - get them from ZoomInfo, not from guesswork. " + rule.
   - **`staff_account` in `staffing_prompts.py`:** replace "No emails needed yet." with an explicit contact pull + `ZI_PULL_RULE`.
   - **`sc_worker` routine wording:**
     - Name: "Let my AI work my DripDrop jobs automatically".
     - Task name: "DripDrop - job worker".
     - Steps: say "every job I send it - AI Prompts jobs and Sales Campaign runs"; claim each run with status working; drop the "Nothing it does sends email" line, since queued jobs can launch campaigns.
   - Remove the `sc_worker` entry from `STARTERS`; keep the routine.
   - **Result screen:** when `_CAT.queue_jobs`, add a primary "Send to my AI" button that calls `_aip_send(s, rf, req)`.
     - `_aip_send` builds `build_prompt(dict(req, queued=True))`.
     - Title is `r["name"]` + " - " + location/company.
     - Repeat comes from `_repeat_spec(r, vals)`, mapped through `CADENCE_LEGACY`.
     - It calls `ai_jobs.queue_job`, resets to step 1 and notifies. If the worker has not checked in within 3 days, it opens `sales_campaign.zi_setup_dialog(s)`.
   - **New `_aip_jobs_panel(s, rf, C)` on step 1** (in `render_page` when `cat.queue_jobs`):
     - Worker status: checked in X ago / last seen / not set up, with a "Set it up" button.
     - The last 8 jobs: status pill, age, repeat text, a Cancel button, and an expansion showing the result or error.
   - New `worker_prompt(cat)` helper builds the `sc_worker` prompt with its defaults.
2. **`sales_campaign.zi_setup_steps`:**
   - Step 4 now says to run a tile that no longer exists. Replace it with a "Copy the setup prompt" button: `ai_prompts.worker_prompt(staffing_prompts.STAFFING)`, then paste it into the desktop AI app once.
   - Retitle the dialog "One-time setup so your AI can work DripDrop jobs".
3. **`mcp_server/dripdrop_mcp.py`:** the docstrings for `sales_runs_pending` / `sales_run_update` should mention AI Prompts jobs: `kind`, `job_` run_ids, and a `result` field with status `done`.
4. **Tests:**
   - Add to `tests/test_zoominfo_pull.py`: every STAFFING routine's prompt contains `ZI_PULL_RULE`; the queued prompt has no "wait for me" or repeat section; `ai_jobs` queue/pending/update/cancel, the repeat spawn and `next_due`; dispatch of `job_` ids through `sc.update_run` / `claim_run`; `pending_runs` merges jobs and touches the worker.
   - Regenerate `tests/fixtures/ai_prompts_golden.json` with `indent=1, ensure_ascii=False`, plus a trailing newline.
   - Prompts must never name an assistant (`test_no_prompt_names_an_assistant`).
5. **Full suite:** the prod base has 8 pre-existing failures (listed in memory). Compare against those, not zero.
6. **Commit, then deploy** with the pattern in the scratchpad `zi/deploy_zi.sh`:
   - Drift-check against the hashes now live: ai_prompts a22e20a, staffing_prompts 1b91e2b, sales_campaign 79ab516, dripdrop_mcp daf2f74, zoominfo_pull 6da7479.
   - Add `ai_jobs.py` as a new file.
   - Restart green, then blue, then `dripdrop-mcp`.
7. **Open question for Mike:** the stale run `sc_20260907_214000_29e0` (CO Commercial Construction, stuck "working"). Cancel it or use it as the supervised test?

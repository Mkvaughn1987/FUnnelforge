# Task 8 — Thread spawn audit

Date: 2026-05-09
Total spawn sites found: 46
Already migrated: 2 (bulk-import `_run_as_user` at L32304, candidate-finder Search `_run_as_user` at L33431 — these use `_run_as_user` so they do NOT appear in the `threading.Thread(target=...)` grep)
Need migration (MIGRATE): 16
System threads (SYSTEM): 5
Read-only (READ_ONLY): 25

---

## MIGRATE — per-user write threads

| Line | Spawn line | Worker fn | Reaches | Suggested name= |
|---|---|---|---|---|
| L5388 | `self._thread = threading.Thread(target=self._loop, daemon=True)` | `CandidatePoolScanner._loop` | `update_candidate_in_pool` → `save_candidate_pool` → `_user_candidate_pool_path()` — runs without any user binding in server mode, causing LEAK_GUARD warnings | `pool_scanner_worker` |
| L6954 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (in `_teach_ai_from_edit`) | `save_config` → `_user_config_path()` | `teach_ai_style_worker` |
| L10299 | `_t = _th.Thread(target=_run, daemon=True)` | `_run` (in `_do_requeue`) | `requeue_campaign` → `_user_queue_path()` | `requeue_campaign_worker` |
| L10731 | `_thr.Thread(target=_bg, daemon=True).start()` | `_bg` (in `_render_call_briefing_card`) | `_generate_call_briefing_for_campaign` → `save_campaign` → `_user_campaigns_dir()` | `call_briefing_gen_worker` |
| L10780 | `_thr2.Thread(target=_bg_refresh, daemon=True).start()` | `_bg_refresh` (call briefing Refresh button) | `_generate_call_briefing_for_campaign` → `save_campaign` → `_user_campaigns_dir()` | `call_briefing_refresh_worker` |
| L11049 | `_thr.Thread(target=_bg, daemon=True).start()` | `_bg` (in `_render_li_message_card`) | `_generate_li_message_for_campaign` → `save_campaign` → `_user_campaigns_dir()` | `li_message_gen_worker` |
| L12497 | `threading.Thread(target=_do_send, daemon=True).start()` | `_do_send` (reply Send via Outlook) | `save_responded` → `_user_responded_json()` | `reply_send_worker` |
| L13651 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (in `_gen_pdf_inline`) | `_user_pdf_dir()`, `_save_pdf_sidecar`, `save_campaign` | `pdf_inline_gen_worker` |
| L19978 | `_thr.Thread(target=_gen_first_issue, daemon=True).start()` | `_gen_first_issue` | `_gen_all_issues_for_campaign` → `save_campaign` → `_user_campaigns_dir()` | `newsletter_first_issue_worker` |
| L25318 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (in `_do_save` PDF editor) | `_rebuild_pdf_from_sidecar_data` → `_user_pdf_dir()` | `pdf_editor_save_worker` |
| L29715 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (AICB main generation) | `_aicb_attach_pdfs` → `_user_pdf_dir()`; `save_campaign` → `_user_campaigns_dir()` | `aicb_campaign_gen_worker` |
| L30796 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (custom PDF Generate from outline) | writes to `_pdf_dir` (= `_user_pdf_dir()` snapshot), `_save_pdf_sidecar`, `_publish_pdf` | `custom_pdf_gen_worker` |
| L31143 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (PDF gen page tile click) | writes to `_pdf_dir` (= `_user_pdf_dir()` snapshot), `_save_pdf_sidecar`, `_publish_pdf` | `pdfgen_page_worker` |
| L32771 | `threading.Thread(target=_worker, daemon=True).start()` | `_worker` (candidate highlights gen) | `update_candidate_in_pool` → `save_candidate_pool` → `_user_candidate_pool_path()` | `candidate_highlights_worker` |
| L39233 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (market intel scan) | `_save_mi_results` → `_user_mi_results_path()`; `_save_mi_watches` → `_user_mi_path()` | `market_intel_scan_worker` |
| L40813 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (company profile auto-fill) | `_save_company_profile` → `save_config` → `_user_config_path()` | `company_autofill_worker` |

---

## SYSTEM — long-running app-level threads (no user binding)

| Line | Spawn line | Worker fn | Why system |
|---|---|---|---|
| L5186 | `self._thread = threading.Thread(target=self._loop, daemon=True)` | `OutlookMonitor._loop` | Desktop-mode only Outlook inbox monitor (`_SERVER_MODE=False`); single-user, no per-user ContextVar needed. Class instance started once at app boot. |
| L5199 | `threading.Thread(target=self._scan, daemon=True).start()` | `OutlookMonitor._scan` | Desktop-mode on-demand scan (same class); single-user. Calls `add_responded`/`add_to_dnc` which resolve to the single base data dir in desktop mode. |
| L12314 | `threading.Thread(target=_run, daemon=True).start()` | `_run` → `_one_user_reply_scan` | Uses explicit `user_dir` path construction (not `_user_*` ContextVar helpers); safe to call from any context because the email is passed as an explicit arg. No `_run_as_user` needed — the helper resolves paths by building `_BASE_DATA_DIR / "users" / safe` directly. |
| L44295 | `t = threading.Thread(target=_loop, daemon=True, name="ServerEmailScheduler")` | `_loop` (ServerEmailScheduler) | App boot scheduler; processes ALL users' send queues in one loop by iterating `users_dir.iterdir()`. No single owning user. |
| L44728 | `t = threading.Thread(target=_loop, daemon=True, name="ServerReplyMonitor")` | `_loop` (ServerReplyMonitor) | App boot monitor; scans ALL users' inboxes via `_server_reply_monitor_tick()`. No single owning user. |

---

## READ_ONLY — no per-user writes

| Line | Spawn line | Worker fn | Notes |
|---|---|---|---|
| L7057 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (in `_ai_assist_email`) | Claude Haiku rewrite; only calls `body_area.set_value(result)`. No file writes. |
| L12544 | `threading.Thread(target=_gen2, daemon=True).start()` | `_gen2` (reply AI regen) | Claude Haiku draft; only sets `s._draft_replies[e]`. No file writes. |
| L12618 | `threading.Thread(target=_gen, daemon=True).start()` | `_gen` (reply AI draft) | Claude Haiku draft; reads `_user_sig_path()` (read-only) for sender name, sets `s._draft_replies[e]`. No writes. |
| L13787 | `threading.Thread(target=_send, daemon=True).start()` | `_send` (email step preview) | Calls `_send_email_universal(..., is_preview=True)`. Sends email; no per-user file writes in the bg thread. |
| L20369 | `_thr.Thread(target=_bg, daemon=True).start()` | `_bg` (newsletter modal gen) | Calls `_generate_newsletter_content_for_step` (AI only); sets `state["subject"]`/`state["body"]` + calls `_body_editor.set_value`. No file writes. |
| L20431 | `threading.Thread(target=_send_prev_bg, daemon=True).start()` | `_send_prev_bg` (newsletter preview) | `_send_email_universal(..., is_preview=True)`. No file writes. |
| L25065 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (PDF AI revise) | `_ai_revise_pdf_data` → Claude Haiku; sets `s._pdf_editor_data[k]`. No file writes. |
| L26485 | `_thr.Thread(target=_run, daemon=True).start()` | `_run` (AICB AI extract) | Claude extraction; calls `_aicb_apply_extracted(s, data)` which only sets AppState fields. No file writes. |
| L27215 | `_thr.Thread(target=_bg, daemon=True).start()` | `_bg` (AICB auto-fill target) | `_aicb_auto_fill_run(s)` → web search; sets `s.aicb_*` state fields only. No file writes. |
| L27297 | `_thr.Thread(target=_bg, daemon=True).start()` | `_bg` (AICB suggest titles) | `_aicb_suggest_titles_run(s)` → web search; appends to `s.aicb_sel_roles`. No file writes. |
| L27334 | `_thr.Thread(target=_bg, daemon=True).start()` | `_bg` (AICB auto-gen candidates) | `_aicb_generate_candidates_run(s, count)` → Claude; sets `s._aicb_cand_text`, `s.aicb_cand_cards`. No file writes. |
| L27608 | `_thr.Thread(target=_bg, daemon=True).start()` | `_bg` (AICB combined titles+candidates) | Calls `_aicb_suggest_titles_run` + `_aicb_generate_candidates_run`; sets AppState only. No file writes. |
| L27761 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (AICB contact upload AI analysis) | `_analyze_contacts_with_ai(rows)` → Claude; sets `s.aicb_*` fields. No file writes. |
| L29278 | `_thr_pdf.Thread(target=_pdf_data_worker, daemon=True).start()` | `_pdf_data_worker` (AICB parallel PDF AI data) | `_aicb_generate_pdf_data(...)` → Claude; stores result in `_pdf_data_holder["data"]` dict. No file writes (build/attach happens in the email thread after `_pdf_data_event.wait`). |
| L30528 | `threading.Thread(target=_run_outline, daemon=True).start()` | `_run_outline` (custom PDF outline preview) | Claude Haiku; sets `s._pdf_custom_outline`. No file writes. |
| L31510 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (candidate placement campaign gen) | Claude Haiku; sets `s.cpc_campaign` and `s.cpc_step`. No file writes. |
| L32004 | `threading.Thread(target=_do_match, daemon=True).start()` | `_do_match` (JD matcher) | Claude Sonnet; sets `s.cf_jd_matches`, `s.cf_jd_summary`, etc. No file writes. |
| L32060 | `threading.Thread(target=_do_submittal, daemon=True).start()` | `_do_submittal` (submittal writeup) | Claude Sonnet; sets `s.cf_submittal_html`. No file writes. |
| L33131 | `threading.Thread(target=_extract, daemon=True).start()` | `_extract` (PDF resume extract) | Claude Haiku with base64 PDF; sets `s.cf_resume_text`. No file writes. |
| L33168 | `threading.Thread(target=_auto_fill2, daemon=True).start()` | `_auto_fill2` (resume auto-fill after AI extract) | Claude Haiku; sets `s.cf_candidate_name`, `s.cf_target_role`, `s.cf_location`. No file writes. |
| L33212 | `threading.Thread(target=_auto_fill, daemon=True).start()` | `_auto_fill` (resume auto-fill from text) | Claude Haiku; sets `s.cf_candidate_name`, `s.cf_target_role`, `s.cf_location`. No file writes. |
| L38552 | `threading.Thread(target=_do_send, daemon=True).start()` | `_do_send` (newsletter desktop preview) | `_send_email_universal(..., is_preview=True)`. No file writes. |
| L38593 | `threading.Thread(target=_do_send, daemon=True).start()` | `_do_send` (newsletter desktop send) | Direct Outlook COM send; no per-user file writes in bg thread. Desktop-mode only. |
| L41675 | `threading.Thread(target=_run, daemon=True).start()` | `_run` (recruiting research) | Claude Haiku with web search; sets `s.rc_ai_pitch`, `s.rc_ai_generating`. No file writes. |
| L41997 | `threading.Thread(target=_run_ai, daemon=True).start()` | `_run_ai` (recruiting campaign gen) | Claude Haiku; parses JSON, sets `s.loaded_camp`, `s.rc_step`. No file writes. |

---

## ALREADY_MIGRATED

| Line (current) | Worker fn | Migrated in |
|---|---|---|
| L32304 (`_run_as_user(...)`) | `_worker` (`_bulk_import_resumes`) | Task 3 / commit 9d5addf — does not appear in `threading.Thread(target=...)` grep |
| L33431 (`_run_as_user(...)`) | `_run` (`cf_search_worker` in `p_candidate_finder`) | Task 4 / commit 2a31f84 — does not appear in `threading.Thread(target=...)` grep |

---

## Notes on edge cases

### L5388 CandidatePoolScanner._loop (classified MIGRATE)
The `CandidatePoolScanner` is a background class that runs once at app boot via `pool_scanner = CandidatePoolScanner()`. Its `_loop` calls `update_candidate_in_pool` and `load_candidate_pool` — both of which use `_user_candidate_pool_path()` → `_resolve_user_root()` without any user bound. In server mode this triggers LEAK_GUARD and falls back to `_BASE_DATA_DIR`. The class needs a redesign to iterate all users (like `ServerEmailScheduler`) or be refactored to be user-aware. Classified MIGRATE for now because the per-user write marker `_user_candidate_pool_path` is present. Implementation note: this class may need a different fix than `_run_as_user` (which is per-request) — the next agent should consider making it user-iterating like the server scheduler rather than wrapping in `_run_as_user`.

### L12314 reply scan `_run` (classified SYSTEM)
Calls `_one_user_reply_scan(user_email, ...)` which builds paths as `_BASE_DATA_DIR / "users" / safe / ...` directly — NOT via `_user_*` ContextVar helpers. The user email is passed explicitly, so no ContextVar rebind needed. No leak risk.

### L10731 / L10780 call briefing threads (classified MIGRATE)
Both `_bg` and `_bg_refresh` already rebind `_CURRENT_USER_EMAIL` inside the thread body (via `_CURRENT_USER_EMAIL.set(_user)`). However, they still use raw `threading.Thread` rather than `_run_as_user`, which means if the rebind fails, they silently write to the wrong user's dir. Migrating to `_run_as_user` adds the guaranteed pre-entry rebind and the `_user_email` forced into the thread.

### L29278 AICB PDF data worker (classified READ_ONLY)
`_pdf_data_worker` only stores AI-generated content into a dict (`_pdf_data_holder["data"]`); the actual file writes happen in the email thread (L29715's `_run`) after `_pdf_data_event.wait`. No direct file writes in this worker.

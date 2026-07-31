# Arena 5×5 Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get the Arena 5×5 template live on prod without disturbing the live 4×4 or the `_next_business_day` start-date fix, convert the 21 not-yet-started 4×4 campaigns to full 5×5 (pilot-gated, sends starting 2026-07-22), and make 5×5 the default for the BD skills/routines going forward.

**Architecture:** Two natures of work. **Code tasks** (Tasks 1–2): bring the local repo's start-date behavior in line with prod (`_next_business_day`) under TDD, and confirm the 5×5 code already committed to local `main` is test-green — these produce the reviewed source of truth. **Operational tasks** (Tasks 3–6): surgically port only the 5×5 symbols onto prod's *current* file (preserving `_next_business_day` and self-serve keys), then drive the campaign conversions through the real launch path — `POST http://127.0.0.1:8080/api/v1/campaigns` with `template=fivebyfive`, called from localhost on the prod box — pilot first, then batch, then flip the skills.

**Tech Stack:** Python 3 / NiceGUI monolith (`flowdrip_app.py`, ~55k lines), pytest, blue/green systemd services on the prod box (`dripdrop` :8080 blue = ACTIVE, `dripdrop-green` :8081 inactive), SSH for prod ops, the `.skill` bundles in `~/Downloads` for the cloud routines.

---

## Reference facts (read before starting; verify live during execution)

These come from project memory and this session's exploration. **Memories are point-in-time — verify against the live box before relying on any file:line or path.**

- **Local repo:** `C:\Users\mkvau\OneDrive\Documents\Sales\Python\FunnelForge`, branch `main`, working tree clean w.r.t. `flowdrip_app.py`. Local `main` **already contains** the full 5×5 code (committed) *and* a later 5×3 (`fivebythree`) build. Local `_resolve_start_date` still uses `_upcoming_monday` (Monday default) — it never got `_next_business_day`.
- **Prod file:** `/opt/dripdrop/app/flowdrip_app.py`. Per memory, prod = `feat/self-serve-api-keys` baseline **+ `_next_business_day` shipped/deployed directly to prod 2026-07-20** (backup `flowdrip_app.py.bak.20260720_221724`). Prod has **0** 5×5 campaigns and **no** 5×5 / 5×3 code. **This must be confirmed live in Task 3.**
- **Live color:** blue — `dripdrop.service` on **:8080** is ACTIVE; `dripdrop-green.service` :8081 inactive. (Memory `dripdrop-bd-agents-permission-stall` records the 2026-07-17 flip to blue. Confirm with `systemctl is-active` before deploying.)
- **Prod data dir:** `/opt/dripdrop/data` — set via systemd `Environment=`, **NOT** in `/opt/dripdrop/.env`. Any manual python that touches the queue MUST `export DRIPDROP_DATA_DIR=/opt/dripdrop/data` first, or `_user_queue_path()` silently resolves to the stray `/opt/dripdrop/app/DripDrop/...` and writes go nowhere the scheduler reads.
- **Prod python:** venv `/opt/dripdrop/venv/bin/python` with `PYTHONPATH=/opt/dripdrop/app` (system python lacks `dotenv`). Source `/opt/dripdrop/.env` before importing (module hard-exits if `DRIPDROP_SECRET` unset).
- **Owner slug:** campaigns live under `/opt/dripdrop/data/users/michael_vaughn_at_arenastaffing_net/{Campaigns/*.json, scheduled_queue.json}`. `_owner_email` in each campaign JSON is `michael.vaughn@arenastaffing.net`.
- **CRLF trap (memory `dripdrop-prod-deploy-drift`):** prod's `flowdrip_app.py` uses CRLF. Editing it with a text-mode write flattens to LF and makes the *whole file* look changed (and can defeat rollback diffs). Patch **in binary mode** preserving line endings.
- **Skills:** `denver-bd-pipeline.skill`, `regional-bd-pipeline.skill` in `~/Downloads` were edited 2026-07-20 to next-business-day wording (backups `.skill.bak.*`) but the **default template is still `fourbyfour`**. They must be edited to `fivebyfive` and **re-imported** for cloud routines to pick up changes.

---

## Local anchors (source of truth for the 5×5 port)

These are the exact symbols to port to prod, with their local `main` locations (verify line numbers with grep before slicing — the file shifts):

| Symbol | Local location | Notes |
|---|---|---|
| `_ARENA_SLATE_TYPES` membership | `flowdrip_app.py:4093` | `frozenset({"fourbyfour", "fivebyfive", "fivebythree"})` — prod likely has only `fourbyfour` (or no frozenset). Port must add `fivebyfive` **only** (not `fivebythree`). |
| `fivebyfive` tuple in `AICB_CAMPAIGN_TYPES` | `flowdrip_app.py:4159`–(end of tuple) | The big NL step-prompt tuple. Extract the exact byte range from local `main`. |
| `_FIVEBYFIVE_*` constants | `flowdrip_app.py:8280`–`8292` | `_FIVEBYFIVE_BUMP_SUBJECT`, `_FIVEBYFIVE_BUMP_BODY`, `_FIVEBYFIVE_INTERVIEW_LINE`, `_FIVEBYFIVE_DELAYS = {1:0,2:3,3:0,4:0,5:2,6:3,7:4}` |
| `_fivebyfive_step_no` + `_apply_fivebyfive_overrides` | `flowdrip_app.py:8295`–`8322` | The step-number parser + override stamper. |
| Call site | `flowdrip_app.py:5448` | `_apply_fivebyfive_overrides(camp_type, campaign_data)` — inside `_aicb_build_campaign_from_brief`, right before `_apply_fivebythree_overrides` (which prod won't have — port only the 5×5 call) and `_spread_email_times`. |
| Chooser tile | `flowdrip_app.py:18729`–`18740` | `{"key": "fivebyfive", "icon": "🌱", ...}` dict in the chooser list. |
| Chooser routing | `flowdrip_app.py:18883`–`18899` | `elif k == "fivebyfive":` branch. |

**Important — do NOT port `fivebythree`.** Local `main` interleaves 5×3 code (`_apply_fivebythree_overrides`, `_FIVEBYTHREE_*`, `fivebythree` in the frozenset/routing). That is a separate, un-deployed feature (PipelineBlast/CandidateBlast, on its own branches). This plan ports **only** the `fivebyfive` symbols. When slicing ranges, exclude any `FIVEBYTHREE`/`fivebythree` lines.

---

## Task 1: Sync local start-date behavior to prod (`_next_business_day`) — TDD

Closes **Gap A**: local `main` + `tests/test_campaign_api.py` still assert Monday; prod ships next-business-day. Bring local into line so git matches prod and future full-file operations don't regress the fix.

**Files:**
- Modify: `flowdrip_app.py` (start-date helper block, ~`5095`–`5115`)
- Test: `tests/test_campaign_api.py`

- [ ] **Step 1: Write the failing tests**

Replace the three Monday-asserting tests and update the one comment. Add these tests to `tests/test_campaign_api.py` (adjust the import to match the file's existing style — it already imports the module under test):

```python
from datetime import date
import flowdrip_app as fa


def test_next_business_day_monday_through_thursday_is_tomorrow():
    # Mon 2026-07-20 -> Tue 21; Thu 2026-07-23 -> Fri 24
    assert fa._next_business_day(date(2026, 7, 20)) == date(2026, 7, 21)
    assert fa._next_business_day(date(2026, 7, 23)) == date(2026, 7, 24)


def test_next_business_day_friday_saturday_sunday_is_coming_monday():
    # Fri 2026-07-24, Sat 25, Sun 26 all -> Mon 2026-07-27
    assert fa._next_business_day(date(2026, 7, 24)) == date(2026, 7, 27)
    assert fa._next_business_day(date(2026, 7, 25)) == date(2026, 7, 27)
    assert fa._next_business_day(date(2026, 7, 26)) == date(2026, 7, 27)


def test_resolve_start_date_blank_uses_next_business_day():
    assert fa._resolve_start_date("") == fa._next_business_day().isoformat()


def test_resolve_start_date_sentinel_uses_next_business_day():
    for sentinel in ("auto", "monday", "next_monday", "upcoming_monday"):
        assert fa._resolve_start_date(sentinel) == fa._next_business_day().isoformat()


def test_resolve_start_date_explicit_iso_passes_through():
    assert fa._resolve_start_date("2026-08-15") == "2026-08-15"
```

Then delete the now-superseded old tests if present: `test_resolve_start_date_blank_uses_upcoming_monday`, `test_resolve_start_date_sentinel_uses_upcoming_monday`, `test_route_defaults_start_date_to_upcoming_monday`. For `test_route_defaults_start_date_to_upcoming_monday`, replace its body's expected value with `fa._next_business_day().isoformat()` and rename it to `test_route_defaults_start_date_to_next_business_day` (keep the route-level assertion — it's still valuable). Update the comment in `test_validate_spec_ok_without_start_date` from "upcoming Monday" to "next business day".

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "C:/Users/mkvau/OneDrive/Documents/Sales/Python/FunnelForge" && python -m pytest tests/test_campaign_api.py -k "next_business_day or resolve_start_date" -v`
Expected: FAIL — `AttributeError: module 'flowdrip_app' has no attribute '_next_business_day'`.

- [ ] **Step 3: Implement `_next_business_day` and repoint `_resolve_start_date`**

In `flowdrip_app.py`, in the start-date helper block (just after `_upcoming_monday`, ~line 5105), add:

```python
def _next_business_day(today: date = None) -> date:
    """The next business day AFTER `today`. Mon–Thu -> tomorrow; Fri/Sat/Sun
    -> the coming Monday. Never returns a weekend, and never returns `today`
    itself (a campaign resolved with no explicit date always starts on a
    later business day)."""
    today = today or date.today()
    wd = today.weekday()  # Mon=0 .. Sun=6
    if wd <= 3:            # Mon, Tue, Wed, Thu
        return today + timedelta(days=1)
    return today + timedelta(days=(7 - wd))  # Fri->+3, Sat->+2, Sun->+1 == Monday
```

Then change `_resolve_start_date` to use it (keep `_upcoming_monday` defined but unused for reference parity with prod):

```python
def _resolve_start_date(raw) -> str:
    """Resolve a spec's start_date to an ISO string. Blank/omitted or a
    sentinel ('upcoming_monday', 'next_monday', 'monday', 'auto') defaults to
    the NEXT BUSINESS DAY after today; an explicit ISO date passes through."""
    s = (raw or "").strip()
    if s.lower() in _START_DATE_AUTO:
        return _next_business_day().isoformat()
    return s
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_campaign_api.py -v`
Expected: PASS (all, including the untouched ones). If any non-start-date test fails, confirm it was in the pre-existing-failures baseline (memory `dripdrop-repo-gotchas`) before proceeding.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/mkvau/OneDrive/Documents/Sales/Python/FunnelForge"
git add flowdrip_app.py tests/test_campaign_api.py
git commit -m "fix: default new-campaign start_date to next business day, not Monday

Brings local in line with the fix shipped directly to prod 2026-07-20.
Adds _next_business_day (Mon-Thu -> tomorrow, Fri/Sat/Sun -> coming Monday);
_resolve_start_date now returns it for blank/sentinel start dates.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Confirm the local 5×5 code is test-green (source-of-truth gate)

The 5×5 is already committed to local `main`. Before porting it to prod, prove it's green here so the port target is known-good.

**Files:**
- Test: `tests/test_arena_5x5.py` (7 tests)

- [ ] **Step 1: Run the 5×5 test suite**

Run: `cd "C:/Users/mkvau/OneDrive/Documents/Sales/Python/FunnelForge" && python -m pytest tests/test_arena_5x5.py -v`
Expected: 7 PASS.

- [ ] **Step 2: Verify the module compiles clean**

Run: `python -c "import py_compile; py_compile.compile('flowdrip_app.py', doraise=True); print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Snapshot the exact local line ranges to port**

Run these and record the output ranges into a scratch file `scratchpad/5x5_port_anchors.txt` — the port script in Task 3 reads them:

```bash
cd "C:/Users/mkvau/OneDrive/Documents/Sales/Python/FunnelForge"
grep -n '_ARENA_SLATE_TYPES = frozenset' flowdrip_app.py
grep -n '("fivebyfive", "Arena 5×5"' flowdrip_app.py
grep -n '_FIVEBYFIVE_BUMP_SUBJECT =' flowdrip_app.py
grep -n 'def _fivebyfive_step_no' flowdrip_app.py
grep -n 'def _apply_fivebyfive_overrides' flowdrip_app.py
grep -n '_apply_fivebyfive_overrides(camp_type, campaign_data)' flowdrip_app.py
grep -n '"key": "fivebyfive"' flowdrip_app.py
grep -n 'elif k == "fivebyfive"' flowdrip_app.py
```

No commit (read-only task).

---

## Task 3: Preflight — capture prod's real state (Gap B) and stage the port locally

**No prod mutations in this task.** Confirm what prod actually runs, prove `_next_business_day` is there, prove 5×5 is absent, and build the patched candidate file locally for review before anything touches the live box.

**Files:**
- Create (scratch, on prod): `/opt/dripdrop/flowdrip_app.py.bak.<ts>` (backup)
- Create (scratch, local): `scratchpad/prod_flowdrip_app.py` (pulled copy), `scratchpad/prod_flowdrip_app.patched.py`

- [ ] **Step 1: Confirm live color and health**

```bash
ssh <prod> 'systemctl is-active dripdrop dripdrop-green; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/healthz'
```
Expected: `active` for the blue one, `inactive`/`failed` for green, `200` from :8080. (If green is the live one, swap ports/paths throughout — do not assume blue.)

- [ ] **Step 2: Confirm `_next_business_day` IS on prod and 5×5 is NOT**

```bash
ssh <prod> 'cd /opt/dripdrop/app && echo "next_business_day:"; grep -c "_next_business_day" flowdrip_app.py; echo "fivebyfive:"; grep -c "fivebyfive" flowdrip_app.py; echo "self-serve keys marker:"; grep -c "mint_api_key\|self_serve\|api_keys" flowdrip_app.py; echo "ARENA_SLATE_TYPES:"; grep -n "_ARENA_SLATE_TYPES" flowdrip_app.py | head'
```
Expected: `_next_business_day` count ≥ 1 (fix present), `fivebyfive` count = 0 (absent), self-serve marker ≥ 1.
**STOP conditions:** if `_next_business_day` count is 0, the prod fix was never deployed — pause and resolve (either it lives elsewhere or the memory is wrong) before continuing. If `fivebyfive` > 0, prod already has some 5×5 — stop and diff before porting.

- [ ] **Step 3: Back up prod's file and pull a copy locally**

```bash
TS=$(ssh <prod> 'date +%Y%m%d_%H%M%S')
ssh <prod> "cp -p /opt/dripdrop/app/flowdrip_app.py /opt/dripdrop/flowdrip_app.py.bak.$TS && ls -la /opt/dripdrop/flowdrip_app.py.bak.$TS"
scp <prod>:/opt/dripdrop/app/flowdrip_app.py "C:/Users/mkvau/AppData/Local/Temp/claude/C--Users-mkvau/31b9de33-8d3a-4e7b-ac03-903c815e449e/scratchpad/prod_flowdrip_app.py"
```
Record `$TS` in `scratchpad/5x5_port_anchors.txt`.

- [ ] **Step 4: Build the patched candidate locally (binary-safe, preserves prod's CRLF)**

Write `scratchpad/apply_5x5_port.py` that reads BOTH files in **binary** mode and inserts only the 5×5 symbols into prod's bytes at anchored positions. It must:
  1. Read `prod_flowdrip_app.py` as bytes; detect line ending (`\r\n` vs `\n`) and preserve it.
  2. From local `flowdrip_app.py`, extract each block by its anchor lines (from `5x5_port_anchors.txt`), **excluding** any line containing `fivebythree`/`FIVEBYTHREE`.
  3. Insertions:
     - Add `"fivebyfive"` to prod's `_ARENA_SLATE_TYPES` frozenset (if prod has no frozenset, create `_ARENA_SLATE_TYPES = frozenset({"fourbyfour", "fivebyfive"})` immediately before its first use — grep prod for `_ARENA_SLATE_TYPES` first; if absent entirely, this is a bigger port and must stop for review).
     - Insert the `("fivebyfive", "Arena 5×5", …)` tuple into `AICB_CAMPAIGN_TYPES` immediately after the `fourbyfour` tuple.
     - Insert the `_FIVEBYFIVE_*` constants + `_fivebyfive_step_no` + `_apply_fivebyfive_overrides` as a block immediately before prod's `def _resume_attach_indices` (or, if that anchor differs on prod, immediately after the `_wrap_4x4_font` definition).
     - Insert the call `_apply_fivebyfive_overrides(camp_type, campaign_data)` in `_aicb_build_campaign_from_brief` immediately before the existing `_spread_email_times(campaign_data.get("emails", []))` line.
     - Insert the chooser tile dict after the 4×4 tile dict, and the `elif k == "fivebyfive":` routing branch after the 4×4 routing branch.
  4. Write `prod_flowdrip_app.patched.py` in binary with the preserved line ending.

Each insertion must be idempotent-guarded (skip if the target string already present) so a re-run can't double-insert.

- [ ] **Step 5: Review the patched candidate — only 5×5 lines changed, fix intact**

```bash
cd "C:/Users/mkvau/AppData/Local/Temp/claude/C--Users-mkvau/31b9de33-8d3a-4e7b-ac03-903c815e449e/scratchpad"
diff <(python -c "print(open('prod_flowdrip_app.py',newline='').read())") <(python -c "print(open('prod_flowdrip_app.patched.py',newline='').read())") | head -200
grep -c "_next_business_day" prod_flowdrip_app.patched.py   # must still be >=1
grep -c "fivebythree" prod_flowdrip_app.patched.py          # must be 0
python -c "import py_compile; py_compile.compile('prod_flowdrip_app.patched.py', doraise=True); print('COMPILE OK')"
```
Expected: the diff shows **only** additions (all `fivebyfive`/`_FIVEBYFIVE_*`/chooser/routing/frozenset), `_next_business_day` still present, no `fivebythree`, compile OK. **Do not proceed if the diff shows any deletion or any unrelated change.**

No prod mutation, no commit.

---

## Task 4: Deploy the 5×5 port to prod (safe single-file, health-gated)

**Files:**
- Modify (prod): `/opt/dripdrop/app/flowdrip_app.py`

- [ ] **Step 1: Upload the patched file to a staging path on prod (not live yet)**

```bash
scp "…/scratchpad/prod_flowdrip_app.patched.py" <prod>:/opt/dripdrop/app/flowdrip_app.py.staged
```

- [ ] **Step 2: Server-side compile + isolated functional check on the staged file**

```bash
ssh <prod> 'set -a; . /opt/dripdrop/.env; set +a; export DRIPDROP_DATA_DIR=/opt/dripdrop/data PYTHONPATH=/opt/dripdrop/app; cd /opt/dripdrop/app; /opt/dripdrop/venv/bin/python -c "import py_compile; py_compile.compile(\"flowdrip_app.py.staged\", doraise=True); print(\"COMPILE OK\")"'
```
Then a byte-identical/behaviour check that the staged file imports and exposes both symbols. Copy staged→a temp module name and import it:
```bash
ssh <prod> 'set -a; . /opt/dripdrop/.env; set +a; export DRIPDROP_DATA_DIR=/opt/dripdrop/data PYTHONPATH=/opt/dripdrop/app; cd /opt/dripdrop/app; cp flowdrip_app.py.staged _ff_stage_check.py; /opt/dripdrop/venv/bin/python -c "import _ff_stage_check as m; print(\"nbd\", callable(m._next_business_day)); print(\"5x5\", callable(m._apply_fivebyfive_overrides)); print(\"types\", \"fivebyfive\" in m._ARENA_SLATE_TYPES)"; rm -f _ff_stage_check.py'
```
Expected: `nbd True`, `5x5 True`, `types True`.

- [ ] **Step 3: Swap staged → live and restart the blue service**

```bash
ssh <prod> 'mv /opt/dripdrop/app/flowdrip_app.py.staged /opt/dripdrop/app/flowdrip_app.py && systemctl restart dripdrop && sleep 4 && systemctl is-active dripdrop && curl -s -o /dev/null -w "health:%{http_code}\n" http://127.0.0.1:8080/healthz'
```
Expected: `active` + `health:200`.

- [ ] **Step 4: Rollback if unhealthy**

If Step 3 is not `active`+`200`, immediately restore:
```bash
ssh <prod> 'cp -p /opt/dripdrop/flowdrip_app.py.bak.<TS> /opt/dripdrop/app/flowdrip_app.py && systemctl restart dripdrop && sleep 4 && curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/healthz'
```
Then stop and diagnose from the staged file's logs (`journalctl -u dripdrop -n 80`). Do not continue to Task 5 until prod is healthy on the ported file.

- [ ] **Step 5: Confirm the scheduler restarted clean**

```bash
ssh <prod> 'journalctl -u dripdrop -n 40 --no-pager | grep -iE "scheduler|error|traceback" | tail -20'
```
Expected: scheduler started, no traceback. (A single transient `Queue save error (.tmp -> .json)` around a tick is the known harmless race — anything else, investigate.)

---

## Task 5: Pilot — convert 1–2 campaigns and verify rendering end to end

**Gate before batch.** Convert the two smallest of the 21 and prove the 5×5 renders correctly (5 emails, verbatim bump, **attached** Interview-Guide PDF, weekday-only schedule, contacts + newsletter preserved).

**Files:**
- Create (scratch, on prod): `/opt/dripdrop/convert_5x5.py` (the conversion driver, reused in Task 6)
- Read (prod): `/opt/dripdrop/data/users/michael_vaughn_at_arenastaffing_net/Campaigns/*.json`
- Modify (prod): the two pilot campaigns' queue items

- [ ] **Step 1: Enumerate the 21 target campaigns and pick 2 pilots**

```bash
ssh <prod> 'set -a; . /opt/dripdrop/.env; set +a; export DRIPDROP_DATA_DIR=/opt/dripdrop/data PYTHONPATH=/opt/dripdrop/app; cd /opt/dripdrop/app; /opt/dripdrop/venv/bin/python - <<PY
import flowdrip_app as fa, json, glob, os
owner="michael.vaughn@arenastaffing.net"
fa._CURRENT_USER_EMAIL.set(owner); fa._switch_to_user_paths(owner)
assert fa._user_queue_path().startswith("/opt/dripdrop/data/users/"), fa._user_queue_path()
rows=[]
for p in glob.glob(os.path.join(os.path.dirname(fa._user_queue_path()),"Campaigns","*.json")):
    c=json.load(open(p))
    ctype=(c.get("aicb_camp_type") or c.get("_chooser_origin") or "")
    sent=sum(1 for e in c.get("emails",[]) if e.get("_sent"))  # adjust to real sent-marker
    rows.append((c.get("name"), ctype, c.get("start_date"), len(c.get("contacts",[])), p))
# The 21 = fourbyfour, 0 sent, start_date 2026-07-21 (verify against known set)
for r in sorted(rows, key=lambda r: r[3]):
    print(r)
PY'
```
Expected: the 21 not-yet-started 4×4s (0 sent, `start_date` 2026-07-21). Record the file paths. Pick the 2 with the fewest contacts as pilots. **Cross-check this list against the session's earlier count of 21 before mutating anything.**

- [ ] **Step 2: Locate Mike's prod per-user API key for the localhost call**

```bash
ssh <prod> 'grep -rIl "michael.vaughn@arenastaffing.net" /opt/dripdrop/data/users/michael_vaughn_at_arenastaffing_net/ 2>/dev/null | head; ls -la /opt/dripdrop/data/users/michael_vaughn_at_arenastaffing_net/*key* 2>/dev/null'
```
Find the stored Bearer key (see memory `dripdrop-api-key-locations` for the scattered locations — reissuing revokes all copies, so **read, don't mint** unless none works). Confirm it authenticates:
```bash
ssh <prod> 'curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer <KEY>" http://127.0.0.1:8080/api/v1/campaigns -X GET'
```
Expected: not 401 (200/404/405 all prove auth works).

- [ ] **Step 3: Write the conversion driver `convert_5x5.py`**

It takes a list of campaign JSON paths and, for each: reads `company`, `contacts[]`, candidate slate (`candidates[]`), `enroll_newsletter`, `industry`/`location`/`roles`; **cancels the existing 4×4 pending queue items** for that campaign; then `POST 127.0.0.1:8080/api/v1/campaigns` with `template="fivebyfive"`, `start_date="2026-07-22"`, and the extracted fields. Hard guards, in this order:

```python
import flowdrip_app as fa, json, sys, urllib.request
OWNER="michael.vaughn@arenastaffing.net"
START="2026-07-22"
KEY=sys.argv[1]; paths=sys.argv[2:]
fa._CURRENT_USER_EMAIL.set(OWNER); fa._switch_to_user_paths(OWNER)
qp=fa._user_queue_path()
assert qp.startswith("/opt/dripdrop/data/users/"), f"WRONG QUEUE PATH: {qp}"  # DRIPDROP_DATA_DIR guard
for p in paths:
    c=json.load(open(p))
    assert (c.get("aicb_camp_type") or c.get("_chooser_origin")) in ("fourbyfour",), f"not a 4x4: {p}"
    assert not any(e.get("_sent") for e in c.get("emails",[])), f"already started: {p}"  # never touch a started campaign
    # 1) cancel this campaign's pending items (requeue_campaign cancels + re-queues; here we cancel only,
    #    then re-create via API). Use fa.cancel_campaign_queue(c) if present, else the requeue path's cancel step.
    fa.cancel_campaign_pending(c)  # confirm the real function name on prod before running
    # 2) build + POST payload
    payload={"template":"fivebyfive","start_date":START,
             "company":c.get("company") or c.get("name"),
             "name":c.get("name"),
             "industry":c.get("industry"),"location":c.get("location"),
             "roles":c.get("roles",[]),
             "candidates":c.get("candidates",[]),
             "contacts":c.get("contacts",[]),
             "enroll_newsletter":c.get("enroll_newsletter")}
    req=urllib.request.Request("http://127.0.0.1:8080/api/v1/campaigns",
        data=json.dumps({k:v for k,v in payload.items() if v is not None}).encode(),
        headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        body=json.loads(r.read())
    assert body.get("steps")==7, f"expected 7 steps for 5x5, got {body.get('steps')}: {body}"
    assert all(fa._is_weekday(s['date']) for s in body.get('schedule',[])), body  # weekday-only
    print("OK", c.get("name"), body.get("campaign_id"), "newsletter", body.get("newsletter_enrollment",{}).get("matched"))
```

**Before running, confirm the real function names on prod** (`cancel_campaign_pending`, `_is_weekday`, the sent-marker key) by grepping `flowdrip_app.py` — the names above are placeholders for whatever the live file actually exposes. If a clean per-campaign cancel helper doesn't exist, use the `requeue_campaign` cancel path from memory `dripdrop-campaign-start-date-monday` (set `camp["start_date"]`, but here we cancel-only then re-create fresh via the API so the content is full 5×5, not a re-queued 4×4).

- [ ] **Step 4: Back up the two pilot campaign JSONs + the queue, then run the driver on the 2 pilots**

```bash
ssh <prod> 'TS=$(date +%Y%m%d_%H%M%S); D=/opt/dripdrop/data/users/michael_vaughn_at_arenastaffing_net; cp $D/scheduled_queue.json $D/scheduled_queue.json.bak.$TS; cp "<pilot1>.json" "<pilot1>.json.bak.$TS"; cp "<pilot2>.json" "<pilot2>.json.bak.$TS"; echo backed up $TS'
ssh <prod> 'set -a; . /opt/dripdrop/.env; set +a; export DRIPDROP_DATA_DIR=/opt/dripdrop/data PYTHONPATH=/opt/dripdrop/app; cd /opt/dripdrop/app; /opt/dripdrop/venv/bin/python /opt/dripdrop/convert_5x5.py "<KEY>" "<pilot1_path>" "<pilot2_path>"'
```
Expected: two `OK … steps 7 …` lines, weekday-only schedules.

- [ ] **Step 5: Verify the pilots render as true 5×5 (the real gate)**

```bash
ssh <prod> 'set -a; . /opt/dripdrop/.env; set +a; export DRIPDROP_DATA_DIR=/opt/dripdrop/data PYTHONPATH=/opt/dripdrop/app; cd /opt/dripdrop/app; /opt/dripdrop/venv/bin/python - <<PY
import flowdrip_app as fa, json
# Load each pilot's freshly created campaign; assert:
#  - 5 email steps present (7 total incl. call + …)
#  - step-5 subject == fa._FIVEBYFIVE_BUMP_SUBJECT and body == verbatim bump
#  - the day-8 email body contains "interview guide"
#  - a real Interview-Guide PDF is attached (check the queued send's attachments, not just the keyword)
#  - every scheduled date is a weekday; contacts count preserved; enroll_newsletter preserved
print("inspect pilots here")
PY'
```
**Hard gate:** the Interview-Guide PDF must actually be attached to the day-8 send (not merely referenced in text). If the PDF is missing, stop — the `_PDF_KIND_KEYWORDS` mapping/asset didn't survive the port; fix on prod before batch. Do **not** proceed to Task 6 until both pilots pass every check.

---

## Task 6: Convert the remaining 19

**Files:**
- Modify (prod): the other 19 campaigns' JSONs + queue

- [ ] **Step 1: Back up all remaining campaign JSONs + the queue**

```bash
ssh <prod> 'TS=$(date +%Y%m%d_%H%M%S); D=/opt/dripdrop/data/users/michael_vaughn_at_arenastaffing_net; cp $D/scheduled_queue.json $D/scheduled_queue.json.bak.$TS; mkdir -p $D/Campaigns/.bak.$TS; cp $D/Campaigns/*.json $D/Campaigns/.bak.$TS/; echo backed up $TS'
```

- [ ] **Step 2: Run the driver on the remaining 19**

```bash
ssh <prod> 'set -a; . /opt/dripdrop/.env; set +a; export DRIPDROP_DATA_DIR=/opt/dripdrop/data PYTHONPATH=/opt/dripdrop/app; cd /opt/dripdrop/app; /opt/dripdrop/venv/bin/python /opt/dripdrop/convert_5x5.py "<KEY>" <the 19 paths>'
```
Expected: 19 `OK … steps 7 …` lines. The guards in the driver refuse any campaign that is already started or not a 4×4 — so a stray path can't corrupt a live campaign.

- [ ] **Step 3: Per-campaign verification sweep**

```bash
ssh <prod> 'set -a; . /opt/dripdrop/.env; set +a; export DRIPDROP_DATA_DIR=/opt/dripdrop/data PYTHONPATH=/opt/dripdrop/app; cd /opt/dripdrop/app; /opt/dripdrop/venv/bin/python - <<PY
import flowdrip_app as fa, json, glob, os
owner="michael.vaughn@arenastaffing.net"; fa._CURRENT_USER_EMAIL.set(owner); fa._switch_to_user_paths(owner)
q=json.load(open(fa._user_queue_path()))
# For each of the 21: assert no leftover 4x4 pending items, all pending dates weekdays,
# step-1 date == 2026-07-22, contacts_queued matches the campaign contact count.
print("total pending items:", len(q))
PY'
```
Expected: all 21 are 5×5, no residual 4×4 pending items, all pending dates weekdays, step-1 = 2026-07-22. Confirm the 63 already-started campaigns' pending counts are **unchanged** from a pre-run snapshot.

- [ ] **Step 4: Clean up any stray queue file and confirm health**

```bash
ssh <prod> 'ls -la /opt/dripdrop/app/DripDrop/users/ 2>/dev/null && echo "STRAY EXISTS — investigate" || echo "no stray"; curl -s -o /dev/null -w "health:%{http_code}\n" http://127.0.0.1:8080/healthz'
```
Expected: `no stray`, `health:200`. If a stray `app/DripDrop/...` queue exists, the `DRIPDROP_DATA_DIR` export was missed on some run — reconcile against the real queue before trusting the result (memory `dripdrop-campaign-start-date-monday`).

---

## Task 7: Flip the default to 5×5, retire 4×4 from the pipeline

**Files:**
- Modify: `~/Downloads/denver-bd-pipeline.skill` (SKILL.md + `references/dripdrop-campaign.md`)
- Modify: `~/Downloads/regional-bd-pipeline.skill` (SKILL.md + `references/dripdrop-campaign.md`)
- Modify: any installed skill copy the cloud routines load; routine prompt text if it names `fourbyfour`

- [ ] **Step 1: Edit the skill bundles to launch `fivebyfive` by default**

In each `.skill` (they're zip bundles — unzip to a temp dir, edit, re-zip; keep a `.skill.bak.<ts>`):
  - In `references/dripdrop-campaign.md`, change the request-body `template` guidance from `"fourbyfour"` to `"fivebyfive"` (and update the "Arena 4x4" phrasing to "Arena 5×5", the "sends `steps` is 5" note to "7 steps" where the doc describes the response).
  - In `SKILL.md`, change any "Arena 4x4" default-campaign references to "Arena 5×5". Leave the routine *schedule* lines (e.g. regional's "Monday 8am") alone — those are cron times, not campaign templates.
  - Note in each: 4×4 remains a valid template (kept in code) but is no longer the pipeline default.

- [ ] **Step 2: Diff-check the edits before re-zipping**

For each bundle, confirm only template/label lines changed and the next-business-day wording added 2026-07-20 is still intact. Re-zip preserving the internal structure (`SKILL.md`, `references/`, `scripts/` at the same paths).

- [ ] **Step 3: Re-import/install the skills into the cloud routine environment**

The Downloads copies are **not** what the routines run — they must be re-imported. Follow the same install path used when the start-date wording was edited (memory `dripdrop-bd-agents-permission-stall` / the routine env). After import, confirm the routine's active skill version shows the 5×5 default.

- [ ] **Step 4: Smoke-test a fresh launch produces a 5×5**

Trigger one BD skill run (or a single dry `POST` with the skill's now-default body) and confirm the created campaign is `fivebyfive` (7 steps, bump + Interview-Guide PDF). This closes the "going forward" acceptance criterion.

- [ ] **Step 5: Update memory**

Update memory `dripdrop-5x5-sequence` (now deployed to prod + default), `dripdrop-campaign-start-date-monday` (local synced/committed), and add a line to `MEMORY.md` if a new memory is warranted (e.g. "5×5 is the BD default as of 2026-07-30; 4×4 retired from pipeline, kept in code; 21 campaigns converted"). Convert relative dates to absolute.

---

## Acceptance criteria (from the spec — verify at the end)

- Prod serves 5×5 (`_next_business_day` and self-serve features still present; health 200; clean scheduler restart). — Tasks 3–4
- The 21 target campaigns are 5×5 (5 emails + verbatim bump + **attached** Interview-Guide PDF), all sends weekday-only, step-1 on 2026-07-22, contacts/newsletter preserved, no residual 4×4 pending items. — Tasks 5–6
- The 63 already-started campaigns are unchanged. — Task 6 Step 3
- The BD skills/routines create `fivebyfive` by default; a fresh test launch produces a 5×5. — Task 7
- Local repo/tests match prod's start-date behavior and are committed. — Task 1

## Open items to confirm during execution (from the spec)

- Interview-Guide PDF asset presence + `_PDF_KIND_KEYWORDS` mapping on prod after the port. — Task 5 Step 5 (hard gate)
- Location of Mike's prod per-user API key for the localhost call. — Task 5 Step 2
- Exact reachability/response of `POST 127.0.0.1:8080/api/v1/campaigns` on the prod box. — Task 5 Step 2
- Real function names on prod for cancel/weekday/sent-marker (the driver uses placeholders). — Task 5 Step 3

## Out of scope (separate work)

- The newsletter content-generation auto-select/create-by-industry+geography rule — separate brainstorm/design/spec. This plan only preserves the existing `enroll_newsletter` value at the conversion seam; it does not implement the new selection logic.
- Full local↔prod divergence reconciliation beyond the start-date sync in Task 1 (e.g. the candidate-bullet drift, the un-deployed 5×3) — not chased here.

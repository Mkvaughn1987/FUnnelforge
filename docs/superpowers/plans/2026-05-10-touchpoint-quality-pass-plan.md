# Touchpoint Quality Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply Leigh's pitch DNA (self-aware honesty + project-anchored specificity + market-data + diagnostic-question close) to DripDrop's cold-call, voicemail, and LinkedIn scripts. Each gets 3 trial-able style variants. Plus close the LinkedIn touchpoint placement gaps surfaced by the 2026-05-10 audit.

**Architecture:**
- Phase A: Five surgical fixes to LI sequence generators so all NEW sequences get exactly one LI step at position 2 with `delay_days:1`. Existing saved campaigns are untouched per user direction.
- Phase B: A per-industry market-stats cache (web-search-driven, 30-day TTL, shared across users) feeds three rewritten AI generators (call, voicemail, LI) that each emit 3 style variants in one Claude call. UI gets pill-selector + Copy on the call card and the LI card; voicemail gets a NEW user-level block at the top of the calls section since the same voicemail applies to everyone you call today.

**Tech Stack:** Python 3.12, NiceGUI, pytest, Anthropic Claude (Haiku 4.5), Anthropic web_search_20250305 tool (already integrated via `_safe_web_search_tool`), `_run_as_user` thread-binding helper from Phase 0.

**Spec / supporting docs:**
- LinkedIn touchpoint audit: [docs/superpowers/specs/2026-05-10-linkedin-touchpoint-audit.md](../specs/2026-05-10-linkedin-touchpoint-audit.md)
- Phase 0 design (for thread-binding helper): [docs/superpowers/specs/2026-05-09-phase-0-stability-design.md](../specs/2026-05-09-phase-0-stability-design.md)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `flowdrip_app.py` | Modify (multiple targeted edits) | All app changes — see per-task line refs |
| `tests/test_li_step_placement.py` | Create | Asserts AICB Free Flow + Recruiting Sequence prompts contain the LI placement constraint; asserts wizard step-add UI has guardrails |
| `tests/test_market_stats_cache.py` | Create | Behavioral tests for the per-industry cache (read, write, TTL expiry, cache miss → web search) |
| `tests/test_call_variants_generation.py` | Create | Tests the 3-variant parser; tests the prompt instructs Leigh-style; tests caching on `camp["call_briefing"]` |
| `tests/test_voicemail_variants_generation.py` | Create | Tests the 3-variant voicemail parser; tests user-level storage path; tests TTL refresh |
| `tests/test_li_variants_generation.py` | Create | Tests the 3-variant LI parser; tests the new `linkedin_variants` field; tests legacy `linkedin_message` fallback |

---

## Phase A — LinkedIn placement enforcement (5 surgical fixes)

### Task 1: Fix Free Flow AICB prompt — hard rule for 1 LI at step 2

**Files:**
- Modify: `flowdrip_app.py` — find AICB byos prompt block via `grep -n "The user wants a CUSTOM sequence" flowdrip_app.py`
- Test: `tests/test_li_step_placement.py` (created here)

- [ ] **Step 1: Write the failing test**

Create `tests/test_li_step_placement.py` with this content:

```python
"""LinkedIn touchpoint placement enforcement.

Every NEW sequence (AICB Free Flow, Recruiting Sequence) must include
exactly ONE LinkedIn step, positioned immediately after the first
email (step 2, delay_days:1). The Free Flow wizard step-add UI must
warn if the user tries to add a second LI or place LI before email 1.

Existing saved campaigns are NOT migrated (per 2026-05-10 audit
findings).
"""
import inspect


def test_aicb_byos_prompt_enforces_one_li_at_step_2():
    """The AICB Free Flow (byos) prompt must explicitly require
    exactly one LinkedIn step at position 2 with delay_days:1.
    Without this hard constraint, the AI free-styles LI placement."""
    import flowdrip_app as fa
    # The byos prompt is built inside the AICB main generation flow.
    # Search for the byos branch source.
    src = inspect.getsource(fa)
    # Locate the byos prompt — the marker phrase is unique:
    assert "The user wants a CUSTOM sequence" in src, (
        "Expected to find the AICB byos prompt in flowdrip_app.py"
    )
    # Slice out a window around the byos prompt (~600 chars after the marker)
    idx = src.index("The user wants a CUSTOM sequence")
    window = src[idx : idx + 1200]
    # The constraint must appear in the prompt window
    assert "exactly ONE LinkedIn" in window or "exactly one linkedin" in window.lower(), (
        "Free Flow AICB prompt must explicitly require exactly ONE "
        "LinkedIn step. Add a hard constraint like 'Include EXACTLY "
        "ONE LinkedIn step at position 2 (delay_days:1).'"
    )
    assert "step 2" in window.lower() or "position 2" in window.lower() or "after the first email" in window.lower(), (
        "Free Flow AICB prompt must specify the LI step's position "
        "(step 2 / position 2 / after the first email)"
    )
```

- [ ] **Step 2: Run the test; it MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_li_step_placement.py::test_aicb_byos_prompt_enforces_one_li_at_step_2 -v`

Expected: FAIL — the constraint phrasing isn't in the byos prompt yet.

- [ ] **Step 3: Update the AICB byos prompt**

Find the AICB byos prompt in `flowdrip_app.py`. Run: `grep -n "The user wants a CUSTOM sequence" flowdrip_app.py` to locate it (around L29515 per the audit; line may have drifted).

Read ~30 lines of the surrounding prompt-build block. The current text is:

```python
'The user wants a CUSTOM sequence. Here is their description:\n'
f'{s.aicb_byos_desc}\n\n'
'Design the sequence based on their instructions. Use step_type values: '
'email_auto, linkedin, call, task_general. Set appropriate delay_days.\n\n'
```

Replace with:

```python
'The user wants a CUSTOM sequence. Here is their description:\n'
f'{s.aicb_byos_desc}\n\n'
'Design the sequence based on their instructions. Use step_type values: '
'email_auto, linkedin, call, task_general. Set appropriate delay_days.\n\n'
'PLACEMENT RULES (these override the user description if there is conflict):\n'
'- Include EXACTLY ONE LinkedIn step at position 2, delay_days:1, '
'time:"10:00 AM". The first step must always be email_auto.\n'
'- Never place LinkedIn before any email step.\n'
'- Never include more than one LinkedIn step.\n\n'
```

- [ ] **Step 4: Run the test; it MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_li_step_placement.py::test_aicb_byos_prompt_enforces_one_li_at_step_2 -v`

Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 268 passed (267 from Phase 0 + 1 new).

- [ ] **Step 6: Commit**

```
git add flowdrip_app.py tests/test_li_step_placement.py
git commit -m "fix(aicb): byos prompt enforces 1 LI step at position 2

The Free Flow AICB prompt previously gave the AI a soft example of
LI placement but no hard rule. Audit at docs/superpowers/specs/
2026-05-10-linkedin-touchpoint-audit.md found 7 saved campaigns
where LI was generated at the wrong position (before email 1, or
buried 6+ emails deep).

Adds explicit PLACEMENT RULES block to the byos prompt that
overrides the user description if needed. New sequences are now
guaranteed to have exactly 1 LI at position 2 with delay_days:1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add LI step to Recruiting Sequence generator

**Files:**
- Modify: `flowdrip_app.py` — Recruiting Sequence prompt around L41901–41924 (line may have drifted)
- Test: `tests/test_li_step_placement.py` (existing file from Task 1)

- [ ] **Step 1: Write the failing test**

Append this test to `tests/test_li_step_placement.py`:

```python
def test_recruiting_sequence_prompt_includes_li_after_email_1():
    """The Recruiting Campaigns page generator currently builds
    email-only sequences. Per the 2026-05-10 directive, every NEW
    sequence (including recruiting-flow ones) should include exactly
    one LinkedIn step at position 2."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    # The recruiting sequence generator's prompt has a unique marker
    # phrase — locate it. Marker chosen from L41901-41924 area.
    assert "Recruiting" in src, "Expected to find recruiting-sequence builder source"
    # Find the recruiting prompt's JSON example block
    idx_candidates = [i for i in range(len(src)) if src[i:i+20] == "Return ONLY valid JS"]
    found_li_in_recruiting = False
    for idx in idx_candidates:
        # Each "Return ONLY valid JSON" marker corresponds to one prompt.
        # Walk forward 800 chars to scan the JSON example.
        window = src[idx : idx + 800]
        # If we see "linkedin" AND "Recruiting" within ~2000 chars before
        # this point, this is the recruiting prompt.
        before = src[max(idx - 2000, 0) : idx]
        if ("recruiting" in before.lower() or "Recruiting" in before) and '"step_type":"linkedin"' in window:
            found_li_in_recruiting = True
            break
    assert found_li_in_recruiting, (
        "The Recruiting Sequence generator's JSON example must include "
        "a step with \"step_type\":\"linkedin\" at position 2. Current "
        "prompt generates email-only sequences."
    )
```

- [ ] **Step 2: Run the test; it MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_li_step_placement.py::test_recruiting_sequence_prompt_includes_li_after_email_1 -v`

Expected: FAIL — the recruiting prompt has no LI step in its example.

- [ ] **Step 3: Locate the recruiting prompt**

Run: `grep -n "_run_ai\|recruiting.*sequence\|rc_step\|rc_ai" flowdrip_app.py | head -10` to find the Recruiting Campaigns generator. The audit identified it at L41896–41985 (lines may have drifted slightly).

Read 30 lines of the prompt-build block. Find the JSON example string (looks like `'{"synopsis":"…","emails":[…]}'`).

- [ ] **Step 4: Update the recruiting JSON example to include an LI step at position 2**

In the Recruiting Sequence prompt's JSON example block, locate the `"emails":[...]` array. The current example has only `email_auto` entries. After the FIRST email entry, insert a LinkedIn step. Example transformation:

Old:
```python
'"emails":[{"week":1,"name":"Step 1 - Intro",'
'"subject":"...","body":"...",'
'"delay_days":0,"time":"9:00 AM","step_type":"email_auto"},'
'{"week":1,"name":"Step 2 - Follow-up",'
```

New:
```python
'"emails":[{"week":1,"name":"Step 1 - Intro",'
'"subject":"...","body":"...",'
'"delay_days":0,"time":"9:00 AM","step_type":"email_auto"},'
'{"week":1,"name":"Step 2 - LinkedIn touch",'
'"subject":"","body":"<short LI connection note>",'
'"delay_days":1,"time":"10:00 AM","step_type":"linkedin"},'
'{"week":1,"name":"Step 3 - Follow-up",'
```

If the prompt has a "STRICT RULES" section, ADD this rule:
- "Include exactly one LinkedIn step at position 2 (delay_days:1, time:10:00 AM). Never place LinkedIn before email 1. Never include more than one LinkedIn step."

- [ ] **Step 5: Run the test; it MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_li_step_placement.py::test_recruiting_sequence_prompt_includes_li_after_email_1 -v`

Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 269 passed.

- [ ] **Step 7: Commit**

```
git add flowdrip_app.py tests/test_li_step_placement.py
git commit -m "fix(recruiting): sequence generator now includes LI step at position 2

The Recruiting Campaigns page previously generated email-only
sequences. Per the 2026-05-10 directive, every NEW sequence should
include exactly one LinkedIn touchpoint at position 2 with
delay_days:1.

Updates the JSON example in the recruiting prompt to include a
linkedin step between Email 1 and Email 2, plus an explicit STRICT
RULES entry pinning the placement.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Free Flow wizard guardrails (warnings, not hard blocks)

**Files:**
- Modify: `flowdrip_app.py:13139-13238` (the step-add UI handler `_confirm_add_step`)
- Test: `tests/test_li_step_placement.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_li_step_placement.py`:

```python
def test_step_add_handler_has_li_guardrails():
    """The Free Flow step-add UI must warn (via ui.notify) if the user
    tries to add a second LinkedIn step or place a LinkedIn step
    before any email. These are SOFT enforcement (warnings, not hard
    blocks) — the user is explicitly building a custom sequence and
    can override."""
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    # The step-add panel is at L13139+ per audit; locate by marker.
    assert "_confirm_add_step" in src, (
        "Expected _confirm_add_step handler in flowdrip_app.py"
    )
    # Find the function body
    idx = src.index("def _confirm_add_step")
    end = src.find("\n    def ", idx + 1)
    if end == -1:
        end = idx + 3000
    body = src[idx:end]
    # The handler must check for an existing LI step before adding another
    assert "linkedin" in body.lower() and ("warn" in body.lower() or "ui.notify" in body), (
        "_confirm_add_step must check for an existing LinkedIn step "
        "and warn the user via ui.notify before adding a second one"
    )
```

- [ ] **Step 2: Run test; it MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_li_step_placement.py::test_step_add_handler_has_li_guardrails -v`

Expected: FAIL — current `_confirm_add_step` has no LI checks.

- [ ] **Step 3: Add guardrails to `_confirm_add_step`**

Find `_confirm_add_step` at `flowdrip_app.py:13207-13232` (line may have drifted; use `grep -n "def _confirm_add_step" flowdrip_app.py`).

Read the current function body. After the line that determines the step_type but BEFORE the line that inserts the step into the sequence, add:

```python
        # LinkedIn placement guardrails (soft warnings, not hard blocks).
        # Per 2026-05-10 directive: each sequence should have exactly
        # one LI step at position 2. The wizard lets users override,
        # but warns first so the convention is visible.
        if step_type == "linkedin":
            existing_emails = sum(1 for st in steps if st.get("step_type") == "email_auto")
            existing_li = sum(1 for st in steps if st.get("step_type") == "linkedin")
            if existing_li >= 1:
                ui.notify(
                    "You already have a LinkedIn touch in this sequence. "
                    "Adding a second one may dilute response. Continuing "
                    "anyway — remove it later if you change your mind.",
                    type="warning", timeout=6000,
                )
            # If user is inserting LI at position 0 (Beginning) AND has
            # at least one email already, warn that LI before email 1
            # rarely lands well.
            if insert_after == 0 and existing_emails >= 1:
                ui.notify(
                    "Heads up — placing a LinkedIn touch BEFORE your "
                    "first email is unusual. Cold LI connects without "
                    "context typically convert worse than after email 1.",
                    type="warning", timeout=6000,
                )
```

NOTE: The exact variable names (`steps`, `step_type`, `insert_after`) depend on the current `_confirm_add_step` body. Read the function first and adapt the guardrail block to use the actual variable names. The CONCEPT is fixed (count existing LI / check insertion position vs first email); the syntax must match local scope.

- [ ] **Step 4: Run test; it MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_li_step_placement.py::test_step_add_handler_has_li_guardrails -v`

Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 270 passed.

- [ ] **Step 6: Commit**

```
git add flowdrip_app.py tests/test_li_step_placement.py
git commit -m "fix(wizard): warn on 2nd LinkedIn step or LI before email 1

The Free Flow step-add UI previously had no guardrails — users
could freely add multiple LinkedIn steps or place LI at any
position. Per the 2026-05-10 audit, this was the root cause of the
7 wrong-position and 7 multi-LI saved campaigns.

Adds soft warnings (ui.notify, not hard blocks) when the user tries
to add a 2nd LinkedIn step or insert LI before any email. The user
can still override — the wizard is for custom sequences.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Victory Card preset — fix `delay_days:0 → 1` for LI

**Files:**
- Modify: `flowdrip_app.py` — find Victory Card preset description in `AICB_CAMPAIGN_TYPES` (around L3402+, search for `victorycard` or `Victory Card`)

- [ ] **Step 1: Locate the Victory Card preset's touch_sequence string**

Run: `grep -n "victorycard\|Victory Card" flowdrip_app.py | head -5`

Read the preset entry. The touch_sequence string includes a step like `"Step 2 - LinkedIn touch (delay_days:0, step_type:linkedin)"` per the audit.

- [ ] **Step 2: Change `delay_days:0` to `delay_days:1` for the LI step**

Use Edit to change ONLY the LinkedIn step's delay from 0 to 1 in the Victory Card preset's touch_sequence string. Preserve all other steps.

Example transformation (the actual text in the preset will differ slightly):

Old: `"Step 2 - LinkedIn touch (delay_days:0, step_type:linkedin)"`
New: `"Step 2 - LinkedIn touch (delay_days:1, step_type:linkedin)"`

- [ ] **Step 3: Verify the file still parses**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0.

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 270 passed.

- [ ] **Step 5: Commit**

```
git add flowdrip_app.py
git commit -m "fix(preset): Victory Card LI step now fires day after email 1

Per the 2026-05-10 audit: Victory Card was structurally correct
(LI at step 2) but its LinkedIn delay_days was 0, so the LI fires
the SAME day as email 1 instead of the day after. Same-day delivery
of an email + LI connect signals 'recruiter blast' rather than
sequenced outreach. Bumped to delay_days:1 to match the other 5
presets.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase B — 3-variant scripts (call + voicemail + LinkedIn) with market stats

### Task 5: Per-industry market stats cache infrastructure

**Files:**
- Modify: `flowdrip_app.py` — add new helpers near other path helpers (around L880-940; or near the existing market_intel infrastructure if you find it)
- Create: `tests/test_market_stats_cache.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_market_stats_cache.py`:

```python
"""Per-industry market stats cache.

Stores AI-generated market data (fill-window days, candidate-pool
trends, etc.) per industry, shared across all users on the same
DripDrop deployment. Cache TTL is 30 days. On miss, the cache
hydrates via web search through the existing _safe_web_search_tool.

This cache feeds the call/voicemail/LI variant generators so they
have real market data to work with — without making a separate web
search per script generation (which would slow the Today page and
increase cost).
"""
import json
import sys
from pathlib import Path


def test_cache_helpers_exist():
    import flowdrip_app as fa
    assert hasattr(fa, "_market_stats_for_industry"), (
        "_market_stats_for_industry(industry) must be defined"
    )
    assert hasattr(fa, "_MARKET_STATS_CACHE_PATH"), (
        "_MARKET_STATS_CACHE_PATH must be defined (path to the cache file)"
    )


def test_cache_returns_dict_or_none(tmp_path, monkeypatch):
    """A cache miss without an API key should return None (not raise)."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if "flowdrip_app" in sys.modules:
        del sys.modules["flowdrip_app"]
    import flowdrip_app as fa
    # No API key set → web search can't fire → cache miss returns None
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    result = fa._market_stats_for_industry("test-industry-xyz")
    assert result is None or isinstance(result, dict)


def test_cache_hits_after_first_write(tmp_path, monkeypatch):
    """After a stats dict is cached for an industry, subsequent calls
    return it without invoking the web-search path."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if "flowdrip_app" in sys.modules:
        del sys.modules["flowdrip_app"]
    import flowdrip_app as fa
    # Hand-write a cache entry
    fa._MARKET_STATS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = {
        "heavy-civil": {
            "fill_window_days": "50 to 65",
            "trend_summary": "fill windows have stretched",
            "_cached_at": "2026-05-10T12:00:00",
        }
    }
    fa._MARKET_STATS_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    result = fa._market_stats_for_industry("heavy-civil")
    assert isinstance(result, dict)
    assert result.get("fill_window_days") == "50 to 65"


def test_cache_miss_with_stale_entry_refreshes(tmp_path, monkeypatch):
    """An entry older than 30 days should be considered stale; the
    helper should attempt to refresh (or return None if no API key)."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if "flowdrip_app" in sys.modules:
        del sys.modules["flowdrip_app"]
    import flowdrip_app as fa
    # Write a stale entry (older than 30 days)
    fa._MARKET_STATS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = {
        "stale-industry": {
            "fill_window_days": "100",
            "_cached_at": "2025-01-01T00:00:00",  # well over 30 days ago
        }
    }
    fa._MARKET_STATS_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    # No API key → can't refresh → returns None even though cache exists
    result = fa._market_stats_for_industry("stale-industry")
    assert result is None
```

- [ ] **Step 2: Run tests; they MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_market_stats_cache.py -v`

Expected: All 4 FAIL with `AttributeError`.

- [ ] **Step 3: Implement the cache helpers**

Add to `flowdrip_app.py` near the other module-level helpers (a good spot is right after `_BASE_DATA_DIR` is defined and before `_resolve_user_root`, around L862):

```python
# ── Per-industry market stats cache ─────────────────────────────────────
# Shared across all users (market data is public). 30-day TTL. Hydrated
# via web_search when an industry is queried for the first time. Used by
# the call / voicemail / LinkedIn variant generators to anchor scripts
# in real market data ("fill windows have stretched to 50-65 days")
# without making a separate web search per script generation.
_MARKET_STATS_CACHE_PATH = _BASE_DATA_DIR / "market_stats_cache.json"
_MARKET_STATS_TTL_DAYS = 30


def _load_market_stats_cache() -> dict:
    if not _MARKET_STATS_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_MARKET_STATS_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_market_stats_cache(cache: dict) -> None:
    try:
        _MARKET_STATS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _MARKET_STATS_CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        tmp.replace(_MARKET_STATS_CACHE_PATH)
    except Exception as ex:
        print(f"[MarketStatsCache] save failed: {ex}", flush=True)


def _market_stats_for_industry(industry: str) -> dict | None:
    """Return market stats for `industry`, refreshing via web search if
    the cached entry is stale or missing. Returns None if no API key
    is available (cache miss can't be filled).

    Cache shape:
        {
          "<industry-key>": {
            "fill_window_days": "50 to 65",
            "trend_summary": "fill windows have stretched this year",
            "_cached_at": "2026-05-10T12:00:00"
          },
          ...
        }
    """
    if not industry:
        return None
    key = industry.strip().lower()
    cache = _load_market_stats_cache()
    entry = cache.get(key)
    if entry:
        # Check freshness
        try:
            cached_at = entry.get("_cached_at", "")
            cached_dt = datetime.fromisoformat(cached_at)
            age_days = (datetime.now() - cached_dt).days
            if age_days < _MARKET_STATS_TTL_DAYS:
                return entry
        except Exception:
            pass  # fall through to refresh
    # Cache miss or stale — try to refresh via web search
    if not ANTHROPIC_API_KEY:
        return None
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception as ex:
        print(f"[MarketStatsCache] Anthropic init failed: {ex}", flush=True)
        return None
    prompt = (
        f"Use web_search to find current 2026 hiring-market stats for the "
        f"{industry} industry in the United States. Search bls.gov, "
        f"linkedin.com, and indeed.com. Return ONLY valid JSON in this "
        f"exact shape:\n"
        f'{{"fill_window_days": "<typical days to fill a senior role, '
        f'e.g. \\"50 to 65\\">", "trend_summary": "<one sentence on '
        f'whether the market is tightening or loosening>"}}\n\n'
        f"If you cannot find specific numbers, return: "
        f'{{"fill_window_days": "", "trend_summary": ""}}'
    )
    try:
        msg = _claude_create_with_retry(client,
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            tools=[_safe_web_search_tool(max_uses=3)],
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
    except Exception as ex:
        print(f"[MarketStatsCache] web search failed for {industry}: {ex}", flush=True)
        return None
    # Extract JSON from response
    try:
        m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    data["_cached_at"] = datetime.now().isoformat(timespec="seconds")
    cache[key] = data
    _save_market_stats_cache(cache)
    return data
```

NOTE: This helper depends on `datetime` (imported at module top), `json` (imported at module top), `re` (imported at module top), `_claude_create_with_retry` (search to confirm it exists), `_safe_web_search_tool` (defined at L7422), and `ANTHROPIC_API_KEY` (defined at L2170).

- [ ] **Step 4: Run tests; they MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_market_stats_cache.py -v`

Expected: All 4 PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 274 passed (270 + 4 new).

- [ ] **Step 6: Commit**

```
git add flowdrip_app.py tests/test_market_stats_cache.py
git commit -m "feat(market-stats): add per-industry cache with 30-day TTL

New helpers _market_stats_for_industry(industry) and supporting
load/save functions. Cache is a single JSON file at
_BASE_DATA_DIR/market_stats_cache.json, shared across all users
(market data is public, not per-user).

Cache miss / stale entry triggers a web_search via the existing
_safe_web_search_tool helper. Returns dict with fill_window_days
and trend_summary fields, or None if no API key is available.

This cache feeds the upcoming call / voicemail / LinkedIn variant
generators so they can anchor scripts in real market data without
making a separate web search per generation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Rewrite call briefing prompt to produce 3 variants in Leigh's style

**Files:**
- Modify: `flowdrip_app.py:37158+` (the `_generate_call_briefing_for_campaign` function)
- Create: `tests/test_call_variants_generation.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_call_variants_generation.py`:

```python
"""Cold-call variants generation.

The call briefing for each campaign now includes 3 style variants —
Project-Anchored / Market-Data / Brief Diagnostic — so the user can
pick which one matches the moment. Storage shape adds a new
`call_variants` field on the briefing dict; the legacy
`conversation_flow.opener` field is retained as variant 1's content
for backwards compatibility with old campaigns.
"""
import inspect


def test_call_variants_in_schema_version():
    """The schema version constant must be bumped so old briefings
    auto-regenerate on first view."""
    import flowdrip_app as fa
    assert hasattr(fa, "_CALL_BRIEFING_SCHEMA_VERSION")
    assert fa._CALL_BRIEFING_SCHEMA_VERSION >= 3, (
        "Schema version must be >= 3 to invalidate v2 cached briefings "
        "that don't have the new variants field"
    )


def test_call_briefing_prompt_asks_for_three_variants():
    """The prompt must explicitly instruct the AI to produce three
    distinct style variants in the response."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_call_briefing_for_campaign)
    # Variant style names must appear in the prompt
    assert "project_anchored" in src.lower() or "project-anchored" in src.lower()
    assert "market_data" in src.lower() or "market-data" in src.lower()
    assert "brief_diagnostic" in src.lower() or "brief-diagnostic" in src.lower() or "diagnostic" in src.lower()
    # The prompt must reference Leigh-style DNA: self-aware, project-anchored, diagnostic close
    assert "cold call" in src.lower() and ("researched" in src.lower() or "diagnostic" in src.lower())


def test_call_briefing_returns_variants_field():
    """The returned dict must include a `variants` field (list of 3)
    in addition to the existing fields (open_jobs, news, etc.)."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_call_briefing_for_campaign)
    # The dict assembly must include the variants key
    assert '"variants"' in src or "'variants'" in src, (
        "_generate_call_briefing_for_campaign must populate "
        "result['variants'] = [{'style': '...', 'script': '...'}, x3]"
    )
```

- [ ] **Step 2: Run tests; they MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_call_variants_generation.py -v`

Expected: All 3 FAIL.

- [ ] **Step 3: Bump the schema version constant**

Find `_CALL_BRIEFING_SCHEMA_VERSION` in `flowdrip_app.py`. Run: `grep -n "_CALL_BRIEFING_SCHEMA_VERSION" flowdrip_app.py`. Increase the constant's value by 1 (currently 2 → 3).

- [ ] **Step 4: Update the call briefing prompt**

Locate the AI prompt block within `_generate_call_briefing_for_campaign` (the function starts at L37158; the conversation_flow generation block is later in the function — search for `"opener"` or `"conversation_flow"` in the function body).

Replace the conversation_flow generation step with a 3-variant generation. The new prompt should:

1. Pull the cached market stats: `mkt = _market_stats_for_industry(sector or niche)` near the top of the function.
2. Build a context block including `company`, `open_jobs[0:2]`, `news[0:1]`, `mkt.get("fill_window_days")`, `mkt.get("trend_summary")`.
3. Ask Claude for THREE variants in one response with this prompt structure:

```python
        variant_prompt = (
            f"You are writing 3 cold-call openers for a recruiter calling "
            f"{company} about {sector or niche or 'their hiring needs'}.\n\n"
            f"CONTEXT:\n"
            f"- Company: {company}\n"
            f"- Sector / niche: {sector} / {niche}\n"
            f"- Open jobs at this company: {open_jobs[:2] if open_jobs else 'none surfaced'}\n"
            f"- Recent news: {news[:1] if news else 'none surfaced'}\n"
            f"- Industry market stats: {mkt or 'unavailable — do NOT invent stats'}\n\n"
            f"WRITE EXACTLY 3 OPENERS, each in a distinct style:\n\n"
            f"VARIANT 1 — Project-Anchored Direct\n"
            f"  Self-aware honesty (acknowledge it's a cold call but a "
            f"researched one). Anchor on a specific project / open role / "
            f"news item. Two questions ending in 'who's owning the hiring, "
            f"and is it you?'\n\n"
            f"VARIANT 2 — Market-Data Contrarian\n"
            f"  Lead with a market data point (use the fill_window_days "
            f"stat above if available; if NOT available, use a structural "
            f"observation like 'the firms hitting 30 days are running "
            f"parallel passive searches'). Frame their open seats as a "
            f"diagnostic: 'sourcing problem, closing problem, or comp "
            f"problem?'\n\n"
            f"VARIANT 3 — Brief Diagnostic\n"
            f"  ONE question only. Reference a specific company project or "
            f"open role. End with: 'what's harder right now: finding the "
            f"right people, or getting them to say yes?'\n\n"
            f"STRICT RULES:\n"
            f"- Each variant under 80 words.\n"
            f"- Use the recruiter's actual name (placeholder {{recruiter_name}}) "
            f"and firm name (placeholder {{firm_name}}). The UI will substitute "
            f"these at display time.\n"
            f"- Address the prospect by first name only (use placeholder {{first_name}}).\n"
            f"- Do NOT fabricate market stats. If mkt is empty, drop the stat.\n"
            f"- Do NOT use emoji or markdown.\n\n"
            f"Return ONLY valid JSON:\n"
            f'{{"variants":['
            f'{{"style":"project_anchored","label":"Project-Anchored Direct","script":"..."}},'
            f'{{"style":"market_data","label":"Market-Data Contrarian","script":"..."}},'
            f'{{"style":"brief_diagnostic","label":"Brief Diagnostic","script":"..."}}'
            f']}}'
        )
```

After the AI call, parse the JSON response for the `variants` field. Add the parsed list to the returned dict as `result["variants"] = parsed["variants"]`.

Keep the existing `conversation_flow.opener` field populated for backwards compatibility — set it to `result["variants"][0]["script"]` so old UI code still works.

- [ ] **Step 5: Run tests; they MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_call_variants_generation.py -v`

Expected: All 3 PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 277 passed (274 + 3 new).

- [ ] **Step 7: Commit**

```
git add flowdrip_app.py tests/test_call_variants_generation.py
git commit -m "feat(call-briefing): generate 3 style variants per campaign

Replaces the single conversation_flow.opener with 3 distinct style
variants — Project-Anchored / Market-Data / Brief Diagnostic — in
Leigh's pitch DNA (self-aware honesty + specific project anchor +
real market data + diagnostic-question close).

Variants are generated in a single Claude call (one JSON response,
parsed into 3) to keep latency and cost bounded. Market stats are
pulled from the per-industry cache (Task 5) so scripts use real
fill-window data without hallucinating numbers.

Schema version bumped to 3 so old v2 cached briefings auto-
regenerate on first view. The legacy conversation_flow.opener
field is kept (set to variant 1's script) for backwards compat.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Call card UI — pill selector + Copy button

**Files:**
- Modify: `flowdrip_app.py:10686+` (the `_render_call_briefing_card` function)

- [ ] **Step 1: Locate the existing opener display block**

Read `flowdrip_app.py:10686+`. Find the section that displays `conversation_flow.opener` (the current single opener). It's likely a `ui.label` or `ui.html` call inside a styled `ui.element("div")`.

- [ ] **Step 2: Add the pill selector and rewrite the script display**

Above the existing opener display, add a pill row that lets the user pick variant 1/2/3. Below the pill row, render the selected variant's script with a Copy button.

Pseudocode (adapt to actual local variable names — `briefing` is the dict from `_generate_call_briefing_for_campaign`):

```python
        variants = briefing.get("variants") or []
        # Backwards compat: if no variants but conversation_flow.opener
        # exists (legacy v2 cache), synthesize a single variant on the fly.
        if not variants and isinstance(briefing.get("conversation_flow"), dict):
            legacy_opener = briefing["conversation_flow"].get("opener", "")
            if legacy_opener:
                variants = [{"style": "legacy", "label": "Opener", "script": legacy_opener}]

        if variants:
            # Track selection in AppState (one per campaign)
            sel_key = f"_call_variant_{camp.get('name', 'unnamed')}"
            sel_idx = getattr(s, sel_key, 0)
            if sel_idx >= len(variants):
                sel_idx = 0

            # Pill row
            with ui.element("div").style(
                    "display:flex;gap:6px;margin-bottom:10px;"):
                for i, v in enumerate(variants):
                    is_sel = (i == sel_idx)
                    def _pick(idx=i, key=sel_key):
                        setattr(s, key, idx); rf()
                    bg = C["teal"] if is_sel else "transparent"
                    fg = "#fff" if is_sel else C["teal"]
                    border = C["teal"]
                    label = v.get("label", f"Variant {i+1}")
                    with ui.element("button").style(
                            f"padding:5px 12px;border-radius:14px;cursor:pointer;"
                            f"background:{bg};color:{fg};border:1px solid {border};"
                            f"font-size:11px;font-family:inherit;font-weight:600;"
                            ).on("click", _pick):
                        ui.label(label).style("pointer-events:none;")

            # Selected variant body
            sel_v = variants[sel_idx]
            with ui.element("div").style(
                    "display:flex;justify-content:space-between;align-items:flex-start;"
                    "gap:12px;margin-bottom:8px;"):
                ui.html(
                    "<div style='font-size:13px;line-height:1.55;color:#222;"
                    "white-space:pre-wrap;'>"
                    + (sel_v.get("script", "") or "").replace("<", "&lt;").replace(">", "&gt;")
                    + "</div>"
                ).style("flex:1;")
                # Copy button
                _script_text = sel_v.get("script", "") or ""
                _esc_script = _script_text.replace("\\", "\\\\").replace("`", "\\`")
                ui.html(
                    f"<button onclick=\"navigator.clipboard.writeText(`{_esc_script}`); "
                    f"this.textContent='✓ Copied'; "
                    f"setTimeout(()=>this.textContent='⧉ Copy', 1500);\" "
                    f"style='padding:5px 12px;border-radius:6px;border:1px solid {C['teal']};"
                    f"background:transparent;color:{C['teal']};font-size:11px;cursor:pointer;"
                    f"font-family:inherit;flex-shrink:0;'>⧉ Copy</button>"
                )

        # REMOVE or comment out the existing conversation_flow.opener
        # display block — it's superseded by the variants UI above.
```

NOTE: The exact integration depends on the existing card structure. The KEY THINGS:
- Read `briefing.get("variants")`; fall back to legacy `conversation_flow.opener`.
- Track selection in `AppState` keyed by campaign name (so user's pick persists across re-renders).
- Pill row at top, single visible script body below, Copy button next to script.
- Escape `<` and `>` in the script before injecting into HTML.

- [ ] **Step 3: Verify the file still parses**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0.

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 277 passed.

- [ ] **Step 5: Manual smoke (optional but recommended)**

Restart the local NiceGUI server. Open the Today page. Pick a campaign with a generated call briefing. Confirm:
- 3 pill buttons show with correct labels
- Clicking a pill swaps the visible script
- Copy button copies the current variant to clipboard

If you can't run the local server, skip — the static check (parse + tests) is the floor of acceptance.

- [ ] **Step 6: Commit**

```
git add flowdrip_app.py
git commit -m "feat(today): call card now shows 3 style variants with pill selector

Per-card pill row lets the user pick Project-Anchored /
Market-Data / Brief Diagnostic. Selected variant renders below
with a Copy button (clipboard API). Selection persists in AppState
across re-renders.

Backwards compat: campaigns with the legacy conversation_flow.opener
field but no variants array fall back to a single 'Opener' pill.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Voicemail variants generator (user-level)

**Files:**
- Modify: `flowdrip_app.py` — add new generator near the existing call briefing generator (around L37158)
- Add new path helper near `_user_*_path` helpers (around L1024)
- Create: `tests/test_voicemail_variants_generation.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_voicemail_variants_generation.py`:

```python
"""Voicemail variants — user-level (not per-campaign).

The same voicemail script applies to every cold call you make today.
Stored at _resolve_user_root() / "voicemail_scripts.json" with a
24-hour TTL so the user gets fresh variants daily.

Three style variants (same DNA as the call openers): Project-Anchored,
Market-Insight, Brief.
"""
import inspect
import json
import sys


def test_voicemail_path_helper_exists():
    import flowdrip_app as fa
    assert hasattr(fa, "_user_voicemail_scripts_path")


def test_voicemail_generator_exists():
    import flowdrip_app as fa
    assert hasattr(fa, "_generate_voicemail_variants_for_user")


def test_voicemail_prompt_asks_for_three_variants():
    """The prompt must produce 3 voicemail variants in Leigh-style DNA."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_voicemail_variants_for_user)
    assert "voicemail" in src.lower()
    # All 3 style markers
    assert "project_anchored" in src.lower() or "project-anchored" in src.lower()
    assert "market_insight" in src.lower() or "market-insight" in src.lower()
    assert "brief" in src.lower()
    # The prompt must instruct phone-number repetition
    assert "phone" in src.lower() and ("repeat" in src.lower() or "twice" in src.lower())


def test_voicemail_24h_cache_returns_existing(tmp_path, monkeypatch):
    """A voicemail file written in the last 24h should be returned as-is
    without regenerating."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if "flowdrip_app" in sys.modules:
        del sys.modules["flowdrip_app"]
    import flowdrip_app as fa
    fa._CURRENT_USER_EMAIL.set("vm-test@example.com")
    monkeypatch.setattr(fa, "_SERVER_MODE", True)
    # Pre-write a fresh voicemail file
    p = fa._user_voicemail_scripts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    cached = {
        "variants": [
            {"style": "project_anchored", "label": "Project-Anchored", "script": "cached-1"},
            {"style": "market_insight", "label": "Market-Insight", "script": "cached-2"},
            {"style": "brief", "label": "Brief", "script": "cached-3"},
        ],
        "_generated_at": "2026-05-10T12:00:00",
    }
    p.write_text(json.dumps(cached), encoding="utf-8")
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    result = fa._generate_voicemail_variants_for_user(force_refresh=False)
    assert result is not None
    assert len(result["variants"]) == 3
    assert result["variants"][0]["script"] == "cached-1"
```

- [ ] **Step 2: Run tests; they MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_voicemail_variants_generation.py -v`

Expected: All 4 FAIL.

- [ ] **Step 3: Add the per-user voicemail path helper**

Find the per-user path helpers (search for `def _user_pdf_dir` to find the cluster, around L1024-1040). Add this new helper alongside them:

```python
def _user_voicemail_scripts_path():
    return _resolve_user_root() / "voicemail_scripts.json"
```

- [ ] **Step 4: Add the voicemail generator function**

Add this function after `_generate_li_message_for_campaign` (around L37520 area; line will have shifted after Task 6's changes — search for `def _generate_li_message_for_campaign` and put the new function immediately after it):

```python
_VOICEMAIL_TTL_HOURS = 24


def _generate_voicemail_variants_for_user(force_refresh: bool = False) -> dict | None:
    """AI-generate 3 voicemail script variants for the current user.

    Voicemails are user-level (not per-campaign) because the same
    voicemail applies to every cold call you make today. Cached at
    _user_voicemail_scripts_path() with a 24-hour TTL so the user
    gets fresh scripts daily without manual refresh.

    Returns dict like:
        {
          "variants": [
            {"style": "project_anchored", "label": "...", "script": "..."},
            {"style": "market_insight",   "label": "...", "script": "..."},
            {"style": "brief",            "label": "...", "script": "..."}
          ],
          "_generated_at": "2026-05-10T12:00:00"
        }
    or None on failure / missing API key.

    Pass force_refresh=True to bypass cache (used by the Refresh
    button in the UI).
    """
    cache_path = _user_voicemail_scripts_path()
    if not force_refresh and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            gen_at = datetime.fromisoformat(cached.get("_generated_at", ""))
            age_h = (datetime.now() - gen_at).total_seconds() / 3600.0
            if age_h < _VOICEMAIL_TTL_HOURS and cached.get("variants"):
                return cached
        except Exception:
            pass

    if not ANTHROPIC_API_KEY:
        return None
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception as ex:
        print(f"[Voicemail] Anthropic init failed: {ex}", flush=True)
        return None

    # Resolve user context: firm name, recruiter name, phone
    firm = ""
    recruiter_name = ""
    phone_raw = ""
    try:
        firm = (_get_company_name() or "").strip()
    except Exception:
        pass
    try:
        cfg = _load_config()
        recruiter_name = (cfg.get("name") or cfg.get("display_name") or "").strip()
        phone_raw = (cfg.get("phone") or "").strip()
    except Exception:
        pass

    # Format phone for voicemail (digit-by-digit, repeated twice)
    phone_digits = re.sub(r"\D", "", phone_raw)
    if len(phone_digits) == 10:
        phone_spoken = (
            f"{phone_digits[0]}-{phone_digits[1]}-{phone_digits[2]}. "
            f"{phone_digits[3]}-{phone_digits[4]}-{phone_digits[5]}. "
            f"{phone_digits[6]}-{phone_digits[7]}-{phone_digits[8]}-{phone_digits[9]}"
        )
        phone_block = f"{phone_spoken}. {phone_spoken}."
    else:
        phone_block = "[no phone configured — add one in My Profile]"

    # Pull user's industry context to anchor market-insight variant
    sector = ""
    try:
        sector = (cfg.get("industry") or cfg.get("sector") or "").strip()
    except Exception:
        pass
    mkt = _market_stats_for_industry(sector) if sector else None

    prompt = (
        f"Write 3 voicemail scripts for a recruiter named {recruiter_name or '[name]'} "
        f"at {firm or '[firm]'}, calling cold prospects in the {sector or 'staffing'} industry.\n\n"
        f"CONTEXT:\n"
        f"- Recruiter: {recruiter_name or '[name]'}\n"
        f"- Firm: {firm or '[firm]'}\n"
        f"- Industry: {sector or 'staffing'}\n"
        f"- Market stats: {mkt or 'unavailable — do NOT invent stats'}\n"
        f"- Phone (already formatted for voicemail readback): {phone_block}\n\n"
        f"WRITE EXACTLY 3 VOICEMAIL SCRIPTS, each in a distinct style:\n\n"
        f"VARIANT 1 — Project-Anchored\n"
        f"  Lead with name and firm. Reference the recruiter's project mix "
        f"in 1 sentence. End with phone twice. Under 30 seconds spoken.\n\n"
        f"VARIANT 2 — Market-Insight\n"
        f"  Lead with name and firm. Drop the market stat (use fill_window_days "
        f"if available; otherwise use a structural observation). End with phone "
        f"twice. Under 30 seconds.\n\n"
        f"VARIANT 3 — Brief\n"
        f"  Lead with name and firm. State briefly what your firm does and "
        f"that it lines up with their hiring profile. End with phone twice. "
        f"Under 20 seconds. THIS IS THE SHORTEST VARIANT.\n\n"
        f"STRICT RULES:\n"
        f"- ALL 3 must end with the phone number repeated twice EXACTLY as "
        f"provided in the phone block above.\n"
        f"- Do NOT use {{first_name}} placeholders — voicemails are name-agnostic.\n"
        f"- Do NOT fabricate market stats. Drop the stat if mkt is empty.\n"
        f"- Do NOT use emoji or markdown.\n\n"
        f"Return ONLY valid JSON:\n"
        f'{{"variants":['
        f'{{"style":"project_anchored","label":"Project-Anchored","script":"..."}},'
        f'{{"style":"market_insight","label":"Market-Insight","script":"..."}},'
        f'{{"style":"brief","label":"Brief","script":"..."}}'
        f']}}'
    )
    try:
        msg = _claude_create_with_retry(client,
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
    except Exception as ex:
        print(f"[Voicemail] AI call failed: {ex}", flush=True)
        return None

    # Extract JSON from response
    try:
        m = re.search(r'\{[\s\S]*\}', text)
        if not m:
            return None
        parsed = json.loads(m.group(0))
        variants = parsed.get("variants") or []
        if len(variants) != 3:
            return None
    except Exception:
        return None

    out = {
        "variants": variants,
        "_generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    # Persist
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
        tmp.replace(cache_path)
    except Exception as ex:
        print(f"[Voicemail] persist failed: {ex}", flush=True)
    return out
```

NOTE: This depends on `_get_company_name()`, `_load_config()`, `_market_stats_for_industry()` (Task 5), `_claude_create_with_retry()`, and `re` (already imported). If `_load_config()` or `_get_company_name()` aren't the exact function names in this codebase, grep to find the right ones and adjust.

- [ ] **Step 5: Run tests; they MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_voicemail_variants_generation.py -v`

Expected: All 4 PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 281 passed (277 + 4 new).

- [ ] **Step 7: Commit**

```
git add flowdrip_app.py tests/test_voicemail_variants_generation.py
git commit -m "feat(voicemail): user-level 3-variant voicemail generator

Voicemails are stored per-user (not per-campaign) at
_user_voicemail_scripts_path() with a 24-hour TTL. The same
voicemail applies to every cold call you make today.

Three variants in Leigh's DNA: Project-Anchored, Market-Insight,
Brief. Each ends with the recruiter's phone number repeated twice
in voicemail-readback format. Phone is pulled from the user's
config; if missing, a placeholder prompts them to set one in
My Profile.

Market stats (Task 5) feed the Market-Insight variant. If the
cache is empty for the user's industry, the prompt explicitly
instructs the AI to drop the stat rather than invent one.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Voicemail block at top of Today calls section

**Files:**
- Modify: `flowdrip_app.py` — find the Today page calls section. Run: `grep -n "_render_call_briefing_card\|today.*call\|p_today" flowdrip_app.py | head -10` to locate the calling site.

- [ ] **Step 1: Identify the calls-section render function**

The Today page renders multiple call cards in a loop. Find the function that wraps that loop (likely `p_today` or a helper called by it). Read 50 lines around the loop to understand the section structure.

- [ ] **Step 2: Add a voicemail block above the call-card loop**

Insert this rendering block IMMEDIATELY before the loop that renders per-campaign call cards:

```python
        # ── Today's Voicemail Script (user-level, applies to all calls today) ──
        from datetime import datetime as _dt
        vm_data = getattr(s, "_today_voicemail", None)

        # Lazy-load: hit the helper once per render. The helper is
        # cached on disk with a 24h TTL so this is cheap after the
        # first call of the day.
        if vm_data is None:
            try:
                vm_data = _generate_voicemail_variants_for_user(force_refresh=False)
                s._today_voicemail = vm_data
            except Exception as ex:
                print(f"[TodayVoicemail] load failed: {ex}", flush=True)

        if vm_data and vm_data.get("variants"):
            vm_variants = vm_data["variants"]
            sel_key = "_voicemail_variant_idx"
            sel_idx = getattr(s, sel_key, 0)
            if sel_idx >= len(vm_variants):
                sel_idx = 0

            with ui.element("div").style(
                    f"background:#fff;border:1px solid #E5E7EB;border-left:4px solid {C['teal']};"
                    f"border-radius:10px;padding:18px 22px;margin-bottom:24px;"):
                # Header
                with ui.element("div").style(
                        "display:flex;justify-content:space-between;align-items:center;"
                        "margin-bottom:10px;"):
                    ui.label("Today's Voicemail Script").style(
                        f"font-size:14px;font-weight:700;color:{C['ink']};")
                    # Refresh button
                    def _refresh_vm():
                        try:
                            s._today_voicemail = _generate_voicemail_variants_for_user(force_refresh=True)
                            ui.notify("Voicemail scripts refreshed.", type="positive")
                            rf()
                        except Exception as ex:
                            ui.notify(f"Refresh failed: {ex}", type="negative")
                    with ui.element("button").style(
                            f"padding:4px 10px;font-size:11px;border-radius:6px;"
                            f"border:1px solid {C['muted']};background:transparent;"
                            f"color:{C['muted']};cursor:pointer;font-family:inherit;"
                            ).on("click", _refresh_vm):
                        ui.label("↻ Refresh").style("pointer-events:none;")

                # Pill row
                with ui.element("div").style(
                        "display:flex;gap:6px;margin-bottom:10px;"):
                    for i, v in enumerate(vm_variants):
                        is_sel = (i == sel_idx)
                        def _pick(idx=i):
                            s._voicemail_variant_idx = idx; rf()
                        bg = C["teal"] if is_sel else "transparent"
                        fg = "#fff" if is_sel else C["teal"]
                        label = v.get("label", f"Variant {i+1}")
                        with ui.element("button").style(
                                f"padding:5px 12px;border-radius:14px;cursor:pointer;"
                                f"background:{bg};color:{fg};border:1px solid {C['teal']};"
                                f"font-size:11px;font-family:inherit;font-weight:600;"
                                ).on("click", _pick):
                            ui.label(label).style("pointer-events:none;")

                # Script body + Copy button
                sel_v = vm_variants[sel_idx]
                with ui.element("div").style(
                        "display:flex;justify-content:space-between;align-items:flex-start;"
                        "gap:12px;"):
                    ui.html(
                        "<div style='font-size:13px;line-height:1.55;color:#222;"
                        "white-space:pre-wrap;'>"
                        + (sel_v.get("script", "") or "").replace("<", "&lt;").replace(">", "&gt;")
                        + "</div>"
                    ).style("flex:1;")
                    _esc = (sel_v.get("script", "") or "").replace("\\", "\\\\").replace("`", "\\`")
                    ui.html(
                        f"<button onclick=\"navigator.clipboard.writeText(`{_esc}`); "
                        f"this.textContent='✓ Copied'; "
                        f"setTimeout(()=>this.textContent='⧉ Copy', 1500);\" "
                        f"style='padding:5px 12px;border-radius:6px;border:1px solid {C['teal']};"
                        f"background:transparent;color:{C['teal']};font-size:11px;cursor:pointer;"
                        f"font-family:inherit;flex-shrink:0;'>⧉ Copy</button>"
                    )
```

- [ ] **Step 3: Verify the file still parses**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0.

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 281 passed.

- [ ] **Step 5: Commit**

```
git add flowdrip_app.py
git commit -m "feat(today): voicemail script block at top of calls section

Single block (not per-card) since the same voicemail applies to
every cold call. 3 pill-selected style variants with Copy + Refresh.
Lazy-loads on first render, then re-uses the s._today_voicemail
cache for subsequent renders within the session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: LinkedIn 3-variant generator + card UI

**Files:**
- Modify: `flowdrip_app.py:37425+` (the `_generate_li_message_for_campaign` function)
- Modify: `flowdrip_app.py:10997+` (the `_render_li_message_card` function)
- Create: `tests/test_li_variants_generation.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_li_variants_generation.py`:

```python
"""LinkedIn message variants — per-campaign (like the call card).

Three style variants in Leigh-style DNA: Project-Anchored,
Market-Data, Brief Diagnostic. Stored on the campaign as
linkedin_variants (list of dicts). Legacy single-string
linkedin_message field is retained for backwards compat (set to
variant 1's message).
"""
import inspect


def test_li_prompt_asks_for_three_variants():
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_li_message_for_campaign)
    assert "project_anchored" in src.lower() or "project-anchored" in src.lower()
    assert "market_data" in src.lower() or "market-data" in src.lower()
    assert "brief" in src.lower() and ("diagnostic" in src.lower() or "direct" in src.lower())


def test_li_returns_variants_list():
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_li_message_for_campaign)
    assert "linkedin_variants" in src or "li_variants" in src or '"variants"' in src or "'variants'" in src


def test_li_card_renders_pill_selector():
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_li_message_card)
    # The card must read variants and show pill buttons
    assert "variants" in src.lower()
    assert "pill" in src.lower() or "_pick" in src or "_li_variant_" in src
```

- [ ] **Step 2: Run tests; they MUST fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_li_variants_generation.py -v`

Expected: All 3 FAIL.

- [ ] **Step 3: Update `_generate_li_message_for_campaign` to produce 3 variants**

Replace the function's prompt-and-parse block with a 3-variant generation. The function signature stays the same (returns a string for backwards compat), but it ALSO writes the full variants list to `camp["linkedin_variants"]` as a side effect.

Build the prompt similar to the call-variants prompt at Task 6. Pull market stats via `_market_stats_for_industry(sector or niche)`. The 3 LI variants are:

- **Variant 1 — Project-Anchored Direct:** "Just sent you an email re: [topic]. Saw [project / open role]. Worth 15 min if you're hiring around it?"
- **Variant 2 — Market-Data Contrarian:** "Quick note — [fill_window stat or structural observation]. With your project mix, are open seats a sourcing or closing problem? (Sent an email a moment ago.)"
- **Variant 3 — Brief Diagnostic:** "One question — what's harder right now: finding the right people, or getting them to say yes?"

Each must stay under 280 chars (LinkedIn cap on connection notes). Return JSON:

```python
li_prompt = (
    f"Write 3 LinkedIn connection-request messages for a recruiter "
    f"following up on an email already sent. Each in a distinct style.\n\n"
    f"CONTEXT:\n"
    f"- Sender works at: {sender_firm or '[firm]'}\n"
    f"- Recruiter focuses on: {topic} hires in {region or 'their market'}\n"
    f"- Industry market stats: {mkt or 'unavailable — do NOT invent stats'}\n\n"
    f"VARIANT 1 — Project-Anchored Direct\n"
    f"  Reference the email. Anchor on a specific project or open role "
    f"if context allows; otherwise on the topic. Soft close.\n\n"
    f"VARIANT 2 — Market-Data Contrarian\n"
    f"  Lead with a market data point if mkt is non-empty; otherwise "
    f"with a structural observation. Frame as a quick diagnostic.\n\n"
    f"VARIANT 3 — Brief Diagnostic\n"
    f"  ONE question only. End with the diagnostic: 'finding the right "
    f"people, or getting them to say yes?'\n\n"
    f"STRICT RULES:\n"
    f"- Each variant under 280 characters (LinkedIn connection-note cap).\n"
    f"- No 'Hi {{first_name}}' (LinkedIn shows the name automatically).\n"
    f"- No sign-off ('Best,' etc.).\n"
    f"- Casual, peer-to-peer tone. No emoji.\n"
    f"- Do NOT fabricate market stats. Drop the stat if mkt is empty.\n\n"
    f"Return ONLY valid JSON:\n"
    f'{{"variants":['
    f'{{"style":"project_anchored","label":"Project-Anchored","message":"..."}},'
    f'{{"style":"market_data","label":"Market-Data","message":"..."}},'
    f'{{"style":"brief_diagnostic","label":"Brief","message":"..."}}'
    f']}}'
)
```

After parsing the response, set `camp["linkedin_variants"] = parsed["variants"]` AND set `camp["linkedin_message"] = variants[0]["message"]` (legacy field, for backwards compat). Save the campaign.

The function should still return the string from `linkedin_message` so the existing call sites that expect a string don't break.

- [ ] **Step 4: Update `_render_li_message_card` to show 3 variants**

In `_render_li_message_card` at L10997+, find the section that displays the cached `camp["linkedin_message"]`. Replace with a pill-selector block that reads from `camp.get("linkedin_variants")` (with legacy fallback to a single `linkedin_message` rendered as variant 1).

The pattern is nearly identical to Task 7's call card pill-selector — copy that block and adapt the variable names: `s._li_variant_<campname>` for the selection key, `variants[i]["message"]` for the body.

- [ ] **Step 5: Run tests; they MUST pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_li_variants_generation.py -v`

Expected: All 3 PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 284 passed (281 + 3 new).

- [ ] **Step 7: Commit**

```
git add flowdrip_app.py tests/test_li_variants_generation.py
git commit -m "feat(linkedin): 3-variant LinkedIn message generator + card UI

Replaces the single linkedin_message string with a 3-variant list
in Leigh-style DNA: Project-Anchored / Market-Data / Brief
Diagnostic. Each variant respects the 280-char LinkedIn cap and
drops market stats if the industry cache is empty (no
hallucinated numbers).

Card UI gets the same pill-selector + Copy treatment as the call
card. Selection persists per-campaign in AppState.

Backwards compat: legacy linkedin_message field is kept (set to
variant 1's message) so existing campaigns with only the legacy
field still render as a single 'Message' variant on first view.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Final integration — full-suite run + manual smoke

- [ ] **Step 1: Run the full project test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 284 passed (or whatever total accumulated through tasks 1-10).

- [ ] **Step 2: AST parse check**

Run: `python -c "import ast; ast.parse(open('flowdrip_app.py', encoding='utf-8').read())"`

Expected: Exit 0.

- [ ] **Step 3: Audit-test for raw thread spawns (Phase 0 regression net)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_audit_no_raw_per_user_threads.py -v`

Expected: PASS. Any new bg threads added in this plan must use `_run_as_user`.

- [ ] **Step 4: Manual smoke (skip if you can't run local server)**

Per the project's CLAUDE.md and memory `feedback_no_local_run.md`, do NOT start the local server here. Smoke test will happen post-deploy on dripdripdrop.ai.

- [ ] **Step 5: Final commit (if anything trailing)**

If there are no trailing changes, skip. Otherwise:

```
git add -A
git commit -m "chore: integration cleanup post touchpoint quality pass"
```

---

## Self-review checklist

- **Spec coverage:**
  - Phase A.1 (Free Flow AICB prompt): Task 1 ✓
  - Phase A.2 (Recruiting Sequence generator): Task 2 ✓
  - Phase A.3 (Free Flow wizard guardrails): Task 3 ✓
  - Phase A.4 (Victory Card delay tweak): Task 4 ✓
  - Phase B.1 (Market stats cache): Task 5 ✓
  - Phase B.2 (Call 3 variants prompt + parser): Task 6 ✓
  - Phase B.3 (Call card pill selector + Copy): Task 7 ✓
  - Phase B.4 (Voicemail user-level generator): Task 8 ✓
  - Phase B.5 (Voicemail block at top of Today calls): Task 9 ✓
  - Phase B.6 (LinkedIn 3 variants prompt + parser): Task 10 ✓
  - Phase B.7 (LI card pill selector + Copy): Task 10 ✓ (same task)
  - Existing campaigns NOT migrated: ✓ (no migration tasks; explicitly out of scope)
- **Placeholder scan:** No TBD/TODO/"add appropriate handling" — all code blocks complete.
- **Type consistency:**
  - Variant dict shape: `{"style": str, "label": str, "script"|"message": str}` — used consistently across call (Task 6, 7), voicemail (Task 8, 9), LI (Task 10).
  - Storage keys: `call_variants` (on campaign), `voicemail_scripts.json` (per-user file), `linkedin_variants` (on campaign) — all distinct, no collisions.
  - Cache helpers: `_market_stats_for_industry(industry)`, `_user_voicemail_scripts_path()`, `_load_market_stats_cache()`, `_save_market_stats_cache()`, `_generate_voicemail_variants_for_user(force_refresh=False)` — consistent naming.
- **Phase 0 regression net:** Task 11 Step 3 explicitly runs `test_audit_no_raw_per_user_threads.py` to ensure no new raw thread spawns with per-user writes have been introduced.

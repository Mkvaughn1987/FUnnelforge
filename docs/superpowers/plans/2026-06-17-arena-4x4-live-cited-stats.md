# Arena 4×4: Live Cited Market Stats — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anchor Arena 4×4 Email 2 and Email 4 in real, sourced market numbers pulled by a live web search at build time, each shown with a "Source: ..." line, instead of model-recalled (hallucination-prone) stats.

**Architecture:** Four small functions in `flowdrip_app.py` — a prompt builder, a strict JSON parser, a block formatter, and a web-search orchestrator — plus a gated call site in the 4×4 campaign build that injects the resulting block into `campaign_prompt`. The three pure helpers are unit-tested; the orchestrator returns `[]` on any failure so a build never breaks.

**Tech Stack:** Python 3, `pytest`, Anthropic SDK web-search tool (`_safe_web_search_tool`), NiceGUI app (`flowdrip_app.py`).

Spec: `docs/superpowers/specs/2026-06-17-arena-4x4-live-cited-stats-design.md`

---

## File Structure

- Modify: `flowdrip_app.py`
  - Add `payscale.com` to `_WEB_SEARCH_DOMAINS` (~L8434-8445).
  - Add `_cited_stats_prompt`, `_parse_cited_stats`, `_format_cited_stats_block`, `_fetch_cited_market_stats` near the existing market-stats helpers (just after `_market_stats_for_industry`, ~L1103).
  - Gated call site + prompt injection in the 4×4 build (insert before `campaign_prompt = (` at ~L33672, and add `+ _stats_block +` after `_cand_block` at ~L33682).
- Test: `tests/test_arena_4x4_cited_stats.py` (new)

**Implementation note (injection defense):** The cited-stats block is injected as authoritative instruction text, NOT wrapped in `_wrap_untrusted`. Wrapping would dilute the "use ONLY these" instruction, and the facts already come from the domain-locked `_safe_web_search_tool` allowlist. This matches how the existing `_market_stats_for_industry` injects search results into call-script prompts.

---

## Task 1: `_cited_stats_prompt` — build the web-search prompt

**Files:**
- Modify: `flowdrip_app.py` (add after `_market_stats_for_industry`, ~L1103)
- Test: `tests/test_arena_4x4_cited_stats.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_arena_4x4_cited_stats.py`:

```python
"""Live cited market-stats helpers for the Arena 4x4 campaign.

Spec: docs/superpowers/specs/2026-06-17-arena-4x4-live-cited-stats-design.md
Plan: docs/superpowers/plans/2026-06-17-arena-4x4-live-cited-stats.md
"""
import flowdrip_app as fa


# ── _cited_stats_prompt ────────────────────────────────────────────
def test_cited_stats_prompt_includes_role_location_industry():
    p = fa._cited_stats_prompt("Construction Foreman", "Phoenix, AZ",
                               "construction")
    assert "Construction Foreman" in p
    assert "Phoenix, AZ" in p
    assert "construction" in p


def test_cited_stats_prompt_requests_shape_and_forbids_fabrication():
    p = fa._cited_stats_prompt("Estimator", "Denver, CO", "construction")
    assert '"fact"' in p
    assert '"source"' in p
    # must tell the model not to invent numbers
    assert "fabricat" in p.lower() or "do not invent" in p.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_arena_4x4_cited_stats.py -q`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_cited_stats_prompt'`

- [ ] **Step 3: Implement `_cited_stats_prompt`**

Add after the end of `_market_stats_for_industry` (after ~L1103):

```python
def _cited_stats_prompt(role, location, industry):
    """Build the web-search prompt for real, sourced hiring-market stats.

    Asks for 3-5 current US facts relevant to the role/location/industry,
    each a concrete number plus a clean source label (publisher + year),
    in a strict JSON shape. Explicitly forbids fabrication.
    """
    role = (role or "the target role").strip()
    location = (location or "the United States").strip()
    industry = (industry or "this industry").strip()
    return (
        f"Use web_search to find 3 to 5 CURRENT (2025-2026) US "
        f"hiring-market facts relevant to {role} roles in {location} "
        f"within the {industry} industry. Search bls.gov, indeed.com, "
        f"glassdoor.com, linkedin.com, payscale.com, and census.gov. "
        f"Each fact must be a specific, verifiable number (a salary band, "
        f"unemployment rate, jobs-added figure, fill-time, or wage-growth "
        f"percentage) that you actually found in the search results.\n\n"
        f"Do NOT fabricate or estimate. If you did not find a real number "
        f"in a source, leave it out. Return ONLY valid JSON in this exact "
        f"shape:\n"
        f'{{"stats":[{{"fact":"<one sentence with the number>",'
        f'"source":"<publisher name and year, e.g. Bureau of Labor '
        f'Statistics, 2026>"}}]}}\n\n'
        f'If you found nothing verifiable, return {{"stats":[]}}.'
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_arena_4x4_cited_stats.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_arena_4x4_cited_stats.py flowdrip_app.py
git commit -m "feat(4x4): add _cited_stats_prompt web-search prompt builder"
```

---

## Task 2: `_parse_cited_stats` — strict JSON parser that drops uncited facts

**Files:**
- Modify: `flowdrip_app.py` (add after `_cited_stats_prompt`)
- Test: `tests/test_arena_4x4_cited_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_arena_4x4_cited_stats.py`:

```python
# ── _parse_cited_stats ─────────────────────────────────────────────
def test_parse_valid_stats():
    text = ('{"stats":[{"fact":"Unemployment in construction is 4.3%",'
            '"source":"BLS, 2026"}]}')
    out = fa._parse_cited_stats(text)
    assert out == [{"fact": "Unemployment in construction is 4.3%",
                    "source": "BLS, 2026"}]


def test_parse_drops_fact_without_source():
    text = ('{"stats":[{"fact":"Wages up 5%","source":""},'
            '{"fact":"Fill time is 47 days","source":"Indeed, 2026"}]}')
    out = fa._parse_cited_stats(text)
    assert out == [{"fact": "Fill time is 47 days",
                    "source": "Indeed, 2026"}]


def test_parse_drops_empty_fact():
    text = '{"stats":[{"fact":"   ","source":"BLS, 2026"}]}'
    assert fa._parse_cited_stats(text) == []


def test_parse_handles_code_fences():
    text = ('```json\n{"stats":[{"fact":"Base $130K","source":'
            '"Payscale, 2026"}]}\n```')
    out = fa._parse_cited_stats(text)
    assert out == [{"fact": "Base $130K", "source": "Payscale, 2026"}]


def test_parse_junk_returns_empty_list():
    assert fa._parse_cited_stats("no json here") == []
    assert fa._parse_cited_stats("") == []
    assert fa._parse_cited_stats(None) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_arena_4x4_cited_stats.py -k parse -q`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_parse_cited_stats'`

- [ ] **Step 3: Implement `_parse_cited_stats`**

Add after `_cited_stats_prompt`:

```python
def _parse_cited_stats(text):
    """Parse the web-search response into a validated stats list.

    Returns a list of {"fact": str, "source": str}. Strips ```json
    fences. Drops any entry whose fact OR source is empty/whitespace, so
    an uncited number can never reach an email. Returns [] on junk.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    clean = text.replace("```json", "").replace("```", "").strip()
    m = re.search(r'\{.*\}', clean, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    raw = data.get("stats") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fact = str(item.get("fact", "") or "").strip()
        source = str(item.get("source", "") or "").strip()
        if fact and source:
            out.append({"fact": fact, "source": source})
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_arena_4x4_cited_stats.py -k parse -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_arena_4x4_cited_stats.py flowdrip_app.py
git commit -m "feat(4x4): add _parse_cited_stats strict parser (drops uncited facts)"
```

---

## Task 3: `_format_cited_stats_block` — render the prompt block

**Files:**
- Modify: `flowdrip_app.py` (add after `_parse_cited_stats`)
- Test: `tests/test_arena_4x4_cited_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_arena_4x4_cited_stats.py`:

```python
# ── _format_cited_stats_block ──────────────────────────────────────
def test_format_block_non_empty_lists_facts_and_sources():
    stats = [{"fact": "Fill time is 47 days", "source": "Indeed, 2026"},
             {"fact": "Base $130K to $150K", "source": "Payscale, 2026"}]
    block = fa._format_cited_stats_block(stats)
    assert "Fill time is 47 days" in block
    assert "Indeed, 2026" in block
    assert "Base $130K to $150K" in block
    assert "Payscale, 2026" in block
    assert "ONLY these" in block
    assert "Email 2" in block and "Email 4" in block


def test_format_block_empty_forbids_numbers():
    block = fa._format_cited_stats_block([])
    assert "no specific" in block.lower() or "no numbers" in block.lower()
    assert "Source:" not in block
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_arena_4x4_cited_stats.py -k format -q`
Expected: FAIL with `AttributeError: module 'flowdrip_app' has no attribute '_format_cited_stats_block'`

- [ ] **Step 3: Implement `_format_cited_stats_block`**

Add after `_parse_cited_stats`:

```python
def _format_cited_stats_block(stats):
    """Render the cited-stats instruction block for the 4x4 prompt.

    Non-empty: list each verified fact with its source and require the
    model to use ONLY these in Email 2 and Email 4, each closed with a
    "Source: <source>" line. Empty: forbid specific figures so the
    emails degrade to qualitative observations with zero fabrication.
    """
    if not stats:
        return (
            "\nVERIFIED MARKET STATS: none were found for this search. "
            "In Email 2 and Email 4, write qualitative market observations "
            "only. Do NOT include any specific figures, percentages, "
            "salary numbers, or stats of any kind.\n\n"
        )
    lines = []
    for st in stats:
        lines.append(f'- {st["fact"]} (Source: {st["source"]})')
    facts = "\n".join(lines)
    return (
        "\nVERIFIED MARKET STATS (real, sourced numbers from web search):\n"
        f"{facts}\n"
        "Use ONLY these stats in Email 2 (Top Talent Insights) and "
        "Email 4 (Market Trends). Weave each into a sentence and close it "
        "with its source as 'Source: <source>'. Do NOT invent any other "
        "number, percentage, or salary figure. Do NOT reuse the same stat "
        "in both emails if more than one is available.\n\n"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_arena_4x4_cited_stats.py -k format -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_arena_4x4_cited_stats.py flowdrip_app.py
git commit -m "feat(4x4): add _format_cited_stats_block prompt renderer"
```

---

## Task 4: `payscale.com` in the search allowlist + `_fetch_cited_market_stats`

**Files:**
- Modify: `flowdrip_app.py` (`_WEB_SEARCH_DOMAINS` ~L8444; add `_fetch_cited_market_stats` after `_format_cited_stats_block`)
- Test: `tests/test_arena_4x4_cited_stats.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_arena_4x4_cited_stats.py`:

```python
# ── allowlist ──────────────────────────────────────────────────────
def test_payscale_in_web_search_allowlist():
    assert "payscale.com" in fa._WEB_SEARCH_DOMAINS
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_arena_4x4_cited_stats.py -k payscale -q`
Expected: FAIL (`assert 'payscale.com' in [...]`)

- [ ] **Step 3: Add payscale.com to the allowlist**

Edit `_WEB_SEARCH_DOMAINS` (~L8443-8444):

Old:
```python
    # Government / labor data
    "bls.gov", "sba.gov", "census.gov",
]
```
New:
```python
    # Government / labor data
    "bls.gov", "sba.gov", "census.gov",
    # Compensation data
    "payscale.com",
]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_arena_4x4_cited_stats.py -k payscale -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Implement `_fetch_cited_market_stats` (orchestrator, no unit test — it does live I/O)**

Add after `_format_cited_stats_block`:

```python
def _fetch_cited_market_stats(role, location, industry):
    """Live web search for real, sourced hiring-market stats.

    Returns a list of {"fact", "source"} (possibly empty). Returns []
    on any failure (no API key, search error, parse failure) so the
    campaign build never blocks or crashes.
    """
    if not ANTHROPIC_API_KEY:
        return []
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception as ex:
        print(f"[CitedStats] Anthropic init failed: {ex}", flush=True)
        return []
    try:
        msg = _claude_create_with_retry(client,
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            tools=[_safe_web_search_tool(max_uses=4)],
            messages=[{"role": "user", "content":
                       _cited_stats_prompt(role, location, industry)}])
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
    except Exception as ex:
        print(f"[CitedStats] web search failed: {ex}", flush=True)
        return []
    return _parse_cited_stats(text)
```

- [ ] **Step 6: Verify the module imports cleanly**

Run: `python -c "import flowdrip_app; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add tests/test_arena_4x4_cited_stats.py flowdrip_app.py
git commit -m "feat(4x4): add payscale allowlist + _fetch_cited_market_stats orchestrator"
```

---

## Task 5: Wire the cited-stats block into the 4×4 build prompt

**Files:**
- Modify: `flowdrip_app.py` (insert before `campaign_prompt = (` ~L33672; add `+ _stats_block +` after `_cand_block` ~L33682)

This is the integration step. The three preceding tasks are inert until
the block is injected here, gated to the 4×4 campaign type.

- [ ] **Step 1: Compute the stats block before the prompt**

Find the line `campaign_prompt = (` (search the exact string `campaign_prompt = (`; it appears twice — use the FIRST occurrence, inside the AICB build worker, currently ~L33672, the one immediately preceded by the `_cand_block` elif chain). Insert directly above it:

```python
                        # 4x4 only: live web search for real, cited market
                        # stats so Email 2 and Email 4 use sourced numbers
                        # instead of model-recalled (hallucination-prone)
                        # figures. Returns "" for every other campaign type.
                        _stats_block = ""
                        if (s.aicb_camp_type or "").strip() == "fourbyfour":
                            _cited = _fetch_cited_market_stats(
                                _first_role or (getattr(s, "cpc_ad_role", "") or ""),
                                location_str or (getattr(s, "cpc_ad_location", "") or ""),
                                niche_str or roles_str or "")
                            _stats_block = _format_cited_stats_block(_cited)

```

- [ ] **Step 2: Inject the block into the prompt**

In the same `campaign_prompt = ( ... )` assignment, find the line:
```python
                            + _cand_block +
```
Replace it with:
```python
                            + _cand_block +
                            _stats_block +
```

- [ ] **Step 3: Verify the module imports cleanly**

Run: `python -c "import flowdrip_app; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Run the full cited-stats test file**

Run: `python -m pytest tests/test_arena_4x4_cited_stats.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(4x4): inject live cited market stats into Email 2 and Email 4"
```

---

## Final verification

- [ ] **Run both 4×4 test files + a neighbor**

Run: `python -m pytest tests/test_arena_4x4_cited_stats.py tests/test_arena_4x4_voice.py tests/test_sb_helpers.py -q`
Expected: all PASS.

- [ ] **Import smoke**

Run: `python -c "import flowdrip_app; print('ok')"`
Expected: `ok`

---

## Self-Review (completed by plan author)

- **Spec coverage:** `_cited_stats_prompt` -> Task 1; `_parse_cited_stats` (drops uncited) -> Task 2; `_format_cited_stats_block` (both states) -> Task 3; `payscale.com` allowlist + `_fetch_cited_market_stats` (returns [] on failure) -> Task 4; gated 4×4 wiring + injection -> Task 5. Error handling (empty -> no-numbers) covered by Tasks 3 + 4. All spec sections mapped.
- **Deviation from spec (noted):** the block is injected as authoritative instruction text, not wrapped in `_wrap_untrusted`, to avoid diluting the "use ONLY these" instruction; the domain-locked search is the injection defense, matching `_market_stats_for_industry`. Documented in File Structure above.
- **Placeholder scan:** none; every step has concrete code/commands.
- **Type consistency:** `_cited_stats_prompt(role, location, industry)`, `_parse_cited_stats(text) -> list[{fact,source}]`, `_format_cited_stats_block(stats)`, `_fetch_cited_market_stats(role, location, industry)`, and `_stats_block` referenced identically across tasks.

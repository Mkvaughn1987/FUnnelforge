# Campaign Create + Launch API (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `POST /api/v1/campaigns` so an external agent can create + launch a full AICB campaign (e.g. Arena 4×4) in one authenticated call, using the same AI generation the wizard uses.

**Architecture:** Add per-user API-key auth (hashed key → owner email), extract the wizard's research+generate+post-process core into a headless `generate_aicb_campaign()` that both the wizard and the API call, and add a FastAPI route that validates a spec, generates, then `save_campaign` + `queue_campaign_emails` under the key's owner. Cadence = `start_date` + each step's template `delay_days`.

**Tech Stack:** Python, FastAPI (via NiceGUI's `app`), Anthropic SDK, pytest + FastAPI `TestClient`. Run tests with `./.venv/Scripts/python.exe -m pytest`.

**Spec:** `docs/superpowers/specs/2026-06-27-campaign-create-launch-api-design.md`

**Conventions:** `flowdrip_app.py` is ~50k lines; locate edit points by the anchors named in each task (function names / unique strings), not by absolute line numbers. New helpers go near related existing code; the route goes with the other `@app.get`/`@app.post` raw routes near the top of the file (after `/healthz`, ~L209).

---

### Task 1: API-key store + helpers

**Files:**
- Modify: `flowdrip_app.py` (add helpers; place them just after the `save_campaign` definition for proximity to other per-user data helpers)
- Test: `tests/test_campaign_api.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_campaign_api.py`:

```python
"""Campaign create+launch API — Phase 1.

Spec: docs/superpowers/specs/2026-06-27-campaign-create-launch-api-design.md
Plan: docs/superpowers/plans/2026-06-27-campaign-create-launch-api.md
"""
import importlib
import flowdrip_app as fa


def _isolate_keys(tmp_path, monkeypatch):
    """Point the API-key store at a temp file so tests never touch real data."""
    store = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: store)
    return store


# ── API key mint / resolve ─────────────────────────────────────────
def test_mint_then_resolve_returns_email(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com", label="cowork")
    assert key.startswith("dd_live_")
    assert fa._resolve_api_key(key) == "rep@arena.com"


def test_resolve_unknown_key_is_none(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    fa._mint_api_key("rep@arena.com")
    assert fa._resolve_api_key("dd_live_bogus") is None
    assert fa._resolve_api_key("") is None
    assert fa._resolve_api_key(None) is None


def test_plaintext_key_never_stored(tmp_path, monkeypatch):
    store = _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    raw = store.read_text(encoding="utf-8")
    assert key not in raw            # only the hash is persisted
    assert fa._hash_api_key(key) in raw
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py -v`
Expected: FAIL — `AttributeError: module 'flowdrip_app' has no attribute '_api_keys_path'`.

- [ ] **Step 3: Implement the helpers**

In `flowdrip_app.py`, immediately after the `save_campaign` function, add (`hashlib` and `secrets` are already imported at the top of the file; `_DATA_DIR`/data-root resolution — use the same root the user-data dirs derive from; if a `_data_root()` or similar exists use it, otherwise resolve `Path(os.environ.get("DRIPDROP_DATA", str(_APP_DIR / "data")))`):

```python
def _api_keys_path() -> Path:
    """Global API-key store: sha256(key) -> {email, label, created}."""
    root = Path(os.environ.get("DRIPDROP_DATA", str(_APP_DIR / "data")))
    root.mkdir(parents=True, exist_ok=True)
    return root / "api_keys.json"


def _hash_api_key(key: str) -> str:
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()


def _load_api_keys() -> dict:
    p = _api_keys_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _mint_api_key(email: str, label: str = "") -> str:
    """Generate a new API key for `email`, persist its hash, return the plaintext once."""
    key = "dd_live_" + secrets.token_urlsafe(32)
    data = _load_api_keys()
    data[_hash_api_key(key)] = {
        "email": (email or "").strip().lower(),
        "label": label or "",
        "created": datetime.now().isoformat(),
    }
    p = _api_keys_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)
    return key


def _resolve_api_key(key: str):
    """Return the owner email for a valid key, else None."""
    if not key:
        return None
    rec = _load_api_keys().get(_hash_api_key(key))
    return rec.get("email") if rec else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_campaign_api.py
git commit -m "feat(api): per-user API key mint/resolve helpers"
```

---

### Task 2: CLI to mint a key

**Files:**
- Create: `scripts/mint_api_key.py`

- [ ] **Step 1: Write the script**

Create `scripts/mint_api_key.py`:

```python
"""Mint an API key for a user. Run on the server where flowdrip_app imports.

Usage: python scripts/mint_api_key.py <email> [label]
Prints the plaintext key ONCE — store it now, only its hash is kept.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import flowdrip_app as fa


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/mint_api_key.py <email> [label]")
        raise SystemExit(2)
    email = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else ""
    key = fa._mint_api_key(email, label=label)
    print(f"API key for {email} (label={label or '-'}):")
    print(key)
    print("Store this now — only its hash is kept on the server.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it runs (no real key needed — uses default store path)**

Run: `./.venv/Scripts/python.exe scripts/mint_api_key.py test@example.com smoke`
Expected: prints a `dd_live_…` key. (This writes to the local default store; harmless. Delete the local `data/api_keys.json` afterward if you want a clean tree, or leave it — it's git-ignored data.)

- [ ] **Step 3: Commit**

```bash
git add scripts/mint_api_key.py
git commit -m "feat(api): CLI to mint per-user API keys"
```

---

### Task 3: Spec validation + contacts parsing

**Files:**
- Modify: `flowdrip_app.py` (add helpers near the new API code)
- Test: `tests/test_campaign_api.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_campaign_api.py`)

```python
# ── contacts CSV parsing ───────────────────────────────────────────
def test_parse_contacts_csv_maps_aliased_columns():
    csv_text = "Email,FirstName,LastName,Company,JobTitle\n" \
               "vp@acme.com,Dana,Lee,Acme,VP Ops\n"
    rows = fa._parse_contacts_csv(csv_text)
    assert rows == [{"email": "vp@acme.com", "first_name": "Dana",
                     "last_name": "Lee", "company": "Acme", "title": "VP Ops"}]


def test_parse_contacts_csv_blank_is_empty():
    assert fa._parse_contacts_csv("") == []


# ── spec validation ────────────────────────────────────────────────
def test_validate_spec_rejects_unknown_template():
    err = fa._validate_campaign_spec({"template": "nope", "company": "Acme",
                                      "start_date": "2026-07-06"})
    assert err and "template" in err.lower()


def test_validate_spec_requires_company_or_niche():
    err = fa._validate_campaign_spec({"template": "fourbyfour",
                                      "start_date": "2026-07-06"})
    assert err and ("company" in err.lower() or "niche" in err.lower())


def test_validate_spec_rejects_bad_date():
    err = fa._validate_campaign_spec({"template": "fourbyfour", "company": "Acme",
                                      "start_date": "07/06/2026"})
    assert err and "date" in err.lower()


def test_validate_spec_ok_returns_none():
    assert fa._validate_campaign_spec({"template": "fourbyfour", "company": "Acme",
                                       "start_date": "2026-07-06"}) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py -k "csv or validate" -v`
Expected: FAIL — `_parse_contacts_csv` / `_validate_campaign_spec` not defined.

- [ ] **Step 3: Implement the helpers** (in `flowdrip_app.py`, near the API-key helpers; `csv`, `io`, `date` are available — `csv` and `io` are stdlib, add `import csv, io` at the top if not present)

```python
def _parse_contacts_csv(csv_text: str) -> list:
    """Parse raw CSV text into normalized contact dicts (email/first_name/...)."""
    text = (csv_text or "").strip()
    if not text:
        return []
    import csv as _csv
    import io as _io
    out = []
    reader = _csv.DictReader(_io.StringIO(text))
    for row in reader:
        g = lambda *keys: next((row[k] for k in keys if row.get(k)), "")
        out.append({
            "email": g("email", "Email").strip(),
            "first_name": g("first_name", "FirstName").strip(),
            "last_name": g("last_name", "LastName").strip(),
            "company": g("company", "Company").strip(),
            "title": g("title", "JobTitle", "Title").strip(),
        })
    return [c for c in out if c["email"]]


_VALID_TEMPLATES = {ct[0] for ct in AICB_CAMPAIGN_TYPES}


def _validate_campaign_spec(spec: dict):
    """Return an error string if the spec is invalid, else None."""
    if not isinstance(spec, dict):
        return "Body must be a JSON object."
    tmpl = (spec.get("template") or "").strip()
    if tmpl not in _VALID_TEMPLATES:
        return f"Unknown template '{tmpl}'. Valid: {sorted(_VALID_TEMPLATES)}."
    if not (spec.get("company") or "").strip() and not (spec.get("niche") or "").strip():
        return "Provide at least one of 'company' or 'niche'."
    sd = (spec.get("start_date") or "").strip()
    try:
        date.fromisoformat(sd)
    except Exception:
        return "Invalid 'start_date' — use ISO format YYYY-MM-DD."
    return None
```

Note: `_VALID_TEMPLATES` must be defined AFTER `AICB_CAMPAIGN_TYPES`. Place these helpers below that constant (e.g. near `save_campaign`), not above it.

- [ ] **Step 4: Run to verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py -k "csv or validate" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_campaign_api.py
git commit -m "feat(api): spec validation + contacts CSV parsing"
```

---

### Task 4: Schedule computation helper

**Files:**
- Modify: `flowdrip_app.py`
- Test: `tests/test_campaign_api.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def test_schedule_from_steps_4x4_business_days():
    # Steps with the 4x4 delays: 0, 3, 0 (call), 4, 4 over business days.
    steps = [
        {"step_type": "email_auto", "delay_days": 0},
        {"step_type": "email_auto", "delay_days": 3},
        {"step_type": "call",       "delay_days": 0},
        {"step_type": "email_auto", "delay_days": 4},
        {"step_type": "email_auto", "delay_days": 4},
    ]
    sched = fa._schedule_from_steps(steps, "2026-07-06")  # Monday
    dates = [r["date"] for r in sched]
    assert dates == ["2026-07-06", "2026-07-09", "2026-07-09",
                     "2026-07-15", "2026-07-21"]
    assert sched[2]["type"] == "call" and sched[2]["step"] == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py -k schedule -v`
Expected: FAIL — `_schedule_from_steps` not defined.

- [ ] **Step 3: Implement** (in `flowdrip_app.py`, near the API helpers). Reuse the existing `_add_business_days(start_date, n)` helper used by the scheduler (confirm its name by searching `def _add_business_days`; it takes a `date` and an int and returns a `date`).

```python
def _schedule_from_steps(steps: list, start_date: str) -> list:
    """Resolve each step's calendar date from cumulative delay_days over
    business days — mirrors how queue_campaign_emails schedules sends."""
    try:
        start_dt = date.fromisoformat(start_date)
    except Exception:
        start_dt = date.today()
    out = []
    cum = 0
    for i, st in enumerate(steps, 1):
        cum += int(st.get("delay_days", 0) or 0)
        d = _add_business_days(start_dt, cum)
        out.append({
            "step": i,
            "type": (st.get("step_type") or "email_auto"),
            "date": d.isoformat(),
        })
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py -k schedule -v`
Expected: PASS. If dates differ, inspect `_add_business_days` semantics (whether it counts the start day) and adjust the expected values in the test to match the REAL scheduler — the goal is parity with `queue_campaign_emails`, which is the source of truth.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_campaign_api.py
git commit -m "feat(api): schedule-from-steps date resolver"
```

---

### Task 5: Extract `generate_aicb_campaign()` and rewire the wizard

This is the core refactor. The wizard's `_do_research._run` (anchor: search `def _do_research(` then the inner `def _run(`) currently inlines: research → candidate block → cited stats → campaign-build prompt → Haiku call → post-process. Lift that into a module-level function and have the wizard call it.

**Files:**
- Modify: `flowdrip_app.py` (new `generate_aicb_campaign`; rewire `_run`)
- Test: `tests/test_campaign_api.py`

- [ ] **Step 1: Write the failing test** (append). Uses a fake client so no network/AI.

```python
class _FakeMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]

class _FakeClient:
    """Returns a market brief on the 1st call, campaign JSON on the 2nd."""
    def __init__(self):
        self.messages = self
        self._n = 0
    def create(self, **kw):
        self._n += 1
        if self._n == 1:
            return _FakeMsg("Brief: Acme hires Plant Managers in Windsor, CO.")
        camp = {
            "synopsis": "S",
            "campaign_name": "Acme - Plant Manager Campaign",
            "emails": [
                {"name": "Step 1", "subject": "Plant Manager Candidates Available",
                 "body": "Intro - with a dash", "delay_days": 0, "time": "9:00 AM",
                 "step_type": "email_auto"},
                {"name": "Step 2", "subject": "Top Talent Insights",
                 "body": "Insights", "delay_days": 3, "time": "9:00 AM",
                 "step_type": "email_auto"},
            ],
        }
        import json as _j
        return _FakeMsg(_j.dumps(camp))


def test_generate_aicb_campaign_returns_normalized_emails(monkeypatch):
    # Avoid the live web-search cited-stats call.
    monkeypatch.setattr(fa, "_fetch_cited_market_stats", lambda *a, **k: [])
    monkeypatch.setattr(fa, "_format_cited_stats_block", lambda *a, **k: "")
    out = fa.generate_aicb_campaign(
        _FakeClient(),
        camp_type="fourbyfour",
        company="Acme Manufacturing",
        website="acme.com",
        niche="food processing",
        industry="manufacturing",
        roles=["Plant Manager"],
        location="Windsor, CO",
        candidate_cards=[{"label": "Candidate A", "role": "Plant Manager",
                          "bullets": ["12 yrs", "PMP"]}],
    )
    assert out["campaign_name"]
    assert len(out["emails"]) == 2
    # Post-processing ran: dash stripped, FirstName greeting added, 4x4 font wrap.
    b0 = out["emails"][0]["body"]
    assert " - " not in b0 and "—" not in b0
    assert b0.lstrip().startswith("Hi {FirstName}")
    assert "font-size:11pt" in b0   # _wrap_4x4_font applied for fourbyfour
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py -k generate_aicb -v`
Expected: FAIL — `generate_aicb_campaign` not defined.

- [ ] **Step 3: Implement `generate_aicb_campaign` by lifting the wizard core.**

Add a module-level function `generate_aicb_campaign(client, *, camp_type, company="", website="", niche="", industry="", roles=None, location=None, candidate_cards=None)`. Build its body by **moving** the existing logic out of `_run`, replacing session reads with the parameters per this mapping:

| In `_run` today | In the function |
|---|---|
| `s.aicb_company` / `company` | `company` param |
| `s.aicb_website` | `website` param |
| `s.aicb_niche` / `niche_str` | `niche` param |
| `s.aicb_industry` → `ind_label` | derive `ind_label` from `industry` param via `AICB_INDUSTRIES.get(industry, {}).get("label", industry)` |
| `s.aicb_sel_roles` / `roles_str` | `roles` param; `roles_str = ", ".join(roles or [])`; `_first_role = (roles or [""])[0]` |
| `s.aicb_sel_locations` → `location_str` | `location` param (fallback `"their primary markets"` if empty) |
| `s.aicb_camp_type` | `camp_type` param |
| `s._aicb_cand_text` / `s.aicb_cand_cards` | build the candidate block from `candidate_cards` (see below) |

The function performs, in order (copying the existing code blocks verbatim except for the substitutions above):
1. Compute `location_str`, `ind_label`, `roles_str`, `_first_role`, `is_niche_mode`/`niche_str` (call the existing `_aicb_force_market_for_4x4(camp_type, is_niche_mode, niche_str, ind_label, roles_str)` exactly as the wizard does).
2. **Research** — the same `research_prompt` (niche vs company mode) + `_claude_create_with_retry(client, model="claude-haiku-4-5-20251001", ... web_search ...)` → `brief`. If `brief` is empty, `raise RuntimeError("research returned empty brief")` (the route maps this to 502).
3. **Candidate block** — format `candidate_cards` into the `_cand_block` string. Reuse the existing formatting: derive `_cand_text` by joining each card into the "Candidate X: role / bullets" shape the wizard's `_cand_block` builds, and set `n_cands = len(candidate_cards or [])`. Keep the exact wording of the existing block so output matches the wizard.
4. **Cited stats** — `if camp_type == "fourbyfour": _stats_block = _format_cited_stats_block(_fetch_cited_market_stats(...))` else `""`.
5. **Campaign prompt** — the existing `campaign_prompt` string (now using the relaxed delay rule already in the file) with `touch_sequence = next(ct for ct in AICB_CAMPAIGN_TYPES if ct[0]==camp_type)[6]`.
6. **Haiku call** → parse JSON (`re.search(r'\{.*\}', clean, re.DOTALL)`) → `campaign_data`.
7. **Post-process** — the existing per-email loop (markdown→HTML, `Hi {FirstName},` prefix, `_strip_ai_signoff`, `_title_case_subject`, `_humanize_email_text`, `_strip_dashes`, `_wrap_4x4_font` when `camp_type=="fourbyfour"`) then `_spread_email_times(campaign_data.get("emails", []))`.
8. `return campaign_data`.

The function takes NO `s`, does NO PDF work, does NOT touch `app.storage` or `ui`.

- [ ] **Step 4: Rewire the wizard `_run` to call the function**

In `_run`, replace the moved research→post-process block with:

```python
                    campaign_data = generate_aicb_campaign(
                        client,
                        camp_type=s.aicb_camp_type,
                        company=(s.aicb_company or "").strip(),
                        website=(s.aicb_website or ""),
                        niche=(s.aicb_niche or ""),
                        industry=(s.aicb_industry or ""),
                        roles=list(s.aicb_sel_roles or []),
                        location=(", ".join(s.aicb_sel_locations)
                                  if s.aicb_sel_locations else ""),
                        candidate_cards=_aicb_cards_from_state(s),
                    )
                    s.aicb_research = {"company": (s.aicb_company or "").strip(),
                                       "brief": ""}
                    s.aicb_docs["campaign"] = campaign_data
                    s.aicb_docs["synopsis"] = campaign_data.get("synopsis", "")
```

Keep everything else in `_run` (the PDF thread start, the `_pdf_data_event.wait`, the résumé attach block, error handling) unchanged. Add a tiny adapter `_aicb_cards_from_state(s)` that returns the candidate cards the wizard already holds — prefer `s.aicb_cand_cards` if present, else parse `s._aicb_cand_text`. If the wizard previously fed `_cand_text` directly, have `generate_aicb_campaign` accept either by also building from a pre-formatted text when `candidate_cards` items are plain strings. Verify by running the regression suite in Step 6.

Wrap the call so a `RuntimeError` from empty research sets `s._aicb_error` like the old empty-brief branch did:

```python
                    try:
                        campaign_data = generate_aicb_campaign(...)
                    except RuntimeError as _ge:
                        s._aicb_error = f"Research failed: {_ge}. Try again."
                        s.aicb_generating = False
                        return
```

- [ ] **Step 5: Run the generation unit test + the full 4×4 regression suite**

Run:
```
./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py -k generate_aicb -v
./.venv/Scripts/python.exe -m pytest tests/test_arena_4x4_voice.py tests/test_arena_4x4_industry_aim.py tests/test_arena_4x4_cited_stats.py tests/test_strategy_chooser.py -q
```
Expected: generation test PASSES; all regression suites PASS. If a 4×4 test fails, the extraction changed output — diff the moved block against the original and fix the substitution until output is identical.

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py tests/test_campaign_api.py
git commit -m "refactor(aicb): extract generate_aicb_campaign; rewire wizard to it"
```

---

### Task 6: The `POST /api/v1/campaigns` route

**Files:**
- Modify: `flowdrip_app.py` (add route near the other raw routes, after `/healthz`)
- Test: `tests/test_campaign_api.py`

- [ ] **Step 1: Write the failing tests** (append). Uses FastAPI `TestClient` + monkeypatched generation/save/queue, so no AI and no real sends.

```python
from fastapi.testclient import TestClient


def _client():
    return TestClient(fa.app)


def _stub_pipeline(monkeypatch, queued=1, raise_queue=None):
    monkeypatch.setattr(fa, "generate_aicb_campaign", lambda *a, **k: {
        "synopsis": "S", "campaign_name": "Acme - Plant Manager Campaign",
        "emails": [
            {"subject": "Plant Manager Candidates Available", "body": "Hi {FirstName},",
             "delay_days": 0, "time": "9:00 AM", "step_type": "email_auto"},
            {"subject": "Top Talent Insights", "body": "Hi {FirstName},",
             "delay_days": 3, "time": "9:00 AM", "step_type": "email_auto"},
            {"subject": "", "body": "Call script", "delay_days": 0, "time": "10:00 AM",
             "step_type": "call"},
            {"subject": "Thoughts on this?", "body": "Hi {FirstName},",
             "delay_days": 4, "time": "9:00 AM", "step_type": "email_auto"},
            {"subject": "Market Trends", "body": "Hi {FirstName},",
             "delay_days": 4, "time": "9:00 AM", "step_type": "email_auto"},
        ],
    })
    captured = {}
    def _fake_save(camp):
        camp["_path"] = "/tmp/x.json"
        captured["camp"] = camp
    monkeypatch.setattr(fa, "save_campaign", _fake_save)
    def _fake_queue(camp, start_step=0):
        if raise_queue:
            raise raise_queue
        captured["queued_camp"] = camp
        return queued
    monkeypatch.setattr(fa, "queue_campaign_emails", _fake_queue)
    return captured


_SPEC = {"template": "fourbyfour", "company": "Acme Manufacturing",
         "website": "acme.com", "niche": "food processing",
         "industry": "manufacturing", "roles": ["Plant Manager"],
         "location": "Windsor, CO", "start_date": "2026-07-06",
         "candidates": [{"label": "Candidate A", "role": "Plant Manager",
                         "bullets": ["12 yrs"]}],
         "contacts": [{"email": "vp@acme.com", "first_name": "Dana"}]}


def test_route_requires_auth(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    r = _client().post("/api/v1/campaigns", json=_SPEC)
    assert r.status_code == 401


def test_route_happy_path_owner_from_key(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    cap = _stub_pipeline(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    r = _client().post("/api/v1/campaigns", json=_SPEC,
                       headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["steps"] == 5
    assert body["contacts_queued"] == 1
    assert len(body["schedule"]) == 5
    # Owner came from the key, not the body.
    assert cap["camp"]["_owner_email"] == "rep@arena.com"
    assert cap["camp"]["aicb_camp_type"] == "fourbyfour"


def test_route_bad_template_400(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    _stub_pipeline(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    bad = dict(_SPEC, template="nope")
    r = _client().post("/api/v1/campaigns", json=bad,
                       headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 400


def test_route_queue_valueerror_422(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    _stub_pipeline(monkeypatch, raise_queue=ValueError("unfilled placeholder"))
    key = fa._mint_api_key("rep@arena.com")
    r = _client().post("/api/v1/campaigns", json=_SPEC,
                       headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py -k route -v`
Expected: FAIL — route returns 404 (not defined) so assertions fail.

- [ ] **Step 3: Implement the route.** Add near the top raw routes (after `@app.get("/healthz")`). Imports: add `from fastapi import Request` and `from fastapi.responses import JSONResponse` at the top of the file if not already imported (search first).

```python
@app.post("/api/v1/campaigns")
async def api_create_campaign(request: Request):
    # 1. Auth — owner comes from the key, never the body.
    auth = request.headers.get("authorization", "")
    key = auth[7:].strip() if auth.lower().startswith("bearer ") else \
          request.headers.get("x-api-key", "").strip()
    owner = _resolve_api_key(key)
    if not owner:
        return JSONResponse({"error": "invalid or missing API key"}, status_code=401)

    try:
        spec = await request.json()
    except Exception:
        return JSONResponse({"error": "body must be valid JSON"}, status_code=400)

    # 2. Validate.
    err = _validate_campaign_spec(spec if isinstance(spec, dict) else {})
    if err:
        return JSONResponse({"error": err}, status_code=400)

    # Contacts: explicit array, or contacts_csv string.
    contacts = spec.get("contacts")
    if not isinstance(contacts, list):
        contacts = _parse_contacts_csv(spec.get("contacts_csv", ""))

    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "AI not configured on server"}, status_code=503)

    # 3. Bind user context so save/queue land in the key owner's account.
    _CURRENT_USER_EMAIL.set(owner)
    try:
        _switch_to_user_paths(owner)
    except Exception:
        pass

    # 4. Generate (synchronous; ~15-40s).
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    template = spec["template"].strip()
    try:
        campaign_data = generate_aicb_campaign(
            client,
            camp_type=template,
            company=(spec.get("company") or "").strip(),
            website=(spec.get("website") or "").strip(),
            niche=(spec.get("niche") or "").strip(),
            industry=(spec.get("industry") or "").strip(),
            roles=list(spec.get("roles") or []),
            location=(spec.get("location") or "").strip(),
            candidate_cards=list(spec.get("candidates") or []),
        )
    except RuntimeError as ge:
        return JSONResponse({"error": f"generation failed: {ge}"}, status_code=502)
    except Exception as ge:
        return JSONResponse({"error": f"generation error: {ge}"}, status_code=500)

    emails = campaign_data.get("emails", [])
    start_date = spec["start_date"].strip()

    # 5. Assemble the campaign dict.
    camp = {
        "name": (spec.get("name") or campaign_data.get("campaign_name")
                 or f"{template} Campaign").strip(),
        "emails": emails,
        "synopsis": campaign_data.get("synopsis", ""),
        "contacts": contacts,
        "start_date": start_date,
        "aicb_camp_type": template,
        "template_key": template,
        "_chooser_origin": template,
        "_owner_email": owner,
        "variables": {
            "CompanyName": (spec.get("company") or "").strip(),
            "TargetRole": ", ".join(spec.get("roles") or []),
            "Geography": (spec.get("location") or "").strip(),
            "Industry": (spec.get("industry") or "").strip(),
        },
    }

    # 6. Create + launch (inherits DNC/opt-out/MX/placeholder guards).
    try:
        save_campaign(camp)
        queued = queue_campaign_emails(camp)
    except ValueError as qe:
        return JSONResponse({"error": str(qe)}, status_code=422)
    except Exception as qe:
        return JSONResponse({"error": f"launch failed: {qe}"}, status_code=500)

    resp = {
        "campaign_id": Path(camp.get("_path", "")).stem or camp["name"],
        "name": camp["name"],
        "steps": len(emails),
        "contacts_queued": queued,
        "start_date": start_date,
        "schedule": _schedule_from_steps(emails, start_date),
    }
    if queued == 0:
        resp["warning"] = "no contacts queued (empty list or all filtered by DNC/opt-out/MX)"
    return JSONResponse(resp, status_code=200)
```

- [ ] **Step 4: Run to verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py -k route -v`
Expected: PASS (4 route tests).

- [ ] **Step 5: Run the whole API test file + 4×4 regression**

Run:
```
./.venv/Scripts/python.exe -m pytest tests/test_campaign_api.py tests/test_arena_4x4_voice.py tests/test_arena_4x4_industry_aim.py tests/test_arena_4x4_cited_stats.py tests/test_strategy_chooser.py -q
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py tests/test_campaign_api.py
git commit -m "feat(api): POST /api/v1/campaigns create+launch route"
```

---

### Task 7: API usage doc for the co-work agent

**Files:**
- Create: `docs/api/campaigns.md`

- [ ] **Step 1: Write the doc**

Create `docs/api/campaigns.md` with: endpoint summary, auth header, the full request schema (every field, required vs optional, with the `contacts` vs `contacts_csv` options), the response schema, status codes, and a runnable `curl` example for an Arena 4×4. Use the exact field names from Task 6's route. Include this example:

```bash
curl -sS -X POST https://dripdripdrop.ai/api/v1/campaigns \
  -H "Authorization: Bearer dd_live_YOURKEY" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "fourbyfour",
    "company": "Acme Manufacturing",
    "website": "acme.com",
    "niche": "food processing",
    "industry": "manufacturing",
    "roles": ["Plant Manager"],
    "location": "Windsor, CO",
    "start_date": "2026-07-06",
    "candidates": [
      {"label": "Candidate A", "role": "Plant Manager",
       "bullets": ["12 yrs in food processing", "PMP, Six Sigma"],
       "location": "Windsor, CO", "target_salary": "$140k"}
    ],
    "contacts": [
      {"email": "vp@acme.com", "first_name": "Dana", "last_name": "Lee",
       "company": "Acme", "title": "VP Operations"}
    ]
  }'
```

Document the valid `template` keys (from `AICB_CAMPAIGN_TYPES`: `fourbyfour`, `blitz`, `talentdrop`, `flood`, `sidequest`, …) and note Phase-1 limits: synchronous (allow 60s), no PDFs, no per-step dates, templates only.

- [ ] **Step 2: Commit**

```bash
git add docs/api/campaigns.md
git commit -m "docs(api): campaign create+launch usage for co-work agent"
```

---

### Task 8: Full suite + deploy

- [ ] **Step 1: Run the full test suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (or no NEW failures vs. the pre-existing baseline — if unrelated suites were already failing before this work, note them but don't block).

- [ ] **Step 2: Deploy flowdrip_app.py only** (do NOT ship uncommitted `ats.py`). Use the app-only deploy approach (extra files + Caddyfile disabled), same as the 4×4 call deploy.

Run the app-only deploy script (the scratchpad `deploy_only_app.sh`, or `_deploy_zero_downtime.sh` with EXTRA_FILES emptied). Expected: `Deploy complete`, `https check: HTTP 200`.

- [ ] **Step 3: Mint a key on the server + smoke test**

```bash
ssh -i ~/.ssh/dripdrop root@134.199.237.206 \
  "cd /opt/dripdrop/app && python3 scripts/mint_api_key.py <your-account-email> cowork"
```
Then `curl` the live endpoint (see `docs/api/campaigns.md`) with ONE safe test contact you control. Confirm `200` + a 5-step schedule, the campaign appears in the account, and the queue shows the sends.

- [ ] **Step 4: Wizard parity smoke test**

In the app, generate an Arena 4×4 the normal way; confirm it still produces the 5-step sequence correctly (the rewired generation path).

---

## Self-review notes

- **Spec coverage:** auth (T1/T2), spec+CSV validation (T3), schedule (T4), generation extraction + wizard rewire (T5), route + inherited safety (T6), docs (T7), deploy + parity (T8). All spec sections mapped.
- **Type consistency:** `generate_aicb_campaign` signature is identical in T5 (def), T5 Step 4 (wizard call), and T6 (route call). `_resolve_api_key`, `_mint_api_key`, `_hash_api_key`, `_api_keys_path`, `_parse_contacts_csv`, `_validate_campaign_spec`, `_schedule_from_steps` names are consistent across tasks.
- **Risk:** the extraction (T5) is the only task that can change existing behavior; the 4×4 regression suites are the guardrail, run in T5 Step 5 and again in T6 Step 5.

# The J Way — Banner + Spotlight Fork Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For The J Way newsletter (Arena-only): drop a fixed Arena "Recruitment Rundown" banner above the Highlights section, remove the hero-photo picker, and replace the cluttered Candidate Spotlights block with a pick-one AI-vs-Pipeline fork.

**Architecture:** Three localized edits to `flowdrip_app.py`. The banner is a static asset served via the existing `/static/` allowlist pattern and injected as an `<img>` inside the pure `_jway_render()` function. The hero-picker is gated off by `newsletter_style == "j_way"` at its two render sites. The spotlight fork is a create-dialog UI change reusing the existing Pipeline-search machinery, with mutually-exclusive save semantics.

**Tech Stack:** Python, NiceGUI, pytest. Single-module app (`flowdrip_app.py`). Tests in `tests/`, run with `python -m pytest`.

**Spec:** docs/superpowers/specs/2026-06-17-jway-banner-and-spotlight-fork-design.md

---

## File Structure

- Modify: `flowdrip_app.py`
  - `_STATIC_ALLOWLIST` (L82) — add `jway_banner.png`
  - `_jway_render()` (L43712) — insert banner `<img>` after intro, before Highlights
  - Issue-editor modal (L22975 area) — gate `_render_hero_gallery()` call for J Way
  - Preview-panel "Change Hero Photo" (L45458 / L45538) — gate for J Way
  - Create-newsletter dialog (L21971–L22091) — spotlight fork; `_create()` save (L22286–L22302) — mutual exclusivity
- Create: `tests/test_jway_banner.py`
- Asset (provided by user, not created by plan): `jway_banner.png` in project root

---

### Task 1: Banner asset is allowlisted

**Files:**
- Modify: `flowdrip_app.py:82` (`_STATIC_ALLOWLIST`)
- Test: `tests/test_jway_banner.py`

- [ ] **Step 1: Write the failing test**

```python
"""The J Way newsletter banner: fixed Arena 'Recruitment Rundown' image,
allowlisted for /static/ serving and rendered above the Highlights block.

Spec: docs/superpowers/specs/2026-06-17-jway-banner-and-spotlight-fork-design.md
"""
import flowdrip_app as fa


def test_banner_is_static_allowlisted():
    """The banner must be servable via /static/ — otherwise the email's
    <img src="https://dripdripdrop.ai/static/jway_banner.png"> 404s."""
    assert "jway_banner.png" in fa._STATIC_ALLOWLIST
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_jway_banner.py::test_banner_is_static_allowlisted -v`
Expected: FAIL — `jway_banner.png` not in the set.

- [ ] **Step 3: Add the filename to the allowlist**

In `flowdrip_app.py` L82:

```python
_STATIC_ALLOWLIST = {
    "dripdrop_logo.png",
    "jway_banner.png",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_jway_banner.py::test_banner_is_static_allowlisted -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_jway_banner.py flowdrip_app.py
git commit -m "feat(jway): allowlist jway_banner.png for /static/ serving"
```

---

### Task 2: Banner renders above Highlights in `_jway_render`

**Files:**
- Modify: `flowdrip_app.py:43726-43731` (inside `_jway_render`)
- Test: `tests/test_jway_banner.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_jway_banner.py`:

```python
def _sample_doc():
    return {
        "intro": "Quick market note for July.",
        "highlights_label": "Highlights (May 2026)",
        "highlights": ["173,000 nonfarm jobs added", "Unemployment 4.0%"],
        "candidates": [],
        "signoff": "Thanks!",
    }


def test_banner_img_present_with_static_url():
    html = fa._jway_render(_sample_doc(), "Jeff")
    assert "/static/jway_banner.png" in html
    assert "https://dripdripdrop.ai/static/jway_banner.png" in html


def test_banner_appears_after_intro_and_before_highlights():
    html = fa._jway_render(_sample_doc(), "Jeff")
    intro_pos = html.index("Quick market note")
    banner_pos = html.index("jway_banner.png")
    highlights_pos = html.index("Highlights (May 2026)")
    assert intro_pos < banner_pos < highlights_pos, (
        "banner must sit between the intro email text and the Highlights block")


def test_no_unsplash_hero_in_jway_body():
    """J Way bodies never carry an Unsplash/city hero image."""
    html = fa._jway_render(_sample_doc(), "Jeff")
    assert "/city_image/" not in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_jway_banner.py -v`
Expected: the two banner tests FAIL (`jway_banner.png` not in output); `test_no_unsplash_hero_in_jway_body` already PASSES.

- [ ] **Step 3: Insert the banner in `_jway_render`**

In `flowdrip_app.py`, the current block reads:

```python
    out = []
    if d.get("intro"):
        out.append(f"<p style='{P}'>{_esc(d['intro'])}</p>")
    out.append(f"<p style='{P}'>If I missed anything or you want to dig into something "
               f"further, just let me know - happy to discuss.</p>")
    if d.get("highlights"):
```

Change it to add the banner right after the intro lines and before Highlights:

```python
    out = []
    if d.get("intro"):
        out.append(f"<p style='{P}'>{_esc(d['intro'])}</p>")
    out.append(f"<p style='{P}'>If I missed anything or you want to dig into something "
               f"further, just let me know - happy to discuss.</p>")
    # Fixed Arena "Recruitment Rundown" banner — J Way is Arena-only, so this
    # branded image is bundled (not user-pickable) and served via /static/.
    # Sits between the personal intro note and the Highlights block.
    out.append(
        "<img src='https://dripdripdrop.ai/static/jway_banner.png' width='600' "
        "style='display:block;width:100%;max-width:600px;height:auto;border:0;"
        "margin:6px 0 14px 0;' alt='Arena Direct Hire - Recruitment Rundown' />")
    if d.get("highlights"):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_jway_banner.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_jway_banner.py flowdrip_app.py
git commit -m "feat(jway): render fixed Recruitment Rundown banner above Highlights"
```

---

### Task 3: Hide the hero-photo picker for J Way

**Files:**
- Modify: `flowdrip_app.py:22975` (the `_render_hero_gallery()` call in the issue-editor modal)
- Modify: `flowdrip_app.py:45458-45538` (the "Change Hero Photo" action in the preview panel)

No new unit test — this is NiceGUI render-path code. Task 2's `test_no_unsplash_hero_in_jway_body` covers that the body carries no hero image; the editor gating is verified manually.

- [ ] **Step 1: Gate the gallery render in the editor modal**

At `flowdrip_app.py:22975`, the line currently reads:

```python
            _render_hero_gallery()
```

Replace with:

```python
            # Hero photo picker is a Full Send concept. The J Way uses a
            # fixed bundled banner (see _jway_render) and has no per-issue
            # photo selection — so skip the whole gallery for J Way issues.
            if (camp.get("newsletter_style") or "").strip() != "j_way":
                _render_hero_gallery()
```

- [ ] **Step 2: Verify `camp` is in scope here**

Run: `python -c "import flowdrip_app"`
Expected: imports cleanly (no NameError introduced). `camp` is the modal function's parameter and is referenced throughout this block, so it is in scope.

- [ ] **Step 3: Gate the "Change Hero Photo" preview action**

Read `flowdrip_app.py:45450-45545` to confirm the exact structure, then wrap the "🖼 Change Hero Photo" control so it only renders when the campaign's `newsletter_style != "j_way"`. Use the same guard expression:

```python
if (camp.get("newsletter_style") or "").strip() != "j_way":
    # ... existing "Change Hero Photo" control block ...
```

Match the indentation of the surrounding block. The variable holding the campaign in that scope may be named `camp` or similar — confirm by reading the function header before editing.

- [ ] **Step 4: Smoke test**

Run: `python -c "import flowdrip_app"`
Expected: imports cleanly.

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(jway): hide hero-photo picker for J Way issues"
```

---

### Task 4: Candidate Spotlights pick-one fork (create dialog)

**Files:**
- Modify: `flowdrip_app.py:21971-22091` (Candidate Spotlights UI block)
- Modify: `flowdrip_app.py:22286-22302` (`_create()` save semantics)

NiceGUI UI — verified manually. The goal: a two-button fork (`✨ Auto-populate with AI` / `📋 Choose from Pipeline`), default AI; show only the selected path's controls; keep the 3-or-6 count visible for both; make the two paths mutually exclusive at save.

- [ ] **Step 1: Read the current block in full**

Read `flowdrip_app.py:21971-22091` so you have the exact existing widgets (`spotlight_recs_in`, `_sel_cands`, `_pipe_q`, `_pipe_search`, `_refresh_chosen`, `_chosen_row`, `_pipe_results`, `spotlight_in`) and their styling in front of you.

- [ ] **Step 2: Introduce the fork state + toggle**

After the "Candidate Spotlights" header + tooltip block (ends ~L21990), and BEFORE the "Spotlight Recommendations" label, add a mode toggle. Use a NiceGUI `ui.toggle` styled like the existing `_style_toggle` (L21903):

```python
        # Pick-one fork: AI auto-populate vs choose from Pipeline. Replaces
        # the old always-on stack (recs + pipeline + count all visible) which
        # users found cluttered. Default = AI.
        _spot_mode = ui.toggle(
            {"ai": "✨ Auto-populate with AI", "pipeline": "📋 Choose from Pipeline"},
            value="ai").props("no-caps").style("margin:2px 0 10px 0;")
```

Note: the Pipeline option is only meaningful for ATS users (`_ats_ok`). If `not _ats_ok`, force `value="ai"` and skip rendering the toggle entirely (only AI path exists):

```python
        if _ats_ok:
            _spot_mode = ui.toggle(
                {"ai": "✨ Auto-populate with AI", "pipeline": "📋 Choose from Pipeline"},
                value="ai").props("no-caps").style("margin:2px 0 10px 0;")
        else:
            _spot_mode = None  # AI-only; no fork shown
```

- [ ] **Step 3: Wrap each path's controls in its own container and toggle visibility**

Wrap the existing "Spotlight Recommendations" widgets (label + helper + `spotlight_recs_in`) in an AI container, and the existing Pipeline widgets (label + helper + `_chosen_row` + `_pipe_results` + search row) in a Pipeline container:

```python
        _ai_box = ui.element("div")
        with _ai_box:
            # ... existing "Spotlight Recommendations (optional)" label,
            #     helper text, and spotlight_recs_in textarea (unchanged) ...

        _pipe_box = ui.element("div")
        if _ats_ok:
            with _pipe_box:
                # ... existing "Featured Candidates — pick from Pipeline" label,
                #     helper, _chosen_row, _pipe_results, and search row (unchanged) ...
```

Then a visibility updater driven by the toggle:

```python
        def _upd_spot_mode():
            _mode = (_spot_mode.value if _spot_mode is not None else "ai")
            _ai_box.set_visibility(_mode == "ai")
            _pipe_box.set_visibility(_mode == "pipeline")
        if _spot_mode is not None:
            _spot_mode.on_value_change(lambda _e=None: _upd_spot_mode())
        _upd_spot_mode()
```

`ui.element("div")` supports `.set_visibility(bool)` in NiceGUI. Keep the "How many per issue" count (`spotlight_in`) OUTSIDE both boxes so it stays visible for both paths.

- [ ] **Step 4: Make save mutually exclusive in `_create()`**

At `flowdrip_app.py:22286-22302`, the current code unconditionally reads both
`spotlight_recs_in` and `_sel_cands`. Make them depend on the active mode:

```python
            _show_city_life = bool(city_life_in.value)
            _mode = (_spot_mode.value if _spot_mode is not None else "ai")
            if _mode == "pipeline":
                _spotlight_recs = ""
                _picked_cands = list(_sel_cands.values())
            else:
                _spotlight_recs = (spotlight_recs_in.value or "").strip()
                _picked_cands = []
```

Then in the `new_camp = dict(...)` literal, use `_picked_cands` instead of the
inline `list(_sel_cands.values())`:

```python
                newsletter_candidates=_picked_cands,
                ...
                newsletter_spotlight_recommendations=_spotlight_recs,
```

- [ ] **Step 5: Smoke test**

Run: `python -c "import flowdrip_app"`
Expected: imports cleanly.

- [ ] **Step 6: Manual verification**

Launch/deploy and open Create Newsletter:
- Default shows the AI recommendations textarea, Pipeline search hidden, count visible.
- Click "📋 Choose from Pipeline" → recommendations hides, search + chips appear, count still visible.
- Pick a candidate, switch back to AI, create → saved campaign has `newsletter_candidates == []` and the recs text.
- Pick Pipeline + a candidate, create → `newsletter_candidates` has the person, `newsletter_spotlight_recommendations == ""`.

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(jway): pick-one AI-vs-Pipeline fork for candidate spotlights"
```

---

### Task 5: Ship the banner asset with the deploy

**Files:**
- Inspect: deploy script(s) (`_deploy_zero_downtime.sh` and any rsync/scp file list)

- [ ] **Step 1: Confirm the asset exists locally**

Run: `ls -la jway_banner.png`
Expected: file present in project root (user-provided). If absent, STOP and request it before deploying.

- [ ] **Step 2: Confirm the deploy copies root PNGs to the app dir**

Read the deploy script and verify `dripdrop_logo.png` (already served via `/static/`) is copied to `/opt/dripdrop/app/`. The banner must land in the same place. If the script copies a specific file list, add `jway_banner.png`. If it copies the whole tree / all `*.png`, no change needed.

- [ ] **Step 3: Verify live after deploy**

After `bash _deploy_zero_downtime.sh`, run:
`curl -sI https://dripdripdrop.ai/static/jway_banner.png | head -1`
Expected: `HTTP/2 200`. Then load `/` and a J Way preview to confirm the banner renders above Highlights (per feedback_smoke_check_before_deploy: live `/`, not just import).

- [ ] **Step 4: Commit the asset (if tracked in git)**

```bash
git add jway_banner.png
git commit -m "assets: add J Way Recruitment Rundown banner"
```

---

## Self-Review

**Spec coverage:**
- Remove hero picker for J Way → Task 3 (both sites). ✓
- Fixed banner above Highlights → Tasks 1, 2 (allowlist + render), Task 5 (deploy). ✓
- Spotlight pick-one fork + mutual-exclusive save → Task 4. ✓
- Multi-user scope (Arena-only, bundled banner) → reflected in Task 2 comment + Task 4 `_ats_ok` handling. ✓

**Placeholder scan:** Task 3 Step 3 and Task 4 Step 1 ask the engineer to read exact line ranges before editing (UI code whose surrounding structure must be matched) — these include the exact guard expression / widget names to use, so they are actionable, not placeholders.

**Type/name consistency:** Guard expression `(camp.get("newsletter_style") or "").strip() != "j_way"` used identically in Task 3 Steps 1 and 3. Widget names (`spotlight_recs_in`, `_sel_cands`, `spotlight_in`, `_ats_ok`, `_spot_mode`) consistent across Task 4 steps. Save uses `_picked_cands`/`_spotlight_recs` defined in Task 4 Step 4.

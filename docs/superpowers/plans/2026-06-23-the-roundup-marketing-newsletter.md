# The Roundup — Internal Marketing Newsletter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "The Roundup", a hand-authored internal company newsletter — gated to Rothany (owner) + Michael (viewer) — that Rothany fills into labeled sections and sends to an all-staff list from inside DripDrop.

**Architecture:** A standalone module inside `flowdrip_app.py`, surfaced as a gated tab on the existing Newsletters page. It has its own JSON issue store (rooted in Rothany's per-user folder so the data is shared "Rothany owns, you view"), a pure HTML renderer, a section-based editor, and a send action. It reuses existing plumbing: the `_email_img_src` image cache, the `_apply_editor_props(ui.editor(...))` rich-text component, the NiceGUI 3.x upload API, `list_saved_contact_lists()`, and `_send_email_universal()` inside a `_run_as_user()` worker. It does NOT touch the AI-generated newsletter flow.

**Tech Stack:** Python, NiceGUI 3.x, pytest. Spec: `docs/superpowers/specs/2026-06-23-the-roundup-marketing-newsletter-design.md`.

**Conventions for every task below:**
- All new code lives in `flowdrip_app.py` unless stated otherwise.
- All new tests live in `tests/test_the_roundup.py` and import `import flowdrip_app as fa`.
- Run a single test with: `python -m pytest tests/test_the_roundup.py::<name> -v`
- Run the whole new file with: `python -m pytest tests/test_the_roundup.py -v`
- Commit messages use the `feat(roundup):` / `test(roundup):` prefixes.

---

## File structure

| File | Responsibility | New/Modified |
|------|----------------|--------------|
| `flowdrip_app.py` | gate constants + helpers, issue store, image helper, HTML renderer, editor tab, send dialog | Modified |
| `tests/test_the_roundup.py` | unit tests for gate, store, renderer, recipient parsing | New |

Insertion points referenced by anchor (the file is ~50k lines — search for the anchor string, don't trust absolute line numbers):
- Gate constants: immediately **after** the `_ATS_ALLOWED_EMAILS = { ... }` block (search `_ATS_ALLOWED_EMAILS`).
- Image subdir allowlist: inside `_serve_email_img` (search `if subdir not in ("cat", "hero", "avatar"`).
- Store + renderer + send helpers: just **above** `def p_newsletters(s, rf):` (search `def p_newsletters`).
- Tab toggle: **inside** `p_newsletters`, right after `_render_page_intro_strip(s, rf, "newsletters")` (search that call).

---

### Task 1: Access gate

**Files:**
- Modify: `flowdrip_app.py` (after the `_ATS_ALLOWED_EMAILS` block)
- Test: `tests/test_the_roundup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_the_roundup.py`:

```python
"""The Roundup — gated, hand-authored internal newsletter.

Spec: docs/superpowers/specs/2026-06-23-the-roundup-marketing-newsletter-design.md
"""
import flowdrip_app as fa


def test_roundup_gate_allows_owner_and_michael():
    assert fa._roundup_allowed("rothany.vu@arenastaffing.net") is True
    assert fa._roundup_allowed("michael.vaughn@arenastaffing.net") is True
    assert fa._roundup_allowed("mkvaughn1987@gmail.com") is True


def test_roundup_gate_is_case_and_space_insensitive():
    assert fa._roundup_allowed("  Rothany.Vu@ArenaStaffing.net ") is True


def test_roundup_gate_blocks_everyone_else():
    assert fa._roundup_allowed("someone.else@arenastaffing.net") is False
    assert fa._roundup_allowed("") is False
    assert fa._roundup_allowed(None) is False


def test_roundup_owner_is_rothany():
    assert fa._ROUNDUP_OWNER_EMAIL == "rothany.vu@arenastaffing.net"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_the_roundup.py -v`
Expected: FAIL — `AttributeError: module 'flowdrip_app' has no attribute '_roundup_allowed'`

- [ ] **Step 3: Add the gate constants + helper**

After the `_ATS_ALLOWED_EMAILS = { ... }` closing brace, add:

```python
# ── The Roundup (gated internal marketing newsletter) ──────────────────────
# Hand-authored company newsletter owned by Rothany (marketing). Visible only
# to the owner + Michael. Everyone else's Newsletters page shows no trace.
# "Rothany owns, you view": all issue data lives under the OWNER's per-user
# folder, so Michael's session reads the same source of truth.
_ROUNDUP_OWNER_EMAIL = "rothany.vu@arenastaffing.net"
_ROUNDUP_ALLOWED_EMAILS = {
    _ROUNDUP_OWNER_EMAIL,
    "michael.vaughn@arenastaffing.net",
    "mkvaughn1987@gmail.com",
}


def _roundup_allowed(email: str) -> bool:
    """True if this account may see The Roundup tab. Mirrors the ATS gate."""
    return (email or "").strip().lower() in _ROUNDUP_ALLOWED_EMAILS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_the_roundup.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_the_roundup.py
git commit -m "feat(roundup): add access gate (owner + Michael)"
```

---

### Task 2: Issue store

The store persists issues under Rothany's folder regardless of who is acting. `_resolve_user_root(email)` (search `def _resolve_user_root`) is pure path computation and accepts an explicit email — pass `_ROUNDUP_OWNER_EMAIL` so reads/writes always hit the owner's dir.

**Files:**
- Modify: `flowdrip_app.py` (above `def p_newsletters`)
- Test: `tests/test_the_roundup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_the_roundup.py`:

```python
def test_roundup_dir_is_under_owner_root(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", tmp_path)
    d = fa._roundup_dir()
    owner_root = fa._resolve_user_root(fa._ROUNDUP_OWNER_EMAIL)
    assert str(d).startswith(str(owner_root))
    assert d.name == "Roundup"


def test_roundup_issue_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", tmp_path)
    issue = fa._roundup_new_issue("June 2026")
    issue["marketing_minute"] = "<p>Hello team</p>"
    issue["new_items"] = [{"lead": "Logos", "body": "<p>x</p>", "image": None}]
    fa._roundup_save_issue(issue)

    loaded = fa._roundup_load_issue(issue["id"])
    assert loaded["issue_label"] == "June 2026"
    assert loaded["marketing_minute"] == "<p>Hello team</p>"
    assert loaded["new_items"][0]["lead"] == "Logos"


def test_roundup_index_lists_saved_issues(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", tmp_path)
    a = fa._roundup_new_issue("May 2026")
    b = fa._roundup_new_issue("June 2026")
    fa._roundup_save_issue(a)
    fa._roundup_save_issue(b)
    idx = fa._roundup_index()
    labels = {row["issue_label"] for row in idx}
    assert {"May 2026", "June 2026"} <= labels


def test_roundup_new_issue_has_default_subject_and_status():
    issue = fa._roundup_new_issue("July 2026")
    assert issue["status"] == "draft"
    assert issue["subject"] == "The Roundup — July 2026"
    assert issue["president"]["title"] == "President & CEO"
    assert issue["new_items"] == []
    assert issue["looking_ahead"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_the_roundup.py -k roundup_dir or roundtrip or index or new_issue -v`
Expected: FAIL — `AttributeError: ... has no attribute '_roundup_dir'`

- [ ] **Step 3: Implement the store**

Add above `def p_newsletters(s, rf):`:

```python
# ── The Roundup: issue store ───────────────────────────────────────────────
# Issues live under the OWNER's folder so the data is shared read-side with
# Michael. Each issue is one JSON file in .../Roundup/issues/<id>.json.
def _roundup_dir():
    """Roundup data dir under Rothany's per-user root. Created on demand."""
    d = _resolve_user_root(_ROUNDUP_OWNER_EMAIL) / "Roundup"
    try:
        (d / "issues").mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def _roundup_issue_path(issue_id: str):
    safe = "".join(ch for ch in (issue_id or "") if ch.isalnum() or ch in "-_")
    return _roundup_dir() / "issues" / f"{safe}.json"


def _roundup_new_issue(issue_label: str) -> dict:
    """Build a fresh draft issue dict (not yet persisted). issue_label is the
    human label shown in 'New Items for {label}' and the default subject."""
    label = (issue_label or "").strip() or "New Issue"
    base_id = "".join(ch for ch in label.lower().replace(" ", "-")
                      if ch.isalnum() or ch == "-") or "issue"
    # Disambiguate if a file with this id already exists.
    issue_id = base_id
    n = 2
    while _roundup_issue_path(issue_id).is_file():
        issue_id = f"{base_id}-{n}"
        n += 1
    return {
        "id": issue_id,
        "title": "The Roundup",
        "issue_label": label,
        "subject": f"The Roundup — {label}",
        "status": "draft",
        "hero_image": "",
        "marketing_minute": "",
        "playbook_callout": "",
        "new_items": [],
        "looking_ahead": [],
        "president": {"photo": "", "body": "", "name": "", "title": "President & CEO"},
        "updated_at": "",
        "sent_at": None,
    }


def _roundup_save_issue(issue: dict) -> None:
    import json as _json, datetime as _dt
    issue["updated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    path = _roundup_issue_path(issue["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(issue, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def _roundup_load_issue(issue_id: str):
    import json as _json
    path = _roundup_issue_path(issue_id)
    if not path.is_file():
        return None
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _roundup_index() -> list:
    """List saved issues newest-first: [{id, issue_label, status, updated_at}]."""
    import json as _json
    rows = []
    issues_dir = _roundup_dir() / "issues"
    if not issues_dir.is_dir():
        return rows
    for f in issues_dir.glob("*.json"):
        try:
            d = _json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append({
            "id": d.get("id", f.stem),
            "issue_label": d.get("issue_label", f.stem),
            "status": d.get("status", "draft"),
            "updated_at": d.get("updated_at", ""),
        })
    rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return rows


def _roundup_mark_sent(issue_id: str) -> None:
    import datetime as _dt
    issue = _roundup_load_issue(issue_id)
    if not issue:
        return
    issue["status"] = "sent"
    issue["sent_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    _roundup_save_issue(issue)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_the_roundup.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_the_roundup.py
git commit -m "feat(roundup): JSON issue store under owner folder"
```

---

### Task 3: Image upload helper + cache subdir

Roundup images go through the existing content-addressed cache `_email_img_src(b64, subdir, mime)` (search `def _email_img_src`). We add a `"roundup"` subdir to the route allowlist and a thin wrapper that takes raw bytes.

**Files:**
- Modify: `flowdrip_app.py` — `_serve_email_img` allowlist + new `_roundup_cache_image`
- Test: `tests/test_the_roundup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_the_roundup.py`:

```python
def test_roundup_cache_image_returns_src(monkeypatch):
    # Desktop/test mode (_SERVER_MODE False) → returns an inline data: URI.
    monkeypatch.setattr(fa, "_SERVER_MODE", False)
    png_1x1 = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
               b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
               b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
               b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
    src = fa._roundup_cache_image(png_1x1, "banner.png")
    assert src.startswith("data:image/png;base64,")


def test_roundup_cache_image_empty_returns_blank():
    assert fa._roundup_cache_image(b"", "x.png") == ""


def test_email_img_route_allows_roundup_subdir():
    # The route rejects unknown subdirs with 404 before touching disk;
    # "roundup" must be in the allowlist. We assert the allowlist source.
    import inspect
    src = inspect.getsource(fa._serve_email_img)
    assert '"roundup"' in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_the_roundup.py -k cache_image or route_allows -v`
Expected: FAIL — no attribute `_roundup_cache_image`

- [ ] **Step 3a: Add "roundup" to the route allowlist**

In `_serve_email_img`, change the allowlist tuple (search `if subdir not in ("cat", "hero", "avatar"`):

```python
    if subdir not in ("cat", "hero", "avatar", "activity", "corner",
                      "logo", "flag", "roundup"):
        return Response(status_code=404)
```

- [ ] **Step 3b: Add the wrapper helper**

Add directly below `_email_img_src` (after its `return f"https://...` line):

```python
def _roundup_cache_image(raw: bytes, filename: str = "image.png") -> str:
    """Cache an uploaded Roundup image and return its <img src> value.

    Server mode → an https URL under /email_img/roundup/. Desktop/test mode →
    an inline data: URI. Returns "" for empty input. Mirrors how newsletter
    hero images are stored, so Outlook gets a real URL, not base64 bloat."""
    if not raw:
        return ""
    import base64 as _b64m
    name = (filename or "").lower()
    if name.endswith(".png"):
        mime = "image/png"
    elif name.endswith(".gif"):
        mime = "image/gif"
    else:
        mime = "image/jpeg"
    b64 = _b64m.b64encode(raw).decode("ascii")
    return _email_img_src(b64, "roundup", mime)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_the_roundup.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_the_roundup.py
git commit -m "feat(roundup): image cache helper + roundup subdir allowlist"
```

---

### Task 4: HTML renderer

`_render_roundup_html(issue)` is a pure function: issue dict → email HTML in Arena's blue styling, matching the April layout. User-entered rich text fields already contain HTML from the editor; lead-ins and names are plain text and MUST be escaped.

**Files:**
- Modify: `flowdrip_app.py` (above `def p_newsletters`, below the store helpers)
- Test: `tests/test_the_roundup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_the_roundup.py`:

```python
def _sample_issue():
    return {
        "id": "june-2026", "title": "The Roundup", "issue_label": "June 2026",
        "subject": "The Roundup — June 2026", "status": "draft",
        "hero_image": "https://dripdripdrop.ai/email_img/roundup/abc.png",
        "marketing_minute": "<p>Welcome to the issue</p>",
        "playbook_callout": "<p>Want to be featured? Email rothany.vu@arenastaffing.net</p>",
        "new_items": [
            {"lead": "New Logos", "body": "<p>10-year logo</p>", "image": None},
            {"lead": "Notecards", "body": "<p>branded</p>",
             "image": "https://dripdripdrop.ai/email_img/roundup/nc.png"},
        ],
        "looking_ahead": [
            {"lead": "New Website", "body": "<p>Launching May 4</p>", "image": None},
        ],
        "president": {"photo": "https://dripdripdrop.ai/email_img/roundup/pr.png",
                      "body": "<p>April showers...</p>", "name": "Dave Kooiman",
                      "title": "President & CEO"},
        "updated_at": "", "sent_at": None,
    }


def test_render_includes_all_sections():
    html = fa._render_roundup_html(_sample_issue())
    assert "Marketing Minute" in html
    assert "New Items for June 2026" in html
    assert "Looking Ahead" in html
    assert "A Message From the President" in html
    assert "Welcome to the issue" in html
    assert "New Logos" in html
    assert "New Website" in html
    assert "Dave Kooiman" in html
    assert "President &amp; CEO" in html  # plain text escaped


def test_render_includes_images_and_footer():
    html = fa._render_roundup_html(_sample_issue())
    assert "email_img/roundup/abc.png" in html      # hero
    assert "email_img/roundup/nc.png" in html        # item image
    assert "email_img/roundup/pr.png" in html        # president photo
    assert "4750 Ontario Mills Pkwy" in html         # fixed footer


def test_render_handles_empty_optionals():
    issue = fa._roundup_new_issue("Empty Issue")
    html = fa._render_roundup_html(issue)
    # No crash, footer + headings still present, no stray "None".
    assert "New Items for Empty Issue" in html
    assert "None" not in html


def test_render_escapes_lead_text():
    issue = fa._roundup_new_issue("X")
    issue["new_items"] = [{"lead": "A & B <script>", "body": "<p>ok</p>",
                           "image": None}]
    html = fa._render_roundup_html(issue)
    assert "A &amp; B &lt;script&gt;" in html
    assert "<script>" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_the_roundup.py -k render -v`
Expected: FAIL — no attribute `_render_roundup_html`

- [ ] **Step 3: Implement the renderer**

Add above `def p_newsletters` (below the store helpers):

```python
# ── The Roundup: email HTML renderer ───────────────────────────────────────
_ROUNDUP_BLUE = "#2e5c8a"
_ROUNDUP_NAVY = "#1d3a5f"
_ROUNDUP_FOOTER = "Arena Staffing | 4750 Ontario Mills Pkwy | Ontario, CA 91764 US"


def _roundup_section_bar(text: str) -> str:
    from html import escape as _esc
    return (f'<tr><td style="background:{_ROUNDUP_BLUE};color:#ffffff;'
            f'text-align:center;font-weight:700;font-size:20px;padding:14px;'
            f'font-family:Arial,sans-serif;">{_esc(text)}</td></tr>')


def _roundup_items_html(items: list) -> str:
    """Render a New Items / Looking Ahead list. Each item = bold lead-in +
    body HTML + optional image. Body is editor HTML (kept); lead is escaped."""
    from html import escape as _esc
    out = []
    for it in (items or []):
        lead = _esc((it.get("lead") or "").strip())
        body = (it.get("body") or "").strip()
        img = (it.get("image") or "").strip()
        img_html = ""
        if img:
            img_html = (f'<div style="margin:6px 0;"><img src="{img}" '
                        f'style="max-width:220px;height:auto;border-radius:4px;"/></div>')
        lead_html = (f'<span style="font-weight:700;color:{_ROUNDUP_NAVY};">'
                     f'{lead}:</span> ') if lead else ""
        out.append(
            f'<div style="margin:0 0 14px;font-size:14px;line-height:1.5;'
            f'color:#444;font-family:Arial,sans-serif;">{lead_html}{body}{img_html}</div>')
    return "".join(out)


def _render_roundup_html(issue: dict) -> str:
    """Pure: issue dict → full email HTML in Arena's brand styling, matching
    the April Roundup layout. Editor-authored fields contain HTML and are kept
    as-is; plain-text fields (lead-ins, names) are escaped."""
    from html import escape as _esc
    label = (issue.get("issue_label") or "").strip()
    hero = (issue.get("hero_image") or "").strip()
    mm = (issue.get("marketing_minute") or "").strip()
    playbook = (issue.get("playbook_callout") or "").strip()
    pres = issue.get("president") or {}
    pres_photo = (pres.get("photo") or "").strip()
    pres_body = (pres.get("body") or "").strip()
    pres_name = _esc((pres.get("name") or "").strip())
    pres_title = _esc((pres.get("title") or "").strip())

    parts = []
    parts.append(
        '<div style="max-width:640px;margin:0 auto;background:#ffffff;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;">')

    # Hero banner
    if hero:
        parts.append(
            f'<tr><td style="padding:0;"><img src="{hero}" '
            f'style="width:100%;height:auto;display:block;"/></td></tr>')

    # Marketing Minute
    parts.append(_roundup_section_bar("Marketing Minute"))
    if mm:
        parts.append(
            f'<tr><td style="padding:16px 22px;font-size:14px;line-height:1.6;'
            f'color:#444;font-family:Arial,sans-serif;">{mm}</td></tr>')

    # Playbook callout
    if playbook:
        parts.append(
            f'<tr><td style="padding:0 22px;"><div style="background:#e9e4d8;'
            f'border:1px solid #b8ad94;border-radius:4px;padding:14px 16px;'
            f'font-size:14px;line-height:1.5;color:{_ROUNDUP_NAVY};'
            f'font-family:Arial,sans-serif;">{playbook}</div></td></tr>')

    # New Items
    parts.append(
        f'<tr><td style="text-align:center;font-weight:700;font-size:20px;'
        f'color:{_ROUNDUP_BLUE};padding:20px 22px 8px;'
        f'font-family:Arial,sans-serif;">New Items for {_esc(label)}</td></tr>')
    items_html = _roundup_items_html(issue.get("new_items"))
    if items_html:
        parts.append(f'<tr><td style="padding:4px 22px;">{items_html}</td></tr>')

    # Looking Ahead
    parts.append(
        f'<tr><td style="text-align:center;font-weight:700;font-size:20px;'
        f'color:{_ROUNDUP_BLUE};padding:20px 22px 8px;'
        f'font-family:Arial,sans-serif;">Looking Ahead</td></tr>')
    ahead_html = _roundup_items_html(issue.get("looking_ahead"))
    if ahead_html:
        parts.append(f'<tr><td style="padding:4px 22px;">{ahead_html}</td></tr>')

    # President
    parts.append(_roundup_section_bar("A Message From the President"))
    pres_inner = ['<td style="padding:16px 22px;text-align:center;'
                  'font-family:Arial,sans-serif;">']
    if pres_photo:
        pres_inner.append(
            f'<img src="{pres_photo}" style="width:160px;height:auto;'
            f'border-radius:4px;margin:0 auto 12px;display:block;"/>')
    if pres_body:
        pres_inner.append(
            f'<div style="font-size:14px;line-height:1.6;color:#444;'
            f'text-align:left;">{pres_body}</div>')
    if pres_name:
        pres_inner.append(
            f'<div style="margin-top:10px;font-weight:700;color:{_ROUNDUP_NAVY};'
            f'text-align:left;">{pres_name}</div>')
    if pres_title:
        pres_inner.append(
            f'<div style="color:#666;text-align:left;">{pres_title}</div>')
    pres_inner.append('</td>')
    parts.append(f'<tr>{"".join(pres_inner)}</tr>')

    # Footer (fixed)
    parts.append(
        f'<tr><td style="background:{_ROUNDUP_NAVY};color:#cfd8e3;'
        f'text-align:center;font-size:12px;padding:16px;'
        f'font-family:Arial,sans-serif;">{_esc(_ROUNDUP_FOOTER)}</td></tr>')

    parts.append('</table></div>')
    return "".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_the_roundup.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_the_roundup.py
git commit -m "feat(roundup): brand-styled email HTML renderer"
```

---

### Task 5: Recipient parsing helper (for send)

Extract the recipient-list parsing as a pure helper so the send action is testable. Mirrors the dedupe/validation logic in `_send_now_dialog._do_send` (search `_raw = (_recip_ta.value`).

**Files:**
- Modify: `flowdrip_app.py` (above `def p_newsletters`)
- Test: `tests/test_the_roundup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_the_roundup.py`:

```python
def test_parse_recipients_dedupes_and_validates():
    raw = "a@x.com, b@y.com\nA@X.COM\nnot-an-email\nc@z.io"
    out = fa._roundup_parse_recipients(raw)
    assert out == ["a@x.com", "b@y.com", "c@z.io"]  # dedupe case-insensitive, drop junk


def test_parse_recipients_empty():
    assert fa._roundup_parse_recipients("") == []
    assert fa._roundup_parse_recipients(None) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_the_roundup.py -k parse_recipients -v`
Expected: FAIL — no attribute `_roundup_parse_recipients`

- [ ] **Step 3: Implement the helper**

Add above `def p_newsletters`:

```python
def _roundup_parse_recipients(raw: str) -> list:
    """Split a comma/newline recipient blob into a deduped, validated list of
    addresses (original casing kept; dedupe is case-insensitive)."""
    out, seen = [], set()
    for line in (raw or "").replace(",", "\n").splitlines():
        e = line.strip()
        if not e or e.lower() in seen:
            continue
        if "@" not in e or "." not in e.split("@")[-1]:
            continue
        seen.add(e.lower())
        out.append(e)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_the_roundup.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_the_roundup.py
git commit -m "feat(roundup): recipient-list parsing helper"
```

---

### Task 6: Editor tab + send (UI wiring)

This wires the tested helpers into the Newsletters page. UI code isn't unit-tested here (the helpers it calls already are); verify by import + manual run. Two changes: (a) a gated tab toggle in `p_newsletters`; (b) the Roundup tab body (`_roundup_tab`) with the section editor and a send dialog.

**Files:**
- Modify: `flowdrip_app.py` — `p_newsletters` (tab toggle) + new `_roundup_tab`, `_roundup_editor`, `_roundup_send_dialog`

- [ ] **Step 1: Add the gated tab toggle in `p_newsletters`**

Right after `_render_page_intro_strip(s, rf, "newsletters")` (search it) and before the `_render_nl_first_gen_status` call, insert:

```python
        # ── The Roundup tab (gated) ───────────────────────────────────────
        # Owner (Rothany) + Michael see a two-tab switch. Everyone else falls
        # straight through to the standard AI-newsletter page (no trace).
        _roundup_ok = _roundup_allowed(getattr(s, "_user_email", "") or "")
        if _roundup_ok:
            _active_tab = getattr(s, "_nl_active_tab", "market")
            with ui.element("div").style(
                    "display:flex;justify-content:center;gap:8px;"
                    "margin:0 0 18px;"):
                for _key, _lbl in (("market", "Market Newsletters"),
                                   ("roundup", "The Roundup")):
                    _is_on = (_active_tab == _key)
                    def _switch(k=_key):
                        s._nl_active_tab = k
                        rf()
                    with ui.element("button").style(
                            f"padding:8px 20px;font-size:13px;font-weight:700;"
                            f"border-radius:8px;cursor:pointer;font-family:inherit;"
                            f"border:1px solid {C['border']};"
                            f"background:{C['teal'] if _is_on else 'transparent'};"
                            f"color:{'#fff' if _is_on else C['muted']};"
                            ).on("click", _switch):
                        ui.label(_lbl).style("pointer-events:none;")
            if _active_tab == "roundup":
                _roundup_tab(s, rf)
                return
```

(Placing the `return` inside the `roundup` branch means the rest of `p_newsletters` — the AI-newsletter cards — only renders for the "market" tab or non-gated users.)

- [ ] **Step 2: Add `_roundup_tab`, `_roundup_editor`, `_roundup_send_dialog`**

Add these just above `def p_newsletters`:

```python
# ── The Roundup: page (tab body) ───────────────────────────────────────────
def _roundup_tab(s, rf):
    """Issue list + 'New Issue' for The Roundup. Selecting an issue opens the
    section editor. Owner edits; Michael views + can send."""
    _is_owner = ((getattr(s, "_user_email", "") or "").strip().lower()
                 == _ROUNDUP_OWNER_EMAIL)
    editing_id = getattr(s, "_roundup_editing_id", None)
    if editing_id:
        issue = _roundup_load_issue(editing_id)
        if issue:
            _roundup_editor(s, rf, issue, can_edit=_is_owner)
            return
        s._roundup_editing_id = None  # stale id → fall back to list

    ui.label("The Roundup").classes("fd-h1").style(
        "margin:0 0 4px;text-align:center;")
    ui.label("Arena's internal company newsletter. "
             + ("Create or edit an issue, then send it to all staff."
                if _is_owner else "View issues Rothany has drafted or sent.")
             ).classes("fd-sub").style("text-align:center;margin-bottom:18px;")

    if _is_owner:
        _new_label = {"v": ""}
        with ui.element("div").style(
                "display:flex;justify-content:center;gap:8px;margin-bottom:20px;"):
            _lbl_in = ui.input(placeholder="Issue label, e.g. June 2026").style(
                "min-width:240px;")
            def _create():
                lbl = (_lbl_in.value or "").strip()
                if not lbl:
                    ui.notify("Give the issue a label first (e.g. June 2026).",
                              type="warning"); return
                issue = _roundup_new_issue(lbl)
                _roundup_save_issue(issue)
                s._roundup_editing_id = issue["id"]
                rf()
            with ui.element("button").classes("fd-pb").style(
                    "padding:9px 22px;font-size:13px;").on("click", _create):
                ui.label("+ New Issue")

    rows = _roundup_index()
    if not rows:
        ui.label("No issues yet." if _is_owner
                 else "Rothany hasn't drafted any issues yet.").style(
            f"text-align:center;color:{C['muted']};margin-top:24px;")
        return

    with ui.element("div").style("max-width:640px;margin:0 auto;"):
        for r in rows:
            _sent = (r.get("status") == "sent")
            with ui.element("div").style(
                    f"display:flex;align-items:center;justify-content:space-between;"
                    f"gap:12px;padding:14px 16px;margin-bottom:10px;"
                    f"background:{C['card']};border:1px solid {C['border']};"
                    f"border-radius:10px;"):
                with ui.element("div"):
                    ui.label(r["issue_label"]).style(
                        f"font-weight:700;color:{C['text_l']};font-size:15px;")
                    ui.label("Sent " + (r.get("updated_at", "")[:10]) if _sent
                             else "Draft").style(
                        f"font-size:12px;color:{'#3a8' if _sent else C['muted']};")
                def _open(rid=r["id"]):
                    s._roundup_editing_id = rid
                    rf()
                with ui.element("button").classes("fd-gb").style(
                        "padding:7px 16px;font-size:12px;").on("click", _open):
                    ui.label("Open" if _is_owner else "View")


def _roundup_editor(s, rf, issue: dict, can_edit: bool):
    """Section-based editor for one issue. can_edit=False → read-only preview
    (Michael). editor.js rich-text reused via _apply_editor_props."""
    def _back():
        s._roundup_editing_id = None
        rf()

    with ui.element("div").style(
            "display:flex;align-items:center;justify-content:space-between;"
            "max-width:760px;margin:0 auto 16px;"):
        with ui.element("button").classes("fd-gb").style(
                "padding:7px 16px;font-size:12px;").on("click", _back):
            ui.label("← Back")
        ui.label(issue.get("issue_label", "Issue")).style(
            f"font-weight:800;font-size:18px;color:{C['text_l']};")

    if not can_edit:
        # Read-only: render the email preview only.
        with ui.element("div").style(
                "max-width:760px;margin:0 auto;border:1px solid "
                f"{C['border']};border-radius:10px;overflow:hidden;"):
            ui.html(_render_roundup_html(issue))
        return

    # Editable form. Widgets write back into `issue` on save.
    refs = {}
    with ui.element("div").style("max-width:760px;margin:0 auto;"):
        ui.label("Subject line").classes("fd-fl")
        refs["subject"] = ui.input(value=issue.get("subject", "")).style(
            "width:100%;margin-bottom:14px;")

        refs["hero_image"] = {"v": issue.get("hero_image", "")}
        _roundup_image_field(s, "Banner image", refs["hero_image"])

        ui.label("Marketing Minute").classes("fd-fl").style("margin-top:14px;")
        refs["marketing_minute"] = _apply_editor_props(
            ui.editor(value=issue.get("marketing_minute", "")), _TOOLBAR_FULL
            ).style("min-height:160px;border-radius:6px;")

        ui.label("The Playbook callout").classes("fd-fl").style("margin-top:14px;")
        refs["playbook_callout"] = _apply_editor_props(
            ui.editor(value=issue.get("playbook_callout", "")), _TOOLBAR_FULL
            ).style("min-height:110px;border-radius:6px;")

        refs["new_items"] = _roundup_item_list(
            s, "New Items", issue.get("new_items", []))
        refs["looking_ahead"] = _roundup_item_list(
            s, "Looking Ahead", issue.get("looking_ahead", []))

        ui.label("A Message From the President").classes("fd-fl").style(
            "margin-top:18px;")
        pres = issue.get("president", {}) or {}
        refs["pres_photo"] = {"v": pres.get("photo", "")}
        _roundup_image_field(s, "President photo", refs["pres_photo"])
        refs["pres_name"] = ui.input(
            value=pres.get("name", ""), placeholder="Name").style(
            "width:100%;margin-top:8px;")
        refs["pres_title"] = ui.input(
            value=pres.get("title", "President & CEO"),
            placeholder="Title").style("width:100%;margin-top:8px;")
        refs["pres_body"] = _apply_editor_props(
            ui.editor(value=pres.get("body", "")), _TOOLBAR_FULL
            ).style("min-height:200px;border-radius:6px;margin-top:8px;")

        def _collect():
            issue["subject"] = refs["subject"].value
            issue["hero_image"] = refs["hero_image"]["v"]
            issue["marketing_minute"] = refs["marketing_minute"].value
            issue["playbook_callout"] = refs["playbook_callout"].value
            issue["new_items"] = [r() for r in refs["new_items"]]
            issue["looking_ahead"] = [r() for r in refs["looking_ahead"]]
            issue["president"] = {
                "photo": refs["pres_photo"]["v"],
                "body": refs["pres_body"].value,
                "name": refs["pres_name"].value,
                "title": refs["pres_title"].value,
            }

        with ui.element("div").style(
                "display:flex;gap:10px;justify-content:flex-end;margin:22px 0;"):
            def _save():
                _collect()
                _roundup_save_issue(issue)
                ui.notify("Saved.", type="positive")
            def _send():
                _collect()
                _roundup_save_issue(issue)
                _roundup_send_dialog(s, rf, issue)
            with ui.element("button").classes("fd-gb").style(
                    "padding:9px 20px;font-size:13px;").on("click", _save):
                ui.label("Save")
            with ui.element("button").classes("fd-pb").style(
                    f"padding:9px 22px;font-size:13px;background:{C['teal']};"
                    ).on("click", _send):
                ui.label("Send to all staff →")


def _roundup_image_field(s, label: str, ref: dict):
    """Upload widget bound to ref['v'] (an <img src> string). Shows the current
    image. Uses the NiceGUI 3.x upload API (await e.file.read())."""
    ui.label(label).classes("fd-fl")
    _preview = ui.html(
        f'<img src="{ref["v"]}" style="max-height:80px;border-radius:4px;"/>'
        if ref["v"] else '<span style="color:#888;font-size:12px;">No image</span>')

    async def _on_upload(e):
        f = getattr(e, "file", None)
        if f is None:
            ui.notify("Upload failed.", type="negative"); return
        try:
            raw = await f.read()
        except Exception:
            ui.notify("Upload failed.", type="negative"); return
        if len(raw) > _MAX_IMAGE_BYTES:
            ui.notify("Image must be under 5 MB.", type="warning"); return
        src = _roundup_cache_image(raw, getattr(f, "name", "image.png"))
        if not src:
            ui.notify("That file isn't a valid image.", type="negative"); return
        ref["v"] = src
        _preview.set_content(
            f'<img src="{src}" style="max-height:80px;border-radius:4px;"/>')
    ui.upload(on_upload=_on_upload, auto_upload=True, max_file_size=5*1024*1024,
              ).props('accept="image/*" flat color="teal"')


def _roundup_item_list(s, label: str, items: list):
    """Render an editable repeatable item list. Returns a list of getter
    callables; each returns {'lead','body','image'} for one row."""
    ui.label(label).classes("fd-fl").style("margin-top:16px;")
    getters = []
    container = ui.element("div")

    def _add_row(seed=None):
        seed = seed or {"lead": "", "body": "", "image": ""}
        with container:
            with ui.element("div").style(
                    f"border:1px solid {C['border']};border-radius:8px;"
                    f"padding:12px;margin-bottom:10px;"):
                lead_in = ui.input(value=seed.get("lead", ""),
                                   placeholder="Bold lead-in (e.g. New Website)"
                                   ).style("width:100%;margin-bottom:6px;")
                body_ed = _apply_editor_props(
                    ui.editor(value=seed.get("body", "")), _TOOLBAR_FULL
                    ).style("min-height:90px;border-radius:6px;")
                img_ref = {"v": seed.get("image", "") or ""}
                _roundup_image_field(s, "Item image (optional)", img_ref)
                def _get(li=lead_in, be=body_ed, ir=img_ref):
                    return {"lead": li.value, "body": be.value,
                            "image": ir["v"] or None}
                getters.append(_get)

    for it in (items or []):
        _add_row(it)
    with ui.element("button").classes("fd-gb").style(
            "padding:6px 14px;font-size:12px;margin-bottom:8px;").on(
            "click", lambda: _add_row()):
        ui.label("+ Add item")
    return getters


def _roundup_send_dialog(s, rf, issue: dict):
    """Confirm + send the rendered issue to a saved staff list. Sends as the
    OWNER (Rothany) regardless of who clicks, so the From identity and the
    issue's sent-status write both happen in Rothany's context."""
    saved = list_saved_contact_lists() or {}
    body_html = _render_roundup_html(issue)
    subject = (issue.get("subject")
               or f"The Roundup — {issue.get('issue_label', '')}").strip()

    with ui.dialog() as dlg, ui.card().style(
            f"background:{C['card']};border:1px solid {C['border']};"
            f"min-width:480px;max-width:560px;padding:24px 26px;"):
        ui.label("Send The Roundup to all staff").style(
            f"font-size:18px;font-weight:800;color:{C['text_l']};"
            f"margin-bottom:8px;")
        if not saved:
            ui.label("No saved contact lists yet. Import an 'All Arena Staff' "
                     "CSV from the Contact List page first.").style(
                f"font-size:13px;color:{C['muted']};")
            with ui.element("button").classes("fd-gb").style(
                    "padding:8px 18px;font-size:12px;margin-top:14px;").on(
                    "click", dlg.close):
                ui.label("Close")
            dlg.open(); return

        ui.label("Pick the staff recipient list:").classes("fd-fl")
        _list_sel = ui.select(options=sorted(saved.keys()),
                              value=sorted(saved.keys())[0]).style(
            "width:100%;margin-bottom:16px;")

        def _do_send():
            name = (_list_sel.value or "").strip()
            path = saved.get(name)
            if not path:
                ui.notify("Pick a list first.", type="warning"); return
            try:
                rows, _ = safe_read_csv_rows(path)
                contacts = _normalize_rows(rows)
            except Exception as ex:
                ui.notify(f"Couldn't read '{name}': {str(ex)[:80]}",
                          type="negative"); return
            recips = _roundup_parse_recipients(
                "\n".join((c.get("Email") or "") for c in contacts))
            if not recips:
                ui.notify(f"'{name}' has no valid emails.", type="warning"); return
            dlg.close()
            ui.notify(f"Sending The Roundup to {len(recips)} staff…",
                      type="ongoing", timeout=4000)
            _iid = issue["id"]
            def _worker():
                ok = fail = 0
                for addr in recips:
                    try:
                        sent, err = _send_email_universal(
                            to=addr, subject=subject, html_body=body_html,
                            attachments=[], is_preview=False,
                            _for_user_email=_ROUNDUP_OWNER_EMAIL)
                        ok += 1 if sent else 0
                        fail += 0 if sent else 1
                        if not sent:
                            print(f"[Roundup] {addr} failed: {err}", flush=True)
                    except Exception as ex:
                        fail += 1
                        print(f"[Roundup] {addr} crashed: {ex}", flush=True)
                _roundup_mark_sent(_iid)
                print(f"[Roundup] Done — {ok} sent, {fail} failed.", flush=True)
            # Run in the OWNER's context so signature + issue write land in
            # Rothany's folder (multi-user safety: explicit email, never ambient).
            _run_as_user(_ROUNDUP_OWNER_EMAIL, _worker, name="roundup_send_worker")

        with ui.element("div").style(
                "display:flex;gap:8px;justify-content:flex-end;"):
            with ui.element("button").classes("fd-gb").style(
                    "padding:8px 18px;font-size:12px;").on("click", dlg.close):
                ui.label("Cancel")
            with ui.element("button").classes("fd-pb").style(
                    f"padding:8px 22px;font-size:13px;background:{C['teal']};"
                    ).on("click", _do_send):
                ui.label("Send now →")
    dlg.open()
```

- [ ] **Step 3: Smoke-check the module imports**

Run: `python -c "import flowdrip_app"`
Expected: no output, exit 0 (no syntax/NameError). If `_TOOLBAR_FULL`, `_apply_editor_props`, `_MAX_IMAGE_BYTES`, `safe_read_csv_rows`, `_normalize_rows`, `_send_email_universal`, or `_run_as_user` resolve with a NameError, search the file for the correct symbol name and fix the reference.

- [ ] **Step 4: Run the full new test file (helpers still green)**

Run: `python -m pytest tests/test_the_roundup.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(roundup): gated tab, section editor, and send dialog"
```

---

### Task 7: Regression + manual verification

**Files:** none (verification only)

- [ ] **Step 1: Full test suite stays green**

Run: `python -m pytest -q`
Expected: all pass — confirms the AI-newsletter flow and the rest of the app are untouched.

- [ ] **Step 2: Manual smoke (deploy or local run per project policy)**

Per memory `feedback_auto_deploy` / `feedback_smoke_check_before_deploy`, deploy with `bash _deploy_zero_downtime.sh` and verify the live `/` renders, then:
1. As a NON-allowed account: Newsletters page shows no tabs, no Roundup trace.
2. As Rothany: two tabs appear; "The Roundup" → "+ New Issue" → fill sections, upload a banner image, Save, reopen → content persists.
3. Preview matches the April layout (hero, blue bars, callout, items, president, footer).
4. As Michael: Roundup tab shows read-only preview of Rothany's issue; Send button present.
5. Send to a small test list → recipients receive it; issue flips to "Sent".

- [ ] **Step 3: Commit any fixes from manual testing**

```bash
git add -A && git commit -m "fix(roundup): adjustments from manual verification"
```

---

## Self-review notes

- **Spec coverage:** gate (T1), shared owner-rooted store (T2), image upload+cache (T3), brand renderer (T4), recipient parsing (T5), gated tab + editor + send-as-owner (T6), regression + manual (T7). All spec sections map to a task.
- **Multi-user safety:** every owner-folder access uses an explicit `_ROUNDUP_OWNER_EMAIL` (store via `_resolve_user_root(OWNER)`, send via `_run_as_user(OWNER, ...)`) — never ambient context, per the signature-leak incident.
- **Type consistency:** issue dict shape is defined once in `_roundup_new_issue` (T2) and consumed identically by `_render_roundup_html` (T4), `_roundup_editor` (T6), and the send dialog (T6). Item shape `{lead, body, image}` is consistent across `_roundup_items_html`, `_roundup_item_list`, and tests.
- **Symbol risk:** T6 depends on existing symbols (`_apply_editor_props`, `_TOOLBAR_FULL`, `_MAX_IMAGE_BYTES`, `safe_read_csv_rows`, `_normalize_rows`, `_send_email_universal`, `_run_as_user`) verified present during planning; Step 3 of T6 is an import smoke check to catch any rename.

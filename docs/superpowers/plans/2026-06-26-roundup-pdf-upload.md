# The Roundup — PDF-Upload Newsletter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Rothany upload a finished PDF newsletter and send it to all Arena Staff with the layout and pictures preserved exactly — replacing the hand-filled section editor.

**Architecture:** Render each PDF page to a hosted PNG with PyMuPDF and stack the pages as the email body; auto-extract embedded hyperlinks into a "Links in this issue" block. The renderer branches on a new `format:"pdf"` issue field; the gated tab, shared store, and send-as-owner flow are unchanged.

**Tech Stack:** Python, NiceGUI 3.x, PyMuPDF (`fitz`), pytest. All edits are in `flowdrip_app.py`; tests in `tests/test_the_roundup.py`.

**Spec:** `docs/superpowers/specs/2026-06-26-roundup-pdf-upload-design.md`

---

## File Structure

- **Modify** `flowdrip_app.py`:
  - Add `_ROUNDUP_PDF_MAX_BYTES`, `_ROUNDUP_PDF_MAX_PAGES` constants + `_roundup_link_label()` + `_roundup_pdf_to_pages()` (conversion helpers, near the other `_roundup_*` helpers ~L23985).
  - Add `_render_roundup_pdf_html()` and a `format=="pdf"` branch at the top of `_render_roundup_html()` (~L24023).
  - Change `_roundup_new_issue()` to emit `format/pages/links/pdf_name` and drop section defaults (~L23905).
  - Replace the editable section form in `_roundup_editor()` (~L24208–24281) with the PDF-upload form.
- **Modify** `tests/test_the_roundup.py`: add PDF-conversion + PDF-render tests; update the three tests that build issues via `_roundup_new_issue`.
- **Modify** `requirements.txt`: add `pymupdf`.

The legacy section renderer (`_render_roundup_html` body, `_roundup_items_html`, `_roundup_section_bar`) is **kept** so any pre-`format` issue still renders. `_roundup_image_field` / `_roundup_item_list` become unused by the editor but are left in place (no callers, harmless) to keep the diff focused.

---

## Task 1: PDF → page-images + links conversion helper

**Files:**
- Modify: `flowdrip_app.py` (add helpers after `_roundup_parse_recipients`, ~L23987)
- Modify: `requirements.txt`
- Test: `tests/test_the_roundup.py`

- [ ] **Step 1: Add PyMuPDF to requirements**

Add this line to `requirements.txt` (alphabetical-ish, near other deps):

```
pymupdf
```

- [ ] **Step 2: Install it locally so tests can run**

Run: `pip install pymupdf`
Expected: `Successfully installed pymupdf-...` (provides the `fitz` module; manylinux wheel, no system deps).

- [ ] **Step 3: Write the failing tests**

Add to `tests/test_the_roundup.py`:

```python
def test_roundup_link_label_strips_scheme_and_www():
    assert fa._roundup_link_label("https://www.arena.example/apply") == "arena.example/apply"
    assert fa._roundup_link_label("http://x.io/") == "x.io"
    assert fa._roundup_link_label("") == ""


def _one_page_pdf_with_link():
    """Build a 1-page PDF (in memory) containing one URI link annotation."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((20, 50), "Hello team")
    page.insert_link({"kind": fitz.LINK_URI,
                      "from": fitz.Rect(20, 60, 160, 80),
                      "uri": "https://arena.example/apply"})
    raw = doc.tobytes()
    doc.close()
    return raw


def test_pdf_to_pages_renders_page_images_and_links(monkeypatch):
    # Desktop/test mode → _roundup_cache_image returns inline data: URIs.
    monkeypatch.setattr(fa, "_SERVER_MODE", False)
    pages, links = fa._roundup_pdf_to_pages(_one_page_pdf_with_link())
    assert len(pages) == 1
    assert pages[0].startswith("data:image/png;base64,")
    assert links == [{"url": "https://arena.example/apply",
                      "label": "arena.example/apply"}]


def test_pdf_to_pages_rejects_non_pdf():
    assert fa._roundup_pdf_to_pages(b"this is not a pdf") == ([], [])
    assert fa._roundup_pdf_to_pages(b"") == ([], [])
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_the_roundup.py -k "link_label or pdf_to_pages" -v`
Expected: FAIL — `AttributeError: module 'flowdrip_app' has no attribute '_roundup_link_label'`.

- [ ] **Step 5: Implement the helpers**

Insert after `_roundup_parse_recipients` (before the `# ── The Roundup: email HTML renderer ──` comment, ~L23987):

```python
# ── The Roundup: PDF → page-image conversion ───────────────────────────────
_ROUNDUP_PDF_MAX_BYTES = 20 * 1024 * 1024   # 20 MB upload ceiling
_ROUNDUP_PDF_MAX_PAGES = 30                  # rasterization guardrail


def _roundup_link_label(url: str) -> str:
    """Human-ish label for a raw URL: drop scheme + leading www., trim length."""
    s = (url or "").strip()
    low = s.lower()
    for pre in ("https://", "http://"):
        if low.startswith(pre):
            s = s[len(pre):]
            break
    if s.lower().startswith("www."):
        s = s[4:]
    s = s.rstrip("/")
    return (s[:60] + "…") if len(s) > 60 else s


def _roundup_pdf_to_pages(raw: bytes):
    """Convert PDF bytes → (page_image_srcs, links).

    Renders each page to a 144-DPI PNG hosted via _roundup_cache_image (https
    URL in server mode, inline data: URI in desktop/test mode), and extracts
    embedded hyperlinks (deduped by URL, order preserved). Returns ([], []) on
    empty / over-limit / unreadable / non-PDF input — never raises."""
    if not raw or len(raw) > _ROUNDUP_PDF_MAX_BYTES:
        return [], []
    try:
        import fitz  # PyMuPDF
    except Exception:
        return [], []
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        return [], []
    pages, links, seen = [], [], set()
    try:
        for i, page in enumerate(doc):
            if i >= _ROUNDUP_PDF_MAX_PAGES:
                break
            try:
                png = page.get_pixmap(dpi=144).tobytes("png")
            except Exception:
                continue
            src = _roundup_cache_image(png, f"page{i + 1}.png")
            if src:
                pages.append(src)
            for lk in (page.get_links() or []):
                uri = (lk.get("uri") or "").strip()
                if uri and uri.lower() not in seen:
                    seen.add(uri.lower())
                    links.append({"url": uri, "label": _roundup_link_label(uri)})
    finally:
        doc.close()
    return pages, links
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_the_roundup.py -k "link_label or pdf_to_pages" -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add flowdrip_app.py requirements.txt tests/test_the_roundup.py
git commit -m "feat(roundup): PDF → page-image + link extraction helper"
```

---

## Task 2: Render a PDF issue to email HTML

**Files:**
- Modify: `flowdrip_app.py` (`_render_roundup_html` ~L24023; add `_render_roundup_pdf_html`)
- Test: `tests/test_the_roundup.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_the_roundup.py`:

```python
def _pdf_issue(links=True):
    return {
        "id": "june-2026", "title": "The Roundup", "issue_label": "June 2026",
        "subject": "The Roundup — June 2026", "status": "draft", "format": "pdf",
        "pages": ["https://dripdripdrop.ai/email_img/roundup/p1.png",
                  "https://dripdripdrop.ai/email_img/roundup/p2.png"],
        "links": ([{"url": "https://arena.example/apply",
                    "label": "arena.example/apply"}] if links else []),
        "pdf_name": "June2026.pdf", "updated_at": "", "sent_at": None,
    }


def test_render_pdf_issue_stacks_pages_and_footer():
    html = fa._render_roundup_html(_pdf_issue())
    assert "email_img/roundup/p1.png" in html
    assert "email_img/roundup/p2.png" in html
    assert "4750 Ontario Mills Pkwy" in html       # fixed footer kept
    assert "Marketing Minute" not in html          # no section layout


def test_render_pdf_issue_includes_links_block():
    html = fa._render_roundup_html(_pdf_issue(links=True))
    assert "Links in this issue" in html
    assert 'href="https://arena.example/apply"' in html
    assert "arena.example/apply" in html           # label text


def test_render_pdf_issue_omits_links_block_when_none():
    html = fa._render_roundup_html(_pdf_issue(links=False))
    assert "Links in this issue" not in html
    assert "email_img/roundup/p1.png" in html       # pages still render
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_the_roundup.py -k "render_pdf_issue" -v`
Expected: FAIL — current renderer ignores `format`, so `Marketing Minute` appears and the links block is absent.

- [ ] **Step 3: Add the PDF renderer and branch**

Add this function immediately **before** `def _render_roundup_html` (~L24023):

```python
def _render_roundup_pdf_html(issue: dict) -> str:
    """Render a PDF-format issue: stacked full-width page images, an optional
    'Links in this issue' block, then the fixed Arena footer."""
    from html import escape as _esc
    pages = issue.get("pages") or []
    links = issue.get("links") or []
    parts = ['<div style="max-width:700px;margin:0 auto;background:#ffffff;">'
             '<table role="presentation" width="100%" cellpadding="0" '
             'cellspacing="0" style="border-collapse:collapse;">']
    for src in pages:
        s = (src or "").strip()
        if not s:
            continue
        parts.append(
            f'<tr><td style="padding:0;"><img src="{s}" '
            f'style="width:100%;max-width:700px;height:auto;display:block;'
            f'border:0;"/></td></tr>')
    if links:
        parts.append(_roundup_section_bar("🔗 Links in this issue"))
        items = []
        for lk in links:
            url = _esc((lk.get("url") or "").strip())
            label = _esc((lk.get("label") or lk.get("url") or "").strip())
            if not url:
                continue
            items.append(
                f'<div style="margin:6px 0;font-size:14px;'
                f'font-family:Arial,sans-serif;">'
                f'<a href="{url}" style="color:{_ROUNDUP_BLUE};">{label}</a></div>')
        if items:
            parts.append(
                f'<tr><td style="padding:14px 22px;">{"".join(items)}</td></tr>')
    parts.append(
        f'<tr><td style="background:{_ROUNDUP_NAVY};color:#cfd8e3;'
        f'text-align:center;font-size:12px;padding:16px;'
        f'font-family:Arial,sans-serif;">{_esc(_ROUNDUP_FOOTER)}</td></tr>')
    parts.append('</table></div>')
    return "".join(parts)
```

Then add the branch as the first lines inside `_render_roundup_html`, right after its docstring (before `from html import escape as _esc`):

```python
    if (issue.get("format") or "").lower() == "pdf":
        return _render_roundup_pdf_html(issue)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_the_roundup.py -k "render_pdf_issue" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add flowdrip_app.py tests/test_the_roundup.py
git commit -m "feat(roundup): render PDF-format issues as stacked page images + links"
```

---

## Task 3: New issues default to PDF format

**Files:**
- Modify: `flowdrip_app.py` (`_roundup_new_issue` ~L23905)
- Test: `tests/test_the_roundup.py`

- [ ] **Step 1: Update the existing test to expect the new shape**

Replace `test_roundup_new_issue_has_default_subject_and_status` in `tests/test_the_roundup.py` with:

```python
def test_roundup_new_issue_has_default_subject_and_pdf_format():
    issue = fa._roundup_new_issue("July 2026")
    assert issue["status"] == "draft"
    assert issue["subject"] == "The Roundup — July 2026"
    assert issue["format"] == "pdf"
    assert issue["pages"] == []
    assert issue["links"] == []
    assert issue["pdf_name"] == ""
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_the_roundup.py -k "new_issue_has_default" -v`
Expected: FAIL — `KeyError: 'format'`.

- [ ] **Step 3: Update `_roundup_new_issue`**

Replace the `return {...}` block in `_roundup_new_issue` (~L23905–23919) with:

```python
    return {
        "id": issue_id,
        "title": "The Roundup",
        "issue_label": label,
        "subject": f"The Roundup — {label}",
        "status": "draft",
        "format": "pdf",
        "pages": [],
        "links": [],
        "pdf_name": "",
        "updated_at": "",
        "sent_at": None,
    }
```

- [ ] **Step 4: Fix the two other tests that relied on section defaults**

`test_render_handles_empty_optionals` previously asserted section headings on a `_roundup_new_issue`. A new issue is now an empty PDF issue. Replace it with:

```python
def test_render_handles_empty_pdf_issue():
    issue = fa._roundup_new_issue("Empty Issue")
    html = fa._render_roundup_html(issue)        # no pages, no links
    assert "4750 Ontario Mills Pkwy" in html      # footer still renders
    assert "None" not in html                     # no stray None
    assert "<img" not in html                     # nothing to stack yet
```

`test_render_escapes_lead_text` tests the **legacy** section renderer's escaping. Make it build a legacy issue explicitly (no `format` key) so it exercises that branch:

```python
def test_render_escapes_lead_text():
    issue = dict(_sample_issue())                 # _sample_issue has no "format"
    issue["new_items"] = [{"lead": "A & B <script>", "body": "<p>ok</p>",
                           "image": None}]
    html = fa._render_roundup_html(issue)
    assert "A &amp; B &lt;script&gt;" in html
    assert "<script>" not in html
```

- [ ] **Step 5: Run the full Roundup suite**

Run: `pytest tests/test_the_roundup.py -v`
Expected: PASS (all tests, including legacy `test_render_includes_all_sections` which uses `_sample_issue` with no `format`).

- [ ] **Step 6: Commit**

```bash
git add flowdrip_app.py tests/test_the_roundup.py
git commit -m "feat(roundup): new issues default to PDF-upload format"
```

---

## Task 4: Replace the section editor with a PDF-upload form

**Files:**
- Modify: `flowdrip_app.py` (`_roundup_editor` editable branch, ~L24208–24281)
- Test: `tests/test_qeditor_registration.py` (must stay green — fewer editors now)

This task is UI wiring; it is verified by manual UI check + the regression test, not a new unit test (the upload handler needs a live NiceGUI client).

- [ ] **Step 1: Replace the editable form block**

In `_roundup_editor`, replace everything from `# Editable form. Widgets write back into `issue` on save.` through the end of the function (the `refs = {}` block and both buttons, ~L24208–24281) with:

```python
    # PDF-upload form. Subject + uploaded PDF (rendered to stacked page images).
    refs = {}
    with ui.element("div").style("max-width:760px;margin:0 auto;"):
        ui.label("Subject line").classes("fd-fl")
        refs["subject"] = ui.input(value=issue.get("subject", "")).style(
            "width:100%;margin-bottom:14px;")

        ui.label("Newsletter PDF").classes("fd-fl")
        ui.label("Upload your finished newsletter as a PDF. Each page becomes "
                 "part of the email, exactly as you designed it.").style(
            f"font-size:12px;color:{C['muted']};margin-bottom:6px;")

        _preview_box = ui.html("")

        def _render_preview():
            if issue.get("pages"):
                _preview_box.set_content(
                    f'<div style="border:1px solid {C["border"]};'
                    f'border-radius:8px;overflow:hidden;margin:10px 0;">'
                    f'{_render_roundup_html(issue)}</div>')
            else:
                _preview_box.set_content(
                    '<span style="color:#888;font-size:12px;">'
                    'No PDF uploaded yet.</span>')

        async def _on_pdf(e):
            f = getattr(e, "file", None)
            if f is None:
                ui.notify("Upload failed.", type="negative"); return
            try:
                raw = await f.read()
            except Exception:
                ui.notify("Upload failed.", type="negative"); return
            pages, links = _roundup_pdf_to_pages(raw)
            if not pages:
                ui.notify("That file isn't a readable PDF.", type="negative")
                return
            issue["format"] = "pdf"
            issue["pages"] = pages
            issue["links"] = links
            issue["pdf_name"] = getattr(f, "name", "newsletter.pdf")
            _roundup_save_issue(issue)
            _render_preview()
            ui.notify(f"Loaded {len(pages)} page(s).", type="positive")

        ui.upload(on_upload=_on_pdf, auto_upload=True,
                  max_file_size=_ROUNDUP_PDF_MAX_BYTES,
                  ).props('accept="application/pdf" flat color="teal"')
        _render_preview()

        def _collect():
            issue["subject"] = refs["subject"].value

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
```

(The read-only branch above this — Michael's `if not can_edit:` preview — is unchanged; it already renders `_render_roundup_html`, which now handles PDF issues.)

- [ ] **Step 2: Verify import still succeeds**

Run: `python -c "import flowdrip_app"`
Expected: no output, exit 0 (no syntax/NameError; `_roundup_pdf_to_pages` and `_ROUNDUP_PDF_MAX_BYTES` are defined above the editor).

- [ ] **Step 3: Verify the editor-registration regression test still passes**

Run: `pytest tests/test_qeditor_registration.py -v`
Expected: PASS — the PDF form contains no `ui.editor`, so there is nothing new to register.

- [ ] **Step 4: Commit**

```bash
git add flowdrip_app.py
git commit -m "feat(roundup): replace section editor with PDF-upload form"
```

---

## Task 5: Full verification + manual UI check

**Files:** none (verification only)

- [ ] **Step 1: Run the whole Roundup + registration suite**

Run: `pytest tests/test_the_roundup.py tests/test_qeditor_registration.py -v`
Expected: all PASS.

- [ ] **Step 2: Confirm the module imports clean**

Run: `python -c "import flowdrip_app; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Manual UI smoke (live/dev), as an allowed account**

1. Open the Newsletters page → **The Roundup** tab.
2. **New Issue** → name it (e.g. "Test June 2026").
3. Upload a multi-page PDF that contains at least one hyperlink.
4. Confirm the preview shows every page stacked in order and a "Links in this issue" block listing the link.
5. Upload a non-PDF file → confirm the "That file isn't a readable PDF." error and no broken preview.
6. **Save**, go Back, re-open the issue → confirm pages/preview persist (issue stored under owner's folder).
7. (Optional, real send) **Send to all staff →** to a test list of one address; confirm the received email shows the pages as images and the links are clickable.

- [ ] **Step 4: Note the deploy prerequisite**

Before deploying: `pip install pymupdf` must run on the server (it's in `requirements.txt`; the deploy script should install it). Then deploy via `bash _deploy_zero_downtime.sh` and verify live `/` renders.

---

## Self-Review Notes

- **Spec coverage:** page-image rendering (Task 2), PyMuPDF engine + link extraction (Task 1), links block (Task 2), `format:"pdf"` data model (Tasks 1–3), upload editor + preview (Task 4), unchanged gate/store/send (untouched code), error handling for non-PDF/over-limit (Task 1 `_roundup_pdf_to_pages` guards + Task 4 notify), back-compat legacy renderer (Task 2 branch keeps the old body; Task 3 legacy test). All covered.
- **Type consistency:** `_roundup_pdf_to_pages` returns `(list[str], list[{"url","label"}])`; consumed identically in the renderer (`lk.get("url")`/`lk.get("label")`) and editor (`issue["pages"]`, `issue["links"]`). `_roundup_link_label` used in one place. Constants `_ROUNDUP_PDF_MAX_BYTES`/`_ROUNDUP_PDF_MAX_PAGES` defined in Task 1, reused in Task 4.
- **No placeholders:** every code step shows full code; every run step shows the command + expected result.

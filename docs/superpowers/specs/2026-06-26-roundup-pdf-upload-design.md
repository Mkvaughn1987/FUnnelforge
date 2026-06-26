# The Roundup — PDF-Upload Newsletter (design)

**Date:** 2026-06-26
**Branch:** `claude/critical-bug-fixes`
**Status:** Approved design, pending spec review
**Supersedes editor portion of:** `2026-06-23-the-roundup-marketing-newsletter-design.md`

## Goal

Let Rothany author The Roundup however she likes, export it as a **PDF**, upload
that PDF to DripDrop, and send it to all Arena Staff with **the layout and
pictures preserved exactly**. Replace the hand-filled, multi-section editor
(Marketing Minute / Playbook / New Items / Looking Ahead / President's message)
with a single "upload your PDF" flow.

## Approach (decided)

Convert the PDF to the email body by **rendering each PDF page to a high-res PNG
image and stacking the pages top-to-bottom as the email body.** This is the only
approach that reliably preserves a finished PDF's layout, fonts, and pictures
across Outlook and Gmail. PDF→reflowed-HTML was rejected: columns, spacing, and
image placement break unpredictably and would require per-issue cleanup.

### The link tradeoff (and how we handle it)

An image-based email has non-selectable text and non-clickable links. The
tempting fix — invisible clickable regions overlaid on the image — **does not
work in email** (Outlook strips `position:absolute`). Instead:

- At upload time we **extract every embedded hyperlink** from the PDF
  (PyMuPDF `page.get_links()` → URIs).
- If any exist, we append a small **"🔗 Links in this issue"** block of real
  `<a>` anchors below the stacked page images. Reliable in every client.
- If the PDF has no links, the block is omitted entirely.

We do **not** attempt to associate a link with its on-page anchor text beyond a
best-effort label (see "Link labels" below). This is a known, accepted
limitation for v1.

## Engine: PyMuPDF (`fitz`)

- Renders pages to PNG with **no system dependencies** (manylinux wheel bundles
  MuPDF) — important for the Linux server. `pip install pymupdf`; add to
  `requirements.txt` and install on the server before deploy.
- One library covers **both** needs: `page.get_pixmap(dpi=...)` for rasterizing
  and `page.get_links()` for hyperlink extraction.
- Render at **~144 DPI** (2× of 72) for crisp text without bloating image size.
  Each page PNG flows through the existing `_roundup_cache_image(raw, name)` →
  hosted `https://dripdripdrop.ai/email_img/roundup/<sha1>.png` URL. Content-
  addressed, so re-uploading an identical PDF reuses cached files.

## Data model change

A Roundup issue JSON gains PDF fields and stops using the section fields. New
shape (only the changed/added keys shown):

```json
{
  "id": "...", "issue_label": "June 2026",
  "subject": "The Roundup — June 2026",
  "format": "pdf",
  "pages": ["https://dripdripdrop.ai/email_img/roundup/<sha>.png", "..."],
  "links": [{"url": "https://...", "label": "https://..."}],
  "pdf_name": "June2026.pdf",
  "sent_at": null
}
```

- `format: "pdf"` distinguishes new issues from any pre-existing section-based
  issues. The renderer branches on it.
- Old section keys (`marketing_minute`, `president`, etc.) are simply no longer
  read for `format == "pdf"` issues. No migration of old issues is required —
  The Roundup has not yet been deployed/used in production (per project notes),
  so there is no live issue data to preserve. If any test/dev issue lacks
  `format`, the renderer treats it as the legacy section layout (back-compat
  branch kept).

## Components

### 1. `_roundup_pdf_to_pages(raw: bytes) -> (pages, links)` — new
Pure conversion helper. Input: PDF bytes. Output: `(list[str] page-image-URLs,
list[dict] links)`.
- Opens the PDF with `fitz.open(stream=raw, filetype="pdf")`.
- For each page: render to PNG at 144 DPI → `_roundup_cache_image(png_bytes,
  f"page{n}.png")` → append URL.
- Collect links: for each page, `page.get_links()`; keep entries with a `uri`;
  de-dupe by URL preserving order.
- Guardrails: cap pages (e.g. 30) and total PDF size (reuse a sane limit, e.g.
  20 MB) to avoid runaway rasterization. On a non-PDF / unreadable file, return
  `([], [])` and the caller shows an error.
- Unit-testable without a browser/server: in desktop/test mode
  `_roundup_cache_image` returns a `data:` URI, so the function returns
  non-empty page entries for a known-good small PDF fixture.

**Link labels:** PyMuPDF link objects don't carry anchor text. For v1 the
`label` is the URL itself (cleaned: strip scheme/`www.`, trim length). Good
enough for an internal newsletter; revisit only if Rothany asks.

### 2. `_render_roundup_html(issue)` — modify
Add a branch at the top: if `issue.get("format") == "pdf"`, render the
PDF layout; otherwise fall through to the existing section renderer (kept for
back-compat / any legacy dev issues).

PDF layout (email-safe, table/inline-style based like the rest of the email):
- Outer centered container (max-width ~700px, matching current Roundup width).
- Each page: `<img src=URL width="100%" style="display:block;max-width:700px;
  border:0;">` stacked with no gaps (or a hairline divider between pages).
- If `links`: a "🔗 Links in this issue" section bar (reuse
  `_roundup_section_bar`) followed by a simple list of `<a href>` items.
- Fixed Arena footer (reuse existing footer markup).

### 3. `_roundup_editor(s, rf, issue, can_edit)` — replace editable form
Keep the back button + read-only preview branch (Michael's view just renders
`_render_roundup_html`). Replace the section form (lines ~24208–24281) with:
- **Subject line** input (unchanged control, prefilled).
- **Upload PDF** widget (`ui.upload`, `accept="application/pdf"`,
  `max_file_size` ~20 MB, NiceGUI 3.x API: `await e.file.read()` — mirror
  `_roundup_image_field`'s handler). On upload:
  - Call `_roundup_pdf_to_pages(raw)`. Empty result → `ui.notify` error.
  - Store `issue["pages"]`, `issue["links"]`, `issue["pdf_name"]`,
    `issue["format"]="pdf"`; save issue; re-render so the preview updates.
- **Live preview** of the rendered email (`ui.html(_render_roundup_html(issue))`)
  showing the stacked pages + any links, so she sees exactly what staff get.
- **Save** and **Send to all staff →** buttons (unchanged behavior; `_collect`
  becomes trivial — just subject, since pages are already stored on upload).

No `ui.editor` widgets remain in this flow, so the
`_register_qeditor` C1-regression rule no longer applies to the editor — but
the read-only/legacy section branch still uses them, so keep the existing
registrations there.

### 4. `_roundup_new_issue` — minor
Set `"format": "pdf"` and initialize `"pages": []`, `"links": []` on new issues.
Drop seeding of the now-unused section defaults (leave them absent).

## Unchanged (explicitly)

- **Gate** (`_roundup_allowed`, `_ROUNDUP_ALLOWED_EMAILS`), tab placement, and
  who sees The Roundup.
- **Shared store** under the owner's folder; `_roundup_save_issue` /
  `_roundup_load_issue` / `_roundup_index` / `_roundup_mark_sent`.
- **Send flow** (`_roundup_send_dialog`): still reads `_render_roundup_html`,
  still sends per-recipient via `_send_email_universal` in the **owner's
  context** via `_run_as_user(_ROUNDUP_OWNER_EMAIL, ...)`. No change.
- Image hosting (`_roundup_cache_image` / `_email_img_src`).

## Error handling

- Non-PDF or corrupt upload → notify "That file isn't a readable PDF." and leave
  the existing pages intact.
- Zero pages rendered → same error.
- Over size/page cap → notify the specific limit; do not partially ingest.
- Conversion exceptions are caught in the upload handler (never crash the page);
  background send already prints `[Roundup]` failures to journald.

## Testing (`tests/test_the_roundup.py` — extend)

- `_roundup_pdf_to_pages` on a tiny generated/fixture PDF returns ≥1 page entry
  and the expected links (build a 1-page PDF with one annotated link in-test
  using PyMuPDF, so no binary fixture is committed).
- `_render_roundup_html` for a `format:"pdf"` issue includes each page URL as an
  `<img>` and renders the links block when links present / omits it when absent.
- Legacy section issue (no `format`) still renders via the old branch
  (back-compat guard).
- Existing gate / store / send tests remain green.

## Out of scope (v1)

- Selectable text or per-link anchor-text labels.
- Editing/reordering pages after upload (re-upload replaces).
- Mixing PDF pages with hand-authored sections in one issue.

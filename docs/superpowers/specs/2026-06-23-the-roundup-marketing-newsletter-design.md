# The Roundup — Internal Marketing Newsletter (design)

**Date:** 2026-06-23
**App:** DripDrop (`flowdrip_app.py`)
**Requested by:** Michael Vaughn, for Rothany Vu (marketing)

## Summary

Add **The Roundup**, a hand-authored internal company newsletter that goes to all
Arena Staffing employees. It is surfaced as a gated tab on the existing Newsletters
page, visible only to Rothany (owner/author) and Michael (viewer). Rothany fills in
a fixed set of labeled sections each issue; DripDrop renders the email in Arena's
brand styling and sends it to an all-staff contact list through the existing send
pipeline.

This is **separate** from the existing AI-generated, per-recipient, monthly
market-pulse newsletters. The Roundup is hand-written, identical for every
recipient, and sent on demand.

## Goals

- A labeled, section-based editor matching Rothany's existing layout, where she
  fills in the content for each issue.
- Image upload for the banner, per-item images, and the President's photo.
- Access restricted to Rothany + Michael; invisible to all other users.
- Send the finished issue to an all-staff list from within DripDrop.

## Non-goals

- No AI generation of Roundup content (it is hand-authored).
- No per-recipient personalization (every staff member gets the identical email).
- No automatic monthly scheduling in v1 (Rothany sends each issue on demand when
  it's ready). Scheduling can be a later phase.

## Access & ownership

"Rothany owns, you view." Rothany is the canonical author; Michael has visibility
and can also send.

```python
_ROUNDUP_OWNER_EMAIL = "rothany.vu@arenastaffing.net"   # confirmed 2026-06-23
_ROUNDUP_ALLOWED_EMAILS = {
    _ROUNDUP_OWNER_EMAIL,
    "michael.vaughn@arenastaffing.net",
    "mkvaughn1987@gmail.com",
}
```

- The gate is a new constant, modeled on `_ATS_ALLOWED_EMAILS` (flowdrip_app.py:57).
- **Non-allowed users:** the Newsletters page (`p_newsletters`) looks exactly as it
  does today — no tab, no trace of The Roundup.
- **Allowed users:** a tab toggle appears at the top of the Newsletters page —
  `Market Newsletters` | `The Roundup`. The existing newsletter content renders
  under the first tab unchanged.
- **Storage location:** all Roundup data always resolves to
  `_resolve_user_root(_ROUNDUP_OWNER_EMAIL) / "Roundup"` regardless of who is
  viewing. Rothany's folder is the single source of truth. `_resolve_user_root`
  (flowdrip_app.py:1225) accepts an explicit email and is pure path computation,
  so a cross-user *read* is safe and deliberate here — this is the one sanctioned
  exception to per-user isolation, and it is read-only for Michael's session.
- **Permissions:** Rothany — full edit + send. Michael — view rendered issues and
  may send; he does not normally edit (read-mostly). Both see the same Send button.

### Multi-user-safety note

Per `project_signature_leak_incident` and `project_bg_thread_user_context`: the
shared store is reached **only** via the explicit `_ROUNDUP_OWNER_EMAIL` arg to
`_resolve_user_root`, never via a module global and never via ambient context.
Any background work (e.g. send) that touches Roundup files must pass that explicit
email (use `_run_as_user(_ROUNDUP_OWNER_EMAIL, ...)` for threads), not rely on the
acting user's ContextVar.

## Data model

Per-issue JSON under `…/Roundup/issues/`, named by issue id (e.g. `2026-06.json`).
One issue == one Roundup email.

```jsonc
{
  "id": "2026-06",
  "title": "The Roundup",            // banner wordmark text (fixed default)
  "issue_label": "June 2026",        // used in "New Items for [Month]" + subject
  "subject": "The Roundup — June 2026",  // email subject; default derived from issue_label
  "status": "draft",                 // "draft" | "sent"
  "hero_image": "roundup/he_ab12.png",   // banner; stored via newsletter image cache
  "marketing_minute": "<rich html>",     // intro section body
  "playbook_callout": "<rich html>",     // the tan highlighted callout box
  "new_items": [
    { "lead": "New Anniversary Logos", "body": "<html>", "image": null }
  ],
  "looking_ahead": [
    { "lead": "New Website", "body": "<html>", "image": null }
  ],
  "president": {
    "photo": "roundup/pr_cd34.png",
    "body": "<html>",
    "name": "Dave Kooiman",
    "title": "President & CEO"
  },
  "updated_at": "2026-06-23T...",
  "sent_at": null
}
```

- Footer is **fixed** (Arena address block), not stored per issue.
- `new_items` and `looking_ahead` are flexible, repeatable lists — Rothany
  adds/removes/reorders items each issue. Nothing in them is hardcoded (the April
  "Notecards" and "New Anniversary Logos" items were that month's content only).
- An `index.json` in `…/Roundup/` lists issues (id, issue_label, status, updated_at)
  for the card view.
- **Images** reuse the existing newsletter image cache (the `/nl-img/…`-style serving
  path, flowdrip_app.py:369–399) and the NiceGUI 3.x upload API
  (`on_upload` → `await e.file.read()`, per `reference_nicegui_upload_api`). This
  gives Outlook real `<img src>` URLs instead of base64 bloat.

## Editor UI

A section-based form rendered on the Roundup tab (NOT the AI `_create_newsletter_dialog`):

1. **Issue header** — issue label + subject line (subject defaults to
   `The Roundup — {issue_label}`, editable).
2. **Banner** — image upload (with the current banner shown).
3. **Marketing Minute** — rich-text intro.
4. **The Playbook callout** — rich-text (rendered as the tan box).
5. **New Items** — repeatable rows: bold lead-in + rich-text body + optional image;
   add / remove / reorder.
6. **Looking Ahead** — repeatable rows, same shape as New Items.
7. **A Message From the President** — photo upload + rich-text body + name + title.
8. **Live preview pane** — renders the real email HTML (`_render_roundup_html`).

Rich-text fields reuse the patched `editor.js` component (per
`reference_editor_js_patch` — do not upgrade NiceGUI without re-patching). Image
fields reuse the newsletter upload + cache path.

Save persists the issue JSON and updates `index.json`.

## Rendering

`_render_roundup_html(issue) -> str` builds the email body in Arena's brand styling,
matching the April layout:

- Hero banner image (full width).
- Blue centered section bars (`Marketing Minute`, `A Message From the President`).
- Tan/beige callout box for The Playbook.
- Centered "New Items for {issue_label}" and "Looking Ahead" headings, each followed
  by their items (bold lead-in, body, optional right-aligned image).
- Centered President block (photo, body, signature name/title).
- Fixed footer: `Arena Staffing | 4750 Ontario Mills Pkwy | Ontario, CA 91764 US`.

Inline CSS, table-based layout for Outlook safety — same conventions as the existing
newsletter HTML serializer.

## Sending

- A **Send to all staff** button on each draft issue.
- Opens a confirmation that reuses `list_saved_contact_lists()` (flowdrip_app.py:5877)
  to pick the recipient list (Rothany maintains an "All Arena Staff" saved CSV), shows
  the recipient count, and confirms.
- On confirm, build a minimal campaign dict carrying the rendered HTML and route it
  through `queue_campaign_emails()` (flowdrip_app.py:7651) — the same queue/scheduler
  the rest of the app uses. The Roundup is a one-shot send (single step, identical
  body for all recipients), so it does not need the per-contact body inlining used by
  multi-step campaigns.
- On success: issue `status` → `"sent"`, `sent_at` stamped; the card shows a "Sent"
  badge.
- Michael's session sees the same Send button (he may send).

## Components & boundaries

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `_roundup_allowed(email)` / gate constants | Decide visibility | session email |
| `_roundup_dir()` / issue load/save/index | Persist issues to Rothany's folder | `_resolve_user_root(OWNER)` |
| Roundup tab + editor (`p_newsletters` integration) | Render tab toggle + section form | editor.js, image upload/cache |
| `_render_roundup_html(issue)` | Issue dict → email HTML | (pure) |
| Roundup send | Queue the issue to a staff list | `list_saved_contact_lists`, `queue_campaign_emails`, `_run_as_user` |

## Testing

- `_render_roundup_html` is a pure function — unit-test it with a fixture issue:
  asserts hero/sections/items/footer present, handles empty optional images, escapes
  user HTML safely via the existing sanitizer.
- Gate: `_roundup_allowed` returns True only for the three emails; False otherwise.
- Issue store: save → load round-trips; index.json updates; cross-user read resolves
  to the owner's folder when Michael's email is the acting session.
- Existing newsletter tests must continue to pass (no change to AI-newsletter flow).

## Open questions / deferred

- Auto monthly scheduling — deferred to a later phase; v1 is send-on-demand.
- Whether Michael should be able to edit (currently read-mostly / view + send).

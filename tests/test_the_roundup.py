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


def test_parse_recipients_dedupes_and_validates():
    raw = "a@x.com, b@y.com\nA@X.COM\nnot-an-email\nc@z.io"
    out = fa._roundup_parse_recipients(raw)
    assert out == ["a@x.com", "b@y.com", "c@z.io"]  # dedupe case-insensitive, drop junk


def test_parse_recipients_empty():
    assert fa._roundup_parse_recipients("") == []
    assert fa._roundup_parse_recipients(None) == []


def test_roundup_link_label_strips_scheme_and_www():
    assert fa._roundup_link_label("https://www.arena.example/apply") == "arena.example/apply"
    assert fa._roundup_link_label("http://x.io/") == "x.io"
    assert fa._roundup_link_label("") == ""
    assert len(fa._roundup_link_label("https://" + "a" * 65)) == 61  # 60 chars + ellipsis


def _one_page_pdf_with_link():
    """Build a 1-page PDF (in memory) containing one URI link annotation."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((20, 50), "Hello team")
    page.insert_link({"kind": fitz.LINK_URI,
                      "from": fitz.Rect(20, 60, 160, 80),
                      "uri": "https://arena.example/apply"})
    try:
        return doc.tobytes()
    finally:
        doc.close()


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

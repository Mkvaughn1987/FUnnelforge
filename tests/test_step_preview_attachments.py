"""_step_preview_attachments decides which files the campaign-page email
preview shows: queue items win, step 1 never carries files, and
'_pending:' placeholders are not files."""


def test_queue_attachments_win_over_step_definition(monkeypatch, tmp_path):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_user_pdf_dir", lambda: tmp_path)
    (tmp_path / "Cost.pdf").write_bytes(b"x" * 2048)
    step = {"attachments": ["Other.pdf"]}
    out = fa._step_preview_attachments(step, 3, [str(tmp_path / "Cost.pdf")])
    assert out == [{"name": "Cost.pdf", "exists": True, "size": 2048}]


def test_queued_without_files_shows_none(monkeypatch, tmp_path):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_user_pdf_dir", lambda: tmp_path)
    assert fa._step_preview_attachments({"attachments": ["A.pdf"]}, 2, []) == []


def test_fallback_skips_step_one_and_pending(monkeypatch, tmp_path):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_user_pdf_dir", lambda: tmp_path)
    step = {"attachments": ["A.pdf", "_pending:ROI", "A.pdf"]}
    assert fa._step_preview_attachments(step, 0, None) == []
    out = fa._step_preview_attachments(step, 1, None)
    assert out == [{"name": "A.pdf", "exists": False, "size": 0}]


def test_fmt_file_size():
    import flowdrip_app as fa
    assert fa._fmt_file_size(0) == ""
    assert fa._fmt_file_size(500) == "500 B"
    assert fa._fmt_file_size(240 * 1024) == "240 KB"
    assert fa._fmt_file_size(3 * 1024 * 1024) == "3.0 MB"

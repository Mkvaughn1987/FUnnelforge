"""H3 regression: _load_signature_text silently returned "" on read
failure, so a corrupted or unreadable signature file would just send
emails with no signature and no warning. Now read failures are logged."""
import pathlib


def test_load_signature_logs_read_failure(isolated_appdata, with_user, capsys, monkeypatch):
    import flowdrip_app as fa

    sig_path = fa._user_sig_path()
    sig_path.parent.mkdir(parents=True, exist_ok=True)
    sig_path.write_text("Michael Vaughn\nDripDrop", encoding="utf-8")

    # Force the read to blow up to simulate a permission/locking error.
    real_read_text = pathlib.Path.read_text
    def boom(self, *a, **kw):
        if str(self) == str(sig_path):
            raise OSError("simulated read error")
        return real_read_text(self, *a, **kw)
    monkeypatch.setattr(pathlib.Path, "read_text", boom)

    result = fa._load_signature_text()

    assert result == "", "Should still degrade to empty signature"
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "signature" in combined or "simulated read error" in combined, (
        f"Expected a log on signature read failure; got out={captured.out!r}, err={captured.err!r}"
    )


def test_load_signature_no_log_when_file_missing(isolated_appdata, with_user, capsys):
    """File-not-exist is normal for new users; don't spam the log."""
    import flowdrip_app as fa

    sig_path = fa._user_sig_path()
    if sig_path.exists():
        sig_path.unlink()

    result = fa._load_signature_text()

    assert result == ""
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "signature" not in combined, (
        f"Missing signature should not produce a warning; got {combined!r}"
    )

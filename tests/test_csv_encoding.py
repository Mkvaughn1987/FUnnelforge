"""H12 regression: safe_read_csv_rows() opened CSVs with utf-8-sig
only. Non-UTF8 files (Latin-1, Windows-1252, GB2312...) crashed with
an uninformative UnicodeDecodeError.  Fall back to a permissive
encoding so the user gets their data instead of a crash."""
import pathlib


def test_safe_read_csv_rows_handles_latin1(isolated_appdata, with_user, tmp_path):
    import flowdrip_app as fa
    p = tmp_path / "latin1.csv"
    # Build a Latin-1 CSV with high-bit characters that aren't valid UTF-8.
    # Bytes 0xE9 0xE0 are 'éà' in Latin-1 but invalid as a standalone UTF-8
    # sequence.
    p.write_bytes(b"Email,FirstName\nalice@example.com,Andr\xe9\nbob@example.com,B\xe9b\xe9\n")

    rows, headers = fa.safe_read_csv_rows(str(p))

    assert len(rows) == 2, f"Both rows should be readable; got {rows!r}"
    assert "Email" in headers
    assert "FirstName" in headers
    # Names came through (exact value is encoding-dependent, but should be
    # non-empty and contain something representing the original characters).
    assert rows[0]["FirstName"]
    assert rows[1]["FirstName"]


def test_safe_read_csv_rows_still_handles_utf8(isolated_appdata, with_user, tmp_path):
    """The fallback must not break the happy UTF-8 path."""
    import flowdrip_app as fa
    p = tmp_path / "utf8.csv"
    p.write_text("Email,FirstName\nalice@example.com,André\n", encoding="utf-8")

    rows, headers = fa.safe_read_csv_rows(str(p))

    assert len(rows) == 1
    assert rows[0]["FirstName"] == "André"


def test_safe_read_csv_rows_strips_utf8_bom(isolated_appdata, with_user, tmp_path):
    """utf-8-sig handling must still strip a leading BOM from headers."""
    import flowdrip_app as fa
    p = tmp_path / "bom.csv"
    p.write_bytes(b"\xef\xbb\xbfEmail,FirstName\nalice@example.com,Alice\n")

    rows, headers = fa.safe_read_csv_rows(str(p))

    assert headers[0] == "Email", f"BOM should be stripped from first header; got {headers!r}"
    assert rows[0]["Email"] == "alice@example.com"

"""H13 regression: normalize_csv silently dropped rows with invalid
email values. The user couldn't tell that some of their contacts had
been excluded. Now the function returns a warning summarizing the
skip count and a few examples."""
import pathlib


def _write_csv(p: pathlib.Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_normalize_csv_warns_on_invalid_emails(isolated_appdata, with_user, tmp_path):
    import flowdrip_app as fa
    src = tmp_path / "src.csv"
    dest = tmp_path / "out.csv"
    _write_csv(src,
        "Email,FirstName\n"
        "alice@example.com,Alice\n"
        "not-an-email,Bob\n"
        "still..bad@,Carol\n"
        "dave@example.com,Dave\n"
    )

    written, warnings = fa.normalize_csv(str(src), str(dest))

    assert written == 2, "Two valid rows should be written"
    # Some warning text should mention the skipped rows.
    joined = " ".join(warnings).lower()
    assert "skipped" in joined or "invalid" in joined or "dropped" in joined, (
        f"Expected a warning about skipped/invalid rows; got {warnings!r}"
    )
    # The number of skipped rows should be discoverable from the warnings.
    assert "2" in joined, (
        f"Expected the count of skipped rows (2) in the warning; got {warnings!r}"
    )


def test_normalize_csv_no_warning_when_all_valid(isolated_appdata, with_user, tmp_path):
    import flowdrip_app as fa
    src = tmp_path / "src.csv"
    dest = tmp_path / "out.csv"
    _write_csv(src,
        "Email,FirstName\n"
        "alice@example.com,Alice\n"
        "bob@example.com,Bob\n"
    )

    written, warnings = fa.normalize_csv(str(src), str(dest))

    assert written == 2
    # No "skipped" / "invalid" warning when every row was good.
    joined = " ".join(warnings).lower()
    assert "skipped" not in joined
    assert "invalid email" not in joined

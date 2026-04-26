"""H10 regression: load_campaigns silently swallowed JSON parse errors,
so a corrupted campaign file would just disappear from the list with no
indication. Now the parse failure is logged so the user (or support)
can find the bad file and recover it."""
import json
import pathlib


def test_load_campaigns_logs_parse_error(isolated_appdata, with_user, capsys):
    """A corrupted campaign JSON file should be reported on stdout/stderr,
    not silently dropped from the list."""
    import flowdrip_app as fa

    campaigns_dir = fa._user_campaigns_dir()
    campaigns_dir.mkdir(parents=True, exist_ok=True)

    # One good campaign, one corrupted file with the same .json extension.
    (campaigns_dir / "good.json").write_text(
        json.dumps({"name": "Good", "emails": []}), encoding="utf-8"
    )
    (campaigns_dir / "broken.json").write_text(
        "{not valid json {{{", encoding="utf-8"
    )

    # Bust any cached value so we exercise the disk read path.
    fa._cache_campaigns.invalidate()

    camps = fa.load_campaigns()

    # Good campaign survives.
    names = [c.get("name") for c in camps]
    assert "Good" in names

    # And the broken one was logged.
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "broken.json" in combined or "broken" in combined, (
        f"Expected a log mentioning broken.json; got out={captured.out!r}, err={captured.err!r}"
    )

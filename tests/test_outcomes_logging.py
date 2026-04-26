"""H9 regression: load_outcomes and save_outcomes silently swallow
errors. A corrupted task_outcomes.json file just disappears (returns
{}) and a save failure is invisible. Add logging on both paths so the
problem is at least diagnosable."""


def test_load_outcomes_logs_corruption(isolated_appdata, with_user, capsys):
    import flowdrip_app as fa

    target = fa._user_outcomes_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not valid json", encoding="utf-8")

    result = fa.load_outcomes()

    assert result == {}, "Corrupt file should still degrade to empty dict"
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "outcome" in combined or str(target.name).lower() in combined, (
        f"Expected a log mentioning outcomes/file; got out={captured.out!r}, err={captured.err!r}"
    )


def test_save_outcomes_logs_failure(isolated_appdata, with_user, capsys, monkeypatch):
    import flowdrip_app as fa

    def boom(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(fa.os, "replace", boom)

    fa.save_outcomes({"some": "data"})

    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "outcome" in combined or "disk full" in combined or "save" in combined, (
        f"Expected a log on save failure; got out={captured.out!r}, err={captured.err!r}"
    )

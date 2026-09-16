"""ui.run(favicon=...) must stay a file path on Arena (var unset) and
become an inline data URL on a rebranded instance, so a changed icon is
not hidden behind the browser's per-URL /favicon.ico cache."""
import base64
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _fa(monkeypatch, isolated_appdata):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_APP_DIR", isolated_appdata)
    (isolated_appdata / "assets").mkdir(exist_ok=True)
    (isolated_appdata / "assets" / "icon.png").write_bytes(PNG)
    monkeypatch.setattr(fa, "BRAND_FAVICON", "assets/icon.png")
    return fa


def test_unset_var_keeps_file_path(isolated_appdata, monkeypatch):
    monkeypatch.delenv("DRIPDROP_BRAND_FAVICON", raising=False)
    fa = _fa(monkeypatch, isolated_appdata)
    assert fa._favicon_for_ui_run() == str(isolated_appdata / "assets/icon.png")


def test_set_var_inlines_data_url(isolated_appdata, monkeypatch):
    monkeypatch.setenv("DRIPDROP_BRAND_FAVICON", "assets/icon.png")
    fa = _fa(monkeypatch, isolated_appdata)
    out = fa._favicon_for_ui_run()
    assert out.startswith("data:image/png;base64,")
    assert base64.b64decode(out.split(",", 1)[1]) == PNG


def test_set_var_missing_file_falls_back_to_path(isolated_appdata, monkeypatch):
    monkeypatch.setenv("DRIPDROP_BRAND_FAVICON", "assets/nope.png")
    fa = _fa(monkeypatch, isolated_appdata)
    monkeypatch.setattr(fa, "BRAND_FAVICON", "assets/nope.png")
    assert fa._favicon_for_ui_run() == str(isolated_appdata / "assets/nope.png")

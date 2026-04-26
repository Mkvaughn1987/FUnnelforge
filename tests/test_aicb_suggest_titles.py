"""_aicb_suggest_role_titles takes company + website + brief, web-searches
the company's career page, returns 5-8 specific titles. Appends to
s.aicb_sel_roles dedup-aware."""
from unittest.mock import MagicMock


def _fake_titles_response(titles: list) -> MagicMock:
    body = "TITLES:\n" + "\n".join(f"- {t}" for t in titles)
    msg = MagicMock()
    block = MagicMock()
    block.text = body
    msg.content = [block]
    return msg


def test_suggest_titles_appends(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_website = "https://acme.com"
    s.aicb_industry = "Manufacturing"
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_titles_response(
            ["CNC Machinist", "Mill Operator", "Production Supervisor"]),
    )
    fa._aicb_suggest_titles_run(s)
    assert "CNC Machinist" in s.aicb_sel_roles
    assert "Mill Operator" in s.aicb_sel_roles
    assert "Production Supervisor" in s.aicb_sel_roles


def test_suggest_titles_dedups(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_website = "https://acme.com"
    s.aicb_sel_roles = ["CNC Machinist"]
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_titles_response(
            ["CNC Machinist", "Mill Operator"]),
    )
    fa._aicb_suggest_titles_run(s)
    assert s.aicb_sel_roles.count("CNC Machinist") == 1
    assert "Mill Operator" in s.aicb_sel_roles

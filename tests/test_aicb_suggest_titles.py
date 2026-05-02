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


def test_suggest_titles_caps_at_six_total(isolated_appdata, with_user, monkeypatch):
    """Regression 2026-05-01: suggest used to append unbounded. With the
    new title-chip picker capped at 6, pre-existing 3 + Suggest returning
    8 would silently overshoot to 11 — breaking the
    one-candidate-per-title contract (A-F = 6 letters max). The helper
    must hard-cap at 6 total regardless of how many titles the AI
    returns or how many were already on the list."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_website = "https://acme.com"
    s.aicb_sel_roles = ["Existing 1", "Existing 2", "Existing 3"]
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_titles_response(
            # AI returns 8 NEW titles → without the cap we'd land on 11.
            ["New 1", "New 2", "New 3", "New 4", "New 5",
             "New 6", "New 7", "New 8"]),
    )
    fa._aicb_suggest_titles_run(s)
    assert len(s.aicb_sel_roles) <= 6, (
        f"Suggest titles must hard-cap aicb_sel_roles at 6 total; "
        f"got {len(s.aicb_sel_roles)}: {s.aicb_sel_roles}"
    )
    # Existing entries are preserved and earlier suggestions take the
    # remaining slots in order.
    assert s.aicb_sel_roles[:3] == ["Existing 1", "Existing 2", "Existing 3"]
    assert s.aicb_sel_roles[3:] == ["New 1", "New 2", "New 3"]


def test_suggest_titles_noop_when_already_at_six(isolated_appdata, with_user, monkeypatch):
    """When already at the 6-title cap, Suggest must add nothing — even
    if the AI returns fresh titles. Belt + suspenders: the wizard
    button is also disabled in this state, but a stale frame or a
    test/script call could still hit the helper."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_website = "https://acme.com"
    s.aicb_sel_roles = ["A", "B", "C", "D", "E", "F"]
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_titles_response(["X", "Y", "Z"]),
    )
    fa._aicb_suggest_titles_run(s)
    assert s.aicb_sel_roles == ["A", "B", "C", "D", "E", "F"]

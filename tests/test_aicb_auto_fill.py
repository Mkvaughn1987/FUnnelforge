"""_aicb_auto_fill_target_details takes company + website, web-searches,
and pre-fills the AICB Step-2 picker fields:
  - aicb_industry (legacy)
  - aicb_primary_industry (new picker primary)
  - aicb_secondary_industries (new picker secondary, list)
  - aicb_sel_locations (multi-pick locations, list)
Mocks the AI call to verify state-update logic without API cost.

Restored 2026-05-02 along with the helper itself; secondary-industry
population is new (the old version only set primary)."""
from unittest.mock import MagicMock


def _fake_industries_locations_response(industries: list, locations: list) -> MagicMock:
    body = (
        "INDUSTRIES:\n"
        + "\n".join(f"- {i}" for i in industries)
        + "\n\nLOCATIONS:\n"
        + "\n".join(f"- {l}" for l in locations)
    )
    msg = MagicMock()
    block = MagicMock()
    block.text = body
    msg.content = [block]
    return msg


def test_auto_fill_populates_industry_and_locations(isolated_appdata, with_user, monkeypatch):
    """First industry → primary, locations append into the multi-list."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Kaufman & Robinson"
    s.aicb_website = "https://kaufman-robinson.com"
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_industries_locations_response(
            industries=["Precision Manufacturing", "Aerospace"],
            locations=["Fort Collins, CO", "Denver, CO"],
        ),
    )
    fa._aicb_auto_fill_run(s)
    assert s.aicb_industry == "Precision Manufacturing"
    assert s.aicb_primary_industry == "Precision Manufacturing"
    assert "Fort Collins, CO" in s.aicb_sel_locations
    assert "Denver, CO" in s.aicb_sel_locations


def test_auto_fill_populates_secondary_industries(isolated_appdata, with_user, monkeypatch):
    """User asked 2026-05-02 for AI to come up with primary + AT
    LEAST one secondary. Verify the helper writes everything past the
    first industry into aicb_secondary_industries (capped at 4)."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme Aerospace"
    s.aicb_website = "https://acme-aerospace.com"
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_industries_locations_response(
            industries=["Aerospace", "Defense", "Manufacturing"],
            locations=["Wichita, KS"],
        ),
    )
    fa._aicb_auto_fill_run(s)
    assert s.aicb_primary_industry == "Aerospace"
    assert s.aicb_secondary_industries == ["Defense", "Manufacturing"]


def test_auto_fill_caps_secondary_industries_at_four(isolated_appdata, with_user, monkeypatch):
    """Picker UI caps at 4 secondaries; helper must respect that even
    if the AI returns more."""
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_website = "https://acme.com"
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_industries_locations_response(
            industries=["Primary"] + [f"Sec{i}" for i in range(8)],
            locations=["City, ST"],
        ),
    )
    fa._aicb_auto_fill_run(s)
    assert s.aicb_primary_industry == "Primary"
    assert len(s.aicb_secondary_industries) <= 4


def test_auto_fill_dedups_existing_locations(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_website = "https://acme.com"
    s.aicb_sel_locations = ["Denver, CO"]
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_industries_locations_response(
            industries=["Manufacturing"],
            locations=["Denver, CO", "Boulder, CO"],
        ),
    )
    fa._aicb_auto_fill_run(s)
    assert s.aicb_sel_locations.count("Denver, CO") == 1
    assert "Boulder, CO" in s.aicb_sel_locations


def test_auto_fill_caps_locations_at_5(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    s = fa.AppState()
    s.aicb_company = "Acme"
    s.aicb_website = "https://acme.com"
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        fa, "_claude_create_with_retry",
        lambda *a, **kw: _fake_industries_locations_response(
            industries=["Mfg"],
            locations=[f"City{i}, ST" for i in range(10)],
        ),
    )
    fa._aicb_auto_fill_run(s)
    assert len(s.aicb_sel_locations) <= 5

"""Campaign create+launch API — Phase 1.

Spec: docs/superpowers/specs/2026-06-27-campaign-create-launch-api-design.md
Plan: docs/superpowers/plans/2026-06-27-campaign-create-launch-api.md
"""
import flowdrip_app as fa


def _isolate_keys(tmp_path, monkeypatch):
    """Point the API-key store at a temp file so tests never touch real data."""
    store = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: store)
    return store


# ── API key mint / resolve ─────────────────────────────────────────
def test_mint_then_resolve_returns_email(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com", label="cowork")
    assert key.startswith("dd_live_")
    assert fa._resolve_api_key(key) == "rep@arena.com"


def test_resolve_unknown_key_is_none(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    fa._mint_api_key("rep@arena.com")
    assert fa._resolve_api_key("dd_live_bogus") is None
    assert fa._resolve_api_key("") is None
    assert fa._resolve_api_key(None) is None


def test_plaintext_key_never_stored(tmp_path, monkeypatch):
    store = _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    raw = store.read_text(encoding="utf-8")
    assert key not in raw            # only the hash is persisted
    assert fa._hash_api_key(key) in raw


# ── contacts CSV parsing ───────────────────────────────────────────
def test_parse_contacts_csv_maps_aliased_columns():
    csv_text = "Email,FirstName,LastName,Company,JobTitle\n" \
               "vp@acme.com,Dana,Lee,Acme,VP Ops\n"
    rows = fa._parse_contacts_csv(csv_text)
    assert rows == [{"email": "vp@acme.com", "first_name": "Dana",
                     "last_name": "Lee", "company": "Acme", "title": "VP Ops"}]


def test_parse_contacts_csv_blank_is_empty():
    assert fa._parse_contacts_csv("") == []


# ── spec validation ────────────────────────────────────────────────
def test_validate_spec_rejects_unknown_template():
    err = fa._validate_campaign_spec({"template": "nope", "company": "Acme",
                                      "start_date": "2026-07-06"})
    assert err and "template" in err.lower()


def test_validate_spec_requires_company_or_niche():
    err = fa._validate_campaign_spec({"template": "fourbyfour",
                                      "start_date": "2026-07-06"})
    assert err and ("company" in err.lower() or "niche" in err.lower())


def test_validate_spec_rejects_bad_date():
    err = fa._validate_campaign_spec({"template": "fourbyfour", "company": "Acme",
                                      "start_date": "07/06/2026"})
    assert err and "date" in err.lower()


def test_validate_spec_ok_returns_none():
    assert fa._validate_campaign_spec({"template": "fourbyfour", "company": "Acme",
                                       "start_date": "2026-07-06"}) is None


# ── schedule computation ───────────────────────────────────────────
def test_schedule_from_steps_4x4_business_days():
    steps = [
        {"step_type": "email_auto", "delay_days": 0},
        {"step_type": "email_auto", "delay_days": 3},
        {"step_type": "call",       "delay_days": 0},
        {"step_type": "email_auto", "delay_days": 4},
        {"step_type": "email_auto", "delay_days": 4},
    ]
    sched = fa._schedule_from_steps(steps, "2026-07-06")  # Monday
    dates = [r["date"] for r in sched]
    assert dates == ["2026-07-06", "2026-07-09", "2026-07-09",
                     "2026-07-15", "2026-07-21"]
    assert sched[2]["type"] == "call" and sched[2]["step"] == 3

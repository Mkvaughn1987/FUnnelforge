"""Campaign create+launch API — Phase 1.

Spec: docs/superpowers/specs/2026-06-27-campaign-create-launch-api-design.md
Plan: docs/superpowers/plans/2026-06-27-campaign-create-launch-api.md
"""
from datetime import date

import pytest
import flowdrip_app as fa


@pytest.fixture(autouse=True)
def _restore_user_ctx():
    """The route binds global user context (_CURRENT_USER_EMAIL /
    _switch_to_user_paths). Snapshot + restore it so these tests never leak
    that state into the rest of the suite."""
    try:
        before = fa._CURRENT_USER_EMAIL.get()
    except Exception:
        before = None
    yield
    try:
        fa._CURRENT_USER_EMAIL.set(before)
    except Exception:
        pass


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


def test_key_and_hash_both_persisted(tmp_path, monkeypatch):
    # By design (reveal & copy feature) the plaintext key is now persisted
    # alongside its hash so it can be shown again later. Auth still resolves
    # by hash only — see _resolve_api_key.
    store = _isolate_keys(tmp_path, monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    raw = store.read_text(encoding="utf-8")
    assert key in raw                     # plaintext persisted (for reveal/copy)
    assert fa._hash_api_key(key) in raw   # hash persisted (used for auth)


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


# ── upcoming-Monday start-date default ─────────────────────────────
# The API takes start_date verbatim; when the caller wants "the upcoming
# Monday" it must resolve to THIS Monday if today is already Monday
# (the campaign then sends today at the current time), NOT a week ahead.
def test_upcoming_monday_on_monday_is_today():
    # 2026-07-13 is a Monday — must return itself, not 2026-07-20.
    assert fa._upcoming_monday(date(2026, 7, 13)) == date(2026, 7, 13)


def test_upcoming_monday_midweek_jumps_to_next_monday():
    # 2026-07-15 is a Wednesday.
    assert fa._upcoming_monday(date(2026, 7, 15)) == date(2026, 7, 20)


def test_upcoming_monday_sunday_is_next_day():
    # 2026-07-19 is a Sunday.
    assert fa._upcoming_monday(date(2026, 7, 19)) == date(2026, 7, 20)


def test_resolve_start_date_explicit_passthrough():
    assert fa._resolve_start_date("2026-08-01") == "2026-08-01"


def test_resolve_start_date_blank_uses_upcoming_monday():
    resolved = fa._resolve_start_date("")
    assert resolved == fa._upcoming_monday().isoformat()
    assert date.fromisoformat(resolved).weekday() == 0  # a Monday


def test_resolve_start_date_sentinel_uses_upcoming_monday():
    assert fa._resolve_start_date("upcoming_monday") == fa._upcoming_monday().isoformat()


def test_validate_spec_ok_without_start_date():
    # Omitting start_date is now valid — the server defaults to upcoming Monday.
    assert fa._validate_campaign_spec({"template": "fourbyfour",
                                       "company": "Acme"}) is None


# ── generation function (extracted core) ───────────────────────────
class _FakeMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]


class _FakeClient:
    """Returns a market brief on the 1st call, campaign JSON on the 2nd."""
    def __init__(self):
        self.messages = self
        self._n = 0

    def create(self, **kw):
        self._n += 1
        if self._n == 1:
            return _FakeMsg("Brief: Acme hires Plant Managers in Windsor, CO.")
        import json as _j
        camp = {
            "synopsis": "S",
            "campaign_name": "Acme - Plant Manager Campaign",
            "emails": [
                {"name": "Step 1", "subject": "Plant Manager Candidates Available",
                 "body": "Intro — with an em dash", "delay_days": 0, "time": "9:00 AM",
                 "step_type": "email_auto"},
                {"name": "Step 2", "subject": "Top Talent Insights",
                 "body": "Insights", "delay_days": 3, "time": "9:00 AM",
                 "step_type": "email_auto"},
            ],
        }
        return _FakeMsg(_j.dumps(camp))


def test_generate_aicb_campaign_returns_normalized_emails(monkeypatch):
    # Avoid the live web-search cited-stats call.
    monkeypatch.setattr(fa, "_fetch_cited_market_stats", lambda *a, **k: [])
    monkeypatch.setattr(fa, "_format_cited_stats_block", lambda *a, **k: "")
    monkeypatch.setattr(fa.time, "sleep", lambda *a, **k: None)
    out = fa.generate_aicb_campaign(
        _FakeClient(),
        camp_type="fourbyfour",
        company="Acme Manufacturing",
        website="acme.com",
        niche="food processing",
        industry="manufacturing",
        roles=["Plant Manager"],
        location="Windsor, CO",
        candidate_cards=[{"label": "Candidate A", "role": "Plant Manager",
                          "bullets": ["12 yrs", "PMP"]}],
    )
    assert out["campaign_name"]
    assert len(out["emails"]) == 2
    # Post-processing ran: dash stripped, FirstName greeting present, 4x4 wrap.
    b0 = out["emails"][0]["body"]
    assert "—" not in b0           # em dash stripped by the humanizer
    assert "Hi {FirstName}" in b0
    assert "font-size:11pt" in b0   # _wrap_4x4_font applied for fourbyfour


# ── the POST /api/v1/campaigns route ───────────────────────────────
# Call the async handler directly with a fake Request — avoids booting the
# whole NiceGUI app via TestClient (which is slow and pollutes the suite).
import asyncio
import json as _json


class _FakeReq:
    def __init__(self, headers, body):
        self.headers = headers
        self._body = body

    async def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _call(headers, body):
    """Invoke the route handler; return (status_code, parsed_json_body)."""
    resp = asyncio.run(fa.api_create_campaign(_FakeReq(headers, body)))
    return resp.status_code, _json.loads(resp.body)


def _stub_pipeline(monkeypatch, queued=1, raise_queue=None):
    # Keep the route from mutating global per-user path state during tests.
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "generate_aicb_campaign", lambda *a, **k: {
        "synopsis": "S", "campaign_name": "Acme - Plant Manager Campaign",
        "emails": [
            {"subject": "Plant Manager Candidates Available", "body": "Hi {FirstName},",
             "delay_days": 0, "time": "9:00 AM", "step_type": "email_auto"},
            {"subject": "Top Talent Insights", "body": "Hi {FirstName},",
             "delay_days": 3, "time": "9:00 AM", "step_type": "email_auto"},
            {"subject": "", "body": "Call script", "delay_days": 0, "time": "10:00 AM",
             "step_type": "call"},
            {"subject": "Thoughts on this?", "body": "Hi {FirstName},",
             "delay_days": 4, "time": "9:00 AM", "step_type": "email_auto"},
            {"subject": "Market Trends", "body": "Hi {FirstName},",
             "delay_days": 4, "time": "9:00 AM", "step_type": "email_auto"},
        ],
    })
    captured = {}

    def _fake_save(camp):
        camp["_path"] = "/tmp/Acme_Plant_Manager.json"
        captured["camp"] = camp
    monkeypatch.setattr(fa, "save_campaign", _fake_save)

    def _fake_queue(camp, start_step=0):
        if raise_queue:
            raise raise_queue
        captured["queued_camp"] = camp
        return queued
    monkeypatch.setattr(fa, "queue_campaign_emails", _fake_queue)
    return captured


_SPEC = {"template": "fourbyfour", "company": "Acme Manufacturing",
         "website": "acme.com", "niche": "food processing",
         "industry": "manufacturing", "roles": ["Plant Manager"],
         "location": "Windsor, CO", "start_date": "2026-07-06",
         "candidates": [{"label": "Candidate A", "role": "Plant Manager",
                         "bullets": ["12 yrs"]}],
         "contacts": [{"email": "vp@acme.com", "first_name": "Dana"}]}


def test_route_requires_auth(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    status, _ = _call({}, _SPEC)
    assert status == 401


def test_route_happy_path_owner_from_key(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    cap = _stub_pipeline(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    status, body = _call({"authorization": f"Bearer {key}"}, _SPEC)
    assert status == 200, body
    assert body["steps"] == 5
    assert body["contacts_queued"] == 1
    assert len(body["schedule"]) == 5
    # Owner came from the key, not the body.
    assert cap["camp"]["_owner_email"] == "rep@arena.com"
    assert cap["camp"]["aicb_camp_type"] == "fourbyfour"


def test_route_defaults_start_date_to_upcoming_monday(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    cap = _stub_pipeline(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    spec = {k: v for k, v in _SPEC.items() if k != "start_date"}
    status, body = _call({"authorization": f"Bearer {key}"}, spec)
    assert status == 200, body
    # Server filled in the upcoming Monday; step 1 lands on that Monday.
    assert date.fromisoformat(body["start_date"]).weekday() == 0
    assert cap["camp"]["start_date"] == body["start_date"]
    assert body["schedule"][0]["date"] == body["start_date"]


def test_route_bad_template_400(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    _stub_pipeline(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    bad = dict(_SPEC, template="nope")
    status, _ = _call({"authorization": f"Bearer {key}"}, bad)
    assert status == 400


def test_route_queue_valueerror_422(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    _stub_pipeline(monkeypatch, raise_queue=ValueError("unfilled placeholder"))
    key = fa._mint_api_key("rep@arena.com")
    status, _ = _call({"authorization": f"Bearer {key}"}, _SPEC)
    assert status == 422

"""The "findcandidates" campaign template - the only one whose recipients
ARE the candidates (job_description-driven outreach) rather than hiring-
company contacts. Covers spec validation and the dedicated branch inside
POST /api/v1/campaigns that bypasses generate_aicb_campaign entirely.

Spec: docs/superpowers/specs (MCP campaign visibility + findcandidates design)
"""
import asyncio
import json as _json

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
    store = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: store)
    return store


# ── spec validation ────────────────────────────────────────────────────

def test_validate_spec_findcandidates_does_not_require_company_or_niche():
    assert fa._validate_campaign_spec({
        "template": "findcandidates",
        "job_description": "Senior Plant Manager...",
        "start_date": "2026-08-01",
    }) is None


def test_validate_spec_findcandidates_rejects_bad_cadence():
    err = fa._validate_campaign_spec({
        "template": "findcandidates", "cadence": "nope",
        "start_date": "2026-08-01",
    })
    assert err and "cadence" in err.lower()


def test_validate_spec_findcandidates_blank_cadence_ok():
    assert fa._validate_campaign_spec({
        "template": "findcandidates", "start_date": "2026-08-01",
    }) is None


def test_validate_spec_findcandidates_valid_cadence_ok():
    assert fa._validate_campaign_spec({
        "template": "findcandidates", "cadence": "three_emails_3days",
        "start_date": "2026-08-01",
    }) is None


# ── the POST /api/v1/campaigns route, findcandidates branch ────────────
# Call the async handler directly with a fake Request - avoids booting the
# whole NiceGUI app via TestClient (which is slow and pollutes the suite).

class _FakeReq:
    def __init__(self, headers, body):
        self.headers = headers
        self._body = body

    async def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _call(headers, body):
    resp = asyncio.run(fa.api_create_campaign(_FakeReq(headers, body)))
    return resp.status_code, _json.loads(resp.body)


def _stub_findcandidates(monkeypatch, emails=None, gen_error=None):
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(fa, "_tc_parse_jd", lambda jd_text: {
        "role_title": "Senior Plant Manager", "seniority": "senior",
        "key_skills": ["lean manufacturing"], "comp_range": "$120k-$150k",
        "location": "Windsor, CO",
    })
    monkeypatch.setattr(fa, "_recruiter_signoff_name", lambda s: "Dana")

    def _fake_generate(cadence, jd_text, jd_parsed, signoff_name):
        if gen_error:
            raise gen_error
        return emails if emails is not None else [
            {"subject": "Are you open to a new plant manager role?",
             "body": "Hi {FirstName},", "delay_days": 0, "time": "9:00 AM",
             "step_type": "email_auto"},
        ]
    monkeypatch.setattr(fa, "_generate_findcandidates_emails", _fake_generate)

    # generate_aicb_campaign must never be called for this template - fail
    # loudly if it is, so a regression that mis-routes findcandidates shows up.
    def _must_not_be_called(*a, **k):
        raise AssertionError("generate_aicb_campaign should not run for findcandidates")
    monkeypatch.setattr(fa, "generate_aicb_campaign", _must_not_be_called)

    captured = {}

    def _fake_save(camp):
        camp["_path"] = "/tmp/Senior_Plant_Manager.json"
        captured["camp"] = camp
    monkeypatch.setattr(fa, "save_campaign", _fake_save)

    def _fake_queue(camp, start_step=0):
        captured["queued_camp"] = camp
        return 1
    monkeypatch.setattr(fa, "queue_campaign_emails", _fake_queue)
    return captured


_FC_SPEC = {
    "template": "findcandidates",
    "job_description": "We are hiring a Senior Plant Manager in Windsor, CO...",
    "cadence": "one_email",
    "start_date": "2026-08-03",
    "contacts": [{"email": "candidate@example.com", "first_name": "Jamie"}],
}


def test_findcandidates_route_happy_path(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    cap = _stub_findcandidates(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    status, body = _call({"authorization": f"Bearer {key}"}, _FC_SPEC)
    assert status == 200, body
    assert body["steps"] == 1
    assert body["contacts_queued"] == 1
    # Campaign name comes from the parsed JD's role title, not spec["name"].
    assert cap["camp"]["name"] == "Senior Plant Manager"
    assert cap["camp"]["template_key"] == "findcandidates"
    assert cap["camp"]["_owner_email"] == "rep@arena.com"
    assert cap["camp"]["contacts"] == _FC_SPEC["contacts"]


def test_findcandidates_route_passes_cadence_through(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    seen = {}

    def _fake_generate(cadence, jd_text, jd_parsed, signoff_name):
        seen["cadence"] = cadence
        seen["jd_text"] = jd_text
        return [{"subject": "s", "body": "b", "delay_days": 0,
                  "time": "9:00 AM", "step_type": "email_auto"}]

    _stub_findcandidates(monkeypatch)
    monkeypatch.setattr(fa, "_generate_findcandidates_emails", _fake_generate)
    key = fa._mint_api_key("rep@arena.com")
    spec = dict(_FC_SPEC, cadence="three_emails_3days")
    status, _ = _call({"authorization": f"Bearer {key}"}, spec)
    assert status == 200
    assert seen["cadence"] == "three_emails_3days"
    assert seen["jd_text"] == spec["job_description"]


def test_findcandidates_route_defaults_cadence_to_one_email(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    seen = {}

    def _fake_generate(cadence, jd_text, jd_parsed, signoff_name):
        seen["cadence"] = cadence
        return [{"subject": "s", "body": "b", "delay_days": 0,
                  "time": "9:00 AM", "step_type": "email_auto"}]

    _stub_findcandidates(monkeypatch)
    monkeypatch.setattr(fa, "_generate_findcandidates_emails", _fake_generate)
    key = fa._mint_api_key("rep@arena.com")
    spec = {k: v for k, v in _FC_SPEC.items() if k != "cadence"}
    status, _ = _call({"authorization": f"Bearer {key}"}, spec)
    assert status == 200
    assert seen["cadence"] == "one_email"


def test_findcandidates_route_generation_error_500(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    _stub_findcandidates(monkeypatch, gen_error=RuntimeError("model returned no JSON"))
    key = fa._mint_api_key("rep@arena.com")
    status, body = _call({"authorization": f"Bearer {key}"}, _FC_SPEC)
    assert status == 500
    assert "generation error" in body["error"].lower()


def test_findcandidates_route_no_job_description_still_generates(tmp_path, monkeypatch):
    # job_description is optional - _tc_parse_jd is only called when present,
    # jd_parsed falls back to {} otherwise.
    _isolate_keys(tmp_path, monkeypatch)

    def _parse_jd_should_not_run(jd_text):
        raise AssertionError("_tc_parse_jd should not run without a job_description")
    cap = _stub_findcandidates(monkeypatch)
    monkeypatch.setattr(fa, "_tc_parse_jd", _parse_jd_should_not_run)
    key = fa._mint_api_key("rep@arena.com")
    spec = {k: v for k, v in _FC_SPEC.items() if k != "job_description"}
    status, body = _call({"authorization": f"Bearer {key}"}, spec)
    assert status == 200, body
    assert cap["camp"]["name"] == "findcandidates Campaign"

"""The "findcandidates" campaign template - the only one whose recipients
ARE the candidates. Covers spec validation, the opening fields, the
cadences, and the dedicated branch inside POST /api/v1/campaigns that
bypasses generate_aicb_campaign entirely, plus the read-only GET
/api/v1/campaigns routes that ship with it.

Spec: docs/superpowers/specs/2026-10-06-find-candidates-prompt-design.md
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


# ── registry ───────────────────────────────────────────────────────────

def test_registered_api_only_and_hidden_from_wizard():
    t = next(t for t in fa.AICB_CAMPAIGN_TYPES if t[0] == "findcandidates")
    assert t[1] == "Find Candidates"
    assert "findcandidates" in fa._VALID_TEMPLATES
    assert "findcandidates" in fa._API_ONLY_TYPES
    assert "findcandidates" not in fa._ARENA_SLATE_TYPES
    assert "findcandidates" not in fa._PIPELINE_SLATE_TYPES
    assert t[6] == ""  # no AICB prompt: written by _generate_findcandidates_emails


def test_cadences_use_relative_gaps():
    gaps = {k: [m["delay_days"] for m in v] for k, v in fa._TC_CADENCE_STEPS.items()}
    assert gaps == {
        "one_email": [0],
        "two_emails_1day": [0, 0],
        "three_emails_3days": [0, 1, 1],
        "three_emails_1week": [0, 3, 4],
    }
    assert set(fa._TC_STEP_PURPOSES) == {1, 2, 3}


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


@pytest.mark.parametrize("cadence", sorted(fa._TC_CADENCE_STEPS))
def test_validate_spec_findcandidates_every_cadence_ok(cadence):
    assert fa._validate_campaign_spec({
        "template": "findcandidates", "cadence": cadence,
        "start_date": "2026-08-01",
    }) is None


def test_validate_spec_findcandidates_selling_points_shape():
    base = {"template": "findcandidates", "start_date": "auto"}
    assert fa._validate_campaign_spec(dict(base, selling_points=["a", "b"])) is None
    assert fa._validate_campaign_spec(dict(base, selling_points="a; b")) is None
    err = fa._validate_campaign_spec(dict(base, selling_points={"a": 1}))
    assert err and "selling_points" in err


def test_other_templates_still_need_company_or_niche():
    err = fa._validate_campaign_spec({"template": "fivebyfive",
                                      "start_date": "auto"})
    assert err and "company" in err


# ── the opening ────────────────────────────────────────────────────────

def test_opening_from_spec_normalises():
    op = fa._fc_opening_from_spec({
        "role": " Plant Manager ", "client": "Acme", "location": "Windsor, CO",
        "pay": "$120k", "selling_points": "new line\nno weekends; owner retiring",
    })
    assert op == {"role": "Plant Manager", "client": "Acme",
                  "confidential": True, "location": "Windsor, CO",
                  "pay": "$120k",
                  "selling_points": ["new line", "no weekends",
                                     "owner retiring"]}
    assert fa._fc_opening_from_spec({"confidential": False})["confidential"] is False
    assert fa._fc_opening_from_spec({"confidential": "no"})["confidential"] is False
    assert fa._fc_opening_from_spec({"company": "Acme"})["client"] == "Acme"
    assert fa._fc_opening_from_spec({})["selling_points"] == []


class _Msg:
    def __init__(self, text):
        self.content = [type("T", (), {"text": text})()]


def _fake_model(monkeypatch, seen, n):
    emails = [{"name": "Step %d" % (i + 1), "subject": "s%d" % i,
               "body": "Hi {FirstName},<br><br>b%d<br><br>Best,<br>Dana" % i,
               "delay_days": 9, "time": "1:00 PM", "step_type": "email_auto"}
              for i in range(n)]

    def _fake(client, **kw):
        seen["prompt"] = kw["messages"][0]["content"]
        return _Msg(_json.dumps({"emails": emails}))
    monkeypatch.setattr(fa, "_claude_create_with_retry", _fake)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(fa, "_spread_email_times", lambda emails: None)


def test_generate_prompt_carries_the_opening_and_confidentiality(monkeypatch):
    seen = {}
    _fake_model(monkeypatch, seen, 3)
    out = fa._generate_findcandidates_emails(
        cadence="three_emails_1week", jd_text="", jd_parsed={},
        signoff_name="Dana",
        opening={"role": "Plant Manager", "client": "Acme Packaging",
                 "confidential": True, "location": "Windsor, CO",
                 "pay": "$120k to $140k",
                 "selling_points": ["new line next spring", "no weekends"]})
    p = seen["prompt"]
    assert "the role of Plant Manager" in p
    assert "Hiring company: confidential" in p
    assert "never name it" in p
    assert "Acme Packaging" not in p.split("ROLE CONTEXT")[0]
    assert "Pay: $120k to $140k" in p
    assert "new line next spring; no weekends" in p
    assert "Location: Windsor, CO" in p
    assert "3 emails over 8 day(s)" in p
    assert "Email 3: Soft close with an easy out" in p
    assert "NO JD PROVIDED" not in p
    # The cadence the caller asked for is pinned over whatever the model wrote.
    assert [e["delay_days"] for e in out] == [0, 3, 4]
    assert [e["time"] for e in out] == ["9:00 AM"] * 3
    assert all("Best," not in e["body"] for e in out)


def test_generate_prompt_names_the_client_when_not_confidential(monkeypatch):
    seen = {}
    _fake_model(monkeypatch, seen, 1)
    fa._generate_findcandidates_emails(
        cadence="one_email", jd_text="", jd_parsed={}, signoff_name="Dana",
        opening={"role": "Estimator", "client": "Acme Builders",
                 "confidential": False})
    p = seen["prompt"]
    assert "Hiring company: Acme Builders (name it)" in p
    assert "confidential" not in p.lower()
    assert "do not invent a number" in p


def test_generate_without_jd_or_opening_is_generic(monkeypatch):
    seen = {}
    _fake_model(monkeypatch, seen, 1)
    fa._generate_findcandidates_emails(
        cadence="one_email", jd_text="", jd_parsed={}, signoff_name="Dana")
    assert "NO JD PROVIDED" in seen["prompt"]
    assert "an open role" in seen["prompt"]


def test_generate_wizard_path_jd_only(monkeypatch):
    seen = {}
    _fake_model(monkeypatch, seen, 3)
    fa._generate_findcandidates_emails(
        cadence="three_emails_3days", jd_text="We need a Senior Plant Manager",
        jd_parsed={"role_title": "Senior Plant Manager", "seniority": "senior",
                   "key_skills": ["lean"], "comp_range": "$150k",
                   "location": "Windsor, CO"},
        signoff_name="Dana")
    p = seen["prompt"]
    assert "Title: Senior Plant Manager" in p
    assert "Seniority: senior" in p
    assert "Pay: $150k" in p
    assert "FULL JD (excerpt)" in p
    assert "3 emails over 3 day(s)" in p


def test_generate_rejects_wrong_count(monkeypatch):
    seen = {}
    _fake_model(monkeypatch, seen, 2)
    with pytest.raises(ValueError):
        fa._generate_findcandidates_emails(
            cadence="three_emails_1week", jd_text="", jd_parsed={},
            signoff_name="Dana")


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
    seen = {}

    def _fake_generate(cadence, jd_text, jd_parsed, signoff_name, opening=None):
        seen.update(cadence=cadence, jd_text=jd_text, jd_parsed=jd_parsed,
                    opening=opening)
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

    captured = {"seen": seen}

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
    # No role given: the campaign is named after the parsed JD's role title.
    assert cap["camp"]["name"] == "Find Candidates - Senior Plant Manager"
    assert cap["camp"]["template_key"] == "findcandidates"
    assert cap["camp"]["_chooser_origin"] == "candidate"
    assert cap["camp"]["_owner_email"] == "rep@arena.com"
    assert cap["camp"]["contacts"] == _FC_SPEC["contacts"]
    assert "candidate_refs" not in cap["camp"]


def test_findcandidates_route_passes_the_opening_through(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    cap = _stub_findcandidates(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    spec = dict(_FC_SPEC, cadence="three_emails_1week", role="Plant Manager",
                client="Acme Packaging", location="Windsor, CO",
                pay="$120k to $140k", selling_points=["new line", "no weekends"])
    spec.pop("job_description")
    status, body = _call({"authorization": f"Bearer {key}"}, spec)
    assert status == 200, body
    seen = cap["seen"]
    assert seen["cadence"] == "three_emails_1week"
    assert seen["jd_text"] == "" and seen["jd_parsed"] == {}
    assert seen["opening"] == {
        "role": "Plant Manager", "client": "Acme Packaging", "confidential": True,
        "location": "Windsor, CO", "pay": "$120k to $140k",
        "selling_points": ["new line", "no weekends"]}
    camp = cap["camp"]
    assert camp["name"] == "Find Candidates - Plant Manager"
    assert camp["variables"]["TargetRole"] == "Plant Manager"
    assert camp["variables"]["Geography"] == "Windsor, CO"
    # Confidential: the client's name never lands in a merge variable.
    assert camp["variables"]["CompanyName"] == ""
    assert "Acme" not in camp["synopsis"]
    assert "Plant Manager" in camp["synopsis"]


def test_findcandidates_route_names_the_client_when_not_confidential(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    cap = _stub_findcandidates(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    spec = dict(_FC_SPEC, role="Estimator", client="Acme Builders",
                confidential=False, name="Acme estimators")
    status, _ = _call({"authorization": f"Bearer {key}"}, spec)
    assert status == 200
    camp = cap["camp"]
    assert camp["name"] == "Acme estimators"
    assert camp["variables"]["CompanyName"] == "Acme Builders"
    assert "at Acme Builders" in camp["synopsis"]
    assert cap["seen"]["opening"]["confidential"] is False


def test_findcandidates_route_defaults_cadence_to_one_email(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    cap = _stub_findcandidates(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    spec = {k: v for k, v in _FC_SPEC.items() if k != "cadence"}
    status, _ = _call({"authorization": f"Bearer {key}"}, spec)
    assert status == 200
    assert cap["seen"]["cadence"] == "one_email"


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
    assert cap["camp"]["name"] == "Find Candidates"


# ── GET /api/v1/campaigns and /{campaign_id} ───────────────────────────

class _GetReq:
    def __init__(self, headers):
        self.headers = headers


def _camps():
    return [
        {"name": "Find Candidates - Plant Manager", "_path": "/x/fc_pm.json",
         "template_key": "findcandidates", "start_date": "2026-10-13",
         "synopsis": "s", "emails": [{"subject": "a"}, {"subject": "b"}],
         "contacts": [{"email": "a@b.com"}, {"email": "c@d.com"}]},
        {"name": "Acme 5x5", "_path": "/x/acme.json",
         "aicb_camp_type": "fivebyfive", "emails": [{}], "contacts": []},
    ]


def _queue():
    return [
        {"campaign": "Find Candidates - Plant Manager", "status": "sent"},
        {"campaign": "Find Candidates - Plant Manager", "status": "pending"},
        {"campaign": "Find Candidates - Plant Manager", "status": "pending"},
        {"campaign": "Acme 5x5", "status": "cancelled"},
        {"campaign": "", "status": "pending"},
    ]


def _stub_reads(monkeypatch):
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "load_campaigns", _camps)
    monkeypatch.setattr(fa, "_load_queue", _queue)


def test_campaigns_list_requires_key(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    resp = asyncio.run(fa.api_campaigns_list(_GetReq({})))
    assert resp.status_code == 401


def test_campaigns_list_returns_summaries_with_queue_stats(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    _stub_reads(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    resp = asyncio.run(fa.api_campaigns_list(_GetReq({"x-api-key": key})))
    assert resp.status_code == 200
    body = _json.loads(resp.body)
    assert [c["campaign_id"] for c in body] == ["fc_pm", "acme"]
    assert body[0] == {
        "campaign_id": "fc_pm", "name": "Find Candidates - Plant Manager",
        "template": "findcandidates", "start_date": "2026-10-13",
        "steps": 2, "contacts": 2,
        "queue": {"pending": 2, "sent": 1, "failed": 0, "cancelled": 0}}
    assert body[1]["template"] == "fivebyfive"
    assert body[1]["queue"]["cancelled"] == 1
    # Summaries never carry the emails or the contacts themselves.
    assert "emails" not in body[0]


def test_campaign_get_by_id_or_name_and_404(tmp_path, monkeypatch):
    _isolate_keys(tmp_path, monkeypatch)
    _stub_reads(monkeypatch)
    key = fa._mint_api_key("rep@arena.com")
    hdr = _GetReq({"authorization": f"Bearer {key}"})
    by_id = _json.loads(asyncio.run(fa.api_campaign_get("fc_pm", hdr)).body)
    by_name = _json.loads(asyncio.run(
        fa.api_campaign_get("Find Candidates - Plant Manager", hdr)).body)
    assert by_id == by_name
    assert by_id["contacts"] == [{"email": "a@b.com"}, {"email": "c@d.com"}]
    assert len(by_id["emails"]) == 2
    assert by_id["queue"] == {"pending": 2, "sent": 1, "failed": 0, "cancelled": 0}
    missing = asyncio.run(fa.api_campaign_get("nope", hdr))
    assert missing.status_code == 404

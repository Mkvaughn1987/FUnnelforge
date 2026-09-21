"""Connector group A (2026-09-21): campaign editing from Claude/ChatGPT.

tm_campaign_edit does what the campaign editor page does (edit, add, delete,
move steps; timing; rename; Rewrite with AI; Remember Style; remove an
attachment) and keeps a running campaign's queue in step. tm_campaign_action
gained duplicate / launch / followon / graduate_responders, and
create_campaign a draft mode. Every route sits behind the same key + gate
door and calls the helper its page calls."""
import ast
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

import flowdrip_app as fa

_OWNER = "rep@thrivemodal.com"
_ROOT = Path(__file__).resolve().parent.parent

_ROUTES = [  # (method, path, handler)
    ("post", "/api/v1/tm/campaigns/edit", "api_tm_campaign_edit"),
    ("post", "/api/v1/tm/campaigns/action", "api_tm_campaign_action"),
]


# ── structure ──────────────────────────────────────────────────────────────

def _src(rel):
    return (_ROOT / rel).read_text(encoding="utf-8")


def _tree(rel):
    return ast.parse(_src(rel))


def _tools():
    out = {}
    for n in ast.walk(_tree("mcp_server/dripdrop_mcp.py")):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.decorator_list:
                t = d.func if isinstance(d, ast.Call) else d
                if isinstance(t, ast.Attribute) and t.attr == "tool":
                    out[n.name] = n
    return out


def _client_methods():
    for n in ast.walk(_tree("mcp_server/dripdrop_client.py")):
        if isinstance(n, ast.ClassDef) and n.name == "DripDropClient":
            return {s.name for s in n.body
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return set()


def _app_func(name):
    for n in _tree("flowdrip_app.py").body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


@pytest.mark.parametrize("name", ["tm_campaign_edit", "tm_campaign_action"])
def test_tools_pair_with_client_methods(name):
    assert name in _tools()
    assert name in _client_methods()


def test_action_tool_takes_the_new_parameters():
    args = {a.arg for a in _tools()["tm_campaign_action"].args.args}
    assert {"start_date", "newsletter_id", "email", "active_clients",
            "contacts", "list_name", "enroll_newsletter", "name"} <= args


def test_tool_descriptions_warn_about_real_email():
    src = _src("mcp_server/dripdrop_mcp.py")
    assert "SENDS REAL EMAIL" in src and "spec.draft=true" in src


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_routes_are_registered_gated_and_keyed(method, path, handler):
    node = _app_func(handler)
    assert node is not None, handler
    decs = [ast.unparse(d) for d in node.decorator_list]
    assert f"app.{method}('{path}')" in decs, decs
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    assert "_is_thrivemodal" in names and "_tm_api_owner" in names
    owners = [a.value for a in ast.walk(node) if isinstance(a, ast.Assign)
              for t in a.targets if isinstance(t, ast.Name) and t.id == "owner"]
    assert len(owners) == 1 and ast.unparse(owners[0]) == "_tm_api_owner(request)"


@pytest.mark.parametrize("rel,begin,end", [
    ("flowdrip_app.py", "# ── connector group A (2026-09-21) begin ──",
     "# ── connector group A end ──"),
    ("mcp_server/dripdrop_client.py", "    # ── connector group A (2026-09-21) begin ──",
     "    # ── connector group A end ──"),
    ("mcp_server/dripdrop_mcp.py", "# ── connector group A (2026-09-21) begin ──",
     "# ── connector group A end ──"),
])
def test_new_code_lives_between_the_group_a_anchors(rel, begin, end):
    src = _src(rel)
    a, b = src.index(begin), src.index(end)
    region = src[a:b]
    for needle in {"flowdrip_app.py": ("def api_tm_campaign_edit", "def _tm_action_launch",
                                       "def _tm_action_followon", "def _tm_action_graduate"),
                   "mcp_server/dripdrop_client.py": ("def tm_campaign_edit",),
                   "mcp_server/dripdrop_mcp.py": ("def tm_campaign_edit",)}[rel]:
        assert needle in region and src.count(needle) == region.count(needle), needle


def test_pages_call_the_shared_helpers():
    """The extractions keep the page and the connector on one code path."""
    assert "_shift_subsequent_fixed_dates(" in ast.unparse(_app_func("_sq_loaded_campaign"))
    assert "_ai_rewrite_email_body(" in ast.unparse(_app_func("_ai_assist_email"))
    teach = ast.unparse(_app_func("_teach_ai_from_edit"))
    assert "_ai_style_rules_from_edit(" in teach and "_append_ai_style_rules(" in teach


# ── pure helpers ───────────────────────────────────────────────────────────

def test_send_time_takes_the_pickers_spelling():
    assert fa._tm_parse_send_time("09:00 am") == "9:00 AM"
    assert fa._tm_parse_send_time("2:30PM") == "2:30 PM"
    assert fa._tm_parse_send_time("2:10 PM") is None  # quarter hours only
    assert fa._tm_parse_send_time("noon") is None


def test_renumber_names_steps_by_type():
    steps = [{"step_type": "email_auto"}, {"step_type": "call"},
             {"step_type": ""}, {"step_type": "linkedin"}]
    fa._tm_renumber_steps(steps)
    assert [s["name"] for s in steps] == ["Email 1", "Call 1", "Email 2", "LinkedIn 1"]
    assert [s["touch_number"] for s in steps] == [1, 2, 3, 4]


def test_shifting_a_date_moves_later_dated_steps():
    steps = [{"fixed_date": "2026-10-01"}, {"fixed_date": "2026-10-05"},
             {"delay_days": 2}, {"fixed_date": "2026-10-20"}]
    fa._shift_subsequent_fixed_dates(steps, 0, "2026-10-01", "2026-10-08")
    assert steps[1]["fixed_date"] == "2026-10-12"
    assert "fixed_date" not in steps[2]
    assert steps[3]["fixed_date"] == "2026-10-27"


class _Msg:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]


def test_rewrite_helper_cleans_the_models_output(monkeypatch):
    seen = {}
    monkeypatch.setattr(fa, "_claude_create_with_retry",
                        lambda client, **kw: seen.update(kw) or
                        _Msg("```html\n**Hi** {FirstName} — there\n```"))
    out = fa._ai_rewrite_email_body(None, "shorter", "Hello", "Subj")
    assert out == "<b>Hi</b> {FirstName} ,  there"
    assert "shorter" in seen["messages"][0]["content"]


def test_style_rules_append_to_the_guide(monkeypatch):
    cfg = {"ai_style_guide": "- Old rule"}
    monkeypatch.setattr(fa, "load_config", lambda: cfg)
    monkeypatch.setattr(fa, "save_config", lambda c: cfg.update(c))
    assert fa._append_ai_style_rules("- A\n- B\n") == 2
    assert cfg["ai_style_guide"] == "- Old rule\n- A\n- B"


def test_generate_passes_the_followon_note_to_the_build_only(monkeypatch):
    seen = {}
    monkeypatch.setattr(fa, "_aicb_research_brief", lambda client, **kw: "BRIEF")
    monkeypatch.setattr(fa.time, "sleep", lambda *a: None)
    monkeypatch.setattr(fa, "_aicb_build_campaign_from_brief",
                        lambda client, **kw: seen.update(kw) or {"emails": []})
    out = fa.generate_aicb_campaign(None, camp_type="tm_stay_in_touch",
                                    company="Acme", brief_prefix="NOTE ")
    assert seen["brief"] == "NOTE BRIEF" and out["_brief"] == "BRIEF"


def test_blocking_create_adds_the_note_only_for_a_followon(monkeypatch):
    calls = []
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    monkeypatch.setattr(fa, "generate_aicb_campaign",
                        lambda client, **kw: calls.append(kw) or {"emails": []})
    fa._api_create_campaign_blocking(None, {"template": "tm_stay_in_touch",
                                            "company": "Acme"}, _OWNER)
    fa._api_create_campaign_blocking(None, {"template": "tm_stay_in_touch",
                                            "company": "Acme",
                                            "followon_from": "Q3 Intro"}, _OWNER)
    assert "brief_prefix" not in calls[0]
    assert "'Q3 Intro'" in calls[1]["brief_prefix"]


# ── harness ────────────────────────────────────────────────────────────────

def _camp(**kw):
    c = {"name": "Acme Outreach", "_path": "/data/Acme_Outreach.json",
         "status": "active", "aicb_camp_type": "tm_fivebyseven",
         "variables": {"CompanyName": "Acme", "TargetRole": "Bookkeeper",
                       "Geography": "Nationwide", "Industry": "Accounting"},
         "contacts": [{"email": "ann@x.com", "first_name": "Ann"},
                      {"email": "bo@x.com", "first_name": "Bo", "removed": True},
                      {"email": "cy@x.com", "first_name": "Cy"}],
         "emails": [{"name": "Email 1", "subject": "Hi {FirstName}",
                     "body": "Hello {FirstName}", "step_type": "email_auto",
                     "delay_days": 0, "time": "9:00 AM", "attachments": []},
                    {"name": "Call 1", "subject": "", "body": "",
                     "script_notes": "Ask about hiring", "step_type": "call",
                     "delay_days": 2, "time": "10:00 AM"},
                    {"name": "Email 2", "subject": "Following up",
                     "body": "Quick follow up", "step_type": "email_auto",
                     "delay_days": 3, "time": "9:00 AM",
                     "attachments": ["Cost_Comparison_Acme.pdf"]}]}
    c.update(kw)
    return c


@pytest.fixture
def api(tmp_path, monkeypatch):
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "sk-test")
    camps = [_camp()]
    saved, queue, requeued, deleted = [], [], [], []
    monkeypatch.setattr(fa, "load_campaigns", lambda: camps)
    monkeypatch.setattr(fa, "save_campaign", lambda c: saved.append(json.loads(json.dumps(c))))
    monkeypatch.setattr(fa, "_load_queue", lambda: queue)
    monkeypatch.setattr(fa, "requeue_campaign", lambda c: requeued.append(c) or
                        {"cancelled": 4, "queued": 4, "skipped_sent": 0})
    monkeypatch.setattr(fa, "delete_campaign", lambda p: deleted.append(p))
    monkeypatch.setattr(fa, "_strip_signature_from_body", lambda b: b)
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    app = FastAPI()
    for method, path, handler in _ROUTES:
        getattr(app, method)(path)(getattr(fa, handler))
    client = TestClient(app)
    key = fa._mint_api_key(_OWNER)

    def call(path, body=None, auth=True):
        h = {"X-API-Key": key} if auth else {}
        return client.post(path, json=body or {}, headers=h)

    def edit(**body):
        return call("/api/v1/tm/campaigns/edit",
                    dict({"campaign_id": "Acme_Outreach"}, **body))

    def action(**body):
        return call("/api/v1/tm/campaigns/action",
                    dict({"campaign_id": "Acme_Outreach"}, **body))
    return {"call": call, "edit": edit, "action": action, "camps": camps,
            "saved": saved, "queue": queue, "requeued": requeued,
            "deleted": deleted}


def _q(status, name="Acme Outreach", **kw):
    return dict({"campaign": name, "status": status, "to": "ann@x.com"}, **kw)


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_routes_need_a_key(api, method, path, handler):
    assert api["call"](path, auth=False).status_code == 401


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_routes_are_404_on_arena(api, monkeypatch, method, path, handler):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    assert api["call"](path).status_code == 404


def test_edit_refuses_unknown_campaigns_actions_and_steps(api):
    e = api["edit"]
    assert api["call"]("/api/v1/tm/campaigns/edit",
                       {"campaign_id": "nope", "action": "rename"}).status_code == 404
    assert e(action="explode").status_code == 400
    assert e(action="update_step", step=9, subject="x").status_code == 400
    assert e(action="update_step", step=1).status_code == 400  # nothing to change


# ── update_step ────────────────────────────────────────────────────────────

def test_update_a_draft_saves_and_touches_no_queue(api):
    r = api["edit"](action="update_step", step=1, subject="New {FirstName}",
                    body="<p>New body</p>", delay_days=1, send_time="10:15 am")
    assert r.status_code == 200, r.text
    st = api["saved"][-1]["emails"][0]
    assert (st["subject"], st["body"], st["delay_days"], st["time"]) == (
        "New {FirstName}", "<p>New body</p>", 1, "10:15 AM")
    assert r.json()["queue"] == {"pending_emails": 0, "queue_items_changed": 0}
    assert api["requeued"] == []
    assert r.json()["campaign_id"] == "Acme_Outreach"
    assert "_path" not in json.dumps(r.json())


def test_update_a_running_campaign_requeues_its_live_contacts(api):
    api["queue"].extend([_q("pending"), _q("pending", to="cy@x.com")])
    r = api["edit"](action="update_step", step=3, body="Better follow up")
    assert r.status_code == 200, r.text
    assert r.json()["queue"]["queue_items_changed"] == 4
    assert r.json()["queue"]["requeue"]["cancelled"] == 4
    sent_to = [c["email"] for c in api["requeued"][0]["contacts"]]
    assert sent_to == ["ann@x.com", "cy@x.com"]  # removed contact stays out


def test_update_validates_timing(api):
    e = api["edit"]
    assert e(action="update_step", step=1, send_time="9:07 AM").status_code == 400
    assert e(action="update_step", step=1, delay_days=400).status_code == 400
    assert e(action="update_step", step=1, send_date="next week").status_code == 400


def test_moving_a_date_carries_later_dated_steps(api):
    steps = api["camps"][0]["emails"]
    steps[0]["fixed_date"], steps[2]["fixed_date"] = "2026-10-01", "2026-10-06"
    r = api["edit"](action="update_step", step=1, send_date="2026-10-08")
    assert r.status_code == 200, r.text
    assert api["saved"][-1]["emails"][2]["fixed_date"] == "2026-10-13"


def test_non_email_steps_take_a_note_not_a_subject(api):
    e = api["edit"]
    assert e(action="update_step", step=2, subject="x").status_code == 400
    assert e(action="update_step", step=1, note="x").status_code == 400
    r = e(action="update_step", step=2, note="New call script")
    assert r.status_code == 200
    assert api["saved"][-1]["emails"][1]["script_notes"] == "New call script"


def test_newsletters_get_their_queued_issue_patched_not_requeued(api, monkeypatch):
    patched = []
    api["camps"][0].update(evergreen_only=True, market_analysis=True)
    api["queue"].append(_q("pending"))
    monkeypatch.setattr(fa, "_tm_patch_pending",
                        lambda *a: patched.append(a) or 3)
    r = api["edit"](action="update_step", step=1, subject="October issue")
    assert r.status_code == 200, r.text
    assert patched[0][:4] == ("Acme Outreach", "Email 1", "Hi {FirstName}", "October issue")
    assert r.json()["queue"]["queue_items_changed"] == 3 and api["requeued"] == []
    assert api["edit"](action="update_step", step=1, delay_days=2).status_code == 409
    assert api["edit"](action="add_step", type="call").status_code == 409


# ── add / delete / move ────────────────────────────────────────────────────

def test_add_a_linkedin_step_first_warns_and_renumbers(api):
    api["camps"][0]["emails"].insert(1, {"name": "LinkedIn 1", "step_type": "linkedin"})
    r = api["edit"](action="add_step", type="linkedin", position=1,
                    note="Connect note")
    assert r.status_code == 200, r.text
    assert len(r.json()["warnings"]) == 2
    steps = api["saved"][-1]["emails"]
    assert steps[0]["step_type"] == "linkedin" and steps[0]["script_notes"] == "Connect note"
    assert steps[0]["channel"] == "li" and steps[0]["delay_days"] == 1
    assert [s["name"] for s in steps] == ["LinkedIn 1", "Email 1", "LinkedIn 2",
                                          "Call 1", "Email 2"]
    assert [s["touch_number"] for s in steps] == [1, 2, 3, 4, 5]


def test_add_an_email_at_the_end_by_default(api):
    r = api["edit"](action="add_step", subject="Last try", body="One more",
                    delay_days=5)
    assert r.status_code == 200, r.text
    last = api["saved"][-1]["emails"][-1]
    assert (last["name"], last["subject"], last["delay_days"]) == ("Email 3", "Last try", 5)
    assert api["edit"](action="add_step", type="fax").status_code == 400
    assert api["edit"](action="add_step", position=9).status_code == 400


def test_steps_are_frozen_once_email_has_gone_out(api):
    api["queue"].append(_q("sent"))
    e = api["edit"]
    assert e(action="add_step").status_code == 409
    assert e(action="delete_step", step=2).status_code == 409
    assert e(action="move_step", step=2, to_position=1).status_code == 409
    assert api["saved"] == []


def test_delete_keeps_at_least_one_step(api):
    r = api["edit"](action="delete_step", step=2)
    assert r.status_code == 200
    assert [s["name"] for s in api["saved"][-1]["emails"]] == ["Email 1", "Email 2"]
    api["camps"][0]["emails"] = api["camps"][0]["emails"][:1]
    assert api["edit"](action="delete_step", step=1).status_code == 400


def test_moving_an_attachment_carrier_first_drops_its_attachment(api):
    r = api["edit"](action="move_step", step=3, to_position=1)
    assert r.status_code == 200, r.text
    assert r.json()["attachments_removed_from_first_step"] == ["Cost_Comparison_Acme.pdf"]
    steps = api["saved"][-1]["emails"]
    assert steps[0]["subject"] == "Following up" and steps[0]["attachments"] == []
    assert api["edit"](action="move_step", step=1, to_position=7).status_code == 400


# ── rename ─────────────────────────────────────────────────────────────────

def test_rename_before_launch_drops_the_old_file(api, monkeypatch):
    def _save(c):
        c["_path"] = "/data/Acme_Q4.json"
        api["saved"].append(dict(c))
    monkeypatch.setattr(fa, "save_campaign", _save)
    r = api["edit"](action="rename", name="Acme Q4")
    assert r.status_code == 200, r.text
    assert r.json()["renamed"] == {"from": "Acme Outreach", "to": "Acme Q4"}
    assert r.json()["campaign_id"] == "Acme_Q4"
    assert api["deleted"] == ["/data/Acme_Outreach.json"]


def test_rename_refuses_a_taken_name_or_a_launched_campaign(api):
    api["camps"].append(_camp(name="Other", _path="/data/Other.json"))
    assert api["edit"](action="rename", name="other").status_code == 409
    api["queue"].append(_q("sent"))
    assert api["edit"](action="rename", name="Brand New").status_code == 409
    assert api["edit"](action="rename", name="").status_code == 400


# ── AI ─────────────────────────────────────────────────────────────────────

def test_ai_rewrite_returns_then_applies(api, monkeypatch):
    seen = []
    cfg = {}
    monkeypatch.setattr(fa, "_ai_rewrite_email_body",
                        lambda client, ins, body, subj: seen.append((ins, body, subj))
                        or "<p>Shorter</p>")
    monkeypatch.setattr(fa, "load_config", lambda: cfg)
    monkeypatch.setattr(fa, "save_config", lambda c: cfg.update(c))
    r = api["edit"](action="ai_rewrite", step=1, instruction="Make it shorter")
    assert r.status_code == 200, r.text
    assert r.json()["body"] == "<p>Shorter</p>" and r.json()["applied"] is False
    assert seen[0] == ("Make it shorter", "Hello {FirstName}", "Hi {FirstName}")
    assert api["saved"] == [] and "ai_style_guide" not in cfg
    r = api["edit"](action="ai_rewrite", step=1, instruction="Make it shorter",
                    apply=True, remember=True)
    assert api["saved"][-1]["emails"][0]["body"] == "<p>Shorter</p>"
    assert cfg["ai_style_guide"] == "Always: Make it shorter"
    assert api["edit"](action="ai_rewrite", step=2, instruction="x").status_code == 400
    assert api["edit"](action="ai_rewrite", step=1).status_code == 400


def test_ai_rewrite_needs_a_body_or_a_write_request(api, monkeypatch):
    monkeypatch.setattr(fa, "_ai_rewrite_email_body", lambda *a: "<p>New</p>")
    api["camps"][0]["emails"][0]["body"] = ""
    assert api["edit"](action="ai_rewrite", step=1,
                       instruction="shorter").status_code == 400
    assert api["edit"](action="ai_rewrite", step=1,
                       instruction="Write a warm intro").status_code == 200


def test_ai_actions_need_the_ai(api, monkeypatch):
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    assert api["edit"](action="ai_rewrite", step=1,
                       instruction="shorter").status_code == 503


def test_remember_style_learns_and_optionally_saves(api, monkeypatch):
    learned = []
    monkeypatch.setattr(fa, "_ai_style_rules_from_edit",
                        lambda client, o, e: "- Keep it short\n- No fluff")
    monkeypatch.setattr(fa, "_append_ai_style_rules", lambda t: learned.append(t) or 2)
    e = api["edit"]
    assert e(action="remember_style", step=1,
             edited_body="Hello {FirstName}").status_code == 400  # no change
    r = e(action="remember_style", step=1, edited_body="Hi {FirstName}, short.")
    assert r.status_code == 200, r.text
    assert r.json()["learned_rules"] == ["- Keep it short", "- No fluff"]
    assert learned and api["saved"] == []
    r = e(action="remember_style", step=1, edited_body="Hi, short.", apply=True)
    assert api["saved"][-1]["emails"][0]["body"] == "Hi, short."


def test_remember_style_reports_content_only_edits(api, monkeypatch):
    monkeypatch.setattr(fa, "_ai_style_rules_from_edit", lambda *a: "NONE")
    monkeypatch.setattr(fa, "_append_ai_style_rules",
                        lambda t: pytest.fail("nothing to learn"))
    r = api["edit"](action="remember_style", step=1,
                    original_body="Acme", edited_body="Beta")
    assert r.status_code == 200 and r.json()["learned_rules"] == []


# ── attachments ────────────────────────────────────────────────────────────

def test_remove_attachment_syncs_pending_emails(api, monkeypatch):
    monkeypatch.setattr(fa, "_tm_save_queue_sync", lambda c: 6)
    assert api["edit"](action="remove_attachment", step=3,
                       attachment="nope.pdf").status_code == 404
    r = api["edit"](action="remove_attachment", step=3,
                    attachment="Cost_Comparison_Acme.pdf")
    assert r.status_code == 200, r.text
    assert r.json()["queue_items_changed"] == 6
    assert api["saved"][-1]["emails"][2]["attachments"] == []


# ── campaign actions ───────────────────────────────────────────────────────

def test_duplicate_goes_through_the_pages_helper(api, monkeypatch):
    monkeypatch.setattr(fa, "duplicate_campaign", lambda c: {
        "name": c["name"] + " (Copy)", "_path": "/data/Acme_Outreach__Copy_.json",
        "emails": c["emails"]})
    r = api["action"](action="duplicate")
    assert r.status_code == 200, r.text
    assert r.json()["duplicate"]["campaign_id"] == "Acme_Outreach__Copy_"
    assert r.json()["duplicate"]["steps"] == 3


@pytest.fixture
def launch(api, monkeypatch):
    queued = []
    api["camps"][0]["status"] = "draft"
    monkeypatch.setattr(fa, "load_client_blocklist", lambda *a: [])
    monkeypatch.setattr(fa, "queue_campaign_emails",
                        lambda c: queued.append(json.loads(json.dumps(c))) or 7)
    api["queued"] = queued
    return api


def test_launch_needs_confirm_a_real_date_and_contacts(launch):
    a = launch["action"]
    assert a(action="launch").status_code == 400
    past = (date.today() - timedelta(days=1)).isoformat()
    assert a(action="launch", confirm=True, start_date=past).status_code == 400
    assert a(action="launch", confirm=True, start_date="soon").status_code == 400
    launch["camps"][0]["contacts"] = []
    assert a(action="launch", confirm=True).status_code == 400
    assert launch["queued"] == []


def test_launch_queues_the_draft(launch):
    start = (date.today() + timedelta(days=2)).isoformat()
    r = launch["action"](action="launch", confirm=True, start_date=start)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["launched"] is True and body["emails_queued"] == 7
    assert body["start_date"] == start and len(body["schedule"]) == 3
    q = launch["queued"][0]
    assert q["status"] == "active" and q["start_date"] == start


def test_launch_can_set_contacts_and_rename(launch, monkeypatch):
    def _save(c):
        c["_path"] = "/data/Acme_Launch.json"
        launch["saved"].append(dict(c))
    monkeypatch.setattr(fa, "save_campaign", _save)
    r = launch["action"](action="launch", confirm=True, name="Acme Launch",
                         contacts=[{"Email": "Zed@Y.com", "FirstName": "Zed"},
                                   {"email": "bad"}])
    assert r.status_code == 200, r.text
    assert [c["email"] for c in launch["queued"][0]["contacts"]] == ["zed@y.com"]
    assert r.json()["invalid_email"] == 1 and r.json()["campaign"] == "Acme Launch"
    assert launch["deleted"] == ["/data/Acme_Outreach.json"]


def test_launch_stops_at_active_clients_until_the_user_decides(launch, monkeypatch):
    monkeypatch.setattr(fa, "load_client_blocklist",
                        lambda *a: [{"domain": "x.com", "client_name": "X Corp"}])
    r = launch["action"](action="launch", confirm=True)
    assert r.status_code == 409
    assert r.json()["active_client_contacts"] == 3
    assert r.json()["clients"][0]["client"] == "X Corp"
    assert launch["queued"] == []
    assert launch["action"](action="launch", confirm=True,
                            active_clients="maybe").status_code == 400
    r = launch["action"](action="launch", confirm=True, active_clients="skip")
    assert r.status_code == 200, r.text
    assert launch["queued"][0]["_ac_decision"] == "skip"


def test_launch_refuses_a_launched_campaign_and_newsletters(launch):
    launch["queue"].append(_q("pending"))
    assert launch["action"](action="launch", confirm=True).status_code == 409
    launch["queue"].clear()
    launch["camps"][0]["evergreen_only"] = True
    assert launch["action"](action="launch", confirm=True).status_code == 409


def test_launch_reports_unfilled_placeholders(launch, monkeypatch):
    def _boom(c):
        raise ValueError("Campaign 'Acme Outreach' has 1 unfilled placeholder(s)")
    monkeypatch.setattr(fa, "queue_campaign_emails", _boom)
    r = launch["action"](action="launch", confirm=True)
    assert r.status_code == 422 and "placeholder" in r.json()["error"]
    assert launch["saved"][-1]["status"] == "draft"


@pytest.fixture
def followon(api, monkeypatch):
    specs = []
    monkeypatch.setattr(fa, "load_responded", lambda: [{"email": "ann@x.com"}])
    monkeypatch.setattr(fa, "load_dnc", lambda: [])
    monkeypatch.setattr(fa, "_api_create_campaign_blocking",
                        lambda client, spec, owner: specs.append(spec) or {
                            "template": spec["template"],
                            "campaign_data": {"campaign_name": "Radar",
                                              "synopsis": "S"},
                            "emails": [{"subject": "Checking in", "body": "Hi",
                                        "step_type": "email_auto"}],
                            "pdfs": [{"kind": "tm_how_it_works", "step": 1}]})
    api["specs"] = specs
    return api


def test_followon_writes_a_draft_for_the_non_repliers(followon):
    r = followon["action"](action="followon")
    assert r.status_code == 200, r.text
    spec = followon["specs"][0]
    assert spec["template"] == "tm_stay_in_touch"
    assert spec["followon_from"] == "Acme Outreach"
    assert spec["company"] == "Acme" and spec["roles"] == ["Bookkeeper"]
    new = followon["saved"][-1]
    assert new["status"] == "draft" and new["aicb_camp_type"] == "tm_stay_in_touch"
    assert new["name"] == "Acme Outreach (Stay on Their Radar)"
    # Ann replied; Bo was removed but never replied, so he stays in.
    assert [c["email"] for c in new["contacts"]] == ["bo@x.com", "cy@x.com"]
    assert r.json()["draft"]["contacts"] == 2 and r.json()["pdfs"]
    assert followon["queue"] == []


def test_followon_only_for_a_finished_tm_campaign(followon, monkeypatch):
    a = followon["action"]
    followon["queue"].append(_q("pending"))
    assert a(action="followon").status_code == 409
    followon["queue"].clear()
    followon["camps"][0]["aicb_camp_type"] = "tm_stay_in_touch"
    assert a(action="followon").status_code == 400
    followon["camps"][0]["aicb_camp_type"] = "tm_fivebyseven"
    monkeypatch.setattr(fa, "load_dnc", lambda: [{"email": "bo@x.com"},
                                                 {"email": "cy@x.com"}])
    assert a(action="followon").status_code == 409
    assert followon["specs"] == []


def test_graduate_repliers_into_a_newsletter(api, monkeypatch):
    enrolled = []
    api["camps"].append(_camp(name="CPA Monthly", _path="/data/CPA_Monthly.json",
                              evergreen_only=True, contacts=[]))
    monkeypatch.setattr(fa, "load_responded", lambda: [{"email": "ann@x.com"}])
    monkeypatch.setattr(fa, "enroll_contact_in_evergreen",
                        lambda c, t: enrolled.append((c["email"], t["name"])) or "enrolled")
    r = api["action"](action="graduate_responders", newsletter_id="CPA_Monthly")
    assert r.status_code == 200, r.text
    # Replied (Ann) and removed (Bo), as the page's Graduate button picks them.
    assert enrolled == [("ann@x.com", "CPA Monthly"), ("bo@x.com", "CPA Monthly")]
    assert r.json()["enrolled"] == 2
    enrolled.clear()
    r = api["action"](action="graduate_responders", newsletter_id="CPA_Monthly",
                      email="CY@x.com")
    assert enrolled == [("cy@x.com", "CPA Monthly")]
    assert api["action"](action="graduate_responders", newsletter_id="CPA_Monthly",
                         email="nobody@x.com").status_code == 404
    assert api["action"](action="graduate_responders",
                         newsletter_id="Acme_Outreach").status_code == 404


def test_unknown_action_lists_the_new_ones(api):
    r = api["action"](action="teleport")
    assert r.status_code == 400 and "graduate_responders" in r.json()["error"]


# ── create_campaign draft mode ─────────────────────────────────────────────

class _Req:
    def __init__(self, body):
        self.headers = {"x-api-key": ""}
        self._body = body

    async def json(self):
        return self._body


def _create(monkeypatch, spec, queued):
    import asyncio
    monkeypatch.setattr(fa, "_resolve_api_key", lambda k: _OWNER)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "sk-test")
    saved = []

    def _save(c):
        c["_path"] = "/data/Acme_Draft.json"
        saved.append(c)
    monkeypatch.setattr(fa, "save_campaign", _save)
    monkeypatch.setattr(fa, "queue_campaign_emails", lambda c: queued.append(c) or 5)
    monkeypatch.setattr(fa, "_api_create_campaign_blocking", lambda client, s, o: {
        "template": s["template"], "campaign_data": {"campaign_name": "Acme Draft"},
        "emails": [{"subject": "Hi", "body": "Hello", "step_type": "email_auto",
                    "delay_days": 0}]})
    resp = asyncio.run(fa.api_create_campaign(_Req(spec)))
    return resp.status_code, json.loads(resp.body), saved


def test_create_campaign_draft_saves_without_queueing(monkeypatch):
    queued = []
    code, body, saved = _create(monkeypatch, {
        "template": "tm_fivebyseven", "company": "Acme", "draft": True,
        "contacts": [{"email": "a@x.com"}], "enroll_newsletter": "CPA Monthly"},
        queued)
    assert code == 200, body
    assert body["status"] == "draft" and body["campaign_id"] == "Acme_Draft"
    assert body["contacts_queued"] == 0 and body["contacts"] == 1
    assert "newsletter_enrollment" in body
    assert queued == [] and saved[0]["status"] == "draft"
    assert saved[0]["aicb_camp_type"] == "tm_fivebyseven"


def test_create_campaign_without_draft_still_launches(monkeypatch):
    queued = []
    code, body, saved = _create(monkeypatch, {
        "template": "tm_fivebyseven", "company": "Acme",
        "contacts": [{"email": "a@x.com"}]}, queued)
    assert code == 200, body
    assert body["contacts_queued"] == 5 and len(queued) == 1
    assert saved[0].get("status") != "draft"
    assert saved[0]["variables"]["CompanyName"] == "Acme"

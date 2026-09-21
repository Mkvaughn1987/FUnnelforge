"""Connector group D (2026-09-21): My Day bulk marks + call briefing, Replies
scan/draft, newsletter issue editing + settings, and the rest of Sales
Assets (Interview Guide, Market Pulse, Create Your Own, edit/AI-revise an
existing PDF). Same door as every connector route; each calls the helper
its page calls."""
import ast
from datetime import date, timedelta
from pathlib import Path

import pytest

import flowdrip_app as fa

_OWNER = "rep@thrivemodal.com"
_ROOT = Path(__file__).resolve().parent.parent

_TOOLS = ("tm_task_done", "tm_replies", "tm_sales_assets", "tm_call_briefing",
          "tm_newsletter_edit", "tm_pdf_edit")

_ROUTES = [  # (method, path, handler)
    ("post", "/api/v1/tm/tasks/done", "api_tm_task_done"),
    ("post", "/api/v1/tm/replies", "api_tm_reply_update"),
    ("get", "/api/v1/tm/sales_assets", "api_tm_sales_assets"),
    ("post", "/api/v1/tm/sales_assets", "api_tm_sales_asset_build"),
    ("post", "/api/v1/tm/tasks/briefing", "api_tm_call_briefing"),
    ("post", "/api/v1/tm/newsletters/edit", "api_tm_newsletter_edit"),
    ("post", "/api/v1/tm/pdfs/edit", "api_tm_pdf_edit"),
]


# ── structure ──────────────────────────────────────────────────────────────

def _tree(rel):
    return ast.parse((_ROOT / rel).read_text(encoding="utf-8"))


def _tool_names():
    out = []
    for n in ast.walk(_tree("mcp_server/dripdrop_mcp.py")):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.decorator_list:
                t = d.func if isinstance(d, ast.Call) else d
                if isinstance(t, ast.Attribute) and t.attr == "tool":
                    out.append(n.name)
    return out


def _client_methods():
    for n in ast.walk(_tree("mcp_server/dripdrop_client.py")):
        if isinstance(n, ast.ClassDef) and n.name == "DripDropClient":
            return {s.name for s in n.body
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return set()


@pytest.mark.parametrize("name", _TOOLS)
def test_every_tool_exists_with_a_client_method(name):
    assert name in _tool_names()
    assert name in _client_methods()


def _app_func(name):
    for n in _tree("flowdrip_app.py").body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_is_registered_gated_and_keyed(method, path, handler):
    node = _app_func(handler)
    assert node is not None, handler
    decs = [ast.unparse(d) for d in node.decorator_list]
    assert f"app.{method}('{path}')" in decs, decs
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    assert "_is_thrivemodal" in names and "_tm_api_owner" in names
    owners = [a.value for a in ast.walk(node) if isinstance(a, ast.Assign)
              for t in a.targets if isinstance(t, ast.Name) and t.id == "owner"]
    assert len(owners) == 1 and ast.unparse(owners[0]) == "_tm_api_owner(request)"


def _src(name):
    return ast.unparse(_app_func(name))


def test_the_pages_call_the_extracted_helpers():
    page = (_ROOT / "flowdrip_app.py").read_text(encoding="utf-8")
    # Replies page Draft Reply, and Create Your Own's outline + fill.
    assert "s._draft_replies[e] = _ai_draft_reply(client, e, bp, cn, nm)" in page
    modal = _src("_render_custom_pdf_modal")
    assert "_custom_pdf_outline(client, p, _ctx)" in modal
    assert "_custom_pdf_build(" in modal and "_custom_pdf_ctx_block(" in modal
    assert "fill_prompt" not in modal


# ── harness ────────────────────────────────────────────────────────────────

def _camp(**kw):
    c = {"name": "Acme Outreach", "_path": "/data/Acme_Outreach.json",
         "status": "active", "contacts": [],
         "emails": [{"name": "Step 1", "subject": "Hi", "body": "Hello",
                     "step_type": "email_auto"}]}
    c.update(kw)
    return c


def _nl(**kw):
    c = {"name": "Freight Notes", "_path": "/data/Freight_Notes.json",
         "status": "active", "contacts": [], "evergreen_only": True,
         "market_analysis": True, "newsletter_spotlight_count": 3,
         "emails": [{"name": "Oct", "fixed_date": "2026-10-05",
                     "subject": "Oct issue", "body": "<p>October</p>"},
                    {"name": "Nov", "fixed_date": "2026-11-05",
                     "subject": "Nov issue", "body": "<p>November</p>"},
                    {"name": "Dec", "fixed_date": "2026-12-05",
                     "subject": "", "body": ""}]}
    c.update(kw)
    return c


@pytest.fixture
def api(tmp_path, monkeypatch):
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "sk-test")
    camps = [_camp(), _nl()]
    saved = []
    monkeypatch.setattr(fa, "load_campaigns", lambda: camps)
    monkeypatch.setattr(fa, "save_campaign", lambda c: saved.append(c))
    monkeypatch.setattr(fa, "_is_evergreen", lambda c: bool(c.get("evergreen_only")))
    pdfs = tmp_path / "PDFs"
    pdfs.mkdir()
    monkeypatch.setattr(fa, "_user_pdf_dir", lambda: pdfs)
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    app = FastAPI()
    for method, path, handler in _ROUTES:
        getattr(app, method)(path)(getattr(fa, handler))
    client = TestClient(app)
    key = fa._mint_api_key(_OWNER)

    def call(method, path, body=None, params=None, auth=True):
        h = {"X-API-Key": key} if auth else {}
        if method == "get":
            return client.get(path, params=params or {}, headers=h)
        return client.post(path, json=body or {}, headers=h)
    return {"call": call, "camps": camps, "saved": saved, "tmp": tmp_path,
            "pdfs": pdfs}


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_needs_a_key(api, method, path, handler):
    assert api["call"](method, path, auth=False).status_code == 401


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_is_404_on_arena(api, monkeypatch, method, path, handler):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    assert api["call"](method, path).status_code == 404


# ── My Day: bulk marks ─────────────────────────────────────────────────────

def _t(tid, channel, overdue=False, seq="Acme Outreach"):
    return {"id": tid, "channel": channel, "overdue": overdue, "sequence": seq,
            "camp_path": f"/data/{seq.replace(' ', '_')}.json"}


_TASKS = [_t("c1", "call"), _t("l1", "li"), _t("k1", "task"),
          _t("c0", "call", overdue=True), _t("l0", "li", overdue=True),
          _t("x1", "li", seq="Other Camp")]


@pytest.fixture
def outcomes(monkeypatch):
    store = {}
    monkeypatch.setattr(fa, "build_drip_tasks", lambda d=None: [dict(t) for t in _TASKS])
    monkeypatch.setattr(fa, "load_outcomes", lambda: dict(store))

    def _save(o):
        store.clear()
        store.update(o)
    monkeypatch.setattr(fa, "save_outcomes", _save)
    return store


def test_bulk_result_matches_the_page():
    assert fa._tm_bulk_task_result("call") == "vm"
    assert fa._tm_bulk_task_result("li") == "connected"
    assert fa._tm_bulk_task_result("task") == "done"


def test_mark_all_overdue_uses_channel_results(api, outcomes):
    r = api["call"]("post", "/api/v1/tm/tasks/done", {"all_overdue": True})
    assert r.status_code == 200, r.text
    assert sorted(r.json()["task_ids"]) == ["c0", "l0"]
    assert outcomes["c0"]["result"] == "vm" and outcomes["l0"]["result"] == "connected"
    assert outcomes["c0"]["date"] == date.today().isoformat()
    assert "c1" not in outcomes


def test_all_linkedin_done_for_one_campaign(api, outcomes):
    r = api["call"]("post", "/api/v1/tm/tasks/done",
                    {"campaign": "Acme_Outreach", "channel": "li"})
    assert r.json()["task_ids"] == ["l1"]  # not the overdue one, not Other Camp
    assert outcomes == {"l1": {"result": "connected",
                               "date": date.today().isoformat()}}


def test_mark_all_for_a_campaign_skips_already_marked(api, outcomes):
    outcomes["k1"] = {"result": "done", "date": "2026-01-01"}
    r = api["call"]("post", "/api/v1/tm/tasks/done", {"campaign": "Acme Outreach"})
    assert sorted(r.json()["task_ids"]) == ["c1", "l1"]
    assert outcomes["k1"]["date"] == "2026-01-01"


def test_bulk_honours_an_explicit_result(api, outcomes):
    api["call"]("post", "/api/v1/tm/tasks/done",
                {"all_overdue": True, "result": "skipped"})
    assert {outcomes["c0"]["result"], outcomes["l0"]["result"]} == {"skipped"}


def test_several_task_ids_and_unknown_ones(api, outcomes):
    r = api["call"]("post", "/api/v1/tm/tasks/done",
                    {"task_ids": ["c1", "k1", "nope"], "result": "vm"})
    assert r.status_code == 200
    assert r.json()["marked"] == 2 and r.json()["unknown"] == ["nope"]
    r = api["call"]("post", "/api/v1/tm/tasks/done",
                    {"task_ids": ["c1", "k1"], "undo": True})
    assert sorted(r.json()["undone"]) == ["c1", "k1"] and outcomes == {}


def test_bulk_filters_are_validated(api, outcomes):
    c = api["call"]
    assert c("post", "/api/v1/tm/tasks/done", {}).status_code == 400
    assert c("post", "/api/v1/tm/tasks/done",
             {"task_id": "c1", "all_overdue": True}).status_code == 400
    assert c("post", "/api/v1/tm/tasks/done", {"channel": "fax"}).status_code == 400
    assert c("post", "/api/v1/tm/tasks/done",
             {"all_overdue": True, "undo": True}).status_code == 400
    assert outcomes == {}


def test_single_task_still_answers_as_before(api, outcomes):
    r = api["call"]("post", "/api/v1/tm/tasks/done", {"task_id": "c1"})
    assert r.json() == {"task_id": "c1", "result": "done"}


# ── My Day: call briefing ──────────────────────────────────────────────────

def test_briefing_returns_the_cached_one_without_ai(api, monkeypatch):
    api["camps"][0]["call_briefing"] = {
        "_schema_version": fa._CALL_BRIEFING_SCHEMA_VERSION,
        "company_name": "Acme", "talking_points": ["a"]}
    monkeypatch.setattr(fa, "_generate_call_briefing_for_campaign",
                        lambda *a, **k: pytest.fail("no AI for a cached one"))
    r = api["call"]("post", "/api/v1/tm/tasks/briefing",
                    {"campaign_id": "Acme_Outreach"})
    assert r.status_code == 200, r.text
    assert r.json()["briefing"] == {"company_name": "Acme", "talking_points": ["a"]}


def test_briefing_refresh_from_a_task(api, monkeypatch):
    api["camps"][0]["call_briefing"] = {"_schema_version": 1, "hq": "old"}
    monkeypatch.setattr(fa, "build_drip_tasks", lambda d=None: [dict(_TASKS[0])])
    seen = {}

    def _gen(camp, force_refresh=False):
        seen["cached_then"] = "call_briefing" in camp
        seen["force"] = force_refresh
        return {"_schema_version": 6, "hq": "Denver, CO"}
    monkeypatch.setattr(fa, "_generate_call_briefing_for_campaign", _gen)
    r = api["call"]("post", "/api/v1/tm/tasks/briefing",
                    {"task_id": "c1", "refresh": True})
    assert r.status_code == 200, r.text
    assert r.json()["briefing"] == {"hq": "Denver, CO"}
    assert seen == {"cached_then": False, "force": True}
    assert r.json()["campaign"] == "Acme Outreach"


def test_briefing_needs_a_real_target(api, monkeypatch):
    monkeypatch.setattr(fa, "build_drip_tasks", lambda d=None: [])
    c = api["call"]
    assert c("post", "/api/v1/tm/tasks/briefing", {}).status_code == 400
    assert c("post", "/api/v1/tm/tasks/briefing", {"task_id": "zz"}).status_code == 404
    assert c("post", "/api/v1/tm/tasks/briefing",
             {"campaign_id": "Nope"}).status_code == 404


# ── Replies: scan + draft ──────────────────────────────────────────────────

def test_scan_runs_the_pages_scan_for_this_user(api, monkeypatch):
    got = []
    monkeypatch.setattr(fa, "_SERVER_MODE", True)
    monkeypatch.setattr(fa, "_one_user_reply_scan",
                        lambda e, force_full=False: got.append((e, force_full)) or 2)
    monkeypatch.setattr(fa, "load_responded", lambda: [{"email": "a@x.com"}])
    r = api["call"]("post", "/api/v1/tm/replies", {"action": "scan"})
    assert r.status_code == 200, r.text
    assert got == [(_OWNER, True)]
    assert r.json()["new_replies"] == 2 and r.json()["awaiting_follow_up"] == 1


def test_draft_suggests_a_reply_and_sends_nothing(api, monkeypatch):
    rows = [{"email": "a@x.com", "name": "Ann", "campaign": "Acme Outreach",
             "subject": "Quick question", "reply_body": "Tell me more"},
            {"email": "b@x.com", "reply_body": ""}]
    monkeypatch.setattr(fa, "load_responded", lambda: [dict(r) for r in rows])
    monkeypatch.setattr(fa, "save_responded",
                        lambda r: pytest.fail("a draft changes nothing"))
    seen = {}
    monkeypatch.setattr(fa, "_ai_draft_reply",
                        lambda client, e, bp, cn, nm: seen.update(
                            e=e, bp=bp, cn=cn, nm=nm) or "Happy to talk.")
    c = api["call"]
    r = c("post", "/api/v1/tm/replies", {"action": "draft", "email": "A@x.com"})
    assert r.status_code == 200, r.text
    assert r.json()["draft"] == "Happy to talk."
    assert r.json()["reply_subject"] == "Re: Quick question"
    assert seen == {"e": "a@x.com", "bp": "Tell me more",
                    "cn": "Acme Outreach", "nm": "Ann"}
    assert c("post", "/api/v1/tm/replies",
             {"action": "draft", "email": "b@x.com"}).status_code == 400
    assert c("post", "/api/v1/tm/replies",
             {"action": "draft", "email": "z@x.com"}).status_code == 404
    assert c("post", "/api/v1/tm/replies", {"action": "send"}).status_code == 400


# ── Newsletters: issues, edit, settings ───────────────────────────────────

@pytest.fixture
def nl(api, monkeypatch):
    monkeypatch.setattr(fa, "_find_next_evergreen_step", lambda c: 1)
    patched = []
    monkeypatch.setattr(fa, "_tm_patch_pending",
                        lambda *a: patched.append(a) or 4)
    api["patched"] = patched
    return api


def test_issues_list_marks_sent_and_editable(nl):
    r = nl["call"]("post", "/api/v1/tm/newsletters/edit",
                   {"campaign_id": "Freight_Notes"})
    assert r.status_code == 200, r.text
    rows = r.json()["issues"]
    assert [(x["issue"], x["sent"], x["editable"], x["written"]) for x in rows] == [
        (1, True, False, True), (2, False, True, True), (3, False, True, False)]
    assert r.json()["next_issue"] == 2


def test_get_issue_defaults_to_the_next_one(nl):
    r = nl["call"]("post", "/api/v1/tm/newsletters/edit",
                   {"campaign_id": "Freight Notes", "action": "get_issue"})
    assert r.json()["issue"] == 2 and r.json()["body_html"] == "<p>November</p>"
    assert r.json()["text"] == "November"


def test_edit_issue_saves_like_the_page_and_repoints_the_queue(nl):
    r = nl["call"]("post", "/api/v1/tm/newsletters/edit", {
        "campaign_id": "Freight_Notes", "action": "edit_issue", "issue": 2,
        "subject": " New Nov ", "body": "<p>Edited</p>"})
    assert r.status_code == 200, r.text
    st = nl["saved"][-1]["emails"][1]
    assert st["subject"] == "New Nov" and st["body"] == "<p>Edited</p>"
    assert st["confirmed"] is True and st["auto_confirmed"] is False
    # Named step: matched by name only, as the page does.
    assert nl["patched"] == [("Freight Notes", "Nov", "", "New Nov", "<p>Edited</p>")]
    assert r.json()["queued_emails_updated"] == 4


def test_edit_issue_refuses_sent_blank_and_empty(nl):
    c = nl["call"]
    base = {"campaign_id": "Freight_Notes", "action": "edit_issue"}
    assert c("post", "/api/v1/tm/newsletters/edit",
             {**base, "issue": 1, "subject": "x"}).status_code == 409
    assert c("post", "/api/v1/tm/newsletters/edit",
             {**base, "issue": 2}).status_code == 400
    assert c("post", "/api/v1/tm/newsletters/edit",
             {**base, "issue": 2, "body": "  "}).status_code == 400
    assert c("post", "/api/v1/tm/newsletters/edit",
             {**base, "issue": 9, "subject": "x"}).status_code == 400
    assert c("post", "/api/v1/tm/newsletters/edit",
             {"campaign_id": "Acme_Outreach"}).status_code == 404
    assert nl["saved"] == []


def test_settings_save_and_rewrite_the_next_issue(nl, monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    ran = []
    monkeypatch.setattr(fa, "_run_as_user",
                        lambda e, fn, name=None: ran.append((e, fn)))
    c = nl["call"]
    r = c("post", "/api/v1/tm/newsletters/edit",
          {"campaign_id": "Freight_Notes", "action": "settings"})
    assert r.json()["settings"] == {"city_life": True, "profiles": True, "topic": ""}
    assert nl["saved"] == []
    r = c("post", "/api/v1/tm/newsletters/edit", {
        "campaign_id": "Freight_Notes", "action": "settings",
        "profiles": False, "topic": "Hiring offshore AP clerks",
        "city_life": False})
    assert r.status_code == 200, r.text
    camp = nl["saved"][-1]
    assert camp["newsletter_spotlight_count"] == 0
    assert camp["newsletter_topic"] == "Hiring offshore AP clerks"
    assert camp["newsletter_show_city_life"] is False
    assert [e for e, _ in ran] == [_OWNER]
    # The background rewrite updates the step and the queued emails.
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step",
                        lambda camp, i: ("Fresh", "<p>fresh</p>"))
    ran[0][1]()
    assert camp["emails"][1]["body"] == "<p>fresh</p>"
    assert camp["emails"][1]["confirmed"] is False
    assert nl["patched"][-1] == ("Freight Notes", "Nov", "Nov issue",
                                 "Fresh", "<p>fresh</p>")
    assert c("post", "/api/v1/tm/newsletters/edit", {
        "campaign_id": "Freight_Notes", "action": "settings",
        "spotlights_per_issue": 6}).status_code == 400


def test_settings_on_a_recruiting_workspace(nl, monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", False)
    monkeypatch.setattr(fa, "_run_as_user", lambda e, fn, name=None: None)
    c = nl["call"]
    assert c("post", "/api/v1/tm/newsletters/edit", {
        "campaign_id": "Freight_Notes", "action": "settings",
        "spotlights_per_issue": 4}).status_code == 400
    r = c("post", "/api/v1/tm/newsletters/edit", {
        "campaign_id": "Freight_Notes", "action": "settings",
        "spotlights_per_issue": 6, "spotlight_guidance": " Senior PMs "})
    assert r.json()["settings"]["spotlights_per_issue"] == 6
    assert nl["saved"][-1]["newsletter_spotlight_recommendations"] == "Senior PMs"


# ── Sales Assets: more kinds, custom ───────────────────────────────────────

def test_sales_assets_lists_every_page_kind(api):
    kinds = [k["kind"] for k in api["call"]("get", "/api/v1/tm/sales_assets").json()["kinds"]]
    assert kinds == ["tm_role_blueprint", "tm_cost_compare", "tm_how_it_works",
                     "interview_guide", "market_pulse", "custom"]


def test_interview_guide_builds_through_the_page_builder(api, monkeypatch):
    seen = {}

    def _build(kind, company, role, location, industry="", client=None):
        seen.update(kind=kind, company=company, role=role, location=location)
        (api["pdfs"] / "Interview_Guide_Acme.pdf").write_bytes(b"%PDF")
        return "Interview_Guide_Acme.pdf"
    monkeypatch.setattr(fa, "_tm_build_sales_asset", _build)
    r = api["call"]("post", "/api/v1/tm/sales_assets", {
        "kind": "interview_guide", "company": "Acme", "role": "AP Clerk",
        "location": "Nationwide"})
    assert r.status_code == 200, r.text
    assert r.json()["path"] == "/pdfs/Interview_Guide_Acme.pdf"
    assert r.json()["kind"] == "interview_guide"
    assert seen == {"kind": "interview_guide", "company": "Acme",
                    "role": "AP Clerk", "location": "Nationwide"}


def test_custom_pdf_outlines_then_fills(api, monkeypatch):
    calls = []
    monkeypatch.setattr(fa, "_custom_pdf_outline",
                        lambda client, d, ctx: calls.append(("outline", d, ctx))
                        or {"title": "T", "sections": []})

    def _fill(client, outline, d, ctx, pdf_dir, cfg):
        calls.append(("fill", outline["title"]))
        (Path(pdf_dir) / "T.pdf").write_bytes(b"%PDF")
        return "T.pdf"
    monkeypatch.setattr(fa, "_custom_pdf_build", _fill)
    c = api["call"]
    assert c("post", "/api/v1/tm/sales_assets",
             {"kind": "custom", "description": "short"}).status_code == 400
    r = c("post", "/api/v1/tm/sales_assets", {
        "kind": "custom", "role": "AP Clerk",
        "description": "A one-pager on month-end close support"})
    assert r.status_code == 200, r.text
    assert r.json()["path"] == "/pdfs/T.pdf" and r.json()["kind"] == "custom"
    assert calls[0][0] == "outline" and "Positions hiring for: AP Clerk" in calls[0][2]
    assert calls[1] == ("fill", "T")


def test_custom_pdf_reports_an_unreadable_outline(api, monkeypatch):
    monkeypatch.setattr(fa, "_custom_pdf_outline",
                        lambda *a: {"error": "Couldn't parse outline."})
    monkeypatch.setattr(fa, "_custom_pdf_build",
                        lambda *a: pytest.fail("no fill without an outline"))
    r = api["call"]("post", "/api/v1/tm/sales_assets", {
        "kind": "custom", "description": "A one-pager on month-end close"})
    assert r.status_code == 502


def test_unknown_kind_lists_the_choices(api):
    r = api["call"]("post", "/api/v1/tm/sales_assets", {"kind": "brochure", "role": "x"})
    assert r.status_code == 400 and len(r.json()["choices"]) == 6


# ── PDF editor ─────────────────────────────────────────────────────────────

def _sidecar(api, name="Blueprint_Acme.pdf"):
    p = api["pdfs"] / name
    p.write_bytes(b"%PDF")
    fa._save_pdf_sidecar(str(p), {
        "title": "Blueprint", "badge": "ROLE", "intro": "Hi", "cta": "Call us",
        "sections": [{"heading": "H", "type": "paragraph", "items": ["x"]}],
        "date": "September 21, 2026", "prepared_by": "Mike",
        "logo_path": "/srv/secret/logo.png"})
    return name


def test_pdf_get_hides_server_paths(api):
    name = _sidecar(api)
    r = api["call"]("post", "/api/v1/tm/pdfs/edit", {"file": f"/pdfs/{name}"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["title"] == "Blueprint"
    assert "logo_path" not in r.text and "/srv/" not in r.text
    assert r.json()["path"] == f"/pdfs/{name}"


def test_pdf_update_rerenders_keeping_what_the_editor_does_not_own(api, monkeypatch):
    name = _sidecar(api)
    got = {}
    monkeypatch.setattr(fa, "_rebuild_pdf_from_sidecar_data",
                        lambda f, d: got.update(f=f, d=d) or True)
    r = api["call"]("post", "/api/v1/tm/pdfs/edit", {
        "file": name, "action": "update", "data": {"intro": "New intro"}})
    assert r.status_code == 200, r.text
    assert got["f"] == name and got["d"]["intro"] == "New intro"
    assert got["d"]["logo_path"] == "/srv/secret/logo.png"
    assert got["d"]["title"] == "Blueprint"
    assert api["call"]("post", "/api/v1/tm/pdfs/edit", {
        "file": name, "action": "update", "data": {"colour": "x"}}).status_code == 400


def test_pdf_revise_goes_through_the_editors_ai(api, monkeypatch):
    name = _sidecar(api)
    monkeypatch.setattr(fa, "_ai_revise_pdf_data",
                        lambda client, d, instr: {**d, "intro": instr.upper(),
                                                  "logo_path": "/evil"})
    got = {}
    monkeypatch.setattr(fa, "_rebuild_pdf_from_sidecar_data",
                        lambda f, d: got.update(d=d) or True)
    r = api["call"]("post", "/api/v1/tm/pdfs/edit", {
        "file": name, "action": "revise", "instruction": "shorter"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["intro"] == "SHORTER"
    assert got["d"]["logo_path"] == "/srv/secret/logo.png"
    assert api["call"]("post", "/api/v1/tm/pdfs/edit", {
        "file": name, "action": "revise"}).status_code == 400


def test_pdf_edit_refuses_other_paths_and_uneditable_files(api):
    c = api["call"]
    for bad in ("../x.pdf", "a/b.pdf", "..\\x.pdf", "notes.txt", "", "Missing.pdf"):
        assert c("post", "/api/v1/tm/pdfs/edit", {"file": bad}).status_code == 404, bad
    (api["pdfs"] / "Upload.pdf").write_bytes(b"%PDF")
    assert c("post", "/api/v1/tm/pdfs/edit", {"file": "Upload.pdf"}).status_code == 409


# ── the connector side ─────────────────────────────────────────────────────

def test_pdf_edit_tool_links_the_file(monkeypatch):
    mcp = pytest.importorskip("mcp_server.dripdrop_mcp")
    monkeypatch.setattr(mcp, "_APP_ORIGIN", "https://app.example.com")
    out = mcp._link_pdfs({"file": "A.pdf", "path": "/pdfs/A.pdf", "data": {}})
    assert out["url"] == "https://app.example.com/pdfs/A.pdf"

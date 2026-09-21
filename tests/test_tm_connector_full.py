"""The connector reaches every page of the ThriveModal app (2026-09-21):
My Day, Replies, Contacts, campaign contacts + lifecycle, send preview,
Newsletters, Sales Assets, Saved Prompts, Clients, Settings, Do Not Contact.
Each route calls the helper its page calls, behind the same key + gate door."""
import ast
import json
from datetime import date
from pathlib import Path

import pytest

import flowdrip_app as fa

_OWNER = "rep@thrivemodal.com"
_ROOT = Path(__file__).resolve().parent.parent

_NEW_TOOLS = ("tm_my_day", "tm_task_done", "tm_replies", "tm_contacts",
              "tm_campaign_contacts", "tm_campaign_action", "tm_send_preview",
              "tm_newsletters", "tm_newsletter_create", "tm_newsletter_issue",
              "tm_sales_assets", "tm_saved_prompts", "tm_clients",
              "tm_settings", "tm_dnc")

_ROUTES = [  # (method, path, handler)
    ("get", "/api/v1/tm/tasks", "api_tm_tasks"),
    ("post", "/api/v1/tm/tasks/done", "api_tm_task_done"),
    ("get", "/api/v1/tm/replies", "api_tm_replies"),
    ("post", "/api/v1/tm/replies", "api_tm_reply_update"),
    ("get", "/api/v1/tm/contacts/search", "api_tm_contacts_search"),
    ("post", "/api/v1/tm/campaigns/contacts", "api_tm_campaign_contacts"),
    ("post", "/api/v1/tm/campaigns/action", "api_tm_campaign_action"),
    ("post", "/api/v1/tm/send_preview", "api_tm_send_preview"),
    ("get", "/api/v1/tm/newsletters", "api_tm_newsletters"),
    ("post", "/api/v1/tm/newsletters", "api_tm_newsletter_create"),
    ("post", "/api/v1/tm/newsletters/issue", "api_tm_newsletter_issue"),
    ("get", "/api/v1/tm/sales_assets", "api_tm_sales_assets"),
    ("post", "/api/v1/tm/sales_assets", "api_tm_sales_asset_build"),
    ("get", "/api/v1/tm/saved_prompts", "api_tm_saved_prompts"),
    ("get", "/api/v1/tm/clients", "api_tm_clients"),
    ("post", "/api/v1/tm/clients", "api_tm_client_update"),
    ("get", "/api/v1/tm/settings", "api_tm_settings"),
    ("post", "/api/v1/tm/settings", "api_tm_settings_update"),
    ("get", "/api/v1/tm/dnc", "api_tm_dnc"),
    ("post", "/api/v1/tm/dnc", "api_tm_dnc_update"),
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


@pytest.mark.parametrize("name", _NEW_TOOLS)
def test_every_new_tool_exists_with_a_client_method(name):
    assert name in _tool_names()
    assert name in _client_methods()


def _app_func(name):
    for n in _tree("flowdrip_app.py").body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_new_route_is_registered_gated_and_keyed(method, path, handler):
    node = _app_func(handler)
    assert node is not None, handler
    decs = [ast.unparse(d) for d in node.decorator_list]
    assert f"app.{method}('{path}')" in decs, decs
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    assert "_is_thrivemodal" in names and "_tm_api_owner" in names
    owners = [a.value for a in ast.walk(node) if isinstance(a, ast.Assign)
              for t in a.targets if isinstance(t, ast.Name) and t.id == "owner"]
    assert len(owners) == 1 and ast.unparse(owners[0]) == "_tm_api_owner(request)"


# ── harness ────────────────────────────────────────────────────────────────

def _camp(**kw):
    c = {"name": "Acme Outreach", "_path": "/data/Acme_Outreach.json",
         "status": "active", "contacts": [],
         "emails": [{"name": "Step 1", "subject": "Hi {FirstName}",
                     "body": "Hello {FirstName} at {Company}",
                     "step_type": "email_auto", "attachments": ["a.pdf"]},
                    {"name": "Step 2", "subject": "", "body": "",
                     "step_type": "call"}]}
    c.update(kw)
    return c


@pytest.fixture
def api(tmp_path, monkeypatch):
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    camps = [_camp()]
    saved = []
    monkeypatch.setattr(fa, "load_campaigns", lambda: camps)
    monkeypatch.setattr(fa, "save_campaign", lambda c: saved.append(c))
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
    return {"call": call, "camps": camps, "saved": saved, "tmp": tmp_path}


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_needs_a_key(api, method, path, handler):
    assert api["call"](method, path, auth=False).status_code == 401


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_is_404_on_arena(api, monkeypatch, method, path, handler):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    assert api["call"](method, path).status_code == 404


# ── My Day ─────────────────────────────────────────────────────────────────

_TASK = {"id": "/data/Acme_Outreach.json::bob@x.com::2", "channel": "call",
         "name": "Bob", "company": "X", "email": "bob@x.com", "touch": 2,
         "sequence": "Acme Outreach", "camp_path": "/data/Acme_Outreach.json",
         "phones": [], "overdue": False}


def test_my_day_lists_tasks_without_server_paths(api, monkeypatch):
    monkeypatch.setattr(fa, "build_drip_tasks", lambda d=None: [dict(_TASK)])
    r = api["call"]("get", "/api/v1/tm/tasks")
    assert r.status_code == 200
    t = r.json()["tasks"][0]
    assert t["campaign"] == "Acme Outreach" and "camp_path" not in t
    assert r.json()["by_channel"]["call"] == 1


def test_my_day_rejects_a_bad_date(api):
    assert api["call"]("get", "/api/v1/tm/tasks", params={"date": "soon"}).status_code == 400


def test_task_done_writes_the_outcome_the_page_writes(api, monkeypatch):
    store = {}
    monkeypatch.setattr(fa, "build_drip_tasks", lambda d=None: [dict(_TASK)])
    monkeypatch.setattr(fa, "load_outcomes", lambda: dict(store))
    monkeypatch.setattr(fa, "save_outcomes", lambda o: store.update(o) or
                        [store.pop(k) for k in list(store) if k not in o])
    r = api["call"]("post", "/api/v1/tm/tasks/done",
                    {"task_id": _TASK["id"], "result": "vm"})
    assert r.status_code == 200
    assert store[_TASK["id"]] == {"result": "vm", "date": date.today().isoformat()}
    r = api["call"]("post", "/api/v1/tm/tasks/done", {"task_id": _TASK["id"], "undo": True})
    assert r.status_code == 200 and _TASK["id"] not in store


def test_task_done_refuses_unknown_ids_and_results(api, monkeypatch):
    monkeypatch.setattr(fa, "build_drip_tasks", lambda d=None: [dict(_TASK)])
    monkeypatch.setattr(fa, "load_outcomes", lambda: {})
    c = api["call"]
    assert c("post", "/api/v1/tm/tasks/done", {"task_id": "nope"}).status_code == 404
    assert c("post", "/api/v1/tm/tasks/done",
             {"task_id": _TASK["id"], "result": "maybe"}).status_code == 400


# ── Replies ────────────────────────────────────────────────────────────────

def test_replies_follow_up_and_dismiss(api, monkeypatch):
    rows = [{"email": "a@x.com", "followed_up": False},
            {"email": "b@x.com", "followed_up": False}]
    saved = []
    monkeypatch.setattr(fa, "load_responded", lambda: [dict(r) for r in rows])
    monkeypatch.setattr(fa, "save_responded", lambda r: saved.append(r))
    c = api["call"]
    assert c("get", "/api/v1/tm/replies").json()["awaiting_follow_up"] == 2
    assert c("post", "/api/v1/tm/replies",
             {"email": "A@x.com", "action": "followed_up"}).status_code == 200
    assert saved[-1][0]["followed_up"] is True
    assert c("post", "/api/v1/tm/replies",
             {"email": "b@x.com", "action": "dismiss"}).status_code == 200
    assert [r["email"] for r in saved[-1]] == ["a@x.com"]
    assert c("post", "/api/v1/tm/replies",
             {"email": "z@x.com", "action": "dismiss"}).status_code == 404


# ── Contacts + campaign contacts ───────────────────────────────────────────

def test_contact_search_filters_one_list(api, monkeypatch):
    monkeypatch.setattr(fa, "list_saved_contact_lists", lambda: {"CPAs": "p"})
    monkeypatch.setattr(fa, "_tm_zi_contacts_on_file", lambda n="": [
        {"email": "a@x.com", "first_name": "Ann", "company": "Acme"},
        {"email": "b@y.com", "first_name": "Bo", "company": "Beta"}])
    r = api["call"]("get", "/api/v1/tm/contacts/search", params={"list": "CPAs", "q": "acme"})
    assert r.json()["matched"] == 1 and r.json()["lists"] == ["CPAs"]
    r = api["call"]("get", "/api/v1/tm/contacts/search", params={"list": "Nope"})
    assert r.status_code == 404


def test_adding_contacts_goes_through_the_pages_helper(api, monkeypatch):
    got = []
    monkeypatch.setattr(fa, "add_contacts_to_campaign",
                        lambda camp, cs: got.extend(cs) or len(cs) - 1)
    monkeypatch.setattr(fa, "is_on_dnc", lambda e: e == "dnc@x.com")
    monkeypatch.setattr(fa, "_is_evergreen", lambda c: False)
    r = api["call"]("post", "/api/v1/tm/campaigns/contacts", {
        "campaign_id": "Acme_Outreach",
        "contacts": [{"Email": "Ann@X.com", "FirstName": "Ann"},
                     {"email": "dnc@x.com"}, {"email": "not-an-email"}]})
    assert r.status_code == 200, r.text
    assert [c["email"] for c in got] == ["ann@x.com", "dnc@x.com"]
    assert got[0]["first_name"] == "Ann"
    body = r.json()
    assert body["added"] == 1 and body["invalid_email"] == 1
    assert body["on_do_not_contact_not_queued"] == 1


def test_adding_to_a_newsletter_enrols_each_contact(api, monkeypatch):
    monkeypatch.setattr(fa, "_is_evergreen", lambda c: True)
    monkeypatch.setattr(fa, "is_on_dnc", lambda e: False)
    monkeypatch.setattr(fa, "enroll_contact_in_evergreen",
                        lambda c, camp: "enrolled" if "a@" in c["email"] else "skipped_dnc")
    r = api["call"]("post", "/api/v1/tm/campaigns/contacts", {
        "campaign_id": "Acme Outreach",
        "contacts": [{"email": "a@x.com"}, {"email": "b@x.com"}]})
    assert r.json()["added"] == 1 and r.json()["statuses"]["skipped_dnc"] == 1


def test_a_cancelled_campaign_takes_no_contacts(api):
    api["camps"][0]["status"] = "cancelled"
    r = api["call"]("post", "/api/v1/tm/campaigns/contacts",
                    {"campaign_id": "Acme_Outreach", "contacts": [{"email": "a@x.com"}]})
    assert r.status_code == 409


def test_removing_a_contact(api, monkeypatch):
    monkeypatch.setattr(fa, "remove_contact_from_campaign",
                        lambda camp, e: 1 if e == "a@x.com" else 0)
    c = api["call"]
    assert c("post", "/api/v1/tm/campaigns/contacts", {
        "campaign_id": "Acme_Outreach", "action": "remove",
        "email": "a@x.com"}).status_code == 200
    assert c("post", "/api/v1/tm/campaigns/contacts", {
        "campaign_id": "Acme_Outreach", "action": "remove",
        "email": "b@x.com"}).status_code == 404


# ── lifecycle + preview ────────────────────────────────────────────────────

def test_cancel_stops_pending_and_marks_the_campaign(api, monkeypatch):
    monkeypatch.setattr(fa, "cancel_campaign_queue", lambda n: 7)
    r = api["call"]("post", "/api/v1/tm/campaigns/action",
                    {"campaign_id": "Acme_Outreach", "action": "cancel"})
    assert r.json()["cancelled_emails"] == 7
    assert api["saved"][-1]["status"] == "cancelled"


def test_delete_needs_confirm(api, monkeypatch):
    gone = []
    monkeypatch.setattr(fa, "delete_campaign", lambda p: gone.append(p))
    c = api["call"]
    assert c("post", "/api/v1/tm/campaigns/action",
             {"campaign_id": "Acme_Outreach", "action": "delete"}).status_code == 400
    assert gone == []
    assert c("post", "/api/v1/tm/campaigns/action", {
        "campaign_id": "Acme_Outreach", "action": "delete",
        "confirm": True}).status_code == 200
    assert gone == ["/data/Acme_Outreach.json"]


def test_send_preview_merges_the_users_own_name(api, monkeypatch):
    sent = {}
    monkeypatch.setattr(fa, "_preview_self_contact",
                        lambda s=None: {"first_name": "Mike", "company": "TM"})
    monkeypatch.setattr(fa, "load_config", lambda: {})
    monkeypatch.setattr(fa, "_send_email_universal",
                        lambda **kw: sent.update(kw) or (True, ""))
    r = api["call"]("post", "/api/v1/tm/send_preview",
                    {"campaign_id": "Acme_Outreach", "step": 1})
    assert r.status_code == 200, r.text
    assert sent["to"] == _OWNER and sent["is_preview"] is True
    assert sent["subject"] == "Hi Mike" and sent["html_body"] == "Hello Mike at TM"
    assert sent["attachments"][0].endswith("a.pdf")
    r = api["call"]("post", "/api/v1/tm/send_preview",
                    {"campaign_id": "Acme_Outreach", "step": 2})
    assert r.status_code == 400


def test_send_preview_reports_a_failed_send(api, monkeypatch):
    monkeypatch.setattr(fa, "_preview_self_contact", lambda s=None: {})
    monkeypatch.setattr(fa, "load_config", lambda: {})
    monkeypatch.setattr(fa, "_send_email_universal", lambda **kw: (False, "403"))
    r = api["call"]("post", "/api/v1/tm/send_preview", {"campaign_id": "Acme_Outreach"})
    assert r.status_code == 502 and "403" in r.json()["error"]


# ── Newsletters ────────────────────────────────────────────────────────────

def test_newsletter_dict_is_one_issue_a_month():
    c = fa._nl_campaign_dict("CPA Monthly", "accounting", "Accounting & CPA Firms",
                             "", "Nationwide", date(2026, 10, 5), count=3)
    assert [e["fixed_date"] for e in c["emails"]] == [
        "2026-10-05", "2026-11-05", "2026-12-05"]
    assert c["market_sector"] == "Accounting & CPA Firms"
    assert c["evergreen_only"] and c["market_analysis"] and c["contacts"] == []
    assert fa._nl_campaign_dict("x", "k", "Label", "Niche", "r",
                                date(2026, 1, 1))["market_sector"] == "Niche"


def test_the_page_builds_newsletters_through_the_shared_helper():
    src = ast.unparse(_app_func("_create_newsletter_dialog"))
    assert "_nl_campaign_dict(" in src and "evergreen_only=True" not in src


def test_create_newsletter_saves_and_writes_the_first_issue(api, monkeypatch):
    ran = []
    monkeypatch.setattr(fa, "_run_as_user", lambda e, fn, name=None: ran.append(e))
    r = api["call"]("post", "/api/v1/tm/newsletters",
                    {"name": "Freight Notes", "sector": "logistics", "count": 2})
    assert r.status_code == 200, r.text
    assert api["saved"][-1]["name"] == "Freight Notes"
    assert api["saved"][-1]["market_region"] == "Nationwide"
    assert ran == [_OWNER]
    c = api["call"]
    assert c("post", "/api/v1/tm/newsletters",
             {"name": "Acme Outreach", "sector": "logistics"}).status_code == 409
    assert c("post", "/api/v1/tm/newsletters",
             {"name": "N", "sector": "space"}).status_code == 400


def test_patch_pending_repoints_that_issues_queued_emails(tmp_path, monkeypatch):
    qp = tmp_path / "q.json"
    qp.write_text(json.dumps([
        {"campaign": "N", "status": "pending", "step_name": "Oct", "subject": "o", "body": "old"},
        {"campaign": "N", "status": "sent", "step_name": "Oct", "subject": "o", "body": "old"},
        {"campaign": "M", "status": "pending", "step_name": "Oct", "subject": "o", "body": "old"},
    ]), encoding="utf-8")
    monkeypatch.setattr(fa, "_user_queue_path", lambda: qp)
    monkeypatch.setattr(fa, "_FUNNELFORGE_OK", False)
    assert fa._tm_patch_pending("N", "Oct", "o", "new s", "new b") == 1
    q = json.loads(qp.read_text(encoding="utf-8"))
    assert q[0]["body"] == "new b" and q[1]["body"] == "old" and q[2]["body"] == "old"


# ── Settings + DNC + Clients ───────────────────────────────────────────────

def test_settings_validate_before_writing(api, monkeypatch):
    sig = api["tmp"] / "signature.txt"
    cfg = {}
    monkeypatch.setattr(fa, "_user_sig_path", lambda: sig)
    monkeypatch.setattr(fa, "load_config", lambda: cfg)
    monkeypatch.setattr(fa, "save_config", lambda c: cfg.update(c))
    c = api["call"]
    assert c("post", "/api/v1/tm/settings", {"timezone": "Mars/Base"}).status_code == 400
    assert c("post", "/api/v1/tm/settings",
             {"profile": {"favourite_colour": "x"}}).status_code == 400
    r = c("post", "/api/v1/tm/settings", {"signature": " Mike\nThriveModal "})
    assert r.json()["updated"] == ["signature"]
    assert sig.read_text(encoding="utf-8") == "Mike\nThriveModal"
    try:  # Windows without the tzdata package knows no zones at all
        from zoneinfo import ZoneInfo
        ZoneInfo("America/Chicago")
    except Exception:
        return
    r = c("post", "/api/v1/tm/settings", {"timezone": "America/Chicago"})
    assert r.json()["updated"] == ["timezone"]
    assert cfg["user_timezone"] == "America/Chicago"


def test_dnc_takes_one_of_email_or_domain(api, monkeypatch):
    calls = []
    monkeypatch.setattr(fa, "add_domain_to_dnc",
                        lambda d, reason="": calls.append(("dom", d)) or 4)
    monkeypatch.setattr(fa, "add_to_dnc",
                        lambda e, reason="", source="": calls.append(("em", e)) or True)
    c = api["call"]
    assert c("post", "/api/v1/tm/dnc", {"action": "add"}).status_code == 400
    assert c("post", "/api/v1/tm/dnc", {"action": "add", "email": "a@x.com",
                                        "domain": "x.com"}).status_code == 400
    r = c("post", "/api/v1/tm/dnc", {"action": "add", "domain": "@Acme.com"})
    assert r.json()["campaign_contacts_stopped"] == 4
    c("post", "/api/v1/tm/dnc", {"action": "add", "email": "B@x.com"})
    assert calls == [("dom", "acme.com"), ("em", "b@x.com")]


def test_clients_add_passes_the_actor(api, monkeypatch):
    seen = {}
    monkeypatch.setattr(fa, "add_client_to_blocklist",
                        lambda d, **kw: seen.update(kw, domain=d) or (True, "ok"))
    r = api["call"]("post", "/api/v1/tm/clients",
                    {"action": "add", "domain": "acme.com", "name": "Acme"})
    assert r.status_code == 200
    assert seen["domain"] == "acme.com" and seen["actor_email"] == _OWNER


# ── the connector side ─────────────────────────────────────────────────────

def test_pdf_paths_become_app_links(monkeypatch):
    mcp = pytest.importorskip("mcp_server.dripdrop_mcp")
    monkeypatch.setattr(mcp, "_APP_ORIGIN", "https://app.example.com")
    one = mcp._link_pdfs({"path": "/pdfs/A.pdf"})
    assert one["url"] == "https://app.example.com/pdfs/A.pdf"
    many = mcp._link_pdfs({"assets": [{"path": "/pdfs/B.pdf"}]})
    assert many["assets"][0]["url"].endswith("/pdfs/B.pdf")

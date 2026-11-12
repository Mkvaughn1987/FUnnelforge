"""DD connector A (2026-11-12): the shared pages, ported from inboxslide's
/api/v1/tm/* to /api/v1/dd/*. Today's Tasks, Replies, Contacts, campaign
contacts / lifecycle / editing, send preview, Newsletters, Outreach
Analytics, Settings, the sending inbox, Do Not Contact, campaign styles,
plus create_campaign's draft mode. Each route is behind the API key and
calls what the DripDrop page's button calls."""
import ast
import asyncio
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

import flowdrip_app as fa

_OWNER = "rep@arena.com"
_ROOT = Path(__file__).resolve().parent.parent

_ROUTES = [  # (method, path, handler)
    ("get", "/api/v1/dd/tasks", "api_dd_tasks"),
    ("post", "/api/v1/dd/tasks/done", "api_dd_task_done"),
    ("post", "/api/v1/dd/tasks/briefing", "api_dd_call_briefing"),
    ("get", "/api/v1/dd/replies", "api_dd_replies"),
    ("post", "/api/v1/dd/replies", "api_dd_reply_update"),
    ("get", "/api/v1/dd/contacts/search", "api_dd_contacts_search"),
    ("post", "/api/v1/dd/contacts", "api_dd_import_contacts"),
    ("post", "/api/v1/dd/contact_lists", "api_dd_contact_list_update"),
    ("post", "/api/v1/dd/campaigns/contacts", "api_dd_campaign_contacts"),
    ("post", "/api/v1/dd/campaigns/action", "api_dd_campaign_action"),
    ("post", "/api/v1/dd/campaigns/edit", "api_dd_campaign_edit"),
    ("post", "/api/v1/dd/send_preview", "api_dd_send_preview"),
    ("get", "/api/v1/dd/newsletters", "api_dd_newsletters"),
    ("post", "/api/v1/dd/newsletters", "api_dd_newsletter_create"),
    ("post", "/api/v1/dd/newsletters/issue", "api_dd_newsletter_issue"),
    ("post", "/api/v1/dd/newsletters/edit", "api_dd_newsletter_edit"),
    ("get", "/api/v1/dd/analytics", "api_dd_analytics"),
    ("get", "/api/v1/dd/settings", "api_dd_settings"),
    ("post", "/api/v1/dd/settings", "api_dd_settings_update"),
    ("get", "/api/v1/dd/mailboxes", "api_dd_mailboxes"),
    ("get", "/api/v1/dd/dnc", "api_dd_dnc"),
    ("post", "/api/v1/dd/dnc", "api_dd_dnc_update"),
    ("post", "/api/v1/dd/campaign_styles", "api_dd_campaign_style_update"),
]

_TOOLS = ("my_day", "task_done", "call_briefing", "replies", "contacts",
          "import_contacts", "contact_lists", "campaign_contacts",
          "campaign_action", "campaign_edit", "send_preview", "newsletters",
          "newsletter_create", "newsletter_issue", "newsletter_edit",
          "analytics", "settings", "mailboxes", "dnc", "campaign_styles")


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
            return {s.name: s for s in n.body
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {}


def _app_func(name):
    for n in _tree("flowdrip_app.py").body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


@pytest.mark.parametrize("name", _TOOLS)
def test_every_tool_exists_with_a_client_method(name):
    assert _tool_names().count(name) == 1
    assert name in _client_methods()


@pytest.mark.parametrize("name", _TOOLS)
def test_every_client_method_hits_a_registered_route(name):
    src = ast.unparse(_client_methods()[name])
    paths = re.findall(r"_conn_a_(get|post)\('([^']+)'", src)
    assert paths, src
    registered = {(m, p) for m, p, _h in _ROUTES}
    for verb, sub in paths:
        assert (verb, f"/api/v1/dd/{sub}") in registered, (verb, sub)


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_is_registered_and_keyed(method, path, handler):
    node = _app_func(handler)
    assert node is not None, handler
    decs = [ast.unparse(d) for d in node.decorator_list]
    assert f"app.{method}('{path}')" in decs, decs
    owners = [a.value for a in ast.walk(node) if isinstance(a, ast.Assign)
              for t in a.targets if isinstance(t, ast.Tuple)
              and [getattr(e, "id", "") for e in t.elts] == ["owner", "err"]]
    assert len(owners) == 1 and ast.unparse(owners[0]) == "_dd_api_owner(request)"
    # No ThriveModal gate on the DripDrop side.
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    assert "_is_thrivemodal" not in names


def test_routes_sit_in_section_a():
    src = (_ROOT / "flowdrip_app.py").read_text(encoding="utf-8")
    a = src.index("# === DD connector A: shared pages")
    b = src.index("# === DD connector B: DripDrop-only pages")
    for _m, path, _h in _ROUTES:
        i = src.index(f'"{path}")')
        assert a < i < b, path


# ── harness ────────────────────────────────────────────────────────────────

def _camp(**kw):
    c = {"name": "Acme Outreach", "_path": "/data/Acme_Outreach.json",
         "status": "active", "contacts": [],
         "emails": [{"name": "Email 1", "subject": "Hi {FirstName}",
                     "body": "Hello {FirstName} at {Company}",
                     "step_type": "email_auto", "attachments": []},
                    {"name": "Call 1", "subject": "", "body": "",
                     "step_type": "call", "script_notes": "say hi"},
                    {"name": "Email 2", "subject": "Following up",
                     "body": "Hi again", "step_type": "email_auto",
                     "attachments": ["a.pdf"]}]}
    c.update(kw)
    return c


@pytest.fixture
def api(tmp_path, monkeypatch):
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    cdir = tmp_path / "Contacts"
    cdir.mkdir()
    monkeypatch.setattr(fa, "_user_contacts_dir", lambda: cdir)
    monkeypatch.setattr(fa, "_user_contacts_csv_path", lambda: cdir / "contacts.csv")
    camps = [_camp()]
    saved = []
    monkeypatch.setattr(fa, "load_campaigns", lambda: camps)
    monkeypatch.setattr(fa, "save_campaign", lambda c: saved.append(c))
    monkeypatch.setattr(fa, "_load_queue", lambda: [])
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
    try:
        before = fa._CURRENT_USER_EMAIL.get()
    except Exception:
        before = None
    yield {"call": call, "camps": camps, "saved": saved, "tmp": tmp_path,
           "cdir": cdir}
    fa._CURRENT_USER_EMAIL.set(before)


@pytest.mark.parametrize("method,path,handler", _ROUTES)
def test_every_route_needs_a_key(api, method, path, handler):
    assert api["call"](method, path, auth=False).status_code == 401


# ── Today's Tasks ──────────────────────────────────────────────────────────

_TASK = {"id": "/data/Acme_Outreach.json::bob@x.com::2", "channel": "call",
         "name": "Bob", "company": "X", "email": "bob@x.com", "touch": "Touch 2 of 3",
         "sequence": "Acme Outreach", "camp_path": "/data/Acme_Outreach.json",
         "phones": [], "overdue": False}
_LI = dict(_TASK, id="/data/Acme_Outreach.json::amy@x.com::3", channel="li",
           email="amy@x.com")


def _outcomes(monkeypatch):
    store = {}
    monkeypatch.setattr(fa, "load_outcomes", lambda: dict(store))

    def _save(o):
        store.clear()
        store.update(o)
    monkeypatch.setattr(fa, "save_outcomes", _save)
    return store


def test_my_day_lists_tasks_without_server_paths(api, monkeypatch):
    monkeypatch.setattr(fa, "build_drip_tasks", lambda d=None: [dict(_TASK)])
    r = api["call"]("get", "/api/v1/dd/tasks")
    assert r.status_code == 200
    t = r.json()["tasks"][0]
    assert t["campaign"] == "Acme Outreach" and t["campaign_id"] == "Acme_Outreach"
    assert "camp_path" not in t
    assert r.json()["by_channel"]["call"] == 1
    assert api["call"]("get", "/api/v1/dd/tasks", params={"date": "soon"}).status_code == 400


def test_task_done_writes_the_outcome_the_page_writes(api, monkeypatch):
    store = _outcomes(monkeypatch)
    monkeypatch.setattr(fa, "build_drip_tasks", lambda d=None: [dict(_TASK)])
    c = api["call"]
    r = c("post", "/api/v1/dd/tasks/done", {"task_id": _TASK["id"], "result": "vm"})
    assert r.status_code == 200, r.text
    assert store[_TASK["id"]] == {"result": "vm", "date": date.today().isoformat()}
    r = c("post", "/api/v1/dd/tasks/done", {"task_id": _TASK["id"], "undo": True})
    assert r.status_code == 200 and _TASK["id"] not in store
    assert c("post", "/api/v1/dd/tasks/done", {"task_id": "nope"}).status_code == 404
    assert c("post", "/api/v1/dd/tasks/done",
             {"task_id": _TASK["id"], "result": "maybe"}).status_code == 400


def test_bulk_marks_need_confirm_and_use_the_pages_results(api, monkeypatch):
    store = _outcomes(monkeypatch)
    monkeypatch.setattr(fa, "build_drip_tasks",
                        lambda d=None: [dict(_TASK), dict(_LI)])
    c = api["call"]
    r = c("post", "/api/v1/dd/tasks/done", {"campaign": "Acme_Outreach"})
    assert r.status_code == 400 and store == {}
    r = c("post", "/api/v1/dd/tasks/done", {"campaign": "Acme_Outreach", "confirm": True})
    assert r.json()["marked"] == 2
    assert store[_TASK["id"]]["result"] == "vm"
    assert store[_LI["id"]]["result"] == "connected"


def test_call_briefing_returns_the_cached_one(api, monkeypatch):
    api["camps"][0]["call_briefing"] = {
        "_schema_version": fa._CALL_BRIEFING_SCHEMA_VERSION, "overview": "Acme builds"}
    monkeypatch.setattr(fa, "build_drip_tasks", lambda d=None: [dict(_TASK)])
    r = api["call"]("post", "/api/v1/dd/tasks/briefing", {"task_id": _TASK["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["briefing"] == {"overview": "Acme builds"}
    assert r.json()["campaign_id"] == "Acme_Outreach"


# ── Replies ────────────────────────────────────────────────────────────────

def test_replies_follow_up_and_dismiss(api, monkeypatch):
    rows = [{"email": "a@x.com", "followed_up": False},
            {"email": "b@x.com", "followed_up": False}]
    saved = []
    monkeypatch.setattr(fa, "load_responded", lambda: [dict(r) for r in rows])
    monkeypatch.setattr(fa, "save_responded", lambda r: saved.append(r))
    c = api["call"]
    assert c("get", "/api/v1/dd/replies").json()["awaiting_follow_up"] == 2
    assert c("post", "/api/v1/dd/replies",
             {"email": "A@x.com", "action": "followed_up"}).status_code == 200
    assert saved[-1][0]["followed_up"] is True
    assert c("post", "/api/v1/dd/replies",
             {"email": "b@x.com", "action": "dismiss"}).status_code == 200
    assert [r["email"] for r in saved[-1]] == ["a@x.com"]
    assert c("post", "/api/v1/dd/replies",
             {"email": "z@x.com", "action": "dismiss"}).status_code == 404
    assert c("post", "/api/v1/dd/replies",
             {"email": "a@x.com", "action": "send"}).status_code == 400


def test_draft_reply_uses_the_pages_prompt_and_sends_nothing(api, monkeypatch):
    monkeypatch.setattr(fa, "load_responded", lambda: [
        {"email": "a@x.com", "reply_body": "Sure, call me", "subject": "Hi",
         "campaign": "Acme Outreach", "name": "Ann"}])
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "test-key")
    seen = {}
    monkeypatch.setattr(fa, "_dda_ai_draft_reply",
                        lambda client, e, bp, cn, nm: seen.update(e=e, bp=bp) or "Great, Tuesday?")
    r = api["call"]("post", "/api/v1/dd/replies", {"email": "a@x.com", "action": "draft"})
    assert r.status_code == 200, r.text
    assert r.json()["draft"] == "Great, Tuesday?" and r.json()["reply_subject"] == "Re: Hi"
    assert seen == {"e": "a@x.com", "bp": "Sure, call me"}


# ── Contacts ───────────────────────────────────────────────────────────────

def _write_list(cdir, name, rows):
    fa._atomic_write_text(cdir / f"{name}.csv", fa._dda_list_text(rows))


def test_contact_search_filters_one_list(api):
    _write_list(api["cdir"], "SD_PMs", [
        {"email": "a@x.com", "first_name": "Ann", "company": "Acme"},
        {"email": "b@y.com", "first_name": "Bo", "company": "Beta"}])
    c = api["call"]
    r = c("get", "/api/v1/dd/contacts/search", params={"list": "SD PMs", "q": "acme"})
    assert r.status_code == 200, r.text
    assert r.json()["matched"] == 1 and r.json()["lists"] == ["SD_PMs"]
    assert r.json()["contacts"][0]["first_name"] == "Ann"
    assert c("get", "/api/v1/dd/contacts/search", params={"list": "Nope"}).status_code == 404


def test_import_contacts_merges_into_a_named_list(api):
    c = api["call"]
    r = c("post", "/api/v1/dd/contacts", {"list": "Denver GCs", "contacts": [
        {"email": "Ann@X.com", "firstName": "Ann", "companyName": "Acme"},
        {"email": "bad"}]})
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 1 and r.json()["list"] == "Denver_GCs"
    assert r.json()["dropped"][0]["reason"] == "no valid email"
    r = c("post", "/api/v1/dd/contacts", {"list": "Denver_GCs", "contacts": [
        {"email": "ann@x.com", "title": "VP Ops", "first_name": ""},
        {"email": "cy@x.com"}]})
    assert r.json()["added"] == 1 and r.json()["updated"] == 1
    rows = fa._dda_read_list(api["cdir"] / "Denver_GCs.csv")
    ann = next(x for x in rows if x["email"] == "ann@x.com")
    assert ann["first_name"] == "Ann" and ann["title"] == "VP Ops"
    assert c("post", "/api/v1/dd/contacts", {"contacts": []}).status_code == 400


def test_contact_list_edits_follow_the_contacts_page(api):
    _write_list(api["cdir"], "PMs", [{"email": "a@x.com", "first_name": "Ann"}])
    # The page has this list open: the active CSV is its byte copy.
    (api["cdir"] / "contacts.csv").write_bytes((api["cdir"] / "PMs.csv").read_bytes())
    c = api["call"]
    r = c("post", "/api/v1/dd/contact_lists", {"action": "add_contact", "list": "PMs",
                                               "contact": {"email": "b@x.com", "city": "Denver"}})
    assert r.status_code == 200 and r.json()["total"] == 2
    assert c("post", "/api/v1/dd/contact_lists", {"action": "add_contact", "list": "PMs",
                                                  "contact": {"email": "b@x.com"}}).status_code == 409
    r = c("post", "/api/v1/dd/contact_lists", {"action": "update_contact", "list": "PMs",
                                               "email": "a@x.com", "changes": {"title": "PM"}})
    assert r.json()["updated"]["title"] == "PM"
    assert c("post", "/api/v1/dd/contact_lists", {
        "action": "update_contact", "list": "PMs", "email": "a@x.com",
        "changes": {"shoe_size": "9"}}).status_code == 400
    active = fa._dda_read_list(api["cdir"] / "contacts.csv")
    assert [x["email"] for x in active] == ["b@x.com", "a@x.com"]
    assert active[0]["city"] == "Denver" and active[1]["title"] == "PM"
    assert c("post", "/api/v1/dd/contact_lists",
             {"action": "delete_list", "list": "PMs"}).status_code == 400
    assert (api["cdir"] / "PMs.csv").exists()
    assert c("post", "/api/v1/dd/contact_lists", {"action": "delete_list", "list": "PMs",
                                                  "confirm": True}).status_code == 200
    assert not (api["cdir"] / "PMs.csv").exists()


# ── campaign contacts + lifecycle ──────────────────────────────────────────

def test_adding_contacts_needs_confirm_and_uses_the_pages_helper(api, monkeypatch):
    got = []
    monkeypatch.setattr(fa, "add_contacts_to_campaign",
                        lambda camp, cs: got.extend(cs) or len(cs) - 1)
    monkeypatch.setattr(fa, "is_on_dnc", lambda e: e == "dnc@x.com")
    monkeypatch.setattr(fa, "_is_evergreen", lambda c: False)
    body = {"campaign_id": "Acme_Outreach",
            "contacts": [{"Email": "Ann@X.com", "FirstName": "Ann"},
                         {"email": "dnc@x.com"}, {"email": "not-an-email"}]}
    c = api["call"]
    assert c("post", "/api/v1/dd/campaigns/contacts", body).status_code == 400
    assert got == []
    r = c("post", "/api/v1/dd/campaigns/contacts", dict(body, confirm=True))
    assert r.status_code == 200, r.text
    assert [x["email"] for x in got] == ["ann@x.com", "dnc@x.com"]
    assert r.json()["added"] == 1 and r.json()["invalid_email"] == 1
    assert r.json()["on_do_not_contact_not_queued"] == 1


def test_a_cancelled_campaign_takes_no_contacts_and_remove_works(api, monkeypatch):
    api["camps"][0]["status"] = "cancelled"
    c = api["call"]
    assert c("post", "/api/v1/dd/campaigns/contacts", {
        "campaign_id": "Acme_Outreach", "confirm": True,
        "contacts": [{"email": "a@x.com"}]}).status_code == 409
    monkeypatch.setattr(fa, "remove_contact_from_campaign",
                        lambda camp, e: 1 if e == "a@x.com" else 0)
    assert c("post", "/api/v1/dd/campaigns/contacts", {
        "campaign_id": "Acme_Outreach", "action": "remove",
        "email": "a@x.com"}).status_code == 200
    assert c("post", "/api/v1/dd/campaigns/contacts", {
        "campaign_id": "Acme_Outreach", "action": "remove",
        "email": "b@x.com"}).status_code == 404


def test_cancel_and_delete_need_confirm(api, monkeypatch):
    monkeypatch.setattr(fa, "cancel_campaign_queue", lambda n: 7)
    gone = []
    monkeypatch.setattr(fa, "delete_campaign", lambda p: gone.append(p))
    c = api["call"]
    body = {"campaign_id": "Acme_Outreach", "action": "cancel"}
    assert c("post", "/api/v1/dd/campaigns/action", body).status_code == 400
    r = c("post", "/api/v1/dd/campaigns/action", dict(body, confirm=True))
    assert r.json()["cancelled_emails"] == 7
    assert api["saved"][-1]["status"] == "cancelled"
    body = {"campaign_id": "Acme_Outreach", "action": "delete"}
    assert c("post", "/api/v1/dd/campaigns/action", body).status_code == 400
    assert gone == []
    assert c("post", "/api/v1/dd/campaigns/action",
             dict(body, confirm=True)).status_code == 200
    assert gone == ["/data/Acme_Outreach.json"]


def test_launch_a_draft_gates_on_confirm_and_current_clients(api, monkeypatch):
    api["camps"][0].update(status="draft", contacts=[{"email": "a@client.com"},
                                                     {"email": "b@x.com"}])
    queued = []
    monkeypatch.setattr(fa, "queue_campaign_emails",
                        lambda camp, start_step=0: queued.append(camp) or 4)
    monkeypatch.setattr(fa, "load_client_blocklist",
                        lambda *a, **k: [{"domain": "client.com", "client_name": "Client"}])
    monkeypatch.setattr(fa, "blocklisted_contacts", lambda cs, bl: [
        (c, bl[0]) for c in cs if c["email"].endswith("@client.com")])
    c = api["call"]
    body = {"campaign_id": "Acme_Outreach", "action": "launch"}
    assert c("post", "/api/v1/dd/campaigns/action", body).status_code == 400
    r = c("post", "/api/v1/dd/campaigns/action", dict(body, confirm=True))
    assert r.status_code == 409 and r.json()["active_client_contacts"] == 1
    assert queued == []
    past = (date.today() - timedelta(days=1)).isoformat()
    assert c("post", "/api/v1/dd/campaigns/action", dict(
        body, confirm=True, active_clients="skip", start_date=past)).status_code == 400
    r = c("post", "/api/v1/dd/campaigns/action",
          dict(body, confirm=True, active_clients="skip"))
    assert r.status_code == 200, r.text
    assert r.json()["launched"] is True and r.json()["emails_queued"] == 4
    camp = queued[-1]
    assert camp["status"] == "active" and camp["_ac_decision"] == "skip"
    assert camp["start_date"] == date.today().isoformat()


def test_launch_refuses_a_campaign_that_already_sent(api, monkeypatch):
    monkeypatch.setattr(fa, "_load_queue", lambda: [
        {"campaign": "Acme Outreach", "status": "sent"}])
    r = api["call"]("post", "/api/v1/dd/campaigns/action", {
        "campaign_id": "Acme_Outreach", "action": "launch", "confirm": True})
    assert r.status_code == 409


def test_graduate_enrols_repliers_into_a_newsletter(api, monkeypatch):
    nl = _camp(name="Market Note", _path="/data/Market_Note.json",
               evergreen_only=True, market_analysis=True, contacts=[])
    api["camps"].append(nl)
    api["camps"][0]["contacts"] = [{"email": "a@x.com"}, {"email": "b@x.com"},
                                   {"email": "c@x.com", "removed": True}]
    monkeypatch.setattr(fa, "load_responded", lambda: [{"email": "a@x.com"}])
    got = []
    monkeypatch.setattr(fa, "enroll_contact_in_evergreen",
                        lambda c, camp: got.append((c["email"], camp["name"])) or "enrolled")
    r = api["call"]("post", "/api/v1/dd/campaigns/action", {
        "campaign_id": "Acme_Outreach", "action": "graduate_responders",
        "newsletter_id": "Market_Note"})
    assert r.status_code == 200, r.text
    assert got == [("a@x.com", "Market Note"), ("c@x.com", "Market Note")]
    assert r.json()["enrolled"] == 2


def test_send_preview_merges_the_users_own_name(api, monkeypatch):
    sent = {}
    monkeypatch.setattr(fa, "_preview_self_contact",
                        lambda s=None: {"first_name": "Mike", "company": "Arena"})
    monkeypatch.setattr(fa, "load_config", lambda: {})
    monkeypatch.setattr(fa, "_send_email_universal",
                        lambda **kw: sent.update(kw) or (True, ""))
    c = api["call"]
    r = c("post", "/api/v1/dd/send_preview", {"campaign_id": "Acme_Outreach", "step": 1})
    assert r.status_code == 200, r.text
    assert sent["to"] == _OWNER and sent["is_preview"] is True
    assert sent["subject"] == "Hi Mike" and sent["html_body"] == "Hello Mike at Arena"
    assert c("post", "/api/v1/dd/send_preview",
             {"campaign_id": "Acme_Outreach", "step": 2}).status_code == 400
    r = c("post", "/api/v1/dd/send_preview", {"campaign_id": "Acme_Outreach", "step": 3})
    assert sent["attachments"][0].endswith("a.pdf")
    monkeypatch.setattr(fa, "_send_email_universal", lambda **kw: (False, "403"))
    r = c("post", "/api/v1/dd/send_preview", {"campaign_id": "Acme_Outreach"})
    assert r.status_code == 502 and "403" in r.json()["error"]


# ── campaign editor ────────────────────────────────────────────────────────

def test_update_step_saves_and_requeues_a_running_campaign(api, monkeypatch):
    monkeypatch.setattr(fa, "_load_queue", lambda: [
        {"campaign": "Acme Outreach", "status": "pending"}])
    req = []
    monkeypatch.setattr(fa, "requeue_campaign",
                        lambda camp: req.append(camp) or {"cancelled": 1, "queued": 1,
                                                          "skipped_sent": 0})
    r = api["call"]("post", "/api/v1/dd/campaigns/edit", {
        "campaign_id": "Acme_Outreach", "action": "update_step", "step": 1,
        "subject": "New subject", "send_time": "2:30 pm"})
    assert r.status_code == 200, r.text
    st = api["camps"][0]["emails"][0]
    assert st["subject"] == "New subject" and st["time"] == "2:30 PM"
    assert r.json()["queue"]["queue_items_changed"] == 1 and len(req) == 1
    assert api["call"]("post", "/api/v1/dd/campaigns/edit", {
        "campaign_id": "Acme_Outreach", "action": "update_step", "step": 1,
        "send_time": "2:31 PM"}).status_code == 400
    assert api["call"]("post", "/api/v1/dd/campaigns/edit", {
        "campaign_id": "Acme_Outreach", "action": "update_step", "step": 2,
        "subject": "x"}).status_code == 400


def test_add_step_renumbers_like_the_tab_bar_and_strips_step_one_files(api):
    api["camps"][0]["emails"][2]["attachments"] = []
    r = api["call"]("post", "/api/v1/dd/campaigns/edit", {
        "campaign_id": "Acme_Outreach", "action": "add_step", "type": "linkedin",
        "position": 2, "note": "connect"})
    assert r.status_code == 200, r.text
    names = [s["name"] for s in api["camps"][0]["emails"]]
    assert names == ["Email 1", "LinkedIn 1", "Call 1", "Email 2"]
    assert api["camps"][0]["emails"][1]["script_notes"] == "connect"


def test_structure_is_locked_once_a_campaign_has_sent(api, monkeypatch):
    monkeypatch.setattr(fa, "_load_queue", lambda: [
        {"campaign": "Acme Outreach", "status": "sent"}])
    for body in ({"action": "add_step"}, {"action": "delete_step", "step": 2},
                 {"action": "move_step", "step": 1, "to_position": 2},
                 {"action": "rename", "name": "Other"}):
        r = api["call"]("post", "/api/v1/dd/campaigns/edit",
                        dict(body, campaign_id="Acme_Outreach"))
        assert r.status_code == 409, body


def test_rename_before_launch(api):
    r = api["call"]("post", "/api/v1/dd/campaigns/edit", {
        "campaign_id": "Acme_Outreach", "action": "rename", "name": "Acme Q4"})
    assert r.status_code == 200, r.text
    assert api["camps"][0]["name"] == "Acme Q4"


def test_ai_rewrite_returns_without_saving_unless_apply(api, monkeypatch):
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(fa, "_dda_ai_rewrite_email_body",
                        lambda client, ins, cur, subj: "Shorter.")
    c = api["call"]
    body = {"campaign_id": "Acme_Outreach", "action": "ai_rewrite", "step": 1,
            "instruction": "make it shorter"}
    r = c("post", "/api/v1/dd/campaigns/edit", body)
    assert r.json()["body"] == "Shorter." and r.json()["applied"] is False
    assert api["saved"] == []
    r = c("post", "/api/v1/dd/campaigns/edit", dict(body, apply=True))
    assert r.status_code == 200 and api["camps"][0]["emails"][0]["body"] == "Shorter."


# ── newsletters ────────────────────────────────────────────────────────────

def test_create_newsletter_matches_the_create_dialog(api, monkeypatch):
    ran = []
    monkeypatch.setattr(fa, "_run_as_user", lambda e, fn, name=None: ran.append(e))
    c = api["call"]
    r = c("post", "/api/v1/dd/newsletters", {
        "name": "Denver Build Note", "sector": "construction", "region": "Denver, CO",
        "start_date": "2027-01-07", "count": 3})
    assert r.status_code == 200, r.text
    nl = api["saved"][-1]
    assert nl["evergreen_only"] and nl["market_analysis"] and nl["contacts"] == []
    assert nl["market_sector"] == "Construction" and nl["market_sector_key"] == "construction"
    assert nl["newsletter_style"] == "j_way" and nl["newsletter_show_city_life"] is False
    assert [e["fixed_date"] for e in nl["emails"]] == ["2027-01-07", "2027-02-07", "2027-03-07"]
    assert ran == [_OWNER]
    assert c("post", "/api/v1/dd/newsletters", {
        "name": "Acme Outreach", "sector": "construction", "region": "X"}).status_code == 409
    assert c("post", "/api/v1/dd/newsletters", {
        "name": "N", "sector": "space", "region": "X"}).status_code == 400
    assert c("post", "/api/v1/dd/newsletters", {
        "name": "N", "sector": "construction"}).status_code == 400
    assert "construction" in c("get", "/api/v1/dd/newsletters").json()["sectors"]


def test_newsletter_edit_issue_and_settings(api, monkeypatch):
    nl = _camp(name="Note", _path="/data/Note.json", evergreen_only=True,
               market_analysis=True, newsletter_style="full_send",
               emails=[{"name": "Jan", "subject": "Jan", "body": "<p>a</p>",
                        "fixed_date": "2099-01-01", "step_type": "email_auto"}])
    api["camps"][:] = [nl]
    monkeypatch.setattr(fa, "_find_next_evergreen_step", lambda c: 0)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    patched = []
    monkeypatch.setattr(fa, "_dda_patch_pending",
                        lambda *a: patched.append(a) or 2)
    c = api["call"]
    r = c("post", "/api/v1/dd/newsletters/edit", {"campaign_id": "Note",
                                                  "action": "get_issue"})
    assert r.json()["text"] == "a"
    r = c("post", "/api/v1/dd/newsletters/edit", {
        "campaign_id": "Note", "action": "edit_issue", "issue": 1, "body": "<p>b</p>"})
    assert r.json()["queued_emails_updated"] == 2
    assert nl["emails"][0]["confirmed"] is True and nl["emails"][0]["body"] == "<p>b</p>"
    assert patched[-1][:2] == ("Note", "Jan")
    assert c("post", "/api/v1/dd/newsletters/edit", {
        "campaign_id": "Note", "action": "settings",
        "spotlights_per_issue": 4}).status_code == 400
    r = c("post", "/api/v1/dd/newsletters/edit", {
        "campaign_id": "Note", "action": "settings", "spotlights_per_issue": 6,
        "city_life": False})
    assert r.json()["settings"]["spotlights_per_issue"] == 6
    assert nl["newsletter_show_city_life"] is False
    assert c("post", "/api/v1/dd/newsletters/edit",
             {"campaign_id": "Acme_Outreach"}).status_code == 404


def test_patch_pending_repoints_that_issues_queued_emails(tmp_path, monkeypatch):
    qp = tmp_path / "q.json"
    qp.write_text(json.dumps([
        {"campaign": "N", "status": "pending", "step_name": "Oct", "subject": "o", "body": "old"},
        {"campaign": "N", "status": "sent", "step_name": "Oct", "subject": "o", "body": "old"},
        {"campaign": "M", "status": "pending", "step_name": "Oct", "subject": "o", "body": "old"},
    ]), encoding="utf-8")
    monkeypatch.setattr(fa, "_user_queue_path", lambda: qp)
    monkeypatch.setattr(fa, "_FUNNELFORGE_OK", False)
    assert fa._dda_patch_pending("N", "Oct", "o", "new s", "new b") == 1
    q = json.loads(qp.read_text(encoding="utf-8"))
    assert q[0]["body"] == "new b" and q[1]["body"] == "old" and q[2]["body"] == "old"


# ── analytics ──────────────────────────────────────────────────────────────

def test_analytics_counts_from_the_queue_and_replies(api, monkeypatch):
    api["camps"][0]["aicb_camp_type"] = "fourbyfour"
    now = fa.datetime.now().isoformat()
    monkeypatch.setattr(fa, "_load_queue", lambda: [
        {"campaign": "Acme Outreach", "status": "sent", "to": "a@x.com",
         "sent_at": now, "touch_number": 1, "step_name": "Email 1"},
        {"campaign": "Acme Outreach", "status": "sent", "to": "b@x.com",
         "sent_at": now, "touch_number": 1, "step_name": "Email 1"}])
    monkeypatch.setattr(fa, "_load_queue_archive", lambda: [])
    monkeypatch.setattr(fa, "load_responded", lambda: [
        {"email": "a@x.com", "campaign": "Acme Outreach", "date": now}])
    monkeypatch.setattr(fa, "load_dnc", lambda: [])
    r = api["call"]("get", "/api/v1/dd/analytics", params={"campaign": "Acme_Outreach"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["totals"]["sent"] == 2 and j["totals"]["replies"] == 1
    assert j["types"][0]["key"] == "fourbyfour" and j["types"][0]["reply_rate"] == 0.5
    assert j["campaign"]["emails"][0]["replies"] == 1
    assert "tracking" in j
    assert api["call"]("get", "/api/v1/dd/analytics",
                       params={"days": "x"}).status_code == 400


# ── settings / inbox / DNC / styles ────────────────────────────────────────

def test_settings_validate_before_writing(api, monkeypatch):
    sig = api["tmp"] / "signature.txt"
    cfg = {}
    monkeypatch.setattr(fa, "_user_sig_path", lambda: sig)
    monkeypatch.setattr(fa, "load_config", lambda: cfg)
    monkeypatch.setattr(fa, "save_config", lambda c: cfg.update(c))
    monkeypatch.setattr(fa, "_mirrors_team_profile", lambda e: False)
    c = api["call"]
    assert c("post", "/api/v1/dd/settings", {"timezone": "Mars/Base"}).status_code == 400
    assert c("post", "/api/v1/dd/settings",
             {"profile": {"favourite_colour": "x"}}).status_code == 400
    r = c("post", "/api/v1/dd/settings", {"signature": " Mike\nArena "})
    assert r.json()["updated"] == ["signature"]
    assert sig.read_text(encoding="utf-8") == "Mike\nArena"
    r = c("post", "/api/v1/dd/settings", {"daily_send_limit": 9000})
    assert r.json()["daily_send_limit"] == 500 and cfg["daily_send_limit"] == 500
    assert c("post", "/api/v1/dd/settings", {}).status_code == 400


def test_a_teammate_cannot_change_the_team_profile(api, monkeypatch):
    monkeypatch.setattr(fa, "_SERVER_MODE", True)
    monkeypatch.setattr(fa, "_mirrors_team_profile", lambda e: True)
    saved = []
    monkeypatch.setattr(fa, "_save_company_profile", lambda p: saved.append(p))
    r = api["call"]("post", "/api/v1/dd/settings",
                    {"profile": {"company_name": "Mine"}})
    assert r.status_code == 409 and saved == []


def test_mailboxes_reports_the_daily_budget(api, monkeypatch):
    monkeypatch.setattr(fa, "load_config", lambda: {
        "daily_send_limit": 10, "smtp_email": "me@x.com", "smtp_password": "s3cret-pw",
        "smtp_host": "smtp.gmail.com"})
    monkeypatch.setattr(fa, "_HAS_MS_EMAIL", False)
    monkeypatch.setattr(fa, "_HAS_GMAIL_OAUTH", False)
    monkeypatch.setattr(fa, "_dda_sent_today", lambda q, cfg=None: 3)
    j = api["call"]("get", "/api/v1/dd/mailboxes").json()
    assert j["sender"] == {"connected": True, "provider": "smtp", "email": "me@x.com"}
    assert j["remaining_today"] == 7 and "next_step" not in j
    assert "s3cret-pw" not in json.dumps(j)


def test_dnc_takes_one_of_email_or_domain(api, monkeypatch):
    calls = []
    monkeypatch.setattr(fa, "add_domain_to_dnc",
                        lambda d, company="", reason="": calls.append(("dom", d)) or 4)
    monkeypatch.setattr(fa, "add_to_dnc",
                        lambda e, name="", company="", reason="", source="":
                        calls.append(("em", e, source)) or True)
    c = api["call"]
    assert c("post", "/api/v1/dd/dnc", {"action": "add"}).status_code == 400
    assert c("post", "/api/v1/dd/dnc", {"action": "add", "email": "a@x.com",
                                        "domain": "x.com"}).status_code == 400
    r = c("post", "/api/v1/dd/dnc", {"action": "add", "domain": "@Acme.com"})
    assert r.json()["campaign_contacts_stopped"] == 4
    c("post", "/api/v1/dd/dnc", {"action": "add", "email": "B@x.com"})
    assert calls == [("dom", "acme.com"), ("em", "b@x.com", "connector")]


def test_campaign_styles_create_and_delete(api, monkeypatch):
    store = []
    monkeypatch.setattr(fa, "_load_my_campaign_styles", lambda: [dict(x) for x in store])
    monkeypatch.setattr(fa, "_save_my_campaign_styles",
                        lambda s: store.__setitem__(slice(None), s))
    c = api["call"]
    r = c("post", "/api/v1/dd/campaign_styles", {"action": "create", "name": "Two step",
          "steps": [{"type": "email", "content": "intro"},
                    {"type": "call", "delay_days": 2, "content": "follow up"}]})
    assert r.status_code == 200, r.text
    assert "Step 2" in store[0]["description"]
    sid = store[0]["id"]
    assert c("post", "/api/v1/dd/campaign_styles", {"action": "create", "name": "two step",
             "description": "x"}).status_code == 409
    assert c("post", "/api/v1/dd/campaign_styles", {"action": "create", "name": "Bad",
             "steps": [{"type": "fax", "content": "x"}]}).status_code == 400
    assert c("post", "/api/v1/dd/campaign_styles",
             {"action": "delete", "id": sid}).status_code == 400
    assert c("post", "/api/v1/dd/campaign_styles",
             {"action": "delete", "id": sid, "confirm": True}).status_code == 200
    assert store == []


# ── create_campaign draft mode ─────────────────────────────────────────────

class _Req:
    def __init__(self, headers, body):
        self.headers = headers
        self._body = body

    async def json(self):
        return self._body


def test_create_campaign_draft_saves_and_queues_nothing(tmp_path, monkeypatch):
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(fa, "_team_worked_hits", lambda *a, **k: {})
    monkeypatch.setattr(fa, "_split_current_clients", lambda cs, owner: (cs, []))
    monkeypatch.setattr(fa, "_api_create_campaign_blocking", lambda client, spec, owner: {
        "template": "fourbyfour", "campaign_data": {"campaign_name": "Acme 4x4"},
        "emails": [{"subject": "Hi", "body": "Hello", "delay_days": 0,
                    "time": "9:00 AM", "step_type": "email_auto"}],
        "candidate_refs": [], "candidate_warnings": []})
    saved = []

    def _save(c):
        c["_path"] = "/tmp/Acme_4x4.json"
        saved.append(dict(c))
    monkeypatch.setattr(fa, "save_campaign", _save)

    def _no_queue(*a, **k):
        raise AssertionError("a draft must not queue")
    monkeypatch.setattr(fa, "queue_campaign_emails", _no_queue)
    key = fa._mint_api_key(_OWNER)
    spec = {"template": "fourbyfour", "company": "Acme", "niche": "food",
            "roles": ["Plant Manager"], "draft": True,
            "candidates": [{"label": "A", "role": "PM", "bullets": ["x"]}],
            "contacts": [{"email": "vp@acme.com", "first_name": "Dana"}]}
    try:
        before = fa._CURRENT_USER_EMAIL.get()
    except Exception:
        before = None
    try:
        resp = asyncio.run(fa.api_create_campaign(_Req({"x-api-key": key}, spec)))
    finally:
        fa._CURRENT_USER_EMAIL.set(before)
    body = json.loads(resp.body)
    assert resp.status_code == 200, body
    assert body["status"] == "draft" and body["contacts_queued"] == 0
    assert body["campaign_id"] == "Acme_4x4" and body["contacts"] == 1
    assert saved[-1]["status"] == "draft" and saved[-1]["_owner_email"] == _OWNER


def test_launch_drops_and_reports_companies_a_teammate_is_working(api, monkeypatch):
    """queue_campaign_emails drops them anyway; launch says who and why so
    Claude can tell the user, and refuses when nobody is left."""
    api["camps"][0].update(status="draft", aicb_camp_type="fivebyfive",
                           contacts=[{"email": "a@worked.com"}, {"email": "b@fresh.com"}])
    queued = []
    monkeypatch.setattr(fa, "queue_campaign_emails",
                        lambda camp, start_step=0: queued.append(camp) or 2)
    monkeypatch.setattr(fa, "load_client_blocklist", lambda *a, **k: [])
    rec = {"path": "/t/x.json", "domain": "worked.com"}
    monkeypatch.setattr(fa, "_team_worked_hits", lambda *a, **k: {"worked.com": rec})
    monkeypatch.setattr(fa, "_team_worked_reason", lambda sk: "worked.com is in Sam's campaign.")
    body = {"campaign_id": "Acme_Outreach", "action": "launch", "confirm": True}
    r = api["call"]("post", "/api/v1/dd/campaigns/action", body)
    assert r.status_code == 200, r.text
    assert r.json()["already_worked"] == "worked.com is in Sam's campaign."
    assert r.json()["contacts"] == 1
    assert [c["email"] for c in queued[-1]["contacts"]] == ["b@fresh.com"]

    api["camps"][0].update(contacts=[{"email": "a@worked.com"}])
    monkeypatch.setattr(fa, "_load_queue", lambda: [])
    r = api["call"]("post", "/api/v1/dd/campaigns/action", body)
    assert r.status_code == 409 and "already in a campaign" in r.json()["error"]


def test_newsletters_are_exempt_from_the_teammate_skip(monkeypatch):
    monkeypatch.setattr(fa, "_team_worked_hits", lambda *a, **k: {"worked.com": {}})
    cs = [{"email": "a@worked.com"}]
    kept, why = fa._dda_team_skip({"name": "N", "evergreen_only": True}, cs, "o@x.com")
    assert kept == cs and why == ""

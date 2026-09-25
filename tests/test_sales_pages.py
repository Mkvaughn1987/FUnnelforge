"""Companies + Pipeline (sales_pages.py): the roll-up, stage rules, the
board subset, the team-scoped record file, and the app wiring.

The roll-up is pure apart from flowdrip_app._company_index, so fixtures go
straight in. Storage tests point _team_dir at a tmp path.
"""
import inspect
import json

import pytest

import flowdrip_app as fa
import sales_pages as sp


def _c(email, first, last, company, title="", domain="", cid=""):
    return {"email": email, "first_name": first, "last_name": last,
            "company": company, "title": title, "company_domain": domain,
            "company_id": cid}


CONTACTS = [
    _c("dana@acme.com", "Dana", "Ortiz", "Acme Corp", "COO"),
    _c("lee@acme.com", "Lee", "Park", "Acme Corp", "Controller"),
    _c("sam@globex.io", "Sam", "Reyes", "Globex", domain="globex.io"),
    _c("pat@initech.com", "Pat", "Quinn", "Initech"),
    _c("nobody@gmail.com", "No", "Company", ""),          # unindexed
]
CAMPAIGNS = [
    {"name": "Fall Intro", "status": "active",
     "contacts": [_c("dana@acme.com", "Dana", "Ortiz", "Acme Corp"),
                  _c("sam@globex.io", "Sam", "Reyes", "Globex", domain="globex.io")]},
    {"name": "Old Draft", "status": "draft",
     "contacts": [_c("pat@initech.com", "Pat", "Quinn", "Initech")]},
]
QUEUE = [
    {"campaign": "Fall Intro", "to": "dana@acme.com", "status": "sent",
     "sent_at": "2026-09-20T09:00:00"},
    {"campaign": "Fall Intro", "to": "dana@acme.com", "status": "sent",
     "sent_at": "2026-09-22 09:00:00"},
    {"campaign": "Fall Intro", "to": "lee@acme.com", "status": "pending",
     "send_dt": "2026-09-30T09:00:00"},
    {"campaign": "Fall Intro", "to": "sam@globex.io", "status": "pending",
     "send_dt": "2026-09-29T09:00:00"},
]
RESPONDED = [
    {"email": "dana@acme.com", "name": "Dana Ortiz", "campaign": "Fall Intro",
     "replied_at": "2026-09-23T14:05:00", "reply_body": "Sure, let's talk."},
]
CLIENTS = [{"domain": "wayne.com", "active": True},
           {"domain": "initech.com", "active": False}]


def _rollup(records=None, clients=None):
    return sp.company_rollup(CONTACTS, CAMPAIGNS, QUEUE, RESPONDED,
                             CLIENTS if clients is None else clients, records or {})


def _by_name(rows):
    return {r["name"]: r for r in rows}


# ── Roll-up ───────────────────────────────────────────────────────────────

def test_rollup_groups_by_company_and_counts_from_the_files():
    rows = _by_name(_rollup())
    assert set(rows) == {"Acme Corp", "Globex", "Initech"}, "freemail no-company contact is not a company"
    acme = rows["Acme Corp"]
    assert acme["contact_count"] == 2
    assert acme["sent"] == 2 and acme["pending"] == 1
    assert acme["reply_count"] == 1
    assert acme["campaigns"] == ["Fall Intro"]
    assert acme["last_activity"] == "2026-09-23T14:05:00", "the reply is the latest thing"
    assert "dana@acme.com" in acme["replied_emails"]
    globex = rows["Globex"]
    assert globex["domain"] == "globex.io"
    assert globex["sent"] == 0 and globex["pending"] == 1
    assert globex["campaigns"] == ["Fall Intro"]


def test_rollup_ignores_drafts_and_merges_campaign_contacts():
    rows = _by_name(_rollup())
    assert rows["Initech"]["campaigns"] == [], "a draft is not a campaign that touched anyone"
    # A contact only present inside a campaign record still counts.
    camps = [{"name": "Solo", "status": "active",
              "contacts": [_c("x@umbrella.com", "X", "Y", "Umbrella")]}]
    rows = _by_name(sp.company_rollup([], camps, [], [], [], {}))
    assert rows["Umbrella"]["contact_count"] == 1
    assert rows["Umbrella"]["campaigns"] == ["Solo"]


def test_rollup_sorts_by_last_activity_then_name():
    rows = _rollup()
    assert rows[0]["name"] == "Acme Corp"
    names = [r["name"] for r in rows if not r["last_activity"]]
    assert names == sorted(names, key=str.lower)


# ── Stages ────────────────────────────────────────────────────────────────

def test_derived_stage():
    assert sp.derived_stage(0, 0) == "prospect"
    assert sp.derived_stage(3, 0) == "contacted"
    assert sp.derived_stage(3, 1) == "replied"
    assert sp.derived_stage(0, 1) == "replied"


def test_client_beats_manual_beats_derived():
    assert sp.resolve_stage("replied", "meeting", True) == ("client", "client")
    assert sp.resolve_stage("replied", "meeting", False) == ("meeting", "manual")
    assert sp.resolve_stage("replied", "", False) == ("replied", "derived")
    assert sp.resolve_stage("replied", "bogus", False) == ("replied", "derived")
    # A manual stage below the data is kept: it is the rep's word.
    assert sp.resolve_stage("replied", "prospect", False) == ("prospect", "manual")


def test_stages_in_rollup():
    rows = _by_name(_rollup())
    assert rows["Acme Corp"]["stage"] == "replied"
    assert rows["Globex"]["stage"] == "prospect"
    rows = _by_name(_rollup(records={"name:acme": {"stage": "proposal"}}))
    assert rows["Acme Corp"]["stage"] == "proposal"
    assert rows["Acme Corp"]["stage_basis"] == "manual"
    assert rows["Acme Corp"]["derived_stage"] == "replied"


def test_client_detection_uses_the_blocklist_like_the_send_path():
    # Verified company domain, contact email domain, and subdomains all count;
    # an inactive blocklist entry does not.
    rows = _by_name(_rollup(clients=[{"domain": "acme.com", "active": True}]))
    assert rows["Acme Corp"]["is_client"] and rows["Acme Corp"]["stage"] == "client"
    rows = _by_name(_rollup(clients=[{"domain": "globex.io", "active": True}]))
    assert rows["Globex"]["is_client"]
    assert sp._domain_is_client("mail.acme.com", ["acme.com"])
    assert not sp._domain_is_client("notacme.com", ["acme.com"])
    rows = _by_name(_rollup())          # initech.com is inactive in CLIENTS
    assert not rows["Initech"]["is_client"]


# ── Board ─────────────────────────────────────────────────────────────────

def test_board_shows_only_touched_companies():
    rows = _rollup()
    board = {r["name"] for r in sp.board_companies(rows)}
    assert board == {"Acme Corp", "Globex"}, "Initech was only in a draft"
    rows = _rollup(records={"name:initech": {"note": "met at a show"}})  # key = "name:" + folded name
    assert "Initech" in {r["name"] for r in sp.board_companies(rows)}


def test_board_columns_cap_and_count():
    many = [_c(f"p{i}@co{i}.com", "P", str(i), f"Co {i}") for i in range(50)]
    camps = [{"name": "Big", "status": "active", "contacts": many}]
    rows = sp.company_rollup([], camps, [], [], [], {})
    cols = sp.board_columns(rows, cap=10)
    assert list(cols) == sp.STAGE_KEYS
    assert cols["prospect"]["total"] == 50 and len(cols["prospect"]["rows"]) == 10
    assert cols["client"]["total"] == 0


def test_filter_rollup():
    rows = _rollup()
    assert [r["name"] for r in sp.filter_rollup(rows, q="glob")] == ["Globex"]
    assert [r["name"] for r in sp.filter_rollup(rows, q="GLOBEX.IO")] == ["Globex"]
    assert [r["name"] for r in sp.filter_rollup(rows, stage="replied")] == ["Acme Corp"]
    assert sp.filter_rollup(rows, stage="lost") == []


def test_public_row_has_no_contact_dump():
    r = sp.public_row(_rollup()[0])
    assert r["contacts"] == 2 and "replies" in r and "stage" in r
    assert "record" not in r and "replied_emails" not in r


# ── Records ───────────────────────────────────────────────────────────────

@pytest.fixture
def team_dir(tmp_path, monkeypatch):
    # Patch the module object sales_pages actually resolves: other test
    # files drop and re-import flowdrip_app, so the `fa` bound at collection
    # time can be a stale copy by the time this runs in the full suite.
    monkeypatch.setattr(sp._ff(), "_team_dir", lambda email=None: tmp_path)
    return tmp_path


def test_record_round_trip_and_cleanup(team_dir):
    assert sp.load_pipeline("a@x.com") == {}
    rec = sp.save_pipeline_record("name:acme corp", {"stage": "Meeting", "note": "call Dana"},
                                  "a@x.com", name="Acme Corp")
    assert rec["stage"] == "meeting" and rec["note"] == "call Dana"
    assert rec["updated_by"] == "a@x.com" and rec["updated_at"]
    on_disk = json.loads((team_dir / "sales_pipeline.json").read_text(encoding="utf-8"))
    assert on_disk["name:acme corp"]["name"] == "Acme Corp"
    # Only the fields given change.
    sp.save_pipeline_record("name:acme corp", {"next_step": "send deck"}, "a@x.com")
    data = sp.load_pipeline("a@x.com")["name:acme corp"]
    assert data["stage"] == "meeting" and data["next_step"] == "send deck"
    # A blank stage goes back to auto; an empty record disappears.
    sp.save_pipeline_record("name:acme corp", {"stage": ""}, "a@x.com")
    assert "stage" not in sp.load_pipeline("a@x.com")["name:acme corp"]
    sp.save_pipeline_record("name:acme corp", {"next_step": "", "note": ""}, "a@x.com")
    assert sp.load_pipeline("a@x.com") == {}
    assert not (team_dir / "sales_pipeline.tmp").exists()


def test_record_rejects_bad_input(team_dir):
    with pytest.raises(ValueError):
        sp.save_pipeline_record("", {"stage": "meeting"}, "a@x.com")
    with pytest.raises(ValueError):
        sp.save_pipeline_record("name:x", {"stage": "won"}, "a@x.com")


# ── Wiring ────────────────────────────────────────────────────────────────

def test_pages_are_routed_titled_and_helped():
    router = inspect.getsource(fa.render_page)
    assert 'elif page in ("companies", "pipeline"):' in router
    for k in ("companies", "pipeline"):
        assert fa.SIDEBAR_PAGE_ROW[k] == k
        assert fa.SIDEBAR_TITLES[k]
        assert fa.PAGE_HELP[k]["summary"] and fa.PAGE_HELP[k]["next_action"]
    by_label = {lbl: key for _sec, rows in fa.SIDEBAR_NAV for _ik, lbl, key in rows}
    assert by_label["Companies"] == "companies" and by_label["Pipeline"] == "pipeline"
    # Arena's classic nav is untouched: no row, so no route to reach it from.
    assert "companies" not in {k for _i, _l, k in fa.SALES_NAV}
    assert "pipeline" not in {k for _i, _l, k in fa.SALES_NAV}


def test_connector_routes_exist():
    src = inspect.getsource(fa)
    for path in ('@app.get("/api/v1/tm/companies")', '@app.get("/api/v1/tm/pipeline")',
                 '@app.post("/api/v1/tm/pipeline")'):
        assert path in src
    assert '.strip().lower() == "client":' in inspect.getsource(fa.api_tm_pipeline_update), \
        "Client must not be settable through the pipeline route"


def test_mcp_tools_registered():
    import pathlib
    root = pathlib.Path(fa.__file__).resolve().parent / "mcp_server"
    server = (root / "dripdrop_mcp.py").read_text(encoding="utf-8")
    client = (root / "dripdrop_client.py").read_text(encoding="utf-8")
    assert "async def tm_companies(" in server and "async def tm_pipeline(" in server
    assert 'self._tm_get("companies"' in client and 'self._tm_post("pipeline"' in client

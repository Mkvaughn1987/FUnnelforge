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
    assert 'elif page in ("companies", "sales_dashboard"):' in router
    for k in ("companies",):
        assert fa.SIDEBAR_PAGE_ROW[k] == k
        assert fa.SIDEBAR_TITLES[k]
        assert fa.PAGE_HELP[k]["summary"] and fa.PAGE_HELP[k]["next_action"]
    by_label = {lbl: key for _sec, rows in fa.SIDEBAR_NAV for _ik, lbl, key in rows}
    assert by_label["Companies"] == "companies"
    # The board is a view on Companies since 2026-09-25, not a page.
    assert "Pipeline" not in by_label
    assert "pipeline" not in fa.SIDEBAR_PAGE_ROW and "pipeline" not in fa.PAGE_HELP
    assert not hasattr(sp, "p_pipeline")
    src = inspect.getsource(sp.p_companies)
    assert '"board"' in src and "_board(" in src and "_stage_select(" in src
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


# ── Industries, selection, newsletter + campaign hand-off (2026-11-05) ────

def test_industry_from_column_name_then_campaigns():
    # The list's own column wins, folded into a headline when it fits one.
    assert sp.company_industry("Commercial & Residential Construction", "Golden Triangle") \
        == "Construction"
    # An industry nothing knows keeps its own name rather than becoming Other.
    assert sp.company_industry("Aquaculture", "Fishy Co") == "Aquaculture"
    # No column: the company name.
    assert sp.company_industry("", "Bridge Logistics") == "Logistics & Freight"
    assert sp.company_industry("", "Triple T Transport") == "Logistics & Freight"
    # Name says nothing: what most of its campaigns are about.
    assert sp.company_industry("", "Allen Lund Company",
                               ["Allen Lund Company", "The Freight Desk, After Hours"]) \
        == "Logistics & Freight"
    assert sp.company_industry("", "The Custom Companies", []) == sp.INDUSTRY_OTHER


def test_rollup_carries_industry_group_and_campaign_niche():
    contacts = [_c("a@lund.com", "A", "B", "Allen Lund Company"),
                _c("c@gt.com", "C", "D", "Golden Triangle", )]
    contacts[1]["industry"] = "Commercial & Residential Construction"
    camps = [{"name": "Fall Newsletter", "status": "active", "market_niche": "Freight Brokerage",
              "contacts": [dict(contacts[0])]}]
    rows = _by_name(sp.company_rollup(contacts, camps, [], [], [], {}))
    assert rows["Allen Lund Company"]["industry_group"] == "Logistics & Freight"
    assert rows["Golden Triangle"]["industry_group"] == "Construction"
    assert sp.public_row(rows["Golden Triangle"])["industry_group"] == "Construction"


def test_industry_groups_biggest_first_other_last():
    rows = [{"key": str(i), "industry_group": g} for i, g in enumerate(
        ["Other", "Other", "Other", "Construction", "Logistics & Freight",
         "Logistics & Freight"])]
    assert [g for g, _ in sp.industry_groups(rows)] == \
        ["Logistics & Freight", "Construction", "Other"]


def test_filter_rollup_by_industry():
    rows = _rollup()
    assert {r["industry_group"] for r in rows} == {sp.INDUSTRY_OTHER}
    assert len(sp.filter_rollup(rows, industry="other")) == len(rows)
    assert sp.filter_rollup(rows, industry="Construction") == []


def test_selected_contacts_dedupes_and_drops_campaign_state():
    rows = _rollup()
    acme = _by_name(rows)["Acme Corp"]
    acme["contacts"][0]["removed"] = True          # one campaign's state
    acme["contacts"].append(dict(acme["contacts"][1]))   # same person twice
    acme["contacts"].append({"first_name": "No", "company": "Acme Corp"})  # no email
    got = sp.selected_contacts(rows, [acme["key"]])
    assert [c["email"] for c in got] == ["dana@acme.com", "lee@acme.com"]
    assert all("removed" not in c for c in got)
    assert got[0]["first_name"] == "Dana" and got[0]["company"] == "Acme Corp"
    assert sp.selected_contacts(rows, []) == []


@pytest.fixture
def nl_env(monkeypatch):
    ff = sp._ff()
    queued, saved = [], []
    monkeypatch.setattr(ff, "is_on_dnc", lambda em: em == "dnc@x.com")
    monkeypatch.setattr(ff, "_is_evergreen_completed", lambda c: bool(c.get("_done")))
    monkeypatch.setattr(ff, "_evergreen_start_step_for_enrollee", lambda c: 3)
    monkeypatch.setattr(ff, "queue_campaign_emails",
                        lambda camp, start_step=0: queued.append((camp, start_step)) or 0)
    monkeypatch.setattr(ff, "save_campaign", lambda camp: saved.append(camp))
    return queued, saved


def test_enroll_many_matches_single_enrol_rules(nl_env):
    queued, saved = nl_env
    camp = {"name": "Freight Note", "contacts": [
        {"email": "on@x.com"}, {"email": "gone@x.com", "removed": True},
        {"email": "done@x.com", "completed": True}]}
    people = [{"email": "New@X.com", "first_name": "N"}, {"email": "new@x.com"},
              {"email": "on@x.com"}, {"email": "gone@x.com"}, {"email": "done@x.com"},
              {"email": "dnc@x.com"}, {"email": ""}]
    t = sp.enroll_many(people, camp)
    assert t == {"enrolled": 1, "skipped_duplicate": 2, "skipped_removed": 1,
                 "skipped_completed": 1, "skipped_dnc": 1, "skipped_no_email": 1}
    # Queued and saved once for everybody, from the newsletter's next issue,
    # and only the new person goes in the queue.
    assert len(queued) == 1 and len(saved) == 1
    assert queued[0][1] == 3 and [c["email"] for c in queued[0][0]["contacts"]] == ["new@x.com"]
    assert camp["contact_count"] == 3     # on, done, new (removed doesn't count)
    s = sp.enroll_summary(t, "Freight Note")
    assert s.startswith("Added 1 contact to 'Freight Note'.")
    assert "3 were already on it" in s and "1 is on your Do Not Contact list" in s


def test_enroll_many_nothing_new_writes_nothing(nl_env):
    queued, saved = nl_env
    t = sp.enroll_many([{"email": "a@x.com"}], {"name": "N", "_done": True, "contacts": []})
    assert t == {"campaign_completed": 1} and not queued and not saved
    assert sp.enroll_summary(t, "N").startswith("Nobody new was added")


class _S:
    pass


def test_pending_contacts_land_on_the_next_empty_campaign(monkeypatch):
    s = _S()
    people = [{"email": "a@x.com"}, {"email": "b@x.com"}]
    sp.set_pending(s, people, "Logistics & Freight")
    busy = {"status": "draft", "contacts": [{"email": "z@x.com"}]}
    assert not sp.apply_pending_to_campaign(s, busy)          # never overwrites
    assert not sp.apply_pending_to_campaign(s, {"status": "active", "contacts": []})
    camp = {"status": "draft", "contacts": []}
    assert sp.apply_pending_to_campaign(s, camp)
    assert camp["contact_count"] == 2 and camp["contact_emails"] == ["a@x.com", "b@x.com"]
    assert not sp.apply_pending_to_campaign(s, {"status": "draft"})   # used once

    s.scon = []
    sp.set_pending(s, people, "")
    assert sp.apply_pending_to_wizard(s) and len(s.scon) == 2


def test_pending_contacts_expire(monkeypatch):
    s = _S()
    sp.set_pending(s, [{"email": "a@x.com"}], "")
    s._co_pending["at"] = "2020-01-01T00:00:00"
    camp = {"status": "draft", "contacts": []}
    assert not sp.apply_pending_to_campaign(s, camp) and camp["contacts"] == []


def test_newsletter_sector_key(monkeypatch):
    ff = sp._ff()
    monkeypatch.setattr(ff, "_SALES_MODE", True)
    assert sp.newsletter_sector_key("Logistics & Freight") == "logistics"
    assert sp.newsletter_sector_key("12 companies") == ""


def test_companies_page_wiring():
    page = inspect.getsource(sp.p_companies)
    assert "industry_groups(" in page and "_selection_bar(" in page
    bar = inspect.getsource(sp._selection_bar)
    assert "Add to newsletter" in bar and "Start a campaign" in bar and "Select all" in bar
    # The hand-off is read on both Choose Contacts screens.
    src = inspect.getsource(sp._ff())
    assert "apply_pending_to_campaign(s, camp)" in src
    assert "apply_pending_to_wizard(s)" in src
    assert "on_created(new_camp)" in inspect.getsource(sp._ff()._create_newsletter_dialog)
    landing = dict(sp._ff()._PAGE_LANDING["companies"])
    assert landing["_co_ind"] == "" and landing["_co_sel"] == []

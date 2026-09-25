"""Sales Dashboard (sales_pages.dashboard_stats + wiring).

Fixtures go straight into company_rollup like test_sales_pages.py; the
dashboard numbers are checked against a hand-counted book of companies.
Storage tests point _team_dir at a tmp path.
"""
import inspect
from datetime import datetime

import pytest

import flowdrip_app as fa
import sales_pages as sp

NOW = datetime(2026, 9, 25, 12, 0, 0)


def _c(email, first, last, company, domain=""):
    return {"email": email, "first_name": first, "last_name": last,
            "company": company, "title": "", "company_domain": domain,
            "company_id": ""}


# Eight companies, one per situation the dashboard has to tell apart.
CONTACTS = [
    _c("a@acme.com",   "A", "A", "Acme"),      # contacted twice, replied, no record
    _c("b@bolt.com",   "B", "B", "Bolt"),      # contacted, no reply
    _c("c@cog.com",    "C", "C", "Cog"),       # replied, manual meeting w/ history
    _c("d@dyne.com",   "D", "D", "Dyne"),      # proposal, legacy record, gone quiet
    _c("e@evo.com",    "E", "E", "Evo"),       # lost (history)
    _c("f@fab.com",    "F", "F", "Fab"),       # client, won this window
    _c("g@gib.com",    "G", "G", "Gib"),       # in a campaign, nothing sent yet
    _c("h@hex.com",    "H", "H", "Hex"),       # in a list only: not on the board
]
CAMPAIGNS = [{"name": "Fall", "status": "active",
              "contacts": [c for c in CONTACTS if c["company"] != "Hex"]}]
QUEUE = [
    {"campaign": "Fall", "to": "a@acme.com", "status": "sent", "sent_at": "2026-08-01T09:00:00"},
    {"campaign": "Fall", "to": "a@acme.com", "status": "sent", "sent_at": "2026-09-20T09:00:00"},
    {"campaign": "Fall", "to": "b@bolt.com", "status": "sent", "sent_at": "2026-09-22T09:00:00"},
    {"campaign": "Fall", "to": "c@cog.com",  "status": "sent", "sent_at": "2026-09-10T09:00:00"},
    {"campaign": "Fall", "to": "d@dyne.com", "status": "sent", "sent_at": "2026-07-01T09:00:00"},
    {"campaign": "Fall", "to": "e@evo.com",  "status": "sent", "sent_at": "2026-09-05T09:00:00"},
    {"campaign": "Fall", "to": "f@fab.com",  "status": "sent", "sent_at": "2026-09-01T09:00:00"},
    {"campaign": "Fall", "to": "g@gib.com",  "status": "pending", "send_dt": "2026-10-01T09:00:00"},
]
RESPONDED = [
    {"email": "a@acme.com", "replied_at": "2026-09-21T10:00:00", "reply_body": "yes"},
    {"email": "c@cog.com",  "replied_at": "2026-09-12T10:00:00", "reply_body": "call me"},
]
CLIENTS = [{"domain": "fab.com", "active": True, "added_at": "2026-09-19T08:00:00"}]
RECORDS = {
    "name:cog": {"name": "Cog", "stage": "meeting", "next_step": "Demo Friday",
                 "updated_at": "2026-09-23T09:00:00", "updated_by": "m@x.com",
                 "history": [{"stage": "meeting", "at": "2026-09-23T09:00:00", "by": "m@x.com"}]},
    "name:dyne": {"name": "Dyne", "stage": "proposal", "next_step": "Chase the PO",
                  "updated_at": "2026-08-20T09:00:00", "updated_by": "m@x.com"},
    "name:evo": {"name": "Evo", "stage": "lost",
                 "updated_at": "2026-09-24T09:00:00", "updated_by": "m@x.com",
                 "history": [{"stage": "lost", "at": "2026-09-24T09:00:00", "by": "m@x.com"}]},
}


def _rollup():
    return sp.company_rollup(CONTACTS, CAMPAIGNS, QUEUE, RESPONDED, CLIENTS, RECORDS)


def _names(rows):
    return sorted(r["name"] for r in rows)


# ── Roll-up additions ─────────────────────────────────────────────────────

def test_rollup_carries_first_sent_first_reply_and_client_since():
    by = {r["name"]: r for r in _rollup()}
    assert by["Acme"]["first_sent"] == "2026-08-01T09:00:00"
    assert by["Acme"]["last_activity"] == "2026-09-21T10:00:00"
    assert by["Acme"]["first_reply"] == "2026-09-21T10:00:00"
    assert by["Bolt"]["first_reply"] == ""
    assert by["Gib"]["first_sent"] == ""
    assert by["Fab"]["client_since"] == "2026-09-19T08:00:00"
    assert by["Acme"]["client_since"] == ""


# ── Funnel ────────────────────────────────────────────────────────────────

def test_funnel_is_cumulative_and_excludes_lost():
    st = sp.dashboard_stats(_rollup(), 30, now=NOW)
    counts = {f["key"]: f["count"] for f in st["funnel"]}
    # Board: Acme(replied) Bolt(contacted) Cog(meeting) Dyne(proposal)
    # Evo(lost) Fab(client) Gib(prospect). Hex is list-only, off the board.
    assert counts == {"prospect": 6, "contacted": 5, "replied": 4,
                      "meeting": 3, "proposal": 2, "client": 1}
    assert [f["key"] for f in st["funnel"]] == ["prospect", "contacted", "replied",
                                                "meeting", "proposal", "client"]
    assert st["lost"] == 1
    assert st["win_rate"] == 0.5


def test_funnel_rates_are_step_over_previous_step():
    st = sp.dashboard_stats(_rollup(), 30, now=NOW)
    rates = {f["key"]: f["rate"] for f in st["funnel"]}
    assert rates["prospect"] is None
    assert rates["contacted"] == pytest.approx(5 / 6)
    assert rates["replied"] == pytest.approx(4 / 5)
    assert rates["client"] == pytest.approx(1 / 2)


def test_funnel_on_an_empty_book():
    st = sp.dashboard_stats([], 30, now=NOW)
    assert all(f["count"] == 0 and not f["rate"] for f in st["funnel"])
    assert st["lost"] == 0 and st["win_rate"] is None
    assert all(v == [] for v in st["window"].values())
    assert all(v == [] for v in st["attention"].values())


# ── This window ───────────────────────────────────────────────────────────

def test_window_tiles_over_30_days():
    w = sp.dashboard_stats(_rollup(), 30, now=NOW)["window"]
    # first send inside 08-26..09-25: Bolt 09-22, Cog 09-10, Evo 09-05, Fab 09-01.
    # Acme's first send was 08-01 (its second send does not count).
    assert _names(w["contacted"]) == ["Bolt", "Cog", "Evo", "Fab"]
    assert _names(w["replied"]) == ["Acme", "Cog"]
    assert _names(w["moved"]) == ["Cog"]        # history entry 09-23
    assert _names(w["won"]) == ["Fab"]          # added_at 09-19
    assert _names(w["lost"]) == ["Evo"]         # history entry 09-24


def test_window_tiles_over_7_days():
    w = sp.dashboard_stats(_rollup(), 7, now=NOW)["window"]
    assert _names(w["contacted"]) == ["Bolt"]
    assert _names(w["replied"]) == ["Acme"]
    assert _names(w["moved"]) == ["Cog"]
    assert _names(w["won"]) == ["Fab"]
    assert _names(w["lost"]) == ["Evo"]


def test_window_all_time_includes_the_legacy_record_fallback():
    w = sp.dashboard_stats(_rollup(), None, now=NOW)["window"]
    # Dyne has no history; its proposal stage counts once via updated_at.
    assert _names(w["moved"]) == ["Cog", "Dyne"]
    assert _names(w["contacted"]) == ["Acme", "Bolt", "Cog", "Dyne", "Evo", "Fab"]


def test_window_rows_are_newest_first():
    w = sp.dashboard_stats(_rollup(), 30, now=NOW)["window"]
    assert [r["name"] for r in w["contacted"]] == ["Bolt", "Cog", "Evo", "Fab"]


# ── Needs a hand ──────────────────────────────────────────────────────────

def test_attention_lists():
    a = sp.dashboard_stats(_rollup(), 30, now=NOW)["attention"]
    # Acme replied, nobody set a stage or a next step. Cog replied too but
    # has a manual stage and a next step.
    assert _names(a["replies_waiting"]) == ["Acme"]
    # Dyne's next step was last touched 08-20, 36 days ago. Cog's is 2 days old.
    assert _names(a["stale_next_steps"]) == ["Dyne"]
    # Dyne is at Proposal with its last send on 07-01. Cog had a reply 09-12.
    assert _names(a["going_quiet"]) == ["Dyne"]


def test_attention_ignores_the_window():
    a7 = sp.dashboard_stats(_rollup(), 7, now=NOW)["attention"]
    a_all = sp.dashboard_stats(_rollup(), None, now=NOW)["attention"]
    assert _names(a7["stale_next_steps"]) == _names(a_all["stale_next_steps"]) == ["Dyne"]


def test_going_quiet_includes_a_meeting_with_no_activity_ever():
    recs = {"name:gib": {"name": "Gib", "stage": "meeting",
                         "updated_at": "2026-09-24T09:00:00", "updated_by": "m@x.com"}}
    rollup = sp.company_rollup(CONTACTS, CAMPAIGNS, QUEUE, RESPONDED, CLIENTS, recs)
    a = sp.dashboard_stats(rollup, 30, now=NOW)["attention"]
    assert "Gib" in _names(a["going_quiet"])


# ── Stage history ─────────────────────────────────────────────────────────

@pytest.fixture
def team_dir(tmp_path, monkeypatch):
    # Patch through sp._ff(): several test files drop and re-import
    # flowdrip_app, so the `fa` bound at collection can be a stale module.
    monkeypatch.setattr(sp._ff(), "_team_dir", lambda email=None: tmp_path)
    return tmp_path


def test_history_appends_on_stage_change_only(team_dir):
    rec = sp.save_pipeline_record("name:acme", {"stage": "meeting"}, "m@x.com")
    assert [h["stage"] for h in rec["history"]] == ["meeting"]
    assert rec["history"][0]["by"] == "m@x.com" and rec["history"][0]["at"]
    rec = sp.save_pipeline_record("name:acme", {"note": "spoke to Dana"}, "m@x.com")
    assert [h["stage"] for h in rec["history"]] == ["meeting"], "a note edit is not a move"
    rec = sp.save_pipeline_record("name:acme", {"stage": "meeting"}, "m@x.com")
    assert len(rec["history"]) == 1, "re-saving the same stage is not a move"
    rec = sp.save_pipeline_record("name:acme", {"stage": "proposal"}, "j@x.com")
    assert [h["stage"] for h in rec["history"]] == ["meeting", "proposal"]
    assert rec["history"][-1]["by"] == "j@x.com"
    # Back to auto is a move too (stage ""), and the record survives on
    # the note alone with its history intact.
    rec = sp.save_pipeline_record("name:acme", {"stage": ""}, "m@x.com")
    assert [h["stage"] for h in rec["history"]] == ["meeting", "proposal", ""]
    assert "stage" not in rec and rec["note"] == "spoke to Dana"
    assert sp.load_pipeline("m@x.com")["name:acme"]["history"][-1]["stage"] == ""


def test_history_is_capped(team_dir):
    for i in range(60):
        sp.save_pipeline_record("name:acme", {"stage": ("meeting", "proposal")[i % 2]}, "m@x.com")
    rec = sp.load_pipeline("m@x.com")["name:acme"]
    assert len(rec["history"]) == sp.HISTORY_CAP == 50
    assert rec["history"][-1]["stage"] == "proposal"


def test_history_goes_with_a_deleted_record(team_dir):
    sp.save_pipeline_record("name:acme", {"stage": "meeting"}, "m@x.com")
    sp.save_pipeline_record("name:acme", {"stage": ""}, "m@x.com")
    assert "name:acme" not in sp.load_pipeline("m@x.com")


# ── Wiring ────────────────────────────────────────────────────────────────

def test_page_is_routed_titled_and_helped():
    router = inspect.getsource(fa.render_page)
    assert 'elif page in ("companies", "pipeline", "sales_dashboard"):' in router
    assert "p_sales_dashboard" in router
    assert fa.SIDEBAR_PAGE_ROW["sales_dashboard"] == "sales_dash"
    assert fa.SIDEBAR_TITLES["sales_dashboard"] == "Sales Dashboard"
    h = fa.PAGE_HELP["sales_dashboard"]
    assert h["summary"] and h["next_action"] and h["sections"]
    by_label = {lbl: key for _sec, rows in fa.SIDEBAR_NAV for _ik, lbl, key in rows}
    assert by_label["Sales Dashboard"] == "sales_dashboard"
    assert "sales_dash" in fa._SIDEBAR_ICONS
    # Arena's classic nav is untouched.
    assert "sales_dashboard" not in {k for _i, _l, k in fa.SALES_NAV}


def test_connector_route_and_mcp_tool():
    import pathlib
    assert '@app.get("/api/v1/tm/sales_dashboard")' in inspect.getsource(fa)
    src = inspect.getsource(fa.api_tm_sales_dashboard)
    assert "dashboard_stats" in src and "public_dashboard" in src
    assert "public_row" in inspect.getsource(sp.public_dashboard)
    root = pathlib.Path(fa.__file__).resolve().parent / "mcp_server"
    server = (root / "dripdrop_mcp.py").read_text(encoding="utf-8")
    client = (root / "dripdrop_client.py").read_text(encoding="utf-8")
    assert "async def tm_sales_dashboard(" in server
    assert 'self._tm_get("sales_dashboard"' in client

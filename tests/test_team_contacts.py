"""Shared Arena Contacts: every contact any teammate ever reached, by
company, minus anyone who said no or sits on a Do Not Contact list."""
import json

import pytest

import team_contacts as tcx

ROOT = None


def _camp(root, owner_dir, name, start, contacts, **extra):
    d = root / owner_dir / "Campaigns"
    d.mkdir(parents=True, exist_ok=True)
    camp = {"name": name, "start_date": start, "contacts": contacts}
    camp.update(extra)
    p = d / (name.replace(" ", "_") + ".json")
    p.write_text(json.dumps(camp), encoding="utf-8")
    return p


def _responded(root, owner_dir, rows):
    d = root / owner_dir / "Campaigns"
    d.mkdir(parents=True, exist_ok=True)
    (d / "responded.json").write_text(json.dumps(rows), encoding="utf-8")


def _list(root, owner_dir, name, text):
    d = root / owner_dir / "Contacts"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.csv").write_text(text, encoding="utf-8")


def _dnc(root, owner_dir, rows):
    (root / owner_dir).mkdir(parents=True, exist_ok=True)
    (root / owner_dir / "dnc_list.json").write_text(json.dumps(rows), encoding="utf-8")


def _bank(tmp_path):
    _camp(tmp_path, "mike_at_arena_net", "CO - Galloway - Civil PE", "2026-10-05", [
        {"email": "Carl@gallowayus.com", "first_name": "Carl", "last_name": "Ray",
         "title": "VP Engineering", "company": "Galloway & Company", "phone_mobile": "303-555-0101"},
        {"email": "dana@gallowayus.com", "name": "Dana Lee", "company": "Galloway & Company"},
        {"email": "nope@gallowayus.com", "name": "No Thanks", "company": "Galloway & Company"},
    ], variables={"Industry": "Civil Engineering", "Geography": "Denver, CO"},
        aicb_camp_type="fivebyfive")
    _camp(tmp_path, "sarah_at_arena_net", "CA - Acme Foods - Plant Manager", "2026-06-01", [
        {"email": "carl@gallowayus.com", "Company": "Galloway", "JobTitle": "VP of Engineering",
         "WorkPhone": "303-555-0200", "LinkedInPage": "https://linkedin.com/in/carlray"},
        {"email": "pat@acmefoods.com", "FirstName": "Pat", "LastName": "Quinn",
         "Company": "Acme Foods", "City": "Fresno", "State": "California"},
        {"email": "bounced@acmefoods.com", "name": "Gone Person", "company": "Acme Foods"},
    ], variables={"Industry": "Food Manufacturing"})
    # Newsletter contacts count too (all time, every campaign).
    _camp(tmp_path, "sarah_at_arena_net", "Colorado Construction Rundown", "2025-01-10", [
        {"email": "news@buildco.com", "name": "Nina News", "company": "BuildCo"},
    ], evergreen_only=True)
    # Candidates are not company contacts.
    _camp(tmp_path, "luke_at_arena_net", "Find Candidates - 2026-10-01", "2026-10-01", [
        {"email": "joe@indeedemail.com", "name": "Joe Cand"}], _chooser_origin="candidate")
    # Other teams never show.
    _camp(tmp_path, "bob_at_other_com", "Other", "2026-10-01", [
        {"email": "x@other.com", "company": "Other"}])
    # Uploaded CSV + Add One Contact lists flow in as well.
    _list(tmp_path, "mike_at_arena_net", "Utah_HVAC_upload",
          "Email,FirstName,LastName,Company,JobTitle,MobilePhone,WorkPhone,LinkedInPage,City,State\n"
          "jo@coolair.com,Jo,Frost,Cool Air HVAC,Owner,801-555-0001,,,Provo,UT\n"
          "dana@gallowayus.com,Dana,Lee,Galloway & Company,Project Manager,720-555-0300,,,Denver,CO\n")
    _list(tmp_path, "luke_at_arena_net", "Single_adds",
          "FirstName,LastName,Email,Company,JobTitle\nAl,Smith,al@gmail.com,,Consultant\n")
    _responded(tmp_path, "mike_at_arena_net", [
        {"email": "nope@gallowayus.com", "campaign": "CO - Galloway - Civil PE", "subject": "Re: hi",
         "reply_body": "Thanks but we are not interested at this time.", "date": "2026-10-06"},
        {"email": "dana@gallowayus.com", "campaign": "CO - Galloway - Civil PE", "subject": "Re: hi",
         "reply_body": "Sure, send me a couple of profiles.", "date": "2026-10-06"},
    ])
    _dnc(tmp_path, "sarah_at_arena_net", [
        {"email": "bounced@acmefoods.com", "reason": "bounce", "source": "ndr"}])
    return tcx.scan(tmp_path, "mike@arena.net")


def test_scan_merges_everyone_on_the_team_by_email(tmp_path):
    bank = _bank(tmp_path)
    by = {c["email"]: c for c in bank["contacts"]}
    assert set(by) == {"carl@gallowayus.com", "dana@gallowayus.com", "pat@acmefoods.com",
                       "news@buildco.com", "jo@coolair.com", "al@gmail.com"}
    carl = by["carl@gallowayus.com"]
    assert carl["name"] == "Carl Ray"
    assert carl["title"] == "VP Engineering"          # first seen wins
    assert carl["phone_mobile"] == "303-555-0101"
    assert carl["phone_office"] == "303-555-0200"     # filled from Sarah's row
    assert carl["linkedin"].endswith("/carlray")
    assert carl["reps"] == ["mike_at_arena_net", "sarah_at_arena_net"]
    assert carl["last_seen"] == "2026-10-05"
    assert carl["first_seen"] == "2026-06-01"
    assert [s["name"] for s in carl["sources"]] == ["CO - Galloway - Civil PE", "CA - Acme Foods - Plant Manager"]
    assert bank["reps"]["mike_at_arena_net"] == "Mike"


def test_not_interested_and_dnc_are_gone_for_everyone(tmp_path):
    bank = _bank(tmp_path)
    emails = {c["email"] for c in bank["contacts"]}
    assert "nope@gallowayus.com" not in emails       # replied "not interested"
    assert "bounced@acmefoods.com" not in emails     # on Sarah's DNC list
    assert bank["excluded"] == 2
    assert tcx._is_negative("Please remove me from your list")
    assert tcx._is_negative("NOT INTERESTED")
    assert not tcx._is_negative("Interested, let's talk Tuesday")


def test_other_replies_are_kept_and_flagged(tmp_path):
    bank = _bank(tmp_path)
    by = {c["email"]: c for c in bank["contacts"]}
    assert by["dana@gallowayus.com"]["replied"] == "2026-10-06"
    assert by["carl@gallowayus.com"]["replied"] == ""


def test_csv_lists_and_both_header_styles(tmp_path):
    bank = _bank(tmp_path)
    by = {c["email"]: c for c in bank["contacts"]}
    jo = by["jo@coolair.com"]
    assert jo["name"] == "Jo Frost" and jo["title"] == "Owner" and jo["state"] == "UT"
    assert jo["sources"][0]["kind"] == "list" and jo["sources"][0]["name"] == "Utah HVAC upload"
    dana = by["dana@gallowayus.com"]
    assert dana["title"] == "Project Manager" and dana["phone_mobile"] == "720-555-0300"
    assert {s["kind"] for s in dana["sources"]} == {"campaign", "list"}
    assert by["al@gmail.com"]["first_name"] == "Al"
    assert by["pat@acmefoods.com"]["state"] == "CA"


def test_norm_contact_shapes():
    assert tcx.norm_contact({"name": "x"}) is None
    assert tcx.norm_contact({"email": "A@B.com", "removed": True}) is None
    n = tcx.norm_contact({"Email": " A@B.COM ", "name": "Ann Bell", "State": "Colorado"})
    assert n["email"] == "a@b.com" and n["first_name"] == "Ann" and n["last_name"] == "Bell"
    assert n["state"] == "CO" and n["domain"] == "b.com"
    assert tcx.norm_contact({"email": "a@b.com", "state": "N/A"})["state"] == ""


def test_group_by_company_rows(tmp_path):
    rows = tcx.group_by_company(_bank(tmp_path)["contacts"])
    by = {r["key"]: r for r in rows}
    g = by["gallowayus.com"]
    assert g["company"] == "Galloway & Company"
    assert [c["email"] for c in g["contacts"]] == ["dana@gallowayus.com", "carl@gallowayus.com"]  # replied first
    assert g["reps"] == ["mike_at_arena_net", "sarah_at_arena_net"]
    assert g["state"] == "CO" and g["industry"] == "Civil & Engineering"
    assert g["replied"] == 1 and g["last_seen"] >= "2026-10-05"  # list rows carry the file date
    assert by["acmefoods.com"]["industry"] == "Manufacturing"
    assert by["acmefoods.com"]["state"] == "CA"
    assert "free:gmail.com" in by and by["free:gmail.com"]["company"] == "free:gmail.com"
    assert rows[0]["key"] == "gallowayus.com"  # newest first


def test_filter_sort_lookup_csv(tmp_path):
    recs = _bank(tmp_path)["contacts"]
    rows = tcx.group_by_company(recs)
    assert [r["key"] for r in tcx.filter_rows(rows, rep="sarah_at_arena_net")] == \
        ["gallowayus.com", "acmefoods.com", "buildco.com"]
    assert [r["key"] for r in tcx.filter_rows(rows, state="UT")] == ["coolair.com"]
    assert [r["key"] for r in tcx.filter_rows(rows, industry="Manufacturing")] == ["acmefoods.com"]
    assert [r["key"] for r in tcx.filter_rows(rows, replied="replied")] == ["gallowayus.com"]
    assert [r["key"] for r in tcx.filter_rows(rows, q="project manager")] == ["gallowayus.com"]
    assert [r["key"] for r in tcx.filter_rows(rows, q="fresno")] == ["acmefoods.com"]
    assert tcx.sort_rows(rows, "most")[0]["key"] == "gallowayus.com"
    assert tcx.sort_rows(rows, "name")[0]["company"] == "Acme Foods"
    assert tcx.facet_counts(rows, "state")["CO"] == 2  # Galloway + the Colorado newsletter's BuildCo

    hit = tcx.lookup(recs, "https://www.gallowayus.com/careers")
    assert len(hit) == 1 and hit[0]["company"] == "Galloway & Company"
    assert tcx.lookup(recs, "mail.gallowayus.com")[0]["key"] == "gallowayus.com"
    assert tcx.lookup(recs, "galloway")[0]["key"] == "gallowayus.com"
    assert tcx.lookup(recs, "Acme")[0]["key"] == "acmefoods.com"
    assert tcx.lookup(recs, "nobody-here.com") == []
    assert tcx.lookup(recs, "") == []

    pub = tcx.contact_public(hit[0]["contacts"][1])
    assert pub["email"] == "carl@gallowayus.com" and pub["reps"] == ["Mike", "Sarah"]
    assert pub["campaigns"] == ["CO - Galloway - Civil PE", "CA - Acme Foods - Plant Manager"]
    csv_text = tcx.rows_csv(rows)
    assert csv_text.splitlines()[0].startswith("Company,Name,Title,Email,Mobile")
    assert "nope@gallowayus.com" not in csv_text
    assert "carl@gallowayus.com" in csv_text


def test_cache_follows_file_changes(tmp_path):
    bank = _bank(tmp_path)
    assert "jo@coolair.com" in {c["email"] for c in bank["contacts"]}
    p = tmp_path / "mike_at_arena_net" / "Contacts" / "Utah_HVAC_upload.csv"
    p.unlink()
    bank = tcx.scan(tmp_path, "mike@arena.net")
    assert "jo@coolair.com" not in {c["email"] for c in bank["contacts"]}
    # A later negative reply removes someone who was in the bank.
    _responded(tmp_path, "sarah_at_arena_net", [
        {"email": "pat@acmefoods.com", "subject": "Re:", "reply_body": "Unsubscribe", "date": "2026-10-07"}])
    bank = tcx.scan(tmp_path, "mike@arena.net")
    assert "pat@acmefoods.com" not in {c["email"] for c in bank["contacts"]}


# ── app wiring: sidebar, page, API, connector, prompt rule ───────────────

def test_sidebar_and_titles_carry_the_page():
    import flowdrip_app as fa
    assert ("bank", tcx.PAGE_TITLE, "shared_contacts") in dict(fa.SIDEBAR_NAV)["PEOPLE"]
    assert fa.SIDEBAR_PAGE_ROW["shared_contacts"] == "bank"
    assert fa.SIDEBAR_TITLES["shared_contacts"] == tcx.PAGE_TITLE
    assert "bank" in fa._SIDEBAR_ICONS
    assert any(label == tcx.PAGE_TITLE and page == "shared_contacts" for _, label, page in fa.SALES_NAV)
    assert "fd-sc" in fa._sc_css()
    assert tcx.PAGE_TITLE == "Shared Arena Contacts"


def _page_text(root) -> str:
    bits = []
    for el in root.descendants():
        for attr in ("text", "content"):
            v = getattr(el, attr, None)
            if isinstance(v, str):
                bits.append(v)
    return "\n".join(bits)


def test_page_renders_and_filters(with_user):
    import flowdrip_app as fa
    from nicegui import ui
    users = fa._BASE_DATA_DIR / "users"
    _bank(users)  # builds the arena.net team; the tester is on example.com
    _camp(users, "tester_at_example_com", "CO - Acme - Estimator", "2026-10-05", [
        {"email": "a@acme.com", "name": "Ann Acme", "title": "Estimator", "company": "Acme Builders",
         "phone_mobile": "720-555-0001"},
        {"email": "quit@acme.com", "name": "Quit Person", "company": "Acme Builders"},
    ], variables={"Industry": "Construction", "Geography": "Denver, CO"})
    _camp(users, "sarah_at_example_com", "TX - Bolt - Plant Manager", "2026-10-01", [
        {"email": "b@bolt.com", "name": "Bo Bolt", "title": "Plant Manager", "company": "Bolt Mfg"},
    ], variables={"Industry": "Manufacturing"})
    _responded(users, "tester_at_example_com", [
        {"email": "quit@acme.com", "subject": "Re:", "reply_body": "Please remove me", "date": "2026-10-06"},
        {"email": "b@bolt.com", "subject": "Re:", "reply_body": "Sure, call me", "date": "2026-10-06"}])
    s = fa.AppState()
    s._user_email = "tester@example.com"
    with ui.card() as card:
        fa.p_shared_contacts(s, lambda: None)
    text = _page_text(card)
    assert "Shared Arena Contacts" in text
    assert "Ann Acme" in text and "720-555-0001" in text and "Bo Bolt" in text
    assert "quit@acme.com" not in text                      # said no
    assert "gallowayus.com" not in text                     # other team
    assert "2 companies · 2 people" in text
    assert "Colorado · Construction" in text and "Texas · Manufacturing" in text
    assert ">Replied<" in text
    selects = [e for e in card.descendants() if isinstance(e, ui.select)]
    assert len(selects) == 3                                # state, industry, sort
    assert "Colorado (1)" in selects[0].options.values()
    selects[0].set_value("CO")
    text = _page_text(card)
    assert "Showing 1 of 2 companies" in text and "Bo Bolt" not in text


@pytest.fixture
def _keys(tmp_path, monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_api_keys_path", lambda: tmp_path / "api_keys.json")


def _client():
    import flowdrip_app as fa
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    return TestClient(Starlette(routes=[
        Route("/api/v1/team_contacts", fa.api_team_contacts, methods=["GET"])]))


def test_api_team_contacts(with_user, _keys):
    import flowdrip_app as fa
    _bank(fa._BASE_DATA_DIR / "users")
    assert _client().get("/api/v1/team_contacts?q=galloway").status_code == 401
    key = fa._mint_api_key("mike@arena.net")
    h = {"X-API-Key": key}
    assert _client().get("/api/v1/team_contacts", headers=h).status_code == 400
    r = _client().get("/api/v1/team_contacts?q=gallowayus.com", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "gallowayus.com" and body["total_contacts"] == 2
    co = body["companies"][0]
    assert co["company"] == "Galloway & Company" and co["reps"] == ["Mike", "Sarah"]
    assert [c["email"] for c in co["contacts"]] == ["dana@gallowayus.com", "carl@gallowayus.com"]
    assert co["contacts"][0]["replied"] == "2026-10-06"
    assert co["contacts"][1]["phone_office"] == "303-555-0200"
    assert "before ZoomInfo" in body["note"]
    r = _client().get("/api/v1/team_contacts?q=nobody.example", headers=h)
    assert r.json()["companies"] == [] and "ZoomInfo" in r.json()["note"]
    # Another team's key sees nothing of Arena's bank.
    other = fa._mint_api_key("bob@other.com")
    assert _client().get("/api/v1/team_contacts?q=galloway", headers={"X-API-Key": other}).json()["companies"] == []


def test_connector_and_prompts_check_the_bank_first():
    import pathlib
    import zoominfo_pull as zp
    root = pathlib.Path(__file__).resolve().parent.parent
    mcp_src = (root / "mcp_server" / "dripdrop_mcp.py").read_text(encoding="utf-8")
    assert "async def team_contacts(company_or_domain: str" in mcp_src
    assert "CHECK THIS BEFORE ZOOMINFO" in mcp_src
    from mcp_server.dripdrop_client import DripDropClient
    assert callable(getattr(DripDropClient, "team_contacts", None))
    assert zp.ZI_PULL_RULE.startswith(zp.BANK_FIRST_RULE)
    assert "team_contacts" in zp.BANK_FIRST_RULE and "Shared Arena Contacts" in zp.BANK_FIRST_RULE
    assert "{" not in zp.ZI_PULL_RULE and "}" not in zp.ZI_PULL_RULE
    # Every Arena AI Prompt that pulls contacts now carries the rule.
    import ai_prompts as aip
    assert aip.ARENA.zi_rule == zp.ZI_PULL_RULE


# ── team-wide Do Not Contact ────────────────────────────────────────────

def test_team_dnc_sets_and_domain_blocks(tmp_path):
    _dnc(tmp_path, "sarah_at_arena_net", [
        {"email": "Opt@Out.com"}, {"email": "@blocked.com"}, {"email": "@gmail.com"}])
    _dnc(tmp_path, "bob_at_other_com", [{"email": "x@other.com"}])
    emails, domains = tcx.team_dnc(tmp_path, "mike@arena.net")
    assert emails == {"opt@out.com"}
    assert domains == {"blocked.com"}          # free-mail domain blocks stay personal
    assert tcx.team_dnc_for_dir(tmp_path, "mike_at_arena_net") == (emails, domains)
    assert tcx.team_dnc_for_dir(tmp_path, "nodomain") == (set(), set())


def test_domain_block_hides_everyone_at_that_company(tmp_path):
    _bank(tmp_path)
    _dnc(tmp_path, "luke_at_arena_net", [{"email": "@coolair.com", "source": "domain-block"}])
    bank = tcx.scan(tmp_path, "mike@arena.net")
    assert "jo@coolair.com" not in {c["email"] for c in bank["contacts"]}


def test_queue_skips_a_teammates_dnc(with_user, monkeypatch):
    import flowdrip_app as fa
    users = fa._BASE_DATA_DIR / "users"
    _dnc(users, "sarah_at_example_com", [{"email": "gone@acme.com"}, {"email": "@blocked.com"}])
    monkeypatch.setattr(fa, "_SERVER_MODE", True)
    emails, domains = fa._dnc_sets("tester@example.com")
    assert "gone@acme.com" in emails and "blocked.com" in domains
    monkeypatch.setattr(fa, "_dnc_sets", lambda owner=None: (emails, domains))
    assert fa.is_on_dnc("GONE@acme.com") and fa.is_on_dnc("anyone@blocked.com")
    assert not fa.is_on_dnc("fine@acme.com")


def test_scheduler_cancels_a_queued_email_a_teammate_opted_out(tmp_path, monkeypatch):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        pytest.skip("no tz database on this machine (Windows without tzdata)")
    import flowdrip_app as fa
    users = tmp_path / "users"
    mike = users / "mike_at_arena_net"
    mike.mkdir(parents=True)
    _dnc(users, "sarah_at_arena_net", [{"email": "gone@acme.com"}])
    queue = [
        {"id": "1", "to": "gone@acme.com", "status": "pending", "campaign": "A",
         "send_dt": "2020-01-01T09:00:00", "subject": "hi"},
        {"id": "2", "to": "ok@acme.com", "status": "pending", "campaign": "B",
         "send_dt": "2020-01-01T09:00:00", "subject": "hi"},
    ]
    (mike / "scheduled_queue.json").write_text(json.dumps(queue), encoding="utf-8")
    sent = []
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", tmp_path)
    monkeypatch.setattr(fa, "_server_send_one", lambda item, *a, **k: (sent.append(item["to"]) or (True, "")))
    monkeypatch.setattr(fa, "_maybe_handoff_4x4_graduate", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_SERVER_INTER_EMAIL_PAUSE", 0, raising=False)
    fa._next_campaign_send_at.clear()
    fa._server_scheduler_tick()
    assert sent == ["ok@acme.com"]
    after = {q["id"]: q for q in json.loads((mike / "scheduled_queue.json").read_text(encoding="utf-8"))}
    assert after["1"]["status"] == "cancelled" and after["1"]["cancel_reason"] == "Do Not Contact (team)"
    assert after["2"]["status"] == "sent"

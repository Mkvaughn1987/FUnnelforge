"""My Top 10: a recruiter's private target-company list. Auto-filled from
their own outreach when empty, hiring signals re-checked on every visit."""
import json
from datetime import datetime, timedelta

import team_campaigns as tc
import top_ten as tt

SIGS = [{"id": "reposted", "label": "role reposted"}, {"id": "urgent", "label": "urgent start"}]


def _data():
    return tt.load("does-not-exist.json")


def _fill(data, n, tier_start=0):
    for i in range(n):
        tt.add(data, {"company": f"Co {tier_start + i}"}, "2026-10-14")


# ── list ─────────────────────────────────────────────────────────────────

def test_add_fills_ten_then_backups_then_refuses():
    d = _data()
    _fill(d, 10)
    assert len(tt.active(d)) == 10
    c, msg = tt.add(d, {"company": "Eleven"})
    assert c["tier"] == "backup" and "backups" in msg
    _fill(d, 9, 100)
    c, msg = tt.add(d, {"company": "Too many"})
    assert c is None and "full" in msg


def test_add_refuses_duplicate_names():
    d = _data()
    tt.add(d, {"company": "Shaw Construction, Inc."})
    c, msg = tt.add(d, {"company": "shaw construction"})
    assert c is None and "already" in msg


def test_promote_swaps_last_active_out():
    d = _data()
    _fill(d, 10)
    b, _ = tt.add(d, {"company": "Backup One"})
    msg = tt.promote(d, b["id"])
    assert "Co 9 moved to backups" in msg
    assert [c["company"] for c in tt.active(d)][-1] == "Backup One"
    assert tt.backups(d)[0]["company"] == "Co 9"
    assert len(tt.active(d)) == 10


def test_move_and_demote():
    d = _data()
    _fill(d, 3)
    ids = [c["id"] for c in tt.active(d)]
    tt.move(d, ids[2], -1)
    assert [c["company"] for c in tt.active(d)] == ["Co 0", "Co 2", "Co 1"]
    tt.demote(d, ids[0])
    assert [c["company"] for c in tt.backups(d)] == ["Co 0"]


def test_save_load_round_trip_and_edit_marks_manual(tmp_path):
    p = tmp_path / "top_ten.json"
    d = _data()
    c, _ = tt.add(d, {"company": "Acme", "state": "colorado"})
    c["source"] = "auto"
    tt.set_focus(d, "Denver, CO", "Construction")
    tt.save(p, d)
    d2 = tt.load(p)
    assert d2["focus"] == {"market": "Denver, CO", "industry": "Construction"}
    assert d2["companies"][0]["state"] == "CO"
    tt.update(d2, c["id"], {"status": "Talking", "notes": "met PM"})
    assert d2["companies"][0]["source"] == "manual"
    assert d2["companies"][0]["status"] == "Talking"


# ── auto-fill ────────────────────────────────────────────────────────────

def _rec(company, owner="mike_at_arena_net", state="CO", industry="General Contracting",
         contacts=5, started="2026-10-01", domains=None, roles="Superintendent", geo="Denver, CO"):
    return {"company": company, "owner_dir": owner, "state": state, "industry": industry,
            "contacts": contacts, "started": started, "roles": roles, "geo": geo,
            "domains": domains or [company.lower().replace(" ", "") + ".com"]}


def test_rank_outreach_focus_and_order():
    recs = [
        _rec("Shaw Construction", contacts=10),
        _rec("Shaw Construction", contacts=8, started="2026-10-05"),
        _rec("Saunders", industry="Mechanical Contracting", contacts=3),
        _rec("Quiet Co", contacts=40),
        _rec("Texas GC", state="TX"),
        _rec("Acme Foods", industry="Manufacturing"),
        _rec("Teammate GC", owner="sarah_at_arena_net"),
    ]
    focus = {"market": "Denver, CO", "industry": "Construction"}
    ranked = tt.rank_outreach(recs, "mike_at_arena_net", focus, tc.state_of,
                              reply_domains={"saunders.com": 2})
    names = [r["company"] for r in ranked]
    assert names == ["Saunders", "Shaw Construction", "Quiet Co"]
    assert ranked[1]["campaigns"] == 2 and ranked[1]["contacts"] == 18


def test_fill_from_outreach_seeds_once_and_marks_auto():
    d = _data()
    assert tt.needs_seed(d)
    ranked = tt.rank_outreach([_rec(f"GC {i}") for i in range(14)], "mike_at_arena_net",
                              {}, tc.state_of)
    n = tt.fill_from_outreach(d, ranked, "2026-10-14")
    assert n == 14 and len(tt.active(d)) == 10 and len(tt.backups(d)) == 4
    c = tt.active(d)[0]
    assert c["source"] == "auto" and c["why"].startswith("From your outreach")
    assert c["city"] == "Denver" and c["state"] == "CO" and c["website"].endswith(".com")
    assert tt._city_of("Colorado Front Range (Denver metro, CO)") == ""
    assert tt._city_of("Denver / Henderson, CO") == "" and tt._city_of("Boulder, CO") == "Boulder"
    for x in list(d["companies"]):
        tt.remove(d, x["id"])
    assert not tt.needs_seed(d)            # emptied by hand: stays empty


# ── signals ──────────────────────────────────────────────────────────────

def test_stale_after_ttl():
    now = datetime(2026, 10, 14, 9)
    c = {"signals_checked": (now - timedelta(hours=3)).isoformat()}
    assert not tt.is_stale(c, now)
    c["signals_checked"] = (now - timedelta(hours=25)).isoformat()
    assert tt.is_stale(c, now)
    assert tt.is_stale({"signals_checked": ""}, now)


def test_due_only_active():
    d = _data()
    _fill(d, 11)
    assert len(tt.due_for_signals(d)) == 10


def test_failed_check_waits_an_hour():
    now = datetime(2026, 10, 14, 9)
    d = _data()
    c, _ = tt.add(d, {"company": "Shaw"})
    tt.record_signals(c, None, "timeout", now=now)
    assert tt.due_for_signals(d, now + timedelta(minutes=10)) == []
    assert tt.due_for_signals(d, now + timedelta(minutes=61)) == [c]


def test_prompt_names_company_focus_and_signals():
    d = _data()
    c, _ = tt.add(d, {"company": "Shaw", "city": "Denver", "state": "CO", "req": "Superintendent"})
    p = tt.signal_prompt(c, SIGS, "2026-10-14", {"market": "Denver, CO", "industry": "Construction"})
    assert "Shaw" in p and "Denver, CO" in p and "Construction" in p
    assert "- reposted: role reposted" in p and "Superintendent" in p and "Never" in p
    assert f"last {tt.FRESH_DAYS} days" in p and '"age_days"' in p


def test_parse_jobs_newest_first_with_age_from_date_or_board():
    from datetime import date
    reply = json.dumps({"summary": "", "jobs": [
        {"title": "Estimator", "location": "Denver, CO", "age_days": None, "date": "",
         "url": "https://www.indeed.com/viewjob?jk=2"},
        {"title": "Superintendent", "location": "Denver, CO", "age_days": 2, "pay": "$80k-$120k",
         "url": "https://www.indeed.com/viewjob?jk=1"},
        {"title": "Project Manager", "date": "2026-10-01", "url": "https://fake.example/x"},
        {"title": ""},
    ], "signals": []})
    out = tt.parse_signals(reply, SIGS, ["https://indeed.com/"], today=date(2026, 10, 14))
    assert [j["title"] for j in out["jobs"]] == ["Superintendent", "Project Manager", "Estimator"]
    assert [j["age_days"] for j in out["jobs"]] == [2, 13, None]
    assert out["jobs"][1]["url"] == ""                       # host never retrieved
    c = {"jobs": out["jobs"]}
    assert [j["title"] for j in tt.fresh_jobs(c)] == ["Superintendent"]


def test_freshest_across_top_ten_and_short_roles():
    d = _data()
    a, _ = tt.add(d, {"company": "Shaw"}); b, _ = tt.add(d, {"company": "Acme"})
    a["jobs"] = [{"title": "Super", "age_days": 5}, {"title": "PM", "age_days": 30}]
    b["jobs"] = [{"title": "Estimator", "age_days": 1}, {"title": "APM", "age_days": None}]
    assert [(c["company"], j["title"]) for c, j in tt.freshest(d)] == [("Acme", "Estimator"), ("Shaw", "Super")]
    assert tt.short_roles("Project Manager, Superintendent, APM, Senior PM, CM") == "Project Manager, Superintendent +3"
    assert tt.short_roles("Superintendent") == "Superintendent"
    assert tt.chip_text({"id": "several", "title": "A very long sentence about openings"}) == "Several openings"
    assert tt.chip_text({"id": "custom", "label": "x"}) == "x"


def test_parse_drops_unknown_ids_and_unseen_urls():
    reply = "Here you go:\n" + json.dumps({"summary": "Two open supers.", "signals": [
        {"id": "reposted", "title": "Superintendent", "detail": "Open 8 weeks",
         "date": "2026-09-01", "url": "https://www.indeed.com/viewjob?jk=1"},
        {"id": "urgent", "title": "PM", "url": "https://made-up.example/job"},
        {"id": "nonsense", "title": "x"}]})
    out = tt.parse_signals(reply, SIGS, ["https://indeed.com/viewjob?jk=1"])
    assert out["summary"] == "Two open supers."
    assert [s["id"] for s in out["signals"]] == ["reposted", "urgent"]
    assert out["signals"][0]["url"].startswith("https://www.indeed.com")
    assert out["signals"][1]["url"] == ""


def test_apply_check_keeps_user_edits_and_last_good_on_failure(tmp_path):
    p = tmp_path / "top_ten.json"
    d = _data()
    c, _ = tt.add(d, {"company": "Shaw"})
    tt.save(p, d)
    # user edits while the search runs
    d2 = tt.load(p); tt.update(d2, c["id"], {"notes": "call Tue"}); tt.save(p, d2)
    tt.apply_check(p, c["id"], {"summary": "s", "signals": [{"id": "urgent"}]})
    got = tt.load(p)["companies"][0]
    assert got["notes"] == "call Tue" and got["signal_summary"] == "s" and got["signals_checked"]
    tt.apply_check(p, c["id"], None, "timeout")
    got = tt.load(p)["companies"][0]
    assert got["signal_summary"] == "s" and got["signals_error"] == "timeout"


def test_pipeline_query_prefers_newest_posting_then_req():
    d = _data()
    c, _ = tt.add(d, {"company": "Shaw", "city": "Denver", "state": "CO",
                      "req": "Project Manager, Superintendent"})
    assert tt.pipeline_query(c) == ("Project Manager", "Denver, CO")
    c["jobs"] = [{"title": "Senior/Lead Estimator", "age_days": None},
                 {"title": "Field Engineer (Civil)", "age_days": 3}]
    assert tt.pipeline_query(c) == ("Field Engineer Civil", "Denver, CO")
    c["city"] = ""
    assert tt.pipeline_query(c)[1] == ""                     # bare state does not geocode
    tt.record_pipeline(c, 4, "Field Engineer Civil", "")
    assert c["pipeline"]["n"] == 4 and c["pipeline"]["checked"]


def test_ats_search_link_runs_the_search(monkeypatch):
    import ats
    seen = {}
    def _ks(q, **kw):
        seen.update(q=q, **kw); return [{"id": 1, "name": "A"}], {"origin": None}
    monkeypatch.setattr(ats, "keyword_search", _ks)
    monkeypatch.setattr(ats, "score_results", lambda q, rows: rows)
    st = {"view": "dashboard", "tearsheet_id": 9}
    ats._apply_search_link(st, " superintendent ", "Denver, CO")
    assert st["view"] == "candidates" and st["query"] == "superintendent"
    assert st["query_draft"] == "superintendent" and st["location"] == "Denver, CO"
    assert st["radius"] == ats.LINK_RADIUS_MI and "tearsheet_id" not in st
    assert seen["location"] == "Denver, CO" and seen["radius_mi"] == ats.LINK_RADIUS_MI
    assert seen["limit"] == ats.LINK_LIMIT
    assert len(st["results"]) == 1


def test_pipeline_count_shares_the_link_cap(monkeypatch):
    """The pill counts with the same cap the /ats deep link shows, and says
    '80+' rather than an exact number once it hits that cap."""
    import ats, flowdrip_app as fa
    seen = {}
    def _ks(q, **kw):
        seen.update(q=q, **kw); return [{"id": i} for i in range(kw["limit"])]
    monkeypatch.setattr(ats, "keyword_search", _ks)
    assert fa._top10_pipeline_count("Project Engineer", "") == ats.LINK_LIMIT
    assert seen["limit"] == ats.LINK_LIMIT and seen["location"] is None and seen["radius_mi"] is None
    assert fa._top10_pipeline_label(ats.LINK_LIMIT) == f"{ats.LINK_LIMIT}+"
    assert fa._top10_pipeline_label(4) == "4" and fa._top10_pipeline_label(0) == "0"
    assert fa._top10_pipeline_count("", "Denver, CO") == 0


def test_campaign_hits_by_name_or_domain():
    d = _data()
    a, _ = tt.add(d, {"company": "Shaw Construction"})
    b, _ = tt.add(d, {"company": "Different Name", "website": "https://www.saunders.com/"})
    hits = tt.campaign_hits(d["companies"], [
        _rec("Shaw Construction Inc", started="2026-10-01"),
        _rec("Shaw Construction", started="2026-10-09"),
        _rec("Saunders Construction", domains=["saunders.com"])])
    assert hits[a["id"]]["started"] == "2026-10-09"
    assert hits[b["id"]]["company"] == "Saunders Construction"


# ── app wiring ───────────────────────────────────────────────────────────

def test_sidebar_and_titles_carry_the_page():
    import flowdrip_app as fa
    assert ("top10", tt.PAGE_TITLE, "my_top10") in dict(fa.SIDEBAR_NAV)["ARENA TEAM"]
    assert fa.SIDEBAR_PAGE_ROW["my_top10"] == "top10"
    assert fa.SIDEBAR_TITLES["my_top10"] == tt.PAGE_TITLE
    assert "top10" in fa._SIDEBAR_ICONS
    assert any(label == tt.PAGE_TITLE and page == "my_top10" for _, label, page in fa.SALES_NAV)


def _page_text(root) -> str:
    bits = []
    for el in root.descendants():
        for attr in ("text", "content"):
            v = getattr(el, attr, None)
            if isinstance(v, str):
                bits.append(v)
    return "\n".join(bits)


def test_page_seeds_from_outreach_and_starts_signal_scan(with_user, monkeypatch):
    import flowdrip_app as fa
    from nicegui import ui
    users = fa._BASE_DATA_DIR / "users"
    camp_dir = users / "tester_at_example_com" / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    (camp_dir / "co_shaw.json").write_text(json.dumps({
        "name": "CO - Shaw Construction - Super", "start_date": datetime.now().date().isoformat(),
        "industry_category": "General Contracting",
        "variables": {"Geography": "Denver, CO", "TargetRole": "Superintendent"},
        "contacts": [{"email": "a@shawconstruction.net", "company": "Shaw Construction"}]}),
        encoding="utf-8")
    started = []
    monkeypatch.setattr(fa, "_top10_start_scan", lambda s, email, rf, ids=None: started.append(email))
    monkeypatch.setattr(fa, "_ats_allowed", lambda e: True)
    monkeypatch.setattr(fa, "_top10_pipeline_count", lambda q, loc: 7)
    s = fa.AppState()
    s._user_email = "tester@example.com"
    with ui.card() as card:
        fa.p_my_top10(s, lambda: None)
    text = _page_text(card)
    assert "My Top 10" in text and "Shaw Construction" in text
    assert "1 campaign" in text and "NEW POSTINGS" in text and "Check & add" in text
    assert text.count("Check pipeline") == 2 and "in pipeline" not in text   # toolbar + card pill
    # Once a check is recorded the pill becomes a link into the Pipeline search.
    p = users / "tester_at_example_com" / tt.FILE_NAME
    d = tt.load(p)
    tt.record_pipeline(d["companies"][0], 4, "Superintendent", "Denver, CO")
    tt.save(p, d)
    with ui.card() as card2:
        fa.p_my_top10(s, lambda: None)
    text2 = _page_text(card2)
    assert "4 in pipeline" in text2 and "/ats?q=Superintendent&amp;loc=Denver%2C+CO" in text2
    assert text2.count("Check pipeline") == 1                # only the toolbar's "for all"
    assert started == ["tester@example.com"] * 2            # one scan start per render
    saved = tt.load(users / "tester_at_example_com" / tt.FILE_NAME)
    assert saved["seeded"] and saved["companies"][0]["source"] == "auto"


# ── the short list at the top + checked adds ────────────────────────────

def test_split_query_tells_a_website_from_a_name():
    assert tt.split_query("weoneil.com") == ("", "weoneil.com")
    assert tt.split_query(" https://www.WEONeil.com/careers ") == ("", "weoneil.com")
    assert tt.split_query("W.E. O'Neil  Construction") == ("W.E. O'Neil Construction", "")
    assert tt.split_query("Howell") == ("Howell", "")
    assert tt.split_query("") == ("", "")


def test_verify_prompt_names_what_was_typed_and_the_desk():
    p = tt.verify_prompt("Shaw Construction", "", {"market": "Denver, CO", "industry": "Construction"},
                         "2026-11-04")
    assert "Company name as typed: Shaw Construction" in p and "Denver, CO Construction" in p
    assert "2026-11-04" in p and '"found"' in p and "Never guess a web address" in p
    assert "Website as typed: shaw.com" in tt.verify_prompt("", "shaw.com", None, "2026-11-04")


def test_parse_verify_keeps_only_a_site_the_search_returned_or_the_user_typed():
    reply = ('Here you go {"found": true, "company": "Shaw Construction", "website": "https://www.shawconstruction.net/", '
             '"city": "Denver", "state": "co", "industry": "General contractor", "about": "Builds things.", "note": ""}')
    got = tt.parse_verify(reply, ["https://www.shawconstruction.net/about", "https://linkedin.com/company/shaw"])
    assert got == {"found": True, "company": "Shaw Construction", "website": "shawconstruction.net",
                   "city": "Denver", "state": "CO", "lane": "General contractor",
                   "about": "Builds things.", "note": ""}
    # A web address the search never returned is dropped; the company still stands.
    unseen = tt.parse_verify(reply, ["https://linkedin.com/company/shaw"])
    assert unseen["found"] and unseen["website"] == ""
    # ... unless it is the one the user typed.
    assert tt.parse_verify(reply, [], "shawconstruction.net")["website"] == "shawconstruction.net"
    assert not tt.parse_verify('{"found": false, "company": ""}', [])["found"]
    assert not tt.parse_verify('{"found": true, "company": ""}', [])["found"]
    try:
        tt.parse_verify("no idea", [])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_add_to_top_makes_room_when_the_ten_is_full():
    d = _data()
    _fill(d, 10)
    c, msg = tt.add_to_top(d, {"company": "Newcomer"}, "2026-11-04")
    assert c["tier"] == "active" and [x["company"] for x in tt.active(d)][-1] == "Newcomer"
    assert len(tt.active(d)) == 10 and [x["company"] for x in tt.backups(d)] == ["Co 9"]
    assert "Newcomer is in your top 10" in msg and "Co 9 moved to backups" in msg
    # Room in the ten: it just lands there.
    d2 = _data()
    c2, msg2 = tt.add_to_top(d2, {"company": "Solo"})
    assert c2["tier"] == "active" and "top 10" in msg2
    assert tt.add_to_top(d2, {"company": "solo inc"})[0] is None      # duplicate still refused


def test_verified_survives_a_save_and_clears_when_the_name_or_site_changes(tmp_path):
    d = _data()
    c, _ = tt.add(d, {"company": "Shaw Construction", "website": "shawconstruction.net",
                      "verified": "2026-11-04T10:00:00"})
    p = tmp_path / tt.FILE_NAME
    tt.save(p, d)
    d = tt.load(p)
    c = d["companies"][0]
    assert c["verified"] == "2026-11-04T10:00:00"
    tt.update(d, c["id"], {"notes": "call Tuesday", "company": "Shaw Construction"})
    assert c["verified"]                                    # nothing that was checked changed
    tt.update(d, c["id"], {"website": "shaw.com"})
    assert c["verified"] == ""
    assert tt.find_name(d, "SHAW construction, Inc.") is c and tt.find_name(d, "") is None


def test_activity_counts_fresh_jobs_and_signals():
    d = _data()
    c, _ = tt.add(d, {"company": "Shaw"})
    assert tt.activity(c) == {"jobs": 0, "signals": 0, "checked": False, "failed": False}
    tt.record_signals(c, {"summary": "", "signals": [{"id": "urgent"}],
                          "jobs": [{"title": "Super", "age_days": 2}, {"title": "PM", "age_days": 40},
                                   {"title": "APM", "age_days": None}]})
    assert tt.activity(c) == {"jobs": 1, "signals": 1, "checked": True, "failed": False}


def test_site_live_only_tries_public_addresses(monkeypatch):
    import socket
    import flowdrip_app as fa
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 443))])
    assert fa._top10_site_live("intranet.example.com") is False
    assert fa._top10_site_live("") is False and fa._top10_site_live("not a site") is False


def test_verify_searches_the_open_web_and_checks_the_site(monkeypatch):
    import flowdrip_app as fa
    seen = {}

    def _research(client, prompt, website="", any_domain=False):
        seen.update(prompt=prompt, any_domain=any_domain)
        return ('{"found": true, "company": "Shaw Construction", "website": "shawconstruction.net", '
                '"city": "Denver", "state": "CO", "industry": "General contractor"}',
                ["https://shawconstruction.net/"])
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(fa, "_pdf_research_message", _research)
    monkeypatch.setattr(fa, "_top10_site_live", lambda site: site == "shawconstruction.net")
    got = fa._top10_verify("shaw construction", {"market": "Denver, CO", "industry": ""})
    assert got["found"] and got["company"] == "Shaw Construction" and got["site_live"] is True
    assert seen["any_domain"] is True and "shaw construction" in seen["prompt"]
    monkeypatch.setattr(fa, "_pdf_research_message", lambda *a, **k: (None, []))
    assert "error" in fa._top10_verify("shaw construction", {})
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    assert "error" in fa._top10_verify("shaw construction", {})


def test_research_message_any_domain_drops_the_allowed_list(monkeypatch):
    import flowdrip_app as fa
    tools = []

    class _Msg:
        content = []
        stop_reason = "end_turn"
    monkeypatch.setattr(fa, "_claude_create_with_retry",
                        lambda client, **kw: (tools.append(kw["tools"][0]), _Msg())[1])
    fa._pdf_research_message(None, "p", any_domain=True)
    fa._pdf_research_message(None, "p", "shawconstruction.net")
    assert "allowed_domains" not in tools[0]
    assert "shawconstruction.net" in tools[1]["allowed_domains"]


def _top10_page(fa, s):
    from nicegui import ui
    with ui.card() as card:
        fa.p_my_top10(s, lambda: None)
    return card


def test_short_list_leads_the_page_with_activity_add_box_and_jump_targets(with_user, monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_top10_start_scan", lambda s, email, rf, ids=None: None)
    monkeypatch.setattr(fa, "_ats_allowed", lambda e: False)
    p = fa._top10_path("tester@example.com")
    d = tt.load(p)
    a, _ = tt.add(d, {"company": "Shaw Construction", "website": "shawconstruction.net",
                      "verified": "2026-11-04T10:00:00"})
    b, _ = tt.add(d, {"company": "Howell"})
    tt.record_signals(a, {"summary": "", "signals": [{"id": "urgent", "label": "urgent"}],
                          "jobs": [{"title": "Superintendent", "age_days": 3}]})
    tt.record_signals(b, {"summary": "", "signals": [], "jobs": []})
    spare, _ = tt.add(d, {"company": "Spare Co"})
    tt.demote(d, spare["id"])
    d["seeded"] = True
    tt.save(p, d)
    s = fa.AppState()
    s._user_email = "tester@example.com"
    card = _top10_page(fa, s)
    text = _page_text(card)
    # The short list comes before the postings strip and the cards.
    assert text.index("Check & add") < text.index("NEW POSTINGS") < text.index("POSTINGS · LAST")
    assert "TOP 2" in text and "1 with new jobs · 1 hiring signal" in text
    assert "1 new job</span><span class=\"fd-t10-pill sig\">1 signal" in text and "Nothing new" in text
    assert "8 open spots" in text and "Move up Spare Co" in text
    assert "Top targets" not in text                      # the stat strip gave way to the list
    assert "✓ shawconstruction.net checked" in text
    ids = {el.props.get("id") for el in card.descendants()}
    assert {f"t10-{a['id']}", f"t10-{b['id']}"} <= ids     # what a click on a name scrolls to
    assert text.count("Yes, remove") == 0

    # One click on remove asks; nothing is deleted until the second.
    s._t10_ui.update(confirm=a["id"], confirm_at=__import__("time").time())
    text = _page_text(_top10_page(fa, s))
    assert "Remove Shaw Construction?" in text and text.count("Yes, remove") == 2   # list row + card
    assert len(tt.load(p)["companies"]) == 3
    s._t10_ui.update(confirm=a["id"], confirm_at=0.0)       # an old question does not linger
    assert "Yes, remove" not in _page_text(_top10_page(fa, s))


def test_add_panel_shows_what_the_lookup_found_before_saving(with_user, monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_top10_start_scan", lambda s, email, rf, ids=None: None)
    monkeypatch.setattr(fa, "_ats_allowed", lambda e: False)
    p = fa._top10_path("tester@example.com")
    d = tt.load(p)
    _fill(d, 10)
    d["seeded"] = True
    tt.save(p, d)
    s = fa.AppState()
    s._user_email = "tester@example.com"
    found = {"found": True, "company": "Shaw Construction", "website": "shawconstruction.net",
             "city": "Denver", "state": "CO", "lane": "General contractor",
             "about": "Commercial builder.", "note": "", "site_live": True}
    s._t10_ui = {"q": "shaw", "phase": "result", "asked": "shaw", "info": found,
                 "confirm": "", "confirm_at": 0.0}
    text = _page_text(_top10_page(fa, s))
    assert "Shaw Construction" in text and "shawconstruction.net" in text and "Denver, CO" in text
    assert "Add to top 10" in text and "Add to backups" in text       # the ten is full
    assert "moves Co 9 to backups" in text and "did not answer" not in text
    assert len(tt.load(p)["companies"]) == 10                         # nothing saved yet

    s._t10_ui.update(info=dict(found, site_live=False, company="Co 3"))
    text = _page_text(_top10_page(fa, s))
    assert "site did not answer" in text and "Co 3 is already on your list." in text
    assert "Add to top 10" not in text

    s._t10_ui.update(info={"found": False, "company": ""})
    text = _page_text(_top10_page(fa, s))
    assert "Could not confirm a company called shaw." in text and "Add as typed" in text
    s._t10_ui.update(info={"error": "boom"})
    text = _page_text(_top10_page(fa, s))
    assert "did not finish" in text and "Try again" in text and "boom" not in text
    s._t10_ui.update(phase="checking", info=None)
    assert "finding its website" in _page_text(_top10_page(fa, s))


def test_a_full_list_still_takes_a_checked_add(with_user, monkeypatch):
    d = _data()
    _fill(d, 20)
    assert tt.is_full(d)
    assert tt.add_to_top(d, {"company": "Newcomer"})[0] is None            # not without saying so
    c, msg = tt.add_to_top(d, {"company": "Newcomer"}, drop_last_backup=True)
    assert c["tier"] == "active" and len(tt.active(d)) == 10 and len(tt.backups(d)) == 10
    assert [x["company"] for x in tt.backups(d)][0] == "Co 9" and not tt.find_name(d, "Co 19")
    assert "Co 9 moved to backups" in msg and "Co 19 came off your backups" in msg
    # A duplicate never costs a backup.
    assert tt.add_to_top(d, {"company": "Newcomer"}, drop_last_backup=True)[0] is None
    assert len(d["companies"]) == 20

    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_top10_start_scan", lambda s, email, rf, ids=None: None)
    monkeypatch.setattr(fa, "_ats_allowed", lambda e: False)
    p = fa._top10_path("tester@example.com")
    d = _data()
    _fill(d, 20)
    d["seeded"] = True
    tt.save(p, d)
    s = fa.AppState()
    s._user_email = "tester@example.com"
    s._t10_ui = {"q": "shaw", "phase": "result", "asked": "shaw", "confirm": "", "confirm_at": 0.0,
                 "info": {"found": True, "company": "Shaw Construction", "website": "", "city": "",
                          "state": "", "lane": "", "about": "", "note": "", "site_live": False}}
    text = _page_text(_top10_page(fa, s))
    assert "moves Co 9 to backups and takes Co 19 off the end of them" in text
    assert "Add to top 10" in text and "Add to backups" not in text and "no website found" in text

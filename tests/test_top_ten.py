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
    s = fa.AppState()
    s._user_email = "tester@example.com"
    with ui.card() as card:
        fa.p_my_top10(s, lambda: None)
    text = _page_text(card)
    assert "My Top 10" in text and "Shaw Construction" in text
    assert "From your outreach" in text
    assert started == ["tester@example.com"]
    saved = tt.load(users / "tester_at_example_com" / tt.FILE_NAME)
    assert saved["seeded"] and saved["companies"][0]["source"] == "auto"

"""Current Running Campaigns: a company any teammate has in an outbound
campaign from the last 30 days (cancelled included) is skipped by new
launches. Regression for the 2026-10-06 Galloway double-run."""
import inspect
import json
from datetime import date

import team_campaigns as tc

TODAY = date(2026, 10, 6)


def _camp(root, owner_dir, name, start, emails, **extra):
    d = root / owner_dir / "Campaigns"
    d.mkdir(parents=True, exist_ok=True)
    camp = {"name": name, "start_date": start,
            "contacts": [{"email": e, "company": "Galloway & Company"} for e in emails]}
    camp.update(extra)
    p = d / (name.replace(" ", "_") + ".json")
    p.write_text(json.dumps(camp), encoding="utf-8")
    return p


def test_cancelled_campaign_by_same_rep_still_blocks(tmp_path):
    _camp(tmp_path, "mike_at_arena_net", "Galloway and Company", "2026-10-05",
          ["carl@gallowayus.com"], status="cancelled")
    recs = tc.team_campaigns(tmp_path, "mike@arena.net", today=TODAY)
    hits = tc.worked_domains(recs, exclude_name="CO - Galloway - Civil PE",
                             exclude_owner_dir="mike_at_arena_net")
    rec = tc.match(tc.email_domain("darren@gallowayus.com"), hits)
    assert rec and rec["status"] == "cancelled"
    assert "cancelled" in tc.describe(rec)


def test_teammate_campaign_blocks_but_other_teams_do_not(tmp_path):
    _camp(tmp_path, "sarah_at_arena_net", "Galloway", "2026-10-05", ["a@gallowayus.com"])
    _camp(tmp_path, "bob_at_other_com", "Acme", "2026-10-05", ["a@acme.com"])
    hits = tc.worked_domains(tc.team_campaigns(tmp_path, "mike@arena.net", today=TODAY))
    assert "gallowayus.com" in hits
    assert hits["gallowayus.com"]["owner"] == "Sarah"
    assert "acme.com" not in hits


def test_window_is_30_days(tmp_path):
    _camp(tmp_path, "mike_at_arena_net", "Old", "2026-09-05", ["a@old.com"])
    _camp(tmp_path, "mike_at_arena_net", "Edge", "2026-09-06", ["a@edge.com"])
    hits = tc.worked_domains(tc.team_campaigns(tmp_path, "mike@arena.net", today=TODAY))
    assert "old.com" not in hits
    assert "edge.com" in hits


def test_newsletters_and_free_mail_never_block(tmp_path):
    _camp(tmp_path, "mike_at_arena_net", "Colorado Construction Rundown", "2026-10-01",
          ["a@gallowayus.com"], evergreen_only=True, market_analysis=True)
    _camp(tmp_path, "mike_at_arena_net", "Gmail lead", "2026-10-01", ["someone@gmail.com"])
    hits = tc.worked_domains(tc.team_campaigns(tmp_path, "mike@arena.net", today=TODAY))
    assert hits == {}


def test_find_candidates_campaigns_never_block(tmp_path):
    _camp(tmp_path, "luke_at_arena_net", "Find Candidates - 2026-10-01", "2026-10-01",
          ["joe@indeedemail.com", "amy@stanfordalumni.org"], _chooser_origin="candidate")
    _camp(tmp_path, "luke_at_arena_net", "FC typed", "2026-10-01",
          ["bo@agcsd.org"], template_key="findcandidates")
    hits = tc.worked_domains(tc.team_campaigns(tmp_path, "mike@arena.net", today=TODAY))
    assert hits == {}
    assert not tc.is_outbound({"_chooser_origin": "candidate"})
    assert tc.is_outbound({"aicb_camp_type": "fivebyfive"})


def test_campaign_never_blocks_itself(tmp_path):
    p = _camp(tmp_path, "mike_at_arena_net", "Galloway", "2026-10-05", ["a@gallowayus.com"])
    recs = tc.team_campaigns(tmp_path, "mike@arena.net", today=TODAY)
    assert tc.worked_domains(recs, exclude_path=str(p)) == {}


def test_subdomain_matches():
    hits = {"acme.com": {"path": "x"}}
    assert tc.match("mail.acme.com", hits)
    assert not tc.match("notacme.com", hits)


def test_cache_sees_new_files(tmp_path):
    assert tc.team_campaigns(tmp_path, "mike@arena.net", today=TODAY) == []
    _camp(tmp_path, "mike_at_arena_net", "New", "2026-10-06", ["a@new.com"])
    assert len(tc.team_campaigns(tmp_path, "mike@arena.net", today=TODAY)) == 1


def test_queue_skips_already_worked_contacts(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    captured = {}

    class _StubFFC:
        def add_to_queue(self, items, queue_path=None):
            captured["items"] = items
    monkeypatch.setattr(fa, "_FUNNELFORGE_OK", True)
    monkeypatch.setattr(fa, "_ffc", _StubFFC())
    monkeypatch.setattr(fa, "load_dnc", lambda: [])
    monkeypatch.setattr(fa, "load_responded", lambda: [])
    monkeypatch.setattr(fa, "load_client_blocklist", lambda: [])
    monkeypatch.setattr(fa, "_load_company_profile", lambda: {})
    monkeypatch.setattr(fa, "_load_signature_text", lambda: "")
    monkeypatch.setattr(fa, "validate_contact_emails", lambda contacts: (contacts, []))
    rec = {"path": "/x/Galloway.json", "company": "Galloway & Company", "owner": "Sarah Henze",
           "campaign": "Galloway & Company", "started": "2026-10-05", "status": "active"}
    monkeypatch.setattr(fa, "_team_worked_hits", lambda *a, **k: {"gallowayus.com": rec})

    camp = {
        "name": "CO - Galloway - Civil PE", "_owner_email": "tester@example.com",
        "contacts": [{"email": "darren@gallowayus.com"}, {"email": "lead@other.com"}],
        "emails": [{"name": "Email 1", "subject": "Hi", "body": "Hello",
                    "step_type": "email_auto", "delay_days": 0, "time": "09:00",
                    "touch_number": 1}],
        "variables": {},
    }
    fa.queue_campaign_emails(camp)
    to = {it.get("to") for it in captured.get("items", [])}
    assert "lead@other.com" in to
    assert "darren@gallowayus.com" not in to


def test_queue_does_not_apply_to_newsletters():
    import flowdrip_app as fa
    src = inspect.getsource(fa.queue_campaign_emails)
    assert "if _tc.is_outbound(camp):" in src
    assert "_team_worked_hits(" in src


def test_api_checks_before_ai_work():
    import flowdrip_app as fa
    src = inspect.getsource(fa.api_create_campaign)
    assert src.index("_split_team_worked(") < src.index("anthropic.Anthropic(")
    assert '"skipped": True' in src


def test_sidebar_has_running_campaigns():
    import flowdrip_app as fa
    rows = [r for _g, items in fa.SIDEBAR_NAV for r in items]
    assert ("running", tc.PAGE_TITLE, "running_campaigns") in rows
    assert tc.PAGE_TITLE == "Arena Running Campaigns"
    assert fa.SIDEBAR_TITLES["running_campaigns"] == tc.PAGE_TITLE
    assert any(lbl == tc.PAGE_TITLE and key == "running_campaigns"
               for _i, lbl, key in fa.SALES_NAV)
    assert fa.SIDEBAR_PAGE_ROW["running_campaigns"] == "running"
    assert "running" in fa._SIDEBAR_ICONS
    assert callable(fa.p_running_campaigns)
    assert "fd-rc" in fa._rc_css()


# ── Arena Running Campaigns page: state / industry / filters ──────────────

def test_state_of_reads_codes_names_and_metros():
    assert tc.state_of("Denver, CO") == "CO"
    assert tc.state_of("Colorado") == "CO"
    assert tc.state_of("CA - Tilden-Coil - PM Super - 2026-09-15") == "CA"
    assert tc.state_of("Arizona - Willmeng - PM-Superintendent (Targeted)") == "AZ"
    assert tc.state_of("Raleigh, North Carolina") == "NC"
    assert tc.state_of("Torrance, CA (Los Angeles metro)") == "CA"
    assert tc.state_of("Sunnyvale / San Francisco, CA") == "CA"
    assert tc.state_of("Howard Building Corporation - LA County Construction W38") == "CA"
    assert tc.state_of("Kansas City") == ""          # straddles KS / MO
    assert tc.state_of("MPCBlast - Empire Cat - Sales") == ""
    assert tc.state_of("PM Super") == ""              # PM is not a state
    assert tc.state_of("") == ""


def test_resolve_state_prefers_name_prefix_then_geography_then_contacts():
    assert tc.resolve_state({"name": "TX - Acme - Estimator",
                             "variables": {"Geography": "Denver, CO"}}) == "TX"
    assert tc.resolve_state({"name": "Acme - Estimator Campaign",
                             "variables": {"Geography": "Phoenix, AZ"}}) == "AZ"
    assert tc.resolve_state({"name": "Acme Campaign", "variables": {},
                             "contacts": [{"email": "a@acme.com", "city": "Boise", "state": "Idaho"}]}) == "ID"
    assert tc.resolve_state({"name": "Acme Campaign", "variables": {}}) == ""


def test_industry_buckets_free_text_and_falls_back_to_roles():
    assert tc.industry_of({"variables": {"Industry": "Healthcare/OSHPD Construction"}}) == "Healthcare Construction"
    assert tc.industry_of({"variables": {"Industry": "Package Manufacturing"}}) == "Manufacturing"
    assert tc.industry_of({"variables": {"Industry": "Civil Engineering Consulting"}}) == "Civil & Engineering"
    assert tc.industry_of({"variables": {"Industry": "Healthcare"}}) == "Healthcare"
    assert tc.industry_of({"variables": {"Industry": "", "TargetRole": "Plant Manager, Quality Manager"}}) == "Manufacturing"
    assert tc.industry_of({"name": "Fresca Foods Talent Strategy Campaign", "variables": {}}) == "Manufacturing"
    assert tc.industry_of({"variables": {"Industry": "Insurance"}}) == "Accounting & Finance"
    assert tc.industry_of({"name": "__cardcheck__", "variables": {}}) == tc.INDUSTRY_OTHER


def test_construction_splits_into_trade_buckets():
    # Real spellings from the Industry variable on prod.
    def ind(text):
        return tc.industry_of({"variables": {"Industry": text}})
    assert ind("Mechanical Construction") == "Mechanical Contracting"
    assert ind("Construction / Mechanical Contracting - Data Centers") == "Mechanical Contracting"
    assert ind("Mechanical and Plumbing Contracting") == "Mechanical Contracting"
    assert ind("Commercial HVAC Service") == "Mechanical Contracting"
    assert ind("Commercial Electrical Contracting") == "Electrical Contracting"
    assert ind("Commercial Construction / Electrical Contracting") == "Electrical Contracting"
    assert ind("Electrical Contracting / Commercial Construction") == "Electrical Contracting"
    assert ind("Commercial General Contracting") == "General Contracting"
    assert ind("General Construction") == "General Contracting"
    assert ind("Commercial Construction") == "General Contracting"
    assert ind("Small to midsize general contractors") == "General Contracting"
    # Plain or specialty construction stays in the Construction bucket.
    assert ind("Construction") == "Construction"
    assert ind("Aggregates and ready-mix concrete") == "Construction"
    # Niches: equipment dealers, OSHPD healthcare builders, data centers.
    assert ind("Heavy Equipment and Construction") == "Heavy Equipment & Rental"
    assert ind("Construction equipment rental") == "Heavy Equipment & Rental"
    assert ind("Construction Equipment (John Deere Dealer)") == "Heavy Equipment & Rental"
    assert ind("Healthcare/OSHPD Construction") == "Healthcare Construction"
    assert ind("Healthcare OSHPD HCAI Construction") == "Healthcare Construction"
    assert tc.industry_of({"name": "Advanced Medical Builders - Healthcare C",
                           "variables": {}}) == "Healthcare Construction"
    assert ind("Mission Critical / Data Center Construction") == "Data Center / Mission Critical"
    assert ind("Commercial Construction / Mission Critical") == "Data Center / Mission Critical"
    # A trade beats the niche it works in.
    assert ind("Construction / Mechanical Contracting - Data Centers") == "Mechanical Contracting"
    assert ind("Car Dealership") == "Automotive"
    assert ind("Hospital") == "Healthcare"
    # Engineering firms are not contractors.
    assert ind("Electrical Engineering") == "Civil & Engineering"


def test_category_picked_at_creation_beats_the_free_text():
    camp = {"industry_category": "general contracting",
            "variables": {"Industry": "Construction"}}
    assert tc.industry_of(camp) == "General Contracting"
    assert tc.category_label("Mechanical Contracting") == "Mechanical Contracting"
    assert tc.category_label("  electrical contracting ") == "Electrical Contracting"
    # Anything off the list is ignored and the free text decides.
    assert tc.category_label("Roofing") == ""
    assert tc.industry_of({"industry_category": "Roofing",
                           "variables": {"Industry": "Construction"}}) == "Construction"
    assert tc.INDUSTRY_OTHER in tc.INDUSTRY_CHOICES
    assert "Construction" in tc.INDUSTRY_CHOICES


def test_company_overrides_round_trip_and_apply(tmp_path):
    users = tmp_path / "users"
    _camp(users, "mike_at_arena_net", "Otto", "2026-10-05", ["a@ottoconstruction.com"],
          variables={"Industry": "Construction"})
    _camp(users, "mike_at_arena_net", "Acme", "2026-10-05", ["a@acme.com"],
          variables={"Industry": "Package Manufacturing"})
    path = tc.overrides_path(users, "mike@arena.net")
    assert path == tmp_path / "teams" / "arena_net" / "industry_overrides.json"
    assert tc.load_overrides(path) == {}

    tc.save_overrides(path, {"ottoconstruction.com": "General Contracting",
                             "bad.com": "Not A Category"})
    assert tc.load_overrides(path) == {"ottoconstruction.com": "General Contracting"}
    tc.save_overrides(path, {"acme.com": "Other"})          # merges, never drops
    assert set(tc.load_overrides(path)) == {"ottoconstruction.com", "acme.com"}

    rows = tc.group_by_company(tc.team_campaigns(users, "mike@arena.net", today=TODAY))
    assert [r["industry"] for r in rows if r["key"] == "ottoconstruction.com"] == ["Construction"]
    assert tc.needs_sort(rows) == [r for r in rows if r["key"] == "ottoconstruction.com"]
    tc.apply_overrides(rows, tc.load_overrides(path))
    by = {r["key"]: r["industry"] for r in rows}
    assert by == {"ottoconstruction.com": "General Contracting", "acme.com": "Other"}
    # A company the AI already sorted is not offered again, even as Other.
    assert tc.needs_sort(rows) == []


def test_sort_prompt_and_parse_picks():
    rows = [{"key": "ottoconstruction.com", "company": "Otto Construction",
             "domains": ["ottoconstruction.com"], "industry": "Construction",
             "camps": [{"campaign": "Otto - PM", "roles": "Project Manager",
                        "industry_text": "Construction"}]}]
    prompt = tc.sort_prompt(rows)
    assert "Otto Construction" in prompt and "ottoconstruction.com" in prompt
    assert "Project Manager" in prompt
    for label in tc.INDUSTRY_CHOICES:
        assert label in prompt
    schema = tc.sort_schema()
    assert schema["properties"]["picks"]["items"]["properties"]["category"]["enum"] == list(tc.INDUSTRY_CHOICES)
    text = json.dumps({"picks": [{"id": 1, "category": "General Contracting"},
                                 {"id": 9, "category": "General Contracting"},
                                 {"id": 1, "category": "Nonsense"}]})
    assert tc.parse_picks(text, rows) == {"ottoconstruction.com": "General Contracting"}
    assert tc.parse_picks("not json", rows) == {}


def test_summary_carries_state_industry_and_kind(tmp_path):
    _camp(tmp_path, "mike_at_arena_net", "CO - Galloway - Civil PE", "2026-10-05",
          ["a@gallowayus.com"], aicb_camp_type="fivebyfive",
          variables={"Industry": "Civil Engineering", "Geography": "Denver, CO",
                     "TargetRole": "Civil PE"})
    (rec,) = tc.team_campaigns(tmp_path, "mike@arena.net", today=TODAY)
    assert rec["state"] == "CO"
    assert rec["industry"] == "Civil & Engineering"
    assert rec["kind"] == "fivebyfive" and rec["kind_label"] == "Arena 5×5"
    assert rec["geo"] == "Denver, CO" and rec["roles"] == "Civil PE"


def _rec(company, dom, owner_dir, started, state="CO", industry="Construction",
         kind="fivebyfive", status="active", campaign=None, roles=""):
    return {"campaign": campaign or company, "company": company, "domains": [dom],
            "contacts": 3, "owner_dir": owner_dir, "owner": tc.owner_from_dir(owner_dir),
            "started": started, "status": status, "path": f"/x/{dom}.json",
            "state": state, "industry": industry, "kind": kind,
            "kind_label": tc.kind_label(kind), "geo": "", "roles": roles}


def test_group_by_company_merges_campaigns_and_flags_two_reps():
    recs = [_rec("Acme", "acme.com", "luke_at_arena_net", "2026-10-01"),
            _rec("Acme", "acme.com", "sarah_at_arena_net", "2026-09-20", status="cancelled",
                 campaign="Acme again", state=""),
            _rec("Bolt", "bolt.com", "luke_at_arena_net", "2026-10-03", state="TX",
                 industry="Manufacturing", kind="fourbyfour")]
    rows = tc.group_by_company(recs)
    assert [r["company"] for r in rows] == ["Bolt", "Acme"]
    acme = rows[1]
    assert acme["reps"] == ["luke_at_arena_net", "sarah_at_arena_net"]
    assert acme["state"] == "CO"                       # newest campaign that names one
    assert acme["opens"] == "2026-10-31"
    assert acme["running"] is True
    assert [c["campaign"] for c in acme["camps"]] == ["Acme", "Acme again"]


def test_filter_rows_by_rep_state_industry_kind_status_and_search():
    rows = tc.group_by_company([
        _rec("Acme", "acme.com", "luke_at_arena_net", "2026-10-01", roles="Estimator"),
        _rec("Bolt", "bolt.com", "sarah_at_arena_net", "2026-10-03", state="TX",
             industry="Manufacturing", kind="fourbyfour", status="cancelled"),
    ])
    names = lambda rs: sorted(r["company"] for r in rs)
    assert names(tc.filter_rows(rows, rep="luke_at_arena_net")) == ["Acme"]
    assert names(tc.filter_rows(rows, state="TX")) == ["Bolt"]
    assert names(tc.filter_rows(rows, industry="Construction")) == ["Acme"]
    assert names(tc.filter_rows(rows, kind="fourbyfour")) == ["Bolt"]
    assert names(tc.filter_rows(rows, status="running")) == ["Acme"]
    assert names(tc.filter_rows(rows, status="cancelled")) == ["Bolt"]
    assert names(tc.filter_rows(rows, q="estimator")) == ["Acme"]   # target roles searchable
    assert names(tc.filter_rows(rows, q="sarah")) == ["Bolt"]
    assert names(tc.filter_rows(rows, rep="luke_at_arena_net", state="TX")) == []


def _page_text(root) -> str:
    bits = []
    for el in root.descendants():
        for attr in ("text", "content"):
            v = getattr(el, attr, None)
            if isinstance(v, str):
                bits.append(v)
    return "\n".join(bits)


def test_page_renders_and_filters(with_user, monkeypatch):
    import flowdrip_app as fa
    from nicegui import ui
    users = fa._BASE_DATA_DIR / "users"
    _camp(users, "tester_at_example_com", "CO - Acme - Estimator", "2026-10-05",
          ["a@acme.com"], aicb_camp_type="fivebyfive",
          variables={"Industry": "Construction", "Geography": "Denver, CO", "TargetRole": "Estimator"})
    _camp(users, "sarah_at_example_com", "TX - Bolt - Plant Manager", "2026-10-01",
          ["b@bolt.com"], aicb_camp_type="fourbyfour", status="cancelled",
          variables={"Industry": "Manufacturing"})
    monkeypatch.setattr(tc, "date", _FixedDate)
    s = fa.AppState()
    s._user_email = "tester@example.com"
    with ui.card() as card:
        fa.p_running_campaigns(s, lambda: None)
    text = _page_text(card)
    assert "Arena Running Campaigns" in text
    assert "Acme" in text and "Bolt" in text
    assert "Colorado · Construction" in text and "Texas · Manufacturing" in text
    assert "Cancelled" in text and "Running" in text
    selects = [e for e in card.descendants() if isinstance(e, ui.select)]
    assert len(selects) == 4                      # state, industry, type, sort
    state_sel = selects[0]
    assert "Colorado (1)" in state_sel.options.values()
    state_sel.set_value("CO")
    text = _page_text(card)
    assert "Acme" in text and "Bolt" not in text
    assert "Showing 1 of 2 companies" in text
    state_sel.set_value("")
    assert "Bolt" in _page_text(card)
    # Acme only says "Construction", so the page offers the AI sort.
    assert "1 company says only \"Construction\"" in text
    assert "Sort them with AI" in text

    # Once the team file places it, the row shows the pick and the offer goes.
    tc.save_overrides(tc.overrides_path(users, "tester@example.com"),
                      {"acme.com": "General Contracting"})
    with ui.card() as card2:
        fa.p_running_campaigns(s, lambda: None)
    text2 = _page_text(card2)
    assert "Colorado · General Contracting" in text2
    assert "Sort them with AI" not in text2


def test_ai_sort_reads_structured_picks(monkeypatch):
    import flowdrip_app as fa
    calls = []

    class _Block:
        type = "text"
        text = json.dumps({"picks": [{"id": 1, "category": "Mechanical Contracting"}]})

    class _Msg:
        stop_reason = "end_turn"
        content = [_Block()]

    def _fake_create(client, **kw):
        calls.append(kw)
        return _Msg()
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(fa, "_claude_create_with_retry", _fake_create)
    rows = [{"key": "acme-mech.com", "company": "Acme Mechanical", "domains": ["acme-mech.com"],
             "industry": "Construction", "camps": []}]
    assert fa._rc_ai_sort(rows) == {"acme-mech.com": "Mechanical Contracting"}
    fmt = calls[0]["extra_body"]["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"] == tc.sort_schema()
    assert calls[0]["model"] == fa._RC_SORT_MODEL


class _FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 6)


def test_sort_facets_opening_and_csv():
    rows = tc.group_by_company([
        _rec("Acme", "acme.com", "luke_at_arena_net", "2026-10-01"),
        _rec("Bolt", "bolt.com", "sarah_at_arena_net", "2026-09-08", state="TX"),
    ])
    assert [r["company"] for r in tc.sort_rows(rows, "opens")] == ["Bolt", "Acme"]
    assert [r["company"] for r in tc.sort_rows(rows, "name")] == ["Acme", "Bolt"]
    assert tc.facet_counts(rows, "state") == {"CO": 1, "TX": 1}
    assert tc.facet_counts(rows, "reps")["luke_at_arena_net"] == 1
    # Bolt opens 2026-10-08, two days after TODAY; Acme opens on the 31st.
    assert [r["company"] for r in tc.opening_within(rows, 7, today=TODAY)] == ["Bolt"]
    csv_text = tc.rows_csv(rows)
    assert csv_text.splitlines()[0].startswith("Company,Domains,State,Industry,Rep")
    assert "Bolt,bolt.com,TX,Construction,Sarah,Bolt,Arena 5×5,Running,2026-09-08,2026-10-08" in csv_text

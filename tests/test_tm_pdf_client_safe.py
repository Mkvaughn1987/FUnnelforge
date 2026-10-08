"""ThriveModal PDFs sent to prospects: no internal market labels, fixed
titles, and a cost comparison without a salary is never attached
(S+B James Construction, 2026-09-19: "INCOMPLETE WORKSHEET" and
"Construction is an exploratory vertical for ThriveModal" both went out)."""
import json
import types

import flowdrip_app as fa


def test_playbook_titles_map_to_an_occupation_without_a_model():
    assert fa._tm_soc_for_role(None, "Project Coordinator")[0] == "131199"
    assert fa._tm_soc_for_role(None, "Estimator")[0] == "131051"
    assert fa._tm_soc_for_role(None, "Project Accountant")[0] == "132011"
    assert fa._tm_soc_for_role(None, "Medical Biller")[0] == "433021"
    # Benchmark rows still win over the keyword table.
    assert fa._tm_soc_for_role(None, "Bookkeeper")[0] == "433031"
    assert fa._tm_soc_for_role(None, "Superintendent") is None


def test_internal_market_labels_are_scrubbed_and_title_is_fixed():
    data = {
        "title": "White City Construction Offshore Role Blueprint",
        "badge": "EXPLORATORY MARKET TEST",
        "intro": ("Construction is an exploratory vertical for ThriveModal, "
                  "and coordinators are a fit. This blueprint outlines the role."),
        "sections": [{"heading": "x", "type": "bullets",
                      "items": ["We watch this market closely as a test market.",
                                "Scheduling moves offshore."]}],
        "cta": "Let's talk.",
    }
    fa._tm_fix_pdf_labels("tm_role_blueprint",
                          {"company": "S+B James Construction"}, data)
    assert data["title"] == "Offshore Role Blueprint - S+B James Construction"
    assert data["badge"] == "ROLE DESIGN"
    flat = json.dumps(data).lower()
    assert "explorator" not in flat and "test market" not in flat
    assert data["intro"] == "This blueprint outlines the role."
    assert data["sections"][0]["items"] == ["", "Scheduling moves offshore."]


def test_prompt_tells_the_model_labels_are_internal():
    rules = fa._tm_rich_rules({})
    assert "internal sales planning" in rules
    assert "Assuming <company>" in rules


def test_no_salary_cost_comparison_is_swapped_for_how_we_work(monkeypatch, tmp_path):
    def fake_gen(client, kind, ctx, research_context="", style_guide=""):
        if kind == "tm_cost_compare":
            return fa._tm_auto_cost_pdf_data("Co", "Superintendent", "", None)
        return {"title": "t", "badge": "b", "intro": "i", "sections": [], "cta": ""}

    monkeypatch.setattr(fa, "_generate_rich_pdf_data", fake_gen)
    fake_mod = types.ModuleType("arena_pdfs")
    fake_mod.build_custom_pdf = lambda path, build: open(path, "wb").close()
    monkeypatch.setitem(__import__("sys").modules, "arena_pdfs", fake_mod)
    out = fa._tm_build_campaign_pdfs(
        ["tm_role_blueprint", "tm_cost_compare"], "Co", "Superintendent",
        "White City, OR", client=object(), dest_dir=tmp_path)
    assert set(out) == {"tm_role_blueprint", "tm_how_it_works"}
    assert not any("Staffing Cost" in f for f in out.values())


def test_bls_refusal_is_not_cached_as_no_data(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(fa, "_TM_BLS_VALUES", {"x": None})
    monkeypatch.setattr(fa, "_TM_BLS_DISK", tmp_path / "v.json")

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({"status": "REQUEST_NOT_PROCESSED",
                               "message": ["daily threshold reached"]}).encode()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: R())
    assert fa._tm_bls_annual_medians(["OEUS1"]) == {}
    assert "OEUS1" not in fa._TM_BLS_VALUES  # retried next time
    assert "BLS API refused" in capsys.readouterr().out


# ── five-role Staffing Cost Comparison ─────────────────────────────────────

def _fake_local(client, roles, location):
    return {r: {"salary": 60000.0 + 1000 * i, "basis": "median",
                "area": "Medford, OR metro area",
                "occupation": f"Occ {r} (SOC 11-1111)",
                "source": "BLS OEWS May 2025", "url": "https://www.bls.gov/x"}
            for i, r in enumerate(roles)}


def test_cost_comparison_names_five_roles_lead_role_first(monkeypatch):
    monkeypatch.setattr(fa, "_tm_bls_local_salaries", _fake_local)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    d = fa._tm_multi_cost_pdf_data(None, "S+B James Construction",
                                   "Project Coordinator", "White City, OR",
                                   "Construction")
    rows = d["sections"][0]["items"]
    roles = [r[0] for r in rows[1:-1]]
    assert len(roles) == 5 and roles[0] == "Project Coordinator"
    assert "Estimator" in roles  # from the construction list
    assert rows[-1][0] == "All 5 roles"
    # Hourly, our rate first, then what they pay, then the saving (Mike,
    # 2026-10-08); the totals row adds up as printed.
    assert rows[0] == ["Role", "Our Rate / Hour", "In-House Cost / Hour",
                       "You Save / Hour", "You Save / Year"]
    money = lambda t: float(t.replace("USD", "").replace("$", "").replace(",", ""))
    for r in rows[1:-1]:
        assert money(r[3]) == money(r[2]) - money(r[1])
        assert money(r[1]) < money(r[2]) < 100      # per hour, not per year
        assert money(r[4]) > 10000                   # per year
    for col in (1, 2, 3, 4):
        assert money(rows[-1][col]) == sum(money(r[col]) for r in rows[1:-1])
    assert d["badge"] == fa._TM_COST_BADGE and d["_worksheet"]
    how = next(s for s in d["sections"] if s["heading"] == "Basis of Calculation")
    assert not any("Philippine" in i for i in how["items"])
    assert any("2,080" in i for i in how["items"])
    assert "Sources" not in [s["heading"] for s in d["sections"]]
    assert "Here's" not in json.dumps(d)


def test_cost_comparison_for_a_staffing_firm_lists_recruiting_roles(monkeypatch):
    """A recruiting firm shares the home-care vertical, but its back office
    is sourcing and recruiting support, not care scheduling."""
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    roles = fa._tm_cost_roles("Sourcer", "Recruiting", "Acme Staffing")
    assert roles[:3] == ["Sourcer", "Recruiter", "Recruiting Coordinator"]
    assert "Care Scheduler" not in roles
    # Every staffing title prices without a model call.
    for r in fa._TM_STAFFING_COST_ROLES:
        assert fa._tm_soc_for_role(None, r) is not None, r
    # Plain "Recruiting" (no vertical keyword) gets the same list.
    roles = fa._tm_cost_roles("Sourcer", "Recruiting", "")
    assert roles[1] == "Recruiter" and "Care Scheduler" not in roles
    # A real home-care agency keeps its own list, even when called a
    # staffing agency.
    roles = fa._tm_cost_roles("", "Home Care Staffing", "Comfort Keepers")
    assert roles[0] == "Care Scheduler"
    # The customer quote is one bullet, so the renderer cannot split it.
    secs = {s["heading"]: s for s in fa._tm_cost_extra_sections()}
    assert secs["What Customers Report"]["type"] == "bullets"
    assert len(secs["What Customers Report"]["items"]) == 1


def test_clause_dashes_become_commas_but_ranges_stay():
    data = {"intro": "Here is what it looks like—and what lands on you.",
            "sections": [{"heading": "x", "type": "bullets",
                          "items": ["Savings of 60-70% - depending on the role.",
                                    "$40,000 - $50,000 a year"]}],
            "cta": "Talk to us – today."}
    fa._tm_fix_pdf_labels("tm_how_it_works", {"company": "Co"}, data)
    assert data["intro"] == "Here is what it looks like, and what lands on you."
    assert data["sections"][0]["items"] == [
        "Savings of 60-70%, depending on the role.", "$40,000 - $50,000 a year"]
    assert data["cta"] == "Talk to us, today."
    assert data["badge"] == "ENGAGEMENT OVERVIEW"


def test_pdf_date_has_no_leading_zero_on_inboxslide_only(monkeypatch):
    import datetime
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    assert fa._pdf_date_label(datetime.date(2026, 10, 8)) == "October 8, 2026"
    assert fa._pdf_date_label(datetime.date(2026, 12, 25)) == "December 25, 2026"
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    assert fa._pdf_date_label(datetime.date(2026, 10, 8)) == "October 08, 2026"


def test_cost_comparison_skips_duplicate_occupations(monkeypatch):
    def same_occ(client, roles, location):
        out = _fake_local(client, roles, location)
        for r in ("Bookkeeper", "Accounts Payable Specialist"):
            if r in out:
                out[r]["occupation"] = "Bookkeeping Clerks (SOC 43-3031)"
        return out
    monkeypatch.setattr(fa, "_tm_bls_local_salaries", same_occ)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    d = fa._tm_multi_cost_pdf_data(None, "Co", "", "", "Accounting")
    roles = [r[0] for r in d["sections"][0]["items"][1:-1]]
    assert not ("Bookkeeper" in roles and "Accounts Payable Specialist" in roles)


def test_cost_comparison_with_nothing_priced_is_the_seller_note(monkeypatch):
    monkeypatch.setattr(fa, "_tm_bls_local_salaries", lambda *a: {})
    monkeypatch.setattr(fa, "_tm_lookup_local_salary", lambda *a: None)
    monkeypatch.setattr(fa, "_TM_VERTICAL_COST_ROLES",
                        {k: ["Superintendent"] for k in fa._TM_VERTICAL_COST_ROLES})
    d = fa._tm_multi_cost_pdf_data(None, "Co", "Superintendent", "", "")
    assert d["badge"] == "INCOMPLETE WORKSHEET" and d["_worksheet"] is None


def test_a_title_with_and_is_one_role(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    roles = fa._tm_cost_roles("Track and Trace Specialist", "Logistics", "")
    assert roles[0] == "Track and Trace Specialist" and "Track" not in roles


def test_market_campaign_reads_as_a_business_not_a_buyer(monkeypatch):
    monkeypatch.setattr(fa, "_tm_bls_local_salaries", _fake_local)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    d = fa._tm_multi_cost_pdf_data(None, "Accounting & Finance", "CPA",
                                   "United States", "Accounting & Finance",
                                   market_only=True)
    assert d["intro"].startswith(fa._TM_COST_SNAPSHOT
                                 + ", for five roles an Accounting & Finance business")
    assert "in United States" not in d["intro"]
    assert "Accounting & Finance's" not in json.dumps(d)


def test_prepared_by_names_the_user_in_a_background_build(monkeypatch):
    """No browser session (campaign create, connector, PDF refresh): the
    name still comes from the user the build runs for."""
    monkeypatch.setattr(fa, "_get_company_name", lambda: "Thrivemodal")
    monkeypatch.setattr(fa, "_get_user_record",
                        lambda e: {"name": "Michael Vaughn"} if e == "m@x.com" else {})
    tok = fa._CURRENT_USER_EMAIL.set("m@x.com")
    try:
        assert fa._pdf_prepared_by({}) == "Michael Vaughn, Thrivemodal"
    finally:
        fa._CURRENT_USER_EMAIL.reset(tok)
    assert fa._pdf_prepared_by({}) == "Thrivemodal"

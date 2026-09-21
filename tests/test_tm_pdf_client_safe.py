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
    assert data["badge"] == "OFFSHORE ROLE BLUEPRINT"
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
    assert not any("Staffing_Cost" in f for f in out.values())


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
    money = lambda t: float(t.replace("USD", "").replace(",", ""))
    assert money(rows[-1][2]) == sum(money(r[2]) for r in rows[1:-1])
    assert money(rows[-1][4]) == money(rows[-1][2]) - money(rows[-1][3])
    assert d["badge"] == "STAFFING COST COMPARISON" and d["_worksheet"]
    assert not any("Philippine" in s for s in d["sections"][2]["items"])


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

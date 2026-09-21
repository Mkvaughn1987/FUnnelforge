"""ThriveModal PDFs sent to prospects: no internal market labels, fixed
titles, and a cost comparison without a salary is never attached
(S+B James Construction, 2026-09-19: "INCOMPLETE WORKSHEET" and
"Construction is an exploratory vertical for ThriveModal" both went out)."""
import json
import types

import flowdrip_app as fa


def test_playbook_titles_map_to_an_occupation_without_a_model():
    assert fa._tm_soc_for_role(None, "Project Coordinator")[0] == "131082"
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

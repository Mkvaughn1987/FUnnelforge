"""ThriveModal: Claude picks a campaign's Sales Assets PDFs through the
connector - on create_campaign (spec.pdfs) and afterwards (tm_campaign_pdfs,
POST /api/v1/tm/campaign_pdfs), including the pending queue items that froze
body + attachments at launch."""
import ast
from pathlib import Path

import pytest

import flowdrip_app as fa

_OWNER = "rep@thrivemodal.com"
_BLUEPRINT_LINE = next(l for k, _, l in fa._TM_CAMPAIGN_PDF_KINDS
                       if k == "tm_role_blueprint")
_COST_LINE = next(l for k, _, l in fa._TM_CAMPAIGN_PDF_KINDS
                  if k == "tm_cost_compare")


def _emails(n=6, call_at=None):
    out = []
    for i in range(n):
        st = "call" if i == call_at else "email_auto"
        out.append({"name": f"Step {i + 1}", "subject": f"s{i + 1}",
                    "body": "Hi {FirstName},<br><br>Body.", "step_type": st})
    return out


def _stub_build(kinds, company, role, location, **_):
    return {k: fa._tm_campaign_pdf_filename(k, company or role) for k in kinds}


# ── parsing the pick ────────────────────────────────────────────────────────

def test_parse_nothing_means_default_and_empty_is_refused():
    assert fa._tm_parse_pdf_request(None) == (None, {}, "")
    kinds, _pins, err = fa._tm_parse_pdf_request([])
    assert kinds is None and "at least 1" in err


def test_parse_kinds_and_pinned_steps():
    kinds, pins, err = fa._tm_parse_pdf_request(
        ["tm_cost_compare", {"kind": "tm_how_it_works", "step": 4}])
    assert err == ""
    assert kinds == ["tm_cost_compare", "tm_how_it_works"]
    assert pins == {"tm_how_it_works": 3}


@pytest.mark.parametrize("raw,needle", [
    ("tm_cost_compare", "must be a list"),
    (["bogus"], "unknown PDF kind"),
    (["tm_cost_compare", "tm_cost_compare"], "twice"),
    (["tm_cost_compare", "tm_role_blueprint", "tm_how_it_works"], "at most 2"),
    (["market_pulse"], "unknown PDF kind"),
    (["interview_guide"], "unknown PDF kind"),
    ([], "at least 1"),
    ([{"kind": "tm_cost_compare", "step": "two"}], "step number"),
    ([42], "kind or {kind, step}"),
])
def test_parse_rejects_bad_picks(raw, needle):
    kinds, _pins, err = fa._tm_parse_pdf_request(raw)
    assert kinds is None and needle in err


# ── pins ────────────────────────────────────────────────────────────────────

def test_placement_honours_a_pin_over_the_subject_match():
    emails = _emails()
    emails[1]["subject"] = "The cost math"          # would win cost_compare
    placed = fa._tm_pdf_placement("", emails, ["tm_cost_compare"],
                                  pinned={"tm_cost_compare": 4})
    assert placed == {"tm_cost_compare": 4}


def test_unpinned_pdfs_still_place_around_a_pin():
    placed = fa._tm_pdf_placement(
        "", _emails(), ["tm_role_blueprint", "tm_cost_compare"],
        pinned={"tm_role_blueprint": 2})
    assert placed["tm_role_blueprint"] == 2
    assert placed["tm_cost_compare"] not in (0, 2)


@pytest.mark.parametrize("pins,needle", [
    ({"tm_cost_compare": 0}, "step 1 cannot"),
    ({"tm_cost_compare": 2}, "step 3 cannot"),      # the call step
    ({"tm_cost_compare": 3, "interview_guide": 3}, "pinned for both"),
    ({"tm_cost_compare": 9}, "step 10 cannot"),
])
def test_bad_pins_are_explained(pins, needle):
    assert needle in fa._tm_check_pdf_pins(_emails(call_at=2), pins)


def test_good_pins_pass():
    assert fa._tm_check_pdf_pins(_emails(), {"tm_cost_compare": 1}) == ""


# ── changing an existing campaign ──────────────────────────────────────────

def _saved_campaign():
    emails = _emails()
    emails[1]["attachments"] = ["Offshore_Role_Blueprint_Acme.pdf"]
    emails[1]["body"] = f"Hi {{FirstName}},<br><br>{_BLUEPRINT_LINE}<br><br>Body."
    emails[3]["attachments"] = ["my_own_upload.pdf"]
    return {"name": "Acme", "emails": emails, "aicb_camp_type": "tm_5x7",
            "variables": {"CompanyName": "Acme", "TargetRole": "Bookkeeper, AP",
                          "Geography": "Denver, CO"}}


def test_set_replaces_sales_assets_and_keeps_hand_uploads():
    camp = _saved_campaign()
    res = fa._tm_set_campaign_pdfs(
        camp, ["tm_cost_compare"], {"tm_cost_compare": 5},
        fa._tm_campaign_pdf_subject(camp), build=_stub_build)
    em = camp["emails"]
    assert res["removed"] == 1 and res["failed"] == []
    assert em[1].get("attachments") == [] and _BLUEPRINT_LINE not in em[1]["body"]
    assert em[3]["attachments"] == ["my_own_upload.pdf"]
    assert em[5]["attachments"] == ["Staffing_Cost_Comparison_Acme.pdf"]
    assert em[5]["body"].startswith(f"Hi {{FirstName}},<br><br>{_COST_LINE}")
    assert res["pdfs"] == [{"kind": "tm_cost_compare",
                            "label": "Staffing Cost Comparison",
                            "file": "Staffing_Cost_Comparison_Acme.pdf",
                            "step": 6, "step_name": "Step 6"}]


def test_set_refuses_a_bad_pin_before_touching_anything():
    camp = _saved_campaign()
    before = [dict(e) for e in camp["emails"]]
    built = []
    res = fa._tm_set_campaign_pdfs(
        camp, ["tm_cost_compare"], {"tm_cost_compare": 3},   # hand upload there
        fa._tm_campaign_pdf_subject(camp),
        build=lambda *a, **k: built.append(1) or {})
    assert "cannot carry" in res["error"]
    assert camp["emails"] == before and built == []


def test_empty_pick_removes_them_all_without_building():
    camp = _saved_campaign()
    res = fa._tm_set_campaign_pdfs(camp, [], {}, fa._tm_campaign_pdf_subject(camp),
                                   build=lambda *a, **k: 1 / 0)
    assert res["removed"] == 1 and res["pdfs"] == []


def test_subject_comes_from_variables_and_overrides_win():
    camp = _saved_campaign()
    assert fa._tm_campaign_pdf_subject(camp) == {
        "company": "Acme", "role": "Bookkeeper", "location": "Denver, CO",
        "industry": ""}
    s = fa._tm_campaign_pdf_subject(camp, {"role": "Controller", "location": " "})
    assert s["role"] == "Controller" and s["location"] == "Denver, CO"


# ── the queue follows ──────────────────────────────────────────────────────

def test_pending_queue_items_pick_up_the_change(monkeypatch, tmp_path):
    monkeypatch.setattr(fa, "_user_pdf_dir", lambda: tmp_path)
    camp = _saved_campaign()
    fa._tm_set_campaign_pdfs(camp, ["tm_cost_compare"], {"tm_cost_compare": 5},
                             fa._tm_campaign_pdf_subject(camp), build=_stub_build)
    old_path = str(tmp_path / "Offshore_Role_Blueprint_Acme.pdf")
    queue = [
        {"campaign": "Acme", "status": "pending", "_step_idx": 1,
         "attachments": [old_path],
         "body": f"Hi Bob,<br><br>{_BLUEPRINT_LINE}<br><br>Body.<br><br>Sig"},
        {"campaign": "Acme", "status": "pending", "_step_idx": 5,
         "attachments": [], "body": "Hi Bob,<br><br>Body.<br><br>Sig"},
        {"campaign": "Acme", "status": "sent", "_step_idx": 1,
         "attachments": [old_path], "body": "sent already"},
        {"campaign": "Other", "status": "pending", "_step_idx": 1,
         "attachments": [old_path], "body": "x"},
    ]
    assert fa._tm_sync_queue_pdfs(camp, queue) == 2
    assert queue[0]["attachments"] == []
    assert queue[0]["body"] == "Hi Bob,<br><br>Body.<br><br>Sig"
    assert queue[1]["attachments"] == [str(tmp_path / "Staffing_Cost_Comparison_Acme.pdf")]
    assert queue[1]["body"] == f"Hi Bob,<br><br>{_COST_LINE}<br><br>Body.<br><br>Sig"
    assert queue[2]["attachments"] == [old_path]
    assert queue[3]["attachments"] == [old_path]


# ── the route ──────────────────────────────────────────────────────────────

@pytest.fixture
def route(tmp_path, monkeypatch):
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    camp = _saved_campaign()
    camp["_path"] = "/data/acme.json"
    saved, synced = [], []
    monkeypatch.setattr(fa, "load_campaigns", lambda: [camp])
    monkeypatch.setattr(fa, "save_campaign", lambda c: saved.append(c))
    monkeypatch.setattr(fa, "_tm_save_queue_sync", lambda c: synced.append(c) or 3)
    monkeypatch.setattr(fa, "_tm_build_campaign_pdfs", _stub_build)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "test")
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    app = FastAPI()
    app.post("/api/v1/tm/campaign_pdfs")(fa.api_tm_campaign_pdfs)
    return {"client": TestClient(app), "key": fa._mint_api_key(_OWNER),
            "camp": camp, "saved": saved, "synced": synced}


def _post(route, body, key=True):
    h = {"X-API-Key": route["key"]} if key else {}
    return route["client"].post("/api/v1/tm/campaign_pdfs", json=body, headers=h)


def test_route_needs_a_key(route):
    assert _post(route, {}, key=False).status_code == 401


def test_route_is_404_on_arena(route, monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    r = _post(route, {"campaign_id": "acme", "pdfs": []})
    assert r.status_code == 404


def test_route_rejects_a_bad_kind_and_lists_the_choices(route):
    r = _post(route, {"campaign_id": "acme", "pdfs": ["salary_guide"]})
    assert r.status_code == 400
    assert {c["kind"] for c in r.json()["choices"]} == set(
        fa._TM_CAMPAIGN_PDF_OFFERED)


def test_route_requires_pdfs(route):
    r = _post(route, {"campaign_id": "acme"})
    assert r.status_code == 400 and "pdfs is required" in r.json()["error"]


def test_route_404s_an_unknown_campaign(route):
    r = _post(route, {"campaign_id": "nope", "pdfs": ["tm_cost_compare"]})
    assert r.status_code == 404


def test_route_swaps_pdfs_saves_and_syncs_the_queue(route):
    r = _post(route, {"campaign_id": "acme", "role": "Controller",
                      "pdfs": ["tm_how_it_works",
                               {"kind": "tm_cost_compare", "step": 3}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["campaign_id"] == "acme"
    assert body["built_for"]["role"] == "Controller"
    assert body["queue_items_updated"] == 3
    steps = {p["kind"]: p["step"] for p in body["pdfs"]}
    assert steps["tm_cost_compare"] == 3
    assert steps["tm_how_it_works"] not in (1, 3, 4)
    assert route["saved"] == [route["camp"]] and route["synced"] == [route["camp"]]


def test_route_bad_pin_is_400_and_nothing_saved(route):
    r = _post(route, {"campaign_id": "acme",
                      "pdfs": [{"kind": "tm_cost_compare", "step": 1}]})
    assert r.status_code == 400 and "step 1 cannot" in r.json()["error"]
    assert route["saved"] == []


# ── create_campaign ────────────────────────────────────────────────────────

@pytest.fixture
def create(monkeypatch):
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    calls = []

    def _build(kinds, company, role, location, **kw):
        calls.append((list(kinds), company, role, location, kw.get("industry")))
        return _stub_build(kinds, company, role, location)
    monkeypatch.setattr(fa, "_tm_build_campaign_pdfs", _build)
    monkeypatch.setattr(fa, "generate_aicb_campaign",
                        lambda client, **kw: {"emails": _emails(8)})
    return calls


def _spec(**kw):
    return {"template": "tm_5x7", "company": "Acme", "roles": ["Bookkeeper"],
            "location": "Denver, CO", "industry": "Logistics", **kw}


def test_create_attaches_the_picked_pdfs_where_asked(create):
    out = fa._api_create_campaign_blocking(None, _spec(pdfs=[
        {"kind": "tm_how_it_works", "step": 7}, "tm_cost_compare"]), _OWNER)
    steps = {p["kind"]: p["step"] for p in out["pdfs"]}
    assert steps["tm_how_it_works"] == 7 and "tm_cost_compare" in steps
    assert create == [(["tm_how_it_works", "tm_cost_compare"], "Acme",
                       "Bookkeeper", "Denver, CO", "Logistics")]
    assert "pdf_notes" not in out


def test_create_with_no_pick_uses_the_default_pair(create):
    out = fa._api_create_campaign_blocking(None, _spec(), _OWNER)
    assert {p["kind"] for p in out["pdfs"]} == set(fa.TM_CAMPAIGN_PDF_DEFAULT)


def test_create_with_empty_pick_is_400_before_generating(create):
    out = fa._api_create_campaign_blocking(None, _spec(pdfs=[]), _OWNER)
    assert out.get("status") == 400 and "at least 1" in out["error"]
    assert create == []


def test_create_bad_pick_is_400_before_generating(create, monkeypatch):
    monkeypatch.setattr(fa, "generate_aicb_campaign", lambda *a, **k: 1 / 0)
    out = fa._api_create_campaign_blocking(None, _spec(pdfs=["nope"]), _OWNER)
    assert out["status"] == 400 and "unknown PDF kind" in out["error"]


def test_create_bad_pin_falls_back_to_auto_with_a_note(create):
    out = fa._api_create_campaign_blocking(
        None, _spec(pdfs=[{"kind": "tm_cost_compare", "step": 1}]), _OWNER)
    assert out["pdfs"][0]["step"] != 1
    assert "Placed automatically" in out["pdf_notes"][0]


def test_create_on_arena_ignores_pdfs(create, monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    out = fa._api_create_campaign_blocking(None, _spec(pdfs=["bogus"]), _OWNER)
    assert "pdfs" not in out and "error" not in out and create == []


# ── connector surface ──────────────────────────────────────────────────────

_ROOT = Path(fa.__file__).resolve().parent


def _tree(rel):
    return ast.parse((_ROOT / rel).read_text(encoding="utf-8"))


def test_tool_and_client_method_exist():
    tools = [n.name for n in ast.walk(_tree("mcp_server/dripdrop_mcp.py"))
             if isinstance(n, ast.AsyncFunctionDef)]
    methods = [n.name for n in ast.walk(_tree("mcp_server/dripdrop_client.py"))
               if isinstance(n, ast.AsyncFunctionDef)]
    assert "tm_campaign_pdfs" in tools and "tm_campaign_pdfs" in methods


def test_tool_docs_name_every_offered_pdf_kind_and_no_other():
    src = (_ROOT / "mcp_server/dripdrop_mcp.py").read_text(encoding="utf-8")
    start = src.index("_PDF_KINDS_DOC = (")
    doc = src[start:src.index("\n)\n", start)]
    for k, *_ in fa._TM_CAMPAIGN_PDF_KINDS:
        assert (k in doc) == (k in fa._TM_CAMPAIGN_PDF_OFFERED), k

"""Find more targets (tm_targets_scan.py + /api/v1/tm/targets): the Target
List's Indeed resume scan, handed to Claude, saved back through the
connector.

The search and instructions the page builds, cleaning what Claude sends
(no candidate details survive), skipping companies already listed,
clients, vendors and big firms, the per-user state file, and the route.
"""
import sys
import urllib.parse
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 16)


@pytest.fixture(scope="module")
def sc():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import tm_targets_scan
    return tm_targets_scan


# ── the scan request ─────────────────────────────────────────────────────

def test_every_market_has_role_presets(sc):
    import tm_targets_data as data
    for mk, _label in data.MARKETS:
        assert len(sc.ROLE_PRESETS[mk]) >= sc.DEFAULT_ROLE_COUNT, mk
        d = sc.default_scan(mk)
        assert d["market"] == mk and d["roles"] == sc.ROLE_PRESETS[mk][:3]
    assert sc.default_scan("nope")["market"] == "freight"


def test_build_query_quotes_phrases_and_drops_repeats(sc):
    assert sc.build_query(["freight broker", "dispatcher", "Dispatcher", "  "]) == \
        '("freight broker" OR dispatcher) "USA"'
    assert sc.build_query(["dispatcher"]) == 'dispatcher "USA"'
    assert sc.build_query([]) == '"USA"'
    # No way to smuggle Indeed operators or quotes in through a typed role.
    assert sc.build_query(['x") OR (y']) == '"x OR y" "USA"'


def test_page_urls_step_by_fifty(sc):
    urls = sc.page_urls('dispatcher "USA"', 3)
    assert [u.rsplit("start=", 1)[1] for u in urls] == ["0", "50", "100"]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(urls[0]).query)
    assert q["q"] == ['dispatcher "USA"'] and q["nl"] == ["false"]
    assert urls[0].startswith("https://resumes.indeed.com/search?")


def test_prompt_carries_the_choices_skip_lists_and_save_call(sc):
    scan = {"market": "freight", "roles": ["dispatcher"], "years": 3, "pages": 3, "size": 200}
    found = [{"name": "Zed Freight LLC", "market": "freight"}]
    p = sc.build_prompt(scan, found=found, clients=["Acme Freight"], today=TODAY)
    assert "2023 or later" in p
    assert p.count("https://resumes.indeed.com/search?") == 3
    assert "over 200 staff" in p
    assert "Zed Freight LLC" in p and "Priority1 Logistics" in p  # finds + research
    assert "Acme Freight" in p and "CoVar Transport" in p          # clients + the fixed one
    assert "Freight Courses 101" in p and "Lean Solutions Group" in p
    assert 'action="add", market="freight"' in p and 'query="dispatcher \\"USA\\""' in p
    assert "Do NOT open any resume" in p and "Never write down a candidate's name" in p
    assert "\n\n\n" not in p


def test_any_size_drops_the_size_rule(sc):
    p = sc.build_prompt({"market": "accounting", "roles": ["bookkeeper"], "years": 5,
                         "pages": 5, "size": 0}, today=TODAY)
    assert "staff, and the big" not in p and "\n\n\n" not in p
    assert "Priority1" not in p  # other markets' companies stay out of the skip list


def test_the_longest_prompt_still_fits_in_a_chat_link(sc):
    import tm_targets_data as data
    many = [{"name": f"Found Co {i} Logistics LLC", "market": "freight"} for i in range(150)]
    for mk, _l in data.MARKETS:
        scan = {"market": mk, "roles": sc.ROLE_PRESETS[mk], "years": 10, "pages": 10, "size": 500}
        p = sc.build_prompt(scan, found=many, clients=["Client %d" % i for i in range(40)])
        url = "https://claude.ai/new?q=" + urllib.parse.quote(p, safe="")
        assert len(url) < 32000, (mk, len(url))


# ── saving what Claude found ─────────────────────────────────────────────

def test_clean_rows_keeps_company_fields_only_and_sets_tier(sc):
    rows, errors = sc.clean_rows([
        {"name": "Zed Freight LLC", "hq": "Dallas, TX", "roles": "Dispatcher",
         "years": "2024-2026", "people": 2, "verified": True,
         "candidate": "Juan Dela Cruz", "email": "juan@x.com"},
        {"name": "Maybe Trucking", "verified": "false"},
        "Solo Name Inc",
        {"hq": "no name"},
        42,
    ], "freight", today=TODAY)
    assert [r["name"] for r in rows] == ["Zed Freight LLC", "Maybe Trucking", "Solo Name Inc"]
    z = rows[0]
    assert z["tier"] == "strong" and z["kind"] == "resume" and z["found"] == "2026-10-16"
    assert z["ph"] == "2 Filipino employees list them on their resumes (2024-2026)."
    assert "Juan" not in str(rows) and "juan@x.com" not in str(rows)
    assert rows[1]["tier"] == "weak" and rows[1]["hq"] == "US (unverified)"
    assert "Check HQ" in rows[1]["note"]
    assert [e["row"] for e in errors] == [3, 4]
    # Same shape as the research rows, so the page renders them unchanged.
    import tm_targets_data as data
    assert set(data.SEED[0]) <= set(z)


def test_tier_for(sc):
    assert sc.tier_for(True, 3) == "strong"
    assert sc.tier_for(True, 1) == "medium"
    assert sc.tier_for(False, 5) == "weak"


def test_add_found_skips_listed_clients_vendors_big_and_repeats(sc):
    state = {"status": {}, "found": [{"name": "Earlier Find LLC", "market": "freight"}]}
    rows, _ = sc.clean_rows([
        {"name": "New Freight Co", "verified": True},
        {"name": "Priority1 Logistics, Inc."},   # in the research seed
        {"name": "Earlier Find"},                 # an earlier scan
        {"name": "Acme Freight LLC"},             # a client
        {"name": "CoVar Transport"},              # fixed leave-out
        {"name": "Lean Solutions Group"},         # vendor
        {"name": "Freight Courses 101"},          # course
        {"name": "Landstar"},                     # big
        {"name": "New Freight Co."},              # repeat within the call
    ], "freight", today=TODAY)
    res = sc.add_found(state, rows, "freight", query="q1", clients=["Acme Freight"], today=TODAY)
    assert res["added"] == 1 and res["skipped"] == 8
    reasons = {r["name"]: r.get("reason") for r in res["results"]}
    assert reasons["Priority1 Logistics, Inc."] == "already on your Target List"
    assert reasons["Earlier Find"] == "already found by an earlier scan"
    assert reasons["Acme Freight LLC"] == "a client"
    assert reasons["CoVar Transport"] == "a ThriveModal client"
    assert reasons["Lean Solutions Group"] == "a staffing vendor, not a prospect"
    assert reasons["Freight Courses 101"] == "a training course"
    assert reasons["Landstar"] == "over 500 staff"
    assert reasons["New Freight Co."] == "repeated in this call"
    assert [r["name"] for r in state["found"]] == ["Earlier Find LLC", "New Freight Co"]
    assert state["scans"] == [{"date": "2026-10-16", "market": "freight", "query": "q1",
                               "added": 1, "skipped": 8}]


def test_add_found_rolls_calls_of_one_scan_together(sc):
    state = {}
    for name in ("One Co", "Two Co"):
        rows, _ = sc.clean_rows([{"name": name}], "freight", today=TODAY)
        sc.add_found(state, rows, "freight", query="q", today=TODAY)
    rows, _ = sc.clean_rows([{"name": "Three Co"}], "freight", today=TODAY)
    sc.add_found(state, rows, "freight", query="other", today=TODAY)
    assert [(x["query"], x["added"]) for x in state["scans"]] == [("other", 1), ("q", 2)]


def test_seed_never_contains_what_a_scan_would_skip(sc):
    import tm_targets_data as data
    seed = {sc.norm(r["name"]) for r in data.SEED}
    for n in sc.VENDORS + sc.COURSES + sc.BIG + tuple(sc.LEAVE_OUT):
        assert sc.norm(n) not in seed, n


def test_client_names_and_scan_line(sc):
    assert sc.client_names([{"client_name": "Acme", "domain": "acme.com"},
                            {"client_name": "", "domain": "zed.io"}, "junk"]) == ["Acme", "zed"]
    assert sc.scan_line({"date": "2026-10-06", "market": "freight", "added": 12}) == \
        "Oct 6 · Freight & 3PL · 12 added"


# ── the route ────────────────────────────────────────────────────────────

@pytest.fixture
def api(tmp_path, monkeypatch):
    from tests.test_tm_signals import _stub_nicegui
    _stub_nicegui()
    import flowdrip_app as fa
    keys = tmp_path / "api_keys.json"
    monkeypatch.setattr(fa, "_api_keys_path", lambda: keys)
    monkeypatch.setattr(fa, "_switch_to_user_paths", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    monkeypatch.setattr(fa, "_resolve_user_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(fa, "load_client_blocklist",
                        lambda *a, **k: [{"client_name": "Acme Freight", "domain": "acme.com"}])
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    app = FastAPI()
    app.get("/api/v1/tm/targets")(fa.api_tm_targets)
    app.post("/api/v1/tm/targets")(fa.api_tm_targets_add)
    client = TestClient(app)
    h = {"X-API-Key": fa._mint_api_key("rep@thrivemodal.com")}
    return {"client": client, "h": h, "tmp": tmp_path}


def test_route_add_then_list(api):
    c, h = api["client"], api["h"]
    r = c.post("/api/v1/tm/targets", headers=h, json={
        "action": "add", "market": "freight", "query": 'dispatcher "USA"',
        "companies": [{"name": "Zed Freight LLC", "verified": True, "people": 2},
                      {"name": "Acme Freight"}, {"nope": 1}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["added"] == 1 and j["skipped"] == 1 and len(j["errors"]) == 1
    import tm_targets
    st = tm_targets.load_state(api["tmp"])
    assert [x["name"] for x in st["found"]] == ["Zed Freight LLC"]
    r = c.get("/api/v1/tm/targets", headers=h, params={"market": "freight"})
    j = r.json()
    assert "Zed Freight LLC" in j["on_list"] and "Priority1 Logistics" in j["on_list"]
    assert j["clients"] == ["Acme Freight"] and j["found"] == 1
    assert j["scans"][0]["added"] == 1


def test_route_keeps_card_status_when_it_saves(api):
    import tm_targets
    tm_targets.save_state({"status": {"acme": "working"}}, api["tmp"])
    api["client"].post("/api/v1/tm/targets", headers=api["h"], json={
        "market": "accounting", "companies": [{"name": "Books R Us"}]})
    st = tm_targets.load_state(api["tmp"])
    assert st["status"] == {"acme": "working"} and st["found"][0]["market"] == "accounting"


@pytest.mark.parametrize("body", [
    {"market": "space", "companies": [{"name": "X"}]},
    {"market": "freight", "companies": []},
    {"market": "freight", "companies": "X"},
    {"market": "freight", "action": "remove", "companies": [{"name": "X"}]},
    {"market": "freight", "companies": [{"name": "X"}] * 201},
])
def test_route_rejects_bad_bodies(api, body):
    r = api["client"].post("/api/v1/tm/targets", headers=api["h"], json=body)
    assert r.status_code == 400


def test_route_rejects_a_bad_market_on_list(api):
    r = api["client"].get("/api/v1/tm/targets", headers=api["h"], params={"market": "space"})
    assert r.status_code == 400

"""Target List (tm_targets.py + tm_targets_data.py): the pure parts.

Seed shape, merging Buying Signals companies, order (signals, then newest
posting), the posted-age wording on every card, filters, status cycling and
the per-user state file. No NiceGUI rendering.
"""
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 16)


@pytest.fixture(scope="module")
def tmt():
    from tests.test_tm_signals import _stub_nicegui
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import tm_targets
    return tm_targets


def _seed(name, posted="", tier="medium", kind="hiring", market="freight", **kw):
    r = {"name": name, "market": market, "tier": tier, "kind": kind, "hq": "", "size": "",
         "ph": "", "roles": "", "posted": posted, "when": kw.pop("when", ""), "pay": "",
         "sources": [], "note": ""}
    r.update(kw)
    return r


def _issue(date_, companies, industry="logistics"):
    return {"date": date_, "sections": [{"industry": industry, "companies": companies}]}


def _co(name, d, offshore=""):
    return {"company": name, "signal": "pe", "headline": "Bought", "why_now": "New owners.",
            "offshore_history": offshore, "location": "Dallas, TX", "date": d,
            "source_url": "https://example.com/x"}


# ── seed ────────────────────────────────────────────────────────────────

def test_seed_rows_are_well_formed_and_unique(tmt):
    import tm_targets_data as data
    markets = {k for k, _ in data.MARKETS}
    tiers = {k for k, _ in data.TIERS}
    seen = set()
    assert len(data.SEED) > 150
    for r in data.SEED:
        assert r["market"] in markets, r["name"]
        assert r["tier"] in tiers, r["name"]
        assert r["kind"] in tmt.KIND_LABEL, r["name"]
        assert r["posted"] or r["when"], f"{r['name']} has no posted date or wording"
        if r["posted"]:
            assert tmt.parse_iso(r["posted"]), r["name"]
        for s in r["sources"]:
            assert s["url"].startswith("https://"), r["name"]
        k = tmt.key_of(r["name"])
        assert k not in seen, f"duplicate {r['name']}"
        seen.add(k)


def test_seed_leaves_out_client_vendors_and_big_firms(tmt):
    import tm_targets_data as data
    names = " ".join(r["name"].lower() for r in data.SEED)
    for out in ("covar", "expedock", "logistics plus", "landstar", "aprio",
                "lean solutions", "valoroo", "loadsmart"):
        assert out not in names, out


# ── merge + order ───────────────────────────────────────────────────────

def test_norm_matches_suffix_variants(tmt):
    assert tmt.norm("Ally Logistics, LLC") == tmt.norm("Ally Logistics")
    assert tmt.norm("GH Logistics (AJG Transport)") == "gh logistics"


def test_signal_rows_keep_newest_per_company(tmt):
    issues = [_issue("2026-10-15", [_co("Acme Freight", "2026-10-14")]),
              _issue("2026-10-13", [_co("Acme Freight, Inc.", "2026-10-10"),
                                    _co("Beta Books", "2026-10-09")], industry="accounting")]
    rows = {r["company"]: r for r in tmt.signal_rows(issues)}
    assert set(rows) == {"Acme Freight", "Beta Books"}
    assert rows["Acme Freight"]["date"] == "2026-10-14"
    assert rows["Beta Books"]["market"] == "accounting"


def test_build_rows_attaches_signal_and_adds_new_companies(tmt):
    seed = [_seed("Acme Freight LLC", "2026-09-01")]
    sigs = tmt.signal_rows([_issue("2026-10-15", [_co("Acme Freight", "2026-10-14"),
                                                  _co("Gamma Haul", "2026-10-12", offshore="OJ post")])])
    rows = {r["name"]: r for r in tmt.build_rows(seed, sigs)}
    assert rows["Acme Freight LLC"]["signal"]["date"] == "2026-10-14"
    g = rows["Gamma Haul"]
    assert g["kind"] == "signal" and g["tier"] == "strong" and g["posted"] == "2026-10-12"


def test_sort_signals_first_then_newest_then_undated_by_tier(tmt):
    rows = tmt.build_rows(
        [_seed("Old", "2026-08-01"), _seed("New", "2026-10-14"),
         _seed("UndatedWeak", tier="weak", when="2024"), _seed("UndatedStrong", tier="strong", when="2025"),
         _seed("Sig", "2026-01-01")],
        tmt.signal_rows([_issue("2026-10-15", [_co("Sig", "2026-10-15")])]))
    assert [r["name"] for r in tmt.sort_rows(rows)] == [
        "Sig", "New", "Old", "UndatedStrong", "UndatedWeak"]


# ── every card says how long it has been posted ─────────────────────────

def test_age_label(tmt):
    assert tmt.age_label({"posted": "2026-10-16"}, TODAY) == "Posted today"
    assert tmt.age_label({"posted": "2026-10-15"}, TODAY) == "Posted 1 day ago"
    assert tmt.age_label({"posted": "2026-10-02"}, TODAY) == "Posted 14 days ago"
    assert tmt.age_label({"posted": "2026-06-09"}, TODAY) == "Posted 4 months ago"
    assert tmt.age_label({"posted": "2026-10-14", "kind": "signal"}, TODAY) == "Signal 2 days ago"
    assert tmt.age_label({"posted": "", "when": "2024-2026"}, TODAY) == "2024-2026"


def test_size_label(tmt):
    assert tmt.size_label("~213") == "~213 staff"
    assert tmt.size_label("201-500") == "201-500 staff"
    assert tmt.size_label("28 trucks") == "28 trucks"
    assert tmt.size_label("") == ""


# ── filters, status, counts ─────────────────────────────────────────────

def test_filters_and_hidden(tmt):
    rows = tmt.build_rows([_seed("A Freight", tier="strong", hq="Dallas, TX"),
                           _seed("B Books", market="accounting", roles="Tax Preparer"),
                           _seed("C Gone")], [])
    status = {tmt.key_of("C Gone"): "no_fit"}
    names = lambda rs: [r["name"] for r in rs]
    assert names(tmt.filter_rows(rows, status)) == ["A Freight", "B Books"]
    assert names(tmt.filter_rows(rows, status, market="accounting")) == ["B Books"]
    assert names(tmt.filter_rows(rows, status, strong_only=True)) == ["A Freight"]
    assert names(tmt.filter_rows(rows, status, q="tax")) == ["B Books"]
    assert names(tmt.filter_rows(rows, status, q="dallas")) == ["A Freight"]
    assert names(tmt.filter_rows(rows, status, show_hidden=True)) == ["C Gone"]


def test_status_cycles_back_to_new(tmt):
    seq = ["new"]
    for _ in range(4):
        seq.append(tmt.next_status(seq[-1]))
    assert seq == ["new", "working", "contacted", "no_fit", "new"]


def test_counts(tmt):
    rows = tmt.build_rows([_seed("A", "2026-10-10", tier="strong"), _seed("B", "2026-07-01"),
                           _seed("C", "2026-10-12")],
                          tmt.signal_rows([_issue("2026-10-15", [_co("B", "2026-10-15")])]))
    c = tmt.counts(rows, {tmt.key_of("C"): "no_fit"}, TODAY)
    assert c == {"total": 2, "strong": 1, "fresh": 1, "signals": 1, "hidden": 1}


def test_state_round_trip_drops_unknown_status(tmt, tmp_path):
    tmt.save_state({"status": {"acme": "working", "bad": "zzz"}}, tmp_path)
    assert tmt.load_state(tmp_path) == {"status": {"acme": "working"}, "found": [], "scans": []}
    assert tmt.load_state(tmp_path / "nope") == {"status": {}, "found": [], "scans": []}


def test_state_keeps_found_rows_and_scans(tmt, tmp_path):
    found = [_seed("Zed Freight LLC", kind="resume", found="2026-10-14"), {"no": "name"}]
    tmt.save_state({"status": {}, "found": found, "scans": [{"date": "2026-10-14"}]}, tmp_path)
    st = tmt.load_state(tmp_path)
    assert [r["name"] for r in st["found"]] == ["Zed Freight LLC"]
    assert st["scans"] == [{"date": "2026-10-14"}]


def test_found_rows_say_when_found_and_sort_by_it(tmt):
    assert tmt.age_label({"posted": "", "found": "2026-10-13", "when": "2025"}, TODAY) == "Found 3 days ago"
    rows = tmt.build_rows([_seed("Old", "2026-08-01"),
                           _seed("Fresh Find", kind="resume", found="2026-10-15"),
                           _seed("Undated", tier="strong", when="2025")], [])
    assert [r["name"] for r in tmt.sort_rows(rows)] == ["Fresh Find", "Old", "Undated"]

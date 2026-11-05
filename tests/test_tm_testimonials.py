"""Testimonials: survey cleaning, the drafted quote, storage and the public
no-login link."""
import json
import types

import pytest

import tm_testimonials as tt


def _fake_ff(tmp_path):
    base = tmp_path / "data"
    m = types.SimpleNamespace(
        _BASE_DATA_DIR=base, C={},
        _resolve_user_root=lambda email=None: base / "users" / (email or "x").replace("@", "_at_"),
        _rate_limit_check=lambda k: True, _rate_limit_record=lambda k: None,
        _PUBLIC_ORIGIN="https://app.example.com")
    return m


@pytest.fixture
def ff(tmp_path, monkeypatch):
    m = _fake_ff(tmp_path)
    monkeypatch.setattr(tt, "_ff", lambda: m)
    return m


def test_clean_answers_drops_unknown_keys_and_values():
    got = tt.clean_answers({
        "roles": ["dispatch", "hacker"], "fill": "lt2w", "tenure": "forever",
        "ratings": {"english": 5, "ethic": 9, "bogus": 3}, "own_words": "  Great  ",
        "evil": "<script>"})
    assert got == {"roles": ["dispatch"], "fill": "lt2w",
                   "ratings": {"english": 5}, "own_words": "Great"}
    assert tt.clean_answers("nope") == {}


def test_draft_uses_only_what_was_picked():
    a = {"challenge": ["local"], "roles": ["dispatch"], "fill": "2-4w", "ramp": "week",
         "savings": "20-40", "hours": "10-20", "expanded": "yes", "phrases": ["sooner"]}
    d = tt.build_draft(a, "ThriveModal", "Maria")
    assert d.startswith("Before ThriveModal, we couldn't find good people locally.")
    assert "ThriveModal filled our dispatch role in under a month, and Maria hit the ground running." in d
    assert "$20,000 to $40,000" in d and "10 to 20 hours" in d
    assert "We've since added more people." in d and "I wish we'd done this sooner." in d


def test_draft_says_nothing_it_was_not_told():
    assert tt.build_draft({}, "ThriveModal") == ""
    d = tt.build_draft({"savings": "skip", "ramp": "2-3m"}, "ThriveModal")
    assert d == ""


def test_draft_grammar_for_unnamed_hire():
    d = tt.build_draft({"fill": "lt2w", "ramp": "month"}, "ThriveModal")
    assert d == "ThriveModal filled our role in under two weeks, and they were up to speed within the month."


def test_every_question_option_key_is_unique():
    for q in tt.QUESTIONS:
        keys = [k for k, _ in q.get("opts", [])]
        assert len(keys) == len(set(keys)), q["id"]
    assert len({q["id"] for q in tt.QUESTIONS}) == len(tt.QUESTIONS)


def test_storage_round_trip_and_delete(ff):
    r = tt.new_request("Acme Freight", "Jane Doe", "jane@acme.com", "Maria")
    tt.add_request("Owner@x.com", r)
    owner, got = tt.find(r["token"])
    assert owner == "owner@x.com" and got["company"] == "Acme Freight"
    assert tt.find("short")[1] is None and tt.find("x" * 20)[1] is None
    tt.delete_request("owner@x.com", r["token"])
    assert tt.find(r["token"]) == (None, None)


def test_request_email_has_link_and_no_login_promise():
    r = tt.new_request("Acme", "Jane Doe", hire="Maria")
    subj, body = tt.request_email(r, "https://x/review/abc", "Sam", "ThriveModal")
    assert subj == "Quick favor?"
    assert body.startswith("Hi Jane,") and "Maria has settled in" in body
    assert "https://x/review/abc" in body and "no login" in body and body.endswith("Sam\nThriveModal")


def test_public_page_escapes_client_text(ff):
    r = tt.new_request("</script><b>Acme", "Jane")
    page = tt._public_html(r, "ThriveModal", "https://x/logo.png")
    assert "</script><b>" not in page
    assert "__DATA__" not in page and "__US__" not in page


def test_public_routes_end_to_end(ff):
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    import nicegui

    fake = FastAPI()
    real = nicegui.app
    nicegui.app = fake
    try:
        tt.register_routes()
    finally:
        nicegui.app = real
    c = TestClient(fake)
    r = tt.new_request("Acme Freight", "Jane Doe")
    tt.add_request("owner@x.com", r)
    tok = r["token"]

    assert c.get("/review/nottherealtoken").status_code == 404
    page = c.get(f"/review/{tok}")
    assert page.status_code == 200 and "noindex" in page.headers.get("x-robots-tag", "")
    assert tt.find(tok)[1]["status"] == "opened"

    assert c.post(f"/review/{tok}/answers", json={"answers": {}}).status_code == 400
    res = c.post(f"/review/{tok}/answers",
                 json={"answers": {"fill": "lt2w", "expanded": "yes"}})
    assert res.status_code == 200 and "under two weeks" in res.json()["draft"]
    assert tt.find(tok)[1]["status"] == "answered"

    assert c.post(f"/review/{tok}/approve", json={"quote": "Great", "permission": "x"}
                  ).status_code == 400
    ok = c.post(f"/review/{tok}/approve", json={
        "quote": "They are great.", "permission": "full", "name": "Jane Doe",
        "title": "Owner", "company": "Acme Freight"})
    assert ok.status_code == 200
    saved = tt.find(tok)[1]
    assert saved["status"] == "approved" and saved["quote"] == "They are great."
    assert tt.credit_line(saved) == "Jane Doe, Owner, Acme Freight"
    assert c.post(f"/review/{tok}/answers", json={"answers": {"fill": "lt2w"}}
                  ).status_code == 409


def test_sidebar_wiring():
    import flowdrip_app as fa
    assert fa._TM_NAV_PAGES["testimonials"] == "tm_testimonials"
    assert fa.SIDEBAR_PAGE_ROW.get("tm_testimonials") == "testimonials"
    assert fa.SIDEBAR_TITLES.get("tm_testimonials") == "Testimonials"
    assert "testimonials" in fa._SIDEBAR_ICONS
    rows = dict((k, p) for _s, rs in fa.SIDEBAR_NAV for k, _l, p in rs)
    assert rows["testimonials"] is None  # ThriveModal only, Arena never sees it
    paths = {getattr(r, "path", "") for r in fa.app.routes}
    assert "/review/{token}" in paths and "/review/{token}/approve" in paths

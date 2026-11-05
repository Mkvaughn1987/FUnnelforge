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


# ── Quotes in PDFs and emails ────────────────────────────────────────────

def _approve(owner, company, quote, perm, title="Owner", approved="2026-11-05T10:00:00Z"):
    r = tt.new_request(company, "Jane Doe")
    r.update(status="approved", quote=quote, permission=perm, sig_name="Jane Doe",
             sig_title=title, sig_company=company, approved_at=approved)
    tt.add_request(owner, r)


def test_public_quotes_newest_first_and_never_internal(ff):
    assert tt.public_quotes("o@x.com") == []
    _approve("o@x.com", "Acme", "Old one.", "full", approved="2026-11-01T00:00:00Z")
    _approve("o@x.com", "Beta", "Secret.", "internal")
    _approve("o@x.com", "Gamma", "New one.", "anon", title="VP Operations")
    got = tt.public_quotes("o@x.com")
    assert got == [("New one.", "VP Operations"), ("Old one.", "Jane Doe, Owner, Acme")]
    assert all("Secret" not in q for q, _c in got)


def test_pdf_sections_add_quotes_only_when_there_are_some():
    import flowdrip_app as fa
    secs = [{"heading": "X", "type": "bullets", "items": ["a", "b"]}]
    none = fa._tm_with_standard(secs, quotes=[])
    assert [s.get("type") for s in none] == ["callout", "bullets"]
    some = fa._tm_with_standard(none, quotes=[("Great team.", "Jane Doe, Owner, Acme")])
    assert [s.get("type") for s in some] == ["callout", "bullets", "quote"]
    assert some[-1]["items"] == ["\u201cGreat team.\u201d\nJane Doe, Owner, Acme"]
    # Rebuilding never doubles the box, and an emptied list removes it.
    again = fa._tm_with_standard(some, quotes=[("Great team.", "Jane")])
    assert [s.get("type") for s in again].count("quote") == 1
    assert "quote" not in [s.get("type") for s in fa._tm_with_standard(some, quotes=[])]


def test_pdf_renders_quote_box(tmp_path):
    from funnel_forge import arena_pdfs as ap
    d = {"title": "Test", "sections": [
        {"heading": "Why", "type": "bullets", "items": ["One.", "Two."]},
        {"heading": "What Our Clients Say", "type": "quote",
         "items": ["\u201cThey hit the ground running & stayed.\u201d\nJane Doe, Owner, Acme <Freight>"]}]}
    out = tmp_path / "t.pdf"
    ap.build_custom_pdf(str(out), d)
    assert out.exists() and out.stat().st_size > 1000


def _emails(n=5):
    return [{"step_type": "email_auto", "name": f"E{i+1}", "subject": f"s{i+1}",
             "body": "Hi Jane,<br><br>Middle paragraph.<br><br>Worth a chat?"}
            for i in range(n)]


def test_email_gets_one_quote_before_the_ask_and_reruns_replace_it():
    import flowdrip_app as fa
    camp = {"emails": _emails()}
    assert fa._tm_add_campaign_testimonial(camp, quotes=[]) is None
    assert all(fa._TM_TESTIMONIAL_LEAD not in e["body"] for e in camp["emails"])
    i = fa._tm_add_campaign_testimonial(camp, quotes=[("Great <team>.", "Jane Doe, Owner, Acme")])
    assert i is not None and i > 0
    body = camp["emails"][i]["body"]
    assert "&lt;team&gt;" in body and body.endswith("Worth a chat?")
    assert body.index(fa._TM_TESTIMONIAL_LEAD) < body.index("Worth a chat?")
    fa._tm_add_campaign_testimonial(camp, quotes=[("Newer.", "VP Ops")])
    all_bodies = " ".join(e["body"] for e in camp["emails"])
    assert all_bodies.count(fa._TM_TESTIMONIAL_LEAD) == 1 and "team" not in all_bodies
    fa._tm_add_campaign_testimonial(camp, quotes=[])
    assert fa._TM_TESTIMONIAL_LEAD not in " ".join(e["body"] for e in camp["emails"])


def test_email_quote_skips_first_email_and_profile_emails():
    import flowdrip_app as fa
    em = _emails(3)
    em[1]["body"] = fa._tm_insert_profiles(em[1]["body"], fa._tm_profiles_html(
        [{"title": "Dispatcher", "years": 4, "bullets": ["x"]}]))
    assert fa._tm_testimonial_email_index(em) == 2
    assert fa._tm_testimonial_email_index(_emails(1)) is None


# ── One shared link for every client ─────────────────────────────────────

def _client(ff):
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
    return TestClient(fake)


def test_shared_token_is_made_once_and_kept(ff):
    assert tt.shared_token("o@x.com", create=False) == ""
    tok = tt.shared_token("o@x.com")
    assert tok and tt.shared_token("o@x.com") == tok
    assert tt.find_shared(tok) == "o@x.com"
    # Saving requests never drops the shared link.
    tt.add_request("o@x.com", tt.new_request("Acme"))
    assert tt.shared_token("o@x.com", create=False) == tok


def test_shared_link_makes_one_entry_per_person(ff):
    c = _client(ff)
    tok = tt.shared_token("o@x.com")
    page = c.get(f"/review/{tok}")
    assert page.status_code == 200 and '"open": true' in page.text

    no_name = c.post(f"/review/{tok}/answers", json={"answers": {"fill": "lt2w"}, "about": {}})
    assert no_name.status_code == 400 and "name and company" in no_name.json()["error"]

    tokens = []
    for who, co in (("Jane Doe", "Acme Freight"), ("Bob Ray", "Beta Logistics")):
        r = c.post(f"/review/{tok}/answers", json={
            "answers": {"fill": "lt2w"},
            "about": {"name": who, "company": co, "title": "Owner", "hire": "Maria"}})
        assert r.status_code == 200
        j = r.json()
        assert j["token"] != tok and "under two weeks" in j["draft"]
        tokens.append(j["token"])
    reqs = tt.load_requests("o@x.com")
    assert {r["company"] for r in reqs} == {"Acme Freight", "Beta Logistics"}
    assert all(r["status"] == "answered" and r["source"] == "shared" for r in reqs)

    # Approving goes to the person's own entry; the shared link stays open.
    ok = c.post(f"/review/{tokens[0]}/approve", json={
        "quote": "Great.", "permission": "full", "name": "Jane Doe", "title": "Owner",
        "company": "Acme Freight"})
    assert ok.status_code == 200
    assert tt.find(tokens[0])[1]["status"] == "approved"
    assert c.get(f"/review/{tok}").status_code == 200
    assert tt.public_quotes("o@x.com") == [("Great.", "Jane Doe, Owner, Acme Freight")]


def test_shared_email_is_generic():
    subj, body = tt.shared_email("https://x/review/abc", "Sam", "ThriveModal")
    assert body.startswith("Hi,\n") and "https://x/review/abc" in body

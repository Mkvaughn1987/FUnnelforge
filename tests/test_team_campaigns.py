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
    assert ("running", "Current Running Campaigns", "running_campaigns") in rows
    assert fa.SIDEBAR_PAGE_ROW["running_campaigns"] == "running"
    assert "running" in fa._SIDEBAR_ICONS
    assert callable(fa.p_running_campaigns)

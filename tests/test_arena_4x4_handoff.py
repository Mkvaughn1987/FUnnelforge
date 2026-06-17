"""4x4 -> J Way newsletter handoff helpers.

Spec: docs/superpowers/specs/2026-06-17-arena-4x4-jway-handoff-design.md
Plan: docs/superpowers/plans/2026-06-17-arena-4x4-jway-handoff.md
"""
import datetime as _dt

import flowdrip_app as fa


# Saved 4x4 campaigns persist the type as template_key (= aicb_camp_type at
# build time). CAMP_OTHER stamps market_analysis=True the way the AICB
# autosave does for EVERY built campaign, to prove a non-4x4 is still
# excluded despite that flag.
CAMP_4X4 = {"name": "Acme 4x4", "template_key": "fourbyfour"}
CAMP_OTHER = {"name": "Acme Blitz", "template_key": "blitz",
              "market_analysis": True}


# ── _is_4x4_graduate ───────────────────────────────────────────────
def _gate(camp, email, responded=(), enrolled=(), dnc=()):
    return fa._is_4x4_graduate(
        {"Email": email}, camp,
        responded_emails=set(responded),
        enrolled_emails=set(enrolled),
        dnc_emails=set(dnc),
    )


def test_clean_non_responder_is_a_graduate():
    assert _gate(CAMP_4X4, "ceo@acme.com") is True


def test_responder_excluded():
    assert _gate(CAMP_4X4, "ceo@acme.com",
                 responded=["ceo@acme.com"]) is False


def test_already_enrolled_excluded():
    assert _gate(CAMP_4X4, "ceo@acme.com",
                 enrolled=["ceo@acme.com"]) is False


def test_dnc_excluded():
    assert _gate(CAMP_4X4, "ceo@acme.com", dnc=["ceo@acme.com"]) is False


def test_non_4x4_campaign_excluded():
    assert _gate(CAMP_OTHER, "ceo@acme.com") is False


def test_4x4_recognized_by_any_persisted_marker():
    for camp in ({"template_key": "fourbyfour"},
                 {"aicb_camp_type": "fourbyfour"},
                 {"_chooser_origin": "fourbyfour"}):
        assert fa._camp_is_4x4(camp) is True
    assert fa._camp_is_4x4({"template_key": "blitz"}) is False


def test_matching_is_case_insensitive():
    assert _gate(CAMP_4X4, "CEO@Acme.com",
                 responded=["ceo@acme.com"]) is False


def test_blank_email_excluded():
    assert _gate(CAMP_4X4, "") is False


# ── _build_jway_handoff_newsletter ─────────────────────────────────
def test_build_jway_newsletter_has_required_keys():
    camp = fa._build_jway_handoff_newsletter(
        name="Acme J Way Note", sector="construction",
        region="Phoenix, AZ", niche="", start_from=_dt.date(2026, 7, 1),
        count=12)
    assert camp["newsletter_style"] == "j_way"
    assert camp["market_analysis"] is True
    assert camp["name"] == "Acme J Way Note"
    assert camp["market_sector"] == "construction"
    assert camp["market_region"] == "Phoenix, AZ"
    assert camp["template_key"] == "evergreen"
    assert camp["status"] == "active"
    assert camp["contacts"] == []
    assert camp["contact_count"] == 0
    assert camp.get("handoff_default") is True


def test_build_jway_newsletter_makes_monthly_emails():
    camp = fa._build_jway_handoff_newsletter(
        name="N", sector="s", region="r", niche="", count=3,
        start_from=_dt.date(2026, 7, 1))
    assert len(camp["emails"]) == 3
    for em in camp["emails"]:
        assert em["step_type"] == "email_auto"
        assert em["fixed_date"]          # ISO date string present
        assert em["body"] == ""          # filled by auto-refresh before send

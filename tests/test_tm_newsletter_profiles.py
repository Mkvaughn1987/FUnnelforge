"""Sales-instance newsletters: the optional 3 AI sample talent profiles.

They must be labelled as samples, carry no pay figure, and leave Arena's
candidate spotlights untouched."""
import inspect

import flowdrip_app as fa


def test_full_send_block_asks_for_three_unpaid_samples():
    ins, schema = fa._tm_spotlight_prompt_block("Freight Brokerage", 3, "")
    assert "SAMPLE TALENT PROFILES" in ins and "composite" in ins
    assert "no pay, salary" in ins and "virtual assistant" in ins
    assert schema.count('"name": "Profile ') == 3
    assert '"salary_ask": ""' in schema
    assert fa._tm_spotlight_prompt_block("x", 0) == ("", "")


def test_recommendations_steer_the_profiles():
    ins, _ = fa._tm_spotlight_prompt_block("CPA Firms", 3, "staff accountants")
    assert "staff accountants" in ins


def test_organic_prompt_adds_profiles_only_when_asked():
    off = fa._jway_sales_prompt("Freight", "Freight Brokerage", "Dallas, TX",
                                "October 2026", "Pat", "Acme")
    on = fa._jway_sales_prompt("Freight", "Freight Brokerage", "Dallas, TX",
                               "October 2026", "Pat", "Acme", 3, "")
    assert '"candidates":[]' in off and "never include candidate profiles" in off
    assert on.count('"label":"Profile ') == 3
    assert '"salary":""' in on and "never include candidate profiles" not in on


def test_arena_spotlights_unchanged():
    ins, schema = fa._spotlight_prompt_block("construction", 3, [], "")
    assert "CANDIDATE SPOTLIGHTS" in ins and "salary_ask" in schema


def test_renderers_label_profiles_as_samples_on_sales_instances():
    src = inspect.getsource(fa._jway_render)
    assert "_TM_PROFILES_HEADING" in src
    assert fa._TM_PROFILES_HEADING == "Candidate Profiles"
    assert not hasattr(fa, "_TM_PROFILES_NOTE")


def test_dialogs_offer_the_toggle_and_save_three_or_zero():
    create = inspect.getsource(fa._create_newsletter_dialog)
    assert "_spotlight_count = 3 if _tm_profiles_in.value else 0" in create
    settings = inspect.getsource(fa._edit_newsletter_settings_dialog)
    assert "_new_count = 3 if _tm_prof_in.value else 0" in settings


# ── AI candidate profiles inside ThriveModal campaigns ─────────────────────

def test_campaign_profiles_block_is_honest_and_unlabelled():
    b = fa._tm_recruit_profiles_block(2, "Track and Trace Specialist", "Freight Brokerage")
    assert "weave 2 short candidate profiles" in b
    assert "Here are some of the candidate profiles in our pipeline:" in b
    assert "Never give a name" in b and "pay, salary" in b
    assert "do not call them samples" in b
    assert fa._tm_recruit_profiles_block(0, "", "") == ""


def test_ai_profiles_clamped_0_to_3():
    assert [fa._clamp_ai_profiles(v) for v in (None, "2", 9, -1, "x")] == [0, 2, 3, 0, 0]


def test_builder_uses_profiles_only_for_tm_without_real_candidates():
    src = inspect.getsource(fa._aicb_build_campaign_from_brief)
    assert "if not cand_block and (camp_type or \"\").strip() in _TM_TYPE_KEYS:" in src
    assert "ai_profiles=ai_profiles" in inspect.getsource(fa.generate_aicb_campaign)
    assert 'spec.get("ai_profiles")' in inspect.getsource(fa._api_create_campaign_blocking)


def test_campaign_profiles_carry_computed_hourly_rates(monkeypatch):
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda: True)
    monkeypatch.setattr(fa, "_tm_profile_rate",
                        lambda client, t: "Est. $9-$11/hr" if "Track" in t else "")
    b = fa._tm_recruit_profiles_block(
        2, "Track and Trace Specialist, Load Planner", "Freight Brokerage")
    assert "- Track and Trace Specialist: Est. $9-$11/hr" in b
    assert "Load Planner:" not in b          # no wage found, no rate line
    assert "ONE exception" in b and "any other pay, salary or rate" in b
    # No target roles: the vertical's usual roles are priced instead.
    b2 = fa._tm_recruit_profiles_block(1, "", "freight brokerage")
    assert "- Track and Trace Specialist: Est. $9-$11/hr" in b2


def test_campaign_profiles_without_rates_keep_the_pay_ban(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda: False)
    b = fa._tm_recruit_profiles_block(1, "Bookkeeper", "Accounting")
    assert "RATES:" not in b and "pay, salary, a rate" in b

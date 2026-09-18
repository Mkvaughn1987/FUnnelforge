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
    assert "_TM_PROFILES_HEADING" in src and "_TM_PROFILES_NOTE" in src
    assert "Illustrative" in fa._TM_PROFILES_NOTE


def test_dialogs_offer_the_toggle_and_save_three_or_zero():
    create = inspect.getsource(fa._create_newsletter_dialog)
    assert "_spotlight_count = 3 if _tm_profiles_in.value else 0" in create
    settings = inspect.getsource(fa._edit_newsletter_settings_dialog)
    assert "_new_count = 3 if _tm_prof_in.value else 0" in settings

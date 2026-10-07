"""The "Find Candidates for an Opening" card on DripDrop's AI Prompts page
(Mike, 2026-10-06): the one run whose recipients are the candidates.

Spec: docs/superpowers/specs/2026-10-06-find-candidates-prompt-design.md
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ai_prompts_catalogue import _stub_nicegui  # noqa: E402

KEY = "staff_find_candidates"


@pytest.fixture(scope="module")
def mods():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_prompts
    import staffing_prompts
    return ai_prompts, staffing_prompts


FILLED = {
    "role": "Plant Manager", "client": "Acme Packaging",
    "location": "Windsor, CO", "fc_titles": "Plant Manager, Production Manager",
    "target_companies": "Northgate Industrial; Summit Packaging",
    "zip": "80550",
}


def _prompt(mods, **vals):
    aip, sp = mods
    r = sp.STAFFING.routine_by_key[KEY]
    v = aip.defaults_for(r)
    v.update(vals)
    return " ".join(aip.build_prompt({"routine": KEY, "vals": v},
                                     sp.STAFFING).split())


def test_card_sits_right_after_mpc(mods):
    aip, sp = mods
    ids = [st["id"] for st in sp.STAFFING.starters]
    assert ids.index(KEY) == ids.index("mpc") + 1
    st = sp.STAFFING.starter_by_id[KEY]
    assert st["label"] == "Find Candidates for an Opening"
    assert st["routine"] == KEY
    # Not on ARENA itself: this card is DripDrop's staffing board only.
    assert KEY not in aip.ARENA.starter_by_id
    assert KEY not in aip.ARENA.routine_by_key


def test_questions_and_defaults(mods):
    aip, sp = mods
    r = sp.STAFFING.routine_by_key[KEY]
    fb = r["field_by_key"]
    asked = [f["key"] for f in r["fields"] if f["ask"]]
    assert asked == ["role", "client", "location", "fc_titles"]
    assert fb["confidential"]["default"] is True
    assert fb["include_alumni"]["default"] is False
    assert fb["add_to_pipeline"]["default"] is True
    assert fb["skip_customers"]["default"] is True
    assert fb["skip_contacted"]["default"] is True
    assert fb["cand_cadence"]["default"] == "Three, over a week"
    assert fb["cand_cadence"]["options"] == list(aip.CADENCE_KEY)
    assert fb["companies"]["default"] == "20"
    assert fb["contacts_each"]["default"] == "5"
    assert fb["email_cap"]["default"] == "100"
    # No newsletter and no candidate slate: the people found ARE the run.
    for k in ("newsletter_mode", "newsletter", "cand_picks", "cand_match",
              "cand_ai", "sequence", "saved_style", "skip_recruiters",
              "only_these", "vertical"):
        assert k not in fb, k
    # The shared schedule block is there.
    assert "repeat_on" in fb and "repeat_time" in fb
    assert sorted(set(r["tools"])) == ["campaign_get", "campaigns_list",
                                       "create_campaign",
                                       "import_candidate_records"]


def test_show_if_follows_the_mode_answers(mods):
    aip, sp = mods
    r = sp.STAFFING.routine_by_key[KEY]
    fb = r["field_by_key"]
    v = aip.defaults_for(r)
    assert aip._visible(r, v, fb["target_companies"])
    assert not aip._visible(r, v, fb["industry"])
    assert aip._visible(r, v, fb["zip"]) and aip._visible(r, v, fb["radius"])
    assert not aip._visible(r, v, fb["state"])
    v["seed_mode"] = sp.FC_SEED_MODES[1]
    v["geo_mode"] = sp.FC_GEO_MODES[1]
    assert not aip._visible(r, v, fb["target_companies"])
    assert aip._visible(r, v, fb["industry"])
    assert not aip._visible(r, v, fb["zip"])
    assert aip._visible(r, v, fb["state"])


def test_default_prompt_named_seeds_confidential(mods):
    p = _prompt(mods, **FILLED)
    assert "{" not in p.replace('{"label"', "")
    assert "I HAVEN'T DECIDED THESE" not in p
    assert "The opening is Plant Manager at Acme Packaging, Windsor, CO." in p
    assert ("The client is confidential: never name Acme Packaging in the "
            "emails") in p
    # Companies: pin the seeds, expand with lookalikes, drop seeds + client.
    assert ("Pin each of these in ZoomInfo with search_companies: Northgate "
            "Industrial, Summit Packaging.") in p
    assert "find_similar_companies on each one with sameIndustry and sameEmployeeRange" in p
    assert "20 companies of about 50 to 1000 people within 25 miles of 80550" in p
    assert "find_similar_companies has no location filter" in p
    assert "zipCode 80550 with zipCodeRadiusMiles 25" in p
    assert "drop Acme Packaging: nobody who works there is a candidate" in p
    # Exclusions: customers on by default, no "worked"/recruiters clauses.
    assert "companies we already do business with" in p
    assert "already worked" not in p
    # People.
    assert "jobTitleList with one title per entry from Plant Manager, Production Manager" in p
    assert "managementLevelList Non Manager and Manager" in p
    assert "2 to 10 years of experience" in p
    assert "current job 2 to 8 years" in p
    assert "requiredFieldsList email" in p
    assert "contactAccuracyScoreMinimum 80" in p
    assert "Keep the best 5 at each company." in p
    assert "companyPastOrPresent" not in p
    assert "Business email addresses only" in p
    assert "Never anyone currently at Acme Packaging." in p
    assert "enrich_contacts in batches of 10" in p
    # Dedupe against earlier runs, then the Pipeline.
    assert ('open every campaign called "Find Candidates - Plant Manager" '
            'with campaign_get') in p
    assert "import_candidate_records, one record per person: external_id set to zi-" in p
    # Review then launch: run-through, no "say go".
    assert "must not send more than 100 emails" in p
    assert "say go" not in p
    assert 'template "findcandidates": role "Plant Manager", client "Acme Packaging", confidential true' in p
    assert 'location "Windsor, CO"' in p
    assert 'cadence "three_emails_1week"' in p
    assert 'name "Find Candidates - Plant Manager"' in p
    assert "phone_mobile and phone_office" in p
    assert "selling_points left out" in p and "job_description left out" in p
    # The ZoomInfo rule is in the steps, so no second ZOOMINFO section.
    assert p.count("recruiter-app.zoominfo.com") == 1
    tools = p.split("TOOLS")[1]
    for t in ("campaigns_list", "campaign_get", "import_candidate_records",
              "create_campaign"):
        assert t in tools
    assert "newsletter" not in p.lower()
    assert "candidates_search" not in p


def test_blank_required_answers_show_as_gaps_and_questions(mods):
    aip, sp = mods
    r = sp.STAFFING.routine_by_key[KEY]
    qs = aip._open_questions(r, aip.defaults_for(r))
    assert qs == ["The role you are filling", "Who the client is",
                  "Where the job is", "Titles to search for"]
    p = _prompt(mods)
    assert "<the role you are filling>" in p
    assert "<which companies to start from>" in p
    assert "<titles to search for>" in p
    assert "<zip code>" in p
    assert 'name "Find Candidates - <the role you are filling>"' in p


def test_named_client_and_industry_mode(mods):
    p = _prompt(mods, confidential=False, seed_mode="An industry and a size band",
                industry="corrugated packaging manufacturers",
                company_size="100 to 500 people", **FILLED)
    assert "Name Acme Packaging in the emails." in p
    assert "confidential false" in p
    assert ("Use ZoomInfo's search_companies to find 20 corrugated packaging "
            "manufacturers companies of about 100 to 500 people within 25 "
            "miles of 80550. Pass zipCode 80550 with zipCodeRadiusMiles 25.") in p
    assert "find_similar_companies" not in p
    assert "Northgate" not in p


def test_state_and_nationwide_geography(mods):
    p = _prompt(mods, geo_mode="A whole state", state="Colorado", **FILLED)
    assert "companies of about 50 to 1000 people in Colorado" in p
    assert "keep only the ones with a site in Colorado" in p
    assert "sorted by contact accuracy, state Colorado." in p
    assert "zipCode" not in p
    p = _prompt(mods, geo_mode="Anywhere in the United States", **FILLED)
    assert "anywhere in the United States" in p
    assert "no location filter" not in p
    assert "zipCode" not in p and "state Colorado" not in p
    # The zip the user typed is still in the table but not in the filter.
    assert "sorted by contact accuracy. Keep the best" in p


def test_radius_blank_means_25_and_typed_radius_wins(mods):
    assert "within 25 miles of 80550" in _prompt(mods, **FILLED)
    assert "within 50 miles of 80550" in _prompt(mods, radius="50", **FILLED)


def test_levels_alumni_and_cadence(mods):
    p = _prompt(mods, levels="Directors and above", include_alumni=True,
                cand_cadence="One email", **FILLED)
    assert "managementLevelList Director, VP Level Exec and C Level Exec" in p
    assert "second pass on each company with companyPastOrPresent set to past" in p
    assert 'cadence "one_email"' in p
    p = _prompt(mods, levels="Any level", **FILLED)
    assert "managementLevelList" not in p


def test_opening_extras_reach_create_campaign(mods):
    p = _prompt(mods, pay="$120k to $140k",
                selling_points="new line next spring\nno weekend shifts",
                jd="We need a plant manager who...", campaign_name="PM search",
                **FILLED)
    assert 'pay "$120k to $140k"' in p
    assert 'selling_points set to ["new line next spring", "no weekend shifts"]' in p
    assert "job_description the job description from THE DETAILS above, in full" in p
    assert 'name "PM search"' in p
    assert 'open every campaign called "PM search"' in p
    assert "Pay range: $120k to $140k" in p


def test_toggles_drop_their_steps(mods):
    p = _prompt(mods, add_to_pipeline=False, skip_contacted=False,
                skip_customers=False, **FILLED)
    assert "import_candidate_records, one record" not in p
    assert "campaign_get, and drop anyone" not in p
    assert "Take these out before you go any further" not in p
    p = _prompt(mods, never_these="Westgate Box", **FILLED)
    assert "these by name: Westgate Box" in p


def test_old_setup_with_three_day_cadence_still_opens(mods):
    p = _prompt(mods, cand_cadence="Three, over three days", **FILLED)
    assert 'cadence "three_emails_3days"' in p


def test_the_staffing_hooks_leave_this_run_alone(mods):
    aip, sp = mods
    r = sp.STAFFING.routine_by_key[KEY]
    vals = aip.defaults_for(r)
    assert sp.prefill_staffing(r, vals) == {}
    assert sp.checklist_staffing(r, vals, "signals") == []
    assert not r.get("recommend")
    for name in ("Claude", "ChatGPT", "GPT"):
        assert name not in _prompt(mods, **FILLED)

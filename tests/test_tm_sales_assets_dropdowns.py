"""Sales Assets on ThriveModal (Mike 2026-11-05): Industry and Jobs are
drop-downs of the most popular offshore industries and the jobs each is
sold on. Either can be typed instead, and the company is optional."""
import inspect

import flowdrip_app as fa
import tm_prompts as tp


# ── the lists ──────────────────────────────────────────────────────────

def test_every_vertical_has_an_industry_row_in_the_same_order():
    assert [k for k, _n, _a, _j in tp.INDUSTRY_JOBS] == \
        [v["key"] for v in tp.VERTICALS]
    assert len(set(tp.INDUSTRY_NAMES)) == len(tp.INDUSTRY_NAMES)
    assert tp.INDUSTRY_NAMES[0] == "Logistics and 3PL"


def test_every_industry_offers_remote_capable_jobs_without_repeats():
    for _key, name, _aliases, jobs in tp.INDUSTRY_JOBS:
        assert len(jobs) >= 5, name
        assert len({j.lower() for j in jobs}) == len(jobs), name
        for j in jobs:
            # Offshore work only: nothing that has to be done on site.
            assert fa._tm_remote_capable(j), (name, j)
            # A comma would split one title into two Target Roles.
            assert "," not in j and ";" not in j, (name, j)


def test_priced_verticals_lead_with_the_cost_comparison_roles():
    """So the Staffing Cost Comparison's five rows did not change."""
    key_of = {"general": "general_offshore"}
    for key, name, _aliases, jobs in tp.INDUSTRY_JOBS:
        cost = fa._TM_VERTICAL_COST_ROLES.get(key_of.get(key, key))
        if cost:
            assert jobs[:len(cost)] == cost, name


def test_new_titles_price_as_the_right_occupation():
    assert fa._tm_soc_for_role(None, "Production Scheduler")[0] == "435061"
    assert fa._tm_soc_for_role(None, "Paralegal")[0] == "232011"
    assert fa._tm_soc_for_role(None, "Scheduling Coordinator")[0] == "436014"
    # The medical-office scheduler rows are untouched.
    assert fa._tm_soc_for_role(None, "Patient Scheduler")[0] == "436013"


# ── matching free text to the list ─────────────────────────────────────

def test_industry_pick_matches_names_labels_and_aliases():
    assert tp.industry_pick("Logistics and 3PL") == "Logistics and 3PL"
    assert tp.industry_pick("logistics") == "Logistics and 3PL"
    assert tp.industry_pick("Logistics & Supply Chain") == "Logistics and 3PL"
    # The AI Prompt page's market label for the same vertical.
    assert tp.industry_pick("Home care agencies") == "Home Care"
    assert tp.industry_pick("Construction") == "Construction and Engineering"
    assert tp.industry_pick("Accounting & Finance") == \
        "Accounting and Bookkeeping"


def test_industry_pick_leaves_other_industries_alone():
    for text in ("", None, "Fintech", "Healthcare Construction",
                 "Insurance agencies", "Other (type your own)"):
        assert tp.industry_pick(text) == "", text
    assert tp.industry_jobs("Fintech") == []


def test_other_is_never_an_industry_name():
    assert fa._PDF_INDUSTRY_OTHER not in fa._pdf_industry_names()
    assert fa._pdf_industry_pick(fa._PDF_INDUSTRY_OTHER) == ""


# ── the Jobs drop-down ─────────────────────────────────────────────────

def test_job_choices_offer_the_industry_list_plus_own_jobs():
    opts, sel = fa._pdf_job_choices("Logistics and 3PL", "dispatcher, Tracer")
    assert opts[:2] == ["Track and Trace Specialist", "Dispatcher"]
    # A typed job joins the options; a listed one is spelled as listed.
    assert opts[-1] == "Tracer"
    assert sel == ["Dispatcher", "Tracer"]
    assert all(s in opts for s in sel)


def test_job_choices_fall_back_to_general_back_office():
    general = tp.industry_jobs("General Back Office")
    assert fa._pdf_job_choices("", "")[0] == general
    assert fa._pdf_job_choices("Insurance agencies", "")[0] == general
    assert "Administrative Assistant" in general


def test_merge_roles_folds_in_a_typed_job_once():
    assert fa._pdf_merge_roles(["Dispatcher", "Tracer"],
                               " tracer, Claims Clerk") == \
        "Dispatcher, Tracer, Claims Clerk"
    assert fa._pdf_merge_roles([], "") == ""
    assert fa._pdf_merge_roles(None, "Estimator") == "Estimator"


def test_switching_industry_drops_the_old_lists_jobs_only():
    out = fa._pdf_switch_industry_roles(
        "Dispatcher, Tracer, Customer Service Representative",
        "Logistics and 3PL", "HVAC and Home Services")
    # Dispatcher and CSR are on both lists; Tracer was typed by hand.
    assert out == "Dispatcher, Tracer, Customer Service Representative"
    out = fa._pdf_switch_industry_roles(
        "Dispatcher, Tracer, Load Planner",
        "Logistics and 3PL", "Accounting and Bookkeeping")
    assert out == "Tracer"


# ── the Staffing Cost Comparison follows the drop-down ─────────────────

def test_cost_roles_use_the_picked_industrys_jobs(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    roles = fa._tm_cost_roles("Dispatcher", "HVAC and Home Services", "")
    assert roles[:3] == ["Dispatcher", "Customer Service Representative",
                         "Appointment Setter"]
    # "Dispatcher" alone used to pull in the freight list.
    assert "Track and Trace Specialist" not in roles
    # An industry that is not on the list keeps the keyword routing.
    roles = fa._tm_cost_roles("", "Regional trucking", "")
    assert roles[0] == "Track and Trace Specialist"


def test_cost_roles_ignore_the_lists_off_thrivemodal(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    roles = fa._tm_cost_roles("", "HVAC and Home Services", "")
    assert roles == fa._TM_VERTICAL_COST_ROLES["general_offshore"]


# ── the page ───────────────────────────────────────────────────────────

def test_form_has_the_drop_downs_on_thrivemodal_only():
    src = inspect.getsource(fa.p_pdf_gen)
    form = src[src.index("# Input form (now in stage 2 only)"):]
    tm = form[form.index("if _pdf_tm:\n            # A typed or pre-filled"):
              form.index('ui.label("Company or Market *")')]
    assert 'ui.label("Industry *")' in tm
    assert "_pdf_industry_names() + [_PDF_INDUSTRY_OTHER]" in tm
    assert 'ui.label("Jobs *")' in tm
    assert "_pdf_job_choices(s._pdf_industry, s._pdf_role)" in tm
    assert "multiple=True" in tm
    assert "+ Add job" in tm
    # Arena keeps the typed boxes.
    assert 'ui.label("Company or Market *")' in form
    assert 'ui.label("Target Role *")' in form


def test_thrivemodal_form_has_no_autofill_button():
    """The drop-downs fill the form, so Autofill with AI is only drawn on
    the typed form other workspaces keep."""
    src = inspect.getsource(fa.p_pdf_gen)
    form = src[src.index("# Input form (now in stage 2 only)"):]
    calls = form.replace("def _pdf_autofill_row():", "")
    assert calls.count("_pdf_autofill_row()") == 1
    typed = calls[calls.index('ui.label("Company or Market *")'):
                  calls.index('ui.label("Target Role *")')]
    assert "_pdf_autofill_row()" in typed


def test_company_is_optional_on_thrivemodal():
    src = inspect.getsource(fa.p_pdf_gen)
    ready = src[src.index("def _pdf_form_ready"):src.index("def _generate_pdf")]
    tm, rest = ready.split("if not (s._pdf_company and", 1)
    assert "s._pdf_industry and s._pdf_role and s._pdf_location" in tm
    assert "_pdf_company" not in tm
    # No company: the PDFs are written for the industry.
    gen = src[src.index("def _generate_pdf"):]
    assert "company = s._pdf_company or s._pdf_industry" in gen
    assert '"market_only": _market_only' in gen
    # Both buttons go through the same check.
    assert src.count("if not _pdf_form_ready():") == 2


def test_other_industry_flag_is_initialised_and_cleared():
    s = fa.AppState()
    fa._ensure_pdf_state(s)
    assert s._pdf_industry_other is False
    src = inspect.getsource(fa.p_pdf_gen)
    clear = src[src.index("def _clear_pdf"):
                src.index("if s._pdf_company or s._pdf_role or s._pdf_result")]
    assert "_pdf_industry_other = False" in clear

"""inboxslide Target details can start from an uploaded contact list: the
rows become the campaign's contacts, the company (or the market when the
list spans several employers) is read from the rows, and it is researched
the same way Autofill is, positions included. The list's own job titles
are never the Target Positions."""
import inspect
import threading

import flowdrip_app as fa


def _row(email="", company="", title="", domain=""):
    return {"Email": email, "Company": company, "JobTitle": title,
            "CompanyDomain": domain}


# ── who the list is about ────────────────────────────────────────────────

def test_one_domain_is_a_company():
    rows = [_row("a@ydlogistics.com", "Yellow Diamond Logistics"),
            _row("b@ydlogistics.com", "Yellow Diamond Logistics, Inc."),
            _row("c@ydlogistics.com", "YD Logistics"),
            _row("d@ydlogistics.com", "YD Logistics")]
    t = fa._tm_contacts_target(rows)
    # "Yellow Diamond Logistics" and "... , Inc." fold together, so with
    # 2 vs 2 the tie breaks by name; folded spellings beat exact ones.
    assert t["mode"] == "company" and t["website"] == "ydlogistics.com"
    assert t["companies"] == 1
    assert t["company"] in ("Yellow Diamond Logistics", "YD Logistics")
    rows.append(_row("e@ydlogistics.com", "Yellow Diamond Logistics Inc"))
    assert fa._tm_contacts_target(rows)["company"] == "Yellow Diamond Logistics"


def test_majority_domain_is_still_a_company():
    rows = [_row("a@acme.com", "Acme")] * 7 + [_row("x@other.com", "Other")] * 3
    t = fa._tm_contacts_target(rows)
    assert t["mode"] == "company" and t["website"] == "acme.com"
    assert t["companies"] == 2


def test_spread_list_is_a_market():
    rows = [_row("a@acme.com", "Acme"), _row("b@beta.com", "Beta"),
            _row("c@gamma.com", "Gamma"), _row("d@delta.com", "Delta")]
    t = fa._tm_contacts_target(rows)
    assert t == {"mode": "market", "company": "", "website": "",
                 "companies": 4}


def test_freemail_rows_join_their_company_by_name():
    # gmail says nothing about the employer; the Company column does.
    rows = [_row("a@acme.com", "Acme Inc"), _row("b@gmail.com", "Acme, Inc."),
            _row("c@yahoo.com", "acme llc")]
    t = fa._tm_contacts_target(rows)
    assert t["mode"] == "company" and t["website"] == "acme.com"
    assert t["companies"] == 1


def test_company_column_only_no_domain():
    rows = [_row("a@gmail.com", "Acme"), _row("b@gmail.com", "Acme")]
    t = fa._tm_contacts_target(rows)
    assert t == {"mode": "company", "company": "Acme", "website": "",
                 "companies": 1}


def test_company_domain_column_wins_over_email():
    rows = [_row("a@gmail.com", "", domain="https://www.acme.com/about")]
    t = fa._tm_contacts_target(rows)
    assert t["mode"] == "company" and t["website"] == "acme.com"
    assert t["company"] == ""  # the lookup names it from the domain


def test_nothing_identifying_is_no_mode():
    rows = [_row("a@gmail.com"), _row("", "", "CEO"), {}]
    assert fa._tm_contacts_target(rows)["mode"] == ""
    assert fa._tm_contacts_target([])["mode"] == ""


# ── applying an upload ───────────────────────────────────────────────────

class _SyncThread:
    def __init__(self, target=None, daemon=None, **kw):
        self._t = target

    def start(self):
        self._t()


def test_one_company_list_runs_the_company_autofill(monkeypatch):
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "sk-test")
    calls = []
    monkeypatch.setattr(fa, "_aicb_ai_extract",
                        lambda s, text, mode, rf: calls.append((text, mode)))
    s = fa.AppState()
    s.aicb_sel_roles = ["Stale"]
    s._tm_open_roles = ["Stale"]
    rows = [_row("a@ydlogistics.com", "Yellow Diamond Logistics", "Owner"),
            _row("b@ydlogistics.com", "Yellow Diamond Logistics", "Controller")]
    fa._tm_upload_contacts_apply(s, rows, lambda: None)
    assert s.aicb_contacts == rows
    assert s.aicb_target_mode == "company"
    assert s.aicb_company == "Yellow Diamond Logistics"
    assert s.aicb_website == "ydlogistics.com"
    assert calls == [("ydlogistics.com", "company")]
    assert s.aicb_sel_roles == [] and s._tm_open_roles == []
    assert s._tm_upload_err == ""


def test_market_list_analyses_then_researches_positions_by_industry(monkeypatch):
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(threading, "Thread", _SyncThread)

    def _fake_analyse(s, rows):
        s.aicb_primary_industry = "Construction"
        s.aicb_sel_roles = ["Owner", "Controller"]  # the list's titles

    monkeypatch.setattr(fa, "_analyze_contacts_with_ai", _fake_analyse)
    seen = {}

    def _fake_research(client, company, website, industry):
        seen.update(company=company, website=website, industry=industry)
        return {"picks": ["Estimator", "AP/AR Specialist"],
                "open": ["Estimator", "AP/AR Specialist", "Scheduler"]}

    monkeypatch.setattr(fa, "_tm_research_offshore_roles", _fake_research)
    monkeypatch.setattr(fa, "_aicb_ai_extract",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    import types, sys
    sys.modules.setdefault("anthropic", types.SimpleNamespace(
        Anthropic=lambda api_key=None: object()))
    s = fa.AppState()
    rows = [_row("a@acme.com", "Acme"), _row("b@beta.com", "Beta"),
            _row("c@gamma.com", "Gamma"), _row("d@delta.com", "Delta")]
    fa._tm_upload_contacts_apply(s, rows, lambda: None)
    assert s.aicb_target_mode == "market"
    assert s.aicb_company == "" and s.aicb_website == ""
    assert seen == {"company": "", "website": "", "industry": "Construction"}
    # Positions come from the research, never from the list's titles.
    assert s.aicb_sel_roles == ["Estimator", "AP/AR Specialist"]
    assert s._tm_open_roles == ["Estimator", "AP/AR Specialist", "Scheduler"]
    assert s._aicb_qs_running is False
    assert s._tm_upload_err == ""


def test_unidentified_list_keeps_contacts_and_explains(monkeypatch):
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(fa, "_aicb_ai_extract",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    s = fa.AppState()
    rows = [_row("a@gmail.com", "", "CEO")]
    fa._tm_upload_contacts_apply(s, rows, lambda: None)
    assert s.aicb_contacts == rows
    assert "no Company or work-email column" in s._tm_upload_err


def test_empty_file_clears_contacts_and_explains():
    s = fa.AppState()
    s.aicb_contacts = [_row("a@acme.com", "Acme")]
    fa._tm_upload_contacts_apply(s, [], lambda: None)
    assert s.aicb_contacts == []
    assert "Email column" in s._tm_upload_err


def test_industry_only_prompt_for_a_market_list():
    p = fa._tm_offshore_roles_prompt("", "", "Construction")
    assert p.startswith("Industry:")
    assert "Construction" in p
    assert "could be done remotely by an offshore team member" in p
    assert "never return an error" in p
    # A domain alone is still a company.
    assert fa._tm_offshore_roles_prompt("", "acme.com", "").startswith("Company:")


# ── wiring (source greps) ────────────────────────────────────────────────

def test_card_is_on_sales_target_details_only():
    src = inspect.getsource(fa.p_ai_campaign)
    assert ("if _SALES_MODE:\n"
            "                        # inboxslide: a contact list can start the campaign.\n"
            "                        _render_tm_contacts_upload(s, rf)") in src
    # Contact titles never become Target Positions on the sales instance.
    assert "and _tis and not _SALES_MODE:" in src
    assert '("Have a contact list?",' in src


def test_card_copy_and_upload_plumbing():
    src = inspect.getsource(fa._render_tm_contacts_upload)
    assert "Start from a contact list" in src
    assert '"Replace list" if n else "Upload CSV"' in src
    assert "dd-tm-uploader" in src
    assert "safe_read_csv_rows(str(tmp))" in src
    assert "_normalize_rows(raw_rows)" in src
    assert "_tm_upload_contacts_apply(s, rows, rf)" in src
    assert "_MAX_CSV_BYTES" in src and "_ALLOWED_CSV_EXTS" in src
    assert 'if busy and mode != "company":' in src


def test_fresh_objective_clears_upload_state():
    src = inspect.getsource(fa._tm_start_objective)
    assert 's._tm_upload_err = ""' in src
    assert 's._tm_upload_name = ""' in src
    assert "s._tm_open_roles = []" in src

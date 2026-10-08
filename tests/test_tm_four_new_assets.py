"""Mike, 2026-10-07: Interview Guide retired on ThriveModal; four new Sales
Assets take its place (Myths vs Reality, Roles That Work Offshore, First 90
Days Plan, Security & Confidentiality)."""
import flowdrip_app as fa

CTX = {"company": "Acme Freight", "primary_industry": "Logistics",
       "positions": "AP Clerk", "location": "Houston, TX"}
NEW = ("tm_myths", "tm_roles_map", "tm_first_90", "tm_security")


def _tm(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)


def test_new_kinds_are_thrivemodal_kinds_everywhere():
    for k in NEW:
        assert k in fa._TM_PDF_KINDS
        assert fa._is_tm_pdf_kind(k)       # Fable + playbook, TM flag or not


def test_each_new_prompt_is_grounded_and_playbook_bound(monkeypatch):
    _tm(monkeypatch)
    for k in NEW:
        p = fa._rich_pdf_prompt(k, CTX)
        assert "THRIVEMODAL PLAYBOOK" in p, k
        assert p.endswith(fa._PDF_LENGTH_RULES), k
        head = p.split("THRIVEMODAL PLAYBOOK")[0]
        assert "construction" not in head.lower(), k
        assert "jobsite" not in head.lower(), k
        assert "Philippines" in head, k


def test_myths_prompt_answers_objections_from_the_playbook(monkeypatch):
    _tm(monkeypatch)
    p = fa._rich_pdf_prompt("tm_myths", CTX)
    for word in ("Myth", "Reality", "quality", "communication", "security",
                 "control", "nationality"):
        assert word in p


def test_roles_map_is_seeded_with_the_cost_roles(monkeypatch):
    _tm(monkeypatch)
    monkeypatch.setattr(fa, "_tm_cost_roles",
                        lambda role, ind, co: ["AP Clerk", "Dispatcher",
                                               "Freight Billing Specialist"])
    p = fa._rich_pdf_prompt("tm_roles_map", CTX)
    assert "Dispatcher" in p and "Freight Billing Specialist" in p
    assert "What Stays With You" in p


def test_first_90_is_a_proposal_not_a_promise(monkeypatch):
    _tm(monkeypatch)
    p = fa._rich_pdf_prompt("tm_first_90", CTX)
    assert "Suggested:" in p and "1-30" in p and "61-90" in p
    assert "Us" in p and "You" in p


def test_security_names_practices_not_certifications(monkeypatch):
    _tm(monkeypatch)
    p = fa._rich_pdf_prompt("tm_security", CTX)
    for word in ("NDA", "VPN", "isolated workstation", "certification"):
        assert word in p
    assert "What You Control" in p


def test_fixed_titles_for_the_new_kinds(monkeypatch):
    _tm(monkeypatch)
    want = {"tm_myths": "Offshore: Myths vs Reality",
            "tm_roles_map": "Roles That Work Offshore",
            "tm_first_90": "First 90 Days Plan",
            "tm_security": "Security and Confidentiality"}
    for k, label in want.items():
        d = {"title": "Houston Construction Something", "sections": []}
        fa._tm_fix_pdf_labels(k, CTX, d)
        assert d["title"] == f"{label} - Acme Freight", k
        assert d["badge"] == label.upper(), k


def test_campaigns_offer_the_new_kinds_and_not_the_interview_guide():
    kinds = [k for k, *_ in fa._TM_CAMPAIGN_PDF_KINDS]
    assert kinds[:3] == ["tm_role_blueprint", "tm_cost_compare", "tm_how_it_works"]
    assert "interview_guide" not in kinds
    for k in NEW:
        assert k in kinds
    assert len(fa._TM_CAMPAIGN_PDF_OFFERED) == 8
    assert set(fa._TM_CAMPAIGN_PDF_BLURBS) == set(kinds)
    assert set(fa._TM_PDF_STEP_WORDS) == set(kinds)
    for _k, _l, line in fa._TM_CAMPAIGN_PDF_KINDS:
        assert line.startswith("I've attached")


def test_sales_assets_menu_matches():
    kinds = [m["kind"] for m in fa._tm_sales_asset_menu()]
    assert "interview_guide" not in kinds
    assert kinds[-1] == "custom" and kinds[-2] == "market_pulse"
    assert set(NEW) <= set(kinds)


def test_retired_interview_guide_keeps_a_readable_filename():
    assert fa._tm_campaign_pdf_filename("interview_guide", "Acme") == \
        "Interview Guide Acme.pdf"
    assert fa._tm_campaign_pdf_filename("tm_myths", "Acme Freight") == \
        "Offshore Myths vs Reality Acme Freight.pdf"

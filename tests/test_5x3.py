"""Arena 5x3 campaign + resume engine (PipelineBlast Component 1).
Import flowdrip_app lazily inside each test (per tests/conftest.py)."""


def _get(fa, key):
    for t in fa.AICB_CAMPAIGN_TYPES:
        if t[0] == key:
            return t
    return None


def test_fivebythree_registered_after_fivebyfive():
    import flowdrip_app as fa
    keys = [t[0] for t in fa.AICB_CAMPAIGN_TYPES]
    assert "fivebythree" in keys
    assert keys.index("fivebythree") == keys.index("fivebyfive") + 1
    t = _get(fa, "fivebythree")
    assert t[1] == "Arena 5×3"
    assert t[2] == "5 steps - 2 weeks"


def test_fivebythree_prompt_has_five_steps():
    import flowdrip_app as fa
    prompt = _get(fa, "fivebythree")[6]
    positions = [prompt.find(f"Step {n} -") for n in range(1, 6)]
    assert all(p != -1 for p in positions), positions
    assert positions == sorted(positions)
    assert "Step 6 -" not in prompt


def test_fivebythree_in_slate_family():
    import flowdrip_app as fa
    assert "fivebythree" in fa._ARENA_SLATE_TYPES
    assert fa._camp_is_4x4({"aicb_camp_type": "fivebythree"}) is True
    assert fa._resume_attach_indices("fivebythree", 5) == [1, 3]


def _sample_5x3_generated():
    return {"emails": [
        {"name": "Step 1 - Warm Intro", "step_type": "email_auto",
         "subject": "Quick note for Acme", "body": "Hi {FirstName},<br><br>intro",
         "delay_days": 0, "attachments": []},
        {"name": "Step 2 - Candidate Slate", "step_type": "email_auto",
         "subject": "A few candidates...", "body": "Hi {FirstName},<br><br>slate",
         "delay_days": 3, "attachments": ["Resume_Candidate_A_Redacted.pdf"]},
        {"name": "Step 3 - Interview Guide", "step_type": "email_auto",
         "subject": "An interview guide, in case it helps",
         "body": '<div style="font-family:Aptos,Calibri,Arial,sans-serif;font-size:11pt;">Hi {FirstName},<br><br>guide</div>',
         "delay_days": 9, "attachments": []},
        {"name": "Step 4 - Following up", "step_type": "email_auto",
         "subject": "Following up", "body": "Hi {FirstName},<br><br>AI DRIFT TEXT",
         "delay_days": 9, "attachments": ["Resume_Candidate_A_Redacted.pdf"]},
        {"name": "Step 5 - Closing the loop", "step_type": "email_auto",
         "subject": "Closing the loop for now", "body": "Hi {FirstName},<br><br>close",
         "delay_days": 9, "attachments": []},
    ]}


def test_5x3_overrides_noop_for_other_types():
    import flowdrip_app as fa
    data = fa._apply_fivebythree_overrides("fivebyfive", _sample_5x3_generated())
    bump = next(e for e in data["emails"] if e["name"].startswith("Step 4"))
    assert "AI DRIFT TEXT" in bump["body"]


def test_5x3_bump_verbatim_keeps_attachments_and_schedule():
    import flowdrip_app as fa
    data = fa._apply_fivebythree_overrides("fivebythree", _sample_5x3_generated())
    bump = next(e for e in data["emails"] if e["name"].startswith("Step 4"))
    assert bump["subject"] == "Following up"
    assert "AI DRIFT TEXT" not in bump["body"]
    assert "review the résumés" in bump["body"] or "look over the résumés" in bump["body"]
    # 5x3 bump RE-ATTACHES resumes — must NOT be cleared (unlike the 5x5)
    assert bump["attachments"] == ["Resume_Candidate_A_Redacted.pdf"]
    assert bump["delay_days"] == 2  # pinned from a drifted 9
    assert "—" not in bump["body"] and "–" not in bump["body"]


def test_5x3_interview_line_once_inside_div():
    import flowdrip_app as fa
    data = fa._apply_fivebythree_overrides("fivebythree", _sample_5x3_generated())
    guide = next(e for e in data["emails"] if e["name"].startswith("Step 3"))
    assert "interview guide" in guide["body"].lower()
    assert guide["body"].rstrip().endswith("</div>")
    data2 = fa._apply_fivebythree_overrides("fivebythree", data)
    guide2 = next(e for e in data2["emails"] if e["name"].startswith("Step 3"))
    assert guide2["body"].lower().count("interview guide") == 1
    # schedule pinned across all five steps
    delays = {fa._fivebyfive_step_no(e["name"]): e["delay_days"] for e in data["emails"]}
    assert delays == {1: 0, 2: 3, 3: 3, 4: 2, 5: 3}


def test_fivebythree_chooser_tile_present():
    import flowdrip_app as fa
    keys = [o.get("key") for o in fa.CHOOSER_OPTIONS]
    assert "fivebythree" in keys
    tile = next(o for o in fa.CHOOSER_OPTIONS if o.get("key") == "fivebythree")
    assert tile["title"] == "Arena 5×3"


def test_fivebythree_pdf_subject_recruiting():
    import flowdrip_app as fa
    camp = {"name": "Arena 5x3 - Acme", "_chooser_origin": "fivebythree",
            "variables": {"TargetRole": "Project Engineer", "CompanyName": "Acme"}}
    company, roles, location, industry = fa._pdf_campaign_subject(camp)
    assert company == "Acme"
    assert roles == "Project Engineer"


def _sample_resume_dict():
    return {
        "code": "Candidate A", "role": "Project Engineer", "representative": False,
        "summary": "Project engineer with about 6 years across civil and water construction.",
        "expertise": ["Water and Wastewater Construction", "RFIs and Submittals"],
        "experience": [
            {"title": "Project Engineer", "employer": "Regional civil engineering firm",
             "dates": "Jan 2024 to Present",
             "bullets": ["Ran RFIs, submittals, and QC on a large public program",
                         "Managed inspectors and construction engineers"]},
        ],
        "skills": "AutoCAD, Revit, ArcGIS",
        "education": ["BS Environmental Science", "Engineer in Training"],
    }


def test_polished_pdf_writes_file_with_content(with_user):
    import flowdrip_app as fa
    fname = fa._build_polished_resume_pdf(_sample_resume_dict())
    assert fname == "Resume_Candidate_A_Redacted.pdf"
    fpath = fa._user_pdf_dir() / fname
    assert fpath.exists() and fpath.stat().st_size > 1500
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    txt = "\n".join((p.extract_text() or "") for p in PdfReader(str(fpath)).pages)
    assert "Candidate A" in txt
    assert "Project Engineer" in txt
    assert "Regional civil engineering firm" in txt
    assert "PROFESSIONAL EXPERIENCE" in txt.upper()
    assert "—" not in txt and "–" not in txt   # no em/en dashes
    assert fa._is_redacted_resume_pdf(fname)    # still recognized by the dropdown


def test_polished_pdf_strips_em_en_dashes(with_user):
    import flowdrip_app as fa
    d = _sample_resume_dict()
    d["summary"] = "Project engineer supporting K–12 schools and public agencies."
    d["experience"][0]["bullets"] = ["Led site work 2019–2024 across multiple campuses"]
    fname = fa._build_polished_resume_pdf(d)
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    txt = "\n".join((p.extract_text() or "")
                    for p in PdfReader(str(fa._user_pdf_dir() / fname)).pages)
    assert "—" not in txt and "–" not in txt
    assert "K-12" in txt


def test_polished_pdf_representative_note(with_user):
    import flowdrip_app as fa
    d = _sample_resume_dict(); d["representative"] = True
    fname = fa._build_polished_resume_pdf(d)
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    txt = "\n".join((p.extract_text() or "") for p in PdfReader(str(fa._user_pdf_dir()/fname)).pages)
    assert "representative" in txt.lower()


def test_redact_resume_pii_strips_contact_and_location():
    import flowdrip_app as fa
    dirty = ("John Doe 4707 Dunkirk Avenue, Oakland, CA 94605 "
             "(562) 619-6292 cadavid.jm@gmail.com Senior Estimator")
    clean = fa._redact_resume_pii(dirty)
    assert "@" not in clean
    assert "94605" not in clean
    assert "Dunkirk Avenue" not in clean
    assert "562" not in clean
    assert "Senior Estimator" in clean  # keeps the substance


class _StubMsg:
    def __init__(self, text): self.content = [type("B", (), {"text": text})()]


class _StubClient:
    """Mimics anthropic client: client.messages.create(...) -> _StubMsg."""
    def __init__(self, payload): self._payload = payload
    @property
    def messages(self):
        outer = self
        class _M:
            def create(self, **kw): return _StubMsg(outer._payload)
        return _M()


def test_representative_resume_from_card():
    import flowdrip_app as fa
    card = {"label": "Candidate C", "role": "Project Manager",
            "bullets": ["- OSHPD healthcare TIs", "• Procore, Bluebeam"]}
    r = fa._representative_resume_from_card(card)
    assert r["representative"] is True
    assert r["role"] == "Project Manager"
    assert r["experience"][0]["bullets"] == ["OSHPD healthcare TIs", "Procore, Bluebeam"]


def test_ai_structure_resume_scrubs_and_structures():
    import flowdrip_app as fa
    payload = ('{"role":"Project Engineer","summary":"Call me at (562) 619-6292.",'
               '"expertise":["QC"],"experience":[{"title":"PE",'
               '"employer":"Regional civil firm","dates":"2024 to Present",'
               '"bullets":["Ran RFIs at 4707 Dunkirk Avenue"]}],'
               '"skills":"AutoCAD","education":["BS"]}')
    client = _StubClient(payload)
    cand = {"resume_text": "real resume here", "target_role": "Project Engineer"}
    r = fa._ai_structure_resume(client, cand)
    assert r["representative"] is False
    assert r["role"] == "Project Engineer"
    assert "562" not in r["summary"]                       # PII scrubbed
    assert "Dunkirk Avenue" not in r["experience"][0]["bullets"][0]
    assert r["experience"][0]["employer"] == "Regional civil firm"


def test_ai_structure_resume_none_without_text():
    import flowdrip_app as fa
    assert fa._ai_structure_resume(_StubClient("{}"), {"resume_text": ""}) is None


def _emails_n(n):
    return [{"name": f"Step {i+1}", "attachments": []} for i in range(n)]


def test_attach_5x3_all_resumes_on_both_slate_emails():
    import flowdrip_app as fa
    emails = _emails_n(5)
    pdfs = ["Resume_A_Redacted.pdf", "Resume_B_Redacted.pdf", "Resume_C_Redacted.pdf"]
    fa._attach_resumes_to_emails("fivebythree", emails, pdfs)
    assert emails[1]["attachments"] == pdfs   # email 2: all 3
    assert emails[3]["attachments"] == pdfs   # email 4: all 3
    assert emails[0]["attachments"] == []
    assert emails[2]["attachments"] == []


def test_attach_legacy_positional_pairing_unchanged():
    import flowdrip_app as fa
    emails = _emails_n(5)
    pdfs = ["Resume_A_Redacted.pdf", "Resume_B_Redacted.pdf"]
    fa._attach_resumes_to_emails("fourbyfour", emails, pdfs)
    assert emails[1]["attachments"] == ["Resume_A_Redacted.pdf"]   # one per email
    assert emails[3]["attachments"] == ["Resume_B_Redacted.pdf"]


def test_attach_noop_when_no_pdfs():
    import flowdrip_app as fa
    emails = _emails_n(5)
    fa._attach_resumes_to_emails("fivebythree", emails, [])
    assert all(e["attachments"] == [] for e in emails)


def test_build_resumes_from_cards_5x3_representative(with_user):
    import flowdrip_app as fa
    cards = [{"label": "Candidate A", "role": "Project Manager",
              "bullets": ["OSHPD healthcare TIs", "Procore, Bluebeam"]}]
    saved = fa._build_redacted_resumes_from_cards(cards, "fivebythree", client=None)
    assert saved == ["Resume_Candidate_A_Redacted.pdf"]
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    txt = "\n".join((p.extract_text() or "")
                    for p in PdfReader(str(fa._user_pdf_dir()/saved[0])).pages)
    assert "representative" in txt.lower()          # no _pool_id -> representative


def test_build_resumes_from_cards_legacy_thin(with_user):
    import flowdrip_app as fa
    cards = [{"label": "Candidate A", "role": "Estimator", "bullets": ["Bridges"]}]
    saved = fa._build_redacted_resumes_from_cards(cards, "fourbyfour", client=None)
    assert saved == ["Resume_Candidate_A_Redacted.pdf"]   # legacy path still works


def test_aicb_build_redacted_resumes_delegates(with_user):
    import flowdrip_app as fa
    class _S:
        aicb_cand_cards = [{"label": "Candidate A", "role": "PM", "bullets": ["x"]}]
        aicb_camp_type = "fivebythree"
    saved = fa._aicb_build_redacted_resumes(_S(), client=None)
    assert saved == ["Resume_Candidate_A_Redacted.pdf"]

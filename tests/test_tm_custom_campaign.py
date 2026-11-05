"""Build a Custom Campaign (Mike 2026-11-05): DripDrop's "Create my own
campaign" walkthrough, rebuilt for what ThriveModal sells.

The user writes their own steps one at a time. Any email after the first can
carry ThriveModal's candidate profiles and one of its eight Sales PDFs, both
written by the app when the campaign is saved. A saved campaign is reused
for other companies, asking only for what was specific to the last one."""
import inspect
import types

import pytest

import tm_custom_campaign as cc


def _steps():
    return [
        {"type": "email", "delay_days": 0,
         "subject": "More room for the work that matters",
         "input": "Hi {FirstName},\n\nWe do offshore staff augmentation for "
                  "freight brokers in Texas.\n\nWorth a quick chat?"},
        {"type": "email", "delay_days": 3, "subject": "",
         "input": "Hi {FirstName},\n\nTouching base again.\n\nWant the numbers?",
         "pdf": "tm_cost_compare", "profiles": True},
        {"type": "call", "delay_days": 2, "input": "Ask where {Company} is stretched."},
        {"type": "email", "delay_days": 4, "subject": "Leaving this with you",
         "input": "Hi {FirstName},\n\nLast note for now.\n\nOpen to one role?",
         "pdf": "tm_cost_compare"},
    ]


# ── The logic ─────────────────────────────────────────────────────────────

def test_pdf_kinds_are_thrivemodals_campaign_pdfs():
    import flowdrip_app as fa
    assert cc.PDF_KINDS == {k: label for k, label, _line in fa._TM_CAMPAIGN_PDF_KINDS}
    assert list(cc.PDF_KINDS) == [k for k, _l, _x in fa._TM_CAMPAIGN_PDF_KINDS]
    # Nothing from DripDrop's recruiting set.
    for gone in ("interview_guide", "salary_guide", "scorecard", "why_staffing"):
        assert gone not in cc.PDF_KINDS


def test_profiles_count_follows_the_campaign_range():
    import flowdrip_app as fa
    assert cc.PROFILES_MIN == fa.TM_CAMPAIGN_PROFILES_MIN
    assert cc.PROFILES_MAX == fa.TM_CAMPAIGN_PROFILES_MAX
    assert [cc.clamp_profiles(v) for v in (None, "x", 1, 4, 9)] == [3, 3, 3, 4, 5]


def test_pdf_and_profiles_never_ride_the_first_email():
    steps = _steps()
    steps[0]["pdf"], steps[0]["profiles"] = "tm_myths", True
    assert cc.pdf_plan(steps) == [(1, "tm_cost_compare")]   # each PDF once
    assert cc.profile_plan(steps) == [1]
    # A call never carries either, and an unknown kind is dropped.
    steps[2].update(pdf="tm_myths", profiles=True)
    steps[3]["pdf"] = "salary_guide"
    assert cc.pdf_plan(steps) == [(1, "tm_cost_compare")]
    assert cc.profile_plan(steps) == [1]


def test_step_names_and_first_email():
    steps = _steps()
    assert cc.step_names(steps) == ["Email 1", "Email 2", "Call 1", "Email 3"]
    assert cc.is_first_email(steps, 0) and not cc.is_first_email(steps, 1)
    assert cc.is_first_email([{"type": "call"}, {"type": "email"}], 1)


def test_a_pdf_or_profiles_asks_for_role_place_and_industry():
    steps = _steps()
    assert cc.step_fillins(steps, 0) == []
    assert cc.step_fillins(steps, 1) == ["Role", "Location", "Industry"]
    assert cc.fillins(steps) == ["Role", "Location", "Industry"]
    steps[1]["pdf"] = ""                       # profiles alone: no place
    assert cc.step_fillins(steps, 1) == ["Role", "Industry"]
    # The later email that asked for the same PDF now carries it.
    assert cc.pdf_plan(steps) == [(3, "tm_cost_compare")]
    steps[3]["pdf"] = ""
    steps[0]["input"] += " {Industry} {Competitors}"
    assert cc.fillins(steps) == ["Industry", "Competitors", "Role"]
    assert cc.missing_fillins(steps, {"Industry": "freight"}) == [
        "Competitors", "Role"]


def test_step_problem_says_what_is_missing():
    steps = _steps()
    assert cc.step_problem(steps, 0) is None
    assert cc.step_problem(steps, 1) == ("fillin", "Role")
    vals = {"Role": "dispatcher", "Location": "USA", "Industry": "freight"}
    assert cc.step_problem(steps, 1, vals) is None
    steps[0]["subject"] = ""
    assert cc.step_problem(steps, 0) == "subject"
    steps[2]["input"] = "  "
    assert cc.step_problem(steps, 2) == "body"
    assert cc.missing_content(steps) == [1, 3]


def test_build_emails_keeps_the_users_words():
    out = cc.build_emails(_steps())
    assert [e["name"] for e in out] == ["Email 1", "Email 2", "Call 1", "Email 3"]
    assert [e["step_type"] for e in out] == [
        "email_auto", "email_auto", "call", "email_auto"]
    assert [e["delay_days"] for e in out] == [0, 3, 2, 4]
    assert out[0]["body"] == (
        "Hi {FirstName},<br><br>We do offshore staff augmentation for "
        "freight brokers in Texas.<br><br>Worth a quick chat?")
    # A follow-up with no subject replies to the first email.
    assert out[1]["subject"] == "Re: More room for the work that matters"
    assert out[3]["subject"] == "Leaving this with you"
    assert out[2]["subject"] == "" and out[2]["channel"] == "call"
    assert all(e["attachments"] == [] for e in out)
    # Typed angle brackets never become markup.
    assert cc.text_to_html("a <b> & c\r\n\r\n\r\nd") == "a &lt;b&gt; &amp; c<br><br>d"


def test_style_steps_keep_only_what_a_launch_needs():
    steps = _steps()
    steps[1].update(_drafting=True, ai_prompt="x", id="abc")
    rows = cc.style_steps(steps)
    assert rows[1] == {"type": "email", "delay_days": 3, "subject": "",
                       "input": steps[1]["input"], "voice": "mine",
                       "pdf": "tm_cost_compare", "profiles": True}
    assert "pdf" not in rows[3] and "profiles" not in rows[0]


def test_detected_details_become_fillins_and_fill_back():
    steps = _steps()
    raw = ('[{"text": "freight brokers", "name": "Industry"},'
           ' {"text": "Texas", "name": "Location"},'
           ' {"text": "not in the text", "name": "Role"},'
           ' {"text": "{FirstName}", "name": "FirstName"}]')
    found = cc.parse_detected(raw, steps)
    assert found == [{"text": "freight brokers", "name": "Industry"},
                     {"text": "Texas", "name": "Location"}]
    saved = cc.apply_detected(steps, found)
    assert "for {Industry} in {Location}." in saved[0]["input"]
    again = cc.fill(saved, {"Industry": "HVAC companies", "Location": "Ohio"})
    assert "for HVAC companies in Ohio." in again[0]["input"]
    assert "{FirstName}" in again[0]["input"]
    hints = cc.style_fillins(saved, {"Industry": "freight brokers"})
    assert hints[0] == {"name": "Industry", "label": "Industry",
                        "last": "freight brokers"}


def test_ai_is_told_what_thrivemodal_sells_not_recruiting():
    steps = _steps()
    vals = {"Role": "dispatcher", "Industry": "freight"}
    p = cc.draft_prompt(steps, 1, "", "direct", vals)
    assert "offshore staff augmentation" in p and "Philippines" in p
    assert "never 'offshore staffing'" in p
    assert "recruiter" not in p.lower()
    # No invented numbers or track record.
    assert "Do not invent facts" in p and "number of placements" in p
    # The PDF and the profiles on this step are explained to the writer.
    assert '"Staffing Cost Comparison" is attached' in p
    assert "candidate profiles from our pipeline for the dispatcher role" in p
    assert "Do not describe any candidate yourself" in p
    assert "[Email 1]" in p and "[Email 2]" not in p       # the other steps
    assert "No subject line." in p
    first = cc.draft_prompt(steps, 0, "intro", with_subject=True)
    assert "Subject: ..." in first and "attached" not in first
    assert "salesperson" in cc.polish_prompt("x", "email")
    assert "salesperson" in cc.detect_prompt(steps)
    for text in list(cc.AI_HINTS.values()) + list(cc.REFERENCE_EXAMPLES.values()):
        low = text.lower()
        assert "recruit for" not in low and "offshore staffing" not in low
        assert "100+" not in text and "%" not in text and "$" not in text
    assert cc.slot_of(steps, 0) == "intro_email"
    assert cc.slot_of(steps, 2) == "call_script"
    assert cc.slot_of(steps, 3) == "followup_email_2"


def test_split_subject():
    assert cc.split_subject("Subject: Hello there\n\nHi {FirstName},") == (
        "Hello there", "Hi {FirstName},")
    assert cc.split_subject("Hi {FirstName},") == ("", "Hi {FirstName},")


# ── Saving, reusing and building ──────────────────────────────────────────

@pytest.fixture
def pg(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    import tm_custom_campaign_page as page
    monkeypatch.setattr(page, "_ff", lambda: fa)
    return page


def test_saved_campaigns_live_in_their_own_file(pg):
    import flowdrip_app as fa
    vals = {"Role": "dispatcher", "Location": "USA", "Industry": "freight"}
    sid = pg.save_style("Dispatcher intro", _steps(), "direct", values=vals,
                        profiles_n=4)
    rows = pg.load_saved()
    assert [r["name"] for r in rows] == ["Dispatcher intro"]
    assert rows[0]["id"] == sid and rows[0]["profiles_n"] == 4
    assert {f["name"]: f["last"] for f in rows[0]["fillins"]} == vals
    assert pg._saved_path().name == "tm_custom_campaigns.json"
    # My Campaign Styles (and so the style pickers) never see it.
    assert fa._load_my_campaign_styles() == []
    # Same name replaces, keeps its id, and keeps last time's hints.
    assert pg.save_style("Dispatcher intro", _steps()[:2], "direct") == sid
    rows = pg.load_saved()
    assert len(rows) == 1 and len(rows[0]["steps"]) == 2
    assert {f["name"]: f["last"] for f in rows[0]["fillins"]} == vals
    pg.remember_values(sid, {"Industry": "HVAC"})
    assert {f["name"]: f["last"] for f in pg.load_saved()[0]["fillins"]}[
        "Industry"] == "HVAC"
    pg.delete_saved(sid)
    assert pg.load_saved() == []


def _stub_build(monkeypatch, fa, built=None):
    saved, calls = [], {}
    profiles = [{"title": "Dispatcher", "years": 5 + i, "rate": "$9/hr",
                 "bullets": ["Runs load boards", "Books carriers"]}
                for i in range(5)]

    def _pdfs(kinds, company, role, location, industry="", client=None,
              dest_dir=None):
        calls["pdfs"] = (list(kinds), company, role, location, industry)
        return dict(built if built is not None
                    else {k: f"{k}.pdf" for k in kinds})

    def _profiles(client, n, roles, niche, company="", brief=""):
        calls["profiles"] = (n, roles, niche)
        return profiles[:n]
    monkeypatch.setattr(fa, "_tm_build_campaign_pdfs", _pdfs)
    monkeypatch.setattr(fa, "_tm_generate_campaign_profiles", _profiles)
    monkeypatch.setattr(fa, "save_campaign", lambda camp: saved.append(camp))
    monkeypatch.setattr(fa, "load_campaigns", lambda: [{"name": "Dispatcher intro"}])
    return saved, calls


def test_build_adds_the_pdf_and_the_profiles_to_their_email(pg, monkeypatch):
    import flowdrip_app as fa
    saved, calls = _stub_build(monkeypatch, fa)
    vals = {"Role": "dispatcher", "Location": "USA", "Industry": "freight"}
    camp, missed = pg.build_campaign(
        "tester@example.com", "Dispatcher intro", cc.fill(_steps(), vals),
        "style-1", vals, profiles_n=4, client=object())
    assert missed == [] and saved == [camp]
    # A second run never lands on the first one's file.
    assert camp["name"] == "Dispatcher intro 2"
    assert camp["status"] == "draft" and camp["contacts"] == []
    assert camp["template_key"] == "tm_custom_campaign"
    assert camp["tm_custom_style_id"] == "style-1"
    assert camp["variables"] == vals
    emails = camp["emails"]
    assert calls["pdfs"] == (["tm_cost_compare"], "", "dispatcher", "USA", "freight")
    assert calls["profiles"] == (4, "dispatcher", "freight")
    assert emails[1]["attachments"] == ["tm_cost_compare.pdf"]
    assert emails[0]["attachments"] == [] and emails[3]["attachments"] == []
    body = emails[1]["body"]
    assert fa._TM_PROFILES_LEAD in body
    assert "<b>Candidate A: Dispatcher</b>" in body and "Candidate D" in body
    assert "Candidate E" not in body
    # Set in before the closing line, around the user's own words.
    assert body.index("Touching base again.") < body.index("Candidate A")
    assert body.index("Candidate D") < body.index("Want the numbers?")
    # The other emails go out exactly as written.
    assert "Candidate A" not in emails[0]["body"] + emails[3]["body"]
    assert emails[0]["body"].startswith("Hi {FirstName},<br><br>We do offshore")


def test_a_pdf_that_cannot_be_built_never_blocks_the_campaign(pg, monkeypatch):
    import flowdrip_app as fa
    vals = {"Role": "dispatcher", "Location": "USA", "Industry": "freight"}
    saved, _calls = _stub_build(monkeypatch, fa, built={})
    camp, missed = pg.build_campaign("t@example.com", "X", _steps(), "", vals,
                                     client=object())
    assert saved and camp["emails"][1]["attachments"] == []
    assert missed == ["Email 2: the Staffing Cost Comparison PDF"]
    # No pay data: the builder's stand-in is attached, and the user is told.
    saved, _calls = _stub_build(monkeypatch, fa,
                                built={"tm_how_it_works": "How.pdf"})
    camp, missed = pg.build_campaign("t@example.com", "X", _steps(), "", vals,
                                     client=object())
    assert camp["emails"][1]["attachments"] == ["How.pdf"]
    assert "How We Work Together is attached in place" in missed[0]


def test_no_ai_key_still_builds_the_users_own_steps(pg, monkeypatch):
    import flowdrip_app as fa
    saved, calls = _stub_build(monkeypatch, fa)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(fa, "_tm_generate_campaign_profiles",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no key")))
    camp, missed = pg.build_campaign("t@example.com", "Y", _steps(), "", {})
    assert saved == [camp] and "pdfs" not in calls
    assert missed == ["Email 2: the Staffing Cost Comparison PDF",
                      "the candidate profiles"]
    assert len(camp["emails"]) == 4


# ── Wiring ────────────────────────────────────────────────────────────────

def test_state_is_one_dict_cleared_with_the_other_wizards(pg):
    import flowdrip_app as fa
    s = fa.AppState()
    assert s.tmc_state == {}
    w = pg._w(s)
    assert w["step"] == 1 and w["steps"] == [] and w["profiles_n"] == 3
    w["steps"].append(pg._new_step("email", 0))
    w["vals"]["Role"] = "dispatcher"
    fa._reset_wizard_state(s)
    assert s.tmc_state == {} and pg._w(s)["steps"] == []
    # Defaults are never shared between two sessions.
    assert pg._w(fa.AppState())["vals"] == {}


def test_open_page_lands_on_a_fresh_walkthrough(pg, monkeypatch):
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "_nav_snapshot", lambda s: {})
    s = fa.AppState()
    s._nav_history = []
    pg._w(s)["steps"].append(pg._new_step("email", 0))
    s.loaded_camp = {"name": "old"}
    done = []
    pg.open_page(s, lambda: done.append(1))
    assert s.sp == "tm_custom_campaign" and s.hub == "sales"
    assert s.loaded_camp is None and pg._w(s)["steps"] == [] and done == [1]


def test_only_an_email_after_the_first_keeps_its_extras(pg):
    import flowdrip_app as fa
    s = fa.AppState()
    w = pg._w(s)
    a, b = pg._new_step("email", 0), pg._new_step("email", 3)
    b.update(pdf="tm_myths", profiles=True)
    w["steps"] = [b, a]          # moved to the front: now the first email
    pg._fix_delays(w)
    assert b["pdf"] == "" and b["profiles"] is False
    assert a["delay_days"] == 3  # only the first step is Day 0


def test_page_is_routed_titled_and_draws_its_own_back():
    import flowdrip_app as fa
    src = inspect.getsource(fa.render_page)
    assert 'elif page == "tm_custom_campaign" and _is_thrivemodal():' in src
    assert "_tmc.render_page(s, rf)" in src
    assert 'if page in ("seq_builder", "tm_custom_campaign"):' in src
    assert fa.SIDEBAR_TITLES["tm_custom_campaign"] == "Build a Custom Campaign"
    # Not a sidebar row of its own: it lights Campaigns > Build a Campaign.
    st = types.SimpleNamespace(hub="sales", sp="tm_custom_campaign", ep="", _tab="")
    assert fa._sidebar_active(st) == "new"


def test_both_ways_in_open_the_walkthrough_behind_the_setup_gate(monkeypatch):
    import flowdrip_app as fa
    import tm_custom_campaign_page as page
    assert page.TITLE == fa.START_CAMPAIGN_OPTIONS[1]["title"]
    dlg = inspect.getsource(fa._start_campaign_dialog)
    assert "_open_custom_campaign(s, rf, setup)" in dlg
    chooser = inspect.getsource(fa._tm_render_chooser_page)
    assert "_open_custom_campaign(s, rf)" in chooser
    assert 's.sp = "seq_builder"' not in chooser
    card = next(o for o in fa.TM_CHOOSER_OPTIONS if o["key"] == "scratch")
    assert card["title"] == page.TITLE and "candidate profiles" in card["desc"]
    # The shared (Arena) chooser's tile is untouched.
    assert next(o for o in fa.CHOOSER_OPTIONS
                if o["key"] == "scratch")["title"] != page.TITLE

    opened, gated = [], []
    monkeypatch.setattr(page, "open_page", lambda s, rf: opened.append(s))
    monkeypatch.setattr(fa, "_show_setup_gate_dialog",
                        lambda s, rf, setup: gated.append(setup))
    monkeypatch.setattr(fa, "_SERVER_MODE", True)
    s = types.SimpleNamespace(_setup_gate_dismissed=False)
    fa._open_custom_campaign(s, lambda: None, {"ready": False})
    assert gated == [{"ready": False}] and opened == []
    fa._open_custom_campaign(s, lambda: None, {"ready": True})
    assert opened == [s]


def test_page_copy_is_inboxslides_and_never_appends_alpha_to_a_var():
    import tm_custom_campaign_page as page
    src = inspect.getsource(page)
    assert "DripDrop sends" not in src and "Today's Tasks" not in src
    assert "Pipeline" not in src.replace("pipeline for the", "")
    # C values are var(--dd-...): a hex alpha goes through _tint().
    import re
    assert not re.search(r"\{C\['[a-z_]+'\]\}[0-9A-Fa-f]{2}[;\"]", src)
    for name in ("Role", "Location", "Industry"):
        assert name in page._FILLIN_ASKS and name in page._FILLIN_HINTS

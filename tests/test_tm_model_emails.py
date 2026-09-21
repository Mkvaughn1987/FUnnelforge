"""Mike's seven model emails are the ThriveModal house style, and Standard
Outreach is seven emails (2026-09-21)."""
import re

import flowdrip_app as fa

REG = {t[0]: t for t in fa.AICB_CAMPAIGN_TYPES}
MODELS = [name for name, _s, _p in fa._TM_MODEL_EMAILS]
TAG_RE = re.compile(r"\(model: ([^)]+)\)")


def _steps(key):
    return REG[key][6].split("\n")


def test_the_seven_models_and_their_subjects():
    assert [(n, s) for n, s, _p in fa._TM_MODEL_EMAILS] == [
        ("Capacity", "More room for the work that matters"),
        ("Economics", "What would the role actually cost?"),
        ("Role scope", "A clearer scope for the role"),
        ("After the person joins", "After the person joins"),
        ("Quality and control", "What you would assess before hiring"),
        ("Commitment", "Start with the role requirements"),
        ("Close", "Leaving this with you"),
    ]


def test_models_carry_the_kept_lines_and_nothing_dropped():
    text = {n: " ".join(p) for n, _s, p in fa._TM_MODEL_EMAILS}
    assert "We do offshore staff augmentation" in text["Capacity"]
    assert "up to 60 to 70 percent" in text["Economics"]
    assert "once a month" in text["Close"]
    for n, t in text.items():
        assert "plug-and-play" not in t, n
        assert "offshore staffing" not in t.lower(), n
        if n != "Economics":
            assert "percent" not in t, n
        assert "$" not in t, n


def test_rule_embeds_every_model():
    r = fa._TM_EMAIL_OPENER_RULE
    for i, (name, subject, paras) in enumerate(fa._TM_MODEL_EMAILS, 1):
        assert f"Model {i} - {name}\nSubject: {subject}\n" in r
        assert "<br><br>".join(paras) in r


def test_every_tag_names_a_real_model():
    for key in fa._TM_TYPE_KEYS:
        for tag in TAG_RE.findall(REG[key][6]):
            assert tag in MODELS, (key, tag)


def test_standard_outreach_is_the_seven_models_in_order():
    t = REG["tm_fivebyseven"]
    assert t[2] == "10 steps - 4 weeks"
    tags = [TAG_RE.search(s).group(1) for s in _steps("tm_fivebyseven")
            if "step_type:email_auto" in s]
    assert tags == MODELS


def test_priority_account_push_uses_all_seven_too():
    tags = [TAG_RE.search(s).group(1) for s in _steps("tm_conversation")
            if "step_type:email_auto" in s]
    assert tags == MODELS


def test_the_last_email_of_each_cold_sequence_is_the_close_model():
    for key in ("tm_fivebyseven", "tm_conversation", "tm_threebythree",
                "tm_hiring_signal", "tm_twelveweek", "tm_stay_in_touch",
                "tm_reengage"):
        last = [s for s in _steps(key) if "step_type:email_auto" in s][-1]
        assert "(model: Close)" in last, key


def test_step_lines_agree_with_the_pinned_shape():
    st = {"email_auto": fa.ST.EMAIL_AUTO, "call": fa.ST.CALL,
          "linkedin": fa.ST.LINKEDIN}
    for key in fa._TM_OFFERED_TYPE_KEYS:
        shape = fa._TM_STEP_SHAPE[key]
        steps = _steps(key)
        assert len(steps) == len(shape), key
        for line in steps:
            m = re.match(r"Step (\d+) - .*?\(delay_days:(\d+), step_type:(\w+)\)",
                         line)
            n, d, typ = int(m.group(1)), int(m.group(2)), m.group(3)
            assert shape[n] == (d, st[typ]), (key, n)


def test_standard_outreach_pdfs_land_on_cost_and_scope():
    emails = []
    for line in _steps("tm_fivebyseven"):
        name = line.split(" (")[0]
        typ = re.search(r"step_type:(\w+)", line).group(1)
        emails.append({"name": name, "subject": "", "step_type": typ})
    placed = fa._tm_pdf_placement("tm_fivebyseven", emails,
                                  ["tm_role_blueprint", "tm_cost_compare"])
    assert emails[placed["tm_cost_compare"]]["name"] == "Step 2 - Economics"
    assert emails[placed["tm_role_blueprint"]]["name"] == "Step 5 - Role scope"


def test_tagged_steps_get_the_model_subject_word_for_word():
    c = {"emails": [
        {"name": "Step 1 - Capacity", "subject": "track and trace after hours",
         "body": "Hi {FirstName},<br><br>x", "step_type": "email_auto"},
        {"name": "Step 3 - Follow-up Call", "subject": "", "body": "script",
         "step_type": "call"},
        {"name": "Step 5 - Role scope", "subject": "What your specialist would own",
         "body": "Hi {FirstName},<br><br>y", "step_type": "email_auto"},
    ]}
    fa._apply_thrivemodal_overrides("tm_fivebyseven", c)
    assert [e["subject"] for e in c["emails"]] == [
        "More room for the work that matters", "",
        "A clearer scope for the role"]
    assert fa._tm_step_models("tm_twelveweek") == {
        7: "Role scope", 9: "Economics", 14: "Close"}
    arena = {"emails": [{"name": "Step 1 - Capacity", "subject": "keep me",
                         "body": "b", "step_type": "email_auto"}]}
    fa._apply_thrivemodal_overrides("fivebyfive", arena)
    assert arena["emails"][0]["subject"] == "keep me"


def test_tm_subjects_are_not_title_cased():
    src = open(fa.__file__, encoding="utf-8").read()
    i = src.index("ThriveModal subjects stay in the sentence case")
    assert "not in _TM_TYPE_KEYS" in src[i:i + 300]

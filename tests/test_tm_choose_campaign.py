"""inboxslide AI Prompt "Choose your campaign" step: every offered campaign
type has a card, and each card's timeline matches the app's own cadence
table (_TM_STEP_SHAPE) and model subjects (_TM_MODEL_EMAILS), so the card
can never describe a campaign that no longer exists."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_ai_prompts_catalogue import _stub_nicegui  # noqa: E402


@pytest.fixture(scope="module")
def mods():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_prompts
    import tm_prompts
    return ai_prompts, tm_prompts


@pytest.fixture(scope="module")
def fa():
    import flowdrip_app
    return flowdrip_app


_KIND = {"email_auto": "email", "email": "email", "call": "call",
         "linkedin": "linkedin"}


def _app_steps(fa, key):
    """[(business day, kind, model subject or None)] from the app's tables."""
    shape = fa._TM_STEP_SHAPE[key]
    models = fa._tm_step_models(key)
    subjects = {name: subj for name, subj, _p in fa._TM_MODEL_EMAILS}
    out, day = [], 1
    for n in sorted(shape):
        delay, st = shape[n]
        day += delay
        out.append((day, _KIND[str(st)], subjects.get(models.get(n))))
    return out


def test_step_is_called_choose_your_campaign(mods):
    aip, tm = mods
    aip._CAT = tm.TM
    try:
        assert dict(aip._aip_sections_for(
            tm.ROUTINE_BY_KEY["tm_signal_hunt"]))["emails"] == \
            "Choose your campaign"
        assert aip._section_copy("emails", "short", "x") == "your campaign"
        # DripDrop's catalogue keeps the engine's words.
        aip._CAT = aip.ARENA
        assert aip._section_copy("emails", "short", "x") == "x"
    finally:
        aip._CAT = aip.ARENA


def test_every_offered_campaign_type_has_a_card(mods):
    aip, tm = mods
    for r in tm.TM.routines:
        f = r["field_by_key"].get("sequence")
        if f:
            missing = [o for o in f["options"] if o not in tm.SEQUENCE_INFO]
            assert not missing, (r["key"], missing)
    # And nothing describes a type the page no longer offers.
    assert set(tm.SEQUENCE_INFO) == set(tm.SEQUENCES)


def test_arena_catalogue_on_this_branch_keeps_the_dropdown(mods):
    aip, _tm = mods
    assert aip.ARENA.sequence_info is None
    assert aip.ARENA.section_copy is None


def test_step_days_never_go_backwards(mods):
    _aip, tm = mods
    for name, info in tm.SEQUENCE_INFO.items():
        days = [st[0] for st in info.get("steps") or []]
        assert days == sorted(days), name
        if days:
            assert days[0] == 1, name


def test_cards_match_the_apps_cadence_and_subjects(mods, fa):
    """Day, kind and (for a model-tagged step) the exact subject, step by
    step, for every type with a template."""
    _aip, tm = mods
    for name, key in tm.TEMPLATE_KEY.items():
        card = [(st[0], st[1], st[2]) for st in tm.SEQUENCE_INFO[name]["steps"]]
        app = _app_steps(fa, key)
        assert len(card) == len(app), (name, len(card), len(app))
        for (cday, ckind, ctitle), (aday, akind, asubj) in zip(card, app):
            assert (cday, ckind) == (aday, akind), (name, ctitle)
            if asubj:
                assert ctitle == asubj, (name, ctitle, asubj)


def test_cards_match_the_apps_default_pdfs(mods, fa):
    """The attachment chips are the type's default PDFs, on the emails the
    app's keyword placement puts them on."""
    _aip, tm = mods
    labels = {k: lab for k, lab, _ in fa._TM_CAMPAIGN_PDF_KINDS}
    subjects = {name: subj for name, subj, _p in fa._TM_MODEL_EMAILS}
    for name, key in tm.TEMPLATE_KEY.items():
        steps = tm.SEQUENCE_INFO[name]["steps"]
        # The app's emails, named like the generator names them.
        seq = next(t[6] for t in fa.AICB_CAMPAIGN_TYPES if t[0] == key)
        names = dict(re.findall(r"Step (\d+) - ([^\n(]+?) \(delay_days",
                                seq))
        models = fa._tm_step_models(key)
        emails = []
        for n in sorted(fa._TM_STEP_SHAPE[key]):
            _d, st = fa._TM_STEP_SHAPE[key][n]
            emails.append({"name": "Step %d - %s" % (n, names[str(n)].strip()),
                           "subject": subjects.get(models.get(n), ""),
                           "step_type": str(st)})
        kinds = fa._tm_default_pdf_kinds(key, emails)
        placed = fa._tm_pdf_placement(key, emails, kinds)
        want = {ei: labels[k] for k, ei in placed.items()}
        got = {i: st[4] for i, st in enumerate(steps) if len(st) > 4 and st[4]}
        assert got == want, (name, got, want)


def test_counts_line(mods):
    aip, tm = mods
    info = tm.SEQUENCE_INFO
    assert aip.sequence_counts("Standard Outreach", info) == \
        "7 emails, 2 calls, 1 LinkedIn, about 4½ weeks"
    assert aip.sequence_counts("Quick Intro", info) == \
        "4 emails, about 2 weeks"
    assert aip.sequence_counts("Long Term Nurture", info) == \
        "12 emails, 4 calls, 1 LinkedIn, about 12 weeks"
    assert aip.sequence_counts("Let Claude choose", info) == ""


def test_profile_rounds_match_the_app(mods, fa):
    """A type that shows its candidate profiles more than once says so on
    exactly the emails the app puts them on, and nowhere else."""
    _aip, tm = mods
    by_key = {v: k for k, v in tm.TEMPLATE_KEY.items()}
    checked = 0
    for key, rounds in fa._TM_PROFILE_ROUNDS.items():
        steps = [st for st in tm.SEQUENCE_INFO[by_key[key]]["steps"]
                 if st[1] == "email"]
        want = set()
        for subj, num, _lead, cnt in rounds:
            if subj:
                assert steps[num - 1][2] == subj, (key, num)
            assert "profiles" in steps[num - 1][3], (key, num)
            if cnt:
                assert "Two of the profiles" in steps[num - 1][3]
            want.add(num - 1)
        got = {i for i, st in enumerate(steps) if "profiles" in st[3]}
        assert got == want, (key, got, want)
        checked += 1
    assert checked >= 3  # Standard Outreach, Quick Intro, Long Term Nurture


def test_connector_describes_the_step_by_its_new_name(mods):
    aip, tm = mods
    aip._CAT = tm.TM
    try:
        runs = aip.describe_runs(tm.TM)
    except TypeError:
        runs = aip.describe_runs()
    finally:
        aip._CAT = aip.ARENA
    sections = {q.get("section") for r in runs
                for q in r.get("questions", r.get("fields", []))}
    assert "Choose your campaign" in sections

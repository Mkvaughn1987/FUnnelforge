"""Arena 5×7: the Arena copy of inboxslide's Standard Outreach."""
import re

import flowdrip_app as fa
import ai_prompts


def _get(key):
    return next(t for t in fa.AICB_CAMPAIGN_TYPES if t[0] == key)


def _sample():
    kinds = {3: "call", 4: "linkedin", 8: "call"}
    return {"emails": [
        {"name": f"Step {n} - x", "subject": f"s{n}",
         "body": f'<div style="font-family:Arial">body {n}</div>',
         "delay_days": 9, "step_type": kinds.get(n, "email_auto")}
        for n in range(1, 11)]}


def test_registered_after_fivebythree():
    keys = [t[0] for t in fa.AICB_CAMPAIGN_TYPES]
    assert keys.index("fivebyseven") == keys.index("fivebythree") + 1
    assert _get("fivebyseven")[1] == "Arena 5×7"
    assert "fivebyseven" in fa._VALID_TEMPLATES


def test_prompt_has_ten_steps_seven_emails():
    prompt = _get("fivebyseven")[6]
    steps = re.findall(r"Step (\d+) - [^(]+\(delay_days:\d+, step_type:(\w+)\)",
                       prompt)
    assert [int(n) for n, _ in steps] == list(range(1, 11))
    assert sum(1 for _, k in steps if k == "email_auto") == 7
    assert [int(n) for n, k in steps if k == "call"] == [3, 8]
    assert [int(n) for n, k in steps if k == "linkedin"] == [4]


def test_candidates_on_emails_three_five_and_two_on_close():
    prompt = _get("fivebyseven")[6]
    assert "Only Steps 5, 7 and 10 mention candidates" in prompt
    assert "EVERY candidate from" in prompt
    assert "SAME candidates" in prompt
    assert "ONLY the first two candidates" in prompt
    assert fa._CAND_NAME_RULE in prompt
    # Same honest wording as Thrive: never claims a candidate was placed.
    assert "Good candidates get placed, so who is available changes." in prompt


def test_in_arena_and_pipeline_families():
    assert "fivebyseven" in fa._ARENA_SLATE_TYPES
    assert "fivebyseven" in fa._PIPELINE_SLATE_TYPES
    assert fa._camp_is_4x4({"aicb_camp_type": "fivebyseven"}) is True


def test_overrides_pin_delays_and_are_scoped():
    data = fa._apply_fivebyseven_overrides("fivebyseven", _sample())
    got = {fa._fivebyfive_step_no(e["name"]): e["delay_days"]
           for e in data["emails"]}
    assert got == fa._FIVEBYSEVEN_DELAYS
    other = fa._apply_fivebyseven_overrides("fivebythree", _sample())
    assert all(e["delay_days"] == 9 for e in other["emails"])


def test_resumes_on_email_five_only_with_line():
    emails = _sample()["emails"]
    fa._attach_resumes_to_emails("fivebyseven", emails, ["a.pdf", "b.pdf", "c.pdf"])
    fa._attach_resumes_to_emails("fivebyseven", emails, ["a.pdf", "b.pdf", "c.pdf"])
    by_step = {fa._fivebyfive_step_no(e["name"]): e for e in emails}
    for n in (7,):
        assert by_step[n]["attachments"] == ["a.pdf", "b.pdf", "c.pdf"]
        body = by_step[n]["body"]
        assert body.count(fa._FIVEBYSEVEN_RESUME_LINE) == 1
        assert body.endswith("</div>")
    for n in (1, 2, 3, 4, 5, 6, 8, 9, 10):
        assert not by_step[n].get("attachments")
        assert fa._FIVEBYSEVEN_RESUME_LINE not in by_step[n]["body"]


def test_no_resumes_means_no_line():
    emails = _sample()["emails"]
    fa._attach_resumes_to_emails("fivebyseven", emails, [])
    assert all(fa._FIVEBYSEVEN_RESUME_LINE not in e["body"] for e in emails)


def test_chooser_tile_and_routing():
    tile = next(o for o in fa.CHOOSER_OPTIONS if o.get("key") == "fivebyseven")
    assert tile["title"] == "Arena 5×7"
    import inspect
    src = inspect.getsource(fa)
    assert 'elif k == "fivebyseven":' in src
    assert 's.aicb_camp_type = "fivebyseven"' in src


def test_ai_prompts_dropdown_offers_it():
    assert ai_prompts.SEQUENCES[0] == "Arena 5x7"
    assert ai_prompts.TEMPLATE_KEY["Arena 5x7"] == "fivebyseven"
    # The default run stays the 5x5.
    assert ai_prompts.TEMPLATE_KEY["Arena 5x5"] == "fivebyfive"


def test_email_three_is_write_ups_and_email_two_has_no_numbers():
    prompt = _get("fivebyseven")[6]
    step5 = prompt.split("Step 5 -")[1].split("Step 6 -")[0]
    assert "Write-ups only" in step5
    step2 = prompt.split("Step 2 -")[1].split("Step 3 -")[0]
    assert "NO numbers of any kind" in step2
    assert "Warm" in step2

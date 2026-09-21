"""inboxslide newsletters take an optional user topic ("what do you want this
newsletter to be about?", Mike 2026-09-21). Blank keeps the stock monthly
article; a topic replaces it in both newsletter styles."""
import inspect

import flowdrip_app as fa


def _plan(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    return fa._tm_newsletter_plan("CPA firm", 2026, 10, 0)


def test_blank_topic_keeps_the_stock_article(monkeypatch):
    plan = _plan(monkeypatch)
    p = fa._tm_newsletter_prompt("x", "ThriveModal", "CPA Firms", "", "October 2026",
                                 plan, "", "", "PLAYBOOK", "")
    assert f"THIS ISSUE'S ARTICLE: \"{plan['angle']}\"" in p
    assert "wants this newsletter to be about" not in p


def test_topic_replaces_the_article_and_keeps_the_rules(monkeypatch):
    plan = _plan(monkeypatch)
    topic = "AI, and why Filipino professionals are a smart hire"
    p = fa._tm_newsletter_prompt("x", "ThriveModal", "CPA Firms", "", "October 2026",
                                 plan, "", "", "PLAYBOOK", "", topic=topic)
    assert f'about: "{topic}"' in p
    assert f"THIS ISSUE'S ARTICLE: \"{plan['angle']}\":" not in p
    assert "HARD RULES" in p and "up to 60-70%" in p and "PLAYBOOK" in p


def test_organic_style_takes_the_topic():
    off = fa._jway_sales_prompt("Accounting", "CPA Firms", "Nationwide", "October 2026",
                                "Mike", "ThriveModal")
    on = fa._jway_sales_prompt("Accounting", "CPA Firms", "Nationwide", "October 2026",
                               "Mike", "ThriveModal", topic="AI in the back office")
    assert "wants this newsletter to be about" not in off
    assert '"AI in the back office"' in on


def test_campaign_dict_stores_the_topic():
    from datetime import date
    c = fa._nl_campaign_dict("N", "k", "Label", "", "Nationwide", date(2026, 10, 1),
                             count=1, topic="  AI  ")
    assert c["newsletter_topic"] == "AI"
    assert fa._nl_campaign_dict("N", "k", "Label", "", "r", date(2026, 10, 1),
                                count=1)["newsletter_topic"] == ""


def test_generator_and_dialogs_wire_the_topic():
    gen = inspect.getsource(fa._generate_newsletter_content_for_step)
    assert 'camp.get("newsletter_topic")' in gen and "topic=_nl_topic" in gen
    assert "_nl_topic_field(" in inspect.getsource(fa._create_newsletter_dialog)
    settings = inspect.getsource(fa._edit_newsletter_settings_dialog)
    assert "_nl_topic_field(" in settings and 'camp["newsletter_topic"]' in settings

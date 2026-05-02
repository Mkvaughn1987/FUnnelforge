"""When a newsletter is created, the background generator should fill in
ALL N scheduled steps, not just step 0."""


def test_gen_all_issues_calls_generator_per_step(
        isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    camp = {
        "name": "Big Test NL",
        "newsletter_name": "Big Test NL",
        "market_analysis": True,
        "evergreen_only": True,
        "market_sector": "construction",
        "market_region": "Denver, CO",
        "_owner_email": "tester@example.com",
        "emails": [
            {"name": f"Issue {i}", "subject": "", "body": "",
             "step_type": "email_auto"}
            for i in range(3)
        ],
    }
    fa.save_campaign(camp)

    calls = []
    def _spy(_camp, idx):
        calls.append(idx)
        return (f"S{idx}", f"B{idx}")
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step", _spy)
    # Skip the inter-issue sleep so the test runs fast.
    import time
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)

    fa._gen_all_issues_for_campaign("Big Test NL")

    assert calls == [0, 1, 2]
    saved = next(c for c in fa.load_campaigns() if c.get("name") == "Big Test NL")
    for i in range(3):
        assert saved["emails"][i]["subject"] == f"S{i}"
        assert saved["emails"][i]["body"] == f"B{i}"

"""Sales instances start every new newsletter Organic (text only) and never
say "J's Way" to the user; Arena keeps Full with pictures."""
from datetime import date

import flowdrip_app as fa


def test_default_style_follows_instance(monkeypatch):
    assert fa._NL_DEFAULT_STYLE == ("j_way" if fa._SALES_MODE else "full_send")
    monkeypatch.setattr(fa, "_NL_DEFAULT_STYLE", "j_way")
    camp = fa._nl_campaign_dict("N", "logistics", "Logistics", "", "USA",
                                date(2026, 11, 1), count=1)
    assert camp["newsletter_style"] == "j_way"
    full = fa._nl_campaign_dict("N", "logistics", "Logistics", "", "USA",
                                date(2026, 11, 1), count=1, style="full_send")
    assert full["newsletter_style"] == "full_send"


def test_handoff_option_says_organic_on_sales():
    import inspect
    src = inspect.getsource(fa._offer_newsletter_enroll)
    assert "New organic newsletter" in src

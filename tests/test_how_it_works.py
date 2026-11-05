"""How it Works: the page header button and its walkthrough dialog.

Mike, 2026-11-05: a How it Works button top right, with a diagram that walks
users through what a campaign does: emails, LinkedIn, calls, and the monthly
newsletter that keeps going once the campaign is over. The week chart is
Standard Outreach, so these tests hold it to the cadence the app really runs."""
import inspect
import re


def test_header_has_the_button_where_start_a_campaign_is():
    import flowdrip_app as fa
    src = inspect.getsource(fa._page_header_v2)
    assert "ui.label(HOW_IT_WORKS_TITLE)" in src
    assert "_how_it_works_dialog(s, rf, _setup)" in src
    assert fa.HOW_IT_WORKS_TITLE == "How it Works"
    # Same gate as the sidebar's Start a Campaign button, which the
    # walkthrough starts from; and it sits between search and theme toggle.
    i = src.index("fd-ph-how")
    assert '_tm_nav_page_key("ai_prompt", None)' in src[i - 300:i]
    assert src.index("fd-ph-search") < i < src.index("fd-theme-toggle")
    assert "help" in fa._SIDEBAR_ICONS


def test_week_chart_matches_standard_outreach():
    """Every dot on the chart is a step Standard Outreach really has."""
    import flowdrip_app as fa
    import tm_prompts as tp
    steps = tp.SEQUENCE_INFO[fa.HOW_IT_WORKS_EXAMPLE]["steps"]
    lanes = {cls: on for cls, _n, _w, _s, on in fa.HOW_IT_WORKS_LANES}
    by_kind = {"em": "email", "call": "call", "li": "linkedin"}
    for cls, kind in by_kind.items():
        assert lanes[cls] == [st[0] for st in steps if st[1] == kind], cls
    emails = [st for st in steps if st[1] == "email"]
    assert lanes["pdf"] == [st[0] for st in emails if len(st) > 4 and st[4]]
    assert lanes["prof"] == [st[0] for st in emails if "profiles" in st[3]]
    assert fa.HOW_IT_WORKS_DAYS == sorted({st[0] for st in steps})
    # The queueing layer runs the same days: delays are business days
    # after the step before.
    shape = fa._TM_STEP_SHAPE["tm_fivebyseven"]
    day, days = 1, []
    for n in sorted(shape):
        day += shape[n][0]
        days.append(day)
    assert days == [st[0] for st in steps]


def test_calls_and_linkedin_are_the_users_and_the_rest_is_automatic():
    import flowdrip_app as fa
    who = {cls: w for cls, _n, w, _s, _on in fa.HOW_IT_WORKS_LANES}
    assert who == {"em": "auto", "call": "you", "li": "you",
                   "pdf": "auto", "prof": "auto"}
    chart = fa._how_it_works_chart_html()
    assert chart.count("You do this") == 2 and chart.count("Automatic") == 3
    # One dot per day a lane lands on, nothing more.
    dots = sum(len(on) for _c, _n, _w, _s, on in fa.HOW_IT_WORKS_LANES)
    assert chart.count('class="fd-ph-how-dot ') == dots
    assert 'role="img"' in chart and "aria-label=" in chart


def test_walkthrough_covers_every_part_mike_asked_for():
    import flowdrip_app as fa
    html = fa._how_it_works_html()
    text = re.sub(r"<[^>]+>", " ", html)
    assert html.count('class="fd-ph-how-step"') == 5
    for word in ("Emails", "Calls", "LinkedIn", "PDFs", "My Day", "Replies",
                 "Do Not Contact", "newsletter", "one issue a month",
                 "keeps going after the campaign is over"):
        assert word in text, word
    # The two ways in carry whatever the Start a Campaign cards are called.
    assert fa.START_CAMPAIGN_TITLE in text
    for o in fa.START_CAMPAIGN_OPTIONS:
        assert o["title"] in text
    assert "7 emails, 2 calls and 1 LinkedIn note over about 4 weeks" in text
    # Plain copy: no dashes standing in for punctuation, no ChatGPT.
    assert "—" not in html and "–" not in html
    assert "ChatGPT" not in html


def test_what_the_dialog_promises_is_what_the_app_does():
    import flowdrip_app as fa
    # Inbox checked every 5 minutes.
    assert fa._REPLY_POLL_INTERVAL == 300
    assert "every 5 minutes" in fa._how_it_works_html()
    # A newsletter keeps emailing people who replied; campaigns do not.
    q = inspect.getsource(fa.queue_campaign_emails)
    assert "_responded_set = set() if _is_newsletter_camp else" in q
    # Opt-outs are checked before a newsletter enrolment.
    assert "is_on_dnc(email)" in inspect.getsource(fa.enroll_contact_in_evergreen)


def test_dialog_closes_and_hands_off_to_start_a_campaign():
    import flowdrip_app as fa
    dlg = inspect.getsource(fa._how_it_works_dialog)
    assert "_how_it_works_html()" in dlg
    assert "_start_campaign_dialog(s, rf, setup)" in dlg and "dlg.close" in dlg
    assert "max-height:90vh" in dlg and "overflow-y:auto" in dlg
    # Never a hex alpha appended to a var() colour.
    assert "_tint(C['teal'],'40')" in dlg


def test_styles_ship_scoped_with_the_sidebar_css():
    import flowdrip_app as fa
    css = fa._sidebar_layout_css()
    used = set(re.findall(r"fd-ph-how[a-z-]*", fa._how_it_works_html()))
    used |= {"fd-ph-how", "fd-ph-how-foot", "fd-ph-how-go"}
    for cls in used:
        assert f".{cls}" in css, cls
    assert ")22" not in css and ")55" not in css and ")2E" not in css

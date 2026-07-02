"""Send-time merge-token substitution for the Organic (J's Way) newsletter.

Newsletters defer their body (one shared HTML), so per-recipient tokens are
filled at send time by _apply_merge_tokens. Campaign bodies are already
substituted at queue time, so the helper must be a no-op for them. The
Organic renderer also prepends an auto "Hi {FirstName}," greeting.
"""
import flowdrip_app as fa


def test_firstname_from_contact_name():
    assert fa._apply_merge_tokens("Hi {FirstName},", {"contact_name": "Mike Vaughn"}) == "Hi Mike,"


def test_explicit_first_name_field_wins():
    out = fa._apply_merge_tokens("{FirstName}", {"first_name": "Bob", "contact_name": "Mike Vaughn"})
    assert out == "Bob"


def test_firstname_falls_back_to_there():
    assert fa._apply_merge_tokens("Hi {FirstName},", {}) == "Hi there,"


def test_lastname_company_jobtitle():
    item = {"contact_name": "Mike Vaughn", "contact_company": "Arena", "contact_title": "VP"}
    assert fa._apply_merge_tokens("{LastName} at {Company} ({JobTitle})", item) == "Vaughn at Arena (VP)"


def test_missing_optional_tokens_blank():
    # single-word name -> no last name; no company/title -> blank
    assert fa._apply_merge_tokens("{LastName}|{Company}|{JobTitle}", {"contact_name": "Cher"}) == "||"


def test_no_tokens_is_noop():
    s = "A plain sentence with no merge fields."
    assert fa._apply_merge_tokens(s, {}) == s


def test_multiple_occurrences_all_replaced():
    assert fa._apply_merge_tokens("{FirstName} & {FirstName}", {"first_name": "Jo"}) == "Jo & Jo"


def test_none_text_safe():
    assert fa._apply_merge_tokens(None, {"first_name": "Jo"}) == ""


def test_jway_render_prepends_greeting_before_intro():
    html = fa._jway_render({"intro": "Market note.", "highlights": [], "candidates": []}, "Jeff")
    assert "Hi {FirstName}," in html
    assert html.index("Hi {FirstName},") < html.index("Market note.")

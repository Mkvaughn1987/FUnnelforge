"""Regression tests for the San Diego Scoop incident (2026-06-04):

1. A queue item carrying real HTML with a missing/false is_html flag must
   NOT be HTML-escaped by the sender — otherwise the recipient sees
   "<!DOCTYPE html>…" as raw visible markup.
2. _resolve_body_from_campaign must use the SAME filename slug as
   save_campaign (re.sub(r"[^\w\-]","_")[:60]), or newsletters with "&" /
   hyphens / long names silently fail to send ("Missing email body").
"""
import json
import flowdrip_app as fa


def test_body_is_html_detects_real_html():
    assert fa._body_is_html("<!DOCTYPE html><html><body>hi</body></html>")
    assert fa._body_is_html('<div style="x">hello</div>')
    assert fa._body_is_html("line one<br>line two")
    assert fa._body_is_html("<table><tr><td>x</td></tr></table>")


def test_body_is_html_false_for_plain_text():
    assert not fa._body_is_html("Hi there,\n\nJust checking in. Thanks!")
    assert not fa._body_is_html("")
    assert not fa._body_is_html("no tags here at all")


def test_resolve_matches_save_campaign_slug_for_ampersand_name(with_user, tmp_path):
    """A newsletter named 'SoCal Schools & Staffing' must resolve its body
    even though the filename has triple underscores ('SoCal_Schools___Staffing')
    that the old re.sub(r'[^\\w]+') slug collapsed to a different name."""
    import flowdrip_app as fa
    camp = {
        "name": "SoCal Schools & Staffing",
        "evergreen_only": True,
        "market_analysis": True,
        "emails": [
            {"name": "Issue 1", "subject": "S0",
             "body": "<html><body>June issue</body></html>"},
        ],
    }
    fa.save_campaign(camp)  # writes SoCal_Schools___Staffing.json
    user_dir = fa._resolve_user_root()
    item = {"campaign": "SoCal Schools & Staffing", "_step_idx": 0}
    body = fa._resolve_body_from_campaign(item, user_dir)
    assert body == "<html><body>June issue</body></html>", (
        "resolve must find the body via the save_campaign slug"
    )


def test_resolve_falls_back_to_name_scan(with_user):
    """Even if the slug formula can't reproduce the filename, the name-scan
    fallback must find the campaign by its stored `name`."""
    import flowdrip_app as fa
    camp = {
        "name": "Weird @@@ Name!!!",
        "evergreen_only": True,
        "market_analysis": True,
        "emails": [{"name": "I0", "subject": "s", "body": "<div>x</div>"}],
    }
    fa.save_campaign(camp)
    user_dir = fa._resolve_user_root()
    item = {"campaign": "Weird @@@ Name!!!", "_step_idx": 0}
    assert fa._resolve_body_from_campaign(item, user_dir) == "<div>x</div>"


def test_resolve_returns_empty_for_unknown_campaign(with_user):
    import flowdrip_app as fa
    user_dir = fa._resolve_user_root()
    item = {"campaign": "Does Not Exist", "_step_idx": 0}
    assert fa._resolve_body_from_campaign(item, user_dir) == ""

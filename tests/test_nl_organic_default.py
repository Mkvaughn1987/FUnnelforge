"""New newsletters start Organic (text only); the handoff picker never says J's Way."""
import inspect

import flowdrip_app as fa


def test_create_dialog_defaults_to_organic():
    src = inspect.getsource(fa._create_newsletter_dialog)
    assert 'or "j_way")).props(' in src
    assert 'newsletter_style=(_style_toggle.value or "j_way")' in src


def test_handoff_option_says_organic():
    src = inspect.getsource(fa._offer_newsletter_enroll)
    assert "New organic newsletter" in src and "J's Way note" not in src

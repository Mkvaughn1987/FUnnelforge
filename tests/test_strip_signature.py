"""C4: _strip_signature_from_body must NOT truncate when the user's
own name appears inside the body (e.g. self-introduction)."""
import pytest


def test_strip_keeps_body_when_no_sig_delimiter_present(isolated_appdata, with_user):
    import flowdrip_app as fa

    sigp = fa._user_sig_path()
    sigp.parent.mkdir(parents=True, exist_ok=True)
    sigp.write_text("Michael Vaughn\nSales Director\nDripDrop\n", encoding="utf-8")

    # Put enough text before the name so idx > 30 (triggering the old fallback)
    body = (
        "Hi {FirstName}, hope you had a great weekend!\n\n"
        "My name is Michael Vaughn from DripDrop. We help sales teams...\n\n"
        "Looking forward to chatting!"
    )

    out = fa._strip_signature_from_body(body)
    assert "Looking forward to chatting!" in out, "Body was truncated on user's own name"
    assert "DripDrop" in out


def test_strip_removes_real_signature_block(isolated_appdata, with_user):
    """The strip MUST still work when a real signature delimiter is present."""
    import flowdrip_app as fa

    sigp = fa._user_sig_path()
    sigp.parent.mkdir(parents=True, exist_ok=True)
    sigp.write_text("Michael Vaughn\nSales Director\n", encoding="utf-8")

    body = (
        "Hi {FirstName},\n\n"
        "Hope you're doing well.\n\n"
        "--\n"
        "Michael Vaughn\n"
        "Sales Director\n"
    )

    out = fa._strip_signature_from_body(body)
    assert "Hope you're doing well." in out
    assert "Sales Director" not in out

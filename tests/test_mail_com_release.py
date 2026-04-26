"""C10c regression: the Mail COM object created via outlook.CreateItem(0)
must be explicitly released (`del mail`) in a `finally` block after every
send attempt — success, exception, or attachment failure. Without this,
each send leaks a COM ref and Outlook memory grows over time.

Static check: assert the `del mail` cleanup is wired correctly."""
import pathlib


def test_send_one_email_releases_mail_in_finally():
    src = pathlib.Path(__file__).resolve().parent.parent / "funnelforge_core.py"
    text = src.read_text(encoding="utf-8")

    # The function must initialize mail = None before the try, so the
    # finally branch can safely test it. (Otherwise an exception thrown
    # before CreateItem() leaves `mail` undefined and the finally
    # itself raises NameError.)
    assert "mail = None" in text, (
        "_send_one_email must initialize `mail = None` before the try/"
        "finally so the cleanup branch is safe even when CreateItem "
        "raises (C10c)."
    )

    # And the cleanup itself must exist in a finally clause.
    assert "del mail" in text, (
        "_send_one_email is missing `del mail` in the finally — "
        "every send leaks a Mail COM object (C10c)."
    )

    # Cross-check: the cleanup must be inside a finally, not just lying
    # in the success path.
    finally_idx = text.find("finally:")
    assert finally_idx != -1, "Expected a finally block in funnelforge_core.py"
    finally_block = text[finally_idx:finally_idx + 600]
    assert "del mail" in finally_block, (
        "del mail is in the file but NOT inside the finally block — "
        "exceptions still leak the Mail object (C10c)."
    )

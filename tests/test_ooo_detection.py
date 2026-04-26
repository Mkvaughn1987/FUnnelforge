"""H4 regression: _is_ooo_reply only inspected the first 500 chars of
the body. OOO keywords that appeared after a quoted prior message,
forwarded thread, or a long preamble were missed, causing the campaign
to keep emailing somebody who is on vacation."""


class _FakeItem:
    def __init__(self, subject: str, body: str):
        self.Subject = subject
        self.Body = body


def test_ooo_keyword_in_long_body_is_detected(isolated_appdata, with_user):
    import flowdrip_app as fa
    # Long preamble (forwarded message header, signature, quoted text...)
    # then the actual OOO marker far past 500 chars.
    preamble = "Thanks for your email. " * 80  # ~1840 chars of filler
    body = preamble + "\n\nI am currently out of the office and will reply when I return."
    assert len(preamble) > 500

    item = _FakeItem(subject="Re: Your message", body=body)

    assert fa._is_ooo_reply(item) is True, (
        "OOO keyword past first 500 chars must still be detected"
    )


def test_ooo_keyword_in_short_body_still_detected(isolated_appdata, with_user):
    """Sanity check: short bodies still work (no regression of happy path)."""
    import flowdrip_app as fa
    item = _FakeItem(subject="Auto-reply", body="On vacation until Friday.")
    assert fa._is_ooo_reply(item) is True


def test_normal_reply_is_not_flagged(isolated_appdata, with_user):
    """A regular reply with no OOO markers must not be flagged."""
    import flowdrip_app as fa
    item = _FakeItem(
        subject="Re: quick question",
        body="Sounds good, let's set up a call next week.",
    )
    assert fa._is_ooo_reply(item) is False

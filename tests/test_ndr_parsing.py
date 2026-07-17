"""Tests for NDR (bounce) parsing used by the reply-monitor suppression loop.

Root-cause context (2026-07-17 deliverability incident): the michael_vaughn
mailbox had 1,005 unprocessed NDRs. 69% came from Office 365's internal
generator (MicrosoftExchange<hex>@arenastaffing.net, display "Microsoft
Outlook"), which the old postmaster/mailer-daemon-only match ignored, and
the recipient/status parsing must not over-suppress transient or
policy-blocked addresses.
"""
import flowdrip_app as fa


# The exact NDR the user pasted from Outlook — an O365 DBEB rejection.
WECKWORTH_NDR = """Your message to thoberecht@weckworth.com couldn't be delivered.
thoberecht wasn't found at weckworth.com.
Status code: 550 5.4.1
This error occurred because a message was sent to an email address hosted
by Office 365, but the address doesn't exist. Directory Based Edge Blocking
(DBEB) is enabled for weckworth.com.
Original Message Details
Sender Address: michael.vaughn@arenastaffing.net
Recipient Address: thoberecht@weckworth.com
Subject: Thoughts on This?
Error: 550 5.4.1 Recipient address rejected: Access denied.
"""

# A DSN-format bounce from an external mailer-daemon.
DSN_NDR = """This is the mail system at host mx0b.pphosted.com.
I'm sorry to have to inform you that your message could not be delivered.
Final-Recipient: rfc822; jdoe@example.com
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
"""


# ── _parse_ndr_recipient ──────────────────────────────────────────────

def test_recipient_from_o365_recipient_address_line():
    r = fa._parse_ndr_recipient("Undeliverable: Thoughts on This?",
                                WECKWORTH_NDR, "arenastaffing.net")
    assert r == "thoberecht@weckworth.com"


def test_recipient_from_dsn_final_recipient():
    r = fa._parse_ndr_recipient("Undeliverable", DSN_NDR, "arenastaffing.net")
    assert r == "jdoe@example.com"


def test_recipient_never_returns_own_sending_domain():
    # The sender address appears in the body; it must not be picked.
    r = fa._parse_ndr_recipient("Undeliverable", WECKWORTH_NDR, "arenastaffing.net")
    assert "arenastaffing.net" not in r


def test_recipient_ignores_exchange_generator_address():
    body = ("From: MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109e@arenastaffing.net\n"
            "Your message to realperson@acme.com couldn't be delivered.")
    r = fa._parse_ndr_recipient("Undeliverable", body, "arenastaffing.net")
    assert r == "realperson@acme.com"


def test_recipient_empty_when_none_present():
    assert fa._parse_ndr_recipient("hi", "no addresses here", "arenastaffing.net") == ""


def test_recipient_strips_surrounding_quotes():
    # Real bug from the backfill dry-run: NDR quotes the address, e.g.
    # "Your message to 'jhooper@treebrand.com' couldn't be delivered" — the
    # captured address must not keep the leading apostrophe.
    body = "Your message to 'jhooper@treebrand.com' couldn't be delivered."
    r = fa._parse_ndr_recipient("Undeliverable", body, "arenastaffing.net")
    assert r == "jhooper@treebrand.com"


def test_recipient_strips_angle_brackets():
    body = "Final-Recipient: rfc822; <victor@treebrand.com>"
    r = fa._parse_ndr_recipient("Undeliverable", body, "arenastaffing.net")
    assert r == "victor@treebrand.com"


# ── _parse_ndr_status ─────────────────────────────────────────────────

def test_status_from_status_code_line():
    assert fa._parse_ndr_status(WECKWORTH_NDR) == "5.4.1"


def test_status_from_dsn_status_line():
    assert fa._parse_ndr_status(DSN_NDR) == "5.1.1"


def test_status_empty_when_absent():
    assert fa._parse_ndr_status("thoberecht wasn't found") == ""


# ── _classify_bounce ──────────────────────────────────────────────────

def test_classify_541_is_hard():
    assert fa._classify_bounce("5.4.1", WECKWORTH_NDR) == "hard"


def test_classify_511_is_hard():
    assert fa._classify_bounce("5.1.1", DSN_NDR) == "hard"


def test_classify_5110_is_hard():
    assert fa._classify_bounce("5.1.10", "recipient not found") == "hard"


def test_classify_mailbox_full_522_is_soft():
    # The person EXISTS — do not suppress a full mailbox.
    assert fa._classify_bounce("5.2.2", "the recipient's mailbox is full") == "soft"


def test_classify_policy_block_571_is_soft():
    # 5.7.1 body often says 'recipient address rejected' too — must NOT be
    # mistaken for a bad address. This is the over-suppression guard.
    body = "550 5.7.1 Recipient address rejected: Access denied by policy"
    assert fa._classify_bounce("5.7.1", body) == "soft"


def test_classify_transient_4xx_is_soft():
    assert fa._classify_bounce("4.4.4", "temporary failure, will retry") == "soft"


def test_classify_no_code_uses_hard_phrase():
    assert fa._classify_bounce("", "thoberecht wasn't found at weckworth.com") == "hard"


def test_classify_no_code_no_phrase_is_soft():
    assert fa._classify_bounce("", "message delayed, will keep trying") == "soft"


# ── _is_ndr_message ───────────────────────────────────────────────────

def test_is_ndr_o365_exchange_generator():
    # The 69% case that the old check missed.
    assert fa._is_ndr_message(
        "microsoftexchange329e71ec88ae4615bbc36ab6ce41109e@arenastaffing.net",
        "Undeliverable: Thoughts on This?") is True


def test_is_ndr_external_mailer_daemon():
    assert fa._is_ndr_message("mailer-daemon@googlemail.com",
                              "Delivery Status Notification (Failure)") is True


def test_is_ndr_by_subject_only():
    assert fa._is_ndr_message("weird-sender@somewhere.com",
                              "Undeliverable: Top Talent Insights") is True


def test_is_not_ndr_for_normal_reply():
    assert fa._is_ndr_message("prospect@acme.com", "Re: Thoughts on This?") is False


# ── End-to-end: the pasted NDR resolves to a suppressible hard bounce ──

def test_weckworth_ndr_end_to_end_hard():
    subj = "Undeliverable: Thoughts on This?"
    assert fa._is_ndr_message("microsoftexchange329e71ec@arenastaffing.net", subj)
    rcpt = fa._parse_ndr_recipient(subj, WECKWORTH_NDR, "arenastaffing.net")
    code = fa._parse_ndr_status(WECKWORTH_NDR)
    assert rcpt == "thoberecht@weckworth.com"
    assert fa._classify_bounce(code, WECKWORTH_NDR) == "hard"


# ── _record_soft_bounce (repeat-then-remove for soft bounces) ─────────

def test_soft_bounce_removes_only_after_threshold():
    t = {}
    assert fa._record_soft_bounce(t, "a@x.com", "m1", "5.2.2", 3) is False
    assert fa._record_soft_bounce(t, "a@x.com", "m2", "5.2.2", 3) is False
    assert fa._record_soft_bounce(t, "a@x.com", "m3", "5.2.2", 3) is True
    assert t["a@x.com"]["count"] == 3


def test_soft_bounce_dedups_same_message_id():
    # The same NDR re-seen across scans must not advance the count.
    t = {}
    fa._record_soft_bounce(t, "a@x.com", "m1", "5.4.316", 3)
    fa._record_soft_bounce(t, "a@x.com", "m1", "5.4.316", 3)
    fa._record_soft_bounce(t, "a@x.com", "m1", "5.4.316", 3)
    assert t["a@x.com"]["count"] == 1  # counted once despite 3 sightings


def test_soft_bounce_distinct_messages_advance():
    t = {}
    fa._record_soft_bounce(t, "a@x.com", "m1", "5.2.2", 3)
    fa._record_soft_bounce(t, "a@x.com", "m1", "5.2.2", 3)   # dup, ignored
    fa._record_soft_bounce(t, "a@x.com", "m2", "5.2.2", 3)
    reached = fa._record_soft_bounce(t, "a@x.com", "m3", "5.2.2", 3)
    assert t["a@x.com"]["count"] == 3 and reached is True


def test_soft_bounce_tracks_per_address():
    t = {}
    fa._record_soft_bounce(t, "a@x.com", "m1", "5.2.2", 3)
    fa._record_soft_bounce(t, "b@y.com", "m2", "5.2.2", 3)
    assert t["a@x.com"]["count"] == 1 and t["b@y.com"]["count"] == 1


def test_soft_bounce_caps_stored_message_ids():
    t = {}
    for i in range(30):
        fa._record_soft_bounce(t, "a@x.com", f"m{i}", "5.2.2", 100)
    assert len(t["a@x.com"]["msg_ids"]) == 20  # keeps only the last 20
    assert t["a@x.com"]["count"] == 30


def test_soft_bounce_records_last_status():
    t = {}
    fa._record_soft_bounce(t, "a@x.com", "m1", "5.2.2", 3)
    fa._record_soft_bounce(t, "a@x.com", "m2", "5.4.316", 3)
    assert t["a@x.com"]["last_status"] == "5.4.316"

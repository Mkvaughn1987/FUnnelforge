"""The Roundup — gated, hand-authored internal newsletter.

Spec: docs/superpowers/specs/2026-06-23-the-roundup-marketing-newsletter-design.md
"""
import flowdrip_app as fa


def test_roundup_gate_allows_owner_and_michael():
    assert fa._roundup_allowed("rothany.vu@arenastaffing.net") is True
    assert fa._roundup_allowed("michael.vaughn@arenastaffing.net") is True
    assert fa._roundup_allowed("mkvaughn1987@gmail.com") is True


def test_roundup_gate_is_case_and_space_insensitive():
    assert fa._roundup_allowed("  Rothany.Vu@ArenaStaffing.net ") is True


def test_roundup_gate_blocks_everyone_else():
    assert fa._roundup_allowed("someone.else@arenastaffing.net") is False
    assert fa._roundup_allowed("") is False
    assert fa._roundup_allowed(None) is False


def test_roundup_owner_is_rothany():
    assert fa._ROUNDUP_OWNER_EMAIL == "rothany.vu@arenastaffing.net"

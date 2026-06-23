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


def test_roundup_dir_is_under_owner_root(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", tmp_path)
    d = fa._roundup_dir()
    owner_root = fa._resolve_user_root(fa._ROUNDUP_OWNER_EMAIL)
    assert str(d).startswith(str(owner_root))
    assert d.name == "Roundup"


def test_roundup_issue_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", tmp_path)
    issue = fa._roundup_new_issue("June 2026")
    issue["marketing_minute"] = "<p>Hello team</p>"
    issue["new_items"] = [{"lead": "Logos", "body": "<p>x</p>", "image": None}]
    fa._roundup_save_issue(issue)

    loaded = fa._roundup_load_issue(issue["id"])
    assert loaded["issue_label"] == "June 2026"
    assert loaded["marketing_minute"] == "<p>Hello team</p>"
    assert loaded["new_items"][0]["lead"] == "Logos"


def test_roundup_index_lists_saved_issues(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", tmp_path)
    a = fa._roundup_new_issue("May 2026")
    b = fa._roundup_new_issue("June 2026")
    fa._roundup_save_issue(a)
    fa._roundup_save_issue(b)
    idx = fa._roundup_index()
    labels = {row["issue_label"] for row in idx}
    assert {"May 2026", "June 2026"} <= labels


def test_roundup_new_issue_has_default_subject_and_status():
    issue = fa._roundup_new_issue("July 2026")
    assert issue["status"] == "draft"
    assert issue["subject"] == "The Roundup — July 2026"
    assert issue["president"]["title"] == "President & CEO"
    assert issue["new_items"] == []
    assert issue["looking_ahead"] == []

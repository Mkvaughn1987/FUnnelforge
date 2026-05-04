"""Every PAGE_HELP entry must have non-empty summary + next_action
fields after the migration to support the page intro strip."""

EXPECTED_KEYS = {
    "dashboard", "drip", "start_seq", "seq_mgr", "evergreen",
    "newsletters", "candidate_finder", "contacts", "pdf_gen",
    "queue", "responses", "signature", "dnc", "ai_settings",
}


def test_every_page_has_summary_and_next_action():
    import flowdrip_app as fa
    missing = []
    for key in EXPECTED_KEYS:
        entry = fa.PAGE_HELP.get(key)
        assert entry is not None, f"PAGE_HELP missing key: {key}"
        if not (entry.get("summary") or "").strip():
            missing.append(f"{key}.summary")
        if not (entry.get("next_action") or "").strip():
            missing.append(f"{key}.next_action")
    assert not missing, f"Empty fields: {missing}"


def test_newsletters_entry_exists_separately_from_evergreen():
    """The Newsletters page used to share the 'evergreen' help entry,
    which is wrong now that the strip uses page-specific copy."""
    import flowdrip_app as fa
    nl = fa.PAGE_HELP.get("newsletters")
    eg = fa.PAGE_HELP.get("evergreen")
    assert nl is not None
    assert eg is not None
    assert nl["title"] != eg["title"]
    assert nl["summary"] != eg["summary"]


def test_summary_is_short_enough():
    """Strip layout assumes summary fits comfortably on one line.
    140 chars is generous (about 2 lines on a narrow column)."""
    import flowdrip_app as fa
    for key in EXPECTED_KEYS:
        s = fa.PAGE_HELP[key]["summary"]
        assert len(s) <= 140, f"{key}.summary is {len(s)} chars (>140): {s}"


def test_next_action_is_short_enough():
    import flowdrip_app as fa
    for key in EXPECTED_KEYS:
        s = fa.PAGE_HELP[key]["next_action"]
        assert len(s) <= 160, f"{key}.next_action is {len(s)} chars (>160): {s}"

"""dismissed_help_strips lives in the user's dripdrop_config.json.
Round-trip semantics: append-on-dismiss, idempotent (no duplicates),
clear-all is supported."""


def test_dismiss_appends_page_key_to_config(with_user):
    import flowdrip_app as fa
    fa.save_config({})
    fa._dismiss_help_strip("dashboard")
    cfg = fa.load_config()
    assert cfg.get("dismissed_help_strips") == ["dashboard"]


def test_dismiss_is_idempotent(with_user):
    import flowdrip_app as fa
    fa.save_config({"dismissed_help_strips": ["dashboard"]})
    fa._dismiss_help_strip("dashboard")
    cfg = fa.load_config()
    assert cfg.get("dismissed_help_strips") == ["dashboard"]


def test_dismiss_preserves_other_config_keys(with_user):
    import flowdrip_app as fa
    fa.save_config({"sig_email": "x@y.com", "user_timezone": "America/Denver"})
    fa._dismiss_help_strip("newsletters")
    cfg = fa.load_config()
    assert cfg["sig_email"] == "x@y.com"
    assert cfg["user_timezone"] == "America/Denver"
    assert cfg["dismissed_help_strips"] == ["newsletters"]


def test_is_help_strip_dismissed_returns_true_when_present(with_user):
    import flowdrip_app as fa
    fa.save_config({"dismissed_help_strips": ["dashboard", "newsletters"]})
    assert fa._is_help_strip_dismissed("dashboard") is True
    assert fa._is_help_strip_dismissed("newsletters") is True
    assert fa._is_help_strip_dismissed("contacts") is False


def test_is_help_strip_dismissed_handles_missing_key(with_user):
    import flowdrip_app as fa
    fa.save_config({})
    assert fa._is_help_strip_dismissed("dashboard") is False


def test_clear_all_dismissals_resets_to_empty_list(with_user):
    import flowdrip_app as fa
    fa.save_config({"dismissed_help_strips": ["a", "b", "c"]})
    fa._clear_all_dismissed_help_strips()
    assert fa.load_config().get("dismissed_help_strips") == []

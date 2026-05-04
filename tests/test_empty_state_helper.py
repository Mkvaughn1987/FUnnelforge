"""_render_empty_state renders a centered card with emoji + headline + body
+ CTA button. Same as the strip helper, we test short-circuit logic and
that elements are emitted when active."""


class _CallCounter:
    def __init__(self):
        self.calls = 0
    def __call__(self, *_a, **_kw):
        self.calls += 1
        return self
    def style(self, *_a, **_kw): return self
    def classes(self, *_a, **_kw): return self
    def on(self, *_a, **_kw): return self
    def __enter__(self): return self
    def __exit__(self, *_a): return False


def test_render_empty_state_does_nothing_for_unknown_page(monkeypatch):
    import flowdrip_app as fa
    counter = _CallCounter()
    monkeypatch.setattr(fa.ui, "element", counter)
    monkeypatch.setattr(fa.ui, "label", counter)
    fa._render_empty_state(None, lambda: None, "not_a_real_page")
    assert counter.calls == 0


def test_render_empty_state_emits_elements_for_known_page(monkeypatch):
    import flowdrip_app as fa
    counter = _CallCounter()
    monkeypatch.setattr(fa.ui, "element", counter)
    monkeypatch.setattr(fa.ui, "label", counter)
    fa._render_empty_state(None, lambda: None, "seq_mgr")
    assert counter.calls > 0


def test_empty_states_dict_has_required_fields():
    import flowdrip_app as fa
    REQUIRED = {"icon", "headline", "body", "cta_label", "cta_target"}
    for key, entry in fa.EMPTY_STATES.items():
        missing = REQUIRED - set(entry.keys())
        assert not missing, f"{key} missing fields: {missing}"
        for field in REQUIRED:
            assert (entry[field] or "").strip(), f"{key}.{field} is empty"


def test_empty_states_route_targets_resolve_or_use_action_prefix():
    """cta_target is either an existing s.sp route key (any non-empty
    string without @ prefix) or a page-local action key with @ prefix.
    We can't introspect all valid route keys here, but we can confirm
    the strings are well-formed."""
    import flowdrip_app as fa
    for key, entry in fa.EMPTY_STATES.items():
        target = entry["cta_target"]
        assert isinstance(target, str) and target.strip(), \
            f"{key}.cta_target must be a non-empty string"

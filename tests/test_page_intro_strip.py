"""_render_page_intro_strip is a UI render helper. We can't easily snapshot-test
the rendered HTML, but we can assert its short-circuit logic: it should render
NOTHING when the page key is missing, when fields are empty, or when the user
has dismissed the strip. We test the render via call counting on a mock
ui.element to avoid a full NiceGUI app context."""


class _CallCounter:
    """Stand-in for ui.element() that lets us count how many child elements
    were created by the helper without spinning up a NiceGUI app."""
    def __init__(self):
        self.calls = 0

    def __call__(self, *_a, **_kw):
        self.calls += 1
        return self

    def style(self, *_a, **_kw):
        return self

    def classes(self, *_a, **_kw):
        return self

    def on(self, *_a, **_kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_render_strip_does_nothing_when_page_key_missing(with_user, monkeypatch):
    import flowdrip_app as fa
    counter = _CallCounter()
    monkeypatch.setattr(fa.ui, "element", counter)
    monkeypatch.setattr(fa.ui, "label", counter)
    monkeypatch.setattr(fa.ui, "html", counter)
    monkeypatch.setattr(fa.ui, "icon", counter, raising=False)
    fa._render_page_intro_strip(None, lambda: None, "not_a_real_page")
    assert counter.calls == 0


def test_render_strip_does_nothing_when_summary_empty(with_user, monkeypatch):
    import flowdrip_app as fa
    fa.PAGE_HELP["__test_empty__"] = {
        "title": "Test",
        "summary": "",
        "next_action": "Click here",
        "sections": [],
    }
    counter = _CallCounter()
    monkeypatch.setattr(fa.ui, "element", counter)
    monkeypatch.setattr(fa.ui, "label", counter)
    monkeypatch.setattr(fa.ui, "html", counter)
    monkeypatch.setattr(fa.ui, "icon", counter, raising=False)
    fa._render_page_intro_strip(None, lambda: None, "__test_empty__")
    assert counter.calls == 0
    del fa.PAGE_HELP["__test_empty__"]


def test_render_strip_does_nothing_when_dismissed(with_user, monkeypatch):
    import flowdrip_app as fa
    fa.save_config({"dismissed_help_strips": ["dashboard"]})
    counter = _CallCounter()
    monkeypatch.setattr(fa.ui, "element", counter)
    monkeypatch.setattr(fa.ui, "label", counter)
    monkeypatch.setattr(fa.ui, "html", counter)
    monkeypatch.setattr(fa.ui, "icon", counter, raising=False)
    fa._render_page_intro_strip(None, lambda: None, "dashboard")
    assert counter.calls == 0


def test_render_strip_emits_elements_when_active(with_user, monkeypatch):
    import flowdrip_app as fa
    fa.save_config({})  # not dismissed
    counter = _CallCounter()
    monkeypatch.setattr(fa.ui, "element", counter)
    monkeypatch.setattr(fa.ui, "label", counter)
    monkeypatch.setattr(fa.ui, "html", counter)
    monkeypatch.setattr(fa.ui, "icon", counter, raising=False)
    fa._render_page_intro_strip(None, lambda: None, "dashboard")
    assert counter.calls > 0  # at minimum: outer div + summary label + next_action label

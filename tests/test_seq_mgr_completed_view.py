"""Current Campaigns: the Completed view must not list active campaigns.

Reported 2026-10-02: clicking Completed in the sidebar kept the Active list
(campaigns with pending emails) on top and only added completed ones below.
"""
import types

import flowdrip_app as fa


class _Fake:
    def __init__(self, log, text=None):
        self._log = log
        if text is not None:
            log.append(str(text))

    def __getattr__(self, _):
        return lambda *a, **k: self

    def __call__(self, *a, **k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter((self, self, self, self))


def _render(monkeypatch, show_completed, sel=""):
    log = []

    class _FakeUI:
        def __getattr__(self, n):
            return lambda *a, **k: _Fake(log, a[0] if (n == "label" and a) else None)

    fake_ui = _FakeUI()
    monkeypatch.setattr(fa, "ui", fake_ui)
    camps = [
        {"name": "Live One", "status": "active", "contacts": [{"email": "a@x.com"}], "emails": []},
        {"name": "Done One", "status": "active", "contacts": [{"email": "b@x.com"}], "emails": []},
    ]
    queue = [
        {"campaign": "Live One", "status": "pending", "subject": "s1"},
        {"campaign": "Done One", "status": "sent", "subject": "s1"},
    ]
    monkeypatch.setattr(fa, "load_campaigns", lambda: camps)
    monkeypatch.setattr(fa, "_load_queue", lambda: queue)
    monkeypatch.setattr(fa, "_render_page_intro_strip", lambda *a, **k: None)
    monkeypatch.setattr(fa, "_show_page_help", lambda *a, **k: None)
    s = types.SimpleNamespace(_mgr_show_completed=show_completed, sel_camp_name=sel)
    try:
        fa.p_seq_mgr(s, lambda: None)
    except Exception:
        pass  # the detail pane needs more app state; the list renders first
    return log, s


def test_completed_view_hides_active(monkeypatch):
    log, s = _render(monkeypatch, True)
    assert "Completed Campaigns" in log
    assert "Live One" not in log
    assert "Done One" in log
    assert not any(t.startswith("Active (") for t in log)
    assert "Show Active (1)" in log


def test_active_view_hides_completed(monkeypatch):
    log, s = _render(monkeypatch, False)
    assert "Current Campaigns" in log
    assert "Live One" in log
    assert not any(t.startswith("Completed (") for t in log)


def test_opening_active_campaign_switches_view(monkeypatch):
    log, s = _render(monkeypatch, True, sel="Live One")
    assert s._mgr_show_completed is False
    assert "Current Campaigns" in log

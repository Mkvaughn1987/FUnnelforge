"""Regression: 2026-05-01 user report — pages "time out" and bounce
back to dashboard if you sit on them too long. Root cause is a
collision between two intents:

1. First open (cold start, idle hours) → land on Dashboard (not the
   user's last-viewed list page).
2. Mid-session websocket reconnect (Cloudflare's ~100s WS idle timeout
   fires) → preserve whatever page the user was on, otherwise it feels
   like the app "kicked them out".

Both events hit `/` and rebuild AppState. We disambiguate by AGE of the
last-page timestamp: if the user was active < ~5 minutes ago, treat it
as a reconnect and preserve the page. If older, treat it as a fresh
open and apply the list-page → dashboard redirect that came in 2026-04-27.
"""
from datetime import datetime, timedelta, timezone


class _FakeStorage(dict):
    """Stand-in for app.storage.user — a plain dict with .get/.pop."""
    pass


def _install_fake_storage(monkeypatch, fa, store: dict):
    """Patch fa.app.storage.user to return our fake dict."""
    class _UserNS:
        def get(self, k, default=None):  return store.get(k, default)
        def __getitem__(self, k):        return store[k]
        def __setitem__(self, k, v):     store[k] = v
        def pop(self, k, default=None):  return store.pop(k, default)
        def __contains__(self, k):       return k in store

    class _StorageNS:
        user = _UserNS()
    class _AppNS:
        storage = _StorageNS()
    monkeypatch.setattr(fa, "app", _AppNS())


def _utc_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── 1. RECENT timestamp + list page → page IS preserved (no bounce) ──

def test_recent_reconnect_on_active_camps_preserves_page(isolated_appdata, with_user, monkeypatch):
    """User on Active Campaigns, websocket dies after 100s, reconnects.
    The reconnect MUST land them back on Active Campaigns, NOT bounce
    to Dashboard. Anything else feels like the app "timed them out"."""
    import flowdrip_app as fa
    store = {
        "_last_hub": "sales",
        "_last_sp":  "active_camps",
        "_last_ep":  "emails_home",
        "_last_page_ts": _utc_iso(datetime.utcnow() - timedelta(seconds=90)),
    }
    _install_fake_storage(monkeypatch, fa, store)
    s = fa.AppState()
    ok = fa._restore_page_if_recent(s)
    assert ok is True
    assert s.sp == "active_camps", (
        f"Recent reconnect (90s ago) on Active Campaigns must preserve the "
        f"page; got {s.sp!r}. This is the user-reported timeout-to-dashboard "
        f"bug."
    )


def test_recent_reconnect_on_seq_mgr_preserves_page(isolated_appdata, with_user, monkeypatch):
    """Same regression on the Sequence Manager page."""
    import flowdrip_app as fa
    store = {
        "_last_hub": "sales",
        "_last_sp":  "seq_mgr",
        "_last_ep":  "emails_home",
        "_last_page_ts": _utc_iso(datetime.utcnow() - timedelta(seconds=30)),
    }
    _install_fake_storage(monkeypatch, fa, store)
    s = fa.AppState()
    fa._restore_page_if_recent(s)
    assert s.sp == "seq_mgr"


def test_recent_reconnect_on_responses_preserves_page(isolated_appdata, with_user, monkeypatch):
    """Same regression on the Replies / Responses page."""
    import flowdrip_app as fa
    store = {
        "_last_hub": "sales",
        "_last_sp":  "responses",
        "_last_ep":  "emails_home",
        "_last_page_ts": _utc_iso(datetime.utcnow() - timedelta(seconds=200)),
    }
    _install_fake_storage(monkeypatch, fa, store)
    s = fa.AppState()
    fa._restore_page_if_recent(s)
    assert s.sp == "responses"


# ── 2. OLD timestamp + list page → redirect to Dashboard (cold open) ──

def test_old_open_on_active_camps_redirects_to_dashboard(isolated_appdata, with_user, monkeypatch):
    """User closed the laptop yesterday on Active Campaigns; opens the
    app fresh today. Dashboard should be the landing page (the
    2026-04-27 product decision), NOT the page they happened to be on
    last."""
    import flowdrip_app as fa
    store = {
        "_last_hub": "sales",
        "_last_sp":  "active_camps",
        "_last_ep":  "emails_home",
        "_last_page_ts": _utc_iso(datetime.utcnow() - timedelta(hours=8)),
    }
    _install_fake_storage(monkeypatch, fa, store)
    s = fa.AppState()
    fa._restore_page_if_recent(s)
    assert s.sp == "dashboard"


def test_old_open_on_seq_mgr_redirects_to_dashboard(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    store = {
        "_last_hub": "sales",
        "_last_sp":  "seq_mgr",
        "_last_ep":  "emails_home",
        "_last_page_ts": _utc_iso(datetime.utcnow() - timedelta(hours=2)),
    }
    _install_fake_storage(monkeypatch, fa, store)
    s = fa.AppState()
    fa._restore_page_if_recent(s)
    assert s.sp == "dashboard"


# ── 3. Deep workflow pages always preserved (any age within TTL) ──

def test_recent_reconnect_on_ai_campaign_wizard_preserves(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    store = {
        "_last_hub": "sales",
        "_last_sp":  "ai_campaign",
        "_last_ep":  "emails_home",
        "_last_page_ts": _utc_iso(datetime.utcnow() - timedelta(seconds=45)),
    }
    _install_fake_storage(monkeypatch, fa, store)
    s = fa.AppState()
    fa._restore_page_if_recent(s)
    assert s.sp == "ai_campaign"


def test_old_open_on_ai_campaign_wizard_still_preserves(isolated_appdata, with_user, monkeypatch):
    """Deep workflow pages — wizards, editors, settings — always
    restore (within the 24h TTL) because losing wizard progress is far
    worse than landing on a non-default page on cold open."""
    import flowdrip_app as fa
    store = {
        "_last_hub": "sales",
        "_last_sp":  "ai_campaign",
        "_last_ep":  "emails_home",
        "_last_page_ts": _utc_iso(datetime.utcnow() - timedelta(hours=6)),
    }
    _install_fake_storage(monkeypatch, fa, store)
    s = fa.AppState()
    fa._restore_page_if_recent(s)
    assert s.sp == "ai_campaign"


def test_stale_beyond_ttl_returns_false(isolated_appdata, with_user, monkeypatch):
    """Saved >24h ago → ignore entirely (existing behavior, regression
    guard)."""
    import flowdrip_app as fa
    store = {
        "_last_hub": "sales",
        "_last_sp":  "ai_campaign",
        "_last_ep":  "emails_home",
        "_last_page_ts": _utc_iso(datetime.utcnow() - timedelta(hours=48)),
    }
    _install_fake_storage(monkeypatch, fa, store)
    s = fa.AppState()
    s.sp = "dashboard"  # default; restore should be a no-op
    ok = fa._restore_page_if_recent(s)
    assert ok is False
    assert s.sp == "dashboard"

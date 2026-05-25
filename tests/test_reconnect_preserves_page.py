"""Root URL always lands on Dashboard (2026-05-25 directive).

History: 2026-04-27 we added a "list pages bounce to Dashboard on cold
open after 5 min" heuristic. 2026-05-02 we reverted it because the age
threshold conflated WS reconnect with cold open. 2026-05-25 the user
asked for the rule we landed on: ALWAYS Dashboard at the root URL,
regardless of where they were last time. AICB / Target-Candidate wizard
state is preserved separately for brief WS reconnects via
`_restore_aicb_state` (5-min TTL), so this contract doesn't lose
mid-wizard work — it just stops persisting "what list view was I on."

These tests lock in that contract.
"""


def test_appstate_default_page_is_dashboard():
    """Fresh AppState defaults to sp='dashboard'. index() relies on
    this default for the root-URL landing — if the default ever
    changes, the landing page silently changes too."""
    import flowdrip_app as fa
    s = fa.AppState()
    assert s.sp == "dashboard"
    assert s.hub == "sales"


def test_restore_page_helper_was_removed():
    """The old `_restore_page_if_recent` helper is gone — root URL
    always lands on the AppState default (Dashboard). Guard against
    a future refactor reintroducing the restore-last-page indirection
    without anyone noticing."""
    import flowdrip_app as fa
    assert not hasattr(fa, "_restore_page_if_recent"), (
        "Restore-last-page logic was removed 2026-05-25 — root URL "
        "should always land on Dashboard. If you reintroduced it, "
        "read docs/superpowers/specs first."
    )


def test_save_current_page_only_writes_timestamp():
    """`_save_current_page` no longer persists hub/sp/ep — only the
    timestamp, which `_restore_aicb_state` uses as its freshness clock
    for WS-reconnect-within-5-min wizard rehydration. If someone adds
    back the page identity writes, the root-URL → Dashboard contract
    breaks silently."""
    import flowdrip_app as fa

    written = {}

    class _UserNS:
        def get(self, k, default=None):
            return written.get(k, default)
        def __setitem__(self, k, v):
            written[k] = v

    class _StorageNS:
        user = _UserNS()

    class _AppNS:
        storage = _StorageNS()

    _orig = fa.app
    fa.app = _AppNS()
    try:
        s = fa.AppState()
        s.hub = "sales"
        s.sp = "responses"
        s.ep = "emails_home"
        fa._save_current_page(s)
    finally:
        fa.app = _orig

    assert "_last_page_ts" in written, "timestamp must be written"
    assert "_last_sp" not in written, (
        "_last_sp must NOT be persisted — would re-enable the old "
        "restore-last-page behavior")
    assert "_last_hub" not in written
    assert "_last_ep" not in written

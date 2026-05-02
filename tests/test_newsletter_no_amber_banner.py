"""Newsletters auto-refresh themselves, so they should NOT appear in the
amber 'Slow Drip emails sending soon' reminder banner. Slow drips still do."""
import json
from datetime import datetime, timedelta


def _seed(fa, name, market_analysis, days_out):
    """Seed a campaign + queue item in the resolved per-user path. In
    desktop test mode `_resolve_user_root()` returns `_BASE_DATA_DIR`
    directly, so we write through the same accessor the app uses."""
    camp_dir = fa._user_campaigns_dir()
    camp_dir.mkdir(parents=True, exist_ok=True)
    (camp_dir / f"{name.replace(' ', '_')}.json").write_text(json.dumps({
        "name": name, "evergreen_only": True,
        "market_analysis": market_analysis,
        "emails": [{"name": "S1", "step_type": "email_auto"}],
    }), encoding="utf-8")
    when = (datetime.now() + timedelta(days=days_out)).isoformat()
    qp = fa._user_queue_path()
    qp.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if qp.exists():
        existing = json.loads(qp.read_text(encoding="utf-8"))
    existing.append({
        "id": f"q-{name}", "campaign": name, "step_name": "S1",
        "to": "x@y.com", "send_dt": when, "status": "pending",
    })
    qp.write_text(json.dumps(existing), encoding="utf-8")


def _disable_ffc(monkeypatch, fa):
    """funnelforge_core wraps queue I/O on desktop; force the JSON path
    so seeded queue files are actually read."""
    monkeypatch.setattr(fa, "_FUNNELFORGE_OK", False)
    monkeypatch.setattr(fa, "_ffc", None)
    fa._cache_queue.invalidate()
    fa._cache_campaigns.invalidate()


def test_newsletter_excluded_from_reminders(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    _disable_ffc(monkeypatch, fa)
    _seed(fa, "NL Camp", market_analysis=True, days_out=2)
    rems = fa.get_evergreen_reminders()
    assert all(r["camp_name"] != "NL Camp" for r in rems), \
        f"Newsletters must NOT appear in the amber banner. Got: {[r['camp_name'] for r in rems]}"


def test_slow_drip_still_appears(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    _disable_ffc(monkeypatch, fa)
    _seed(fa, "Plain SD", market_analysis=False, days_out=2)
    rems = fa.get_evergreen_reminders()
    assert any(r["camp_name"] == "Plain SD" for r in rems), \
        f"Slow drips should still appear in the amber banner. Got: {[r['camp_name'] for r in rems]}"

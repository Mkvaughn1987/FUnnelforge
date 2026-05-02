"""Each monthly issue should default to a different hero photo so the
newsletter doesn't look identical month after month. Auto-refresh sets
`_hero_variant = step_idx % 5` if not already set. If the user has
manually set _hero_variant, it must be preserved."""
import json
from datetime import datetime, timedelta, timezone


def _setup_with_steps(user_root, steps):
    camp_dir = user_root / "Campaigns"
    camp_dir.mkdir(parents=True, exist_ok=True)
    (camp_dir / "NL.json").write_text(json.dumps({
        "name": "NL", "newsletter_name": "NL", "market_analysis": True,
        "evergreen_only": True, "_owner_email": "tester@example.com",
        "emails": steps,
    }), encoding="utf-8")
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None).isoformat()
    queue = []
    for i, st in enumerate(steps):
        queue.append({"id": f"q{i}", "campaign": "NL",
                      "step_name": st["name"], "subject": st.get("subject",""),
                      "to": "x@y.com", "send_dt": soon, "status": "pending"})
    (user_root / "scheduled_queue.json").write_text(json.dumps(queue), encoding="utf-8")


def test_hero_variant_defaults_to_step_index_mod_5(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    _setup_with_steps(with_user, [
        {"name": f"I{i}", "subject": "stale", "body": "<p>stale</p>",
         "step_type": "email_auto"} for i in range(7)
    ])
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step",
        lambda c, i: (f"S{i}", f"<p>B{i}</p>"))
    monkeypatch.setattr(fa, "_send_email_universal", lambda **kw: (True, ""))
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", with_user.parent.parent)

    # The sweep refreshes one step per campaign per tick (the next pending one),
    # so loop until all are done.
    for _ in range(10):
        fa._auto_refresh_newsletter_tick()

    saved = json.loads((with_user / "Campaigns" / "NL.json").read_text(encoding="utf-8"))
    for i, st in enumerate(saved["emails"]):
        if st.get("auto_confirmed"):
            assert st.get("_hero_variant") == i % 5, \
                f"step {i}: expected variant {i % 5}, got {st.get('_hero_variant')}"


def test_hero_variant_user_override_preserved(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa
    _setup_with_steps(with_user, [
        {"name": "I0", "subject": "stale", "body": "<p>stale</p>",
         "step_type": "email_auto", "_hero_variant": 4},
    ])
    monkeypatch.setattr(fa, "_generate_newsletter_content_for_step",
        lambda c, i: ("FRESH", "<p>FRESH</p>"))
    monkeypatch.setattr(fa, "_send_email_universal", lambda **kw: (True, ""))
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", with_user.parent.parent)
    fa._auto_refresh_newsletter_tick()
    saved = json.loads((with_user / "Campaigns" / "NL.json").read_text(encoding="utf-8"))
    assert saved["emails"][0]["_hero_variant"] == 4

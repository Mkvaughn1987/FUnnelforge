"""New sales-instance users get one organic newsletter per industry."""
import flowdrip_app as fa


def _run_inline(monkeypatch):
    monkeypatch.setattr(fa, "_run_as_user", lambda e, t, name=None, daemon=True: t())


def test_seeds_one_organic_per_sector(monkeypatch):
    _run_inline(monkeypatch)
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    saved, gen = [], []
    monkeypatch.setattr(fa, "load_campaigns", lambda *a, **k: [])
    monkeypatch.setattr(fa, "save_campaign", lambda c: saved.append(c))
    monkeypatch.setattr(fa, "_gen_one_issue_for_campaign",
                        lambda n, i: gen.append((n, i)))
    fa._seed_starter_newsletters("a@b.com")
    assert len(saved) == len(fa._TM_NEWSLETTER_SECTORS)
    assert {c["newsletter_style"] for c in saved} == {"j_way"}
    assert all(c["newsletter_spotlight_count"] == 0 and not c["contacts"] for c in saved)
    assert len(gen) == len(saved) and all(i == 0 for _, i in gen)


def test_idempotent_and_arena_noop(monkeypatch):
    _run_inline(monkeypatch)
    saved = []
    monkeypatch.setattr(fa, "save_campaign", lambda c: saved.append(c))
    monkeypatch.setattr(fa, "_gen_one_issue_for_campaign", lambda n, i: None)
    monkeypatch.setattr(fa, "_SALES_MODE", False)
    monkeypatch.setattr(fa, "load_campaigns", lambda *a, **k: [])
    fa._seed_starter_newsletters("a@b.com")
    assert saved == []
    monkeypatch.setattr(fa, "_SALES_MODE", True)
    names = [f"{m['label']} Monthly Note" for m in fa._TM_NEWSLETTER_SECTORS.values()]
    monkeypatch.setattr(fa, "load_campaigns", lambda *a, **k: [{"name": n} for n in names])
    fa._seed_starter_newsletters("a@b.com")
    assert saved == []

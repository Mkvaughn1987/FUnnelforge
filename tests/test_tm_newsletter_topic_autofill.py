"""The "what do you want this newsletter to be about?" box is drafted for
the user on the sales instance (Mike, 2026-09-24): a short brief written
from the newsletter name, sector, niche and region, editable afterwards.
A failed AI call still fills the box from the sector's own role list."""
import inspect
import types

import anthropic

import flowdrip_app as fa


def test_stock_brief_names_the_niche_and_its_roles(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    b = fa._tm_stock_topic_brief("Accounting & CPA Firms", "CPA Firms")
    assert b.startswith("CPA Firms")
    assert "bookkeeper" in b.lower() or "staff accountant" in b.lower()
    assert "AI" in b and "not salesy" in b
    assert len(b) <= 600


def test_stock_brief_falls_back_to_the_sector_then_general(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    assert fa._tm_stock_topic_brief("Logistics & Freight", "").startswith(
        "Logistics & Freight")
    g = fa._tm_stock_topic_brief("", "")
    assert g and "executive assistant" in g.lower()


def test_stock_brief_stays_generic_off_thrivemodal(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    b = fa._tm_stock_topic_brief("Accounting & CPA Firms", "CPA Firms")
    assert b.startswith("CPA Firms") and "executive assistant" in b.lower()


def test_prompt_carries_name_sector_niche_and_asks_for_a_short_brief():
    p = fa._tm_topic_brief_prompt("AI Didn't Replace Human Interaction",
                                  "Accounting & CPA Firms", "CPA Firms",
                                  "Nationwide")
    assert "AI Didn't Replace Human Interaction" in p
    assert "CPA Firms" in p and "Accounting & CPA Firms" in p
    assert "<newsletter>" in p          # user text goes in as data
    assert "no bullets" in p.lower() and "75 words" in p
    assert "CPA firms win." in p        # Mike's own brief is the model


def test_draft_returns_the_model_text_trimmed_and_capped(monkeypatch):
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "k")
    long = "CPA firms win. " * 80
    reply = types.SimpleNamespace(content=[types.SimpleNamespace(text=long)])
    monkeypatch.setattr(fa, "_claude_create_with_retry",
                        lambda client, **kw: reply)
    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key: object())
    out = fa._tm_draft_topic_brief("N", "Accounting & CPA Firms", "CPA Firms", "")
    assert out.startswith("CPA firms win.") and len(out) <= 600


def test_draft_falls_back_to_the_stock_brief_on_failure(monkeypatch):
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key: object())

    def boom(client, **kw):
        raise RuntimeError("down")
    monkeypatch.setattr(fa, "_claude_create_with_retry", boom)
    out = fa._tm_draft_topic_brief("N", "Accounting & CPA Firms", "CPA Firms", "")
    assert out == fa._tm_stock_topic_brief("Accounting & CPA Firms", "CPA Firms")


def test_draft_without_a_key_never_calls_the_model(monkeypatch):
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    called = []
    monkeypatch.setattr(fa, "_claude_create_with_retry",
                        lambda *a, **k: called.append(1))
    out = fa._tm_draft_topic_brief("N", "Law Firms", "", "")
    assert not called and out == fa._tm_stock_topic_brief("Law Firms", "")


def test_both_dialogs_wire_the_autodraft():
    create = inspect.getsource(fa._create_newsletter_dialog)
    assert "_nl_topic_field(" in create and "ctx_fn=" in create
    assert "watch=" in create               # sector / niche / name changes redraft
    settings = inspect.getsource(fa._edit_newsletter_settings_dialog)
    assert "_nl_topic_field(" in settings and "ctx_fn=" in settings
    field = inspect.getsource(fa._nl_topic_field)
    assert "run_in_executor" in field       # never a bare thread (0f8b435)
    assert "Redraft" in field
    assert '"blur"' in field and "on_value_change" in field
    # A saved topic opened in Settings is the user's own text, never redrafted.
    assert '"mine": ""' in field

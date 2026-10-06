import types

import ai_prompts


def test_saved_style_names_sorted_deduped(monkeypatch):
    fake = types.SimpleNamespace(_load_my_campaign_styles=lambda: [
        {"name": "zeta"}, {"name": "Alpha"}, {"name": "zeta"}, {"name": ""},
        {}, None])
    monkeypatch.setattr(ai_prompts, "_ff", lambda: fake)
    assert ai_prompts._saved_style_names() == ["Alpha", "zeta"]


def test_saved_style_names_survives_loader_error(monkeypatch):
    def boom():
        raise RuntimeError
    monkeypatch.setattr(ai_prompts, "_ff", lambda: types.SimpleNamespace(
        _load_my_campaign_styles=boom))
    assert ai_prompts._saved_style_names() == []

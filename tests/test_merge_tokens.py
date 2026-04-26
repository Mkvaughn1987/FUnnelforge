"""C7: unresolved merge tokens must hard-fail (not leak to recipient)."""
import pytest


def test_merge_tokens_resolves_known():
    import funnelforge_core as ff
    out = ff.merge_tokens("Hi {FirstName}!", {"FirstName": "Sam"})
    assert out == "Hi Sam!"


def test_merge_tokens_raises_on_unknown():
    import funnelforge_core as ff
    with pytest.raises(ValueError) as ei:
        ff.merge_tokens("Hi {FirstNae}!", {"FirstName": "Sam"})
    msg = str(ei.value)
    assert "FirstNae" in msg
    assert "unresolved" in msg.lower() or "unknown" in msg.lower()


def test_merge_tokens_ignores_non_token_braces():
    """Curly braces around code/JSON-looking content shouldn't trigger
    a hard-fail. Only patterns that look like a {Identifier} count."""
    import funnelforge_core as ff
    # JSON-ish snippet with spaces, colons, quotes — not a token shape
    out = ff.merge_tokens('{"key": "val"} and {FirstName}', {"FirstName": "X"})
    assert out == '{"key": "val"} and X'

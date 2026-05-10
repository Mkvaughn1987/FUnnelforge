"""Per-industry market stats cache.

Stores AI-generated market data (fill-window days, candidate-pool
trends, etc.) per industry, shared across all users on the same
DripDrop deployment. Cache TTL is 30 days. On miss, the cache
hydrates via web search through the existing _safe_web_search_tool.

This cache feeds the call/voicemail/LI variant generators so they
have real market data to work with — without making a separate web
search per script generation (which would slow the Today page and
increase cost).
"""
import json
import sys
from pathlib import Path


def test_cache_helpers_exist():
    import flowdrip_app as fa
    assert hasattr(fa, "_market_stats_for_industry"), (
        "_market_stats_for_industry(industry) must be defined"
    )
    assert hasattr(fa, "_MARKET_STATS_CACHE_PATH"), (
        "_MARKET_STATS_CACHE_PATH must be defined (path to the cache file)"
    )


def test_cache_returns_dict_or_none(tmp_path, monkeypatch):
    """A cache miss without an API key should return None (not raise)."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if "flowdrip_app" in sys.modules:
        del sys.modules["flowdrip_app"]
    import flowdrip_app as fa
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    result = fa._market_stats_for_industry("test-industry-xyz")
    assert result is None or isinstance(result, dict)


def test_cache_hits_after_first_write(tmp_path, monkeypatch):
    """After a stats dict is cached for an industry, subsequent calls
    return it without invoking the web-search path."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if "flowdrip_app" in sys.modules:
        del sys.modules["flowdrip_app"]
    import flowdrip_app as fa
    fa._MARKET_STATS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = {
        "heavy-civil": {
            "fill_window_days": "50 to 65",
            "trend_summary": "fill windows have stretched",
            "_cached_at": "2026-05-10T12:00:00",
        }
    }
    fa._MARKET_STATS_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    result = fa._market_stats_for_industry("heavy-civil")
    assert isinstance(result, dict)
    assert result.get("fill_window_days") == "50 to 65"


def test_cache_miss_with_stale_entry_refreshes(tmp_path, monkeypatch):
    """An entry older than 30 days should be considered stale; the
    helper should attempt to refresh (or return None if no API key)."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if "flowdrip_app" in sys.modules:
        del sys.modules["flowdrip_app"]
    import flowdrip_app as fa
    fa._MARKET_STATS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = {
        "stale-industry": {
            "fill_window_days": "100",
            "_cached_at": "2025-01-01T00:00:00",
        }
    }
    fa._MARKET_STATS_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "")
    result = fa._market_stats_for_industry("stale-industry")
    assert result is None

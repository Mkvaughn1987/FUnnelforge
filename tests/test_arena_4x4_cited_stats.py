"""Live cited market-stats helpers for the Arena 4x4 campaign.

Spec: docs/superpowers/specs/2026-06-17-arena-4x4-live-cited-stats-design.md
Plan: docs/superpowers/plans/2026-06-17-arena-4x4-live-cited-stats.md
"""
import flowdrip_app as fa


# ── _cited_stats_prompt ────────────────────────────────────────────
def test_cited_stats_prompt_includes_role_location_industry():
    p = fa._cited_stats_prompt("Construction Foreman", "Phoenix, AZ",
                               "construction")
    assert "Construction Foreman" in p
    assert "Phoenix, AZ" in p
    assert "construction" in p


def test_cited_stats_prompt_requests_shape_and_forbids_fabrication():
    p = fa._cited_stats_prompt("Estimator", "Denver, CO", "construction")
    assert '"fact"' in p
    assert '"source"' in p
    # must tell the model not to invent numbers
    assert "fabricat" in p.lower() or "do not invent" in p.lower()


# ── _parse_cited_stats ─────────────────────────────────────────────
def test_parse_valid_stats():
    text = ('{"stats":[{"fact":"Unemployment in construction is 4.3%",'
            '"source":"BLS, 2026"}]}')
    out = fa._parse_cited_stats(text)
    assert out == [{"fact": "Unemployment in construction is 4.3%",
                    "source": "BLS, 2026"}]


def test_parse_drops_fact_without_source():
    text = ('{"stats":[{"fact":"Wages up 5%","source":""},'
            '{"fact":"Fill time is 47 days","source":"Indeed, 2026"}]}')
    out = fa._parse_cited_stats(text)
    assert out == [{"fact": "Fill time is 47 days",
                    "source": "Indeed, 2026"}]


def test_parse_drops_empty_fact():
    text = '{"stats":[{"fact":"   ","source":"BLS, 2026"}]}'
    assert fa._parse_cited_stats(text) == []


def test_parse_handles_code_fences():
    text = ('```json\n{"stats":[{"fact":"Base $130K","source":'
            '"Payscale, 2026"}]}\n```')
    out = fa._parse_cited_stats(text)
    assert out == [{"fact": "Base $130K", "source": "Payscale, 2026"}]


def test_parse_junk_returns_empty_list():
    assert fa._parse_cited_stats("no json here") == []
    assert fa._parse_cited_stats("") == []
    assert fa._parse_cited_stats(None) == []


# ── _format_cited_stats_block ──────────────────────────────────────
def test_format_block_non_empty_lists_facts_and_sources():
    stats = [{"fact": "Fill time is 47 days", "source": "Indeed, 2026"},
             {"fact": "Base $130K to $150K", "source": "Payscale, 2026"}]
    block = fa._format_cited_stats_block(stats)
    assert "Fill time is 47 days" in block
    assert "Indeed, 2026" in block
    assert "Base $130K to $150K" in block
    assert "Payscale, 2026" in block
    assert "ONLY these" in block
    assert "Email 2" in block and "Email 4" in block


def test_format_block_empty_forbids_numbers():
    block = fa._format_cited_stats_block([])
    assert "no specific" in block.lower() or "no numbers" in block.lower()
    assert "Source:" not in block


# ── allowlist ──────────────────────────────────────────────────────
def test_payscale_in_web_search_allowlist():
    assert "payscale.com" in fa._WEB_SEARCH_DOMAINS

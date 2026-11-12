"""Connector instructions (2026-11-12): campaigns are offered as a numbered
multiple-choice menu, built as drafts, and launched only on the user's yes;
named Pipeline candidates work on every template."""
import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MCP = (_ROOT / "mcp_server/dripdrop_mcp.py").read_text(encoding="utf-8")


def _instructions():
    for n in ast.parse(_MCP).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "DD_INSTRUCTIONS":
            return ast.literal_eval(n.value)
    raise AssertionError("DD_INSTRUCTIONS missing")


def test_server_passes_instructions():
    assert "instructions=DD_INSTRUCTIONS" in _MCP


def test_instructions_offer_a_numbered_menu_then_draft_then_confirm():
    t = _instructions()
    for must in ("numbered multiple-choice menu", "campaign_types",
                 "my_campaign_styles", "Custom - your own wording",
                 "spec.draft=true", "send_preview", "confirm=true",
                 "SENDS REAL EMAIL", "_pool_id"):
        assert must in t, must
    assert t.index("multiple-choice") < t.index("spec.draft=true") < t.index("action='launch'")


def test_candidates_not_limited_to_two_templates():
    assert "used by the fivebythree" not in _MCP
    assert "every template accepts them" in _MCP


def test_campaign_types_route_returns_length():
    src = (_ROOT / "flowdrip_app.py").read_text(encoding="utf-8")
    i = src.index('@app.get("/api/v1/campaign_types")')
    assert '"length": t[2]' in src[i:i + 2000]

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
    assert t.index("multiple-choice") < t.index("5. Always create") < t.index("6. Launch only")


def test_candidates_not_limited_to_two_templates():
    assert "used by the fivebythree" not in _MCP
    assert "every template accepts them" in _MCP


def test_campaign_types_route_returns_length():
    src = (_ROOT / "flowdrip_app.py").read_text(encoding="utf-8")
    i = src.index('@app.get("/api/v1/campaign_types")')
    assert '"length": t[2]' in src[i:i + 2000]


def test_instructions_offer_a_contacts_menu_and_skip_check():
    t = _instructions()
    for must in ("Who should this go to?", "saved contact lists",
                 "import_contacts", "sales_contacts action='search'",
                 "zoominfo_drop", "Decide later", "skip_check",
                 "already_worked"):
        assert must in t, must
    assert t.index("Who should this go to?") < t.index("spec.draft=true")


def test_launch_and_add_report_teammate_skips():
    src = (_ROOT / "flowdrip_app.py").read_text(encoding="utf-8")
    assert "def _dda_team_skip(" in src
    i = src.index("async def _dda_action_launch(")
    assert "_dda_team_skip(camp, contacts, owner)" in src[i:i + 4000]
    j = src.index('@app.post("/api/v1/dd/campaigns/contacts")')
    assert "_dda_team_skip(camp, contacts, owner)" in src[j:j + 6000]

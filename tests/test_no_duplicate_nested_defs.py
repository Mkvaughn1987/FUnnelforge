"""Regression 2026-05-01: clicking 'A Market' on Step 2 of the AI
Campaign Builder did nothing because two nested defs in p_ai_campaign
shared the name `_set_mode` — Step 2's target-mode toggle and Step 3's
candidate-source picker. Python late-binds free variables in lambdas,
so click handlers on Step 2 cards silently dispatched to Step 3's
helper, mutating aicb_cand_source instead of aicb_target_mode.

This is a static check: walk the AST of `p_ai_campaign` (and any other
known mega-page-render function) and assert no two nested function
definitions at the SAME nesting level share a name. Catches the bug
class without exhaustively testing every click handler."""
import ast
import pathlib


def _gather_function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found in source")


def _scope_def_counts(fn_node: ast.FunctionDef) -> dict:
    """Count function definitions in fn_node's lexical scope: walk its
    body and recurse through control-flow blocks (If/For/While/With/Try)
    but DO NOT cross into nested FunctionDef/Lambda — those are
    separate scopes and same-named defs in them don't collide.

    Returns a dict {name: count} for any name defined more than once
    in fn_node's own scope (which IS where Python's late-binding bug
    bites lambdas)."""
    counts: dict = {}

    def _visit(body):
        for node in body:
            if isinstance(node, ast.FunctionDef):
                counts[node.name] = counts.get(node.name, 0) + 1
                # Don't recurse — node has its own scope.
            elif isinstance(node, ast.AsyncFunctionDef):
                counts[node.name] = counts.get(node.name, 0) + 1
            elif isinstance(node, (ast.If, ast.For, ast.While)):
                _visit(node.body)
                _visit(node.orelse)
            elif isinstance(node, ast.With):
                _visit(node.body)
            elif isinstance(node, ast.Try):
                _visit(node.body)
                _visit(node.orelse)
                _visit(node.finalbody)
                for h in node.handlers:
                    _visit(h.body)

    _visit(fn_node.body)
    return {k: v for k, v in counts.items() if v > 1}


def _duplicate_def_names(fn_node: ast.FunctionDef) -> dict:
    return _scope_def_counts(fn_node)


def test_p_ai_campaign_has_no_dup_nested_defs():
    """p_ai_campaign is one giant render fn (~2k lines). Any two nested
    `def`s with the same name will silently shadow each other inside
    lambda click handlers. Real outage 2026-05-01: _set_mode collision
    between Step 2's target-mode toggle and Step 3's candidate-mode
    picker made 'A Market' unclickable on Step 2."""
    src_path = pathlib.Path(__file__).resolve().parent.parent / "flowdrip_app.py"
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    fn = _gather_function_node(tree, "p_ai_campaign")
    dups = _duplicate_def_names(fn)
    assert not dups, (
        "Duplicate nested function names inside p_ai_campaign — Python "
        "late-binds free variables in lambdas, so click handlers will "
        "silently misroute to whichever def was evaluated last. "
        f"Offenders (name: count): {dups}\n"
        "Fix: rename the helpers to make their target-state explicit "
        "(e.g. _set_target_mode vs _set_cand_mode)."
    )

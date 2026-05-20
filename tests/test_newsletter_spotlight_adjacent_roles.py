"""The newsletter spotlight prompt builder must inject the campaign's
target roles, sector adjacency hints, and the manager+ / tech-role
seniority rules — so Arena Direct Hire newsletters stop surfacing
trades-level or junior IC roles in candidate spotlights.

Spec: docs/superpowers/specs/2026-05-20-newsletter-spotlight-adjacent-roles-design.md
"""
import flowdrip_app as fa


def test_block_empty_when_n_is_zero():
    """When spotlight count is 0, the helper returns ('', '') — caller
    appends nothing to the prompt. Mirrors the current behavior."""
    instr, schema = fa._spotlight_prompt_block(
        sector="construction", n=0, target_roles=[])
    assert instr == ""
    assert schema == ""


def test_block_includes_manager_plus_rule():
    """Every non-empty block must carry the seniority guardrail."""
    instr, _ = fa._spotlight_prompt_block(
        sector="construction", n=3, target_roles=[])
    assert "manager-level or above" in instr.lower()
    # Must explicitly forbid the categories Arena does not place
    forbidden_terms = ("trades", "field/labor", "junior", "entry-level")
    for term in forbidden_terms:
        assert term in instr.lower(), f"missing seniority exclusion: {term}"


def test_block_includes_tech_role_rule():
    """Spec requires at least one tech-flavored manager+ role per issue."""
    instr, _ = fa._spotlight_prompt_block(
        sector="architecture", n=3, target_roles=[])
    assert "tech-flavored" in instr.lower() or "tech flavored" in instr.lower()
    assert "at least one" in instr.lower()


def test_block_lists_sector_adjacency_when_no_target_roles():
    """When the campaign has no target roles, the adjacency list is the
    only role guidance — it MUST appear in the prompt."""
    instr, _ = fa._spotlight_prompt_block(
        sector="architecture", n=6, target_roles=[])
    # Architecture's adjacency list (per spec) includes these
    assert "BIM Manager" in instr
    assert "Project Architect" in instr


def test_block_includes_target_roles_when_present():
    """If the campaign has target roles, they MUST appear verbatim in
    the prompt — that's the whole point of using them."""
    target = ["Senior Estimator", "VP Operations", "Director of Preconstruction"]
    instr, _ = fa._spotlight_prompt_block(
        sector="construction", n=6, target_roles=target)
    for role in target:
        assert role in instr, f"target role missing from prompt: {role}"


def test_block_handles_unknown_sector_with_generic_adjacency():
    """For a sector not in the map, fall back to a generic manager+
    role list so the prompt isn't empty."""
    instr, _ = fa._spotlight_prompt_block(
        sector="basket_weaving", n=3, target_roles=[])
    # Generic fallback titles, per spec
    assert "Director" in instr
    assert "VP" in instr or "Vice President" in instr
    # Seniority rule still applies
    assert "manager-level or above" in instr.lower()


def test_block_selection_rule_text_present():
    """The AI is told how to mix target roles vs adjacency. The exact
    wording can evolve; what we lock in is that BOTH 'target' and
    'adjacent' appear so the AI knows the split exists."""
    instr, _ = fa._spotlight_prompt_block(
        sector="manufacturing", n=6,
        target_roles=["Plant Manager", "Quality Manager", "Production Manager"])
    instr_l = instr.lower()
    assert "target role" in instr_l
    assert "adjacent" in instr_l


def test_schema_block_unchanged_shape():
    """We're NOT changing the JSON output schema — spotlights still have
    name, title, location, salary_ask, bullets. Guard against accidental
    drift while refactoring."""
    _, schema = fa._spotlight_prompt_block(
        sector="construction", n=3, target_roles=[])
    for key in ('"name"', '"title"', '"location"', '"salary_ask"', '"bullets"'):
        assert key in schema, f"schema missing key: {key}"


def test_adjacency_map_covers_every_industry():
    """Every key in AICB_INDUSTRIES must have an entry in the adjacency
    map — otherwise users with that industry get the generic fallback
    silently. Spec explicitly lists 8 industries; map must include them."""
    for industry_key in fa.AICB_INDUSTRIES.keys():
        assert industry_key in fa._SPOTLIGHT_ADJACENT_ROLES, (
            f"AICB industry '{industry_key}' missing from adjacency map")


def test_adjacency_lists_are_all_manager_plus():
    """Every role in every adjacency list must clear the manager+ bar.
    Reject titles that contain obvious below-manager words. This is a
    defensive check on our hand-curated map — easy to slip a Drafter
    or Operator in by accident."""
    forbidden_fragments = (
        "intern", "junior", "drafter", "operator", "machinist",
        "field tech", "foreman", "laborer", "apprentice", "entry",
    )
    for sector, roles in fa._SPOTLIGHT_ADJACENT_ROLES.items():
        for role in roles:
            role_l = role.lower()
            for bad in forbidden_fragments:
                assert bad not in role_l, (
                    f"adjacency for '{sector}' contains below-manager "
                    f"role '{role}' (matched '{bad}')")

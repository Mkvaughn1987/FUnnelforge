"""ThriveModal Phase 4 — the vertical knowledge pack.

Phase 0 shipped six ThriveModal campaign types. They are objective-shaped
(start a conversation, follow up a meeting, re-engage) and deliberately
vertical-blind: each one tells the model to work "from the BRIEF and the
playbook's target industries". That is why a construction campaign and a
healthcare campaign come out of the model sounding like the same campaign
with the nouns swapped, and why the model invents AEC specifics when it needs
them.

Phase 4 fixes that WITHOUT adding campaign types. It adds one orthogonal
layer: a per-vertical knowledge block, resolved from the industry the wizard
already collects, appended to the ThriveModal playbook that governs the
campaign. Two verticals x six objectives, no new types, no combinatorial
explosion.

What the tests pin, and why each one is load-bearing:

  * Group A — resolution. `_tm_vertical_for` is a TOTAL function: every
    possible industry string resolves to a vertical that actually has a block,
    because a campaign that silently got no vertical layer is exactly the
    vertical-blind campaign Phase 4 exists to remove. The one trap worth a
    test of its own is "engineering": an AEC firm and a software company both
    use the word, and sending a software CTO a takeoff-and-submittals email is
    worse than sending them a generic one.

  * Group B — the blocks themselves. This copy is written straight into the
    generation prompt, so anything in it can end up in a real prospect's
    inbox. The blocks therefore carry no price, no percentage, no statistic
    and no named customer, and they must not contradict the standing model
    (ThriveModal recruits and places; it is not the employer of record).
    They also have to say what stays ONSHORE, because the fastest way to lose
    an AEC buyer is to sound like you are offering to offshore their
    superintendent.

  * Group C — injection. The vertical rides on the PLAYBOOK, not on the
    workspace, so an Arena sequence stays byte-identical to what it was
    before Phase 4 even in a ThriveModal workspace.

  * Group D/E — wiring and Arena isolation, same shape as Phases 2 and 3.

Written against the spec, not the implementation. Every test in Groups A-D
was red before the Phase 4 splice.
"""
import ast
import re

import pytest


# NEVER import flowdrip_app at module level (see tests/conftest.py).

@pytest.fixture
def fa(isolated_appdata, with_user, monkeypatch):
    """flowdrip_app with the instance playbook lock cleared, so playbook
    resolution is decided by the campaign type like a normal shared box."""
    import flowdrip_app as _fa
    monkeypatch.setattr(_fa, "_LOCKED_PLAYBOOK", "")
    return _fa


# The headings every vertical block carries. A block missing one of these is
# missing the part of the answer the buyer actually asks about.
_REQUIRED_HEADINGS = (
    "ROLES ROUTINELY PLACED OFFSHORE:",
    "WHAT STAYS ONSHORE, ALWAYS:",
    "WHO ACTUALLY BUYS:",
    "WHAT THIS BUYER IS ACTUALLY DEALING WITH:",
    "HOW TO TALK TO THEM:",
)


# ═══════════════════════════════════════════════════════════════════════════
#  Group A — resolving an industry to a vertical
# ═══════════════════════════════════════════════════════════════════════════

def test_01_the_registry_is_ordered_and_has_the_two_shipped_verticals(fa):
    keys = [k for k, _label, _blurb in fa._TM_VERTICALS]
    assert keys == ["construction_aec", "general_offshore"], (
        "Phase 4 ships exactly two verticals, AEC first and general last; "
        "general_offshore is the fallback and must sort last so a future "
        "vertical is added above it, not after it")
    for key, label, blurb in fa._TM_VERTICALS:
        assert label.strip(), f"{key} has no label"
        assert blurb.strip(), f"{key} has no blurb"


def test_02_no_industry_resolves_to_the_general_vertical(fa):
    """A campaign built without an industry still gets a knowledge layer.
    Returning "" here would put us back to vertical-blind generation."""
    for empty in ("", "   ", None):
        assert fa._tm_vertical_for(empty) == "general_offshore"


def test_03_construction_architecture_and_engineering_all_resolve_to_aec(fa):
    for text in ("Construction", "Architecture", "Engineering"):
        assert fa._tm_vertical_for(text) == "construction_aec", text


def test_04_resolution_ignores_case_and_surrounding_words(fa):
    for text in ("CONSTRUCTION", "commercial construction firms in Texas",
                 "civil engineering", "general contractor", "AEC"):
        assert fa._tm_vertical_for(text) == "construction_aec", text


def test_05_software_engineering_is_not_construction(fa):
    """The single most expensive false positive available here. "Engineering"
    is an AEC industry label AND half of every technology niche string."""
    for text in ("software engineering", "Technology software engineering",
                 "sales engineering", "data engineering",
                 "engineering manager", "platform engineering"):
        assert fa._tm_vertical_for(text) == "general_offshore", text


def test_06_an_explicit_aec_term_survives_a_software_word_in_the_same_string(fa):
    """A construction-tech company is still sold the AEC way."""
    assert fa._tm_vertical_for(
        "software engineering for general contractors") == "construction_aec"


def test_07_unrelated_industries_resolve_to_the_general_vertical(fa):
    for text in ("Healthcare", "Legal", "Retail & Consumer", "Education",
                 "Financial Services", "Hospitality & Food Service"):
        assert fa._tm_vertical_for(text) == "general_offshore", text


def test_08_a_company_name_is_enough_of_a_signal(fa):
    """The builder feeds company + industry + niche in together, so a firm
    whose industry was never picked still lands in the right vertical."""
    assert fa._tm_vertical_for("Turner Construction Co") == "construction_aec"


def test_09_every_shipped_industry_label_resolves_to_a_real_block(fa):
    """`_tm_vertical_for` is total. Every label the wizard can offer must map
    to a key that `_tm_vertical_block` actually has copy for."""
    labels = [(meta or {}).get("label", "")
              for meta in fa.AICB_INDUSTRIES.values()]
    assert labels, "no industry labels found to check"
    for label in labels:
        key = fa._tm_vertical_for(label)
        assert key in fa._TM_VERTICAL_BLOCKS, f"{label!r} -> {key!r}"
        assert fa._tm_vertical_block(key).strip(), f"{label!r} -> empty block"


def test_10_resolution_never_raises_on_junk(fa):
    for junk in (123, [], {}, object(), "\x00\n\t", "a" * 5000):
        assert fa._tm_vertical_for(junk) in fa._TM_VERTICAL_BLOCKS


# ═══════════════════════════════════════════════════════════════════════════
#  Group B — the knowledge blocks
# ═══════════════════════════════════════════════════════════════════════════

def test_11_an_unknown_key_returns_nothing_rather_than_a_default(fa):
    """Resolution picks the fallback; lookup must not. A typo'd key silently
    serving the general block would hide the typo forever."""
    for key in ("", None, "nope", "CONSTRUCTION_AEC", 7):
        assert fa._tm_vertical_block(key) == ""


def test_12_every_registered_vertical_has_a_block(fa):
    for key, _label, _blurb in fa._TM_VERTICALS:
        assert fa._tm_vertical_block(key).strip(), key


def test_13_every_block_carries_the_same_five_headings(fa):
    for key, _label, _blurb in fa._TM_VERTICALS:
        block = fa._tm_vertical_block(key)
        for heading in _REQUIRED_HEADINGS:
            assert heading in block, f"{key} is missing {heading!r}"


def test_14_every_block_names_the_vertical_it_is(fa):
    for key, label, _blurb in fa._TM_VERTICALS:
        block = fa._tm_vertical_block(key)
        assert block.lstrip().startswith("VERTICAL KNOWLEDGE:"), key
        assert label in block, f"{key} does not name itself"


def test_15_no_block_quotes_a_number_a_price_or_a_percentage(fa):
    """This copy is prompt text the model will happily paraphrase into an
    email. An invented saving or placement statistic in here becomes a written
    claim to a real prospect, which is the one thing the playbook forbids."""
    for key, _label, _blurb in fa._TM_VERTICALS:
        block = fa._tm_vertical_block(key)
        assert "%" not in block, f"{key} contains a percentage"
        assert "$" not in block, f"{key} contains a price"
        digits = re.findall(r"\d", block)
        assert not digits, f"{key} contains digits {digits!r}"


def test_16_no_block_promises_or_guarantees_anything(fa):
    banned = ("guarantee", "guaranteed", "we promise", "risk free",
              "case study", "our client ", "testimonial")
    for key, _label, _blurb in fa._TM_VERTICALS:
        low = fa._tm_vertical_block(key).lower()
        for word in banned:
            assert word not in low, f"{key} contains {word!r}"


def test_17_no_block_contradicts_the_staffing_model(fa):
    """ThriveModal recruits and places dedicated people the client selects.
    It is not the employer of record, the payroll provider or the compliance
    provider, and a vertical block must never imply otherwise."""
    banned = ("employer of record", " eor ", "we payroll", "payroll provider",
              "we employ them", "peo ", "benefits administration")
    for key, _label, _blurb in fa._TM_VERTICALS:
        low = " " + fa._tm_vertical_block(key).lower() + " "
        for word in banned:
            assert word not in low, f"{key} contains {word!r}"


def test_18_no_block_uses_dashes_the_house_style_bans(fa):
    """Same rule the playbook tail puts on generated copy. Leaking an em dash
    in through the prompt is how the model learns it is allowed."""
    for key, _label, _blurb in fa._TM_VERTICALS:
        block = fa._tm_vertical_block(key)
        assert "—" not in block, f"{key} contains an em dash"
        assert "–" not in block, f"{key} contains an en dash"
        assert "--" not in block, f"{key} contains a double hyphen"


def test_19_the_aec_block_knows_the_actual_work(fa):
    """Specificity is the whole point of the feature. If this block does not
    contain the words an AEC buyer uses every day, the layer bought nothing."""
    low = fa._tm_vertical_block("construction_aec").lower()
    for term in ("submittal", "rfi", "takeoff", "estimat", "pay application",
                 "drafter", "job cost", "look ahead"):
        assert term in low, f"AEC block never mentions {term!r}"


def test_20_the_aec_block_names_titles_that_can_actually_sign(fa):
    low = fa._tm_vertical_block("construction_aec").lower()
    hits = [t for t in ("owner", "president", "vp of operations", "controller",
                        "cfo", "director of estimating", "principal")
            if t in low]
    assert len(hits) >= 4, f"AEC block names too few buying titles: {hits}"


def test_21_the_aec_block_protects_the_onshore_roles(fa):
    """The reflex objection in this vertical is "you cannot offshore my
    superintendent". The block has to concede that before the model has to
    improvise an answer to it."""
    low = fa._tm_vertical_block("construction_aec").lower()
    assert "superintendent" in low
    assert "licen" in low, "block never mentions licensure"
    assert "jobsite" in low or "job site" in low


def test_22_the_general_block_stays_general(fa):
    """The fallback must not quietly be a second AEC block, or every
    non-AEC campaign gets construction vocabulary it cannot support."""
    low = fa._tm_vertical_block("general_offshore").lower()
    for term in ("submittal", "takeoff", "superintendent", "jobsite"):
        assert term not in low, f"general block leaks AEC term {term!r}"


def test_23_the_blocks_are_context_not_copy(fa):
    """A block the model treats as an email template produces identical
    emails across every prospect in the vertical."""
    for key, _label, _blurb in fa._TM_VERTICALS:
        low = fa._tm_vertical_block(key).lower()
        assert "not copy to paste" in low or "do not paste" in low, key


# ═══════════════════════════════════════════════════════════════════════════
#  Group C — injection into the playbook that governs the campaign
# ═══════════════════════════════════════════════════════════════════════════

def _tm_type(fa):
    return sorted(fa._TM_TYPE_KEYS)[0]


def _arena_type(fa):
    return sorted(fa._SALES_TYPE_KEYS)[0]


def test_24_a_thrivemodal_campaign_gets_the_vertical_for_its_industry(fa):
    text = fa._active_playbook_text(_tm_type(fa), {}, industry="Construction")
    assert fa._tm_vertical_block("construction_aec") in text


def test_25_a_thrivemodal_campaign_with_no_industry_gets_the_general_pack(fa):
    text = fa._active_playbook_text(_tm_type(fa), {}, industry="")
    assert fa._tm_vertical_block("general_offshore") in text
    assert fa._tm_vertical_block("construction_aec") not in text


def test_26_exactly_one_vertical_is_ever_injected(fa):
    text = fa._active_playbook_text(_tm_type(fa), {}, industry="Construction")
    assert text.count("VERTICAL KNOWLEDGE:") == 1


def test_27_the_playbook_itself_is_untouched_and_comes_first(fa):
    """Additive only. The vertical layer appends; it may not rewrite, reorder
    or drop a single section of the approved playbook."""
    base = fa._thrivemodal_playbook_text({})
    text = fa._active_playbook_text(_tm_type(fa), {}, industry="Construction")
    assert text.startswith(base)
    assert text[len(base):].strip(), "nothing was actually appended"


def test_28_the_industry_argument_is_optional(fa):
    """Every existing caller passes two arguments. Phase 4 must not break
    them, and an un-passed industry still resolves to the general pack."""
    text = fa._active_playbook_text(_tm_type(fa), {})
    assert fa._tm_vertical_block("general_offshore") in text


def test_29_an_arena_sequence_is_byte_identical_to_before_phase_4(fa):
    """The load-bearing isolation test. An Arena type carries the Arena voice
    even in a ThriveModal workspace, and Arena has no vertical layer."""
    for industry in ("Construction", "Healthcare", ""):
        text = fa._active_playbook_text(_arena_type(fa), {}, industry=industry)
        assert text == fa._DRIPDROP_PLAYBOOK, industry


def test_30_a_locked_arena_instance_never_sees_a_vertical(fa, monkeypatch):
    monkeypatch.setattr(fa, "_LOCKED_PLAYBOOK", fa.PLAYBOOK_ARENA)
    text = fa._active_playbook_text(_tm_type(fa), {}, industry="Construction")
    assert text == fa._DRIPDROP_PLAYBOOK
    assert "VERTICAL KNOWLEDGE:" not in text


def test_31_a_locked_thrivemodal_instance_gets_the_vertical(fa, monkeypatch):
    monkeypatch.setattr(fa, "_LOCKED_PLAYBOOK", fa.PLAYBOOK_THRIVEMODAL)
    text = fa._active_playbook_text(_arena_type(fa), {}, industry="Construction")
    assert fa._tm_vertical_block("construction_aec") in text


def test_32_the_workspace_fallback_also_gets_the_vertical(fa, monkeypatch):
    """A playbook-neutral type (byos, a saved style) in a ThriveModal
    workspace resolves through the gate, and must pick up the layer too."""
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    neutral = sorted(fa._PLAYBOOK_NEUTRAL_TYPE_KEYS)[0]
    text = fa._active_playbook_text(neutral, {}, industry="Construction")
    assert fa._tm_vertical_block("construction_aec") in text


def test_33_every_thrivemodal_type_gets_a_vertical(fa):
    """Two verticals x six objectives. No objective may be left blind."""
    for key in sorted(fa._TM_TYPE_KEYS):
        text = fa._active_playbook_text(key, {}, industry="Architecture")
        assert fa._tm_vertical_block("construction_aec") in text, key


# ═══════════════════════════════════════════════════════════════════════════
#  Group D — the generation path actually passes an industry
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def app_tree():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent /
           "flowdrip_app.py").read_text(encoding="utf-8")
    return ast.parse(src)


def _top_level_functions(tree):
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _referenced_names(node):
    return ({n.id for n in ast.walk(node) if isinstance(n, ast.Name)} |
            {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)})


def test_34_the_builder_passes_an_industry_to_the_playbook(app_tree):
    """Without this the whole layer is dead code: every campaign would build
    with the general pack no matter what the wizard collected."""
    fn = _top_level_functions(app_tree)["_aicb_build_campaign_from_brief"]
    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)
             and n.func.id == "_active_playbook_text"]
    assert calls, "_active_playbook_text is no longer called from the builder"
    for call in calls:
        assert any(kw.arg == "industry" for kw in call.keywords), (
            "_active_playbook_text is called without industry=")


def test_35_the_playbook_signature_keeps_industry_last_with_a_default(app_tree):
    fn = _top_level_functions(app_tree)["_active_playbook_text"]
    args = [a.arg for a in fn.args.args]
    assert args[:2] == ["camp_type", "cfg"], (
        f"existing positional arguments moved: {args}")
    assert args[-1] == "industry", f"industry is not last: {args}"
    assert len(fn.args.defaults) == len(args), "industry has no default"


# ═══════════════════════════════════════════════════════════════════════════
#  Group E — Arena isolation and purity
# ═══════════════════════════════════════════════════════════════════════════

_TM_VERTICAL_NAMES = {"_tm_vertical_for", "_tm_vertical_block"}

# Reached only through `_active_playbook_text`, which checks the gate itself.
_VERTICAL_CHAIN_EXEMPT = _TM_VERTICAL_NAMES | {"_active_playbook_text"}


def test_36_every_caller_of_a_vertical_helper_also_checks_the_playbook(app_tree):
    offenders = []
    for name, node in _top_level_functions(app_tree).items():
        if name in _VERTICAL_CHAIN_EXEMPT:
            continue
        refs = _referenced_names(node)
        reached = refs & _TM_VERTICAL_NAMES
        if reached and not (refs & {"_is_thrivemodal", "_LOCKED_PLAYBOOK",
                                    "_workspace_playbook",
                                    "_active_playbook_text"}):
            offenders.append((name, sorted(reached)))
    assert offenders == [], (
        f"ungated vertical callers — Arena can reach these: {offenders}")


def test_37_the_playbook_resolver_still_checks_the_gate(app_tree):
    fn = _top_level_functions(app_tree)["_active_playbook_text"]
    refs = _referenced_names(fn)
    assert "_is_thrivemodal" in refs
    assert refs & _TM_VERTICAL_NAMES, (
        "_active_playbook_text never reaches the vertical layer")


def test_38_the_vertical_helpers_are_pure(app_tree):
    fns = _top_level_functions(app_tree)
    writers = {"save_campaign", "save_dnc", "save_config", "load_config",
               "_atomic_write_text", "_atomic_write_csv_text", "notify"}
    for name in sorted(_TM_VERTICAL_NAMES):
        assert name in fns, f"{name} is not defined at module level"
        node = fns[name]
        body = ast.dump(node)
        assert "'ui'" not in body, f"{name} builds UI; it must stay pure"
        hit = _referenced_names(node) & writers
        assert not hit, f"{name} is not pure: {sorted(hit)}"


def test_39_the_registry_and_the_blocks_agree(fa):
    """One source of truth. A vertical in the registry with no block is a
    campaign with no knowledge; a block with no registry entry is unreachable
    copy that will rot."""
    registry = {k for k, _l, _b in fa._TM_VERTICALS}
    assert registry == set(fa._TM_VERTICAL_BLOCKS), (
        f"registry {sorted(registry)} != blocks "
        f"{sorted(fa._TM_VERTICAL_BLOCKS)}")


def test_40_the_fallback_vertical_is_a_registered_vertical(fa):
    assert fa._TM_VERTICAL_GENERAL in fa._TM_VERTICAL_BLOCKS
    assert fa._tm_vertical_for("something nobody ships") == \
        fa._TM_VERTICAL_GENERAL

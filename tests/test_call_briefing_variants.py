"""Unit tests for call-briefing variant default selection (schema v6).

2026-07-16: the Market-Data Contrarian / Market-Insight variants were
dropped, leaving two of each, and the brief style became the default.

The pill rows default to index 0, and the generation prompts emit the
brief style first — so ordering alone would "work". `_default_variant_idx`
exists so that the intended default still wins if the model ever returns
the variants out of order, which would otherwise silently select the
project-anchored script instead.
"""
import flowdrip_app as fa


def _v(*styles):
    return [{"style": s, "label": s, "script": f"script for {s}"} for s in styles]


def test_picks_brief_when_first():
    """The normal case: prompts emit brief first, so index 0."""
    variants = _v("brief_diagnostic", "project_anchored")
    assert fa._default_variant_idx(variants, "brief_diagnostic") == 0


def test_picks_brief_when_model_reorders():
    """The reason this helper exists — order flipped, brief still wins."""
    variants = _v("project_anchored", "brief_diagnostic")
    assert fa._default_variant_idx(variants, "brief_diagnostic") == 1


def test_voicemail_styles_use_their_own_keys():
    """VM styles are namespaced separately from the opener styles."""
    variants = _v("vm_project_anchored", "vm_brief_direct")
    assert fa._default_variant_idx(variants, "vm_brief_direct") == 1


def test_falls_back_to_zero_when_style_absent():
    """Old/odd data without the preferred style still renders something."""
    variants = _v("legacy")
    assert fa._default_variant_idx(variants, "brief_diagnostic") == 0


def test_empty_and_none_are_safe():
    """Renderer guards on truthiness, but don't blow up regardless."""
    assert fa._default_variant_idx([], "brief_diagnostic") == 0
    assert fa._default_variant_idx(None, "brief_diagnostic") == 0


def test_ignores_malformed_entries():
    """A non-dict in the list must not raise — it's model output."""
    variants = ["junk", None, {"style": "brief_diagnostic"}]
    assert fa._default_variant_idx(variants, "brief_diagnostic") == 2


# ── _strip_cite_tags (pre-existing helper, reused by v6) ──────────────
# The web_search tool wraps sourced prose in <cite index="...">...</cite>.
# Observed live on the v6 company overview: without stripping, ui.label()
# escapes the markup and the recruiter reads tag soup on a call card.
# These pin the behavior v6 depends on; the helper predates this feature
# (around_town blurbs use it too), so don't loosen it without checking
# those callers.

def test_strips_cite_tags_keeping_inner_text():
    """The exact shape observed live from the AuST overview."""
    raw = '<cite index="1-2,1-3">AuST is a medical device firm.</cite>'
    assert fa._strip_cite_tags(raw) == "AuST is a medical device firm."


def test_strips_multiple_cites():
    raw = ('<cite index="1-2">First claim.</cite> '
           '<cite index="4-9,4-10">Second claim.</cite>')
    assert fa._strip_cite_tags(raw) == "First claim. Second claim."


def test_leaves_clean_text_untouched():
    assert fa._strip_cite_tags("Arlington, VA") == "Arlington, VA"


def test_strip_cite_passes_falsy_through():
    """Documents the existing contract: falsy in, falsy out (NOT "").

    The v6 call sites coerce with str(x or "") before calling precisely
    because this returns None unchanged rather than an empty string.
    """
    assert fa._strip_cite_tags("") == ""
    assert fa._strip_cite_tags(None) is None

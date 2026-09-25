"""Sidebar navigation layout (DRIPDROP_NAV_LAYOUT=sidebar) for inboxslide.

Source-grep / value-check style, like tests/test_light_mode_polish.py:
UI rendering needs a live NiceGUI client, so we assert the structural
markers that keep the layout switch honest. The key guarantee is that an
instance with the variable unset (Arena) keeps the classic chrome.
"""
import inspect


def test_default_layout_is_classic():
    """With DRIPDROP_NAV_LAYOUT unset the module must resolve to the
    classic layout, so Arena's navigation is unchanged."""
    import flowdrip_app as fa
    assert fa.NAV_LAYOUT == "classic"
    assert fa._SIDEBAR_LAYOUT is False


def test_unbuilt_destinations_have_no_page_and_are_skipped():
    """Sales Dashboard has no page and stays hidden. Outreach Analytics,
    AI Prompt and Saved Prompts are ThriveModal-only: None in the model,
    resolved by _tm_nav_page_key on that playbook. Everything else is a
    built page. The renderer still filters None rows (no empty pages)."""
    import flowdrip_app as fa
    by_label = {lbl: key for _sec, rows in fa.SIDEBAR_NAV for _ik, lbl, key in rows}
    for lbl in ("Sales Dashboard", "Outreach Analytics", "AI Prompt", "Saved Prompts"):
        assert lbl in by_label, f"{lbl} missing from SIDEBAR_NAV"
        assert by_label[lbl] is None, f"{lbl} must not be wired directly"
    for lbl in ("Overview", "My Day", "Replies", "Companies", "Contacts", "Pipeline",
                "Clients", "Campaigns", "Newsletters", "Sales Assets"):
        assert by_label.get(lbl), f"{lbl} must map to an existing page key"
    assert "Content Library" not in by_label, "Content Library is no longer a row"
    src = inspect.getsource(fa._sidebar_v2)
    assert "rows = [r for r in rows if r[2]]" in src
    assert "if not rows:" in src


def test_sections_are_home_sales_campaigns_content_performance():
    import flowdrip_app as fa
    assert [sec for sec, _rows in fa.SIDEBAR_NAV] == [
        "HOME", "SALES", "CAMPAIGNS", "CONTENT", "PERFORMANCE"]
    rows = dict(fa.SIDEBAR_NAV)
    assert [r[1] for r in rows["SALES"]] == ["Companies", "Contacts", "Pipeline", "Clients"]
    assert [r[1] for r in rows["CAMPAIGNS"]] == ["Campaigns", "Newsletters"]
    assert [r[1] for r in rows["CONTENT"]] == ["Sales Assets", "AI Prompt", "Saved Prompts"]


def test_wired_page_keys_exist_in_router():
    """Every non-None page key in the sidebar model, the settings
    sub-rows and the header/title maps must be a page the classic nav
    already knows about, so no route is invented."""
    import flowdrip_app as fa
    known = {k for _i, _l, k in fa.SALES_NAV} | {k for _i, _l, k in fa.EMAILS_NAV}
    # Pages the classic layout reaches through settings sub-rows rather
    # than a SALES_NAV tuple; all are routed in render_page.
    known |= {"admin", "start_seq", "create_camp", "drip", "dashboard",
              "signature", "timezone"}
    # Sidebar-only pages (no classic nav row) routed through sales_pages.
    known |= {"companies", "pipeline"}
    router = inspect.getsource(fa.render_page)
    for k in ("signature", "timezone"):
        assert f'elif page == "{k}":' in router
    assert 'elif page in ("companies", "pipeline"):' in router
    assert "import sales_pages as _spg" in router
    wired = {key for _sec, rows in fa.SIDEBAR_NAV for _ik, _lbl, key in rows if key}
    wired |= {key for _ik, _lbl, key in fa.SIDEBAR_SETTINGS}
    unknown = wired - known
    assert not unknown, f"sidebar wires page keys the app does not route: {unknown}"


def test_topbar_and_sidebar_switch_on_layout_flag():
    import flowdrip_app as fa
    tb = inspect.getsource(fa.topbar)
    sb = inspect.getsource(fa.sidebar)
    assert "if _SIDEBAR_LAYOUT:" in tb and "_page_header_v2(s, rf)" in tb
    assert "if _SIDEBAR_LAYOUT:" in sb and "_sidebar_v2(s, rf)" in sb
    # The switch is the first statement so the classic body is never
    # partially rendered on the sidebar layout.
    assert tb.split("\n")[1].strip() == "if _SIDEBAR_LAYOUT:"
    assert sb.split("\n")[1].strip() == "if _SIDEBAR_LAYOUT:"


def test_sidebar_css_is_scoped_and_injected():
    """The sidebar CSS is always injected; it must only target the new
    class names so the classic layout is unaffected, and the f-string
    must have rendered its braces."""
    import flowdrip_app as fa
    css = fa._sidebar_layout_css()
    assert ".fd-side{" in css and ".fd-ph{" in css
    assert "width:240px" in css
    assert "{{" not in css and "}}" not in css
    assert "var(--dd-" in css, "sidebar CSS must use the theme tokens"
    for line in css.split("\n"):
        line = line.strip()
        if not line or line.startswith(("/*", "@media", "}", ":root")):
            continue
        if "{" in line and not line.startswith("."):
            continue
        if line.startswith("."):
            assert line.startswith((".fd-side", ".fd-ws", ".fd-ph", ".fd-shell-side",
                                    ".fd-main")), f"unscoped rule: {line[:60]}"
    assert "{_sidebar_layout_css()}" in inspect.getsource(fa.inject_styles)


def test_onboarding_tour_selectors_survive():
    """The product tour targets these data-tour attributes; the sidebar
    layout must keep every one of them."""
    import flowdrip_app as fa
    src = inspect.getsource(fa._sidebar_v2)
    assert 'data-tour="nav-start_seq"' in src
    assert 'data-tour="avatar"' in src
    assert '"overview": "nav-dashboard"' in src
    assert '"contacts": "nav-contacts"' in src
    assert 'tour="nav-ai_settings"' in src


def test_admin_row_is_gated():
    import flowdrip_app as fa
    src = inspect.getsource(fa._sidebar_v2)
    assert "_is_admin(" in src, "Admin row must only render for authorized users"


def test_active_row_mapping_for_consolidated_pages():
    """Current + Saved campaigns collapse into one Campaigns row; the
    newsletter and sales-asset pages collapse into Content Library; the
    settings pages collapse into Settings."""
    import flowdrip_app as fa
    m = fa.SIDEBAR_PAGE_ROW
    assert m["seq_mgr"] == "campaigns"
    assert m["newsletters"] == "newsletters" and m["pdf_gen"] == "assets"
    assert m["companies"] == "companies" and m["pipeline"] == "pipeline"
    for k in ("ai_settings", "company_profile", "team_settings", "signature",
              "timezone", "dnc"):
        assert m[k] == "settings", k
    assert m["responses"] == "replies" and m["e_responses"] == "replies"
    src = inspect.getsource(fa._sidebar_active)
    assert '"saved"' in src and '"campaigns"' in src


def test_page_header_has_search_and_no_section_tabs():
    import flowdrip_app as fa
    src = inspect.getsource(fa._page_header_v2)
    # Campaigns' and Content Library's views are sidebar sub-rows now.
    for tab in ("Active", "Completed", "Saved", "Templates", "Sales Assets"):
        assert f'"{tab}"' not in src, f"header still has tab {tab}"
    assert "Do Not Contact" in src, "suppression management must stay one click away"
    assert "fd-ph-search" in src


def test_campaign_views_are_sidebar_subrows():
    import types
    import flowdrip_app as fa
    assert [r[1] for r in fa.SIDEBAR_CAMPAIGNS] == ["Active", "Completed", "Drafts", "Templates"]
    for ik, _lbl, _view in fa.SIDEBAR_CAMPAIGNS:
        assert ik in fa._SIDEBAR_ICONS, f"missing icon {ik}"
    src = inspect.getsource(fa._sidebar_v2)
    assert "SIDEBAR_CAMPAIGNS" in src and "_mgr_show_completed" in src

    def st(sp, tab="", done=False):
        return types.SimpleNamespace(hub="sales", sp=sp, ep="", _tab=tab,
                                     _mgr_show_completed=done)
    cases = [(st("seq_mgr"), "active"), (st("seq_mgr", done=True), "completed"),
             (st("start_seq", "saved"), "saved"), (st("start_seq"), "templates")]
    for s, view in cases:
        assert fa._sidebar_active(s) == "campaigns"
        assert fa._sidebar_campaign_view(s) == view
    # Past the chooser is the + New Campaign wizard, not a Campaigns view.
    wiz = st("start_seq", "templates")
    assert fa._sidebar_active(wiz) == "new" and fa._sidebar_campaign_view(wiz) == ""


def test_dashboard_pipeline_card_gated_on_ats():
    """The 'candidates in Pipeline' card counts ATS candidates. Sales-only
    instances run with the ATS off, so the card must be gated rather
    than relabelled with a metric that does not exist."""
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_dashboard)
    i = src.index("# Pipeline (ATS) status")
    assert "if _ATS_ENABLED:" in src[i:i + 300]


def test_clients_copy_follows_brand_copy():
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    assert 'if BRAND_COPY == "sales"' in src
    assert "accidentally pitch our own clients." in src
    assert "accidentally recruit from our own clients." in src


def test_sync_brand_env_carries_nav_keys():
    import importlib.util
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[1] / "deploy" / "sync_brand_env.py"
    spec = importlib.util.spec_from_file_location("sync_brand_env", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "DRIPDROP_NAV_" in mod.PREFIXES
    assert "DRIPDROP_WORKSPACE_" in mod.PREFIXES


def test_inboxslide_env_example_enables_sidebar():
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[1] / "deploy" / "env.inboxslide.example"
    text = p.read_text(encoding="utf-8")
    assert "DRIPDROP_NAV_LAYOUT=sidebar" in text
    assert "DRIPDROP_WORKSPACE_NAME=ThriveModal" in text


def test_content_pages_are_top_level_rows():
    """Content Library's sub-rows became rows of their own (2026-09-24).
    Every row key has an icon, every page lights its own row, and the two
    ThriveModal-only prompt rows resolve through the additive table so
    Arena's sidebar never shows them."""
    import flowdrip_app as fa
    for _sec, rows in fa.SIDEBAR_NAV:
        for ik, _lbl, _key in rows:
            assert ik in fa._SIDEBAR_ICONS, f"missing icon {ik}"
    assert fa.SIDEBAR_PAGE_ROW.get("tm_prompts") == "ai_prompt"
    assert fa.SIDEBAR_PAGE_ROW.get("tm_saved_prompts") == "saved_prompts"
    assert fa.SIDEBAR_TITLES.get("tm_prompts") == "AI Prompt"
    assert fa.SIDEBAR_TITLES.get("newsletters") == "Newsletters"
    assert fa.SIDEBAR_TITLES.get("pdf_gen") == "Sales Assets"
    assert fa._TM_NAV_PAGES["ai_prompt"] == "tm_prompts"
    assert fa._TM_NAV_PAGES["saved_prompts"] == "tm_saved_prompts"
    assert not hasattr(fa, "SIDEBAR_LIBRARY")
    src = inspect.getsource(fa._sidebar_v2)
    assert "SIDEBAR_LIBRARY" not in src and "_lib_open" not in src


def test_roundup_hidden_on_sales_instances():
    import flowdrip_app as fa
    src = inspect.getsource(fa.p_newsletters)
    assert "and not _SALES_MODE)" in src


def test_newsletter_sectors_are_thrivemodal_on_sales_instances():
    import flowdrip_app as fa
    src = inspect.getsource(fa._create_newsletter_dialog)
    assert "_TM_NEWSLETTER_SECTORS if _SALES_MODE else AICB_INDUSTRIES" in src
    assert "AICB_INDUSTRIES.items()" not in src
    labels = {v["label"] for v in fa._TM_NEWSLETTER_SECTORS.values()}
    assert "Logistics & Freight" in labels and "Architecture" not in labels
    for v in fa._TM_NEWSLETTER_SECTORS.values():
        assert v["niches"]


def test_sales_newsletter_prompts_have_no_candidates():
    import flowdrip_app as fa
    p = fa._jway_sales_prompt("Freight", "Freight Brokerage", "Dallas, TX",
                              "October 2026", "Pat", "Acme")
    assert '"candidates":[]' in p
    assert "Top Talent" not in p and "recruiting market newsletter" not in p
    assert "{FirstName}" in p

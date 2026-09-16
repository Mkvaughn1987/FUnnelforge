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
    """Companies, sales Pipeline, Sales Dashboard and Outreach Analytics
    were requested but have no page. They stay in the nav model with a
    None page key and the renderer filters them out (no empty pages)."""
    import flowdrip_app as fa
    by_label = {lbl: key for _sec, rows in fa.SIDEBAR_NAV for _ik, lbl, key in rows}
    for lbl in ("Companies", "Pipeline", "Sales Dashboard", "Outreach Analytics"):
        assert lbl in by_label, f"{lbl} missing from SIDEBAR_NAV"
        assert by_label[lbl] is None, f"{lbl} must not be wired until a page exists"
    for lbl in ("Overview", "My Day", "Replies", "Contacts", "Clients",
                "Campaigns", "Content Library"):
        assert by_label.get(lbl), f"{lbl} must map to an existing page key"
    src = inspect.getsource(fa._sidebar_v2)
    assert "rows = [r for r in rows if r[2]]" in src
    assert "if not rows:" in src


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
    router = inspect.getsource(fa.render_page)
    for k in ("signature", "timezone"):
        assert f'elif page == "{k}":' in router
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
    assert m["newsletters"] == "library" and m["pdf_gen"] == "library"
    for k in ("ai_settings", "company_profile", "team_settings", "signature",
              "timezone", "dnc"):
        assert m[k] == "settings", k
    assert m["responses"] == "replies" and m["e_responses"] == "replies"
    src = inspect.getsource(fa._sidebar_active)
    assert '"saved"' in src and '"campaigns"' in src


def test_page_header_has_campaign_and_library_tabs_and_search():
    import flowdrip_app as fa
    src = inspect.getsource(fa._page_header_v2)
    for tab in ("Active", "Completed", "Saved", "Templates", "Newsletters", "Sales Assets"):
        assert f'"{tab}"' in src, f"missing header tab {tab}"
    assert "_mgr_show_completed" in src
    assert "Do Not Contact" in src, "suppression management must stay one click away"
    assert "fd-ph-search" in src


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

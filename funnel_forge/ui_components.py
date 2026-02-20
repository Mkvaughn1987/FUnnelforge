# ui_components.py
# Reusable UI widget factories for Funnel Forge
# Every component uses design tokens from styles.py - never hardcode values.

import tkinter as tk
from tkinter import ttk

from funnel_forge.styles import (
    # Surfaces
    SURFACE_PAGE, SURFACE_CARD, SURFACE_INSET,
    BG_ROOT, BG_CARD, BG_HOVER, BG_SIDEBAR,
    # Grays
    GRAY_50, GRAY_100, GRAY_200, GRAY_300, GRAY_400, GRAY_500,
    GRAY_600, GRAY_700, GRAY_800, GRAY_900,
    # Primary
    PRIMARY_50, PRIMARY_100, PRIMARY_500, PRIMARY_600,
    ACCENT, ACCENT_HOVER,
    # Semantic
    GOOD, DANGER, WARN, INFO,
    SUCCESS_BG, SUCCESS_FG, DANGER_BG, DANGER_FG,
    WARN_BG, WARN_FG, INFO_BG, INFO_FG,
    # Text
    FG_TEXT, FG_MUTED, FG_LIGHT, FG_WHITE,
    # Borders
    BORDER, BORDER_MEDIUM,
    # Nav states
    NAV_DEFAULT_BG, NAV_DEFAULT_FG, NAV_HOVER_BG, NAV_HOVER_FG,
    NAV_ACTIVE_BG, NAV_ACTIVE_FG, NAV_ACTIVE_BAR, NAV_SUB_FG,
    # Typography
    FONT_CAPTION, FONT_SMALL, FONT_BASE, FONT_BODY, FONT_BODY_MEDIUM,
    FONT_SUBTITLE, FONT_TITLE, FONT_HEADING, FONT_DISPLAY,
    FONT_BUTTON, FONT_BUTTON_SECONDARY, FONT_BTN_SM, FONT_BTN_LG,
    # Spacing
    SP_1, SP_2, SP_3, SP_4, SP_5, SP_6, SP_8, SP_10, SP_12,
)


# =====================================================================
# BUTTONS
# =====================================================================

def make_button(parent, text, command, variant="primary", size="md", **kwargs):
    """
    Create a styled button.

    variant: "primary" | "secondary" | "ghost" | "danger" | "success" | "warning"
    size:    "sm" | "md" | "lg"
    """
    size_map = {
        "sm": {"font": FONT_BTN_SM, "px": SP_3, "py": SP_1},
        "md": {"font": FONT_BUTTON, "px": SP_4, "py": SP_2},
        "lg": {"font": FONT_BTN_LG, "px": SP_5, "py": SP_3},
    }
    s = size_map.get(size, size_map["md"])
    font = kwargs.pop("font", s["font"])
    px = kwargs.pop("padx", s["px"])
    py = kwargs.pop("pady", s["py"])

    variants = {
        "primary": {
            "bg": PRIMARY_500, "fg": "#FFFFFF",
            "active_bg": PRIMARY_600, "active_fg": "#FFFFFF",
            "hover_bg": ACCENT_HOVER, "hover_fg": "#FFFFFF",
        },
        "secondary": {
            "bg": SURFACE_CARD, "fg": GRAY_700,
            "active_bg": GRAY_100, "active_fg": GRAY_800,
            "hover_bg": GRAY_50, "hover_fg": GRAY_800,
            "border": GRAY_300,
        },
        "ghost": {
            "bg": "parent", "fg": GRAY_500,
            "active_bg": "parent", "active_fg": GRAY_800,
            "hover_bg": "parent", "hover_fg": GRAY_800,
        },
        "danger": {
            "bg": DANGER, "fg": "#FFFFFF",
            "active_bg": "#B91C1C", "active_fg": "#FFFFFF",
            "hover_bg": "#DC2626", "hover_fg": "#FFFFFF",
        },
        "success": {
            "bg": GOOD, "fg": "#FFFFFF",
            "active_bg": "#059669", "active_fg": "#FFFFFF",
            "hover_bg": "#059669", "hover_fg": "#FFFFFF",
        },
        "warning": {
            "bg": WARN, "fg": "#FFFFFF",
            "active_bg": WARN_FG, "active_fg": "#FFFFFF",
            "hover_bg": WARN_FG, "hover_fg": "#FFFFFF",
        },
    }
    v = variants.get(variant, variants["primary"])

    # Resolve "parent" bg
    try:
        parent_bg = parent.cget("bg")
    except Exception:
        parent_bg = BG_ROOT
    bg = parent_bg if v["bg"] == "parent" else v["bg"]
    active_bg = parent_bg if v.get("active_bg") == "parent" else v.get("active_bg", bg)
    hover_bg = parent_bg if v.get("hover_bg") == "parent" else v.get("hover_bg", bg)

    # If secondary variant, wrap in border frame
    if variant == "secondary" and "border" in v:
        border_frame = tk.Frame(parent, bg=v["border"])
        btn = tk.Button(
            border_frame, text=text, command=command,
            bg=bg, fg=v["fg"],
            activebackground=active_bg, activeforeground=v["active_fg"],
            font=font, relief="flat", bd=0, cursor="hand2",
            padx=px, pady=py, **kwargs
        )
        btn.pack(padx=1, pady=1)

        def _enter(e):
            btn.config(bg=hover_bg, fg=v["hover_fg"])
            border_frame.config(bg=GRAY_400)
        def _leave(e):
            btn.config(bg=bg, fg=v["fg"])
            border_frame.config(bg=v["border"])
        btn.bind("<Enter>", _enter)
        btn.bind("<Leave>", _leave)
        border_frame._inner_btn = btn
        return border_frame

    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=v["fg"],
        activebackground=active_bg, activeforeground=v["active_fg"],
        font=font, relief="flat", bd=0, cursor="hand2",
        padx=px, pady=py, **kwargs
    )

    def _enter(e):
        btn.config(bg=hover_bg, fg=v["hover_fg"])
    def _leave(e):
        btn.config(bg=bg, fg=v["fg"])
    btn.bind("<Enter>", _enter)
    btn.bind("<Leave>", _leave)

    return btn


# =====================================================================
# CARDS & SURFACES
# =====================================================================

def make_card(parent, bg=None, border_color=None, pad=None):
    """
    Card with subtle 1px border (simulated elevation).
    Returns (outer_frame, inner_frame). Pack/grid outer, add content to inner.
    """
    bg = bg or SURFACE_CARD
    border_color = border_color or GRAY_200
    pad = pad if pad is not None else SP_5

    outer = tk.Frame(parent, bg=border_color)
    inner = tk.Frame(outer, bg=bg, padx=pad, pady=pad)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    return outer, inner


def make_section(parent, title, subtitle=None, bg=None):
    """
    Section with title and optional subtitle. No borders, just typography hierarchy.
    Returns (container, content_frame) - add children to content_frame.
    """
    bg = bg or BG_ROOT
    container = tk.Frame(parent, bg=bg)

    tk.Label(
        container, text=title, bg=bg, fg=GRAY_800,
        font=FONT_SUBTITLE, anchor="w"
    ).pack(fill="x")

    if subtitle:
        tk.Label(
            container, text=subtitle, bg=bg, fg=GRAY_500,
            font=FONT_SMALL, anchor="w"
        ).pack(fill="x", pady=(SP_1, 0))

    content = tk.Frame(container, bg=bg)
    content.pack(fill="both", expand=True, pady=(SP_3, 0))
    return container, content


def make_divider(parent, bg=None, color=None):
    """Thin horizontal divider line."""
    bg = bg or BG_ROOT
    color = color or GRAY_200
    div = tk.Frame(parent, bg=color, height=1)
    div.pack(fill="x")
    return div


# =====================================================================
# PAGE HEADER
# =====================================================================

def make_page_header(parent, title, subtitle=None, bg=None):
    """
    Standard page header: large title + muted subtitle.
    Returns the header frame.
    """
    bg = bg or BG_ROOT
    header = tk.Frame(parent, bg=bg)

    tk.Label(
        header, text=title, bg=bg, fg=GRAY_900,
        font=FONT_TITLE, anchor="w"
    ).pack(fill="x")

    if subtitle:
        tk.Label(
            header, text=subtitle, bg=bg, fg=GRAY_500,
            font=FONT_BASE, anchor="w"
        ).pack(fill="x", pady=(SP_1, 0))

    return header


# =====================================================================
# STAT CARDS (Dashboard KPIs)
# =====================================================================

def make_stat_card(parent, label, value, color=None, bg=None):
    """
    Compact stat card: large number + label.
    Returns (outer, inner, value_label) so the value can be updated later.
    """
    bg = bg or SURFACE_CARD
    color = color or ACCENT
    outer, inner = make_card(parent, bg=bg)
    inner.configure(padx=SP_4, pady=SP_3)

    lbl = tk.Label(
        inner, text=label, bg=bg, fg=GRAY_500,
        font=FONT_SMALL, anchor="w"
    )
    lbl.pack(fill="x")

    val = tk.Label(
        inner, text=str(value), bg=bg, fg=color,
        font=FONT_HEADING, anchor="w"
    )
    val.pack(fill="x", pady=(SP_1, 0))

    return outer, inner, val


# =====================================================================
# BADGES / CHIPS
# =====================================================================

def make_badge(parent, text, variant="default", bg_override=None):
    """
    Small colored badge/chip for status indicators.
    variant: "default" | "success" | "danger" | "warning" | "info" | "primary"
    """
    badge_styles = {
        "default":  {"bg": GRAY_100,    "fg": GRAY_600},
        "success":  {"bg": SUCCESS_BG,  "fg": SUCCESS_FG},
        "danger":   {"bg": DANGER_BG,   "fg": DANGER_FG},
        "warning":  {"bg": WARN_BG,     "fg": WARN_FG},
        "info":     {"bg": INFO_BG,     "fg": INFO_FG},
        "primary":  {"bg": PRIMARY_50,  "fg": PRIMARY_500},
    }
    s = badge_styles.get(variant, badge_styles["default"])
    bg = bg_override or s["bg"]

    badge = tk.Label(
        parent, text=text, bg=bg, fg=s["fg"],
        font=FONT_CAPTION, padx=SP_2, pady=2
    )
    return badge


# =====================================================================
# EMPTY STATE
# =====================================================================

def make_empty_state(parent, icon_text="", headline="", description="",
                     button_text="", button_command=None, bg=None):
    """
    Centered empty state: icon + headline + description + optional CTA.
    Use when a list/table has no data.
    """
    bg = bg or SURFACE_CARD
    container = tk.Frame(parent, bg=bg)

    inner = tk.Frame(container, bg=bg)
    inner.place(relx=0.5, rely=0.4, anchor="center")

    if icon_text:
        tk.Label(
            inner, text=icon_text, bg=bg, fg=GRAY_300,
            font=("Segoe UI", 36)
        ).pack(pady=(0, SP_4))

    if headline:
        tk.Label(
            inner, text=headline, bg=bg, fg=GRAY_800,
            font=FONT_SUBTITLE
        ).pack(pady=(0, SP_2))

    if description:
        tk.Label(
            inner, text=description, bg=bg, fg=GRAY_500,
            font=FONT_BASE, wraplength=340, justify="center"
        ).pack(pady=(0, SP_5))

    if button_text and button_command:
        make_button(inner, button_text, button_command, variant="primary").pack()

    return container


# =====================================================================
# FORM FIELDS
# =====================================================================

def make_form_field(parent, label_text, placeholder="", required=False, bg=None):
    """
    Standard form field: label above input with focus-state border.
    Returns (container, entry, border_frame).
    """
    bg = bg or parent.cget("bg") if hasattr(parent, "cget") else BG_ROOT
    container = tk.Frame(parent, bg=bg)

    # Label
    label = f"{label_text} *" if required else label_text
    tk.Label(
        container, text=label, bg=bg, fg=GRAY_600,
        font=FONT_BODY_MEDIUM, anchor="w"
    ).pack(fill="x", pady=(0, SP_1))

    # Input with border simulation
    entry_border = tk.Frame(container, bg=GRAY_200)
    entry_border.pack(fill="x")

    entry = tk.Entry(
        entry_border, font=FONT_BASE, bg=SURFACE_CARD, fg=GRAY_800,
        relief="flat", bd=0, insertbackground=GRAY_800
    )
    entry.pack(fill="x", ipady=SP_2, padx=(SP_2 + 1,  SP_2 + 1), pady=1)

    # Placeholder
    if placeholder:
        entry.insert(0, placeholder)
        entry.config(fg=GRAY_400)

        def _focus_in(e):
            if entry.get() == placeholder:
                entry.delete(0, "end")
                entry.config(fg=GRAY_800)

        def _focus_out(e):
            if not entry.get():
                entry.insert(0, placeholder)
                entry.config(fg=GRAY_400)

        entry.bind("<FocusIn>", _focus_in, add="+")
        entry.bind("<FocusOut>", _focus_out, add="+")

    # Focus state: accent border
    def _on_focus(e):
        entry_border.config(bg=PRIMARY_500)
    def _on_blur(e):
        entry_border.config(bg=GRAY_200)
    entry.bind("<FocusIn>", _on_focus, add="+")
    entry.bind("<FocusOut>", _on_blur, add="+")

    return container, entry, entry_border


# =====================================================================
# TOAST NOTIFICATION
# =====================================================================

class Toast:
    """
    Non-blocking auto-dismissing notification overlay.

    Usage:
        toast = Toast(root)
        toast.show("Campaign launched!", "success")
        toast.show("Something went wrong", "error")
    """

    STYLES = {
        "success": {"bg": SUCCESS_FG, "fg": "#FFFFFF", "icon": "\u2713"},
        "error":   {"bg": DANGER,     "fg": "#FFFFFF", "icon": "\u2717"},
        "warning": {"bg": WARN_FG,    "fg": "#FFFFFF", "icon": "\u26A0"},
        "info":    {"bg": GRAY_800,   "fg": "#FFFFFF", "icon": "\u2139"},
    }

    def __init__(self, root):
        self.root = root
        self._current = None

    def show(self, message, variant="info", duration=3000):
        if self._current:
            try:
                self._current.destroy()
            except Exception:
                pass

        style = self.STYLES.get(variant, self.STYLES["info"])

        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg=style["bg"])

        content = tk.Frame(toast, bg=style["bg"], padx=SP_4, pady=SP_2)
        content.pack()

        tk.Label(
            content, text=f'{style["icon"]}  {message}',
            bg=style["bg"], fg=style["fg"],
            font=FONT_BODY_MEDIUM
        ).pack(side="left")

        # Position bottom-right of root window
        self.root.update_idletasks()
        rx = self.root.winfo_rootx() + self.root.winfo_width() - SP_5
        ry = self.root.winfo_rooty() + self.root.winfo_height() - SP_5
        toast.update_idletasks()
        tw = toast.winfo_reqwidth()
        th = toast.winfo_reqheight()
        toast.geometry(f"+{rx - tw}+{ry - th}")

        self._current = toast
        toast.after(duration, lambda: self._dismiss(toast))

    def _dismiss(self, toast):
        try:
            toast.destroy()
        except Exception:
            pass
        if self._current is toast:
            self._current = None


# =====================================================================
# SIDEBAR NAVIGATION (collapsible Gmail-style)
# =====================================================================

def make_sidebar(parent, nav_items, on_navigate, active_key="dashboard",
                 app_version="", footer_text=""):
    """
    Collapsible sidebar with expandable parent sections.

    nav_items: list of dicts. Two formats supported:
      Flat item:    {"text": "Dashboard", "key": "dashboard"}
      Group item:   {"text": "Create a Campaign", "key": "campaign", "children": [
                        {"text": "Build Emails", "key": "build"},
                        ...
                    ]}
      Legacy indent: {"text": "...", "key": "...", "indent": True}  (treated as flat sub-item)

    Clicking a parent toggles its children open/closed.
    Clicking a parent also navigates to its key.
    Clicking a child navigates to the child key and auto-expands the parent.

    Returns (sidebar_frame, update_fn) where update_fn(new_key) refreshes active state.
    """
    sidebar = tk.Frame(parent, bg=BG_SIDEBAR, width=220)
    sidebar.grid_propagate(False)
    sidebar.pack_propagate(False)

    # Top spacing
    tk.Frame(sidebar, bg=BG_SIDEBAR, height=SP_4).pack()

    buttons = {}       # key -> {row, btn, indicator, is_sub}
    groups = {}        # parent_key -> {container, expanded, child_keys}
    child_to_parent = {}  # child_key -> parent_key

    def _set_hover(btn, bg, fg):
        btn.unbind("<Enter>")
        btn.unbind("<Leave>")
        btn.bind("<Enter>", lambda e, b=btn: b.config(bg=NAV_HOVER_BG, fg=NAV_HOVER_FG))
        btn.bind("<Leave>", lambda e, b=btn, _bg=bg, _fg=fg: b.config(bg=_bg, fg=_fg))

    def _clear_hover(btn):
        btn.unbind("<Enter>")
        btn.unbind("<Leave>")

    def _toggle_group(parent_key):
        """Expand/collapse a parent's children."""
        g = groups[parent_key]
        g["expanded"] = not g["expanded"]
        if g["expanded"]:
            g["container"].pack(fill="x", after=buttons[parent_key]["row"])
            # Update chevron
            buttons[parent_key]["btn"].config(
                text=f"  {buttons[parent_key]['_text']}   \u25B4"
            )
        else:
            g["container"].pack_forget()
            buttons[parent_key]["btn"].config(
                text=f"  {buttons[parent_key]['_text']}   \u25BE"
            )

    def _on_parent_click(parent_key):
        """Toggle children and navigate to the parent screen."""
        _toggle_group(parent_key)
        on_navigate(parent_key)

    def _on_child_click(child_key):
        """Navigate to child, auto-expand parent if collapsed."""
        pk = child_to_parent.get(child_key)
        if pk and pk in groups and not groups[pk]["expanded"]:
            _toggle_group(pk)
        # Use nav_key if set (allows multiple sidebar items to share a screen)
        nav_key = buttons[child_key].get("_nav_key", child_key)
        on_navigate(nav_key)

    def _make_parent_item(item):
        key = item["key"]
        text = item["text"]
        children = item.get("children", [])
        is_active = (key == active_key)
        has_active_child = any(c.get("nav_key", c["key"]) == active_key for c in children)
        start_expanded = has_active_child  # auto-expand if a child is active

        # Parent row
        row = tk.Frame(sidebar, bg=BG_SIDEBAR)
        row.pack(fill="x")

        indicator = tk.Frame(
            row, bg=NAV_ACTIVE_BAR if is_active else BG_SIDEBAR, width=3
        )
        indicator.pack(side="left", fill="y")

        bg = NAV_ACTIVE_BG if is_active else NAV_DEFAULT_BG
        fg = NAV_ACTIVE_FG if is_active else NAV_DEFAULT_FG
        font = FONT_BODY_MEDIUM if is_active else FONT_BASE
        chevron = "\u25B4" if start_expanded else "\u25BE"

        btn = tk.Button(
            row, text=f"  {text}   {chevron}", anchor="w",
            bg=bg, fg=fg, font=font,
            relief="flat", bd=0, cursor="hand2",
            padx=SP_4, pady=SP_2,
            activebackground=NAV_HOVER_BG, activeforeground=NAV_HOVER_FG,
            command=lambda k=key: _on_parent_click(k)
        )
        btn.pack(fill="x", expand=True)

        if not is_active:
            _set_hover(btn, bg, fg)

        buttons[key] = {
            "row": row, "btn": btn, "indicator": indicator,
            "is_sub": False, "_text": text,
        }

        # Children container
        child_container = tk.Frame(sidebar, bg=BG_SIDEBAR)
        child_keys = []

        for child in children:
            ckey = child["key"]
            ctext = child["text"]
            c_nav_key = child.get("nav_key", ckey)
            child_keys.append(ckey)
            child_to_parent[ckey] = key
            c_is_active = (c_nav_key == active_key)

            crow = tk.Frame(child_container, bg=BG_SIDEBAR)
            crow.pack(fill="x")

            c_indicator = tk.Frame(
                crow, bg=NAV_ACTIVE_BAR if c_is_active else BG_SIDEBAR, width=3
            )
            c_indicator.pack(side="left", fill="y")

            c_bg = NAV_ACTIVE_BG if c_is_active else NAV_DEFAULT_BG
            c_fg = NAV_ACTIVE_FG if c_is_active else NAV_SUB_FG
            c_font = FONT_BODY_MEDIUM if c_is_active else FONT_SMALL

            c_btn = tk.Button(
                crow, text=ctext, anchor="w",
                bg=c_bg, fg=c_fg, font=c_font,
                relief="flat", bd=0, cursor="hand2",
                padx=SP_6, pady=SP_1,
                activebackground=NAV_HOVER_BG, activeforeground=NAV_HOVER_FG,
                command=lambda ck=ckey: _on_child_click(ck)
            )
            c_btn.pack(fill="x", expand=True)

            if not c_is_active:
                _set_hover(c_btn, c_bg, c_fg)

            buttons[ckey] = {
                "row": crow, "btn": c_btn, "indicator": c_indicator,
                "is_sub": True, "_nav_key": c_nav_key,
            }

        groups[key] = {
            "container": child_container,
            "expanded": start_expanded,
            "child_keys": child_keys,
        }

        # Show children if starting expanded
        if start_expanded:
            child_container.pack(fill="x", after=row)

    def _make_flat_item(item):
        key = item["key"]
        text = item["text"]
        is_sub = item.get("indent", False)
        is_active = (key == active_key)

        row = tk.Frame(sidebar, bg=BG_SIDEBAR)
        row.pack(fill="x")

        indicator = tk.Frame(
            row, bg=NAV_ACTIVE_BAR if is_active else BG_SIDEBAR, width=3
        )
        indicator.pack(side="left", fill="y")

        bg = NAV_ACTIVE_BG if is_active else NAV_DEFAULT_BG
        fg = NAV_ACTIVE_FG if is_active else (NAV_SUB_FG if is_sub else NAV_DEFAULT_FG)
        font = FONT_BODY_MEDIUM if is_active else (FONT_SMALL if is_sub else FONT_BASE)
        left_pad = SP_6 if is_sub else SP_4

        btn = tk.Button(
            row, text=text, anchor="w",
            bg=bg, fg=fg, font=font,
            relief="flat", bd=0, cursor="hand2",
            padx=left_pad, pady=SP_2,
            activebackground=NAV_HOVER_BG, activeforeground=NAV_HOVER_FG,
            command=lambda k=key: on_navigate(k)
        )
        btn.pack(fill="x", expand=True)

        if not is_active:
            _set_hover(btn, bg, fg)

        buttons[key] = {"row": row, "btn": btn, "indicator": indicator, "is_sub": is_sub}

    # Build all items
    for item in nav_items:
        if "children" in item and item["children"]:
            _make_parent_item(item)
        else:
            _make_flat_item(item)

    # Push footer to bottom
    tk.Label(sidebar, text="", bg=BG_SIDEBAR).pack(expand=True, fill="y")

    # Version footer
    if app_version:
        tk.Label(
            sidebar, text=f"Version {app_version}",
            bg=BG_SIDEBAR, fg=GRAY_400, font=FONT_CAPTION, anchor="w"
        ).pack(fill="x", padx=SP_4, pady=(0, 2))

    if footer_text:
        footer_lbl = tk.Label(
            sidebar, text=footer_text,
            bg=BG_SIDEBAR, fg=GRAY_400, font=("Segoe UI", 8, "italic"), anchor="w"
        )
        footer_lbl.pack(fill="x", padx=SP_4, pady=(0, SP_2))
        sidebar._footer_label = footer_lbl

    def update_active(new_key):
        """Update the active state and auto-expand the parent group if needed."""
        # Find all sidebar buttons whose nav_key matches, auto-expand their parent
        for k, parts in buttons.items():
            nav = parts.get("_nav_key", k)
            if nav == new_key:
                pk = child_to_parent.get(k)
                if pk and pk in groups and not groups[pk]["expanded"]:
                    _toggle_group(pk)

        for k, parts in buttons.items():
            # Match on nav_key so shared-screen children both highlight
            nav = parts.get("_nav_key", k)
            is_active = (nav == new_key)
            is_sub = parts["is_sub"]

            bg = NAV_ACTIVE_BG if is_active else NAV_DEFAULT_BG
            fg = NAV_ACTIVE_FG if is_active else (NAV_SUB_FG if is_sub else NAV_DEFAULT_FG)
            font = FONT_BODY_MEDIUM if is_active else (FONT_SMALL if is_sub else FONT_BASE)

            # Parents keep their chevron text
            if "_text" in parts:
                g = groups.get(k)
                chevron = "\u25B4" if (g and g["expanded"]) else "\u25BE"
                parts["btn"].config(bg=bg, fg=fg, font=font,
                                    text=f"  {parts['_text']}   {chevron}")
            else:
                parts["btn"].config(bg=bg, fg=fg, font=font)

            parts["indicator"].config(bg=NAV_ACTIVE_BAR if is_active else BG_SIDEBAR)

            _clear_hover(parts["btn"])
            if not is_active:
                _set_hover(parts["btn"], bg, fg)

    return sidebar, update_active

"""
html_format.py
HTML formatting support for FunnelForge Email Editor.

Provides:
- Bold, Italic, Underline
- Font Size (Small / Normal / Large / XL)
- Font Color (preset palette)
- Bullet & Numbered lists (multi-line)
- Hyperlinks
- Text alignment (Left / Center / Right)
- Line spacing
- Clear formatting
- Serialization (tk.Text → HTML) and Deserialization (HTML → tk.Text)
- Toolbar builder
"""

import re
import tkinter as tk
from html.parser import HTMLParser

from funnel_forge.styles import (
    BG_CARD, BG_ENTRY, BG_HOVER, FG_TEXT, FG_MUTED,
    ACCENT, DANGER, GRAY_200, FONT_SMALL,
)

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

_SIZES = {"small": 8, "normal": 10, "large": 12, "xl": 14}
_SIZE_PT = {"small": 8, "large": 12, "xl": 14}  # non-default sizes

_SIZE_OPTIONS = [
    ("Small", "small"),
    ("Normal", "normal"),
    ("Large", "large"),
    ("Extra Large", "xl"),
]

_COLOR_OPTIONS = [
    ("black",  "#1E293B"),
    ("gray",   "#64748B"),
    ("red",    "#DC2626"),
    ("blue",   "#2563EB"),
    ("green",  "#059669"),
    ("purple", "#7C3AED"),
]
_COLOR_MAP = {n: h for n, h in _COLOR_OPTIONS}
_COLOR_HEX_TO_NAME = {h: n for n, h in _COLOR_OPTIONS}

# Build set of all font-related tag names (size × style compound tags)
_ALL_FONT_TAGS = {"bold", "italic", "bold_italic"}
for _sn in _SIZE_PT:
    _ALL_FONT_TAGS.add(f"size_{_sn}")
    _ALL_FONT_TAGS.add(f"size_{_sn}_bold")
    _ALL_FONT_TAGS.add(f"size_{_sn}_italic")
    _ALL_FONT_TAGS.add(f"size_{_sn}_bold_italic")

_COLOR_TAGS = {f"color_{n}" for n, _ in _COLOR_OPTIONS}
_ALIGN_TAGS = {"align_center", "align_right"}
_LIST_TAGS = {"bullet", "numbered"}

# All format tags for serialization detection
_FORMAT_TAGS = (
    _ALL_FONT_TAGS | {"underline", "hyperlink"}
    | _COLOR_TAGS | _ALIGN_TAGS | _LIST_TAGS
)

_SPACING_MAP = {
    "1.0":  (0, 0),
    "1.15": (2, 2),
    "1.5":  (4, 4),
    "2.0":  (8, 8),
}


# ──────────────────────────────────────────────
# Tag setup
# ──────────────────────────────────────────────

def configure_format_tags(text_widget):
    """Configure all formatting tags on a tk.Text widget."""

    # Keep selection visible when toolbar buttons take focus
    text_widget.configure(exportselection=False)

    # --- Font compound tags (size × style) ---
    # Normal size (10pt)
    text_widget.tag_configure("bold", font=("Segoe UI", 10, "bold"))
    text_widget.tag_configure("italic", font=("Segoe UI", 10, "italic"))
    text_widget.tag_configure("bold_italic", font=("Segoe UI", 10, "bold italic"))

    # Other sizes
    for sname, sval in _SIZE_PT.items():
        text_widget.tag_configure(f"size_{sname}", font=("Segoe UI", sval))
        text_widget.tag_configure(f"size_{sname}_bold", font=("Segoe UI", sval, "bold"))
        text_widget.tag_configure(f"size_{sname}_italic", font=("Segoe UI", sval, "italic"))
        text_widget.tag_configure(f"size_{sname}_bold_italic", font=("Segoe UI", sval, "bold italic"))

    # --- Non-font inline tags ---
    text_widget.tag_configure("underline", underline=True)
    text_widget.tag_configure("hyperlink", foreground="#4E6FD8", underline=True)

    # --- Color tags ---
    for cname, chex in _COLOR_OPTIONS:
        text_widget.tag_configure(f"color_{cname}", foreground=chex)

    # --- List tags ---
    text_widget.tag_configure("bullet", lmargin1=20, lmargin2=35)
    text_widget.tag_configure("numbered", lmargin1=20, lmargin2=35)

    # --- Alignment tags ---
    text_widget.tag_configure("align_center", justify="center")
    text_widget.tag_configure("align_right", justify="right")

    # --- Priority: font tags on top, then underline, then hyperlink ---
    for tag in _ALL_FONT_TAGS:
        text_widget.tag_raise(tag)
    text_widget.tag_raise("underline")
    text_widget.tag_raise("hyperlink")

    # --- Widget state ---
    if not hasattr(text_widget, "_hyperlink_urls"):
        text_widget._hyperlink_urls = {}
    if not hasattr(text_widget, "_hyperlink_counter"):
        text_widget._hyperlink_counter = 0
    if not hasattr(text_widget, "_line_spacing"):
        text_widget._line_spacing = "1.0"
        text_widget.configure(spacing1=0, spacing3=0)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _get_selection(text_widget):
    """Return (start, end) of selection or (None, None)."""
    try:
        return text_widget.index("sel.first"), text_widget.index("sel.last")
    except tk.TclError:
        return None, None


def _has_tag_in_range(text_widget, tag_name, start, end):
    """Check if *tag_name* overlaps the range [start, end)."""
    ranges = text_widget.tag_ranges(tag_name)
    for i in range(0, len(ranges), 2):
        ts = str(ranges[i])
        te = str(ranges[i + 1])
        if text_widget.compare(ts, "<", end) and text_widget.compare(te, ">", start):
            return True
    return False


def _has_tag_in_selection(text_widget, tag_name):
    start, end = _get_selection(text_widget)
    if not start:
        return False
    return _has_tag_in_range(text_widget, tag_name, start, end)


def _detect_font_state(text_widget, start, end):
    """Return (bold, italic, size_name) for the selection."""
    bold = italic = False
    size = "normal"
    for tag in _ALL_FONT_TAGS:
        if _has_tag_in_range(text_widget, tag, start, end):
            if "bold" in tag:
                bold = True
            if "italic" in tag:
                italic = True
            for sn in _SIZE_PT:
                if f"size_{sn}" in tag:
                    size = sn
    return bold, italic, size


def _apply_font_state(text_widget, start, end, bold, italic, size):
    """Clear all font tags in range, then apply the correct compound tag."""
    for tag in _ALL_FONT_TAGS:
        text_widget.tag_remove(tag, start, end)

    if size == "normal":
        if bold and italic:
            text_widget.tag_add("bold_italic", start, end)
        elif bold:
            text_widget.tag_add("bold", start, end)
        elif italic:
            text_widget.tag_add("italic", start, end)
    else:
        suffix = ""
        if bold and italic:
            suffix = "_bold_italic"
        elif bold:
            suffix = "_bold"
        elif italic:
            suffix = "_italic"
        text_widget.tag_add(f"size_{size}{suffix}", start, end)


# ──────────────────────────────────────────────
# Toggle / apply functions
# ──────────────────────────────────────────────

def toggle_bold(text_widget):
    start, end = _get_selection(text_widget)
    if not start:
        return
    bold, italic, size = _detect_font_state(text_widget, start, end)
    _apply_font_state(text_widget, start, end, not bold, italic, size)


def toggle_italic(text_widget):
    start, end = _get_selection(text_widget)
    if not start:
        return
    bold, italic, size = _detect_font_state(text_widget, start, end)
    _apply_font_state(text_widget, start, end, bold, not italic, size)


def toggle_underline(text_widget):
    start, end = _get_selection(text_widget)
    if not start:
        return
    if _has_tag_in_range(text_widget, "underline", start, end):
        text_widget.tag_remove("underline", start, end)
    else:
        text_widget.tag_add("underline", start, end)


def apply_font_size(text_widget, size_name):
    start, end = _get_selection(text_widget)
    if not start:
        return
    bold, italic, _ = _detect_font_state(text_widget, start, end)
    _apply_font_state(text_widget, start, end, bold, italic, size_name)


def apply_font_color(text_widget, color_name):
    start, end = _get_selection(text_widget)
    if not start:
        return
    # Remove all color tags first
    for ctag in _COLOR_TAGS:
        text_widget.tag_remove(ctag, start, end)
    # Apply new color (skip if black/default)
    if color_name != "black":
        text_widget.tag_add(f"color_{color_name}", start, end)


def apply_alignment(text_widget, align):
    """Apply alignment to the current/selected lines. align = 'left', 'center', or 'right'."""
    try:
        line_start = text_widget.index("sel.first linestart")
        line_end = text_widget.index("sel.last lineend")
    except tk.TclError:
        try:
            line_start = text_widget.index("insert linestart")
            line_end = text_widget.index("insert lineend")
        except tk.TclError:
            return

    # Remove existing alignment tags
    for atag in _ALIGN_TAGS:
        text_widget.tag_remove(atag, line_start, line_end)

    # Apply new alignment (skip if left = default)
    if align == "center":
        text_widget.tag_add("align_center", line_start, line_end)
    elif align == "right":
        text_widget.tag_add("align_right", line_start, line_end)


def clear_formatting(text_widget):
    """Remove ALL formatting tags from the current selection."""
    start, end = _get_selection(text_widget)
    if not start:
        return
    for tag in _FORMAT_TAGS:
        text_widget.tag_remove(tag, start, end)
    # Also remove hyperlink-specific tags
    for tag_name in list(getattr(text_widget, "_hyperlink_urls", {}).keys()):
        text_widget.tag_remove(tag_name, start, end)


# ──────────────────────────────────────────────
# Lists (bullet + numbered) — multi-line
# ──────────────────────────────────────────────

def _remove_list_prefix(text_widget, line_start, line_end, range_end):
    """Remove bullet or numbered prefix from a line. Returns adjusted range_end."""
    line_text = text_widget.get(line_start, line_end)
    # Only adjust range_end if modification is on the same line —
    # Tkinter line.column indices on other lines are unaffected by the edit.
    same_line = line_start.split('.')[0] == text_widget.index(range_end).split('.')[0]

    # Bullet prefix
    if line_text.startswith("\u2022 "):
        text_widget.delete(line_start, f"{line_start}+2c")
        text_widget.tag_remove("bullet", line_start, text_widget.index(f"{line_start} lineend"))
        return text_widget.index(f"{range_end}-2c") if same_line else range_end

    # Numbered prefix
    m = re.match(r'^(\d+\.\s)', line_text)
    if m:
        plen = len(m.group(1))
        text_widget.delete(line_start, f"{line_start}+{plen}c")
        text_widget.tag_remove("numbered", line_start, text_widget.index(f"{line_start} lineend"))
        return text_widget.index(f"{range_end}-{plen}c") if same_line else range_end

    return range_end


def toggle_bullet(text_widget):
    """Add or remove bullet formatting on selected lines (or current line)."""
    try:
        range_start = text_widget.index("sel.first linestart")
        range_end = text_widget.index("sel.last lineend")
    except tk.TclError:
        try:
            range_start = text_widget.index("insert linestart")
            range_end = text_widget.index("insert lineend")
        except tk.TclError:
            return

    first_line = text_widget.get(range_start, text_widget.index(f"{range_start} lineend"))
    removing = first_line.startswith("\u2022 ")

    current = range_start
    while text_widget.compare(current, "<=", range_end):
        line_start = text_widget.index(f"{current} linestart")
        line_end = text_widget.index(f"{current} lineend")
        line_text = text_widget.get(line_start, line_end)
        # Only adjust range_end when editing the same line it sits on —
        # Tkinter line.column indices on other lines are unaffected.
        same_line = line_start.split('.')[0] == text_widget.index(range_end).split('.')[0]

        if removing:
            if line_text.startswith("\u2022 "):
                text_widget.delete(line_start, f"{line_start}+2c")
                line_end = text_widget.index(f"{line_start} lineend")
                text_widget.tag_remove("bullet", line_start, line_end)
                if same_line:
                    range_end = text_widget.index(f"{range_end}-2c")
        else:
            if not line_text.startswith("\u2022 "):
                # Remove any existing list prefix first
                if line_text.strip():
                    range_end = _remove_list_prefix(text_widget, line_start, text_widget.index(f"{line_start} lineend"), range_end)
                    line_text = text_widget.get(line_start, text_widget.index(f"{line_start} lineend"))
                # Add bullet prefix (works on empty lines too)
                if not line_text.startswith("\u2022 "):
                    text_widget.insert(line_start, "\u2022 ")
                    line_end = text_widget.index(f"{line_start} lineend")
                    text_widget.tag_add("bullet", line_start, line_end)
                    if same_line:
                        range_end = text_widget.index(f"{range_end}+2c")

        next_line = text_widget.index(f"{line_start}+1line linestart")
        if text_widget.compare(next_line, "==", current):
            break
        current = next_line


def toggle_numbered(text_widget):
    """Add or remove numbered list formatting on selected lines."""
    try:
        range_start = text_widget.index("sel.first linestart")
        range_end = text_widget.index("sel.last lineend")
    except tk.TclError:
        try:
            range_start = text_widget.index("insert linestart")
            range_end = text_widget.index("insert lineend")
        except tk.TclError:
            return

    first_line = text_widget.get(range_start, text_widget.index(f"{range_start} lineend"))
    removing = bool(re.match(r'^\d+\.\s', first_line))

    current = range_start
    num = 1
    while text_widget.compare(current, "<=", range_end):
        line_start = text_widget.index(f"{current} linestart")
        line_end = text_widget.index(f"{current} lineend")
        line_text = text_widget.get(line_start, line_end)
        # Only adjust range_end when editing the same line it sits on —
        # Tkinter line.column indices on other lines are unaffected.
        same_line = line_start.split('.')[0] == text_widget.index(range_end).split('.')[0]

        if removing:
            m = re.match(r'^(\d+\.\s)', line_text)
            if m:
                plen = len(m.group(1))
                text_widget.delete(line_start, f"{line_start}+{plen}c")
                line_end = text_widget.index(f"{line_start} lineend")
                text_widget.tag_remove("numbered", line_start, line_end)
                if same_line:
                    range_end = text_widget.index(f"{range_end}-{plen}c")
        else:
            if not re.match(r'^\d+\.\s', line_text):
                if line_text.strip():
                    # Remove any existing list prefix first
                    range_end = _remove_list_prefix(text_widget, line_start, text_widget.index(f"{line_start} lineend"), range_end)
                    line_text = text_widget.get(line_start, text_widget.index(f"{line_start} lineend"))
                if not re.match(r'^\d+\.\s', line_text):
                    prefix = f"{num}. "
                    text_widget.insert(line_start, prefix)
                    line_end = text_widget.index(f"{line_start} lineend")
                    text_widget.tag_add("numbered", line_start, line_end)
                    if same_line:
                        range_end = text_widget.index(f"{range_end}+{len(prefix)}c")
            num += 1

        next_line = text_widget.index(f"{line_start}+1line linestart")
        if text_widget.compare(next_line, "==", current):
            break
        current = next_line


# ──────────────────────────────────────────────
# Hyperlink
# ──────────────────────────────────────────────

def insert_hyperlink(text_widget, parent_window):
    """Prompt for URL and display text, then insert a hyperlink."""
    dialog = tk.Toplevel(parent_window)
    dialog.title("Insert Hyperlink")
    dialog.transient(parent_window)
    dialog.grab_set()
    dialog.resizable(False, False)

    dialog.update_idletasks()
    pw = parent_window.winfo_width()
    ph = parent_window.winfo_height()
    px = parent_window.winfo_rootx()
    py = parent_window.winfo_rooty()
    dw, dh = 400, 190
    x = px + (pw - dw) // 2
    y = py + (ph - dh) // 2
    dialog.geometry(f"{dw}x{dh}+{x}+{y}")
    dialog.configure(bg=BG_CARD)

    selected_text = ""
    try:
        selected_text = text_widget.get("sel.first", "sel.last")
    except tk.TclError:
        pass

    tk.Label(dialog, text="URL:", bg=BG_CARD, fg=FG_TEXT,
             font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=(16, 4))
    url_var = tk.StringVar(value="https://")
    ent_url = tk.Entry(dialog, textvariable=url_var, bg=BG_ENTRY, fg=FG_TEXT,
                       insertbackground=FG_TEXT, relief="flat", font=("Segoe UI", 10),
                       highlightthickness=1, highlightbackground=GRAY_200,
                       highlightcolor=ACCENT)
    ent_url.pack(fill="x", padx=16)

    tk.Label(dialog, text="Display text:", bg=BG_CARD, fg=FG_TEXT,
             font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=(10, 4))
    display_var = tk.StringVar(value=selected_text)
    ent_display = tk.Entry(dialog, textvariable=display_var, bg=BG_ENTRY, fg=FG_TEXT,
                           insertbackground=FG_TEXT, relief="flat", font=("Segoe UI", 10),
                           highlightthickness=1, highlightbackground=GRAY_200,
                           highlightcolor=ACCENT)
    ent_display.pack(fill="x", padx=16)

    result = {"ok": False}

    def _on_ok(event=None):
        result["ok"] = True
        dialog.destroy()

    def _on_cancel(event=None):
        dialog.destroy()

    btn_frame = tk.Frame(dialog, bg=BG_CARD)
    btn_frame.pack(fill="x", padx=16, pady=(14, 12))

    tk.Button(btn_frame, text="Insert", command=_on_ok,
              bg=ACCENT, fg="white", activebackground="#4338CA",
              activeforeground="white", relief="flat", font=("Segoe UI", 10, "bold"),
              padx=14, pady=3, cursor="hand2").pack(side="right")
    tk.Button(btn_frame, text="Cancel", command=_on_cancel,
              bg=BG_CARD, fg=FG_TEXT, activebackground=BG_HOVER,
              activeforeground=FG_TEXT, relief="flat", font=("Segoe UI", 10),
              padx=14, pady=3, cursor="hand2").pack(side="right", padx=(0, 8))

    dialog.bind("<Return>", _on_ok)
    dialog.bind("<Escape>", _on_cancel)
    ent_url.focus_set()
    dialog.wait_window()

    if not result["ok"]:
        return

    url = url_var.get().strip()
    display = display_var.get().strip() or url
    if not url or url == "https://":
        return

    counter = getattr(text_widget, "_hyperlink_counter", 0)
    tag_name = f"hyperlink_{counter}"
    text_widget._hyperlink_counter = counter + 1

    if not hasattr(text_widget, "_hyperlink_urls"):
        text_widget._hyperlink_urls = {}
    text_widget._hyperlink_urls[tag_name] = url
    text_widget.tag_configure(tag_name, foreground="#4E6FD8", underline=True)

    try:
        sel_start = text_widget.index("sel.first")
        sel_end = text_widget.index("sel.last")
        text_widget.delete(sel_start, sel_end)
        text_widget.insert(sel_start, display, (tag_name, "hyperlink"))
    except tk.TclError:
        text_widget.insert("insert", display, (tag_name, "hyperlink"))


# ──────────────────────────────────────────────
# Line spacing
# ──────────────────────────────────────────────

def _set_line_spacing(text_widget, value, btn=None):
    s1, s3 = _SPACING_MAP.get(value, (2, 2))
    text_widget.configure(spacing1=s1, spacing3=s3)
    text_widget._line_spacing = value
    if btn:
        btn.configure(text=f"\u2195 {value}")


def _show_spacing_menu(text_widget, btn, parent_window):
    menu = tk.Menu(parent_window, tearoff=0, bg=BG_CARD, fg=FG_TEXT,
                   activebackground=ACCENT, activeforeground="white",
                   font=FONT_SMALL, relief="flat", bd=1)
    current = getattr(text_widget, "_line_spacing", "1.0")
    for label, value in [("Single (1.0)", "1.0"), ("1.15 spacing", "1.15"),
                         ("1.5 spacing", "1.5"), ("Double (2.0)", "2.0")]:
        prefix = "\u2713  " if value == current else "     "
        menu.add_command(label=prefix + label,
                         command=lambda v=value: (_set_line_spacing(text_widget, v, btn), text_widget.focus_set()))
    menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())


# ──────────────────────────────────────────────
# Toolbar popup menus
# ──────────────────────────────────────────────

def _show_size_menu(text_widget, btn, parent_window):
    menu = tk.Menu(parent_window, tearoff=0, bg=BG_CARD, fg=FG_TEXT,
                   activebackground=ACCENT, activeforeground="white",
                   font=FONT_SMALL, relief="flat", bd=1)
    # Detect current size
    start, end = _get_selection(text_widget)
    cur_size = "normal"
    if start:
        _, _, cur_size = _detect_font_state(text_widget, start, end)

    for label, sname in _SIZE_OPTIONS:
        pt = _SIZES[sname]
        prefix = "\u2713  " if sname == cur_size else "     "
        menu.add_command(label=f"{prefix}{label} ({pt}pt)",
                         command=lambda s=sname: (apply_font_size(text_widget, s), text_widget.focus_set()))
    menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())


def _show_color_menu(text_widget, btn, parent_window):
    menu = tk.Menu(parent_window, tearoff=0, bg=BG_CARD, fg=FG_TEXT,
                   activebackground=ACCENT, activeforeground="white",
                   font=FONT_SMALL, relief="flat", bd=1)
    # Detect current color
    start, end = _get_selection(text_widget)
    cur_color = "black"
    if start:
        for cname, _ in _COLOR_OPTIONS:
            if cname != "black" and _has_tag_in_range(text_widget, f"color_{cname}", start, end):
                cur_color = cname
                break

    for cname, chex in _COLOR_OPTIONS:
        prefix = "\u2713  " if cname == cur_color else "     "
        display_name = cname.capitalize()
        if cname == "black":
            display_name = "Default"
        menu.add_command(label=f"{prefix}{display_name}",
                         foreground=chex,
                         command=lambda c=cname: (_apply_color_and_update(text_widget, c, btn), text_widget.focus_set()))
    menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())


def _apply_color_and_update(text_widget, color_name, btn):
    apply_font_color(text_widget, color_name)
    chex = _COLOR_MAP.get(color_name, FG_TEXT)
    btn.configure(fg=chex)


def _show_align_menu(text_widget, btn, parent_window):
    menu = tk.Menu(parent_window, tearoff=0, bg=BG_CARD, fg=FG_TEXT,
                   activebackground=ACCENT, activeforeground="white",
                   font=FONT_SMALL, relief="flat", bd=1)
    # Detect current alignment
    try:
        ls = text_widget.index("sel.first linestart")
        le = text_widget.index("sel.last lineend")
    except tk.TclError:
        try:
            ls = text_widget.index("insert linestart")
            le = text_widget.index("insert lineend")
        except tk.TclError:
            ls = le = None

    cur = "left"
    if ls:
        if _has_tag_in_range(text_widget, "align_center", ls, le):
            cur = "center"
        elif _has_tag_in_range(text_widget, "align_right", ls, le):
            cur = "right"

    for label, value in [("Left", "left"), ("Center", "center"), ("Right", "right")]:
        prefix = "\u2713  " if value == cur else "     "
        menu.add_command(label=prefix + label,
                         command=lambda v=value: (apply_alignment(text_widget, v), text_widget.focus_set()))
    menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())


# ──────────────────────────────────────────────
# Serialization: Text widget → HTML
# ──────────────────────────────────────────────

def is_html(body: str) -> bool:
    """Check if body string contains HTML formatting tags."""
    if not body:
        return False
    return bool(re.search(
        r'<(b|i|u|ul|ol|li|a |br|p[ >]|span |div |/b>|/i>|/u>|/span>|/ol>)[> /]',
        body
    ))


def _parse_tags(tags, hyperlink_urls):
    """Parse a frozenset of active tag names into a formatting dict."""
    bold = italic = False
    size_pt = None
    color_hex = None
    alignment = None
    is_bullet = is_numbered = False
    link_tag = None

    for t in tags:
        # Font compound tags
        if t in _ALL_FONT_TAGS:
            if "bold" in t:
                bold = True
            if "italic" in t:
                italic = True
            for sn, sv in _SIZE_PT.items():
                if f"size_{sn}" in t:
                    size_pt = sv
        # Color
        if t.startswith("color_"):
            cname = t[6:]
            color_hex = _COLOR_MAP.get(cname)
        # Alignment
        if t == "align_center":
            alignment = "center"
        elif t == "align_right":
            alignment = "right"
        # Lists
        if t == "bullet":
            is_bullet = True
        if t == "numbered":
            is_numbered = True
        # Hyperlink
        if t.startswith("hyperlink_") and t in hyperlink_urls:
            link_tag = t

    return {
        "bold": bold, "italic": italic, "size_pt": size_pt,
        "color_hex": color_hex, "alignment": alignment,
        "is_bullet": is_bullet, "is_numbered": is_numbered,
        "link_tag": link_tag,
        "underline": "underline" in tags,
        "is_hyperlink": "hyperlink" in tags,
    }


def text_to_html(text_widget) -> str:
    """Convert tagged tk.Text content to HTML. Returns '' if no formatting found."""
    try:
        dump = text_widget.dump("1.0", "end-1c", tag=True, text=True)
    except tk.TclError:
        return ""
    if not dump:
        return ""

    active_tags = set()
    has_formatting = False
    segments = []

    for item in dump:
        key, value = item[0], item[1]
        if key == "tagon":
            if value in _FORMAT_TAGS or value.startswith("hyperlink_"):
                active_tags.add(value)
                has_formatting = True
        elif key == "tagoff":
            active_tags.discard(value)
        elif key == "text":
            segments.append((value, frozenset(active_tags)))

    if not has_formatting:
        return ""

    # ── Pre-process: flatten segments into lines ──
    # Each line collects its content pieces and the union of list tags
    # This prevents the bug where a bare '\n' between list items lacks
    # the bullet/numbered tag and prematurely closes the list.
    flat_lines = []       # list of {pieces, is_bullet, is_numbered}
    current_line = {"pieces": [], "is_bullet": False, "is_numbered": False}
    hyperlink_urls = getattr(text_widget, "_hyperlink_urls", {})

    for text_chunk, tags in segments:
        state = _parse_tags(tags, hyperlink_urls)
        parts = text_chunk.split("\n")

        for pi, part in enumerate(parts):
            if pi > 0:
                # Newline → finish current line, start a new one
                flat_lines.append(current_line)
                current_line = {"pieces": [], "is_bullet": False, "is_numbered": False}

            if part:
                current_line["pieces"].append((part, tags, state))
                if state["is_bullet"]:
                    current_line["is_bullet"] = True
                if state["is_numbered"]:
                    current_line["is_numbered"] = True

    # Don't forget the last line
    flat_lines.append(current_line)

    # ── Generate HTML from flat lines ──
    # `need_line_break` tracks whether the previous non-list text line
    # needs a <br> to end it.  List items don't need this because
    # </li> already acts as a block-level line break.
    html_parts = []
    in_ul = in_ol = in_li = False
    first_content = True
    need_line_break = False
    spacing = getattr(text_widget, "_line_spacing", "1.0")

    if spacing != "1.0":
        html_parts.append(f'<div style="line-height: {spacing};">')

    for line_info in flat_lines:
        pieces = line_info["pieces"]
        line_is_bullet = line_info["is_bullet"]
        line_is_numbered = line_info["is_numbered"]

        # Empty line: close any open list, emit <br>
        if not pieces:
            if in_li:
                html_parts.append("</li>")
                in_li = False
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            if in_ol:
                html_parts.append("</ol>")
                in_ol = False
            # Flush the pending line break from a previous text line,
            # then add another <br> for this blank line itself.
            if need_line_break:
                html_parts.append("<br>\n")
                need_line_break = False
            if not first_content:
                html_parts.append("<br>\n")
            continue

        # Close previous <li>
        if in_li:
            html_parts.append("</li>")
            in_li = False

        # Close list if leaving list context
        if in_ul and not line_is_bullet:
            html_parts.append("</ul>")
            in_ul = False
        if in_ol and not line_is_numbered:
            html_parts.append("</ol>")
            in_ol = False

        # Flush pending line break from a previous text line
        if need_line_break:
            html_parts.append("<br>\n")
            need_line_break = False

        # Open list if entering list context
        if line_is_bullet and not in_ul:
            html_parts.append("<ul>")
            in_ul = True
        if line_is_numbered and not in_ol:
            html_parts.append("<ol>")
            in_ol = True

        # Open <li>
        if line_is_bullet or line_is_numbered:
            html_parts.append("<li>")
            in_li = True

        # Render each piece of the line
        first_piece = True
        for part_text, part_tags, part_state in pieces:
            display = part_text

            # Strip bullet/number prefix from first piece only
            if first_piece:
                if line_is_bullet and display.startswith("\u2022 "):
                    display = display[2:]
                if line_is_numbered:
                    m = re.match(r'^\d+\.\s', display)
                    if m:
                        display = display[m.end():]
                first_piece = False

            if not display:
                continue

            # Alignment wrapper
            align_open = ""
            align_close = ""
            if part_state["alignment"]:
                align_open = f'<div style="text-align: {part_state["alignment"]};">'
                align_close = "</div>"

            # Build inline HTML
            content = _escape_html(display)

            if part_state["link_tag"]:
                url = hyperlink_urls.get(part_state["link_tag"], "")
                content = f'<a href="{_escape_html(url)}">{content}</a>'
            if part_state["bold"]:
                content = f"<b>{content}</b>"
            if part_state["italic"]:
                content = f"<i>{content}</i>"
            if part_state["underline"] and not part_state["is_hyperlink"]:
                content = f"<u>{content}</u>"

            # Span for size / color
            span_styles = []
            if part_state["size_pt"]:
                span_styles.append(f"font-size: {part_state['size_pt']}pt")
            if part_state["color_hex"]:
                span_styles.append(f"color: {part_state['color_hex']}")
            if span_styles:
                content = f'<span style="{"; ".join(span_styles)}">{content}</span>'

            html_parts.append(align_open + content + align_close)

        # Non-list text lines need a <br> to end them; list items
        # don't because </li> is block-level.
        if not line_is_bullet and not line_is_numbered:
            need_line_break = True

        first_content = False

    # Close any trailing open tags
    if in_li:
        html_parts.append("</li>")
    if in_ul:
        html_parts.append("</ul>")
    if in_ol:
        html_parts.append("</ol>")
    if spacing != "1.0":
        html_parts.append("</div>")

    result = "".join(html_parts)
    return _add_list_styles(result)


def _escape_html(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ──────────────────────────────────────────────
# Deserialization: HTML → Text widget
# ──────────────────────────────────────────────

class _HTMLToTextParser(HTMLParser):
    def __init__(self, text_widget):
        super().__init__()
        self.w = text_widget
        self.tag_stack = []
        self.active_tags = set()
        self.in_ol = False
        self.ol_counter = 0
        self._link_counter = getattr(text_widget, "_hyperlink_counter", 0)

    def _current_tags(self):
        return tuple(self.active_tags)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = dict(attrs)

        if tag in ("b", "strong"):
            self.active_tags.add("bold")
            self.tag_stack.append("bold")
        elif tag in ("i", "em"):
            self.active_tags.add("italic")
            self.tag_stack.append("italic")
        elif tag == "u":
            self.active_tags.add("underline")
            self.tag_stack.append("underline")
        elif tag == "ul":
            self.tag_stack.append("_ul")
        elif tag == "ol":
            self.in_ol = True
            self.ol_counter = 0
            self.tag_stack.append("_ol")
        elif tag == "li":
            if self.in_ol:
                self.ol_counter += 1
                self.active_tags.add("numbered")
                self.w.insert("end", f"{self.ol_counter}. ", self._current_tags())
                self.tag_stack.append("li_ol")
            else:
                self.active_tags.add("bullet")
                self.w.insert("end", "\u2022 ", self._current_tags())
                self.tag_stack.append("li_ul")
        elif tag == "a":
            href = attrs_dict.get("href", "")
            if href:
                link_tag = f"hyperlink_{self._link_counter}"
                self._link_counter += 1
                self.w.tag_configure(link_tag, foreground="#4E6FD8", underline=True)
                if not hasattr(self.w, "_hyperlink_urls"):
                    self.w._hyperlink_urls = {}
                self.w._hyperlink_urls[link_tag] = href
                self.active_tags.add("hyperlink")
                self.active_tags.add(link_tag)
                self.tag_stack.append(("a", link_tag))
        elif tag == "br":
            self.w.insert("end", "\n")
        elif tag == "p":
            content = self.w.get("1.0", "end-1c")
            if content and not content.endswith("\n"):
                self.w.insert("end", "\n")
        elif tag == "span":
            style = attrs_dict.get("style", "")
            span_tags = []
            # Font size
            sz_match = re.search(r'font-size:\s*(\d+)pt', style)
            if sz_match:
                pt = int(sz_match.group(1))
                for sn, sv in _SIZE_PT.items():
                    if sv == pt:
                        self.active_tags.add(f"_size_{sn}")
                        span_tags.append(f"_size_{sn}")
                        break
            # Color
            clr_match = re.search(r'color:\s*(#[0-9a-fA-F]{6})', style)
            if clr_match:
                chex = clr_match.group(1).upper()
                cname = _COLOR_HEX_TO_NAME.get(chex)
                if not cname:
                    for n, h in _COLOR_OPTIONS:
                        if h.upper() == chex:
                            cname = n
                            break
                if cname:
                    self.active_tags.add(f"color_{cname}")
                    span_tags.append(f"color_{cname}")
            if span_tags:
                self.tag_stack.append(("_span", span_tags))
        elif tag == "div":
            style = attrs_dict.get("style", "")
            # Line height
            lh = re.search(r'line-height:\s*([\d.]+)', style)
            if lh:
                val = lh.group(1)
                if val in _SPACING_MAP:
                    s1, s3 = _SPACING_MAP[val]
                    self.w.configure(spacing1=s1, spacing3=s3)
                    self.w._line_spacing = val
            # Text alignment
            ta = re.search(r'text-align:\s*(\w+)', style)
            if ta:
                align = ta.group(1).lower()
                if align in ("center", "right"):
                    self.active_tags.add(f"align_{align}")
                    self.tag_stack.append(f"align_{align}")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("b", "strong"):
            self.active_tags.discard("bold")
        elif tag in ("i", "em"):
            self.active_tags.discard("italic")
        elif tag == "u":
            self.active_tags.discard("underline")
        elif tag == "ul":
            pass
        elif tag == "ol":
            self.in_ol = False
            self.ol_counter = 0
        elif tag == "li":
            self.active_tags.discard("bullet")
            self.active_tags.discard("numbered")
            self.w.insert("end", "\n")
        elif tag == "a":
            self.active_tags.discard("hyperlink")
            for item in reversed(self.tag_stack):
                if isinstance(item, tuple) and item[0] == "a":
                    self.active_tags.discard(item[1])
                    break
        elif tag == "p":
            content = self.w.get("1.0", "end-1c")
            if content and not content.endswith("\n"):
                self.w.insert("end", "\n")
        elif tag == "span":
            # Remove all tags associated with this span element
            for item in reversed(self.tag_stack):
                if isinstance(item, tuple) and item[0] == "_span":
                    for t in item[1]:
                        self.active_tags.discard(t)
                    self.tag_stack.remove(item)
                    break
        elif tag == "div":
            for item in reversed(self.tag_stack):
                if isinstance(item, str) and item.startswith("align_"):
                    self.active_tags.discard(item)
                    break

    def handle_data(self, data):
        if not data:
            return
        # Resolve compound font tags from active_tags
        tags = set()

        bold = "bold" in self.active_tags
        italic = "italic" in self.active_tags
        size = "normal"
        for t in self.active_tags:
            if t.startswith("_size_"):
                size = t[6:]  # strip "_size_"

        # Apply the correct compound font tag
        if size == "normal":
            if bold and italic:
                tags.add("bold_italic")
            elif bold:
                tags.add("bold")
            elif italic:
                tags.add("italic")
        else:
            suffix = ""
            if bold and italic:
                suffix = "_bold_italic"
            elif bold:
                suffix = "_bold"
            elif italic:
                suffix = "_italic"
            tags.add(f"size_{size}{suffix}")

        # Add non-font tags directly
        for t in self.active_tags:
            if t == "underline":
                tags.add("underline")
            elif t.startswith("color_"):
                tags.add(t)
            elif t.startswith("align_"):
                tags.add(t)
            elif t in ("bullet", "numbered"):
                tags.add(t)
            elif t == "hyperlink" or t.startswith("hyperlink_"):
                tags.add(t)

        self.w.insert("end", data, tuple(tags))

    def close(self):
        super().close()
        self.w._hyperlink_counter = self._link_counter


def html_to_text_widget(text_widget, html: str):
    """Parse HTML and insert into tk.Text widget with formatting tags."""
    text_widget.delete("1.0", "end")

    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    if body_match:
        html = body_match.group(1)

    parser = _HTMLToTextParser(text_widget)
    parser.feed(html)
    parser.close()

    content = text_widget.get("1.0", "end-1c")
    if content.endswith("\n"):
        text_widget.delete("end-2c", "end-1c")


# ──────────────────────────────────────────────
# Email HTML wrapper
# ──────────────────────────────────────────────

def wrap_html_for_email(html_body: str) -> str:
    return (
        '<html><head><meta charset="utf-8"></head>'
        '<body style="font-family: Calibri, Arial, sans-serif; '
        'font-size: 11pt; color: #1E293B;">\n'
        f'{html_body}\n'
        '</body></html>'
    )


def _add_list_styles(html_body: str) -> str:
    """Add inline styles to <ul>/<ol>/<li> to tighten spacing in email clients."""
    html_body = html_body.replace(
        "<ul>",
        '<ul style="margin:0; padding-left:28px;">'
    )
    html_body = html_body.replace(
        "<ol>",
        '<ol style="margin:0; padding-left:28px;">'
    )
    html_body = html_body.replace(
        "<li>",
        '<li style="margin:0; padding:0;">'
    )
    return html_body


# ──────────────────────────────────────────────
# Toolbar builder
# ──────────────────────────────────────────────

def _add_tooltip(widget, text):
    """Attach a hover tooltip to any widget."""
    tip = None

    def _enter(e):
        nonlocal tip
        tip = tk.Toplevel(widget)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        x = widget.winfo_rootx() + widget.winfo_width() // 2
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        tip.geometry(f"+{x}+{y}")
        lbl = tk.Label(tip, text=text, bg="#1E293B", fg="white",
                       font=("Segoe UI", 8), padx=6, pady=3, relief="solid", bd=1)
        lbl.pack()

    def _leave(e):
        nonlocal tip
        if tip:
            tip.destroy()
            tip = None

    widget.bind("<Enter>", _enter, add="+")
    widget.bind("<Leave>", _leave, add="+")


def build_format_toolbar(parent_frame, text_widget, app_root):
    """Build full formatting toolbar and return the frame."""
    toolbar = tk.Frame(parent_frame, bg=BG_CARD)
    toolbar.pack(fill="x", pady=(0, 4))

    def _do(fn, *args):
        """Execute formatting action and return focus to text widget."""
        fn(*args)
        text_widget.focus_set()

    def _sep():
        tk.Frame(toolbar, bg=GRAY_200, width=1, height=22).pack(side="left", padx=4, pady=1)

    def _icon(width=28):
        """Create a standard canvas icon button with hover effects."""
        c = tk.Canvas(toolbar, width=width, height=22, bg=BG_CARD,
                      highlightthickness=1, highlightbackground=GRAY_200,
                      cursor="hand2", bd=0, takefocus=False)
        c.bind("<Enter>", lambda e: c.configure(bg=BG_HOVER))
        c.bind("<Leave>", lambda e: c.configure(bg=BG_CARD))
        return c

    def _dropdown_arrow(c, x):
        """Draw a small dropdown triangle on the canvas."""
        c.create_polygon(x, 9, x + 6, 9, x + 3, 14, fill=FG_MUTED, outline="")

    # ── Bold ──
    c = _icon()
    c.create_text(14, 12, text="B", font=("Segoe UI", 12, "bold"), fill=ACCENT)
    c.bind("<Button-1>", lambda e: _do(toggle_bold, text_widget))
    c.pack(side="left", padx=(0, 1))
    _add_tooltip(c, "Bold (Ctrl+B)")

    # ── Italic ──
    c = _icon()
    c.create_text(14, 12, text="I", font=("Segoe UI", 12, "italic"), fill=ACCENT)
    c.bind("<Button-1>", lambda e: _do(toggle_italic, text_widget))
    c.pack(side="left", padx=(0, 1))
    _add_tooltip(c, "Italic (Ctrl+I)")

    # ── Underline ──
    c = _icon()
    c.create_text(14, 10, text="U", font=("Segoe UI", 11, "bold"), fill=ACCENT)
    c.create_line(6, 20, 22, 20, fill=ACCENT, width=2)
    c.bind("<Button-1>", lambda e: _do(toggle_underline, text_widget))
    c.pack(side="left", padx=(0, 1))
    _add_tooltip(c, "Underline (Ctrl+U)")

    _sep()

    # ── Bullet List ──
    c = _icon()
    for i, y in enumerate((4, 10, 16)):
        c.create_oval(4, y, 7, y + 3, fill=ACCENT, outline=ACCENT)
        c.create_line(10, y + 1, 25, y + 1, fill=FG_MUTED, width=2)
    c.bind("<Button-1>", lambda e: _do(toggle_bullet, text_widget))
    c.pack(side="left", padx=(0, 1))
    _add_tooltip(c, "Bullet List")

    # ── Numbered List ──
    c = _icon()
    for i, y in enumerate((4, 10, 16)):
        c.create_text(6, y + 2, text=str(i + 1),
                      font=("Segoe UI", 5, "bold"), fill=ACCENT, anchor="center")
        c.create_line(10, y + 1, 25, y + 1, fill=FG_MUTED, width=2)
    c.bind("<Button-1>", lambda e: _do(toggle_numbered, text_widget))
    c.pack(side="left", padx=(0, 1))
    _add_tooltip(c, "Numbered List")

    _sep()

    # ── Hyperlink (chain-link icon) ──
    c = _icon()
    c.create_oval(2, 5, 16, 15, outline=ACCENT, width=2)
    c.create_oval(12, 7, 26, 17, outline=ACCENT, width=2)
    c.bind("<Button-1>", lambda e: _do(insert_hyperlink, text_widget, app_root))
    c.pack(side="left", padx=(0, 1))
    _add_tooltip(c, "Insert Hyperlink")

    _sep()

    # ── Font Size (Aa ▾) ──
    c = _icon(36)
    c.create_text(14, 12, text="Aa", font=("Segoe UI", 10, "bold"), fill=ACCENT)
    _dropdown_arrow(c, 27)
    c.bind("<Button-1>", lambda e: _show_size_menu(text_widget, c, app_root))
    c.pack(side="left", padx=(0, 1))
    _add_tooltip(c, "Font Size")

    # ── Font Color (A with color bar ▾) ──
    c = _icon(36)
    c.create_text(14, 9, text="A", font=("Segoe UI", 11, "bold"), fill=ACCENT)
    c.create_rectangle(6, 18, 22, 21, fill=DANGER, outline="")
    _dropdown_arrow(c, 27)
    c.bind("<Button-1>", lambda e: _show_color_menu(text_widget, c, app_root))
    c.pack(side="left", padx=(0, 1))
    _add_tooltip(c, "Font Color")

    # ── Text Alignment (lines icon ▾) ──
    c = _icon(36)
    c.create_line(4, 6, 18, 6, fill=ACCENT, width=2)
    c.create_line(4, 11, 22, 11, fill=ACCENT, width=2)
    c.create_line(4, 16, 14, 16, fill=ACCENT, width=2)
    _dropdown_arrow(c, 27)
    c.bind("<Button-1>", lambda e: _show_align_menu(text_widget, c, app_root))
    c.pack(side="left", padx=(0, 1))
    _add_tooltip(c, "Text Alignment")

    _sep()

    # ── Line Spacing (lines with up/down arrows ▾) ──
    c = _icon(36)
    c.create_line(4, 6, 18, 6, fill=ACCENT, width=2)
    c.create_line(4, 16, 18, 16, fill=ACCENT, width=2)
    c.create_polygon(22, 4, 20, 8, 24, 8, fill=FG_MUTED, outline="")
    c.create_polygon(22, 18, 20, 14, 24, 14, fill=FG_MUTED, outline="")
    _dropdown_arrow(c, 28)
    c.bind("<Button-1>", lambda e: _show_spacing_menu(text_widget, c, app_root))
    c.pack(side="left", padx=(0, 1))
    _add_tooltip(c, "Line Spacing")

    # ── Keyboard shortcuts ──
    def _kb_bold(e):
        toggle_bold(text_widget)
        return "break"

    def _kb_italic(e):
        toggle_italic(text_widget)
        return "break"

    def _kb_underline(e):
        toggle_underline(text_widget)
        return "break"

    def _kb_return(e):
        """Auto-continue bullet / numbered lists on Enter."""
        line_start = text_widget.index("insert linestart")
        line_end = text_widget.index("insert lineend")
        line_text = text_widget.get(line_start, line_end)

        # ── Bullet list continuation ──
        if line_text.startswith("\u2022 "):
            # Empty bullet (just the prefix) → remove it and stop the list
            if line_text.strip() == "\u2022":
                text_widget.delete(line_start, line_end)
                text_widget.tag_remove("bullet", line_start, text_widget.index(f"{line_start} lineend"))
                return "break"
            # Insert new bullet line
            text_widget.insert("insert", "\n\u2022 ")
            new_line_start = text_widget.index("insert linestart")
            new_line_end = text_widget.index("insert lineend")
            text_widget.tag_add("bullet", new_line_start, new_line_end)
            return "break"

        # ── Numbered list continuation ──
        m = re.match(r'^(\d+)\.\s', line_text)
        if m:
            num = int(m.group(1))
            prefix_text = m.group(0)
            # Empty numbered item (just the prefix) → remove it and stop
            if line_text.strip() == f"{num}.":
                text_widget.delete(line_start, line_end)
                text_widget.tag_remove("numbered", line_start, text_widget.index(f"{line_start} lineend"))
                return "break"
            # Insert next numbered line
            next_prefix = f"{num + 1}. "
            text_widget.insert("insert", "\n" + next_prefix)
            new_line_start = text_widget.index("insert linestart")
            new_line_end = text_widget.index("insert lineend")
            text_widget.tag_add("numbered", new_line_start, new_line_end)
            return "break"

        # Default: let tkinter handle the Return key normally
        return None

    text_widget.bind("<Control-b>", _kb_bold)
    text_widget.bind("<Control-i>", _kb_italic)
    text_widget.bind("<Control-u>", _kb_underline)
    text_widget.bind("<Return>", _kb_return)

    return toolbar

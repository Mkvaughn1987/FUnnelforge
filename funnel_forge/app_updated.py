# app.py
# Funnel Forge – Modular GUI Application
# Main GUI application file with all UI components

import os
import sys
import re
import csv
import json
import shutil
import importlib
from datetime import datetime, timedelta
from typing import Optional, Any, Dict, List, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

# Calendar/date picker (Pylance-safe)
try:
    from tkcalendar import DateEntry as _DateEntry  # type: ignore
    DateEntry = _DateEntry
    HAVE_TKCAL = True
except Exception:
    DateEntry = None  # type: ignore
    HAVE_TKCAL = False

from PIL import Image, ImageTk

# Pillow resample constant (Pylance-friendly)
_RESAMPLING = getattr(Image, "Resampling", None)
RESAMPLE_LANCZOS: Any = getattr(_RESAMPLING, "LANCZOS", None)
if RESAMPLE_LANCZOS is None:
    RESAMPLE_LANCZOS = 0  # fallback

# Import all constants, helpers, and styling from styles module
from .styles import (
    APP_NAME, APP_VERSION, APP_DIR, USER_DIR, LOG_DIR,
    _write_crash_log, resource_path, user_path, ensure_dir,
    BG_ROOT, BG_CARD, BG_SIDEBAR, BG_HEADER, BG_ENTRY, BG_HOVER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT, DARK_AQUA, DARK_AQUA_HOVER,
    SECONDARY, SECONDARY_HOVER,
    FG_TEXT, FG_MUTED, FG_LIGHT, FG_WHITE,
    BORDER, BORDER_MEDIUM, BORDER_SOFT, ACCENT_2,
    GOOD, DANGER, WARN, INFO,
    FONT_BASE, FONT_LABEL, FONT_FIELD_HDR, FONT_TITLE, FONT_SUBTITLE, FONT_BUTTON, FONT_BUTTON_SECONDARY,
    PAD_SM, PAD_MD, PAD_LG, PAD_XL,
    MARGIN_SM, MARGIN_MD, MARGIN_LG, MARGIN_XL,
    CARD_OUTER_PAD, CARD_INNER_PAD, SECTION_SPACING, FIELD_SPACING,
    BTN_PAD_X, BTN_PAD_Y, BTN_SM_PAD_X, BTN_SM_PAD_Y,
    EMAIL_RE, CONTACT_FIELDS, TIME_OPTIONS, BODY_FILES,
    CONFIG_PATH, TEMPLATES_DIR, CONTACTS_DIR, OFFICIAL_CONTACTS_PATH, CAMPAIGNS_DIR, SEGMENTS_DIR,
    CFG_KEY_HIDE_CONTACTS_IMPORT_POPUP,
    load_config, save_config, safe_read_csv_rows, merge_tokens, normalize_text,
    _open_folder_in_explorer, _open_file_location,
    detect_and_convert_contacts_to_official
)

# Import core engine
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import funnelforge_core as fourdrip_core
fourdrip_core = importlib.reload(fourdrip_core)

# Outlook (for "Send Test Emails" and "Cancel Pending")
try:
    import win32com.client as win32  # type: ignore
except Exception:
    win32 = None

# =========================
# GUI Components
# =========================

# -----------------------
# Tooltip
# -----------------------

class ToolTip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            bg="#020617",
            fg=FG_TEXT,
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
            padx=8,
            pady=4,
        )
        label.pack()

    def _hide(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


# -----------------------
# Auto-hide scrollbar
# -----------------------

class AutoHideVScrollbar(ttk.Scrollbar):
    """A ttk vertical scrollbar that hides itself when not needed."""
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self._is_packed = False

    def set(self, first, last):
        first_f = float(first)
        last_f = float(last)

        if first_f <= 0.0 and last_f >= 1.0:
            if self._is_packed:
                self.pack_forget()
                self._is_packed = False
        else:
            if not self._is_packed:
                self.pack(side="right", fill="y")
                self._is_packed = True

        super().set(first, last)


# =========================
# Contacts Preview Window
# =========================

class ContactsTableWindow(tk.Toplevel):
    def __init__(self, parent, contacts_path: str):
        super().__init__(parent)
        self.title("Final Contact List")
        self.configure(bg=BG_ROOT)
        self.geometry("980x640")

        top = tk.Frame(self, bg=BG_ROOT)
        top.pack(fill="x", padx=14, pady=(14, 10))

        tk.Label(top, text="Final Contact List", bg=BG_ROOT, fg=ACCENT,
                 font=("Segoe UI Semibold", 15)).pack(anchor="w")
        tk.Label(
            top,
            text=contacts_path,
            bg=BG_ROOT,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))

        search_row = tk.Frame(self, bg=BG_ROOT)
        search_row.pack(fill="x", padx=14, pady=(0, 10))

        tk.Label(search_row, text="Search:", bg=BG_ROOT, fg=FG_TEXT,
                 font=("Segoe UI", 10)).pack(side="left")
        self.search_var = tk.StringVar(value="")
        ent = tk.Entry(
            search_row,
            textvariable=self.search_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
        )
        ent.pack(side="left", fill="x", expand=True, padx=(8, 8))
        tk.Button(
            search_row,
            text="Clear",
            command=lambda: self.search_var.set(""),
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            padx=10,
            pady=6,
            cursor="hand2",
        ).pack(side="left")

        box = tk.Frame(self, bg=BG_CARD, highlightbackground=ACCENT_2, highlightthickness=1)
        box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)

        tree_frame = tk.Frame(box, bg=BG_CARD)
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self._rows: List[Dict[str, str]] = []
        self._headers: List[str] = []
        self.contacts_path = contacts_path

        self._load_contacts()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())

    def _sanitize_columns(self, headers: List[str]) -> Tuple[str, ...]:
        clean_cols: List[str] = []
        seen = set()
        for c in headers:
            if c is None:
                continue
            c = str(c).strip()
            if not c:
                continue
            if c.lower() == "phone":
                continue
            if c in seen:
                continue
            seen.add(c)
            clean_cols.append(c)

        if not clean_cols:
            clean_cols = list(CONTACT_FIELDS)

        return tuple(clean_cols)

    def _load_contacts(self):
        if not self.contacts_path or not os.path.isfile(self.contacts_path):
            messagebox.showerror("Missing", "Official contacts.csv not found.")
            return

        try:
            rows, headers = safe_read_csv_rows(self.contacts_path)
        except Exception as e:
            messagebox.showerror("Read error", f"Could not read contacts.csv:\n{e}")
            return

        self._rows = rows
        self._headers = list(headers) if headers else list(CONTACT_FIELDS)

        cols = self._sanitize_columns(self._headers)

        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = cols

        for col in cols:
            self.tree.heading(col, text=col)
            w = 150
            if col.lower() == "email":
                w = 260
            elif col.lower() == "company":
                w = 220
            self.tree.column(col, width=w, stretch=True, anchor="w")

        for r in rows:
            values = []
            for col in cols:
                v = r.get(col)
                if v is None:
                    v = r.get(col.strip())
                values.append("" if v is None else str(v))
            self.tree.insert("", "end", values=values)

    def _apply_filter(self):
        q = self.search_var.get().strip().lower()
        cols = self.tree["columns"]
        self.tree.delete(*self.tree.get_children())

        for r in self._rows:
            blob = " ".join([str(r.get(h, "") or "") for h in self._headers]).lower()
            if q and q not in blob:
                continue

            values = []
            for col in cols:
                v = r.get(col)
                if v is None:
                    v = r.get(col.strip())
                values.append("" if v is None else str(v))
            self.tree.insert("", "end", values=values)


# =========================
# Attachment Manager (per-email)
# =========================

class AttachmentManagerWindow(tk.Toplevel):
    def __init__(self, parent, email_label: str, files: List[str], on_update):
        super().__init__(parent)
        self.title(f"Manage Attachments – {email_label}")
        self.configure(bg=BG_ROOT)
        self.geometry("760x420")
        self.resizable(True, True)

        self._files = files  # reference to the list (mutated in-place)
        self._on_update = on_update

        top = tk.Frame(self, bg=BG_ROOT)
        top.pack(fill="x", padx=14, pady=(14, 10))

        tk.Label(
            top,
            text=f"Manage Attachments – {email_label}",
            bg=BG_ROOT,
            fg=ACCENT,
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w")

        tk.Label(
            top,
            text="Add files, remove selected, or clear all attachments for this email.",
            bg=BG_ROOT,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))

        main = tk.Frame(self, bg=BG_ROOT)
        main.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        box = tk.Frame(main, bg=BG_CARD, highlightbackground=ACCENT_2, highlightthickness=1)
        box.grid(row=0, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        inner = tk.Frame(box, bg=BG_CARD)
        inner.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            inner,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            selectbackground=ACCENT_2,
            selectforeground=FG_TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            activestyle="none",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(inner, orient="vertical", command=self.listbox.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=vsb.set)

        btn_row = tk.Frame(main, bg=BG_ROOT)
        btn_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        tk.Button(
            btn_row,
            text="Add files",
            command=self._add_files,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(side="left")

        tk.Button(
            btn_row,
            text="Remove selected",
            command=self._remove_selected,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            btn_row,
            text="Clear all",
            command=self._clear_all,
            bg="#7F1D1D",
            fg=FG_TEXT,
            activebackground="#991B1B",
            activeforeground=FG_TEXT,
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            btn_row,
            text="Open file location",
            command=self._open_location,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            btn_row,
            text="Close",
            command=self.destroy,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            padx=14,
            pady=7,
            cursor="hand2",
        ).pack(side="right")

        self._refresh_list()

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for fp in self._files:
            self.listbox.insert("end", fp)

    def _notify_update(self):
        try:
            self._on_update()
        except Exception:
            pass

    def _add_files(self):
        files = filedialog.askopenfilenames(title="Select attachments")
        if not files:
            return

        existing = set(self._files)
        added = 0
        for fp in files:
            if fp and fp not in existing:
                self._files.append(fp)
                existing.add(fp)
                added += 1

        if added:
            self._refresh_list()
            self._notify_update()

    def _remove_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            messagebox.showinfo("No selection", "Select a file to remove.")
            return

        for idx in sorted(sel, reverse=True):
            try:
                del self._files[idx]
            except Exception:
                pass

        self._refresh_list()
        self._notify_update()

    def _clear_all(self):
        if not self._files:
            return
        ok = messagebox.askyesno("Clear all", "Remove all attachments for this email?")
        if not ok:
            return
        self._files.clear()
        self._refresh_list()
        self._notify_update()

    def _open_location(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("No selection", "Select a file first.")
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._files):
            return
        _open_file_location(self._files[idx])


# =========================
# One-time Contacts Imported popup
# =========================

class OneTimeContactsImportedDialog(tk.Toplevel):
    def __init__(self, parent, on_done):
        super().__init__(parent)
        self.title("Contacts Imported")
        self.configure(bg=BG_ROOT)
        self.resizable(False, False)

        self._on_done = on_done
        self.dont_show_var = tk.BooleanVar(value=False)

        tk.Label(
            self,
            text="Contacts Imported",
            bg=BG_ROOT,
            fg=ACCENT,
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w", padx=16, pady=(14, 8))

        msg = (
            "Funnel Forge copied your file into its official Contacts folder and will always use that version going forward.\n\n"
            "To make edits, replace the file using Import Contacts."
        )
        tk.Label(
            self,
            text=msg,
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
            justify="left",
            wraplength=520,
        ).pack(anchor="w", padx=16, pady=(0, 12))

        ck = tk.Checkbutton(
            self,
            text="Don’t show this again",
            variable=self.dont_show_var,
            bg=BG_ROOT,
            fg=FG_TEXT,
            activebackground=BG_ROOT,
            activeforeground=FG_WHITE,
            selectcolor=BG_ENTRY,
        )
        ck.pack(anchor="w", padx=16, pady=(0, 12))

        btn_row = tk.Frame(self, bg=BG_ROOT)
        btn_row.pack(fill="x", padx=16, pady=(0, 14))

        tk.Button(
            btn_row,
            text="OK",
            command=self._close,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
        ).pack(side="right")

        self.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw // 2) - (w // 2)
        y = py + (ph // 2) - (h // 2)
        self.geometry(f"+{x}+{y}")

    def _close(self):
        try:
            self._on_done(bool(self.dont_show_var.get()))
        except Exception:
            pass
        self.destroy()


# =========================
# GUI App
# =========================

class FunnelForgeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Funnel Forge – Automated Email Engine")

        try:
            self.iconbitmap(resource_path("assets", "funnelforge.ico"))
        except Exception:
            pass

        self.configure(bg=BG_ROOT)
        self.geometry("1180x800")
        self.minsize(980, 620)

        # NEW: Load watermark and banner images once at startup
        try:
            watermark_path = resource_path("assets", "fnnl_forge_watermark.png")
            watermark_img = Image.open(watermark_path)
            # Store original for later resizing
            self.watermark_original = watermark_img
            self.watermark_photo = None  # Will be created when we know canvas size
        except Exception as e:
            print(f"Could not load watermark: {e}")
            self.watermark_original = None
            self.watermark_photo = None

        try:
            banner_path = resource_path("assets", "fnnl_forge_banner.png")
            banner_img = Image.open(banner_path)
            # Resize banner to fit window width (e.g., 1180px wide, maintain aspect ratio)
            banner_height = int((banner_img.height / banner_img.width) * 1180)
            banner_resized = banner_img.resize((1180, banner_height), RESAMPLE_LANCZOS)
            self.banner_photo = ImageTk.PhotoImage(banner_resized)
        except Exception as e:
            print(f"Could not load banner: {e}")
            self.banner_photo = None


        # Dynamic timezone label (informational)
        self.tz_label = datetime.now().astimezone().tzname() or "local time"

        ensure_dir(CONTACTS_DIR)
        if not os.path.exists(OFFICIAL_CONTACTS_PATH):
            with open(OFFICIAL_CONTACTS_PATH, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=CONTACT_FIELDS)
                w.writeheader()

        # Data
        self.name_vars: List[tk.StringVar] = []
        self.subject_vars: List[tk.StringVar] = []
        self.body_texts: List[tk.Text] = []
        self.date_vars: List[tk.StringVar] = []
        self.time_vars: List[tk.StringVar] = []

        # Per-email attachments
        self.per_email_attachments: List[List[str]] = []
        self.per_email_manage_btns: List[tk.Button] = []

        # Contacts always points to OFFICIAL file
        self.contacts_path_var = tk.StringVar(value=OFFICIAL_CONTACTS_PATH)

        self.test_email_var = tk.StringVar(value="")
        self.cancel_query_var = tk.StringVar(value="")
        self.cancel_mode_var = tk.StringVar(value="email")  # email | domain

        # Campaign selector
        self.campaign_selector_var = tk.StringVar(value="-- Start Fresh --")
        self.campaign_selector = None  # Will be set when UI is built

        # Contact Lists main screen
        self.contact_lists_dropdown_var = tk.StringVar(value="")
        self.contact_lists_table = None  # Treeview widget for displaying contacts

        # Choose contact list screen state
        self.contact_lists: Dict[str, str] = {}  # map list name → full csv path
        self.selected_contact_list_var = tk.StringVar(value="")
        self.contact_list_info_var = tk.StringVar(value="No list selected")

        # Templates
        self.template_var = tk.StringVar(value="None")
        self._ensure_templates_dir()

        # Status pulse timer
        self._status_reset_after_id: Optional[str] = None

        # Rebuild debouncing
        self._rebuilding_sequence_table = False
        self._rebuild_pending_after_id: Optional[str] = None
        self._schedule_rebuild_after_id: Optional[str] = None

        # Screens + nav tracking
        self._nav_buttons: Dict[str, tk.Button] = {}
        self._screens: Dict[str, tk.Frame] = {}
        self._active_nav: Optional[str] = None

        self._build_styles()
        self._build_header()
        self._build_nav_and_content()
        self._build_status_bar()

        # DISABLED: Always start clean, never load previous session
        # self._load_existing_config()
        self._force_clean_startup()

    # -------------------------------
    # Styles
    # -------------------------------
    def _build_styles(self):
        """Configure TTK styles for professional light theme"""
        style = ttk.Style()
        style.theme_use("clam")

        # Card frames (white with shadow effect via border)
        style.configure(
            "Card.TFrame",
            background=BG_CARD,
            relief="flat",
            borderwidth=1,
            bordercolor=BORDER
        )

        # Notebook (tabs)
        style.configure(
            "TNotebook",
            background=BG_ROOT,
            borderwidth=0
        )
        style.configure(
            "TNotebook.Tab",
            background=BG_CARD,
            foreground=FG_TEXT,
            padding=[16, 10],
            borderwidth=1,
            relief="flat"
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_CARD), ("!selected", BG_ROOT)],
            foreground=[("selected", ACCENT), ("!selected", FG_MUTED)],
            expand=[("selected", [1, 1, 1, 0])]
        )

        # Combobox (dropdowns)
        style.configure(
            "Dark.TCombobox",
            fieldbackground=BG_ENTRY,
            background=BG_ENTRY,
            foreground=FG_TEXT,
            arrowcolor=ACCENT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            borderwidth=1,
            relief="flat"
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", BG_ENTRY)],
            selectbackground=[("readonly", BG_ENTRY)],
            selectforeground=[("readonly", FG_TEXT)]
        )

        # Treeview (tables) - Clean light theme
        style.configure(
            "Treeview",
            background=BG_CARD,
            foreground=FG_TEXT,
            fieldbackground=BG_CARD,
            borderwidth=0,
            rowheight=32
        )
        style.configure(
            "Treeview.Heading",
            background=BG_ROOT,
            foreground=FG_TEXT,
            relief="flat",
            font=("Segoe UI Semibold", 10),
            padding=12,
            borderwidth=1
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT_LIGHT)],
            foreground=[("selected", FG_TEXT)]
        )
        style.map(
            "Treeview.Heading",
            background=[("active", BG_HOVER)]
        )

        # Scrollbar - Modern minimal style
        style.configure(
            "Vertical.TScrollbar",
            background=BORDER_SOFT,
            troughcolor=BG_ROOT,
            borderwidth=0,
            arrowsize=12
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", BORDER_MEDIUM)]
        )

    def _build_header(self):
        """Build top banner with image"""
        # NEW: top banner image
        if self.banner_photo:
            # Create banner frame at the very top
            banner_frame = tk.Frame(self, bg=BG_ROOT)
            banner_frame.pack(fill="x", side="top")

            banner_label = tk.Label(
                banner_frame,
                image=self.banner_photo,
                bg=BG_ROOT,
                borderwidth=0
            )
            banner_label.pack()
        else:
            # Fallback: minimal header if banner image not found
            header = tk.Frame(self, bg=BG_HEADER, height=70)
            header.pack(fill="x", side="top")
            header.pack_propagate(False)

            left_section = tk.Frame(header, bg=BG_HEADER)
            left_section.pack(side="left", padx=24, pady=16)

            tk.Label(
                left_section,
                text="FUNNEL FORGE",
                bg=BG_HEADER,
                fg=FG_WHITE,
                font=("Segoe UI", 18, "bold"),
            ).pack(side="left")

        def _build_nav_and_content(self):
        shell = tk.Frame(self, bg=BG_ROOT)
        shell.pack(side="top", fill="both", expand=True, padx=0, pady=(0, 16))
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        # Sidebar
        sidebar = tk.Frame(shell, bg=BG_SIDEBAR, width=190)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        tk.Label(
            sidebar,
            text="Funnel Forge",
            bg=BG_SIDEBAR,
            fg=ACCENT,
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w", padx=16, pady=(10, 4))

        tk.Label(
            sidebar,
            text="Automated email engine",
            bg=BG_SIDEBAR,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=16, pady=(0, 12))

        def _nav_button(text: str, key: str):
            btn = tk.Button(
                sidebar,
                text=text,
                anchor="w",
                command=lambda k=key: self._show_screen(k),
                bg=BG_SIDEBAR,
                fg=FG_TEXT,
                activebackground=BG_ENTRY,
                activeforeground=FG_WHITE,
                relief="flat",
                padx=16,
                pady=6,
                cursor="hand2",
                font=("Segoe UI", 10),
            )
            btn.pack(fill="x")
            self._nav_buttons[key] = btn

        def _sub_nav_button(text: str, key: str):
            btn = tk.Button(
                sidebar,
                text="    • " + text,
                anchor="w",
                command=lambda k=key: self._show_screen(k),
                bg=BG_SIDEBAR,
                fg=FG_TEXT,
                activebackground=BG_ENTRY,
                activeforeground=FG_WHITE,
                relief="flat",
                padx=16,
                pady=4,
                cursor="hand2",
                font=("Segoe UI", 9),
            )
            btn.pack(fill="x")
            self._nav_buttons[key] = btn

        _nav_button("Dashboard", "dashboard")
        _nav_button("Create a campaign", "campaign")
        _sub_nav_button("Build Emails", "build")
        _sub_nav_button("Choose Contacts", "contacts")
        _sub_nav_button("Set Schedule", "sequence")
        _sub_nav_button("Preview and Launch", "execute")
        _nav_button("Contact Lists", "contact_lists_main")

        tk.Label(sidebar, text="", bg=BG_SIDEBAR).pack(expand=True, fill="y")

        tk.Label(
            sidebar,
            text=f"Version {APP_VERSION}",
            bg=BG_SIDEBAR,
            fg=FG_MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=16, pady=(0, 2))

        tk.Label(
            sidebar,
            text="MV build",
            bg=BG_SIDEBAR,
            fg=FG_MUTED,
            font=("Segoe UI", 8, "italic"),
        ).pack(anchor="w", padx=16, pady=(0, 8))

        # Content stack
        content_stack = tk.Frame(shell, bg=BG_ROOT)
        content_stack.grid(row=0, column=1, sticky="nsew")
        content_stack.rowconfigure(0, weight=1)
        content_stack.columnconfigure(0, weight=1)

        # NEW: watermark background - add canvas behind all content
        if self.watermark_original:
            watermark_canvas = tk.Canvas(
                content_stack,
                bg=BG_ROOT,
                highlightthickness=0,
                borderwidth=0
            )
            watermark_canvas.grid(row=0, column=0, sticky="nsew")

            # Function to update watermark on resize
            def update_watermark(event=None):
                try:
                    if not self.watermark_original:
                        return

                    w = watermark_canvas.winfo_width()
                    h = watermark_canvas.winfo_height()

                    if w <= 1 or h <= 1:
                        return

                    # Resize watermark to fit nicely in center (e.g., 40% of canvas size)
                    scale = 0.4
                    wm_width = int(w * scale)
                    wm_height = int((self.watermark_original.height / self.watermark_original.width) * wm_width)

                    watermark_resized = self.watermark_original.resize((wm_width, wm_height), RESAMPLE_LANCZOS)
                    self.watermark_photo = ImageTk.PhotoImage(watermark_resized)

                    # Clear and redraw
                    watermark_canvas.delete("all")
                    watermark_canvas.create_image(
                        w // 2, h // 2,
                        image=self.watermark_photo,
                        anchor="center"
                    )
                except Exception as e:
                    print(f"Error updating watermark: {e}")

            # Bind resize event
            watermark_canvas.bind("<Configure>", update_watermark)

            # Initial draw
            self.after(100, update_watermark)


        self._screens["dashboard"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["dashboard"].grid(row=0, column=0, sticky="nsew")
        self._build_dashboard_screen(self._screens["dashboard"])

        self._screens["campaign"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["campaign"].grid(row=0, column=0, sticky="nsew")
        self._build_create_campaign_screen(self._screens["campaign"])

        self._screens["build"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["build"].grid(row=0, column=0, sticky="nsew")
        self._build_build_emails_screen(self._screens["build"])

        try:
            print("DEBUG: Creating sequence screen...")
            self._screens["sequence"] = tk.Frame(content_stack, bg=BG_ROOT)
            self._screens["sequence"].grid(row=0, column=0, sticky="nsew")
            self._build_sequence_screen(self._screens["sequence"])
            print("[OK] Sequence screen created successfully")
        except Exception as e:
            print(f"[ERROR] creating sequence screen: {e}")
            import traceback
            traceback.print_exc()

        print("DEBUG: About to create contacts screen...")
        try:
            self._screens["contacts"] = tk.Frame(content_stack, bg=BG_ROOT)
            self._screens["contacts"].grid(row=0, column=0, sticky="nsew")
            self._build_contacts_only_screen(self._screens["contacts"])
            print("[OK] Contacts screen created successfully")
        except Exception as e:
            print(f"[ERROR] creating contacts screen: {e}")
            import traceback
            traceback.print_exc()

        # Preview/Execute Campaign screen
        print("DEBUG: About to create execute screen...")
        try:
            self._screens["execute"] = tk.Frame(content_stack, bg=BG_ROOT)
            self._screens["execute"].grid(row=0, column=0, sticky="nsew")
            self._build_execute_screen(self._screens["execute"])
            print("[OK] Execute screen created successfully")
        except Exception as e:
            print(f"[ERROR] creating execute screen: {e}")
            import traceback
            traceback.print_exc()

        # self._screens["preview"] = tk.Frame(content_stack, bg=BG_ROOT)
        # self._screens["preview"].grid(row=0, column=0, sticky="nsew")
        # self._build_preview_screen(self._screens["preview"])

        self._screens["cancel"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["cancel"].grid(row=0, column=0, sticky="nsew")
        self._build_cancel_screen(self._screens["cancel"])

        # Contact Lists main screen
        self._screens["contact_lists_main"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["contact_lists_main"].grid(row=0, column=0, sticky="nsew")
        self._build_contact_lists_main_screen(self._screens["contact_lists_main"])

        self._content_stack = content_stack

        # Default screen
        self._show_screen("dashboard")

    def _update_nav_styles(self):
        for key, btn in self._nav_buttons.items():
            if key == self._active_nav:
                btn.configure(bg=BG_ENTRY, fg=ACCENT)
            else:
                btn.configure(bg=BG_SIDEBAR, fg=FG_TEXT)

    def _show_screen(self, key: str):
        print(f"DEBUG: Trying to show screen: {key}")

        # Use the key directly (no aliases needed)
        screen_key = key

        frame = self._screens.get(screen_key)
        if frame is None:
            print(f"DEBUG: Frame is None! Key={key}, Screen key={screen_key}, Available screens={list(self._screens.keys())}")
            return

        # Hide all screens first using grid_remove()
        for screen_key_iter, screen_frame in self._screens.items():
            screen_frame.grid_remove()
        print(f"DEBUG: Successfully showed screen: {screen_key}")

        # Show only the selected screen
        frame.grid(row=0, column=0, sticky="nsew")

        self._active_nav = key
        self._update_nav_styles()
        
        # Soft status for navigation
        if key == "dashboard":
            self._set_status("Viewing dashboard", GOOD)
            # Refresh active campaigns when showing dashboard
            if hasattr(self, '_refresh_active_campaigns'):
                self._refresh_active_campaigns()
        elif key == "campaign":
            self._set_status("Create a campaign", GOOD)
        elif key == "build":
            self._set_status("Editing emails only", GOOD)
        elif key == "sequence":
            self._set_status("Customizing sequence", GOOD)
        elif key == "contacts":
            self._set_status("Managing contact list", GOOD)
        elif key == "execute":
            self._set_status("Ready to execute campaign", GOOD)
        elif key == "preview":
            self._set_status("Previewing test emails", GOOD)
        elif key == "cancel":
            self._set_status("Cancelling pending emails", WARN)


    # ============================================
    # Create a campaign main page
    # ============================================
    def _build_create_campaign_screen(self, parent):
        """Create a campaign main informational page"""
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=40, pady=30)
        wrapper.columnconfigure(0, weight=1)

        # Main heading
        tk.Label(
            wrapper,
            text="Create a campaign",
            bg=BG_ROOT,
            fg=ACCENT,
            font=("Segoe UI Semibold", 22),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        # Subheading
        tk.Label(
            wrapper,
            text="Build smart, multi-touch email sequences that follow up for you while you work on higher-value tasks.",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 12),
            wraplength=900,
            justify="left"
        ).grid(row=1, column=0, sticky="w", pady=(0, 20))

        # Introduction paragraph
        tk.Label(
            wrapper,
            text="A campaign in Funnel Forge is a scheduled sequence of emails sent to a specific contact list.\nStart by shaping your message, then choose who it goes to, when it's delivered, and what attachments go with each touch.",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
            wraplength=900,
            justify="left"
        ).grid(row=2, column=0, sticky="w", pady=(0, 30))

        # Section: How campaigns work
        tk.Label(
            wrapper,
            text="How campaigns work in Funnel Forge",
            bg=BG_ROOT,
            fg=ACCENT,
            font=("Segoe UI Semibold", 15),
        ).grid(row=3, column=0, sticky="w", pady=(0, 15))

        # Step 1
        tk.Label(
            wrapper,
            text="1. Build your emails",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI Semibold", 11),
        ).grid(row=4, column=0, sticky="w", pady=(0, 5))

        tk.Label(
            wrapper,
            text="Craft each touch with its own subject line, body, and optional attachments. Add or remove emails until the sequence matches how you actually sell.",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
            wraplength=900,
            justify="left"
        ).grid(row=5, column=0, sticky="w", pady=(0, 15))

        # Step 2
        tk.Label(
            wrapper,
            text="2. Choose your contact list",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI Semibold", 11),
        ).grid(row=6, column=0, sticky="w", pady=(0, 5))

        tk.Label(
            wrapper,
            text="Import or select a saved contact list. Funnel Forge cleans up the data, maps common headers, and shows you exactly who will receive this campaign before you launch.",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
            wraplength=900,
            justify="left"
        ).grid(row=7, column=0, sticky="w", pady=(0, 15))

        # Step 3
        tk.Label(
            wrapper,
            text="3. Set Schedule",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI Semibold", 11),
        ).grid(row=8, column=0, sticky="w", pady=(0, 5))

        tk.Label(
            wrapper,
            text="Pick send dates and times for each email in the sequence. Scheduling uses your local computer time so you always know exactly when touches will go out.",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
            wraplength=900,
            justify="left"
        ).grid(row=9, column=0, sticky="w", pady=(0, 15))

        # Step 4
        tk.Label(
            wrapper,
            text="4. Preview and Launch",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI Semibold", 11),
        ).grid(row=10, column=0, sticky="w", pady=(0, 5))

        tk.Label(
            wrapper,
            text="Send previews to yourself, double-check merge fields and attachments, then execute the campaign. Funnel Forge runs the play while you move on to the next deal.",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
            wraplength=900,
            justify="left"
        ).grid(row=11, column=0, sticky="w", pady=(0, 30))

        # Section: Quick start checklist
        tk.Label(
            wrapper,
            text="Quick start checklist",
            bg=BG_ROOT,
            fg=ACCENT,
            font=("Segoe UI Semibold", 15),
        ).grid(row=12, column=0, sticky="w", pady=(0, 15))

        # Step 1 checklist
        tk.Label(
            wrapper,
            text="Step 1 – Customize your sequence",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI Semibold", 11),
        ).grid(row=13, column=0, sticky="w", pady=(0, 5))

        checklist_1 = "• Click Customize your sequence in the left navigation\n• Rename Email 1–4 (or add more)\n• Write subjects and bodies\n• Add or remove attachments"
        tk.Label(
            wrapper,
            text=checklist_1,
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
            wraplength=900,
            justify="left"
        ).grid(row=14, column=0, sticky="w", pady=(0, 15))

        # Step 2 checklist
        tk.Label(
            wrapper,
            text="Step 2 – Select your contact list",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI Semibold", 11),
        ).grid(row=15, column=0, sticky="w", pady=(0, 5))

        checklist_2 = "• Go to Contact Lists\n• Import or choose a saved list\n• Confirm name, email, and company fields"
        tk.Label(
            wrapper,
            text=checklist_2,
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
            wraplength=900,
            justify="left"
        ).grid(row=16, column=0, sticky="w", pady=(0, 15))

        # Step 3 checklist
        tk.Label(
            wrapper,
            text="Step 3 – Schedule & execute",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI Semibold", 11),
        ).grid(row=17, column=0, sticky="w", pady=(0, 5))

        checklist_3 = "• Return to Customize your sequence\n• Set send dates and times\n• Preview your full sequence\n• Click Execute campaign to launch"
        tk.Label(
            wrapper,
            text=checklist_3,
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
            wraplength=900,
            justify="left"
        ).grid(row=18, column=0, sticky="w", pady=(0, 30))

        # Footer message
        tk.Label(
            wrapper,
            text="You stay in control the whole time — Funnel Forge just handles the timing, follow-up, and consistency for you.",
            bg=BG_ROOT,
            fg=FG_MUTED,
            font=("Segoe UI", 10, "italic"),
            wraplength=900,
            justify="left"
        ).grid(row=19, column=0, sticky="w", pady=(0, 20))

    # ============================================
    # Dashboard screen
    # ============================================
    def _build_dashboard_screen(self, parent):
        """Dashboard with Active Campaigns and Cancel Sequences"""
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=16, pady=16)
        wrapper.columnconfigure(0, weight=1)

        # Welcome section
        welcome_card = ttk.Frame(wrapper, style="Card.TFrame")
        welcome_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        welcome_box = tk.Frame(welcome_card, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
        welcome_box.pack(fill="x", padx=12, pady=12)

        tk.Label(
            welcome_box,
            text=f"Welcome to Funnel Forge {APP_VERSION}",
            bg=BG_ENTRY,
            fg=ACCENT,
            font=("Segoe UI Semibold", 15),
        ).pack(anchor="w", padx=10, pady=(10, 4))

        tk.Label(
            welcome_box,
            text="Manage your email campaigns, track active sequences, and more.",
            bg=BG_ENTRY,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=10, pady=(0, 10))

        # Active Campaigns section
        self._build_active_campaigns_card(wrapper, row=1)

        # Cancel Sequences section  
        self._build_cancel_card_for_dashboard(wrapper, row=2)


    def _build_active_campaigns_card(self, parent, row=1):
        """Active campaigns display"""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 12))
        card.rowconfigure(1, weight=1)
        card.columnconfigure(0, weight=1)

        box = tk.Frame(card, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.rowconfigure(1, weight=1)
        box.columnconfigure(0, weight=1)

        tk.Label(
            box,
            text="Active Campaigns",
            bg=BG_ENTRY,
            fg=ACCENT,
            font=("Segoe UI Semibold", 13),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 8))

        # Scrollable frame for campaigns
        canvas = tk.Canvas(box, bg=BG_ENTRY, highlightthickness=0, height=200)
        canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        scrollbar = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        canvas.configure(yscrollcommand=scrollbar.set)

        campaigns_frame = tk.Frame(canvas, bg=BG_ENTRY)
        canvas_window = canvas.create_window((0, 0), window=campaigns_frame, anchor="nw")

        def _on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=event.width)

        campaigns_frame.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))

        self.active_campaigns_frame = campaigns_frame
        self._refresh_active_campaigns()

    def _build_cancel_card_for_dashboard(self, parent, row=2):
        """Cancel sequences section on dashboard"""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 8))

        box = tk.Frame(card, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
        box.pack(fill="x", padx=12, pady=12)

        tk.Label(
            box,
            text="Cancel Sequences",
            bg=BG_ENTRY,
            fg=ACCENT,
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w", padx=10, pady=(10, 4))

        tk.Label(
            box,
            text="Remove pending/scheduled emails from Outlook. Use email for singles, domain for companies.",
            bg=BG_ENTRY,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=10, pady=(0, 10))

        row_input = tk.Frame(box, bg=BG_ENTRY)
        row_input.pack(fill="x", padx=10, pady=(0, 10))

        tk.Label(row_input, text="Email/Domain:", bg=BG_ENTRY, fg=FG_TEXT, font=FONT_LABEL).pack(side="left")

        cancel_entry = tk.Entry(
            row_input,
            textvariable=self.cancel_query_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            highlightcolor=ACCENT,
        )
        cancel_entry.pack(side="left", fill="x", expand=True, padx=(10, 10))

        # Radio buttons
        row_radio = tk.Frame(box, bg=BG_ENTRY)
        row_radio.pack(fill="x", padx=10, pady=(0, 10))

        tk.Radiobutton(
            row_radio,
            text="Email",
            variable=self.cancel_mode_var,
            value="email",
            bg=BG_ENTRY,
            fg=FG_TEXT,
            selectcolor=BG_CARD,
            activebackground=BG_ENTRY,
            activeforeground=FG_TEXT,
            font=FONT_BASE,
        ).pack(side="left", padx=(0, 15))

        tk.Radiobutton(
            row_radio,
            text="Domain",
            variable=self.cancel_mode_var,
            value="domain",
            bg=BG_ENTRY,
            fg=FG_TEXT,
            selectcolor=BG_CARD,
            activebackground=BG_ENTRY,
            activeforeground=FG_TEXT,
            font=FONT_BASE,
        ).pack(side="left")

        tk.Button(
            box,
            text="Cancel + Delete",
            command=self._cancel_pending_emails,
            bg="#EF4444",
            fg=FG_TEXT,
            activebackground="#DC2626",
            activeforeground=FG_TEXT,
            relief="flat",
            font=("Segoe UI Semibold", 10),
            padx=16,
            pady=8,
            cursor="hand2",
        ).pack(padx=10, pady=(0, 10))

    def _refresh_active_campaigns(self):
        """Refresh the active campaigns list"""
        if not hasattr(self, 'active_campaigns_frame'):
            return

        # Clear existing
        for widget in self.active_campaigns_frame.winfo_children():
            widget.destroy()

        # Load active campaigns
        active_campaigns = self._get_active_campaigns()

        if not active_campaigns:
            tk.Label(
                self.active_campaigns_frame,
                text="No active campaigns. Create and run a campaign to see it here!",
                bg=BG_ENTRY,
                fg=FG_MUTED,
                font=("Segoe UI", 10, "italic"),
                pady=20
            ).pack()
            return

        # Display each campaign
        for camp in active_campaigns:
            self._create_campaign_widget(self.active_campaigns_frame, camp)

    def _create_campaign_widget(self, parent, campaign):
        """Create a widget displaying one campaign"""
        frame = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill="x", pady=5, padx=5)

        # Campaign name
        tk.Label(
            frame,
            text=campaign.get("name", "Unnamed Campaign"),
            bg=BG_CARD,
            fg=ACCENT,
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w", padx=12, pady=(10, 4))

        # Email count and contact count
        emails_count = len(campaign.get("emails", []))
        contact_count = campaign.get("contact_count", 0)
        
        info_text = f"{emails_count} emails • {contact_count} contacts"
        tk.Label(
            frame,
            text=info_text,
            bg=BG_CARD,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=12, pady=(0, 4))

        # Show email dates
        emails = campaign.get("emails", [])
        if emails:
            dates_text = "Email dates: "
            email_dates = []
            for email in emails:
                date = email.get("date", "")
                time = email.get("time", "")
                if date:
                    email_dates.append(f"{date} @ {time}")
            
            if email_dates:
                # Show first 3 dates, then "..."
                if len(email_dates) <= 3:
                    dates_text += ", ".join(email_dates)
                else:
                    dates_text += ", ".join(email_dates[:3]) + f" (+{len(email_dates)-3} more)"
                
                tk.Label(
                    frame,
                    text=dates_text,
                    bg=BG_CARD,
                    fg=FG_TEXT,
                    font=("Segoe UI", 9),
                    wraplength=350,
                    justify="left"
                ).pack(anchor="w", padx=12, pady=(0, 10))

    def _get_active_campaigns(self):
        """Get list of active campaigns from files"""
        try:
            campaigns = []
            if not CAMPAIGNS_DIR.exists():
                return campaigns

            for file in CAMPAIGNS_DIR.glob("*.json"):
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        camp = json.load(f)
                        if camp.get("status") == "active":
                            campaigns.append(camp)
                except:
                    continue

            # Sort by created date (newest first)
            campaigns.sort(key=lambda c: c.get("created_date", ""), reverse=True)
            return campaigns
        except:
            return []

    # ============================================
    # Scrollable "Build emails" screen
    # ============================================
    def _build_build_emails_screen(self, parent):
        container = tk.Frame(parent, bg=BG_ROOT)
        container.pack(side="top", fill="both", expand=True, padx=0, pady=0)

        self._canvas = tk.Canvas(container, bg=BG_ROOT, highlightthickness=0)
        self._canvas.pack(side="left", fill="both", expand=True)

        self._scrollbar = AutoHideVScrollbar(container, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self.main_frame = tk.Frame(self._canvas, bg=BG_ROOT)
        window_id = self._canvas.create_window((0, 0), window=self.main_frame, anchor="nw")

        def _sync_width(_event=None):
            if self._canvas is None or self.main_frame is None:
                return
            try:
                self._canvas.itemconfigure(window_id, width=self._canvas.winfo_width())
            except Exception:
                pass

        def _on_frame_configure(_event=None):
            if self._canvas is None:
                return
            try:
                self._canvas.configure(scrollregion=self._canvas.bbox("all"))
            except Exception:
                pass

        self.main_frame.bind("<Configure>", _on_frame_configure)
        self._canvas.bind("<Configure>", _sync_width)

        # Mousewheel (Windows)
        def _on_mousewheel(event):
            if hasattr(event, "delta") and event.delta and self._canvas is not None:
                try:
                    self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                except Exception:
                    pass

        def _bind_wheel(_e=None):
            self.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_wheel(_e=None):
            self.unbind_all("<MouseWheel>")

        self._canvas.bind("<Enter>", _bind_wheel)
        self._canvas.bind("<Leave>", _unbind_wheel)

        self._build_main_layout(self.main_frame)

    # ============================================
    # Create a campaign screen - sequence table + preview + create
    # ============================================
    def _build_sequence_screen(self, parent):
        """Set Schedule screen - shows only the schedule card"""
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=16, pady=16)
        wrapper.columnconfigure(0, weight=1)

        # Show only the sequence schedule card (no tabs, no top bar)
        self._build_schedule_card(wrapper, row=0)


    def _build_sequence_tab(self, parent):
        """Build the sequence tab content"""
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=8, pady=8)
        wrapper.columnconfigure(0, weight=1)
        
        self._build_schedule_card(wrapper, row=0)

    def _build_contacts_tab(self, parent):
        """Build the contacts tab content"""
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=8, pady=8)
        wrapper.columnconfigure(0, weight=1)
        
        self._build_contacts_card(wrapper, row=0)

    def _build_preview_run_tab(self, parent):
        """Build the preview & run tab content"""
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=8, pady=8)
        wrapper.columnconfigure(0, weight=1)
        
        # Preview section
        self._build_tools_card(wrapper, row=0, mode="preview_only")
        
        # Create/Run section
        self._build_tools_card(wrapper, row=1, mode="create_only")


    # ============================================
    # Campaign Management
    # ============================================
    def _get_saved_campaign_names(self):
        """Get list of saved campaign names"""
        try:
            names = ["-- Start Fresh --"]
            if not CAMPAIGNS_DIR.exists():
                return names

            for file in CAMPAIGNS_DIR.glob("*.json"):
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        camp = json.load(f)
                        names.append(camp.get("name", file.stem))
                except:
                    continue

            return names
        except:
            return ["-- Start Fresh --"]

    def _refresh_campaign_selector(self):
        """Refresh the campaign dropdown list"""
        if hasattr(self, 'campaign_selector') and self.campaign_selector is not None:
            self.campaign_selector['values'] = self._get_saved_campaign_names()
            try:
                self._set_status("Campaign list refreshed", GOOD)
            except:
                pass

    def _on_campaign_selected(self, event=None):
        """Load a campaign when selected from dropdown"""
        campaign_name = self.campaign_selector_var.get()
        
        if campaign_name == "-- Start Fresh --":
            return

        # Ask if they want to load (might lose current work)
        if not messagebox.askyesno(
            "Load Campaign",
            f"Load '{campaign_name}'?\n\nThis will replace your current work."
        ):
            self.campaign_selector_var.set("-- Start Fresh --")
            return

        # Load the campaign
        self._load_campaign_by_name(campaign_name)

    def _load_campaign_by_name(self, name):
        """Load a specific campaign by name"""
        try:
            # Find the campaign file
            campaign_file = None
            for file in CAMPAIGNS_DIR.glob("*.json"):
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        camp = json.load(f)
                        if camp.get("name") == name:
                            campaign_file = file
                            break
                except:
                    continue

            if not campaign_file:
                messagebox.showerror("Error", f"Could not find campaign: {name}")
                return

            # Load campaign data
            with open(campaign_file, "r", encoding="utf-8") as f:
                campaign = json.load(f)

            # Clear current emails
            for tab_id in self.email_notebook.tabs():
                try:
                    self.email_notebook.forget(tab_id)
                except:
                    pass

            self.name_vars = []
            self.subject_vars = []
            self.body_texts = []
            self.date_vars = []
            self.time_vars = []
            self.per_email_attachments = []

            # Load emails from campaign
            for email_data in campaign.get("emails", []):
                self._add_email(
                    name=email_data.get("name", ""),
                    subject=email_data.get("subject", ""),
                    body=email_data.get("body", ""),
                    date=email_data.get("date", ""),
                    time=email_data.get("time", "9:00 AM")
                )
                # Load attachments for this email
                if self.per_email_attachments:
                    self.per_email_attachments[-1] = email_data.get("attachments", [])

            self._rebuild_sequence_table()
            self._refresh_tab_labels()

            try:
                self._set_status(f"Loaded campaign: {name}", GOOD)
            except:
                pass

            messagebox.showinfo("Success", f"Campaign '{name}' loaded successfully!")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load campaign:\n{e}")

    def _save_current_campaign(self):
        """Save the current campaign"""
        # Ask for campaign name
        name = simpledialog.askstring(
            "Save Campaign",
            "Enter a name for this campaign:",
            parent=self
        )

        if not name or not name.strip():
            return

        name = name.strip()

        # Collect all current data
        campaign_data = {
            "name": name,
            "created_date": datetime.now().strftime("%Y-%m-%d"),
            "emails": [],
            "contact_count": self._count_contacts(),
            "status": "saved"  # Will be "active" when run
        }

        # Collect email data
        for i in range(len(self.subject_vars)):
            email_data = {
                "name": self.name_vars[i].get() if i < len(self.name_vars) else f"Email {i+1}",
                "subject": self.subject_vars[i].get(),
                "body": self.body_texts[i].get("1.0", "end").rstrip(),
                "date": self.date_vars[i].get(),
                "time": self.time_vars[i].get(),
                "attachments": self.per_email_attachments[i] if i < len(self.per_email_attachments) else []
            }
            campaign_data["emails"].append(email_data)

        # Save to file
        safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name)
        filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = CAMPAIGNS_DIR / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(campaign_data, f, indent=2)

            try:
                self._set_status(f"Campaign saved: {name}", GOOD)
            except:
                pass

            messagebox.showinfo("Success", f"Campaign '{name}' saved successfully!")

            # Refresh the dropdown
            self._refresh_campaign_selector()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save campaign:\n{e}")

    def _count_contacts(self):
        """Count contacts in the contacts file"""
        try:
            if not os.path.exists(OFFICIAL_CONTACTS_PATH):
                return 0
            rows, _ = safe_read_csv_rows(OFFICIAL_CONTACTS_PATH)
            return len(rows)
        except:
            return 0


    def _save_campaign_as_active(self, name):
        """Save campaign as active when run"""
        campaign_data = {
            "name": name,
            "created_date": datetime.now().strftime("%Y-%m-%d"),
            "emails": [],
            "contact_count": self._count_contacts(),
            "status": "active"
        }

        # Collect email data
        for i in range(len(self.subject_vars)):
            email_data = {
                "name": self.name_vars[i].get() if i < len(self.name_vars) else f"Email {i+1}",
                "subject": self.subject_vars[i].get(),
                "body": self.body_texts[i].get("1.0", "end").rstrip(),
                "date": self.date_vars[i].get(),
                "time": self.time_vars[i].get(),
                "attachments": self.per_email_attachments[i] if i < len(self.per_email_attachments) else []
            }
            campaign_data["emails"].append(email_data)

        # Save to file
        safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name)
        filename = f"active_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = CAMPAIGNS_DIR / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(campaign_data, f, indent=2)
        except:
            pass

    # ============================================
    # Contacts-only screen (Choose contact list)
    # ============================================
    def _build_contacts_only_screen(self, parent):
        """Choose contact list screen"""
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=40, pady=30)
        wrapper.columnconfigure(0, weight=1)

        # Title
        tk.Label(
            wrapper,
            text="Choose contact list",
            bg=BG_ROOT,
            fg=ACCENT,
            font=("Segoe UI Semibold", 22),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        # Subtitle
        tk.Label(
            wrapper,
            text="Import and manage contact lists for your campaigns",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 12),
        ).grid(row=1, column=0, sticky="w", pady=(0, 30))

        # Card for list selection
        card = tk.Frame(wrapper, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=2, column=0, sticky="ew", pady=(0, 20))
        card.columnconfigure(0, weight=1)

        # Card header
        tk.Label(
            card,
            text="Select a contact list",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_TITLE,
        ).grid(row=0, column=0, sticky="w", padx=CARD_INNER_PAD, pady=(CARD_INNER_PAD, 8))

        # Dropdown row
        dropdown_row = tk.Frame(card, bg=BG_CARD)
        dropdown_row.grid(row=1, column=0, sticky="ew", padx=CARD_INNER_PAD, pady=(0, 12))
        dropdown_row.columnconfigure(0, weight=1)

        tk.Label(
            dropdown_row,
            text="Select list:",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_LABEL,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        # Dropdown for selecting contact lists
        self.contact_list_selector_combo = ttk.Combobox(
            dropdown_row,
            textvariable=self.selected_contact_list_var,
            state="readonly",
            style="Dark.TCombobox",
            font=FONT_BASE,
        )
        self.contact_list_selector_combo.grid(row=1, column=0, sticky="ew", pady=(0, 0))
        self.contact_list_selector_combo.bind("<<ComboboxSelected>>", lambda e: self._on_contact_list_selected())

        # Button row
        btn_row = tk.Frame(card, bg=BG_CARD)
        btn_row.grid(row=2, column=0, sticky="ew", padx=CARD_INNER_PAD, pady=(0, CARD_INNER_PAD))

        # Import new list button
        tk.Button(
            btn_row,
            text="Import new list",
            command=self._import_new_contact_list,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            font=FONT_BUTTON,
            relief="flat",
            padx=BTN_PAD_X,
            pady=BTN_PAD_Y,
            cursor="hand2",
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
        ).pack(side="left", padx=(0, 8))

        # Save list button (replaces "Preview selected list")
        tk.Button(
            btn_row,
            text="Save list",
            command=self._save_selected_list_as_official,
            bg=SECONDARY,
            fg=FG_WHITE,
            font=FONT_BUTTON,
            relief="flat",
            padx=BTN_PAD_X,
            pady=BTN_PAD_Y,
            cursor="hand2",
            activebackground=SECONDARY_HOVER,
            activeforeground=FG_WHITE,
        ).pack(side="left")

        # Selected list info card with embedded table
        info_card = tk.Frame(wrapper, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        info_card.grid(row=3, column=0, sticky="nsew")
        info_card.columnconfigure(0, weight=1)
        wrapper.rowconfigure(3, weight=1)  # Make the info card expand

        # Info label
        info_label_frame = tk.Frame(info_card, bg=BG_CARD)
        info_label_frame.pack(fill="x", padx=CARD_INNER_PAD, pady=(CARD_INNER_PAD, 8))

        self.contact_list_info_label = tk.Label(
            info_label_frame,
            textvariable=self.contact_list_info_var,
            bg=BG_CARD,
            fg=FG_TEXT,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        self.contact_list_info_label.pack(side="left", fill="x", expand=True)

        # Embedded contacts table
        table_frame = tk.Frame(info_card, bg=BG_CARD)
        table_frame.pack(fill="both", expand=True, padx=CARD_INNER_PAD, pady=(0, CARD_INNER_PAD))

        # Create Treeview for contacts
        columns = ("Email", "FirstName", "LastName", "Company", "JobTitle")
        self.choose_contacts_table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=12,
        )

        # Configure columns
        self.choose_contacts_table.column("Email", width=220, anchor="w")
        self.choose_contacts_table.column("FirstName", width=120, anchor="w")
        self.choose_contacts_table.column("LastName", width=120, anchor="w")
        self.choose_contacts_table.column("Company", width=150, anchor="w")
        self.choose_contacts_table.column("JobTitle", width=150, anchor="w")

        # Configure headings
        for col in columns:
            self.choose_contacts_table.heading(col, text=col, anchor="w")

        # Add scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.choose_contacts_table.yview)
        self.choose_contacts_table.configure(yscrollcommand=scrollbar.set)

        # Pack table and scrollbar
        self.choose_contacts_table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Load contact lists on startup
        self._load_contact_lists_on_startup()

    # ============================================
    # Choose contact list helper methods
    # ============================================

    def _load_contact_lists_on_startup(self):
        """Scan Contacts folder for *.csv files (except contacts.csv) and populate dropdown"""
        self.contact_lists.clear()

        if not os.path.exists(CONTACTS_DIR):
            ensure_dir(CONTACTS_DIR)
            return

        # Scan for CSV files
        for filename in os.listdir(CONTACTS_DIR):
            if filename.endswith(".csv") and filename != "contacts.csv":
                list_name = os.path.splitext(filename)[0]
                full_path = os.path.join(CONTACTS_DIR, filename)
                self.contact_lists[list_name] = full_path

        # Update dropdown
        list_names = sorted(self.contact_lists.keys())
        if hasattr(self, 'contact_list_selector_combo'):
            self.contact_list_selector_combo['values'] = list_names

            # Select first list if available
            if list_names:
                self.selected_contact_list_var.set(list_names[0])
                self._on_contact_list_selected()
            else:
                self.selected_contact_list_var.set("")
                self.contact_list_info_var.set("No lists available. Click 'Import new list' to get started.")

    def _on_contact_list_selected(self):
        """Update info label and load contacts into table when a list is selected"""
        selected = self.selected_contact_list_var.get()

        # Clear table first
        if hasattr(self, 'choose_contacts_table'):
            for item in self.choose_contacts_table.get_children():
                self.choose_contacts_table.delete(item)

        if not selected or selected not in self.contact_lists:
            self.contact_list_info_var.set("No list selected")
            return

        # Get the path and count contacts
        list_path = self.contact_lists[selected]
        try:
            rows, _ = safe_read_csv_rows(list_path)
            count = len(rows)
            basename = os.path.basename(list_path)
            self.contact_list_info_var.set(f"Selected: {basename} — {count} contacts")

            # Load contacts into the embedded table
            if hasattr(self, 'choose_contacts_table'):
                for row in rows:
                    self.choose_contacts_table.insert("", "end", values=(
                        row.get("Email", ""),
                        row.get("FirstName", ""),
                        row.get("LastName", ""),
                        row.get("Company", ""),
                        row.get("JobTitle", "")
                    ))
        except Exception:
            self.contact_list_info_var.set(f"Selected: {selected} — Error reading file")

    def _import_new_contact_list(self):
        """Import new contact list with name dialog"""
        # 1. Open file picker
        src = filedialog.askopenfilename(
            title="Select contacts CSV to import",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not src:
            return

        # 2. Show name dialog
        default_name = os.path.splitext(os.path.basename(src))[0]
        name = simpledialog.askstring(
            "Name this contact list",
            "Name this list so you can re-use it later:",
            initialvalue=default_name,
            parent=self,
        )
        if not name or not name.strip():
            return

        name = name.strip()

        # 3. Sanitize filename
        safe_name = self._safe_list_filename(name)

        # 4. Create destination path with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_filename = f"{safe_name}_{timestamp}.csv"
        dest_path = os.path.join(CONTACTS_DIR, dest_filename)

        # 5. Convert and import
        try:
            count, warnings = detect_and_convert_contacts_to_official(src, dest_path)

            # 6. Add to dropdown
            self.contact_lists[safe_name] = dest_path
            list_names = sorted(self.contact_lists.keys())
            self.contact_list_selector_combo['values'] = list_names

            # 7. Select the new list
            self.selected_contact_list_var.set(safe_name)
            self._on_contact_list_selected()

            # 8. Update status
            self._set_status(f"Imported {count} contacts as '{name}'", GOOD)

            # 9. Show warnings if any
            if warnings:
                messagebox.showinfo(
                    "Import completed with notes",
                    "Import completed.\n\n" + "\n".join(f"• {w}" for w in warnings),
                )
        except Exception as e:
            _write_crash_log("contact_list_import")
            self._set_status("Import failed", DANGER)
            messagebox.showerror("Import failed", f"Could not import contacts:\n{e}")

    def _save_selected_list_as_official(self):
        """Save the selected list as the official contacts file"""
        selected = self.selected_contact_list_var.get()

        if not selected or selected not in self.contact_lists:
            messagebox.showerror("Error", "Select a contact list first.")
            return

        # Get the selected list's path
        src_path = self.contact_lists[selected]

        try:
            # Copy to OFFICIAL_CONTACTS_PATH
            shutil.copyfile(src_path, OFFICIAL_CONTACTS_PATH)

            # Update contacts_path_var if it exists
            if hasattr(self, 'contacts_path_var'):
                self.contacts_path_var.set(OFFICIAL_CONTACTS_PATH)

            # Count contacts for the message
            rows, _ = safe_read_csv_rows(OFFICIAL_CONTACTS_PATH)
            count = len(rows)

            # Update status
            self._set_status(f"Saved '{selected}' as official contact list", GOOD)

            # Show success message
            messagebox.showinfo(
                "Saved",
                f"Saved. This list ({count} contacts) is now the official contact list Funnel Forge will send to.",
            )
        except Exception as e:
            _write_crash_log("save_list_as_official")
            self._set_status("Save failed", DANGER)
            messagebox.showerror("Save failed", f"Could not save list:\n{e}")

    def _build_execute_screen(self, parent):
        """Preview/Execute Campaign screen"""
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=16, pady=16)
        wrapper.columnconfigure(0, weight=1)

        # Title card
        title_card = ttk.Frame(wrapper, style="Card.TFrame")
        title_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        title_box = tk.Frame(title_card, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1, relief="flat")
        title_box.pack(fill="x", padx=12, pady=12)

        tk.Label(
            title_box,
            text="Preview & Execute Campaign",
            bg=BG_CARD,
            fg=ACCENT,
            font=("Segoe UI Semibold", 15),
        ).pack(anchor="w", padx=10, pady=(10, 4))

        tk.Label(
            title_box,
            text="Test your emails and run your campaign when ready.",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=10, pady=(0, 10))

        # Preview section
        self._build_tools_card(wrapper, row=1, mode="preview_only")
        
        # Execute section
        self._build_tools_card(wrapper, row=2, mode="create_only")

    # ============================================
    # Preview-only screen
    # ============================================
    def _build_preview_screen(self, parent):
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=16, pady=16)
        wrapper.columnconfigure(0, weight=1)

        self._build_tools_card(wrapper, row=0, mode="preview_only")

    # ============================================
    # Cancel-only screen
    # ============================================
    def _build_cancel_screen(self, parent):
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=16, pady=16)
        wrapper.columnconfigure(0, weight=1)

        self._build_tools_card(wrapper, row=0, mode="cancel_only")

    # ============================================
    # Contact Lists Main Screen
    # ============================================
    def _build_contact_lists_main_screen(self, parent):
        """Main Contact Lists management screen with list selector and viewer"""
        # Scrollable container
        canvas = tk.Canvas(parent, bg=BG_ROOT, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg=BG_ROOT)

        scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=16, pady=16)
        scrollbar.pack(side="right", fill="y", pady=16)

        scrollable.columnconfigure(0, weight=1)

        # Title Card
        title_card = tk.Frame(scrollable, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        title_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_SPACING))
        title_card.columnconfigure(0, weight=1)

        tk.Label(
            title_card,
            text="Contact Lists",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_TITLE,
        ).pack(anchor="w", padx=CARD_INNER_PAD, pady=(CARD_INNER_PAD, 4))

        tk.Label(
            title_card,
            text="Manage your contact lists. Import new lists or view existing ones.",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=FONT_SUBTITLE,
        ).pack(anchor="w", padx=CARD_INNER_PAD, pady=(0, CARD_INNER_PAD))

        # Selection and Import Card
        controls_card = tk.Frame(scrollable, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        controls_card.grid(row=1, column=0, sticky="ew", pady=(0, SECTION_SPACING))
        controls_card.columnconfigure(0, weight=1)

        controls_inner = tk.Frame(controls_card, bg=BG_CARD)
        controls_inner.pack(fill="x", padx=CARD_INNER_PAD, pady=CARD_INNER_PAD)
        controls_inner.columnconfigure(0, weight=1)

        # Dropdown row
        dropdown_row = tk.Frame(controls_inner, bg=BG_CARD)
        dropdown_row.grid(row=0, column=0, sticky="ew", pady=(0, PAD_MD))
        dropdown_row.columnconfigure(1, weight=1)

        tk.Label(
            dropdown_row,
            text="Select list:",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_LABEL,
        ).grid(row=0, column=0, sticky="w", padx=(0, PAD_MD))

        self.contact_lists_dropdown = ttk.Combobox(
            dropdown_row,
            textvariable=self.contact_lists_dropdown_var,
            state="readonly",
            width=50,
            style="Dark.TCombobox"
        )
        self.contact_lists_dropdown.grid(row=0, column=1, sticky="ew")
        self.contact_lists_dropdown.bind("<<ComboboxSelected>>", self._on_contact_list_main_selected)

        # Import button
        btn_import = tk.Button(
            dropdown_row,
            text="Import new list...",
            command=self._import_new_contact_list_main,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            font=FONT_BUTTON,
            relief="flat",
            cursor="hand2",
            padx=BTN_PAD_X,
            pady=BTN_PAD_Y,
        )
        btn_import.grid(row=0, column=2, sticky="e", padx=(PAD_MD, 0))

        # Table Card
        table_card = tk.Frame(scrollable, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        table_card.grid(row=2, column=0, sticky="nsew")
        table_card.columnconfigure(0, weight=1)
        table_card.rowconfigure(0, weight=1)
        scrollable.rowconfigure(2, weight=1)

        # Table header
        tk.Label(
            table_card,
            text="Contacts",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_FIELD_HDR,
        ).pack(anchor="w", padx=CARD_INNER_PAD, pady=(CARD_INNER_PAD, PAD_SM))

        # Table frame
        table_frame = tk.Frame(table_card, bg=BG_CARD)
        table_frame.pack(fill="both", expand=True, padx=CARD_INNER_PAD, pady=(0, CARD_INNER_PAD))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # Create Treeview table
        self.contact_lists_table = ttk.Treeview(
            table_frame,
            columns=("Email", "FirstName", "LastName", "Company", "JobTitle"),
            show="headings",
            height=20
        )

        # Configure columns
        self.contact_lists_table.heading("Email", text="Email")
        self.contact_lists_table.heading("FirstName", text="First Name")
        self.contact_lists_table.heading("LastName", text="Last Name")
        self.contact_lists_table.heading("Company", text="Company")
        self.contact_lists_table.heading("JobTitle", text="Job Title")

        self.contact_lists_table.column("Email", width=250, anchor="w")
        self.contact_lists_table.column("FirstName", width=150, anchor="w")
        self.contact_lists_table.column("LastName", width=150, anchor="w")
        self.contact_lists_table.column("Company", width=200, anchor="w")
        self.contact_lists_table.column("JobTitle", width=180, anchor="w")

        # Scrollbars for table
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.contact_lists_table.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.contact_lists_table.xview)
        self.contact_lists_table.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.contact_lists_table.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Populate dropdown with existing contact lists
        self._refresh_contact_lists_main_dropdown()

    def _refresh_contact_lists_main_dropdown(self):
        """Populate the Contact Lists main screen dropdown with all available CSV files"""
        ensure_dir(CONTACTS_DIR)
        items = []

        for fn in os.listdir(CONTACTS_DIR):
            if not fn.lower().endswith(".csv"):
                continue
            full_path = os.path.join(CONTACTS_DIR, fn)
            base_name = os.path.splitext(fn)[0]

            # Mark the official file
            if os.path.normpath(full_path) == os.path.normpath(OFFICIAL_CONTACTS_PATH):
                label = f"Official – {base_name}"
            else:
                label = base_name

            items.append(label)

        # Sort by name
        items.sort()

        if hasattr(self, 'contact_lists_dropdown'):
            self.contact_lists_dropdown['values'] = items
            if items:
                self.contact_lists_dropdown.set(items[0])
                self._load_contacts_into_main_table(items[0])

    def _on_contact_list_main_selected(self, event=None):
        """When user selects a list from dropdown, load its contacts into the table"""
        selected_label = self.contact_lists_dropdown_var.get()
        if selected_label:
            self._load_contacts_into_main_table(selected_label)

    def _load_contacts_into_main_table(self, label: str):
        """Load contacts from the selected list into the table"""
        # Clear existing table
        if self.contact_lists_table:
            for item in self.contact_lists_table.get_children():
                self.contact_lists_table.delete(item)

        # Find the actual file path
        # Remove "Official – " prefix if present
        if label.startswith("Official – "):
            base_name = label.replace("Official – ", "")
        else:
            base_name = label

        file_path = os.path.join(CONTACTS_DIR, f"{base_name}.csv")

        if not os.path.exists(file_path):
            self._set_status(f"File not found: {base_name}.csv", DANGER)
            return

        try:
            rows, headers = safe_read_csv_rows(file_path)

            # Insert rows into table
            if self.contact_lists_table:
                for row in rows:
                    self.contact_lists_table.insert("", "end", values=(
                        row.get("Email", ""),
                        row.get("FirstName", ""),
                        row.get("LastName", ""),
                        row.get("Company", ""),
                        row.get("JobTitle", "")
                    ))

            self._set_status(f"Loaded {len(rows)} contacts from {base_name}", GOOD)

        except Exception as e:
            self._set_status(f"Error loading contacts: {e}", DANGER)

    def _import_new_contact_list_main(self):
        """Import a new contact list with name prompt for Contact Lists main screen"""
        from tkinter import filedialog, simpledialog

        # Ask user to select CSV file
        src = filedialog.askopenfilename(
            title="Import Contact List",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not src:
            return

        # Prompt for list name
        list_name = simpledialog.askstring(
            "Name Your List",
            "Enter a name for this contact list:",
            parent=self
        )

        if not list_name or not list_name.strip():
            messagebox.showwarning("No Name", "You must provide a name for the list.")
            return

        list_name = list_name.strip()

        # Sanitize the name for use as filename
        safe_name = re.sub(r'[<>:"/\\|?*]+', '', list_name)
        safe_name = re.sub(r'\s+', '_', safe_name)

        if not safe_name:
            safe_name = "contacts"

        # Create destination path
        dest = os.path.join(CONTACTS_DIR, f"{safe_name}.csv")

        # Check if file exists
        if os.path.exists(dest):
            overwrite = messagebox.askyesno(
                "File Exists",
                f"A list named '{safe_name}' already exists. Overwrite it?"
            )
            if not overwrite:
                return

        try:
            # Convert and save
            count, warnings = detect_and_convert_contacts_to_official(src, dest)

            if warnings:
                warning_msg = "\n".join(warnings[:3])  # Show first 3 warnings
                messagebox.showwarning("Import Warnings", warning_msg)

            self._set_status(f"Imported {count} contacts as '{safe_name}'", GOOD)

            # Refresh dropdown and select the new list
            self._refresh_contact_lists_main_dropdown()
            self.contact_lists_dropdown_var.set(safe_name)
            self._load_contacts_into_main_table(safe_name)

        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import contacts:\n{e}")
            self._set_status("Import failed", DANGER)

    # ============================================
    # Main layout for Build Emails screen - ONLY EMAIL EDITOR
    # ============================================
    def _build_main_layout(self, parent):
        # Build emails screen now shows email editor (70%) + schedule panel (30%)
        main = tk.Frame(parent, bg=BG_ROOT)
        main.pack(side="top", fill="both", expand=True, padx=16, pady=16)

        # Create split container for side-by-side layout
        split_container = tk.Frame(main, bg=BG_ROOT)
        split_container.pack(fill="both", expand=True)

        # Left side: Email editor (70%)
        left_frame = tk.Frame(split_container, bg=BG_ROOT)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self._build_email_editor(left_frame)

        # Right side: Schedule panel (30%)
        right_frame = tk.Frame(split_container, bg=BG_ROOT)
        right_frame.pack(side="right", fill="both", padx=(8, 0))
        right_frame.config(width=300)  # Fixed width for ~30% of typical screen
        self._build_schedule_panel(right_frame)

        # Initialize emails if this is the first time
        if not self.subject_vars:
            self._init_default_emails()

    # ============================================
    # Status bar
    # ============================================
    def _build_status_bar(self):
        bar = tk.Frame(self, bg=BG_CARD)
        bar.pack(side="bottom", fill="x")

        self.status_dot = tk.Label(bar, text="●", bg=BG_CARD, fg=GOOD, font=("Segoe UI", 10))
        self.status_dot.pack(side="left", padx=(12, 6), pady=8)

        self.status_var = tk.StringVar(value="Ready")
        self.status_label = tk.Label(bar, textvariable=self.status_var, bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9))
        self.status_label.pack(side="left", pady=8)

        spacer = tk.Label(bar, text="", bg=BG_CARD)
        spacer.pack(side="left", expand=True, fill="x")

        tk.Label(bar, text="MV", bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 8, "italic")).pack(
            side="right", padx=(0, 10)
        )

    def _set_status(self, msg: str, pulse_color: str = GOOD, pulse_ms: int = 1400) -> None:
        """
        Verb-style status messages + dot briefly changes color then fades back to green.
        Message stays; only the dot resets to green.
        """
        # Safety check: if status widgets don't exist yet, just skip
        if not hasattr(self, 'status_var') or not hasattr(self, 'status_dot'):
            return

        self.status_var.set(msg)

        if self._status_reset_after_id:
            try:
                self.after_cancel(self._status_reset_after_id)
            except Exception:
                pass
            self._status_reset_after_id = None

        try:
            self.status_dot.configure(fg=pulse_color)
        except Exception:
            return

        def _reset_dot():
            try:
                self.status_dot.configure(fg=GOOD)
            except Exception:
                pass
            self._status_reset_after_id = None

        self._status_reset_after_id = self.after(pulse_ms, _reset_dot)

    # ============================================
    # UI helpers
    # ============================================
    def _make_fancy_box(self, parent, title: str, subtitle: str = ""):
        outer = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat", bd=0)
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        header = tk.Frame(outer, bg=BG_ENTRY)
        header.pack(fill="x", padx=10, pady=(10, 6))

        tk.Label(header, text=title, bg=BG_ENTRY, fg=ACCENT, font=("Segoe UI Semibold", 13)).pack(anchor="w")

        if subtitle:
            tk.Label(header, text=subtitle, bg=BG_ENTRY, fg=FG_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

        tk.Frame(outer, bg=BORDER, height=1).pack(fill="x", padx=10, pady=(6, 0))

        content = tk.Frame(outer, bg=BG_ENTRY)
        content.pack(fill="both", expand=True, padx=10, pady=10)
        return outer, content

    def _styled_entry(self, parent, textvariable):
        return tk.Entry(
            parent,
            textvariable=textvariable,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            highlightcolor=ACCENT,
        )

    def _on_tab_click(self, event):
        """Handle clicks on tab labels to detect X (delete button) clicks"""
        if not hasattr(self, "email_notebook"):
            return

        try:
            # Identify which element was clicked
            element = str(self.email_notebook.identify(event.x, event.y))

            # Only process clicks on tab labels
            if "label" not in element:
                return

            # Get the tab index that was clicked
            clicked_index = self.email_notebook.index(f"@{event.x},{event.y}")

            # Verify it's a valid email tab
            if clicked_index < 0 or clicked_index >= len(self.name_vars):
                return

            # Get the tab text to check if it has an X
            tab_text = self.email_notebook.tab(clicked_index, "text")

            if "✕" not in tab_text:
                return

            # Delete immediately without confirmation
            self._delete_email_tab(clicked_index)

        except Exception:
            pass

    def _delete_email_tab(self, index: int):
        """Delete a specific email tab by index - NO CONFIRMATION DIALOGS"""
        # Validate index
        if index < 0 or index >= len(self.subject_vars):
            return

        # Silently prevent deleting the last email (X should be hidden anyway)
        if len(self.subject_vars) <= 1:
            return

        # Call the existing delete function (which we'll update to remove confirmations)
        self._delete_email(index)

    def _refresh_tab_labels(self):
        """Refresh all email tab labels (no X buttons)"""
        if not hasattr(self, "email_notebook"):
            return

        tabs = self.email_notebook.tabs()
        num_emails = len(self.name_vars)

        # Update all email tabs (no X delete buttons)
        for i in range(num_emails):
            if i < len(tabs):
                label = self.name_vars[i].get().strip() or f"Email {i+1}"
                self.email_notebook.tab(tabs[i], text=f"  {label}  ")

    def _make_collapsible_panel(self, parent, title: str, subtitle: str = "", start_open: bool = True):
        panel = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
        panel.pack(fill="x", pady=(10, 12))

        header = tk.Frame(panel, bg=BG_ENTRY)
        header.pack(fill="x", padx=10, pady=(8, 6))

        is_open = tk.BooleanVar(value=start_open)

        arrow = tk.Label(
            header,
            text="▾" if start_open else "▸",
            bg=BG_ENTRY,
            fg=ACCENT,
            font=("Segoe UI Semibold", 12),
            cursor="hand2",
        )
        arrow.pack(side="left")

        title_lbl = tk.Label(
            header,
            text=title,
            bg=BG_ENTRY,
            fg=ACCENT,
            font=("Segoe UI Semibold", 10),
            cursor="hand2",
        )
        title_lbl.pack(side="left", padx=(8, 0))

        sub_lbl = None
        if subtitle:
            sub_lbl = tk.Label(
                header,
                text=subtitle,
                bg=BG_ENTRY,
                fg=FG_MUTED,
                font=("Segoe UI", 9),
                cursor="hand2",
            )
            sub_lbl.pack(side="left", padx=(10, 0))

        content = tk.Frame(panel, bg=BG_ENTRY)
        content.pack(fill="x", padx=10, pady=(0, 10))

        def _toggle(_evt=None):
            open_now = not is_open.get()
            is_open.set(open_now)
            arrow.configure(text="▾" if open_now else "▸")
            if open_now:
                content.pack(fill="x", padx=10, pady=(0, 10))
            else:
                content.pack_forget()

        header.bind("<Button-1>", _toggle)
        arrow.bind("<Button-1>", _toggle)
        title_lbl.bind("<Button-1>", _toggle)
        if sub_lbl is not None:
            sub_lbl.bind("<Button-1>", _toggle)

        if not start_open:
            content.pack_forget()

        return panel, content, is_open

    # ============================================
    # Email Editor
    # ============================================
    def _build_email_editor(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="both", expand=True)

        # Header above tabs
        header_frame = tk.Frame(card, bg=BG_CARD)
        header_frame.pack(fill="x", padx=22, pady=(20, 10))

        tk.Label(
            header_frame,
            text="Build a Campaign",
            bg=BG_CARD,
            fg=ACCENT,
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w")

        tk.Label(
            header_frame,
            text="Create up to 15 separate emails in one campaign",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        # Email tabs
        self.email_notebook = ttk.Notebook(card)
        self.email_notebook.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Control row below tabs: Add Email | Delete Email | Send Date | Send Time
        control_row = tk.Frame(card, bg=BG_CARD)
        control_row.pack(fill="x", padx=10, pady=(0, 10))

        # + Add Email button
        tk.Button(
            control_row,
            text="+ Add Email",
            command=self._add_email_from_button,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=("Segoe UI Semibold", 9),
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        # Delete Email button
        tk.Button(
            control_row,
            text="Delete Email",
            command=self._delete_current_email,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=("Segoe UI", 9),
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(0, 16))

        # Send Date
        tk.Label(
            control_row,
            text="Send Date:",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_LABEL,
        ).pack(side="left", padx=(0, 6))

        # Create dedicated StringVars for control row (to avoid fluttering)
        self.control_date_var = tk.StringVar()
        self.control_time_var = tk.StringVar()

        self.current_date_widget = self._dateentry_widget(control_row, self.control_date_var)
        self.current_date_widget.pack(side="left", padx=(0, 16))

        # Send Time
        tk.Label(
            control_row,
            text="Send Time:",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_LABEL,
        ).pack(side="left", padx=(0, 6))

        self.current_time_combo = ttk.Combobox(
            control_row,
            textvariable=self.control_time_var,
            values=TIME_OPTIONS,
            width=10,
            state="readonly",
            style="Dark.TCombobox",
            font=FONT_BASE
        )
        self.current_time_combo.pack(side="left")

        # Bind tab selection to update date/time controls (without fluttering)
        self.email_notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Bind control row changes to update the selected email's data
        self.control_date_var.trace_add("write", self._on_control_date_changed)
        self.control_time_var.trace_add("write", self._on_control_time_changed)

    def _create_variables_panel(self, parent):
        _, content, _ = self._make_collapsible_panel(
            parent,
            title="Variables",
            subtitle="Click to expand/collapse",
            start_open=False,
        )

        row = tk.Frame(content, bg=BG_ENTRY)
        row.pack(fill="x")

        variables = ["{FirstName}", "{LastName}", "{Company}", "{JobTitle}", "{Email}"]
        for v in variables:
            tk.Button(
                row,
                text=v,
                command=lambda val=v: self._insert_variable(val),
                bg=BORDER_SOFT,
                fg=FG_TEXT,
                activebackground=BG_HOVER,
                activeforeground=FG_WHITE,
                relief="flat",
                font=("Segoe UI", 9),
                padx=10,
                pady=5,
                cursor="hand2",
            ).pack(side="left", padx=5)

    # ---------- Templates ----------
    def _ensure_templates_dir(self) -> None:
        try:
            ensure_dir(TEMPLATES_DIR)
        except Exception:
            pass

    def _safe_template_filename(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            name = "Template"
        bad = '<>:"/\\|?*'
        for ch in bad:
            name = name.replace(ch, "")
        name = name.replace("\n", " ").replace("\r", " ")
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            name = "Template"
        return name[:80]

    def _safe_list_filename(self, name: str) -> str:
        """
        Turn a list name into a safe filename stem, e.g. 'RLW – UT Supers' -> 'RLW_UT_Supers'.
        """
        raw = (name or "").strip()
        if not raw:
            raw = "Contacts"
        # strip illegal filename chars
        bad = '<>:"/\\|?*'
        for ch in bad:
            raw = raw.replace(ch, "")
        raw = raw.replace("\n", " ").replace("\r", " ")
        # collapse whitespace and non-alphanumerics to '_'
        stem = re.sub(r"\s+", " ", raw).strip()
        stem = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
        if not stem:
            stem = "Contacts"
        return stem[:80]


    def _refresh_templates(self):
        """Refresh templates list - placeholder for future template dropdown"""
        try:
            self._set_status("Templates refreshed", GOOD)
        except:
            pass
        messagebox.showinfo("Templates", "Template list refreshed!")

    def _create_template_from_current(self):
        """Create a template from the current email"""
        # Get current tab index
        try:
            current_tab = self.email_notebook.index(self.email_notebook.select())
        except:
            messagebox.showwarning("No Email Selected", "Please select an email tab to save as template.")
            return
        
        if current_tab < 0 or current_tab >= len(self.subject_vars):
            messagebox.showwarning("No Email Selected", "Please select an email tab to save as template.")
            return
        
        # Get current email data
        subject = self.subject_vars[current_tab].get()
        body = self.body_texts[current_tab].get("1.0", "end").rstrip()
        
        if not subject and not body:
            messagebox.showwarning("Empty Email", "Cannot save an empty email as template.")
            return
        
        # Ask for template name
        template_name = simpledialog.askstring(
            "Save Template",
            "Enter a name for this template:",
            parent=self
        )
        
        if not template_name or not template_name.strip():
            return
        
        template_name = template_name.strip()
        
        # Save template
        try:
            self._ensure_templates_dir()
            safe_name = self._safe_template_filename(template_name)
            template_path = os.path.join(TEMPLATES_DIR, f"{safe_name}.json")
            
            template_data = {
                "name": template_name,
                "subject": subject,
                "body": body,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(template_path, "w", encoding="utf-8") as f:
                json.dump(template_data, f, indent=2)
            
            try:
                self._set_status(f"Template '{template_name}' created", GOOD)
            except:
                pass
            
            messagebox.showinfo("Success", f"Template '{template_name}' saved successfully!")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save template:\n{e}")

    def _upload_email_template(self):
        """Upload a complete email template from file"""
        filepath = filedialog.askopenfilename(
            title="Select Email Template",
            filetypes=[
                ("JSON files", "*.json"),
                ("Text files", "*.txt"),
                ("All files", "*.*")
            ]
        )
        
        if not filepath:
            return
        
        try:
            # Read the file
            with open(filepath, "r", encoding="utf-8") as f:
                if filepath.endswith(".json"):
                    data = json.load(f)
                    subject = data.get("subject", "")
                    body = data.get("body", "")
                else:
                    # Plain text file - use as body
                    body = f.read()
                    subject = ""
            
            # Get current tab or create new one
            try:
                current_tab = self.email_notebook.index(self.email_notebook.select())
            except:
                current_tab = -1
            
            if current_tab >= 0 and current_tab < len(self.subject_vars):
                # Load into current tab
                self.subject_vars[current_tab].set(subject)
                self.body_texts[current_tab].delete("1.0", "end")
                self.body_texts[current_tab].insert("1.0", body)
            else:
                # Create new email with this content
                next_num = len(self.subject_vars) + 1
                self._add_email(
                    name=f"Email {next_num}",
                    subject=subject,
                    body=body,
                    date=(datetime.now() + timedelta(days=next_num * 3)).strftime("%Y-%m-%d"),
                    time="9:00 AM"
                )
            
            try:
                self._set_status("Template uploaded", GOOD)
            except:
                pass
            
            messagebox.showinfo("Success", "Template loaded successfully!")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load template:\n{e}")

    def _list_templates(self) -> List[str]:
        self._ensure_templates_dir()
        try:
            items = []
            for fn in os.listdir(TEMPLATES_DIR):
                if fn.lower().endswith(".json"):
                    items.append(os.path.splitext(fn)[0])
            items.sort(key=lambda s: s.lower())
            return items
        except Exception:
            return []

    def _template_values(self) -> List[str]:
        return ["None"] + self._list_templates()

    def _refresh_templates_dropdown(self) -> None:
        try:
            if hasattr(self, "template_combo"):
                self.template_combo["values"] = self._template_values()
        except Exception:
            pass

    def _update_template_buttons(self) -> None:
        sel = (self.template_var.get() or "").strip()
        chosen = bool(sel) and sel != "None"
        try:
            if hasattr(self, "btn_overwrite"):
                self.btn_overwrite.configure(state=("normal" if chosen else "disabled"))
            if hasattr(self, "btn_delete_tmpl"):
                self.btn_delete_tmpl.configure(state=("normal" if chosen else "disabled"))
        except Exception:
            pass

    def _on_template_selected(self, _evt=None) -> None:
        sel = (self.template_var.get() or "").strip()
        self._update_template_buttons()
        if not sel or sel == "None":
            return
        self._load_template(sel)

    def _prompt_save_template(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Save Template")
        dlg.configure(bg=BG_ROOT)
        dlg.resizable(False, False)

        tk.Label(
            dlg,
            text="Name this sequence template:",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=14, pady=(14, 6))

        current = (self.template_var.get() or "").strip()
        if current == "None":
            current = ""
        name_var = tk.StringVar(value=current)
        ent = tk.Entry(
            dlg,
            textvariable=name_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            highlightcolor=ACCENT,
            width=38,
        )
        ent.pack(fill="x", padx=14, pady=(0, 10))
        ent.focus_set()

        btn_row = tk.Frame(dlg, bg=BG_ROOT)
        btn_row.pack(fill="x", padx=14, pady=(0, 14))

        def _do_save():
            nm = self._safe_template_filename(name_var.get())
            if not nm:
                messagebox.showerror("Missing", "Enter a template name.")
                return
            dlg.destroy()
            self._save_template(nm)

        tk.Button(
            btn_row,
            text="Cancel",
            command=dlg.destroy,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(side="right")

        tk.Button(
            btn_row,
            text="Save",
            command=_do_save,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(side="right", padx=(0, 8))

        dlg.bind("<Return>", lambda _e: _do_save())

        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - (dlg.winfo_width() // 2)
        y = self.winfo_rooty() + (self.winfo_height() // 2) - (dlg.winfo_height() // 2)
        dlg.geometry(f"+{x}+{y}")

    def _save_template(self, name: str) -> None:
        self._ensure_templates_dir()
        safe = self._safe_template_filename(name)
        path = os.path.join(TEMPLATES_DIR, f"{safe}.json")

        cfg = self._collect_config()
        payload = {
            "template_name": safe,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "config": cfg,
        }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            messagebox.showerror("Save Failed", f"Could not save template:\n{e}")
            self._set_status("Save failed", DANGER)
            return

        self._refresh_templates_dropdown()
        self.template_var.set(safe)
        self._update_template_buttons()
        self._set_status("Template saved", GOOD)
        messagebox.showinfo("Saved", f"Template saved:\n{safe}")

    def _overwrite_selected_template(self) -> None:
        name = (self.template_var.get() or "").strip()
        if not name or name == "None":
            messagebox.showinfo("Select a template", "Choose a template from the dropdown first.")
            return

        ok = messagebox.askyesno(
            "Overwrite Template",
            f"Overwrite template '{name}' with your current sequence?\n\nThis will replace the saved version of that template.",
        )
        if not ok:
            self._set_status("Overwrite cancelled", WARN)
            return

        self._save_template(name)
        self._set_status("Template overwritten", GOOD)

    def _load_template(self, name: str) -> None:
        name = (name or "").strip()
        if not name or name == "None":
            return

        path = os.path.join(TEMPLATES_DIR, f"{name}.json")
        if not os.path.isfile(path):
            messagebox.showerror("Not found", f"Template not found:\n{path}")
            self._set_status("Template not found", DANGER)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            cfg = payload.get("config", payload)
        except Exception as e:
            messagebox.showerror("Load Failed", f"Could not read template:\n{e}")
            self._set_status("Load failed", DANGER)
            return

        ok = messagebox.askyesno(
            "Load Template",
            f"Load template '{name}'?\n\nThis will replace your current emails/sequence.",
        )
        if not ok:
            self.template_var.set("None")
            self._update_template_buttons()
            self._set_status("Load cancelled", WARN)
            return

        try:
            self._load_from_config_dict(cfg)
            self._set_status("Template loaded", GOOD)
        except Exception:
            _write_crash_log("template_load")
            messagebox.showerror("Load Failed", "Could not apply template. Check logs.")
            self._set_status("Load failed", DANGER)
            return

    def _delete_template(self, name: str) -> None:
        name = (name or "").strip()
        if not name or name == "None":
            messagebox.showinfo("Select a template", "Choose a template from the dropdown.")
            return

        path = os.path.join(TEMPLATES_DIR, f"{name}.json")
        if not os.path.isfile(path):
            messagebox.showerror("Not found", f"Template not found:\n{path}")
            self._set_status("Template not found", DANGER)
            return

        ok = messagebox.askyesno(
            "Delete Template",
            f"Delete template '{name}'?\n\nThis won’t delete any emails already scheduled.",
        )
        if not ok:
            self._set_status("Delete cancelled", WARN)
            return

        try:
            os.remove(path)
        except Exception as e:
            messagebox.showerror("Delete Failed", f"Could not delete template:\n{e}")
            self._set_status("Delete failed", DANGER)
            return

        self._refresh_templates_dropdown()
        self.template_var.set("None")
        self._update_template_buttons()
        self._set_status("Template deleted", WARN)

    def _refresh_sequence_to_default(self) -> None:
        ok = messagebox.askyesno(
            "Reset Sequence",
            "Reset this sequence back to the default 4-email layout?\n\n"
            "This will remove Email 5+ and clear per-email attachments.",
        )
        if not ok:
            self._set_status("Reset cancelled", WARN)
            return

        try:
            staged_root = user_path("PerEmailAttachments")
            if os.path.isdir(staged_root):
                shutil.rmtree(staged_root, ignore_errors=True)
        except Exception:
            pass

        now = datetime.now()
        default_cfg = {
            "emails": [
                {
                    "name": f"Email {i+1}",
                    "subject": "",
                    "body": "",
                    "date": (now + timedelta(days=3 * i)).strftime("%Y-%m-%d"),
                    "time": "9:00 AM",
                    "per_attachments": [],
                }
                for i in range(4)
            ],
            "test_email": self.test_email_var.get(),
        }

        self._load_from_config_dict(default_cfg)
        self.template_var.set("None")
        self._refresh_templates_dropdown()
        self._update_template_buttons()
        self._set_status("Sequence reset", GOOD)
        messagebox.showinfo("Reset", "Sequence reset to Email 1–Email 4.")

    def _create_templates_panel(self, parent):
        self._ensure_templates_dir()

        _, content, _ = self._make_collapsible_panel(
            parent,
            title="Templates",
            subtitle="Save and reuse email sequences",
            start_open=False,
        )

        row1 = tk.Frame(content, bg=BG_ENTRY)
        row1.pack(fill="x", pady=(0, 8))

        tk.Label(
            row1,
            text="Template:",
            bg=BG_ENTRY,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left")

        self.template_combo = ttk.Combobox(
            row1,
            textvariable=self.template_var,
            values=self._template_values(),
            state="readonly",
            width=28,
            style="Dark.TCombobox",
        )
        self.template_combo.pack(side="left", padx=(8, 0))
        self.template_combo.bind("<<ComboboxSelected>>", self._on_template_selected)

        row2 = tk.Frame(content, bg=BG_ENTRY)
        row2.pack(fill="x")

        tk.Button(
            row2,
            text="Save as New",
            command=self._prompt_save_template,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            padx=10,
            pady=6,
            cursor="hand2",
        ).pack(side="left")

        self.btn_overwrite = tk.Button(
            row2,
            text="Overwrite Selected",
            command=self._overwrite_selected_template,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            padx=10,
            pady=6,
            cursor="hand2",
            state="disabled",
        )
        self.btn_overwrite.pack(side="left", padx=(8, 0))

        self.btn_delete_tmpl = tk.Button(
            row2,
            text="Delete Template",
            command=lambda: self._delete_template((self.template_var.get() or "").strip()),
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            padx=10,
            pady=6,
            cursor="hand2",
            state="disabled",
        )
        self.btn_delete_tmpl.pack(side="left", padx=(8, 0))

        tk.Button(
            row2,
            text="Refresh Sequence (Reset to Email 1–4)",
            command=self._refresh_sequence_to_default,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            padx=10,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        self._refresh_templates_dropdown()
        if not (self.template_var.get() or "").strip():
            self.template_var.set("None")
        self._update_template_buttons()

    def _create_email_tab(self, index: int, name_var: tk.StringVar, subject_var: tk.StringVar, body_text: str = "") -> tk.Text:
        tab = tk.Frame(self.email_notebook, bg=BG_CARD)

        # Add tab (no X buttons)
        label = name_var.get().strip() or f"Email {index}"
        self.email_notebook.add(tab, text=f"  {label}  ")

        # Main content frame with padding
        inner = tk.Frame(tab, bg=BG_CARD)
        inner.pack(fill="both", expand=True, padx=22, pady=16)

        # Control row at top: Add Email | Delete Email | Send Date | Send Time
        control_row = tk.Frame(inner, bg=BG_CARD)
        control_row.pack(fill="x", pady=(0, 16))

        # + Add Email button
        tk.Button(
            control_row,
            text="+ Add Email",
            command=self._add_email_from_button,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=("Segoe UI Semibold", 9),
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        # Delete Email button
        tk.Button(
            control_row,
            text="Delete Email",
            command=self._delete_current_email,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=("Segoe UI", 9),
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(0, 16))

        # Send Date
        tk.Label(
            control_row,
            text="Send Date:",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_LABEL,
        ).pack(side="left", padx=(0, 6))

        # Get the correct date/time vars for this email (index-1 because lists are 0-based)
        actual_index = index - 1
        if actual_index >= 0 and actual_index < len(self.date_vars):
            tab_date_var = self.date_vars[actual_index]
        else:
            tab_date_var = tk.StringVar()

        date_widget = self._dateentry_widget(control_row, tab_date_var)
        date_widget.pack(side="left", padx=(0, 16))

        # Send Time
        tk.Label(
            control_row,
            text="Send Time:",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_LABEL,
        ).pack(side="left", padx=(0, 6))

        if actual_index >= 0 and actual_index < len(self.time_vars):
            tab_time_var = self.time_vars[actual_index]
        else:
            tab_time_var = tk.StringVar(value="9:00 AM")

        time_combo = ttk.Combobox(
            control_row,
            textvariable=tab_time_var,
            values=TIME_OPTIONS,
            width=10,
            state="readonly",
            style="Dark.TCombobox",
            font=FONT_BASE
        )
        time_combo.pack(side="left")

        # Name field
        tk.Label(inner, text="Name", bg=BG_CARD, fg=ACCENT, font=FONT_FIELD_HDR).pack(anchor="w", pady=(0, 4))
        ent_name = self._styled_entry(inner, name_var)
        ent_name.pack(fill="x", pady=(0, 8))

        def _on_name_change(*_):
            self._refresh_tab_labels()
        name_var.trace_add("write", _on_name_change)

        # Subject field
        tk.Label(inner, text="Subject", bg=BG_CARD, fg=ACCENT, font=FONT_FIELD_HDR).pack(anchor="w", pady=(0, 4))
        self._styled_entry(inner, subject_var).pack(fill="x", pady=(0, 8))

        # Variables panel (before body)
        self._create_variables_panel(inner)

        # Body field
        tk.Label(inner, text="Body", bg=BG_CARD, fg=ACCENT, font=FONT_FIELD_HDR).pack(anchor="w", pady=(0, 4))
        txt_body = tk.Text(
            inner,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            wrap="word",
            height=14,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            highlightcolor=ACCENT,
        )
        txt_body.pack(fill="both", expand=True, pady=(0, 8))

        if body_text:
            txt_body.insert("1.0", body_text)

        return txt_body

    def _insert_variable(self, var: str):
        widget = self.focus_get()
        try:
            if isinstance(widget, (tk.Entry, tk.Text)):
                widget.insert("insert", var)
        except tk.TclError:
            pass
        try:
            self.clipboard_clear()
            self.clipboard_append(var)
        except tk.TclError:
            pass

    # ============================================
    # SEQUENCE (local time only)
    # ============================================
    def _build_schedule_panel(self, parent):
        """Build the compact schedule sidebar panel (30% width)"""
        # Main card container
        card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
        card.pack(fill="both", expand=True)

        # Header
        header = tk.Frame(card, bg=BG_ENTRY)
        header.pack(fill="x", padx=12, pady=(12, 8))

        tk.Label(
            header,
            text="Email Schedule",
            bg=BG_ENTRY,
            fg=ACCENT,
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")

        tk.Label(
            header,
            text=f"Local timezone: {self.tz_label}",
            bg=BG_ENTRY,
            fg=FG_MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(2, 0))

        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=12, pady=(0, 8))

        # Scrollable list of emails
        list_container = tk.Frame(card, bg=BG_ENTRY)
        list_container.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Create canvas for scrolling
        canvas = tk.Canvas(list_container, bg=BG_ENTRY, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        self.schedule_list_frame = tk.Frame(canvas, bg=BG_ENTRY)

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.create_window((0, 0), window=self.schedule_list_frame, anchor="nw", width=canvas.winfo_reqwidth())

        def _on_list_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        self.schedule_list_frame.bind("<Configure>", _on_list_configure)

        # Store reference for updates
        self.schedule_panel_canvas = canvas
        self.schedule_list_items = []  # List of item frames for highlighting

        # Initial population
        self._rebuild_schedule_panel()

    def _rebuild_schedule_panel(self):
        """Rebuild the schedule panel list to match current emails"""
        if not hasattr(self, "schedule_list_frame"):
            return

        # Clear existing items
        for child in self.schedule_list_frame.winfo_children():
            child.destroy()

        self.schedule_list_items = []

        # Get current tab index for highlighting
        current_tab = -1
        if hasattr(self, "email_notebook"):
            try:
                current_tab = self.email_notebook.index(self.email_notebook.select())
            except:
                pass

        # Create an item for each email
        for i in range(len(self.name_vars)):
            is_selected = (i == current_tab)

            # Create item frame with click handler
            item_frame = tk.Frame(
                self.schedule_list_frame,
                bg=ACCENT_2 if is_selected else BG_ENTRY,
                highlightbackground=ACCENT if is_selected else BORDER_MEDIUM,
                highlightthickness=1,
                relief="flat",
                cursor="hand2"
            )
            item_frame.pack(fill="x", pady=2)

            # Store reference for highlighting later
            self.schedule_list_items.append(item_frame)

            # Make entire item clickable
            item_frame.bind("<Button-1>", lambda _e, idx=i: self._schedule_item_clicked(idx))

            # Content padding
            content = tk.Frame(item_frame, bg=item_frame["bg"])
            content.pack(fill="x", padx=8, pady=6)

            # Email name (bold) - clickable to switch tabs
            # Use textvariable for automatic updates without rebuilding
            if i < len(self.name_vars):
                name_label = tk.Label(
                    content,
                    textvariable=self.name_vars[i],
                    bg=content["bg"],
                    fg=FG_TEXT,
                    font=("Segoe UI Semibold", 10),
                    anchor="w",
                    cursor="hand2"
                )
            else:
                name_label = tk.Label(
                    content,
                    text=f"Email {i+1}",
                    bg=content["bg"],
                    fg=FG_TEXT,
                    font=("Segoe UI Semibold", 10),
                    anchor="w",
                    cursor="hand2"
                )
            name_label.pack(fill="x")
            name_label.bind("<Button-1>", lambda _e, idx=i: self._schedule_item_clicked(idx))

            # Date field (editable)
            date_frame = tk.Frame(content, bg=content["bg"])
            date_frame.pack(fill="x", pady=(4, 0))

            tk.Label(
                date_frame,
                text="Date:",
                bg=content["bg"],
                fg=FG_MUTED,
                font=("Segoe UI", 8),
            ).pack(side="left", padx=(0, 4))

            if i < len(self.date_vars):
                date_entry = self._dateentry_widget(date_frame, self.date_vars[i])
                date_entry.configure(font=("Segoe UI", 8), width=12)
                date_entry.pack(side="left", fill="x", expand=True)

            # Time field (editable)
            time_frame = tk.Frame(content, bg=content["bg"])
            time_frame.pack(fill="x", pady=(2, 0))

            tk.Label(
                time_frame,
                text="Time:",
                bg=content["bg"],
                fg=FG_MUTED,
                font=("Segoe UI", 8),
            ).pack(side="left", padx=(0, 4))

            if i < len(self.time_vars):
                time_combo = ttk.Combobox(
                    time_frame,
                    textvariable=self.time_vars[i],
                    values=TIME_OPTIONS,
                    width=8,
                    state="readonly",
                    style="Dark.TCombobox",
                    font=("Segoe UI", 8)
                )
                time_combo.pack(side="left", fill="x", expand=True)

            # Attachment count
            if i < len(self.per_email_attachments):
                attach_count = len(self.per_email_attachments[i])
                if attach_count > 0:
                    attach_label = tk.Label(
                        content,
                        text=f"📎 {attach_count} attachment{'s' if attach_count != 1 else ''}",
                        bg=content["bg"],
                        fg=FG_MUTED,
                        font=("Segoe UI", 8),
                        anchor="w",
                        cursor="hand2"
                    )
                    attach_label.pack(fill="x", pady=(2, 0))
                    attach_label.bind("<Button-1>", lambda _e, idx=i: self._schedule_item_clicked(idx))

    def _schedule_item_clicked(self, index):
        """Handle click on a schedule item - switch to that email tab"""
        if not hasattr(self, "email_notebook"):
            return

        if index < 0 or index >= len(self.email_notebook.tabs()):
            return

        # Switch to the clicked tab
        self.email_notebook.select(index)

        # Update highlighting (will be triggered by tab change event)

    def _update_schedule_panel_highlighting(self, current_tab):
        """Update only the highlighting in the schedule panel (efficient)"""
        if not hasattr(self, "schedule_list_items"):
            return

        # Update highlighting for each item
        for i, item_frame in enumerate(self.schedule_list_items):
            is_selected = (i == current_tab)

            # Update frame background and border
            try:
                item_frame.configure(
                    bg=ACCENT_2 if is_selected else BG_ENTRY,
                    highlightbackground=ACCENT if is_selected else BORDER_MEDIUM
                )

                # Update all child widgets' backgrounds
                for child in item_frame.winfo_children():
                    child.configure(bg=ACCENT_2 if is_selected else BG_ENTRY)
                    # Update nested children (labels inside content frame)
                    for subchild in child.winfo_children():
                        try:
                            subchild.configure(bg=ACCENT_2 if is_selected else BG_ENTRY)
                        except:
                            pass
            except:
                pass


    def _build_schedule_card(self, parent, row=0):
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 8))

        box = tk.Frame(card, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
        box.pack(fill="x", padx=12, pady=12)

        tk.Label(
            box,
            text="Set & Confirm Email Schedule",
            bg=BG_ENTRY,
            fg=ACCENT,
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w", padx=10, pady=(10, 4))

        tk.Label(
            box,
            text=f"Scheduling uses your local timezone ({self.tz_label}).",
            bg=BG_ENTRY,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=10, pady=(0, 10))

        tk.Frame(box, bg=BORDER, height=1).pack(fill="x", padx=10, pady=(0, 10))

        self.sequence_table = tk.Frame(box, bg=BG_ENTRY)
        self.sequence_table.pack(fill="x", padx=10, pady=(0, 10))

        self.sequence_table.columnconfigure(0, weight=2, minsize=170)
        self.sequence_table.columnconfigure(1, weight=1, minsize=120)
        self.sequence_table.columnconfigure(2, weight=1, minsize=110)
        self.sequence_table.columnconfigure(3, weight=0, minsize=180)

        btn_row = tk.Frame(box, bg=BG_ENTRY)
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        tk.Button(
            btn_row,
            text="+ Add Email",
            command=self._add_email,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=7,
            cursor="hand2",
        ).pack(side="left")

        tk.Button(
            btn_row,
            text="Preview sequence",
            command=self._preview_sequence,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=("Segoe UI", 9),
            padx=10,
            pady=7,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        self._rebuild_sequence_table()

    def _dateentry_widget(self, parent, var: tk.StringVar):
        if DateEntry is None:
            ent = tk.Entry(
                parent,
                textvariable=var,
                bg=BG_ENTRY,
                fg=FG_TEXT,
                insertbackground=FG_TEXT,
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER_MEDIUM,
                highlightcolor=ACCENT,
            )
            return ent

        de = DateEntry(  # type: ignore
            parent,
            textvariable=var,
            date_pattern="yyyy-mm-dd",
            width=12,
            style="Dark.DateEntry",
            background=BG_ENTRY,
            foreground=FG_TEXT,
            bordercolor=BORDER,
            headersbackground=BG_ENTRY,
            headersforeground=FG_TEXT,
            selectbackground=ACCENT_2,
            selectforeground=FG_TEXT,
            normalbackground=BG_ENTRY,
            normalforeground=FG_TEXT,
            weekendbackground=BG_ENTRY,
            weekendforeground=FG_TEXT,
            othermonthbackground=BG_ENTRY,
            othermonthforeground=FG_MUTED,
            othermonthwebackground=BG_ENTRY,
            othermonthweforeground=FG_MUTED,
            disabledbackground=BG_ENTRY,
            disabledforeground=FG_MUTED,
        )
        try:
            de.configure(state="normal")
        except Exception:
            pass
        return de

    def _sync_manage_button(self, index: int):
        if index < 0 or index >= len(self.per_email_manage_btns):
            return
        if index < 0 or index >= len(self.per_email_attachments):
            return
        n = len(self.per_email_attachments[index])
        btn = self.per_email_manage_btns[index]
        btn.configure(text=(f"Add / Delete ({n})" if n else "Add / Delete"))
        btn.configure(state="normal")

    def _rebuild_sequence_table(self):
        if not hasattr(self, "sequence_table"):
            return

        # Prevent recursive rebuilds
        if self._rebuilding_sequence_table:
            return

        # Cancel any pending rebuild
        if self._rebuild_pending_after_id:
            self.after_cancel(self._rebuild_pending_after_id)
            self._rebuild_pending_after_id = None

        # Debounce: schedule rebuild after 100ms
        self._rebuild_pending_after_id = self.after(100, self._do_rebuild_sequence_table)

    def _do_rebuild_sequence_table(self):
        """Actually rebuild the sequence table (called after debounce delay)"""
        if not hasattr(self, "sequence_table"):
            return

        self._rebuilding_sequence_table = True
        self._rebuild_pending_after_id = None

        try:
            for child in self.sequence_table.winfo_children():
                child.destroy()

            hdr_font = ("Segoe UI Semibold", 9)

            tk.Label(self.sequence_table, text="Email", bg=BG_ENTRY, fg=FG_MUTED, font=hdr_font) \
                .grid(row=0, column=0, sticky="w", pady=(0, 6))
            tk.Label(self.sequence_table, text="Send date", bg=BG_ENTRY, fg=FG_MUTED, font=hdr_font) \
                .grid(row=0, column=1, sticky="w", padx=(10, 0), pady=(0, 6))
            tk.Label(self.sequence_table, text="Send time", bg=BG_ENTRY, fg=FG_MUTED, font=hdr_font) \
                .grid(row=0, column=2, sticky="w", padx=(10, 0), pady=(0, 6))
            tk.Label(self.sequence_table, text="Attachments", bg=BG_ENTRY, fg=FG_MUTED, font=hdr_font) \
                .grid(row=0, column=3, sticky="w", padx=(10, 0), pady=(0, 6))

            self.per_email_manage_btns = []

            for i in range(len(self.date_vars)):
                r = i + 1

                name_var = self.name_vars[i] if i < len(self.name_vars) else tk.StringVar(value=f"Email {i+1}")

                lbl_name = tk.Label(
                    self.sequence_table,
                    textvariable=name_var,
                    bg=BG_ENTRY,
                    fg=FG_TEXT,
                    anchor="w",
                    font=FONT_BASE,
                )
                lbl_name.grid(row=r, column=0, sticky="ew", pady=3)
                ToolTip(lbl_name, "Email name (edit this on the Email tab in the left panel).")

                date_widget = self._dateentry_widget(self.sequence_table, self.date_vars[i])
                date_widget.grid(row=r, column=1, sticky="ew", padx=(10, 0), pady=3)

                time_combo = ttk.Combobox(
                    self.sequence_table,
                    textvariable=self.time_vars[i],
                    values=TIME_OPTIONS,
                    width=10,
                    state="readonly",
                    style="Dark.TCombobox",
                )
                if not self.time_vars[i].get():
                    self.time_vars[i].set("9:00 AM")
                time_combo.grid(row=r, column=2, sticky="ew", padx=(10, 0), pady=3)

                attach_cell = tk.Frame(self.sequence_table, bg=BG_ENTRY)
                attach_cell.grid(row=r, column=3, sticky="ew", padx=(10, 0), pady=3)
                attach_cell.columnconfigure(0, weight=1)

                btn_manage = tk.Button(
                    attach_cell,
                    text="Add / Delete",
                    command=lambda idx=i: self._open_attachment_manager(idx),
                    bg=BORDER_SOFT,
                    fg=FG_TEXT,
                    activebackground=BG_HOVER,
                    activeforeground=FG_TEXT,
                    relief="flat",
                    font=("Segoe UI", 9),
                    padx=10,
                    pady=5,
                    cursor="hand2",
                )
                btn_manage.grid(row=0, column=0, sticky="ew")
                ToolTip(btn_manage, "Add or delete attachments for this email.")
                self.per_email_manage_btns.append(btn_manage)

                self._sync_manage_button(i)
        finally:
            # Always reset the rebuilding flag
            self._rebuilding_sequence_table = False

    def _open_attachment_manager(self, index: int):
        if index < 0 or index >= len(self.per_email_attachments):
            return
        label = self.name_vars[index].get().strip() if index < len(self.name_vars) else f"Email {index+1}"
        label = label or f"Email {index+1}"

        def _on_update():
            self._sync_manage_button(index)
            # Note: Attachment count in schedule panel will update on next tab switch
            self._set_status("Attachments updated", GOOD)

        AttachmentManagerWindow(self, label, self.per_email_attachments[index], _on_update)

    # ============================================
    # CONTACT LIST box (official file workflow)
    # ============================================
    def _build_contacts_card(self, parent, row=1):
        """Contact list with embedded table view"""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 8))
        card.rowconfigure(1, weight=1)  # Make table expand
        card.columnconfigure(0, weight=1)

        box = tk.Frame(card, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.rowconfigure(2, weight=1)  # Table row expands
        box.columnconfigure(0, weight=1)

        # Header
        tk.Label(
            box,
            text="Contact list",
            bg=BG_CARD,
            fg=ACCENT,
            font=("Segoe UI Semibold", 13),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))

        # Buttons row
        row_btns = tk.Frame(box, bg=BG_CARD)
        row_btns.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        tk.Button(
            row_btns,
            text="Import Contacts",
            command=self._import_contacts_and_refresh,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=("Segoe UI Semibold", 10),
            padx=14,
            pady=8,
            cursor="hand2",
        ).pack(side="left")

        tk.Button(
            row_btns,
            text="Add Contact",
            command=self._add_new_contact,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=("Segoe UI", 9),
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            row_btns,
            text="Delete Selected",
            command=self._delete_selected_contact,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=("Segoe UI", 9),
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            row_btns,
            text="Double-click any cell to edit",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=("Segoe UI", 9, "italic")
        ).pack(side="right", padx=(10, 0))

        # Contacts table (embedded treeview)
        table_frame = tk.Frame(box, bg=BG_CARD)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # Create treeview with headers
        self.contacts_tree = ttk.Treeview(
            table_frame,
            columns=("Email", "FirstName", "LastName", "Company", "JobTitle"),
            show="headings",
            height=15
        )
        
        # Configure columns
        self.contacts_tree.heading("Email", text="Email")
        self.contacts_tree.heading("FirstName", text="First Name")
        self.contacts_tree.heading("LastName", text="Last Name")
        self.contacts_tree.heading("Company", text="Company")
        self.contacts_tree.heading("JobTitle", text="Job Title")
        
        # Configure columns with centering
        self.contacts_tree.column("Email", width=250, anchor="center")
        self.contacts_tree.column("FirstName", width=150, anchor="center")
        self.contacts_tree.column("LastName", width=150, anchor="center")
        self.contacts_tree.column("Company", width=200, anchor="center")
        self.contacts_tree.column("JobTitle", width=180, anchor="center")
        
        # Rows configured in _build_styles()

        # Add scrollbars
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.contacts_tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.contacts_tree.xview)
        self.contacts_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Grid layout for tree and scrollbars
        self.contacts_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")


        # Enable double-click editing
        self.contacts_tree.bind("<Double-1>", self._on_contact_double_click)

        # Load existing contacts if file exists
        self._refresh_contacts_table()

    def _load_contacts_into_table(self):
        """Load contacts from the official CSV into the table"""
        # Clear existing items
        for item in self.contacts_tree.get_children():
            self.contacts_tree.delete(item)
        
        contacts_path = OFFICIAL_CONTACTS_PATH
        if not os.path.isfile(contacts_path):
            return
        
        try:
            rows, headers = safe_read_csv_rows(contacts_path)
            
            for row in rows:
                email = row.get("Email", "")
                first = row.get("FirstName", "")
                last = row.get("LastName", "")
                company = row.get("Company", "")
                title = row.get("JobTitle", "")
                
                self.contacts_tree.insert("", "end", values=(email, first, last, company, title))
            
            
        except Exception as e:
            pass

    def _copy_official_contacts_path(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(OFFICIAL_CONTACTS_PATH)
            self._set_status("Path copied", GOOD)
        except Exception:
            pass

    def _maybe_show_contacts_import_popup(self):
        cfg = load_config()
        hide = bool(cfg.get(CFG_KEY_HIDE_CONTACTS_IMPORT_POPUP, False))
        if hide:
            return

        def _done(dont_show: bool):
            if dont_show:
                cfg2 = load_config()
                cfg2[CFG_KEY_HIDE_CONTACTS_IMPORT_POPUP] = True
                save_config(cfg2)

        OneTimeContactsImportedDialog(self, _done)

    def _import_contacts_list(self):
        src = filedialog.askopenfilename(
            title="Select contacts CSV to import",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not src:
            return

        try:
            # 1) Normalize into the OFFICIAL contacts file (same as today)
            count, warnings = detect_and_convert_contacts_to_official(
                src,
                OFFICIAL_CONTACTS_PATH,
            )

            self.contacts_path_var.set(OFFICIAL_CONTACTS_PATH)
            self._set_status(f"Contacts imported ({count} contacts)", GOOD)

            # Optional: small info message instead of the big custom popup
            if warnings:
                messagebox.showinfo(
                    "Import notes",
                    "Import completed.\n\n" + "\n".join(f"• {w}" for w in warnings),
                )
            else:
                messagebox.showinfo(
                    "Imported",
                    f"Imported {count} contact(s) into:\n\n{OFFICIAL_CONTACTS_PATH}",
                )

            # 2) NEW: Ask if this should be saved as a reusable list
            if count > 0:
                save_as_list = messagebox.askyesno(
                    "Save as reusable list?",
                    "Do you want to save this imported file as a reusable contact list?\n\n"
                    "If yes, you can select it later from the contact list dropdown "
                    "without re-importing the CSV.",
                )
                if save_as_list:
                    self._save_import_as_named_list(count)

        except Exception as e:
            _write_crash_log("contacts_import")
            self._set_status("Import failed", DANGER)
            messagebox.showerror("Import failed", f"Could not import contacts:\n{e}")

    def _save_import_as_named_list(self, row_count: int) -> None:
        """
        Take the current OFFICIAL_CONTACTS_PATH and save a copy as a named list
        in the Contacts folder.
        """
        # Ask user for a list name
        default_name = os.path.splitext(os.path.basename(OFFICIAL_CONTACTS_PATH))[0]
        name = simpledialog.askstring(
            "Name contact list",
            "Name this contact list (e.g. 'RLW – UT Supers Q1'):",
            initialvalue=default_name,
            parent=self,
        )
        if not name:
            return  # user cancelled

        stem = self._safe_list_filename(name)
        dest = os.path.join(CONTACTS_DIR, f"{stem}.csv")

        # If a file with that name exists, it's okay to overwrite – this is an explicit action.
        try:
            shutil.copy2(OFFICIAL_CONTACTS_PATH, dest)
        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save list:\n{e}")
            return

        # Refresh the Contact Lists dropdown if it exists
        if hasattr(self, "_refresh_contact_lists_main_dropdown"):
            self._refresh_contact_lists_main_dropdown()

        msg = f"Saved contact list '{name}' ({row_count} contacts)."
        self._set_status(msg, GOOD)


    def _import_contacts_and_refresh(self):
        """Import contacts and refresh the embedded table"""
        self._import_contacts_list()
        # Refresh the table after import
        if hasattr(self, 'contacts_tree'):
            self._refresh_contacts_table()

    def _refresh_contacts_table(self):
        """Refresh the contacts table with data from contacts.csv"""
        if not hasattr(self, 'contacts_tree'):
            return
        
        # Clear existing items
        for item in self.contacts_tree.get_children():
            self.contacts_tree.delete(item)
        
        # Load contacts from file
        if not os.path.exists(OFFICIAL_CONTACTS_PATH):
            return
        
        try:
            rows, headers = safe_read_csv_rows(OFFICIAL_CONTACTS_PATH)
            
            # Add each contact to the table
            for row in rows:
                email = row.get("Email", "")
                first = row.get("FirstName", "")
                last = row.get("LastName", "")
                company = row.get("Company", "")
                title = row.get("JobTitle", "")
                
                self.contacts_tree.insert("", "end", values=(email, first, last, company, title))
            
            try:
                self._set_status(f"Loaded {len(rows)} contacts", GOOD)
            except:
                pass
        except Exception as e:
            pass  # Failed to load


    def _on_contact_double_click(self, event):
        """Handle double-click to edit a cell"""
        if not hasattr(self, 'contacts_tree'):
            return
        
        tree = self.contacts_tree
        region = tree.identify("region", event.x, event.y)
        
        if region != "cell":
            return
        
        # Get the item and column
        item = tree.identify_row(event.y)
        column = tree.identify_column(event.x)
        
        if not item or not column:
            return
        
        # Get column index
        col_idx = int(column.replace("#", "")) - 1
        col_names = ["Email", "FirstName", "LastName", "Company", "JobTitle"]
        col_name = col_names[col_idx]
        
        # Get current value
        values = tree.item(item, "values")
        current_value = values[col_idx] if col_idx < len(values) else ""
        
        # Create edit window
        self._edit_contact_cell(item, col_idx, col_name, current_value)
    
    def _edit_contact_cell(self, item, col_idx, col_name, current_value):
        """Open a dialog to edit a contact cell"""
        edit_win = tk.Toplevel(self)
        edit_win.title(f"Edit {col_name}")
        edit_win.geometry("400x150")
        edit_win.configure(bg=BG_ROOT)
        edit_win.transient(self)
        edit_win.grab_set()
        
        tk.Label(
            edit_win,
            text=f"Edit {col_name}:",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=("Segoe UI", 10)
        ).pack(pady=(20, 5))
        
        entry_var = tk.StringVar(value=current_value)
        entry = tk.Entry(
            edit_win,
            textvariable=entry_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            width=40
        )
        entry.pack(pady=5, padx=20)
        entry.focus_set()
        entry.select_range(0, tk.END)
        
        def save():
            new_value = entry_var.get().strip()
            # Update tree
            values = list(self.contacts_tree.item(item, "values"))
            values[col_idx] = new_value
            self.contacts_tree.item(item, values=values)
            
            # Save to file
            self._save_contacts_to_file()
            try:
                self._set_status("Contact updated", GOOD)
            except:
                pass
            edit_win.destroy()
        
        def cancel():
            edit_win.destroy()
        
        btn_frame = tk.Frame(edit_win, bg=BG_ROOT)
        btn_frame.pack(pady=15)
        
        tk.Button(
            btn_frame,
            text="Save",
            command=save,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            relief="flat",
            font=("Segoe UI Semibold", 9),
            padx=20,
            pady=6,
            cursor="hand2"
        ).pack(side="left", padx=5)
        
        tk.Button(
            btn_frame,
            text="Cancel",
            command=cancel,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            relief="flat",
            font=("Segoe UI", 9),
            padx=20,
            pady=6,
            cursor="hand2"
        ).pack(side="left", padx=5)
        
        entry.bind("<Return>", lambda e: save())
        entry.bind("<Escape>", lambda e: cancel())
    
    def _delete_selected_contact(self):
        """Delete the selected contact(s) from the table"""
        if not hasattr(self, 'contacts_tree'):
            return
        
        selected = self.contacts_tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select a contact to delete.")
            return
        
        # Confirm deletion
        count = len(selected)
        msg = f"Delete {count} contact(s)?"
        if not messagebox.askyesno("Confirm Delete", msg):
            return
        
        # Delete from tree
        for item in selected:
            self.contacts_tree.delete(item)
        
        # Save to file
        self._save_contacts_to_file()
        try:
            self._set_status(f"Deleted {count} contact(s)", GOOD)
        except:
            pass
    
    def _save_contacts_to_file(self):
        """Save all contacts from tree back to the CSV file"""
        if not hasattr(self, 'contacts_tree'):
            return
        
        try:
            # Get all contacts from tree
            contacts = []
            for item in self.contacts_tree.get_children():
                values = self.contacts_tree.item(item, "values")
                if len(values) >= 5:
                    contacts.append({
                        "Email": values[0],
                        "FirstName": values[1],
                        "LastName": values[2],
                        "Company": values[3],
                        "JobTitle": values[4]
                    })
            
            # Write to file
            ensure_dir(os.path.dirname(OFFICIAL_CONTACTS_PATH))
            with open(OFFICIAL_CONTACTS_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CONTACT_FIELDS)
                writer.writeheader()
                writer.writerows(contacts)
            
        except Exception as e:
            pass  # self._set_status("Failed to save contacts", DANGER)


    def _add_new_contact(self):
        """Open dialog to add a new contact manually"""
        add_win = tk.Toplevel(self)
        add_win.title("Add New Contact")
        add_win.geometry("450x320")
        add_win.configure(bg=BG_ROOT)
        add_win.transient(self)
        add_win.grab_set()
        
        tk.Label(
            add_win,
            text="Add New Contact",
            bg=BG_ROOT,
            fg=ACCENT,
            font=("Segoe UI Semibold", 13)
        ).pack(pady=(15, 10))
        
        # Create entry fields
        fields = {}
        field_names = [("Email", "Email"), ("FirstName", "First Name"), 
                      ("LastName", "Last Name"), ("Company", "Company"), 
                      ("JobTitle", "Job Title")]
        
        for field_key, field_label in field_names:
            frame = tk.Frame(add_win, bg=BG_ROOT)
            frame.pack(fill="x", padx=30, pady=5)
            
            tk.Label(
                frame,
                text=f"{field_label}:",
                bg=BG_ROOT,
                fg=FG_TEXT,
                font=("Segoe UI", 9),
                width=12,
                anchor="w"
            ).pack(side="left")
            
            var = tk.StringVar()
            entry = tk.Entry(
                frame,
                textvariable=var,
                bg=BG_ENTRY,
                fg=FG_TEXT,
                insertbackground=FG_TEXT,
                relief="flat",
                font=FONT_BASE
            )
            entry.pack(side="left", fill="x", expand=True)
            fields[field_key] = var
        
        def save():
            email = fields["Email"].get().strip()
            if not email:
                messagebox.showwarning("Missing Email", "Email is required.")
                return
            
            # Add to tree
            self.contacts_tree.insert("", "end", values=(
                email,
                fields["FirstName"].get().strip(),
                fields["LastName"].get().strip(),
                fields["Company"].get().strip(),
                fields["JobTitle"].get().strip()
            ))
            
            # Save to file
            self._save_contacts_to_file()
            try:
                self._set_status("Contact added", GOOD)
            except:
                pass
            add_win.destroy()
        
        def cancel():
            add_win.destroy()
        
        btn_frame = tk.Frame(add_win, bg=BG_ROOT)
        btn_frame.pack(pady=20)
        
        tk.Button(
            btn_frame,
            text="Add Contact",
            command=save,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            relief="flat",
            font=("Segoe UI Semibold", 10),
            padx=20,
            pady=8,
            cursor="hand2"
        ).pack(side="left", padx=5)
        
        tk.Button(
            btn_frame,
            text="Cancel",
            command=cancel,
            bg="#F1F5F9",
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            relief="flat",
            font=("Segoe UI", 9),
            padx=20,
            pady=7,
            cursor="hand2"
        ).pack(side="left", padx=5)

    def _open_contacts_table(self):
        path = OFFICIAL_CONTACTS_PATH
        if not path or not os.path.isfile(path):
            messagebox.showerror("Not found", f"Official contacts.csv not found:\n{path}")
            self._set_status("Contacts missing", DANGER)
            return
        ContactsTableWindow(self, path)

    # ============================================
    # Tools card: Preview + Create + Cancel
    # ============================================
    def _build_tools_card(self, parent, row=2, mode: str = "all"):
        """
        mode:
          - "all"          : preview + create + cancel
          - "preview_only" : preview block only
          - "create_only"  : create sequence block only
          - "cancel_only"  : cancel pending block only
        """
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 8))

        frame = tk.Frame(card, bg=BG_CARD)
        frame.pack(fill="x", padx=12, pady=12)

        include_preview = mode in ("all", "preview_only")
        include_create = mode in ("all", "create_only")
        include_cancel = mode in ("all", "cancel_only")

        # PREVIEW EMAILS
        if include_preview:
            test_box = tk.Frame(frame, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
            test_box.pack(fill="x")

            header_row = tk.Frame(test_box, bg=BG_ENTRY)
            header_row.pack(fill="x", padx=10, pady=(10, 6))

            tk.Label(
                header_row,
                text="Preview emails",
                bg=BG_ENTRY,
                fg=ACCENT,
                font=("Segoe UI Semibold", 13),
            ).pack(side="left")

            tk.Label(
                header_row,
                text="Input your email address and hit send to preview all emails",
                bg=BG_ENTRY,
                fg=FG_MUTED,
                font=("Segoe UI", 9),
            ).pack(side="left", padx=(10, 0))

            row2 = tk.Frame(test_box, bg=BG_ENTRY)
            row2.pack(fill="x", padx=10, pady=(0, 10))

            tk.Entry(
                row2,
                textvariable=self.test_email_var,
                bg=BG_ENTRY,
                fg=FG_TEXT,
                insertbackground=FG_TEXT,
                relief="flat",
                font=FONT_BASE,
                highlightthickness=1,
                highlightbackground=BORDER_MEDIUM,
                highlightcolor=ACCENT,
            ).pack(side="left", fill="x", expand=True)

            btn_test = tk.Button(
                row2,
                text="Send Test Emails",
                command=self._send_test_emails,
                bg=DARK_AQUA,
                fg=FG_WHITE,
                activebackground=DARK_AQUA_HOVER,
                activeforeground=FG_WHITE,
                relief="flat",
                font=("Segoe UI Semibold", 9),
                padx=12,
                pady=7,
                cursor="hand2",
            )
            btn_test.pack(side="left", padx=(10, 0))
            ToolTip(btn_test, "Sends your sequence to the address above (includes per-email attachments).")

        # CREATE SEQUENCE
        if include_create:
            create_box = tk.Frame(frame, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
            create_box.pack(fill="x", pady=(10, 0))

            tk.Label(
                create_box,
                text="Create sequence",
                bg=BG_ENTRY,
                fg=ACCENT,
                font=("Segoe UI Semibold", 13),
                padx=10,
            ).pack(anchor="w", pady=(10, 4))

            tk.Label(
                create_box,
                text="Save your settings, then run Funnel Forge below to create your email sequence",
                bg=BG_ENTRY,
                fg=FG_MUTED,
                font=("Segoe UI", 9),
                padx=10,
            ).pack(anchor="w", pady=(0, 10))

            create_row = tk.Frame(create_box, bg=BG_ENTRY)
            create_row.pack(fill="x", padx=10, pady=(0, 10))

            btn_save = ttk.Button(create_row, text="Save", style="Accent.TButton", command=self._save_all_with_feedback)
            btn_save.pack(side="left")

            btn_run = tk.Button(
                create_row,
                text="Run Funnel Forge",
                command=self._run_sequence,
                bg=DARK_AQUA,
                fg=FG_WHITE,
                activebackground=DARK_AQUA_HOVER,
                activeforeground=FG_WHITE,
                relief="flat",
                font=("Segoe UI Semibold", 10),
                padx=14,
                pady=7,
                cursor="hand2",
            )
            btn_run.pack(side="left", padx=(10, 0))
            ToolTip(btn_run, "Schedules/sends through Outlook Classic using your current configuration.")

        # CANCEL PENDING EMAILS
        if include_cancel:
            cancel_box = tk.Frame(frame, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
            cancel_box.pack(fill="x", pady=(10, 0))

            tk.Label(
                cancel_box,
                text="Cancel a previous sequence",
                bg=BG_ENTRY,
                fg=ACCENT,
                font=("Segoe UI Semibold", 13),
                padx=10,
            ).pack(anchor="w", pady=(10, 4))

            tk.Label(
                cancel_box,
                text="Removes pending/scheduled emails. For singles, use email. For companies, use @domain.com",
                bg=BG_ENTRY,
                fg=FG_MUTED,
                font=("Segoe UI", 9),
                padx=10,
            ).pack(anchor="w", pady=(0, 10))

            cancel_row = tk.Frame(cancel_box, bg=BG_ENTRY)
            cancel_row.pack(fill="x", padx=10, pady=(0, 10))

            entry = tk.Entry(
                cancel_row,
                textvariable=self.cancel_query_var,
                bg=BG_ENTRY,
                fg=FG_TEXT,
                insertbackground=FG_TEXT,
                relief="flat",
                font=FONT_BASE,
                highlightthickness=1,
                highlightbackground=BORDER_MEDIUM,
                highlightcolor=ACCENT,
            )
            entry.pack(side="left", fill="x", expand=True)

            mode_box = tk.Frame(cancel_row, bg=BG_ENTRY)
            mode_box.pack(side="left", padx=(10, 10))

            tk.Radiobutton(
                mode_box,
                text="Email",
                variable=self.cancel_mode_var,
                value="email",
                bg=BG_ENTRY,
                fg=FG_TEXT,
                selectcolor=BG_ENTRY,
                activebackground=BG_ENTRY,
                activeforeground=FG_TEXT,
            ).pack(side="top", anchor="w")

            tk.Radiobutton(
                mode_box,
                text="Domain",
                variable=self.cancel_mode_var,
                value="domain",
                bg=BG_ENTRY,
                fg=FG_TEXT,
                selectcolor=BG_ENTRY,
                activebackground=BG_ENTRY,
                activeforeground=FG_TEXT,
            ).pack(side="top", anchor="w")

            btn_cancel = tk.Button(
                cancel_row,
                text="Cancel + Delete",
                command=self._cancel_pending_emails,
                bg=DARK_AQUA,
                fg=FG_WHITE,
                activebackground=DARK_AQUA_HOVER,
                activeforeground=FG_WHITE,
                relief="flat",
                font=("Segoe UI Semibold", 9),
                padx=12,
                pady=7,
                cursor="hand2",
            )
            btn_cancel.pack(side="left")
            ToolTip(btn_cancel, "Finds matching pending emails in Outbox and moves them to Deleted Items.")

    # ============================================
    # Sequence management
    # ============================================
    def _add_email_from_button(self):
        """Add a new email when user clicks + Add Email tab"""
        # Check max limit
        if len(self.subject_vars) >= 15:
            messagebox.showinfo("Maximum emails", "You can have at most 15 emails in your sequence.")
            self._set_status("Cannot add more emails", WARN)
            return

        # Calculate next email number and date
        next_num = len(self.subject_vars) + 1

        # Calculate date: last email's date + 3 days
        if self.date_vars:
            try:
                last_date_str = self.date_vars[-1].get()
                last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
                next_date = (last_date + timedelta(days=3)).strftime("%Y-%m-%d")
            except:
                next_date = (datetime.now() + timedelta(days=3 * next_num)).strftime("%Y-%m-%d")
        else:
            next_date = datetime.now().strftime("%Y-%m-%d")

        # Add the email
        self._add_email(
            name=f"Email {next_num}",
            subject="",
            body="",
            date=next_date,
            time="9:00 AM"
        )

        # Switch to the newly created tab (the last one)
        try:
            tabs = self.email_notebook.tabs()
            if len(tabs) >= 1:
                self.email_notebook.select(tabs[-1])
        except:
            pass

        self._set_status(f"Email {next_num} added", GOOD)

    def _add_email(self, subject: str = "", body: str = "", date: str = "", time: str = "", name: str = ""):
        idx = len(self.subject_vars) + 1

        name_default = name.strip() if name else f"Email {idx}"
        name_var = tk.StringVar(value=name_default)

        subj_var = tk.StringVar(value=subject)
        date_var = tk.StringVar(value=date)
        time_var = tk.StringVar(value=time if time else "9:00 AM")

        # No need for variable traces - schedule panel uses textvariable for automatic updates

        self.name_vars.append(name_var)
        self.subject_vars.append(subj_var)
        self.date_vars.append(date_var)
        self.time_vars.append(time_var)

        self.per_email_attachments.append([])

        body_widget = self._create_email_tab(idx, name_var, subj_var, body_text=body)
        self.body_texts.append(body_widget)

        self._rebuild_sequence_table()
        self._rebuild_schedule_panel()
        self._refresh_tab_labels()
        # self._set_status("Email added", GOOD)  # Disabled to prevent startup crash

    def _delete_email(self, index: int):
        """Delete an email from the sequence - NO CONFIRMATION DIALOGS"""
        # Silently prevent deletion if only 1 email (X should be hidden anyway)
        if len(self.subject_vars) <= 1:
            return

        if index < 0 or index >= len(self.subject_vars):
            return

        # Get current bodies before deletion
        bodies = [t.get("1.0", "end").rstrip() for t in self.body_texts]

        # Remove data for this email
        del self.name_vars[index]
        del self.subject_vars[index]
        del self.date_vars[index]
        del self.time_vars[index]
        del self.per_email_attachments[index]
        del bodies[index]

        # Remove all tabs from notebook
        for tab_id in self.email_notebook.tabs():
            self.email_notebook.forget(tab_id)

        # Rebuild all email tabs with re-indexed names (Email 1, Email 2, ...)
        self.body_texts = []
        for i, (name_var, subj_var, body_text) in enumerate(zip(self.name_vars, self.subject_vars, bodies), start=1):
            body_widget = self._create_email_tab(i, name_var, subj_var, body_text=body_text)
            self.body_texts.append(body_widget)

        # Select a valid tab after deletion (previous tab or first tab)
        try:
            tabs = self.email_notebook.tabs()
            if tabs:
                # Select previous tab if available, otherwise first tab
                new_index = max(0, min(index, len(tabs) - 1))
                self.email_notebook.select(tabs[new_index])
        except:
            pass

        # Update sequence table, schedule panel, and tab labels
        self._rebuild_sequence_table()
        self._rebuild_schedule_panel()
        self._refresh_tab_labels()
        self._set_status("Email deleted", WARN)

    def _delete_current_email(self):
        """Delete the currently selected email from the control row Delete button"""
        if not hasattr(self, "email_notebook"):
            return

        # Prevent deletion if only 1 email
        if len(self.subject_vars) <= 1:
            messagebox.showinfo("Cannot delete", "You must have at least one email in your campaign.")
            return

        try:
            # Get the currently selected tab index
            current_tab = self.email_notebook.index(self.email_notebook.select())
            self._delete_email(current_tab)
        except:
            pass

    def _on_tab_changed(self, event=None):
        """Update date/time controls when user switches between email tabs (without fluttering)"""
        if not hasattr(self, "email_notebook"):
            return
        if not hasattr(self, "control_date_var") or not hasattr(self, "control_time_var"):
            return

        try:
            # Get the currently selected tab index
            current_tab = self.email_notebook.index(self.email_notebook.select())

            if current_tab < 0 or current_tab >= len(self.date_vars):
                return

            # Copy the selected email's date/time into control row vars (without triggering trace callbacks)
            # Temporarily disable trace callbacks to prevent rebuilding
            self._updating_from_tab_change = True

            date_val = self.date_vars[current_tab].get()
            time_val = self.time_vars[current_tab].get()

            self.control_date_var.set(date_val)
            self.control_time_var.set(time_val)

            self._updating_from_tab_change = False

            # Update schedule panel highlighting
            self._update_schedule_panel_highlighting(current_tab)
        except:
            self._updating_from_tab_change = False

    def _on_control_date_changed(self, *args):
        """When user changes date in control row, update the selected email's date"""
        if getattr(self, "_updating_from_tab_change", False):
            return  # Ignore changes triggered by tab switching

        if not hasattr(self, "email_notebook"):
            return

        try:
            current_tab = self.email_notebook.index(self.email_notebook.select())
            if current_tab >= 0 and current_tab < len(self.date_vars):
                # Copy control row date to selected email's date var
                self.date_vars[current_tab].set(self.control_date_var.get())
        except:
            pass

    def _on_control_time_changed(self, *args):
        """When user changes time in control row, update the selected email's time"""
        if getattr(self, "_updating_from_tab_change", False):
            return  # Ignore changes triggered by tab switching

        if not hasattr(self, "email_notebook"):
            return

        try:
            current_tab = self.email_notebook.index(self.email_notebook.select())
            if current_tab >= 0 and current_tab < len(self.time_vars):
                # Copy control row time to selected email's time var
                self.time_vars[current_tab].set(self.control_time_var.get())
        except:
            pass

    def _preview_sequence(self):
        if not self.subject_vars:
            messagebox.showinfo("Sequence", "No emails in the sequence yet.")
            self._set_status("Nothing to preview", WARN)
            return

        lines = [f"Scheduling uses local computer time ({self.tz_label}).", ""]

        for i in range(len(self.subject_vars)):
            label = self.name_vars[i].get().strip() if i < len(self.name_vars) else f"Email {i+1}"
            label = label or f"Email {i+1}"
            subj = self.subject_vars[i].get().strip() or label
            date = self.date_vars[i].get().strip() or "(no date)"
            time_str = self.time_vars[i].get().strip() or "(no time)"

            per_count = len(self.per_email_attachments[i]) if i < len(self.per_email_attachments) else 0
            per_label = f"{per_count} attachment(s) for this email" if per_count else "No attachments"

            lines.append(f"{label}: {subj}")
            lines.append(f"   {date} @ {time_str}")
            lines.append(f"   {per_label}")
            lines.append("")

        messagebox.showinfo("Sequence Preview", "\n".join(lines).strip())
        self._set_status("Sequence previewed", GOOD)

    # ============================================
    # Preview test emails (per-email attachments)
    # ============================================
    def _send_test_emails(self):
        if win32 is None:
            messagebox.showerror(
                "Outlook not available",
                "pywin32 / Outlook COM is not available.\n\nInstall pywin32 and make sure Outlook Classic is installed.",
            )
            self._set_status("Outlook missing", DANGER)
            return

        to_addr = self.test_email_var.get().strip()
        if not to_addr:
            messagebox.showerror("Missing", "Enter an email address for test sends.")
            self._set_status("Email required", WARN)
            return
        if not EMAIL_RE.match(to_addr):
            messagebox.showerror("Invalid", f"That doesn't look like a valid email:\n{to_addr}")
            self._set_status("Invalid email", WARN)
            return

        subjects = []
        bodies = []
        for i, v in enumerate(self.subject_vars):
            label = self.name_vars[i].get().strip() if i < len(self.name_vars) else f"Email {i+1}"
            label = label or f"Email {i+1}"
            subjects.append(v.get().strip() or label)
            bodies.append(self.body_texts[i].get("1.0", "end").rstrip())

        tokens = {
            "Email": to_addr,
            "FirstName": "Test",
            "LastName": "Contact",
            "Company": "Test Company",
            "JobTitle": "Test Title",
        }
        merged_bodies = [merge_tokens(b, tokens) for b in bodies]

        ok = messagebox.askyesno(
            "Send Test Emails",
            f"This will send {len(subjects)} emails to:\n\n{to_addr}\n\nProceed?"
        )
        if not ok:
            self._set_status("Send cancelled", WARN)
            return

        try:
            try:
                outlook = win32.gencache.EnsureDispatch("Outlook.Application")  # type: ignore
            except Exception:
                outlook = win32.Dispatch("Outlook.Application")  # type: ignore

            try:
                ns = outlook.GetNamespace("MAPI")
                try:
                    ns.Logon()
                except Exception:
                    pass
            except Exception:
                pass

            for i in range(len(subjects)):
                mail = outlook.CreateItem(0)
                mail.To = to_addr
                mail.Subject = normalize_text(f"[TEST] {subjects[i]}")
                mail.Body = normalize_text(merged_bodies[i])

                files = self.per_email_attachments[i] if i < len(self.per_email_attachments) else []
                for fp in files:
                    try:
                        if fp and os.path.isfile(fp):
                            mail.Attachments.Add(fp)
                    except Exception:
                        pass

                mail.Send()

            self._set_status("Test emails sent", GOOD)
            messagebox.showinfo("Sent", "Test emails sent.\n\nCheck your inbox (and Sent Items).")
        except Exception as e:
            self._set_status("Send failed", DANGER)
            messagebox.showerror("Error", f"Could not send test emails:\n{e}")

    # ============================================
    # Cancel pending (Outbox -> Deleted Items)
    # ============================================
    def _cancel_pending_emails(self):
        if win32 is None:
            messagebox.showerror(
                "Outlook not available",
                "pywin32 / Outlook COM is not available.\n\nInstall pywin32 and make sure Outlook Classic is installed.",
            )
            self._set_status("Outlook missing", DANGER)
            return

        q = self.cancel_query_var.get().strip()
        mode = self.cancel_mode_var.get().strip()

        if not q:
            messagebox.showerror("Missing", "Enter an email or domain to cancel (example: someone@company.com or @company.com).")
            self._set_status("Input required", WARN)
            return

        if mode == "domain":
            if "@" not in q:
                q = "@" + q
            q = q.lower()

        if mode == "email":
            if not EMAIL_RE.match(q):
                messagebox.showerror("Invalid", f"That doesn't look like a valid email:\n{q}")
                self._set_status("Invalid email", WARN)
                return

        ok = messagebox.askyesno(
            "Confirm Cancel",
            f"This will remove pending Outbox emails matching:\n\n{q}\n\nand move them to Deleted Items.\n\nProceed?"
        )
        if not ok:
            self._set_status("Cancel cancelled", WARN)
            return

        try:
            outlook = win32.Dispatch("Outlook.Application")  # type: ignore
            ns = outlook.GetNamespace("MAPI")

            now = datetime.now()
            moved = 0
            scanned = 0

            for i in range(1, ns.Folders.Count + 1):
                store = ns.Folders.Item(i)
                try:
                    outbox = store.Folders.Item("Outbox")
                except Exception:
                    continue

                deleted = None
                for del_name in ("Deleted Items", "Deleted", "Trash"):
                    try:
                        deleted = store.Folders.Item(del_name)
                        break
                    except Exception:
                        continue
                if deleted is None:
                    try:
                        deleted = ns.GetDefaultFolder(3)  # olFolderDeletedItems
                    except Exception:
                        deleted = None

                items = outbox.Items
                try:
                    count = items.Count
                except Exception:
                    count = 0

                for idx in range(count, 0, -1):
                    try:
                        item = items.Item(idx)
                    except Exception:
                        continue

                    scanned += 1

                    try:
                        _ = item.Subject
                        _ = item.To
                    except Exception:
                        continue

                    try:
                        ddt = item.DeferredDeliveryTime
                        if ddt:
                            try:
                                if ddt <= now:
                                    continue
                            except Exception:
                                pass
                    except Exception:
                        pass

                    try:
                        to_field = str(item.To or "")
                    except Exception:
                        to_field = ""

                    to_l = to_field.lower()

                    if mode == "email":
                        match = q.lower() in to_l
                    else:
                        match = q in to_l

                    if not match:
                        continue

                    if deleted is None:
                        try:
                            item.Delete()
                            moved += 1
                        except Exception:
                            pass
                    else:
                        try:
                            item.Move(deleted)
                            moved += 1
                        except Exception:
                            try:
                                item.Delete()
                                moved += 1
                            except Exception:
                                pass

            self._set_status("Pending emails cancelled", GOOD)
            messagebox.showinfo("Cancelled", f"Cancelled (moved) {moved} pending Outbox emails.\n\nScanned: {scanned}")
        except Exception:
            _write_crash_log("cancel_pending")
            self._set_status("Cancel failed", DANGER)
            messagebox.showerror(
                "Cancel failed",
                "Could not cancel pending emails.\n\nA crash log was written to:\n%LOCALAPPDATA%\\Funnel Forge\\logs"
            )

    # ============================================
    # Save / Load Config
    # ============================================
    def _collect_config(self):
        emails = []
        for i in range(len(self.subject_vars)):
            subj = self.subject_vars[i].get()
            body = self.body_texts[i].get("1.0", "end").rstrip()
            date = self.date_vars[i].get()
            time = self.time_vars[i].get()
            name = self.name_vars[i].get() if i < len(self.name_vars) else f"Email {i+1}"
            per_attach = self.per_email_attachments[i] if i < len(self.per_email_attachments) else []
            emails.append({
                "name": name,
                "subject": subj,
                "body": body,
                "date": date,
                "time": time,
                "per_attachments": per_attach
            })

        return {
            "emails": emails,
            "test_email": self.test_email_var.get(),
        }

    def _save_bodies_to_files(self):
        for filename, text_widget in zip(BODY_FILES, self.body_texts):
            path = user_path(filename)
            content = text_widget.get("1.0", "end").rstrip() + "\n"
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception:
                pass

    def _save_all(self):
        cfg = self._collect_config()
        save_config(cfg)
        self._save_bodies_to_files()

    def _save_all_with_feedback(self):
        try:
            self._save_all()
            self._set_status("Saved", GOOD)
            messagebox.showinfo("Saved", "Settings + bodies saved.")
        except Exception:
            _write_crash_log("gui_save")
            self._set_status("Save failed", DANGER)
            messagebox.showerror("Save Failed", "Could not save. Check logs in:\n%LOCALAPPDATA%\\Funnel Forge\\logs")

    def _init_default_emails(self):
        if self.subject_vars:
            return
        now = datetime.now()
        for i in range(4):
            d = (now + timedelta(days=3 * i)).strftime("%Y-%m-%d")
            self._add_email(name=f"Email {i+1}", subject="", body="", date=d, time="9:00 AM")

    def _load_from_config_dict(self, cfg: dict):
        for tab_id in getattr(self, "email_notebook", ttk.Notebook()).tabs():
            try:
                self.email_notebook.forget(tab_id)
            except Exception:
                pass

        self.name_vars = []
        self.subject_vars = []
        self.body_texts = []
        self.date_vars = []
        self.time_vars = []
        self.per_email_attachments = []

        emails_cfg = cfg.get("emails", []) if isinstance(cfg, dict) else []
        if not emails_cfg:
            self._init_default_emails()
        else:
            for e in emails_cfg:
                self._add_email(
                    name=e.get("name", ""),
                    subject=e.get("subject", ""),
                    body=e.get("body", ""),
                    date=e.get("date", ""),
                    time=e.get("time", "9:00 AM"),
                )
                try:
                    self.per_email_attachments[-1] = list(e.get("per_attachments", []) or [])
                except Exception:
                    pass

        if "test_email" in cfg:
            self.test_email_var.set(cfg["test_email"])

        self._rebuild_sequence_table()
        self._refresh_tab_labels()

    def _load_existing_config(self):
        cfg = load_config()
        if not isinstance(cfg, dict):
            cfg = {}
        self._load_from_config_dict(cfg)

    def _force_clean_startup(self):
        """Force clean defaults - ignore any saved config"""
        # Clear all email tabs
        for tab_id in getattr(self, "email_notebook", ttk.Notebook()).tabs():
            try:
                self.email_notebook.forget(tab_id)
            except Exception:
                pass

        # Reset all email state lists
        self.name_vars = []
        self.subject_vars = []
        self.body_texts = []
        self.date_vars = []
        self.time_vars = []
        self.per_email_attachments = []

        # Initialize exactly 4 default emails: Email 1, Email 2, Email 3, Email 4
        now = datetime.now()
        for i in range(4):
            d = (now + timedelta(days=3 * i)).strftime("%Y-%m-%d")
            self._add_email(name=f"Email {i+1}", subject="", body="", date=d, time="9:00 AM")

        # Clear contact list selection
        if hasattr(self, 'selected_contact_list_var'):
            self.selected_contact_list_var.set("")
        if hasattr(self, 'contact_list_info_var'):
            self.contact_list_info_var.set("No list selected")
        if hasattr(self, 'choose_contacts_table'):
            for item in self.choose_contacts_table.get_children():
                self.choose_contacts_table.delete(item)

        # Clear template selection
        if hasattr(self, 'template_var'):
            self.template_var.set("None")

        # Clear test email
        if hasattr(self, 'test_email_var'):
            self.test_email_var.set("")

        # Rebuild UI
        self._rebuild_sequence_table()
        self._refresh_tab_labels()

    # ============================================
    # Run Funnel Forge
    # ============================================
    def _stage_per_email_attachments(self) -> List[List[str]]:
        staged_root = user_path("PerEmailAttachments")
        ensure_dir(staged_root)

        staged: List[List[str]] = []
        for i, files in enumerate(self.per_email_attachments):
            email_dir = os.path.join(staged_root, f"Email_{i+1}")
            ensure_dir(email_dir)
            staged_list: List[str] = []

            for fp in files:
                if not fp or not os.path.isfile(fp):
                    continue
                try:
                    base = os.path.basename(fp)
                    dest = os.path.join(email_dir, base)
                    if os.path.exists(dest):
                        name, ext = os.path.splitext(base)
                        counter = 1
                        while True:
                            cand = os.path.join(email_dir, f"{name} ({counter}){ext}")
                            if not os.path.exists(cand):
                                dest = cand
                                break
                            counter += 1
                    shutil.copy2(fp, dest)
                    staged_list.append(dest)
                except Exception:
                    pass

            staged.append(staged_list)

        return staged

    def _run_sequence(self):
        # Prompt for campaign name before running
        campaign_name = simpledialog.askstring(
            "Name Your Campaign",
            "Enter a name for this campaign:",
            parent=self
        )

        if not campaign_name or not campaign_name.strip():
            messagebox.showinfo("Cancelled", "Campaign run cancelled. Please provide a name.")
            return

        campaign_name = campaign_name.strip()

        try:
            self._save_all()
        except Exception:
            _write_crash_log("gui_run_save")
            self._set_status("Save failed", DANGER)
            messagebox.showerror("Save Failed", "Could not save. Check logs in:\n%LOCALAPPDATA%\\Funnel Forge\\logs")
            return

        contacts_path = OFFICIAL_CONTACTS_PATH

        if not os.path.isfile(contacts_path):
            self._set_status("Contacts missing", DANGER)
            messagebox.showerror("Not found", f"Official contacts file does not exist:\n{contacts_path}")
            return
        if not self.subject_vars:
            self._set_status("No emails", WARN)
            messagebox.showerror("No emails", "You must have at least one email in your sequence.")
            return

        staged_per_email = self._stage_per_email_attachments()

        schedule = []
        for i in range(len(self.subject_vars)):
            label = self.name_vars[i].get().strip() if i < len(self.name_vars) else f"Email {i+1}"
            label = label or f"Email {i+1}"

            subj = self.subject_vars[i].get().strip() or label
            body = self.body_texts[i].get("1.0", "end").rstrip()
            date = self.date_vars[i].get().strip()
            time = self.time_vars[i].get().strip()

            if not date or not time:
                self._set_status("Schedule incomplete", WARN)
                messagebox.showerror("Missing schedule", f"{label} is missing a date or time.")
                return

            schedule.append({
                "subject": subj,
                "body": body,
                "date": date,
                "time": time,
                "attachments": staged_per_email[i] if i < len(staged_per_email) else [],
            })

        ok = messagebox.askyesno(
            "Confirm",
            "Begin your email sequence?\n\n"
            "Note: Outlook Classic must be open to run correctly.\n\n"
            "Proceed?"
        )
        if not ok:
            self._set_status("Run cancelled", WARN)
            return

        try:
            fourdrip_core.run_4drip(
                schedule=schedule,
                contacts_path=contacts_path,
                attachments_path=None,  # global attachments removed
                send_emails=True,
            )

            self._set_status(f"{len(schedule)} emails scheduled", GOOD)
            messagebox.showinfo("Sequence initiated", "Sequence initiated. Hit the phones")

        except TypeError as e:
            _write_crash_log("core_typeerror")
            self._set_status("Core mismatch", DANGER)
            messagebox.showerror(
                "Core error",
                "Your core function signature doesn't match what the GUI is calling.\n\n"
                f"Error:\n{e}\n\n"
                "Check the crash log in:\n%LOCALAPPDATA%\\Funnel Forge\\logs"
            )
        except Exception:
            _write_crash_log("core_failed")
            self._set_status("Core failed", DANGER)
            messagebox.showerror(
                "Error",
                "Core failed.\n\nA crash log was written to:\n%LOCALAPPDATA%\\Funnel Forge\\logs"
            )


        # Save campaign as active
        self._save_campaign_as_active(campaign_name)
        
        # Refresh dashboard
        if hasattr(self, '_refresh_active_campaigns'):
            self._refresh_active_campaigns()

# =========================
# Splash + launch
# =========================

def _launch_splash_then_main():
    root = tk.Tk()
    try:
        root.iconbitmap(resource_path("assets", "funnelforge.ico"))
    except Exception:
        pass

    root.overrideredirect(True)
    root.configure(bg=BG_HEADER)

    splash_path = resource_path("assets", "FunnelForge_splash.png")
    splash_img = None
    try:
        if os.path.exists(splash_path):
            splash_img = ImageTk.PhotoImage(Image.open(splash_path))
            splash_label = tk.Label(root, image=splash_img, bg=BG_HEADER)
        else:
            splash_label = tk.Label(root, text="Funnel Forge", bg=BG_HEADER, fg=ACCENT, font=("Segoe UI Black", 26))
    except Exception:
        splash_label = tk.Label(root, text="Funnel Forge", bg=BG_HEADER, fg=ACCENT, font=("Segoe UI Black", 26))

    splash_label.pack(padx=20, pady=20)

    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    def launch_main():
        root.destroy()
        app = FunnelForgeApp()
        app.mainloop()

    root.after(1200, launch_main)
    root.mainloop()


def main():
    """Entry point for the modular Funnel Forge app"""
    try:
        _launch_splash_then_main()
    except Exception:
        _write_crash_log("gui_startup")
        raise


if __name__ == "__main__":
    main()
    
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
import threading
import queue
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, Any, Dict, List, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

# -----------------------------
# Ensure package context (CRITICAL for PyInstaller)
# -----------------------------
if __package__ is None or __package__ == "":
    # Running as a script or frozen EXE
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    sys.path.insert(0, str(project_root))
    __package__ = "funnel_forge"

# -----------------------------
# Calendar/date picker (safe)
# -----------------------------
try:
    from tkcalendar import DateEntry as _DateEntry  # type: ignore
    DateEntry = _DateEntry
    HAVE_TKCAL = True
except Exception:
    DateEntry = None  # type: ignore
    HAVE_TKCAL = False

from PIL import Image, ImageTk

# Drag-and-drop from Windows Explorer (optional)
try:
    import windnd
    HAVE_WINDND = True
except ImportError:
    HAVE_WINDND = False

# Pillow resample constant
_RESAMPLING = getattr(Image, "Resampling", None)
RESAMPLE_LANCZOS: Any = getattr(_RESAMPLING, "LANCZOS", None)
if RESAMPLE_LANCZOS is None:
    RESAMPLE_LANCZOS = 0

# -----------------------------
# IMPORT STYLES (ABSOLUTE, SAFE)
# -----------------------------
from funnel_forge.styles import (
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
    CONFIG_PATH, TEMPLATES_DIR, SIGNATURE_PATH, CONTACTS_DIR, OFFICIAL_CONTACTS_PATH, CAMPAIGNS_DIR, SEGMENTS_DIR,
    SHARED_TEMPLATES_ROOT, SHARED_TEAM_DIR, SHARED_USER_DIR,
    SHARED_REGISTRY_DIR, SHARED_REGISTRY_PATH,
    SHARED_CONFIG_DIR, SHARED_CONFIG_PATH,
    CFG_KEY_HIDE_CONTACTS_IMPORT_POPUP,
    load_config, save_config, safe_read_csv_rows, merge_tokens, normalize_text,
    load_user_registry, save_user_registry, register_user, update_user_activity,
    is_admin, set_admin,
    _open_folder_in_explorer, _open_file_location,
    detect_and_convert_contacts_to_official,
    ensure_first_run_setup, ensure_default_template, ensure_default_campaign_exists,
    reset_app_data, get_default_config
)

from funnel_forge.html_format import (
    configure_format_tags, build_format_toolbar,
    text_to_html, html_to_text_widget, is_html, wrap_html_for_email,
)
from funnel_forge.ai_assist import (
    call_openai_async,
    build_write_email_messages, build_improve_email_messages,
    build_subject_line_messages, build_tone_change_messages,
    build_sequence_messages, build_schedule_messages,
)

# -----------------------------
# Core engine import (SAFE)
# -----------------------------
import funnelforge_core as fourdrip_core
fourdrip_core = importlib.reload(fourdrip_core)

# -----------------------------
# Outlook COM
# -----------------------------
try:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore
except Exception:
    pythoncom = None

# Outlook (for "Send Test Emails" and "Cancel Pending")
try:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore
    import win32com.client.dynamic  # type: ignore - CRITICAL: bypasses gencache
    HAVE_OUTLOOK = True
except Exception:
    pythoncom = None  # type: ignore
    win32com = None  # type: ignore
    HAVE_OUTLOOK = False


# =========================
# Outlook Preview Send (DYNAMIC DISPATCH)
# =========================

def send_preview_email(to_email: str, subject: str, body: str, attachments: list = None):
    """Send a single preview email via Outlook - DYNAMIC DISPATCH (no gencache)"""
    if not HAVE_OUTLOOK:
        raise RuntimeError("Outlook not available")

    pythoncom.CoInitialize()  # type: ignore
    try:
        outlook = win32com.client.dynamic.Dispatch("Outlook.Application")  # type: ignore
        mail = outlook.CreateItem(0)

        mail.To = to_email
        mail.Subject = subject
        if is_html(body):
            mail.HTMLBody = wrap_html_for_email(body)
        else:
            mail.Body = body

        # Attach files if provided
        if attachments:
            for filepath in attachments:
                if filepath and os.path.isfile(filepath):
                    mail.Attachments.Add(filepath)

        mail.Send()
    finally:
        pythoncom.CoUninitialize()  # type: ignore


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
        self._after_id = None
        widget.bind("<Enter>", self._schedule_show)
        widget.bind("<Leave>", self._hide)

    def _schedule_show(self, event=None):
        """Show tooltip after a short delay to avoid flash on quick mouse-overs."""
        self._cancel()
        self._after_id = self.widget.after(350, self._show)

    def _cancel(self):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self, event=None):
        if self.tipwindow or not self.text:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.configure(bg="#FFFFFF")

        # Keep tooltip above other windows
        try:
            tw.attributes("-topmost", True)
        except Exception:
            pass

        # Build the label first, then position — avoids gray flash on Windows
        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            bg="#FFFFFF",
            fg=ACCENT,
            relief="solid",
            borderwidth=1,
            font=FONT_BASE,
            padx=10,
            pady=6,
            wraplength=420         # prevents super-wide tooltips
        )
        label.pack()
        tw.update_idletasks()

        # Nudge left if tooltip would go off-screen
        sw = tw.winfo_screenwidth()
        w = tw.winfo_width()
        if x + w > sw - 10:
            x = max(10, sw - w - 10)

        tw.wm_geometry(f"+{x}+{y}")

    def _hide(self, event=None):
        self._cancel()
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
# Scrollable Frame Helper for Popups
# =========================

def make_scrollable_frame(parent, bg=None):
    """
    Create a scrollable frame inside a parent widget (typically a Toplevel).
    Returns the inner frame where you should pack/grid your content.
    """
    if bg is None:
        bg = BG_CARD

    container = ttk.Frame(parent)
    container.pack(fill="both", expand=True)

    canvas = tk.Canvas(container, highlightthickness=0, bg=bg)
    vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vbar.set)

    vbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner = ttk.Frame(canvas)  # Use ttk.Frame for consistency
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    # Update scroll region when inner frame content changes
    def _on_inner_configure(_):
        canvas.configure(scrollregion=canvas.bbox("all"))

    # Update inner frame width when canvas is resized
    def _on_canvas_configure(_):
        canvas.itemconfigure(window_id, width=canvas.winfo_width())

    inner.bind("<Configure>", _on_inner_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    # Mousewheel scrolling (Windows)
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # Bind only while this popup is focused
    parent.bind("<Enter>", lambda e: parent.bind_all("<MouseWheel>", _on_mousewheel))
    parent.bind("<Leave>", lambda e: parent.unbind_all("<MouseWheel>"))
    parent.bind("<Destroy>", lambda e: parent.unbind_all("<MouseWheel>"))

    return inner


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
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(
            top,
            text=contacts_path,
            bg=BG_ROOT,
            fg=FG_MUTED,
            font=FONT_SMALL,
        ).pack(anchor="w", pady=(4, 0))

        search_row = tk.Frame(self, bg=BG_ROOT)
        search_row.pack(fill="x", padx=14, pady=(0, 10))

        tk.Label(search_row, text="Search:", bg=BG_ROOT, fg=FG_TEXT,
                 font=FONT_BASE).pack(side="left")
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
            bg=BG_CARD,
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
        self.title(f"Attachments – {email_label}")
        self.configure(bg=BG_ROOT)
        self.geometry("480x420")
        self.resizable(False, False)

        self._files = files  # reference to the list (mutated in-place)
        self._on_update = on_update
        self._drop_queue = queue.Queue()  # thread-safe queue for windnd drops

        # ── Title ──
        tk.Label(
            self, text=f"Attachments – {email_label}",
            bg=BG_ROOT, fg=ACCENT, font=FONT_SECTION,
        ).pack(anchor="w", padx=16, pady=(14, 8))

        # ── Drop zone (click to upload) ──
        self._drop = tk.Canvas(
            self, bg=BG_ENTRY, height=180,
            highlightthickness=0, cursor="hand2",
        )
        self._drop.pack(fill="x", padx=16)
        self._drop.bind("<Configure>", self._draw_drop_zone)
        self._drop.bind("<Button-1>", lambda e: self._add_files())
        self._drop.bind("<Enter>", lambda e: self._drop.configure(bg=BG_HOVER))
        self._drop.bind("<Leave>", lambda e: self._drop.configure(bg=BG_ENTRY))

        # Enable Windows drag-and-drop onto the entire window
        if HAVE_WINDND:
            windnd.hook_dropfiles(self, func=self._on_drop_files)
            self._poll_drop_queue()

        # ── File list ──
        list_frame = tk.Frame(self, bg=BG_ROOT)
        list_frame.pack(fill="x", padx=16, pady=(8, 0))

        self.listbox = tk.Listbox(
            list_frame, bg=BG_ENTRY, fg=FG_TEXT,
            selectbackground=ACCENT_2, selectforeground=FG_TEXT,
            relief="flat", highlightthickness=1,
            highlightbackground=BORDER_MEDIUM, activestyle="none",
            font=FONT_SMALL, selectmode="extended", height=5,
        )
        self.listbox.pack(fill="x", side="left", expand=True)

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        vsb.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=vsb.set)

        # ── Buttons ──
        btn_row = tk.Frame(self, bg=BG_ROOT)
        btn_row.pack(fill="x", padx=16, pady=(8, 14))

        rm_btn = tk.Button(
            btn_row, text="Remove selected",
            command=self._remove_selected,
            bg=BORDER_SOFT, fg=FG_TEXT,
            activebackground=BG_HOVER, activeforeground=ACCENT,
            relief="flat", font=FONT_SMALL,
            padx=12, pady=6, cursor="hand2",
        )
        rm_btn.pack(side="left")
        rm_btn.bind("<Enter>", lambda e: rm_btn.config(bg="#FFFFFF", fg=ACCENT))
        rm_btn.bind("<Leave>", lambda e: rm_btn.config(bg=BORDER_SOFT, fg=FG_TEXT))

        close_btn = tk.Button(
            btn_row, text="Close",
            command=self.destroy,
            bg=ACCENT, fg=FG_WHITE,
            activebackground=ACCENT_HOVER, activeforeground=FG_WHITE,
            relief="flat", font=FONT_SMALL,
            padx=14, pady=6, cursor="hand2",
        )
        close_btn.pack(side="right")
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg=ACCENT_HOVER))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg=ACCENT))

        self._refresh_list()

    def _draw_drop_zone(self, event=None):
        """Draw dashed border and prompt text on the drop zone canvas."""
        self._drop.delete("all")
        w = self._drop.winfo_width()
        h = self._drop.winfo_height()
        pad = 6
        self._drop.create_rectangle(
            pad, pad, w - pad, h - pad,
            outline=GRAY_300, width=2, dash=(6, 4),
        )
        self._drop.create_text(
            w // 2, h // 2 - 8,
            text="Drag & Drop files or",
            font=FONT_SMALL, fill=FG_MUTED,
        )
        self._drop.create_text(
            w // 2, h // 2 + 10,
            text="Click to upload",
            font=("Segoe UI Semibold", 9), fill=FG_MUTED,
        )

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for fp in self._files:
            self.listbox.insert("end", os.path.basename(fp))

    def _notify_update(self):
        try:
            self._on_update()
        except Exception:
            pass

    def _add_files(self):
        files = filedialog.askopenfilenames(title="Select attachments")
        if not files:
            return
        self._ingest_files(files)

    def _on_drop_files(self, file_list):
        """Handle files dropped from Windows Explorer.
        windnd calls this from a non-main thread — MUST NOT touch any tkinter
        objects.  Just decode the paths and put them in a thread-safe queue;
        the main-thread polling loop (_poll_drop_queue) will pick them up."""
        paths = []
        for item in file_list:
            try:
                fp = item.decode("utf-8") if isinstance(item, bytes) else str(item)
                paths.append(fp)
            except Exception:
                pass
        if paths:
            self._drop_queue.put(paths)

    def _poll_drop_queue(self):
        """Main-thread loop: drain the drop queue and ingest files."""
        try:
            while True:
                paths = self._drop_queue.get_nowait()
                valid = [p for p in paths if os.path.isfile(p)]
                if valid:
                    self._ingest_files(valid)
        except queue.Empty:
            pass
        # Re-schedule as long as the window exists
        try:
            self.after(150, self._poll_drop_queue)
        except Exception:
            pass  # window was destroyed

    def _ingest_files(self, files):
        """Add new files to the attachment list (deduplicating)."""
        existing = set(self._files)
        added = 0
        for fp in files:
            fp = str(fp)
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
            font=FONT_TITLE,
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
            font=FONT_BASE,
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

        # ANTI-FLICKER: Use after() instead of update_idletasks() for centering
        def _center():
            try:
                px = parent.winfo_rootx()
                py = parent.winfo_rooty()
                pw = parent.winfo_width()
                ph = parent.winfo_height()
                w = self.winfo_width()
                h = self.winfo_height()
                x = px + (pw // 2) - (w // 2)
                y = py + (ph // 2) - (h // 2)
                self.geometry(f"+{x}+{y}")
            except:
                pass
        self.after(10, _center)

    def _close(self):
        try:
            self._on_done(bool(self.dont_show_var.get()))
        except Exception:
            pass
        self.destroy()


# =========================
# Toast Notification
# =========================

class ToastNotification(tk.Toplevel):
    """Non-modal toast notification that appears at bottom-right of parent."""

    def __init__(self, parent, message: str, on_view=None, on_undo=None, duration_ms: int = 8000):
        super().__init__(parent)
        self.overrideredirect(True)  # No window decorations
        self.configure(bg=BG_CARD)
        self.attributes("-topmost", True)

        self._parent = parent
        self._on_view = on_view
        self._on_undo = on_undo
        self._fade_after_id = None

        # Main frame with border
        frame = tk.Frame(self, bg=BG_CARD, highlightbackground=ACCENT, highlightthickness=2)
        frame.pack(fill="both", expand=True)

        # Content
        content = tk.Frame(frame, bg=BG_CARD)
        content.pack(fill="both", expand=True, padx=16, pady=12)

        # Success icon + message
        msg_row = tk.Frame(content, bg=BG_CARD)
        msg_row.pack(fill="x")

        tk.Label(
            msg_row,
            text="✓",
            bg=BG_CARD,
            fg=GOOD,
            font=FONT_TITLE,
        ).pack(side="left", padx=(0, 8))

        tk.Label(
            msg_row,
            text=message,
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_BASE,
            wraplength=280,
            justify="left",
        ).pack(side="left", fill="x", expand=True)

        # Close button
        close_btn = tk.Label(
            msg_row,
            text="✕",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=FONT_BASE,
            cursor="hand2",
        )
        close_btn.pack(side="right", padx=(8, 0))
        close_btn.bind("<Button-1>", lambda e: self._close())

        # Action buttons row
        if on_view or on_undo:
            btn_row = tk.Frame(content, bg=BG_CARD)
            btn_row.pack(fill="x", pady=(10, 0))

            if on_view:
                view_btn = tk.Button(
                    btn_row,
                    text="View",
                    command=self._do_view,
                    bg=DARK_AQUA,
                    fg=FG_WHITE,
                    activebackground=DARK_AQUA_HOVER,
                    activeforeground=FG_WHITE,
                    relief="flat",
                    font=FONT_BTN_SM,
                    padx=12,
                    pady=4,
                    cursor="hand2",
                )
                view_btn.pack(side="left", padx=(0, 8))

            if on_undo:
                undo_btn = tk.Button(
                    btn_row,
                    text="Undo",
                    command=self._do_undo,
                    bg=BG_ENTRY,
                    fg=FG_TEXT,
                    activebackground=BORDER_SOFT,
                    activeforeground=FG_TEXT,
                    relief="flat",
                    font=FONT_SMALL,
                    padx=12,
                    pady=4,
                    cursor="hand2",
                )
                undo_btn.pack(side="left")

        # Position toast
        self.after(10, self._position)

        # Auto-dismiss after duration
        if duration_ms > 0:
            self._fade_after_id = self.after(duration_ms, self._close)

    def _position(self):
        """Position toast at bottom-right of parent."""
        try:
            self.update_idletasks()
            px = self._parent.winfo_rootx()
            py = self._parent.winfo_rooty()
            pw = self._parent.winfo_width()
            ph = self._parent.winfo_height()
            tw = self.winfo_width()
            th = self.winfo_height()

            # Bottom-right with padding
            x = px + pw - tw - 20
            y = py + ph - th - 20
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _do_view(self):
        if self._on_view:
            self._on_view()
        self._close()

    def _do_undo(self):
        if self._on_undo:
            self._on_undo()
        self._close()

    def _close(self):
        if self._fade_after_id:
            self.after_cancel(self._fade_after_id)
        self.destroy()


# =========================
# Themed Input Dialog
# =========================

class ThemedInputDialog(tk.Toplevel):
    """A themed input dialog that matches the app's color scheme."""

    def __init__(self, parent, title: str, prompt: str, initialvalue: str = ""):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG_ROOT)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = None

        # Center on parent
        self.withdraw()

        # Main container
        container = tk.Frame(self, bg=BG_ROOT)
        container.pack(fill="both", expand=True, padx=24, pady=20)

        # Prompt label
        tk.Label(
            container,
            text=prompt,
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=FONT_BASE,
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        # Entry field
        self._entry_var = tk.StringVar(value=initialvalue)
        self._entry = tk.Entry(
            container,
            textvariable=self._entry_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_SECTION_TITLE,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            highlightcolor=ACCENT,
        )
        self._entry.pack(fill="x", ipady=6, pady=(0, 16))
        self._entry.focus_set()
        self._entry.select_range(0, "end")
        self._entry.bind("<Return>", lambda e: self._ok())
        self._entry.bind("<Escape>", lambda e: self._cancel())

        # Button row
        btn_row = tk.Frame(container, bg=BG_ROOT)
        btn_row.pack(fill="x")

        tk.Button(
            btn_row,
            text="OK",
            command=self._ok,
            bg=ACCENT,
            fg=FG_WHITE,
            activebackground=ACCENT,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=20,
            pady=6,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row,
            text="Cancel",
            command=self._cancel,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            activebackground=BORDER_SOFT,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            cursor="hand2",
            padx=16,
            pady=6,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="left")

        # Position and show
        self.update_idletasks()
        w = max(350, self.winfo_reqwidth())
        h = self.winfo_reqheight()
        px = parent.winfo_rootx() + (parent.winfo_width() // 2) - (w // 2)
        py = parent.winfo_rooty() + (parent.winfo_height() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{px}+{py}")
        self.deiconify()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _ok(self):
        self.result = self._entry_var.get()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


def themed_askstring(parent, title: str, prompt: str, initialvalue: str = "") -> str:
    """Show a themed input dialog and return the result (or None if cancelled)."""
    dialog = ThemedInputDialog(parent, title, prompt, initialvalue)
    parent.wait_window(dialog)
    return dialog.result


# =========================
# Edit Signature Window
# =========================

class EditSignatureWindow(tk.Toplevel):
    """Modal window for editing the user's email signature"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Edit Signature")
        self.configure(bg=BG_ROOT)
        self.geometry("700x550")
        self.minsize(700, 520)  # Prevent buttons from being clipped
        self.resizable(True, True)
        self.transient(parent)

        # Load current signature (strip delimiter if present for editing)
        self.signature_text = self._load_signature()

        # PACK BUTTONS FIRST (bottom) - ensures they're always visible
        btn_row = tk.Frame(self, bg=BG_ROOT)
        btn_row.pack(side="bottom", fill="x", padx=16, pady=(8, 16))

        tk.Button(
            btn_row,
            text="Cancel",
            command=self.destroy,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            padx=16,
            pady=8,
            cursor="hand2",
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_row,
            text="Save Signature",
            command=self._save_signature,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BUTTON,
            padx=16,
            pady=8,
            cursor="hand2",
        ).pack(side="right")

        # Header
        header = tk.Frame(self, bg=BG_ROOT)
        header.pack(side="top", fill="x", padx=16, pady=(16, 12))

        tk.Label(
            header,
            text="Edit Your Signature",
            bg=BG_ROOT,
            fg=ACCENT,
            font=FONT_TITLE,
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Type your signature once. Funnel Forge adds it to every email automatically.",
            bg=BG_ROOT,
            fg=FG_MUTED,
            font=FONT_SMALL,
        ).pack(anchor="w", pady=(4, 0))


        # Editor (fills remaining space between header and buttons)
        editor_frame = tk.Frame(self, bg=BG_ROOT)
        editor_frame.pack(side="top", fill="both", expand=True, padx=16, pady=(0, 8))

        tk.Label(
            editor_frame,
            text="Signature:",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=FONT_FIELD_HDR,
        ).pack(anchor="w", pady=(0, 6))

        # Strip delimiter from signature before showing to user
        display_text = self.signature_text
        if display_text.startswith("\n\n--\n"):
            display_text = display_text[5:]  # Remove delimiter

        self.text_editor = tk.Text(
            editor_frame,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            wrap="word",
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            highlightcolor=ACCENT,
        )
        self.text_editor.pack(fill="both", expand=True)
        self.text_editor.insert("1.0", display_text)

        # Center window
        self.after(10, self._center_window)

    def _load_signature(self) -> str:
        """Load signature from parent app cache"""
        # Load from parent's cached signature
        parent = self.master
        if hasattr(parent, "signature_text") and parent.signature_text:
            return parent.signature_text

        # Fallback: load from file
        try:
            if os.path.exists(SIGNATURE_PATH):
                with open(SIGNATURE_PATH, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception:
            pass

        # Default signature template
        return "\n\n--\nBest regards,\nYour Name\nYour Company\nyou@yourcompany.com\n(555) 123-4567"

    def _save_signature(self):
        """Save signature to file and update parent app"""
        try:
            signature = self.text_editor.get("1.0", "end-1c")

            # Ensure signature starts with delimiter
            delimiter = "\n\n--\n"
            if not signature.startswith(delimiter):
                signature = delimiter + signature.lstrip()

            # Ensure parent directory exists
            os.makedirs(os.path.dirname(SIGNATURE_PATH), exist_ok=True)

            # Save to file
            with open(SIGNATURE_PATH, "w", encoding="utf-8") as f:
                f.write(signature)

            # Update parent app cache and strip old signature from editors
            parent = self.master
            if hasattr(parent, "signature_text"):
                old_signature = parent.signature_text
                parent.signature_text = signature

                # Strip old signature from body editors (new one is added at send time)
                if hasattr(parent, "_update_all_email_signatures"):
                    parent._update_all_email_signatures(old_signature=old_signature)

                if hasattr(parent, "_refresh_execute_review_panel"):
                    try:
                        parent._refresh_execute_review_panel()
                    except:
                        pass

            messagebox.showinfo("Saved", "Signature saved! It will be added to emails when you send.")
            self.destroy()
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"Failed to save signature to:\n{SIGNATURE_PATH}\n\nError:\n{e}"
            )

    def _center_window(self):
        """Center window on parent"""
        try:
            self.update_idletasks()
            parent = self.master
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w = self.winfo_width()
            h = self.winfo_height()
            x = px + (pw // 2) - (w // 2)
            y = py + (ph // 2) - (h // 2)
            self.geometry(f"+{x}+{y}")
        except:
            pass


# --- UI Color Constants (mapped to design tokens) ---
from funnel_forge.styles import (
    SURFACE_CARD, GRAY_50, GRAY_100, GRAY_200, GRAY_300, GRAY_400,
    GRAY_500, GRAY_600, GRAY_700, GRAY_800, GRAY_900,
    PRIMARY_50, PRIMARY_500, PRIMARY_600,
    GOOD, DANGER, WARN,
    SUCCESS_BG, SUCCESS_FG, DANGER_BG, DANGER_FG,
    WARN_BG, WARN_FG, INFO_BG, INFO_FG,
    SURFACE_PAGE, SURFACE_INSET,
    NAV_DEFAULT_BG, NAV_DEFAULT_FG, NAV_HOVER_BG, NAV_HOVER_FG,
    NAV_ACTIVE_BG, NAV_ACTIVE_FG, NAV_ACTIVE_BAR, NAV_SUB_FG,
    FONT_CAPTION, FONT_SMALL, FONT_BASE, FONT_BODY, FONT_BODY_MEDIUM,
    FONT_SUBTITLE as FONT_SECTION_TITLE, FONT_SECTION, FONT_TITLE,
    FONT_HEADING, FONT_DISPLAY,
    FONT_BUTTON, FONT_BTN_SM, FONT_BTN_LG,
    SP_1, SP_2, SP_3, SP_4, SP_5, SP_6, SP_8, SP_10, SP_12,
)
from funnel_forge.ui_components import (
    make_button, make_card, make_section, make_divider,
    make_page_header, make_stat_card, make_badge,
    make_empty_state, make_sidebar, Toast,
)

# Legacy aliases for existing code that references these
PAGE_BG = SURFACE_PAGE
TEXT_MUTED = GRAY_500
BRAND_BLUE = PRIMARY_500
CARD_BORDER = GRAY_200
SHADOW_BG = GRAY_100


# =========================
# GUI App
# =========================

class FunnelForgeApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # FIRST-RUN SETUP: Ensure clean folder structure and default template
        ensure_first_run_setup()
        # ALWAYS ensure default template exists (permanent built-in)
        ensure_default_template()
        # ALWAYS ensure default campaign exists (auto-loaded system campaign)
        ensure_default_campaign_exists()

        # ANTI-FLICKER: Hide window during UI construction
        self.withdraw()

        self.title("Funnel Forge – Automated Email Engine")

        try:
            self.iconbitmap(resource_path("assets", "funnelforge_taskbar.ico"))
        except Exception:
            try:
                self.iconbitmap("funnelforge_taskbar.ico")
            except Exception:
                pass

        self.configure(bg=BG_ROOT)
        self.geometry("1180x800")
        self.minsize(980, 620)

        # Load banner image once at startup
        # FIXED HEADER HEIGHT - banner is scaled to this height, preserving aspect ratio
        self.header_height = 100  # Fixed header height (no stretching)

        try:
            # Load banner_left.png to fill header vertically (height-driven, not width)
            banner_path = resource_path("assets", "banner_left.png")
            banner_img = Image.open(banner_path)

            # Resize based on HEIGHT only - width is computed from aspect ratio
            aspect_ratio = banner_img.width / banner_img.height
            target_width = int(self.header_height * aspect_ratio)

            banner_resized = banner_img.resize((target_width, self.header_height), RESAMPLE_LANCZOS)
            self.banner_photo = ImageTk.PhotoImage(banner_resized)
        except Exception as e:
            print(f"Could not load banner: {e}")
            self.banner_photo = None

        # Client logo (top-right overlay)
        self.header_frame = None  # Will be set in _build_header
        self.client_logo_label = None
        self._client_logo_imgtk = None

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

        # Schedule mode: "fixed" or "relative"
        self.schedule_mode_var = tk.StringVar(value="fixed")
        self.relative_start_date_var = tk.StringVar(value="")  # YYYY-MM-DD
        self.relative_window_start_var = tk.StringVar(value="08:00")  # HH:MM 24h
        self.relative_window_end_var = tk.StringVar(value="10:30")  # HH:MM 24h
        self.relative_skip_weekends_var = tk.BooleanVar(value=True)
        self.delay_vars: List[tk.StringVar] = []  # Business days delay per email

        # Deliverability settings
        self.send_window_minutes_var = tk.StringVar(value="90")
        self.daily_send_limit_var = tk.StringVar(value="150")
        self.daily_limit_enabled_var = tk.BooleanVar(value=True)

        # Auto-Build Schedule (Relative helper that populates date/time fields)
        self.autobuild_start_date_var = tk.StringVar(value="")      # YYYY-MM-DD; blank means "next business day"
        self.autobuild_send_time_var = tk.StringVar(value="9:00 AM")
        self.autobuild_skip_weekends_var = tk.BooleanVar(value=True)
        self._autobuild_after_id: Optional[str] = None  # debounce apply button (optional)

        # Per-email attachments
        self.per_email_attachments: List[List[str]] = []
        self.per_email_manage_btns: List[tk.Button] = []
        self.per_email_attach_labels: List[tk.Label] = []

        # Contacts always points to OFFICIAL file
        self.contacts_path_var = tk.StringVar(value=OFFICIAL_CONTACTS_PATH)

        self.test_email_var = tk.StringVar(value="")
        self.cancel_query_var = tk.StringVar(value="")
        self.cancel_mode_var = tk.StringVar(value="email")  # email | domain
        self.cancel_help_var = tk.StringVar(value="")

        # Campaign selector
        self.campaign_selector_var = tk.StringVar(value="-- Start Fresh --")
        self.campaign_selector = None  # Will be set when UI is built

        # Campaign name (visible in Build a Campaign header)
        self.campaign_name_var = tk.StringVar(value="Untitled Campaign")
        # Track if currently editing the default system campaign
        self.is_editing_system_campaign = False

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

        # ANTI-FLICKER: Prevent unnecessary rebuilds
        self._seq_table_last_n = -1
        self._suspend_rebuilds = False

        # Sequence scheduling mode: "days" or "dates"
        self._seq_mode_var = tk.StringVar(value="days")

        # Guard flag to prevent "+" tab from triggering runaway email creation
        self._adding_email = False

        # Track last focused editor widget for variable insertion
        self._last_editor_widget = None  # type: Optional[tk.Widget]
        self._schedule_after_id: Optional[str] = None

        # Signature cache (loaded once at startup, updated when edited)
        self.signature_text = ""  # Will be loaded in _init_signature()

        # Screens + nav tracking
        self._nav_buttons: Dict[str, tk.Button] = {}
        self._screens: Dict[str, tk.Frame] = {}
        self._active_nav: Optional[str] = None

        self._build_styles()
        self._build_header()
        self.refresh_client_logo()  # Load client logo after header is built
        self._build_nav_and_content()
        self._build_status_bar()

        # DISABLED: Always start clean, never load previous session
        # self._load_existing_config()
        self._force_clean_startup()

        # AUTO-LOAD: Always load the default system campaign on startup
        self._auto_load_default_campaign()

        # SIGNATURE: Load signature and ensure it's in all email bodies
        self._init_signature()

        # ANTI-FLICKER: Show window after UI is fully built
        # (but stay hidden if registration is needed — _check_show_user_profile handles reveal)
        self.update_idletasks()
        config = load_config()
        if config.get("username"):
            self.deiconify()
            self.lift()
            self.focus_force()
        # else: window stays withdrawn until registration completes

        # Check for pending nurture list assignments (from completed campaigns)
        try:
            self._process_pending_nurture_assignment()
        except Exception:
            pass

        # AUTO-SCAN: Scan Outlook for campaign responses in background thread (non-blocking)
        self.after(2000, self._auto_scan_all_campaigns_on_startup)

        # STARTUP WIZARD: Show on first launch
        self.after(500, self._check_show_startup_wizard)

    # -------------------------------
    # Page Help Content (synced with Startup Wizard)
    # -------------------------------
    PAGE_HELP = {
        "Dashboard": [
            "HOW TO USE THIS PAGE:",
            "",
            "1. Click any campaign name to expand and see details",
            "2. Switch between 'Active' and 'Completed' tabs at the top",
            "3. Click the email count (e.g. '6 emails') to see email titles",
            "4. Click the contact count to see who you reached out to",
            "",
            "AUTOMATIC FEATURES:",
            "• Outlook is scanned for replies when you open FunnelForge",
            "• Responses auto-cancel ALL pending follow-up emails",
            "  (out-of-office replies are ignored and won't cancel emails)",
            "• 'Emails Removed' tracks emails cancelled from responses",
            "  or removed via Cancel Sequences",
            "• Stats update automatically as emails send"
        ],
        "Email Editor": [
            "HOW TO CREATE YOUR CAMPAIGN:",
            "",
            "1. Select a template from 'Your Templates' dropdown OR start fresh",
            "2. Click 'Explore Templates' to browse shared team templates",
            "3. Enter a subject line for each email",
            "4. Write your email body in the text area",
            "5. Add personalization by typing: {FirstName}, {Company}, {JobTitle}",
            "6. Click '+ Add Email' to add more emails to your sequence",
            "7. Click 'Delete Email' to remove the active email",
            "",
            "SAVING: Click 'Save Template' — choose 'Save' for yourself",
            "or 'Save and Share' to share with your team.",
            "",
            "TIP: Pasting from Word? Smart quotes and bullets are",
            "automatically cleaned up for you.",
            "",
            "NEXT STEP: Go to 'Send Schedule' to set timing and delivery"
        ],
        "Send Schedule": [
            "HOW TO SET YOUR SCHEDULE:",
            "",
            "1. Set Email 1's send date and time",
            "2. Set 'Wait (business days)' for steps 2+ (Mon–Fri, weekends skipped)",
            "3. Click 'Apply Schedule' to compute all send dates",
            "4. Click 'Add / Delete' to manage attachments (optional, drag & drop supported)",
            "",
            "PRESET SEQUENCES:",
            "• Pick a proven cadence (3-10 emails) and hit Apply",
            "• Click 'Customize' to adjust the days and times before applying",
            "",
            "SEND WINDOW (Deliverability):",
            "• Randomizes each contact's send time within a window (e.g., 1.5 hours)",
            "• Prevents all emails going out at the exact same time",
            "• Max 20 emails per minute — mimics natural sending behavior",
            "• Enabled by default — strongly recommended to keep on",
            "",
            "TIPS:",
            "• Space emails 2-3 business days apart",
            "• Morning sends (8-10 AM) get better open rates",
            "",
            "NEXT STEP: Go to 'Choose Contacts' to select recipients"
        ],
        "Choose Contacts": [
            "HOW TO ADD CONTACTS:",
            "",
            "1. Click 'Import CSV' to load contacts from a file",
            "   - CSV must have: Email, FirstName, LastName, Company, JobTitle",
            "2. OR click 'Add Contact' to add one contact manually",
            "3. Select a contact list from the dropdown to use it",
            "4. Click 'Delete Contact' to remove selected contacts",
            "",
            "NEXT STEP: Go to 'Preview and Launch' to send your campaign"
        ],
        "Preview and Launch": [
            "HOW TO LAUNCH YOUR CAMPAIGN:",
            "",
            "1. STAY CONNECTED (optional):",
            "   - Check the box to add contacts to a nurture list after the sequence",
            "2. PREVIEW EMAILS:",
            "   - Sends test emails to YOUR inbox so you can review",
            "3. RUN FUNNEL FORGE:",
            "   - Schedules all emails through Outlook",
            "",
            "IMPORTANT:",
            "• Keep Outlook OPEN for emails to send on schedule",
            "• Go to 'Cancel Sequences' if you need to stop emails"
        ],
        "Cancel Sequences": [
            "HOW TO CANCEL PENDING EMAILS:",
            "",
            "1. Find the email(s) you want to cancel in the list",
            "2. Select the checkbox next to each email to cancel",
            "3. Click 'Cancel Selected' to remove them from the queue",
            "",
            "OR use 'Cancel All' to stop the entire campaign",
            "",
            "NOTE: Emails already sent cannot be recalled."
        ],
        "Stay Connected": [
            "HOW TO USE STAY CONNECTED:",
            "",
            "1. Select a list from the left sidebar (or click '+' to create one)",
            "2. Go to the Contacts tab to add contacts (Import CSV)",
            "3. Go to the Messages tab to write your email",
            "4. Set the send date and time at the top",
            "5. Use {FirstName}, {Company}, etc. for personalization",
            "6. Click 'Send Email' to send to all contacts in the list",
            "",
            "Your signature is automatically added to every email."
        ],
        "Campaign Analytics": [
            "HOW TO USE ANALYTICS:",
            "",
            "1. Select a campaign from the dropdown to view its stats",
            "2. Review response rates and email performance",
            "3. Compare campaigns to find what works best",
            "",
            "Use these insights to improve your next campaign!"
        ],
        "Create a Campaign": [
            "HOW TO CREATE A CAMPAIGN:",
            "",
            "Follow these steps in order:",
            "",
            "1. BUILD EMAILS - Write your email sequence",
            "   • Add subject lines and body content",
            "   • Use {FirstName}, {Company} for personalization",
            "",
            "2. SEQUENCE AND ATTACHMENTS - Set timing",
            "   • Set business days between emails and click 'Update Dates'",
            "   • Use Preset Sequences for proven cadences (or Customize)",
            "   • Drag & drop file attachments",
            "",
            "3. CHOOSE CONTACTS - Select recipients",
            "   • Import a CSV or use existing list",
            "",
            "4. PREVIEW AND LAUNCH - Send it!",
            "   • Preview emails in your inbox first",
            "   • Click 'Run Funnel Forge' to launch"
        ],
        "Manage Contacts": [
            "HOW TO MANAGE YOUR CONTACTS:",
            "",
            "1. Click 'Import CSV' to load a new contact list",
            "   • File must have: Email, FirstName, LastName, Company, JobTitle",
            "",
            "2. Click 'New List' to create an empty list",
            "",
            "3. Select a list from the dropdown to view/edit it",
            "",
            "4. Click 'Add Contact' to add individual contacts",
            "",
            "5. Select contacts and click 'Delete' to remove them",
            "",
            "Your contact lists are saved and can be reused across campaigns."
        ],
    }

    def _show_page_help(self, title):
        """Show a help popup for the given page."""
        help_content = self.PAGE_HELP.get(title, ["No help available for this page."])

        popup = tk.Toplevel(self)
        popup.title(f"Help: {title}")
        popup.configure(bg=BG_CARD)
        popup.transient(self)
        popup.grab_set()
        popup.resizable(False, False)

        # Content frame
        content = tk.Frame(popup, bg=BG_CARD)
        content.pack(fill="both", expand=True, padx=20, pady=15)

        # Title with icon
        title_frame = tk.Frame(content, bg=BG_CARD)
        title_frame.pack(fill="x", pady=(0, 10))

        tk.Label(
            title_frame,
            text="ⓘ",
            bg=BG_CARD,
            fg=ACCENT,
            font=("Segoe UI", 16)
        ).pack(side="left")

        tk.Label(
            title_frame,
            text=f"  {title}",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_TITLE
        ).pack(side="left")

        # Help text
        text_widget = tk.Text(
            content,
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_BASE,
            wrap="word",
            relief="flat",
            height=12,
            width=50,
            highlightthickness=0,
            padx=5,
            pady=5
        )
        text_widget.pack(fill="both", expand=True)
        text_widget.insert("1.0", "\n".join(help_content))
        text_widget.config(state="disabled")

        # Close button
        tk.Button(
            content,
            text="Got it!",
            command=popup.destroy,
            bg=ACCENT,
            fg=FG_WHITE,
            activebackground=ACCENT_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=20,
            pady=8
        ).pack(pady=(15, 0))

        # Center popup on parent
        popup.update_idletasks()
        w = popup.winfo_reqwidth()
        h = popup.winfo_reqheight()
        px = self.winfo_rootx() + (self.winfo_width() // 2) - (w // 2)
        py = self.winfo_rooty() + (self.winfo_height() // 2) - (h // 2)
        popup.geometry(f"+{px}+{py}")

    # -------------------------------
    # Startup Wizard
    # -------------------------------
    def _check_show_startup_wizard(self):
        """Check if this is first launch and show wizard if needed, then check profile."""
        try:
            config = load_config()
            if not config.get("wizard_completed", False):
                self._show_startup_wizard()
        except Exception:
            pass
        # Always check profile after wizard (profile dialog is modal, won't conflict)
        self.after(300, self._check_show_user_profile)

    def _show_startup_wizard(self):
        """Show the startup wizard for first-time users."""
        wizard = tk.Toplevel(self)
        wizard.title("Welcome to FunnelForge")
        wizard.geometry("700x500")
        wizard.configure(bg=BG_ROOT)
        wizard.transient(self)
        wizard.grab_set()
        wizard.resizable(False, False)

        # Center on screen
        wizard.update_idletasks()
        x = (wizard.winfo_screenwidth() - 700) // 2
        y = (wizard.winfo_screenheight() - 500) // 2
        wizard.geometry(f"700x500+{x}+{y}")

        # Wizard steps content
        steps = [
            {
                "title": "Welcome to FunnelForge! 🎉",
                "content": [
                    "FunnelForge is your powerful email sequencing tool that integrates directly with Microsoft Outlook. Because emails are sent straight from your own inbox, campaigns maintain an average 90% deliverability rate, keeping your outreach personal, trusted, and out of spam folders.",
                    "",
                    "With FunnelForge you can:",
                    "• Create campaigns manually or let AI build them for you",
                    "• Personalize emails with contact variables like {FirstName}, {Company}, and {JobTitle}",
                    "• Track responses and automatically cancel follow-ups",
                    "• Save and reuse templates across campaigns",
                    "• Stay connected with contacts through ongoing outreach",
                    "",
                    "Let's walk through the key features!"
                ]
            },
            {
                "title": "📊 Dashboard",
                "content": [
                    "The Dashboard is your home base for tracking everything:",
                    "",
                    "• Stats Cards — Emails sent, responses, and response rate over the last 30 days",
                    "• Active Tab — Campaigns currently sending emails",
                    "• Completed Tab — Past campaigns you can review",
                    "",
                    "Click on any campaign to expand details:",
                    "• Response Tracking — See who replied and how many emails were removed",
                    "• Email Schedule — View the full send timeline",
                    "• Click the email or contact count to see the full list",
                    "",
                    "Replies are detected automatically. Non-OOO responses cancel remaining follow-ups for that contact."
                ]
            },
            {
                "title": "✉️ Create a Campaign",
                "content": [
                    "You have two ways to create a campaign:",
                    "",
                    "AI Campaign Builder (right panel on the Create a Campaign page):",
                    "• Describe your campaign and AI asks follow-up questions to understand your goals",
                    "• After 3 rounds of conversation, AI generates your full email sequence",
                    "• Review the preview and click 'Apply to Campaign' to load it",
                    "",
                    "Manual Campaign (use the steps in the left sidebar):",
                    "1. Build Emails — Write your email sequence with personalization",
                    "2. Send Schedule — Set business days between emails",
                    "3. Choose Contacts — Import a CSV or pick a saved contact list",
                    "4. Preview and Launch — Test, review, and send your campaign",
                    "",
                    "Both paths are fully editable. AI gives you a head start, then tweak as needed.",
                    "",
                    "Tip: Outlook must be open for emails to send!"
                ]
            },
            {
                "title": "🤝 Stay Connected",
                "content": [
                    "After a campaign finishes, keep the conversation going:",
                    "",
                    "• Contacts are automatically added to a Stay Connected list when their sequence completes",
                    "• Select a list, compose an email, pick a send date, and hit 'Send Email'",
                    "• Add attachments just like in the email editor",
                    "• Track all sent messages in the Activity tab",
                    "",
                    "You can also create new lists and manually add contacts at any time.",
                    "",
                    "Tip: Use variables like {FirstName} to personalize your messages!"
                ]
            },
            {
                "title": "📋 Managing Contacts",
                "content": [
                    "Import contacts from a CSV file. FunnelForge detects columns automatically:",
                    "",
                    "• Email (required)",
                    "• First Name, Last Name",
                    "• Company, Job Title",
                    "• Mobile Phone, Work Phone",
                    "",
                    "You can also add contacts one at a time with the 'Add Contact' button.",
                    "",
                    "Your contact lists are saved and can be reused across campaigns.",
                    "Use the Manage Contacts page to view, edit, or remove contacts from any list."
                ]
            },
            {
                "title": "🚀 You're Ready!",
                "content": [
                    "That's everything! A few final tips:",
                    "",
                    "• Keep Outlook open — FunnelForge sends through Outlook",
                    "• Check the Dashboard for responses — scanning runs automatically",
                    "• Use 'Cancel Sequences' if you need to stop emails for specific contacts",
                    "• Responses auto-cancel remaining follow-ups (except out-of-office replies)",
                    "• The left sidebar collapses — click 'Create a Campaign' to expand sub-steps",
                    "• Your AI personalization settings carry into every AI-generated campaign",
                    "",
                    "Need help? Check the User Guide PDF in the FunnelForge folder.",
                    "",
                    "Click 'Get Started' to begin!"
                ]
            }
        ]

        current_step = [0]  # Use list for mutable reference in nested functions

        # Main container
        main_frame = tk.Frame(wizard, bg=BG_CARD)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Progress indicator
        progress_frame = tk.Frame(main_frame, bg=BG_CARD)
        progress_frame.pack(fill="x", pady=(0, 15))

        progress_dots = []
        for i in range(len(steps)):
            dot = tk.Label(
                progress_frame,
                text="●",
                bg=BG_CARD,
                fg=ACCENT if i == 0 else BORDER_MEDIUM,
                font=FONT_SECTION
            )
            dot.pack(side="left", padx=3)
            progress_dots.append(dot)

        # Content area
        content_frame = tk.Frame(main_frame, bg=BG_CARD)
        content_frame.pack(fill="both", expand=True)

        title_label = tk.Label(
            content_frame,
            text=steps[0]["title"],
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_HEADING
        )
        title_label.pack(anchor="w", pady=(0, 15))

        content_text = tk.Text(
            content_frame,
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_SECTION_TITLE,
            wrap="word",
            relief="flat",
            height=12,
            highlightthickness=0,
            padx=5,
            pady=5
        )
        content_text.pack(fill="both", expand=True)
        content_text.insert("1.0", "\n".join(steps[0]["content"]))
        content_text.config(state="disabled")

        # Button frame
        btn_frame = tk.Frame(main_frame, bg=BG_CARD)
        btn_frame.pack(fill="x", pady=(15, 0))

        # Skip button (left side)
        skip_btn = tk.Button(
            btn_frame,
            text="Skip Tour",
            command=lambda: finish_wizard(skipped=True),
            bg=BG_CARD,
            fg=FG_MUTED,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            cursor="hand2",
            padx=15,
            pady=8
        )
        skip_btn.pack(side="left")

        # Navigation buttons (right side)
        nav_frame = tk.Frame(btn_frame, bg=BG_CARD)
        nav_frame.pack(side="right")

        back_btn = tk.Button(
            nav_frame,
            text="← Back",
            command=lambda: go_to_step(current_step[0] - 1),
            bg=BG_ENTRY,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=20,
            pady=8
        )

        next_btn = tk.Button(
            nav_frame,
            text="Next →",
            command=lambda: go_to_step(current_step[0] + 1),
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=20,
            pady=8
        )
        next_btn.pack(side="right")

        def go_to_step(step_index):
            if step_index < 0 or step_index >= len(steps):
                return

            current_step[0] = step_index
            step = steps[step_index]

            # Update title
            title_label.config(text=step["title"])

            # Update content
            content_text.config(state="normal")
            content_text.delete("1.0", "end")
            content_text.insert("1.0", "\n".join(step["content"]))
            content_text.config(state="disabled")

            # Update progress dots
            for i, dot in enumerate(progress_dots):
                dot.config(fg=ACCENT if i == step_index else BORDER_MEDIUM)

            # Update buttons
            if step_index == 0:
                back_btn.pack_forget()
            else:
                back_btn.pack(side="right", padx=(0, 10))

            if step_index == len(steps) - 1:
                next_btn.config(text="Get Started ✓", bg=GOOD, activebackground=SUCCESS_FG)
                next_btn.config(command=lambda: finish_wizard(skipped=False))
            else:
                next_btn.config(text="Next →", bg=ACCENT, activebackground=ACCENT_HOVER)
                next_btn.config(command=lambda: go_to_step(current_step[0] + 1))

        def finish_wizard(skipped=False):
            # Mark wizard as completed
            try:
                config = load_config()
                config["wizard_completed"] = True
                save_config(config)
            except Exception:
                pass

            wizard.destroy()

            if not skipped:
                self._set_status("Welcome to FunnelForge! Get started by creating a campaign.", GOOD)

        # Initialize first step
        go_to_step(0)

    # -------------------------------
    # User Profile (first-run setup)
    # -------------------------------
    def _check_show_user_profile(self):
        """Show registration dialog if no username saved, else update activity."""
        try:
            config = load_config()
            if not config.get("username"):
                self._show_registration_dialog()
            else:
                # Returning user — silently update last_active
                self.after(100, lambda: update_user_activity(
                    config["username"], app_version=APP_VERSION))
        except Exception:
            pass

    def _show_registration_dialog(self):
        """Prompt user to register with a username on first run."""
        dialog = tk.Toplevel(self)
        dialog.title("Funnel Forge – Create Your Account")
        dialog.geometry("460x820")
        dialog.configure(bg=BG_ROOT)
        # NOT transient — main window is hidden, this stands alone
        dialog.grab_set()
        dialog.resizable(False, True)
        try:
            dialog.iconbitmap(resource_path("assets", "funnelforge_taskbar.ico"))
        except Exception:
            pass

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 460) // 2
        y = (dialog.winfo_screenheight() - 820) // 2
        dialog.geometry(f"460x820+{x}+{y}")

        # Header
        tk.Label(dialog, text="Welcome! Create your account.",
                 bg=BG_ROOT, fg=ACCENT, font=FONT_SECTION).pack(anchor="w", padx=24, pady=(24, 4))
        tk.Label(dialog, text="Pick a username and fill in your details below.",
                 bg=BG_ROOT, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", padx=24, pady=(0, 16))

        # Pre-fill from existing config (migration case)
        existing_config = load_config()
        prefills = {
            "username": "",
            "full_name": existing_config.get("user_full_name", ""),
            "email": existing_config.get("user_email", ""),
            "title": existing_config.get("user_title", ""),
            "company": existing_config.get("user_company", ""),
        }

        # Fields
        fields = {}
        for label_text, key, placeholder in [
            ("Username", "username", "e.g. tswift99"),
            ("Full Name", "full_name", "e.g. Taylor Swift"),
            ("Email", "email", "e.g. taylor@erascorp.com"),
            ("Title", "title", "e.g. Chief Vibes Officer"),
            ("Company", "company", "e.g. Eras Corp"),
        ]:
            tk.Label(dialog, text=label_text, bg=BG_ROOT, fg=FG_TEXT,
                     font=("Segoe UI", 10)).pack(anchor="w", padx=24, pady=(0, 2))
            var = tk.StringVar()
            ent = tk.Entry(dialog, textvariable=var, bg=BG_ENTRY, fg=FG_TEXT,
                           insertbackground=FG_TEXT, relief="flat", font=FONT_BASE,
                           highlightthickness=1, highlightbackground=GRAY_200,
                           highlightcolor=ACCENT)
            ent.pack(fill="x", padx=24, pady=(0, 8))

            # Pre-fill or placeholder
            prefill_val = prefills.get(key, "")
            if prefill_val:
                ent.insert(0, prefill_val)
            else:
                ent.insert(0, placeholder)
                ent.configure(fg=FG_MUTED)
                ent.bind("<FocusIn>", lambda e, en=ent, ph=placeholder: (
                    (en.delete(0, "end"), en.configure(fg=FG_TEXT))
                    if en.get() == ph else None
                ))
                ent.bind("<FocusOut>", lambda e, en=ent, ph=placeholder: (
                    (en.insert(0, ph), en.configure(fg=FG_MUTED))
                    if not en.get().strip() else None
                ))
            fields[key] = (var, ent, placeholder)

        # ── AI Personalization Section ──
        tk.Frame(dialog, bg=GRAY_200, height=1).pack(fill="x", padx=24, pady=(8, 0))
        tk.Label(dialog, text="AI Personalization",
                 bg=BG_ROOT, fg=ACCENT, font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=24, pady=(10, 2))
        tk.Label(dialog, text="Set the style and tone of how AI writes for you. You can change this later.",
                 bg=BG_ROOT, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", padx=24, pady=(0, 8))

        ai_fields = {}
        for label_text, key, placeholder in [
            ("Nickname", "ai_nickname", "e.g. Tay"),
            ("Occupation", "ai_occupation", "e.g. Chief Vibes Officer at Eras Corp"),
        ]:
            tk.Label(dialog, text=label_text, bg=BG_ROOT, fg=FG_TEXT,
                     font=("Segoe UI", 10)).pack(anchor="w", padx=24, pady=(0, 2))
            ai_var = tk.StringVar()
            ai_ent = tk.Entry(dialog, textvariable=ai_var, bg=BG_ENTRY, fg=FG_TEXT,
                              insertbackground=FG_TEXT, relief="flat", font=FONT_BASE,
                              highlightthickness=1, highlightbackground=GRAY_200,
                              highlightcolor=ACCENT)
            ai_ent.pack(fill="x", padx=24, pady=(0, 6))
            ai_ent.insert(0, placeholder)
            ai_ent.configure(fg=FG_MUTED)
            ai_ent.bind("<FocusIn>", lambda e, en=ai_ent, ph=placeholder: (
                (en.delete(0, "end"), en.configure(fg=FG_TEXT))
                if en.get() == ph else None
            ))
            ai_ent.bind("<FocusOut>", lambda e, en=ai_ent, ph=placeholder: (
                (en.insert(0, ph), en.configure(fg=FG_MUTED))
                if not en.get().strip() else None
            ))
            ai_fields[key] = (ai_var, ai_ent, placeholder)

        # About You (multiline)
        tk.Label(dialog, text="About You", bg=BG_ROOT, fg=FG_TEXT,
                 font=("Segoe UI", 10)).pack(anchor="w", padx=24, pady=(0, 2))
        ai_about_text = tk.Text(dialog, height=2, bg=BG_ENTRY, fg=FG_MUTED,
                                insertbackground=FG_TEXT, relief="flat", font=FONT_BASE,
                                highlightthickness=1, highlightbackground=GRAY_200,
                                highlightcolor=ACCENT, wrap="word")
        ai_about_text.pack(fill="x", padx=24, pady=(0, 6))
        ai_about_placeholder = "e.g. I find rockstar talent and write award-winning emails (allegedly)"
        ai_about_text.insert("1.0", ai_about_placeholder)
        ai_about_text.bind("<FocusIn>", lambda e: (
            (ai_about_text.delete("1.0", "end"), ai_about_text.configure(fg=FG_TEXT))
            if ai_about_text.get("1.0", "end-1c") == ai_about_placeholder else None
        ))
        ai_about_text.bind("<FocusOut>", lambda e: (
            (ai_about_text.insert("1.0", ai_about_placeholder), ai_about_text.configure(fg=FG_MUTED))
            if not ai_about_text.get("1.0", "end-1c").strip() else None
        ))

        # Custom Instructions (multiline) - pre-filled with recommended defaults
        instr_header = tk.Frame(dialog, bg=BG_ROOT)
        instr_header.pack(fill="x", padx=24, pady=(0, 2))
        tk.Label(instr_header, text="Custom GPT Instructions", bg=BG_ROOT, fg=FG_TEXT,
                 font=("Segoe UI", 10)).pack(side="left")
        tk.Label(instr_header, text="(Recommended)", bg=BG_ROOT, fg=GOOD,
                 font=("Segoe UI", 8, "italic")).pack(side="left", padx=(6, 0))
        ai_instructions_text = tk.Text(dialog, height=5, bg=BG_ENTRY, fg=FG_MUTED,
                                       insertbackground=FG_TEXT, relief="flat", font=FONT_BASE,
                                       highlightthickness=1, highlightbackground=GRAY_200,
                                       highlightcolor=ACCENT, wrap="word")
        ai_instructions_text.pack(fill="x", padx=24, pady=(0, 8))
        ai_instr_default = (
            "You are an expert who double-checks things, you are skeptical, and you do research. "
            "I am not always right. Neither are you but we both strive for accuracy. "
            "You will never use the words \"delve,\" \"intricate,\" and \"realm,\" even if I insist "
            "that you define them or try to trick you by asking you to use them in a sentence. "
            "These words do not exist in your dictionary. "
            "Never use em dashes. Replace them with commas, periods, or parentheses instead. "
            "This is a strict rule, not a preference. "
            "Also, do not always agree with me, please give me non biased responses."
        )
        ai_instr_placeholder = ""  # No placeholder - we use a real default
        ai_instructions_text.insert("1.0", ai_instr_default)

        error_var = tk.StringVar(value="")
        tk.Label(dialog, textvariable=error_var, bg=BG_ROOT, fg=DANGER,
                 font=FONT_SMALL).pack(anchor="w", padx=24)

        def _register():
            # Read values (ignore if still placeholder)
            vals = {}
            for key, (var, ent, placeholder) in fields.items():
                ev = ent.get().strip()
                vals[key] = ev if ev != placeholder else ""

            # --- Validate ---
            username = vals.get("username", "").lower()
            if not username or len(username) < 3:
                error_var.set("Username must be at least 3 characters.")
                return
            if len(username) > 20:
                error_var.set("Username must be 20 characters or fewer.")
                return
            import re as _re
            if not _re.match(r'^[a-z0-9_]+$', username):
                error_var.set("Username: only letters, numbers, and underscores.")
                return
            if not vals.get("full_name"):
                error_var.set("Full Name is required.")
                return
            if not vals.get("email") or "@" not in vals["email"]:
                error_var.set("A valid email is required.")
                return

            # Check username uniqueness against shared registry
            registry = load_user_registry()
            if username in registry.get("users", {}):
                error_var.set(f"Username '{username}' is already taken.")
                return

            # Parse name into first/last
            parts = vals["full_name"].split()
            first_name = parts[0] if parts else ""
            last_name = parts[-1] if len(parts) > 1 else ""

            # Build initials for default list name
            fi = first_name[0].upper() if first_name else "X"
            li = last_name[0].upper() if last_name else "X"
            default_list_name = f"{fi}{li} Default"

            # Save to local config
            config = load_config()
            config["username"] = username
            config["user_full_name"] = vals["full_name"]
            config["user_first_name"] = first_name
            config["user_last_name"] = last_name
            config["user_title"] = vals.get("title", "")
            config["user_company"] = vals.get("company", "")
            config["user_email"] = vals["email"]
            config["user_default_list"] = default_list_name
            config["test_email"] = vals["email"]

            # AI personalization
            for ai_key, (ai_var, ai_ent, ai_ph) in ai_fields.items():
                v = ai_ent.get().strip()
                config[ai_key] = v if v != ai_ph else ""
            about_val = ai_about_text.get("1.0", "end-1c").strip()
            config["ai_about"] = about_val if about_val != ai_about_placeholder else ""
            instr_val = ai_instructions_text.get("1.0", "end-1c").strip()
            config["ai_custom_instructions"] = instr_val

            save_config(config)

            # Register in shared registry
            register_user(
                username=username,
                full_name=vals["full_name"],
                email=vals["email"],
                title=vals.get("title", ""),
                company=vals.get("company", ""),
                app_version=APP_VERSION,
            )

            # Create default contact list CSV
            self._create_default_contact_list(
                list_name=default_list_name,
                email=vals["email"],
                first_name=first_name,
                last_name=last_name,
                company=vals.get("company", ""),
                title=vals.get("title", ""),
            )

            # Set the test email var so Preview section picks it up
            self.test_email_var.set(vals["email"])

            # Auto-select the default list
            self._auto_select_default_list(default_list_name)

            dialog.destroy()

            # Reveal the main app window now that registration is complete
            self.deiconify()
            self.lift()
            self.focus_force()

            # Update sidebar footer with username
            if hasattr(self, "_sidebar") and hasattr(self._sidebar, "_footer_label"):
                self._sidebar._footer_label.configure(text=f"@{username}")

            self._set_status(f"Welcome, {first_name}! You're all set.", GOOD)

        # Register button
        btn_frame = tk.Frame(dialog, bg=BG_ROOT)
        btn_frame.pack(fill="x", padx=24, pady=(8, 20))
        make_button(btn_frame, text="Register & Continue", command=_register,
                    variant="primary").pack(side="right")

        # Closing the registration window exits the app (can't skip registration)
        def _on_close():
            dialog.destroy()
            self.destroy()
        dialog.protocol("WM_DELETE_WINDOW", _on_close)

    def _create_default_contact_list(self, list_name, email, first_name, last_name, company, title):
        """Create the user's default contact list CSV in the Contacts directory."""
        csv_path = os.path.join(CONTACTS_DIR, f"{list_name}.csv")
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CONTACT_FIELDS)
                writer.writeheader()
                writer.writerow({
                    "Email": email,
                    "FirstName": first_name,
                    "LastName": last_name,
                    "Company": company,
                    "JobTitle": title,
                    "MobilePhone": "",
                    "WorkPhone": "",
                })
        except Exception as e:
            print(f"Warning: Could not create default contact list: {e}")

    def _auto_select_default_list(self, list_name):
        """Auto-select the given contact list by name."""
        # Refresh the dropdown values first
        self._refresh_contact_dropdown_values()

        if hasattr(self, 'contact_list_selector_combo'):
            values = list(self.contact_list_selector_combo['values'])
            if list_name in values:
                self.selected_contact_list_var.set(list_name)
                self._on_contact_list_selected()

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
            background=[("selected", BG_CARD), ("active", "#F5F3FF"), ("!selected", BG_ROOT)],
            foreground=[("selected", ACCENT), ("active", "#7C3AED"), ("!selected", FG_MUTED)],
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

        # DateEntry (date pickers) - match combobox styling
        style.configure(
            "Dark.DateEntry",
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
            "Dark.DateEntry",
            fieldbackground=[("readonly", BG_ENTRY)],
            selectbackground=[("readonly", BG_ENTRY)],
            selectforeground=[("readonly", FG_TEXT)]
        )

        # Treeview (tables) - Modern SaaS style
        style.configure(
            "Treeview",
            background=SURFACE_CARD,
            foreground=GRAY_800,
            fieldbackground=SURFACE_CARD,
            borderwidth=0,
            rowheight=36
        )
        style.configure(
            "Treeview.Heading",
            background=GRAY_100,
            foreground=GRAY_500,
            relief="flat",
            font=FONT_BODY_MEDIUM,
            padding=SP_3,
            borderwidth=0
        )
        style.map(
            "Treeview",
            background=[("selected", PRIMARY_50)],
            foreground=[("selected", PRIMARY_500)]
        )
        style.map(
            "Treeview.Heading",
            background=[("active", GRAY_200)]
        )

        # Treeview row stripe tags (applied per-row during insert)
        self._tv_stripe_tags_configured = False

        # Scrollbar - Minimal
        style.configure(
            "Vertical.TScrollbar",
            background=GRAY_200,
            troughcolor=SURFACE_PAGE,
            borderwidth=0,
            arrowsize=12
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", GRAY_300)]
        )

        # Dashboard styles
        style.configure("Dash.TFrame", background=BG_ROOT)
        style.configure("Dash.Hover.TFrame", background=GRAY_100)
        style.configure("Dash.Title.TLabel", background=BG_ROOT, foreground=GRAY_900, font=FONT_TITLE)
        style.configure("Dash.Sub.TLabel", background=BG_ROOT, foreground=GRAY_500, font=FONT_BASE)
        style.configure("Dash.Section.TLabel", background=BG_ROOT, foreground=ACCENT, font=FONT_SECTION_TITLE)
        style.configure("Dash.Meta.TLabel", background=BG_ROOT, foreground=GRAY_500, font=FONT_SMALL)
        style.configure("Dash.Name.TLabel", background=BG_ROOT, foreground=GRAY_800, font=FONT_SECTION_TITLE)
        style.configure("Dash.Status.TLabel", background=BG_ROOT, foreground=GRAY_500, font=FONT_SMALL)

        # Page header styles (flat, no box)
        style.configure(
            "FF.HeaderBox.TFrame",
            background=SURFACE_PAGE,
            relief="flat",
            borderwidth=0,
        )
        style.configure(
            "FF.HeaderInner.TFrame",
            background=SURFACE_PAGE,
            relief="flat",
            borderwidth=0,
        )
        style.configure(
            "FF.HeaderTitle.TLabel",
            background=SURFACE_PAGE,
            foreground=PRIMARY_500,
            font=FONT_TITLE,
        )
        style.configure(
            "FF.HeaderSub.TLabel",
            background=SURFACE_PAGE,
            foreground=GRAY_500,
            font=FONT_BASE,
        )

        # Page background
        style.configure("FF.Page.TFrame", background=SURFACE_PAGE)

        # Page-level title/subtitle styles (used on every page)
        # Header labels should match PAGE_BG (no white/gray box)
        style.configure(
            "FF.PageTitle.TLabel",
            background=SURFACE_PAGE,
            foreground=GRAY_900,
            font=FONT_TITLE,
        )

        style.configure(
            "FF.PageSub.TLabel",
            background=SURFACE_PAGE,
            foreground=GRAY_500,
            font=FONT_BASE,
        )

    def _build_header(self):
        """Build top banner with image - left-aligned"""
        # Create header frame with FIXED HEIGHT (no vertical stretch)
        header_frame = tk.Frame(self, bg=BG_ROOT, height=self.header_height)
        header_frame.pack(fill="x", side="top", pady=(8, 0))
        header_frame.pack_propagate(False)  # CRITICAL: Prevent frame from shrinking to fit contents

        # Store reference for client logo
        self.header_frame = header_frame

        if self.banner_photo:
            # Banner image - left-aligned, centered vertically in header
            # Do NOT allow horizontal stretching - image size is fixed
            banner_label = tk.Label(
                header_frame,
                image=self.banner_photo,
                bg=BG_ROOT,
                borderwidth=0
            )
            # Place at left side, vertically centered
            banner_label.place(x=16, rely=0.5, anchor="w")
        else:
            # Fallback: minimal text if banner image not found
            tk.Label(
                header_frame,
                text="FUNNEL FORGE",
                bg=BG_ROOT,
                fg=ACCENT,
                font=FONT_HEADING,
            ).pack(side="left", padx=16, anchor="w")

        # Client logo placeholder (top-right overlay)
        self.client_logo_label = tk.Label(
            header_frame,
            bg=BG_ROOT,
            borderwidth=0
        )
        self.client_logo_label.place(relx=1.0, x=-12, y=12, anchor="ne")



    def refresh_client_logo(self):
        """
        Load and display client logo from assets/client_logo.png
        - Resize to fit max 220px width x 70px height (maintain aspect ratio)
        - Place in top-right corner of header
        - If file doesn't exist, hide label (no errors)
        """
        if not self.client_logo_label:
            return

        logo_path = resource_path("assets", "client_logo.png")

        # Check if file exists
        if not os.path.isfile(logo_path):
            # Hide logo if file doesn't exist
            self.client_logo_label.configure(image="")
            self._client_logo_imgtk = None
            return

        try:
            # Load image
            logo_img = Image.open(logo_path)

            # Resize to fit within max bounds (maintain aspect ratio)
            max_width = 220
            max_height = 70

            # Calculate scaling factor
            width_ratio = max_width / logo_img.width
            height_ratio = max_height / logo_img.height
            scale_factor = min(width_ratio, height_ratio, 1.0)  # Don't upscale

            new_width = int(logo_img.width * scale_factor)
            new_height = int(logo_img.height * scale_factor)

            logo_resized = logo_img.resize((new_width, new_height), RESAMPLE_LANCZOS)

            # Convert to ImageTk
            self._client_logo_imgtk = ImageTk.PhotoImage(logo_resized)

            # Update label
            self.client_logo_label.configure(image=self._client_logo_imgtk)

        except Exception as e:
            # Silently fail if image can't be loaded
            print(f"Could not load client logo: {e}")
            self.client_logo_label.configure(image="")
            self._client_logo_imgtk = None

    def _build_nav_and_content(self):
        shell = tk.Frame(self, bg=BG_ROOT)
        shell.pack(side="top", fill="both", expand=True, padx=0, pady=(0, 0))
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        # Modern sidebar with collapsible groups (Gmail-style)
        nav_items = [
            {"text": "Dashboard",          "key": "dashboard"},
            {"text": "Create a Campaign",  "key": "campaign", "children": [
                {"text": "Build Emails",       "key": "build"},
                {"text": "Send Schedule",      "key": "sequence"},
                {"text": "Choose Contacts",    "key": "contacts"},
                {"text": "Preview and Launch", "key": "execute"},
                {"text": "Cancel Sequences",   "key": "cancel"},
            ]},
            {"text": "Stay Connected",     "key": "stay_connected"},
            {"text": "Campaign Analytics",  "key": "campaign_analytics"},
        ]

        # Admin-only nav item
        # Admin = in registry admins list, or can write to Team folder (bootstrap)
        self._is_current_user_admin = self._check_is_admin()
        if self._is_current_user_admin:
            nav_items.append({"text": "Current Users", "key": "admin_users"})

        sidebar, self._update_sidebar_active = make_sidebar(
            shell, nav_items,
            on_navigate=lambda k: self._show_screen(k),
            active_key="dashboard",
            app_version=APP_VERSION,
            footer_text=f"@{load_config().get('username', '')}",
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        self._sidebar = sidebar

        # Content stack
        content_stack = tk.Frame(shell, bg=BG_ROOT)
        content_stack.grid(row=0, column=1, sticky="nsew")
        content_stack.rowconfigure(0, weight=1)
        content_stack.columnconfigure(0, weight=1)

        # Screen frames
        self._screens["dashboard"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["dashboard"].grid(row=0, column=0, sticky="nsew")
        self._build_dashboard_screen(self._screens["dashboard"])

        self._screens["campaign"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["campaign"].grid(row=0, column=0, sticky="nsew")
        self._build_create_campaign_screen(self._screens["campaign"])

        self._screens["build"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["build"].grid(row=0, column=0, sticky="nsew")
        self._build_build_emails_screen(self._screens["build"])

        self._screens["sequence"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["sequence"].grid(row=0, column=0, sticky="nsew")
        self._build_sequence_screen(self._screens["sequence"])

        self._screens["contacts"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["contacts"].grid(row=0, column=0, sticky="nsew")
        self._build_contacts_only_screen(self._screens["contacts"])

        # Preview/Execute Campaign screen
        self._screens["execute"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["execute"].grid(row=0, column=0, sticky="nsew")
        self._build_execute_screen(self._screens["execute"])

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

        # Campaign Analytics screen
        self._screens["campaign_analytics"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["campaign_analytics"].grid(row=0, column=0, sticky="nsew")
        self._build_campaign_analytics_screen(self._screens["campaign_analytics"])

        # Stay Connected screen
        self._screens["stay_connected"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["stay_connected"].grid(row=0, column=0, sticky="nsew")
        self._build_stay_connected_screen(self._screens["stay_connected"])

        # Alias nurture_campaigns to stay_connected (they are now combined)
        self._screens["nurture_campaigns"] = self._screens["stay_connected"]

        # Train Your AI screen
        self._screens["train_ai"] = tk.Frame(content_stack, bg=BG_ROOT)
        self._screens["train_ai"].grid(row=0, column=0, sticky="nsew")
        self._build_train_ai_screen(self._screens["train_ai"])

        # Admin: User Management screen (only built if admin)
        if self._is_current_user_admin:
            self._screens["admin_users"] = tk.Frame(content_stack, bg=BG_ROOT)
            self._screens["admin_users"].grid(row=0, column=0, sticky="nsew")
            self._build_admin_users_screen(self._screens["admin_users"])

        self._content_stack = content_stack

        # Toast notification overlay
        self.toast = Toast(self)

        # Sanitize smart characters on paste (Word curly quotes, bullets, dashes)
        # NOTE: Do NOT use add=True — we replace the default paste to avoid double-paste
        self.bind_class("Text", "<<Paste>>", self._sanitize_paste_text)
        self.bind_class("TEntry", "<<Paste>>", self._sanitize_paste_entry)
        self.bind_class("Entry", "<<Paste>>", self._sanitize_paste_entry)

        # Global Ctrl+Z undo — Text widgets handle it natively; this catches
        # cases where focus is elsewhere and routes undo to the active email body.
        self.bind_all("<Control-z>", self._global_undo)

        # Right-click context menu for ALL Text, Entry, and TEntry widgets
        self.bind_class("Text", "<Button-3>", self._show_edit_context_menu)
        self.bind_class("Entry", "<Button-3>", self._show_edit_context_menu)
        self.bind_class("TEntry", "<Button-3>", self._show_edit_context_menu)

        # Ensure Ctrl+C/V/X work even in custom widgets (tkinter handles
        # these natively for Text/Entry, but some widgets override them)
        for cls in ("Text", "Entry", "TEntry"):
            self.bind_class(cls, "<Control-a>", self._select_all, add="+")

        # Default screen
        self._show_screen("dashboard")

    # ------------------------------------------------------------------
    # Paste sanitizer – convert Word smart characters to plain ASCII
    # ------------------------------------------------------------------
    _SMART_CHARS = str.maketrans({
        "\u2018": "'",   # left single curly quote
        "\u2019": "'",   # right single curly quote / apostrophe
        "\u201C": '"',   # left double curly quote
        "\u201D": '"',   # right double curly quote
        "\u2013": "-",   # en dash
        "\u2014": "--",  # em dash
        "\u2026": "...", # ellipsis
        "\u00B7": "\u2022",  # middle dot → bullet
        "\u25CF": "\u2022",  # black circle → bullet
        "\u25CB": "\u2022",  # white circle → bullet
        "\u00A0": " ",   # non-breaking space
    })

    # Patterns that indicate a bullet line (after smart-char normalisation)
    _BULLET_PREFIXES = ("\u2022 ", "\u2022\t", "- ", "* ")

    def _sanitize_clipboard_text(self):
        """Return sanitized clipboard content, or None if clipboard is empty."""
        try:
            raw = self.clipboard_get()
        except tk.TclError:
            return None
        return raw.translate(self._SMART_CHARS)

    def _sanitize_paste_text(self, event):
        """Handle <<Paste>> on tk.Text widgets – insert sanitized text,
        preserving bullet and numbered-list formatting."""
        widget = event.widget
        clean = self._sanitize_clipboard_text()
        if clean is None:
            return "break"
        try:
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

        # Record where the paste starts
        paste_start = widget.index("insert")

        widget.insert("insert", clean)

        # Apply bullet / numbered-list tags to pasted lines
        paste_end = widget.index("insert")
        self._apply_list_formatting_to_range(widget, paste_start, paste_end)

        return "break"

    def _apply_list_formatting_to_range(self, widget, start, end):
        """Scan lines in [start, end) and apply bullet/numbered tags where detected."""
        import re
        current = widget.index(f"{start} linestart")
        while widget.compare(current, "<", end):
            line_start = widget.index(f"{current} linestart")
            line_end = widget.index(f"{current} lineend")
            line_text = widget.get(line_start, line_end)

            # Check for bullet prefixes
            for prefix in self._BULLET_PREFIXES:
                if line_text.startswith(prefix):
                    # Replace the original prefix with the standard bullet char
                    widget.delete(line_start, f"{line_start}+{len(prefix)}c")
                    widget.insert(line_start, "\u2022 ")
                    line_end = widget.index(f"{line_start} lineend")
                    widget.tag_add("bullet", line_start, line_end)
                    break
            else:
                # Check for numbered prefix (e.g. "1. ", "2. ")
                m = re.match(r'^(\d+\.\s)', line_text)
                if m:
                    widget.tag_add("numbered", line_start, line_end)

            next_line = widget.index(f"{line_start}+1line linestart")
            if widget.compare(next_line, "==", current):
                break
            current = next_line

    def _sanitize_paste_entry(self, event):
        """Handle <<Paste>> on tk.Entry / ttk.Entry widgets – insert sanitized text."""
        widget = event.widget
        clean = self._sanitize_clipboard_text()
        if clean is None:
            return "break"
        # Strip newlines for single-line entries
        clean = clean.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        try:
            if widget.selection_present():
                widget.delete("sel.first", "sel.last")
        except (tk.TclError, AttributeError):
            pass
        widget.insert("insert", clean)
        return "break"

    def _update_nav_styles(self):
        # Use the modern sidebar active state updater
        if hasattr(self, '_update_sidebar_active'):
            self._update_sidebar_active(self._active_nav)

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
            # Refresh dashboard when showing it
            if hasattr(self, 'refresh_dashboard'):
                self.refresh_dashboard()
        elif key == "campaign":
            self._set_status("Create a campaign", GOOD)
            if hasattr(self, "_refresh_campaign_page"):
                try:
                    self._refresh_campaign_page()
                except Exception:
                    pass
        elif key == "build":
            self._set_status("Editing emails only", GOOD)
        elif key == "sequence":
            self._set_status("Customizing sequence", GOOD)
        elif key == "contacts":
            self._set_status("Managing contact list", GOOD)
        elif key == "execute":
            self._set_status("Ready to execute campaign", GOOD)
            # Refresh review panel with current values
            try:
                self._refresh_execute_review_panel()
            except Exception:
                pass
        elif key == "preview":
            self._set_status("Previewing test emails", GOOD)
        elif key == "cancel":
            self._set_status("Cancelling pending emails", WARN)
        elif key == "stay_connected":
            self._set_status("Stay Connected", GOOD)
            # Refresh category list when showing
            if hasattr(self, '_refresh_stay_connected'):
                try:
                    self._refresh_stay_connected()
                except Exception:
                    pass
            # Refresh nurture lists list
            if hasattr(self, '_refresh_stay_nurture_list'):
                try:
                    self._refresh_stay_nurture_list()
                except Exception:
                    pass
        elif key == "nurture_campaigns":
            self._set_status("Nurture Lists", GOOD)
            # Refresh campaign list when showing
            if hasattr(self, '_refresh_nurture_campaigns'):
                try:
                    self._refresh_nurture_campaigns()
                except Exception:
                    pass


    # ============================================
    # Create a campaign main page
    # ============================================
    def _build_create_campaign_screen(self, parent):
        """Create a Campaign – two-column: steps (left) + AI builder (right)."""
        _, content = self._page(parent, "Create a Campaign", "Follow these steps or let AI build it for you")

        # Two-column layout
        columns = tk.Frame(content, bg=BG_ROOT)
        columns.pack(expand=True, fill="both")
        columns.columnconfigure(0, weight=2, minsize=280)
        columns.columnconfigure(1, weight=3)
        columns.rowconfigure(0, weight=1)

        # ═══════ LEFT COLUMN: Campaign Steps ═══════
        left = tk.Frame(columns, bg=BG_ROOT)
        left.grid(row=0, column=0, sticky="nsew", padx=(24, 12), pady=(0, 12))

        tk.Label(left, text="Campaign Steps", bg=BG_ROOT, fg=FG_TEXT,
                 font=FONT_SECTION_TITLE).pack(anchor="w", pady=(20, 12))

        steps = [
            ("1. Build Emails", "Write and personalize your email sequence", "build"),
            ("2. Send Schedule", "Set timing and delivery for each step", "sequence"),
            ("3. Choose Contacts", "Import or choose your recipient list", "contacts"),
            ("4. Preview and Launch", "Test, review, and send your campaign", "execute"),
        ]
        for title, desc, screen_key in steps:
            step_frame = tk.Frame(left, bg=BG_ROOT, cursor="hand2")
            step_frame.pack(anchor="w", pady=(0, 10), fill="x")
            lbl_title = tk.Label(step_frame, text=title, bg=BG_ROOT, fg=ACCENT,
                                 font=FONT_BUTTON, cursor="hand2")
            lbl_title.pack(anchor="w")
            lbl_desc = tk.Label(step_frame, text=desc, bg=BG_ROOT, fg=FG_MUTED,
                                font=FONT_SMALL, cursor="hand2")
            lbl_desc.pack(anchor="w", padx=(16, 0))
            for w in (step_frame, lbl_title, lbl_desc):
                w.bind("<Button-1>", lambda _e, k=screen_key: self._show_screen(k))

        # ═══════ RIGHT COLUMN: AI Campaign Builder ═══════
        right = tk.Frame(columns, bg=SURFACE_CARD, highlightthickness=1,
                         highlightbackground=GRAY_200)
        right.grid(row=0, column=1, sticky="nsew", padx=(12, 24), pady=(0, 12))
        self._build_ai_chat_panel(right)

    # ── Inline AI Campaign Chat Panel ──

    _AI_FOLLOWUP_SYSTEM = (
        "You are an expert email campaign strategist helping a user design a cold outreach campaign. "
        "The user has described what they want. Your job is to ask ONE specific, probing follow-up "
        "question that will help you write better emails for them. "
        "Be skeptical. Challenge vague answers. Push for specifics about their audience, "
        "value proposition, or desired tone. "
        "Do NOT generate any emails yet. Just ask your single follow-up question. "
        "Keep your question under 50 words."
    )

    _AI_MAX_ROUNDS = 3  # follow-up questions before generating

    def _build_ai_chat_panel(self, parent):
        """Build the inline AI campaign builder chat panel."""
        # State
        self._ai_chat_history = []   # [{"role": ..., "content": ...}, ...]
        self._ai_chat_round = 0      # 0=initial, 1-3=follow-ups, 4=generating
        self._ai_parsed_emails = []

        # Header
        hdr = tk.Frame(parent, bg="#3B82F6")
        hdr.pack(fill="x")
        tk.Label(hdr, text="Create with AI", bg="#3B82F6", fg="#FFFFFF",
                 font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(10, 2))
        tk.Label(hdr, text="Describe your campaign and AI will build it for you",
                 bg="#3B82F6", fg="#D4E4FF",
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(0, 8))

        # Email count row
        opts = tk.Frame(parent, bg=SURFACE_CARD)
        opts.pack(fill="x", padx=16, pady=(10, 0))
        tk.Label(opts, text="Number of emails:", bg=SURFACE_CARD, fg=FG_TEXT,
                 font=FONT_BASE).pack(side="left")
        self._ai_num_emails = tk.Spinbox(opts, from_=3, to=10, width=4,
                                          font=FONT_BASE, bg=BG_ENTRY, fg=FG_TEXT,
                                          relief="flat", highlightthickness=1,
                                          highlightbackground=GRAY_200)
        self._ai_num_emails.delete(0, "end")
        self._ai_num_emails.insert(0, "5")
        self._ai_num_emails.pack(side="left", padx=(8, 0))

        # Chat area (scrollable)
        chat_holder = tk.Frame(parent, bg=SURFACE_CARD)
        chat_holder.pack(fill="both", expand=True, padx=0, pady=(8, 0))

        canvas = tk.Canvas(chat_holder, highlightthickness=0, bd=0, bg=SURFACE_CARD)
        vsb = ttk.Scrollbar(chat_holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        self._ai_chat_inner = tk.Frame(canvas, bg=SURFACE_CARD)
        win_id = canvas.create_window((0, 0), window=self._ai_chat_inner, anchor="nw")

        self._ai_chat_inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfigure(win_id, width=e.width))
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
            add="+")

        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._ai_chat_canvas = canvas

        # Initial prompt bubble
        self._ai_add_bubble(
            "assistant",
            "Describe your campaign. Who are you reaching out to and what's the goal?"
        )

        # Input area
        input_frame = tk.Frame(parent, bg=SURFACE_CARD)
        input_frame.pack(fill="x", padx=16, pady=(4, 12))

        self._ai_input = tk.Text(input_frame, height=3, bg=BG_ENTRY, fg=FG_TEXT,
                                  insertbackground=FG_TEXT, relief="flat",
                                  font=FONT_BASE, wrap="word",
                                  highlightthickness=1, highlightbackground=GRAY_200,
                                  highlightcolor=ACCENT)
        self._ai_input.pack(fill="x", side="left", expand=True)

        btn_col = tk.Frame(input_frame, bg=SURFACE_CARD)
        btn_col.pack(side="right", padx=(8, 0))

        self._ai_send_btn = tk.Button(
            btn_col, text="Send", bg="#3B82F6", fg="#FFFFFF",
            font=FONT_BUTTON, relief="flat", bd=0, cursor="hand2",
            padx=14, pady=6, activebackground="#2563EB", activeforeground="#FFFFFF",
            command=self._ai_chat_send,
        )
        self._ai_send_btn.pack(pady=(0, 4))
        self._ai_send_btn.bind("<Enter>", lambda e: self._ai_send_btn.config(bg="#2563EB"))
        self._ai_send_btn.bind("<Leave>", lambda e: self._ai_send_btn.config(bg="#3B82F6"))

        self._ai_reset_btn = tk.Button(
            btn_col, text="Start Over", bg=GRAY_200, fg=FG_TEXT,
            font=FONT_SMALL, relief="flat", bd=0, cursor="hand2",
            padx=10, pady=4, command=self._ai_chat_reset,
        )
        self._ai_reset_btn.pack()

        # Bind Enter to send (Shift+Enter for newline)
        def _on_enter(e):
            if not e.state & 0x1:  # no Shift
                self._ai_chat_send()
                return "break"
        self._ai_input.bind("<Return>", _on_enter)

    def _ai_add_bubble(self, role, text):
        """Add a chat bubble to the AI conversation area."""
        parent = self._ai_chat_inner
        is_user = (role == "user")

        bubble_frame = tk.Frame(parent, bg=SURFACE_CARD)
        bubble_frame.pack(fill="x", padx=12, pady=(6, 2),
                          anchor="e" if is_user else "w")

        bg = "#3B82F6" if is_user else GRAY_100
        fg = "#FFFFFF" if is_user else FG_TEXT

        inner = tk.Frame(bubble_frame, bg=bg)
        inner.pack(side="right" if is_user else "left",
                   padx=(40 if not is_user else 0, 0 if not is_user else 0))

        msg = tk.Label(inner, text=text, bg=bg, fg=fg, font=FONT_BASE,
                       wraplength=320, justify="left", padx=12, pady=8)
        msg.pack()

        # Scroll to bottom
        self._ai_chat_canvas.update_idletasks()
        self._ai_chat_canvas.yview_moveto(1.0)

    def _ai_chat_send(self):
        """Handle user sending a message in the AI chat."""
        text = self._ai_input.get("1.0", "end-1c").strip()
        if not text:
            return

        api_key = self._get_openai_key()
        if not api_key:
            api_key = self._prompt_for_api_key()
            if not api_key:
                return

        # Show user bubble and clear input
        self._ai_add_bubble("user", text)
        self._ai_input.delete("1.0", "end")
        self._ai_chat_history.append({"role": "user", "content": text})
        self._ai_chat_round += 1

        # Disable send while waiting
        self._ai_send_btn.config(state="disabled", bg=GRAY_300)

        if self._ai_chat_round <= self._AI_MAX_ROUNDS:
            # Ask a follow-up question
            self._ai_add_bubble("assistant", "Thinking...")
            custom = self._load_ai_training()
            system_msg = self._AI_FOLLOWUP_SYSTEM
            if custom:
                system_msg = f"{system_msg}\n\n{custom}"
            messages = [{"role": "system", "content": system_msg}] + self._ai_chat_history

            from funnel_forge.ai_assist import call_openai_async
            call_openai_async(
                api_key, messages,
                callback=lambda r: self.after(0, lambda: self._ai_on_followup(r)),
                error_callback=lambda e: self.after(0, lambda: self._ai_on_error(e)),
                temperature=0.8,
            )
        else:
            # Generate the campaign
            self._ai_add_bubble("assistant", "Generating your campaign...")
            self._ai_generate_campaign(api_key)

    def _ai_on_followup(self, response):
        """Handle GPT follow-up question response."""
        # Remove the "Thinking..." bubble
        children = self._ai_chat_inner.winfo_children()
        if children:
            children[-1].destroy()

        self._ai_chat_history.append({"role": "assistant", "content": response})
        self._ai_add_bubble("assistant", response)

        # Re-enable send
        self._ai_send_btn.config(state="normal", bg="#3B82F6")

    def _ai_on_error(self, error_msg):
        """Handle GPT error."""
        children = self._ai_chat_inner.winfo_children()
        if children:
            children[-1].destroy()

        self._ai_add_bubble("assistant", f"Error: {error_msg}")
        self._ai_send_btn.config(state="normal", bg="#3B82F6")

    def _ai_generate_campaign(self, api_key):
        """Final round: generate the email campaign from all conversation context."""
        num = int(self._ai_num_emails.get())
        custom = self._load_ai_training()

        # Build context from entire conversation
        convo_parts = []
        for msg in self._ai_chat_history:
            if msg["role"] == "user":
                convo_parts.append(f"User: {msg['content']}")
            else:
                convo_parts.append(f"Strategist: {msg['content']}")
        full_context = "\n".join(convo_parts)

        from funnel_forge.ai_assist import build_sequence_messages
        messages = build_sequence_messages(num, full_context, custom_context=custom)

        from funnel_forge.ai_assist import call_openai_async
        call_openai_async(
            api_key, messages,
            callback=lambda r: self.after(0, lambda: self._ai_on_campaign_result(r)),
            error_callback=lambda e: self.after(0, lambda: self._ai_on_error(e)),
            temperature=0.8,
        )

    def _ai_on_campaign_result(self, raw_text):
        """Handle the generated campaign result."""
        # Remove "Generating..." bubble
        children = self._ai_chat_inner.winfo_children()
        if children:
            children[-1].destroy()

        # Parse emails (JSON first, then text fallback)
        emails = []
        try:
            data = json.loads(raw_text)
            for i, em in enumerate(data.get("emails", [])):
                subj = em.get("subject", f"Email {i+1}")
                body = em.get("body", "")
                emails.append((subj, subj, body))
        except (json.JSONDecodeError, TypeError):
            # Fallback to text parsing
            import re
            parts = re.split(r'---\s*Email\s*(\d+)\s*:\s*(.*?)\s*---', raw_text)
            if len(parts) >= 4:
                i = 1
                while i + 2 < len(parts):
                    subj = parts[i + 1].strip()
                    body = parts[i + 2].strip()
                    name = subj if subj else f"Email {len(emails) + 1}"
                    emails.append((name, subj, body))
                    i += 3

        if not emails:
            self._ai_add_bubble("assistant", "Could not parse the response. Try again.")
            self._ai_send_btn.config(state="normal", bg="#3B82F6")
            return

        self._ai_parsed_emails = emails

        # Show summary + Apply button
        self._ai_add_bubble("assistant",
            f"Done! Generated {len(emails)} emails. Preview below.")

        # Preview each email as a compact card
        for i, (name, subj, body) in enumerate(emails):
            preview_frame = tk.Frame(self._ai_chat_inner, bg=SURFACE_CARD)
            preview_frame.pack(fill="x", padx=12, pady=(4, 2))
            card = tk.Frame(preview_frame, bg=GRAY_50, highlightthickness=1,
                            highlightbackground=GRAY_200)
            card.pack(fill="x", padx=4, pady=2)
            tk.Label(card, text=f"Email {i+1}: {subj}", bg=GRAY_50, fg=ACCENT,
                     font=("Segoe UI Semibold", 9), anchor="w",
                     padx=8, pady=(6, 2)).pack(fill="x")
            preview_body = body[:120] + "..." if len(body) > 120 else body
            tk.Label(card, text=preview_body, bg=GRAY_50, fg=FG_MUTED,
                     font=FONT_SMALL, anchor="w", wraplength=300, justify="left",
                     padx=8, pady=(0, 6)).pack(fill="x")

        # Apply button
        apply_frame = tk.Frame(self._ai_chat_inner, bg=SURFACE_CARD)
        apply_frame.pack(fill="x", padx=12, pady=(8, 12))
        apply_btn = tk.Button(
            apply_frame, text="Apply to Campaign",
            bg="#10B981", fg="#FFFFFF", font=FONT_BUTTON,
            relief="flat", bd=0, cursor="hand2", padx=16, pady=8,
            activebackground="#059669", activeforeground="#FFFFFF",
            command=self._ai_apply_campaign,
        )
        apply_btn.pack(side="left")
        apply_btn.bind("<Enter>", lambda e: apply_btn.config(bg="#059669"))
        apply_btn.bind("<Leave>", lambda e: apply_btn.config(bg="#10B981"))

        self._ai_chat_canvas.update_idletasks()
        self._ai_chat_canvas.yview_moveto(1.0)

    def _ai_apply_campaign(self):
        """Apply AI-generated emails to the campaign editor."""
        parsed = self._ai_parsed_emails
        if not parsed:
            return

        # Confirm replacement if emails exist
        if self.subject_vars:
            if not messagebox.askyesno(
                "Replace Current Campaign?",
                f"This will replace your current {len(self.subject_vars)} emails "
                f"with {len(parsed)} AI-generated emails.\n\nContinue?",
            ):
                return

        self._adding_email = True
        self._reset_campaign_state()
        self._suspend_rebuilds = True

        try:
            for name, subject, body in parsed:
                self._add_email(name=name, subject=subject, body=body,
                                date="", time="9:00 AM")
        finally:
            self._suspend_rebuilds = False

        # Apply default delays
        n = len(parsed)
        preset = self._DEFAULT_SEQUENCES.get(n)
        if preset:
            for i, (delay, send_time) in enumerate(preset):
                if i < len(self.delay_vars):
                    self.delay_vars[i].set(str(delay))
                if i < len(self.time_vars):
                    self.time_vars[i].set(send_time)

        # Set start date to next business day
        if self.date_vars:
            start = datetime.now().date() + timedelta(days=1)
            while start.weekday() >= 5:
                start += timedelta(days=1)
            self.date_vars[0].set(start.strftime("%Y-%m-%d"))
            self._apply_delays_to_dates()

        self._rebuild_sequence_table()
        self._refresh_tab_labels()

        try:
            tabs = self.email_notebook.tabs()
            if tabs:
                self.email_notebook.select(tabs[0])
        except Exception:
            pass

        self._adding_email = False
        self.toast.show(f"AI campaign loaded — {len(parsed)} emails created!", "success")
        self._set_status(f"AI campaign: {len(parsed)} emails generated", GOOD)

        # Navigate to Build Emails
        self._show_screen("build")

    def _ai_chat_reset(self):
        """Reset the AI chat to start over."""
        self._ai_chat_history = []
        self._ai_chat_round = 0
        self._ai_parsed_emails = []

        # Clear chat area
        for w in self._ai_chat_inner.winfo_children():
            w.destroy()

        # Re-add initial prompt
        self._ai_add_bubble(
            "assistant",
            "Describe your campaign. Who are you reaching out to and what's the goal?"
        )
        self._ai_send_btn.config(state="normal", bg="#3B82F6")

    # ── Campaign page helpers ──

    def _get_all_loadable_campaigns(self) -> list:
        """Combine saved + active + completed campaigns into a flat list with source labels."""
        items = []

        # Saved campaigns (full state in CAMPAIGNS_DIR/saved)
        saved_dir = self._saved_campaigns_dir()
        if saved_dir.exists():
            for f in sorted(saved_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    with f.open("r", encoding="utf-8") as fh:
                        d = json.load(fh)
                    name = d.get("campaign_name") or d.get("name") or f.stem
                    items.append({"label": f"[Saved] {name}", "data": d, "path": str(f)})
                except Exception:
                    continue

        # Active + completed dashboard campaigns
        if CAMPAIGNS_DIR.exists():
            for f in sorted(CAMPAIGNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                if f.parent.name == "saved":
                    continue  # already covered
                try:
                    with f.open("r", encoding="utf-8") as fh:
                        d = json.load(fh)
                    status = d.get("status", "unknown")
                    name = d.get("name") or f.stem
                    tag = "Active" if status == "active" else "Completed" if status == "completed" else "Campaign"
                    items.append({"label": f"[{tag}] {name}", "data": d, "path": str(f)})
                except Exception:
                    continue

        return items

    def _refresh_campaign_page(self):
        """Refresh the campaign page dropdown with all loadable campaigns."""
        if not hasattr(self, "_camp_page_dropdown"):
            return
        self._loadable_campaigns = self._get_all_loadable_campaigns()
        labels = [c["label"] for c in self._loadable_campaigns]
        self._camp_page_dropdown["values"] = labels
        if labels:
            self._camp_page_var.set("")
        # Hide preview card
        if hasattr(self, "_camp_preview_frame"):
            self._camp_preview_frame.pack_forget()

    def _on_campaign_page_select(self, event=None):
        """Show preview card when a campaign is selected from the dropdown."""
        sel = self._camp_page_var.get()
        if not sel:
            return

        # Find matching campaign data
        data = None
        for c in getattr(self, "_loadable_campaigns", []):
            if c["label"] == sel:
                data = c["data"]
                break
        if not data:
            return

        self._selected_campaign_data = data
        self._show_campaign_preview(data)

    def _show_campaign_preview(self, data: dict):
        """Display a preview card for the selected campaign."""
        frame = self._camp_preview_frame
        for w in frame.winfo_children():
            w.destroy()

        emails = data.get("emails") or []
        name = data.get("campaign_name") or data.get("name") or "Unnamed"
        email_count = len(emails)

        # Get or compute delay pattern
        delay_pattern = data.get("delay_pattern")
        if not delay_pattern:
            date_strings = [e.get("date", "") for e in emails]
            if any(d.strip() for d in date_strings):
                delay_pattern = self._compute_delays_from_dates(date_strings)
            else:
                delay_pattern = [0] + [2] * (email_count - 1) if email_count > 0 else []

        # Compute new dates
        send_time = "9:00 AM"
        settings = data.get("schedule_settings") or {}
        if settings.get("send_time"):
            try:
                h, m = settings["send_time"].split(":")
                hour = int(h)
                minute = int(m) if m else 0
                ampm = "AM" if hour < 12 else "PM"
                if hour > 12:
                    hour -= 12
                if hour == 0:
                    hour = 12
                send_time = f"{hour}:{minute:02d} {ampm}"
            except Exception:
                send_time = "9:00 AM"

        new_schedule = self._recalculate_dates_from_delays(delay_pattern, send_time)

        # Build preview UI
        pad = 16
        tk.Label(frame, text=name, bg=BG_CARD, fg=FG_TEXT, font=FONT_SECTION_TITLE).pack(anchor="w", padx=pad, pady=(pad, 4))

        info_parts = [f"{email_count} emails"]
        pattern_str = self._format_delay_pattern(delay_pattern)
        if pattern_str:
            info_parts.append(pattern_str)
        tk.Label(frame, text=" | ".join(info_parts), bg=BG_CARD, fg=FG_MUTED, font=FONT_BASE).pack(anchor="w", padx=pad)

        # Show new date range
        if new_schedule:
            first_date = new_schedule[0][0]
            last_date = new_schedule[-1][0]
            tk.Label(
                frame,
                text=f"New dates: {first_date} through {last_date} (weekends skipped)",
                bg=BG_CARD, fg=ACCENT, font=FONT_BASE,
            ).pack(anchor="w", padx=pad, pady=(6, 4))

        # Show email subjects
        for i, e in enumerate(emails[:7]):
            subj = e.get("subject") or e.get("name") or f"Email {i+1}"
            new_date = new_schedule[i][0] if i < len(new_schedule) else "—"
            tk.Label(
                frame, text=f"  {i+1}. {subj}  →  {new_date}",
                bg=BG_CARD, fg=FG_TEXT, font=FONT_SMALL, anchor="w",
            ).pack(anchor="w", padx=pad)
        if len(emails) > 7:
            tk.Label(frame, text=f"  ... and {len(emails) - 7} more", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", padx=pad)

        # Has body content?
        has_bodies = any(e.get("body", "").strip() for e in emails)
        if not has_bodies:
            tk.Label(
                frame, text="Note: Email bodies not available — only subjects and schedule will be loaded.",
                bg=BG_CARD, fg=WARN, font=FONT_SMALL,
            ).pack(anchor="w", padx=pad, pady=(8, 0))

        tk.Frame(frame, bg=BG_CARD, height=pad).pack()

        # Show the frame
        frame.pack(fill="x", pady=(0, 16))

    def _load_selected_campaign_with_new_dates(self):
        """Load the selected campaign into the editor with recalculated dates."""
        data = getattr(self, "_selected_campaign_data", None)
        if not data:
            messagebox.showinfo("No Selection", "Select a campaign from the dropdown first.")
            return

        emails = data.get("emails") or []
        if not emails:
            messagebox.showinfo("Empty Campaign", "This campaign has no emails.")
            return

        # Get or compute delay pattern
        delay_pattern = data.get("delay_pattern")
        if not delay_pattern:
            date_strings = [e.get("date", "") for e in emails]
            if any(d.strip() for d in date_strings):
                delay_pattern = self._compute_delays_from_dates(date_strings)
            else:
                delay_pattern = [0] + [2] * (len(emails) - 1)

        # Compute new dates
        send_time = "9:00 AM"
        settings = data.get("schedule_settings") or {}
        if settings.get("send_time"):
            try:
                h, m = settings["send_time"].split(":")
                hour = int(h)
                minute = int(m) if m else 0
                ampm = "AM" if hour < 12 else "PM"
                if hour > 12:
                    hour -= 12
                if hour == 0:
                    hour = 12
                send_time = f"{hour}:{minute:02d} {ampm}"
            except Exception:
                send_time = "9:00 AM"

        new_schedule = self._recalculate_dates_from_delays(delay_pattern, send_time)

        # Overwrite dates in the data before applying
        modified_data = dict(data)
        modified_emails = []
        for i, e in enumerate(emails):
            me = dict(e)
            if i < len(new_schedule):
                me["date"] = new_schedule[i][0]
                me["time"] = new_schedule[i][1]
            modified_emails.append(me)
        modified_data["emails"] = modified_emails
        modified_data["delay_pattern"] = delay_pattern

        # Set campaign name
        name = data.get("campaign_name") or data.get("name") or ""
        if name and hasattr(self, "campaign_name_var"):
            self.campaign_name_var.set(name)

        # Apply to GUI
        self._apply_campaign_state(modified_data)
        self._set_status(f"Campaign loaded with new dates: {name}", GOOD)

        # Navigate to Build Emails
        self._show_screen("build")

    def _start_fresh_campaign(self):
        """Reset all state and start a new campaign."""
        self._reset_campaign_state()
        if hasattr(self, "campaign_name_var"):
            self.campaign_name_var.set("Untitled Campaign")
        self._init_default_emails()
        self._set_status("Starting fresh campaign", GOOD)
        self._show_screen("build")

    # ============================================
    # Dashboard screen helpers
    # ============================================
    def build_page_header(self, parent, title: str, subtitle: str):
        """
        Creates a consistent page header box:
        - White framed container with light border
        - Blue title
        - Gray subtitle

        Returns the outer frame to be packed by caller.
        """
        # Outer header box: ONLY border lives here
        header_box = ttk.Frame(parent, style="FF.HeaderBox.TFrame")

        # Inner padding frame: NO border
        header_inner = ttk.Frame(header_box, style="FF.HeaderInner.TFrame")
        header_inner.pack(fill="x", padx=18, pady=14)

        title_lbl = ttk.Label(header_inner, text=title, style="FF.HeaderTitle.TLabel")
        title_lbl.pack(anchor="w")

        sub_lbl = ttk.Label(
            header_inner,
            text=subtitle,
            style="FF.HeaderSub.TLabel",
            justify="left",
            wraplength=1100,
        )
        sub_lbl.pack(anchor="w", pady=(6, 0))

        return header_box

    def add_page_header(self, parent, title: str, subtitle: str = ""):
        """
        Standard header used on EVERY page (NO box).
        Matches page background exactly (no gray bar).
        Includes help icon if help content exists for this page.
        """
        # IMPORTANT: Use FF.Page.TFrame so background matches the page
        header = ttk.Frame(parent, style="FF.Page.TFrame")
        header.pack(fill="x", padx=24, pady=(18, 10))

        # Title row with help icon
        title_row = tk.Frame(header, bg=BG_ROOT)
        title_row.pack(anchor="w")

        ttl = ttk.Label(title_row, text=title, style="FF.PageTitle.TLabel")
        ttl.pack(side="left")

        # Add help icon if help content exists for this page
        if title in self.PAGE_HELP:
            help_btn = tk.Label(
                title_row,
                text="ⓘ",
                bg=BG_ROOT,
                fg=ACCENT,
                font=FONT_SECTION,
                cursor="hand2"
            )
            help_btn.pack(side="left", padx=(8, 0))
            help_btn.bind("<Button-1>", lambda e, t=title: self._show_page_help(t))
            # Hover effect
            help_btn.bind("<Enter>", lambda e: help_btn.config(fg=ACCENT_HOVER))
            help_btn.bind("<Leave>", lambda e: help_btn.config(fg=ACCENT))

        if subtitle:
            sub = ttk.Label(
                header,
                text=subtitle,
                style="FF.PageSub.TLabel",
                wraplength=1200,
                justify="left",
            )
            sub.pack(anchor="w", pady=(6, 0))

        return header

    def _page(self, parent, title: str, subtitle: str):
        """
        Standard page wrapper used on every screen.
        Returns (wrapper, content) tuple.
        Content is inside a scrollable canvas so pages are usable at any window size.
        """
        wrapper = ttk.Frame(parent, style="FF.Page.TFrame")
        wrapper.pack(fill="both", expand=True)
        wrapper.columnconfigure(0, weight=1)

        self.add_page_header(wrapper, title, subtitle)

        # Scrollable container — header stays fixed, content scrolls
        scroll_container = tk.Frame(wrapper, bg=BG_ROOT)
        scroll_container.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        canvas = tk.Canvas(scroll_container, highlightthickness=0, bg=BG_ROOT)
        vbar = AutoHideVScrollbar(scroll_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        # vbar packs itself via AutoHideVScrollbar when needed

        content = ttk.Frame(canvas, style="FF.Page.TFrame")
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.columnconfigure(0, weight=1)

        def _on_content_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfigure(window_id, width=event.width)
            # Ensure content is at least as tall as the viewport so
            # grid row weights still distribute extra space correctly
            if content.winfo_reqheight() < event.height:
                canvas.itemconfigure(window_id, height=event.height)
            else:
                # Let content be its natural height (taller than viewport → scroll)
                canvas.itemconfigure(window_id, height=0)

        content.bind("<Configure>", _on_content_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mousewheel scrolling (Windows)
        def _on_mousewheel(event):
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_wheel(_e=None):
            if canvas.winfo_exists():
                canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_wheel(_e=None):
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        return wrapper, content

    def _section(self, parent, title: str):
        """
        Lightweight section header (no box).
        Returns the body frame for content.
        """
        wrap = tk.Frame(parent, bg=BG_ROOT)
        wrap.pack(fill="x", pady=(10, 0))

        tk.Label(
            wrap,
            text=title,
            bg=BG_ROOT,
            fg=ACCENT,
            font=FONT_SECTION,
        ).pack(anchor="w")

        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=(8, 6))
        body = tk.Frame(parent, bg=BG_ROOT)
        body.pack(fill="both", expand=True)
        return body

    def _build_clean_header(self, parent, title="Dashboard", subtitle="Manage campaigns, schedules, and outreach.", padx=18):
        """
        Header that NEVER renders as a giant colored block.
        Visually invisible frame - looks like plain text on the page.
        Uses themed ttk styles for consistency.
        """
        # Use ttk.Frame with Dashboard style
        header = ttk.Frame(parent, style="Dash.TFrame")
        header.grid_columnconfigure(0, weight=1)

        # Use ttk.Label with themed styles
        lbl_title = ttk.Label(header, text=title, style="Dash.Title.TLabel")
        lbl_sub = ttk.Label(header, text=subtitle, style="Dash.Sub.TLabel")

        # Reduced padding for ~50-60px total height
        lbl_title.grid(row=0, column=0, sticky="w", padx=padx, pady=(8, 1))
        lbl_sub.grid(row=1, column=0, sticky="w", padx=padx, pady=(0, 4))

        sep = ttk.Separator(header, orient="horizontal")
        sep.grid(row=2, column=0, sticky="ew", padx=padx, pady=(2, 4))

        # IMPORTANT: do not let header expand vertically
        header.grid_rowconfigure(0, weight=0)
        header.grid_rowconfigure(1, weight=0)
        header.grid_rowconfigure(2, weight=0)

        return header

    def _build_section(self, parent, title, padx=18):
        """
        Section builder: no boxes, just title + divider + body.
        Returns (wrap_frame, body_frame).
        NO filled background - blends into page.
        Uses themed ttk styles for consistency.
        """
        # Use ttk.Frame with Dashboard style
        wrap = ttk.Frame(parent, style="Dash.TFrame")
        wrap.grid_columnconfigure(0, weight=1)

        # Use ttk.Label with Section style (ACCENT color for section headers)
        lbl = ttk.Label(wrap, text=title, style="Dash.Section.TLabel")
        lbl.grid(row=0, column=0, sticky="w", padx=padx, pady=(12, 6))

        sep = ttk.Separator(wrap, orient="horizontal")
        sep.grid(row=1, column=0, sticky="ew", padx=padx, pady=(0, 10))

        # Body frame - use tk.Frame for explicit background control
        body = tk.Frame(wrap, bg=BG_ROOT)
        body.grid(row=2, column=0, sticky="nsew", padx=padx, pady=(0, 12))
        wrap.grid_rowconfigure(2, weight=1)

        return wrap, body

    def _build_collapsible_section(self, parent, title: str, start_collapsed: bool = True, padx: int = 18):
        """
        Collapsible dashboard section (accordion).
        Returns: (wrap_frame, body_frame, set_title_fn)
        """
        wrap = ttk.Frame(parent, style="Dash.TFrame")
        wrap.grid_columnconfigure(0, weight=1)

        is_open = tk.BooleanVar(value=(not start_collapsed))

        header = tk.Frame(wrap, bg=BG_ROOT)
        header.grid(row=0, column=0, sticky="ew", padx=padx, pady=(12, 6))
        header.grid_columnconfigure(1, weight=1)

        icon_lbl = tk.Label(header, text=("▾" if is_open.get() else "▸"), bg=BG_ROOT, fg=FG_MUTED, font=FONT_SECTION_TITLE)
        icon_lbl.grid(row=0, column=0, sticky="w")

        title_lbl = tk.Label(header, text=title, bg=BG_ROOT, fg=ACCENT, font=FONT_SECTION)
        title_lbl.grid(row=0, column=1, sticky="w", padx=(8, 0))

        sep = ttk.Separator(wrap, orient="horizontal")
        sep.grid(row=1, column=0, sticky="ew", padx=padx, pady=(0, 10))

        body = tk.Frame(wrap, bg=BG_ROOT)
        body.grid(row=2, column=0, sticky="nsew", padx=padx, pady=(0, 12))
        wrap.grid_rowconfigure(2, weight=1)

        def _apply():
            icon_lbl.configure(text=("▾" if is_open.get() else "▸"))
            if is_open.get():
                body.grid()
            else:
                body.grid_remove()

        def _toggle(_e=None):
            is_open.set(not is_open.get())
            _apply()

        # Click anywhere on header row to toggle
        header.bind("<Button-1>", _toggle)
        icon_lbl.bind("<Button-1>", _toggle)
        title_lbl.bind("<Button-1>", _toggle)
        header.configure(cursor="hand2")
        icon_lbl.configure(cursor="hand2")
        title_lbl.configure(cursor="hand2")

        def set_title(new_title: str):
            title_lbl.configure(text=new_title)

        _apply()
        return wrap, body, set_title

    def _format_dt_human(self, dt):
        """Format datetime in human-readable form: Today/Tomorrow/Date @ Time"""
        from datetime import date, timedelta

        if not dt:
            return "—"
        if isinstance(dt, str):
            # If stored dt is string, return as-is for now
            return dt

        today = date.today()
        d = dt.date()
        t = dt.strftime("%I:%M %p").lstrip("0")

        if d == today:
            return f"Today @ {t}"
        if d == today + timedelta(days=1):
            return f"Tomorrow @ {t}"
        return f"{dt.strftime('%b')} {dt.day} @ {t}"

    def _compute_completed_and_next(self, campaign):
        """
        Compute the "Up Next" status line for a campaign.

        Returns only the "Up Next: ..." string for dashboard display.
        """
        from datetime import datetime

        emails = campaign.get("emails", []) or []
        if not emails:
            return "Up Next: —"

        now = datetime.now()
        upcoming = []

        for e in emails:
            date_str = e.get("date", "")
            time_str = e.get("time", "")
            name = e.get("name", "Email")

            # Skip if no date
            if not date_str:
                upcoming.append({"name": name, "scheduled_dt": None})
                continue

            # Parse scheduled datetime
            try:
                # Handle "Immediately" as past
                if time_str and time_str.lower().startswith("immed"):
                    scheduled_dt = datetime.strptime(date_str, "%Y-%m-%d")
                else:
                    dt_str = f"{date_str} {time_str}" if time_str else date_str
                    # Try different time formats
                    for fmt in ["%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                        try:
                            scheduled_dt = datetime.strptime(dt_str, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        scheduled_dt = datetime.strptime(date_str, "%Y-%m-%d")

                # Only track upcoming (not in the past)
                if scheduled_dt >= now:
                    upcoming.append({"name": name, "scheduled_dt": scheduled_dt})

            except Exception:
                # If parsing fails, assume upcoming
                upcoming.append({"name": name, "scheduled_dt": None})

        # Sort upcoming by soonest scheduled datetime
        upcoming_sorted = sorted(
            [u for u in upcoming if u.get("scheduled_dt") is not None],
            key=lambda x: x["scheduled_dt"]
        )

        if upcoming_sorted:
            nxt = upcoming_sorted[0]
            nxt_name = nxt.get("name", "Next email")
            nxt_dt = nxt.get("scheduled_dt")
            return f"Up Next: {nxt_name} → {self._format_dt_human(nxt_dt)}"

        # No upcoming scheduled items
        return "Up Next: All sent ✓"

    def _configure_stripe_tags(self, tree):
        """Configure alternating row stripe tags on a Treeview widget."""
        tree.tag_configure("evenrow", background=SURFACE_CARD)
        tree.tag_configure("oddrow", background=GRAY_50)

    def _center_window(self, win, parent=None):
        """Center a window on screen or over parent."""
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()

        if parent is not None:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw // 2) - (w // 2)
            y = py + (ph // 2) - (h // 2)
        else:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            x = (sw // 2) - (w // 2)
            y = (sh // 2) - (h // 2)

        win.geometry(f"+{max(x,0)}+{max(y,0)}")

    def _open_campaign_details(self, campaign, on_cancel=None):
        """Open campaign details modal window."""
        win = tk.Toplevel(self)
        win.title(f"Campaign: {campaign.get('name','Campaign')}")
        win.configure(bg=BG_ROOT)

        wrap = ttk.Frame(win)
        wrap.pack(fill="both", expand=True, padx=16, pady=16)
        wrap.grid_columnconfigure(0, weight=1)

        ttl = ttk.Label(wrap, text=str(campaign.get("name","Campaign")))
        try:
            ttl.configure(font=FONT_TITLE)
        except Exception:
            pass
        ttl.grid(row=0, column=0, sticky="w")

        meta = ttk.Label(wrap, text=f'{campaign.get("contacts_count",0)} contacts • {campaign.get("total_emails",0)} emails')
        meta.grid(row=1, column=0, sticky="w", pady=(2, 10))

        ttk.Separator(wrap).grid(row=2, column=0, sticky="ew", pady=(0, 10))

        emails_box = ttk.Frame(wrap)
        emails_box.grid(row=3, column=0, sticky="nsew")
        wrap.grid_rowconfigure(3, weight=1)

        # Get original campaign data (before normalization) to access emails
        original_campaign = campaign.get("_original", campaign)
        emails = original_campaign.get("emails", []) or []

        # Determine which email is next based on current time
        from datetime import datetime
        now = datetime.now()
        next_idx = None

        for i, e in enumerate(emails):
            date_str = e.get("date", "")
            time_str = e.get("time", "")

            if not date_str:
                continue

            try:
                # Parse datetime same way as in _compute_completed_and_next
                if time_str and time_str.lower().startswith("immed"):
                    scheduled_dt = datetime.strptime(date_str, "%Y-%m-%d")
                else:
                    dt_str = f"{date_str} {time_str}" if time_str else date_str
                    for fmt in ["%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                        try:
                            scheduled_dt = datetime.strptime(dt_str, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        scheduled_dt = datetime.strptime(date_str, "%Y-%m-%d")

                # First email in the future is "next"
                if scheduled_dt >= now and next_idx is None:
                    next_idx = i
                    break
            except Exception:
                continue

        # Display emails with icons
        for i, e in enumerate(emails):
            date_str = e.get("date", "")
            time_str = e.get("time", "")

            # Determine if sent (in the past)
            is_sent = False
            try:
                if date_str:
                    if time_str and time_str.lower().startswith("immed"):
                        scheduled_dt = datetime.strptime(date_str, "%Y-%m-%d")
                    else:
                        dt_str = f"{date_str} {time_str}" if time_str else date_str
                        for fmt in ["%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                            try:
                                scheduled_dt = datetime.strptime(dt_str, fmt)
                                break
                            except ValueError:
                                continue
                        else:
                            scheduled_dt = datetime.strptime(date_str, "%Y-%m-%d")

                    is_sent = scheduled_dt < now
            except Exception:
                pass

            if is_sent:
                prefix = "✓"
            elif next_idx is not None and i == next_idx:
                prefix = "→"
            else:
                prefix = "•"

            ttk.Label(emails_box, text=f"{prefix}  {e.get('name','(unnamed)')}").pack(anchor="w", pady=2)

        btns = ttk.Frame(wrap)
        btns.grid(row=4, column=0, sticky="e", pady=(12, 0))

        def _cancel():
            if on_cancel and messagebox.askyesno("Cancel campaign?", "This will cancel scheduled emails for this campaign. Continue?"):
                on_cancel(campaign)
                win.destroy()

        tk.Button(
            btns,
            text="Close",
            command=win.destroy,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            font=FONT_BTN_SM,
            cursor="hand2",
            padx=12,
            pady=4,
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            btns,
            text="Cancel Campaign",
            command=_cancel,
            bg=BG_ENTRY,
            fg=DANGER,
            activebackground=BG_HOVER,
            activeforeground=DANGER,
            relief="flat",
            font=FONT_BTN_SM,
            cursor="hand2",
            padx=12,
            pady=4,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="right")

        # Center the window and make it modal
        self._center_window(win, parent=self)
        win.transient(self)
        win.grab_set()

    def _make_scroller(self, parent):
        """Create scrollable container with canvas and inner frame."""
        # Use tk.Frame with explicit background to match page
        holder = tk.Frame(parent, bg=BG_ROOT)
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(0, weight=1)

        # CRITICAL: Canvas must have explicit background matching page
        canvas = tk.Canvas(holder, highlightthickness=0, bd=0, bg=BG_ROOT)
        vsb = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        # Inner frame must also match background
        inner = tk.Frame(canvas, bg=BG_ROOT)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_config(_evt=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_config(evt):
            canvas.itemconfigure(win_id, width=evt.width)

        inner.bind("<Configure>", _on_inner_config)
        canvas.bind("<Configure>", _on_canvas_config)

        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Mousewheel scrolling (Windows)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        holder.bind("<Enter>", lambda e: holder.bind_all("<MouseWheel>", _on_mousewheel))
        holder.bind("<Leave>", lambda e: holder.unbind_all("<MouseWheel>"))

        return holder, inner

    def _render_campaign_row(self, parent, campaign, on_click=None, is_completed=False):
        """
        Render a compact, scannable campaign row with responses and expandable details.

        Shows:
        - Campaign name (bold, clickable)
        - "X emails • Y contacts • Z responses"
        - Response rate badge
        - "Up Next: ..."
        - Expandable details section
        """
        # Main container
        container = ttk.Frame(parent, style="Dash.TFrame")

        row = ttk.Frame(container, style="Dash.TFrame")
        row.pack(fill="x")
        row.grid_columnconfigure(0, weight=2, minsize=220)  # Name
        row.grid_columnconfigure(1, weight=0, minsize=80)   # Badge
        row.grid_columnconfigure(2, weight=0, minsize=100)  # Responses
        row.grid_columnconfigure(3, weight=0, minsize=110)  # Emails Removed
        row.grid_columnconfigure(4, weight=0, minsize=80)   # Emails
        row.grid_columnconfigure(5, weight=0, minsize=100)  # Contacts
        row.grid_columnconfigure(6, weight=1)               # Spacer
        row.grid_columnconfigure(7, weight=0)               # Delete

        # Campaign name (bold, clickable)
        name = ttk.Label(row, text=str(campaign.get("name", "Untitled")), style="Dash.Name.TLabel", cursor="hand2")

        # Response count with color coding (moved left)
        responses = campaign.get("responses", campaign.get("_original", {}).get("responses", 0))
        response_color = GOOD if responses > 0 else FG_MUTED

        email_count = campaign.get("total_emails", campaign.get("email_count", 0))
        contact_count = campaign.get("contacts_count", campaign.get("contact_count", 0))

        # Calculate response rate
        total_sent = email_count * contact_count
        response_rate = round((responses / total_sent) * 100, 1) if total_sent > 0 else 0

        responses_text = f'{responses} responses'
        if responses > 0 and total_sent > 0:
            responses_text += f' ({response_rate}%)'

        responses_label = tk.Label(
            row,
            text=responses_text,
            bg=BG_CARD,
            fg=response_color,
            font=FONT_SMALL,
        )

        # Emails removed count
        emails_removed = campaign.get("emails_removed", campaign.get("_original", {}).get("emails_removed", 0))
        removed_color = WARN if emails_removed > 0 else FG_MUTED
        removed_label = tk.Label(
            row,
            text=f'{emails_removed} removed',
            bg=BG_CARD,
            fg=removed_color,
            font=FONT_SMALL,
        )

        # Email count (clickable)
        emails_label = tk.Label(
            row,
            text=f'{email_count} emails',
            bg=BG_CARD, fg=ACCENT, font=FONT_SMALL, cursor="hand2",
        )
        emails_label.bind("<Button-1>", lambda _e, c=campaign: self._show_email_titles_popup(c))

        # Contact count (clickable)
        contacts_label = tk.Label(
            row,
            text=f'{contact_count} contacts',
            bg=BG_CARD, fg=ACCENT, font=FONT_SMALL, cursor="hand2",
        )
        contacts_label.bind("<Button-1>", lambda _e, c=campaign: self._show_contacts_popup(c))

        # Status badge
        if is_completed:
            status_badge = make_badge(row, text="Completed", variant="default")
        elif responses > 0:
            status_badge = make_badge(row, text="In Progress", variant="info")
        else:
            status_badge = make_badge(row, text="Active", variant="success")

        # Up Next status
        status2 = ttk.Label(row, text=campaign.get("status_line2", "Up Next: --"), style="Dash.Status.TLabel")

        # Delete button (matches "Delete Email" style from Build Emails)
        delete_btn = tk.Button(
            row,
            text="Delete",
            command=lambda c=campaign: self._confirm_delete_campaign(c),
            bg=DANGER_BG,
            fg=DANGER_FG,
            activebackground=DANGER_BG,
            activeforeground=DANGER_FG,
            relief="flat",
            font=FONT_SMALL,
            padx=10,
            pady=4,
            cursor="hand2",
        )

        # Layout with proper alignment and more breathing room
        name.grid(row=0, column=0, sticky="w", padx=(SP_3, SP_2), pady=(SP_3, 4))
        status_badge.grid(row=0, column=1, sticky="w", padx=(0, SP_2), pady=(SP_3, 4))
        responses_label.grid(row=0, column=2, sticky="e", padx=(SP_2, SP_2), pady=(SP_3, 4))
        removed_label.grid(row=0, column=3, sticky="e", padx=(SP_2, SP_2), pady=(SP_3, 4))
        emails_label.grid(row=0, column=4, sticky="e", padx=(SP_2, SP_2), pady=(SP_3, 4))
        contacts_label.grid(row=0, column=5, sticky="e", padx=(SP_2, SP_3), pady=(SP_3, 4))
        delete_btn.grid(row=0, column=7, sticky="e", padx=(0, SP_3), pady=(SP_3, 4))
        status2.grid(row=1, column=0, columnspan=8, sticky="w", padx=SP_3, pady=(0, SP_3))

        # Expandable details section (hidden by default)
        details_frame = tk.Frame(container, bg=SURFACE_INSET)
        details_visible = tk.BooleanVar(value=False)

        def toggle_details(_e=None):
            if details_visible.get():
                details_frame.pack_forget()
                details_visible.set(False)
            else:
                self._populate_campaign_details(details_frame, campaign, is_completed=is_completed)
                details_frame.pack(fill="x", padx=SP_3, pady=(0, SP_2))
                details_visible.set(True)

        # Make row clickable to expand
        name.bind("<Button-1>", toggle_details)
        row.bind("<Button-1>", toggle_details)

        # Make entire row hoverable (subtle highlight)
        def on_enter(_e):
            row.configure(style="Dash.Hover.TFrame")
            for lbl in (emails_label, contacts_label, responses_label, removed_label):
                lbl.config(bg=GRAY_100)
        def on_leave(_e):
            row.configure(style="Dash.TFrame")
            for lbl in (emails_label, contacts_label, responses_label, removed_label):
                lbl.config(bg=BG_CARD)

        row.bind("<Enter>", on_enter)
        row.bind("<Leave>", on_leave)

        # Right-click context menu
        def show_response_menu(event):
            menu = tk.Menu(row, tearoff=0)
            menu.add_command(label="View Details", command=toggle_details)
            menu.post(event.x_root, event.y_root)

        row.bind("<Button-3>", show_response_menu)
        name.bind("<Button-3>", show_response_menu)

        # Return container and separator
        sep = ttk.Separator(parent, orient="horizontal")

        return container, sep

    def _confirm_delete_campaign(self, campaign):
        """Prompt user to confirm campaign deletion, then cancel pending emails and remove the campaign file."""
        original = campaign.get("_original", campaign)
        name = campaign.get("name", original.get("name", "Untitled"))
        contact_emails = original.get("contact_emails", [])
        email_count = campaign.get("total_emails", len(original.get("emails", [])))
        contact_count = len(contact_emails) if contact_emails else campaign.get("contacts_count", 0)

        ok = messagebox.askyesno(
            "Delete Campaign",
            f"Are you sure you want to delete \"{name}\"?\n\n"
            f"This will cancel all pending emails for this campaign "
            f"({email_count} emails x {contact_count} contacts) "
            f"and remove them from your Outlook Outbox.\n\n"
            f"This cannot be undone.",
            icon="warning",
        )
        if not ok:
            return

        # Cancel pending Outlook emails for all contacts in this campaign
        cancelled = 0
        if contact_emails and HAVE_OUTLOOK:
            try:
                cancelled = self._cancel_campaign_outbox_emails(contact_emails)
            except Exception:
                _write_crash_log("delete_campaign_cancel")

        # Delete the campaign JSON file
        filepath = original.get("_filepath", "")
        if filepath and os.path.isfile(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass

        # Refresh the dashboard
        self._set_status(f"Deleted \"{name}\" — {cancelled} pending emails cancelled", GOOD)
        self.toast.show(f"Campaign deleted — {cancelled} pending emails cancelled", "warning")
        self._refresh_dashboard()

    def _cancel_campaign_outbox_emails(self, contact_emails):
        """Cancel all pending Outlook Outbox emails addressed to the given contact list.
        Returns the number of emails cancelled."""
        contacts_lower = set(e.lower() for e in contact_emails if e)
        if not contacts_lower:
            return 0

        outlook = win32com.client.dynamic.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
        now = datetime.now()
        moved = 0

        for i in range(1, ns.Folders.Count + 1):
            store = ns.Folders.Item(i)
            try:
                outbox = store.Folders.Item("Outbox")
            except Exception:
                continue

            # Find Deleted Items folder
            deleted = None
            for del_name in ("Deleted Items", "Deleted", "Trash"):
                try:
                    deleted = store.Folders.Item(del_name)
                    break
                except Exception:
                    continue
            if deleted is None:
                try:
                    deleted = ns.GetDefaultFolder(3)
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

                # Skip already-sent items
                try:
                    ddt = item.DeferredDeliveryTime
                    if ddt and ddt <= now:
                        continue
                except Exception:
                    pass

                # Check if recipient matches any campaign contact
                try:
                    to_field = str(item.To or "").lower()
                except Exception:
                    continue

                if any(contact in to_field for contact in contacts_lower):
                    try:
                        if deleted:
                            item.Move(deleted)
                        else:
                            item.Delete()
                        moved += 1
                    except Exception:
                        pass

        return moved

    def _refresh_dashboard(self):
        """Refresh the dashboard campaign lists."""
        try:
            active = self._get_active_campaigns()
            completed = self._get_completed_campaigns()
            if hasattr(self, "active_campaigns_body"):
                self._populate_active_campaigns(self.active_campaigns_body, active)
            if hasattr(self, "completed_campaigns_body"):
                self._populate_active_campaigns(self.completed_campaigns_body, completed, is_completed=True)
            # Update tab counts
            if hasattr(self, "_dash_tab_active"):
                self._dash_tab_active.configure(text=f"Active Campaigns ({len(active)})")
            if hasattr(self, "_dash_tab_completed"):
                self._dash_tab_completed.configure(text=f"Completed Campaigns ({len(completed)})")
        except Exception:
            pass

    def _show_email_titles_popup(self, campaign):
        """Show a popup listing the email titles/subjects for a campaign."""
        original = campaign.get("_original", campaign)
        emails = original.get("emails", [])
        name = campaign.get("name", "Campaign")

        dlg = tk.Toplevel(self)
        dlg.title(f"Emails — {name}")
        dlg.configure(bg=BG_ROOT)
        dlg.resizable(False, False)
        dlg.geometry("450x350")

        tk.Label(dlg, text=f"Emails in {name}", bg=BG_ROOT, fg=FG_TEXT, font=FONT_SECTION_TITLE).pack(anchor="w", padx=14, pady=(14, 8))

        list_frame = tk.Frame(dlg, bg=BG_ROOT)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(
            list_frame, bg=BG_ENTRY, fg=FG_TEXT, font=FONT_BASE,
            selectbackground=ACCENT, selectforeground="#FFFFFF",
            highlightthickness=0, relief="flat", yscrollcommand=scrollbar.set,
        )
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        if emails:
            for i, email in enumerate(emails):
                subj = email.get("subject", email.get("name", f"Email {i+1}"))
                date = email.get("date", "")
                time_str = email.get("time", "")
                line = f"Email {i+1}: {subj}"
                if date:
                    line += f"  —  {date} @ {time_str}"
                listbox.insert("end", line)
        else:
            listbox.insert("end", "No email data available")

        tk.Button(
            dlg, text="Close", command=dlg.destroy,
            bg=BG_CARD, fg=FG_TEXT, activebackground=BG_HOVER, activeforeground=FG_TEXT,
            relief="flat", padx=12, pady=7, cursor="hand2",
        ).pack(pady=(0, 14))

        def _center():
            try:
                x = self.winfo_rootx() + (self.winfo_width() // 2) - (dlg.winfo_width() // 2)
                y = self.winfo_rooty() + (self.winfo_height() // 2) - (dlg.winfo_height() // 2)
                dlg.geometry(f"450x350+{x}+{y}")
            except Exception:
                pass
        dlg.after(10, _center)

    def _show_contacts_popup(self, campaign):
        """Show a popup listing the contacts for a campaign."""
        original = campaign.get("_original", campaign)
        contacts = original.get("contact_emails", [])
        contact_list = original.get("contacts", [])
        name = campaign.get("name", "Campaign")

        dlg = tk.Toplevel(self)
        dlg.title(f"Contacts — {name}")
        dlg.configure(bg=BG_ROOT)
        dlg.resizable(False, False)
        dlg.geometry("450x350")

        tk.Label(dlg, text=f"Contacts in {name}", bg=BG_ROOT, fg=FG_TEXT, font=FONT_SECTION_TITLE).pack(anchor="w", padx=14, pady=(14, 8))

        list_frame = tk.Frame(dlg, bg=BG_ROOT)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(
            list_frame, bg=BG_ENTRY, fg=FG_TEXT, font=FONT_BASE,
            selectbackground=ACCENT, selectforeground="#FFFFFF",
            highlightthickness=0, relief="flat", yscrollcommand=scrollbar.set,
        )
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        # Try contact_emails first, then contacts list, then responders as fallback
        if contacts:
            for email in contacts:
                listbox.insert("end", email)
        elif contact_list:
            for contact in contact_list:
                if isinstance(contact, dict):
                    display = contact.get("email", contact.get("Email", ""))
                    fname = contact.get("FirstName", contact.get("first_name", ""))
                    lname = contact.get("LastName", contact.get("last_name", ""))
                    if fname or lname:
                        display = f"{fname} {lname}".strip() + f"  —  {display}" if display else f"{fname} {lname}".strip()
                    listbox.insert("end", display or str(contact))
                else:
                    listbox.insert("end", str(contact))
        else:
            # Fallback: show responder emails (older campaigns without contact_emails)
            responders = original.get("responders", [])
            if responders:
                seen = set()
                for resp in responders:
                    email_addr = resp.split(" - ")[0].strip()
                    if email_addr and email_addr not in seen:
                        seen.add(email_addr)
                        listbox.insert("end", email_addr)
            else:
                listbox.insert("end", "No contact data available")

        tk.Button(
            dlg, text="Close", command=dlg.destroy,
            bg=BG_CARD, fg=FG_TEXT, activebackground=BG_HOVER, activeforeground=FG_TEXT,
            relief="flat", padx=12, pady=7, cursor="hand2",
        ).pack(pady=(0, 14))

        def _center():
            try:
                x = self.winfo_rootx() + (self.winfo_width() // 2) - (dlg.winfo_width() // 2)
                y = self.winfo_rooty() + (self.winfo_height() // 2) - (dlg.winfo_height() // 2)
                dlg.geometry(f"450x350+{x}+{y}")
            except Exception:
                pass
        dlg.after(10, _center)

    def _populate_campaign_details(self, frame, campaign, is_completed=False):
        """Populate the expandable campaign details section."""
        # Clear existing
        for w in frame.winfo_children():
            w.destroy()

        # Get original campaign data
        original = campaign.get("_original", campaign)
        detail_bg = SURFACE_INSET

        inner = tk.Frame(frame, bg=detail_bg)
        inner.pack(fill="x", padx=SP_3, pady=SP_3)

        # Header
        tk.Label(
            inner, text="Campaign Details",
            bg=detail_bg, fg=ACCENT,
            font=FONT_SECTION_TITLE,
        ).pack(anchor="w", pady=(0, SP_2))

        # Two column layout
        cols = tk.Frame(inner, bg=detail_bg)
        cols.pack(fill="x")
        cols.columnconfigure((0, 1), weight=1)

        # Left column: Response tracking (moved to left)
        left = tk.Frame(cols, bg=detail_bg)
        left.grid(row=0, column=0, sticky="nw", padx=(0, SP_4))

        tk.Label(left, text="Response Tracking:", bg=detail_bg, fg=FG_TEXT, font=FONT_BODY_MEDIUM).pack(anchor="w")

        responses = original.get("responses", 0)
        responders = original.get("responders", [])
        emails_removed = original.get("emails_removed", 0)

        tk.Label(
            left, text=f"  Total responses: {responses}",
            bg=detail_bg, fg=SUCCESS_FG if responses > 0 else GRAY_400,
            font=FONT_SMALL,
        ).pack(anchor="w")

        tk.Label(
            left, text=f"  Emails removed: {emails_removed}",
            bg=detail_bg, fg=WARN if emails_removed > 0 else GRAY_400,
            font=FONT_SMALL,
        ).pack(anchor="w")

        if responders:
            tk.Label(left, text="  Recent responders:", bg=detail_bg, fg=GRAY_600, font=FONT_SMALL).pack(anchor="w")
            for responder in responders[:3]:
                tk.Label(
                    left, text=f"    {responder}",
                    bg=detail_bg, fg=GRAY_500, font=FONT_SMALL,
                ).pack(anchor="w", pady=1)

        # Right column: Email schedule
        right = tk.Frame(cols, bg=detail_bg)
        right.grid(row=0, column=1, sticky="nw")

        tk.Label(right, text="Email Schedule:", bg=detail_bg, fg=FG_TEXT, font=FONT_BODY_MEDIUM).pack(anchor="w")

        emails = original.get("emails", [])
        for i, email in enumerate(emails[:5]):  # Show first 5
            name = email.get("name", email.get("subject", f"Email {i+1}"))
            date = email.get("date", "")
            time = email.get("time", "")
            schedule = f"{date} @ {time}" if date else "Not scheduled"

            tk.Label(
                right, text=f"  {name}: {schedule}",
                bg=detail_bg, fg=GRAY_500, font=FONT_SMALL,
            ).pack(anchor="w", pady=1)

        if len(emails) > 5:
            tk.Label(right, text=f"  ... and {len(emails) - 5} more", bg=detail_bg, fg=GRAY_400, font=FONT_CAPTION).pack(anchor="w")


    def _find_campaign_file(self, campaign_data):
        """Find the actual campaign file on disk.

        Campaign files are saved as {sanitized_name}_{timestamp}.json, but the
        campaign dict stores the display name. This method resolves the correct file
        using the stored _filepath, or falls back to searching by name content.
        """
        # 1. Use stored filepath if available
        filepath = campaign_data.get("_filepath")
        if filepath:
            p = Path(filepath)
            if p.exists():
                return p

        camp_name = campaign_data.get("name", "")
        if not camp_name:
            return None

        # 2. Try direct name match (legacy)
        direct = CAMPAIGNS_DIR / f"{camp_name}.json"
        if direct.exists():
            return direct

        # 3. Search by sanitized name prefix
        safe_name = self._sanitize_filename(camp_name)
        matches = sorted(
            CAMPAIGNS_DIR.glob(f"{safe_name}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0]

        # 4. Search by matching name field in file content
        for f in CAMPAIGNS_DIR.glob("*.json"):
            try:
                with f.open("r", encoding="utf-8") as fh:
                    d = json.load(fh)
                if d.get("name") == camp_name:
                    return f
            except Exception:
                continue

        return None

    def _add_campaign_response(self, campaign):
        """Manually add a response to a campaign."""
        original = campaign.get("_original", campaign)
        camp_name = original.get("name", "Unknown")

        # Ask for responder email/name
        responder = themed_askstring(self, "Add Response", f"Enter responder email or name for '{camp_name}':", "")
        if not responder or not responder.strip():
            return

        responder = responder.strip()

        # Update campaign file
        try:
            camp_file = self._find_campaign_file(original)
            if camp_file and camp_file.exists():
                with camp_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                data["responses"] = data.get("responses", 0) + 1
                if "responders" not in data:
                    data["responders"] = []
                data["responders"].insert(0, f"{responder} - {datetime.now().strftime('%m/%d %I:%M %p')}")

                with camp_file.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

                self._set_status(f"Response added to {camp_name}", GOOD)
                self.refresh_dashboard()
                self._refresh_dashboard_stats()
            else:
                messagebox.showerror("Error", f"Campaign file not found for '{camp_name}'.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add response: {e}")

    def _scan_campaign_replies(self, campaign):
        """Scan Outlook inbox for replies to this campaign."""
        original = campaign.get("_original", campaign)
        camp_name = original.get("name", "Unknown")

        # Get campaign contacts and subjects
        emails = original.get("emails", [])
        subjects = [e.get("subject", "") for e in emails if e.get("subject")]

        if not subjects:
            messagebox.showinfo("No Subjects", "No email subjects found in this campaign to scan for.")
            return

        self._set_status(f"Scanning Outlook for replies...", WARN)
        self.update_idletasks()

        try:
            # Try to scan Outlook
            outlook = fourdrip_core.get_outlook_app()
            namespace = outlook.GetNamespace("MAPI")
            inbox = namespace.GetDefaultFolder(6)  # 6 = Inbox

            found_replies = 0
            deleted_emails = 0
            new_responders = []
            skipped_ooo = 0

            # Get existing responders to avoid counting duplicates
            existing_responders = set(
                r.split(" - ")[0] for r in original.get("responders", [])
            )

            # Get campaign contacts for validation
            campaign_contacts = set(
                e.lower() for e in original.get("contact_emails", [])
            )

            # Build lowercase subject set for exact matching
            subjects_lower = set(s.lower() for s in subjects)

            # Use Outlook Restrict for faster filtering (last 30 days)
            cutoff = datetime.now() - timedelta(days=30)
            cutoff_str = cutoff.strftime("%m/%d/%Y")
            date_filter = f"[ReceivedTime] >= '{cutoff_str}'"
            recent_items = inbox.Items.Restrict(date_filter)
            recent_items.Sort("[ReceivedTime]", True)

            for item in recent_items:
                try:
                    if not hasattr(item, 'Subject') or not item.Subject:
                        continue

                    # Strip RE:/FW:/FWD: prefixes for exact matching
                    reply_subj = item.Subject.lower().strip()
                    cleaned = reply_subj
                    while True:
                        stripped = cleaned.lstrip()
                        if stripped.startswith("re:"):
                            cleaned = stripped[3:]
                        elif stripped.startswith("fw:"):
                            cleaned = stripped[3:]
                        elif stripped.startswith("fwd:"):
                            cleaned = stripped[4:]
                        else:
                            break
                    cleaned = cleaned.strip()

                    # Skip if not a reply (no prefix was stripped)
                    if cleaned == reply_subj.strip():
                        continue

                    # Exact match: cleaned subject must match a campaign subject
                    if cleaned not in subjects_lower:
                        continue

                    # Skip out-of-office and automatic replies
                    if self._is_out_of_office_reply(item):
                        skipped_ooo += 1
                        continue

                    sender = self._get_sender_smtp_address(item)

                    # Skip X500/Exchange addresses
                    if "/CN=" in sender.upper() or "/O=" in sender.upper():
                        continue

                    # If campaign has contact list, only count responses
                    # from people who were actually contacts in this campaign
                    if campaign_contacts and sender.lower() not in campaign_contacts:
                        continue

                    # Skip if already tracked in this campaign
                    if sender not in new_responders and sender not in existing_responders:
                        new_responders.append(sender)
                        found_replies += 1

                        # Delete pending emails to this contact
                        deleted = self._delete_pending_emails_for_contact(namespace, sender)
                        deleted_emails += deleted
                except:
                    continue

                if found_replies >= 50:  # Limit scan
                    break

            # Update campaign with found replies
            if found_replies > 0:
                camp_file = self._find_campaign_file(original)
                if camp_file and camp_file.exists():
                    with camp_file.open("r", encoding="utf-8") as f:
                        data = json.load(f)

                    data["responses"] = data.get("responses", 0) + found_replies
                    if "responders" not in data:
                        data["responders"] = []

                    for resp in new_responders:
                        data["responders"].insert(0, f"{resp} - {datetime.now().strftime('%m/%d %I:%M %p')}")

                    if deleted_emails > 0:
                        data["emails_removed"] = data.get("emails_removed", 0) + deleted_emails

                    with camp_file.open("w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)

                # Build result message
                result_msg = f"Found {found_replies} new replies to '{camp_name}'!"
                if deleted_emails > 0:
                    result_msg += f"\n\nCancelled {deleted_emails} pending follow-up email(s)."
                if skipped_ooo > 0:
                    result_msg += f"\n\nSkipped {skipped_ooo} out-of-office reply(ies)."

                self._set_status(f"Found {found_replies} replies!", GOOD)
                messagebox.showinfo("Scan Complete", result_msg)
                self.refresh_dashboard()
                self._refresh_dashboard_stats()
            else:
                status_msg = f"No new replies found for '{camp_name}'."
                if skipped_ooo > 0:
                    status_msg += f"\n\n(Skipped {skipped_ooo} out-of-office reply(ies))"
                self._set_status("No new replies found", WARN)
                messagebox.showinfo("Scan Complete", status_msg)

        except Exception as e:
            self._set_status("Scan failed", DANGER)
            messagebox.showerror("Scan Error", f"Could not scan Outlook:\n{e}")

    def _get_sender_smtp_address(self, item):
        """Get the proper SMTP email address from an Outlook mail item.

        Handles Exchange X500 addresses by extracting the actual SMTP address.
        """
        try:
            # First try to get the SMTP address directly
            if hasattr(item, 'SenderEmailType') and item.SenderEmailType == "SMTP":
                return item.SenderEmailAddress

            # For Exchange users, try to get the SMTP address
            if hasattr(item, 'Sender') and item.Sender:
                sender = item.Sender

                # Try GetExchangeUser for Exchange addresses
                try:
                    exchange_user = sender.GetExchangeUser()
                    if exchange_user and exchange_user.PrimarySmtpAddress:
                        return exchange_user.PrimarySmtpAddress
                except:
                    pass

                # Try PropertyAccessor for SMTP address on sender
                try:
                    PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001F"
                    smtp_address = sender.PropertyAccessor.GetProperty(PR_SMTP_ADDRESS)
                    if smtp_address and "@" in smtp_address:
                        return smtp_address
                except:
                    pass

            # Try PropertyAccessor on item itself
            try:
                PR_SENDER_SMTP = "http://schemas.microsoft.com/mapi/proptag/0x5D01001F"
                sender_smtp = item.PropertyAccessor.GetProperty(PR_SENDER_SMTP)
                if sender_smtp and "@" in sender_smtp:
                    return sender_smtp
            except:
                pass

            # Fallback: try to extract email from SenderEmailAddress if it looks like X500
            sender_addr = item.SenderEmailAddress if hasattr(item, 'SenderEmailAddress') else ""
            if sender_addr and "/CN=" in sender_addr.upper():
                # X500 format - try to get from SenderName or reply-to
                if hasattr(item, 'SenderName') and "@" in str(item.SenderName or ""):
                    return item.SenderName
                # Try Reply-To
                try:
                    if hasattr(item, 'ReplyRecipients') and item.ReplyRecipients.Count > 0:
                        reply_addr = item.ReplyRecipients.Item(1).Address
                        if "@" in reply_addr:
                            return reply_addr
                except:
                    pass
                # Return a cleaned version of the name if available
                if hasattr(item, 'SenderName') and item.SenderName:
                    return f"{item.SenderName} (Exchange)"
                return "Exchange User"

            # Return the SenderEmailAddress as-is if it looks like an email
            if sender_addr and "@" in sender_addr:
                return sender_addr

            # Last resort: SenderName
            if hasattr(item, 'SenderName') and item.SenderName:
                return item.SenderName

            return "Unknown"
        except:
            # Fallback
            try:
                return item.SenderEmailAddress if hasattr(item, 'SenderEmailAddress') else "Unknown"
            except:
                return "Unknown"

    def _is_out_of_office_reply(self, item):
        """Check if an email item is an out-of-office or automatic reply."""
        try:
            subject = item.Subject.lower() if hasattr(item, 'Subject') and item.Subject else ""

            # Common out-of-office patterns
            ooo_patterns = [
                "out of office",
                "out of the office",
                "automatic reply",
                "auto-reply",
                "autoreply",
                "auto reply",
                "i am currently out",
                "i'm currently out",
                "i will be out",
                "i'm out of the office",
                "away from the office",
                "on vacation",
                "on leave",
                "limited access to email",
                "delayed response",
                "ooo:",
                "[ooo]",
                "abwesenheitsnotiz",  # German
                "absence du bureau",  # French
            ]

            for pattern in ooo_patterns:
                if pattern in subject:
                    return True

            # Check sender for automated addresses
            sender = self._get_sender_smtp_address(item).lower()

            auto_senders = ["noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster"]
            for auto in auto_senders:
                if auto in sender:
                    return True

            return False
        except:
            return False

    def _delete_pending_emails_for_contact(self, namespace, contact_email):
        """Delete any pending/scheduled emails to a contact from Outlook outbox."""
        deleted_count = 0
        try:
            # Get Outbox folder (4 = olFolderOutbox)
            outbox = namespace.GetDefaultFolder(4)
            items_to_delete = []

            contact_email_lower = contact_email.lower()

            # Find emails to this contact in the outbox
            for item in outbox.Items:
                try:
                    if hasattr(item, 'To'):
                        recipients = (item.To or "").lower()
                        if contact_email_lower in recipients:
                            items_to_delete.append(item)
                except:
                    continue

            # Delete the found items
            for item in items_to_delete:
                try:
                    item.Delete()
                    deleted_count += 1
                except:
                    continue

        except Exception:
            pass  # Silently fail - outbox access can be tricky

        return deleted_count

    def _auto_scan_all_campaigns_on_startup(self):
        """Launch the Outlook scan in a background thread to avoid freezing the UI."""
        def _scan_thread():
            try:
                self._do_background_scan()
            except Exception:
                pass
            finally:
                # Update UI from main thread
                self.after(0, lambda: self._set_status("Ready", GOOD))

        # Show scanning status
        self._set_status("Scanning Outlook for responses...", WARN)

        # Run in background thread
        thread = threading.Thread(target=_scan_thread, daemon=True)
        thread.start()

    def _do_background_scan(self):
        """Perform the actual Outlook scan (runs in background thread)."""
        try:
            # Get all campaign files
            if not CAMPAIGNS_DIR.exists():
                return

            campaign_files = list(CAMPAIGNS_DIR.glob("*.json"))
            if not campaign_files:
                return

            # Try to connect to Outlook
            import pythoncom
            pythoncom.CoInitialize()  # Required for COM in threads

            try:
                outlook = fourdrip_core.get_outlook_app()
                namespace = outlook.GetNamespace("MAPI")
                inbox = namespace.GetDefaultFolder(6)  # 6 = Inbox

                total_found = 0
                total_deleted = 0
                campaigns_with_replies = []

                # Track (sender, subject) pairs already claimed by a campaign
                # to prevent the same reply being counted across multiple campaigns
                globally_claimed = set()

                # Use Outlook's Restrict to filter to last 30 days only (MUCH faster)
                cutoff = datetime.now() - timedelta(days=30)
                cutoff_str = cutoff.strftime("%m/%d/%Y")
                date_filter = f"[ReceivedTime] >= '{cutoff_str}'"

                # Get only recent items
                recent_items = inbox.Items.Restrict(date_filter)
                recent_items.Sort("[ReceivedTime]", True)

                # Build a list of recent items once (avoid repeated iteration)
                recent_emails = []
                for item in recent_items:
                    try:
                        if hasattr(item, 'Subject') and item.Subject:
                            recent_emails.append({
                                'subject': item.Subject.lower(),
                                'sender': self._get_sender_smtp_address(item),
                                'item': item
                            })
                    except:
                        continue
                    if len(recent_emails) >= 500:  # Limit to avoid memory issues
                        break

                for camp_file in campaign_files:
                    try:
                        with camp_file.open("r", encoding="utf-8") as f:
                            data = json.load(f)

                        camp_name = data.get("name", camp_file.stem)
                        emails = data.get("emails", [])
                        subjects = [e.get("subject", "").lower() for e in emails if e.get("subject")]

                        if not subjects:
                            continue

                        # Get existing responders to avoid duplicates
                        existing_responders = set(
                            r.split(" - ")[0] for r in data.get("responders", [])
                        )

                        # Get campaign contacts for validation (only count responses
                        # from people who were actually in this campaign)
                        campaign_contacts = set(
                            e.lower() for e in data.get("contact_emails", [])
                        )

                        found_replies = 0
                        camp_deleted = 0
                        new_responders = []

                        # Build a set of campaign subjects for exact matching
                        subjects_set = set(subjects)

                        # Search recent emails for replies
                        for email_data in recent_emails:
                            try:
                                # Strip all RE:/FW:/FWD: prefixes to get the original subject
                                reply_subj = email_data['subject']
                                cleaned = reply_subj
                                while True:
                                    stripped = cleaned.lstrip()
                                    if stripped.startswith("re:"):
                                        cleaned = stripped[3:]
                                    elif stripped.startswith("fw:"):
                                        cleaned = stripped[3:]
                                    elif stripped.startswith("fwd:"):
                                        cleaned = stripped[4:]
                                    else:
                                        break
                                cleaned = cleaned.strip()

                                # Skip if not a reply at all (no prefix was stripped)
                                if cleaned == reply_subj.strip():
                                    continue

                                # Exact match: cleaned subject must match a campaign subject exactly
                                if cleaned in subjects_set:
                                    # Skip out-of-office and automatic replies
                                    if self._is_out_of_office_reply(email_data['item']):
                                        continue

                                    sender = email_data['sender']
                                    # Skip X500/Exchange addresses that slipped through
                                    if "/CN=" in sender.upper() or "/O=" in sender.upper():
                                        continue

                                    # If campaign has contact list, only count responses
                                    # from people who were actually contacts in this campaign
                                    if campaign_contacts and sender.lower() not in campaign_contacts:
                                        continue

                                    # Skip if this reply was already claimed by another campaign
                                    claim_key = (sender.lower(), cleaned)
                                    if claim_key in globally_claimed:
                                        continue

                                    # Always claim this (sender, subject) pair to prevent
                                    # other campaigns from counting the same reply
                                    globally_claimed.add(claim_key)

                                    # Skip if already tracked in this campaign
                                    if sender not in existing_responders and sender not in new_responders:
                                        new_responders.append(sender)
                                        found_replies += 1

                                        # Delete pending emails to this contact
                                        deleted = self._delete_pending_emails_for_contact(namespace, sender)
                                        total_deleted += deleted
                                        camp_deleted += deleted
                            except:
                                continue

                            if found_replies >= 20:  # Limit per campaign
                                break

                        # Update campaign if new replies found
                        if found_replies > 0:
                            data["responses"] = data.get("responses", 0) + found_replies
                            if "responders" not in data:
                                data["responders"] = []

                            for resp in new_responders:
                                data["responders"].insert(0, f"{resp} - {datetime.now().strftime('%m/%d %I:%M %p')}")

                            if camp_deleted > 0:
                                data["emails_removed"] = data.get("emails_removed", 0) + camp_deleted

                            with camp_file.open("w", encoding="utf-8") as f:
                                json.dump(data, f, indent=2)

                            total_found += found_replies
                            campaigns_with_replies.append(camp_name)

                    except Exception:
                        continue  # Skip problematic campaigns

                # Update UI from main thread
                if total_found > 0:
                    camp_list = ", ".join(campaigns_with_replies[:3])
                    if len(campaigns_with_replies) > 3:
                        camp_list += f" +{len(campaigns_with_replies) - 3} more"
                    status_msg = f"Found {total_found} new responses! ({camp_list})"
                    if total_deleted > 0:
                        status_msg += f" | Cancelled {total_deleted} pending emails"
                    self.after(0, lambda msg=status_msg: self._set_status(msg, GOOD))
                    self.after(0, self.refresh_dashboard)
                    self.after(0, self._refresh_dashboard_stats)
                else:
                    self.after(0, lambda: self._set_status("Ready", GOOD))

            finally:
                pythoncom.CoUninitialize()

        except Exception:
            # Silently fail - don't interrupt the user
            self.after(0, lambda: self._set_status("Ready", GOOD))

    def _populate_active_campaigns(self, active_body, active_campaigns, is_completed=False):
        """Populate the Active Campaigns section with campaign rows."""
        # Clear existing widgets
        for w in active_body.winfo_children():
            w.destroy()

        # Create scrollable container
        scroller, rows_parent = self._make_scroller(active_body)
        scroller.pack(fill="both", expand=True)

        if not active_campaigns:
            empty = make_empty_state(
                rows_parent,
                icon_text="🚀" if not is_completed else "✓",
                headline="No active campaigns" if not is_completed else "No completed campaigns yet",
                description="Create and launch a campaign to start sending emails automatically." if not is_completed else "Campaigns appear here after all emails have been sent.",
                button_text="New Campaign" if not is_completed else "",
                button_command=(lambda: self._show_screen("campaign")) if not is_completed else None,
                bg=BG_ENTRY
            )
            empty.pack(fill="both", expand=True, padx=12, pady=12)
            return

        # Clear + render
        for child in rows_parent.winfo_children():
            child.destroy()

        for c in active_campaigns:
            # Store original for details modal
            original_campaign = c

            # Adapt object->dict if needed
            if not isinstance(c, dict):
                c = {
                    "name": getattr(c, "name", str(c)),
                    "total_emails": getattr(c, "total_emails", 0),
                    "contacts_count": getattr(c, "contacts_count", 0),
                    "status_line2": "Up Next: —",
                }
            else:
                # Compute "Up Next" status
                up_next = self._compute_completed_and_next(c)

                # Normalize dict keys for row rendering
                c = {
                    "name": c.get("name", "Unnamed Campaign"),
                    "total_emails": len(c.get("emails", [])),
                    "contacts_count": c.get("contact_count", 0),
                    "status_line2": up_next,
                    "_original": original_campaign,  # Preserve original for details modal
                }

            r, s = self._render_campaign_row(rows_parent, c, on_click=None, is_completed=is_completed)
            r.pack(fill="x")
            s.pack(fill="x", padx=12, pady=(0, 2))

    # ============================================
    # Dashboard screen
    # ============================================
    def _build_dashboard_stats_cards(self, parent):
        """Build the stats cards row at the top of the dashboard."""
        stats_frame = tk.Frame(parent, bg=BG_ROOT)
        stats_frame.grid(row=0, column=0, sticky="ew", padx=SP_6, pady=(0, SP_3))
        stats_frame.columnconfigure((0, 1, 2, 3), weight=1, uniform="stats")

        # Calculate stats
        stats = self._calculate_dashboard_stats()

        # Store references for refresh
        self._dashboard_stat_labels = {}

        # Card 1: Emails Sent Past 30 Days
        self._create_stat_card(
            stats_frame, 0,
            icon="📧",
            title="Emails Past 30 Days",
            value=str(stats["emails_past_30_days"]),
            color=ACCENT,
            key="emails_past_30_days"
        )

        # Card 2: Total Responses
        self._create_stat_card(
            stats_frame, 1,
            icon="💬",
            title="Responses",
            value=str(stats["total_responses"]),
            color=GOOD,
            key="total_responses"
        )

        # Card 3: Response Rate
        self._create_stat_card(
            stats_frame, 2,
            icon="📊",
            title="Response Rate",
            value=f"{stats['response_rate']}%",
            color=DARK_AQUA,
            key="response_rate"
        )

        # Card 4: Active Campaigns
        self._create_stat_card(
            stats_frame, 3,
            icon="🎯",
            title="Active Campaigns",
            value=str(stats["active_campaigns"]),
            color=WARN,
            key="active_campaigns"
        )

    def _create_stat_card(self, parent, col, icon, title, value, color, key):
        """Create a single stat card (modern, minimal)."""
        card = tk.Frame(parent, bg=GRAY_200)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else SP_2, 0), pady=0)

        inner = tk.Frame(card, bg=SURFACE_CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        # Colored accent line at top
        tk.Frame(inner, bg=color, height=3).pack(fill="x")

        content = tk.Frame(inner, bg=SURFACE_CARD)
        content.pack(fill="both", expand=True, padx=SP_4, pady=(SP_2, SP_3))

        # Title (small, muted)
        tk.Label(
            content, text=title, bg=SURFACE_CARD, fg=GRAY_500,
            font=FONT_SMALL,
        ).pack(anchor="w")

        # Value (prominent)
        value_label = tk.Label(
            content, text=value, bg=SURFACE_CARD, fg=color,
            font=FONT_HEADING,
        )
        value_label.pack(anchor="w", pady=(SP_1, 0))

        # Store reference for updates
        self._dashboard_stat_labels[key] = value_label

    def _calculate_dashboard_stats(self) -> dict:
        """Calculate dashboard statistics."""
        stats = {
            "emails_past_30_days": 0,
            "total_responses": 0,
            "response_rate": 0,
            "active_campaigns": 0,
        }

        try:
            # Get all campaigns
            active_campaigns = self._get_active_campaigns()
            completed_campaigns = self._get_completed_campaigns()
            all_campaigns = active_campaigns + completed_campaigns

            stats["active_campaigns"] = len(active_campaigns)

            # Calculate emails past 30 days and total responses
            now = datetime.now()
            thirty_days_ago = now - timedelta(days=30)
            total_emails_sent = 0
            total_responses = 0

            for camp in all_campaigns:
                # Count emails scheduled in the past 30 days
                emails = camp.get("emails", [])
                for email in emails:
                    date_str = email.get("date", "")
                    if date_str:
                        try:
                            email_date = datetime.strptime(date_str, "%Y-%m-%d")
                            if thirty_days_ago <= email_date <= now:
                                contact_count = camp.get("contact_count", 0)
                                stats["emails_past_30_days"] += contact_count
                        except:
                            pass

                # Get responses from campaign data
                responses = camp.get("responses", 0)
                total_responses += responses

                # Calculate total emails sent (for response rate)
                contact_count = camp.get("contact_count", 0)
                email_count = len(emails)
                total_emails_sent += contact_count * email_count

            stats["total_responses"] = total_responses

            # Calculate response rate
            if total_emails_sent > 0:
                stats["response_rate"] = round((total_responses / total_emails_sent) * 100, 1)

        except Exception:
            pass

        return stats

    def _sync_user_stats_to_registry(self, stats: dict):
        """Write the current user's dashboard stats to the shared registry."""
        try:
            config = load_config()
            username = config.get("username", "")
            if not username:
                return
            registry = load_user_registry()
            if username in registry.get("users", {}):
                registry["users"][username]["stats"] = {
                    "emails_past_30_days": stats.get("emails_past_30_days", 0),
                    "total_responses": stats.get("total_responses", 0),
                    "response_rate": stats.get("response_rate", 0),
                    "active_campaigns": stats.get("active_campaigns", 0),
                }
                save_user_registry(registry)
        except Exception:
            pass

    def _refresh_dashboard_stats(self):
        """Refresh the dashboard stats cards."""
        if not hasattr(self, '_dashboard_stat_labels'):
            return

        stats = self._calculate_dashboard_stats()

        if "emails_past_30_days" in self._dashboard_stat_labels:
            self._dashboard_stat_labels["emails_past_30_days"].config(text=str(stats["emails_past_30_days"]))
        if "total_responses" in self._dashboard_stat_labels:
            self._dashboard_stat_labels["total_responses"].config(text=str(stats["total_responses"]))
        if "response_rate" in self._dashboard_stat_labels:
            self._dashboard_stat_labels["response_rate"].config(text=f"{stats['response_rate']}%")
        if "active_campaigns" in self._dashboard_stat_labels:
            self._dashboard_stat_labels["active_campaigns"].config(text=str(stats["active_campaigns"]))

        # Sync stats to shared registry so admins can see them
        self._sync_user_stats_to_registry(stats)

    def _build_dashboard_screen(self, parent):
        """Dashboard with tabbed Active / Completed Campaigns"""
        _, content = self._page(parent, "Dashboard", "Your campaigns and activity at a glance")

        content.rowconfigure(0, weight=0)  # Stats cards
        content.rowconfigure(1, weight=0)  # Tab bar
        content.rowconfigure(2, weight=1)  # Campaign content

        # ========== STATS CARDS ROW ==========
        self._build_dashboard_stats_cards(content)

        # ========== TAB BAR ==========
        tab_bar = tk.Frame(content, bg=BG_ROOT)
        tab_bar.grid(row=1, column=0, sticky="ew", padx=18, pady=(12, 0))

        active_campaigns = self._get_active_campaigns()
        completed_campaigns = self._get_completed_campaigns()

        self._dash_tab_active = tk.Label(
            tab_bar, text=f"Active Campaigns ({len(active_campaigns)})",
            bg=BG_ROOT, fg=ACCENT, font=FONT_SECTION,
            cursor="hand2", padx=4, pady=6,
        )
        self._dash_tab_active.pack(side="left", padx=(0, 24))

        self._dash_tab_completed = tk.Label(
            tab_bar, text=f"Completed Campaigns ({len(completed_campaigns)})",
            bg=BG_ROOT, fg=FG_MUTED, font=FONT_SECTION,
            cursor="hand2", padx=4, pady=6,
        )
        self._dash_tab_completed.pack(side="left")

        # Underline indicator
        self._dash_tab_indicator = tk.Frame(content, bg=ACCENT, height=3)
        self._dash_tab_indicator.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 0))
        # Position indicator under active tab after render
        def _position_indicator():
            try:
                w = self._dash_tab_active.winfo_width()
                self._dash_tab_indicator.place_forget()
                self._dash_tab_indicator.grid_forget()
                self._dash_tab_indicator.place(
                    in_=tab_bar, x=0,
                    y=self._dash_tab_active.winfo_height() - 1,
                    width=w, height=3,
                )
            except Exception:
                pass
        tab_bar.after(50, _position_indicator)

        # ========== CAMPAIGN CONTENT AREA ==========
        campaign_area = tk.Frame(content, bg=BG_ROOT)
        campaign_area.grid(row=2, column=0, sticky="nsew", padx=18, pady=(10, 0))

        # Active campaigns body
        self.active_campaigns_body = tk.Frame(campaign_area, bg=BG_ROOT)
        self.active_campaigns_body.pack(fill="both", expand=True)
        self._populate_active_campaigns(self.active_campaigns_body, active_campaigns)

        # Completed campaigns body (hidden initially)
        self.completed_campaigns_body = tk.Frame(campaign_area, bg=BG_ROOT)
        self._populate_active_campaigns(self.completed_campaigns_body, completed_campaigns, is_completed=True)

        # Tab switching logic
        self._dash_active_tab = "active"

        def _switch_tab(tab):
            self._dash_active_tab = tab
            if tab == "active":
                self.completed_campaigns_body.pack_forget()
                self.active_campaigns_body.pack(fill="both", expand=True)
                self._dash_tab_active.configure(fg=ACCENT)
                self._dash_tab_completed.configure(fg=FG_MUTED)
                # Move indicator
                try:
                    w = self._dash_tab_active.winfo_width()
                    self._dash_tab_indicator.place(
                        in_=tab_bar, x=0,
                        y=self._dash_tab_active.winfo_height() - 1,
                        width=w, height=3,
                    )
                except Exception:
                    pass
            else:
                self.active_campaigns_body.pack_forget()
                self.completed_campaigns_body.pack(fill="both", expand=True)
                self._dash_tab_completed.configure(fg=ACCENT)
                self._dash_tab_active.configure(fg=FG_MUTED)
                # Move indicator
                try:
                    x = self._dash_tab_completed.winfo_x()
                    w = self._dash_tab_completed.winfo_width()
                    self._dash_tab_indicator.place(
                        in_=tab_bar, x=x,
                        y=self._dash_tab_completed.winfo_height() - 1,
                        width=w, height=3,
                    )
                except Exception:
                    pass

        self._dash_switch_tab = _switch_tab
        self._dash_tab_active.bind("<Button-1>", lambda _e: _switch_tab("active"))
        self._dash_tab_completed.bind("<Button-1>", lambda _e: _switch_tab("completed"))

    def refresh_dashboard(self):
        """Refresh dashboard data after campaign changes (thread-safe)."""
        # Invalidate cache to force reload
        if hasattr(self, '_campaigns_cache_hash'):
            del self._campaigns_cache_hash

        # Refresh stats cards
        self._refresh_dashboard_stats()

        # Refresh Active Campaigns section
        if hasattr(self, 'active_campaigns_body'):
            active_campaigns = self._get_active_campaigns()
            self._populate_active_campaigns(self.active_campaigns_body, active_campaigns)
            if hasattr(self, '_dash_tab_active'):
                self._dash_tab_active.configure(text=f"Active Campaigns ({len(active_campaigns)})")

        # Refresh Completed Campaigns section
        if hasattr(self, 'completed_campaigns_body'):
            completed_campaigns = self._get_completed_campaigns()
            self._populate_active_campaigns(self.completed_campaigns_body, completed_campaigns, is_completed=True)
            if hasattr(self, '_dash_tab_completed'):
                self._dash_tab_completed.configure(text=f"Completed Campaigns ({len(completed_campaigns)})")

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
            font=FONT_SECTION,
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

        # Mousewheel scrolling (Windows)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        self.active_campaigns_frame = campaigns_frame
        self._refresh_active_campaigns()

    def _refresh_active_campaigns(self):
        """Refresh the active campaigns list"""
        if not hasattr(self, 'active_campaigns_frame'):
            return

        # ANTI-FLICKER: Cache campaigns to avoid unnecessary rebuilds
        active_campaigns = self._get_active_campaigns()
        campaigns_hash = str(len(active_campaigns)) + str([c.get("name", "") for c in active_campaigns])

        if hasattr(self, '_campaigns_cache_hash') and self._campaigns_cache_hash == campaigns_hash:
            return  # No changes, skip rebuild

        self._campaigns_cache_hash = campaigns_hash

        # Clear existing
        for widget in self.active_campaigns_frame.winfo_children():
            widget.destroy()

        # Load active campaigns
        if not active_campaigns:
            empty = make_empty_state(
                self.active_campaigns_frame,
                icon_text="🚀",
                headline="No active campaigns",
                description="Create and launch a campaign to start sending emails automatically.",
                button_text="New Campaign",
                button_command=lambda: self._show_screen("campaign"),
                bg=BG_ENTRY
            )
            empty.pack(fill="both", expand=True)
            return

        # Display each campaign
        for camp in active_campaigns:
            self._create_campaign_widget(self.active_campaigns_frame, camp)

    def _create_campaign_widget(self, parent, campaign):
        """Create a widget displaying one campaign (lighter, less boxy)"""
        # Container with subtle bottom border only (no full box)
        frame = tk.Frame(parent, bg=BG_CARD)
        frame.pack(fill="x", pady=(0, 2), padx=0)

        # Campaign name
        tk.Label(
            frame,
            text=campaign.get("name", "Unnamed Campaign"),
            bg=BG_CARD,
            fg=ACCENT,
            font=FONT_SECTION,
        ).pack(anchor="w", padx=4, pady=(10, 4))

        # Email count and contact count
        emails_count = len(campaign.get("emails", []))
        contact_count = campaign.get("contact_count", 0)

        info_text = f"{emails_count} emails • {contact_count} contacts"
        tk.Label(
            frame,
            text=info_text,
            bg=BG_CARD,
            fg=FG_MUTED,
            font=FONT_SMALL,
        ).pack(anchor="w", padx=4, pady=(0, 4))

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
                    font=FONT_SMALL,
                    wraplength=350,
                    justify="left"
                ).pack(anchor="w", padx=4, pady=(0, 8))

        # Subtle bottom divider (separator line instead of full border)
        divider = tk.Frame(frame, bg=BORDER, height=1)
        divider.pack(fill="x", padx=4, pady=(0, 8))

    def _campaign_is_completed_by_schedule(self, camp: dict) -> bool:
        """
        A campaign is considered completed if:
        - It has emails, and
        - Every email with a date/time is strictly in the past, and
        - If any email is missing a date, treat as NOT completed (still active)
        """
        try:
            emails = camp.get("emails", []) or []
            if not emails:
                return False

            now = datetime.now()

            for e in emails:
                date_str = (e.get("date") or "").strip()
                time_str = (e.get("time") or "").strip()

                # Missing date => not completed (still pending / unscheduled)
                if not date_str:
                    return False

                # Parse scheduled datetime (handle "Immediately")
                try:
                    if time_str.lower().startswith("immed"):
                        scheduled_dt = datetime.strptime(date_str, "%Y-%m-%d")
                    else:
                        dt_str = f"{date_str} {time_str}" if time_str else date_str
                        scheduled_dt = None
                        for fmt in ["%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                            try:
                                scheduled_dt = datetime.strptime(dt_str, fmt)
                                break
                            except ValueError:
                                continue
                        if scheduled_dt is None:
                            scheduled_dt = datetime.strptime(date_str, "%Y-%m-%d")

                    # If ANY email is in the future or now => not completed
                    if scheduled_dt >= now:
                        return False

                except Exception:
                    # If we can't parse, assume not completed
                    return False

            # If we never found an upcoming email, it's completed
            return True

        except Exception:
            return False

    def _get_completed_campaigns(self) -> List[dict]:
        """Get completed campaigns from files, and auto-delete anything older than 7 days."""
        try:
            campaigns: List[dict] = []
            if not CAMPAIGNS_DIR.exists():
                return campaigns

            cutoff = datetime.now() - timedelta(days=7)

            for file in CAMPAIGNS_DIR.glob("*.json"):
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        camp = json.load(f)

                    if camp.get("status") != "completed":
                        continue

                    # Determine completion datetime
                    completed_dt = None

                    completed_raw = (camp.get("completed_date") or "").strip()
                    if completed_raw:
                        try:
                            completed_dt = datetime.strptime(completed_raw, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            completed_dt = None

                    if completed_dt is None:
                        created_raw = (camp.get("created_date") or "").strip()
                        if created_raw:
                            try:
                                completed_dt = datetime.strptime(created_raw, "%Y-%m-%d")
                            except Exception:
                                completed_dt = None

                    # If no usable date, treat as old and remove
                    if completed_dt is None or completed_dt < cutoff:
                        try:
                            file.unlink()
                        except Exception:
                            pass
                        continue

                    # Store file path for later operations
                    camp["_filepath"] = str(file)
                    campaigns.append(camp)

                except Exception:
                    continue

            # Newest first
            campaigns.sort(key=lambda c: c.get("completed_date", c.get("created_date", "")), reverse=True)
            return campaigns

        except Exception:
            return []

    def _get_active_campaigns(self):
        """Get list of active campaigns from files (auto-move completed)."""
        try:
            campaigns = []
            if not CAMPAIGNS_DIR.exists():
                return campaigns

            for file in CAMPAIGNS_DIR.glob("*.json"):
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        camp = json.load(f)

                    # Only consider actives here
                    if camp.get("status") != "active":
                        continue

                    # If it's actually completed by schedule, persist the move
                    if self._campaign_is_completed_by_schedule(camp):
                        camp["status"] = "completed"
                        camp["completed_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        try:
                            with open(file, "w", encoding="utf-8") as wf:
                                json.dump(camp, wf, indent=2)
                        except Exception:
                            pass
                        continue  # do NOT return as active anymore

                    # Still active — store file path for later operations
                    camp["_filepath"] = str(file)
                    campaigns.append(camp)

                except Exception:
                    continue

            campaigns.sort(key=lambda c: c.get("created_date", ""), reverse=True)
            return campaigns
        except Exception:
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
        """Set Schedule screen - shows mode toggle + schedule card"""
        _, content = self._page(parent, "Send Schedule", "Set timing and delivery for each email in your sequence")

        # ── Mode toggle card ──
        toggle_card = ttk.Frame(content, style="Card.TFrame")
        toggle_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        toggle_box = tk.Frame(toggle_card, bg=BG_CARD, highlightbackground=BORDER_MEDIUM,
                              highlightthickness=1, relief="flat")
        toggle_box.pack(fill="x", padx=12, pady=12)

        tk.Label(toggle_box, text="How would you like to schedule your emails?",
                 bg=BG_CARD, fg=FG_TEXT, font=FONT_SECTION).pack(anchor="w", padx=10, pady=(8, 10))

        btn_row = tk.Frame(toggle_box, bg=BG_CARD)
        btn_row.pack(anchor="w", padx=10, pady=(0, 12))

        self._seq_mode_var = tk.StringVar(value="")

        self._seq_mode_days_btn = tk.Button(
            btn_row, text="Days Between Emails",
            command=lambda: self._set_seq_mode("days"),
            bg=BORDER_SOFT, fg=FG_TEXT, activebackground=BG_HOVER,
            activeforeground=ACCENT, relief="flat", font=FONT_BTN_SM,
            padx=16, pady=8, cursor="hand2",
        )
        self._seq_mode_days_btn.pack(side="left", padx=(0, 8))
        ToolTip(self._seq_mode_days_btn,
                "Each email sends X business days after the previous. Best for ongoing outreach.")

        self._seq_mode_dates_btn = tk.Button(
            btn_row, text="Specific Send Dates",
            command=lambda: self._set_seq_mode("dates"),
            bg=BORDER_SOFT, fg=FG_TEXT, activebackground=BG_HOVER,
            activeforeground=ACCENT, relief="flat", font=FONT_BTN_SM,
            padx=16, pady=8, cursor="hand2",
        )
        self._seq_mode_dates_btn.pack(side="left")
        ToolTip(self._seq_mode_dates_btn,
                "Pick exact calendar dates for each email. Best for event-driven campaigns.")

        self._ai_schedule_btn = tk.Button(
            btn_row, text="Ask ChatGPT",
            command=self._run_ai_schedule,
            bg="#3B82F6", fg="#FFFFFF", activebackground="#2563EB",
            activeforeground="#FFFFFF", relief="flat", font=FONT_BTN_SM,
            padx=16, pady=8, cursor="hand2",
        )
        self._ai_schedule_btn.pack(side="left", padx=(8, 0))
        self._ai_schedule_btn.bind("<Enter>", lambda e: self._ai_schedule_btn.config(bg="#2563EB"))
        self._ai_schedule_btn.bind("<Leave>", lambda e: self._ai_schedule_btn.config(bg="#3B82F6"))
        ToolTip(self._ai_schedule_btn,
                "ChatGPT reads your emails and recommends the best send schedule automatically.")

        # ── Schedule table card (mode-dependent content) — hidden until user picks a mode ──
        self._schedule_content_parent = content
        self._build_schedule_card(content, row=1)
        self._build_preset_sequences_card(content, row=2)

        # Hide schedule cards initially — only the toggle box is visible
        self._schedule_card_widget.grid_remove()
        self._preset_card_widget.grid_remove()


    def _build_sequence_tab(self, parent):
        """Build the sequence tab content"""
        wrapper = tk.Frame(parent, bg=BG_ROOT)
        wrapper.pack(fill="both", expand=True, padx=8, pady=8)
        wrapper.columnconfigure(0, weight=1)

        self._build_schedule_card(wrapper, row=0)
        self._build_preset_sequences_card(wrapper, row=1)

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
        """Get list of saved campaign names (saved folder only)."""
        try:
            names = ["-- Start Fresh --"]
            d = self._saved_campaigns_dir()
            if not d.exists():
                return names

            for file in d.glob("*.json"):
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        camp = json.load(f)
                    # Prefer campaign_name field; fallback to filename
                    names.append(camp.get("campaign_name") or camp.get("name") or file.stem)
                except Exception:
                    names.append(file.stem)

            # Remove duplicates while preserving order
            seen = set()
            clean = []
            for n in names:
                if n not in seen:
                    clean.append(n)
                    seen.add(n)
            return clean

        except Exception:
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
            # Reset campaign name to default when starting fresh
            if hasattr(self, 'campaign_name_var'):
                self.campaign_name_var.set("Untitled Campaign")
            # No longer editing system campaign
            self.is_editing_system_campaign = False
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

            # CRITICAL: Clear ALL existing state before loading
            # This prevents duplicate schedule rows
            self._reset_campaign_state()

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

            # Update campaign name field
            if hasattr(self, 'campaign_name_var'):
                self.campaign_name_var.set(campaign.get("name", "Untitled Campaign"))

            # Check if this is the system campaign
            if campaign.get("system_campaign_id") == "default-7-email-campaign":
                self.is_editing_system_campaign = True
            else:
                self.is_editing_system_campaign = False

            try:
                self._set_status(f"Loaded campaign: {name}", GOOD)
            except:
                pass

            self.toast.show(f"Campaign '{name}' loaded", "success")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load campaign:\n{e}")

    def _reset_campaign_state(self):
        """Completely reset all campaign state (emails, tabs, schedule rows)"""
        self._adding_email = True  # Guard against "+" tab auto-select
        # Clear all email tabs
        if hasattr(self, "email_notebook"):
            for tab_id in self.email_notebook.tabs():
                try:
                    self.email_notebook.forget(tab_id)
                except:
                    pass
            # Re-add "+" tab
            if hasattr(self, "_add_tab_frame"):
                self.email_notebook.add(self._add_tab_frame, text="  +  ")
        self._adding_email = False

        # Clear email data lists
        self.name_vars = []
        self.subject_vars = []
        self.body_texts = []
        self.sig_preview_widgets = []
        self.date_vars = []
        self.time_vars = []
        self.per_email_attachments = []

        # CRITICAL: Destroy ALL children of schedule_list_frame to remove orphaned rows
        if hasattr(self, "schedule_list_frame"):
            for child in self.schedule_list_frame.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass

        # Clear schedule rows tracking dict
        if hasattr(self, "schedule_rows"):
            self.schedule_rows.clear()

        # Clear schedule list items
        if hasattr(self, "schedule_list_items"):
            self.schedule_list_items.clear()

    def _auto_load_default_campaign(self):
        """Silently auto-load the default system campaign on startup"""
        try:
            # Find the default system campaign file
            campaign_file = None
            for file in CAMPAIGNS_DIR.glob("*.json"):
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        camp = json.load(f)
                        if camp.get("system_campaign_id") == "default-7-email-campaign":
                            campaign_file = file
                            break
                except:
                    continue

            if not campaign_file:
                # Default campaign doesn't exist (shouldn't happen since we ensure it exists)
                return

            # Load campaign data
            with open(campaign_file, "r", encoding="utf-8") as f:
                campaign = json.load(f)

            # CRITICAL: Clear ALL existing state before loading
            # This prevents duplicate schedule rows
            self._reset_campaign_state()

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

            # Safety: Ensure schedule rows match emails exactly (remove any orphaned rows)
            self._sync_schedule_rows_to_emails()

            # Update campaign name field
            if hasattr(self, 'campaign_name_var'):
                self.campaign_name_var.set(campaign.get("name", "Default 7 Email Campaign"))

            # Mark that we're editing the system campaign
            self.is_editing_system_campaign = True

            # Silent status update (no message box)
            try:
                self._set_status("Default campaign loaded", GOOD)
            except:
                pass

        except Exception as e:
            # Silent failure - just log it
            print(f"Failed to auto-load default campaign: {e}")

    def _save_current_campaign(self):
        """Save the current campaign"""
        # Ask for campaign name
        name = themed_askstring(self, "Save Campaign", "Enter a name for this campaign:")

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

            self.toast.show(f"Campaign '{name}' saved", "success")

            # Refresh campaign page dropdown
            try:
                self._refresh_campaign_page()
            except Exception:
                pass

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

    def _save_campaign_to_dashboard(self, name: str, schedule: list, contacts_path: str):
        """Save campaign to dashboard as an active campaign (in-memory tracking only)."""
        try:
            # Count contacts and collect their emails for response validation
            contact_count = 0
            contact_emails = []
            try:
                rows, _ = safe_read_csv_rows(contacts_path)
                contact_count = len(rows)
                for row in rows:
                    email = (row.get("email") or row.get("Email") or "").strip()
                    if email:
                        contact_emails.append(email.lower())
            except:
                pass

            # Collect delay pattern from current session
            delay_pattern = []
            n = len(self.delay_vars) if hasattr(self, "delay_vars") else 0
            for i in range(len(schedule)):
                if i < n:
                    try:
                        delay_pattern.append(int(self.delay_vars[i].get()))
                    except (ValueError, AttributeError):
                        delay_pattern.append(0 if i == 0 else 2)
                else:
                    delay_pattern.append(0 if i == 0 else 2)

            # Build campaign data (includes full email content for reload)
            campaign_data = {
                "name": name,
                "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active",
                "contact_count": contact_count,
                "contact_emails": contact_emails,
                "email_count": len(schedule),
                "delay_pattern": delay_pattern,
                "emails": []
            }

            # Add email schedule info with full content
            for i, email in enumerate(schedule):
                email_name = ""
                if hasattr(self, "name_vars") and i < len(self.name_vars):
                    email_name = (self.name_vars[i].get() or "").strip()
                if not email_name:
                    email_name = f"Email {i + 1}"

                campaign_data["emails"].append({
                    "name": email_name,
                    "subject": email.get("subject", ""),
                    "body": email.get("body", ""),
                    "date": email.get("date", ""),
                    "time": email.get("time", ""),
                    "attachments": email.get("attachments", []),
                })

            # Save to campaigns directory
            safe_name = self._sanitize_filename(name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_name}_{timestamp}.json"
            filepath = CAMPAIGNS_DIR / filename

            CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(campaign_data, f, indent=2)

        except Exception as e:
            # Non-fatal - just log it
            print(f"Failed to save campaign to dashboard: {e}")

    # ============================================
    # Campaign state management (save/load full campaign)
    # ============================================
    def _campaigns_dir(self) -> Path:
        """Get campaigns directory path"""
        base = Path(os.getenv("LOCALAPPDATA", str(Path.cwd())))
        d = base / "Funnel Forge" / "campaigns"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize campaign name for use as filename"""
        name = (name or "").strip()
        if not name:
            return "campaign"
        name = re.sub(r"[^\w\- ]+", "", name)
        name = re.sub(r"\s+", "_", name).strip("_")
        return name[:60] if len(name) > 60 else name

    def _saved_campaigns_dir(self) -> Path:
        """
        Directory for user-saved campaigns only.
        Keeps things clean and prevents runtime/active clutter.
        """
        d = CAMPAIGNS_DIR / "saved"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _campaign_path_for_name(self, campaign_name: str) -> Path:
        """
        Clean filename: <Campaign Name>.json (no timestamps, no counters).
        """
        safe = self._sanitize_filename(campaign_name).replace("_", " ").strip()
        if not safe:
            safe = "Campaign"
        return self._saved_campaigns_dir() / f"{safe}.json"

    # ============================================
    # Stay Connected - Data helpers
    # ============================================
    def _stay_connected_dir(self) -> Path:
        """Directory for Stay Connected data."""
        d = USER_DIR / "stay_connected"
        (d / "categories").mkdir(parents=True, exist_ok=True)
        return d

    def _stay_index_path(self) -> Path:
        """Path to Stay Connected index file."""
        return self._stay_connected_dir() / "index.json"

    def _load_stay_index(self) -> dict:
        """Load Stay Connected index."""
        path = self._stay_index_path()
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"categories": []}

    def _save_stay_index(self, data: dict) -> None:
        """Save Stay Connected index."""
        with self._stay_index_path().open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _stay_slug(self, name: str) -> str:
        """Create a slug from category name."""
        return re.sub(r"[^\w]+", "_", name.strip().lower()).strip("_")

    def _stay_category_name_exists(self, name: str, exclude_id: str = None) -> bool:
        """Check if category name already exists (case-insensitive)."""
        name = name.strip().lower()
        idx = self._load_stay_index()
        for c in idx["categories"]:
            if exclude_id and c["id"] == exclude_id:
                continue
            if c["name"].strip().lower() == name:
                return True
        return False

    def _create_stay_category(self, name: str) -> str:
        """Create a new Stay Connected category. Returns category ID."""
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        if self._stay_category_name_exists(name):
            raise ValueError("Category already exists")

        cid = self._stay_slug(name)
        # Handle slug collisions by appending number
        base_cid = cid
        counter = 1
        idx = self._load_stay_index()
        existing_ids = {c["id"] for c in idx["categories"]}
        while cid in existing_ids:
            cid = f"{base_cid}_{counter}"
            counter += 1

        idx["categories"].append({"id": cid, "name": name})
        self._save_stay_index(idx)

        path = self._stay_connected_dir() / "categories" / f"{cid}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump({
                "id": cid,
                "name": name,
                "paused": False,
                "template": {"subject": "", "body": ""},
                "contacts": []
            }, f, indent=2)

        return cid

    def _rename_stay_category(self, cid: str, new_name: str) -> None:
        """Rename an existing Stay Connected category."""
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Category name cannot be empty")
        if self._stay_category_name_exists(new_name, exclude_id=cid):
            raise ValueError("Category already exists")

        idx = self._load_stay_index()
        for c in idx["categories"]:
            if c["id"] == cid:
                c["name"] = new_name
                break
        self._save_stay_index(idx)

        # Update category file
        path = self._stay_connected_dir() / "categories" / f"{cid}.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                cat = json.load(f)
            cat["name"] = new_name
            with path.open("w", encoding="utf-8") as f:
                json.dump(cat, f, indent=2)

    def _delete_stay_category(self, cid: str) -> None:
        """Delete a Stay Connected category."""
        idx = self._load_stay_index()
        idx["categories"] = [c for c in idx["categories"] if c["id"] != cid]
        self._save_stay_index(idx)

        path = self._stay_connected_dir() / "categories" / f"{cid}.json"
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    def _load_stay_category(self, cid: str) -> dict:
        """Load a Stay Connected category by ID."""
        path = self._stay_connected_dir() / "categories" / f"{cid}.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _save_stay_category(self, cid: str, data: dict) -> None:
        """Save a Stay Connected category."""
        path = self._stay_connected_dir() / "categories" / f"{cid}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _add_contacts_to_stay_category(self, cid: str, contacts: list) -> int:
        """Add contacts to a Stay Connected category. Returns count added."""
        path = self._stay_connected_dir() / "categories" / f"{cid}.json"
        with path.open("r", encoding="utf-8") as f:
            cat = json.load(f)

        existing = {c["email_key"] for c in cat["contacts"]}
        added = 0

        for row in contacts:
            email = (row.get("Work Email") or row.get("Email") or "").strip().lower()
            if not email or email in existing:
                continue

            cat["contacts"].append({
                "email_key": email,
                "data": row
            })
            existing.add(email)
            added += 1

        with path.open("w", encoding="utf-8") as f:
            json.dump(cat, f, indent=2)

        return added

    # ============================================
    # Nurture Lists - Data helpers
    # ============================================
    def _nurture_campaigns_dir(self) -> Path:
        """Directory for Nurture Lists data."""
        d = USER_DIR / "nurture_campaigns"
        (d / "campaigns").mkdir(parents=True, exist_ok=True)
        return d

    def _nurture_index_path(self) -> Path:
        """Path to Nurture Lists index file."""
        return self._nurture_campaigns_dir() / "index.json"

    def _load_nurture_index(self) -> dict:
        """Load Nurture Lists index."""
        path = self._nurture_index_path()
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"campaigns": []}

    def _save_nurture_index(self, data: dict) -> None:
        """Save Nurture Lists index."""
        with self._nurture_index_path().open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _nurture_slug(self, name: str) -> str:
        """Create a slug from campaign name."""
        return re.sub(r"[^\w]+", "_", name.strip().lower()).strip("_")

    def _nurture_campaign_name_exists(self, name: str, exclude_id: str = None) -> bool:
        """Check if campaign name already exists (case-insensitive)."""
        name = name.strip().lower()
        idx = self._load_nurture_index()
        for c in idx["campaigns"]:
            if exclude_id and c["id"] == exclude_id:
                continue
            if c["name"].strip().lower() == name:
                return True
        return False

    def _create_nurture_campaign(self, name: str) -> str:
        """Create a new Nurture List. Returns campaign ID."""
        name = name.strip()
        if not name:
            raise ValueError("Campaign name cannot be empty")
        if self._nurture_campaign_name_exists(name):
            raise ValueError("Campaign already exists")

        cid = self._nurture_slug(name)
        # Handle slug collisions by appending number
        base_cid = cid
        counter = 1
        idx = self._load_nurture_index()
        existing_ids = {c["id"] for c in idx["campaigns"]}
        while cid in existing_ids:
            cid = f"{base_cid}_{counter}"
            counter += 1

        idx["campaigns"].append({"id": cid, "name": name})
        self._save_nurture_index(idx)

        # Default message templates (semantic names, not "Email 1")
        default_messages = [
            {
                "id": "msg_1",
                "name": "Check-in",
                "subject": "Just checking in, {FirstName}",
                "body": "Hi {FirstName},\n\nJust wanted to check in and see how things are going.\n\nLet me know if you'd like to catch up.\n\n{Signature}",
            },
            {
                "id": "msg_2",
                "name": "Value Add",
                "subject": "Thought you'd find this useful",
                "body": "Hi {FirstName},\n\nI came across something I thought might be useful for you.\n\n[Add your value here]\n\nLet me know if you'd like to discuss.\n\n{Signature}",
            },
            {
                "id": "msg_3",
                "name": "Market Update",
                "subject": "Quick market update",
                "body": "Hi {FirstName},\n\nWanted to share a quick update on the market.\n\n[Add market insights here]\n\nHappy to discuss if you're interested.\n\n{Signature}",
            },
            {
                "id": "msg_4",
                "name": "Re-engagement",
                "subject": "It's been a while, {FirstName}",
                "body": "Hi {FirstName},\n\nIt's been a while since we last connected. I wanted to reach out and see how you're doing.\n\nWould love to catch up when you have time.\n\n{Signature}",
            },
        ]

        path = self._nurture_campaigns_dir() / "campaigns" / f"{cid}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump({
                "id": cid,
                "name": name,
                "messages": default_messages,
                "contacts": [],
            }, f, indent=2)

        # Refresh Stay Connected nurture list
        if hasattr(self, '_refresh_stay_nurture_list'):
            try:
                self._refresh_stay_nurture_list()
            except Exception:
                pass

        return cid

    def _rename_nurture_campaign(self, cid: str, new_name: str) -> None:
        """Rename an existing Nurture List."""
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Campaign name cannot be empty")
        if self._nurture_campaign_name_exists(new_name, exclude_id=cid):
            raise ValueError("Campaign already exists")

        idx = self._load_nurture_index()
        for c in idx["campaigns"]:
            if c["id"] == cid:
                c["name"] = new_name
                break
        self._save_nurture_index(idx)

        # Update campaign file
        path = self._nurture_campaigns_dir() / "campaigns" / f"{cid}.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                camp = json.load(f)
            camp["name"] = new_name
            with path.open("w", encoding="utf-8") as f:
                json.dump(camp, f, indent=2)

    def _delete_nurture_campaign(self, cid: str) -> None:
        """Delete a Nurture List."""
        idx = self._load_nurture_index()
        idx["campaigns"] = [c for c in idx["campaigns"] if c["id"] != cid]
        self._save_nurture_index(idx)

        path = self._nurture_campaigns_dir() / "campaigns" / f"{cid}.json"
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    def _load_nurture_campaign(self, cid: str) -> dict:
        """Load a Nurture List by ID."""
        path = self._nurture_campaigns_dir() / "campaigns" / f"{cid}.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _save_nurture_campaign(self, cid: str, data: dict) -> None:
        """Save a Nurture List."""
        path = self._nurture_campaigns_dir() / "campaigns" / f"{cid}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _add_contacts_to_nurture_campaign(self, cid: str, contacts: list) -> int:
        """Add contacts to a Nurture List. Returns count added."""
        path = self._nurture_campaigns_dir() / "campaigns" / f"{cid}.json"
        with path.open("r", encoding="utf-8") as f:
            camp = json.load(f)

        existing = {c["email_key"] for c in camp["contacts"]}
        added = 0

        for row in contacts:
            email = (row.get("Work Email") or row.get("Email") or "").strip().lower()
            if not email or email in existing:
                continue

            camp["contacts"].append({
                "email_key": email,
                "data": row
            })
            existing.add(email)
            added += 1

        with path.open("w", encoding="utf-8") as f:
            json.dump(camp, f, indent=2)

        # Refresh Stay Connected nurture list
        if hasattr(self, '_refresh_stay_nurture_list'):
            try:
                self._refresh_stay_nurture_list()
            except Exception:
                pass

        return added

    # ============================================
    # Pending Nurture Assignment (on campaign complete)
    # ============================================
    def _pending_nurture_path(self) -> Path:
        """Path to pending nurture assignment file."""
        return USER_DIR / "pending_nurture_assignment.json"

    def _load_pending_nurture(self) -> dict:
        """Load pending nurture assignment."""
        path = self._pending_nurture_path()
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _save_pending_nurture(self, nurture_campaign_id: str, nurture_campaign_name: str):
        """Save pending nurture assignment. Contacts will be added when campaign completes."""
        data = {
            "nurture_campaign_id": nurture_campaign_id,
            "nurture_campaign_name": nurture_campaign_name,
            "enabled": True,
            "created_at": datetime.now().isoformat()
        }
        with self._pending_nurture_path().open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _clear_pending_nurture(self):
        """Clear pending nurture assignment after processing."""
        path = self._pending_nurture_path()
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    def _get_campaign_completion_date(self) -> str:
        """Get the date of the last scheduled email in the current campaign.

        Reads from persisted config file (funnelforge_config.json).
        Call _save_all() before this to ensure UI state is persisted.
        """
        try:
            # Read from persisted config
            config = load_config()
            emails = config.get("emails", [])
            if not emails:
                return None

            # Find the latest date
            latest_date = None
            for i, email in enumerate(emails):
                date_str = email.get("date", "").strip()
                if date_str:
                    try:
                        date = datetime.strptime(date_str, "%Y-%m-%d")
                        if latest_date is None or date > latest_date:
                            latest_date = date
                    except ValueError:
                        # Debug: log which email has invalid date
                        print(f"DEBUG: Invalid date format in email {i+1}: '{date_str}'")
                else:
                    # Debug: log which email is missing date
                    email_name = email.get("name", f"Email {i+1}")
                    print(f"DEBUG: Missing schedule date for '{email_name}' (index {i})")

            return latest_date.strftime("%Y-%m-%d") if latest_date else None
        except Exception as e:
            print(f"DEBUG: _get_campaign_completion_date error: {e}")
            return None

    def _process_pending_nurture_assignment(self):
        """Process pending nurture assignment if campaign is complete."""
        pending = self._load_pending_nurture()
        if not pending or not pending.get("enabled"):
            return

        # Calculate completion date at processing time
        completion_date_str = self._get_campaign_completion_date()
        if not completion_date_str:
            # No schedule yet - don't process, keep pending
            return

        try:
            completion_date = datetime.strptime(completion_date_str, "%Y-%m-%d")
            # Add 1 day buffer - consider complete after the completion date
            if datetime.now() < completion_date + timedelta(days=1):
                # Not yet complete - don't process
                return
        except ValueError:
            return

        # Campaign is complete - transfer contacts
        nurture_id = pending.get("nurture_campaign_id")
        nurture_name = pending.get("nurture_campaign_name", "Nurture List")
        contacts = self._get_current_campaign_contacts()  # Get contacts at processing time

        if nurture_id and contacts:
            # Add contacts with duplicate protection (built into _add_contacts_to_nurture_campaign)
            added = self._add_contacts_to_nurture_campaign(nurture_id, contacts)

            # Show toast notification
            self._show_nurture_transfer_toast(nurture_id, nurture_name, added)

        self._clear_pending_nurture()

    def _show_nurture_transfer_toast(self, nurture_id: str, nurture_name: str, contact_count: int):
        """Show toast notification after contacts are transferred to nurture list."""
        message = f"{contact_count} contacts added to \"{nurture_name}\""

        def on_view():
            # Navigate to Nurture Lists screen and select this campaign
            self._navigate_to_nurture_campaign(nurture_id)

        def on_undo():
            # Remove contacts from the nurture list
            self._undo_nurture_transfer(nurture_id, contact_count)

        ToastNotification(self, message, on_view=on_view, on_undo=on_undo)

    def _navigate_to_nurture_campaign(self, nurture_id: str):
        """Navigate to Nurture Lists screen and select the specified campaign."""
        # Switch to nurture lists screen
        self._show_screen("nurture_campaigns")

        # Select the campaign in the listbox
        idx = self._load_nurture_index()
        campaigns = idx.get("campaigns", [])
        for i, c in enumerate(campaigns):
            if c["id"] == nurture_id:
                self._nurture_campaign_listbox.selection_clear(0, "end")
                self._nurture_campaign_listbox.selection_set(i)
                self._nurture_campaign_listbox.see(i)
                self._nurture_selected_campaign_id = nurture_id
                self._nurture_show_content()
                break

    def _undo_nurture_transfer(self, nurture_id: str, contact_count: int):
        """Remove recently added contacts from nurture list."""
        camp = self._load_nurture_campaign(nurture_id)
        if not camp:
            return

        contacts = camp.get("contacts", [])
        if len(contacts) >= contact_count:
            # Remove the last N contacts (the ones just added)
            camp["contacts"] = contacts[:-contact_count]
            self._save_nurture_campaign(nurture_id, camp)
            self._set_status(f"Removed {contact_count} contacts from nurture list", GOOD)

    def _refresh_nurture_status(self):
        """Update the nurture status label based on current selection."""
        if not hasattr(self, '_nurture_status_label'):
            return

        if hasattr(self, '_nurture_enabled_var') and self._nurture_enabled_var.get():
            name = self._nurture_dropdown_var.get() if hasattr(self, '_nurture_dropdown_var') else ""
            if name:
                contact_count = self._count_contacts()
                self._nurture_status_label.configure(
                    text=f"{contact_count} contacts will be added to \"{name}\" after completion",
                    fg=GOOD
                )
                return

        # Default: not enabled
        self._nurture_status_label.configure(text="", fg=FG_MUTED)

    def _refresh_nurture_dropdown(self):
        """Populate the nurture list dropdown."""
        if not hasattr(self, '_nurture_dropdown'):
            return

        idx = self._load_nurture_index()
        campaigns = idx.get("campaigns", [])
        names = [c["name"] for c in campaigns]

        self._nurture_dropdown['values'] = names
        if names and not self._nurture_dropdown_var.get():
            self._nurture_dropdown_var.set(names[0])

    def _restore_nurture_selection(self):
        """Restore nurture selection from saved pending state."""
        pending = self._load_pending_nurture()
        if pending and pending.get("enabled"):
            # Restore checkbox state
            if hasattr(self, '_nurture_enabled_var'):
                self._nurture_enabled_var.set(True)
                self._nurture_dropdown.configure(state="readonly")
                self._nurture_new_btn.configure(state="normal")

            # Restore dropdown selection
            name = pending.get("nurture_campaign_name", "")
            if name and hasattr(self, '_nurture_dropdown_var'):
                self._nurture_dropdown_var.set(name)

            self._refresh_nurture_status()

    def _on_nurture_checkbox_changed(self):
        """Handle nurture checkbox toggle."""
        enabled = self._nurture_enabled_var.get()

        if enabled:
            self._nurture_dropdown.configure(state="readonly")
            self._nurture_new_btn.configure(state="normal")
            self._refresh_nurture_dropdown()

            # Save selection if dropdown has a value
            selected = self._nurture_dropdown_var.get()
            if selected:
                self._save_nurture_selection(selected)
        else:
            self._nurture_dropdown.configure(state="disabled")
            self._nurture_new_btn.configure(state="disabled")
            self._clear_pending_nurture()

        self._refresh_nurture_status()

    def _on_nurture_dropdown_changed(self, event=None):
        """Handle nurture dropdown selection change."""
        if not self._nurture_enabled_var.get():
            return

        selected = self._nurture_dropdown_var.get()
        if selected:
            self._save_nurture_selection(selected)
            self._refresh_nurture_status()

    def _save_nurture_selection(self, campaign_name: str):
        """Save the nurture list selection."""
        idx = self._load_nurture_index()
        campaigns = idx.get("campaigns", [])

        for c in campaigns:
            if c["name"] == campaign_name:
                self._save_pending_nurture(c["id"], campaign_name)
                return

    def _create_nurture_from_launch(self):
        """Create a new nurture list from the launch screen."""
        name = themed_askstring(self, "New Nurture List", "Campaign name:")
        if not name or not name.strip():
            return

        try:
            cid = self._create_nurture_campaign(name.strip())
            self._refresh_nurture_dropdown()
            self._nurture_dropdown_var.set(name.strip())
            self._save_pending_nurture(cid, name.strip())
            self._refresh_nurture_status()
            self._set_status(f"Nurture campaign '{name}' created", GOOD)
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def _get_current_campaign_contacts(self) -> List[Dict[str, str]]:
        """Get the contacts used for the current campaign (from official contacts)."""
        rows, _ = safe_read_csv_rows(OFFICIAL_CONTACTS_PATH)
        return rows

    def _show_stay_connected_modal(self):
        """Show modal to add campaign contacts to a Stay Connected category."""
        # Get categories
        idx = self._load_stay_index()
        categories = idx.get("categories", [])

        # Build modal
        modal = tk.Toplevel(self)
        modal.title("Add to Stay Connected")
        modal.transient(self)
        modal.grab_set()
        modal.configure(bg=BG_CARD)
        modal.resizable(False, False)

        # Center on parent
        modal.geometry("400x280")
        modal.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (modal.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (modal.winfo_height() // 2)
        modal.geometry(f"+{x}+{y}")

        content = tk.Frame(modal, bg=BG_CARD)
        content.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(
            content,
            text="Add contacts to category",
            bg=BG_CARD,
            fg=ACCENT,
            font=FONT_TITLE,
        ).pack(anchor="w", pady=(0, 16))

        # Existing category dropdown
        tk.Label(
            content,
            text="Choose existing category:",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_BASE,
        ).pack(anchor="w", pady=(0, 4))

        category_var = tk.StringVar()
        category_names = [c["name"] for c in categories]
        if category_names:
            category_var.set(category_names[0])

        category_dropdown = ttk.Combobox(
            content,
            textvariable=category_var,
            values=category_names,
            state="readonly" if category_names else "disabled",
            style="Dark.TCombobox",
        )
        category_dropdown.pack(fill="x", pady=(0, 12))

        # Or create new
        tk.Label(
            content,
            text="Or create new category:",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_BASE,
        ).pack(anchor="w", pady=(0, 4))

        new_cat_var = tk.StringVar()
        new_cat_entry = tk.Entry(
            content,
            textvariable=new_cat_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            font=FONT_BASE,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        new_cat_entry.pack(fill="x", ipady=6, pady=(0, 20))

        # Buttons
        btn_frame = tk.Frame(content, bg=BG_CARD)
        btn_frame.pack(fill="x")

        def _do_add():
            new_name = new_cat_var.get().strip()
            selected = category_var.get()

            # Determine target category
            target_cid = None

            if new_name:
                # Create new category
                try:
                    target_cid = self._create_stay_category(new_name)
                except ValueError as e:
                    messagebox.showerror("Error", str(e), parent=modal)
                    return
            elif selected:
                # Find existing category ID
                for c in categories:
                    if c["name"] == selected:
                        target_cid = c["id"]
                        break

            if not target_cid:
                messagebox.showwarning("No Selection", "Please select or create a category.", parent=modal)
                return

            # Get contacts and add them
            contacts = self._get_current_campaign_contacts()
            added = self._add_contacts_to_stay_category(target_cid, contacts)

            modal.destroy()

            # Refresh Stay Connected if open
            if hasattr(self, '_refresh_stay_connected'):
                try:
                    self._refresh_stay_connected()
                    # If the category is currently selected, refresh its view
                    if hasattr(self, '_stay_selected_category_id') and self._stay_selected_category_id == target_cid:
                        self._on_stay_category_selected()
                except Exception:
                    pass

            cat_name = new_name if new_name else selected
            self.toast.show(f"{added} contacts added to '{cat_name}'", "success")

        tk.Button(
            btn_frame,
            text="Add Contacts",
            command=_do_add,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=16,
            pady=8,
        ).pack(side="left")

        tk.Button(
            btn_frame,
            text="Cancel",
            command=modal.destroy,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            cursor="hand2",
            padx=16,
            pady=8,
        ).pack(side="left", padx=(8, 0))

        modal.wait_window()

    def _get_campaign_name_for_save(self) -> str:
        """Get campaign name from user or existing variable"""
        # Try to use existing campaign name variable if available
        existing = ""
        if hasattr(self, "campaign_name_var"):
            try:
                existing = (self.campaign_name_var.get() or "").strip()
            except Exception:
                existing = ""

        name = existing
        if not name:
            name = themed_askstring(self, "Campaign Name", "Enter a name for this campaign:")
            if not name:
                raise ValueError("Campaign name is required to save.")
            if hasattr(self, "campaign_name_var"):
                try:
                    self.campaign_name_var.set(name.strip())
                except Exception:
                    pass
        return name.strip()

    def _collect_campaign_state(self) -> dict:
        """Collect FULL campaign state from current GUI"""
        n = len(self.subject_vars) if hasattr(self, "subject_vars") else 0

        emails = []
        for i in range(n):
            # Name/tab label
            email_name = ""
            if hasattr(self, "name_vars") and i < len(self.name_vars):
                email_name = (self.name_vars[i].get() or "").strip()
            else:
                email_name = f"Email {i+1}"

            # Subject
            subject = ""
            if hasattr(self, "subject_vars") and i < len(self.subject_vars):
                subject = (self.subject_vars[i].get() or "").strip()

            # Body (Text widget list) — use HTML if formatting exists
            body = ""
            if hasattr(self, "body_texts") and i < len(self.body_texts):
                try:
                    body = text_to_html(self.body_texts[i]) or self.body_texts[i].get("1.0", "end").rstrip()
                except Exception:
                    body = ""

            # Date/time vars
            date = ""
            time = ""
            if hasattr(self, "date_vars") and i < len(self.date_vars):
                date = (self.date_vars[i].get() or "").strip()
            if hasattr(self, "time_vars") and i < len(self.time_vars):
                time = (self.time_vars[i].get() or "").strip()

            # Attachments per email
            attachments = []
            if hasattr(self, "per_email_attachments") and i < len(self.per_email_attachments):
                try:
                    attachments = list(self.per_email_attachments[i] or [])
                except Exception:
                    attachments = []

            emails.append({
                "name": email_name,
                "subject": subject,
                "body": body,
                "date": date,
                "time": time,
                "attachments": attachments,
            })

        campaign_name = ""
        if hasattr(self, "campaign_name_var"):
            try:
                campaign_name = (self.campaign_name_var.get() or "").strip()
            except Exception:
                campaign_name = ""

        # Collect delay pattern from current session
        delay_pattern = []
        for i in range(n):
            if hasattr(self, "delay_vars") and i < len(self.delay_vars):
                try:
                    delay_pattern.append(int(self.delay_vars[i].get()))
                except (ValueError, AttributeError):
                    delay_pattern.append(0 if i == 0 else 2)
            else:
                delay_pattern.append(0 if i == 0 else 2)

        return {
            "schema": 2,
            "campaign_name": campaign_name,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "delay_pattern": delay_pattern,
            "schedule_settings": {
                "schedule_mode": self.schedule_mode_var.get() if hasattr(self, "schedule_mode_var") else "fixed",
                "skip_weekends": self.relative_skip_weekends_var.get() if hasattr(self, "relative_skip_weekends_var") else True,
                "send_time": self.relative_window_start_var.get() if hasattr(self, "relative_window_start_var") else "09:00",
            },
            "emails": emails,
        }

    def _apply_campaign_state(self, data: dict) -> None:
        """Apply FULL campaign state to GUI"""
        emails = data.get("emails") or []
        if not isinstance(emails, list):
            raise ValueError("Invalid campaign file: 'emails' must be a list.")

        # Set campaign name if available
        name = (data.get("campaign_name") or "").strip()
        if name and hasattr(self, "campaign_name_var"):
            try:
                self.campaign_name_var.set(name)
            except Exception:
                pass

        # Check if this is the system campaign
        if data.get("system_campaign_id") == "default-7-email-campaign":
            self.is_editing_system_campaign = True
        else:
            self.is_editing_system_campaign = False

        # CRITICAL: Clear ALL existing state before loading
        # This prevents duplicate schedule rows
        self._reset_campaign_state()

        # Suspend rebuild jitter
        if hasattr(self, "_suspend_rebuilds"):
            self._suspend_rebuilds = True

        try:
            # Create emails using existing _add_email method
            for i, e in enumerate(emails):
                nm = (e.get("name") or f"Email {i+1}").strip()
                subj = (e.get("subject") or "").strip()
                body = (e.get("body") or "")
                date = (e.get("date") or "").strip()
                time = (e.get("time") or "9:00 AM").strip()
                atts = e.get("attachments") or []

                # Add email (this creates the tab and widgets)
                self._add_email(
                    name=nm,
                    subject=subj,
                    body=body,
                    date=date,
                    time=time
                )

                # Set attachments for this email
                if i < len(self.per_email_attachments):
                    self.per_email_attachments[i] = list(atts)

        finally:
            if hasattr(self, "_suspend_rebuilds"):
                self._suspend_rebuilds = False

        # Refresh UI once
        if hasattr(self, "_rebuild_sequence_table"):
            try:
                self._rebuild_sequence_table()
            except Exception:
                pass
        # Schedule rows are now created incrementally by _add_email() -> _schedule_add_row()
        # No need to rebuild schedule panel here
        if hasattr(self, "_refresh_tab_labels"):
            try:
                self._refresh_tab_labels()
            except Exception:
                pass

        # Safety: Ensure schedule rows match emails exactly (remove any orphaned rows)
        if hasattr(self, "_sync_schedule_rows_to_emails"):
            try:
                self._sync_schedule_rows_to_emails()
            except Exception:
                pass

        # Restore delay pattern (for sequence preservation on reload)
        delay_pattern = data.get("delay_pattern")
        if delay_pattern and isinstance(delay_pattern, list):
            # Explicit pattern stored in campaign file
            self._ensure_delay_vars_len()
            for i, d in enumerate(delay_pattern):
                if i < len(self.delay_vars):
                    self.delay_vars[i].set(str(d))
        else:
            # Legacy: compute pattern from stored dates
            date_strings = [e.get("date", "") for e in emails]
            if any(d.strip() for d in date_strings):
                computed = self._compute_delays_from_dates(date_strings)
                self._ensure_delay_vars_len()
                for i, d in enumerate(computed):
                    if i < len(self.delay_vars):
                        self.delay_vars[i].set(str(d))

        # Restore schedule settings if present
        settings = data.get("schedule_settings") or {}
        if settings:
            if "schedule_mode" in settings and hasattr(self, "schedule_mode_var"):
                self.schedule_mode_var.set(settings["schedule_mode"])
            if "skip_weekends" in settings and hasattr(self, "relative_skip_weekends_var"):
                self.relative_skip_weekends_var.set(settings["skip_weekends"])
            if "send_time" in settings and hasattr(self, "relative_window_start_var"):
                self.relative_window_start_var.set(settings["send_time"])

    def _save_campaign(self) -> None:
        """Save current campaign state to a clean, human-readable file name."""
        try:
            name = self._get_campaign_name_for_save()
            state = self._collect_campaign_state()
            state["campaign_name"] = name

            # Preserve system campaign markers if applicable
            is_system = getattr(self, "is_editing_system_campaign", False)
            if is_system and (state.get("system_campaign_id") == "default-7-email-campaign" or name == "Default 7 Email Campaign"):
                state["is_system_campaign"] = True
                state["system_campaign_id"] = "default-7-email-campaign"

            path = self._campaign_path_for_name(name)

            # Overwrite confirmation (NO auto-numbering)
            if path.exists():
                ok = messagebox.askyesno(
                    "Overwrite campaign?",
                    f"A saved campaign named:\n\n{name}\n\nalready exists.\nOverwrite it?"
                )
                if not ok:
                    self._set_status("Save cancelled", WARN)
                    return

            with path.open("w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            try:
                self._set_status(f"Campaign saved: {name}", GOOD)
            except Exception:
                pass

            # Refresh campaign page dropdown
            try:
                self._refresh_campaign_page()
            except Exception:
                pass

            try:
                if hasattr(self, "refresh_dashboard"):
                    self.after(0, self.refresh_dashboard)
            except Exception:
                pass

            messagebox.showinfo("Saved", f"Campaign saved:\n{path}")

        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _open_campaign(self) -> None:
        """Open and load a saved campaign (saved campaigns only)."""
        try:
            initial = str(self._saved_campaigns_dir())
            path = filedialog.askopenfilename(
                title="Open Campaign",
                initialdir=initial,
                filetypes=[("Campaign JSON", "*.json"), ("All files", "*.*")]
            )
            if not path:
                return

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._apply_campaign_state(data)

            try:
                self._set_status(f"Campaign loaded: {Path(path).name}", GOOD)
            except Exception:
                pass

            messagebox.showinfo("Loaded", f"Campaign loaded:\n{path}")

        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def _refresh_campaign_dropdown(self):
        """Populate the campaign dropdown with saved campaigns."""
        try:
            campaigns_dir = self._saved_campaigns_dir()
            campaign_files = list(campaigns_dir.glob("*.json"))

            # Get campaign names from files
            campaign_names = []
            for f in campaign_files:
                try:
                    with f.open("r", encoding="utf-8") as file:
                        data = json.load(file)
                        name = data.get("name", f.stem)
                        campaign_names.append(name)
                except:
                    campaign_names.append(f.stem)

            # Sort alphabetically
            campaign_names.sort()

            # Update dropdown values
            if hasattr(self, '_campaign_dropdown'):
                self._campaign_dropdown['values'] = campaign_names

        except Exception:
            pass

    def _on_campaign_dropdown_select(self, event=None):
        """Load the selected campaign from the dropdown."""
        try:
            selected_name = self.campaign_name_var.get()
            if not selected_name:
                return

            # Find the campaign file
            campaigns_dir = self._saved_campaigns_dir()
            campaign_file = campaigns_dir / f"{selected_name}.json"

            if campaign_file.exists():
                with campaign_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                self._apply_campaign_state(data)
                self._set_status(f"Campaign loaded: {selected_name}", GOOD)
            else:
                # Try to find by matching name in file contents
                for f in campaigns_dir.glob("*.json"):
                    try:
                        with f.open("r", encoding="utf-8") as file:
                            data = json.load(file)
                            if data.get("name") == selected_name:
                                self._apply_campaign_state(data)
                                self._set_status(f"Campaign loaded: {selected_name}", GOOD)
                                return
                    except:
                        continue

        except Exception as e:
            self._set_status(f"Failed to load campaign", DANGER)

    # ============================================
    # Contacts-only screen (Choose contact list)
    # ============================================
    def _build_contacts_only_screen(self, parent):
        """Choose contact list screen - table-first design"""
        _, content = self._page(parent, "Choose Contacts", "Import or manage the contact list for this campaign")

        # Controls row (no box)
        controls = tk.Frame(content, bg=BG_ROOT)
        controls.pack(fill="x", pady=(0, 12))

        tk.Label(
            controls,
            text="Active list:",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=FONT_LABEL,
        ).pack(side="left", padx=(0, 8))

        # Dropdown for selecting contact lists
        self.contact_list_selector_combo = ttk.Combobox(
            controls,
            textvariable=self.selected_contact_list_var,
            state="readonly",
            style="Dark.TCombobox",
            font=FONT_BASE,
            width=40,
        )
        self.contact_list_selector_combo.pack(side="left", padx=(0, 16))
        self.contact_list_selector_combo.bind("<<ComboboxSelected>>", lambda e: self._on_contact_list_selected())

        # Import button (primary)
        make_button(
            controls, text="Import New List",
            command=self._import_new_contact_list,
            variant="primary",
        ).pack(side="left")

        # Add Contact button
        make_button(
            controls, text="Add Contact",
            command=self._add_new_contact_to_list,
            variant="secondary",
        ).pack(side="left", padx=(8, 0))

        # Delete Contact button
        make_button(
            controls, text="Delete Contact",
            command=self._delete_selected_contact_from_list,
            variant="danger", size="sm",
        ).pack(side="left", padx=(8, 0))

        # Info label
        self.contact_list_info_label = tk.Label(
            content,
            textvariable=self.contact_list_info_var,
            bg=BG_ROOT,
            fg=FG_MUTED,
            font=FONT_BASE,
            anchor="w",
        )
        self.contact_list_info_label.pack(fill="x", pady=(0, 8))

        # Table frame (the hero element)
        table_frame = tk.Frame(content, bg=BG_ROOT)
        table_frame.pack(fill="both", expand=True)

        # Create Treeview for contacts
        columns = ("Email", "FirstName", "LastName", "Company", "JobTitle", "MobilePhone", "WorkPhone")
        self.choose_contacts_table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=12,
        )

        # Configure columns
        self.choose_contacts_table.column("Email", width=200, anchor="w")
        self.choose_contacts_table.column("FirstName", width=100, anchor="w")
        self.choose_contacts_table.column("LastName", width=100, anchor="w")
        self.choose_contacts_table.column("Company", width=130, anchor="w")
        self.choose_contacts_table.column("JobTitle", width=130, anchor="w")
        self.choose_contacts_table.column("MobilePhone", width=110, anchor="w")
        self.choose_contacts_table.column("WorkPhone", width=110, anchor="w")

        # Configure headings
        display_names = {"MobilePhone": "Mobile Phone", "WorkPhone": "Work Phone"}
        for col in columns:
            self.choose_contacts_table.heading(col, text=display_names.get(col, col), anchor="w")

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

            # Don't auto-select — user must choose a list each session
            self.selected_contact_list_var.set("Choose a list")
            if not list_names:
                self.contact_list_info_var.set("No lists available. Click 'Import new list' to get started.")

    def _refresh_contact_dropdown_values(self):
        """Reload contact list names into dropdown without selecting one."""
        self.contact_lists.clear()
        if os.path.exists(CONTACTS_DIR):
            for filename in os.listdir(CONTACTS_DIR):
                if filename.endswith(".csv") and filename != "contacts.csv":
                    list_name = os.path.splitext(filename)[0]
                    self.contact_lists[list_name] = os.path.join(CONTACTS_DIR, filename)
        list_names = sorted(self.contact_lists.keys())
        if hasattr(self, 'contact_list_selector_combo'):
            self.contact_list_selector_combo['values'] = list_names

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
            # Note: _set_active_contacts will update this label, but we set it here for immediate feedback
            self.contact_list_info_var.set(f"Selected: {basename} — {count} contacts")

            # Load contacts into the embedded table
            if hasattr(self, 'choose_contacts_table'):
                self._configure_stripe_tags(self.choose_contacts_table)
                for idx, row in enumerate(rows):
                    tag = "evenrow" if idx % 2 == 0 else "oddrow"
                    self.choose_contacts_table.insert("", "end", values=(
                        row.get("Email", ""),
                        row.get("FirstName", ""),
                        row.get("LastName", ""),
                        row.get("Company", ""),
                        row.get("JobTitle", ""),
                        row.get("MobilePhone", ""),
                        row.get("WorkPhone", ""),
                    ), tags=(tag,))

            # IMMEDIATELY set as active contacts (persists to config)
            self._set_active_contacts(list_path)

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
        name = themed_askstring(self, "Name this contact list", "Name this list so you can re-use it later:", default_name)
        if not name or not name.strip():
            return

        name = name.strip()

        # 3. Sanitize filename
        safe_name = self._safe_list_filename(name)

        # 4. Create destination path (no timestamp)
        dest_filename = f"{safe_name}.csv"
        dest_path = os.path.join(CONTACTS_DIR, dest_filename)

        # 5. Check if file already exists
        if os.path.exists(dest_path):
            overwrite = messagebox.askyesno(
                "List already exists",
                f"A list named '{safe_name}' already exists. Overwrite?"
            )
            if not overwrite:
                return  # Cancel import

        # 6. Convert and import
        try:
            count, warnings = detect_and_convert_contacts_to_official(src, dest_path)

            # 7. Add to dropdown
            self.contact_lists[safe_name] = dest_path
            list_names = sorted(self.contact_lists.keys())
            self.contact_list_selector_combo['values'] = list_names

            # 8. Select the new list
            self.selected_contact_list_var.set(safe_name)
            self._on_contact_list_selected()

            # 9. IMMEDIATELY set as active contacts (persists to config)
            self._set_active_contacts(dest_path)

            # 10. Confirm with toast
            self._set_status(f"Imported {count} contacts as '{name}'", GOOD)
            self.toast.show(f"{count} contacts added to '{name}'", "success")

            # 11. Show warnings if any
            if warnings:
                messagebox.showinfo(
                    "Import completed with notes",
                    f"{count} contacts imported.\n\n" + "\n".join(f"• {w}" for w in warnings),
                )
        except Exception as e:
            _write_crash_log("contact_list_import")
            self._set_status("Import failed", DANGER)
            messagebox.showerror("Import failed", f"Could not import contacts:\n{e}")

    def _delete_selected_contact_from_list(self):
        """Delete the selected contact from the current list."""
        # Check if a contact is selected
        if not hasattr(self, 'choose_contacts_table'):
            return

        selected = self.choose_contacts_table.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a contact to delete.")
            return

        # Get the selected contact's email for confirmation
        item = selected[0]
        values = self.choose_contacts_table.item(item, "values")
        email = values[0] if values else "Unknown"

        # Confirm deletion
        if not messagebox.askyesno("Delete Contact", f"Delete contact '{email}' from this list?"):
            return

        # Get the current list path
        list_name = self.selected_contact_list_var.get()
        if not list_name or list_name not in self.contact_lists:
            messagebox.showerror("Error", "No contact list selected.")
            return

        list_path = self.contact_lists[list_name]

        try:
            # Read all contacts
            rows, headers = safe_read_csv_rows(list_path)

            # Find and remove the contact with matching email
            email_to_delete = values[0] if values else None
            if email_to_delete:
                rows = [r for r in rows if r.get("Email", "") != email_to_delete and r.get("Work Email", "") != email_to_delete]

            # Write back to file
            import csv
            with open(list_path, "w", newline="", encoding="utf-8") as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=headers if headers else rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                else:
                    # Write empty file with headers
                    if headers:
                        writer = csv.DictWriter(f, fieldnames=headers)
                        writer.writeheader()

            # Remove from treeview
            self.choose_contacts_table.delete(item)

            # Update info label
            self.contact_list_info_var.set(f"Selected: {os.path.basename(list_path)} — {len(rows)} contacts")

            # Update active contacts if this is the active list
            self._set_active_contacts(list_path)

            self._set_status(f"Contact '{email}' deleted", GOOD)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete contact:\n{e}")

    def _add_new_contact_to_list(self):
        """Add a new contact to the current list."""
        # Check if a list is selected
        list_name = self.selected_contact_list_var.get()
        if not list_name or list_name not in self.contact_lists:
            messagebox.showwarning("No List", "Please select or import a contact list first.")
            return

        # Create add contact dialog
        dialog = tk.Toplevel(self)
        dialog.title("Add New Contact")
        dialog.configure(bg=BG_ROOT)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        # Center on parent
        dialog.withdraw()

        container = tk.Frame(dialog, bg=BG_ROOT)
        container.pack(fill="both", expand=True, padx=24, pady=20)

        # Fields
        fields = [
            ("Email:", "email"),
            ("First Name:", "first_name"),
            ("Last Name:", "last_name"),
            ("Company:", "company"),
            ("Job Title:", "job_title"),
            ("Mobile Phone:", "mobile_phone"),
            ("Work Phone:", "work_phone"),
        ]

        entries = {}
        for label_text, field_name in fields:
            row = tk.Frame(container, bg=BG_ROOT)
            row.pack(fill="x", pady=(0, 8))

            tk.Label(
                row,
                text=label_text,
                bg=BG_ROOT,
                fg=FG_TEXT,
                font=FONT_BASE,
                width=12,
                anchor="w",
            ).pack(side="left")

            entry = tk.Entry(
                row,
                bg=BG_ENTRY,
                fg=FG_TEXT,
                insertbackground=FG_TEXT,
                relief="flat",
                font=FONT_BASE,
                highlightthickness=1,
                highlightbackground=BORDER_MEDIUM,
                highlightcolor=ACCENT,
            )
            entry.pack(side="left", fill="x", expand=True, ipady=4)
            entries[field_name] = entry

        # Focus on email field
        entries["email"].focus_set()

        # Button row
        btn_row = tk.Frame(container, bg=BG_ROOT)
        btn_row.pack(fill="x", pady=(12, 0))

        def save_contact():
            email = entries["email"].get().strip()
            if not email:
                messagebox.showwarning("Email Required", "Please enter an email address.")
                return

            # Get list path
            list_path = self.contact_lists[list_name]

            try:
                # Read existing contacts
                rows, headers = safe_read_csv_rows(list_path)

                # Check for duplicate
                for r in rows:
                    if r.get("Email", "").lower() == email.lower() or r.get("Work Email", "").lower() == email.lower():
                        messagebox.showwarning("Duplicate", f"Contact '{email}' already exists in this list.")
                        return

                # Create new contact
                new_contact = {
                    "Email": email,
                    "FirstName": entries["first_name"].get().strip(),
                    "LastName": entries["last_name"].get().strip(),
                    "Company": entries["company"].get().strip(),
                    "JobTitle": entries["job_title"].get().strip(),
                    "MobilePhone": entries["mobile_phone"].get().strip(),
                    "WorkPhone": entries["work_phone"].get().strip(),
                }

                # Add any missing headers
                if headers:
                    for key in new_contact.keys():
                        if key not in headers:
                            headers.append(key)
                else:
                    headers = list(new_contact.keys())

                rows.append(new_contact)

                # Write back
                import csv
                with open(list_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(rows)

                # Add to treeview
                self.choose_contacts_table.insert("", "end", values=(
                    new_contact.get("Email", ""),
                    new_contact.get("FirstName", ""),
                    new_contact.get("LastName", ""),
                    new_contact.get("Company", ""),
                    new_contact.get("JobTitle", ""),
                ))

                # Update info label
                self.contact_list_info_var.set(f"Active: {os.path.basename(list_path)} — {len(rows)} contacts")

                # Update active contacts
                self._set_active_contacts(list_path)

                self._set_status(f"Contact '{email}' added", GOOD)
                self.toast.show(f"1 contact added to '{list_name}'", "success")
                dialog.destroy()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to add contact:\n{e}")

        tk.Button(
            btn_row,
            text="Add Contact",
            command=save_contact,
            bg=ACCENT,
            fg=FG_WHITE,
            activebackground=ACCENT,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=16,
            pady=6,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row,
            text="Cancel",
            command=dialog.destroy,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            activebackground=BORDER_SOFT,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            cursor="hand2",
            padx=12,
            pady=6,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="left")

        # Position dialog
        dialog.update_idletasks()
        w = max(400, dialog.winfo_reqwidth())
        h = dialog.winfo_reqheight()
        px = self.winfo_rootx() + (self.winfo_width() // 2) - (w // 2)
        py = self.winfo_rooty() + (self.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{px}+{py}")
        dialog.deiconify()

        # Bind Enter key to save
        dialog.bind("<Return>", lambda e: save_contact())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def _set_active_contacts(self, csv_path: str) -> None:
        """
        Set a contact list as immediately active and persist to config.
        Copies the selected list to OFFICIAL_CONTACTS_PATH (single source of truth).

        Args:
            csv_path: Full path to the CSV file to set as active
        """
        try:
            # Validate file exists
            if not os.path.isfile(csv_path):
                raise FileNotFoundError(f"Contact file not found: {csv_path}")

            # Validate it's a CSV we can read
            rows, _ = safe_read_csv_rows(csv_path)
            if not rows:
                raise ValueError("Contact file is empty or invalid")

            count = len(rows)

            # 1) Copy chosen list into OFFICIAL_CONTACTS_PATH (single source of truth)
            # Guard: don't copy if source and destination are the same file
            from pathlib import Path

            src = Path(csv_path).expanduser().resolve()
            dst = Path(OFFICIAL_CONTACTS_PATH).expanduser().resolve()

            # If user selected the official file itself, skip the copy
            try:
                if src.samefile(dst):
                    # Still update config/UI, but skip the copy
                    pass
                else:
                    shutil.copy2(str(src), str(dst))
            except FileNotFoundError:
                # Fallback: if samefile fails due to missing file, only copy if paths differ
                if str(src).lower() != str(dst).lower():
                    shutil.copy2(str(src), str(dst))

            # 2) Persist active selection in config
            config = load_config()  # IMPORTANT: call it, don't reference it

            # Store the selected list name if available
            if hasattr(self, 'selected_contact_list_var'):
                config["active_contact_list_name"] = self.selected_contact_list_var.get()
            elif hasattr(self, 'contact_lists_dropdown_var'):
                config["active_contact_list_name"] = self.contact_lists_dropdown_var.get()

            config["active_contact_list_path"] = csv_path
            config["active_contacts_file"] = OFFICIAL_CONTACTS_PATH  # Always point to official path
            save_config(config)

            # 3) Update UI labels if they exist
            if hasattr(self, 'contacts_path_var'):
                self.contacts_path_var.set(OFFICIAL_CONTACTS_PATH)

            if hasattr(self, 'contact_list_info_var'):
                basename = os.path.basename(csv_path)
                self.contact_list_info_var.set(f"Active: {basename} — {count} contacts")

            # 4) Update status bar
            self._set_status(f"Active contacts: {os.path.basename(csv_path)} ({count} contacts)", GOOD)

        except Exception as e:
            _write_crash_log("set_active_contacts")
            self._set_status("Failed to set active contacts", DANGER)
            messagebox.showerror("Error", f"Could not set active contacts:\n{e}")
            raise

    def _save_selected_list_as_official(self):
        """
        DEPRECATED: Save the selected list as the official contacts file.
        This method is no longer used. Lists are now automatically set as active
        when selected via _set_active_contacts().
        """
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

    def _validate_campaign_ready(self) -> dict:
        """
        Validate that the campaign is ready to launch.
        Returns dict with validation results and checklist messages.
        """
        messages = []

        # 1. Check contacts
        contacts_path = ""
        if hasattr(self, "contacts_path_var"):
            contacts_path = (self.contacts_path_var.get() or "").strip()
        if not contacts_path:
            contacts_path = OFFICIAL_CONTACTS_PATH

        try:
            rows, _ = safe_read_csv_rows(contacts_path)
            contact_count = len(rows)
        except Exception:
            contact_count = 0

        contacts_ok = contact_count >= 1
        if contacts_ok:
            messages.append(("ok", f"✅ {contact_count} contact(s) loaded"))
        else:
            messages.append(("fail", "❌ No contacts loaded"))

        # 2. Check emails exist
        email_count = len(self.name_vars) if hasattr(self, "name_vars") else 0
        emails_exist = email_count >= 1
        if emails_exist:
            messages.append(("ok", f"✅ {email_count} email(s) in sequence"))
        else:
            messages.append(("fail", "❌ No emails in sequence"))

        # 3. Check subjects filled
        missing_subjects = 0
        for i in range(email_count):
            subj = self.subject_vars[i].get().strip() if i < len(self.subject_vars) else ""
            if not subj:
                missing_subjects += 1

        subjects_ok = missing_subjects == 0
        if subjects_ok:
            messages.append(("ok", "✅ All subjects filled"))
        else:
            messages.append(("fail", f"❌ {missing_subjects} email(s) missing subject"))

        # 4. Check bodies filled (ignoring signature-only bodies)
        missing_bodies = 0
        for i in range(email_count):
            body = self.body_texts[i].get("1.0", "end-1c").strip() if i < len(self.body_texts) else ""
            # Check if body is empty or signature-only
            # Signature starts with \n\n--\n
            if not body or body.startswith("\n\n--\n"):
                missing_bodies += 1
            elif body.replace(self.signature_text, "").strip() == "":
                # Body contains only signature
                missing_bodies += 1

        bodies_ok = missing_bodies == 0
        if bodies_ok:
            messages.append(("ok", "✅ All email bodies filled"))
        else:
            messages.append(("fail", f"❌ {missing_bodies} email(s) missing body content"))

        # 5. Check signature saved
        signature_ok = False
        try:
            if hasattr(self, "signature_text") and self.signature_text:
                signature_ok = True
            elif os.path.exists(SIGNATURE_PATH):
                with open(SIGNATURE_PATH, "r", encoding="utf-8") as f:
                    sig_content = f.read().strip()
                    if sig_content and len(sig_content) > 10:  # Non-trivial content
                        signature_ok = True
        except Exception:
            pass

        if signature_ok:
            messages.append(("ok", "✅ Signature saved"))
        else:
            messages.append(("warn", "⚠️ No signature saved (recommended)"))

        # 6. Check schedule complete
        missing_schedule = 0
        for i in range(email_count):
            d = self.date_vars[i].get().strip() if i < len(self.date_vars) else ""
            t = self.time_vars[i].get().strip() if i < len(self.time_vars) else ""
            if (not d) or (not t):
                missing_schedule += 1

        schedule_ok = missing_schedule == 0
        if schedule_ok:
            messages.append(("ok", "✅ All emails scheduled"))
        else:
            messages.append(("fail", f"❌ {missing_schedule} email(s) missing schedule"))

        # Overall OK (signature warnings only, not failures)
        ok = (contacts_ok and emails_exist and subjects_ok and bodies_ok and schedule_ok)

        return {
            "ok": ok,
            "contact_count": contact_count,
            "email_count": email_count,
            "missing_subjects": missing_subjects,
            "missing_bodies": missing_bodies,
            "missing_schedule": missing_schedule,
            "signature_ok": signature_ok,
            "messages": messages
        }

    def _build_execute_review_panel(self, parent):
        """Left-side Review panel for Preview & Launch."""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="both", expand=True)

        box = tk.Frame(card, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1, relief="flat")
        box.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(box, text="Review", bg=BG_CARD, fg=ACCENT, font=FONT_SECTION).pack(anchor="w", padx=12, pady=(10, 4))

        # Store reference to meta label (will be filled by refresh)
        self.execute_review_meta_label = tk.Label(
            box,
            text="",  # will be filled by refresh
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_BASE,
            justify="left"
        )
        self.execute_review_meta_label.pack(anchor="w", padx=12, pady=(0, 10))

        tk.Frame(box, bg=BORDER, height=1).pack(fill="x", padx=12, pady=(0, 10))

        # Schedule preview table
        sched_header = tk.Frame(box, bg=BG_CARD)
        sched_header.pack(fill="x", padx=12)
        tk.Label(sched_header, text="Schedule preview", bg=BG_CARD, fg=FG_TEXT, font=FONT_BUTTON).pack(side="left")

        # Store reference to table
        self.execute_review_table = ttk.Treeview(box, columns=("step", "date", "time", "att"), show="headings", height=10)
        self.execute_review_table.heading("step", text="Email")
        self.execute_review_table.heading("date", text="Date")
        self.execute_review_table.heading("time", text="Time")
        self.execute_review_table.heading("att", text="Attachments")

        self.execute_review_table.column("step", width=220, anchor="w")
        self.execute_review_table.column("date", width=120, anchor="w")
        self.execute_review_table.column("time", width=110, anchor="w")
        self.execute_review_table.column("att", width=120, anchor="w")

        # Pack without expand=True so it only takes height=10 rows, leaving room for checklist below
        self.execute_review_table.pack(fill="x", padx=12, pady=(8, 12))

        # Rows will be populated by _refresh_execute_review_panel()

        # Campaign Ready Checklist section
        tk.Frame(box, bg=BORDER, height=1).pack(fill="x", padx=12, pady=(4, 10))

        tk.Label(box, text="Campaign Ready Checklist", bg=BG_CARD, fg=FG_TEXT, font=FONT_BUTTON).pack(anchor="w", padx=12, pady=(0, 6))

        # Checklist rows frame (will be populated with colored icons by refresh)
        self._checklist_rows_frame = tk.Frame(box, bg=BG_CARD)
        self._checklist_rows_frame.pack(fill="x", padx=12, pady=(0, 10))

        self._checklist_row_widgets = []  # list of (icon_label, text_label)

        # Status/help line (always visible at bottom)
        self._checklist_status_lbl = tk.Label(
            box,
            text="",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=FONT_SMALL,
            wraplength=820,
            justify="left",
            anchor="w",
        )
        self._checklist_status_lbl.pack(fill="x", padx=12, pady=(6, 12))

    def _refresh_execute_review_panel(self):
        """Refresh Preview & Launch review panel using current in-memory values."""
        if not hasattr(self, "execute_review_table") or not hasattr(self, "execute_review_meta_label"):
            return

        # Campaign name
        campaign_name = (self.campaign_name_var.get() or "Untitled Campaign") if hasattr(self, "campaign_name_var") else "Untitled Campaign"

        # Email count
        email_count = len(self.name_vars)

        # Contacts count
        contacts_path = ""
        if hasattr(self, "contacts_path_var"):
            contacts_path = (self.contacts_path_var.get() or "").strip()
        if not contacts_path:
            contacts_path = OFFICIAL_CONTACTS_PATH

        try:
            rows, _ = safe_read_csv_rows(contacts_path)
            contact_count = len(rows)
        except Exception:
            contact_count = 0

        # Missing schedule count
        missing_schedule = 0
        for i in range(email_count):
            d = self.date_vars[i].get().strip() if i < len(self.date_vars) else ""
            t = self.time_vars[i].get().strip() if i < len(self.time_vars) else ""
            if (not d) or (not t):
                missing_schedule += 1

        # Update meta text
        self.execute_review_meta_label.configure(
            text=f"{campaign_name}\n{email_count} emails • {contact_count} contacts • {missing_schedule} missing schedule"
        )

        # Clear table
        table = self.execute_review_table
        for iid in table.get_children():
            table.delete(iid)

        # Repopulate from CURRENT values
        for i in range(email_count):
            name = self.name_vars[i].get().strip() if i < len(self.name_vars) else f"Email {i+1}"
            d = self.date_vars[i].get().strip() if i < len(self.date_vars) else ""
            t = self.time_vars[i].get().strip() if i < len(self.time_vars) else ""

            att_count = 0
            try:
                att_count = len(self.per_email_attachments[i]) if i < len(self.per_email_attachments) else 0
            except Exception:
                att_count = 0

            table.insert("", "end", values=(name, d or "—", t or "—", f"{att_count} file(s)"))

        # VALIDATION: Run checklist and update UI with colored icons
        validation = self._validate_campaign_ready()

        # Render checklist rows with colored icons
        if hasattr(self, "_checklist_rows_frame"):
            self._render_checklist_lines(validation["messages"], validation["ok"])

        # Enable/disable Launch button based on validation
        if hasattr(self, "execute_launch_btn"):
            if validation["ok"]:
                self.execute_launch_btn.configure(state="normal")
            else:
                self.execute_launch_btn.configure(state="disabled")

    def _render_checklist_lines(self, lines, is_ready: bool):
        """
        Render checklist lines with colored status icons in TWO COLUMNS.
        lines: list of tuples like (state, text) where state in {"ok","fail","warn"}
        """
        if not hasattr(self, "_checklist_rows_frame"):
            return

        # Clear old rows
        for w in self._checklist_rows_frame.winfo_children():
            w.destroy()
        self._checklist_row_widgets.clear()

        # Two-column layout with smaller wraplength per column
        max_col_width = 420

        # Render each checklist item in two columns
        for idx, (state, text) in enumerate(lines):
            col = idx % 2  # Alternate between columns 0 and 1
            row = idx // 2  # Row increases every 2 items

            if state == "ok":
                icon, color = "✓", GOOD
            elif state == "warn":
                icon, color = "⚠", WARN
            else:  # fail
                icon, color = "✕", DANGER

            # Icon goes in column col*2, text goes in column col*2+1
            icon_col = col * 2
            text_col = col * 2 + 1

            icon_lbl = tk.Label(
                self._checklist_rows_frame,
                text=icon,
                bg=BG_CARD,
                fg=color,
                font=FONT_SECTION,
                width=2,
                anchor="w",
            )
            icon_lbl.grid(row=row, column=icon_col, sticky="w", padx=(0, 6), pady=1)

            # Add extra spacing between columns (left padding for column 1)
            padx_left = 0 if col == 0 else 18
            txt_lbl = tk.Label(
                self._checklist_rows_frame,
                text=text,
                bg=BG_CARD,
                fg=FG_TEXT,
                font=FONT_BASE,
                anchor="w",
                justify="left",
                wraplength=max_col_width,
            )
            txt_lbl.grid(row=row, column=text_col, sticky="w", padx=(padx_left, 0), pady=1)

            self._checklist_row_widgets.append((icon_lbl, txt_lbl))

        # Configure column weights so text columns can expand
        try:
            self._checklist_rows_frame.grid_columnconfigure(1, weight=1)  # First text column
            self._checklist_rows_frame.grid_columnconfigure(3, weight=1)  # Second text column
        except Exception:
            pass

        # Update status/help line (always visible at bottom)
        if hasattr(self, "_checklist_status_lbl"):
            if is_ready:
                self._checklist_status_lbl.configure(text="✅ Ready to launch.", fg=GOOD)
            else:
                self._checklist_status_lbl.configure(
                    text="Fix checklist items above to launch campaign.",
                    fg=WARN
                )

        # Force geometry refresh (helps with clipping in some layouts)
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _build_execute_screen(self, parent):
        """Preview/Execute Campaign screen - simplified"""
        _, content = self._page(parent, "Preview and Launch", "Review your campaign, send a test, then go live")

        # Two-column layout
        body = tk.Frame(content, bg=BG_ROOT)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        # Left: Review panel (schedule preview)
        left = tk.Frame(body, bg=BG_ROOT)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_execute_review_panel(left)

        # Right: Actions
        right = tk.Frame(body, bg=BG_ROOT)
        right.grid(row=0, column=1, sticky="nsew")

        self._build_tools_card(right, row=0, mode="preview_only")
        self._build_tools_card(right, row=1, mode="create_only")

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
        """Cancel Sequences screen - simplified"""
        _, content = self._page(parent, "Cancel Sequences", "Cancel or remove pending emails from Outlook")
        self._build_tools_card(content, row=0, mode="cancel_only")

    # ============================================
    # Manage Contacts Screen
    # ============================================
    def _build_contact_lists_main_screen(self, parent):
        """Main Manage Contacts screen - simplified"""
        _, content = self._page(parent, "Manage Contacts", "Import, review, and update your contact lists")

        # Controls row (no box)
        controls = tk.Frame(content, bg=BG_ROOT)
        controls.pack(fill="x", pady=(0, 12))

        tk.Label(
            controls,
            text="Select list:",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=FONT_LABEL,
        ).pack(side="left", padx=(0, 8))

        self.contact_lists_dropdown = ttk.Combobox(
            controls,
            textvariable=self.contact_lists_dropdown_var,
            state="readonly",
            width=40,
            style="Dark.TCombobox"
        )
        self.contact_lists_dropdown.pack(side="left", padx=(0, 16))
        self.contact_lists_dropdown.bind("<<ComboboxSelected>>", self._on_contact_list_main_selected)

        # Import button (secondary)
        make_button(controls, text="Import List", command=self._import_new_contact_list_main, variant="secondary").pack(side="left")

        # Action bar
        action_bar = tk.Frame(content, bg=BG_ROOT)
        action_bar.pack(fill="x", pady=(0, 12))

        # Add Contact (primary)
        make_button(action_bar, text="Add Contact", command=self._add_contact_to_list, variant="primary").pack(side="left", padx=(0, 8))

        # Delete Selected (danger)
        make_button(action_bar, text="Delete Selected", command=self._delete_selected_contacts, variant="danger", size="sm").pack(side="left", padx=(0, 8))

        # Refresh (ghost)
        make_button(action_bar, text="Refresh", command=self._update_contact_lists, variant="ghost").pack(side="left", padx=(0, 8))

        # Delete List (danger small)
        make_button(action_bar, text="Delete List", command=self._delete_current_contact_list, variant="danger", size="sm").pack(side="right")

        # Table frame (the hero element)
        table_frame = tk.Frame(content, bg=BG_ROOT)
        table_frame.pack(fill="both", expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # Create Treeview table
        self.contact_lists_table = ttk.Treeview(
            table_frame,
            columns=("Email", "FirstName", "LastName", "Company", "JobTitle", "MobilePhone", "WorkPhone"),
            show="headings",
            height=20,
            selectmode="extended"
        )

        # Configure columns
        self.contact_lists_table.heading("Email", text="Email")
        self.contact_lists_table.heading("FirstName", text="First Name")
        self.contact_lists_table.heading("LastName", text="Last Name")
        self.contact_lists_table.heading("Company", text="Company")
        self.contact_lists_table.heading("JobTitle", text="Job Title")
        self.contact_lists_table.heading("MobilePhone", text="Mobile Phone")
        self.contact_lists_table.heading("WorkPhone", text="Work Phone")

        self.contact_lists_table.column("Email", width=200, anchor="w")
        self.contact_lists_table.column("FirstName", width=110, anchor="w")
        self.contact_lists_table.column("LastName", width=110, anchor="w")
        self.contact_lists_table.column("Company", width=150, anchor="w")
        self.contact_lists_table.column("JobTitle", width=140, anchor="w")
        self.contact_lists_table.column("MobilePhone", width=110, anchor="w")
        self.contact_lists_table.column("WorkPhone", width=110, anchor="w")

        # Scrollbars for table
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.contact_lists_table.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.contact_lists_table.xview)
        self.contact_lists_table.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.contact_lists_table.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Populate dropdown with existing contact lists
        self._refresh_contact_lists_main_dropdown()

    # ============================================
    # Campaign Analytics Screen
    # ============================================
    def _build_campaign_analytics_screen(self, parent):
        """Campaign Analytics screen - Coming Soon"""
        _, content = self._page(parent, "Campaign Analytics", "Campaign performance and engagement insights")

        empty = make_empty_state(
            content,
            icon_text="📊",
            headline="Analytics Coming Soon",
            description="Campaign performance metrics, engagement tracking, and ROI reporting are on the way.",
            bg=BG_ROOT
        )
        empty.pack(fill="both", expand=True)

    # ============================================
    # Start with AI screen
    # ============================================
    _AI_VOICE_LIMIT = 3000
    _AI_VOICE_DEFAULT = (
        "I am a boutique construction recruiter specializing in project managers, "
        "superintendents, and executives in data center and infrastructure construction "
        "across the U.S. I work primarily with ENR contractors and developers. My approach "
        "is relationship-driven and consultative, focused on long-term fit rather than "
        "transactional placements. My outreach should sound professional, direct, and "
        "conversational, with concise emails and clear value to the recipient. Avoid hype "
        "or recruiter clichés."
    )

    def _build_train_ai_screen(self, parent):
        """Start with AI — single free-text voice field (OpenAI custom-instructions style)."""
        _, content = self._page(parent, "Start with AI",
                                "Teach ChatGPT about your company so every email sounds like you")

        # Load existing voice text (with migration from old multi-field format)
        voice_text = self._load_voice_text()

        # ── Single card ──
        card = tk.Frame(content, bg=BG_CARD, highlightbackground=BORDER_MEDIUM,
                        highlightthickness=1, relief="flat")
        card.pack(fill="x", pady=(0, 12))

        tk.Label(card, text="About you and your recruiting voice", bg=BG_CARD,
                 fg=ACCENT, font=FONT_SECTION).pack(anchor="w", padx=14, pady=(12, 4))

        tk.Label(card, text=(
            "Describe your recruiting focus, target clients and candidates, "
            "differentiators, and how you like outreach to sound. The AI will "
            "use this to write emails in your voice."
        ), bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL, wraplength=600,
                 justify="left").pack(anchor="w", padx=14, pady=(0, 8))

        self._ai_voice_text = tk.Text(card, bg=BG_ENTRY, fg=FG_TEXT, font=FONT_BASE,
                                      wrap="word", height=14, relief="flat",
                                      highlightthickness=1,
                                      highlightbackground=BORDER_MEDIUM,
                                      padx=8, pady=6)
        self._ai_voice_text.pack(fill="x", padx=14, pady=(0, 4))
        self._ai_voice_text.insert("1.0", voice_text)

        # Live character counter
        counter_lbl = tk.Label(card, text=f"{len(voice_text)} / {self._AI_VOICE_LIMIT}",
                               bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL)
        counter_lbl.pack(anchor="e", padx=14, pady=(0, 12))

        def _on_voice_change(event=None):
            txt = self._ai_voice_text.get("1.0", "end-1c")
            if len(txt) > self._AI_VOICE_LIMIT:
                self._ai_voice_text.delete(f"1.0+{self._AI_VOICE_LIMIT}c", "end")
                txt = self._ai_voice_text.get("1.0", "end-1c")
            counter_lbl.config(text=f"{len(txt)} / {self._AI_VOICE_LIMIT}")

        self._ai_voice_text.bind("<KeyRelease>", _on_voice_change)

        # ── Save button ──
        btn_row = tk.Frame(content, bg=BG_ROOT)
        btn_row.pack(fill="x", pady=(4, 16))

        save_btn = tk.Button(
            btn_row, text="Save",
            command=self._save_ai_training_from_ui,
            bg="#7C3AED", fg="#FFFFFF", activebackground="#6D28D9",
            activeforeground="#FFFFFF", relief="flat",
            font=("Segoe UI Semibold", 11), padx=24, pady=10, cursor="hand2",
        )
        save_btn.pack(side="left")
        save_btn.bind("<Enter>", lambda e: save_btn.config(bg="#6D28D9"))
        save_btn.bind("<Leave>", lambda e: save_btn.config(bg="#7C3AED"))

        self._ai_training_status = tk.Label(btn_row, text="", bg=BG_ROOT, fg=FG_MUTED,
                                            font=FONT_SMALL)
        self._ai_training_status.pack(side="left", padx=(16, 0))

    def _load_ai_training_dict(self) -> dict:
        """Load raw AI training data dict from shared team config."""
        try:
            if SHARED_CONFIG_PATH.exists():
                with open(SHARED_CONFIG_PATH, "r", encoding="utf-8") as f:
                    team_cfg = json.load(f)
                return team_cfg.get("ai_training", {})
        except Exception:
            pass
        return {}

    @staticmethod
    def _migrate_old_fields(data: dict) -> str:
        """Build a voice_text string from legacy multi-field ai_training data."""
        parts = []
        if data.get("company_name"):
            desc = data.get("company_description", "").strip()
            parts.append(f"Company: {data['company_name']}" +
                         (f" — {desc}" if desc else ""))
        elif data.get("company_description"):
            parts.append(data["company_description"].strip())
        if data.get("target_audience"):
            parts.append(f"Target audience: {data['target_audience'].strip()}")
        if data.get("tone"):
            parts.append(f"Preferred tone: {data['tone'].strip()}")
        if data.get("words_to_use"):
            parts.append(f"Words/phrases to use: {data['words_to_use'].strip()}")
        if data.get("words_to_avoid"):
            parts.append(f"Words/phrases to avoid: {data['words_to_avoid'].strip()}")
        if data.get("example_emails"):
            parts.append(f"\nExample emails:\n{data['example_emails'].strip()}")
        return "\n".join(parts)

    def _load_voice_text(self) -> str:
        """Return the voice_text string, migrating old fields if needed."""
        data = self._load_ai_training_dict()
        if data.get("voice_text"):
            return data["voice_text"]
        # Migrate legacy multi-field format
        migrated = self._migrate_old_fields(data)
        if migrated:
            return migrated
        # Nothing saved — return default prefill
        return self._AI_VOICE_DEFAULT

    def _load_ai_training(self) -> str:
        """Load voice text + per-user personalization for the AI system prompt."""
        voice = self._load_voice_text()
        parts = []
        if voice:
            parts.append(f"Additional context about the user's business:\n{voice}")

        # Per-user AI personalization from local config
        cfg = load_config()
        if cfg.get("ai_nickname"):
            parts.append(f"User's name: {cfg['ai_nickname']}")
        if cfg.get("ai_occupation"):
            parts.append(f"User's occupation: {cfg['ai_occupation']}")
        if cfg.get("ai_about"):
            parts.append(f"About the user: {cfg['ai_about']}")
        if cfg.get("ai_custom_instructions"):
            parts.append(f"Custom instructions from the user (follow these closely): {cfg['ai_custom_instructions']}")

        return "\n\n".join(parts)

    def _save_ai_training_from_ui(self):
        """Save the single voice_text field to shared config."""
        voice = self._ai_voice_text.get("1.0", "end-1c").strip()

        try:
            SHARED_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            team_cfg = {}
            if SHARED_CONFIG_PATH.exists():
                with open(SHARED_CONFIG_PATH, "r", encoding="utf-8") as f:
                    team_cfg = json.load(f)
            if "ai_training" not in team_cfg:
                team_cfg["ai_training"] = {}
            team_cfg["ai_training"]["voice_text"] = voice
            with open(SHARED_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(team_cfg, f, indent=2)
            self.toast.show("AI voice saved! All future AI output will use this context.", "info")
            self._ai_training_status.config(text="Saved", fg=GOOD)
        except Exception as e:
            self.toast.show(f"Error saving: {e}", "error")
            self._ai_training_status.config(text=f"Error: {e}", fg=DANGER)

    # ============================================
    # Admin: User Management screen
    # ============================================
    def _build_admin_users_screen(self, parent):
        """Admin screen showing all registered users from the shared registry."""
        _, content = self._page(parent, "Current Users",
                                "Track registered FunnelForge users and their activity")

        # --- Stats cards row ---
        stats_frame = tk.Frame(content, bg=BG_ROOT)
        stats_frame.pack(fill="x", padx=0, pady=(0, SP_4))
        stats_frame.columnconfigure((0, 1, 2), weight=1, uniform="admin_stats")

        self._admin_stat_labels = {}

        for col, (title, key, color) in enumerate([
            ("Total Users", "total", ACCENT),
            ("Active This Week", "week", GOOD),
            ("Active This Month", "month", INFO),
        ]):
            card = tk.Frame(stats_frame, bg=GRAY_200)
            card.grid(row=0, column=col, sticky="nsew",
                      padx=(0 if col == 0 else SP_2, 0))
            inner = tk.Frame(card, bg=SURFACE_CARD)
            inner.pack(fill="both", expand=True, padx=1, pady=1)
            tk.Frame(inner, bg=color, height=3).pack(fill="x")
            body = tk.Frame(inner, bg=SURFACE_CARD)
            body.pack(fill="both", expand=True, padx=SP_4, pady=(SP_2, SP_3))
            tk.Label(body, text=title, bg=SURFACE_CARD, fg=GRAY_500,
                     font=FONT_SMALL).pack(anchor="w")
            val_lbl = tk.Label(body, text="0", bg=SURFACE_CARD, fg=color,
                               font=FONT_HEADING)
            val_lbl.pack(anchor="w", pady=(SP_1, 0))
            self._admin_stat_labels[key] = val_lbl

        # --- Refresh button ---
        btn_row = tk.Frame(content, bg=BG_ROOT)
        btn_row.pack(fill="x", pady=(0, SP_3))
        make_button(btn_row, text="Refresh", command=self._refresh_admin_users,
                    variant="secondary").pack(side="right")

        # --- Table header ---
        columns = ["Username", "Full Name", "Email", "Company",
                    "Registered", "Last Active", "Version", "Admin"]
        # Fixed column min-widths so header + rows stay aligned
        col_mins = [100, 140, 200, 120, 100, 160, 70, 60]

        hdr_frame = tk.Frame(content, bg=GRAY_100)
        hdr_frame.pack(fill="x")
        for i, col_name in enumerate(columns):
            hdr_frame.columnconfigure(i, weight=1, minsize=col_mins[i])
            tk.Label(hdr_frame, text=col_name, bg=GRAY_100, fg=GRAY_600,
                     font=FONT_SMALL, anchor="w",
                     padx=SP_3, pady=SP_2).grid(row=0, column=i, sticky="ew")

        # --- Scrollable rows ---
        scroller, rows_inner = self._make_scroller(content)
        scroller.pack(fill="both", expand=True)
        self._admin_users_table = rows_inner
        self._admin_col_mins = col_mins

        # Initial populate
        self.after(200, self._refresh_admin_users)

    def _refresh_admin_users(self):
        """Reload user registry and repopulate the admin table."""
        registry = load_user_registry()
        users = registry.get("users", {})
        admins = registry.get("admins", [])

        # Update stats
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        active_week = 0
        active_month = 0
        for u in users.values():
            try:
                la = datetime.strptime(u.get("last_active", ""), "%Y-%m-%d %H:%M:%S")
                if la >= week_ago:
                    active_week += 1
                if la >= month_ago:
                    active_month += 1
            except (ValueError, TypeError):
                pass

        if hasattr(self, "_admin_stat_labels"):
            self._admin_stat_labels["total"].configure(text=str(len(users)))
            self._admin_stat_labels["week"].configure(text=str(active_week))
            self._admin_stat_labels["month"].configure(text=str(active_month))

        # Clear existing rows
        table = self._admin_users_table
        for w in table.winfo_children():
            w.destroy()

        if not users:
            tk.Label(table, text="No registered users yet.", bg=BG_ROOT,
                     fg=FG_MUTED, font=FONT_BASE, pady=SP_6).pack()
            return

        # Sort by last_active descending
        sorted_users = sorted(
            users.values(),
            key=lambda u: u.get("last_active", ""),
            reverse=True,
        )

        col_mins = self._admin_col_mins
        for idx, user in enumerate(sorted_users):
            row_bg = BG_ROOT if idx % 2 == 0 else GRAY_50
            # Wrapper holds both the summary row and the expandable detail
            wrapper = tk.Frame(table, bg=row_bg)
            wrapper.pack(fill="x")

            row_frame = tk.Frame(wrapper, bg=row_bg, cursor="hand2")
            row_frame.pack(fill="x")
            for i, cm in enumerate(col_mins):
                row_frame.columnconfigure(i, weight=1, minsize=cm)

            uname = user.get("username", "")

            # Format dates for display
            reg_date = user.get("registered_at", "")
            if reg_date:
                try:
                    dt = datetime.strptime(reg_date, "%Y-%m-%d %H:%M:%S")
                    reg_date = dt.strftime("%b %d, %Y")
                except (ValueError, TypeError):
                    pass

            last_active = user.get("last_active", "")
            if last_active:
                try:
                    dt = datetime.strptime(last_active, "%Y-%m-%d %H:%M:%S")
                    last_active = dt.strftime("%b %d, %Y %I:%M %p")
                except (ValueError, TypeError):
                    pass

            # Text columns (0-6)
            version = user.get("app_version", "")
            values = [uname, user.get("full_name", ""), user.get("email", ""),
                      user.get("company", ""), reg_date, last_active, version]
            for i, val in enumerate(values):
                tk.Label(row_frame, text=val, bg=row_bg, fg=FG_TEXT,
                         font=FONT_BASE, anchor="w",
                         padx=SP_3, pady=SP_2).grid(row=0, column=i, sticky="ew")

            # Admin toggle column (7)
            user_is_admin = uname in admins
            btn_text = "Admin" if user_is_admin else "User"
            btn_fg = ACCENT if user_is_admin else FG_MUTED
            btn = tk.Label(
                row_frame, text=btn_text, bg=row_bg, fg=btn_fg,
                font=FONT_SMALL, anchor="w", padx=SP_3, pady=SP_2,
                cursor="hand2",
            )
            btn.grid(row=0, column=7, sticky="ew")
            btn.bind("<Button-1>", lambda e, u=uname, a=user_is_admin: self._toggle_admin(u, a))

            # Expandable detail panel (hidden by default)
            detail = tk.Frame(wrapper, bg=PRIMARY_50)
            detail._visible = False

            user_stats = user.get("stats", {})
            stat_items = [
                ("Emails (30 days)", str(user_stats.get("emails_past_30_days", 0)), ACCENT),
                ("Responses", str(user_stats.get("total_responses", 0)), GOOD),
                ("Response Rate", f"{user_stats.get('response_rate', 0)}%", INFO),
                ("Active Campaigns", str(user_stats.get("active_campaigns", 0)), WARN),
            ]

            detail_inner = tk.Frame(detail, bg=PRIMARY_50)
            detail_inner.pack(fill="x", padx=(SP_6, SP_4), pady=SP_3)

            for s_label, s_val, s_color in stat_items:
                card = tk.Frame(detail_inner, bg=SURFACE_CARD, bd=0,
                                highlightthickness=1, highlightbackground=GRAY_200)
                card.pack(side="left", padx=(0, SP_3), ipadx=SP_4, ipady=SP_2)
                tk.Label(card, text=s_label, bg=SURFACE_CARD, fg=GRAY_500,
                         font=FONT_SMALL).pack(anchor="w")
                tk.Label(card, text=s_val, bg=SURFACE_CARD, fg=s_color,
                         font=FONT_SUBTITLE).pack(anchor="w")

            if not user_stats:
                tk.Label(detail_inner, text="No activity data yet",
                         bg=PRIMARY_50, fg=FG_MUTED, font=FONT_SMALL).pack(side="left", padx=SP_3)

            # Click row to toggle detail
            def _toggle_detail(e, d=detail):
                if d._visible:
                    d.pack_forget()
                    d._visible = False
                else:
                    d.pack(fill="x")
                    d._visible = True

            row_frame.bind("<Button-1>", _toggle_detail)
            for child in row_frame.winfo_children():
                if child != btn:
                    child.bind("<Button-1>", _toggle_detail)

    # ============================================
    # Stay Connected screen
    def _toggle_admin(self, username: str, currently_admin: bool):
        """Toggle admin status for a user and refresh the table."""
        set_admin(username, not currently_admin)
        action = "removed from" if currently_admin else "added to"
        self._set_status(f"{username} {action} admins.", GOOD)
        self._refresh_admin_users()

    # ============================================
    def _build_stay_connected_screen(self, parent):
        """Stay Connected page - modern two-column layout."""
        _, content = self._page(parent, "Stay Connected", "Keep in touch with contacts through ongoing outreach")

        # State tracking
        self._nurture_selected_campaign_id = None
        self._nurture_attachments = []

        # Main container
        main_container = tk.Frame(content, bg=BG_ROOT)
        main_container.pack(fill="both", expand=True)

        # Two-column layout
        main_container.columnconfigure(0, weight=0, minsize=240)
        main_container.columnconfigure(1, weight=3)
        main_container.rowconfigure(0, weight=1)

        # ========== LEFT PANEL ==========
        left_panel = tk.Frame(main_container, bg=BG_CARD, width=240)
        left_panel.grid(row=0, column=0, sticky="nsew")
        left_panel.grid_propagate(False)

        # Header with + button
        header_row = tk.Frame(left_panel, bg=BG_CARD)
        header_row.pack(fill="x", padx=16, pady=(16, 12))

        tk.Label(
            header_row, text="Lists", bg=BG_CARD, fg=FG_TEXT,
            font=FONT_SECTION,
        ).pack(side="left")

        tk.Button(
            header_row, text="+", command=self._nurture_new_campaign,
            bg=ACCENT, fg="white", activebackground=ACCENT_HOVER, activeforeground="white",
            relief="flat", font=FONT_SECTION, cursor="hand2",
            padx=8, pady=0, bd=0,
        ).pack(side="right")

        # Subtle separator
        tk.Frame(left_panel, bg=BORDER, height=1).pack(fill="x", padx=16)

        # Campaign listbox
        self._nurture_campaign_listbox = tk.Listbox(
            left_panel, bg=BG_CARD, fg=FG_TEXT,
            selectbackground=PRIMARY_50, selectforeground=ACCENT,
            highlightthickness=0, borderwidth=0,
            font=FONT_BASE, activestyle="none", exportselection=False,
        )
        self._nurture_campaign_listbox.pack(fill="both", expand=True, padx=8, pady=8)
        self._nurture_campaign_listbox.bind("<<ListboxSelect>>", self._on_nurture_campaign_selected)

        # Bottom actions (Rename / Delete as text links)
        bottom_row = tk.Frame(left_panel, bg=BG_CARD)
        bottom_row.pack(fill="x", padx=16, pady=(0, 12))

        tk.Button(
            bottom_row, text="Rename", command=self._nurture_rename_campaign_btn,
            bg=BG_CARD, fg=FG_MUTED, activebackground=BG_CARD, activeforeground=FG_TEXT,
            relief="flat", font=FONT_SMALL, cursor="hand2", bd=0,
        ).pack(side="left")

        tk.Label(bottom_row, text="·", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(side="left", padx=4)

        tk.Button(
            bottom_row, text="Delete", command=self._nurture_delete_campaign_btn,
            bg=BG_CARD, fg=DANGER, activebackground=BG_CARD, activeforeground=DANGER,
            relief="flat", font=FONT_SMALL, cursor="hand2", bd=0,
        ).pack(side="left")

        # ========== RIGHT PANEL ==========
        right_panel = tk.Frame(main_container, bg=BG_ROOT)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._nurture_content_area = tk.Frame(right_panel, bg=BG_ROOT)
        self._nurture_content_area.pack(fill="both", expand=True)

        self._build_nurture_placeholder()
        self._build_nurture_detail_page()
        self._nurture_show_placeholder()
        self._refresh_nurture_campaigns()

    def _refresh_stay_nurture_list(self):
        """Refresh the Running Nurture Lists list on Stay Connected page."""
        if not hasattr(self, '_stay_nurture_inner'):
            return

        # Clear existing items
        for widget in self._stay_nurture_inner.winfo_children():
            widget.destroy()

        # Hide contact panel
        if hasattr(self, '_stay_contact_panel'):
            self._stay_contact_panel.pack_forget()

        # Load nurture lists
        idx = self._load_nurture_index()
        campaigns = idx.get("campaigns", [])

        # Filter to active campaigns only (those with contacts)
        active_campaigns = []
        for camp_info in campaigns:
            camp_data = self._load_nurture_campaign(camp_info["id"])
            if camp_data:
                contacts = camp_data.get("contacts", [])
                if len(contacts) > 0:  # Only show campaigns with contacts
                    active_campaigns.append({
                        "id": camp_info["id"],
                        "name": camp_info["name"],
                        "contact_count": len(contacts),
                        "created_at": camp_info.get("created_at", ""),
                        "contacts": contacts,
                    })

        if not active_campaigns:
            # Empty state
            empty_frame = tk.Frame(self._stay_nurture_inner, bg=BG_CARD)
            empty_frame.pack(fill="both", expand=True, pady=40)
            tk.Label(
                empty_frame,
                text="No active nurture lists",
                bg=BG_CARD,
                fg=FG_MUTED,
                font=FONT_SECTION_TITLE,
            ).pack()
            tk.Label(
                empty_frame,
                text="Create a campaign and add contacts to get started",
                bg=BG_CARD,
                fg=FG_MUTED,
                font=FONT_SMALL,
            ).pack(pady=(4, 0))
            return

        # Render each campaign row
        for camp in active_campaigns:
            self._render_stay_nurture_row(camp)

    def _render_stay_nurture_row(self, campaign):
        """Render a single nurture list row in the Stay Connected list."""
        row = tk.Frame(self._stay_nurture_inner, bg=BG_CARD, cursor="hand2")
        row.pack(fill="x", padx=0, pady=0)

        # Content frame
        content = tk.Frame(row, bg=BG_CARD)
        content.pack(fill="x", padx=12, pady=10)

        # Top row: Name and Status
        top_row = tk.Frame(content, bg=BG_CARD)
        top_row.pack(fill="x")

        name_label = tk.Label(
            top_row,
            text=campaign["name"],
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_SECTION_TITLE,
            cursor="hand2",
        )
        name_label.pack(side="left")

        # Status pill (Active)
        status_pill = tk.Label(
            top_row,
            text="Active",
            bg=GOOD,
            fg="white",
            font=FONT_CAPTION,
            padx=6,
            pady=1,
        )
        status_pill.pack(side="right")

        # Bottom row: Contact count
        contact_count = campaign.get("contact_count", 0)
        meta_label = tk.Label(
            content,
            text=f"{contact_count} contact{'s' if contact_count != 1 else ''}",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=FONT_SMALL,
        )
        meta_label.pack(anchor="w", pady=(4, 0))

        # Separator
        sep = ttk.Separator(self._stay_nurture_inner, orient="horizontal")
        sep.pack(fill="x")

        # Click handler to show contacts
        def _on_click(event=None):
            self._show_stay_nurture_contacts(campaign)

        for widget in [row, content, top_row, name_label, meta_label]:
            widget.bind("<Button-1>", _on_click)

        # Hover effect
        def _on_enter(event=None):
            row.configure(bg=BG_HOVER)
            content.configure(bg=BG_HOVER)
            top_row.configure(bg=BG_HOVER)
            name_label.configure(bg=BG_HOVER)
            meta_label.configure(bg=BG_HOVER)

        def _on_leave(event=None):
            row.configure(bg=BG_CARD)
            content.configure(bg=BG_CARD)
            top_row.configure(bg=BG_CARD)
            name_label.configure(bg=BG_CARD)
            meta_label.configure(bg=BG_CARD)

        for widget in [row, content, top_row, name_label, meta_label]:
            widget.bind("<Enter>", _on_enter)
            widget.bind("<Leave>", _on_leave)

    def _show_stay_nurture_contacts(self, campaign):
        """Show contacts panel for selected nurture list."""
        if not hasattr(self, '_stay_contact_panel'):
            return

        # Clear existing content
        for widget in self._stay_contact_panel_inner.winfo_children():
            widget.destroy()

        # Header
        header = tk.Frame(self._stay_contact_panel_inner, bg=BG_CARD)
        header.pack(fill="x", pady=(0, 8))

        tk.Label(
            header,
            text=f"Contacts in {campaign['name']}",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_BUTTON,
        ).pack(side="left")

        # Close button
        tk.Button(
            header,
            text="\u2715",
            command=lambda: self._stay_contact_panel.pack_forget(),
            bg=BG_CARD,
            fg=FG_MUTED,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            cursor="hand2",
            padx=4,
            pady=0,
        ).pack(side="right")

        # Contacts list (scrollable)
        contacts_frame = tk.Frame(self._stay_contact_panel_inner, bg=BG_CARD)
        contacts_frame.pack(fill="both", expand=True)

        contacts = campaign.get("contacts", [])
        if not contacts:
            tk.Label(
                contacts_frame,
                text="No contacts in this campaign",
                bg=BG_CARD,
                fg=FG_MUTED,
                font=FONT_SMALL,
            ).pack(pady=8)
        else:
            # Show up to 10 contacts with scrolling
            canvas = tk.Canvas(contacts_frame, bg=BG_CARD, highlightthickness=0, height=150)
            scrollbar = ttk.Scrollbar(contacts_frame, orient="vertical", command=canvas.yview)
            inner = tk.Frame(canvas, bg=BG_CARD)

            inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            # Mousewheel scrolling (Windows)
            def _on_mousewheel(event, c=canvas):
                c.yview_scroll(int(-1 * (event.delta / 120)), "units")

            canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
            canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

            for contact in contacts:
                data = contact.get("data", {})
                name = f"{data.get('FirstName', '')} {data.get('LastName', '')}".strip() or "Unknown"
                email = data.get("Email", contact.get("email_key", ""))

                contact_row = tk.Frame(inner, bg=BG_CARD)
                contact_row.pack(fill="x", pady=2)

                tk.Label(
                    contact_row,
                    text=name,
                    bg=BG_CARD,
                    fg=FG_TEXT,
                    font=FONT_SMALL,
                    width=20,
                    anchor="w",
                ).pack(side="left")

                tk.Label(
                    contact_row,
                    text=email,
                    bg=BG_CARD,
                    fg=FG_MUTED,
                    font=FONT_SMALL,
                    anchor="w",
                ).pack(side="left", padx=(8, 0))

        # Show the panel
        self._stay_contact_panel.pack(fill="x", pady=(12, 0))

    def _build_stay_overview(self):
        """Build the Campaign Overview view (default when campaign is selected)."""
        overview = self._stay_overview_content

        # Header row: Campaign name + Status pill + Edit button
        header = tk.Frame(overview, bg=BG_CARD)
        header.pack(fill="x", padx=16, pady=(16, 12))

        self._stay_overview_name = tk.Label(
            header,
            text="",
            bg=BG_CARD,
            fg=ACCENT,
            font=FONT_HEADING,
        )
        self._stay_overview_name.pack(side="left")

        self._stay_overview_status = tk.Label(
            header,
            text="",
            bg=BG_CARD,
            fg=FG_WHITE,
            font=FONT_BTN_SM,
            padx=8,
            pady=2,
        )
        self._stay_overview_status.pack(side="left", padx=(12, 0))

        tk.Button(
            header,
            text="Edit Campaign",
            command=self._stay_show_editor,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=16,
            pady=6,
        ).pack(side="right")

        # Overview cards row
        cards_row = tk.Frame(overview, bg=BG_CARD)
        cards_row.pack(fill="x", padx=16, pady=(0, 16))

        # Card 1: Last Email
        card1 = tk.Frame(cards_row, bg=BG_ROOT, highlightbackground=BORDER, highlightthickness=1)
        card1.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(card1, text="Last Email", bg=BG_ROOT, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", padx=12, pady=(12, 4))
        self._stay_card_subject = tk.Label(card1, text="—", bg=BG_ROOT, fg=FG_TEXT, font=FONT_SECTION_TITLE, wraplength=180, justify="left")
        self._stay_card_subject.pack(anchor="w", padx=12)
        self._stay_card_sent = tk.Label(card1, text="Not sent yet", bg=BG_ROOT, fg=FG_MUTED, font=FONT_SMALL)
        self._stay_card_sent.pack(anchor="w", padx=12, pady=(4, 12))

        # Card 2: Contacts
        card2 = tk.Frame(cards_row, bg=BG_ROOT, highlightbackground=BORDER, highlightthickness=1)
        card2.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(card2, text="Contacts", bg=BG_ROOT, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", padx=12, pady=(12, 4))
        self._stay_card_contacts = tk.Label(card2, text="0", bg=BG_ROOT, fg=FG_TEXT, font=FONT_SECTION_TITLE)
        self._stay_card_contacts.pack(anchor="w", padx=12)
        tk.Button(
            card2,
            text="View Contacts",
            command=self._stay_show_contacts_from_overview,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_CAPTION,
            cursor="hand2",
            padx=6,
            pady=2,
        ).pack(anchor="w", padx=12, pady=(4, 12))

        # Card 3: Next Send
        card3 = tk.Frame(cards_row, bg=BG_ROOT, highlightbackground=BORDER, highlightthickness=1)
        card3.pack(side="left", fill="both", expand=True)

        tk.Label(card3, text="Next Send", bg=BG_ROOT, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", padx=12, pady=(12, 4))
        self._stay_card_next = tk.Label(card3, text="Not scheduled", bg=BG_ROOT, fg=FG_TEXT, font=FONT_SECTION_TITLE)
        self._stay_card_next.pack(anchor="w", padx=12, pady=(0, 12))

        # Activity Timeline
        timeline_header = tk.Frame(overview, bg=BG_CARD)
        timeline_header.pack(fill="x", padx=16, pady=(0, 8))

        tk.Label(
            timeline_header,
            text="Activity",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_SECTION,
        ).pack(side="left")

        timeline_frame = tk.Frame(overview, bg=BG_CARD)
        timeline_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self._stay_timeline_list = tk.Listbox(
            timeline_frame,
            bg=BG_ROOT,
            fg=FG_MUTED,
            font=FONT_SMALL,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            selectmode="none",
            activestyle="none",
            height=6,
        )
        self._stay_timeline_list.pack(fill="both", expand=True)

        # Bottom actions
        actions_frame = tk.Frame(overview, bg=BG_CARD)
        actions_frame.pack(fill="x", padx=16, pady=(0, 16))

        tk.Button(
            actions_frame,
            text="Delete Campaign",
            command=self._stay_delete_category,
            bg=BG_CARD,
            fg=DANGER,
            activebackground=BG_HOVER,
            activeforeground=DANGER,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=8,
            pady=4,
        ).pack(side="left")

        self._stay_pause_btn = tk.Button(
            actions_frame,
            text="Pause Campaign",
            command=self._stay_toggle_pause,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=8,
            pady=4,
        )
        self._stay_pause_btn.pack(side="left", padx=(8, 0))

    def _build_stay_editor(self):
        """Build the Edit Campaign view (accessed via Edit button)."""
        editor = self._stay_editor_content

        # Header with back button
        header = tk.Frame(editor, bg=BG_CARD)
        header.pack(fill="x", padx=16, pady=(16, 8))

        tk.Button(
            header,
            text="< Back to Overview",
            command=self._stay_show_overview,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=8,
            pady=4,
        ).pack(side="left")

        self._stay_editor_name = tk.Label(
            header,
            text="Edit Campaign",
            bg=BG_CARD,
            fg=ACCENT,
            font=FONT_TITLE,
        )
        self._stay_editor_name.pack(side="left", padx=(12, 0))

        # Notebook for tabs
        self._stay_notebook = ttk.Notebook(editor)
        self._stay_notebook.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        # ===== TAB 1: BUILD EMAIL =====
        email_tab = tk.Frame(self._stay_notebook, bg=BG_CARD)
        self._stay_notebook.add(email_tab, text="Email")

        subj_frame = tk.Frame(email_tab, bg=BG_CARD)
        subj_frame.pack(fill="x", padx=12, pady=(12, 8))

        tk.Label(subj_frame, text="Subject", bg=BG_CARD, fg=FG_TEXT, font=FONT_BUTTON).pack(anchor="w", pady=(0, 4))

        self._stay_subject_var = tk.StringVar()
        self._stay_subject_entry = tk.Entry(
            subj_frame,
            textvariable=self._stay_subject_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            font=FONT_BASE,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self._stay_subject_entry.pack(fill="x", ipady=6)

        body_frame = tk.Frame(email_tab, bg=BG_CARD)
        body_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        tk.Label(body_frame, text="Body", bg=BG_CARD, fg=FG_TEXT, font=FONT_BUTTON).pack(anchor="w", pady=(0, 4))

        self._stay_body_text = tk.Text(
            body_frame,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            font=FONT_BASE,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            wrap="word",
            height=8,
        )
        self._stay_body_text.pack(fill="both", expand=True)

        vars_frame = tk.Frame(email_tab, bg=BG_CARD)
        vars_frame.pack(fill="x", padx=12, pady=(8, 8))

        tk.Label(vars_frame, text="Insert:", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(side="left", padx=(0, 8))

        for var_name in ["FirstName", "LastName", "Company", "JobTitle", "Signature"]:
            tk.Button(
                vars_frame,
                text=f"{{{var_name}}}",
                command=lambda v=var_name: self._stay_insert_variable(v),
                bg=BG_CARD,
                fg=FG_TEXT,
                activebackground=BG_HOVER,
                activeforeground=FG_TEXT,
                relief="flat",
                font=FONT_CAPTION,
                cursor="hand2",
                padx=6,
                pady=2,
            ).pack(side="left", padx=(0, 4))

        bottom_frame = tk.Frame(email_tab, bg=BG_CARD)
        bottom_frame.pack(fill="x", padx=12, pady=(0, 12))

        self._stay_paused_var = tk.BooleanVar(value=False)

        tk.Button(
            bottom_frame,
            text="Save Email",
            command=self._stay_save_email,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=16,
            pady=6,
        ).pack(side="right")

        # ===== TAB 2: SCHEDULE =====
        schedule_tab = tk.Frame(self._stay_notebook, bg=BG_CARD)
        self._stay_notebook.add(schedule_tab, text="Schedule")

        schedule_content = tk.Frame(schedule_tab, bg=BG_CARD)
        schedule_content.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(schedule_content, text="Schedule your email", bg=BG_CARD, fg=FG_TEXT, font=FONT_SECTION).pack(anchor="w", pady=(0, 12))

        date_row = tk.Frame(schedule_content, bg=BG_CARD)
        date_row.pack(fill="x", pady=(0, 12))

        tk.Label(date_row, text="Send Date:", bg=BG_CARD, fg=FG_TEXT, font=FONT_BASE, width=12, anchor="w").pack(side="left")

        self._stay_schedule_date_var = tk.StringVar()
        if DateEntry is not None:
            self._stay_date_entry = DateEntry(
                date_row,
                textvariable=self._stay_schedule_date_var,
                date_pattern="yyyy-mm-dd",
                width=14,
                background=DARK_AQUA,
                foreground=FG_WHITE,
                headersbackground=DARK_AQUA,
                headersforeground=FG_WHITE,
                selectbackground=ACCENT,
                selectforeground=FG_WHITE,
                normalbackground=BG_ENTRY,
                normalforeground=FG_TEXT,
                weekendbackground=BG_ENTRY,
                weekendforeground=FG_TEXT,
                borderwidth=0,
            )
            self._stay_date_entry.pack(side="left")
        else:
            self._stay_date_entry = tk.Entry(
                date_row,
                textvariable=self._stay_schedule_date_var,
                bg=BG_ENTRY,
                fg=FG_TEXT,
                insertbackground=FG_TEXT,
                font=FONT_BASE,
                relief="flat",
                width=14,
                highlightthickness=1,
                highlightbackground=BORDER,
                highlightcolor=ACCENT,
            )
            self._stay_date_entry.pack(side="left", ipady=4)

        time_row = tk.Frame(schedule_content, bg=BG_CARD)
        time_row.pack(fill="x", pady=(0, 12))

        tk.Label(time_row, text="Send Time:", bg=BG_CARD, fg=FG_TEXT, font=FONT_BASE, width=12, anchor="w").pack(side="left")

        self._stay_schedule_time_var = tk.StringVar(value="9:00 AM")
        self._stay_time_combo = ttk.Combobox(
            time_row,
            textvariable=self._stay_schedule_time_var,
            values=TIME_OPTIONS,
            width=12,
            state="readonly",
            style="Dark.TCombobox",
        )
        self._stay_time_combo.pack(side="left")

        tk.Button(
            schedule_content,
            text="Save Schedule",
            command=self._stay_save_schedule,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=16,
            pady=6,
        ).pack(anchor="w", pady=(12, 0))

        # ===== TAB 3: PREVIEW AND LAUNCH =====
        launch_tab = tk.Frame(self._stay_notebook, bg=BG_CARD)
        self._stay_notebook.add(launch_tab, text="Launch")

        launch_content = tk.Frame(launch_tab, bg=BG_CARD)
        launch_content.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(launch_content, text="Send a test email", bg=BG_CARD, fg=FG_TEXT, font=FONT_SECTION).pack(anchor="w", pady=(0, 8))

        test_row = tk.Frame(launch_content, bg=BG_CARD)
        test_row.pack(fill="x", pady=(0, 8))

        tk.Label(test_row, text="Your email:", bg=BG_CARD, fg=FG_TEXT, font=FONT_BASE).pack(side="left", padx=(0, 8))

        self._stay_test_email_var = tk.StringVar()
        self._stay_test_email_entry = tk.Entry(
            test_row,
            textvariable=self._stay_test_email_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            font=FONT_BASE,
            relief="flat",
            width=25,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self._stay_test_email_entry.pack(side="left", ipady=4, padx=(0, 8))

        tk.Button(
            test_row,
            text="Send Test",
            command=self._stay_send_test_email,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=12,
            pady=4,
        ).pack(side="left")

        ttk.Separator(launch_content, orient="horizontal").pack(fill="x", pady=16)

        tk.Label(launch_content, text="Launch Campaign", bg=BG_CARD, fg=FG_TEXT, font=FONT_SECTION).pack(anchor="w", pady=(0, 8))

        self._stay_launch_summary = tk.Label(
            launch_content,
            text="",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=FONT_BASE,
            justify="left",
        )
        self._stay_launch_summary.pack(anchor="w", pady=(0, 12))

        tk.Button(
            launch_content,
            text="Launch Stay Connected",
            command=self._stay_launch,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_SECTION_TITLE,
            cursor="hand2",
            padx=20,
            pady=8,
        ).pack(anchor="w")

        # ===== TAB 4: CONTACTS =====
        contacts_tab = tk.Frame(self._stay_notebook, bg=BG_CARD)
        self._stay_notebook.add(contacts_tab, text="Contacts")

        contacts_header = tk.Frame(contacts_tab, bg=BG_CARD)
        contacts_header.pack(fill="x", padx=12, pady=(12, 8))

        self._stay_contact_count_label = tk.Label(
            contacts_header,
            text="0 contacts",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=FONT_BASE,
        )
        self._stay_contact_count_label.pack(side="left")

        tree_frame = tk.Frame(contacts_tab, bg=BG_CARD)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        columns = ("Email", "FirstName", "LastName", "Company", "JobTitle")
        self._stay_contacts_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )

        for col in columns:
            self._stay_contacts_tree.heading(col, text=col)
            self._stay_contacts_tree.column(col, width=120, minwidth=80)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._stay_contacts_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._stay_contacts_tree.xview)
        self._stay_contacts_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._stay_contacts_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        contact_btn_frame = tk.Frame(contacts_tab, bg=BG_CARD)
        contact_btn_frame.pack(fill="x", padx=12, pady=(0, 12))

        tk.Button(
            contact_btn_frame,
            text="Remove Selected",
            command=self._stay_remove_selected_contacts,
            bg=BG_CARD,
            fg=DANGER,
            activebackground=BG_HOVER,
            activeforeground=DANGER,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=8,
            pady=4,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            contact_btn_frame,
            text="Export to CSV",
            command=self._stay_export_contacts_csv,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=8,
            pady=4,
        ).pack(side="left")

    # ===== View Navigation =====

    def _stay_show_placeholder(self):
        """Show placeholder, hide overview and editor."""
        self._stay_overview_content.pack_forget()
        self._stay_editor_content.pack_forget()
        self._stay_placeholder.pack(fill="both", expand=True)
        self._stay_current_view = "placeholder"

    def _stay_show_overview(self):
        """Show overview, hide placeholder and editor."""
        self._stay_placeholder.pack_forget()
        self._stay_editor_content.pack_forget()
        self._stay_overview_content.pack(fill="both", expand=True)
        self._stay_current_view = "overview"
        self._stay_refresh_overview()

    def _stay_show_editor(self):
        """Show editor, hide placeholder and overview."""
        self._stay_placeholder.pack_forget()
        self._stay_overview_content.pack_forget()
        self._stay_editor_content.pack(fill="both", expand=True)
        self._stay_current_view = "editor"
        self._stay_refresh_editor()

    def _stay_show_contacts_from_overview(self):
        """Switch to editor and show Contacts tab."""
        self._stay_show_editor()
        self._stay_notebook.select(3)  # Contacts tab

    def _stay_view_contacts(self):
        """Switch to the Contacts tab in editor."""
        if self._stay_current_view != "editor":
            self._stay_show_editor()
        self._stay_notebook.select(3)

    def _stay_insert_variable(self, var_name: str):
        """Insert a variable token into the body text."""
        if hasattr(self, '_stay_body_text'):
            self._stay_body_text.insert(tk.INSERT, f"{{{var_name}}}")
            self._stay_body_text.focus_set()

    def _refresh_stay_connected(self):
        """Refresh the Stay Connected category list."""
        if hasattr(self, '_stay_category_listbox'):
            self._stay_category_listbox.delete(0, tk.END)
            idx = self._load_stay_index()
            for cat in idx["categories"]:
                self._stay_category_listbox.insert(tk.END, cat["name"])

    def _on_stay_category_selected(self, _event=None):
        """Handle category selection in listbox - shows Overview by default."""
        if not hasattr(self, '_stay_category_listbox'):
            return

        selection = self._stay_category_listbox.curselection()
        if not selection:
            return

        idx = self._load_stay_index()
        if selection[0] >= len(idx["categories"]):
            return

        cat_info = idx["categories"][selection[0]]
        self._stay_selected_category_id = cat_info["id"]

        # Reset launch button state
        self._stay_launch_enabled = True

        # Show overview (default view)
        self._stay_show_overview()

    def _stay_refresh_overview(self):
        """Refresh the Campaign Overview with current category data."""
        if not self._stay_selected_category_id:
            return

        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat:
            return

        # Header: name and status
        self._stay_overview_name.config(text=cat["name"])

        # Determine status
        paused = cat.get("paused", False)
        schedule = cat.get("schedule", {})
        last_launch = cat.get("last_launch", {})
        has_schedule = schedule.get("date") and schedule.get("time")

        if paused:
            status_text = "Paused"
            status_bg = FG_MUTED
        elif last_launch.get("date"):
            status_text = "Sent"
            status_bg = GOOD
        elif has_schedule:
            status_text = "Scheduled"
            status_bg = ACCENT
        else:
            status_text = "Draft"
            status_bg = FG_MUTED

        self._stay_overview_status.config(text=status_text, bg=status_bg)

        # Card 1: Last Email
        subject = cat.get("template", {}).get("subject", "").strip()
        self._stay_card_subject.config(text=subject if subject else "—")

        if last_launch.get("date"):
            sent_text = f"Sent: {last_launch['date']} @ {last_launch.get('time', '')}"
        else:
            sent_text = "Not sent yet"
        self._stay_card_sent.config(text=sent_text)

        # Card 2: Contacts
        contact_count = len(cat.get("contacts", []))
        self._stay_card_contacts.config(text=f"{contact_count} total")

        # Card 3: Next Send
        if paused:
            self._stay_card_next.config(text="Paused")
        elif has_schedule:
            self._stay_card_next.config(text=f"{schedule['date']} @ {schedule['time']}")
        else:
            self._stay_card_next.config(text="Not scheduled")

        # Update pause button text
        self._stay_pause_btn.config(text="Resume Campaign" if paused else "Pause Campaign")

        # Activity timeline
        self._stay_timeline_list.delete(0, tk.END)
        activities = cat.get("activity", [])
        if activities:
            for activity in reversed(activities[-10:]):  # Show last 10, newest first
                self._stay_timeline_list.insert(tk.END, f"  {activity}")
        else:
            self._stay_timeline_list.insert(tk.END, "  No activity yet")

    def _stay_refresh_editor(self):
        """Refresh the Edit Campaign view with current category data."""
        if not self._stay_selected_category_id:
            return

        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat:
            return

        # Header
        self._stay_editor_name.config(text=f"Edit: {cat['name']}")

        # Email fields
        self._stay_subject_var.set(cat.get("template", {}).get("subject", ""))
        self._stay_body_text.delete("1.0", tk.END)
        self._stay_body_text.insert("1.0", cat.get("template", {}).get("body", ""))
        self._stay_paused_var.set(cat.get("paused", False))

        # Schedule fields
        schedule = cat.get("schedule", {})
        self._stay_schedule_date_var.set(schedule.get("date", ""))
        self._stay_schedule_time_var.set(schedule.get("time", "9:00 AM"))

        # Launch summary
        self._stay_update_launch_summary(cat)

        # Contacts table
        self._stay_refresh_contacts_table(cat)

    def _stay_toggle_pause(self):
        """Toggle pause status for current campaign."""
        if not self._stay_selected_category_id:
            return

        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat:
            return

        cat["paused"] = not cat.get("paused", False)

        # Log activity
        action = "Campaign paused" if cat["paused"] else "Campaign resumed"
        self._stay_log_activity(cat, action)

        self._save_stay_category(self._stay_selected_category_id, cat)
        self._stay_refresh_overview()
        self._set_status(action, GOOD)

    def _stay_log_activity(self, cat: dict, message: str):
        """Add an activity entry to the category."""
        from datetime import datetime
        if "activity" not in cat:
            cat["activity"] = []
        timestamp = datetime.now().strftime("%b %d, %I:%M %p")
        cat["activity"].append(f"{timestamp} - {message}")

    def _stay_refresh_contacts_table(self, cat: dict = None):
        """Refresh the contacts treeview for the selected category."""
        if not hasattr(self, '_stay_contacts_tree'):
            return

        # Clear existing rows
        for item in self._stay_contacts_tree.get_children():
            self._stay_contacts_tree.delete(item)

        if cat is None and self._stay_selected_category_id:
            cat = self._load_stay_category(self._stay_selected_category_id)

        if not cat:
            return

        contacts = cat.get("contacts", [])
        self._stay_contact_count_label.config(text=f"{len(contacts)} contacts")

        for contact in contacts:
            data = contact.get("data", {})
            values = (
                data.get("Email") or data.get("Work Email") or contact.get("email_key", ""),
                data.get("FirstName", ""),
                data.get("LastName", ""),
                data.get("Company", ""),
                data.get("JobTitle", ""),
            )
            self._stay_contacts_tree.insert("", tk.END, values=values, tags=(contact.get("email_key", ""),))

    def _stay_update_launch_summary(self, cat: dict = None):
        """Update the launch summary text on Preview and Launch tab."""
        if not hasattr(self, '_stay_launch_summary'):
            return

        if cat is None and self._stay_selected_category_id:
            cat = self._load_stay_category(self._stay_selected_category_id)

        if not cat:
            self._stay_launch_summary.config(text="No category selected")
            return

        contact_count = len(cat.get("contacts", []))
        subject = cat.get("template", {}).get("subject", "").strip()
        schedule = cat.get("schedule", {})
        date_str = schedule.get("date", "")
        time_str = schedule.get("time", "")

        lines = []
        if subject:
            lines.append(f"Subject: {subject[:50]}{'...' if len(subject) > 50 else ''}")
        else:
            lines.append("Subject: (not set)")

        lines.append(f"Contacts: {contact_count}")

        if date_str and time_str:
            lines.append(f"Scheduled: {date_str} at {time_str}")
        else:
            lines.append("Scheduled: (not set)")

        self._stay_launch_summary.config(text="\n".join(lines))

    def _stay_save_email(self):
        """Save the email template (subject, body, pause status)."""
        if not self._stay_selected_category_id:
            return

        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat:
            return

        cat["template"]["subject"] = self._stay_subject_var.get()
        cat["template"]["body"] = self._stay_body_text.get("1.0", tk.END).rstrip()
        cat["paused"] = self._stay_paused_var.get()

        self._stay_log_activity(cat, "Email saved")
        self._save_stay_category(self._stay_selected_category_id, cat)
        self._stay_update_launch_summary(cat)
        self._stay_launch_enabled = True  # Re-enable launch on content change
        self._set_status(f"Email saved: {cat['name']}", GOOD)

    def _stay_save_schedule(self):
        """Save the schedule date and time."""
        if not self._stay_selected_category_id:
            return

        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat:
            return

        date_val = self._stay_schedule_date_var.get().strip()
        time_val = self._stay_schedule_time_var.get().strip()

        if not date_val:
            messagebox.showwarning("Missing Date", "Please select a send date.")
            return

        if not time_val:
            messagebox.showwarning("Missing Time", "Please select a send time.")
            return

        cat["schedule"] = {
            "date": date_val,
            "time": time_val,
        }

        self._stay_log_activity(cat, f"Schedule set: {date_val} @ {time_val}")
        self._save_stay_category(self._stay_selected_category_id, cat)
        self._stay_update_launch_summary(cat)
        self._stay_launch_enabled = True  # Re-enable launch on schedule change
        self._set_status(f"Schedule saved: {date_val} at {time_val}", GOOD)

    def _stay_send_test_email(self):
        """Send a test email for the current category."""
        if not self._stay_selected_category_id:
            messagebox.showwarning("No Category", "Please select a category first.")
            return

        test_email = self._stay_test_email_var.get().strip()
        if not test_email:
            messagebox.showerror("Missing Email", "Enter your email address to send a test.")
            return

        if not HAVE_OUTLOOK:
            messagebox.showerror("Outlook not available", "Outlook is not available on this machine.")
            return

        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat:
            return

        subject = cat.get("template", {}).get("subject", "").strip()
        body = cat.get("template", {}).get("body", "").strip()

        if not subject:
            messagebox.showwarning("Missing Subject", "Please enter a subject in the Build Email tab.")
            return

        if not body:
            messagebox.showwarning("Missing Body", "Please enter a body in the Build Email tab.")
            return

        # Get first contact for token merge (if any)
        contacts = cat.get("contacts", [])
        sig = getattr(self, "signature_text", "") or ""
        tokens = {}
        if contacts:
            first_contact = contacts[0].get("data", {})
            tokens = {
                "FirstName": first_contact.get("FirstName", ""),
                "LastName": first_contact.get("LastName", ""),
                "Company": first_contact.get("Company", ""),
                "JobTitle": first_contact.get("JobTitle", ""),
                "Signature": sig,
            }
        else:
            tokens = {
                "FirstName": "[FirstName]",
                "LastName": "[LastName]",
                "Company": "[Company]",
                "JobTitle": "[JobTitle]",
                "Signature": sig,
            }

        # Merge tokens
        merged_subject = merge_tokens(subject, tokens)
        merged_body = merge_tokens(body, tokens)

        # Ensure signature is in body
        merged_body = self._ensure_signature_in_body(merged_body)

        test_subject = f"[TEST] {merged_subject}"

        try:
            # For HTML bodies, skip normalize_text (it strips non-ASCII) but still fix smart quotes
            if is_html(merged_body):
                final_body = merged_body
            else:
                final_body = normalize_text(merged_body)
            send_preview_email(
                to_email=test_email,
                subject=normalize_text(test_subject),
                body=final_body,
            )
            # Log activity
            self._stay_log_activity(cat, f"Test email sent to {test_email}")
            self._save_stay_category(self._stay_selected_category_id, cat)
            messagebox.showinfo("Test Sent", f"Test email sent to {test_email}")
            self._set_status("Test email sent", GOOD)
        except Exception as e:
            messagebox.showerror("Send Failed", f"Failed to send test email:\n\n{e}")
            self._set_status("Test email failed", DANGER)

    def _stay_launch(self):
        """Launch Stay Connected - schedule emails for all contacts."""
        if not self._stay_selected_category_id:
            messagebox.showwarning("No Category", "Please select a category first.")
            return

        # Check if launch is disabled (already launched)
        if hasattr(self, '_stay_launch_enabled') and not self._stay_launch_enabled:
            messagebox.showinfo("Already Launched", "This email has already been launched.\n\nChange the date/time or email content to launch again.")
            return

        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat:
            return

        # Validate subject and body
        subject = cat.get("template", {}).get("subject", "").strip()
        body = cat.get("template", {}).get("body", "").strip()

        if not subject:
            messagebox.showerror("Missing Subject", "Please enter a subject in the Build Email tab.")
            return

        if not body:
            messagebox.showerror("Missing Body", "Please enter a body in the Build Email tab.")
            return

        # Validate schedule
        schedule = cat.get("schedule", {})
        date_str = schedule.get("date", "").strip()
        time_str = schedule.get("time", "").strip()

        if not date_str:
            messagebox.showerror("Missing Schedule", "Please set a send date in the Schedule tab.")
            return

        if not time_str:
            messagebox.showerror("Missing Schedule", "Please set a send time in the Schedule tab.")
            return

        # Validate contacts
        contacts = cat.get("contacts", [])
        if not contacts:
            messagebox.showerror("No Contacts", "This category has no contacts.\n\nAdd contacts after completing a campaign.")
            return

        # Check if paused
        if cat.get("paused", False):
            messagebox.showwarning("Category Paused", "This category is paused.\n\nUncheck 'Pause this category' in the Build Email tab to launch.")
            return

        if not HAVE_OUTLOOK:
            messagebox.showerror("Outlook not available", "Outlook is not available.\n\nInstall pywin32 and ensure Outlook is installed.")
            return

        # Confirm launch
        ok = messagebox.askyesno(
            "Launch Stay Connected",
            f"Schedule email to {len(contacts)} contact(s)?\n\n"
            f"Subject: {subject[:50]}{'...' if len(subject) > 50 else ''}\n"
            f"Send: {date_str} at {time_str}\n\n"
            "Note: Outlook Classic must be open.\n\n"
            "Proceed?"
        )
        if not ok:
            return

        # Create temporary CSV with contacts
        import tempfile
        try:
            # Build CSV content
            all_keys = set()
            for contact in contacts:
                all_keys.update(contact.get("data", {}).keys())

            # Ensure email column exists
            priority = ["Email", "Work Email", "FirstName", "LastName", "Company", "JobTitle"]
            columns = [k for k in priority if k in all_keys]
            columns += sorted(k for k in all_keys if k not in priority)

            # Write temp CSV
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
                temp_path = f.name
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                for contact in contacts:
                    writer.writerow(contact.get("data", {}))

            # Build schedule (single email)
            body_with_signature = self._ensure_signature_in_body(body)
            email_schedule = [{
                "subject": subject,
                "body": body_with_signature,
                "date": date_str,
                "time": time_str,
                "attachments": [],
            }]

            # Run via core
            fourdrip_core.run_4drip(
                schedule=email_schedule,
                contacts_path=temp_path,
                attachments_path=None,
                send_emails=True,
            )

            # Record last launch info
            cat["last_launch"] = {
                "date": date_str,
                "time": time_str,
                "contacts": len(contacts),
            }

            # Log activity and save
            self._stay_log_activity(cat, f"Campaign launched: {len(contacts)} emails scheduled for {date_str} @ {time_str}")
            self._save_stay_category(self._stay_selected_category_id, cat)

            # Success - disable launch button to prevent double-send
            self._stay_launch_enabled = False
            self._set_status(f"Stay Connected launched: {len(contacts)} emails scheduled", GOOD)
            messagebox.showinfo(
                "Launched",
                f"Email scheduled for {date_str} at {time_str}\n\n"
                f"Sending to {len(contacts)} contact(s)."
            )

        except Exception as e:
            self._set_status("Launch failed", DANGER)
            messagebox.showerror("Launch Failed", f"Failed to launch Stay Connected:\n\n{e}")

        finally:
            # Clean up temp file
            try:
                if 'temp_path' in locals():
                    os.unlink(temp_path)
            except Exception:
                pass

    def _stay_remove_selected_contacts(self):
        """Remove selected contacts from the current category."""
        if not self._stay_selected_category_id:
            return

        selection = self._stay_contacts_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select contacts to remove.")
            return

        # Get email keys to remove
        emails_to_remove = set()
        for item in selection:
            tags = self._stay_contacts_tree.item(item, "tags")
            if tags:
                emails_to_remove.add(tags[0])

        if not emails_to_remove:
            return

        if not messagebox.askyesno("Remove Contacts", f"Remove {len(emails_to_remove)} contact(s) from this category?"):
            return

        # Load category, filter contacts, save
        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat:
            return

        cat["contacts"] = [c for c in cat["contacts"] if c.get("email_key") not in emails_to_remove]
        self._save_stay_category(self._stay_selected_category_id, cat)

        # Refresh table and header
        self._stay_refresh_contacts_table(cat)
        self._stay_header_contact_count.config(text=f"Contacts: {len(cat['contacts'])}")
        self._stay_update_launch_summary(cat)
        self._set_status(f"Removed {len(emails_to_remove)} contact(s)", GOOD)

    def _stay_export_contacts_csv(self):
        """Export category contacts to a CSV file."""
        if not self._stay_selected_category_id:
            return

        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat or not cat.get("contacts"):
            messagebox.showwarning("No Contacts", "No contacts to export.")
            return

        # Ask for save location
        path = filedialog.asksaveasfilename(
            title="Export Contacts",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"{cat['name']}_contacts.csv",
        )
        if not path:
            return

        try:
            # Collect all unique keys from contact data
            all_keys = set()
            for contact in cat["contacts"]:
                all_keys.update(contact.get("data", {}).keys())

            # Prioritize common columns
            priority = ["Email", "Work Email", "FirstName", "LastName", "Company", "JobTitle"]
            columns = [k for k in priority if k in all_keys]
            columns += sorted(k for k in all_keys if k not in priority)

            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                for contact in cat["contacts"]:
                    writer.writerow(contact.get("data", {}))

            messagebox.showinfo("Exported", f"Exported {len(cat['contacts'])} contacts to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def _stay_new_category(self):
        """Create a new Stay Connected category."""
        name = themed_askstring(self, "New Category", "Enter category name:")
        if not name:
            return

        name = name.strip()
        if not name:
            return

        try:
            self._create_stay_category(name)
            self._refresh_stay_connected()
            self._set_status(f"Category created: {name}", GOOD)
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def _stay_rename_category(self):
        """Rename the selected Stay Connected category."""
        if not self._stay_selected_category_id:
            messagebox.showwarning("No Selection", "Please select a category to rename.")
            return

        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat:
            return

        new_name = themed_askstring(self, "Rename Category", "Enter new name:", cat["name"])
        if not new_name:
            return

        new_name = new_name.strip()
        if not new_name:
            return

        try:
            self._rename_stay_category(self._stay_selected_category_id, new_name)
            self._refresh_stay_connected()
            self._stay_cat_name_label.config(text=new_name)
            self._set_status(f"Category renamed: {new_name}", GOOD)
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def _stay_delete_category(self):
        """Delete the selected Stay Connected category."""
        if not self._stay_selected_category_id:
            messagebox.showwarning("No Selection", "Please select a category to delete.")
            return

        cat = self._load_stay_category(self._stay_selected_category_id)
        if not cat:
            return

        if not messagebox.askyesno("Delete Category", f"Delete '{cat['name']}'?\n\nThis will remove all contacts in this category."):
            return

        self._delete_stay_category(self._stay_selected_category_id)
        self._stay_selected_category_id = None

        # Hide editor, show placeholder
        self._stay_editor_content.pack_forget()
        self._stay_placeholder.pack(fill="both", expand=True)

        self._refresh_stay_connected()
        self._set_status("Category deleted", GOOD)

    # ============================================
    # Nurture Lists - Screen Builder
    # ============================================
    def _build_nurture_campaigns_screen(self, parent):
        """Build the Nurture Lists screen with two-column layout - Campaign Detail Page design."""
        # State tracking
        self._nurture_selected_campaign_id = None
        self._nurture_attachments = []

        # Main container
        container = tk.Frame(parent, bg=BG_ROOT)
        container.pack(fill="both", expand=True)

        # Two-column layout
        container.columnconfigure(0, weight=0, minsize=220)
        container.columnconfigure(1, weight=3)
        container.rowconfigure(0, weight=1)

        # ========== LEFT PANEL: Campaign List ==========
        left_panel = tk.Frame(container, bg=BG_SIDEBAR, width=220)
        left_panel.grid(row=0, column=0, sticky="nsew")
        left_panel.grid_propagate(False)

        # Header
        tk.Label(
            left_panel,
            text="Lists",
            bg=BG_SIDEBAR,
            fg=ACCENT,
            font=FONT_SECTION,
        ).pack(anchor="w", padx=12, pady=(12, 8))

        # Campaign listbox
        listbox_frame = tk.Frame(left_panel, bg=BG_SIDEBAR)
        listbox_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._nurture_campaign_listbox = tk.Listbox(
            listbox_frame,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            selectbackground=ACCENT,
            selectforeground=FG_WHITE,
            highlightthickness=0,
            borderwidth=0,
            font=FONT_BASE,
            activestyle="none",
            exportselection=False,
        )
        self._nurture_campaign_listbox.pack(fill="both", expand=True)
        self._nurture_campaign_listbox.bind("<<ListboxSelect>>", self._on_nurture_campaign_selected)

        # Buttons row (New, Rename, Delete)
        btn_row = tk.Frame(left_panel, bg=BG_SIDEBAR)
        btn_row.pack(fill="x", padx=8, pady=(0, 12))

        make_button(btn_row, text="New", command=self._nurture_new_campaign, variant="primary", size="sm").pack(side="left", padx=(0, 4))
        make_button(btn_row, text="Rename", command=self._nurture_rename_campaign_btn, variant="ghost", size="sm").pack(side="left", padx=(0, 4))
        make_button(btn_row, text="Delete", command=self._nurture_delete_campaign_btn, variant="danger", size="sm").pack(side="left")

        # ========== RIGHT PANEL: Campaign Detail ==========
        right_panel = tk.Frame(container, bg=BG_ROOT)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(1, 0))

        self._nurture_content_area = tk.Frame(right_panel, bg=BG_ROOT)
        self._nurture_content_area.pack(fill="both", expand=True)

        # Build placeholder and detail views
        self._build_nurture_placeholder()
        self._build_nurture_detail_page()

        # Show placeholder by default
        self._nurture_show_placeholder()

        # Initial refresh
        self._refresh_nurture_campaigns()

    def _build_nurture_placeholder(self):
        """Build the placeholder view shown when no campaign is selected."""
        self._nurture_placeholder = tk.Frame(self._nurture_content_area, bg=BG_ROOT)

        empty_frame = tk.Frame(self._nurture_placeholder, bg=BG_ROOT)
        empty_frame.pack(expand=True)

        tk.Label(
            empty_frame,
            text="Select a list to see contacts and activity.",
            bg=BG_ROOT,
            fg=FG_MUTED,
            font=FONT_SECTION,
        ).pack()

    def _build_nurture_detail_page(self):
        """Build the Campaign Detail Page with header bar + Messages/Contacts tabs."""
        self._nurture_detail_page = tk.Frame(self._nurture_content_area, bg=BG_ROOT)

        # ===== COMPACT HEADER BAR =====
        self._build_nurture_header_bar()

        # ===== TWO-TAB NOTEBOOK: Messages | Contacts =====
        self._nurture_tabs = ttk.Notebook(self._nurture_detail_page)
        self._nurture_tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # --- Messages Tab ---
        messages_tab = tk.Frame(self._nurture_tabs, bg=BG_ROOT)
        self._nurture_tabs.add(messages_tab, text="  Messages  ")
        self._build_nurture_messages_tab(messages_tab)

        # --- Contacts Tab ---
        contacts_tab = tk.Frame(self._nurture_tabs, bg=BG_ROOT)
        self._nurture_tabs.add(contacts_tab, text="  Contacts  ")
        self._build_nurture_contacts_tab(contacts_tab)

    def _build_nurture_header_bar(self):
        """Compact header bar with campaign name, status badge, and action buttons."""
        header = tk.Frame(self._nurture_detail_page, bg=BG_CARD)
        header.pack(fill="x", padx=8, pady=(8, 4))

        content = tk.Frame(header, bg=BG_CARD)
        content.pack(fill="x", padx=12, pady=10)

        # Left: Campaign name + status badge + stats
        info = tk.Frame(content, bg=BG_CARD)
        info.pack(side="left", fill="x", expand=True)

        self._nurture_overview_name = tk.Label(
            info, text="—", bg=BG_CARD, fg=FG_TEXT,
            font=FONT_SECTION,
        )
        self._nurture_overview_name.pack(side="left")

        # Status pill badge
        self._nurture_status_badge = tk.Label(
            info, text="Draft", bg=BORDER, fg=FG_MUTED,
            font=FONT_CAPTION, padx=8, pady=2,
        )
        self._nurture_status_badge.pack(side="left", padx=(10, 0))

        tk.Label(info, text="  |  ", bg=BG_CARD, fg=BORDER, font=FONT_BASE).pack(side="left")

        self._nurture_overview_contacts = tk.Label(
            info, text="0 contacts", bg=BG_CARD, fg=FG_MUTED,
            font=FONT_BASE,
        )
        self._nurture_overview_contacts.pack(side="left")

        tk.Label(info, text="  |  ", bg=BG_CARD, fg=BORDER, font=FONT_BASE).pack(side="left")

        self._nurture_overview_last_activity = tk.Label(
            info, text="No activity", bg=BG_CARD, fg=FG_MUTED,
            font=FONT_BASE,
        )
        self._nurture_overview_last_activity.pack(side="left")

        # Right: Send button
        btn_frame = tk.Frame(content, bg=BG_CARD)
        btn_frame.pack(side="right")

        # Hidden pause/resume for compatibility
        self._nurture_pause_btn = tk.Frame(btn_frame)
        self._nurture_resume_btn = tk.Frame(btn_frame)

        self._nurture_send_btn = make_button(btn_frame, text="Send Email", command=self._nurture_save_updates, variant="success", size="sm")
        self._nurture_send_btn.pack(side="left", padx=(0, 6))

        # Hidden labels for compatibility
        self._nurture_overview_status = tk.Label(content, text="Draft")
        self._nurture_overview_sent = tk.Label(content, text="0")
        self._nurture_overview_next_send = tk.Label(content, text="—")

    def _create_overview_field(self, parent, label, value):
        """Create a labeled field for the overview section. Returns the value label."""
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x", pady=2)

        tk.Label(
            row,
            text=f"{label}:",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=FONT_BASE,
            width=15,
            anchor="w",
        ).pack(side="left")

        value_label = tk.Label(
            row,
            text=value,
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_SECTION_TITLE,
            anchor="w",
        )
        value_label.pack(side="left", fill="x", expand=True)

        return value_label

    def _build_nurture_messages_tab(self, parent):
        """Build the Messages tab — single email editor mirroring Build Emails."""
        # Initialize message data (single email)
        self._nurture_msg_name_vars = []
        self._nurture_msg_subject_vars = []
        self._nurture_msg_body_widgets = []
        self._nurture_msg_date_vars = []
        self._nurture_msg_time_vars = []
        self._nurture_msg_attachments = []
        self._nurture_msg_cards = []
        self._nurture_msg_expanded_index = 0

        name_var = tk.StringVar(value="")
        self._nurture_msg_name_vars.append(name_var)

        subject_var = tk.StringVar(value="")
        self._nurture_msg_subject_vars.append(subject_var)

        date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self._nurture_msg_date_vars.append(date_var)

        time_var = tk.StringVar(value="09:00 AM")
        self._nurture_msg_time_vars.append(time_var)

        attachments_list = []
        self._nurture_msg_attachments.append(attachments_list)

        # Main card
        card = tk.Frame(parent, bg=BG_CARD)
        card.pack(fill="both", expand=True, padx=12, pady=12)

        inner = tk.Frame(card, bg=BG_CARD)
        inner.pack(fill="both", expand=True, padx=16, pady=14)

        # Row 1: Send Date + Send Time at top
        sched_row = tk.Frame(inner, bg=BG_CARD)
        sched_row.pack(fill="x", pady=(0, 12))

        dc = tk.Frame(sched_row, bg=BG_CARD)
        dc.pack(side="left", padx=(0, 16))
        tk.Label(dc, text="Send Date", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        if DateEntry is not None:
            DateEntry(
                dc, textvariable=date_var, date_pattern="yyyy-mm-dd", style="Dark.DateEntry",
                background=BG_ENTRY, foreground=FG_TEXT, bordercolor=BORDER, width=12,
            ).pack(pady=(4, 0))
        else:
            tk.Entry(
                dc, textvariable=date_var, bg=BG_ENTRY, fg=FG_TEXT, relief="flat",
                font=FONT_BASE, width=12, highlightthickness=1, highlightbackground=BORDER_MEDIUM,
            ).pack(pady=(4, 0))

        tc = tk.Frame(sched_row, bg=BG_CARD)
        tc.pack(side="left", padx=(0, 16))
        tk.Label(tc, text="Send Time", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        ttk.Combobox(
            tc, textvariable=time_var, values=TIME_OPTIONS,
            width=10, state="readonly", style="Dark.TCombobox",
        ).pack(pady=(4, 0))

        # Attachments (same row)
        ac = tk.Frame(sched_row, bg=BG_CARD)
        ac.pack(side="left", padx=(16, 0))
        tk.Label(ac, text="Attachments", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        ar = tk.Frame(ac, bg=BG_CARD)
        ar.pack(fill="x", pady=(4, 0))

        self._nurture_attach_label = tk.Label(ar, text="None", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL)
        self._nurture_attach_label.pack(side="left", padx=(0, 8))

        def _add_attach():
            files = filedialog.askopenfilenames(title="Select Attachment(s)", filetypes=[
                ("All files", "*.*"), ("PDF files", "*.pdf"),
                ("Word documents", "*.docx;*.doc"), ("Excel files", "*.xlsx;*.xls"),
            ])
            if files:
                for f in files:
                    if f not in attachments_list:
                        attachments_list.append(f)
                if attachments_list:
                    names = [Path(f).name for f in attachments_list[:2]]
                    display = ", ".join(names)
                    if len(attachments_list) > 2:
                        display += f" +{len(attachments_list) - 2} more"
                    self._nurture_attach_label.config(text=display, fg=GOOD)

        def _clear_attach():
            attachments_list.clear()
            self._nurture_attach_label.config(text="None", fg=FG_MUTED)

        tk.Button(ar, text="Add", command=_add_attach, bg=BG_CARD, fg=FG_TEXT,
                  activebackground=BG_HOVER, relief="flat", font=FONT_SMALL,
                  padx=6, pady=2, cursor="hand2").pack(side="left", padx=(0, 4))
        tk.Button(ar, text="Clear", command=_clear_attach, bg=BG_CARD, fg=FG_MUTED,
                  activebackground=BG_HOVER, activeforeground=DANGER, relief="flat",
                  font=FONT_SMALL, padx=4, pady=2, cursor="hand2").pack(side="left")

        # Row 2: Name + Subject (mirrors Build Emails)
        fields_row = tk.Frame(inner, bg=BG_CARD)
        fields_row.pack(fill="x", pady=(0, 8))
        fields_row.columnconfigure(1, weight=1)

        tk.Label(fields_row, text="Name", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).grid(row=0, column=0, sticky="w", padx=(0, 12))
        tk.Entry(
            fields_row, textvariable=name_var, bg=BG_ENTRY, fg=FG_TEXT, insertbackground=FG_TEXT,
            relief="flat", font=FONT_BASE, width=18,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        ).grid(row=1, column=0, sticky="w", padx=(0, 12))

        tk.Label(fields_row, text="Subject", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).grid(row=0, column=1, sticky="w")
        subject_entry = tk.Entry(
            fields_row, textvariable=subject_var, bg=BG_ENTRY, fg=FG_TEXT, insertbackground=FG_TEXT,
            relief="flat", font=FONT_BASE,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        )
        subject_entry.grid(row=1, column=1, sticky="ew")

        # + Variable button
        body_ref = [None]
        tk.Button(
            fields_row, text="+ Variable",
            command=lambda: self._nurture_show_variable_popup(subject_entry, body_ref),
            bg=BG_CARD, fg=FG_MUTED, activebackground=BG_HOVER, activeforeground=FG_TEXT,
            relief="flat", font=FONT_SMALL, padx=6, pady=3, cursor="hand2", bd=0,
        ).grid(row=1, column=2, sticky="e", padx=(12, 0))

        # Row 3: Body text editor
        body_text = tk.Text(
            inner, bg=BG_ENTRY, fg=FG_TEXT, insertbackground=FG_TEXT,
            relief="flat", font=FONT_BASE, wrap="word", height=14,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        )
        body_text.pack(fill="both", expand=True, pady=(0, 8))
        self._nurture_msg_body_widgets.append(body_text)
        body_ref[0] = body_text

        # Store card reference for compatibility
        self._nurture_msg_cards.append((card, inner, None))

    def _nurture_create_message_card(self, index: int, name: str = "", subject: str = "", body: str = ""):
        """Create an accordion-style message card (collapsed by default)."""
        default_name = name if name else f"Message {index + 1}"
        name_var = tk.StringVar(value=default_name)
        self._nurture_msg_name_vars.append(name_var)

        subject_var = tk.StringVar(value=subject)
        self._nurture_msg_subject_vars.append(subject_var)

        date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self._nurture_msg_date_vars.append(date_var)

        time_var = tk.StringVar(value="09:00 AM")
        self._nurture_msg_time_vars.append(time_var)

        attachments_list = []
        self._nurture_msg_attachments.append(attachments_list)

        card_index = len(self._nurture_msg_cards)

        # --- Card Container ---
        card = tk.Frame(self._nurture_cards_inner, bg=BG_CARD, highlightthickness=0)
        card.pack(fill="x", pady=(0, 6))

        # Colored accent bar on left via a top accent line
        accent_colors = [ACCENT, GOOD, "#8B5CF6", WARN, "#EC4899", "#06B6D4", "#F97316"]
        accent_color = accent_colors[card_index % len(accent_colors)]
        tk.Frame(card, bg=accent_color, height=3).pack(fill="x")

        # --- COLLAPSED HEADER (always visible, clickable) ---
        header = tk.Frame(card, bg=BG_CARD, cursor="hand2")
        header.pack(fill="x", padx=14, pady=(8, 8))

        # Arrow indicator
        arrow_label = tk.Label(
            header, text="\u25B8", bg=BG_CARD, fg=FG_MUTED,
            font=FONT_BASE, cursor="hand2",
        )
        arrow_label.pack(side="left", padx=(0, 8))

        # Message number badge
        num_label = tk.Label(
            header, text=str(card_index + 1), bg=accent_color, fg="white",
            font=FONT_CAPTION, padx=6, pady=1,
        )
        num_label.pack(side="left", padx=(0, 10))

        # Name (bold)
        name_display = tk.Label(
            header, textvariable=name_var, bg=BG_CARD, fg=FG_TEXT,
            font=FONT_BUTTON, cursor="hand2",
        )
        name_display.pack(side="left", padx=(0, 12))

        # Subject (muted)
        subj_display = tk.Label(
            header, textvariable=subject_var, bg=BG_CARD, fg=FG_MUTED,
            font=FONT_SMALL, cursor="hand2",
        )
        subj_display.pack(side="left", padx=(0, 12))

        # Schedule info (right side)
        schedule_display = tk.Label(
            header, text="", bg=BG_CARD, fg=FG_MUTED,
            font=FONT_SMALL, cursor="hand2",
        )
        schedule_display.pack(side="right")

        def _update_schedule_display(*_):
            d = date_var.get()
            t = time_var.get()
            schedule_display.configure(text=f"{d}  {t}")
        date_var.trace_add("write", _update_schedule_display)
        time_var.trace_add("write", _update_schedule_display)
        _update_schedule_display()

        # --- EXPANDED EDITOR (hidden by default) ---
        editor = tk.Frame(card, bg=BG_CARD)

        editor_inner = tk.Frame(editor, bg=BG_CARD)
        editor_inner.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        # Row 1: Name + Subject fields
        fields_row = tk.Frame(editor_inner, bg=BG_CARD)
        fields_row.pack(fill="x", pady=(0, 8))
        fields_row.columnconfigure(1, weight=1)

        tk.Label(fields_row, text="Name", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).grid(row=0, column=0, sticky="w", padx=(0, 12))
        tk.Entry(
            fields_row, textvariable=name_var, bg=BG_ENTRY, fg=FG_TEXT, insertbackground=FG_TEXT,
            relief="flat", font=FONT_BASE, width=18,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        ).grid(row=1, column=0, sticky="w", padx=(0, 12))

        tk.Label(fields_row, text="Subject", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).grid(row=0, column=1, sticky="w")
        subject_entry = tk.Entry(
            fields_row, textvariable=subject_var, bg=BG_ENTRY, fg=FG_TEXT, insertbackground=FG_TEXT,
            relief="flat", font=FONT_BASE,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        )
        subject_entry.grid(row=1, column=1, sticky="ew")

        body_ref = [None]

        # Action buttons inline with fields
        actions = tk.Frame(fields_row, bg=BG_CARD)
        actions.grid(row=1, column=2, sticky="e", padx=(12, 0))

        tk.Button(
            actions, text="+ Variable",
            command=lambda se=subject_entry, br=body_ref: self._nurture_show_variable_popup(se, br),
            bg=BG_CARD, fg=FG_MUTED, activebackground=BG_HOVER, activeforeground=FG_TEXT,
            relief="flat", font=FONT_SMALL, padx=6, pady=3, cursor="hand2", bd=0,
        ).pack(side="left", padx=(0, 4))

        tk.Button(
            actions, text="Delete",
            command=lambda idx=card_index: self._nurture_delete_message_card(idx),
            bg=BG_CARD, fg=DANGER, activebackground=BG_CARD, activeforeground=DANGER,
            relief="flat", font=FONT_SMALL, padx=6, pady=3, cursor="hand2", bd=0,
        ).pack(side="left")

        # Row 2: Body editor
        body_text = tk.Text(
            editor_inner, bg=BG_ENTRY, fg=FG_TEXT, insertbackground=FG_TEXT,
            relief="flat", font=FONT_BASE, wrap="word", height=12,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        )
        body_text.pack(fill="both", expand=True, pady=(0, 8))
        if body:
            body_text.insert("1.0", body)
        self._nurture_msg_body_widgets.append(body_text)
        body_ref[0] = body_text

        # Row 3: Schedule (Date + Time + Attachments)
        sched = tk.Frame(editor_inner, bg=BG_CARD)
        sched.pack(fill="x")

        # Date
        dc = tk.Frame(sched, bg=BG_CARD)
        dc.pack(side="left", padx=(0, 16))
        tk.Label(dc, text="Send Date", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        if DateEntry is not None:
            DateEntry(
                dc, textvariable=date_var, date_pattern="yyyy-mm-dd", style="Dark.DateEntry",
                background=BG_ENTRY, foreground=FG_TEXT, bordercolor=BORDER, width=12,
            ).pack(pady=(4, 0))
        else:
            tk.Entry(
                dc, textvariable=date_var, bg=BG_ENTRY, fg=FG_TEXT, relief="flat",
                font=FONT_BASE, width=12, highlightthickness=1, highlightbackground=BORDER_MEDIUM,
            ).pack(pady=(4, 0))

        # Time
        tc = tk.Frame(sched, bg=BG_CARD)
        tc.pack(side="left", padx=(0, 16))
        tk.Label(tc, text="Send Time", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        ttk.Combobox(
            tc, textvariable=time_var, values=TIME_OPTIONS,
            width=10, state="readonly", style="Dark.TCombobox",
        ).pack(pady=(4, 0))

        # Attachments
        ac = tk.Frame(sched, bg=BG_CARD)
        ac.pack(side="left", padx=(16, 0))
        tk.Label(ac, text="Attachments", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")

        ar = tk.Frame(ac, bg=BG_CARD)
        ar.pack(fill="x", pady=(4, 0))

        attach_label = tk.Label(ar, text="None", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL)
        attach_label.pack(side="left", padx=(0, 8))

        def _add_attach():
            files = filedialog.askopenfilenames(title="Select Attachment(s)", filetypes=[
                ("All files", "*.*"), ("PDF files", "*.pdf"),
                ("Word documents", "*.docx;*.doc"), ("Excel files", "*.xlsx;*.xls"),
            ])
            if files:
                for f in files:
                    if f not in attachments_list:
                        attachments_list.append(f)
                if attachments_list:
                    names = [Path(f).name for f in attachments_list[:2]]
                    display = ", ".join(names)
                    if len(attachments_list) > 2:
                        display += f" +{len(attachments_list) - 2} more"
                    attach_label.config(text=display, fg=GOOD)

        def _clear_attach():
            attachments_list.clear()
            attach_label.config(text="None", fg=FG_MUTED)

        tk.Button(ar, text="Add", command=_add_attach, bg=BG_CARD, fg=FG_TEXT,
                  activebackground=BG_HOVER, relief="flat", font=FONT_SMALL,
                  padx=6, pady=2, cursor="hand2").pack(side="left", padx=(0, 4))
        tk.Button(ar, text="Clear", command=_clear_attach, bg=BG_CARD, fg=FG_MUTED,
                  activebackground=BG_HOVER, activeforeground=DANGER, relief="flat",
                  font=FONT_SMALL, padx=4, pady=2, cursor="hand2").pack(side="left")

        # Store card references
        self._nurture_msg_cards.append((card, editor, arrow_label))

        # Click to toggle
        def _toggle(evt=None, ci=card_index):
            self._nurture_toggle_card(ci)

        for w in [header, arrow_label, name_display, subj_display, num_label, schedule_display]:
            w.bind("<Button-1>", _toggle)

        return body_text

    def _nurture_toggle_card(self, index):
        """Toggle accordion card - expand clicked, collapse others."""
        for i, (card, editor, arrow) in enumerate(self._nurture_msg_cards):
            if i == index and self._nurture_msg_expanded_index != index:
                # Expand this card
                editor.pack(fill="x", after=card.winfo_children()[1])  # after header
                arrow.configure(text="\u25BE")
            else:
                # Collapse
                editor.pack_forget()
                arrow.configure(text="\u25B8")

        if self._nurture_msg_expanded_index == index:
            self._nurture_msg_expanded_index = -1  # collapse all
        else:
            self._nurture_msg_expanded_index = index

    def _nurture_add_message_tab(self):
        """Add a new message tab (legacy compat)."""
        self._nurture_add_message_card()

    def _nurture_add_message_card(self):
        """Add a new accordion message card and expand it."""
        index = len(self._nurture_msg_name_vars)
        self._nurture_create_message_card(index)
        self._nurture_toggle_card(index)

    def _nurture_save_template(self):
        """Save current messages as a template."""
        if not self._nurture_msg_name_vars:
            messagebox.showwarning("No Messages", "No messages to save.")
            return

        # Collect all messages
        messages = []
        for i in range(len(self._nurture_msg_name_vars)):
            try:
                messages.append({
                    "name": self._nurture_msg_name_vars[i].get(),
                    "subject": self._nurture_msg_subject_vars[i].get(),
                    "body": self._nurture_msg_body_widgets[i].get("1.0", "end").rstrip(),
                })
            except Exception:
                pass

        if not messages:
            messagebox.showwarning("No Messages", "No messages to save.")
            return

        # Ask for template name
        template_name = themed_askstring(self, "Save Template", "Enter a name for this template:", "My Template")
        if not template_name or not template_name.strip():
            return

        template_name = template_name.strip()

        # Save to templates directory
        templates_dir = USER_DIR / "nurture_templates"
        templates_dir.mkdir(parents=True, exist_ok=True)

        template_file = templates_dir / f"{template_name}.json"

        try:
            with template_file.open("w", encoding="utf-8") as f:
                json.dump({"name": template_name, "messages": messages}, f, indent=2)

            self._set_status(f"Template '{template_name}' saved", GOOD)
            messagebox.showinfo("Saved", f"Template '{template_name}' saved successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save template:\n{e}")

    def _nurture_load_template(self):
        """Load messages from a saved template."""
        templates_dir = USER_DIR / "nurture_templates"
        templates_dir.mkdir(parents=True, exist_ok=True)

        # Get list of templates
        templates = list(templates_dir.glob("*.json"))
        if not templates:
            messagebox.showinfo("No Templates", "No saved templates found.\n\nSave a template first using 'Save Template'.")
            return

        # Create selection popup
        popup = tk.Toplevel(self)
        popup.title("Load Template")
        popup.transient(self)
        popup.grab_set()

        # Center on parent
        popup.geometry("350x400")
        x = self.winfo_x() + (self.winfo_width() - 350) // 2
        y = self.winfo_y() + (self.winfo_height() - 400) // 2
        popup.geometry(f"+{x}+{y}")
        popup.configure(bg=BG_CARD)

        tk.Label(
            popup,
            text="Select a template to load:",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_SECTION_TITLE,
        ).pack(anchor="w", padx=16, pady=(16, 8))

        # Listbox for templates
        listbox_frame = tk.Frame(popup, bg=BG_CARD)
        listbox_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        listbox = tk.Listbox(
            listbox_frame,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            selectbackground=ACCENT,
            selectforeground=FG_WHITE,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            font=FONT_BASE,
        )
        listbox.pack(fill="both", expand=True)

        template_files = {}
        for t in sorted(templates, key=lambda x: x.stem):
            listbox.insert("end", t.stem)
            template_files[t.stem] = t

        def load_selected():
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("Select Template", "Please select a template.")
                return

            template_name = listbox.get(sel[0])
            template_file = template_files.get(template_name)

            try:
                with template_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                messages = data.get("messages", [])
                if not messages:
                    messagebox.showwarning("Empty Template", "This template has no messages.")
                    return

                # Clear existing accordion cards
                for card, editor, arrow in self._nurture_msg_cards:
                    card.destroy()

                self._nurture_msg_name_vars = []
                self._nurture_msg_subject_vars = []
                self._nurture_msg_body_widgets = []
                self._nurture_msg_date_vars = []
                self._nurture_msg_time_vars = []
                self._nurture_msg_attachments = []
                self._nurture_msg_cards = []
                self._nurture_msg_expanded_index = -1

                # Load messages from template
                for i, msg in enumerate(messages):
                    self._nurture_create_message_card(
                        i,
                        name=msg.get("name", f"Message {i+1}"),
                        subject=msg.get("subject", ""),
                        body=msg.get("body", "")
                    )

                popup.destroy()
                self._set_status(f"Template '{template_name}' loaded", GOOD)

            except Exception as e:
                messagebox.showerror("Error", f"Failed to load template:\n{e}")

        def delete_selected():
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("Select Template", "Please select a template to delete.")
                return

            template_name = listbox.get(sel[0])
            if not messagebox.askyesno("Delete Template", f"Delete template '{template_name}'?"):
                return

            template_file = template_files.get(template_name)
            try:
                template_file.unlink()
                listbox.delete(sel[0])
                del template_files[template_name]
                self._set_status(f"Template deleted", WARN)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete template:\n{e}")

        # Buttons
        btn_frame = tk.Frame(popup, bg=BG_CARD)
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))

        tk.Button(
            btn_frame,
            text="Load",
            command=load_selected,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            font=FONT_BUTTON,
            padx=16,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame,
            text="Delete",
            command=delete_selected,
            bg=BG_ENTRY,
            fg=DANGER,
            activebackground=BG_HOVER,
            activeforeground=DANGER,
            relief="flat",
            font=FONT_BASE,
            padx=16,
            pady=6,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame,
            text="Cancel",
            command=popup.destroy,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            padx=16,
            pady=6,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="left")

    def _nurture_delete_message_tab(self, index: int):
        """Delete a message tab by index (legacy compat)."""
        self._nurture_delete_message_card(index)

    def _nurture_delete_message_card(self, index: int):
        """Delete an accordion message card by index."""
        if len(self._nurture_msg_name_vars) <= 1:
            messagebox.showwarning("Cannot Delete", "You must have at least one message.")
            return

        # Destroy the card widget
        if index < len(self._nurture_msg_cards):
            card, editor, arrow = self._nurture_msg_cards[index]
            card.destroy()
            self._nurture_msg_cards.pop(index)

        # Remove data
        if index < len(self._nurture_msg_name_vars):
            self._nurture_msg_name_vars.pop(index)
        if index < len(self._nurture_msg_subject_vars):
            self._nurture_msg_subject_vars.pop(index)
        if index < len(self._nurture_msg_body_widgets):
            self._nurture_msg_body_widgets.pop(index)
        if index < len(self._nurture_msg_date_vars):
            self._nurture_msg_date_vars.pop(index)
        if index < len(self._nurture_msg_time_vars):
            self._nurture_msg_time_vars.pop(index)
        if index < len(self._nurture_msg_attachments):
            self._nurture_msg_attachments.pop(index)

        # Reset expanded index
        self._nurture_msg_expanded_index = -1

    def _nurture_refresh_message_tab_labels(self):
        """Refresh all message card labels (no-op for accordion, names auto-update via StringVar)."""
        pass

    def _nurture_show_variable_popup(self, subject_widget, body_ref):
        """Show variable insertion popup positioned near the subject field."""
        popup = tk.Toplevel(self)
        popup.title("Insert Variable")
        popup.overrideredirect(True)
        popup.configure(bg=BG_CARD)
        popup.attributes("-topmost", True)

        # Content frame (build before positioning to avoid gray flash)
        content = tk.Frame(popup, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        content.pack(fill="both", expand=True)

        # Position near the subject field (deferred to after content built)
        x = subject_widget.winfo_rootx()
        y = subject_widget.winfo_rooty() + subject_widget.winfo_height() + 4
        popup.geometry(f"+{x}+{y}")

        # Title
        tk.Label(
            content,
            text="Insert variable",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_BUTTON,
        ).pack(anchor="w", padx=12, pady=(10, 8))

        # Variable buttons
        variables = [
            ("{FirstName}", "Contact's first name"),
            ("{LastName}", "Contact's last name"),
            ("{Company}", "Contact's company"),
            ("{JobTitle}", "Contact's job title"),
            ("{Email}", "Contact's email"),
        ]

        def insert_and_close(var):
            # Insert into the last focused widget or body
            try:
                if body_ref[0] and body_ref[0].winfo_exists():
                    body_ref[0].insert(tk.INSERT, var)
            except:
                pass
            popup.destroy()

        for var, desc in variables:
            btn_frame = tk.Frame(content, bg=BG_CARD)
            btn_frame.pack(fill="x", padx=8, pady=2)

            tk.Button(
                btn_frame,
                text=var,
                command=lambda v=var: insert_and_close(v),
                bg=BG_CARD,
                fg=FG_TEXT,
                activebackground=BG_HOVER,
                activeforeground=FG_TEXT,
                relief="flat",
                font=FONT_SMALL,
                padx=10,
                pady=6,
                cursor="hand2",
                anchor="w",
            ).pack(side="left", fill="x", expand=True)

            tk.Label(
                btn_frame,
                text=desc,
                bg=BG_CARD,
                fg=FG_MUTED,
                font=FONT_CAPTION,
            ).pack(side="left", padx=(8, 8))

        # Padding at bottom
        tk.Frame(content, bg=BG_CARD, height=8).pack()

        # Close on escape or focus out
        def close_popup(_e=None):
            popup.destroy()

        popup.bind("<Escape>", close_popup)
        popup.bind("<FocusOut>", close_popup)
        popup.focus_set()

    def _build_nurture_contacts_tab(self, parent):
        """Build the Contacts tab content."""
        # Summary bar with count + action buttons
        summary = tk.Frame(parent, bg=BG_CARD)
        summary.pack(fill="x", padx=12, pady=(12, 8))

        summary_inner = tk.Frame(summary, bg=BG_CARD)
        summary_inner.pack(fill="x", padx=12, pady=10)

        self._nurture_contact_count_label = tk.Label(
            summary_inner, text="0 contacts", bg=BG_CARD, fg=FG_TEXT,
            font=FONT_SECTION_TITLE,
        )
        self._nurture_contact_count_label.pack(side="left")

        tk.Button(
            summary_inner, text="Upload CSV", command=self._nurture_upload_contacts,
            bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_HOVER, activeforeground=FG_WHITE,
            relief="flat", font=FONT_BTN_SM, cursor="hand2", padx=12, pady=5,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            summary_inner, text="Remove Selected", command=self._nurture_remove_contact,
            bg=BG_CARD, fg=DANGER, activebackground=BG_CARD, activeforeground=DANGER,
            relief="flat", font=FONT_SMALL, cursor="hand2", bd=0,
        ).pack(side="right")

        # Contact table (full height)
        table_frame = tk.Frame(parent, bg=BG_ROOT)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        columns = ("name", "company", "email", "last_sent", "status")
        self._nurture_contacts_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            selectmode="browse", height=12,
        )
        self._nurture_contacts_tree.heading("name", text="Name")
        self._nurture_contacts_tree.heading("company", text="Company")
        self._nurture_contacts_tree.heading("email", text="Email")
        self._nurture_contacts_tree.heading("last_sent", text="Last Sent")
        self._nurture_contacts_tree.heading("status", text="Status")

        self._nurture_contacts_tree.column("name", width=150, minwidth=100, stretch=True)
        self._nurture_contacts_tree.column("company", width=150, minwidth=80, stretch=True)
        self._nurture_contacts_tree.column("email", width=200, minwidth=120, stretch=True)
        self._nurture_contacts_tree.column("last_sent", width=100, minwidth=80, stretch=True)
        self._nurture_contacts_tree.column("status", width=80, minwidth=60, stretch=True)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self._nurture_contacts_tree.yview)
        self._nurture_contacts_tree.configure(yscrollcommand=scrollbar.set)

        self._nurture_contacts_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _build_nurture_messages_section(self):
        """Build the Messages section with collapsible message cards."""
        # Messages Card
        messages_card = tk.Frame(self._nurture_detail_inner, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        messages_card.pack(fill="x", padx=16, pady=(8, 16))

        content = tk.Frame(messages_card, bg=BG_CARD)
        content.pack(fill="both", expand=True, padx=20, pady=16)

        # Header with count badge
        header = tk.Frame(content, bg=BG_CARD)
        header.pack(fill="x", pady=(0, 16))

        # Left side: Title
        title_frame = tk.Frame(header, bg=BG_CARD)
        title_frame.pack(side="left")

        tk.Label(
            title_frame,
            text="Messages",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_TITLE,
        ).pack(side="left")

        # Message count badge
        self._nurture_message_count_label = tk.Label(
            title_frame,
            text="0",
            bg=BG_ENTRY,
            fg=FG_MUTED,
            font=FONT_BUTTON,
            padx=8,
            pady=2,
        )
        self._nurture_message_count_label.pack(side="left", padx=(10, 0))

        # Right side: Add button
        tk.Button(
            header,
            text="+ Add Message",
            command=self._nurture_add_message,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=14,
            pady=6,
        ).pack(side="right")

        # Message cards container
        self._nurture_messages_container = tk.Frame(content, bg=BG_CARD)
        self._nurture_messages_container.pack(fill="x")

    def _render_message_card(self, message, index):
        """Render a single message card."""
        enabled = message.get("enabled", True)

        # Card with visual distinction for disabled state
        card_bg = BG_ENTRY if enabled else BG_ROOT
        card_border = BORDER_MEDIUM if enabled else BORDER

        card = tk.Frame(
            self._nurture_messages_container,
            bg=card_bg,
            highlightthickness=1,
            highlightbackground=card_border,
        )
        card.pack(fill="x", pady=(0, 10))

        content = tk.Frame(card, bg=card_bg)
        content.pack(fill="x", padx=16, pady=14)

        # Header row: Message number badge + Name + Status indicators
        header_row = tk.Frame(content, bg=card_bg)
        header_row.pack(fill="x", pady=(0, 8))

        # Message number badge (left side)
        badge = tk.Label(
            header_row,
            text=f"#{index + 1}",
            bg=ACCENT if enabled else FG_MUTED,
            fg="white",
            font=FONT_BTN_SM,
            padx=8,
            pady=2,
        )
        badge.pack(side="left", padx=(0, 10))

        # Message name
        name = message.get("name", f"Email {index + 1}")
        name_color = FG_TEXT if enabled else FG_MUTED
        tk.Label(
            header_row,
            text=name,
            bg=card_bg,
            fg=name_color,
            font=FONT_SECTION,
        ).pack(side="left")

        # Right side indicators: Timing + Status badge
        indicators = tk.Frame(header_row, bg=card_bg)
        indicators.pack(side="right")

        # Timing pill
        timing = message.get("timing_rule", "immediate")
        timing_display = self._format_timing_rule(timing)
        tk.Label(
            indicators,
            text=timing_display,
            bg=BG_ROOT,
            fg=FG_MUTED,
            font=FONT_SMALL,
            padx=8,
            pady=2,
        ).pack(side="left", padx=(0, 8))

        # Enabled/Disabled badge
        status_text = "Enabled" if enabled else "Disabled"
        status_bg = GOOD if enabled else BG_ROOT
        status_fg = "white" if enabled else FG_MUTED
        tk.Label(
            indicators,
            text=status_text,
            bg=status_bg,
            fg=status_fg,
            font=FONT_BTN_SM,
            padx=8,
            pady=2,
        ).pack(side="left")

        # Subject line (prominent)
        subject = message.get("subject", "")
        subject_display = subject if subject else "(no subject)"
        subject_color = FG_TEXT if enabled and subject else FG_MUTED

        subject_frame = tk.Frame(content, bg=card_bg)
        subject_frame.pack(fill="x", pady=(0, 6))

        tk.Label(
            subject_frame,
            text="Subject:",
            bg=card_bg,
            fg=FG_MUTED,
            font=FONT_SMALL,
        ).pack(side="left", padx=(0, 6))

        tk.Label(
            subject_frame,
            text=subject_display[:60] + ('...' if len(subject_display) > 60 else ''),
            bg=card_bg,
            fg=subject_color,
            font=FONT_BASE,
            anchor="w",
        ).pack(side="left", fill="x")

        # Body preview (if available)
        body = message.get("body", "")
        if body:
            # Strip HTML and show first 80 chars
            body_preview = body.replace("<br>", " ").replace("<p>", "").replace("</p>", " ")
            body_preview = body_preview[:80] + ('...' if len(body_preview) > 80 else '')
            tk.Label(
                content,
                text=body_preview,
                bg=card_bg,
                fg=FG_MUTED,
                font=FONT_SMALL,
                anchor="w",
                wraplength=500,
                justify="left",
            ).pack(fill="x", pady=(0, 10))
        else:
            # Add spacing if no body
            tk.Frame(content, bg=card_bg, height=4).pack(fill="x")

        # Action buttons row with better styling
        btn_row = tk.Frame(content, bg=card_bg)
        btn_row.pack(fill="x")

        # Edit button (primary action)
        tk.Button(
            btn_row,
            text="Edit",
            command=lambda m=message, i=index: self._nurture_edit_message(m, i),
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            font=FONT_BTN_SM,
            cursor="hand2",
            padx=12,
            pady=4,
        ).pack(side="left", padx=(0, 6))

        # Secondary actions
        tk.Button(
            btn_row,
            text="Duplicate",
            command=lambda m=message: self._nurture_duplicate_message(m),
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=10,
            pady=4,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="left", padx=(0, 6))

        toggle_text = "Disable" if enabled else "Enable"
        toggle_fg = WARN if enabled else GOOD
        tk.Button(
            btn_row,
            text=toggle_text,
            command=lambda m=message, i=index: self._nurture_toggle_message(m, i),
            bg=BG_CARD,
            fg=toggle_fg,
            activebackground=BG_HOVER,
            activeforeground=toggle_fg,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=10,
            pady=4,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="left", padx=(0, 6))

        # Delete button (danger zone - right aligned)
        tk.Button(
            btn_row,
            text="Delete",
            command=lambda m=message, i=index: self._nurture_delete_message(m, i),
            bg=BG_CARD,
            fg=DANGER,
            activebackground=BG_HOVER,
            activeforeground=DANGER,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=10,
            pady=4,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="right")

        return card

    def _format_timing_rule(self, timing):
        """Format timing rule for display."""
        if timing == "immediate" or not timing:
            return "Immediately"
        if timing.startswith("days_after:"):
            days = timing.split(":")[1]
            return f"{days} days after previous"
        if timing.startswith("every:"):
            days = timing.split(":")[1]
            return f"Every {days} days"
        return timing

    # ============================================
    # Nurture Lists - View Navigation
    # ============================================
    def _nurture_show_placeholder(self):
        """Show placeholder, hide detail page."""
        if hasattr(self, '_nurture_detail_page'):
            self._nurture_detail_page.pack_forget()
        self._nurture_placeholder.pack(fill="both", expand=True)

    def _nurture_show_detail(self):
        """Show detail page, hide placeholder."""
        self._nurture_placeholder.pack_forget()
        self._nurture_detail_page.pack(fill="both", expand=True)
        self._nurture_refresh_detail()

    def _nurture_refresh_detail(self):
        """Refresh all sections of the detail page."""
        if not self._nurture_selected_campaign_id:
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        # Update Overview
        self._nurture_refresh_overview(camp)

        # Update Contacts
        self._nurture_refresh_contacts()

        # Load last saved message into the editor (if any)
        messages = camp.get("messages", [])
        if messages and len(messages) > 0:
            msg = messages[0]
            if self._nurture_msg_name_vars:
                self._nurture_msg_name_vars[0].set(msg.get("name", ""))
            if self._nurture_msg_subject_vars:
                self._nurture_msg_subject_vars[0].set(msg.get("subject", ""))
            if self._nurture_msg_body_widgets:
                self._nurture_msg_body_widgets[0].delete("1.0", "end")
                self._nurture_msg_body_widgets[0].insert("1.0", msg.get("body", ""))
            if self._nurture_msg_date_vars:
                self._nurture_msg_date_vars[0].set(msg.get("date", datetime.now().strftime("%Y-%m-%d")))
            if self._nurture_msg_time_vars:
                self._nurture_msg_time_vars[0].set(msg.get("time", "09:00 AM"))
            if self._nurture_msg_attachments:
                self._nurture_msg_attachments[0] = msg.get("attachments", [])
        else:
            # Clear editor for fresh start
            if self._nurture_msg_name_vars:
                self._nurture_msg_name_vars[0].set("")
            if self._nurture_msg_subject_vars:
                self._nurture_msg_subject_vars[0].set("")
            if self._nurture_msg_body_widgets:
                self._nurture_msg_body_widgets[0].delete("1.0", "end")
            if self._nurture_msg_date_vars:
                self._nurture_msg_date_vars[0].set(datetime.now().strftime("%Y-%m-%d"))
            if self._nurture_msg_time_vars:
                self._nurture_msg_time_vars[0].set("09:00 AM")

    def _nurture_refresh_overview(self, camp):
        """Refresh the Campaign header bar."""
        # Campaign name
        self._nurture_overview_name.configure(text=camp.get("name", "Untitled"))

        # Status badge with color
        status = camp.get("status", "draft").capitalize()
        status_lower = camp.get("status", "draft").lower()
        self._nurture_overview_status.configure(text=status)

        badge_colors = {"draft": (BORDER, FG_MUTED), "live": (GOOD, "white"), "paused": (WARN, "white"), "completed": (ACCENT, "white")}
        bg_c, fg_c = badge_colors.get(status_lower, (BORDER, FG_MUTED))
        self._nurture_status_badge.configure(text=status, bg=bg_c, fg=fg_c)

        # Contacts count
        contacts = camp.get("contacts", [])
        count = len(contacts)
        self._nurture_overview_contacts.configure(text=f"{count} contact{'s' if count != 1 else ''}")

        # Last activity
        stats = camp.get("stats", {})
        activity_log = camp.get("activity_log", [])

        if activity_log:
            recent = activity_log[0]
            if recent.get("type") == "email_sent":
                activity_text = f"Sent '{recent.get('message_name', 'Email')}' on {recent.get('sent_date', '')}"
            else:
                activity_text = f"Last: {recent.get('sent_date', stats.get('last_activity_at', ''))}"
            self._nurture_overview_last_activity.configure(text=activity_text)
        elif stats.get("last_activity_at"):
            self._nurture_overview_last_activity.configure(text=f"Last: {stats.get('last_activity_at')}")
        else:
            self._nurture_overview_last_activity.configure(text="No activity")

        # Hidden labels for compatibility
        self._nurture_overview_sent.configure(text=str(stats.get("emails_sent", 0)))
        self._nurture_overview_next_send.configure(text=stats.get("next_send_at", "\u2014") or "\u2014")

        # Pause/Resume removed — single send model

    # ============================================
    # Nurture Lists - Refresh Methods
    # ============================================
    def _refresh_nurture_campaigns(self):
        """Refresh the campaign listbox."""
        self._nurture_campaign_listbox.delete(0, "end")
        idx = self._load_nurture_index()
        for c in idx.get("campaigns", []):
            # Show contact count in parentheses
            camp_data = self._load_nurture_campaign(c["id"])
            contact_count = len(camp_data.get("contacts", [])) if camp_data else 0
            self._nurture_campaign_listbox.insert("end", f"{c['name']} ({contact_count})")

    def _on_nurture_campaign_selected(self, event=None):
        """Handle campaign selection from listbox."""
        sel = self._nurture_campaign_listbox.curselection()
        if not sel:
            return

        idx = self._load_nurture_index()
        campaigns = idx.get("campaigns", [])
        if sel[0] >= len(campaigns):
            return

        self._nurture_selected_campaign_id = campaigns[sel[0]]["id"]
        self._nurture_show_detail()

    def _nurture_refresh_messages(self):
        """Refresh messages (no-op for accordion card UI - cards update via StringVars)."""
        pass

    def _nurture_save_message(self):
        """Save the message as a reusable template."""
        subject = self._nurture_message_subject_var.get().strip()
        body = self._nurture_message_body_text.get("1.0", "end-1c").strip()

        if not subject and not body:
            messagebox.showwarning("Empty Template", "Please enter a subject or body before saving.")
            return

        # Prompt for template name
        default_name = self._nurture_message_name_var.get().strip() or "New Template"
        name = themed_askstring(self, "Save Template", "Enter template name:", default_name)

        if not name or not name.strip():
            return

        name = name.strip()

        # Save to global templates
        templates = self._load_nurture_templates()

        # Check for existing template with same name and ask to overwrite
        existing_idx = None
        for i, t in enumerate(templates):
            if t.get("name", "").lower() == name.lower():
                existing_idx = i
                break

        if existing_idx is not None:
            if not messagebox.askyesno("Overwrite Template", f"Template '{name}' already exists. Overwrite?"):
                return
            templates[existing_idx] = {"name": name, "subject": subject, "body": body}
        else:
            templates.append({"name": name, "subject": subject, "body": body})

        self._save_nurture_templates(templates)
        self._nurture_message_name_var.set(name)
        self._refresh_nurture_templates()
        self._set_status(f"Template '{name}' saved", GOOD)

    def _nurture_send_message(self):
        """Send message to all contacts in the campaign."""
        if not self._nurture_selected_campaign_id:
            messagebox.showwarning("No List", "Please select a list first.")
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        contacts = camp.get("contacts", [])
        contact_count = len(contacts)

        if contact_count == 0:
            messagebox.showwarning("No Contacts", "This campaign has no contacts to send to.")
            return

        # Get current message from editor
        subject = self._nurture_message_subject_var.get().strip()
        body = self._nurture_message_body_text.get("1.0", "end-1c").strip()

        if not subject:
            messagebox.showwarning("Missing Subject", "Please enter a subject line.")
            return

        if not body:
            messagebox.showwarning("Missing Body", "Please enter a message body.")
            return

        # Get attachments
        attachments = getattr(self, "_nurture_attachments", [])
        attach_count = len(attachments)
        attach_msg = f"\n\nWith {attach_count} attachment{'s' if attach_count != 1 else ''}" if attach_count > 0 else ""

        # Confirmation dialog
        if not messagebox.askyesno(
            "Send Message",
            f"Send to {contact_count} contact{'s' if contact_count != 1 else ''}?{attach_msg}"
        ):
            return

        # Send emails to all contacts via Outlook
        sent_count = 0
        errors = []

        try:
            outlook = fourdrip_core.get_outlook_app()
        except Exception as e:
            messagebox.showerror("Outlook Error", f"Could not connect to Outlook:\n{e}")
            return

        for contact in contacts:
            data = contact.get("data", {})
            email = data.get("Email") or data.get("Work Email") or contact.get("email_key", "")
            if not email:
                continue

            # Substitute variables
            personalized_subject = self._substitute_variables(subject, data)
            personalized_body = self._substitute_variables(body, data)

            try:
                mail = outlook.CreateItem(0)  # 0 = olMailItem
                mail.To = email
                mail.Subject = personalized_subject
                if is_html(personalized_body):
                    mail.HTMLBody = wrap_html_for_email(personalized_body)
                else:
                    mail.Body = personalized_body

                # Add attachments
                for attach_path in attachments:
                    if Path(attach_path).exists():
                        mail.Attachments.Add(str(attach_path))

                mail.Send()
                sent_count += 1
            except Exception as e:
                errors.append(f"{email}: {e}")

        # Clear attachments after sending
        self._nurture_clear_attachments()

        if errors and sent_count == 0:
            messagebox.showerror("Send Failed", f"Failed to send emails:\n" + "\n".join(errors[:5]))
        elif errors:
            self._set_status(f"Sent to {sent_count}, {len(errors)} failed", WARN)
        else:
            self._set_status(f"Sent to {sent_count} contact{'s' if sent_count != 1 else ''}", GOOD)

    def _nurture_refresh_contacts(self):
        """Refresh the contacts list with new table structure."""
        if not self._nurture_selected_campaign_id:
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        # Clear existing items
        for item in self._nurture_contacts_tree.get_children():
            self._nurture_contacts_tree.delete(item)

        contacts = camp.get("contacts", [])
        self._nurture_all_contacts = contacts  # Store for filtering

        # Update count label
        n = len(contacts)
        self._nurture_contact_count_label.configure(text=f"{n} contact{'s' if n != 1 else ''}")

        for c in contacts:
            data = c.get("data", {})
            first = data.get("FirstName", "")
            last = data.get("LastName", "")
            name = f"{first} {last}".strip() or "Unknown"
            company = data.get("Company", "")
            email = data.get("Email", data.get("Work Email", c.get("email_key", "")))
            last_sent = c.get("last_sent_at", "—") or "—"
            status = c.get("contact_status", "active").capitalize()

            self._nurture_contacts_tree.insert("", "end", values=(name, company, email, last_sent, status))

    def _nurture_filter_contacts(self):
        """Filter contacts based on search term."""
        if not hasattr(self, '_nurture_all_contacts'):
            return

        search_term = self._nurture_contact_search_var.get().lower().strip()

        # Clear existing items
        for item in self._nurture_contacts_tree.get_children():
            self._nurture_contacts_tree.delete(item)

        filtered = []
        for c in self._nurture_all_contacts:
            data = c.get("data", {})
            first = data.get("FirstName", "")
            last = data.get("LastName", "")
            name = f"{first} {last}".strip() or "Unknown"
            company = data.get("Company", "")
            email = data.get("Email", data.get("Work Email", c.get("email_key", "")))

            # Check if search term matches name, company, or email
            if (search_term in name.lower() or
                search_term in company.lower() or
                search_term in email.lower()):
                filtered.append(c)

        # Update count
        n = len(filtered)
        self._nurture_contact_count_label.configure(text=f"{n} contact{'s' if n != 1 else ''}")

        # Insert filtered contacts
        for c in filtered:
            data = c.get("data", {})
            first = data.get("FirstName", "")
            last = data.get("LastName", "")
            name = f"{first} {last}".strip() or "Unknown"
            company = data.get("Company", "")
            email = data.get("Email", data.get("Work Email", c.get("email_key", "")))
            last_sent = c.get("last_sent_at", "—") or "—"
            status = c.get("contact_status", "active").capitalize()

            self._nurture_contacts_tree.insert("", "end", values=(name, company, email, last_sent, status))

    def _nurture_remove_contact(self):
        """Remove the selected contact from the campaign (not from database)."""
        if not self._nurture_selected_campaign_id:
            messagebox.showwarning("No List", "Please select a list first.")
            return

        selected = self._nurture_contacts_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a contact to remove.")
            return

        item = selected[0]
        values = self._nurture_contacts_tree.item(item, "values")
        name = values[0] if values else "Unknown"
        email = values[2] if len(values) > 2 else "Unknown"

        if not messagebox.askyesno(
            "Remove Contact",
            f"Remove '{name}' from this campaign?\n\nThis contact will not be deleted from your database."
        ):
            return

        try:
            camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
            if not camp:
                return

            contacts = camp.get("contacts", [])
            new_contacts = [c for c in contacts if (
                c.get("data", {}).get("Email", c.get("email_key", "")).lower() != email.lower()
            )]

            camp["contacts"] = new_contacts
            self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)

            self._nurture_refresh_contacts()
            self._nurture_refresh_overview(camp)
            self._refresh_nurture_campaigns()
            self._set_status(f"Contact removed from campaign", GOOD)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove contact:\n{e}")

    # ============================================
    # Nurture Lists - Campaign Actions
    # ============================================
    def _nurture_rename_campaign_btn(self):
        """Handle Rename button click."""
        if not self._nurture_selected_campaign_id:
            messagebox.showwarning("No List", "Please select a list first.")
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        current_name = camp.get("name", "")
        new_name = themed_askstring(self, "Rename Campaign", "Enter new name:", current_name)

        if not new_name or new_name.strip() == current_name:
            return

        try:
            self._rename_nurture_campaign(self._nurture_selected_campaign_id, new_name.strip())
            self._refresh_nurture_campaigns()
            self._nurture_refresh_overview(self._load_nurture_campaign(self._nurture_selected_campaign_id))
            self._set_status(f"Campaign renamed to '{new_name.strip()}'", GOOD)
        except ValueError as e:
            messagebox.showerror("Rename Failed", str(e))

    def _nurture_delete_campaign_btn(self):
        """Handle Delete button click with safe confirmation."""
        if not self._nurture_selected_campaign_id:
            messagebox.showwarning("No List", "Please select a list first.")
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        camp_name = camp.get("name", "Untitled")

        # Create safe delete confirmation dialog
        self._show_safe_delete_dialog(camp_name)

    def _show_safe_delete_dialog(self, camp_name):
        """Show safe delete confirmation dialog requiring typed name."""
        dialog = tk.Toplevel(self)
        dialog.title("Delete Campaign")
        dialog.configure(bg=BG_ROOT)
        dialog.transient(self)
        dialog.grab_set()

        # Center the dialog
        dialog.geometry("400x220")
        self._center_window(dialog, parent=self)

        content = tk.Frame(dialog, bg=BG_ROOT)
        content.pack(fill="both", expand=True, padx=24, pady=24)

        # Warning message
        tk.Label(
            content,
            text=f"Delete campaign '{camp_name}'?",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=FONT_SECTION,
        ).pack(anchor="w")

        tk.Label(
            content,
            text="This removes the campaign and its message drafts.\nContacts are not deleted from your database.",
            bg=BG_ROOT,
            fg=FG_MUTED,
            font=FONT_BASE,
            justify="left",
        ).pack(anchor="w", pady=(8, 16))

        tk.Label(
            content,
            text=f"Type '{camp_name}' to confirm:",
            bg=BG_ROOT,
            fg=FG_TEXT,
            font=FONT_BASE,
        ).pack(anchor="w")

        confirm_var = tk.StringVar()
        confirm_entry = tk.Entry(
            content,
            textvariable=confirm_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            highlightcolor=ACCENT,
        )
        confirm_entry.pack(fill="x", pady=(4, 16))
        confirm_entry.focus_set()

        # Buttons
        btn_row = tk.Frame(content, bg=BG_ROOT)
        btn_row.pack(fill="x")

        def _do_delete():
            if confirm_var.get().strip() == camp_name:
                dialog.destroy()
                self._delete_nurture_campaign(self._nurture_selected_campaign_id)
                self._nurture_selected_campaign_id = None
                self._refresh_nurture_campaigns()
                self._nurture_show_placeholder()
                self._set_status(f"Campaign '{camp_name}' deleted", GOOD)

                # Refresh Stay Connected list
                if hasattr(self, '_refresh_stay_nurture_list'):
                    try:
                        self._refresh_stay_nurture_list()
                    except Exception:
                        pass
            else:
                messagebox.showwarning("Name Mismatch", "The campaign name doesn't match. Delete cancelled.")

        tk.Button(
            btn_row,
            text="Cancel",
            command=dialog.destroy,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BTN_SM,
            cursor="hand2",
            padx=12,
            pady=4,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_row,
            text="Delete Campaign",
            command=_do_delete,
            bg=DANGER,
            fg="white",
            activebackground=DANGER_FG,
            activeforeground="white",
            relief="flat",
            font=FONT_BTN_SM,
            cursor="hand2",
            padx=12,
            pady=4,
        ).pack(side="right")

    def _nurture_launch_campaign(self):
        """Launch the campaign (change status to Live)."""
        if not self._nurture_selected_campaign_id:
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        contacts = camp.get("contacts", [])
        if not contacts:
            messagebox.showwarning("No Contacts", "Please add contacts before launching the campaign.")
            return

        messages = camp.get("messages", [])
        enabled_messages = [m for m in messages if m.get("enabled", True)]
        if not enabled_messages:
            messagebox.showwarning("No Messages", "Please add at least one enabled message before launching.")
            return

        if not messagebox.askyesno(
            "Launch Campaign",
            f"Launch '{camp.get('name')}'?\n\n{len(contacts)} contacts will receive messages."
        ):
            return

        camp["status"] = "live"
        camp["stats"] = camp.get("stats", {})
        camp["stats"]["launched_at"] = datetime.now().isoformat()
        self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)

        self._nurture_refresh_overview(camp)
        self._refresh_nurture_campaigns()
        self._set_status(f"Campaign launched", GOOD)

    def _nurture_pause_campaign(self):
        """Pause the campaign."""
        if not self._nurture_selected_campaign_id:
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        camp["status"] = "paused"
        self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)

        self._nurture_refresh_overview(camp)
        self._refresh_nurture_campaigns()
        self._set_status(f"Campaign paused", WARN)

    def _nurture_resume_campaign(self):
        """Resume the campaign."""
        if not self._nurture_selected_campaign_id:
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        camp["status"] = "live"
        self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)

        self._nurture_refresh_overview(camp)
        self._refresh_nurture_campaigns()
        self._set_status(f"Campaign resumed", GOOD)

    def _nurture_save_updates(self):
        """Send the email to all contacts in the selected list."""
        if not self._nurture_selected_campaign_id:
            messagebox.showwarning("No List", "Please select a list first.")
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            messagebox.showerror("Error", "Could not load list data.")
            return

        contacts = camp.get("contacts", [])
        if not contacts:
            messagebox.showwarning("No Contacts", "This list has no contacts. Add contacts first via the Contacts tab.")
            return

        if not self._nurture_msg_subject_vars:
            return

        # Collect the single email from the editor
        name = self._nurture_msg_name_vars[0].get().strip() if self._nurture_msg_name_vars else "Email"
        subject = self._nurture_msg_subject_vars[0].get().strip()
        body = self._nurture_msg_body_widgets[0].get("1.0", "end").rstrip() if self._nurture_msg_body_widgets else ""
        date_str = self._nurture_msg_date_vars[0].get().strip() if self._nurture_msg_date_vars else ""
        time_str = self._nurture_msg_time_vars[0].get().strip() if self._nurture_msg_time_vars else ""

        if not subject:
            messagebox.showwarning("Missing Subject", "Please enter a subject line.")
            return
        if not body.strip():
            messagebox.showwarning("Missing Body", "Please write your email body.")
            return
        if not date_str or not time_str:
            messagebox.showwarning("Missing Schedule", "Please set a send date and time.")
            return

        # Ensure signature is included
        body_with_signature = self._ensure_signature_in_body(body)

        contact_count = len(contacts)
        if not messagebox.askyesno(
            "Send Email",
            f"Send this email to {contact_count} contact{'s' if contact_count != 1 else ''}?\n\n"
            f"Subject: {subject}\n"
            f"Schedule: {date_str} at {time_str}"
        ):
            return

        # Get attachments
        attachments = self._nurture_msg_attachments[0] if self._nurture_msg_attachments else []

        import tempfile
        import csv

        try:
            temp_fd, temp_path = tempfile.mkstemp(suffix=".csv", prefix="nurture_contacts_")
            os.close(temp_fd)

            with open(temp_path, "w", newline="", encoding="utf-8") as f:
                first_data = contacts[0].get("data", {})
                fieldnames = list(first_data.keys()) if first_data else ["Email", "FirstName", "LastName", "Company", "JobTitle"]
                if "Email" not in fieldnames and "Work Email" not in fieldnames:
                    fieldnames.insert(0, "Email")

                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for contact in contacts:
                    data = contact.get("data", {})
                    if not data:
                        data = {"Email": contact.get("email_key", "")}
                    writer.writerow(data)

            send_schedule = [{
                "subject": subject,
                "body": body_with_signature,
                "date": date_str,
                "time": time_str,
                "attachments": attachments,
            }]

            fourdrip_core.run_4drip(
                schedule=send_schedule,
                contacts_path=temp_path,
                attachments_path=None,
                send_emails=True,
            )

            # Track in campaign
            if "sent_messages" not in camp:
                camp["sent_messages"] = []
            if "activity_log" not in camp:
                camp["activity_log"] = []

            camp["sent_messages"].append({
                "name": name,
                "subject": subject,
                "sent_date": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
                "contacts_count": contact_count,
            })
            camp["activity_log"].insert(0, {
                "type": "email_sent",
                "message_name": name,
                "subject": subject,
                "sent_date": datetime.now().strftime("%m/%d/%Y %I:%M %p"),
                "contacts_count": contact_count,
            })

            if "stats" not in camp:
                camp["stats"] = {"emails_sent": 0}
            camp["stats"]["emails_sent"] = camp["stats"].get("emails_sent", 0) + contact_count
            camp["stats"]["last_activity_at"] = datetime.now().strftime("%m/%d/%Y")

            self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)
            self._nurture_refresh_overview(camp)
            self._refresh_nurture_campaigns()

            self._set_status(f"{contact_count} emails queued", GOOD)
            self.toast.show(f"Email queued to {contact_count} contacts via Outlook", "success")

        except Exception as e:
            self._set_status("Send failed", DANGER)
            messagebox.showerror("Error", f"Failed to send emails:\n\n{e}")
        finally:
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    def _nurture_save_campaign_messages(self, camp, messages):
        """Save messages to campaign without sending."""
        camp["messages"] = [{
            "name": m["name"],
            "subject": m["subject"],
            "body": m["body"],
            "date": m["date"],
            "time": m["time"],
            "attachments": m.get("attachments", []),
        } for m in messages]
        self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)

    def _nurture_remove_sent_tabs(self, tab_indices):
        """Remove message cards that have been sent (by index, in reverse order)."""
        if not hasattr(self, '_nurture_msg_cards'):
            return

        for idx in sorted(tab_indices, reverse=True):
            try:
                # Destroy the card widget
                if idx < len(self._nurture_msg_cards):
                    card, editor, arrow = self._nurture_msg_cards[idx]
                    card.destroy()
                    self._nurture_msg_cards.pop(idx)

                # Remove from tracking lists
                if idx < len(self._nurture_msg_name_vars):
                    self._nurture_msg_name_vars.pop(idx)
                if idx < len(self._nurture_msg_subject_vars):
                    self._nurture_msg_subject_vars.pop(idx)
                if idx < len(self._nurture_msg_body_widgets):
                    self._nurture_msg_body_widgets.pop(idx)
                if idx < len(self._nurture_msg_date_vars):
                    self._nurture_msg_date_vars.pop(idx)
                if idx < len(self._nurture_msg_time_vars):
                    self._nurture_msg_time_vars.pop(idx)
                if idx < len(self._nurture_msg_attachments):
                    self._nurture_msg_attachments.pop(idx)
            except Exception:
                continue
        self._nurture_msg_expanded_index = -1

    # ============================================
    # Nurture Lists - Message Actions
    # ============================================
    def _nurture_add_message(self):
        """Add a new message to the campaign."""
        if not self._nurture_selected_campaign_id:
            return

        self._show_message_editor(None, -1)

    def _nurture_edit_message(self, message, index):
        """Edit an existing message."""
        self._show_message_editor(message, index)

    def _nurture_duplicate_message(self, message):
        """Duplicate a message."""
        if not self._nurture_selected_campaign_id:
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        new_message = message.copy()
        new_message["id"] = f"msg_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        new_message["name"] = f"{message.get('name', 'Message')} (Copy)"

        camp["messages"] = camp.get("messages", [])
        camp["messages"].append(new_message)
        self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)

        self._nurture_refresh_messages()
        self._set_status("Message duplicated", GOOD)

    def _nurture_toggle_message(self, message, index):
        """Toggle message enabled/disabled state."""
        if not self._nurture_selected_campaign_id:
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        messages = camp.get("messages", [])
        if index < len(messages):
            current = messages[index].get("enabled", True)
            messages[index]["enabled"] = not current
            self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)
            self._nurture_refresh_messages()

            status = "enabled" if not current else "disabled"
            self._set_status(f"Message {status}", GOOD)

    def _nurture_delete_message(self, message, index):
        """Delete a message with confirmation."""
        if not self._nurture_selected_campaign_id:
            return

        msg_name = message.get("name", f"Message {index + 1}")

        if not messagebox.askyesno(
            "Delete Message",
            f"Delete '{msg_name}'?\n\nThis cannot be undone."
        ):
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        messages = camp.get("messages", [])
        if index < len(messages):
            messages.pop(index)
            self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)
            self._nurture_refresh_messages()
            self._set_status("Message deleted", GOOD)

    def _show_message_editor(self, message, index):
        """Show the message editor modal."""
        is_new = message is None
        message = message or {"name": "", "subject": "", "body": "", "timing_rule": "immediate", "enabled": True}

        editor = tk.Toplevel(self)
        editor.title("Edit Message" if not is_new else "New Message")
        editor.configure(bg=BG_ROOT)
        editor.transient(self)
        editor.grab_set()
        editor.geometry("600x500")
        self._center_window(editor, parent=self)

        content = tk.Frame(editor, bg=BG_ROOT)
        content.pack(fill="both", expand=True, padx=24, pady=24)

        # Message Name
        tk.Label(content, text="Message Name:", bg=BG_ROOT, fg=FG_TEXT, font=FONT_BUTTON).pack(anchor="w")
        name_var = tk.StringVar(value=message.get("name", ""))
        tk.Entry(
            content,
            textvariable=name_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            highlightcolor=ACCENT,
        ).pack(fill="x", pady=(4, 12))

        # Subject
        tk.Label(content, text="Subject:", bg=BG_ROOT, fg=FG_TEXT, font=FONT_BUTTON).pack(anchor="w")
        subject_var = tk.StringVar(value=message.get("subject", ""))
        subject_entry = tk.Entry(
            content,
            textvariable=subject_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            highlightcolor=ACCENT,
        )
        subject_entry.pack(fill="x", pady=(4, 8))

        # Insert Token button
        token_row = tk.Frame(content, bg=BG_ROOT)
        token_row.pack(fill="x", pady=(0, 12))

        def insert_token(token, target=None):
            widget = target or body_text
            if isinstance(widget, tk.Entry):
                widget.insert(tk.INSERT, token)
            else:
                widget.insert("insert", token)

        tk.Button(
            token_row,
            text="Insert Token",
            command=lambda: self._show_token_picker(lambda t: insert_token(t, body_text)),
            bg=BG_ENTRY,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_SMALL,
            cursor="hand2",
            padx=8,
            pady=2,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="left")

        # Timing
        tk.Label(token_row, text="Timing:", bg=BG_ROOT, fg=FG_TEXT, font=FONT_SMALL).pack(side="left", padx=(16, 4))
        timing_var = tk.StringVar(value=message.get("timing_rule", "immediate"))
        timing_combo = ttk.Combobox(
            token_row,
            textvariable=timing_var,
            values=["immediate", "days_after:3", "days_after:7", "every:30"],
            state="readonly",
            width=15,
            style="Dark.TCombobox",
        )
        timing_combo.pack(side="left")

        # Body
        tk.Label(content, text="Body:", bg=BG_ROOT, fg=FG_TEXT, font=FONT_BUTTON).pack(anchor="w")
        body_text = tk.Text(
            content,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            wrap="word",
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
            highlightcolor=ACCENT,
            height=12,
        )
        body_text.pack(fill="both", expand=True, pady=(4, 16))
        body_text.insert("1.0", message.get("body", ""))

        # Note about editing live campaigns
        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if camp and camp.get("status") == "live":
            tk.Label(
                content,
                text="Note: Changes apply to future sends only.",
                bg=BG_ROOT,
                fg=WARN,
                font=("Segoe UI", 9, "italic"),
            ).pack(anchor="w", pady=(0, 8))

        # Buttons
        btn_row = tk.Frame(content, bg=BG_ROOT)
        btn_row.pack(fill="x")

        def _save():
            name = name_var.get().strip()
            subject = subject_var.get().strip()
            body = body_text.get("1.0", "end-1c").strip()
            timing = timing_var.get()

            if not name:
                messagebox.showwarning("Missing Name", "Please enter a message name.")
                return

            if not subject:
                messagebox.showwarning("Missing Subject", "Please enter a subject line.")
                return

            camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
            if not camp:
                return

            messages = camp.get("messages", [])

            if is_new:
                new_msg = {
                    "id": f"msg_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "name": name,
                    "subject": subject,
                    "body": body,
                    "timing_rule": timing,
                    "enabled": True,
                }
                messages.append(new_msg)
            else:
                if index < len(messages):
                    messages[index]["name"] = name
                    messages[index]["subject"] = subject
                    messages[index]["body"] = body
                    messages[index]["timing_rule"] = timing

            camp["messages"] = messages
            self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)

            editor.destroy()
            self._nurture_refresh_messages()
            self._set_status("Message saved", GOOD)

        tk.Button(
            btn_row,
            text="Cancel",
            command=editor.destroy,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=12,
            pady=6,
            highlightthickness=1,
            highlightbackground=BORDER_MEDIUM,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_row,
            text="Save",
            command=_save,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            font=FONT_BUTTON,
            cursor="hand2",
            padx=16,
            pady=6,
        ).pack(side="right")

    def _show_token_picker(self, on_select):
        """Show token picker popup."""
        picker = tk.Toplevel(self)
        picker.title("Insert Token")
        picker.configure(bg=BG_ROOT)
        picker.transient(self)
        picker.grab_set()
        picker.geometry("200x200")
        self._center_window(picker, parent=self)

        tokens = ["{FirstName}", "{LastName}", "{Company}", "{JobTitle}", "{Email}", "{Signature}"]

        for token in tokens:
            tk.Button(
                picker,
                text=token,
                command=lambda t=token: (on_select(t), picker.destroy()),
                bg=BG_ENTRY,
                fg=FG_TEXT,
                activebackground=BG_HOVER,
                activeforeground=FG_TEXT,
                relief="flat",
                font=FONT_BASE,
                cursor="hand2",
                anchor="w",
                padx=12,
                pady=6,
            ).pack(fill="x", padx=8, pady=2)

    def _nurture_insert_variable(self, var_name: str):
        """Insert variable into the last focused editor field."""
        widget = getattr(self, "_nurture_last_editor", None)
        if not widget:
            widget = self._nurture_message_body_text

        try:
            if isinstance(widget, tk.Entry):
                widget.insert(tk.INSERT, var_name)
            elif isinstance(widget, tk.Text):
                widget.insert("insert", var_name)
        except tk.TclError:
            pass

    def _nurture_add_attachments(self):
        """Add attachments to the nurture message."""
        file_paths = filedialog.askopenfilenames(
            title="Select Attachments",
            filetypes=[
                ("All files", "*.*"),
                ("PDF files", "*.pdf"),
                ("Images", "*.png;*.jpg;*.jpeg;*.gif"),
                ("Documents", "*.doc;*.docx;*.txt"),
            ],
            parent=self
        )

        if not file_paths:
            return

        # Store attachment paths
        if not hasattr(self, "_nurture_attachments"):
            self._nurture_attachments = []

        for path in file_paths:
            if path not in self._nurture_attachments:
                self._nurture_attachments.append(path)

        # Update label to show count
        count = len(self._nurture_attachments)
        if count > 0:
            names = [Path(p).name for p in self._nurture_attachments[:2]]
            label_text = ", ".join(names)
            if count > 2:
                label_text += f" +{count - 2} more"
            self._nurture_attachments_label.configure(text=f"📎 {label_text}")
        else:
            self._nurture_attachments_label.configure(text="")

        self._set_status(f"{count} attachment{'s' if count != 1 else ''} selected", GOOD)

    def _nurture_clear_attachments(self):
        """Clear all attachments."""
        self._nurture_attachments = []
        self._nurture_attachments_label.configure(text="")

    # ============================================
    # Nurture Lists - Template Management
    # ============================================
    def _nurture_templates_path(self) -> Path:
        """Path to global nurture templates file."""
        return self._nurture_campaigns_dir() / "templates.json"

    def _load_nurture_templates(self) -> list:
        """Load global nurture message templates."""
        path = self._nurture_templates_path()
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_nurture_templates(self, templates: list) -> None:
        """Save global nurture message templates."""
        with self._nurture_templates_path().open("w", encoding="utf-8") as f:
            json.dump(templates, f, indent=2)

    def _refresh_nurture_templates(self):
        """Refresh the template dropdown."""
        templates = self._load_nurture_templates()
        names = [t.get("name", "Untitled") for t in templates]
        self._nurture_template_dropdown["values"] = names
        if names:
            self._nurture_template_var.set("")  # Clear selection

    def _on_nurture_template_selected(self, event=None):
        """Load selected template into editor."""
        name = self._nurture_template_var.get()
        if not name:
            return

        templates = self._load_nurture_templates()
        for t in templates:
            if t.get("name") == name:
                self._nurture_message_name_var.set(t.get("name", ""))
                self._nurture_message_subject_var.set(t.get("subject", ""))
                self._nurture_message_body_text.delete("1.0", "end")
                self._nurture_message_body_text.insert("1.0", t.get("body", ""))
                self._set_status(f"Loaded template '{name}'", GOOD)
                break

    def _nurture_delete_template(self):
        """Delete the selected template."""
        name = self._nurture_template_var.get()
        if not name:
            messagebox.showwarning("No Selection", "Please select a template to delete.")
            return

        if not messagebox.askyesno("Delete Template", f"Delete template '{name}'?"):
            return

        templates = self._load_nurture_templates()
        templates = [t for t in templates if t.get("name") != name]
        self._save_nurture_templates(templates)
        self._refresh_nurture_templates()
        self._set_status(f"Template '{name}' deleted", GOOD)

    # ============================================
    # Nurture Lists - Contact Upload
    # ============================================
    def _nurture_upload_contacts(self):
        """Upload contacts from CSV file."""
        if not self._nurture_selected_campaign_id:
            messagebox.showwarning("No List", "Please select a list first.")
            return

        file_path = filedialog.askopenfilename(
            title="Select Contacts CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            parent=self
        )

        if not file_path:
            return

        try:
            import csv
            contacts_added = 0
            camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
            if not camp:
                return

            existing_contacts = camp.get("contacts", [])
            existing_emails = {
                c.get("data", {}).get("Email", "").lower() or c.get("data", {}).get("Work Email", "").lower()
                for c in existing_contacts
            }

            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Get email from common column names
                    email = (
                        row.get("Email") or row.get("email") or
                        row.get("Work Email") or row.get("work_email") or
                        row.get("E-mail") or row.get("EMAIL") or ""
                    ).strip()

                    if not email or email.lower() in existing_emails:
                        continue

                    # Normalize field names
                    data = {
                        "FirstName": row.get("FirstName") or row.get("First Name") or row.get("first_name") or "",
                        "LastName": row.get("LastName") or row.get("Last Name") or row.get("last_name") or "",
                        "Email": email,
                        "Company": row.get("Company") or row.get("company") or row.get("Organization") or "",
                        "JobTitle": row.get("JobTitle") or row.get("Job Title") or row.get("Title") or row.get("title") or "",
                    }

                    existing_contacts.append({
                        "email_key": email,
                        "data": data,
                        "added_at": datetime.now().isoformat(),
                    })
                    existing_emails.add(email.lower())
                    contacts_added += 1

            camp["contacts"] = existing_contacts
            self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)
            self._nurture_refresh_contacts()

            # Refresh Stay Connected nurture list
            if hasattr(self, '_refresh_stay_nurture_list'):
                try:
                    self._refresh_stay_nurture_list()
                except Exception:
                    pass

            if contacts_added > 0:
                self._set_status(f"Added {contacts_added} contact{'s' if contacts_added != 1 else ''}", GOOD)
            else:
                messagebox.showinfo("No New Contacts", "No new contacts were found in the file (duplicates or empty emails skipped).")

        except Exception as e:
            messagebox.showerror("Upload Error", f"Failed to upload contacts:\n{e}")

    def _nurture_delete_contact(self):
        """Delete the selected contact from the nurture list."""
        if not self._nurture_selected_campaign_id:
            messagebox.showwarning("No List", "Please select a list first.")
            return

        # Check if a contact is selected
        selected = self._nurture_contacts_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a contact to delete.")
            return

        # Get the selected contact's info
        item = selected[0]
        values = self._nurture_contacts_tree.item(item, "values")
        email = values[1] if len(values) > 1 else "Unknown"
        name = values[0] if values else "Unknown"

        # Confirm deletion
        if not messagebox.askyesno("Delete Contact", f"Delete contact '{name}' ({email}) from this campaign?"):
            return

        try:
            camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
            if not camp:
                return

            contacts = camp.get("contacts", [])

            # Find and remove the contact with matching email
            new_contacts = []
            for c in contacts:
                c_email = c.get("data", {}).get("Email", "") or c.get("data", {}).get("Work Email", "") or c.get("email_key", "")
                if c_email.lower() != email.lower():
                    new_contacts.append(c)

            camp["contacts"] = new_contacts
            self._save_nurture_campaign(self._nurture_selected_campaign_id, camp)

            # Remove from treeview
            self._nurture_contacts_tree.delete(item)

            # Update header
            self._nurture_contacts_header.configure(text=f"Contacts ({len(new_contacts)})")

            # Refresh Stay Connected nurture list
            if hasattr(self, '_refresh_stay_nurture_list'):
                try:
                    self._refresh_stay_nurture_list()
                except Exception:
                    pass

            self._set_status(f"Contact '{name}' deleted", GOOD)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete contact:\n{e}")

    # ============================================
    # Nurture Lists - Campaign Management
    # ============================================
    def _nurture_delete_campaign_ui(self):
        """Delete the selected campaign (UI handler)."""
        if not self._nurture_selected_campaign_id:
            messagebox.showwarning("No Selection", "Please select a list to delete.")
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        if not messagebox.askyesno("Delete Campaign", f"Delete '{camp.get('name')}'?\n\nThis will remove all emails and contacts in this campaign."):
            return

        self._delete_nurture_campaign(self._nurture_selected_campaign_id)
        self._nurture_selected_campaign_id = None
        self._nurture_show_placeholder()
        self._refresh_nurture_campaigns()
        self._set_status("Campaign deleted", GOOD)

    def _nurture_new_campaign(self):
        """Create a new nurture list."""
        name = themed_askstring(self, "New Campaign", "Campaign name:")
        if not name or not name.strip():
            return

        try:
            cid = self._create_nurture_campaign(name.strip())
            self._refresh_nurture_campaigns()
            self._nurture_selected_campaign_id = cid

            # Select in listbox
            idx = self._load_nurture_index()
            for i, c in enumerate(idx.get("campaigns", [])):
                if c["id"] == cid:
                    self._nurture_campaign_listbox.selection_clear(0, "end")
                    self._nurture_campaign_listbox.selection_set(i)
                    break

            self._nurture_show_content()
            self._set_status(f"Campaign '{name}' created", GOOD)
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def _nurture_rename_campaign(self):
        """Rename the selected campaign."""
        if not self._nurture_selected_campaign_id:
            messagebox.showwarning("No Selection", "Please select a list to rename.")
            return

        camp = self._load_nurture_campaign(self._nurture_selected_campaign_id)
        if not camp:
            return

        new_name = themed_askstring(self, "Rename Campaign", "New name:", camp.get("name", ""))
        if not new_name or not new_name.strip():
            return

        try:
            self._rename_nurture_campaign(self._nurture_selected_campaign_id, new_name.strip())
            self._refresh_nurture_campaigns()
            # Update the campaign name label in content view
            self._nurture_campaign_name_label.configure(text=new_name.strip())
            self._set_status(f"Campaign renamed to '{new_name}'", GOOD)
        except ValueError as e:
            messagebox.showerror("Error", str(e))

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
                self._configure_stripe_tags(self.contact_lists_table)
                for idx, row in enumerate(rows):
                    tag = "evenrow" if idx % 2 == 0 else "oddrow"
                    self.contact_lists_table.insert("", "end", values=(
                        row.get("Email", ""),
                        row.get("FirstName", ""),
                        row.get("LastName", ""),
                        row.get("Company", ""),
                        row.get("JobTitle", ""),
                        row.get("MobilePhone", ""),
                        row.get("WorkPhone", ""),
                    ), tags=(tag,))

            # IMMEDIATELY set as active contacts (persists to config)
            self._set_active_contacts(file_path)

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
        list_name = themed_askstring(self, "Name Your List", "Enter a name for this contact list:")

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

            # Refresh dropdown and select the new list
            self._refresh_contact_lists_main_dropdown()
            self.contact_lists_dropdown_var.set(safe_name)
            self._load_contacts_into_main_table(safe_name)

            # IMMEDIATELY set as active contacts (persists to config)
            self._set_active_contacts(dest)

        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import contacts:\n{e}")
            self._set_status("Import failed", DANGER)

    def _add_contact_to_list(self):
        """Open modal to add a new contact to the currently selected list"""
        from tkinter import messagebox
        import re

        selected_label = self.contact_lists_dropdown_var.get()
        if not selected_label:
            messagebox.showwarning("No List Selected", "Please select a contact list first.")
            return

        # Create modal dialog with FF styling
        dialog = tk.Toplevel(self)
        dialog.title("Add Contact")
        dialog.geometry("640x560")
        dialog.minsize(640, 460)
        dialog.configure(bg=BG_ROOT)
        dialog.transient(self)
        dialog.grab_set()

        # Center the dialog
        self._center_window(dialog, self)

        # --- Scroll container ---
        container = ttk.Frame(dialog)
        container.pack(fill="both", expand=True, padx=14, pady=14)

        canvas = tk.Canvas(container, highlightthickness=0, bg=BG_ROOT)
        vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)

        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(_):
            canvas.itemconfigure(win_id, width=canvas.winfo_width())

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mousewheel (Windows)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        dialog.bind("<Enter>", lambda e: dialog.bind_all("<MouseWheel>", _on_mousewheel))
        dialog.bind("<Leave>", lambda e: dialog.unbind_all("<MouseWheel>"))
        dialog.bind("<Destroy>", lambda e: dialog.unbind_all("<MouseWheel>"))

        # --- Card frame (FF styled) ---
        card = tk.Frame(inner, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        # Content padding inside card
        content = tk.Frame(card, bg=BG_CARD)
        content.pack(fill="both", expand=True, padx=22, pady=18)

        # Title
        tk.Label(content, text="Add New Contact", bg=BG_CARD, fg=FG_TEXT,
                 font=FONT_HEADING).pack(anchor="w", pady=(0, 14))

        # Helper for label + entry
        def field(label_text, required=False):
            lbl = tk.Label(content,
                           text=f"{label_text}{' *' if required else ''}",
                           bg=BG_CARD, fg=FG_MUTED, font=FONT_BODY_MEDIUM)
            lbl.pack(anchor="w", pady=(10, 4))

            var = tk.StringVar()
            ent = tk.Entry(content, textvariable=var, relief="solid", bd=1, highlightthickness=1,
                           highlightbackground=BORDER_MEDIUM, highlightcolor=ACCENT,
                           bg=BG_ENTRY, fg=FG_TEXT, insertbackground=FG_TEXT,
                           font=FONT_SECTION_TITLE)
            ent.pack(fill="x", ipady=7)
            return var, ent

        email_var, email_ent = field("Email", required=True)
        firstname_var, _ = field("First Name")
        lastname_var, _ = field("Last Name")
        company_var, _ = field("Company")
        jobtitle_var, _ = field("Job Title")

        # Focus email field
        email_ent.focus()

        def on_submit():
            email = email_var.get().strip()

            # Validate email
            if not email:
                messagebox.showwarning("Email Required", "Email address is required.")
                return

            # Basic email validation
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                messagebox.showwarning("Invalid Email", "Please enter a valid email address.")
                return

            # Get list name and file path
            if selected_label.startswith("Official – "):
                base_name = selected_label.replace("Official – ", "")
            else:
                base_name = selected_label

            file_path = os.path.join(CONTACTS_DIR, f"{base_name}.csv")

            try:
                # Read existing contacts
                rows, headers = safe_read_csv_rows(file_path)

                # Check for duplicate email (check both Email and Work Email)
                for row in rows:
                    existing_email = row.get("Email", "") or row.get("Work Email", "")
                    if existing_email.lower() == email.lower():
                        messagebox.showwarning("Duplicate Email", "This email already exists in the list.")
                        return

                # Determine which email field to use based on existing headers
                email_field = "Email"
                if headers and "Work Email" in headers and "Email" not in headers:
                    email_field = "Work Email"

                # Add new contact with matching headers
                new_contact = {}

                # Map to existing headers or use defaults
                if headers:
                    for h in headers:
                        new_contact[h] = ""

                    # Set email
                    if email_field in headers:
                        new_contact[email_field] = email
                    elif "Email" in headers:
                        new_contact["Email"] = email
                    else:
                        new_contact["Email"] = email
                        if "Email" not in headers:
                            headers.insert(0, "Email")

                    # Set other fields - try various common header names
                    firstname = firstname_var.get().strip()
                    lastname = lastname_var.get().strip()
                    company = company_var.get().strip()
                    jobtitle = jobtitle_var.get().strip()

                    for h in headers:
                        h_lower = h.lower().replace(" ", "").replace("_", "")
                        if h_lower in ["firstname", "first", "fname"]:
                            new_contact[h] = firstname
                        elif h_lower in ["lastname", "last", "lname"]:
                            new_contact[h] = lastname
                        elif h_lower in ["company", "companyname", "organization"]:
                            new_contact[h] = company
                        elif h_lower in ["jobtitle", "title", "position", "role"]:
                            new_contact[h] = jobtitle
                else:
                    # No existing headers, use defaults
                    headers = CONTACT_FIELDS
                    new_contact = {
                        "Email": email,
                        "FirstName": firstname_var.get().strip(),
                        "LastName": lastname_var.get().strip(),
                        "Company": company_var.get().strip(),
                        "JobTitle": jobtitle_var.get().strip(),
                        "MobilePhone": "",
                        "WorkPhone": "",
                    }

                rows.append(new_contact)

                # Write back to CSV with original headers
                import csv
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(rows)

                # Refresh table
                self._load_contacts_into_main_table(selected_label)
                self._set_status(f"Contact added to {base_name}", GOOD)

                dialog.destroy()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to add contact:\n{e}")

        # --- Buttons row ---
        btn_row = tk.Frame(content, bg=BG_CARD)
        btn_row.pack(fill="x", pady=(18, 0))

        cancel_btn = tk.Button(btn_row, text="Cancel",
                               font=FONT_BODY_MEDIUM,
                               bg=PRIMARY_50, fg=FG_TEXT, bd=0, padx=18, pady=10,
                               activebackground=BG_HOVER, cursor="hand2",
                               command=dialog.destroy)
        cancel_btn.pack(side="right", padx=(10, 0))

        add_btn = tk.Button(btn_row, text="Add Contact",
                            font=FONT_BODY_MEDIUM,
                            bg=DARK_AQUA, fg=FG_WHITE, bd=0, padx=18, pady=10,
                            activebackground=DARK_AQUA_HOVER, cursor="hand2",
                            command=on_submit)
        add_btn.pack(side="right")

    def _delete_selected_contacts(self):
        """Delete selected contacts from the currently selected list"""
        from tkinter import messagebox

        selected_label = self.contact_lists_dropdown_var.get()
        if not selected_label:
            messagebox.showwarning("No List Selected", "Please select a contact list first.")
            return

        # Get selected items
        selected_items = self.contact_lists_table.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select one or more contacts to delete.")
            return

        # Confirm deletion
        count = len(selected_items)
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete {count} contact(s)?\nThis action cannot be undone."
        )

        if not confirm:
            return

        # Get list name and file path
        if selected_label.startswith("Official – "):
            base_name = selected_label.replace("Official – ", "")
        else:
            base_name = selected_label

        file_path = os.path.join(CONTACTS_DIR, f"{base_name}.csv")

        try:
            # Get emails to delete
            emails_to_delete = set()
            for item in selected_items:
                values = self.contact_lists_table.item(item, "values")
                if values:
                    emails_to_delete.add(values[0])  # Email is first column

            # Read existing contacts
            rows, headers = safe_read_csv_rows(file_path)

            # Filter out deleted contacts
            filtered_rows = [row for row in rows if row.get("Email", "") not in emails_to_delete]

            # Write back to CSV
            import csv
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CONTACT_FIELDS)
                writer.writeheader()
                writer.writerows(filtered_rows)

            # Refresh table
            self._load_contacts_into_main_table(selected_label)
            self._set_status(f"Deleted {count} contact(s) from {base_name}", GOOD)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete contacts:\n{e}")
            self._set_status("Delete failed", DANGER)

    def _delete_current_contact_list(self):
        """Delete the currently selected contact list"""
        from tkinter import messagebox

        selected_label = self.contact_lists_dropdown_var.get()
        if not selected_label:
            messagebox.showwarning("No List Selected", "Please select a contact list to delete.")
            return

        # Get list name
        if selected_label.startswith("Official – "):
            base_name = selected_label.replace("Official – ", "")
        else:
            base_name = selected_label

        # Confirm deletion with strong warning
        confirm = messagebox.askyesno(
            "Delete Contact List",
            f"Are you sure you want to DELETE the entire list '{base_name}'?\n\n"
            f"This will permanently remove all contacts in this list.\n"
            f"This action CANNOT be undone.\n\n"
            f"Continue?"
        )

        if not confirm:
            return

        file_path = os.path.join(CONTACTS_DIR, f"{base_name}.csv")

        try:
            # Delete the file
            if os.path.exists(file_path):
                os.remove(file_path)

            # Clear the table
            for item in self.contact_lists_table.get_children():
                self.contact_lists_table.delete(item)

            # Refresh dropdown
            self._refresh_contact_lists_main_dropdown()
            self.contact_lists_dropdown_var.set("")

            self._set_status(f"Deleted list '{base_name}'", GOOD)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete list:\n{e}")
            self._set_status("Delete failed", DANGER)

    def _update_contact_lists(self):
        """Update all contact lists - refreshes both Manage Contacts and Choose Contacts dropdowns"""
        try:
            # Refresh the Manage Contacts dropdown
            self._refresh_contact_lists_main_dropdown()

            # Refresh the Choose Contact List dropdown
            self._load_contact_lists_on_startup()

            # Update the Manage Contacts Combobox values
            if hasattr(self, 'contact_lists_dropdown'):
                # Get list of contact list names
                names = sorted(self.contact_lists.keys()) if hasattr(self, 'contact_lists') else []
                self.contact_lists_dropdown["values"] = names

                # Keep current selection if still valid, otherwise select first
                current = self.contact_lists_dropdown_var.get().strip()
                if names:
                    if current not in names:
                        self.contact_lists_dropdown_var.set(names[0])
                else:
                    self.contact_lists_dropdown_var.set("")

            # Update the Choose Contacts Combobox if it exists
            if hasattr(self, 'selected_contact_list_var') and hasattr(self, 'contact_lists'):
                # This may be a different dropdown on Choose Contacts page
                # Refresh by rebuilding the values
                pass  # The _load_contact_lists_on_startup handles this

            self._set_status("Contact lists updated successfully", GOOD)
            self.toast.show("All contact lists updated", "success")

        except Exception as e:
            self._set_status("Update failed", DANGER)
            messagebox.showerror("Error", f"Failed to update lists:\n{e}")

    # ============================================
    # Main layout for Build Emails screen - ONLY EMAIL EDITOR
    # ============================================
    def _build_main_layout(self, parent):
        # Build emails screen - focused on writing
        main = ttk.Frame(parent, style="FF.Page.TFrame")
        main.pack(side="top", fill="both", expand=True)

        self.add_page_header(main, "Email Editor", "Compose your email sequence with personalization")

        content = ttk.Frame(main, style="FF.Page.TFrame")
        content.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self._build_email_editor(content)

        if not self.subject_vars:
            self._init_default_emails()

        # Initialize template controls (now in the email editor header row)
        self._refresh_templates_dropdown()
        self._restore_last_selected_template()
        if not (self.template_var.get() or "").strip():
            self.template_var.set("None")
        self._update_template_buttons()

    # ============================================
    # Status bar
    # ============================================
    def _build_status_bar(self):
        bar = tk.Frame(self, bg=BG_CARD)
        bar.pack(side="bottom", fill="x")

        self.status_dot = tk.Label(bar, text="●", bg=BG_CARD, fg=GOOD, font=FONT_BASE)
        self.status_dot.pack(side="left", padx=(12, 6), pady=8)

        self.status_var = tk.StringVar(value="Ready")
        # ANTI-FLICKER: Fixed width prevents resizing when text changes
        self.status_label = tk.Label(
            bar,
            textvariable=self.status_var,
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_SMALL,
            width=60,  # Fixed width prevents window resize on text change
            anchor="w"
        )
        self.status_label.pack(side="left", pady=8)

        spacer = tk.Label(bar, text="", bg=BG_CARD)
        spacer.pack(side="left", expand=True, fill="x")

        tk.Label(bar, text="MV", bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 8, "italic")).pack(
            side="right", padx=(0, 10)
        )

    def _substitute_variables(self, template: str, contact_data: dict) -> str:
        """
        Replace {FirstName}, {LastName}, {Company}, {Email}, etc. in the template
        with actual contact data values.
        """
        if not template:
            return template

        # Build tokens from contact data (handle different column name formats)
        tokens = {
            "FirstName": contact_data.get("FirstName", contact_data.get("First Name", "")),
            "LastName": contact_data.get("LastName", contact_data.get("Last Name", "")),
            "Company": contact_data.get("Company", ""),
            "Email": contact_data.get("Email", contact_data.get("Work Email", "")),
            "Work Email": contact_data.get("Work Email", contact_data.get("Email", "")),
            "Title": contact_data.get("Title", contact_data.get("JobTitle", "")),
            "JobTitle": contact_data.get("JobTitle", contact_data.get("Title", "")),
            "City": contact_data.get("City", ""),
            "State": contact_data.get("State", ""),
            "Phone": contact_data.get("Phone", contact_data.get("Mobile Phone", "")),
        }

        # Also add any other fields from the contact data directly
        for key, value in contact_data.items():
            if key not in tokens:
                tokens[key] = value or ""

        # Replace all placeholders
        result = template
        for key, value in tokens.items():
            placeholder = "{" + key + "}"
            result = result.replace(placeholder, str(value) if value else "")

        return result

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

    def _debounce(self, attr_name: str, delay_ms: int, func):
        """Generic debouncer: schedules func after delay_ms; cancels prior pending call."""
        after_id = getattr(self, attr_name, None)
        if after_id:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        setattr(self, attr_name, self.after(delay_ms, func))

    # ============================================
    # UI helpers
    # ============================================
    def _make_fancy_box(self, parent, title: str, subtitle: str = ""):
        outer = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat", bd=0)
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        header = tk.Frame(outer, bg=BG_ENTRY)
        header.pack(fill="x", padx=10, pady=(10, 6))

        tk.Label(header, text=title, bg=BG_ENTRY, fg=ACCENT, font=FONT_SECTION).pack(anchor="w")

        if subtitle:
            tk.Label(header, text=subtitle, bg=BG_ENTRY, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", pady=(2, 0))

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

            if "×" not in tab_text:
                return

            # Delete immediately without confirmation
            self._delete_email_tab(clicked_index)

        except Exception:
            pass

    def _on_tab_close_click(self, event):
        """Handle click on the × portion of a tab label."""
        if not hasattr(self, "email_notebook"):
            return
        if len(self.subject_vars) <= 1:
            return  # Only one tab — no close
        try:
            clicked_index = self.email_notebook.index(f"@{event.x},{event.y}")
            tab_id = self.email_notebook.tabs()[clicked_index]
            tab_text = self.email_notebook.tab(tab_id, "text")
            if "×" not in tab_text:
                return
            # Find the right edge of this tab by probing 1px at a time
            probe_x = event.x
            try:
                while self.email_notebook.index(f"@{probe_x},{event.y}") == clicked_index:
                    probe_x += 1
            except Exception:
                pass
            right_edge = probe_x
            click_from_right = right_edge - event.x
            # The "  ×  " occupies roughly the last 30px of the tab
            if click_from_right > 30:
                return  # Clicked on the label text, not the ×
            self.after(1, lambda idx=clicked_index: self._delete_email_tab(idx))
            return "break"
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
        """Refresh all email tab labels with × close indicator."""
        if not hasattr(self, "email_notebook"):
            return

        tabs = self.email_notebook.tabs()
        num_emails = len(self.name_vars)
        show_close = num_emails > 1

        for i in range(num_emails):
            if i < len(tabs):
                label = self.name_vars[i].get().strip() or f"Email {i+1}"
                if show_close:
                    self.email_notebook.tab(tabs[i], text=f"  {label}  ×  ")
                else:
                    self.email_notebook.tab(tabs[i], text=f"  {label}  ")

        pass  # end of _refresh_tab_labels

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
            font=FONT_SECTION,
            cursor="hand2",
        )
        arrow.pack(side="left")

        title_lbl = tk.Label(
            header,
            text=title,
            bg=BG_ENTRY,
            fg=ACCENT,
            font=FONT_BUTTON,
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
                font=FONT_SMALL,
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

        # Template Header: dropdown + buttons
        template_row = tk.Frame(card, bg=BG_CARD)
        template_row.pack(fill="x", padx=22, pady=(12, 0))
        template_row.columnconfigure(1, weight=1)

        tk.Label(
            template_row, text="Your Templates:",
            bg=BG_CARD, fg=FG_TEXT, font=FONT_LABEL,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.my_template_combo = ttk.Combobox(
            template_row,
            textvariable=self.template_var,
            values=self._my_template_values(),
            state="readonly",
            font=FONT_BASE,
            style="Dark.TCombobox",
        )
        self.my_template_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.my_template_combo.bind("<<ComboboxSelected>>", self._on_template_selected)

        # Separator below template header row
        ttk.Separator(card, orient="horizontal").pack(fill="x", padx=22, pady=(14, 12))

        # Email controls row: Add/Delete on left, Explore/Save on right
        controls_row = tk.Frame(card, bg=BG_CARD)
        controls_row.pack(fill="x", padx=22, pady=(0, 12))

        tk.Button(
            controls_row,
            text="Save New Template",
            command=self._prompt_save_template,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BTN_SM,
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="right", padx=(8, 0))

        ai_camp_btn = tk.Button(
            controls_row,
            text="AI Campaign",
            command=self._open_ai_campaign_dialog,
            bg="#3B82F6", fg="#FFFFFF",
            activebackground="#2563EB", activeforeground="#FFFFFF",
            relief="flat", font=FONT_BTN_SM,
            padx=12, pady=6, cursor="hand2",
        )
        ai_camp_btn.pack(side="right", padx=(8, 0))
        ai_camp_btn.bind("<Enter>", lambda e: ai_camp_btn.config(bg="#2563EB"))
        ai_camp_btn.bind("<Leave>", lambda e: ai_camp_btn.config(bg="#3B82F6"))
        ToolTip(ai_camp_btn, "Use ChatGPT to generate an entire email campaign from a description.")

        tk.Button(
            controls_row,
            text="Explore Templates",
            command=self._explore_templates,
            bg="#7C3AED",
            fg="#FFFFFF",
            activebackground="#6D28D9",
            activeforeground="#FFFFFF",
            relief="flat",
            font=FONT_BTN_SM,
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="right")

        # Email tabs
        self.email_notebook = ttk.Notebook(card)
        self.email_notebook.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Permanent "+" tab at the end for adding emails
        self._add_tab_frame = tk.Frame(self.email_notebook, bg=BG_CARD)
        self.email_notebook.add(self._add_tab_frame, text="  +  ")

        # Bind tab change event
        self.email_notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Bind close button click on tabs (ButtonPress for immediate response)
        self.email_notebook.bind("<ButtonPress-1>", self._on_tab_close_click, add=True)

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
                font=FONT_SMALL,
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

    # ---------- Shared Templates (OneDrive) ----------

    def _ensure_shared_dirs(self) -> bool:
        """Create shared template folders if OneDrive root is accessible. Returns True if available."""
        try:
            if not SHARED_TEMPLATES_ROOT.parent.exists():
                return False
            SHARED_TEAM_DIR.mkdir(parents=True, exist_ok=True)
            SHARED_USER_DIR.mkdir(parents=True, exist_ok=True)
            return True
        except (PermissionError, OSError):
            return False

    def _shared_available(self) -> bool:
        """Check if the shared OneDrive template root is accessible (cached)."""
        if not hasattr(self, "_shared_ok"):
            self._shared_ok = self._ensure_shared_dirs()
        return self._shared_ok

    def _team_writable(self) -> bool:
        """Check if the current user can write to the Team templates folder."""
        try:
            test = SHARED_TEAM_DIR / ".write_test"
            test.write_text("test")
            test.unlink()
            return True
        except (PermissionError, OSError):
            return False

    def _check_is_admin(self) -> bool:
        """Admin = in registry admins list (by username or email), or Team-folder-writable (bootstrap)."""
        config = load_config()
        username = config.get("username", "")
        email = config.get("user_email", "")
        if username and is_admin(username):
            return True
        if email and is_admin(email):
            return True
        # Bootstrap: if user can write to Team folder, they're an admin
        return self._team_writable()

    def _list_shared_templates(self, folder: Path) -> List[str]:
        """List template names (stems) from a shared folder."""
        try:
            if not folder.is_dir():
                return []
            return sorted(
                [f.stem for f in folder.glob("*.json")],
                key=lambda s: s.lower()
            )
        except (PermissionError, OSError):
            return []

    def _resolve_template_path(self, selection: str) -> Optional[Path]:
        """Map a prefixed dropdown value to a file path."""
        if selection.startswith("team:"):
            return SHARED_TEAM_DIR / f"{selection[5:]}.json"
        elif selection.startswith("user:"):
            return SHARED_USER_DIR / f"{selection[5:]}.json"
        elif selection.startswith("local:"):
            return Path(TEMPLATES_DIR) / f"{selection[6:]}.json"
        else:
            return Path(TEMPLATES_DIR) / f"{selection}.json"

    def _display_name(self, selection: str) -> str:
        """Strip the prefix from a dropdown value for display."""
        for prefix in ("team:", "user:", "local:"):
            if selection.startswith(prefix):
                return selection[len(prefix):]
        return selection

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
        template_name = themed_askstring(self, "Save Template", "Enter a name for this template:")
        
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
                if is_html(body):
                    html_to_text_widget(self.body_texts[current_tab], body)
                else:
                    self.body_texts[current_tab].delete("1.0", "end")
                    self.body_texts[current_tab].insert("1.0", body)
                # Clear undo history so Ctrl+Z doesn't undo the template load
                self.body_texts[current_tab].edit_reset()
                self.body_texts[current_tab].edit_modified(False)
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
        """All templates combined (kept for compatibility)."""
        items = ["None"]
        if self._shared_available():
            team = self._list_shared_templates(SHARED_TEAM_DIR)
            mine = self._list_shared_templates(SHARED_USER_DIR)
            if team:
                items.extend([f"team:{n}" for n in team])
            if mine:
                items.extend([f"user:{n}" for n in mine])
        local = self._list_templates()
        if local:
            items.extend([f"local:{n}" for n in local])
        return items

    def _my_template_values(self) -> List[str]:
        """User + local templates for the Your Templates dropdown (clean display names)."""
        self._tmpl_display_to_key = {}  # display name -> prefixed key
        items = ["None"]
        seen = set()
        if self._shared_available():
            mine = self._list_shared_templates(SHARED_USER_DIR)
            for n in mine:
                if n not in seen:
                    items.append(n)
                    self._tmpl_display_to_key[n] = f"user:{n}"
                    seen.add(n)
        local = self._list_templates()
        for n in local:
            if n not in seen:
                items.append(n)
                self._tmpl_display_to_key[n] = f"local:{n}"
                seen.add(n)
        return items

    def _refresh_templates_dropdown(self) -> None:
        try:
            if hasattr(self, "my_template_combo"):
                self.my_template_combo["values"] = self._my_template_values()
        except Exception:
            pass

    @staticmethod
    def _btn_state(widget, state: str) -> None:
        """Set state on a button, handling make_button's border_frame wrapper."""
        btn = getattr(widget, "_inner_btn", widget)
        try:
            btn.configure(state=state)
        except Exception:
            pass

    def _update_template_buttons(self) -> None:
        sel = (self.template_var.get() or "").strip()
        chosen = bool(sel) and sel != "None"
        try:
            if hasattr(self, "btn_delete_tmpl"):
                self._btn_state(self.btn_delete_tmpl, "normal" if chosen else "disabled")
        except Exception:
            pass


    def _on_template_selected(self, _evt=None) -> None:
        sel = (self.template_var.get() or "").strip()
        if not sel or sel == "None":
            self._update_template_buttons()
            return
        # Resolve display name to prefixed key if needed
        key = getattr(self, "_tmpl_display_to_key", {}).get(sel, sel)
        self._update_template_buttons()
        self._persist_template_selection(key)
        self._load_template(key)

    def _persist_template_selection(self, template_name: str) -> None:
        """Save the full prefixed template selection to config for persistence across restarts."""
        if not template_name or template_name == "None":
            return
        try:
            config = load_config()
            config["last_selected_template_id"] = template_name
            save_config(config)
        except Exception:
            pass

    def _restore_last_selected_template(self) -> None:
        """Auto-select and auto-load the last used template from config on startup."""
        try:
            config = load_config()
            last_id = config.get("last_selected_template_id", "")

            if not last_id:
                last_id = "default-outreach-5-step"

            # If the persisted value already has a prefix, try resolving it directly
            if any(last_id.startswith(p) for p in ("team:", "user:", "local:")):
                path = self._resolve_template_path(last_id)
                if path and path.is_file():
                    display = self._display_name(last_id)
                    self.template_var.set(display)
                    self._load_template(last_id, skip_confirmation=True)
                    return

            # Legacy: search by system_template_id or stem across all directories
            search_dirs = []
            if self._shared_available():
                search_dirs.append(("team", SHARED_TEAM_DIR))
                search_dirs.append(("user", SHARED_USER_DIR))
            search_dirs.append(("local", Path(TEMPLATES_DIR)))

            for prefix, folder in search_dirs:
                if not folder.is_dir():
                    continue
                for template_file in folder.glob("*.json"):
                    try:
                        with open(template_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        tid = data.get("system_template_id", template_file.stem)
                        if tid == last_id or template_file.stem == last_id:
                            prefixed = f"{prefix}:{template_file.stem}"
                            self.template_var.set(template_file.stem)
                            self._load_template(prefixed, skip_confirmation=True)
                            return
                    except Exception:
                        continue

        except Exception:
            pass

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
            font=FONT_BASE,
        ).pack(anchor="w", padx=14, pady=(14, 6))

        current = self._display_name((self.template_var.get() or "").strip())
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
        ent.pack(fill="x", padx=14, pady=(0, 14))
        ent.focus_set()

        # Public / Private toggle
        visibility_var = tk.StringVar(value="private")

        toggle_row = tk.Frame(dlg, bg=BG_ROOT)
        toggle_row.pack(fill="x", padx=14, pady=(0, 14))

        PURPLE = "#7C3AED"
        PURPLE_HOVER = "#6D28D9"

        def _update_toggle():
            is_public = visibility_var.get() == "public"
            pub_btn.config(
                bg=PURPLE if is_public else BG_ENTRY,
                fg="white" if is_public else FG_MUTED,
            )
            priv_btn.config(
                bg=PURPLE if not is_public else BG_ENTRY,
                fg="white" if not is_public else FG_MUTED,
            )

        pub_btn = tk.Button(
            toggle_row,
            text="Public",
            command=lambda: (visibility_var.set("public"), _update_toggle()),
            bg=BG_ENTRY,
            fg=FG_MUTED,
            activebackground=PURPLE_HOVER,
            activeforeground="white",
            relief="flat",
            font=FONT_BUTTON,
            padx=16,
            pady=6,
            cursor="hand2",
        )
        pub_btn.pack(side="left", padx=(0, 4))

        priv_btn = tk.Button(
            toggle_row,
            text="Private",
            command=lambda: (visibility_var.set("private"), _update_toggle()),
            bg=PURPLE,
            fg="white",
            activebackground=PURPLE_HOVER,
            activeforeground="white",
            relief="flat",
            font=FONT_BUTTON,
            padx=16,
            pady=6,
            cursor="hand2",
        )
        priv_btn.pack(side="left")

        # Save button (right-aligned)
        def _do_save():
            nm = self._safe_template_filename(name_var.get())
            if not nm:
                messagebox.showerror("Missing", "Enter a template name.")
                return
            dest = "arena" if visibility_var.get() == "public" else "mine"
            dlg.destroy()
            self._save_template_to(nm, dest)

        tk.Button(
            toggle_row,
            text="Save",
            command=_do_save,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BUTTON,
            padx=20,
            pady=6,
            cursor="hand2",
        ).pack(side="right")

        # ANTI-FLICKER: Use after() instead of update_idletasks() for centering
        def _center():
            try:
                x = self.winfo_rootx() + (self.winfo_width() // 2) - (dlg.winfo_width() // 2)
                y = self.winfo_rooty() + (self.winfo_height() // 2) - (dlg.winfo_height() // 2)
                dlg.geometry(f"+{x}+{y}")
            except:
                pass
        dlg.after(10, _center)

    def _save_template(self, name: str) -> None:
        """Legacy save — saves to user/local folder."""
        self._save_template_to(name, "mine")

    def _save_template_to(self, name: str, dest: str = "mine") -> None:
        """Save template to Arena (team) or personal (user/local) folder."""
        safe = self._safe_template_filename(name)

        if dest == "arena":
            if not self._shared_available():
                messagebox.showerror("Unavailable", "Arena shared folder is not accessible.")
                return
            folder = SHARED_TEAM_DIR
            prefix = "team:"
        elif self._shared_available():
            folder = SHARED_USER_DIR
            prefix = "user:"
        else:
            self._ensure_templates_dir()
            folder = Path(TEMPLATES_DIR)
            prefix = "local:"

        path = folder / f"{safe}.json"

        if path.exists():
            ok = messagebox.askyesno(
                "Template Exists",
                f"A template named '{safe}' already exists.\n\nOverwrite it?",
            )
            if not ok:
                return

        cfg = self._collect_config()
        payload = {
            "template_name": safe,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "config": cfg,
        }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except PermissionError:
            messagebox.showerror("Permission Denied", "You don't have write access to that folder.")
            self._set_status("Save failed", DANGER)
            return
        except Exception as e:
            messagebox.showerror("Save Failed", f"Could not save template:\n{e}")
            self._set_status("Save failed", DANGER)
            return

        self._refresh_templates_dropdown()
        self.template_var.set(safe)
        self._update_template_buttons()
        dest_label = "Arena" if dest == "arena" else "your templates"
        self._set_status("Template saved", GOOD)
        self.toast.show(f"Template '{safe}' saved to {dest_label}", "success")

    def _overwrite_selected_template(self) -> None:
        name = (self.template_var.get() or "").strip()
        if not name or name == "None":
            messagebox.showinfo("Select a template", "Choose a template from the dropdown first.")
            return
        if name.startswith("team:"):
            messagebox.showinfo("Team Template", "Cannot overwrite a Team template.\nUse 'Save as New' to save your own version.")
            return

        display = self._display_name(name)
        ok = messagebox.askyesno(
            "Overwrite Template",
            f"Overwrite template '{display}' with your current sequence?\n\nThis will replace the saved version of that template.",
        )
        if not ok:
            self._set_status("Overwrite cancelled", WARN)
            return

        # Overwrite in place using the resolved path
        safe = self._safe_template_filename(display)
        path = self._resolve_template_path(name)
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
        self._update_template_buttons()
        self._set_status("Template overwritten", GOOD)
        self.toast.show(f"Template '{display}' overwritten", "success")

    def _load_template(self, name: str, skip_confirmation: bool = False) -> None:
        name = (name or "").strip()
        if not name or name == "None":
            return

        path = self._resolve_template_path(name)
        if not path or not path.is_file():
            if not skip_confirmation:
                messagebox.showerror("Not found", f"Template not found:\n{path}")
            self._set_status("Template not found", DANGER)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            cfg = payload.get("config", payload)
        except Exception as e:
            if not skip_confirmation:
                messagebox.showerror("Load Failed", f"Could not read template:\n{e}")
            self._set_status("Load failed", DANGER)
            return

        display = self._display_name(name)

        try:
            self._load_from_config_dict(cfg)
            if not skip_confirmation:
                self._set_status("Template loaded", GOOD)
        except Exception:
            _write_crash_log("template_load")
            if not skip_confirmation:
                messagebox.showerror("Load Failed", "Could not apply template. Check logs.")
            self._set_status("Load failed", DANGER)
            return

    def _delete_template(self, name: str) -> None:
        name = (name or "").strip()
        if not name or name == "None":
            messagebox.showinfo("Select a template", "Choose a template from the dropdown.")
            return
        # Resolve display name to prefixed key
        key = getattr(self, "_tmpl_display_to_key", {}).get(name, name)
        if key.startswith("team:"):
            messagebox.showinfo("Team Template", "Team templates cannot be deleted from here.\nAsk an admin to remove it from the Team folder.")
            return

        display = self._display_name(key)
        path = self._resolve_template_path(key)
        if not path or not path.is_file():
            messagebox.showerror("Not found", f"Template not found:\n{path}")
            self._set_status("Template not found", DANGER)
            return

        ok = messagebox.askyesno(
            "Delete Template",
            f"Delete template '{display}'?\n\nThis won't delete any emails already scheduled.",
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

    def _explore_templates(self) -> None:
        """Open a dialog listing Arena/team templates to choose from."""
        if not self._shared_available():
            messagebox.showinfo("Unavailable", "Arena shared templates folder is not accessible.")
            return

        team = self._list_shared_templates(SHARED_TEAM_DIR)
        if not team:
            messagebox.showinfo("No Templates", "No Arena templates found in the shared folder.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Explore Templates")
        dlg.configure(bg=BG_ROOT)
        dlg.resizable(False, False)
        dlg.geometry("420x400")

        tk.Label(
            dlg, text="Arena Templates",
            bg=BG_ROOT, fg=FG_TEXT, font=FONT_SECTION_TITLE,
        ).pack(anchor="w", padx=14, pady=(14, 4))

        tk.Label(
            dlg, text="Select a template to load into the editor",
            bg=BG_ROOT, fg=FG_MUTED, font=FONT_SMALL,
        ).pack(anchor="w", padx=14, pady=(0, 10))

        # Scrollable listbox
        list_frame = tk.Frame(dlg, bg=BG_ROOT)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(
            list_frame,
            bg=BG_ENTRY, fg=FG_TEXT, font=FONT_BASE,
            selectbackground="#7C3AED", selectforeground="#FFFFFF",
            highlightthickness=1, highlightbackground=GRAY_200, highlightcolor="#7C3AED",
            relief="flat", yscrollcommand=scrollbar.set,
        )
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        for name in team:
            listbox.insert("end", name)

        btn_row = tk.Frame(dlg, bg=BG_ROOT)
        btn_row.pack(fill="x", padx=14, pady=(0, 14))

        def _do_load():
            sel = listbox.curselection()
            if not sel:
                return
            name = team[sel[0]]
            prefixed = f"team:{name}"
            dlg.destroy()
            self.template_var.set(name)
            self._update_template_buttons()
            self._persist_template_selection(prefixed)
            self._load_template(prefixed)

        tk.Button(
            btn_row, text="Cancel", command=dlg.destroy,
            bg=BG_CARD, fg=FG_TEXT, activebackground=BG_HOVER, activeforeground=FG_TEXT,
            relief="flat", padx=12, pady=7, cursor="hand2",
        ).pack(side="right")

        tk.Button(
            btn_row, text="Load Template", command=_do_load,
            bg="#7C3AED", fg="#FFFFFF", activebackground="#6D28D9", activeforeground="#FFFFFF",
            relief="flat", padx=12, pady=7, cursor="hand2",
        ).pack(side="right", padx=(0, 8))

        listbox.bind("<Double-Button-1>", lambda _e: _do_load())

        def _center():
            try:
                x = self.winfo_rootx() + (self.winfo_width() // 2) - (dlg.winfo_width() // 2)
                y = self.winfo_rooty() + (self.winfo_height() // 2) - (dlg.winfo_height() // 2)
                dlg.geometry(f"420x400+{x}+{y}")
            except Exception:
                pass
        dlg.after(10, _center)

    def _publish_to_team(self) -> None:
        """Copy the selected template to the shared Team folder."""
        sel = (self.template_var.get() or "").strip()
        if not sel or sel == "None" or sel.startswith("\u2500\u2500"):
            messagebox.showinfo("Select Template", "Choose one of your templates to publish.")
            return
        if sel.startswith("team:"):
            messagebox.showinfo("Already Published", "This template is already in Team Templates.")
            return

        source = self._resolve_template_path(sel)
        if not source or not source.is_file():
            messagebox.showerror("Not Found", "Template file not found.")
            return

        display = self._display_name(sel)
        safe = self._safe_template_filename(display)
        dest = SHARED_TEAM_DIR / f"{safe}.json"

        if dest.exists():
            ok = messagebox.askyesno(
                "Name Conflict",
                f"A Team template named '{safe}' already exists.\n\nOverwrite it?",
            )
            if not ok:
                return

        try:
            shutil.copy2(str(source), str(dest))
            self.toast.show(f"Published '{safe}' to Team Templates", "success")
            self._refresh_templates_dropdown()
        except PermissionError:
            messagebox.showerror("Permission Denied", "You don't have write access to the Team folder.")
        except Exception as e:
            messagebox.showerror("Publish Failed", f"Could not publish template:\n{e}")

    def _refresh_sequence_to_default(self) -> None:
        ok = messagebox.askyesno(
            "Reset Sequence",
            "Reset this sequence back to the default 5-email layout?\n\n"
            "This will remove Email 6+ and clear per-email attachments.",
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

        config = load_config()
        default_email_count = config.get("default_email_count", 5)

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
                for i in range(default_email_count)
            ],
            "test_email": self.test_email_var.get(),
        }

        self._load_from_config_dict(default_cfg)
        self.template_var.set("None")
        self._refresh_templates_dropdown()
        self._update_template_buttons()
        self._set_status("Sequence reset", GOOD)
        messagebox.showinfo("Reset", f"Sequence reset to Email 1–Email {default_email_count}.")

    def _create_templates_panel(self, parent):
        self._ensure_templates_dir()

        _, content, _ = self._make_collapsible_panel(
            parent,
            title="Templates",
            subtitle="Save and reuse email sequences",
            start_open=False,
        )

        row1 = tk.Frame(content, bg=BG_ENTRY)
        row1.pack(fill="x", pady=(0, 4))

        tk.Label(
            row1,
            text="Template:",
            bg=BG_ENTRY,
            fg=FG_MUTED,
            font=FONT_SMALL,
        ).pack(side="left")

        self.template_combo = ttk.Combobox(
            row1,
            textvariable=self.template_var,
            values=self._template_values(),
            state="readonly",
            width=36,
            style="Dark.TCombobox",
        )
        self.template_combo.pack(side="left", padx=(8, 0))
        self.template_combo.bind("<<ComboboxSelected>>", self._on_template_selected)

        # Source label (Team / My / Local)
        self.lbl_source = tk.Label(content, text="", bg=BG_ENTRY, fg=FG_MUTED, font=FONT_SMALL)
        self.lbl_source.pack(anchor="w", pady=(0, 6))

        row2 = tk.Frame(content, bg=BG_ENTRY)
        row2.pack(fill="x")

        make_button(
            row2, text="Save as New",
            command=self._prompt_save_template,
            variant="primary", size="sm",
        ).pack(side="left")

        self.btn_overwrite = make_button(
            row2, text="Overwrite Selected",
            command=self._overwrite_selected_template,
            variant="secondary", size="sm",
        )
        self.btn_overwrite.pack(side="left", padx=(8, 0))
        self._btn_state(self.btn_overwrite, "disabled")

        self.btn_delete_tmpl = make_button(
            row2, text="Delete",
            command=lambda: self._delete_template((self.template_var.get() or "").strip()),
            variant="danger", size="sm",
        )
        self.btn_delete_tmpl.pack(side="left", padx=(8, 0))
        self._btn_state(self.btn_delete_tmpl, "disabled")

        if self._shared_available():
            self.btn_publish = make_button(
                row2, text="Publish to Team",
                command=self._publish_to_team,
                variant="secondary", size="sm",
            )
            self.btn_publish.pack(side="left", padx=(8, 0))
            self._btn_state(self.btn_publish, "disabled")

        make_button(
            row2, text="Reset Sequence",
            command=self._refresh_sequence_to_default,
            variant="ghost", size="sm",
        ).pack(side="left", padx=(8, 0))

        self._refresh_templates_dropdown()

        # Auto-select the last used template from config
        self._restore_last_selected_template()

        # Fallback to "None" if no template is selected
        if not (self.template_var.get() or "").strip():
            self.template_var.set("None")
        self._update_template_buttons()

    def _create_email_tab(self, index: int, name_var: tk.StringVar, subject_var: tk.StringVar, body_text: str = "") -> tk.Text:
        tab = tk.Frame(self.email_notebook, bg=BG_CARD)

        label = name_var.get().strip() or f"Email {index}"
        # Count real email tabs (exclude the "+" tab)
        real_count = sum(1 for t in self.email_notebook.tabs()
                         if not hasattr(self, '_add_tab_frame') or t != str(self._add_tab_frame))
        tab_text = f"  {label}  ×  " if real_count >= 1 else f"  {label}  "
        if hasattr(self, '_add_tab_frame'):
            try:
                plus_idx = self.email_notebook.index(self._add_tab_frame)
                self.email_notebook.insert(plus_idx, tab, text=tab_text)
            except Exception:
                self.email_notebook.add(tab, text=tab_text)
        else:
            self.email_notebook.add(tab, text=tab_text)

        # Simple content frame with padding (no fancy box, no inner card)
        inner = tk.Frame(tab, bg=BG_CARD)
        inner.pack(fill="both", expand=True, padx=20, pady=20)

        # Email Name / Subject Line — single combined field
        header_row = tk.Frame(inner, bg=BG_CARD)
        header_row.pack(fill="x", pady=(0, 16))

        tk.Label(header_row, text="Email Name / Subject Line", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")

        entry_row = tk.Frame(header_row, bg=BG_CARD)
        entry_row.pack(fill="x", pady=(4, 0))
        entry_row.columnconfigure(0, weight=1)  # Subject entry expands

        ent_subject = tk.Entry(
            entry_row,
            textvariable=subject_var,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            highlightthickness=1,
            highlightbackground=GRAY_200,
            highlightcolor=ACCENT,
        )
        ent_subject.grid(row=0, column=0, sticky="ew")

        # Sync name_var from subject_var so tabs and all name references auto-update
        def _on_subject_change(*_):
            val = subject_var.get()
            if name_var.get() != val:
                name_var.set(val)
        subject_var.trace_add("write", _on_subject_change)

        def _on_name_change(*_):
            self._refresh_tab_labels()
        name_var.trace_add("write", _on_name_change)

        # Track last focused editor (subject)
        ent_subject.bind("<FocusIn>", lambda _e, w=ent_subject: setattr(self, "_last_editor_widget", w))

        # Store reference to body text widget for variable insertion
        txt_body_ref = [None]  # Use list to allow modification in nested function

        # "+ Insert variable" button
        btn_var = tk.Button(
            entry_row,
            text="+ Insert variable",
            command=lambda: self._show_variable_popup(ent_subject, txt_body_ref[0]),
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_SMALL,
            padx=10,
            pady=5,
            cursor="hand2",
        )
        btn_var.grid(row=0, column=1, sticky="w", padx=(8, 0))

        # "Add/Edit Signature" button
        btn_sig = tk.Button(
            entry_row,
            text="Add/Edit Signature",
            command=self._open_signature_editor,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_SMALL,
            padx=10,
            pady=5,
            cursor="hand2",
        )
        btn_sig.grid(row=0, column=2, sticky="w", padx=(8, 0))

        # "AI Assist" button (ChatGPT)
        btn_ai = tk.Button(
            entry_row,
            text="AI Assist",
            command=lambda: self._open_ai_assist_dialog(ent_subject, txt_body_ref),
            bg="#3B82F6", fg="#FFFFFF",
            activebackground="#2563EB", activeforeground="#FFFFFF",
            relief="flat", font=("Segoe UI Semibold", 9),
            padx=10, pady=5, cursor="hand2",
        )
        btn_ai.grid(row=0, column=3, sticky="w", padx=(8, 0))
        btn_ai.bind("<Enter>", lambda e: btn_ai.config(bg="#2563EB"))
        btn_ai.bind("<Leave>", lambda e: btn_ai.config(bg="#3B82F6"))
        ToolTip(btn_ai, "Use ChatGPT to write, improve, or rewrite this email.")

        # Separator
        tk.Frame(inner, bg=GRAY_200, height=1).pack(fill="x", pady=(0, 16))

        # Body editor (dominant, minimal border, increased height)
        txt_body = tk.Text(
            inner,
            bg=BG_ENTRY,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            font=FONT_BASE,
            wrap="word",
            height=20,  # Increased from 12
            highlightthickness=1,
            highlightbackground=GRAY_200,  # Lighter border
            highlightcolor=ACCENT,
            undo=True,
            maxundo=-1,
        )

        # Configure formatting tags and add toolbar BEFORE packing the body
        configure_format_tags(txt_body)
        build_format_toolbar(inner, txt_body, self)

        txt_body.pack(fill="both", expand=True)

        # ── Signature preview (read-only) below the editor ──
        sig_sep = tk.Frame(inner, bg=BORDER, height=1)
        sig_sep.pack(fill="x", pady=(4, 0))

        sig_preview = tk.Text(
            inner,
            bg=BG_CARD,
            fg=FG_MUTED,
            relief="flat",
            font=FONT_BASE,
            wrap="word",
            height=5,
            highlightthickness=0,
            cursor="arrow",
            state="disabled",
        )
        sig_preview.pack(fill="x")

        # Tooltip: tell users to use Add/Edit Signature
        _sig_tip = None

        def _sig_enter(e):
            nonlocal _sig_tip
            _sig_tip = tk.Toplevel(sig_preview)
            _sig_tip.overrideredirect(True)
            _sig_tip.configure(bg="#FFFFFF")
            _sig_tip.attributes("-topmost", True)
            lbl = tk.Label(
                _sig_tip,
                text='Use "Add/Edit Signature" to customize',
                bg="#FFFFFF", fg=ACCENT,
                font=("Segoe UI", 8), padx=6, pady=3,
                relief="solid", bd=1,
            )
            lbl.pack()
            _sig_tip.update_idletasks()
            x = sig_preview.winfo_rootx() + sig_preview.winfo_width() // 2
            y = sig_preview.winfo_rooty() - 30
            _sig_tip.geometry(f"+{x}+{y}")

        def _sig_leave(e):
            nonlocal _sig_tip
            if _sig_tip:
                _sig_tip.destroy()
                _sig_tip = None

        sig_preview.bind("<Enter>", _sig_enter, add="+")
        sig_preview.bind("<Leave>", _sig_leave, add="+")

        # Populate preview with current signature
        sig_text = self._sig_for_display().strip()
        if sig_text:
            sig_preview.configure(state="normal")
            sig_preview.insert("1.0", sig_text)
            sig_preview.configure(state="disabled")

        if not hasattr(self, "sig_preview_widgets"):
            self.sig_preview_widgets = []
        self.sig_preview_widgets.append(sig_preview)

        # Strip signature from loaded body so it only lives in the preview
        if body_text:
            body_text = self._strip_signature_from_body(body_text)
            if is_html(body_text):
                html_to_text_widget(txt_body, body_text)
            else:
                txt_body.insert("1.0", body_text)

        # Clear undo history so Ctrl+Z doesn't undo the initial load
        txt_body.edit_reset()
        txt_body.edit_modified(False)

        # Track last focused editor (body)
        txt_body.bind("<FocusIn>", lambda _e, w=txt_body: setattr(self, "_last_editor_widget", w))

        # Store body reference for variable insertion
        txt_body_ref[0] = txt_body

        return txt_body

    def _show_variable_popup(self, subject_widget, body_widget):
        """Show a small popup menu with variable options"""
        # Create popup window
        popup = tk.Toplevel(self)
        popup.title("Insert Variable")
        popup.overrideredirect(True)
        popup.configure(bg=BG_CARD)
        popup.attributes("-topmost", True)

        # Content frame
        content = tk.Frame(popup, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        content.pack(fill="both", expand=True, padx=0, pady=0)

        # Position near the subject field
        x = subject_widget.winfo_rootx()
        y = subject_widget.winfo_rooty() + subject_widget.winfo_height() + 4
        popup.geometry(f"+{x}+{y}")

        # Title
        tk.Label(
            content,
            text="Insert variable",
            bg=BG_CARD,
            fg=FG_TEXT,
            font=FONT_BUTTON,
        ).pack(anchor="w", padx=12, pady=(10, 8))

        # Variable buttons
        variables = [
            ("{FirstName}", "Contact's first name"),
            ("{LastName}", "Contact's last name"),
            ("{Company}", "Contact's company"),
            ("{JobTitle}", "Contact's job title"),
            ("{Email}", "Contact's email"),
        ]

        for var, desc in variables:
            btn_frame = tk.Frame(content, bg=BG_CARD)
            btn_frame.pack(fill="x", padx=8, pady=2)

            btn = tk.Button(
                btn_frame,
                text=var,
                command=lambda v=var: self._insert_variable_and_close(v, popup),
                bg=BG_CARD,
                fg=FG_TEXT,
                activebackground=BG_HOVER,
                activeforeground=FG_TEXT,
                relief="flat",
                font=FONT_SMALL,
                padx=10,
                pady=6,
                cursor="hand2",
                anchor="w",
            )
            btn.pack(side="left", fill="x", expand=True)

            tk.Label(
                btn_frame,
                text=desc,
                bg=BG_CARD,
                fg=FG_MUTED,
                font=FONT_CAPTION,
            ).pack(side="left", padx=(8, 8))

        # Add padding at bottom
        tk.Frame(content, bg=BG_CARD, height=8).pack()

        # Close popup when clicking outside
        def close_popup(_e=None):
            popup.destroy()

        # Bind escape key to close
        popup.bind("<Escape>", close_popup)
        popup.bind("<FocusOut>", close_popup)

        popup.focus_set()

    def _insert_variable_and_close(self, var: str, popup):
        """Insert variable and close the popup"""
        self._insert_variable(var)
        popup.destroy()

    def _insert_variable(self, var: str):
        """
        Insert variable into the last-focused editor widget (Subject entry or Body text).
        Using focus_get() alone fails because clicking the variable popup steals focus.
        """
        widget = getattr(self, "_last_editor_widget", None) or self.focus_get()

        try:
            if isinstance(widget, tk.Entry):
                widget.insert(tk.INSERT, var)
                widget.focus_set()
            elif isinstance(widget, tk.Text):
                widget.insert("insert", var)
                widget.focus_set()
        except tk.TclError:
            pass

        # Keep clipboard behavior (optional)
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
            font=FONT_SECTION,
        ).pack(anchor="w")

        tk.Label(
            header,
            text=f"Local timezone: {self.tz_label}",
            bg=BG_ENTRY,
            fg=FG_MUTED,
            font=FONT_CAPTION,
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

        # Mousewheel scrolling (Windows)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Store reference for updates
        self.schedule_panel_canvas = canvas
        self.schedule_list_items = []  # List of item frames for highlighting
        self.schedule_rows = {}  # Dict mapping email_index → {frame, widgets, vars} for incremental updates

        # Initial population removed - schedule rows now created incrementally by _add_email() -> _schedule_add_row()
        # No placeholder rows should be created here

    def _rebuild_schedule_panel(self):
        """Rebuild the schedule panel list to match current emails"""
        if not hasattr(self, "schedule_list_frame"):
            return

        # ANTI-FLICKER: Skip rebuild during batch operations
        if getattr(self, "_suspend_rebuilds", False):
            return

        # ANTI-FLICKER: Only rebuild if email count changed
        current_count = len(self.name_vars) if hasattr(self, "name_vars") else 0
        existing_count = len(self.schedule_list_items) if hasattr(self, "schedule_list_items") else 0

        # If counts match, just update highlighting instead of rebuilding
        if current_count == existing_count and existing_count > 0:
            self._update_schedule_panel_highlighting(-1)
            return

        # Clear existing items only when count changed
        for child in self.schedule_list_frame.winfo_children():
            child.destroy()

        self.schedule_list_items = []
        self.schedule_rows = {}  # Clear row tracking dict

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
                    font=FONT_BUTTON,
                    anchor="w",
                    cursor="hand2"
                )
            else:
                name_label = tk.Label(
                    content,
                    text=f"Email {i+1}",
                    bg=content["bg"],
                    fg=FG_TEXT,
                    font=FONT_BUTTON,
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
                font=FONT_CAPTION,
            ).pack(side="left", padx=(0, 4))

            date_entry = None
            if i < len(self.date_vars):
                date_entry = self._dateentry_widget(date_frame, self.date_vars[i])
                date_entry.configure(font=FONT_CAPTION, width=12)
                date_entry.pack(side="left", fill="x", expand=True)

            # Time field (editable)
            time_frame = tk.Frame(content, bg=content["bg"])
            time_frame.pack(fill="x", pady=(2, 0))

            tk.Label(
                time_frame,
                text="Time:",
                bg=content["bg"],
                fg=FG_MUTED,
                font=FONT_CAPTION,
            ).pack(side="left", padx=(0, 4))

            time_combo = None
            if i < len(self.time_vars):
                time_combo = ttk.Combobox(
                    time_frame,
                    textvariable=self.time_vars[i],
                    values=TIME_OPTIONS,
                    width=8,
                    state="readonly",
                    style="Dark.TCombobox",
                    font=FONT_CAPTION
                )
                time_combo.pack(side="left", fill="x", expand=True)

            # Store row data for incremental updates
            self.schedule_rows[i] = {
                "frame": item_frame,
                "content": content,
                "name_label": name_label,
                "date_entry": date_entry,
                "time_combo": time_combo
            }

            # Attachment count
            if i < len(self.per_email_attachments):
                attach_count = len(self.per_email_attachments[i])
                if attach_count > 0:
                    attach_label = tk.Label(
                        content,
                        text=f"📎 {attach_count} attachment{'s' if attach_count != 1 else ''}",
                        bg=content["bg"],
                        fg=FG_MUTED,
                        font=FONT_CAPTION,
                        anchor="w",
                        cursor="hand2"
                    )
                    attach_label.pack(fill="x", pady=(2, 0))
                    attach_label.bind("<Button-1>", lambda _e, idx=i: self._schedule_item_clicked(idx))

    def _schedule_add_row(self, email_index: int):
        """Add a single schedule row for a new email (incremental, no rebuild)"""
        if not hasattr(self, "schedule_list_frame") or not hasattr(self, "schedule_rows"):
            return

        # Skip during batch operations - full rebuild will happen at end
        if getattr(self, "_suspend_rebuilds", False):
            return

        # Get current tab for highlighting
        current_tab = -1
        if hasattr(self, "email_notebook"):
            try:
                current_tab = self.email_notebook.index(self.email_notebook.select())
            except:
                pass

        is_selected = (email_index == current_tab)

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
        item_frame.bind("<Button-1>", lambda _e, idx=email_index: self._schedule_item_clicked(idx))

        # Content padding
        content = tk.Frame(item_frame, bg=item_frame["bg"])
        content.pack(fill="x", padx=8, pady=6)

        # Email name (bold) - uses textvariable for automatic updates
        if email_index < len(self.name_vars):
            name_label = tk.Label(
                content,
                textvariable=self.name_vars[email_index],
                bg=content["bg"],
                fg=FG_TEXT,
                font=FONT_BUTTON,
                anchor="w",
                cursor="hand2"
            )
        else:
            name_label = tk.Label(
                content,
                text=f"Email {email_index+1}",
                bg=content["bg"],
                fg=FG_TEXT,
                font=FONT_BUTTON,
                anchor="w",
                cursor="hand2"
            )
        name_label.pack(fill="x")
        name_label.bind("<Button-1>", lambda _e, idx=email_index: self._schedule_item_clicked(idx))

        # Date field (editable)
        date_frame = tk.Frame(content, bg=content["bg"])
        date_frame.pack(fill="x", pady=(4, 0))

        tk.Label(
            date_frame,
            text="Date:",
            bg=content["bg"],
            fg=FG_MUTED,
            font=FONT_CAPTION,
        ).pack(side="left", padx=(0, 4))

        date_entry = None
        if email_index < len(self.date_vars):
            date_entry = self._dateentry_widget(date_frame, self.date_vars[email_index])
            date_entry.configure(font=FONT_CAPTION, width=12)
            date_entry.pack(side="left", fill="x", expand=True)

        # Time field (editable)
        time_frame = tk.Frame(content, bg=content["bg"])
        time_frame.pack(fill="x", pady=(2, 0))

        tk.Label(
            time_frame,
            text="Time:",
            bg=content["bg"],
            fg=FG_MUTED,
            font=FONT_CAPTION,
        ).pack(side="left", padx=(0, 4))

        time_combo = None
        if email_index < len(self.time_vars):
            time_combo = ttk.Combobox(
                time_frame,
                textvariable=self.time_vars[email_index],
                values=TIME_OPTIONS,
                width=8,
                state="readonly",
                style="Dark.TCombobox",
                font=FONT_CAPTION
            )
            time_combo.pack(side="left", fill="x", expand=True)

        # Store row data for future updates
        self.schedule_rows[email_index] = {
            "frame": item_frame,
            "content": content,
            "name_label": name_label,
            "date_entry": date_entry,
            "time_combo": time_combo
        }

        # Update scroll region after adding
        if hasattr(self, "schedule_panel_canvas"):
            self.after_idle(lambda: self.schedule_panel_canvas.configure(scrollregion=self.schedule_panel_canvas.bbox("all")))

    def _schedule_remove_row(self, email_index: int):
        """Remove a single schedule row (incremental, no rebuild)"""
        if not hasattr(self, "schedule_rows") or email_index not in self.schedule_rows:
            return

        # Skip during batch operations - full rebuild will happen at end
        if getattr(self, "_suspend_rebuilds", False):
            return

        # Get row data
        row_data = self.schedule_rows[email_index]
        frame = row_data["frame"]

        # Remove from visual list
        if hasattr(self, "schedule_list_items") and frame in self.schedule_list_items:
            self.schedule_list_items.remove(frame)

        # Destroy the frame (and all its children)
        frame.destroy()

        # Remove from dict
        del self.schedule_rows[email_index]

        # Re-index remaining rows (shift down indices after deleted row)
        new_schedule_rows = {}
        for idx, row in self.schedule_rows.items():
            if idx > email_index:
                new_schedule_rows[idx - 1] = row
            else:
                new_schedule_rows[idx] = row
        self.schedule_rows = new_schedule_rows

        # Update scroll region after removing
        if hasattr(self, "schedule_panel_canvas"):
            self.after_idle(lambda: self.schedule_panel_canvas.configure(scrollregion=self.schedule_panel_canvas.bbox("all")))

    def _schedule_update_row(self, email_index: int):
        """Update a schedule row's values (no widget recreation)"""
        if not hasattr(self, "schedule_rows") or email_index not in self.schedule_rows:
            return

        # Row data already uses textvariable bindings, so values update automatically
        # This method is here for completeness if we need manual updates in the future
        pass

    def _sync_schedule_rows_to_emails(self):
        """
        Safety cleanup: Remove any orphaned schedule rows that don't have corresponding emails.
        Ensures schedule_rows dict exactly matches the current email list.
        """
        if not hasattr(self, "schedule_rows") or not hasattr(self, "name_vars"):
            return

        # Get canonical set of valid email indices
        valid_indices = set(range(len(self.name_vars)))

        # Remove any schedule rows not in current emails
        orphaned_keys = [key for key in self.schedule_rows.keys() if key not in valid_indices]

        for key in orphaned_keys:
            try:
                # Destroy the frame widget
                if "frame" in self.schedule_rows[key]:
                    self.schedule_rows[key]["frame"].destroy()

                # Remove from tracking dict
                del self.schedule_rows[key]
            except Exception as e:
                print(f"Warning: Failed to remove orphaned schedule row {key}: {e}")

        # Update scroll region if we removed anything
        if orphaned_keys and hasattr(self, "schedule_panel_canvas"):
            self.after_idle(lambda: self.schedule_panel_canvas.configure(scrollregion=self.schedule_panel_canvas.bbox("all")))

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


    def _set_seq_mode(self, mode: str):
        """Switch between 'days' and 'dates' scheduling mode."""
        self._seq_mode_var.set(mode)

        # Update button styles
        if mode == "days":
            self._seq_mode_days_btn.config(bg="#7C3AED", fg="#FFFFFF")
            self._seq_mode_dates_btn.config(bg=BORDER_SOFT, fg=FG_TEXT)
        else:
            self._seq_mode_days_btn.config(bg=BORDER_SOFT, fg=FG_TEXT)
            self._seq_mode_dates_btn.config(bg="#7C3AED", fg="#FFFFFF")

        # Show schedule cards (hidden until first mode selection)
        if hasattr(self, "_schedule_card_widget"):
            self._schedule_card_widget.grid()
        if hasattr(self, "_preset_card_widget"):
            self._preset_card_widget.grid()

        # Force rebuild the sequence table immediately (no debounce for user clicks)
        self._seq_table_last_key = None  # Reset to force rebuild
        self._do_rebuild_sequence_table()

    def _build_schedule_card(self, parent, row=0):
        # Content card (schedule table)
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        self._schedule_card_widget = card

        box = tk.Frame(card, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
        box.pack(fill="x", padx=12, pady=12)

        # ── Side-by-side layout: inputs (left) + schedule preview (right) ──
        split = tk.Frame(box, bg=BG_CARD)
        split.pack(fill="x", padx=10, pady=(6, 10))
        split.columnconfigure(0, weight=0)  # Input table
        split.columnconfigure(1, weight=1)  # Schedule preview

        # ── Left: Email Schedule Table ──
        left = tk.Frame(split, bg=BG_ENTRY)
        left.grid(row=0, column=0, sticky="nw")

        self.sequence_table = tk.Frame(left, bg=BG_ENTRY)
        self.sequence_table.pack(fill="x")

        # Columns: Email | Days/Date | Send time | Attachments
        self.sequence_table.columnconfigure(0, weight=0, minsize=160)
        self.sequence_table.columnconfigure(1, weight=0, minsize=140)
        self.sequence_table.columnconfigure(2, weight=0, minsize=120)
        self.sequence_table.columnconfigure(3, weight=0, minsize=170)

        # ── Right: Schedule Preview (populated when Update is clicked) ──
        self._schedule_summary_frame = tk.Frame(split, bg=BG_CARD)
        self._schedule_summary_frame.grid(row=0, column=1, sticky="new", padx=(20, 0))

        # Create placeholder for delay spinboxes (hidden but needed for compatibility)
        self.autobuild_delay_spinboxes_frame = tk.Frame(box, bg=BG_ENTRY)
        # Don't pack it - keeps the frame available but invisible

        self._rebuild_sequence_table()

        # (Saved Sequences card is built separately below)

    def _build_preset_sequences_card(self, parent, row=1):
        """Preset Sequences card — built-in presets with Customize option."""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        self._preset_card_widget = card

        box = tk.Frame(card, bg=BG_CARD, highlightbackground=BORDER_MEDIUM,
                       highlightthickness=1, relief="flat")
        box.pack(fill="x", padx=12, pady=12)

        # Title
        tk.Label(box, text="Preset Sequences", bg=BG_CARD, fg=ACCENT,
                 font=FONT_SECTION).pack(anchor="w", padx=10, pady=(8, 4))

        tk.Label(box, text="Pick one and hit Apply, or Customize and save your own for future use",
                 bg=BG_CARD, fg=FG_MUTED, font=FONT_CAPTION
                 ).pack(anchor="w", padx=10, pady=(0, 6))

        # Dropdown + Apply + Customize
        builtin_row = tk.Frame(box, bg=BG_CARD)
        builtin_row.pack(fill="x", padx=10, pady=(0, 10))

        self._preset_seq_var = tk.StringVar(value="7 emails")
        ttk.Combobox(
            builtin_row, textvariable=self._preset_seq_var,
            values=[f"{n} emails" for n in range(3, 11)],
            width=12, state="readonly", style="Dark.TCombobox",
        ).pack(side="left", padx=(0, 8))

        apply_seq_btn = tk.Button(
            builtin_row, text="Apply",
            command=self._apply_default_sequence,
            bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_HOVER,
            activeforeground=FG_WHITE, relief="flat", font=FONT_SMALL,
            padx=12, pady=4, cursor="hand2",
        )
        apply_seq_btn.pack(side="left", padx=(0, 4))
        apply_seq_btn.bind("<Enter>", lambda e: apply_seq_btn.config(bg=ACCENT_HOVER))
        apply_seq_btn.bind("<Leave>", lambda e: apply_seq_btn.config(bg=ACCENT))

        cust_btn = tk.Button(
            builtin_row, text="Customize",
            command=self._open_customize_preset,
            bg=BORDER_SOFT, fg=FG_TEXT, activebackground=BG_HOVER,
            activeforeground=ACCENT, relief="flat", font=FONT_SMALL,
            padx=12, pady=4, cursor="hand2",
        )
        cust_btn.pack(side="left")
        cust_btn.bind("<Enter>", lambda e: cust_btn.config(bg="#FFFFFF", fg=ACCENT))
        cust_btn.bind("<Leave>", lambda e: cust_btn.config(bg=BORDER_SOFT, fg=FG_TEXT))


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
        # Update attachment filename label
        if index < len(self.per_email_attach_labels):
            if n:
                names = [os.path.basename(p) for p in self.per_email_attachments[index]]
                self.per_email_attach_labels[index].configure(text=", ".join(names))
            else:
                self.per_email_attach_labels[index].configure(text="")

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

        # ANTI-FLICKER: Skip rebuild during batch operations
        if getattr(self, "_suspend_rebuilds", False):
            return

        # Auto-select "days" mode if emails exist but no mode chosen yet
        n = len(self.date_vars)
        current_mode = self._seq_mode_var.get()
        if n > 0 and not current_mode:
            self._set_seq_mode("days")
            return  # _set_seq_mode triggers its own rebuild

        # ANTI-FLICKER: Only rebuild when email count or mode changes
        cache_key = (n, current_mode)
        if cache_key == getattr(self, "_seq_table_last_key", None):
            return
        self._seq_table_last_key = cache_key
        self._seq_table_last_n = n

        self._rebuilding_sequence_table = True
        self._rebuild_pending_after_id = None

        # Ensure delay_vars matches email count
        while len(self.delay_vars) < len(self.date_vars):
            self.delay_vars.append(tk.StringVar(value="2"))
        while len(self.delay_vars) > len(self.date_vars):
            self.delay_vars.pop()

        try:
            # Hide table during rebuild to prevent visual flutter
            self.sequence_table.pack_forget()

            for child in self.sequence_table.winfo_children():
                child.destroy()

            hdr_font = ("Segoe UI Semibold", 9)
            seq_mode = self._seq_mode_var.get()

            # Reconfigure columns based on mode
            # Columns: 0=Email, 1=Days/Date, 2=Send time, 3=Attachments, 4=Spacer
            self.sequence_table.columnconfigure(0, weight=0, minsize=160)  # Email
            self.sequence_table.columnconfigure(1, weight=0, minsize=140)  # Days after OR Send date
            self.sequence_table.columnconfigure(2, weight=0, minsize=120)  # Send time
            self.sequence_table.columnconfigure(3, weight=0, minsize=170)  # Attachments
            self.sequence_table.columnconfigure(4, weight=1)               # Spacer

            # Headers
            tk.Label(self.sequence_table, text="Step", bg=BG_ENTRY, fg=FG_MUTED, font=hdr_font) \
                .grid(row=0, column=0, sticky="w", pady=(0, 6))

            if seq_mode == "days":
                tk.Label(self.sequence_table, text="Wait (business days)", bg=BG_ENTRY, fg=FG_MUTED, font=hdr_font) \
                    .grid(row=0, column=1, sticky="w", padx=(6, 0), pady=(0, 6))
            else:
                tk.Label(self.sequence_table, text="Send Date", bg=BG_ENTRY, fg=FG_MUTED, font=hdr_font) \
                    .grid(row=0, column=1, sticky="w", padx=(6, 0), pady=(0, 6))

            tk.Label(self.sequence_table, text="Send Time", bg=BG_ENTRY, fg=FG_MUTED, font=hdr_font) \
                .grid(row=0, column=2, sticky="w", padx=(6, 0), pady=(0, 6))
            attach_hdr = tk.Label(self.sequence_table, text="Attachments (optional)", bg=BG_ENTRY, fg=FG_MUTED, font=hdr_font)
            attach_hdr.grid(row=0, column=3, sticky="w", padx=(6, 0), pady=(0, 6))

            self.per_email_manage_btns = []
            self.per_email_attach_labels = []

            for i in range(n):
                r = i + 1
                name_var = self.name_vars[i] if i < len(self.name_vars) else tk.StringVar(value=f"Email {i+1}")

                # Email name (clickable — opens email preview popup)
                lbl_name = tk.Label(self.sequence_table, textvariable=name_var, bg=BG_ENTRY, fg=ACCENT,
                                    anchor="w", font=("Segoe UI", 10, "underline"), cursor="hand2")
                lbl_name.grid(row=r, column=0, sticky="w", pady=4)
                lbl_name.bind("<Button-1>", lambda e, idx=i: self._show_email_popup(idx))
                lbl_name.bind("<Enter>", lambda e, l=lbl_name: l.config(fg=ACCENT_HOVER))
                lbl_name.bind("<Leave>", lambda e, l=lbl_name: l.config(fg=ACCENT))
                ToolTip(lbl_name, "Click to preview this email.")

                # Column 1: Days after OR Send date (depending on mode)
                if seq_mode == "days":
                    if i == 0:
                        self.delay_vars[i].set("0")
                        tk.Label(self.sequence_table, text="—", bg=BG_ENTRY, fg=FG_MUTED,
                                 font=FONT_BASE).grid(row=r, column=1, sticky="w", padx=(6, 0), pady=4)
                    else:
                        delay_spin = tk.Spinbox(
                            self.sequence_table, from_=1, to=90, textvariable=self.delay_vars[i],
                            width=4, bg=BG_CARD, fg=FG_TEXT, font=FONT_BASE,
                            buttonbackground=GRAY_200, relief="flat",
                            highlightthickness=1, highlightbackground=BORDER_MEDIUM,
                            highlightcolor=ACCENT,
                        )
                        delay_spin.grid(row=r, column=1, sticky="w", padx=(6, 0), pady=4)
                else:
                    date_widget = self._dateentry_widget(self.sequence_table, self.date_vars[i])
                    date_widget.grid(row=r, column=1, sticky="w", padx=(6, 0), pady=4)

                # Send time
                time_combo = ttk.Combobox(
                    self.sequence_table, textvariable=self.time_vars[i],
                    values=TIME_OPTIONS, width=10, state="readonly", style="Dark.TCombobox",
                )
                if not self.time_vars[i].get():
                    self.time_vars[i].set("9:00 AM")
                time_combo.grid(row=r, column=2, sticky="w", padx=(6, 0), pady=4)

                # Attachments
                attach_cell = tk.Frame(self.sequence_table, bg=BG_ENTRY)
                attach_cell.grid(row=r, column=3, sticky="w", padx=(6, 0), pady=4)

                btn_manage = tk.Button(
                    attach_cell, text="Add / Delete",
                    command=lambda idx=i: self._open_attachment_manager(idx),
                    bg=BORDER_SOFT, fg=FG_TEXT, activebackground=BG_HOVER,
                    activeforeground=ACCENT, relief="flat", font=FONT_SMALL,
                    padx=10, pady=5, cursor="hand2",
                )
                btn_manage.pack(side="left")
                btn_manage.bind("<Enter>", lambda e, b=btn_manage: b.config(bg="#FFFFFF", fg=ACCENT))
                btn_manage.bind("<Leave>", lambda e, b=btn_manage: b.config(bg=BORDER_SOFT, fg=FG_TEXT))
                ToolTip(btn_manage, "Add or delete attachments for this email.")
                self.per_email_manage_btns.append(btn_manage)

                if i == 0:
                    tk.Label(attach_cell, text="Avoid attachments on first cold outreach",
                             bg=BG_ENTRY, fg=DANGER, font=FONT_CAPTION, anchor="w").pack(side="left", padx=(8, 0))

                attach_lbl = tk.Label(attach_cell, text="", bg=BG_ENTRY, fg=FG_MUTED, font=FONT_CAPTION, anchor="w")
                attach_lbl.pack(side="left", padx=(8, 0))
                self.per_email_attach_labels.append(attach_lbl)

                self._sync_manage_button(i)

            # ── Apply Schedule button + business days note (both modes) ──
            if n > 0:
                btn_row = tk.Frame(self.sequence_table, bg=BG_ENTRY)
                btn_row.grid(row=n + 1, column=0, columnspan=4, sticky="w", pady=(8, 4))

                ud_btn = tk.Button(
                    btn_row, text="Apply Schedule",
                    command=self._update_schedule,
                    bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_HOVER,
                    activeforeground=FG_WHITE, relief="flat", font=FONT_SMALL,
                    padx=14, pady=5, cursor="hand2",
                )
                ud_btn.pack(side="left")
                ud_btn.bind("<Enter>", lambda e: ud_btn.config(bg=ACCENT_HOVER))
                ud_btn.bind("<Leave>", lambda e: ud_btn.config(bg=ACCENT))

                if seq_mode == "days":
                    tk.Label(btn_row, text="Business days = Mon\u2013Fri. Weekends are skipped.",
                             bg=BG_ENTRY, fg=FG_MUTED, font=FONT_CAPTION).pack(side="left", padx=(12, 0))

        finally:
            # Show table again after rebuild is complete
            self.sequence_table.pack(fill="x")
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
        # Page header (shared style - white box with border)
        header = self.build_page_header(
            parent,
            "Choose contact list",
            "Import and manage contact lists for your campaigns."
        )
        header.grid(row=row, column=0, sticky="ew", padx=18, pady=(12, 14))

        # Content card (contacts table)
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=row+1, column=0, sticky="nsew", pady=(0, 8))
        card.rowconfigure(1, weight=1)  # Make table expand
        card.columnconfigure(0, weight=1)

        box = tk.Frame(card, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.rowconfigure(1, weight=1)  # Table row expands (was row 2, now row 1)
        box.columnconfigure(0, weight=1)

        # Buttons row
        row_btns = tk.Frame(box, bg=BG_CARD)
        row_btns.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 10))

        tk.Button(
            row_btns,
            text="Import Contacts",
            command=self._import_contacts_and_refresh,
            bg=DARK_AQUA,
            fg=FG_WHITE,
            activebackground=DARK_AQUA_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_BUTTON,
            padx=14,
            pady=8,
            cursor="hand2",
        ).pack(side="left")

        tk.Button(
            row_btns,
            text="Add Contact",
            command=self._add_new_contact,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_WHITE,
            relief="flat",
            font=FONT_SMALL,
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            row_btns,
            text="Delete Selected",
            command=self._delete_selected_contact,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            font=FONT_SMALL,
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

            # Update config to reflect active contacts
            config = load_config()
            config["active_contacts_file"] = OFFICIAL_CONTACTS_PATH
            config["active_contact_list_path"] = src
            save_config(config)

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
        name = themed_askstring(self, "Name contact list", "Name this contact list (e.g. 'RLW – UT Supers Q1'):", default_name)
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
            self._update_nurture_btn_state(0)
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

            # Update Stay Connected button state
            self._update_nurture_btn_state(len(rows))
        except Exception as e:
            self._update_nurture_btn_state(0)  # Disable on error

    def _update_nurture_btn_state(self, contact_count: int = None):
        """Enable/disable Add to Nurture List button based on contact count."""
        if not hasattr(self, 'btn_add_nurture_on_complete'):
            return

        if contact_count is None:
            contact_count = self._count_contacts()

        if contact_count > 0:
            self.btn_add_nurture_on_complete.configure(state="normal", cursor="hand2")
        else:
            self.btn_add_nurture_on_complete.configure(state="disabled", cursor="")

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
            font=FONT_BASE
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
            font=FONT_BTN_SM,
            padx=20,
            pady=6,
            cursor="hand2"
        ).pack(side="left", padx=5)
        
        tk.Button(
            btn_frame,
            text="Cancel",
            command=cancel,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            relief="flat",
            font=FONT_SMALL,
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
        add_win.geometry("640x560")
        add_win.minsize(640, 460)
        add_win.configure(bg=BG_ROOT)
        add_win.transient(self)
        add_win.grab_set()

        # --- Scroll container ---
        container = ttk.Frame(add_win)
        container.pack(fill="both", expand=True, padx=14, pady=14)

        canvas = tk.Canvas(container, highlightthickness=0, bg=BG_ROOT)
        vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)

        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(_):
            canvas.itemconfigure(win_id, width=canvas.winfo_width())

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mousewheel (Windows)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        add_win.bind("<Enter>", lambda e: add_win.bind_all("<MouseWheel>", _on_mousewheel))
        add_win.bind("<Leave>", lambda e: add_win.unbind_all("<MouseWheel>"))
        add_win.bind("<Destroy>", lambda e: add_win.unbind_all("<MouseWheel>"))

        # --- Card frame (FF styled) ---
        card = tk.Frame(inner, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        # Content padding inside card
        content = tk.Frame(card, bg=BG_CARD)
        content.pack(fill="both", expand=True, padx=22, pady=18)

        # Title
        tk.Label(content, text="Add New Contact", bg=BG_CARD, fg=FG_TEXT,
                 font=FONT_HEADING).pack(anchor="w", pady=(0, 14))

        # Helper for label + entry
        def field(label_text, required=False):
            lbl = tk.Label(content,
                           text=f"{label_text}{' *' if required else ''}",
                           bg=BG_CARD, fg=FG_MUTED, font=FONT_BODY_MEDIUM)
            lbl.pack(anchor="w", pady=(10, 4))

            var = tk.StringVar()
            ent = tk.Entry(content, textvariable=var, relief="solid", bd=1, highlightthickness=1,
                           highlightbackground=BORDER_MEDIUM, highlightcolor=ACCENT,
                           bg=BG_ENTRY, fg=FG_TEXT, insertbackground=FG_TEXT,
                           font=FONT_SECTION_TITLE)
            ent.pack(fill="x", ipady=7)
            return var, ent

        email_var, email_ent = field("Email", required=True)
        firstname_var, _ = field("First Name")
        lastname_var, _ = field("Last Name")
        company_var, _ = field("Company")
        jobtitle_var, _ = field("Job Title")

        # Focus email field
        email_ent.focus()

        def save():
            email = email_var.get().strip()
            if not email:
                messagebox.showwarning("Missing Email", "Email is required.")
                return

            # Add to tree
            self.contacts_tree.insert("", "end", values=(
                email,
                firstname_var.get().strip(),
                lastname_var.get().strip(),
                company_var.get().strip(),
                jobtitle_var.get().strip()
            ))

            # Save to file
            self._save_contacts_to_file()
            try:
                self._set_status("Contact added", GOOD)
            except:
                pass
            add_win.destroy()

        # --- Buttons row ---
        btn_row = tk.Frame(content, bg=BG_CARD)
        btn_row.pack(fill="x", pady=(18, 0))

        cancel_btn = tk.Button(btn_row, text="Cancel",
                               font=FONT_BODY_MEDIUM,
                               bg=PRIMARY_50, fg=FG_TEXT, bd=0, padx=18, pady=10,
                               activebackground=BG_HOVER, cursor="hand2",
                               command=add_win.destroy)
        cancel_btn.pack(side="right", padx=(10, 0))

        add_btn = tk.Button(btn_row, text="Add Contact",
                            font=FONT_BODY_MEDIUM,
                            bg=DARK_AQUA, fg=FG_WHITE, bd=0, padx=18, pady=10,
                            activebackground=DARK_AQUA_HOVER, cursor="hand2",
                            command=save)
        add_btn.pack(side="right")

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

        # ── 1) STAY CONNECTED (nurture assignment) ──
        if include_create:
            nurture_box = tk.Frame(frame, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
            nurture_box.pack(fill="x")

            tk.Label(
                nurture_box,
                text="Stay Connected",
                bg=BG_ENTRY,
                fg=ACCENT,
                font=FONT_SECTION,
            ).pack(anchor="w", padx=12, pady=(10, 4))

            nurture_row = tk.Frame(nurture_box, bg=BG_ENTRY)
            nurture_row.pack(fill="x", padx=12, pady=(0, 10))

            self._nurture_enabled_var = tk.BooleanVar(value=False)
            self._nurture_checkbox = tk.Checkbutton(
                nurture_row,
                text="Contacts added to list after sequence:",
                variable=self._nurture_enabled_var,
                command=self._on_nurture_checkbox_changed,
                bg=BG_ENTRY,
                fg=FG_TEXT,
                activebackground=BG_ENTRY,
                activeforeground=FG_TEXT,
                selectcolor=BG_ENTRY,
                font=FONT_BASE,
                cursor="hand2",
            )
            self._nurture_checkbox.pack(side="left")

            self._nurture_dropdown_var = tk.StringVar()
            self._nurture_dropdown = ttk.Combobox(
                nurture_row,
                textvariable=self._nurture_dropdown_var,
                state="disabled",
                width=25,
                font=FONT_BASE,
                style="Dark.TCombobox",
            )
            self._nurture_dropdown.pack(side="left", padx=(8, 0))
            self._nurture_dropdown.bind("<<ComboboxSelected>>", self._on_nurture_dropdown_changed)

            self._nurture_new_btn = tk.Button(
                nurture_row,
                text="+ New",
                command=self._create_nurture_from_launch,
                bg=BG_ENTRY,
                fg=ACCENT,
                activebackground=BORDER_SOFT,
                activeforeground=ACCENT,
                relief="flat",
                font=FONT_SMALL,
                cursor="hand2",
                state="disabled",
            )
            self._nurture_new_btn.pack(side="left", padx=(8, 0))

            self._nurture_status_label = tk.Label(
                nurture_box,
                text="",
                bg=BG_ENTRY,
                fg=FG_MUTED,
                font=FONT_SMALL,
            )
            self._nurture_status_label.pack(anchor="w", padx=12, pady=(0, 10))

            self._refresh_nurture_dropdown()
            self._restore_nurture_selection()

        # ── 2) PREVIEW EMAILS — warm yellow ──
        _PREVIEW_BG = "#FFF9E6"
        _PREVIEW_HOVER = "#FFF3CC"
        _PREVIEW_FG = "#92700C"

        if include_preview:
            test_box = tk.Frame(frame, bg=_PREVIEW_BG, highlightbackground="#E8D48B",
                                highlightthickness=1, relief="flat")
            test_box.pack(fill="x", pady=(10, 0))

            self._preview_btn_imgtk = None
            try:
                emblem_path = resource_path("assets", "funnelforge.png")
                if os.path.isfile(emblem_path):
                    emblem_img = Image.open(emblem_path)
                    emblem_img = emblem_img.resize((28, 28), RESAMPLE_LANCZOS)
                    self._preview_btn_imgtk = ImageTk.PhotoImage(emblem_img)
            except Exception:
                pass

            btn_test = tk.Button(
                test_box,
                text="  PREVIEW EMAILS",
                image=self._preview_btn_imgtk if self._preview_btn_imgtk else "",
                compound="left",
                command=self._send_test_emails,
                bg=_PREVIEW_BG,
                fg=_PREVIEW_FG,
                activebackground=_PREVIEW_HOVER,
                activeforeground=_PREVIEW_FG,
                relief="flat",
                font=("Segoe UI", 11, "bold"),
                cursor="hand2",
                padx=16,
                pady=8,
                bd=0,
            )
            btn_test.pack(fill="x", padx=10, pady=10)

            def _on_preview_enter(e, _btn=btn_test):
                _btn.config(bg=_PREVIEW_HOVER)
            def _on_preview_leave(e, _btn=btn_test):
                _btn.config(bg=_PREVIEW_BG)
            btn_test.bind("<Enter>", _on_preview_enter)
            btn_test.bind("<Leave>", _on_preview_leave)

            ToolTip(btn_test, "Test and Preview emails by sending them to your inbox")

        # ── 3) RUN FUNNEL FORGE — warm green ──
        _RUN_BG = "#ECFDF0"         # very light warm green
        _RUN_HOVER = "#D1FAE0"      # slightly deeper on hover
        _RUN_FG = "#166534"          # deep green text

        if include_create:
            create_box = tk.Frame(frame, bg=_RUN_BG, highlightbackground="#86D9A0",
                                  highlightthickness=1, relief="flat")
            create_box.pack(fill="x", pady=(10, 0))

            # Load the FF emblem
            self._run_btn_imgtk = None
            try:
                emblem_path = resource_path("assets", "funnelforge.png")
                if os.path.isfile(emblem_path):
                    emblem_img = Image.open(emblem_path)
                    emblem_img = emblem_img.resize((28, 28), RESAMPLE_LANCZOS)
                    self._run_btn_imgtk = ImageTk.PhotoImage(emblem_img)
            except Exception:
                pass

            btn_run = tk.Button(
                create_box,
                text="  RUN FUNNEL FORGE",
                image=self._run_btn_imgtk if self._run_btn_imgtk else "",
                compound="left",
                command=self._run_sequence,
                bg=_RUN_BG,
                fg=_RUN_FG,
                activebackground=_RUN_HOVER,
                activeforeground=_RUN_FG,
                relief="flat",
                font=("Segoe UI", 11, "bold"),
                cursor="hand2",
                padx=16,
                pady=8,
                bd=0,
            )
            btn_run.pack(fill="x", padx=10, pady=10)
            ToolTip(btn_run, "Schedules/sends through Outlook Classic using your current configuration.")

            # Hover effects
            def _on_run_enter(e, _btn=btn_run):
                _btn.config(bg=_RUN_HOVER)
            def _on_run_leave(e, _btn=btn_run):
                _btn.config(bg=_RUN_BG)
            btn_run.bind("<Enter>", _on_run_enter)
            btn_run.bind("<Leave>", _on_run_leave)

            # Store reference to Launch button for enable/disable control
            self.execute_launch_btn = btn_run

        # CANCEL PENDING EMAILS
        if include_cancel:
            cancel_box = tk.Frame(frame, bg=BG_CARD, highlightbackground=BORDER_MEDIUM, highlightthickness=1, relief="flat")
            cancel_box.pack(fill="x", pady=(10, 0))

            tk.Label(
                cancel_box,
                text="Cancel a previous sequence",
                bg=BG_ENTRY,
                fg=ACCENT,
                font=FONT_SECTION,
                padx=10,
            ).pack(anchor="w", pady=(10, 4))

            tk.Label(
                cancel_box,
                text="Remove pending/scheduled emails from Outlook",
                bg=BG_ENTRY,
                fg=FG_MUTED,
                font=FONT_SMALL,
                padx=10,
            ).pack(anchor="w", pady=(0, 10))

            # Mode selector row
            mode_row = tk.Frame(cancel_box, bg=BG_ENTRY)
            mode_row.pack(fill="x", padx=10, pady=(0, 8))

            tk.Radiobutton(
                mode_row,
                text="Email",
                variable=self.cancel_mode_var,
                value="email",
                bg=BG_ENTRY,
                fg=FG_TEXT,
                selectcolor=BG_ENTRY,
                activebackground=BG_ENTRY,
                activeforeground=FG_TEXT,
                command=self._update_cancel_help,
            ).pack(side="left", padx=(0, 12))

            tk.Radiobutton(
                mode_row,
                text="Domain",
                variable=self.cancel_mode_var,
                value="domain",
                bg=BG_ENTRY,
                fg=FG_TEXT,
                selectcolor=BG_ENTRY,
                activebackground=BG_ENTRY,
                activeforeground=FG_TEXT,
                command=self._update_cancel_help,
            ).pack(side="left")

            # Dynamic helper text (changes based on Email/Domain selection)
            help_label = tk.Label(
                cancel_box,
                textvariable=self.cancel_help_var,
                bg=BG_ENTRY,
                fg=FG_MUTED,
                font=FONT_SMALL,
                justify="left",
                wraplength=720,
                padx=10,
            )
            help_label.pack(anchor="w", pady=(0, 10))

            # Input row
            cancel_row = tk.Frame(cancel_box, bg=BG_ENTRY)
            cancel_row.pack(fill="x", padx=10, pady=(0, 10))

            self.cancel_query_entry = tk.Entry(
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
            self.cancel_query_entry.pack(side="left", fill="x", expand=True)

            # Clear placeholder text on focus
            def _on_focus_in(e):
                if self.cancel_query_entry.get() in ["john.smith@company.com", "@company.com"]:
                    self.cancel_query_entry.delete(0, "end")
                    self.cancel_query_entry.config(fg=FG_TEXT)

            def _on_focus_out(e):
                if not self.cancel_query_entry.get():
                    self._update_cancel_help()

            self.cancel_query_entry.bind("<FocusIn>", _on_focus_in)
            self.cancel_query_entry.bind("<FocusOut>", _on_focus_out)

            btn_cancel = make_button(cancel_row, text="Cancel Pending Emails", command=self._cancel_pending_emails, variant="warning")
            btn_cancel.pack(side="left", padx=(10, 0))
            ToolTip(btn_cancel, "Finds matching pending emails in Outbox and moves them to Deleted Items.")

            # "What will happen" explainer box
            info_box = tk.Frame(cancel_box, bg=WARN_BG, highlightbackground=WARN, highlightthickness=1, relief="flat")
            info_box.pack(fill="x", padx=10, pady=(0, 10))

            tk.Label(
                info_box,
                text="⚠️  What happens when you cancel",
                bg=WARN_BG,
                fg=WARN_FG,
                font=FONT_BTN_SM,
            ).pack(anchor="w", padx=10, pady=(8, 4))

            tk.Label(
                info_box,
                text="•  Pending and scheduled emails are removed from Outlook\n"
                     "•  Already sent emails are NOT affected\n"
                     "•  This action cannot be undone",
                bg=WARN_BG,
                fg=WARN_FG,
                font=FONT_SMALL,
                justify="left",
            ).pack(anchor="w", padx=10, pady=(0, 8))

            # Initialize help text on first load
            self._update_cancel_help()

    # ============================================
    # Sequence management
    # ============================================
    # ============================================
    # Signature helpers
    # ============================================
    _DEFAULT_SIG_MARKER = "Your Name"  # used to detect un-customised signature

    def _load_signature_from_file(self) -> str:
        """Load signature from file, creating default if doesn't exist"""
        # Default signature template (ALWAYS starts with \n\n--\n delimiter)
        default_signature = (
            "\n\n--\n"
            "Your Name\n"
            "Your Title | Your Industry\n"
            "C: (555) 123-4567\n"
            "you@yourcompany.com\n"
            "https://www.linkedin.com/in/yourprofile/"
        )

        try:
            if os.path.exists(SIGNATURE_PATH):
                with open(SIGNATURE_PATH, "r", encoding="utf-8") as f:
                    sig = f.read()
                    # Ensure signature starts with delimiter
                    if sig and not sig.startswith("\n\n--\n"):
                        sig = "\n\n--\n" + sig.lstrip()
                    return sig
        except Exception:
            pass

        # File doesn't exist - create it with default
        try:
            os.makedirs(os.path.dirname(SIGNATURE_PATH), exist_ok=True)
            with open(SIGNATURE_PATH, "w", encoding="utf-8") as f:
                f.write(default_signature)
        except Exception:
            pass

        return default_signature

    def _init_signature(self):
        """Load signature on app startup and apply to all existing email bodies"""
        # Load signature from file into cache
        self.signature_text = self._load_signature_from_file()

        # Populate any signature preview widgets that were created before
        # the signature was loaded (e.g. during _auto_load_default_campaign)
        self._refresh_signature_previews()

        # If the signature is still the default template, prompt user to set it up
        if self._is_default_signature():
            self.after(600, self._show_signature_setup)

    def _replace_signature_in_body(self, body: str) -> str:
        """Replace signature in body string using delimiter approach"""
        # Try the internal delimiter first (legacy bodies with --)
        delimiter = "\n\n--\n"
        if delimiter in body:
            body = body.split(delimiter)[0]
        else:
            # Body without -- : find existing signature by content match
            sig_content = self._sig_for_display().strip()
            if sig_content and sig_content in body:
                idx = body.find(sig_content)
                body = body[:idx]

        # Add current signature (from cache), stripping -- for display
        return body.rstrip() + self._sig_for_display()

    def _ensure_signature_in_body(self, body: str) -> str:
        """Ensure signature is in body string (for sending)"""
        sig_display = self._sig_for_display()
        sig_content = sig_display.strip()

        if is_html(body):
            # HTML body — check for signature in both plain and HTML forms
            sig_as_html = "<br>".join(line for line in sig_content.split("\n"))
            if sig_content and (sig_content in body or sig_as_html in body):
                return body  # Already has signature
            # Also check for the first line (name) as a last-resort match
            first_line = sig_content.split("\n")[0].strip()
            if first_line and len(first_line) > 3 and first_line in body:
                return body  # Signature already present
            sig_html = "<br><br>" + sig_as_html
            return body.rstrip() + sig_html

        # Plain text: check if signature already present (with or without --)
        if "\n\n--\n" in body or (sig_content and sig_content in body):
            return self._replace_signature_in_body(body)

        # No signature - add it
        return body.rstrip() + sig_display

    def _sig_for_display(self) -> str:
        """Return signature text without the -- marker for display/sending."""
        sig = self.signature_text
        if sig.startswith("\n\n--\n"):
            return "\n\n" + sig[5:]
        return sig

    def _ensure_signature_in_text_widget(self, txt_widget: tk.Text):
        """Ensure signature is present in a Text widget"""
        try:
            current_body = txt_widget.get("1.0", "end-1c")
            updated_body = self._ensure_signature_in_body(current_body)

            # Only update if changed
            if current_body != updated_body:
                txt_widget.delete("1.0", "end")
                txt_widget.insert("1.0", updated_body)
        except Exception:
            pass

    def _is_default_signature(self) -> bool:
        """Return True if the cached signature is still the un-customised template."""
        return self._DEFAULT_SIG_MARKER in self.signature_text

    def _show_signature_setup(self):
        """Show a first-run dialog so the user can set up their email signature."""
        popup = tk.Toplevel(self)
        popup.title("Set Up Your Signature")
        popup.geometry("520x420")
        popup.configure(bg=BG_ROOT)
        popup.transient(self)
        popup.grab_set()

        tk.Label(
            popup, text="Create Your Email Signature",
            bg=BG_ROOT, fg=ACCENT, font=FONT_SECTION,
        ).pack(anchor="w", padx=20, pady=(16, 4))

        tk.Label(
            popup,
            text="This will be added to the end of every email you send.\nEdit the example below with your own information.",
            bg=BG_ROOT, fg=FG_TEXT, font=FONT_BASE, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 10))

        # Example / editable area
        txt = tk.Text(
            popup, bg=BG_ENTRY, fg=FG_TEXT, insertbackground=FG_TEXT,
            relief="flat", font=FONT_BASE, wrap="word", height=8,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        txt.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        example = (
            "Michael Vaughn\n"
            "Search Consultant | Construction & Engineering\n"
            "C: 443-791-0026\n"
            "Michael.Vaughn@arenastaffing.net\n"
            "https://www.linkedin.com/in/mkvaughn/"
        )
        txt.insert("1.0", example)
        txt.focus_set()
        # Select all so user can immediately start typing their own
        txt.tag_add("sel", "1.0", "end-1c")

        def _save():
            sig_text = txt.get("1.0", "end-1c").strip()
            if not sig_text:
                messagebox.showwarning("Empty Signature", "Please enter your signature information.", parent=popup)
                return
            # Store with delimiter
            signature = "\n\n--\n" + sig_text
            try:
                os.makedirs(os.path.dirname(SIGNATURE_PATH), exist_ok=True)
                with open(SIGNATURE_PATH, "w", encoding="utf-8") as f:
                    f.write(signature)
            except Exception:
                pass
            self.signature_text = signature
            popup.destroy()

        btn_row = tk.Frame(popup, bg=BG_ROOT)
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        make_button(btn_row, text="Save Signature", command=_save, variant="primary").pack(side="right")

    def _strip_signature_from_body(self, body: str) -> str:
        """Remove any signature content from a body string, returning only the message."""
        if not body:
            return body

        # HTML body: strip signature by looking for the sig content
        if is_html(body):
            sig_content = self._sig_for_display().strip()
            if sig_content:
                sig_as_html = "<br>".join(line for line in sig_content.split("\n"))
                # Remove HTML version
                if sig_as_html in body:
                    idx = body.find(sig_as_html)
                    body = body[:idx].rstrip()
                    # Also strip leading <br> separators before signature
                    while body.endswith("<br>") or body.endswith("<br>\n"):
                        if body.endswith("<br>\n"):
                            body = body[:-5].rstrip()
                        elif body.endswith("<br>"):
                            body = body[:-4].rstrip()
                elif sig_content in body:
                    idx = body.find(sig_content)
                    body = body[:idx].rstrip()
            return body

        # Plain text: strip by delimiter or content match
        delimiter = "\n\n--\n"
        if delimiter in body:
            return body.split(delimiter)[0].rstrip()

        sig_content = self._sig_for_display().strip()
        if sig_content and sig_content in body:
            idx = body.find(sig_content)
            return body[:idx].rstrip()

        return body

    def _refresh_signature_previews(self):
        """Update all signature preview widgets with the current signature text."""
        sig_text = self._sig_for_display().strip()
        for preview in getattr(self, "sig_preview_widgets", []):
            try:
                preview.configure(state="normal")
                preview.delete("1.0", "end")
                if sig_text:
                    preview.insert("1.0", sig_text)
                preview.configure(state="disabled")
            except Exception:
                pass

    def _update_all_email_signatures(self, old_signature: str = ""):
        """Strip old signature from body editors when the user edits their signature.
        The new signature is added automatically at send time — not in the editor.
        """
        old_display = ""
        if old_signature:
            if old_signature.startswith("\n\n--\n"):
                old_display = "\n\n" + old_signature[5:]
            else:
                old_display = old_signature

        for txt_body in self.body_texts:
            try:
                current_body = txt_body.get("1.0", "end-1c")
                stripped = current_body
                delimiter = "\n\n--\n"
                if delimiter in stripped:
                    stripped = stripped.split(delimiter)[0]
                elif old_display.strip() and old_display.strip() in stripped:
                    idx = stripped.find(old_display.strip())
                    stripped = stripped[:idx]

                if stripped != current_body:
                    txt_body.delete("1.0", "end")
                    txt_body.insert("1.0", stripped.rstrip())
            except Exception:
                pass

        # Refresh all signature previews with the new signature
        self._refresh_signature_previews()

    def _open_signature_editor(self):
        """Open the signature editor window"""
        EditSignatureWindow(self)

    # ============================================
    # Relative scheduling helpers
    # ============================================
    def _parse_hhmm(self, text: str) -> tuple:
        """Parse HH:MM (24h) string to (hour, minute). Raises ValueError if invalid."""
        try:
            parts = text.strip().split(":")
            if len(parts) != 2:
                raise ValueError("Invalid time format")
            h = int(parts[0])
            m = int(parts[1])
            if h < 0 or h > 23 or m < 0 or m > 59:
                raise ValueError("Hour must be 0-23, minute 0-59")
            return (h, m)
        except Exception as e:
            raise ValueError(f"Invalid time format '{text}': {e}")

    def _format_time_ampm(self, h: int, m: int) -> str:
        """Convert 24h hour/minute to 'H:MM AM/PM' format."""
        period = "AM" if h < 12 else "PM"
        display_hour = h if h <= 12 else h - 12
        if display_hour == 0:
            display_hour = 12
        return f"{display_hour}:{m:02d} {period}"

    def _is_weekend(self, date_obj: date) -> bool:
        """Check if date is Saturday (5) or Sunday (6)."""
        return date_obj.weekday() in (5, 6)

    def _add_business_days(self, start_date: date, days: int, skip_weekends: bool) -> date:
        """Add business days to a date, optionally skipping weekends."""
        if days == 0:
            return start_date

        current = start_date
        added = 0

        while added < days:
            current = current + timedelta(days=1)
            if skip_weekends and self._is_weekend(current):
                continue  # Don't count weekends
            added += 1

        return current

    def _compute_delays_from_dates(self, date_strings: list) -> list:
        """Given a list of date strings (YYYY-MM-DD), compute business day gaps.

        Returns [0, gap1, gap2, ...] where gap_i is business days between
        email i-1 and email i.  Used to reconstruct the sequence pattern
        from campaigns that only stored computed dates.
        """
        delays = [0]  # First email is always 0
        for i in range(1, len(date_strings)):
            prev_str = (date_strings[i - 1] or "").strip()
            curr_str = (date_strings[i] or "").strip()
            if not prev_str or not curr_str:
                delays.append(2)  # default fallback
                continue
            try:
                prev_date = datetime.strptime(prev_str, "%Y-%m-%d").date()
                curr_date = datetime.strptime(curr_str, "%Y-%m-%d").date()
                bdays = 0
                d = prev_date
                while d < curr_date:
                    d = d + timedelta(days=1)
                    if d.weekday() not in (5, 6):
                        bdays += 1
                delays.append(max(bdays, 1))
            except Exception:
                delays.append(2)
        return delays

    def _recalculate_dates_from_delays(self, delay_pattern: list,
                                        send_time: str = "9:00 AM",
                                        skip_weekends: bool = True) -> list:
        """Compute fresh dates starting from the next business day after today.

        Given delay_pattern like [0, 2, 2, 1, 2, 1], returns a list of
        (date_str, time_str) tuples with weekends skipped.
        """
        start_date = datetime.now().date() + timedelta(days=1)
        if skip_weekends:
            while start_date.weekday() in (5, 6):
                start_date = start_date + timedelta(days=1)

        schedule = []
        current_date = start_date

        for i, delay in enumerate(delay_pattern):
            if i > 0:
                current_date = self._add_business_days(current_date, delay, skip_weekends)
            schedule.append((current_date.strftime("%Y-%m-%d"), send_time))

        return schedule

    @staticmethod
    def _format_delay_pattern(delays: list) -> str:
        """Return human-readable string like '2-2-1-2-1 business day gaps'."""
        if not delays or len(delays) < 2:
            return ""
        gaps = [str(d) for d in delays[1:]]  # skip the leading 0
        return "-".join(gaps) + " business day gaps"

    def _compute_relative_schedule(self) -> List[tuple]:
        """
        Compute relative schedule based on delay_vars and relative settings.
        Returns list of (date_str, time_str) tuples aligned with email count.
        """
        email_count = len(self.name_vars)
        if email_count == 0:
            return []

        # Parse settings
        try:
            window_start_h, window_start_m = self._parse_hhmm(self.relative_window_start_var.get())
        except ValueError:
            window_start_h, window_start_m = 8, 0  # Default fallback

        skip_weekends = self.relative_skip_weekends_var.get()

        # Determine start date
        start_date_str = self.relative_start_date_var.get().strip()
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            except:
                start_date = datetime.now().date()
        else:
            # Auto-set to next business day if empty
            start_date = datetime.now().date() + timedelta(days=1)
            if skip_weekends:
                while self._is_weekend(start_date):
                    start_date = start_date + timedelta(days=1)

        # Compute schedule for each email
        schedule = []
        current_date = start_date

        for i in range(email_count):
            # Email 1 uses start_date, Email i>1 adds delay
            if i > 0:
                try:
                    delay = int(self.delay_vars[i].get()) if i < len(self.delay_vars) else 0
                except:
                    delay = 0

                current_date = self._add_business_days(current_date, delay, skip_weekends)

            # Format date and time
            date_str = current_date.strftime("%Y-%m-%d")
            time_str = self._format_time_ampm(window_start_h, window_start_m)

            schedule.append((date_str, time_str))

        return schedule

    # -------------------------------------------------------------------------
    # Auto-Build Schedule helpers
    # -------------------------------------------------------------------------

    def _ensure_delay_vars_len(self):
        """Keep delay_vars aligned with email count. Email 1 is always 0."""
        email_count = len(self.subject_vars)
        current_len = len(self.delay_vars)

        if current_len < email_count:
            # Add missing delay vars (default to 2 business days)
            for i in range(current_len, email_count):
                if i == 0:
                    self.delay_vars.append(tk.StringVar(value="0"))  # Email 1 is always 0
                else:
                    self.delay_vars.append(tk.StringVar(value="2"))
        elif current_len > email_count:
            # Remove extra delay vars
            self.delay_vars = self.delay_vars[:email_count]

    def _parse_int_safe(self, text: str, default: int) -> int:
        """Parse int safely, return default if invalid."""
        try:
            return int(text.strip())
        except:
            return default

    def _next_business_day(self, from_date: date, skip_weekends: bool) -> date:
        """Advance to Monday if from_date is weekend (when skip_weekends=True)."""
        if skip_weekends:
            while self._is_weekend(from_date):
                from_date = from_date + timedelta(days=1)
        return from_date

    def _auto_fill_empty_dates(self):
        """Auto-fill empty dates with 2 business days apart, starting from next business day."""
        if not self.date_vars:
            return

        # Find first valid date or use next business day as base
        base_date = None
        for i, date_var in enumerate(self.date_vars):
            date_str = date_var.get().strip()
            if date_str:
                try:
                    base_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    break
                except:
                    pass

        # If no valid date found, start from next business day
        if base_date is None:
            base_date = self._next_business_day(datetime.now().date() + timedelta(days=1), skip_weekends=True)
            # Set first email date
            self.date_vars[0].set(base_date.strftime("%Y-%m-%d"))

        # Fill all dates with 2 business days apart
        current_date = base_date
        for i in range(len(self.date_vars)):
            date_str = self.date_vars[i].get().strip()
            if not date_str:
                # Set this date based on previous email + 2 business days
                if i == 0:
                    self.date_vars[i].set(current_date.strftime("%Y-%m-%d"))
                else:
                    current_date = self._add_business_days(current_date, 2, skip_weekends=True)
                    self.date_vars[i].set(current_date.strftime("%Y-%m-%d"))
            else:
                # Use existing date as the base for next calculation
                try:
                    current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except:
                    pass

            # Also ensure time is set
            if i < len(self.time_vars) and not self.time_vars[i].get().strip():
                self.time_vars[i].set("9:00 AM")

    def _get_autobuild_base_date(self) -> date:
        """Get start date for autobuild. If blank, use next business day."""
        start_str = self.autobuild_start_date_var.get().strip()
        skip_weekends = self.autobuild_skip_weekends_var.get()

        if start_str:
            try:
                base = datetime.strptime(start_str, "%Y-%m-%d").date()
            except:
                base = datetime.now().date() + timedelta(days=1)
        else:
            # Default: next business day
            base = datetime.now().date() + timedelta(days=1)

        return self._next_business_day(base, skip_weekends)

    def _apply_autobuild_schedule(self):
        """
        Compute dates from autobuild settings and write to date_vars/time_vars.
        Uses 2 business day intervals between all emails.
        """
        email_count = len(self.subject_vars)
        if email_count == 0:
            return

        # Ensure delay_vars are in sync
        self._ensure_delay_vars_len()

        # Set all delays to 2 business days (first email is 0)
        for i in range(email_count):
            if i == 0:
                self.delay_vars[i].set("0")
            else:
                self.delay_vars[i].set("2")  # 2 business days for all

        # Get base date and time
        base_date = self._get_autobuild_base_date()
        send_time = self.autobuild_send_time_var.get().strip()
        skip_weekends = self.autobuild_skip_weekends_var.get()

        # Compute dates for each email
        current_date = base_date
        for i in range(email_count):
            # Apply delay (business days)
            if i > 0:
                current_date = self._add_business_days(current_date, 2, skip_weekends)

            # Write to date_vars and time_vars
            if i < len(self.date_vars):
                self.date_vars[i].set(current_date.strftime("%Y-%m-%d"))
            if i < len(self.time_vars):
                self.time_vars[i].set(send_time)

        # Refresh UI (schedule table and review panel if visible)
        self._rebuild_sequence_table()

        # Show confirmation
        messagebox.showinfo(
            "Schedule Applied",
            f"Schedule applied to {email_count} email(s) with 2 business day intervals.\n\n"
            f"You can edit any date/time in the table above."
        )

    def _debounced_autobuild_apply(self):
        """Optional debounced apply (can be used if triggering from spinbox changes)."""
        if self._autobuild_after_id:
            self.after_cancel(self._autobuild_after_id)
        self._autobuild_after_id = self.after(500, self._apply_autobuild_schedule)

    def _rebuild_autobuild_delay_inputs(self):
        """Rebuild the delay spinboxes in Auto-Build Schedule section to match email count."""
        if not hasattr(self, "autobuild_delay_spinboxes_frame"):
            return

        # Clear existing spinboxes
        for widget in self.autobuild_delay_spinboxes_frame.winfo_children():
            widget.destroy()

        # Ensure delay_vars are in sync
        self._ensure_delay_vars_len()

        email_count = len(self.subject_vars)
        if email_count == 0:
            tk.Label(
                self.autobuild_delay_spinboxes_frame,
                text="(no emails yet)",
                bg=BG_ENTRY,
                fg=FG_MUTED,
                font=("Segoe UI", 8, "italic")
            ).pack(side="left")
            return

        # Create spinbox for each email
        for i in range(email_count):
            email_name = self.name_vars[i].get() if i < len(self.name_vars) else f"Email {i+1}"
            if not email_name:
                email_name = f"Email {i+1}"

            # Create frame for this email's delay
            delay_frame = tk.Frame(self.autobuild_delay_spinboxes_frame, bg=BG_ENTRY)
            delay_frame.pack(side="left", padx=(0, 12))

            tk.Label(
                delay_frame,
                text=f"{email_name}:",
                bg=BG_ENTRY,
                fg=FG_TEXT,
                font=FONT_CAPTION
            ).pack(side="left", padx=(0, 4))

            if i == 0:
                # Email 1 is always 0 (locked)
                self.delay_vars[i].set("0")
                tk.Label(
                    delay_frame,
                    text="0",
                    bg=BG_ENTRY,
                    fg=FG_MUTED,
                    font=FONT_CAPTION
                ).pack(side="left")
            else:
                # Other emails: editable spinbox
                delay_spinbox = tk.Spinbox(
                    delay_frame,
                    from_=0,
                    to=30,
                    textvariable=self.delay_vars[i],
                    width=4,
                    bg=BG_ENTRY,
                    fg=FG_TEXT,
                    font=FONT_CAPTION,
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BORDER_MEDIUM,
                    highlightcolor=ACCENT,
                )
                delay_spinbox.pack(side="left")

    def _set_schedule_mode(self, mode: str):
        """Switch between 'fixed' and 'relative' schedule modes."""
        self.schedule_mode_var.set(mode)
        self._sync_mode_toggle_style()
        self._on_schedule_mode_changed()

    def _sync_mode_toggle_style(self):
        """Update mode toggle button colors to reflect current selection."""
        mode = self.schedule_mode_var.get()
        if not hasattr(self, "_mode_btn_fixed"):
            return
        if mode == "fixed":
            self._mode_btn_fixed.configure(bg=ACCENT, fg=FG_WHITE,
                                           activebackground=ACCENT_HOVER, activeforeground=FG_WHITE)
            self._mode_btn_relative.configure(bg=BG_ENTRY, fg=FG_TEXT,
                                              activebackground=BG_HOVER, activeforeground=FG_TEXT)
        else:
            self._mode_btn_relative.configure(bg=ACCENT, fg=FG_WHITE,
                                              activebackground=ACCENT_HOVER, activeforeground=FG_WHITE)
            self._mode_btn_fixed.configure(bg=BG_ENTRY, fg=FG_TEXT,
                                           activebackground=BG_HOVER, activeforeground=FG_TEXT)

    def _on_daily_limit_toggled(self):
        """Enable/disable the daily limit spinbox based on checkbox state."""
        if hasattr(self, "_daily_limit_spin"):
            if self.daily_limit_enabled_var.get():
                self._daily_limit_spin.configure(state="normal")
            else:
                self._daily_limit_spin.configure(state="disabled")

    def _on_schedule_mode_changed(self):
        """Handle schedule mode change."""
        mode = self.schedule_mode_var.get()

        # Show/hide relative settings frame
        if mode == "relative":
            if hasattr(self, "relative_settings_frame"):
                # Pack BEFORE the sequence_table
                self.relative_settings_frame.pack(fill="x", padx=10, pady=(0, 8),
                                                  before=self.sequence_table)
        else:
            if hasattr(self, "relative_settings_frame"):
                self.relative_settings_frame.pack_forget()

        # Force rebuild (bypass the anti-flicker "same count" guard)
        self._seq_table_last_n = -1
        self._rebuild_sequence_table()

    def _on_relative_settings_changed(self):
        """Handle changes to relative scheduling settings (recalculate dates)."""
        if self.schedule_mode_var.get() == "relative":
            # Reset anti-flicker guard so the rebuild proceeds (email count unchanged)
            self._seq_table_last_n = -1
            self._rebuild_sequence_table()

    def _apply_delays_to_dates(self):
        """Compute send dates for emails 2+ from Email 1's date + business days."""
        if len(self.date_vars) < 2:
            return

        # Parse Email 1's date as the anchor
        start_str = self.date_vars[0].get().strip()
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        except Exception:
            self._set_status("Set a valid date for Email 1 first", WARN)
            return

        current_date = start_date

        for i in range(1, len(self.date_vars)):
            try:
                delay = int(self.delay_vars[i].get()) if i < len(self.delay_vars) else 2
            except (ValueError, TypeError):
                delay = 2

            # Always skip weekends — these are business days
            current_date = self._add_business_days(current_date, delay, skip_weekends=True)
            self.date_vars[i].set(current_date.strftime("%Y-%m-%d"))

        self._set_status("Dates updated from business days", GOOD)

    def _update_schedule(self):
        """Update schedule: compute dates (days mode) or validate (dates mode),
        then show the schedule summary."""
        # Ensure all date_vars have a value (DateEntry may not write back to var)
        today_str = datetime.now().strftime("%Y-%m-%d")
        for dv in self.date_vars:
            if not dv.get().strip():
                dv.set(today_str)

        seq_mode = self._seq_mode_var.get()

        if seq_mode == "days":
            # Compute actual send dates from business-day offsets
            self._apply_delays_to_dates()

        # Build the schedule summary display
        self._show_schedule_summary()

    def _show_schedule_summary(self):
        """Render a styled schedule preview table in the right-side panel."""
        if not hasattr(self, "_schedule_summary_frame"):
            return

        # Clear previous summary
        for child in self._schedule_summary_frame.winfo_children():
            child.destroy()

        n = len(self.date_vars)
        if n == 0:
            return

        # Collect schedule entries
        entries = []
        for i in range(n):
            name = self.name_vars[i].get().strip() if i < len(self.name_vars) else f"Email {i+1}"
            name = name or f"Email {i+1}"
            date_str = self.date_vars[i].get().strip() if i < len(self.date_vars) else ""
            time_str = self.time_vars[i].get().strip() if i < len(self.time_vars) else ""
            attach_n = len(self.per_email_attachments[i]) if i < len(self.per_email_attachments) else 0

            # Format the date nicely (e.g. "Mon, Feb 17")
            display_date = date_str
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                display_date = dt.strftime("%a, %b %d")
            except Exception:
                pass

            entries.append((name, display_date, time_str, attach_n))

        # ── Build the styled table ──
        HEADER_BG = "#7C3AED"   # Purple header
        HEADER_FG = "#FFFFFF"
        ROW_EVEN = "#FFFFFF"
        ROW_ODD = "#F5F3FF"     # Light purple tint
        BORDER_CLR = "#E2E8F0"
        TEXT_CLR = GRAY_800
        MUTED_CLR = GRAY_500

        # Title
        tk.Label(
            self._schedule_summary_frame, text="Schedule Preview",
            bg=BG_CARD, fg=ACCENT, font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", pady=(0, 6))

        # Table container with border
        table_border = tk.Frame(self._schedule_summary_frame, bg=BORDER_CLR)
        table_border.pack(fill="x")

        table = tk.Frame(table_border, bg=BORDER_CLR)
        table.pack(fill="x", padx=1, pady=1)

        # Column config
        table.columnconfigure(0, weight=1, minsize=120)  # Email
        table.columnconfigure(1, weight=0, minsize=110)  # Date
        table.columnconfigure(2, weight=0, minsize=80)   # Time
        table.columnconfigure(3, weight=0, minsize=90)   # Attachments

        hdr_font = ("Segoe UI Semibold", 9)
        cell_font = ("Segoe UI", 9)
        pad_x = 10
        pad_y = 6

        # Header row
        for col_idx, hdr_text in enumerate(["Step", "Date", "Time", "Attachments"]):
            tk.Label(
                table, text=hdr_text, bg=HEADER_BG, fg=HEADER_FG,
                font=hdr_font, anchor="w", padx=pad_x, pady=pad_y,
            ).grid(row=0, column=col_idx, sticky="nsew", padx=(0, 1) if col_idx < 3 else 0)

        # Data rows
        for i, (name, d, t, att) in enumerate(entries):
            row_bg = ROW_EVEN if i % 2 == 0 else ROW_ODD
            r = i + 1

            tk.Label(
                table, text=name, bg=row_bg, fg=TEXT_CLR,
                font=cell_font, anchor="w", padx=pad_x, pady=pad_y,
            ).grid(row=r, column=0, sticky="nsew", padx=(0, 1))

            tk.Label(
                table, text=d, bg=row_bg, fg=TEXT_CLR,
                font=cell_font, anchor="w", padx=pad_x, pady=pad_y,
            ).grid(row=r, column=1, sticky="nsew", padx=(0, 1))

            tk.Label(
                table, text=t, bg=row_bg, fg=TEXT_CLR,
                font=cell_font, anchor="w", padx=pad_x, pady=pad_y,
            ).grid(row=r, column=2, sticky="nsew", padx=(0, 1))

            att_text = f"{att} file(s)" if att else "None"
            att_fg = TEXT_CLR if att else MUTED_CLR
            tk.Label(
                table, text=att_text, bg=row_bg, fg=att_fg,
                font=cell_font, anchor="center", padx=pad_x, pady=pad_y,
            ).grid(row=r, column=3, sticky="nsew")

        self._set_status("Schedule updated", GOOD)

    # ── Default sequence presets ──
    # (delay_days, send_time) per email — delay for Step 1 is always 0
    # Escalating delays: later follow-ups space out further (industry best practice)
    _DEFAULT_SEQUENCES = {
        3: [(0, "9:00 AM"), (2, "9:00 AM"), (5, "2:00 PM")],
        4: [(0, "9:00 AM"), (2, "9:00 AM"), (3, "2:00 PM"), (5, "10:00 AM")],
        5: [(0, "9:00 AM"), (2, "9:00 AM"), (3, "2:00 PM"), (5, "10:00 AM"),
            (7, "9:00 AM")],
        6: [(0, "9:00 AM"), (2, "9:00 AM"), (3, "2:00 PM"), (4, "10:00 AM"),
            (5, "9:00 AM"), (7, "2:00 PM")],
        7: [(0, "9:00 AM"), (2, "9:00 AM"), (2, "2:00 PM"), (3, "10:00 AM"),
            (4, "9:00 AM"), (5, "2:00 PM"), (7, "10:00 AM")],
        8: [(0, "9:00 AM"), (2, "9:00 AM"), (2, "2:00 PM"), (3, "10:00 AM"),
            (3, "9:00 AM"), (4, "2:00 PM"), (5, "10:00 AM"), (7, "9:00 AM")],
        9: [(0, "9:00 AM"), (2, "9:00 AM"), (2, "2:00 PM"), (3, "10:00 AM"),
            (3, "9:00 AM"), (4, "2:00 PM"), (5, "10:00 AM"), (7, "9:00 AM"),
            (7, "2:00 PM")],
        10: [(0, "9:00 AM"), (2, "9:00 AM"), (2, "2:00 PM"), (3, "10:00 AM"),
             (3, "9:00 AM"), (4, "2:00 PM"), (4, "10:00 AM"), (5, "9:00 AM"),
             (7, "2:00 PM"), (7, "10:00 AM")],
    }

    def _apply_default_sequence(self):
        """Apply a built-in preset sequence from the dropdown."""
        choice = self._preset_seq_var.get()
        try:
            target_n = int(choice.split()[0])
        except (ValueError, IndexError):
            return
        preset = self._DEFAULT_SEQUENCES.get(target_n)
        if not preset:
            return

        self._suspend_rebuilds = True
        try:
            while len(self.subject_vars) < target_n:
                next_num = len(self.subject_vars) + 1
                self._add_email(
                    name=f"Email {next_num}",
                    subject="", body="", date="", time="9:00 AM",
                )
            while len(self.subject_vars) > target_n:
                self._delete_email(len(self.subject_vars) - 1)
        finally:
            self._suspend_rebuilds = False

        for i, (delay, send_time) in enumerate(preset):
            if i < len(self.delay_vars):
                self.delay_vars[i].set(str(delay))
            if i < len(self.time_vars):
                self.time_vars[i].set(send_time)

        if self.date_vars and not self.date_vars[0].get().strip():
            start = datetime.now().date() + timedelta(days=1)
            while start.weekday() >= 5:
                start += timedelta(days=1)
            self.date_vars[0].set(start.strftime("%Y-%m-%d"))

        self._apply_delays_to_dates()

        self._seq_table_last_n = -1
        self._rebuild_sequence_table()
        self._refresh_tab_labels()
        self._ensure_delay_vars_len()
        self._rebuild_autobuild_delay_inputs()
        self._set_status(f"Applied {target_n}-email preset sequence", GOOD)

    def _open_customize_preset(self):
        """Open popup to customize the days-after and send-time for the selected preset."""
        choice = self._preset_seq_var.get()
        try:
            target_n = int(choice.split()[0])
        except (ValueError, IndexError):
            return
        preset = self._DEFAULT_SEQUENCES.get(target_n)
        if not preset:
            return

        # Make a mutable copy
        preset_copy = list(preset)

        win = tk.Toplevel(self)
        win.title(f"Customize {target_n}-Email Sequence")
        win.configure(bg=BG_ROOT)
        w, h = 380, min(100 + target_n * 36, 520)
        # Centre on screen
        sx = self.winfo_screenwidth()
        sy = self.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sx - w) // 2}+{(sy - h) // 2}")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        tk.Label(
            win, text=f"Customize {target_n}-Email Sequence",
            bg=BG_ROOT, fg=ACCENT, font=FONT_SECTION,
        ).pack(anchor="w", padx=16, pady=(14, 8))

        # Grid of emails
        grid = tk.Frame(win, bg=BG_ROOT)
        grid.pack(fill="x", padx=16)

        # Headers
        tk.Label(grid, text="Step", bg=BG_ROOT, fg=FG_MUTED,
                 font=FONT_SMALL, width=8, anchor="w").grid(row=0, column=0, padx=(0, 6), pady=(0, 4))
        tk.Label(grid, text="Wait (business days)", bg=BG_ROOT, fg=FG_MUTED,
                 font=FONT_SMALL, anchor="w").grid(row=0, column=1, padx=(0, 6), pady=(0, 4))
        tk.Label(grid, text="Send Time", bg=BG_ROOT, fg=FG_MUTED,
                 font=FONT_SMALL, anchor="w").grid(row=0, column=2, pady=(0, 4))

        delay_vars = []
        time_vars = []

        for i in range(target_n):
            r = i + 1
            delay, send_time = preset_copy[i]

            # Email label
            tk.Label(grid, text=f"Email {i + 1}", bg=BG_ROOT, fg=FG_TEXT,
                     font=FONT_SMALL, anchor="w").grid(row=r, column=0, padx=(0, 6), pady=2, sticky="w")

            # Days-after: Email 1 is always "—"
            dv = tk.StringVar(value=str(delay))
            delay_vars.append(dv)
            if i == 0:
                tk.Label(grid, text="—", bg=BG_ROOT, fg=FG_MUTED,
                         font=FONT_SMALL, width=6).grid(row=r, column=1, padx=(0, 6), pady=2)
            else:
                tk.Spinbox(
                    grid, textvariable=dv, from_=1, to=90, width=5,
                    font=FONT_SMALL, bg=BG_ENTRY, fg=FG_TEXT,
                    buttonbackground=BG_CARD, relief="flat",
                    highlightthickness=1, highlightbackground=BORDER_MEDIUM,
                ).grid(row=r, column=1, padx=(0, 6), pady=2)

            # Send time
            tv = tk.StringVar(value=send_time)
            time_vars.append(tv)
            ttk.Combobox(
                grid, textvariable=tv, values=TIME_OPTIONS,
                width=10, state="readonly", style="Dark.TCombobox",
            ).grid(row=r, column=2, pady=2)

        # Buttons
        btn_frame = tk.Frame(win, bg=BG_ROOT)
        btn_frame.pack(fill="x", padx=16, pady=(12, 14))

        def _on_apply():
            # Build custom preset from the popup values
            custom = []
            for i in range(target_n):
                try:
                    d = int(delay_vars[i].get()) if i > 0 else 0
                except ValueError:
                    d = 2
                t = time_vars[i].get() or "9:00 AM"
                custom.append((d, t))

            win.destroy()

            # Apply like a normal preset
            self._suspend_rebuilds = True
            try:
                while len(self.subject_vars) < target_n:
                    next_num = len(self.subject_vars) + 1
                    self._add_email(
                        name=f"Email {next_num}",
                        subject="", body="", date="", time="9:00 AM",
                    )
                while len(self.subject_vars) > target_n:
                    self._delete_email(len(self.subject_vars) - 1)
            finally:
                self._suspend_rebuilds = False

            for i, (delay, send_time) in enumerate(custom):
                if i < len(self.delay_vars):
                    self.delay_vars[i].set(str(delay))
                if i < len(self.time_vars):
                    self.time_vars[i].set(send_time)

            if self.date_vars and not self.date_vars[0].get().strip():
                start = datetime.now().date() + timedelta(days=1)
                while start.weekday() >= 5:
                    start += timedelta(days=1)
                self.date_vars[0].set(start.strftime("%Y-%m-%d"))

            self._apply_delays_to_dates()
            self._seq_table_last_n = -1
            self._rebuild_sequence_table()
            self._refresh_tab_labels()
            self._ensure_delay_vars_len()
            self._rebuild_autobuild_delay_inputs()
            self._set_status(f"Applied custom {target_n}-email sequence", GOOD)

        apply_btn = tk.Button(
            btn_frame, text="Save",
            command=_on_apply,
            bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_HOVER,
            activeforeground=FG_WHITE, relief="flat", font=FONT_SMALL,
            padx=14, pady=6, cursor="hand2",
        )
        apply_btn.pack(side="left", padx=(0, 8))
        apply_btn.bind("<Enter>", lambda e: apply_btn.config(bg=ACCENT_HOVER))
        apply_btn.bind("<Leave>", lambda e: apply_btn.config(bg=ACCENT))

        cancel_btn = tk.Button(
            btn_frame, text="Cancel",
            command=win.destroy,
            bg=BORDER_SOFT, fg=FG_TEXT, activebackground=BG_HOVER,
            activeforeground=ACCENT, relief="flat", font=FONT_SMALL,
            padx=14, pady=6, cursor="hand2",
        )
        cancel_btn.pack(side="left")
        cancel_btn.bind("<Enter>", lambda e: cancel_btn.config(bg="#FFFFFF", fg=ACCENT))
        cancel_btn.bind("<Leave>", lambda e: cancel_btn.config(bg=BORDER_SOFT, fg=FG_TEXT))

    # ============================================
    # Email management
    # ============================================
    def _handle_plus_tab_click(self):
        """Called when user clicks the '+' tab — switch back, add email, clear flag."""
        try:
            tabs = self.email_notebook.tabs()
            real = [t for t in tabs if t != str(self._add_tab_frame)]
            if real:
                self.email_notebook.select(real[-1])
            self._add_email_from_button()
        finally:
            self._adding_email = False

    def _add_email_from_button(self):
        """Add a new email when user clicks + Add Email tab"""
        # Check max limit
        if len(self.subject_vars) >= 15:
            messagebox.showinfo("Maximum emails", "You can have at most 15 emails in your sequence.")
            self._set_status("Cannot add more emails", WARN)
            return

        # Calculate next email number and date
        next_num = len(self.subject_vars) + 1

        # Calculate date: 2 business days after last email (or next business day for first)
        if self.date_vars:
            try:
                last_date_str = self.date_vars[-1].get()
                last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                next_date = self._add_business_days(last_date, 2, skip_weekends=True).strftime("%Y-%m-%d")
            except:
                base_date = datetime.now().date() + timedelta(days=1)
                next_date = self._next_business_day(base_date, skip_weekends=True).strftime("%Y-%m-%d")
        else:
            base_date = datetime.now().date() + timedelta(days=1)
            next_date = self._next_business_day(base_date, skip_weekends=True).strftime("%Y-%m-%d")

        # Add a new blank email (signature shown in read-only preview)
        self._add_email(
            name=f"Email {next_num}",
            subject="",
            body="",
            date=next_date,
            time="9:00 AM"
        )

        # Switch to the newly created tab (second-to-last, before "+" tab)
        try:
            tabs = self.email_notebook.tabs()
            if len(tabs) >= 2:
                self.email_notebook.select(tabs[-2])
            elif tabs:
                self.email_notebook.select(tabs[0])
        except:
            pass

        self._set_status(f"Email {next_num} added", GOOD)

        # Refresh execute screen checklist (if on that screen)
        if hasattr(self, "_refresh_execute_review_panel"):
            try:
                self._refresh_execute_review_panel()
            except:
                pass

    # ==================================================================
    # AI Assist (ChatGPT Integration)
    # ==================================================================

    def _get_openai_key(self) -> str:
        """Get the OpenAI API key. Checks shared team config first, then local."""
        # 1. Check shared team config (OneDrive)
        try:
            if SHARED_CONFIG_PATH.exists():
                with open(SHARED_CONFIG_PATH, "r", encoding="utf-8") as f:
                    team_cfg = json.load(f)
                key = team_cfg.get("openai_api_key", "")
                if key:
                    return key
        except Exception:
            pass
        # 2. Fall back to local config
        cfg = load_config()
        return cfg.get("openai_api_key", "")

    def _save_openai_key(self, key: str):
        """Save the OpenAI API key to shared team config (if admin) and local config."""
        key = key.strip()
        # Save to shared team config so the whole team can use it
        try:
            SHARED_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            team_cfg = {}
            if SHARED_CONFIG_PATH.exists():
                with open(SHARED_CONFIG_PATH, "r", encoding="utf-8") as f:
                    team_cfg = json.load(f)
            team_cfg["openai_api_key"] = key
            with open(SHARED_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(team_cfg, f, indent=2)
        except Exception:
            pass  # OneDrive unavailable — save locally only
        # Also save to local config as fallback
        cfg = load_config()
        cfg["openai_api_key"] = key
        save_config(cfg)

    def _prompt_for_api_key(self) -> str:
        """Show a dialog to enter the OpenAI API key. Returns the key or empty string."""
        win = tk.Toplevel(self)
        win.title("OpenAI API Key")
        win.geometry("500x220")
        win.configure(bg=BG_CARD)
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        result = {"key": ""}

        tk.Label(win, text="Enter your OpenAI API Key", bg=BG_CARD, fg=FG_TEXT,
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(win, text="Get your key at platform.openai.com/api-keys",
                 bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", padx=20, pady=(0, 12))

        key_var = tk.StringVar(value=self._get_openai_key())
        ent = tk.Entry(win, textvariable=key_var, bg=BG_ENTRY, fg=FG_TEXT,
                       insertbackground=FG_TEXT, font=FONT_BASE, show="*",
                       relief="flat", highlightthickness=1,
                       highlightbackground=BORDER_MEDIUM, highlightcolor=ACCENT)
        ent.pack(fill="x", padx=20, pady=(0, 8))
        ent.focus_set()

        show_var = tk.BooleanVar(value=False)
        def _toggle_show():
            ent.config(show="" if show_var.get() else "*")
        tk.Checkbutton(win, text="Show key", variable=show_var, command=_toggle_show,
                       bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL,
                       activebackground=BG_CARD, selectcolor=BG_ENTRY).pack(anchor="w", padx=20)

        btn_row = tk.Frame(win, bg=BG_CARD)
        btn_row.pack(fill="x", padx=20, pady=(12, 16))

        def _save():
            k = key_var.get().strip()
            if not k:
                self.toast.show("API key cannot be empty", "error")
                return
            self._save_openai_key(k)
            result["key"] = k
            win.destroy()

        save_btn = tk.Button(btn_row, text="Save Key", command=_save,
                             bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_HOVER,
                             activeforeground=FG_WHITE, relief="flat",
                             font=("Segoe UI Semibold", 10), padx=16, pady=6, cursor="hand2")
        save_btn.pack(side="left")

        tk.Button(btn_row, text="Cancel", command=win.destroy,
                  bg=BORDER_SOFT, fg=FG_TEXT, activebackground=BG_HOVER,
                  relief="flat", font=FONT_SMALL, padx=12, pady=6, cursor="hand2"
                  ).pack(side="right")

        win.bind("<Return>", lambda e: _save())
        win.bind("<Escape>", lambda e: win.destroy())
        win.wait_window()
        return result["key"]

    def _run_ai_schedule(self):
        """Ask ChatGPT to recommend a schedule based on the email bodies — no user input needed."""
        api_key = self._get_openai_key()
        if not api_key:
            api_key = self._prompt_for_api_key()
            if not api_key:
                return

        num_emails = len(self.subject_vars)
        if num_emails == 0:
            self.toast.show("Add emails first before asking ChatGPT for a schedule.", "error")
            return

        # Gather email content automatically
        email_summaries = []
        for i in range(num_emails):
            name = self.name_vars[i].get() if i < len(self.name_vars) else f"Email {i+1}"
            subject = self.subject_vars[i].get() if i < len(self.subject_vars) else ""
            body = ""
            if i < len(self.body_texts):
                body = self.body_texts[i].get("1.0", "end-1c").strip()
            # Truncate long bodies to keep the prompt reasonable
            if len(body) > 300:
                body = body[:300] + "..."
            email_summaries.append(f"Email {i+1} - \"{name}\"\nSubject: {subject}\nBody: {body}")

        context = "\n\n".join(email_summaries)
        messages = build_schedule_messages(num_emails, context, custom_context=self._load_ai_training())

        # Disable button and show status
        self._ai_schedule_btn.config(state="disabled", text="Thinking...")
        self._set_status("ChatGPT is analyzing your emails...", "#3B82F6")

        import re

        def _parse_schedule(text):
            """Parse ChatGPT schedule into list of (day_offset, time_str) tuples."""
            schedule = []
            for line in text.split("\n"):
                line = line.strip()
                m = re.match(
                    r'Email\s+\d+\s*:\s*Day\s+(\d+)\s*,\s*(\d{1,2}:\d{2}\s*[AaPp][Mm])',
                    line
                )
                if m:
                    day = int(m.group(1))
                    time_str = m.group(2).strip().upper()
                    time_str = re.sub(r'(\d{1,2}:\d{2})\s*([AP]M)', r'\1 \2', time_str)
                    schedule.append((day, time_str))
            return schedule

        def _on_result(text):
            def _apply():
                self._ai_schedule_btn.config(state="normal", text="Ask ChatGPT")

                parsed = _parse_schedule(text)
                if not parsed:
                    self.toast.show("Could not parse schedule — try again.", "error")
                    self._set_status("AI schedule failed to parse", DANGER)
                    return

                # Switch to "days" mode and reveal schedule cards
                self._set_seq_mode("days")

                # Apply delays and times
                for i, (day_offset, time_str) in enumerate(parsed):
                    if i < len(self.time_vars):
                        self.time_vars[i].set(time_str)
                    if i == 0:
                        if i < len(self.delay_vars):
                            self.delay_vars[i].set("0")
                    else:
                        prev_day = parsed[i - 1][0]
                        gap = day_offset - prev_day
                        if gap < 1:
                            gap = 1
                        if i < len(self.delay_vars):
                            self.delay_vars[i].set(str(gap))

                # Set start date to next business day
                if self.date_vars:
                    start = datetime.now().date() + timedelta(days=1)
                    while start.weekday() >= 5:
                        start += timedelta(days=1)
                    self.date_vars[0].set(start.strftime("%Y-%m-%d"))
                    self._apply_delays_to_dates()

                self._rebuild_sequence_table()
                self.toast.show(f"AI schedule applied — {len(parsed)} emails scheduled!", "info")
                self._set_status("AI-recommended schedule applied", GOOD)

            self.after(0, _apply)

        def _on_error(err):
            def _handle():
                self._ai_schedule_btn.config(state="normal", text="Ask ChatGPT")
                self.toast.show(f"AI error: {err}", "error")
                self._set_status(f"AI schedule error: {err}", DANGER)
            self.after(0, _handle)

        call_openai_async(api_key, messages, _on_result, _on_error, temperature=0.7)

    def _open_ai_campaign_dialog(self):
        """Open the AI Campaign generator dialog."""
        api_key = self._get_openai_key()
        if not api_key:
            api_key = self._prompt_for_api_key()
            if not api_key:
                return

        win = tk.Toplevel(self)
        win.title("AI Campaign Generator")
        win.geometry("760x820")
        win.configure(bg=BG_CARD)
        win.resizable(True, True)
        win.transient(self)
        win.grab_set()

        # Header
        hdr = tk.Frame(win, bg="#3B82F6", height=48)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="AI Campaign Generator  \u2014  Powered by ChatGPT",
                 bg="#3B82F6", fg="#FFFFFF",
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=20, pady=10)

        # ── Bottom bar (pack before content so it always has space) ──
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", side="bottom")
        bottom = tk.Frame(win, bg=BG_CARD)
        bottom.pack(fill="x", side="bottom", padx=24, pady=12)

        apply_btn = tk.Button(
            bottom, text="Apply",
            command=lambda: _apply(),
            bg="#3B82F6", fg="#FFFFFF", activebackground="#2563EB",
            activeforeground="#FFFFFF", disabledforeground="#BFDBFE",
            relief="flat", font=("Segoe UI Semibold", 10),
            padx=16, pady=8, cursor="hand2", state="disabled",
        )
        apply_btn.pack(side="right")

        content = tk.Frame(win, bg=BG_CARD)
        content.pack(fill="both", expand=True, padx=24, pady=(20, 10))

        # ── Number of emails ──
        row1 = tk.Frame(content, bg=BG_CARD)
        row1.pack(fill="x", pady=(0, 10))

        tk.Label(row1, text="How many emails?", bg=BG_CARD, fg=FG_TEXT,
                 font=("Segoe UI Semibold", 10)).pack(side="left")

        num_var = tk.StringVar(value="7")
        num_spin = tk.Spinbox(row1, from_=3, to=10, textvariable=num_var, width=4,
                              bg=BG_ENTRY, fg=FG_TEXT, font=FONT_BASE,
                              buttonbackground=GRAY_200, relief="flat",
                              highlightthickness=1, highlightbackground=BORDER_MEDIUM)
        num_spin.pack(side="left", padx=(12, 0))

        # ── Describe your campaign ──
        tk.Label(content, text="Describe your campaign", bg=BG_CARD, fg=FG_TEXT,
                 font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 6))

        # Instructions box
        tips_frame = tk.Frame(content, bg="#EFF6FF", highlightbackground="#BFDBFE",
                              highlightthickness=1, relief="flat")
        tips_frame.pack(fill="x", pady=(0, 10))

        tips_text = (
            "The more detail you give, the better your campaign will be. Include:\n"
            "\n"
            "\u2022  Who you're targeting  \u2014  job titles, industries, company size, location\n"
            "\u2022  What you're selling  \u2014  your product, service, or offering\n"
            "\u2022  Your company  \u2014  name, what makes you different, key strengths\n"
            "\u2022  Pain points  \u2014  what problems does your audience face?\n"
            "\u2022  Value props  \u2014  how do you solve those problems? Results/stats if you have them\n"
            "\u2022  Tone  \u2014  professional, casual, consultative, urgent, friendly\n"
            "\u2022  Call to action  \u2014  book a call, reply, visit a link, etc.\n"
            "\u2022  Your name & title  \u2014  so the emails sound like they're from you"
        )
        tk.Label(tips_frame, text=tips_text, bg="#EFF6FF", fg=GRAY_700,
                 font=("Segoe UI", 9), justify="left", anchor="nw",
                 padx=12, pady=10).pack(fill="x")

        # Single prompt box
        prompt_text = tk.Text(content, bg=BG_ENTRY, fg=FG_TEXT, font=FONT_BASE,
                              wrap="word", height=5, relief="flat",
                              highlightthickness=1, highlightbackground=BORDER_MEDIUM,
                              highlightcolor=ACCENT, padx=10, pady=8)
        prompt_text.pack(fill="x", pady=(0, 10))
        prompt_text.insert("1.0",
            "Example: I'm a recruiter at Arena Staffing selling skilled trades "
            "staffing services to construction project managers and superintendents "
            "in the Southeast US. We specialize in placing electricians, plumbers, "
            "and pipefitters quickly. Pain point: they can't find reliable workers "
            "fast enough and lose money on project delays. Tone: professional but "
            "conversational. CTA: book a quick 10-min call. My name is Michael Vaughn."
        )
        prompt_text.config(fg=FG_LIGHT)

        def _on_focus_in(e):
            if prompt_text.get("1.0", "end-1c").startswith("Example:"):
                prompt_text.delete("1.0", "end")
                prompt_text.config(fg=FG_TEXT)

        def _on_focus_out(e):
            if not prompt_text.get("1.0", "end-1c").strip():
                prompt_text.insert("1.0",
                    "Example: I'm a recruiter at Arena Staffing selling skilled trades "
                    "staffing services to construction project managers..."
                )
                prompt_text.config(fg=FG_LIGHT)

        prompt_text.bind("<FocusIn>", _on_focus_in)
        prompt_text.bind("<FocusOut>", _on_focus_out)

        # ── Generate button + status ──
        gen_row = tk.Frame(content, bg=BG_CARD)
        gen_row.pack(fill="x", pady=(0, 10))

        status_label = tk.Label(gen_row, text="", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL)
        status_label.pack(side="right")

        gen_btn = tk.Button(
            gen_row, text="Generate Campaign",
            command=lambda: _generate(),
            bg="#3B82F6", fg="#FFFFFF", activebackground="#2563EB",
            activeforeground="#FFFFFF", relief="flat",
            font=("Segoe UI Semibold", 11), padx=20, pady=8, cursor="hand2",
        )
        gen_btn.pack(side="left")

        # ── Preview area ──
        tk.Label(content, text="Preview", bg=BG_CARD, fg=FG_TEXT,
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(0, 4))

        preview_text = tk.Text(content, bg="#FFFFFF", fg=FG_TEXT, font=FONT_BASE,
                               wrap="word", height=6, relief="flat",
                               highlightthickness=1, highlightbackground=BORDER_MEDIUM,
                               padx=10, pady=8)
        preview_text.pack(fill="both", expand=True, pady=(0, 4))
        preview_text.config(state="disabled")

        # Store parsed emails for apply
        parsed_emails = []

        def _generate():
            api_key = self._get_openai_key()
            if not api_key:
                return

            description = prompt_text.get("1.0", "end-1c").strip()
            if not description or description.startswith("Example:"):
                self.toast.show("Describe your campaign first", "error")
                return

            try:
                num_emails = int(num_var.get())
            except ValueError:
                num_emails = 7

            messages = build_sequence_messages(num_emails, description, custom_context=self._load_ai_training())

            gen_btn.config(state="disabled", text="Generating...")
            status_label.config(text="ChatGPT is writing your campaign...", fg="#3B82F6")

            def _on_result(text):
                win.after(0, lambda: _show_result(text))

            def _on_error(err):
                win.after(0, lambda: _show_error(err))

            call_openai_async(api_key, messages, _on_result, _on_error,
                              temperature=0.8)

        def _show_result(text):
            gen_btn.config(state="normal", text="Generate Campaign")
            status_label.config(text="Campaign generated! Review below, then click Apply.", fg=GOOD)

            preview_text.config(state="normal")
            preview_text.delete("1.0", "end")
            preview_text.insert("1.0", text)
            preview_text.config(state="disabled")

            # Parse the generated emails
            parsed_emails.clear()
            parsed_emails.extend(_parse_campaign(text))

            if parsed_emails:
                apply_btn.config(state="normal")
                status_label.config(
                    text=f"{len(parsed_emails)} emails generated! Review below, then click Apply.",
                    fg=GOOD)

        def _show_error(err):
            gen_btn.config(state="normal", text="Generate Campaign")
            status_label.config(text=f"Error: {err}", fg=DANGER)

        def _parse_campaign(text):
            """Parse ChatGPT output into list of (name, subject, body) tuples."""
            emails = []
            # Split on --- Email N: ... --- pattern
            import re
            parts = re.split(r'---\s*Email\s*(\d+)\s*:\s*(.*?)\s*---', text)
            # parts = [preamble, num, subject, body, num, subject, body, ...]
            if len(parts) >= 4:
                i = 1
                while i + 2 < len(parts):
                    num = parts[i].strip()
                    subject = parts[i + 1].strip()
                    body = parts[i + 2].strip()
                    # Clean up body — remove leading/trailing whitespace
                    body = body.strip()
                    # Use subject as the email name for meaningful tab labels
                    name = subject if subject else f"Email {num}" if num.isdigit() else f"Email {len(emails) + 1}"
                    emails.append((name, subject, body))
                    i += 3
            else:
                # Fallback: try splitting on "Email N:" or "Subject:" patterns
                blocks = re.split(r'\n(?=(?:Email\s+\d+|Subject\s*:))', text)
                for block in blocks:
                    block = block.strip()
                    if not block:
                        continue
                    subj_match = re.search(r'Subject\s*:\s*(.+)', block, re.IGNORECASE)
                    subject = subj_match.group(1).strip() if subj_match else ""
                    # Remove the subject line from body
                    body = block
                    if subj_match:
                        body = block[:subj_match.start()] + block[subj_match.end():]
                    # Remove "Email N" header
                    body = re.sub(r'^Email\s+\d+\s*[\-:]*\s*', '', body).strip()
                    if body:
                        name = subject if subject else f"Email {len(emails) + 1}"
                        emails.append((name, subject, body))
            return emails

        def _apply():
            if not parsed_emails:
                return

            # Confirm replacement
            if self.subject_vars:
                if not messagebox.askyesno(
                    "Replace Current Campaign?",
                    f"This will replace your current {len(self.subject_vars)} emails "
                    f"with {len(parsed_emails)} AI-generated emails.\n\nContinue?",
                    parent=win
                ):
                    return

            win.destroy()

            # Guard against "+" tab creating a blank email during rebuild
            self._adding_email = True

            # Reset and build new campaign
            self._reset_campaign_state()
            self._suspend_rebuilds = True

            try:
                for name, subject, body in parsed_emails:
                    self._add_email(
                        name=name,
                        subject=subject,
                        body=body,
                        date="",
                        time="9:00 AM",
                    )
            finally:
                self._suspend_rebuilds = False

            # Apply default delays
            n = len(parsed_emails)
            preset = self._DEFAULT_SEQUENCES.get(n)
            if preset:
                for i, (delay, send_time) in enumerate(preset):
                    if i < len(self.delay_vars):
                        self.delay_vars[i].set(str(delay))
                    if i < len(self.time_vars):
                        self.time_vars[i].set(send_time)

            # Set start date to next business day
            if self.date_vars:
                start = datetime.now().date() + timedelta(days=1)
                while start.weekday() >= 5:
                    start += timedelta(days=1)
                self.date_vars[0].set(start.strftime("%Y-%m-%d"))
                self._apply_delays_to_dates()

            self._rebuild_sequence_table()
            self._refresh_tab_labels()

            # Navigate to first email tab
            try:
                tabs = self.email_notebook.tabs()
                if tabs:
                    self.email_notebook.select(tabs[0])
            except Exception:
                pass

            self._adding_email = False

            self.toast.show(f"AI campaign loaded — {len(parsed_emails)} emails created!", "info")
            self._set_status(f"AI campaign: {len(parsed_emails)} emails generated", GOOD)

        win.bind("<Escape>", lambda e: win.destroy())

    def _open_ai_assist_dialog(self, subject_entry, body_ref):
        """Open the AI Assist dialog for the current email tab."""
        # Ensure we have an API key
        api_key = self._get_openai_key()
        if not api_key:
            api_key = self._prompt_for_api_key()
            if not api_key:
                return

        # Get current email index
        try:
            idx = self.email_notebook.index("current")
        except Exception:
            idx = 0

        if idx >= len(self.body_texts):
            return

        txt_body = self.body_texts[idx]
        current_body = txt_body.get("1.0", "end-1c").strip()
        current_subject = self.subject_vars[idx].get() if idx < len(self.subject_vars) else ""
        email_name = self.name_vars[idx].get() if idx < len(self.name_vars) else f"Email {idx+1}"
        email_position = f"Email {idx+1} of {len(self.body_texts)}"

        # Build sequence context (summaries of other emails)
        seq_parts = []
        for i, sv in enumerate(self.subject_vars):
            if i != idx:
                s = sv.get().strip()
                if s:
                    seq_parts.append(f"Email {i+1}: {s}")
        seq_context = "; ".join(seq_parts) if seq_parts else ""

        # ── Dialog ──
        win = tk.Toplevel(self)
        win.title(f"AI Assist — {email_name}")
        win.geometry("740x680")
        win.configure(bg=BG_CARD)
        win.resizable(True, True)
        win.transient(self)
        win.grab_set()

        # Header
        hdr = tk.Frame(win, bg="#3B82F6", height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="AI Assist  \u2014  Powered by ChatGPT", bg="#3B82F6", fg="#FFFFFF",
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=20, pady=10)

        # Settings gear
        gear_btn = tk.Button(hdr, text="API Key", command=self._prompt_for_api_key,
                             bg="#2563EB", fg="#FFFFFF", relief="flat",
                             font=FONT_SMALL, padx=8, pady=2, cursor="hand2")
        gear_btn.pack(side="right", padx=16, pady=8)

        content = tk.Frame(win, bg=BG_CARD)
        content.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Action selector ──
        tk.Label(content, text="What would you like to do?", bg=BG_CARD, fg=FG_TEXT,
                 font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 8))

        action_var = tk.StringVar(value="write")
        actions_frame = tk.Frame(content, bg=BG_CARD)
        actions_frame.pack(fill="x", pady=(0, 12))

        action_buttons = {}
        for val, label in [("write", "Write New"), ("improve", "Improve"),
                           ("tone", "Change Tone"), ("subject", "Subject Lines")]:
            btn = tk.Button(
                actions_frame, text=label,
                command=lambda v=val: _select_action(v),
                bg=BORDER_SOFT, fg=FG_TEXT, activebackground=BG_HOVER,
                relief="flat", font=FONT_SMALL, padx=12, pady=6, cursor="hand2",
            )
            btn.pack(side="left", padx=(0, 6))
            action_buttons[val] = btn

        def _select_action(action):
            action_var.set(action)
            for k, b in action_buttons.items():
                if k == action:
                    b.config(bg="#3B82F6", fg="#FFFFFF")
                else:
                    b.config(bg=BORDER_SOFT, fg=FG_TEXT)
            # Update prompt placeholder
            placeholders = {
                "write": "Describe the email you want (e.g., 'Cold intro for construction hiring managers about staffing services')",
                "improve": "Optional: specific instructions (e.g., 'Make it shorter' or 'Add more urgency')",
                "tone": "",
                "subject": "AI will generate subject lines based on the current email body.",
            }
            prompt_text.delete("1.0", "end")
            if action == "subject":
                prompt_text.config(state="disabled", bg=GRAY_100)
            else:
                prompt_text.config(state="normal", bg=BG_ENTRY)
            prompt_label.config(text=placeholders.get(action, ""))
            # Show/hide tone selector (pack right after actions_frame)
            if action == "tone":
                tone_frame.pack(fill="x", pady=(0, 8), after=actions_frame)
                prompt_text.config(state="disabled", bg=GRAY_100)
            else:
                tone_frame.pack_forget()

        # ── Tone selector (placed here so it appears between actions and prompt) ──
        tone_frame = tk.Frame(content, bg=BG_CARD)
        # Don't pack yet — shown/hidden by _select_action
        tone_var = tk.StringVar(value="professional")
        tone_buttons = {}
        for tone in ["Professional", "Casual", "Urgent", "Friendly", "Confident", "Empathetic"]:
            tb = tk.Button(
                tone_frame, text=tone,
                command=lambda t=tone.lower(): _select_tone(t),
                bg=BORDER_SOFT, fg=FG_TEXT, relief="flat",
                font=FONT_SMALL, padx=10, pady=4, cursor="hand2",
            )
            tb.pack(side="left", padx=(0, 4))
            tone_buttons[tone.lower()] = tb

        def _select_tone(t):
            tone_var.set(t)
            for k, b in tone_buttons.items():
                b.config(bg=("#7C3AED" if k == t else BORDER_SOFT),
                         fg=("#FFFFFF" if k == t else FG_TEXT))

        _select_tone("professional")

        # ── Prompt input ──
        prompt_label = tk.Label(content, text="", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL,
                                wraplength=650, justify="left")
        prompt_label.pack(anchor="w", pady=(0, 4))

        prompt_text = tk.Text(content, bg=BG_ENTRY, fg=FG_TEXT, font=FONT_BASE,
                              wrap="word", height=3, relief="flat",
                              highlightthickness=1, highlightbackground=BORDER_MEDIUM,
                              highlightcolor=ACCENT, padx=8, pady=6)
        prompt_text.pack(fill="x", pady=(0, 8))

        # ── Generate button + status ──
        gen_row = tk.Frame(content, bg=BG_CARD)
        gen_row.pack(fill="x", pady=(0, 8))

        status_label = tk.Label(gen_row, text="", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL)
        status_label.pack(side="right")

        gen_btn = tk.Button(
            gen_row, text="Generate",
            command=lambda: _generate(),
            bg="#3B82F6", fg="#FFFFFF", activebackground="#2563EB",
            activeforeground="#FFFFFF", relief="flat",
            font=("Segoe UI Semibold", 10), padx=16, pady=6, cursor="hand2",
        )
        gen_btn.pack(side="left")

        # ── Result preview ──
        tk.Label(content, text="Preview", bg=BG_CARD, fg=FG_TEXT,
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(4, 4))

        result_text = tk.Text(content, bg="#FFFFFF", fg=FG_TEXT, font=FONT_BASE,
                              wrap="word", height=10, relief="flat",
                              highlightthickness=1, highlightbackground=BORDER_MEDIUM,
                              padx=10, pady=8)
        result_text.pack(fill="both", expand=True)
        result_text.config(state="disabled")

        # ── Bottom bar (fixed, outside scrollable content) ──
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        bottom = tk.Frame(win, bg=BG_CARD)
        bottom.pack(fill="x", padx=20, pady=12)

        insert_btn = tk.Button(
            bottom, text="Insert into Email",
            command=lambda: _insert_result(),
            bg="#3B82F6", fg="#FFFFFF", activebackground="#2563EB",
            activeforeground="#FFFFFF", disabledforeground="#BFDBFE",
            relief="flat", font=("Segoe UI Semibold", 10),
            padx=16, pady=8, cursor="hand2", state="disabled",
        )
        insert_btn.pack(side="left")

        replace_btn = tk.Button(
            bottom, text="Replace Email Body",
            command=lambda: _replace_result(),
            bg="#7C3AED", fg="#FFFFFF", activebackground="#6D28D9",
            activeforeground="#FFFFFF", disabledforeground="#C4B5FD",
            relief="flat", font=("Segoe UI Semibold", 10),
            padx=16, pady=8, cursor="hand2", state="disabled",
        )
        replace_btn.pack(side="left", padx=(8, 0))

        tk.Button(bottom, text="Close", command=win.destroy,
                  bg=BORDER_SOFT, fg=FG_TEXT, relief="flat",
                  font=FONT_SMALL, padx=14, pady=8, cursor="hand2"
                  ).pack(side="right")

        # Initialize first action
        _select_action("write")

        # ── Handlers ──
        def _generate():
            api_key = self._get_openai_key()
            if not api_key:
                api_key = self._prompt_for_api_key()
                if not api_key:
                    return

            action = action_var.get()
            prompt = prompt_text.get("1.0", "end-1c").strip()

            # Build messages based on action
            ai_ctx = self._load_ai_training()
            if action == "write":
                if not prompt:
                    self.toast.show("Enter a description of the email you want", "error")
                    return
                messages = build_write_email_messages(prompt, email_position, seq_context, custom_context=ai_ctx)
            elif action == "improve":
                if not current_body:
                    self.toast.show("No email body to improve — write something first", "error")
                    return
                messages = build_improve_email_messages(current_body, prompt, custom_context=ai_ctx)
            elif action == "tone":
                if not current_body:
                    self.toast.show("No email body to rewrite — write something first", "error")
                    return
                messages = build_tone_change_messages(current_body, tone_var.get(), custom_context=ai_ctx)
            elif action == "subject":
                body_for_subj = current_body
                if not body_for_subj:
                    # Check if result preview has content
                    result_text.config(state="normal")
                    body_for_subj = result_text.get("1.0", "end-1c").strip()
                    result_text.config(state="disabled")
                if not body_for_subj:
                    self.toast.show("No email body to base subject lines on", "error")
                    return
                messages = build_subject_line_messages(body_for_subj, custom_context=ai_ctx)
            else:
                return

            # Disable button, show loading
            gen_btn.config(state="disabled", text="Generating...")
            status_label.config(text="Calling ChatGPT...", fg="#3B82F6")

            def _on_result(text):
                win.after(0, lambda: _show_result(text))

            def _on_error(err):
                win.after(0, lambda: _show_error(err))

            call_openai_async(api_key, messages, _on_result, _on_error)

        def _show_result(text):
            gen_btn.config(state="normal", text="Generate")
            status_label.config(text="Done!", fg=GOOD)
            result_text.config(state="normal")
            result_text.delete("1.0", "end")
            result_text.insert("1.0", text)
            result_text.config(state="disabled")
            insert_btn.config(state="normal")
            replace_btn.config(state="normal")

        def _show_error(err):
            gen_btn.config(state="normal", text="Generate")
            status_label.config(text=f"Error: {err}", fg=DANGER)

        def _insert_result():
            result_text.config(state="normal")
            text = result_text.get("1.0", "end-1c").strip()
            result_text.config(state="disabled")
            if not text:
                return

            action = action_var.get()
            if action == "subject":
                # Insert first subject line into subject field
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if lines:
                    # Strip numbering
                    first = lines[0]
                    for prefix in ["1.", "1)", "1:"]:
                        if first.startswith(prefix):
                            first = first[len(prefix):].strip()
                    self.subject_vars[idx].set(first)
                    self.toast.show("Subject line inserted", "info")
            else:
                # Append to body
                txt_body.insert("end", "\n\n" + text)
                self.toast.show("AI text inserted into email", "info")
            win.destroy()

        def _replace_result():
            result_text.config(state="normal")
            text = result_text.get("1.0", "end-1c").strip()
            result_text.config(state="disabled")
            if not text:
                return

            action = action_var.get()
            if action == "subject":
                # Same as insert for subject lines
                _insert_result()
                return

            # Replace entire body
            txt_body.delete("1.0", "end")
            txt_body.insert("1.0", text)
            self.toast.show("Email body replaced with AI text", "info")
            win.destroy()

        win.bind("<Escape>", lambda e: win.destroy())

    def _show_email_popup(self, index: int):
        """Show a popup preview of the email at the given index."""
        if index < 0 or index >= len(self.body_texts):
            return

        name = self.name_vars[index].get().strip() if index < len(self.name_vars) else f"Email {index+1}"
        subject = self.subject_vars[index].get().strip() if index < len(self.subject_vars) else ""
        body = self.body_texts[index].get("1.0", "end-1c").strip()
        date_str = self.date_vars[index].get().strip() if index < len(self.date_vars) else ""
        time_str = self.time_vars[index].get().strip() if index < len(self.time_vars) else ""
        attach_n = len(self.per_email_attachments[index]) if index < len(self.per_email_attachments) else 0

        # Format date
        display_date = date_str
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            display_date = dt.strftime("%A, %B %d, %Y")
        except Exception:
            pass

        # Popup window
        popup = tk.Toplevel(self)
        popup.title(f"Preview — {name}")
        popup.geometry("680x560")
        popup.configure(bg=BG_CARD)
        popup.resizable(True, True)
        popup.transient(self)
        popup.grab_set()

        # ── Header bar ──
        header = tk.Frame(popup, bg="#7C3AED", height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=name, bg="#7C3AED", fg="#FFFFFF",
                 font=("Segoe UI Semibold", 14)).pack(side="left", padx=16, pady=10)

        # ── Content area ──
        content = tk.Frame(popup, bg=BG_CARD)
        content.pack(fill="both", expand=True, padx=20, pady=16)

        # Meta info row
        meta = tk.Frame(content, bg=BG_CARD)
        meta.pack(fill="x", pady=(0, 12))

        if display_date or time_str:
            schedule_text = f"{display_date}  at  {time_str}" if display_date and time_str else display_date or time_str
            tk.Label(meta, text=schedule_text, bg=BG_CARD, fg=FG_MUTED,
                     font=("Segoe UI", 10)).pack(side="left")

        if attach_n:
            tk.Label(meta, text=f"{attach_n} attachment(s)", bg=BG_CARD, fg=ACCENT,
                     font=("Segoe UI", 10)).pack(side="right")
        else:
            tk.Label(meta, text="No attachments", bg=BG_CARD, fg=FG_LIGHT,
                     font=("Segoe UI", 10)).pack(side="right")

        # Divider
        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(0, 12))

        # Subject line
        subj_frame = tk.Frame(content, bg=BG_CARD)
        subj_frame.pack(fill="x", pady=(0, 8))
        tk.Label(subj_frame, text="Subject:", bg=BG_CARD, fg=FG_MUTED,
                 font=("Segoe UI Semibold", 10)).pack(side="left")
        tk.Label(subj_frame, text=subject or "(no subject)", bg=BG_CARD,
                 fg=FG_TEXT if subject else FG_LIGHT,
                 font=("Segoe UI", 10)).pack(side="left", padx=(6, 0))

        # Divider
        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(0, 12))

        # Body text (read-only)
        body_frame = tk.Frame(content, bg=BG_CARD)
        body_frame.pack(fill="both", expand=True)

        txt = tk.Text(
            body_frame, bg="#FFFFFF", fg=FG_TEXT, font=("Segoe UI", 10),
            wrap="word", relief="flat", highlightthickness=1,
            highlightbackground=BORDER, padx=12, pady=10,
        )
        txt.pack(fill="both", expand=True)

        # Insert body content with formatting
        try:
            from funnel_forge.html_format import html_to_text_widget as _h2tw
            body_html = text_to_html(self.body_texts[index])
            if body_html:
                _h2tw(txt, body_html)
            else:
                txt.insert("1.0", body)
        except Exception:
            txt.insert("1.0", body)

        # Signature
        sig = self._sig_for_display().strip()
        if sig:
            txt.insert("end", "\n\n")
            txt.insert("end", sig, "sig")
            txt.tag_configure("sig", foreground=FG_MUTED)

        txt.config(state="disabled")

        # ── Bottom bar ──
        bottom = tk.Frame(popup, bg=BG_CARD)
        bottom.pack(fill="x", padx=20, pady=(0, 16))

        # "Go to Email" button
        go_btn = tk.Button(
            bottom, text="Go to Email",
            command=lambda: self._goto_email_and_close(index, popup),
            bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_HOVER,
            activeforeground=FG_WHITE, relief="flat", font=("Segoe UI Semibold", 10),
            padx=16, pady=6, cursor="hand2",
        )
        go_btn.pack(side="left")
        go_btn.bind("<Enter>", lambda e: go_btn.config(bg=ACCENT_HOVER))
        go_btn.bind("<Leave>", lambda e: go_btn.config(bg=ACCENT))

        # Close button
        close_btn = tk.Button(
            bottom, text="Close",
            command=popup.destroy,
            bg=BORDER_SOFT, fg=FG_TEXT, activebackground=BG_HOVER,
            activeforeground=FG_TEXT, relief="flat", font=("Segoe UI", 10),
            padx=16, pady=6, cursor="hand2",
        )
        close_btn.pack(side="right")

        popup.bind("<Escape>", lambda e: popup.destroy())

    def _goto_email_and_close(self, index: int, popup):
        """Navigate to the Build Emails screen at the given tab, then close the popup."""
        popup.destroy()
        self._show_screen("build_emails")
        if hasattr(self, "email_notebook"):
            try:
                tabs = self.email_notebook.tabs()
                real_tabs = [t for t in tabs if not hasattr(self, '_add_tab_frame') or t != str(self._add_tab_frame)]
                if index < len(real_tabs):
                    self.email_notebook.select(real_tabs[index])
            except Exception:
                pass

    def _add_email(self, subject: str = "", body: str = "", date: str = "", time: str = "", name: str = ""):
        idx = len(self.subject_vars) + 1

        name_default = name.strip() if name else f"Email {idx}"
        name_var = tk.StringVar(value=name_default)

        subj_var = tk.StringVar(value=subject)
        _today = datetime.now().strftime("%Y-%m-%d")
        date_var = tk.StringVar(value=date if date else _today)
        time_var = tk.StringVar(value=time if time else "9:00 AM")

        # No need for variable traces - schedule panel uses textvariable for automatic updates

        self.name_vars.append(name_var)
        self.subject_vars.append(subj_var)
        self.date_vars.append(date_var)
        self.time_vars.append(time_var)

        self.per_email_attachments.append([])

        body_widget = self._create_email_tab(idx, name_var, subj_var, body_text=body)
        self.body_texts.append(body_widget)

        # Skip heavy UI refreshes during batch operations (preset apply)
        if getattr(self, "_suspend_rebuilds", False):
            self._ensure_delay_vars_len()
            return

        # Calculate the new email's index (0-based)
        new_email_index = len(self.subject_vars) - 1

        self._rebuild_sequence_table()
        # Incremental update: add only the new row instead of rebuilding entire schedule
        self._schedule_add_row(new_email_index)
        self._refresh_tab_labels()
        # self._set_status("Email added", GOOD)  # Disabled to prevent startup crash

        # Auto-Build Schedule: keep delay_vars in sync and rebuild delay inputs
        self._ensure_delay_vars_len()
        self._rebuild_autobuild_delay_inputs()

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

        # During batch operations, only update data — skip full tab rebuild
        if getattr(self, "_suspend_rebuilds", False):
            # Just remove the tab for this index
            tabs = self.email_notebook.tabs()
            if index < len(tabs):
                self.email_notebook.forget(tabs[index])
            if index < len(self.body_texts):
                del self.body_texts[index]
            self._ensure_delay_vars_len()
            return

        # Remove all tabs from notebook
        self._adding_email = True  # Guard against "+" tab auto-select
        for tab_id in self.email_notebook.tabs():
            self.email_notebook.forget(tab_id)

        # Re-add "+" tab so _create_email_tab can insert before it
        if hasattr(self, "_add_tab_frame"):
            self.email_notebook.add(self._add_tab_frame, text="  +  ")

        # Rebuild all email tabs with re-indexed names (Email 1, Email 2, ...)
        self.body_texts = []
        self.sig_preview_widgets = []
        for i, (name_var, subj_var, body_text) in enumerate(zip(self.name_vars, self.subject_vars, bodies), start=1):
            body_widget = self._create_email_tab(i, name_var, subj_var, body_text=body_text)
            self.body_texts.append(body_widget)

        # Select a valid tab after deletion (exclude "+" tab)
        try:
            tabs = self.email_notebook.tabs()
            real = [t for t in tabs if not hasattr(self, "_add_tab_frame") or t != str(self._add_tab_frame)]
            if real:
                new_index = max(0, min(index, len(real) - 1))
                self.email_notebook.select(real[new_index])
        except:
            pass

        # Update sequence table, schedule panel, and tab labels
        self._rebuild_sequence_table()
        # Incremental update: remove only the deleted row instead of rebuilding entire schedule
        self._schedule_remove_row(index)
        self._refresh_tab_labels()
        self._set_status("Email deleted", WARN)

        # Refresh execute screen checklist (if on that screen)
        if hasattr(self, "_refresh_execute_review_panel"):
            try:
                self._refresh_execute_review_panel()
            except:
                pass

        # Auto-Build Schedule: keep delay_vars in sync and rebuild delay inputs
        self._ensure_delay_vars_len()
        self._rebuild_autobuild_delay_inputs()
        self._adding_email = False

    def _undo_email_editor(self):
        """Undo the last edit in the active email body text widget."""
        # Find the active email tab's body text widget
        if not hasattr(self, "email_notebook") or not self.body_texts:
            return
        try:
            idx = self.email_notebook.index("current")
        except Exception:
            return
        if idx < 0 or idx >= len(self.body_texts):
            return
        try:
            self.body_texts[idx].edit_undo()
        except tk.TclError:
            # Nothing to undo
            self.toast.show("Nothing to undo", "info")

    def _global_undo(self, event=None):
        """Global Ctrl+Z handler. If the focused widget is a Text widget with
        undo support, let it handle Ctrl+Z natively (don't interfere).
        Otherwise, route undo to the active email body editor."""
        focused = self.focus_get()
        if isinstance(focused, tk.Text):
            # Text widget handles Ctrl+Z on its own — do nothing
            return
        # Fall back to undoing the active email body
        self._undo_email_editor()

    def _show_edit_context_menu(self, event):
        """Show a right-click context menu with Cut/Copy/Paste/Undo/Select All."""
        widget = event.widget
        menu = tk.Menu(self, tearoff=0)

        is_text = isinstance(widget, tk.Text)
        is_disabled = False
        try:
            state = str(widget.cget("state"))
            is_disabled = state in ("disabled", "readonly")
        except Exception:
            pass

        has_selection = False
        try:
            if is_text:
                has_selection = bool(widget.tag_ranges("sel"))
            else:
                has_selection = widget.selection_present()
        except Exception:
            pass

        if not is_disabled:
            menu.add_command(label="Cut", accelerator="Ctrl+X",
                             command=lambda: widget.event_generate("<<Cut>>"),
                             state="normal" if has_selection else "disabled")
        menu.add_command(label="Copy", accelerator="Ctrl+C",
                         command=lambda: widget.event_generate("<<Copy>>"),
                         state="normal" if has_selection else "disabled")
        if not is_disabled:
            menu.add_command(label="Paste", accelerator="Ctrl+V",
                             command=lambda: widget.event_generate("<<Paste>>"))
            menu.add_separator()
            menu.add_command(label="Undo", accelerator="Ctrl+Z",
                             command=lambda: widget.edit_undo() if is_text else None)
        menu.add_separator()
        menu.add_command(label="Select All", accelerator="Ctrl+A",
                         command=lambda: self._select_all_widget(widget))

        menu.tk_popup(event.x_root, event.y_root)

    def _select_all(self, event=None):
        """Handle Ctrl+A for Text and Entry widgets."""
        widget = event.widget if event else self.focus_get()
        self._select_all_widget(widget)
        return "break"

    def _select_all_widget(self, widget):
        """Select all text in a widget."""
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
        elif isinstance(widget, (tk.Entry, ttk.Entry)):
            widget.select_range(0, "end")

    def _confirm_delete_active_email(self):
        """Delete the currently active email (called from per-email delete button)"""
        if not hasattr(self, "email_notebook"):
            return

        # Prevent deletion if only 1 email
        if len(self.subject_vars) <= 1:
            return

        try:
            current_tab = self.email_notebook.index(self.email_notebook.select())
            self._delete_email(current_tab)
        except:
            pass

    def _delete_current_email(self):
        """Delete the currently selected email from the control row Delete button"""
        if not hasattr(self, "email_notebook"):
            return

        # Prevent deletion if only 1 email
        if len(self.subject_vars) <= 1:
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

        # Detect "+" tab selection — add a new email instead of switching
        try:
            selected = self.email_notebook.select()
            if hasattr(self, "_add_tab_frame") and selected == str(self._add_tab_frame):
                if not self._adding_email:
                    self._adding_email = True
                    self.after(1, self._handle_plus_tab_click)
                return
        except Exception:
            pass

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

        # ANTI-FLICKER: Debounce date changes to prevent jitter
        self._debounce("_schedule_after_id", 200, self._apply_control_date_change)

    def _apply_control_date_change(self):
        """Apply the date change after debounce delay"""
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

        # ANTI-FLICKER: Debounce time changes to prevent jitter
        self._debounce("_schedule_after_id", 200, self._apply_control_time_change)

    def _apply_control_time_change(self):
        """Apply the time change after debounce delay"""
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
    # Preview test emails (FIXED - NO COM ERRORS)
    # ============================================
    def _validate_preview_send(self):
        """Validate preview send is ready - returns (ok, message)"""
        test_email = (self.test_email_var.get() or "").strip()
        if not test_email:
            return False, "Please enter a test email address."

        if not EMAIL_RE.match(test_email):
            return False, "Invalid email address format."

        if not self.subject_vars or not self.body_texts:
            return False, "No emails available to preview."

        try:
            idx = self.email_notebook.index(self.email_notebook.select())
        except Exception:
            return False, "No email selected."

        if idx < 0 or idx >= len(self.subject_vars):
            return False, "Invalid email selection."

        subject = (self.subject_vars[idx].get() or "").strip()
        body = self.body_texts[idx].get("1.0", "end").strip()

        if not subject:
            return False, "Email subject cannot be empty."
        if not body:
            return False, "Email body cannot be empty."

        return True, ""

    def _get_preview_tokens(self) -> Dict[str, str]:
        """
        Build a token dict for preview merges using the FIRST contact in the active/official contacts CSV.
        Includes common aliases so merge_tokens() has a good chance of matching your placeholders.
        """
        # Fallback tokens (if no contacts exist yet)
        fallback = {
            "FirstName": "Test",
            "LastName": "Contact",
            "Company": "Test Company",
            "JobTitle": "Test Title",
            "Email": "test@example.com",
            "SenderName": "Your Name",
            "SenderEmail": "you@yourcompany.com",
        }

        try:
            contacts_path = ""
            if hasattr(self, "contacts_path_var"):
                contacts_path = (self.contacts_path_var.get() or "").strip()
            if not contacts_path:
                contacts_path = OFFICIAL_CONTACTS_PATH

            if not contacts_path or not os.path.isfile(contacts_path):
                return fallback

            rows, _headers = safe_read_csv_rows(contacts_path)
            if not rows:
                return fallback

            row = rows[0] or {}

            # Canonicalize keys for alias matching
            def canon(k: str) -> str:
                return re.sub(r"[^a-z0-9]", "", (k or "").strip().lower())

            # Build a lookup of canonical_key -> value
            canon_map: Dict[str, str] = {}
            for k, v in row.items():
                ck = canon(str(k))
                if ck and ck not in canon_map:
                    canon_map[ck] = "" if v is None else str(v)

            # Helper to pick a value from several possible column names
            def pick(*keys: str) -> str:
                for k in keys:
                    ck = canon(k)
                    if ck in canon_map and canon_map[ck].strip():
                        return canon_map[ck].strip()
                return ""

            tokens = {
                "FirstName": pick("FirstName", "First Name", "first_name", "firstname", "FName"),
                "LastName": pick("LastName", "Last Name", "last_name", "lastname", "LName"),
                "Company": pick("Company", "company", "Account", "Account Name"),
                "JobTitle": pick("JobTitle", "Job Title", "Title", "job_title"),
                "Email": pick("Email", "email", "E-mail", "Email Address"),
                "SenderName": pick("SenderName", "Sender Name"),
                "SenderEmail": pick("SenderEmail", "Sender Email"),
            }

            # Fill empties with fallback values
            for k, v in fallback.items():
                if not tokens.get(k):
                    tokens[k] = v

            # Add aliases so merge_tokens can match different placeholder styles
            alias_pairs = {
                "First Name": tokens["FirstName"],
                "first_name": tokens["FirstName"],
                "firstname": tokens["FirstName"],
                "Last Name": tokens["LastName"],
                "last_name": tokens["LastName"],
                "lastname": tokens["LastName"],
                "Job Title": tokens["JobTitle"],
                "job_title": tokens["JobTitle"],
                "EmailAddress": tokens["Email"],
                "emailaddress": tokens["Email"],
            }
            tokens.update(alias_pairs)

            return tokens

        except Exception:
            return fallback

    def _send_test_emails(self):
        """Send preview emails for ALL emails in the current sequence with real token merging."""
        test_email = (self.test_email_var.get() or "").strip()
        if not test_email:
            # Try loading from config
            config = load_config()
            test_email = config.get("user_email", "").strip()
            if test_email:
                self.test_email_var.set(test_email)

        if not test_email:
            messagebox.showerror("No Profile",
                                 "Set up your profile first so we know where to send previews.")
            self._show_user_profile_dialog()
            return

        if not HAVE_OUTLOOK:
            messagebox.showerror("Outlook not available", "Outlook is not available on this machine.")
            self._set_status("Outlook missing", DANGER)
            return

        total = len(self.subject_vars)
        if total <= 0:
            messagebox.showinfo("Nothing to send", "No emails found in this campaign.")
            return

        tokens = self._get_preview_tokens()

        sent = 0
        try:
            for i in range(total):
                subject = self.subject_vars[i].get() if i < len(self.subject_vars) else ""
                # Use HTML body if formatting exists, otherwise plain text
                body = ""
                if i < len(self.body_texts):
                    body = text_to_html(self.body_texts[i]) or self.body_texts[i].get("1.0", "end-1c")

                # Ensure signature is included
                body_with_signature = self._ensure_signature_in_body(body)

                # Merge tokens into BOTH subject and body
                merged_subject_core = merge_tokens(subject, tokens)
                merged_body = merge_tokens(body_with_signature, tokens)

                merged_subject = f"[TEST PREVIEW {i+1}/{total}] {merged_subject_core}"

                # Gather per-email attachments
                email_attachments = []
                if i < len(self.per_email_attachments):
                    email_attachments = [fp for fp in self.per_email_attachments[i]
                                         if fp and os.path.isfile(fp)]

                send_preview_email(
                    to_email=test_email,
                    subject=normalize_text(merged_subject),
                    body=merged_body,
                    attachments=email_attachments,
                )
                sent += 1

            messagebox.showinfo("Preview sent", f"Sent {sent}/{total} preview emails to {test_email}")
            self._set_status("Preview emails sent", GOOD)

        except Exception as e:
            self._set_status("Preview failed", DANGER)
            messagebox.showerror(
                "Preview failed",
                f"Sent {sent}/{total} previews, then failed.\n\nError:\n{e}"
            )

    # ============================================
    # Cancel pending (Outbox -> Deleted Items)
    # ============================================
    def _update_cancel_help(self):
        """Update the dynamic help text and placeholder based on Email/Domain mode"""
        mode = self.cancel_mode_var.get()

        if mode == "email":
            self.cancel_help_var.set(
                "Cancel emails for one person\n"
                "Enter a full email address to cancel all pending emails for that contact.\n\n"
                "Example:\n"
                "  john.smith@company.com"
            )
            try:
                if hasattr(self, 'cancel_query_entry'):
                    current = self.cancel_query_entry.get()
                    # Only update placeholder if field is empty or contains the old placeholder
                    if not current or current == "@company.com":
                        self.cancel_query_entry.delete(0, "end")
                        self.cancel_query_entry.insert(0, "john.smith@company.com")
                        self.cancel_query_entry.config(fg=FG_MUTED)
            except Exception:
                pass

        else:  # domain
            self.cancel_help_var.set(
                "Cancel emails for an entire company\n"
                "Enter a domain (starting with @) to cancel all pending emails for that company.\n\n"
                "Example:\n"
                "  @company.com"
            )
            try:
                if hasattr(self, 'cancel_query_entry'):
                    current = self.cancel_query_entry.get()
                    # Only update placeholder if field is empty or contains the old placeholder
                    if not current or current == "john.smith@company.com":
                        self.cancel_query_entry.delete(0, "end")
                        self.cancel_query_entry.insert(0, "@company.com")
                        self.cancel_query_entry.config(fg=FG_MUTED)
            except Exception:
                pass

    def _cancel_pending_emails(self):
        if not HAVE_OUTLOOK:
            messagebox.showerror(
                "Outlook not available",
                "Outlook is not available.\n\nInstall pywin32 and ensure Outlook is installed."
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
            outlook = win32com.client.dynamic.Dispatch("Outlook.Application")  # type: ignore
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
            self.toast.show(f"Cancelled {moved} pending emails (scanned {scanned})", "warning")

            # Track removed emails in matching campaign files
            if moved > 0:
                self._attribute_removed_emails(q, mode, moved)

        except Exception:
            _write_crash_log("cancel_pending")
            self._set_status("Cancel failed", DANGER)
            messagebox.showerror(
                "Cancel failed",
                "Could not cancel pending emails.\n\nA crash log was written to:\n%LOCALAPPDATA%\\Funnel Forge\\logs"
            )

    def _attribute_removed_emails(self, query: str, mode: str, removed_count: int):
        """Attribute cancelled emails to matching campaigns based on contact lists."""
        try:
            campaign_files = list(CAMPAIGNS_DIR.glob("*.json"))
            query_lower = query.lower()

            for camp_file in campaign_files:
                try:
                    with camp_file.open("r", encoding="utf-8") as f:
                        data = json.load(f)

                    if data.get("status") != "active":
                        continue

                    contacts = [e.lower() for e in data.get("contact_emails", [])]
                    if not contacts:
                        continue

                    # Check if any campaign contacts match the cancelled query
                    matched = False
                    if mode == "email":
                        matched = query_lower in contacts
                    elif mode == "domain":
                        matched = any(query_lower in c for c in contacts)

                    if matched:
                        data["emails_removed"] = data.get("emails_removed", 0) + removed_count
                        with camp_file.open("w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)
                except Exception:
                    continue
        except Exception:
            pass  # Don't interrupt cancel flow

    # ============================================
    # Save / Load Config
    # ============================================
    def _collect_config(self):
        emails = []
        for i in range(len(self.subject_vars)):
            subj = self.subject_vars[i].get()
            body = text_to_html(self.body_texts[i]) or self.body_texts[i].get("1.0", "end").rstrip()
            date = self.date_vars[i].get()
            time = self.time_vars[i].get()
            name = self.name_vars[i].get() if i < len(self.name_vars) else f"Email {i+1}"
            per_attach = self.per_email_attachments[i] if i < len(self.per_email_attachments) else []
            delay = self.delay_vars[i].get() if i < len(self.delay_vars) else "2"
            emails.append({
                "name": name,
                "subject": subj,
                "body": body,
                "date": date,
                "time": time,
                "per_attachments": per_attach,
                "delay": delay
            })

        return {
            "emails": emails,
            "test_email": self.test_email_var.get(),
            "schedule_mode": self.schedule_mode_var.get(),
            "relative_start_date": self.relative_start_date_var.get(),
            "relative_window_start": self.relative_window_start_var.get(),
            "relative_window_end": self.relative_window_end_var.get(),
            "relative_skip_weekends": self.relative_skip_weekends_var.get(),
            "send_window_minutes": self.send_window_minutes_var.get(),
            "daily_send_limit": self.daily_send_limit_var.get(),
            "daily_limit_enabled": self.daily_limit_enabled_var.get(),
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
            self.toast.show("Settings and bodies saved", "success")
        except Exception:
            _write_crash_log("gui_save")
            self._set_status("Save failed", DANGER)
            messagebox.showerror("Save Failed", "Could not save. Check logs in:\n%LOCALAPPDATA%\\Funnel Forge\\logs")

    def _init_default_emails(self):
        if self.subject_vars:
            return

        # ANTI-FLICKER: Suspend rebuilds during batch email creation
        # No longer suspend - incremental schedule updates handle rows efficiently now
        # Start from next business day, then 2 business days apart
        base_date = self._next_business_day(datetime.now().date() + timedelta(days=1), skip_weekends=True)
        current_date = base_date

        for i in range(4):
            d = current_date.strftime("%Y-%m-%d")
            self._add_email(name=f"Email {i+1}", subject="", body="", date=d, time="9:00 AM")
            # Next email is 2 business days later
            current_date = self._add_business_days(current_date, 2, skip_weekends=True)

        # Rebuild sequence table only (schedule rows created incrementally by _add_email)
        self._rebuild_sequence_table()

    def _load_from_config_dict(self, cfg: dict):
        self._adding_email = True
        for tab_id in getattr(self, "email_notebook", ttk.Notebook()).tabs():
            try:
                self.email_notebook.forget(tab_id)
            except Exception:
                pass
        # Re-add "+" tab
        if hasattr(self, "_add_tab_frame") and hasattr(self, "email_notebook"):
            self.email_notebook.add(self._add_tab_frame, text="  +  ")
        self._adding_email = False

        self.name_vars = []
        self.subject_vars = []
        self.body_texts = []
        self.sig_preview_widgets = []
        self.date_vars = []
        self.time_vars = []
        self.per_email_attachments = []
        self.delay_vars = []  # Clear delay vars

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

                # Restore delay for this email
                delay_val = e.get("delay", "2")
                delay_var = tk.StringVar(value=str(delay_val))
                self.delay_vars.append(delay_var)

        if "test_email" in cfg:
            self.test_email_var.set(cfg["test_email"])

        # Restore schedule mode settings (default to "fixed" for legacy campaigns)
        if "schedule_mode" in cfg:
            self.schedule_mode_var.set(cfg["schedule_mode"])
        else:
            self.schedule_mode_var.set("fixed")

        if "relative_start_date" in cfg:
            self.relative_start_date_var.set(cfg["relative_start_date"])

        if "relative_window_start" in cfg:
            self.relative_window_start_var.set(cfg["relative_window_start"])

        if "relative_window_end" in cfg:
            self.relative_window_end_var.set(cfg["relative_window_end"])

        if "relative_skip_weekends" in cfg:
            self.relative_skip_weekends_var.set(cfg["relative_skip_weekends"])

        # Deliverability settings
        if "send_window_minutes" in cfg:
            self.send_window_minutes_var.set(cfg["send_window_minutes"])
        if "daily_send_limit" in cfg:
            self.daily_send_limit_var.set(cfg["daily_send_limit"])
        if "daily_limit_enabled" in cfg:
            self.daily_limit_enabled_var.set(cfg["daily_limit_enabled"])

        # Auto-fill any empty dates with 2 business days apart
        self._auto_fill_empty_dates()

        self._rebuild_sequence_table()
        self._refresh_tab_labels()

    def _load_existing_config(self):
        cfg = load_config()
        if not isinstance(cfg, dict):
            cfg = {}
        self._load_from_config_dict(cfg)

    def _force_clean_startup(self):
        """Force clean defaults - ignore any saved config"""
        self._adding_email = True
        # Clear all email tabs
        for tab_id in getattr(self, "email_notebook", ttk.Notebook()).tabs():
            try:
                self.email_notebook.forget(tab_id)
            except Exception:
                pass
        # Re-add "+" tab
        if hasattr(self, "_add_tab_frame") and hasattr(self, "email_notebook"):
            self.email_notebook.add(self._add_tab_frame, text="  +  ")
        self._adding_email = False

        # Reset all email state lists
        self.name_vars = []
        self.subject_vars = []
        self.body_texts = []
        self.sig_preview_widgets = []
        self.date_vars = []
        self.time_vars = []
        self.per_email_attachments = []

        # CRITICAL: Destroy ALL children of schedule_list_frame to remove orphaned rows
        if hasattr(self, "schedule_list_frame"):
            for child in self.schedule_list_frame.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass

        # Clear schedule rows tracking dict
        if hasattr(self, "schedule_rows"):
            self.schedule_rows.clear()

        # Clear schedule list items
        if hasattr(self, "schedule_list_items"):
            self.schedule_list_items.clear()

        # Initialize default emails based on config (default: 5)
        config = load_config()
        default_email_count = config.get("default_email_count", 5)
        now = datetime.now()
        for i in range(default_email_count):
            d = (now + timedelta(days=3 * i)).strftime("%Y-%m-%d")
            self._add_email(name=f"Email {i+1}", subject="", body="", date=d, time="9:00 AM")

        # Reset contact list dropdown — auto-select user's default list if available
        if hasattr(self, 'contact_list_info_var'):
            self.contact_list_info_var.set("")
        if hasattr(self, 'choose_contacts_table'):
            for item in self.choose_contacts_table.get_children():
                self.choose_contacts_table.delete(item)
        self._refresh_contact_dropdown_values()

        default_list = config.get("user_default_list", "")
        if default_list and hasattr(self, 'contact_list_selector_combo'):
            values = list(self.contact_list_selector_combo['values'] or ())
            if default_list in values:
                self.selected_contact_list_var.set(default_list)
                try:
                    self._on_contact_list_selected()
                except Exception:
                    pass
            else:
                self.selected_contact_list_var.set("Choose a list")
        elif hasattr(self, 'selected_contact_list_var'):
            self.selected_contact_list_var.set("Choose a list")

        # Clear template selection
        if hasattr(self, 'template_var'):
            self.template_var.set("None")

        # Set test email from saved profile (or clear if no profile)
        user_email = config.get("user_email", "")
        if hasattr(self, 'test_email_var'):
            self.test_email_var.set(user_email)

        # Rebuild UI
        self._rebuild_sequence_table()
        self._refresh_tab_labels()

        # Safety: Ensure schedule rows match emails exactly (remove any orphaned rows)
        self._sync_schedule_rows_to_emails()

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

    # ------------------------------------------------------------------
    # Daily send-limit batching
    # ------------------------------------------------------------------

    def _apply_daily_limit(self, schedule, contacts_path):
        """Split contacts into batches so no single day exceeds the daily limit.

        Returns a list of (schedule, contacts_path) tuples.  When the daily
        limit is disabled or the contact count fits within the limit, a single
        tuple referencing the original *contacts_path* is returned (no temp
        files created).

        For overflow batches, a temporary CSV is written to the Funnel Forge
        logs directory (auto-cleaned on next launch) with the subset of
        contacts for that batch, and the schedule dates are shifted forward
        by N business days.
        """
        # Bypass if daily limit is disabled
        if not self.daily_limit_enabled_var.get():
            return [(schedule, contacts_path)]

        try:
            daily_limit = max(1, int(self.daily_send_limit_var.get() or "150"))
        except (ValueError, TypeError):
            daily_limit = 150

        # Read contacts
        try:
            rows, headers = safe_read_csv_rows(contacts_path)
        except Exception:
            # If we can't read contacts, fall through to the core which will
            # raise its own clear error.
            return [(schedule, contacts_path)]

        if len(rows) <= daily_limit:
            return [(schedule, contacts_path)]

        # Split rows into chunks of daily_limit
        import tempfile
        batches = []
        batch_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Funnel Forge" / "temp_batches"
        batch_dir.mkdir(parents=True, exist_ok=True)

        for batch_idx in range(0, len(rows), daily_limit):
            chunk = rows[batch_idx : batch_idx + daily_limit]
            batch_num = batch_idx // daily_limit  # 0, 1, 2, ...

            if batch_num == 0:
                # First batch — use original schedule and contacts file
                batches.append((schedule, contacts_path))
            else:
                # Overflow batch — shift every email date by batch_num business days
                shifted = []
                for item in schedule:
                    date_str = item.get("date", "")
                    try:
                        orig_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                        new_date = self._add_business_days(orig_date, batch_num, skip_weekends=True)
                        shifted.append({**item, "date": new_date.strftime("%Y-%m-%d")})
                    except Exception:
                        shifted.append(item)  # keep original if unparseable

                # Write subset CSV
                batch_csv = batch_dir / f"batch_{batch_num}.csv"
                with open(batch_csv, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(chunk)

                batches.append((shifted, str(batch_csv)))

        return batches

    def _run_sequence(self):
        # VALIDATION GUARD: Check if campaign is ready
        validation = self._validate_campaign_ready()
        if not validation["ok"]:
            failed_items = [msg[1] for msg in validation["messages"] if msg[0] == "fail"]
            messagebox.showerror(
                "Checklist Incomplete",
                "Cannot launch campaign. Please fix these issues:\n\n" + "\n".join(failed_items)
            )
            return

        # Get campaign name for UI messaging only (no auto-save)
        campaign_name = ""
        try:
            campaign_name = (self.campaign_name_var.get() or "").strip()
        except Exception:
            campaign_name = ""

        if not campaign_name:
            campaign_name = "Untitled Campaign"

        # FORCE SAVE before nurture validation (ensures UI state is persisted)
        try:
            self._save_all()
        except Exception:
            _write_crash_log("gui_run_save")
            self._set_status("Save failed", DANGER)
            messagebox.showerror("Save Failed", "Could not save. Check logs in:\n%LOCALAPPDATA%\\Funnel Forge\\logs")
            return

        # NURTURE VALIDATION: If nurture is enabled, ensure schedule is set
        # NOTE: Must be AFTER _save_all() so we validate the persisted model
        pending_nurture = self._load_pending_nurture()
        if pending_nurture and pending_nurture.get("enabled"):
            completion_date = self._get_campaign_completion_date()
            if not completion_date:
                messagebox.showerror(
                    "Schedule Required",
                    "Emails must be scheduled before launching with nurture lists enabled.\n\n"
                    "Please set dates and times for all emails in Send Schedule."
                )
                return

        # Use OFFICIAL_CONTACTS_PATH (single source of truth)
        # The active list is copied here by _set_active_contacts()
        contacts_path = OFFICIAL_CONTACTS_PATH

        if not os.path.isfile(contacts_path):
            self._set_status("Contacts missing", DANGER)
            messagebox.showerror(
                "No Active Contact List",
                f"Active contacts file does not exist:\n{contacts_path}\n\n"
                "Please import or select a contact list first."
            )
            return
        if not self.subject_vars:
            self._set_status("No emails", WARN)
            messagebox.showerror("No emails", "You must have at least one email in your sequence.")
            return

        staged_per_email = self._stage_per_email_attachments()

        # Determine schedule mode and compute dates/times accordingly
        mode = self.schedule_mode_var.get()
        computed_schedule = []

        if mode == "relative":
            # Validate relative settings
            try:
                window_start_h, window_start_m = self._parse_hhmm(self.relative_window_start_var.get())
                window_end_h, window_end_m = self._parse_hhmm(self.relative_window_end_var.get())

                # Check that start < end
                if (window_start_h > window_end_h) or (window_start_h == window_end_h and window_start_m >= window_end_m):
                    messagebox.showerror(
                        "Invalid Send Window",
                        "Send window start time must be before end time.\n\nPlease fix this in the Sequence & Attachments screen."
                    )
                    return
            except ValueError as e:
                messagebox.showerror(
                    "Invalid Time Format",
                    f"Send window times must be in 24h HH:MM format (e.g., 08:00).\n\nError: {e}"
                )
                return

            # Validate delays are integers >= 0
            for i in range(len(self.delay_vars)):
                try:
                    delay = int(self.delay_vars[i].get())
                    if delay < 0:
                        raise ValueError("Delay must be >= 0")
                except:
                    messagebox.showerror(
                        "Invalid Delay",
                        f"Email {i+1} has an invalid delay value. Must be an integer >= 0."
                    )
                    return

            # Auto-set start date if empty
            start_date_str = self.relative_start_date_var.get().strip()
            if not start_date_str:
                skip_weekends = self.relative_skip_weekends_var.get()
                start_date = datetime.now().date() + timedelta(days=1)
                if skip_weekends:
                    while self._is_weekend(start_date):
                        start_date = start_date + timedelta(days=1)
                self.relative_start_date_var.set(start_date.strftime("%Y-%m-%d"))

            # Compute relative schedule
            try:
                computed_schedule = self._compute_relative_schedule()
            except Exception as e:
                messagebox.showerror(
                    "Schedule Computation Failed",
                    f"Failed to compute relative schedule:\n\n{e}"
                )
                return

        schedule = []
        for i in range(len(self.subject_vars)):
            label = self.name_vars[i].get().strip() if i < len(self.name_vars) else f"Email {i+1}"
            label = label or f"Email {i+1}"

            subj = self.subject_vars[i].get().strip() or label
            body = text_to_html(self.body_texts[i]) or self.body_texts[i].get("1.0", "end").rstrip()

            # Ensure signature is included in every email
            body_with_signature = self._ensure_signature_in_body(body)

            # Get date and time based on mode
            if mode == "relative":
                # Use computed schedule
                if i < len(computed_schedule):
                    date = computed_schedule[i][0]
                    time = computed_schedule[i][1]
                else:
                    messagebox.showerror("Schedule Error", f"{label} is missing computed schedule.")
                    return
            else:
                # Use fixed schedule from date_vars/time_vars
                date = self.date_vars[i].get().strip()
                time = self.time_vars[i].get().strip()

                if not date or not time:
                    self._set_status("Schedule incomplete", WARN)
                    messagebox.showerror("Missing schedule", f"{label} is missing a date or time.")
                    return

            schedule.append({
                "subject": subj,
                "body": body_with_signature,
                "date": date,
                "time": time,
                "attachments": staged_per_email[i] if i < len(staged_per_email) else [],
            })

        # Prompt for campaign name
        campaign_name = themed_askstring(self, "Name Your Campaign", "Enter a name for this campaign:", campaign_name or "My Campaign")

        if not campaign_name or not campaign_name.strip():
            self._set_status("Run cancelled", WARN)
            return

        campaign_name = campaign_name.strip()

        # Build snapshot summary
        email_count = len(schedule)
        try:
            contact_rows, _ = safe_read_csv_rows(contacts_path)
            contact_count = len(contact_rows)
        except Exception:
            contact_count = 0

        dates = []
        for s in schedule:
            try:
                dates.append(datetime.strptime(s["date"], "%Y-%m-%d").date())
            except Exception:
                pass
        if dates:
            first_date = min(dates)
            last_date = max(dates)
            day_span = (last_date - first_date).days
            date_range = f"{first_date.strftime('%b %d')} \u2014 {last_date.strftime('%b %d')}" if day_span > 0 else first_date.strftime("%b %d, %Y")
        else:
            day_span = 0
            date_range = "Not scheduled"

        total_emails = email_count * contact_count
        span_text = f"over {day_span} days" if day_span > 0 else "same day"

        # Show snapshot confirmation dialog
        run_confirmed = [False]

        dlg = tk.Toplevel(self)
        dlg.title(f"Launch \u2014 {campaign_name}")
        dlg.configure(bg=BG_ROOT)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        body_frame = tk.Frame(dlg, bg=BG_ROOT)
        body_frame.pack(fill="both", expand=True, padx=28, pady=20)

        tk.Label(body_frame, text=campaign_name, bg=BG_ROOT, fg=ACCENT, font=FONT_SECTION).pack(anchor="w", pady=(0, 12))

        summary = f"{email_count} emails to {contact_count} contacts {span_text}"
        tk.Label(body_frame, text=summary, bg=BG_ROOT, fg=FG_TEXT, font=FONT_SECTION_TITLE).pack(anchor="w", pady=(0, 4))

        tk.Label(body_frame, text=f"{date_range}  \u2022  {total_emails} total emails", bg=BG_ROOT, fg=FG_MUTED, font=FONT_BASE).pack(anchor="w", pady=(0, 4))

        # Deliverability info
        try:
            sw_val = int(self.send_window_minutes_var.get() or "90")
        except (ValueError, TypeError):
            sw_val = 90
        deliv_parts = []
        if sw_val > 0:
            deliv_parts.append(f"\u00b1{sw_val} min send window")
        if self.daily_limit_enabled_var.get():
            try:
                dl_val = int(self.daily_send_limit_var.get() or "150")
            except (ValueError, TypeError):
                dl_val = 150
            if contact_count > dl_val:
                import math
                num_batches = math.ceil(contact_count / dl_val)
                deliv_parts.append(f"{dl_val}/day limit (sends across {num_batches} days per step)")
            else:
                deliv_parts.append(f"{dl_val}/day limit")
        if deliv_parts:
            tk.Label(body_frame, text="  \u2022  ".join(deliv_parts),
                     bg=BG_ROOT, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", pady=(0, 4))

        tk.Label(body_frame, text="Outlook Classic must be open to send.", bg=BG_ROOT, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", pady=(0, 16))

        btn_row = tk.Frame(body_frame, bg=BG_ROOT)
        btn_row.pack(fill="x")

        def _do_run():
            run_confirmed[0] = True
            dlg.destroy()

        make_button(btn_row, text="Run", command=_do_run, variant="primary").pack(side="left", padx=(0, 8))
        make_button(btn_row, text="Cancel", command=lambda: dlg.destroy(), variant="ghost").pack(side="left")

        dlg.withdraw()
        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_reqheight()) // 2
        dlg.geometry(f"+{x}+{y}")
        dlg.deiconify()

        self.wait_window(dlg)

        if not run_confirmed[0]:
            self._set_status("Run cancelled", WARN)
            return

        try:
            sw_minutes = max(0, int(self.send_window_minutes_var.get() or "90"))
        except (ValueError, TypeError):
            sw_minutes = 90

        try:
            batches = self._apply_daily_limit(schedule, contacts_path)
            for batch_schedule, batch_contacts_path in batches:
                fourdrip_core.run_4drip(
                    schedule=batch_schedule,
                    contacts_path=batch_contacts_path,
                    attachments_path=None,  # global attachments removed
                    send_emails=True,
                    send_window_minutes=sw_minutes,
                )

            self._set_status(f"{len(schedule)} emails scheduled", GOOD)

            # Save campaign to dashboard as active
            self._save_campaign_to_dashboard(campaign_name, schedule, contacts_path)

            self.toast.show(f"Campaign '{campaign_name}' launched! Hit the phones.", "success")

            # Check for pending nurture list assignment and process it
            self._process_pending_nurture_assignment()

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

        # Refresh dashboard to show the new active campaign
        try:
            if hasattr(self, "refresh_dashboard"):
                self.after(0, self.refresh_dashboard)
        except Exception:
            pass

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
    
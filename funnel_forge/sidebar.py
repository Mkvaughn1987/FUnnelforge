# sidebar.py
# Left navigation sidebar for Funnel Forge

import tkinter as tk
from .styles import (
    BG_SIDEBAR, FG_TEXT, FG_MUTED, BG_ENTRY, FG_WHITE, APP_VERSION, ACCENT,
    PAD_MD, PAD_LG, MARGIN_SM, MARGIN_MD, BG_HOVER
)


def create_sidebar(parent, nav_callback):
    """
    Create the left navigation sidebar.

    Args:
        parent: Parent widget (Frame or Tk)
        nav_callback: Function to call when navigation buttons are clicked.
                     Should accept a single string parameter (the view key).

    Returns:
        tuple: (sidebar_frame, nav_buttons_dict)
            - sidebar_frame: The sidebar Frame widget
            - nav_buttons_dict: Dict mapping view keys to Button widgets
    """
    sidebar = tk.Frame(parent, bg=BG_SIDEBAR, width=250)
    sidebar.pack_propagate(False)

    # Header section with consistent spacing
    tk.Label(
        sidebar,
        text="Funnel Forge",
        bg=BG_SIDEBAR,
        fg=ACCENT,
        font=("Segoe UI Semibold", 14),
    ).pack(anchor="w", padx=PAD_LG, pady=(PAD_MD, 4))

    tk.Label(
        sidebar,
        text="Automated email engine",
        bg=BG_SIDEBAR,
        fg=FG_MUTED,
        font=("Segoe UI", 9),
    ).pack(anchor="w", padx=PAD_LG, pady=(0, PAD_LG))

    nav_buttons = {}

    def _nav_button(text: str, key: str):
        btn = tk.Button(
            sidebar,
            text=text,
            anchor="w",
            command=lambda k=key: nav_callback(k),
            bg=BG_SIDEBAR,
            fg=FG_TEXT,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            padx=PAD_LG,
            pady=MARGIN_MD,
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
            bd=0,
        )
        btn.pack(fill="x", pady=1)
        nav_buttons[key] = btn

    def _sub_nav_button(text: str, key: str):
        btn = tk.Button(
            sidebar,
            text="  • " + text,
            anchor="w",
            command=lambda k=key: nav_callback(k),
            bg=BG_SIDEBAR,
            fg=FG_MUTED,
            activebackground=BG_HOVER,
            activeforeground=FG_TEXT,
            relief="flat",
            padx=24,  # Increased indent for sub-items
            pady=MARGIN_SM,
            cursor="hand2",
            font=("Segoe UI", 10),
            bd=0,
        )
        btn.pack(fill="x", pady=1)
        nav_buttons[key] = btn

    # Dashboard is now first button right after header
    _nav_button("Dashboard", "dashboard")
    _nav_button("Create a campaign", "campaign")
    _sub_nav_button("Build emails", "build")
    _sub_nav_button("Choose contact list", "contacts")
    _sub_nav_button("Set Schedule", "sequence")
    _sub_nav_button("Preview and Launch", "execute")
    _nav_button("Contact Lists", "contact_lists_main")
    _nav_button("Cancel Emails", "cancel_emails")

    # Spacer to push footer to bottom
    tk.Label(sidebar, text="", bg=BG_SIDEBAR).pack(expand=True, fill="y")

    # Footer section
    tk.Label(
        sidebar,
        text=f"Version {APP_VERSION}",
        bg=BG_SIDEBAR,
        fg=FG_MUTED,
        font=("Segoe UI", 8),
    ).pack(anchor="w", padx=PAD_LG, pady=(0, 2))

    tk.Label(
        sidebar,
        text="MV build",
        bg=BG_SIDEBAR,
        fg=FG_MUTED,
        font=("Segoe UI", 8, "italic"),
    ).pack(anchor="w", padx=PAD_LG, pady=(0, PAD_MD))

    return sidebar, nav_buttons

# styles.py
# Shared constants, colors, fonts, and helper functions for Funnel Forge GUI

import os
import re
import csv
import json
import shutil
import getpass
import subprocess
from pathlib import Path
from typing import Optional, Any, Dict, List, Tuple
from tkinter import messagebox

# =========================
# Runtime-safe paths + logging
# =========================
import sys
from datetime import datetime
import traceback

def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


APP_DIR = _app_dir()

try:
    os.chdir(APP_DIR)
except Exception:
    pass


def _user_data_dir() -> Path:
    base = Path(os.getenv("LOCALAPPDATA", str(APP_DIR))) / "Funnel Forge"
    base.mkdir(parents=True, exist_ok=True)
    return base


USER_DIR = _user_data_dir()
LOG_DIR = USER_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _write_crash_log(tag: str = "gui") -> Optional[Path]:
    try:
        log_file = LOG_DIR / f"{tag}_crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_file.write_text(traceback.format_exc(), encoding="utf-8")
        return log_file
    except Exception:
        return None


def resource_path(*parts: str) -> str:
    """
    Absolute path to resources for dev + PyInstaller onedir builds.
    In onedir, resources are next to the EXE in the install folder.
    """
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.abspath(".")
    return os.path.join(base_dir, *parts)


def user_path(*parts: str) -> str:
    return str(USER_DIR.joinpath(*parts))


def ensure_dir(path: str) -> None:
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


# =========================
# Constants
# =========================

APP_NAME = "Funnel Forge"
APP_VERSION = "2.3"

BODY_FILES = ["body1.txt", "body2.txt", "body3.txt", "body4breakup.txt"]

# =====================================================================
# DESIGN SYSTEM - Funnel Forge
# Inspired by Linear, Stripe, Vercel, Notion
# All UI code should reference these tokens, never hardcode hex values.
# =====================================================================

# === NEUTRAL SCALE (Tailwind Slate) ===
# 10-step gray ramp for backgrounds, text, borders, disabled states
GRAY_50  = "#F8FAFC"    # App background, page surface
GRAY_100 = "#F1F5F9"    # Hover backgrounds, inset surfaces, alternating rows
GRAY_200 = "#E2E8F0"    # Borders, dividers, card outlines
GRAY_300 = "#CBD5E1"    # Disabled borders, secondary borders
GRAY_400 = "#94A3B8"    # Placeholder text, disabled text, muted icons
GRAY_500 = "#64748B"    # Secondary text, labels
GRAY_600 = "#475569"    # Icons, form labels
GRAY_700 = "#334155"    # Strong secondary text
GRAY_800 = "#1E293B"    # Primary text, headings
GRAY_900 = "#0F172A"    # Highest contrast text

# === PRIMARY BRAND COLORS ===
PRIMARY_BLUE = "#4E6FD8"     # Main buttons, active tabs, key highlights
SECONDARY_BLUE = "#5FA3F3"   # Hover states, icons, accents
LIGHT_BLUE = "#6FDCE3"       # Subtle gradient start only (use sparingly)

# Primary accent scale (for tinted backgrounds, hover, pressed)
PRIMARY_50  = "#EEF2FF"     # Tinted backgrounds (active sidebar, selected row)
PRIMARY_100 = "#E0E7FF"     # Light hover tint
PRIMARY_200 = "#C7D2FE"     # Borders on active elements
PRIMARY_400 = "#818CF8"     # Hover state for primary buttons
PRIMARY_500 = PRIMARY_BLUE  # Brand blue (primary)
PRIMARY_600 = "#4338CA"     # Pressed state

# === SEMANTIC COLORS (state + background pairs) ===
GOOD = "#10B981"             # Green-500 (success)
DANGER = "#EF4444"           # Red-500 (error)
WARN = "#F59E0B"             # Amber-500 (warning)
INFO = "#3B82F6"             # Blue-500 (info)

SUCCESS_BG = "#ECFDF5"      # Green tint background
SUCCESS_FG = "#059669"       # Green-600 text on tint
DANGER_BG  = "#FEF2F2"      # Red tint background
DANGER_FG  = "#DC2626"       # Red-600 text on tint
WARN_BG    = "#FFFBEB"      # Amber tint background
WARN_FG    = "#D97706"       # Amber-600 text on tint
INFO_BG    = "#EFF6FF"      # Blue tint background
INFO_FG    = "#2563EB"       # Blue-600 text on tint

# === SURFACE HIERARCHY ===
# Use these instead of raw grays for semantic clarity
SURFACE_PAGE   = GRAY_50     # Default page/app background
SURFACE_CARD   = "#FFFFFF"   # Elevated card surfaces
SURFACE_INSET  = GRAY_100    # Recessed areas (inputs, code blocks)
SURFACE_RAISED = "#FFFFFF"   # Modals, dropdowns (white + border)

# Legacy aliases (keep existing code working)
APP_BACKGROUND = GRAY_50
CARD_WHITE = SURFACE_CARD
BORDER_GRAY = GRAY_200

# === BACKGROUNDS ===
BG_ROOT = SURFACE_PAGE       # App background
BG_CARD = SURFACE_CARD       # Cards / sections
BG_SIDEBAR = GRAY_50         # Sidebar background
BG_HEADER = GRAY_900         # Dark top banner
BG_ENTRY = SURFACE_CARD      # Input fields
BG_HOVER = GRAY_100          # Hover state background

# === ACCENT COLORS ===
ACCENT = PRIMARY_500         # Primary brand color
ACCENT_HOVER = SECONDARY_BLUE
ACCENT_LIGHT = PRIMARY_50    # Light tint for selected states
DARK_AQUA = PRIMARY_500      # Legacy alias
DARK_AQUA_HOVER = SECONDARY_BLUE

# === SECONDARY ===
SECONDARY = GRAY_500
SECONDARY_HOVER = GRAY_600

# === TEXT COLORS ===
FG_TEXT = GRAY_800           # Primary text
FG_MUTED = GRAY_500          # Secondary text
FG_LIGHT = GRAY_400          # Muted/placeholder text
FG_WHITE = "#FFFFFF"         # White text on dark backgrounds

# === BORDERS ===
BORDER = GRAY_200            # Default border
BORDER_MEDIUM = GRAY_300     # Stronger border
BORDER_SOFT = GRAY_200       # Soft borders
ACCENT_2 = GRAY_200          # Legacy alias

# === SIDEBAR NAVIGATION STATES ===
NAV_DEFAULT_BG = BG_SIDEBAR
NAV_DEFAULT_FG = GRAY_600
NAV_HOVER_BG   = GRAY_100
NAV_HOVER_FG   = GRAY_800
NAV_ACTIVE_BG  = PRIMARY_50  # Light blue tint
NAV_ACTIVE_FG  = PRIMARY_500 # Blue text
NAV_ACTIVE_BAR = PRIMARY_500 # Left indicator bar
NAV_SUB_FG     = GRAY_500    # Sub-nav default text

# === TYPOGRAPHY ===
# Scale: caption(9) < small(9) < body(10) < subtitle(11) < title(14) < heading(18) < display(24)
FONT_CAPTION       = ("Segoe UI", 8)               # Timestamps, footnotes, version
FONT_SMALL         = ("Segoe UI", 9)                # Badges, secondary info
FONT_BASE          = ("Segoe UI", 10)               # Body text, table cells
FONT_BODY          = ("Segoe UI", 10)               # Alias for FONT_BASE
FONT_BODY_MEDIUM   = ("Segoe UI Semibold", 10)      # Labels, field headers, nav items
FONT_SUBTITLE      = ("Segoe UI Semibold", 11)      # Card titles, section headers
FONT_SECTION       = ("Segoe UI Semibold", 12)      # Section headers, card titles
FONT_TITLE         = ("Segoe UI Semibold", 14)      # Page titles
FONT_HEADING       = ("Segoe UI Bold", 18)          # Large section headings
FONT_DISPLAY       = ("Segoe UI Bold", 24)          # Dashboard KPI numbers

# Button typography
FONT_BUTTON            = ("Segoe UI Semibold", 10)  # Primary buttons
FONT_BUTTON_SECONDARY  = ("Segoe UI", 9)            # Small/secondary buttons
FONT_BTN_SM            = ("Segoe UI Semibold", 9)   # Small buttons
FONT_BTN_LG            = ("Segoe UI Semibold", 11)  # Large action buttons

# Legacy aliases
FONT_LABEL     = FONT_BASE
FONT_FIELD_HDR = FONT_BODY_MEDIUM

# Typography rhythm
BODY_LINE_HEIGHT = 1.5

# === SPACING (4px base grid) ===
SP_1  = 4      # Tight: icon-to-label, inline gaps
SP_2  = 8      # Standard: between siblings, list items
SP_3  = 12     # Comfortable: inside compact cards, form groups
SP_4  = 16     # Normal: container padding, between form groups
SP_5  = 20     # Generous: card internal padding
SP_6  = 24     # Spacious: page margins, section padding
SP_8  = 32     # Major: between page sections
SP_10 = 40     # Hero: page top margin
SP_12 = 48     # Maximum: between unrelated regions

# Legacy spacing aliases
PAD_SM = SP_2           # 8
PAD_MD = SP_3           # 12
PAD_LG = SP_4 + 2      # 18 (kept for compat)
PAD_XL = SP_6           # 24

MARGIN_SM = 6
MARGIN_MD = SP_2 + 2    # 10
MARGIN_LG = SP_4        # 16
MARGIN_XL = SP_8 - 4    # 28

# Card/Panel spacing
CARD_OUTER_PAD = SP_4 + 2     # 18
CARD_INNER_PAD = SP_5          # 20
SECTION_SPACING = SP_8 - 4     # 28
FIELD_SPACING = SP_3            # 12

# Page header spacing
HEADER_TOP_MARGIN = SP_8 - 4   # 28
HEADER_BOTTOM_MARGIN = SP_5    # 20

# Button dimensions
BTN_PAD_X = SP_4               # 16
BTN_PAD_Y = SP_2 + 2           # 10
BTN_SM_PAD_X = SP_3            # 12
BTN_SM_PAD_Y = 7

# Border radius
CARD_RADIUS = 8
BUTTON_RADIUS = 6
TABLE_RADIUS = 0
RADIUS = 6

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Standard contacts fields Funnel Forge uses
CONTACT_FIELDS = ["Email", "FirstName", "LastName", "Company", "JobTitle", "MobilePhone", "WorkPhone"]

# 24-hour time options in 15-minute increments (no business-hour restriction)
TIME_OPTIONS = [
    "12:00 AM", "12:15 AM", "12:30 AM", "12:45 AM",
    "1:00 AM", "1:15 AM", "1:30 AM", "1:45 AM",
    "2:00 AM", "2:15 AM", "2:30 AM", "2:45 AM",
    "3:00 AM", "3:15 AM", "3:30 AM", "3:45 AM",
    "4:00 AM", "4:15 AM", "4:30 AM", "4:45 AM",
    "5:00 AM", "5:15 AM", "5:30 AM", "5:45 AM",
    "6:00 AM", "6:15 AM", "6:30 AM", "6:45 AM",
    "7:00 AM", "7:15 AM", "7:30 AM", "7:45 AM",
    "8:00 AM", "8:15 AM", "8:30 AM", "8:45 AM",
    "9:00 AM", "9:15 AM", "9:30 AM", "9:45 AM",
    "10:00 AM", "10:15 AM", "10:30 AM", "10:45 AM",
    "11:00 AM", "11:15 AM", "11:30 AM", "11:45 AM",
    "12:00 PM", "12:15 PM", "12:30 PM", "12:45 PM",
    "1:00 PM", "1:15 PM", "1:30 PM", "1:45 PM",
    "2:00 PM", "2:15 PM", "2:30 PM", "2:45 PM",
    "3:00 PM", "3:15 PM", "3:30 PM", "3:45 PM",
    "4:00 PM", "4:15 PM", "4:30 PM", "4:45 PM",
    "5:00 PM", "5:15 PM", "5:30 PM", "5:45 PM",
    "6:00 PM", "6:15 PM", "6:30 PM", "6:45 PM",
    "7:00 PM", "7:15 PM", "7:30 PM", "7:45 PM",
    "8:00 PM", "8:15 PM", "8:30 PM", "8:45 PM",
    "9:00 PM", "9:15 PM", "9:30 PM", "9:45 PM",
    "10:00 PM", "10:15 PM", "10:30 PM", "10:45 PM",
    "11:00 PM", "11:15 PM", "11:30 PM", "11:45 PM",
]

CONFIG_PATH = user_path("funnelforge_config.json")

# Templates (local)
TEMPLATES_DIR = user_path("Templates")

# Shared templates (OneDrive)
SHARED_TEMPLATES_ROOT = Path.home() / "Arena Staffing" / "Arena Direct Hire - Documents" / "FunnelForge" / "Templates"
SHARED_TEAM_DIR = SHARED_TEMPLATES_ROOT / "Team"
SHARED_USER_DIR = SHARED_TEMPLATES_ROOT / "Users" / getpass.getuser()

# Shared user registry (OneDrive)
SHARED_REGISTRY_DIR = SHARED_TEMPLATES_ROOT.parent / "Registry"
SHARED_REGISTRY_PATH = SHARED_REGISTRY_DIR / "users_registry.json"

# Shared team config (OneDrive) — stores API keys, team-wide settings
SHARED_CONFIG_DIR = SHARED_TEMPLATES_ROOT.parent / "Config"
SHARED_CONFIG_PATH = SHARED_CONFIG_DIR / "team_config.json"

# Signature file
SIGNATURE_PATH = user_path("signature.txt")

# Contacts (official single source of truth)
CONTACTS_DIR = user_path("Contacts")
OFFICIAL_CONTACTS_PATH = os.path.join(CONTACTS_DIR, "contacts.csv")
CAMPAIGNS_DIR = USER_DIR / "Campaigns"
CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)

# Segments storage
SEGMENTS_DIR = user_path("Segments")

# Config keys
CFG_KEY_HIDE_CONTACTS_IMPORT_POPUP = "hide_contacts_import_popup"

# -----------------------
# Helpers
# -----------------------

def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(config: dict) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        messagebox.showerror("Error", f"Could not save config:\n{e}")


def load_user_registry() -> dict:
    """Read the shared user registry. Returns {"users": {...}} or empty dict."""
    try:
        if not SHARED_REGISTRY_PATH.exists():
            return {"users": {}}
        with open(SHARED_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "users" in data:
            return data
        return {"users": {}}
    except Exception:
        return {"users": {}}


def save_user_registry(data: dict) -> bool:
    """Write the user registry. Returns True on success."""
    try:
        SHARED_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        with open(SHARED_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def register_user(username: str, full_name: str, email: str,
                  title: str = "", company: str = "",
                  app_version: str = "") -> bool:
    """Add a new user to the shared registry. Returns True on success."""
    registry = load_user_registry()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    registry["users"][username] = {
        "username": username,
        "full_name": full_name,
        "email": email,
        "title": title,
        "company": company,
        "machine_user": getpass.getuser(),
        "registered_at": now,
        "last_active": now,
        "app_version": app_version,
    }
    return save_user_registry(registry)


def update_user_activity(username: str, app_version: str = "") -> None:
    """Update last_active timestamp for a user in the shared registry."""
    try:
        registry = load_user_registry()
        if username in registry["users"]:
            registry["users"][username]["last_active"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if app_version:
                registry["users"][username]["app_version"] = app_version
            save_user_registry(registry)
    except Exception:
        pass  # Non-critical — don't block app startup


def is_admin(identifier: str) -> bool:
    """Check if the given username or email is in the admins list.

    Matches against the admins list directly (usernames) and also checks
    if the identifier is an email belonging to an admin user.
    """
    if not identifier:
        return False
    registry = load_user_registry()
    admins = registry.get("admins", [])
    # Direct username match
    if identifier in admins:
        return True
    # Email match: check if any admin user has this email
    if "@" in identifier:
        users = registry.get("users", {})
        for admin_name in admins:
            user_data = users.get(admin_name, {})
            if user_data.get("email", "").lower() == identifier.lower():
                return True
    return False


def set_admin(username: str, is_admin_flag: bool) -> bool:
    """Add or remove a username from the admins list. Returns True on success."""
    registry = load_user_registry()
    admins = registry.get("admins", [])
    if is_admin_flag and username not in admins:
        admins.append(username)
    elif not is_admin_flag and username in admins:
        admins.remove(username)
    registry["admins"] = admins
    return save_user_registry(registry)


def safe_read_csv_rows(path: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Read a CSV and return:
      - rows: list of dicts with ONLY string keys (no None keys) and string values
      - headers: list of header strings (no None)
    This cleans up the `None` header/keys that DictReader can produce when
    there are extra columns.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        raw_headers = reader.fieldnames or []
        headers: List[str] = [str(h) for h in raw_headers if h is not None]

        rows: List[Dict[str, str]] = []
        for raw_row in reader:
            clean_row: Dict[str, str] = {}
            for k, v in raw_row.items():
                if k is None:
                    continue
                clean_row[str(k)] = "" if v is None else str(v)
            rows.append(clean_row)

    return rows, headers


# -----------------------
# Factory Reset & First-Run Setup
# -----------------------

def get_default_config() -> dict:
    """Return clean default configuration for first run"""
    return {
        "default_email_count": 5,
        "last_opened_page": "dashboard",
        "last_selected_template_id": "default-outreach-5-step",
        "hide_contacts_import_popup": False,
        "active_contacts_file": OFFICIAL_CONTACTS_PATH,
        "wizard_completed": False
    }


def get_default_template() -> dict:
    """Return the default 5-email template (permanent built-in system template)"""
    return {
        "name": "Default 5 Email Campaign",
        "is_system_template": True,
        "system_template_id": "default-5-email-campaign",
        "emails": [
            {
                "index": 1,
                "name": "Intro",
                "subject": "Quick intro — {Company}",
                "body": "Hi {FirstName},\n\nI came across your work at {Company} and wanted to reach out.\n\nI specialize in helping teams hire in construction and mission-critical environments, and I thought it might make sense to connect.\n\nIf you're open to it, I'd love to ask a couple quick questions and see where you're headed this year.\n\nBest,\n{SenderName}"
            },
            {
                "index": 2,
                "name": "Follow-up",
                "subject": "Following up — {Company}",
                "body": "Hi {FirstName},\n\nJust wanted to follow up on my note below in case it got buried.\n\nHappy to share how we're helping similar teams, or simply connect for future planning.\n\nLet me know what makes sense.\n\nBest,\n{SenderName}"
            },
            {
                "index": 3,
                "name": "Per my VM",
                "subject": "Per my voicemail",
                "body": "Hi {FirstName},\n\nI left you a quick voicemail earlier and wanted to follow up here as well.\n\nNo rush at all—just wanted to briefly introduce myself and see if it makes sense to connect.\n\nBest,\n{SenderName}"
            },
            {
                "index": 4,
                "name": "Value Add",
                "subject": "Quick question — {Company}",
                "body": "Hi {FirstName},\n\nOne quick question I often ask leaders at {Company}:\n\nWhat's been the hardest role to fill over the past year?\n\nEven if now isn't the right time, the answer helps me stay aligned with what teams are actually facing.\n\nBest,\n{SenderName}"
            },
            {
                "index": 5,
                "name": "Close the Loop",
                "subject": "Should I close the loop?",
                "body": "Hi {FirstName},\n\nI haven't heard back, so I'll assume now isn't the right time.\n\nIf priorities change or you'd like to reconnect down the road, feel free to reach out anytime.\n\nEither way, wishing you continued success at {Company}.\n\nBest,\n{SenderName}"
            }
        ]
    }


def ensure_default_contact_list():
    """Create a default contact list so the Choose Contacts page isn't empty on first run."""
    contacts_path = Path(CONTACTS_DIR)
    contacts_path.mkdir(parents=True, exist_ok=True)

    # Only create if no CSV lists exist yet (ignore contacts.csv master file)
    existing = [f for f in contacts_path.glob("*.csv") if f.name != "contacts.csv"]
    if existing:
        return

    default_file = contacts_path / "My First List.csv"
    try:
        with open(default_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CONTACT_FIELDS)
            writer.writeheader()
            writer.writerow({
                "Email": "yourname@example.com",
                "FirstName": "You",
                "LastName": "Are",
                "Company": "Loved",
                "JobTitle": "",
                "MobilePhone": "",
                "WorkPhone": "",
            })
    except Exception as e:
        print(f"Warning: Could not create default contact list: {e}")


def migrate_saved_campaigns_to_templates():
    """Migrate old saved campaigns to templates on upgrade to v2.2+.

    Scans CAMPAIGNS_DIR/saved/ for campaign JSON files, converts each to
    template format, and writes to TEMPLATES_DIR. Renames the saved folder
    to saved_migrated so migration only runs once.
    """
    saved_dir = CAMPAIGNS_DIR / "saved"
    if not saved_dir.exists() or not saved_dir.is_dir():
        return  # Nothing to migrate

    campaign_files = list(saved_dir.glob("*.json"))
    if not campaign_files:
        return

    templates_path = Path(TEMPLATES_DIR)
    templates_path.mkdir(parents=True, exist_ok=True)
    migrated = 0

    for f in campaign_files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            # Skip system campaigns
            if data.get("is_system_campaign") or data.get("system_campaign_id"):
                continue

            name = data.get("campaign_name") or data.get("name") or f.stem
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', name).strip()
            if not safe_name:
                continue

            dest = templates_path / f"{safe_name}.json"
            if dest.exists():
                continue  # Don't overwrite existing templates

            # Convert campaign emails to template config format
            campaign_emails = data.get("emails") or []
            delay_pattern = data.get("delay_pattern") or []
            schedule = data.get("schedule_settings") or {}

            config_emails = []
            for i, em in enumerate(campaign_emails):
                delay = str(delay_pattern[i]) if i < len(delay_pattern) else ("0" if i == 0 else "2")
                config_emails.append({
                    "name": em.get("name", f"Email {i+1}"),
                    "subject": em.get("subject", ""),
                    "body": em.get("body", ""),
                    "date": em.get("date", ""),
                    "time": em.get("time", ""),
                    "per_attachments": em.get("attachments") or em.get("per_attachments") or [],
                    "delay": delay,
                })

            template_payload = {
                "template_name": safe_name,
                "saved_at": data.get("saved_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                "migrated_from_campaign": True,
                "config": {
                    "emails": config_emails,
                    "test_email": "",
                    "schedule_mode": schedule.get("schedule_mode", "fixed"),
                    "relative_start_date": "",
                    "relative_window_start": schedule.get("send_time", "09:00"),
                    "relative_window_end": "17:00",
                    "relative_skip_weekends": schedule.get("skip_weekends", True),
                },
            }

            with open(dest, "w", encoding="utf-8") as fh:
                json.dump(template_payload, fh, indent=2, ensure_ascii=False)
            migrated += 1

        except Exception:
            continue

    # Rename saved folder so migration only runs once
    if migrated > 0 or campaign_files:
        try:
            migrated_dir = CAMPAIGNS_DIR / "saved_migrated"
            if migrated_dir.exists():
                # Merge: just move individual files
                for f in campaign_files:
                    try:
                        f.rename(migrated_dir / f.name)
                    except Exception:
                        pass
                try:
                    saved_dir.rmdir()
                except Exception:
                    pass
            else:
                saved_dir.rename(migrated_dir)
        except Exception:
            pass

    if migrated > 0:
        print(f"Migrated {migrated} saved campaign(s) to templates.")


def ensure_first_run_setup():
    """
    Ensure clean folder structure and default data exist.
    Called on app startup if config doesn't exist.
    """
    # Create folder structure
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    Path(CONTACTS_DIR).mkdir(parents=True, exist_ok=True)
    Path(TEMPLATES_DIR).mkdir(parents=True, exist_ok=True)
    Path(SEGMENTS_DIR).mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Write default config if it doesn't exist
    if not os.path.exists(CONFIG_PATH):
        save_config(get_default_config())

    # Migrate old saved campaigns to templates (v2.2 upgrade)
    migrate_saved_campaigns_to_templates()

    # Create default contact list if no lists exist
    ensure_default_contact_list()

    # Create default template if no templates exist
    ensure_default_template()


def ensure_default_template():
    """
    ALWAYS ensure the default template exists (permanent built-in system template).
    Recreates it if missing, even after deletion.
    Prevents duplicates by checking for system_template_id.
    """
    templates_path = Path(TEMPLATES_DIR)
    templates_path.mkdir(parents=True, exist_ok=True)

    # Check if the default template already exists
    default_exists = False
    for template_file in templates_path.glob("*.json"):
        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("system_template_id") == "default-5-email-campaign":
                    default_exists = True
                    break
        except Exception:
            continue

    if default_exists:
        return  # Default template already exists

    # Create default template
    default_template = get_default_template()
    template_file = templates_path / "Default 5 Email Campaign.json"

    try:
        with open(template_file, 'w', encoding='utf-8') as f:
            json.dump(default_template, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not create default template: {e}")


def ensure_default_campaign_exists():
    """
    ALWAYS ensure the default system campaign exists with correct version.
    This is an auto-saved campaign that loads on startup.
    Recreates it if missing, even after deletion.
    Overwrites if version is outdated or missing.
    """
    campaigns_path = Path(CAMPAIGNS_DIR)
    campaigns_path.mkdir(parents=True, exist_ok=True)

    CURRENT_VERSION = "arena-default-7-v1"
    campaign_file_path = None
    needs_update = True

    # Check if the default campaign already exists with correct version
    for campaign_file in campaigns_path.glob("*.json"):
        try:
            with open(campaign_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("system_campaign_id") == "default-7-email-campaign":
                    campaign_file_path = campaign_file
                    # Check version
                    if data.get("system_default_version") == CURRENT_VERSION:
                        needs_update = False
                    break
        except Exception:
            continue

    if not needs_update:
        return  # Default campaign exists with correct version

    # Create/update default campaign
    default_campaign = {
        "name": "Default 7 Email Campaign",
        "is_system_campaign": True,
        "system_campaign_id": "default-7-email-campaign",
        "system_default_version": CURRENT_VERSION,
        "test_email": "",
        "emails": [
            {
                "name": "Introduction",
                "subject": "Quick introduction",
                "body": "Hi {FirstName},\n\nI wanted to take a moment to introduce myself and briefly connect. I work closely with construction teams across the country, supporting hiring needs across project management, field leadership, and technical roles.\n\nI spend most of my time partnering with teams that are scaling, navigating tight labor markets, or simply want access to better talent without wasting time.\n\nIf it makes sense, I'd be happy to learn more about what you're working on and see if there's any way I can be a helpful resource.",
                "date": "",
                "time": "9:00 AM",
                "attachments": []
            },
            {
                "name": "Follow Up",
                "subject": "Following up",
                "body": "Hi {FirstName},\n\nI just wanted to follow up on my previous note and see if this is a good time to connect.\n\nI'm regularly speaking with construction professionals who are open to new opportunities or available for upcoming projects, and I often help teams get ahead of hiring needs before they become urgent.\n\nLet me know if you're open to a brief conversation, or if there's a better time to reconnect down the road.",
                "date": "",
                "time": "9:00 AM",
                "attachments": []
            },
            {
                "name": "Value Add",
                "subject": "A quick thought",
                "body": "Hi {FirstName},\n\nOne thing I'm seeing consistently across construction teams is how competitive the market has become for experienced project and field leaders.\n\nMany of the groups I work with use external support simply to stay proactive and avoid last-minute scrambles when projects ramp up.\n\nIf hiring is on your radar at all this year, I'm happy to share what I'm seeing in the market or provide insight on available talent.",
                "date": "",
                "time": "9:00 AM",
                "attachments": []
            },
            {
                "name": "Per My Voicemail",
                "subject": "Per my voicemail",
                "body": "Hi {FirstName},\n\nI recently left you a brief voicemail and wanted to follow up here as well in case email is easier.\n\nI work closely with construction teams supporting project delivery roles across a wide range of scopes and regions. My goal is simply to be a resource when staffing needs come up.\n\nIf you're open to a quick conversation, I'd be glad to connect. If not, no worries at all.",
                "date": "",
                "time": "9:00 AM",
                "attachments": []
            },
            {
                "name": "Alignment",
                "subject": "Alignment",
                "body": "Hi {FirstName},\n\nI wanted to reach out again to see if there's any alignment between what your team is focused on and the type of work I support.\n\nI tend to work best with teams that value speed, accuracy, and candidates who understand construction environments from day one.\n\nIf it makes sense to explore a conversation, I'm happy to connect. If not, I appreciate you taking the time to read this.",
                "date": "",
                "time": "9:00 AM",
                "attachments": []
            },
            {
                "name": "Check In",
                "subject": "Just checking in",
                "body": "Hi {FirstName},\n\nI know inboxes can get busy, so I wanted to check in once more.\n\nEven if hiring isn't an immediate priority, I'm always glad to stay connected and be a resource when needs arise.\n\nLet me know if a brief intro call would be helpful, or if there's a better time to reconnect.",
                "date": "",
                "time": "9:00 AM",
                "attachments": []
            },
            {
                "name": "Close the Loop",
                "subject": "Closing the loop",
                "body": "Hi {FirstName},\n\nI wanted to close the loop so I'm not continuing to reach out unnecessarily. I'll assume now isn't the right time.\n\nIf priorities shift or you need support down the road, I'd be happy to reconnect and assist where I can.\n\nWishing you continued success with your projects.",
                "date": "",
                "time": "9:00 AM",
                "attachments": []
            }
        ]
    }

    # Determine file path (reuse existing or create new)
    if campaign_file_path is None:
        campaign_file_path = campaigns_path / "Default 7 Email Campaign.json"

    try:
        with open(campaign_file_path, 'w', encoding='utf-8') as f:
            json.dump(default_campaign, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not create/update default campaign: {e}")


def reset_app_data():
    """
    Factory reset: Delete all user data and recreate clean state.

    WARNING: This permanently deletes:
    - All campaigns
    - All contact lists
    - All templates
    - All segments
    - Cache and logs
    - Config file

    Does NOT touch:
    - Application code
    - Outlook data
    - Executables
    """
    try:
        # Delete all user data
        if CAMPAIGNS_DIR.exists():
            shutil.rmtree(CAMPAIGNS_DIR)

        contacts_path = Path(CONTACTS_DIR)
        if contacts_path.exists():
            shutil.rmtree(contacts_path)

        templates_path = Path(TEMPLATES_DIR)
        if templates_path.exists():
            shutil.rmtree(templates_path)

        segments_path = Path(SEGMENTS_DIR)
        if segments_path.exists():
            shutil.rmtree(segments_path)

        # Clear logs (but keep directory)
        if LOG_DIR.exists():
            for log_file in LOG_DIR.glob("*"):
                if log_file.is_file():
                    log_file.unlink()

        # Delete config
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)

        # Recreate clean structure
        ensure_first_run_setup()

        # Recreate default system campaign
        ensure_default_campaign_exists()

        return True
    except Exception as e:
        print(f"Reset failed: {e}")
        return False


def merge_tokens(template: str, tokens: dict) -> str:
    out = template
    for k, v in tokens.items():
        out = out.replace("{" + k + "}", str(v) if v is not None else "")
    return out


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    replacements = {
        """: '"', """: '"',
        "'": "'", "'": "'",
        "—": "-", "–": "-",
    }
    for src, tgt in replacements.items():
        text = text.replace(src, tgt)
    return "".join(ch for ch in text if ord(ch) <= 127)


def _open_folder_in_explorer(folder_path: str) -> None:
    try:
        if os.name == "nt":
            os.startfile(folder_path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open", folder_path])
    except Exception as e:
        messagebox.showerror("Error", f"Could not open folder:\n{e}")


def _open_file_location(file_path: str) -> None:
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(file_path)])
        else:
            folder = os.path.dirname(file_path)
            subprocess.Popen(["open", folder])
    except Exception:
        try:
            folder = os.path.dirname(file_path)
            _open_folder_in_explorer(folder)
        except Exception:
            pass


# -----------------------
# Header auto-detect / mapping
# -----------------------

def _norm_header(h: str) -> str:
    h = (h or "").strip().lower()
    h = re.sub(r"[\s\-_]+", " ", h)
    return h


def _pick_first_nonempty(row: Dict[str, Any], keys: List[str]) -> str:
    for k in keys:
        if k in row and row[k] is not None and str(row[k]).strip():
            return str(row[k]).strip()
    return ""


def detect_and_convert_contacts_to_official(src_csv: str, dest_csv: str) -> Tuple[int, List[str]]:
    """
    Reads src_csv with arbitrary headers (ZoomInfo-style etc),
    detects likely columns, writes standardized CONTACT_FIELDS to dest_csv.
    Returns (count_written, warnings).
    """
    warnings: List[str] = []
    rows, headers = safe_read_csv_rows(src_csv)
    if not rows:
        ensure_dir(os.path.dirname(dest_csv))
        with open(dest_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CONTACT_FIELDS)
            w.writeheader()
        return 0, ["No rows found in the imported CSV."]

    norm_map: Dict[str, str] = {}
    for h in headers:
        norm_map[_norm_header(h)] = h

    email_candidates = [
        "work email", "business email", "email", "email address", "e mail", "e-mail",
        "personal email"
    ]
    first_candidates = ["first name", "firstname", "first"]
    last_candidates = ["last name", "lastname", "last"]
    company_candidates = ["company", "company name", "account name", "organization", "org", "employer"]
    title_candidates = ["job title", "title", "position", "role"]
    mobile_candidates = ["mobile phone", "mobile", "cell phone", "cell", "personal phone", "mobile number", "cell number"]
    work_phone_candidates = ["work phone", "phone", "business phone", "office phone", "direct phone", "work number", "phone number", "direct dial"]

    def _find_header(cands: List[str]) -> Optional[str]:
        for c in cands:
            key = _norm_header(c)
            if key in norm_map:
                return norm_map[key]
        all_norm = list(norm_map.keys())
        for c in cands:
            c_norm = _norm_header(c)
            for h_norm in all_norm:
                if c_norm and c_norm in h_norm:
                    return norm_map[h_norm]
        return None

    h_email = _find_header(email_candidates)
    h_first = _find_header(first_candidates)
    h_last = _find_header(last_candidates)
    h_company = _find_header(company_candidates)
    h_title = _find_header(title_candidates)
    h_mobile = _find_header(mobile_candidates)
    h_work_phone = _find_header(work_phone_candidates)

    if h_email is None:
        for h in headers:
            if "email" in _norm_header(h):
                h_email = h
                break

    if h_email is None:
        warnings.append("Could not detect an Email column. Import still created the file, but Email will be blank.")
    if h_first is None:
        warnings.append("Could not detect FirstName (okay).")
    if h_last is None:
        warnings.append("Could not detect LastName (okay).")
    if h_company is None:
        warnings.append("Could not detect Company (okay).")
    if h_title is None:
        warnings.append("Could not detect JobTitle (okay).")

    ensure_dir(os.path.dirname(dest_csv))
    written = 0

    with open(dest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CONTACT_FIELDS)
        writer.writeheader()

        for r in rows:
            email_val = ""
            if h_email:
                email_val = (r.get(h_email, "") or "").strip()

            if not email_val:
                email_val = _pick_first_nonempty(
                    r,
                    [norm_map.get("work email", ""), norm_map.get("personal email", ""), norm_map.get("email", "")]
                )

            if email_val and not EMAIL_RE.match(email_val):
                continue

            out_row = {
                "Email": email_val,
                "FirstName": (r.get(h_first, "") if h_first else "").strip(),
                "LastName": (r.get(h_last, "") if h_last else "").strip(),
                "Company": (r.get(h_company, "") if h_company else "").strip(),
                "JobTitle": (r.get(h_title, "") if h_title else "").strip(),
                "MobilePhone": (r.get(h_mobile, "") if h_mobile else "").strip(),
                "WorkPhone": (r.get(h_work_phone, "") if h_work_phone else "").strip(),
            }

            writer.writerow(out_row)
            written += 1

    return written, warnings

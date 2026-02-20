"""
funnelforge_core.py

Core logic for Funnel Forge:
- Reads contacts from CSV
- Builds and schedules Outlook emails based on a sequence
- Handles explicit dates + times (from GUI)
- Also supports older offset_days/days schedules (backward compatible)
- Accepts either 'Work Email' OR 'Email' in the contacts CSV
- Logs crashes to %LOCALAPPDATA%\\Funnel Forge\\logs

IMPORTANT:
- Uses LOCAL MACHINE TIME ONLY for scheduling.
- Exposes both run_funnelforge(...) and run_4drip(...) for GUI compatibility.
"""

import csv
import os
import random
import re
import shutil
import sys
import tempfile
import time as _time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------
# Outlook COM
# ---------------------------
try:
    import pythoncom  # type: ignore
    import pywintypes  # type: ignore  # For COM-compatible datetime
    import win32com.client  # type: ignore
    from win32com.client import gencache
    HAVE_OUTLOOK = True
except ImportError:
    pythoncom = None
    pywintypes = None
    win32com = None
    gencache = None
    HAVE_OUTLOOK = False


# ---------------------------
# Configuration
# ---------------------------

# Enable automatic timezone compensation for Outlook deferred delivery.
# When True, the app will detect if Outlook shifts the deferred time (e.g., by 7 hours)
# and automatically compensate so the final stored time matches user intent.
# Set to False if your Outlook/Exchange does not exhibit this behavior.
ENABLE_OUTLOOK_TIME_COMPENSATION = True


# ---------------------------
# Outlook helper (gen_py cache recovery)
# ---------------------------

def _clear_gen_py_cache():
    try:
        gen_py = os.path.join(tempfile.gettempdir(), "gen_py")
        if os.path.isdir(gen_py):
            shutil.rmtree(gen_py, ignore_errors=True)
    except Exception:
        pass

def get_outlook_app():
    try:
        return win32com.client.Dispatch("Outlook.Application")
    except AttributeError:
        # Recover from corrupted gen_py cache (CLSIDToClassMap error)
        _clear_gen_py_cache()
        try:
            gencache.is_readonly = False
            gencache.Rebuild()
        except Exception:
            pass
        # Retry once
        return win32com.client.Dispatch("Outlook.Application")


def _is_outlook_offline(outlook) -> bool:
    """Check if Outlook is in offline mode. Returns True if offline."""
    try:
        # Check if the default store is offline
        namespace = outlook.GetNamespace("MAPI")
        # ExchangeConnectionMode: 0 = disconnected/offline
        # We check if we can access the Inbox as a proxy for connectivity
        if hasattr(namespace, "Offline"):
            return namespace.Offline
        return False
    except Exception:
        return False  # Assume online if we can't detect


def _set_sending_account(outlook, mail, target_smtp: Optional[str] = None):
    """
    Force the sending account on a MailItem.

    In multi-account Outlook profiles, Send() can succeed but the item may not
    be submitted reliably without explicitly binding to an account.

    Args:
        outlook: Outlook.Application COM object
        mail: MailItem to configure
        target_smtp: Optional specific SMTP address to use

    Returns:
        The chosen Account object, or None if no account found
    """
    try:
        session = outlook.Session
        accounts = session.Accounts
        chosen = None

        # Prefer exact SMTP match if provided
        if target_smtp:
            target_smtp_lower = target_smtp.lower()
            for i in range(1, accounts.Count + 1):
                acct = accounts.Item(i)
                try:
                    if acct.SmtpAddress and acct.SmtpAddress.lower() == target_smtp_lower:
                        chosen = acct
                        break
                except Exception:
                    continue

        # Fallback: first account in the session
        if chosen is None and accounts.Count > 0:
            chosen = accounts.Item(1)

        if chosen is not None:
            mail.SendUsingAccount = chosen
            return chosen

    except Exception:
        pass  # Best effort; don't fail the send

    return None


# ---------------------------
# Paths & logging
# ---------------------------


def _app_dir() -> Path:
    """Return the directory where the app is running from (handles frozen EXE)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


APP_DIR = _app_dir()
LOG_DIR = Path(os.getenv("LOCALAPPDATA", str(APP_DIR))) / "Funnel Forge" / "logs"


def _ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def log_exception() -> Path:
    """
    Write the current exception traceback to a timestamped log file
    and return its path.
    """
    _ensure_log_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"core_crash_{ts}.log"
    with log_path.open("w", encoding="utf-8") as f:
        traceback.print_exc(file=f)
    return log_path


# ---------------------------
# Email scheduling diagnostic log
# ---------------------------

_EMAIL_LOG_PATH: Optional[Path] = None


def _init_email_log() -> Path:
    """Initialize a new email scheduling log file for this session."""
    global _EMAIL_LOG_PATH
    _ensure_log_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _EMAIL_LOG_PATH = LOG_DIR / f"email_schedule_{ts}.log"

    # Write header
    with _EMAIL_LOG_PATH.open("w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"Funnel Forge Email Scheduling Log\n")
        f.write(f"Session started: {datetime.now().isoformat()}\n")
        f.write(f"System timezone offset: UTC{_get_local_tz_offset()}\n")
        f.write("=" * 80 + "\n\n")

    return _EMAIL_LOG_PATH


def _get_local_tz_offset() -> str:
    """Get local timezone offset as string like '+05:00' or '-07:00'."""
    import time
    offset_seconds = -time.timezone if time.daylight == 0 else -time.altzone
    offset_hours = offset_seconds // 3600
    offset_minutes = abs(offset_seconds % 3600) // 60
    sign = "+" if offset_hours >= 0 else "-"
    return f"{sign}{abs(offset_hours):02d}:{offset_minutes:02d}"


def _log_email_schedule(
    recipient: str,
    subject: str,
    email_index: int,
    raw_date: str,
    raw_time: str,
    parsed_send_dt: Optional[datetime],
    final_deferred_dt: Optional[datetime],
    send_called: bool,
    sending_account: Optional[str] = None,
    entry_id: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Log diagnostic info for a scheduled email."""
    global _EMAIL_LOG_PATH
    if _EMAIL_LOG_PATH is None:
        _init_email_log()

    now = datetime.now()

    lines = [
        f"--- Email #{email_index} ---",
        f"Logged at: {now.isoformat()}",
        f"Recipient: {recipient}",
        f"Subject: {subject[:50]}{'...' if len(subject) > 50 else ''}",
        f"Sending account: {sending_account or 'N/A'}",
        f"Raw UI date: '{raw_date}'",
        f"Raw UI time: '{raw_time}'",
        f"Parsed send_dt: {repr(parsed_send_dt)}",
        f"Final naive local datetime: {repr(final_deferred_dt)}",
        f"System local time: {now.isoformat()}",
        f"System TZ offset: UTC{_get_local_tz_offset()}",
        f"Send() called: {send_called}",
    ]

    if entry_id:
        lines.append(f"EntryID: {entry_id}")
    if error:
        lines.append(f"ERROR: {error}")

    lines.append("")  # blank line between entries

    with _EMAIL_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------
# Outlook Deferred Delivery Time Compensation
# ---------------------------

def _set_deferred_with_compensation(mail, desired_dt: datetime) -> dict:
    """
    Set DeferredDeliveryTime with automatic timezone compensation.

    Outlook/Exchange sometimes shifts the deferred time (e.g., by 7 hours due to
    UTC conversion). This function detects the shift and compensates automatically
    so the final stored time matches the user's intended local time.

    Returns a dict with diagnostic info for logging.
    """
    result = {
        "desired_dt": desired_dt,
        "first_readback": None,
        "shift": None,
        "corrected_dt": None,
        "final_readback": None,
        "compensation_applied": False,
        "error": None,
    }

    try:
        # Ensure naive local datetime
        desired = desired_dt.replace(tzinfo=None)
        result["desired_dt"] = desired

        # First attempt: set to desired time
        com_time = pywintypes.Time(desired)
        mail.DeferredDeliveryTime = com_time

        # Read back what Outlook actually stored
        rb = mail.DeferredDeliveryTime
        result["first_readback"] = rb

        # Normalize readback to naive datetime for comparison
        # pywintypes.datetime may have tzinfo; strip it for delta calculation
        if hasattr(rb, "replace"):
            rb_naive = rb.replace(tzinfo=None)
        elif hasattr(rb, "timetuple"):
            # Convert to datetime if needed
            rb_naive = datetime(*rb.timetuple()[:6])
        else:
            # Can't compare, skip compensation
            result["error"] = f"Cannot normalize readback type: {type(rb)}"
            return result

        # Calculate shift
        shift = rb_naive - desired
        result["shift"] = shift

        # Only compensate if shift is within a sane window (timezone-like shift)
        # and greater than 1 minute (to avoid floating point noise)
        if not ENABLE_OUTLOOK_TIME_COMPENSATION:
            # Compensation disabled
            return result

        if abs(shift) >= timedelta(minutes=1) and abs(shift) <= timedelta(hours=12):
            # Apply compensation: subtract the shift so Outlook's conversion lands on desired
            corrected = (desired - shift).replace(tzinfo=None)
            result["corrected_dt"] = corrected

            # Set again with corrected time
            mail.DeferredDeliveryTime = pywintypes.Time(corrected)

            # Read back final value
            rb2 = mail.DeferredDeliveryTime
            result["final_readback"] = rb2
            result["compensation_applied"] = True

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result


def _log_compensation_result(comp_result: dict) -> None:
    """Log the compensation result to the email schedule log."""
    global _EMAIL_LOG_PATH
    if _EMAIL_LOG_PATH is None:
        return

    lines = [
        "  [Timezone Compensation]",
        f"    Desired local time: {repr(comp_result.get('desired_dt'))}",
        f"    First readback: {repr(comp_result.get('first_readback'))}",
        f"    Detected shift: {comp_result.get('shift')}",
        f"    Compensation applied: {comp_result.get('compensation_applied')}",
    ]

    if comp_result.get("compensation_applied"):
        lines.append(f"    Corrected datetime: {repr(comp_result.get('corrected_dt'))}")
        lines.append(f"    Final readback: {repr(comp_result.get('final_readback'))}")

    if comp_result.get("error"):
        lines.append(f"    ERROR: {comp_result.get('error')}")

    with _EMAIL_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------
# Text helpers
# ---------------------------


def _is_html(body: str) -> bool:
    """Check if body string contains HTML formatting tags."""
    if not body:
        return False
    return bool(re.search(r'<(b|i|u|ul|ol|li|a |br|p[ >]|span |div |/b>|/i>|/u>|/span>|/ol>)[> /]', body))


def _wrap_html_for_email(html_body: str) -> str:
    """Wrap HTML body content in a full HTML email document."""
    # Tighten list spacing for email clients (Outlook adds large default margins)
    if "<ul>" in html_body or "<ol>" in html_body:
        html_body = html_body.replace(
            "<ul>", '<ul style="margin:0; padding-left:28px;">'
        ).replace(
            "<ol>", '<ol style="margin:0; padding-left:28px;">'
        ).replace(
            "<li>", '<li style="margin:0; padding:0;">'
        )
    return (
        '<html><head><meta charset="utf-8"></head>'
        '<body style="font-family: Calibri, Arial, sans-serif; '
        'font-size: 11pt; color: #1E293B;">\n'
        f'{html_body}\n'
        '</body></html>'
    )


def normalize_text(text: Optional[str]) -> str:
    """Clean smart quotes/dashes and strip non-ASCII characters."""
    if text is None:
        return ""
    replacements = {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "—": "-",
        "–": "-",
    }
    for src, tgt in replacements.items():
        text = text.replace(src, tgt)
    return "".join(ch for ch in text if ord(ch) <= 127)


def merge_tokens(template: str, tokens: Dict[str, Any]) -> str:
    """
    Replace {FirstName}, {Company}, {Work Email}, {Email}, etc. in the template.
    """
    out = template
    for k, v in tokens.items():
        placeholder = "{" + k + "}"
        out = out.replace(placeholder, str(v) if v is not None else "")
    return out


# ---------------------------
# CSV helpers
# ---------------------------


def _read_contacts(contacts_path: Path) -> List[Dict[str, Any]]:
    """
    Read contacts from CSV into a list of dicts.

    REQUIRED: either a 'Work Email' column OR an 'Email' column.
    Rows with no usable email are skipped.
    """
    if not contacts_path.exists():
        raise FileNotFoundError(f"Contacts file not found: {contacts_path}")

    rows: List[Dict[str, Any]] = []
    with contacts_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or []) if h is not None]

        has_work_email = "Work Email" in headers
        has_email = "Email" in headers

        if not has_work_email and not has_email:
            raise ValueError(
                "Contacts CSV must include either a 'Work Email' or 'Email' column. "
                f"Found columns: {headers}"
            )

        for row in reader:
            cleaned = {(k or "").strip(): (v or "").strip() for k, v in row.items()}

            email = cleaned.get("Work Email") or cleaned.get("Email") or ""
            if not email:
                continue

            # Normalize to both keys so templates can use either
            cleaned["Work Email"] = email
            if "Email" not in cleaned:
                cleaned["Email"] = email

            rows.append(cleaned)

    if not rows:
        raise ValueError(
            "No valid contacts found in CSV (all rows missing 'Work Email' or 'Email')."
        )

    return rows


# ---------------------------
# Time helpers (local time only)
# ---------------------------


def _parse_send_datetime_to_naive(
    date_str: str,
    time_str: str,
) -> Optional[datetime]:
    """
    Parse explicit date ('YYYY-MM-DD') + time string into a naive datetime
    in LOCAL MACHINE TIME.

    Returns None if:
      - date is blank/unparseable, or
      - time is blank/'Immediately' (caller sends immediately).
    """
    date_str = (date_str or "").strip()
    time_str = (time_str or "").strip()

    if not date_str:
        return None

    if not time_str or time_str.lower().startswith("immed"):
        return None

    try:
        send_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            t = datetime.strptime(time_str, fmt).time()
            return datetime.combine(send_date, t)
        except ValueError:
            continue

    return None


def _parse_send_datetime_with_offset(
    base_now: datetime,
    day_offset: int,
    send_time_str: str,
) -> Optional[datetime]:
    """
    Older style: base_now + N days + send_time_str, using LOCAL MACHINE TIME.
    """
    send_time_str = (send_time_str or "").strip()

    if not send_time_str:
        return None
    if send_time_str.lower().startswith("immed"):
        return None

    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            t = datetime.strptime(send_time_str, fmt).time()
            send_date = base_now.date() + timedelta(days=day_offset)
            return datetime.combine(send_date, t)
        except ValueError:
            continue

    return None


# ---------------------------
# Outlook sending
# ---------------------------


def _ensure_outlook():
    """
    Outlook COM initialization using DYNAMIC DISPATCH.
    This completely bypasses pywin32 gencache and gen_py.
    """
    if not HAVE_OUTLOOK:
        raise RuntimeError("pywin32 is not installed")

    pythoncom.CoInitialize()  # type: ignore
    try:
        outlook = get_outlook_app()
        return outlook
    except Exception:
        pythoncom.CoUninitialize()  # type: ignore
        raise


def _send_sequence_for_contact(
    outlook: Any,
    contact: Dict[str, Any],
    schedule: Iterable[Dict[str, Any]],
    send_emails: bool,
    send_window_minutes: int = 0,
) -> int:
    """
    Send (or create) all scheduled emails for a single contact.

    If send_window_minutes > 0, each email's send time is offset by a
    random number of minutes (0..send_window_minutes) to distribute
    sends across a window for deliverability.

    Returns the number of emails created/sent.
    """
    email = (contact.get("Work Email") or contact.get("Email") or "").strip()
    if not email:
        return 0

    tokens: Dict[str, Any] = {
        "FirstName": contact.get("FirstName", contact.get("First Name", "")),
        "LastName": contact.get("LastName", contact.get("Last Name", "")),
        "Company": contact.get("Company", ""),
        "Work Email": email,
        "Email": email,
        "Title": contact.get("Title", contact.get("JobTitle", "")),
        "JobTitle": contact.get("JobTitle", contact.get("Title", "")),
        "City": contact.get("City", ""),
        "State": contact.get("State", ""),
    }

    now = datetime.now()
    count = 0
    email_index = 0

    for item in schedule:
        if not isinstance(item, dict):
            continue

        email_index += 1
        subject_template = item.get("subject") or item.get("Subject") or ""
        body_template = item.get("body") or item.get("Body") or ""

        if not subject_template.strip() and not body_template.strip():
            continue

        # New style (GUI): explicit date + time
        date_str = (item.get("date") or "").strip()
        time_str = (item.get("time") or item.get("send_time") or "").strip()

        send_dt: Optional[datetime] = None

        if date_str:
            send_dt = _parse_send_datetime_to_naive(date_str, time_str)
        else:
            # Backwards compat: offset_days / days (assumed local machine time)
            day_offset = int(item.get("offset_days") or item.get("days") or 0)
            send_dt = _parse_send_datetime_with_offset(now, day_offset, time_str)

        # Send window randomization: offset send time by random minutes
        if send_dt is not None and send_window_minutes > 0:
            offset = random.randint(0, send_window_minutes)
            send_dt = send_dt + timedelta(minutes=offset)

        # CRITICAL: Ensure send_dt is NAIVE (no timezone info).
        # Outlook COM expects naive local datetime for DeferredDeliveryTime.
        # If tzinfo is present, Outlook may misinterpret and shift the time.
        final_deferred_dt: Optional[datetime] = None
        if send_dt is not None:
            # Strip any timezone info to ensure naive local time
            final_deferred_dt = send_dt.replace(tzinfo=None)

        # Attachments: may be list[str] or comma-separated string
        raw_attachments = item.get("attachments") or item.get("attachment_paths") or []
        if isinstance(raw_attachments, str):
            attachment_paths = [p.strip() for p in raw_attachments.split(",") if p.strip()]
        else:
            attachment_paths = list(raw_attachments)

        subject = merge_tokens(normalize_text(subject_template), tokens)

        if _is_html(body_template):
            # HTML body: fix smart quotes but preserve tags (skip normalize_text)
            body_clean = body_template
            for src, tgt in {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'", "\u2014": "-", "\u2013": "-"}.items():
                body_clean = body_clean.replace(src, tgt)
            body = merge_tokens(body_clean, tokens)
        else:
            body = merge_tokens(normalize_text(body_template), tokens)

        mail = outlook.CreateItem(0)  # olMailItem
        mail.To = email
        mail.Subject = subject
        if _is_html(body):
            mail.HTMLBody = _wrap_html_for_email(body)
        else:
            mail.Body = body

        # CRITICAL: Force sending account binding for reliable submission
        # In multi-account profiles, this ensures the mail is properly routed
        sending_acct = _set_sending_account(outlook, mail)
        acct_smtp = None
        try:
            acct_smtp = getattr(sending_acct, "SmtpAddress", None) if sending_acct else None
        except Exception:
            pass

        if attachment_paths:
            for p in attachment_paths:
                try:
                    path_obj = Path(p)
                    if path_obj.exists():
                        mail.Attachments.Add(str(path_obj))
                except Exception:
                    # Best effort; skip bad attachment
                    continue

        # Track for logging
        send_called = False
        entry_id = None
        warning_msg = None  # Non-fatal warnings (e.g., compensation issues)
        fatal_error = None  # Fatal errors that should stop processing
        comp_result = None
        is_deferred = False

        if send_emails:
            # Build message fully → set DeferredDeliveryTime with compensation → Save → Send
            # Save before Send commits all properties reliably (especially for deferred delivery)
            # Do NOT modify the mail item after Send().
            try:
                if final_deferred_dt and final_deferred_dt > datetime.now():
                    is_deferred = True
                    # Use timezone compensation to handle Outlook's time shifting behavior.
                    # This detects any shift and auto-corrects so the final stored time
                    # matches the user's intended local time.
                    comp_result = _set_deferred_with_compensation(mail, final_deferred_dt)

                    # Log compensation details
                    _log_compensation_result(comp_result)

                    # If compensation encountered an error, log as warning but continue
                    if comp_result.get("error"):
                        warning_msg = f"Compensation warning: {comp_result['error']}"

                # For deferred emails: Save before Send commits all properties reliably
                # This ensures DeferredDeliveryTime, account binding, and attachments are committed
                if is_deferred:
                    mail.Save()

                mail.Send()
                send_called = True

                # Try to get EntryID (may not be available immediately after Send)
                try:
                    entry_id = getattr(mail, "EntryID", None)
                except Exception:
                    pass

            except Exception as e:
                fatal_error = f"{type(e).__name__}: {e}"
                # Still try to log the error
        else:
            # Just save as draft (not scheduled for send)
            mail.Save()

        # Log diagnostic info for every email
        _log_email_schedule(
            recipient=email,
            subject=subject,
            email_index=email_index,
            raw_date=date_str,
            raw_time=time_str,
            parsed_send_dt=send_dt,
            final_deferred_dt=final_deferred_dt,
            sending_account=acct_smtp,
            send_called=send_called,
            entry_id=entry_id,
            error=fatal_error or warning_msg,
        )

        if fatal_error:
            # Re-raise so caller knows something failed
            raise RuntimeError(f"Failed to send email #{email_index}: {fatal_error}")

        count += 1

    return count


# ---------------------------
# Public API
# ---------------------------


def run_funnelforge(
    schedule: Iterable[Dict[str, Any]],
    contacts_path: str,
    attachments_path: Optional[str] = None,  # kept for backwards compatibility (ignored)
    timezone: Optional[str] = None,          # ignored; kept for backwards compatibility
    send_emails: bool = True,
    send_window_minutes: int = 0,
) -> None:
    """
    Main entry point called by the Funnel Forge GUI.

    Parameters
    ----------
    schedule:
        Iterable of dicts describing each email step.
        Expected keys per item (case-insensitive, best-effort):
          - 'subject' or 'Subject'
          - 'body' or 'Body'
          - EITHER:
                - 'date' (YYYY-MM-DD from the GUI) + 'time'/'send_time'
            OR  - 'offset_days'/'days' + 'time'/'send_time'
          - 'attachments' or 'attachment_paths' (optional list[str] or csv string)

    contacts_path:
        Path to CSV with at least 'Work Email' or 'Email' column.
        Rows without an email address are skipped.

    attachments_path:
        (Ignored) kept only so older GUIs don't crash.

    timezone:
        (Ignored) kept only so older GUIs don't crash.

    send_emails:
        If True, emails are sent (or deferred) via Outlook.
        If False, emails are created as drafts only.
    """
    contacts_file = Path(contacts_path)
    outlook = None

    # Initialize email scheduling log for this session
    log_path = _init_email_log()
    print(f"Email scheduling log: {log_path}")

    try:
        contacts = _read_contacts(contacts_file)
        if not contacts:
            raise ValueError("No contacts to send to.")

        outlook = _ensure_outlook()

        # Preflight: Check if Outlook is offline
        if send_emails and _is_outlook_offline(outlook):
            raise RuntimeError(
                "Outlook is in offline mode. Emails cannot be sent reliably. "
                "Please go online (File → Work Offline to toggle) and try again."
            )

        total_emails = 0
        for ci, contact in enumerate(contacts):
            total_emails += _send_sequence_for_contact(
                outlook=outlook,
                contact=contact,
                schedule=schedule,
                send_emails=send_emails,
                send_window_minutes=send_window_minutes,
            )
            # Throttle: max 20 emails/minute → 3-second pause between contacts
            if send_emails and send_window_minutes > 0 and ci < len(contacts) - 1:
                _time.sleep(3)

        # Kick Send/Receive to process the queue immediately
        # This helps Outlook process deferred items reliably
        if send_emails and total_emails > 0:
            try:
                outlook.Session.SendAndReceive(True)
            except Exception:
                pass  # Best effort; don't fail if this doesn't work

        # Log summary
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"Session completed: {datetime.now().isoformat()}\n")
            f.write(f"Total emails processed: {total_emails}\n")
            f.write(f"SendAndReceive triggered: {send_emails and total_emails > 0}\n")
            f.write("=" * 80 + "\n")

        return

    except Exception:
        crash_log = log_exception()
        print(f"Core failed. Crash log: {crash_log}", file=sys.stderr)
        raise

    finally:
        # CRITICAL: Cleanup COM properly
        if outlook is not None:
            try:
                pythoncom.CoUninitialize()  # type: ignore
            except Exception:
                pass


def run_4drip(
    schedule: Iterable[Dict[str, Any]],
    contacts_path: str,
    attachments_path: Optional[str] = None,
    timezone: Optional[str] = None,
    send_emails: bool = True,
    send_window_minutes: int = 0,
) -> None:
    """
    Backward-compatible wrapper so older GUIs can keep calling run_4drip(...).
    """
    return run_funnelforge(
        schedule=schedule,
        contacts_path=contacts_path,
        attachments_path=attachments_path,
        timezone=timezone,
        send_emails=send_emails,
        send_window_minutes=send_window_minutes,
    ) 
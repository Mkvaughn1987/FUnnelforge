"""
funnelforge_core.py

Core logic for Funnel Forge:
- Reads contacts from CSV
- Queues emails internally (no Outlook DeferredDeliveryTime)
- Background scheduler thread fires emails at the right time via Outlook
- Emails are sent IMMEDIATELY when due — nothing sits in the Outbox

HOW IT WORKS:
  Instead of setting DeferredDeliveryTime on Outlook items and letting Outlook
  hold them, FunnelForge manages its own queue (saved to disk). A daemon thread
  wakes every 60 seconds, checks for due emails, and sends them on the spot.
  Outlook receives a fresh item with NO deferred time → sends immediately.

REQUIREMENTS:
  - FunnelForge must be running when emails are scheduled to fire.
  - Outlook must be open and online at send time.
  - Both were already required with the old deferred approach.

CHANGELOG:
  v3.0 — Replaced DeferredDeliveryTime with internal scheduler queue.
         Emails now fire directly from FunnelForge at scheduled time.
         Queue persists across app restarts in scheduled_queue.json.
"""

import csv
import json
import os
import random
import re
import shutil
import sys
import tempfile
import threading
import time as _time
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


# ---------------------------
# Outlook COM (DYNAMIC DISPATCH ONLY)
# ---------------------------
try:
    import pythoncom   # type: ignore
    import pywintypes  # type: ignore
    import win32com.client          # type: ignore
    import win32com.client.dynamic  # type: ignore
    HAVE_OUTLOOK = True
except ImportError:
    pythoncom  = None
    pywintypes = None
    win32com   = None
    HAVE_OUTLOOK = False


# ---------------------------
# Paths & logging
# ---------------------------

def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

APP_DIR = _app_dir()
LOG_DIR = Path(os.getenv("LOCALAPPDATA", str(APP_DIR))) / "DripDrop" / "logs"
_QUEUE_NEW = Path(os.getenv("LOCALAPPDATA", str(APP_DIR))) / "DripDrop" / "scheduled_queue.json"
_QUEUE_LEGACY = Path(os.getenv("LOCALAPPDATA", str(APP_DIR))) / "Funnel Forge" / "scheduled_queue.json"
QUEUE_PATH = _QUEUE_NEW if _QUEUE_NEW.exists() else _QUEUE_LEGACY

# ---------------------------
# Configuration
# ---------------------------
SCHEDULER_INTERVAL_SECONDS = 60   # How often the background thread wakes up
INTER_EMAIL_PAUSE           = 1    # Seconds between emails in a batch send
MAX_SEND_RETRY              = 2    # Retry attempts per email on failure
SEND_RECEIVE_BATCH_SIZE     = 30   # Trigger SendAndReceive every N sends
SEND_RECEIVE_COOLDOWN       = 10   # Seconds to wait after SendAndReceive


# ---------------------------
# Logging helpers
# ---------------------------

_EMAIL_LOG_PATH: Optional[Path] = None

def _ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR

def _init_email_log() -> Path:
    global _EMAIL_LOG_PATH
    _ensure_log_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _EMAIL_LOG_PATH = LOG_DIR / f"email_schedule_{ts}.log"
    with _EMAIL_LOG_PATH.open("w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("Funnel Forge Email Schedule Log — v3.0 Scheduler Build\n")
        f.write(f"Session started: {datetime.now().isoformat()}\n")
        f.write("Mode: Internal scheduler (no DeferredDeliveryTime)\n")
        f.write("=" * 80 + "\n\n")
    return _EMAIL_LOG_PATH

def _get_local_tz_offset() -> str:
    import time
    offset_seconds = -time.timezone if not time.daylight else -time.altzone
    h = offset_seconds // 3600
    m = abs(offset_seconds % 3600) // 60
    sign = "+" if h >= 0 else "-"
    return f"{sign}{abs(h):02d}:{m:02d}"

def _log_raw(text: str) -> None:
    global _EMAIL_LOG_PATH
    if _EMAIL_LOG_PATH is None:
        return
    try:
        with _EMAIL_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass

def log_exception() -> Path:
    _ensure_log_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = LOG_DIR / f"core_crash_{ts}.log"
    with p.open("w", encoding="utf-8") as f:
        traceback.print_exc(file=f)
    return p


# ---------------------------
# Persistent Queue
# ---------------------------

_queue_lock = threading.Lock()


def _load_queue() -> List[Dict]:
    """Load the persisted email queue from disk."""
    try:
        if QUEUE_PATH.exists():
            with QUEUE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
                queue = data if isinstance(data, list) else []
                # Backfill any items that have blank campaign names
                dirty = False
                for item in queue:
                    if not item.get("campaign"):
                        item["campaign"] = "Untitled Campaign"
                        dirty = True
                if dirty:
                    _save_queue(queue)
                return queue
    except Exception:
        pass
    return []


def _save_queue(queue: List[Dict]) -> None:
    """Save the email queue to disk atomically."""
    try:
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = QUEUE_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2, default=str)
        tmp.replace(QUEUE_PATH)
    except Exception as e:
        _log_raw(f"[Queue] Save failed: {e}")


def add_to_queue(items: List[Dict]) -> None:
    """Add a list of email dicts to the persistent queue."""
    with _queue_lock:
        queue = _load_queue()
        queue.extend(items)
        _save_queue(queue)
    _log_raw(f"[Queue] Added {len(items)} item(s). Total pending: {sum(1 for q in queue if q.get('status') == 'pending')}")


def get_queue() -> List[Dict]:
    """Return a copy of the current queue."""
    with _queue_lock:
        return list(_load_queue())


def cancel_queue_items(ids: List[str]) -> int:
    """Cancel queue items by ID. Returns count cancelled."""
    cancelled = 0
    with _queue_lock:
        queue = _load_queue()
        for item in queue:
            if item.get("id") in ids and item.get("status") == "pending":
                item["status"] = "cancelled"
                cancelled += 1
        _save_queue(queue)
    return cancelled


def cancel_all_pending() -> int:
    """Cancel every pending item in the queue. Returns count cancelled."""
    with _queue_lock:
        queue = _load_queue()
        count = 0
        for item in queue:
            if item.get("status") == "pending":
                item["status"] = "cancelled"
                count += 1
        _save_queue(queue)
    return count


def get_pending_count() -> int:
    """Return number of pending emails in queue."""
    return sum(1 for q in get_queue() if q.get("status") == "pending")


def get_pending_for_campaign(campaign_name: str) -> List[Dict]:
    """Return pending items for a specific campaign."""
    return [q for q in get_queue()
            if q.get("status") == "pending" and q.get("campaign") == campaign_name]


# ---------------------------
# Outlook helpers
# ---------------------------

def get_outlook_app():
    """Get Outlook COM object using DYNAMIC DISPATCH."""
    return win32com.client.dynamic.Dispatch("Outlook.Application")


def _is_outlook_offline(outlook) -> bool:
    try:
        ns = outlook.GetNamespace("MAPI")
        return bool(getattr(ns, "Offline", False))
    except Exception:
        return False


def _set_sending_account(outlook, mail, target_smtp: Optional[str] = None):
    try:
        session   = outlook.Session
        accounts  = session.Accounts
        chosen    = None
        if target_smtp:
            for i in range(1, accounts.Count + 1):
                acct = accounts.Item(i)
                try:
                    if acct.SmtpAddress and acct.SmtpAddress.lower() == target_smtp.lower():
                        chosen = acct
                        break
                except Exception:
                    continue
        if chosen is None and accounts.Count > 0:
            chosen = accounts.Item(1)
        if chosen is not None:
            mail.SendUsingAccount = chosen
            return chosen
    except Exception:
        pass
    return None


def _get_outbox_count(outlook) -> int:
    try:
        ns = outlook.GetNamespace("MAPI")
        return ns.GetDefaultFolder(4).Items.Count
    except Exception:
        return 0


def _flush_send_receive(outlook, reason: str = "") -> None:
    try:
        outlook.Session.SendAndReceive(True)
        _log_raw(f"  [SendAndReceive] {reason}")
    except Exception as e:
        _log_raw(f"  [SendAndReceive] Failed ({reason}): {e}")


# ---------------------------
# Text helpers
# ---------------------------

def _is_html(body: str) -> bool:
    if not body:
        return False
    return bool(re.search(r'<(b|i|u|ul|ol|li|a |br|p[ >]|span |div |/b>|/i>|/u>|/span>|/ol>)[> /]', body))


def _wrap_html_for_email(html_body: str, unsubscribe_email: Optional[str] = None,
                          company_address: Optional[str] = None) -> str:
    """Wrap an email body with a CAN-SPAM compliant footer.

    The footer is now ALWAYS included (not gated on unsubscribe_email) because
    every commercial email must carry an opt-out mechanism + physical address
    per CAN-SPAM. The unsubscribe_email arg is kept for backwards compat but
    no longer toggles visibility.
    """
    if "<ul>" in html_body or "<ol>" in html_body:
        html_body = html_body.replace("<ul>", '<ul style="margin:0; padding-left:28px;">') \
                             .replace("<ol>", '<ol style="margin:0; padding-left:28px;">') \
                             .replace("<li>", '<li style="margin:0; padding:0;">')

    _addr_line = ""
    if company_address and str(company_address).strip():
        _addr_line = f'<br>{str(company_address).strip()}'
    unsub = (
        '<br><br>'
        '<div style="border-top:1px solid #E2E8F0; margin-top:24px; padding-top:10px;'
        ' font-size:8.5pt; color:#94A3B8; font-family:Calibri,Arial,sans-serif;">'
        'If you would like to unsubscribe, please reply &ldquo;UNSUBSCRIBE&rdquo; and you will be removed.'
        f'{_addr_line}'
        '</div>'
    )
    return (
        '<html><head><meta charset="utf-8"></head>'
        '<body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #1E293B;">\n'
        f'{html_body}\n{unsub}\n</body></html>'
    )


def normalize_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    for src, tgt in {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
                     "\u2014": "-", "\u2013": "-"}.items():
        text = text.replace(src, tgt)
    return "".join(ch for ch in text if ord(ch) <= 127)


def merge_tokens(template: str, tokens: Dict[str, Any]) -> str:
    out = template
    for k, v in tokens.items():
        out = out.replace("{" + k + "}", str(v) if v is not None else "")
    return out


# ---------------------------
# CSV helpers
# ---------------------------

def _read_contacts(contacts_path: Path) -> List[Dict[str, Any]]:
    if not contacts_path.exists():
        raise FileNotFoundError(f"Contacts file not found: {contacts_path}")
    rows: List[Dict[str, Any]] = []
    with contacts_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or []) if h]
        if "Work Email" not in headers and "Email" not in headers:
            raise ValueError(f"Contacts CSV needs 'Work Email' or 'Email'. Found: {headers}")
        for row in reader:
            cleaned = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            email = cleaned.get("Work Email") or cleaned.get("Email") or ""
            if not email:
                continue
            cleaned["Work Email"] = email
            if "Email" not in cleaned:
                cleaned["Email"] = email
            rows.append(cleaned)
    if not rows:
        raise ValueError("No valid contacts found in CSV.")
    return rows


# ---------------------------
# Time helpers
# ---------------------------

def _parse_send_datetime(date_str: str, time_str: str) -> Optional[datetime]:
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


def _parse_send_datetime_offset(base_now: datetime, day_offset: int, time_str: str) -> Optional[datetime]:
    time_str = (time_str or "").strip()
    if not time_str or time_str.lower().startswith("immed"):
        return None
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            t = datetime.strptime(time_str, fmt).time()
            return datetime.combine(base_now.date() + timedelta(days=day_offset), t)
        except ValueError:
            continue
    return None


# ---------------------------
# Immediate Outlook send (NO DeferredDeliveryTime)
# ---------------------------

def _send_one_email(outlook, item: Dict) -> bool:
    """
    Send a single queued email. Tries SendGrid first (server), falls back to Outlook (desktop).
    Returns True on success.
    """
    to      = item.get("to", "")
    subject = item.get("subject", "")
    body    = item.get("body", "")
    html    = item.get("is_html", False)
    attachments = item.get("attachments") or []
    unsubscribe = item.get("unsubscribe_email")
    company_address = item.get("company_address", "") or ""
    sender_smtp = item.get("sender_smtp", "")

    if not to:
        return False

    if not html:
        body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body = body.replace("\n", "<br>")

    # Build the List-Unsubscribe mailto header value. Points to the sender's
    # own address with subject UNSUBSCRIBE — the existing reply monitor
    # picks these up via _is_opt_out() and auto-adds to the DNC list.
    _unsub_to = sender_smtp or ""
    _list_unsub_mailto = f"mailto:{_unsub_to}?subject=UNSUBSCRIBE" if _unsub_to else ""

    # Try SMTP first (works on server)
    try:
        import email_sender as _cloud
        _cfg_path = Path(os.getenv("DRIPDROP_DATA_DIR", os.getenv("LOCALAPPDATA", "."))) / "DripDrop" / "dripdrop_config.json"
        _from = sender_smtp or ""
        _name = ""
        _pass = ""
        _host = ""
        _port = 587
        if _cfg_path.exists():
            try:
                _c = json.loads(_cfg_path.read_text(encoding="utf-8"))
                _from = _from or _c.get("smtp_email", "")
                _name = _c.get("smtp_from_name", "")
                _pass = _c.get("smtp_password", "")
                _host = _c.get("smtp_host", "")
                _port = int(_c.get("smtp_port", 587) or 587)
                if not _list_unsub_mailto and _from:
                    _list_unsub_mailto = f"mailto:{_from}?subject=UNSUBSCRIBE"
            except Exception:
                pass
        if _from and _pass:
            ok, err = _cloud.send_email(
                to=to, subject=subject,
                html_body=_wrap_html_for_email(body, unsubscribe_email=unsubscribe,
                                               company_address=company_address),
                from_email=_from, from_name=_name, password=_pass,
                smtp_host=_host, smtp_port=_port, attachments=attachments,
                list_unsubscribe_mailto=_list_unsub_mailto,
            )
            if ok:
                return True
            _log_raw(f"  [SMTP] Failed: {err} — falling back to Outlook")
    except ImportError:
        pass

    # Fallback: Outlook COM (Windows only)
    if not HAVE_OUTLOOK or outlook is None:
        _log_raw(f"  [SEND FAIL] No email service available for {to}")
        return False

    try:
        mail = outlook.CreateItem(0)  # olMailItem
        mail.To      = to
        mail.Subject = subject
        mail.HTMLBody = _wrap_html_for_email(body, unsubscribe_email=unsubscribe,
                                             company_address=company_address)

        acct = _set_sending_account(outlook, mail, target_smtp=sender_smtp if sender_smtp else None)

        if sender_smtp and acct:
            try:
                actual = acct.SmtpAddress.lower() if acct.SmtpAddress else ""
                if actual and actual != sender_smtp.lower():
                    _log_raw(f"  [SKIP] Sender mismatch: queued by {sender_smtp}, current account {actual}")
                    return False
            except Exception:
                pass

        for p in attachments:
            try:
                if p and Path(p).exists():
                    mail.Attachments.Add(str(p))
            except Exception:
                pass

        mail.Send()
        return True

    except Exception as e:
        _log_raw(f"  [SEND FAIL] {to} — {subject[:40]}: {e}")
        return False


# ---------------------------
# Background Scheduler Thread
# ---------------------------

class _SchedulerThread(threading.Thread):
    """
    Daemon thread that wakes every SCHEDULER_INTERVAL_SECONDS,
    checks the queue for due emails, and sends them immediately via Outlook.
    """

    def __init__(self):
        super().__init__(name="FunnelForgeScheduler", daemon=True)
        self._stop_event = threading.Event()
        self._outlook    = None
        self._send_count = 0  # Tracks sends since last SendAndReceive

    def stop(self):
        self._stop_event.set()

    def run(self):
        _log_raw(f"[Scheduler] Started — checking every {SCHEDULER_INTERVAL_SECONDS}s")
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as e:
                _log_raw(f"[Scheduler] Tick error: {e}")
            self._stop_event.wait(SCHEDULER_INTERVAL_SECONDS)
        _log_raw("[Scheduler] Stopped.")

    def _get_outlook(self):
        """Get or re-connect the Outlook COM object."""
        if not HAVE_OUTLOOK:
            return None
        try:
            if self._outlook is None:
                pythoncom.CoInitialize()
                self._outlook = get_outlook_app()
            # Quick health check
            _ = self._outlook.Session
            return self._outlook
        except Exception:
            # COM object stale — reconnect
            self._outlook = None
            try:
                self._outlook = get_outlook_app()
                return self._outlook
            except Exception:
                return None

    def _tick(self):
        """One scheduler tick: find due emails and send them."""
        now = datetime.now()

        with _queue_lock:
            queue = _load_queue()
            due = [
                (i, item) for i, item in enumerate(queue)
                if item.get("status") == "pending"
                and item.get("send_dt")
                and datetime.fromisoformat(item["send_dt"]) <= now
            ]

        if not due:
            return

        _log_raw(f"[Scheduler] {now.isoformat()} — {len(due)} email(s) due")

        outlook = self._get_outlook()
        if outlook is None:
            _log_raw("[Scheduler] Outlook unavailable — will retry next tick")
            return

        if _is_outlook_offline(outlook):
            _log_raw("[Scheduler] Outlook is offline — will retry next tick")
            return

        sent_ids   = []
        failed_ids = []

        for _, item in due:
            success = False
            for attempt in range(1, MAX_SEND_RETRY + 1):
                if _send_one_email(outlook, item):
                    success = True
                    break
                _log_raw(f"  [Scheduler] Retry {attempt}/{MAX_SEND_RETRY} for {item.get('to')}")
                _time.sleep(2)

            if success:
                sent_ids.append(item["id"])
                self._send_count += 1
                _log_raw(f"  ✓ Sent: {item.get('to')} — {item.get('subject', '')[:50]}")
            else:
                failed_ids.append(item["id"])
                _log_raw(f"  ✗ Failed: {item.get('to')} — {item.get('subject', '')[:50]}")

            _time.sleep(INTER_EMAIL_PAUSE)

            # Periodic SendAndReceive to keep exchange flowing
            if self._send_count > 0 and self._send_count % SEND_RECEIVE_BATCH_SIZE == 0:
                _flush_send_receive(outlook, reason=f"batch after {self._send_count} sends")
                _time.sleep(SEND_RECEIVE_COOLDOWN)

        # Update statuses
        with _queue_lock:
            queue = _load_queue()
            for item in queue:
                if item["id"] in sent_ids:
                    item["status"] = "sent"
                    item["sent_at"] = datetime.now().isoformat()
                elif item["id"] in failed_ids:
                    item["status"] = "failed"
                    item["failed_at"] = datetime.now().isoformat()
            _save_queue(queue)

        _log_raw(f"[Scheduler] Tick complete — sent: {len(sent_ids)}, failed: {len(failed_ids)}")


# Module-level scheduler singleton
_scheduler: Optional[_SchedulerThread] = None
_scheduler_lock = threading.Lock()


def start_scheduler() -> None:
    """Start the background scheduler (call once on app startup)."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None or not _scheduler.is_alive():
            if _EMAIL_LOG_PATH is None:
                _init_email_log()
            _scheduler = _SchedulerThread()
            _scheduler.start()


def stop_scheduler() -> None:
    """Stop the background scheduler (call on app exit)."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler and _scheduler.is_alive():
            _scheduler.stop()
            _scheduler.join(timeout=5)
            _scheduler = None


def scheduler_is_running() -> bool:
    """Check if the scheduler thread is alive."""
    return _scheduler is not None and _scheduler.is_alive()


# ---------------------------
# Build queue items from schedule + contacts
# ---------------------------

def _build_queue_items(
    schedule: List[Dict],
    contacts: List[Dict],
    send_window_minutes: int = 0,
    campaign_name: str = "",
    unsubscribe_email: Optional[str] = None,
) -> List[Dict]:
    """
    Build queue items (one per contact × email) from a schedule + contacts list.
    Applies token substitution and send-window jitter here so items are ready to fire.
    """
    items = []
    now   = datetime.now()

    for contact in contacts:
        email = (contact.get("Work Email") or contact.get("Email") or "").strip()
        if not email:
            continue

        tokens: Dict[str, Any] = {
            "FirstName": contact.get("FirstName", contact.get("First Name", "")),
            "LastName":  contact.get("LastName",  contact.get("Last Name",  "")),
            "Company":   contact.get("Company",   ""),
            "Work Email": email,
            "Email":      email,
            "Title":      contact.get("Title",    contact.get("JobTitle", "")),
            "JobTitle":   contact.get("JobTitle", contact.get("Title",    "")),
            "City":       contact.get("City",     ""),
            "State":      contact.get("State",    ""),
        }

        for step_idx, step in enumerate(schedule):
            if not isinstance(step, dict):
                continue

            subject_tmpl = step.get("subject") or step.get("Subject") or ""
            body_tmpl    = step.get("body")    or step.get("Body")    or ""
            if not subject_tmpl.strip() and not body_tmpl.strip():
                continue

            date_str = (step.get("date") or "").strip()
            time_str = (step.get("time") or step.get("send_time") or "").strip()

            if date_str:
                send_dt = _parse_send_datetime(date_str, time_str)
            else:
                day_offset = int(step.get("offset_days") or step.get("days") or 0)
                send_dt = _parse_send_datetime_offset(now, day_offset, time_str)

            # Apply send window jitter
            if send_dt is not None and send_window_minutes > 0:
                offset  = random.randint(-send_window_minutes, send_window_minutes)
                send_dt = send_dt + timedelta(minutes=offset)
                # Never schedule in the past
                send_dt = max(send_dt, now + timedelta(minutes=1))

            # Token substitution
            subject = merge_tokens(normalize_text(subject_tmpl), tokens)
            if _is_html(body_tmpl):
                body_clean = body_tmpl
                for src, tgt in {"\u201c": '"', "\u201d": '"', "\u2018": "'",
                                  "\u2019": "'", "\u2014": "-", "\u2013": "-"}.items():
                    body_clean = body_clean.replace(src, tgt)
                body = merge_tokens(body_clean, tokens)
            else:
                body = merge_tokens(normalize_text(body_tmpl), tokens)

            raw_att = step.get("attachments") or step.get("attachment_paths") or []
            if isinstance(raw_att, str):
                att_list = [p.strip() for p in raw_att.split(",") if p.strip()]
            else:
                att_list = list(raw_att)

            items.append({
                "id":               str(uuid.uuid4()),
                "status":           "pending",
                "send_dt":          send_dt.isoformat() if send_dt else None,
                "to":               email,
                "subject":          subject,
                "body":             body,
                "is_html":          _is_html(body),
                "attachments":      att_list,
                "campaign":         campaign_name or "Untitled Campaign",
                "step_index":       step_idx,
                "email_name":       step.get("name", f"Email {step_idx + 1}"),
                "unsubscribe_email": unsubscribe_email,
                "queued_at":        now.isoformat(),
                "contact_name":     tokens.get("FirstName", "") + (" " + tokens.get("LastName", "")).rstrip(),
                "contact_company":  tokens.get("Company", ""),
            })

    return items


# ---------------------------
# Public API
# ---------------------------

def run_funnelforge(
    schedule: Iterable[Dict[str, Any]],
    contacts_path: str,
    attachments_path: Optional[str] = None,   # kept for backwards compat (ignored)
    timezone: Optional[str] = None,            # kept for backwards compat (ignored)
    send_emails: bool = True,
    send_window_minutes: int = 0,
    unsubscribe_email: Optional[str] = None,
    campaign_name: str = "",
) -> None:
    """
    Main entry point called by the Funnel Forge GUI.

    Queues all emails in the internal scheduler queue.
    The background scheduler thread fires each email at its scheduled time
    directly via Outlook — no DeferredDeliveryTime, nothing waiting in Outbox.

    If send_emails=False, items are queued as 'draft' status (not sent).
    """
    log_path = _init_email_log()
    print(f"Email schedule log: {log_path}")

    contacts_file  = Path(contacts_path)
    schedule_list  = list(schedule)

    try:
        contacts = _read_contacts(contacts_file)
        if not contacts:
            raise ValueError("No contacts to send to.")

        _log_raw(f"Building queue: {len(contacts)} contacts × {len(schedule_list)} emails")
        _log_raw(f"Send window: ±{send_window_minutes} min")
        _log_raw("")

        items = _build_queue_items(
            schedule=schedule_list,
            contacts=contacts,
            send_window_minutes=send_window_minutes,
            campaign_name=campaign_name,
            unsubscribe_email=unsubscribe_email,
        )

        if not send_emails:
            for item in items:
                item["status"] = "draft"

        add_to_queue(items)

        # Ensure scheduler is running
        start_scheduler()

        _log_raw(f"Queued {len(items)} email(s). Scheduler will fire them at scheduled times.")
        _log_raw(f"Scheduler running: {scheduler_is_running()}")

    except Exception:
        log_exception()
        raise


def run_4drip(
    schedule: Iterable[Dict[str, Any]],
    contacts_path: str,
    attachments_path: Optional[str] = None,
    timezone: Optional[str] = None,
    send_emails: bool = True,
    send_window_minutes: int = 0,
    unsubscribe_email: Optional[str] = None,
    campaign_name: str = "",
) -> None:
    """Backward-compatible wrapper — calls run_funnelforge."""
    return run_funnelforge(
        schedule=schedule,
        contacts_path=contacts_path,
        attachments_path=attachments_path,
        timezone=timezone,
        send_emails=send_emails,
        send_window_minutes=send_window_minutes,
        unsubscribe_email=unsubscribe_email,
        campaign_name=campaign_name,
    )

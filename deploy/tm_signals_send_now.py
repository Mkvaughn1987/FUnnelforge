"""One-off: build and email today's Buying News & Signals issue for one user,
through the app's own sending path (the user's own mailbox), exactly as the
page's "Send me one now" button does. Useful when a scan needs re-running
from the box without a browser, e.g. after a research fix.

Run on the box as the service user. DRIPDROP_DATA_DIR comes from the systemd
unit, not .env, so the script sets it itself; .env is loaded with
python-dotenv because a plain `set -a; . .env` trips on values with spaces.

  cd /opt/dripdrop/app && sudo -u dripdrop /opt/dripdrop/venv/bin/python \\
      deploy/tm_signals_send_now.py mkvaughn1987@gmail.com

Nothing found or every industry failing means no email; the issue is still
stored and shows on the page with the reason.
"""
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
os.chdir(APP)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(str(APP.parent / ".env"))
os.environ.setdefault("DRIPDROP_DATA_DIR", str(APP.parent / "data"))
import flowdrip_app as fa  # noqa: E402
import tm_signals as tms  # noqa: E402


def main():
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print(__doc__)
        return 2
    email = sys.argv[1]
    user_dir = Path(fa._BASE_DATA_DIR) / "users" / email.replace("@", "_at_").replace(".", "_")
    if not (user_dir / tms.SETTINGS_FILE).exists():
        print(f"no {tms.SETTINGS_FILE} under {user_dir}: open Buying Signals once and Save")
        return 1
    print("user_dir:", user_dir, "model:", tms.MODEL, flush=True)
    issue = tms.run_issue(email, user_dir)
    if issue is None:
        print("RESULT: run_issue returned None (already running, or failed: see above)")
        return 1
    print("RESULT: sent_at=", issue["sent_at"] or "-", "| send_error=", issue["send_error"] or "-")
    for s in issue["sections"]:
        print(f"  {s['label']}: {len(s.get('companies') or [])} companies, "
              f"{len(s.get('news') or [])} news"
              + (f"  ERROR: {s['error'][:120]}" if s.get("error") else ""))
    print("blocked search domains learned this run:", sorted(tms._BLOCKED_DOMAINS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

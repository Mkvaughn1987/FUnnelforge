"""AI Prompts jobs queued for the user's own AI.

"Send to my AI" on the AI Prompts page writes a job here instead of handing
the user a prompt to paste. The hourly worker the user set up once in their
desktop AI app picks it up through the same two connector tools as a Sales
Campaign run (sales_runs_pending / sales_run_update - sales_campaign.py
merges these jobs into the one list and hands back any run_id starting
"job_"), works it with nobody watching, and posts the result back here.

A job asked to repeat is not turned into a scheduled task on the AI side:
DripDrop queues the next copy itself when it comes due, so the user's one
worker is the only schedule there is.

Same rule as sales_campaign.py: never `import flowdrip_app` at the top.
"""
import json
import re
import uuid
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:                                     # pragma: no cover
    ZoneInfo = None

JOB_STATUSES = ("queued", "working", "done", "error", "cancelled")
OPEN_STATUSES = ("queued", "working")
# A job claimed this long ago with nothing posted back is handed out again:
# the session that claimed it died. Shorter than this and a long job would
# be picked up twice by the next hourly check.
STALE_AFTER = timedelta(hours=3)

TZ = {"Mountain": "America/Denver", "Central": "America/Chicago",
      "Eastern": "America/New_York", "Pacific": "America/Los_Angeles"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]


def _ff():
    import sales_campaign
    return sales_campaign._ff()


def _now():
    return datetime.now()


def _iso(dt):
    return dt.isoformat(timespec="seconds")


# -- Storage -------------------------------------------------------------------

def _jobs_dir(owner=None):
    p = _ff()._resolve_user_root(owner) / "AIJobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(job_id, owner=None):
    return _jobs_dir(owner) / ("%s.json" % re.sub(r"[^A-Za-z0-9_-]", "",
                                                   job_id))


def save_job(rec, owner=None):
    rec["updated_at"] = _iso(_now())
    _ff()._atomic_write_text(_path(rec["job_id"], owner),
                             json.dumps(rec, indent=2, default=str))


def load_job(job_id, owner=None):
    p = _path(job_id, owner)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_jobs(owner=None, limit=25):
    out = []
    for p in sorted(_jobs_dir(owner).glob("*.json"),
                    key=lambda q: q.stat().st_mtime, reverse=True)[:limit]:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return out


def _log(rec, msg):
    rec.setdefault("log", []).append(
        "%s  %s" % (_now().strftime("%m-%d %H:%M"), str(msg)[:500]))


# -- Repeats -------------------------------------------------------------------

def _parse_time(text):
    m = re.match(r"\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)?", str(text or ""),
                 re.I)
    if not m:
        return 8, 0
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    ap = (m.group(3) or "").lower()
    if ap == "pm" and h != 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return h, mi


def _run_days(rep):
    cad = str(rep.get("every") or "Once a week").strip().lower()
    if cad == "every day":
        return WEEKDAYS[:5]
    if cad == "every other day":
        days = [d.strip() for d in str(rep.get("days") or "").split(",")]
        days = [d for d in days if d in WEEKDAYS]
        return days or ["Monday", "Wednesday", "Friday"]
    day = str(rep.get("day") or "Monday").strip()
    return [day if day in WEEKDAYS else "Monday"]


def next_due(rep, after):
    """The next slot strictly after `after` (naive server-local time), as a
    naive server-local datetime. Days and time are read in the user's own
    timezone."""
    h, mi = _parse_time(rep.get("time"))
    days = _run_days(rep)
    tz = None
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo(TZ.get(rep.get("tz") or "Mountain",
                                 "America/Denver"))
        except Exception:
            tz = None
    base = after.astimezone(tz) if tz else after
    for i in range(0, 15):
        day = base + timedelta(days=i)
        cand = day.replace(hour=h, minute=mi, second=0, microsecond=0)
        if WEEKDAYS[cand.weekday()] in days and cand > base:
            return cand.astimezone().replace(tzinfo=None) if tz else cand
    return after + timedelta(days=7)


def repeat_text(rep):
    if not rep:
        return ""
    cad = str(rep.get("every") or "Once a week")
    days = _run_days(rep)
    when = (cad.lower() if cad.lower() == "every day" else
            "%s (%s)" % (cad.lower(), ", ".join(days)))
    return "Repeats %s at %s %s" % (when, rep.get("time") or "8:00am",
                                    rep.get("tz") or "Mountain")


# -- Queue ---------------------------------------------------------------------

POST_BACK = """

WHEN YOU ARE DONE
  This job came from DripDrop's queue as job {job_id}. Post the result back
  with sales_run_update, run_id '{job_id}':
    status 'done' and 'result': what you did, in plain words - every
    company, contact, campaign or file you made or changed, with links
    where there are any, and every judgement call you made.
  If you could not finish, post status 'error' and 'error' with the literal
  error instead. Do that before you stop either way: DripDrop shows the
  user this result, and nothing else tells them the job ran."""


def queue_job(owner, title, prompt, routine="", repeat=None):
    """Write one job and return it. `prompt` is the full brief, built with
    the queued flag so it already runs unattended; the post-back block is
    added here because only here is the job id known."""
    jid = "job_%s_%s" % (_now().strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:4])
    rec = {
        "job_id": jid,
        "owner": owner,
        "title": str(title or "AI job")[:200],
        "routine": routine,
        "status": "queued",
        "created_at": _iso(_now()),
        "prompt": prompt,
        "result": "",
        "error": "",
        "log": [],
        "repeat": repeat or None,
        "next_at": _iso(next_due(repeat, _now())) if repeat else None,
        "next_job": None,
    }
    _log(rec, "Queued for your AI")
    save_job(rec, owner)
    return rec


CLAIM = """BEFORE YOU START
  Call sales_run_update with run_id '{job_id}' and status 'working', so
  DripDrop shows the user it is under way and does not hand it out again.

"""


def instructions(rec):
    return (CLAIM.format(job_id=rec["job_id"])
            + (rec.get("prompt") or "").rstrip()
            + POST_BACK.format(job_id=rec["job_id"]))


def _spawn_repeats(owner):
    """Queue the next copy of every repeating job whose slot has come. One
    copy per slot: the parent records the child, so a second sweep in the
    same hour adds nothing."""
    now = _now()
    made = []
    for rec in list_jobs(owner, limit=200):
        rep = rec.get("repeat")
        if not rep or rec.get("next_job") or rec.get("status") == "cancelled":
            continue
        due = rec.get("next_at") or ""
        if not due or due > _iso(now):
            continue
        child = queue_job(owner, rec.get("title"), rec.get("prompt"),
                          rec.get("routine", ""), rep)
        rec["next_job"] = child["job_id"]
        _log(rec, "Next run queued as %s" % child["job_id"])
        save_job(rec, owner)
        made.append(child["job_id"])
    return made


def pending(owner):
    """What the worker should do now, oldest first, in the shape
    sales_runs_pending returns."""
    _spawn_repeats(owner)
    stale = _iso(_now() - STALE_AFTER)
    out = []
    for rec in list_jobs(owner, limit=100):
        st = rec.get("status")
        if st == "queued" or (st == "working"
                              and (rec.get("updated_at") or "") < stale):
            out.append({
                "run_id": rec["job_id"],
                "kind": "ai_job",
                "title": rec.get("title", ""),
                "status": st,
                "created_at": rec.get("created_at"),
                "instructions": instructions(rec),
            })
    out.sort(key=lambda r: r.get("created_at") or "")
    return out


def update_job(owner, job_id, patch):
    rec = load_job(job_id, owner)
    if not rec:
        raise RuntimeError("job %s not found" % job_id)
    if rec.get("status") not in OPEN_STATUSES:
        raise RuntimeError("job %s is already '%s'" % (job_id,
                                                       rec.get("status")))
    patch = dict(patch or {})
    status = str(patch.get("status") or "").strip().lower()
    if status and status not in JOB_STATUSES:
        raise ValueError("status must be one of %s" % ", ".join(JOB_STATUSES))
    if patch.get("result"):
        rec["result"] = str(patch["result"])[:20000]
    logs = patch.get("log") or []
    for line in ([logs] if isinstance(logs, str) else logs):
        _log(rec, line)
    if status == "working":
        rec["status"] = "working"
        _log(rec, "Your AI picked it up")
    elif status == "done":
        rec["status"] = "done"
        _log(rec, "Done")
    elif status == "error":
        rec["status"] = "error"
        rec["error"] = str(patch.get("error") or "the AI reported a failure"
                           )[:2000]
        _log(rec, "Failed: %s" % rec["error"])
    elif status == "cancelled":
        rec["status"] = "cancelled"
        _log(rec, "Cancelled by the AI")
    save_job(rec, owner)
    return summary(rec)


def cancel_job(owner, job_id):
    """The page's Cancel: stops a queued job, and stops a repeating one from
    coming back."""
    rec = load_job(job_id, owner)
    if not rec:
        raise RuntimeError("job %s not found" % job_id)
    if rec.get("status") in OPEN_STATUSES:
        rec["status"] = "cancelled"
    rec["repeat"] = None
    rec["next_at"] = None
    _log(rec, "Cancelled from DripDrop")
    save_job(rec, owner)
    return summary(rec)


def summary(rec):
    return {k: rec.get(k) for k in ("job_id", "title", "status", "result",
                                    "error", "created_at", "updated_at",
                                    "next_at")}


# -- The worker's check-in ------------------------------------------------------

def _worker_path(owner=None):
    return _ff()._resolve_user_root(owner) / "ai_worker.json"


def touch_worker(owner):
    """Called every time the worker asks for work, so the page can say
    whether the user's AI is actually checking in."""
    _ff()._atomic_write_text(_worker_path(owner),
                             json.dumps({"last_seen": _iso(_now())}))


def worker_last_seen(owner=None):
    try:
        p = _worker_path(owner)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")).get("last_seen")
    except Exception:
        pass
    return None

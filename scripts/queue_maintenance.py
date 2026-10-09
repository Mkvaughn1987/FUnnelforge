#!/usr/bin/env python3
"""Daily queue hygiene: empty the body/attachments of terminal (sent/cancelled)
queue items across all users. Those fields are never read again — requeue dedups
on to/subject/step_name (not body), the send path is done, and the History UI
renders metadata only. Keeps scheduled_queue.json small so the single-process
app never blocks on a giant JSON parse. Pending + failed items are left fully
intact (unsent / retriable). Atomic writes; skips malformed files.
"""
import glob, json, os

def maintain(path):
    try:
        q = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(q, list):
        return None
    stripped = 0
    for i in q:
        if i.get("status") in ("sent", "cancelled") and (i.get("body") or i.get("attachments")):
            i["body"] = ""; i["attachments"] = []; stripped += 1
    if not stripped:
        return (0, os.path.getsize(path), os.path.getsize(path))
    before = os.path.getsize(path)
    tmp = path + ".maint.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(q, f)
    os.replace(tmp, path)
    return (stripped, before, os.path.getsize(path))

def main():
    for p in sorted(glob.glob("/opt/dripdrop/data/users/*/scheduled_queue.json")):
        r = maintain(p)
        if r and r[0]:
            u = p.split("/")[-2]
            print(f"[queue_maint] {u}: stripped {r[0]} ({r[1]//1024//1024}MB -> {r[2]//1024//1024}MB)", flush=True)

if __name__ == "__main__":
    main()

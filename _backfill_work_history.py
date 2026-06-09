"""Backfill talents.work_history (last ~3 jobs) for candidates that don't have
it yet. Parallel Haiku extraction; single-writer UPDATEs. Re-runnable."""
import os, sqlite3, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import ats

DB = os.path.join(os.environ.get("DRIPDROP_DATA_DIR", "."), "ats.db")
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT id, resume_text FROM talents "
    "WHERE COALESCE(work_history,'')='' AND LENGTH(COALESCE(resume_text,''))>60"
).fetchall()
con.close()
print(f"to process: {len(rows)}", flush=True)


def work(r):
    return (r["id"], ats.extract_work_history(r["resume_text"]))


t0 = time.time()
done = filled = 0
w = sqlite3.connect(DB)
with ThreadPoolExecutor(max_workers=6) as ex:
    futs = [ex.submit(work, r) for r in rows]
    for fut in as_completed(futs):
        tid, wh = fut.result()
        done += 1
        if wh:
            w.execute("UPDATE talents SET work_history=? WHERE id=?", (wh, tid))
            filled += 1
        if done % 100 == 0:
            w.commit()
            print(f"  {done}/{len(rows)}  filled={filled}  {time.time()-t0:.0f}s", flush=True)
w.commit()
w.close()
print(f"DONE in {time.time()-t0:.0f}s — processed {done}, filled {filled}", flush=True)

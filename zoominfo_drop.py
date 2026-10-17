"""ZoomInfo Drop: a rep's old ZoomInfo exports, merged into one archive.

Reps drop whatever ZoomInfo files they still have (csv, tsv, xlsx, or a zip
of them, any file names). Each file's columns are lined up on one set of
names, people who show up in more than one file are merged field by field
(a cell from one copy and a direct dial from another both survive), and the
result lands in the rep's own contact list, Contacts/ZoomInfo Archive.csv.

That list is an ordinary DripDrop contact list, so it shows on the Contacts
page and feeds the Arena Sales Contacts bank (team_contacts.scan reads
every teammate's Contacts/*.csv), which dedupes across the whole team.

Each drop is logged to ZoomInfo/drops.json for the team progress strip.

Pure file reads/writes on paths it is handed, no app imports, so it is
unit-testable on its own. xlsx is read with the standard library (zip +
XML) because prod has no pandas/openpyxl.
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ARCHIVE_NAME = "ZoomInfo Archive"
ARCHIVE_FILE = ARCHIVE_NAME + ".csv"
LEDGER_DIR = "ZoomInfo"
LEDGER_FILE = "drops.json"
# ZoomInfo Talent candidate exports (Talent_Candidate_Export_...) are job
# seekers, not hiring managers. They are kept, but outside Contacts/ so the
# team bank and BD campaigns never pick them up.
CANDIDATE_FILE = "ZoomInfo Candidates.csv"


def is_candidate_file(name: str) -> bool:
    return "candidate" in Path(name or "").name.lower()

# ZoomInfo's free re-download window on monthly credits (help.zoominfo.com,
# My Lists / My Contacts). Bulk credits get 365 days; reps export on monthly.
FREE_WINDOW_MONTHS = 6

READABLE = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm")
MAX_ZIP_DEPTH = 2

# Canonical column -> header spellings ZoomInfo (and reps renaming things)
# use for it. Matched after folding to lower case, punctuation to spaces and
# a trailing "(...)" dropped. Order matters only inside one list.
CANON = {
    "First Name":        ["first name", "firstname", "first", "fname", "given name", "contact first name"],
    "Last Name":         ["last name", "lastname", "last", "lname", "surname", "family name", "contact last name"],
    "Full Name":         ["full name", "name", "contact name", "person name", "candidate name"],
    "Job Title":         ["job title", "title", "position", "current title", "jobtitle", "contact title"],
    "Management Level":  ["management level", "seniority", "level", "job level"],
    "Job Function":      ["job function", "department", "function", "job department"],
    "Email":             ["email address", "email", "work email", "business email", "e mail", "primary email", "contact email"],
    "Email 2":           ["supplemental email", "secondary email", "other email", "personal email", "email 2"],
    "Direct Phone":      ["direct phone number", "direct phone", "direct dial", "work phone", "office phone", "phone number", "phone", "business phone", "workphone"],
    "Mobile Phone":      ["mobile phone", "mobile", "cell phone", "cell", "mobile number", "mobile phone number", "mobilephone"],
    "Company":           ["company name", "company", "account name", "employer", "organization", "current employer"],
    "Company Phone":     ["company hq phone", "company phone", "hq phone", "main phone"],
    "Website":           ["website", "company domain", "domain", "company website", "url"],
    "LinkedIn":          ["linkedin contact profile url", "linkedin url", "linkedin", "person linkedin url", "contact linkedin", "linkedinpage"],
    "Company LinkedIn":  ["company linkedin url", "company linkedin"],
    "Industry":          ["industry", "primary industry", "company industry", "sub industry"],
    "Employees":         ["employee count", "employees", "company employee count", "headcount", "number of employees", "company headcount"],
    "Revenue":           ["company revenue", "revenue", "annual revenue", "revenue range"],
    "City":              ["person city", "city", "contact city", "mailing city"],
    "State":             ["person state", "state", "contact state", "mailing state", "person state/province", "person state province"],
    "Zip":               ["person zip code", "zip", "postal code", "zip code", "person zip"],
    "Country":           ["person country", "country", "contact country"],
    "Street":            ["person street", "street", "address", "mailing street", "person address"],
    "Company City":      ["company city", "hq city"],
    "Company State":     ["company state", "hq state", "company state/province", "company state province"],
    "Company Street":    ["company street", "company address", "hq street"],
    "Company Zip":       ["company zip code", "company zip", "hq zip"],
    "ZoomInfo Contact ID": ["zoominfo contact id", "contact id", "person id", "zi contact id", "zoominfo person id"],
    "ZoomInfo Company ID": ["zoominfo company id", "company id", "zi company id"],
    "Accuracy Score":    ["contact accuracy score", "accuracy score", "accuracy"],
    "Last Updated":      ["last updated", "last updated date", "date last verified", "updated"],
}


def _fold(h: str) -> str:
    h = str(h or "").strip().lower()
    h = re.sub(r"\s*\(.*?\)\s*$", "", h)
    h = re.sub(r"[\s_\-\./]+", " ", h)
    return h.strip()


_LOOKUP = {_fold(a): canon for canon, aliases in CANON.items() for a in aliases}

# A table is contacts when at least two of these line up.
_SIGNALS = {"First Name", "Last Name", "Full Name", "Email", "Job Title",
            "Company", "Direct Phone", "Mobile Phone", "ZoomInfo Contact ID"}

# The archive's columns. The first ten are DripDrop's own contact-list
# headers (CONTACT_FIELDS in flowdrip_app) so the Contacts page, campaigns
# and the team bank read the file like any other list; the rest keep the
# ZoomInfo detail.
ARCHIVE_COLUMNS = [
    ("Email", "Email"), ("FirstName", "First Name"), ("LastName", "Last Name"),
    ("Company", "Company"), ("JobTitle", "Job Title"),
    ("MobilePhone", "Mobile Phone"), ("WorkPhone", "Direct Phone"),
    ("LinkedInPage", "LinkedIn"), ("City", "City"), ("State", "State"),
    ("Email 2", "Email 2"), ("Management Level", "Management Level"),
    ("Job Function", "Job Function"), ("Company Phone", "Company Phone"),
    ("Website", "Website"), ("Industry", "Industry"), ("Employees", "Employees"),
    ("Revenue", "Revenue"), ("Zip", "Zip"), ("Country", "Country"),
    ("Street", "Street"), ("Company City", "Company City"),
    ("Company State", "Company State"), ("Company Street", "Company Street"),
    ("Company Zip", "Company Zip"), ("Company LinkedIn", "Company LinkedIn"),
    ("ZoomInfo Contact ID", "ZoomInfo Contact ID"),
    ("ZoomInfo Company ID", "ZoomInfo Company ID"),
    ("Accuracy Score", "Accuracy Score"), ("Last Updated", "Last Updated"),
    ("Export Date", "Export Date"), ("Source Files", "Source Files"),
]
_HEADER_OF = {canon: header for header, canon in ARCHIVE_COLUMNS}
_CANON_OF = {header: canon for header, canon in ARCHIVE_COLUMNS}


def canon_header(h: str) -> str:
    """The canonical name for a header, or the header itself."""
    return _LOOKUP.get(_fold(h), str(h or "").strip())


# ── reading files ───────────────────────────────────────────────────────

def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _csv_rows(data: bytes, tab: bool = False) -> list:
    text = _decode(data)
    if tab:
        delim = "\t"
    else:
        # The delimiter that splits the most of the first lines; comma on a
        # tie. (csv.Sniffer trips on a title line above the headers.)
        head = text[:8192].splitlines()[:12]
        delim = max(",\t;|", key=lambda d: (sum(1 for ln in head if d in ln),
                                            sum(ln.count(d) for ln in head), d == ","))
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    return [r for r in reader]


_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return max(n - 1, 0)


def _xlsx_sheets(data: bytes) -> list:
    """[(sheet name, rows as lists of strings)] from an .xlsx, stdlib only."""
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        targets = {}
        if "xl/_rels/workbook.xml.rels" in names:
            rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            for r in rels:
                targets[r.get("Id")] = r.get("Target", "")
        sheets = []
        if "xl/workbook.xml" in names:
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            for sh in wb.iter(f"{{{_NS['m']}}}sheet"):
                tgt = targets.get(sh.get(f"{{{_REL_NS}}}id"), "")
                tgt = tgt.lstrip("/")
                path = tgt if tgt.startswith("xl/") else "xl/" + tgt
                sheets.append((sh.get("name") or "", path))
        if not sheets:
            sheets = [(Path(n).stem, n) for n in sorted(names)
                      if n.startswith("xl/worksheets/") and n.endswith(".xml")]
        for name, path in sheets:
            if path not in names:
                continue
            root = ET.fromstring(z.read(path))
            rows = []
            for row in root.iter(f"{{{_NS['m']}}}row"):
                vals: dict = {}
                for c in row.findall("m:c", _NS):
                    t = c.get("t")
                    v = c.find("m:v", _NS)
                    if t == "s" and v is not None:
                        try:
                            val = shared[int(v.text)]
                        except (ValueError, IndexError, TypeError):
                            val = ""
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{{{_NS['m']}}}t"))
                    else:
                        val = v.text if v is not None and v.text is not None else ""
                    vals[_col_index(c.get("r") or "A")] = val
                if vals:
                    rows.append([vals.get(i, "") for i in range(max(vals) + 1)])
            out.append((name, rows))
    return out


_DATE_PATTERNS = (
    (re.compile(r"(\d{1,2})[-_.](\d{1,2})[-_.](20\d\d)"), ("m", "d", "y")),
    (re.compile(r"(20\d\d)[-_.](\d{1,2})[-_.](\d{1,2})"), ("y", "m", "d")),
)


def date_from_name(name: str) -> str:
    """ZoomInfo stamps exports like Talent_Contact_Export_10-15-2026_14-51-52.
    Returns YYYY-MM-DD or ""."""
    for rx, order in _DATE_PATTERNS:
        m = rx.search(name or "")
        if m:
            parts = dict(zip(order, (int(g) for g in m.groups())))
            try:
                return date(parts["y"], parts["m"], parts["d"]).isoformat()
            except ValueError:
                continue
    return ""


# What makes a file a ZoomInfo export (same two signals as the reps' finder
# script): a ZoomInfo file name anywhere in its path, or 2+ column headers
# only ZoomInfo writes. Anything else (Indeed lists, payroll, a rep's own
# notes) is skipped, so "drag in the whole Downloads folder" stays safe.
_ZI_NAMES = ("talent_candidate_export", "talent_contact_export", "talent_company_export",
             "candidate_export", "contact_export", "company_export", "people_export",
             "zi_contacts", "zi_companies", "zoominfo", "zoom_info", "zoom info", "zi_export",
             "reachout", "discoverorg", "salesos", "talentos", "recruiteros")
_ZI_HEADERS = {"zoominfo contact id", "zoominfo company id", "zoominfo person id",
               "zoominfo talent url", "direct phone number", "company hq phone",
               "supplemental email", "management level", "job function",
               "linkedin contact profile url", "contact accuracy score", "sic code 1",
               "naics code 1", "employee count", "company revenue", "person street",
               "company street", "person city", "person state", "person zip code",
               "company headcount", "primary industry"}


def is_zoominfo(name: str, raw_headers: list) -> bool:
    low = (name or "").lower().replace("-", "_")
    if any(n in low for n in _ZI_NAMES):
        return True
    return len({_fold(h) for h in raw_headers} & _ZI_HEADERS) >= 2


def _table(label: str, rows: list, export_date: str) -> dict | None:
    """Find the header row (first row with 2+ known contact columns within
    the first 10) and return {"label", "headers", "rows", "export_date"}."""
    for i, row in enumerate(rows[:10]):
        headers = [canon_header(h) for h in row]
        if len(set(headers) & _SIGNALS) >= 2:
            body = [r for r in rows[i + 1:] if any(str(x).strip() for x in r)]
            return {"label": label, "headers": headers, "rows": body, "raw_headers": row,
                    "export_date": export_date,
                    "candidates": is_candidate_file(label.split(" [")[0])}
    return None


def read_upload(name: str, data: bytes, when: str = "", _depth: int = 0) -> tuple:
    """(tables, skipped). tables: contact tables found in the file (a zip
    yields one per readable member). skipped: [(file name, plain reason)].
    Never raises."""
    tables, skipped = [], []
    low = (name or "").lower()
    base = Path(name or "file").name
    when = date_from_name(base) or when
    try:
        if low.endswith(".zip"):
            if _depth >= MAX_ZIP_DEPTH:
                return [], [(base, "a zip inside a zip inside a zip; unzip it first")]
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for info in z.infolist():
                    if info.is_dir() or Path(info.filename).name.startswith(("~$", ".")):
                        continue
                    if "__MACOSX" in info.filename:
                        continue
                    try:
                        stamp = date(*info.date_time[:3]).isoformat()
                    except Exception:
                        stamp = ""
                    t, s = read_upload(f"{base}/{info.filename}", z.read(info),
                                       stamp, _depth + 1)
                    tables += t
                    skipped += s
            return tables, skipped
        if low.endswith((".csv", ".txt")):
            found = [_table(base, _csv_rows(data), when)]
        elif low.endswith(".tsv"):
            found = [_table(base, _csv_rows(data, tab=True), when)]
        elif low.endswith((".xlsx", ".xlsm")):
            found = [_table(f"{base} [{sh}]" if sh else base, rows, when)
                     for sh, rows in _xlsx_sheets(data)]
        elif low.endswith(".xls"):
            return [], [(base, "old Excel 97-2003 file; open it in Excel, Save As .xlsx, and drop it again")]
        else:
            return [], [(base, "not a spreadsheet")]
    except zipfile.BadZipFile:
        return [], [(base, "the file is damaged or not really a zip/xlsx")]
    except Exception as e:
        return [], [(base, f"could not be read ({type(e).__name__})")]
    found = [t for t in found if t]
    if not found:
        return [], [(base, "no contact columns (name, email, title, company...) found")]
    found = [t for t in found if is_zoominfo(name, t["raw_headers"])]
    if not found:
        return [], [(base, "doesn't look like a ZoomInfo export, left out")]
    return found, []


# ── records and merging ─────────────────────────────────────────────────

def _clean(v) -> str:
    v = str(v if v is not None else "").strip()
    return "" if v.lower() in ("nan", "none", "null", "n/a", "-") else v


def table_records(table: dict) -> list:
    """Rows of one table as canonical dicts. Rows with no name, email or
    phone are dropped."""
    out = []
    headers = table["headers"]
    for row in table["rows"]:
        rec: dict = {}
        for h, v in zip(headers, row):
            v = _clean(v)
            if v and h in _HEADER_OF and not rec.get(h):
                rec[h] = v
        if rec.get("Full Name") and not (rec.get("First Name") or rec.get("Last Name")):
            parts = rec["Full Name"].split(" ", 1)
            rec["First Name"] = parts[0]
            if len(parts) > 1:
                rec["Last Name"] = parts[1]
        rec.pop("Full Name", None)
        if rec.get("Email"):
            rec["Email"] = rec["Email"].lower()
            if "@" not in rec["Email"]:
                rec.pop("Email")
        if not rec.get("State") and rec.get("Company State"):
            rec["State"] = rec["Company State"]
        if not (rec.get("Email") or rec.get("First Name") or rec.get("Last Name")
                or rec.get("Mobile Phone") or rec.get("Direct Phone")):
            continue
        rec["Source Files"] = table["label"]
        if table.get("export_date"):
            rec["Export Date"] = table["export_date"]
        out.append(rec)
    return out


def _digits(v: str) -> str:
    d = re.sub(r"\D", "", v or "")
    return d[-10:] if len(d) >= 10 else ""


def person_keys(rec: dict) -> list:
    """Every key that identifies this person, strongest first: email,
    ZoomInfo contact ID, phone + name, name + company. Two records sharing
    any key are the same person."""
    keys = []
    em = (rec.get("Email") or "").lower()
    if "@" in em:
        keys.append("e:" + em)
    zid = (rec.get("ZoomInfo Contact ID") or "").strip()
    if zid:
        keys.append("z:" + zid)
    name = " ".join(p for p in (rec.get("First Name", ""), rec.get("Last Name", "")) if p).lower()
    name = re.sub(r"\s+", " ", name).strip()
    for p in ("Mobile Phone", "Direct Phone"):
        d = _digits(rec.get(p, ""))
        if d and name:
            keys.append(f"t:{d}|{name}")
    co = re.sub(r"\s+", " ", (rec.get("Company") or "").lower()).strip()
    if name and co:
        keys.append(f"n:{name}|{co}")
    return keys


def _fill(rec: dict) -> int:
    return sum(1 for k, v in rec.items() if v and k not in ("Source Files", "Export Date"))


def _absorb(into: dict, other: dict) -> None:
    for k, v in other.items():
        if not v:
            continue
        if k == "Source Files":
            have = [s for s in (into.get(k) or "").split(" + ") if s]
            for s in v.split(" + "):
                if s and s not in have:
                    have.append(s)
            into[k] = " + ".join(have)
        elif k == "Export Date":
            into[k] = min(into[k], v) if into.get(k) else v
        elif not into.get(k):
            into[k] = v


def merge(existing: list, incoming: list) -> tuple:
    """Fold incoming records into existing ones. Returns (merged list,
    stats {"rows", "added", "merged"}); "added" = people not in existing."""
    people = [dict(r) for r in existing]
    index: dict = {}
    for i, r in enumerate(people):
        for k in person_keys(r):
            index.setdefault(k, i)
    added = merged = 0
    for rec in sorted(incoming, key=_fill, reverse=True):
        hit = next((index[k] for k in person_keys(rec) if k in index), None)
        if hit is None:
            people.append(dict(rec))
            hit = len(people) - 1
            added += 1
        else:
            _absorb(people[hit], rec)
            merged += 1
        for k in person_keys(people[hit]):
            index.setdefault(k, hit)
    return people, {"rows": len(incoming), "added": added, "merged": merged}


# ── the archive file ────────────────────────────────────────────────────

def archive_path(user_root) -> Path:
    return Path(user_root) / "Contacts" / ARCHIVE_FILE


def candidates_path(user_root) -> Path:
    return Path(user_root) / LEDGER_DIR / CANDIDATE_FILE


def load_archive(user_root, path: Path | None = None) -> list:
    p = path or archive_path(user_root)
    if not p.is_file():
        return []
    try:
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return []
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        rec = {}
        for h, v in row.items():
            canon = _CANON_OF.get(h or "")
            if canon and _clean(v):
                rec[canon] = _clean(v)
        if rec:
            out.append(rec)
    return out


def archive_csv(records: list) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([h for h, _ in ARCHIVE_COLUMNS])
    for r in sorted(records, key=lambda r: ((r.get("Company") or "").lower(),
                                            (r.get("Last Name") or "").lower())):
        w.writerow([r.get(c, "") for _, c in ARCHIVE_COLUMNS])
    return buf.getvalue()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def bank_key(rec: dict) -> str:
    """The key team_contacts.norm_contact gives this person, so a drop can
    say who the team bank already has."""
    em = (rec.get("Email") or "").lower()
    if "@" in em:
        return em
    name = " ".join(p for p in (rec.get("First Name", ""), rec.get("Last Name", "")) if p)
    name = re.sub(r"\s+", " ", name).strip().lower()
    for p in ("Mobile Phone", "Direct Phone"):
        d = _digits(rec.get(p, ""))
        if d and name:
            return f"tel:{d}|{name}"
    return ""


def drop(user_root, uploads: list, bank_keys: set | None = None,
         today: date | None = None) -> dict:
    """Read every uploaded (name, bytes), merge into the rep's archive, save
    it, log the drop. bank_keys: the team bank's keys before this drop, so
    the receipt can split new-to-the-team from already-known people.
    Returns the receipt."""
    today = today or date.today()
    tables, skipped = [], []
    for name, data in uploads:
        t, s = read_upload(name, data)
        tables += t
        skipped += s
    incoming, cands = [], []
    files = []
    for t in tables:
        recs = table_records(t)
        (cands if t.get("candidates") else incoming).extend(recs)
        files.append({"name": t["label"], "rows": len(recs),
                      "export_date": t.get("export_date", ""),
                      "candidates": bool(t.get("candidates"))})
    unique_in_drop, _ = merge([], incoming)
    before = load_archive(user_root)
    after, stats = merge(before, incoming)
    if incoming:
        _atomic_write(archive_path(user_root), archive_csv(after))
    n_cands = 0
    if cands:
        c_before = load_archive(user_root, candidates_path(user_root))
        c_after, c_stats = merge(c_before, cands)
        _atomic_write(candidates_path(user_root), archive_csv(c_after))
        n_cands = len(merge([], cands)[0])
    known = new = 0
    if bank_keys is not None:
        for r in unique_in_drop:
            k = bank_key(r)
            if k and k in bank_keys:
                known += 1
            else:
                new += 1
    receipt = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "files": files,
        "skipped": [{"name": n, "reason": r} for n, r in skipped],
        "rows": len(incoming),
        "people": len(unique_in_drop),
        "added": stats["added"],
        "merged": stats["merged"],
        "archive_total": len(after),
        "candidates": n_cands,
        "already_in_bank": known if bank_keys is not None else None,
        "new_to_team": new if bank_keys is not None else None,
    }
    if files:
        _log(user_root, receipt)
    return receipt


# ── ledger + progress ───────────────────────────────────────────────────

def ledger_path(user_root) -> Path:
    return Path(user_root) / LEDGER_DIR / LEDGER_FILE


def load_ledger(user_root) -> list:
    try:
        data = json.loads(ledger_path(user_root).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _log(user_root, receipt: dict) -> None:
    rows = load_ledger(user_root)
    rows.append(receipt)
    _atomic_write(ledger_path(user_root), json.dumps(rows[-500:], indent=1))


def rep_progress(user_root) -> dict:
    """One rep's totals for the team strip."""
    led = load_ledger(user_root)
    dates = [f["export_date"] for r in led for f in r.get("files", []) if f.get("export_date")]
    return {
        "drops": len(led),
        "files": sum(len(r.get("files", [])) for r in led),
        "people": len(load_archive(user_root)) if led else 0,
        "candidates": len(load_archive(user_root, candidates_path(user_root))) if led else 0,
        "last_drop": max((r.get("date", "") for r in led), default="")[:10],
        "oldest_export": min(dates, default=""),
        "newest_export": max(dates, default=""),
    }


def free_window_start(today: date | None = None) -> date:
    """Earliest export date ZoomInfo still re-downloads free (monthly
    credits): today minus FREE_WINDOW_MONTHS."""
    today = today or date.today()
    m = today.month - FREE_WINDOW_MONTHS
    y = today.year
    while m < 1:
        m += 12
        y -= 1
    day = min(today.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)

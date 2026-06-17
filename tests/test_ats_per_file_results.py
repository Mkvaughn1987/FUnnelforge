"""Per-file results from a bulk résumé import.

The bulk uploader used to report only aggregate counts ("added 5, skipped 3"),
so a user uploading 20 résumés couldn't see WHICH file was added and which was
a duplicate. ingest_resumes now also returns a per-file `files` list — one
record per uploaded file with its filename, parsed name, and outcome — so the
UI can show a grouped status list.
"""
import sqlite3
import sys

import pytest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS talents (
  id INTEGER PRIMARY KEY,
  first_name TEXT, last_name TEXT, email TEXT, phone TEXT,
  city TEXT, state TEXT, current_title TEXT, current_employer TEXT,
  years_experience TEXT, seniority TEXT, skills TEXT, summary TEXT,
  status TEXT DEFAULT 'Candidate', source_file TEXT, resume_text TEXT,
  added_by TEXT, created_at TEXT, updated_at TEXT,
  owner_email TEXT DEFAULT '', notes TEXT DEFAULT '', work_history TEXT DEFAULT '',
  lat REAL, lng REAL
);
CREATE VIRTUAL TABLE IF NOT EXISTS talents_fts USING fts5(
  first_name, last_name, current_title, current_employer, skills,
  summary, city, state, resume_text, content='talents', content_rowid='id'
);
"""

_SAMPLE = (
    "JANE DOE\nSenior Project Manager\nDenver, CO\njane.doe@example.com · 555-1234\n\n"
    "EXPERIENCE\nSenior Project Manager, Acme Construction, 2018-Present\n"
    "Led commercial builds, managed budgets and subcontractor schedules.\n"
    "SKILLS: scheduling, budgeting, OSHA, Procore.\n"
)

_OWNER = "elizabeth.simonov@arenastaffing.net"


@pytest.fixture
def ats_mod(tmp_path, monkeypatch):
    db = tmp_path / "ats.db"
    con = sqlite3.connect(str(db))
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    monkeypatch.setenv("ATS_DB_PATH", str(db))
    if "ats" in sys.modules:
        del sys.modules["ats"]
    import ats
    # Avoid the network: the AI parser returns a fixed structured record.
    monkeypatch.setattr(ats, "_ai_parse_resume", lambda text: {
        "first_name": "Jane", "last_name": "Doe", "email": "jane.doe@example.com",
        "phone": "555-1234", "city": "Denver", "state": "CO",
        "current_title": "Senior Project Manager", "current_employer": "Acme Construction",
        "key_skills": ["scheduling", "budgeting"], "summary": "Commercial PM.",
    })
    return ats


def test_returns_one_file_record_per_uploaded_file(ats_mod):
    files = [("jane_doe.txt", _SAMPLE.encode("utf-8"))]
    stats = ats_mod.ingest_resumes(files, _OWNER, "Elizabeth", rebuild=True)
    assert isinstance(stats.get("files"), list), "stats must include a per-file `files` list"
    assert len(stats["files"]) == 1
    rec = stats["files"][0]
    assert rec["filename"] == "jane_doe.txt"
    assert rec["status"] == "added"
    assert rec["name"] == "Jane Doe"


def test_duplicate_file_is_marked_dup_not_added(ats_mod):
    # Two identical résumés in one batch: first lands as added, the second
    # is recognised as already-on-file.
    files = [
        ("first.txt", _SAMPLE.encode("utf-8")),
        ("again.txt", _SAMPLE.encode("utf-8")),
    ]
    stats = ats_mod.ingest_resumes(files, _OWNER, "Elizabeth", rebuild=True)
    by_name = {f["filename"]: f for f in stats["files"]}
    statuses = {f["status"] for f in stats["files"]}
    assert by_name["first.txt"]["status"] == "added"
    # The second is either merged (kept fuller record) or a plain dup — both
    # mean "already on file", never a second add.
    assert by_name["again.txt"]["status"] in ("dup", "merged")
    assert "added" in statuses


def test_unreadable_file_is_skipped_with_reason(ats_mod):
    # Too little extractable text → can't read it (e.g. a scanned image PDF).
    files = [("blank.txt", b"hi")]
    stats = ats_mod.ingest_resumes(files, _OWNER, "Elizabeth", rebuild=True)
    rec = stats["files"][0]
    assert rec["filename"] == "blank.txt"
    assert rec["status"] == "scanned"

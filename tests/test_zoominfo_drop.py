"""ZoomInfo Drop: reps' old ZoomInfo exports merged into one archive list
that feeds the Shared Arena Contacts bank."""
import io
import json
import zipfile
from datetime import date

import pytest

import team_contacts as tcx
import zoominfo_drop as zd

ZI_HEADERS = ("ZoomInfo Contact ID,First Name,Last Name,Job Title,Management Level,"
              "Email Address,Direct Phone Number,Mobile phone,Company Name,"
              "Company HQ Phone,Person City,Person State,LinkedIn Contact Profile URL\n")


def _csv(*rows) -> bytes:
    return (ZI_HEADERS + "".join(r + "\n" for r in rows)).encode("utf-8")


def _xlsx(rows) -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contacts"
    for r in rows:
        ws.append(r)
    other = wb.create_sheet("Notes")
    other.append(["just some notes"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _zip(files: dict, stamp=(2026, 5, 2, 9, 0, 0)) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=stamp)
            z.writestr(info, data)
    return buf.getvalue()


# ── reading ─────────────────────────────────────────────────────────────

def test_canon_headers_cover_zoominfo_spellings():
    assert zd.canon_header("Email Address") == "Email"
    assert zd.canon_header("Direct Phone Number") == "Direct Phone"
    assert zd.canon_header("Mobile phone") == "Mobile Phone"
    assert zd.canon_header("Person State/Province") == "State"
    assert zd.canon_header("Revenue (in 000s USD)") == "Revenue"
    assert zd.canon_header("LinkedIn Contact Profile URL") == "LinkedIn"
    assert zd.canon_header("Company HQ Phone") == "Company Phone"
    assert zd.canon_header("Something Else") == "Something Else"


def test_csv_with_any_name_is_read_and_dated_from_the_file_name():
    tables, skipped = zd.read_upload("leads_final_v3.csv", _csv("1,Ann,Bell,VP Ops,VP,ann@acme.com,,,Acme,,Denver,CO,"))
    assert not skipped and len(tables) == 1 and tables[0]["export_date"] == ""
    tables, _ = zd.read_upload("Talent_Contact_Export_10-15-2026_14-51-52.csv",
                               _csv("1,Ann,Bell,VP Ops,VP,ann@acme.com,,,Acme,,Denver,CO,"))
    assert tables[0]["export_date"] == "2026-10-15"


def test_semicolon_and_header_row_below_a_title_line():
    data = ("ZoomInfo export\nFirst Name;Last Name;Email;Company\nAnn;Bell;ann@acme.com;Acme\n").encode()
    tables, _ = zd.read_upload("zoominfo_x.csv", data)
    recs = zd.table_records(tables[0])
    assert recs == [{"First Name": "Ann", "Last Name": "Bell", "Email": "ann@acme.com",
                     "Company": "Acme", "Source Files": "zoominfo_x.csv"}]


def test_contact_lists_that_are_not_zoominfo_are_left_out():
    data = b"First Name,Last Name,Email,Company\nAnn,Bell,ann@acme.com,Acme\n"
    tables, skipped = zd.read_upload("indeed_applicants.csv", data)
    assert tables == [] and "ZoomInfo" in skipped[0][1]
    # a ZoomInfo name anywhere on the path is enough (a zip called ZoomInfo...)
    z = _zip({"list.csv": data})
    assert len(zd.read_upload("My ZoomInfo Exports.zip", z)[0]) == 1
    assert zd.read_upload("stuff.zip", z)[0] == []


def test_xlsx_read_without_pandas_and_non_contact_sheets_skipped():
    data = _xlsx([["First Name", "Last Name", "Email Address", "Company Name", "Mobile phone",
                   "Management Level", "Job Function"],
                  ["Cal", "Dunn", "Cal@Bolt.com", "Bolt Mfg", "(303) 555-0102", "Manager", "Ops"],
                  [None, None, None, None, None, None, None]])
    tables, skipped = zd.read_upload("export.xlsx", data)
    assert not skipped and len(tables) == 1 and tables[0]["label"] == "export.xlsx [Contacts]"
    recs = zd.table_records(tables[0])
    assert recs[0]["Email"] == "cal@bolt.com" and recs[0]["Mobile Phone"] == "(303) 555-0102"
    assert len(recs) == 1


def test_zip_of_a_folder_with_junk_and_old_excel():
    data = _zip({
        "ZoomInfo-Exports/a.csv": _csv("1,Ann,Bell,VP Ops,VP,ann@acme.com,,,Acme,,Denver,CO,"),
        "ZoomInfo-Exports/resume.pdf": b"%PDF-1.4",
        "ZoomInfo-Exports/old.xls": b"\xd0\xcf\x11\xe0",
        "ZoomInfo-Exports/budget.csv": b"Month,Spend\nJan,10\n",
        "__MACOSX/._a.csv": b"junk",
    })
    tables, skipped = zd.read_upload("rep.zip", data)
    assert [t["label"] for t in tables] == ["a.csv"]
    assert tables[0]["export_date"] == "2026-05-02"         # zip entry date
    reasons = {n: r for n, r in skipped}
    assert "not a spreadsheet" in reasons["resume.pdf"]
    assert "Save As .xlsx" in reasons["old.xls"]
    assert "no contact columns" in reasons["budget.csv"]


def test_damaged_file_never_raises():
    assert zd.read_upload("bad.xlsx", b"not a zip")[1][0][1].startswith("the file is damaged")


# ── merging ─────────────────────────────────────────────────────────────

def test_same_person_across_files_merges_field_by_field():
    a = zd.table_records(zd.read_upload("a.csv", _csv(
        "77,Ann,Bell,VP,,ann@acme.com,303-555-0100,,Acme,,Denver,CO,"))[0][0])
    b = zd.table_records(zd.read_upload("b.csv", _csv(
        "77,Ann,Bell,VP of Operations,VP,,,(720) 555-0199,Acme,,,,https://linkedin.com/in/ann"))[0][0])
    people, st = zd.merge([], a + b)
    assert len(people) == 1 and st == {"rows": 2, "added": 1, "merged": 1}
    p = people[0]
    assert p["Email"] == "ann@acme.com" and p["Direct Phone"] == "303-555-0100"
    assert p["Mobile Phone"] == "(720) 555-0199" and p["LinkedIn"].endswith("/ann")
    assert set(p["Source Files"].split(" + ")) == {"a.csv", "b.csv"}


def test_phone_alone_does_not_merge_two_people_on_a_main_line():
    recs = [{"First Name": "Ann", "Last Name": "Bell", "Direct Phone": "303-555-0100", "Company": "Acme"},
            {"First Name": "Bo", "Last Name": "Cole", "Direct Phone": "303-555-0100", "Company": "Acme"}]
    assert len(zd.merge([], recs)[0]) == 2


def test_name_and_company_or_phone_match_people_without_email():
    recs = [{"First Name": "Ann", "Last Name": "Bell", "Company": "Acme", "Mobile Phone": "3035550100"},
            {"First Name": "ann", "Last Name": "bell", "Company": "ACME", "Job Title": "VP"},
            {"First Name": "Ann", "Last Name": "Bell", "Company": "Acme Inc", "Mobile Phone": "+1 303 555 0100"}]
    people, _ = zd.merge([], recs)
    assert len(people) == 1 and people[0]["Job Title"] == "VP"


# ── drop: archive + ledger + bank ───────────────────────────────────────

def test_drop_writes_archive_list_and_second_drop_merges(tmp_path):
    root = tmp_path / "users" / "mike_at_arena_net"
    rc = zd.drop(root, [("one.csv", _csv(
        "1,Ann,Bell,VP Ops,VP,ann@acme.com,303-555-0100,,Acme,,Denver,CO,",
        "2,Bo,Cole,Controller,,,,(720) 555-0111,Acme,,,,"))], bank_keys=set())
    assert rc["people"] == 2 and rc["added"] == 2 and rc["new_to_team"] == 2
    text = zd.archive_path(root).read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith(
        "Email,FirstName,LastName,Company,JobTitle,MobilePhone,WorkPhone,LinkedInPage,City,State,")
    rc2 = zd.drop(root, [("Contact_Export_2026-04-01.csv", _csv(
        "1,Ann,Bell,VP Ops,VP,ann@acme.com,,(720) 555-0123,Acme,,Denver,CO,"))],
        bank_keys={"ann@acme.com"})
    assert rc2["added"] == 0 and rc2["merged"] == 1 and rc2["already_in_bank"] == 1
    arch = zd.load_archive(root)
    assert len(arch) == 2
    ann = next(r for r in arch if r.get("Email") == "ann@acme.com")
    assert ann["Mobile Phone"] == "(720) 555-0123" and ann["Direct Phone"] == "303-555-0100"
    assert ann["Export Date"] == "2026-04-01"
    prog = zd.rep_progress(root)
    assert prog["drops"] == 2 and prog["files"] == 2 and prog["people"] == 2
    assert prog["oldest_export"] == "2026-04-01"


def test_talent_candidate_exports_stay_out_of_the_bank(tmp_path):
    users = tmp_path / "users"
    root = users / "mike_at_arena_net"
    data = ('"ZoomInfo person ID","First name","Last name","Mobile phone","Personal email",'
            '"Work email","Job title","Company name","Company headcount"\n'
            '9,Cara,Diaz,303-555-0170,cara@gmail.com,cara@oldjob.com,Welder,OldJob,120\n').encode()
    rc = zd.drop(root, [("Talent_Candidate_Export_10-15-2026_14-51-52.csv", data)], bank_keys=set())
    assert rc["candidates"] == 1 and rc["people"] == 0 and rc["files"][0]["candidates"]
    assert not zd.archive_path(root).exists()
    cand = zd.load_archive(root, zd.candidates_path(root))
    assert cand[0]["Email"] == "cara@oldjob.com" and cand[0]["Email 2"] == "cara@gmail.com"
    assert cand[0]["ZoomInfo Contact ID"] == "9" and cand[0]["Employees"] == "120"
    assert tcx.scan(users, "mike@arena.net")["contacts"] == []
    assert zd.rep_progress(root)["candidates"] == 1


def test_empty_or_junk_drop_writes_nothing(tmp_path):
    rc = zd.drop(tmp_path, [("notes.pdf", b"x")], bank_keys=set())
    assert rc["files"] == [] and rc["skipped"][0]["name"] == "notes.pdf"
    assert not zd.archive_path(tmp_path).exists() and zd.load_ledger(tmp_path) == []


def test_archive_feeds_the_team_bank_with_phone_only_people(tmp_path):
    users = tmp_path / "users"
    zd.drop(users / "mike_at_arena_net", [("a.csv", _csv(
        "1,Ann,Bell,VP Ops,VP,ann@acme.com,,,Acme,,Denver,CO,",
        "2,Bo,Cole,Controller,,,,(720) 555-0111,Acme,,,,"))], bank_keys=set())
    zd.drop(users / "sarah_at_arena_net", [("b.csv", _csv(
        "1,Ann,Bell,VP Ops,VP,ANN@acme.com,,,Acme,,Denver,CO,"))], bank_keys=set())
    bank = tcx.scan(users, "mike@arena.net")
    by = {c["key"]: c for c in bank["contacts"]}
    assert set(by) == {"ann@acme.com", "tel:7205550111|bo cole"}
    assert by["ann@acme.com"]["reps"] == ["mike_at_arena_net", "sarah_at_arena_net"]
    assert by["tel:7205550111|bo cole"]["email"] == ""
    rows = tcx.group_by_company(bank["contacts"])
    assert len(rows) == 1 and rows[0]["domains"] == ["acme.com"]
    assert zd.bank_key(zd.load_archive(users / "mike_at_arena_net")[1]) in by


def test_norm_contact_phone_fallback_needs_a_name():
    assert tcx.norm_contact({"phone_mobile": "303-555-0100"}) is None
    n = tcx.norm_contact({"FirstName": "Bo", "LastName": "Cole", "WorkPhone": "303.555.0100"})
    assert n["key"] == "tel:3035550100|bo cole" and n["domain"] == ""
    assert tcx.norm_contact({"email": "A@b.com"})["key"] == "a@b.com"


def test_free_window_start():
    assert zd.free_window_start(date(2026, 10, 16)) == date(2026, 4, 16)
    assert zd.free_window_start(date(2026, 8, 31)) == date(2026, 2, 28)
    assert zd.free_window_start(date(2026, 3, 5)) == date(2025, 9, 5)


# ── app wiring ──────────────────────────────────────────────────────────

def test_sidebar_and_titles_carry_the_page():
    import flowdrip_app as fa
    assert ("zidrop", "ZoomInfo Drop", "zoominfo_drop") in dict(fa.SIDEBAR_NAV)["ARENA TEAM"]
    assert fa.SIDEBAR_PAGE_ROW["zoominfo_drop"] == "zidrop"
    assert fa.SIDEBAR_TITLES["zoominfo_drop"] == "ZoomInfo Drop"
    assert "zidrop" in fa._SIDEBAR_ICONS
    assert any(page == "zoominfo_drop" for _, _, page in fa.SALES_NAV)
    assert "fd-zd" in fa._zd_css()


def _page_text(root) -> str:
    bits = []
    for el in root.descendants():
        for attr in ("text", "content"):
            v = getattr(el, attr, None)
            if isinstance(v, str):
                bits.append(v)
    return "\n".join(bits)


def test_page_renders_with_team_progress(with_user):
    import flowdrip_app as fa
    from nicegui import ui
    users = fa._BASE_DATA_DIR / "users"
    zd.drop(users / "sarah_at_example_com", [("a.csv", _csv(
        "1,Ann,Bell,VP Ops,VP,ann@acme.com,,,Acme,,Denver,CO,"))], bank_keys=set())
    (users / "tester_at_example_com").mkdir(parents=True, exist_ok=True)
    s = fa.AppState()
    s._user_email = "tester@example.com"
    with ui.card() as card:
        fa.p_zoominfo_drop(s, lambda: None)
    text = _page_text(card)
    assert "ZoomInfo Drop" in text and "My Contacts" in text
    assert "Team progress" in text and "<td>1</td>" in text
    assert "Still to drop" in text
    assert any(isinstance(e, ui.upload) for e in card.descendants())

"""ThriveModal Phase 1 — firmographic targeting helpers.

Twenty-five tests in the five groups the Phase 1 handoff calls for
(docs/HANDOFF-thrivemodal-phase1.md, "Tests Phase 1 requires").

These are written against the SPEC, not against the code: the load-bearing
assertions are the negative ones. Phase 1 changes the shape of contact data
and adds pure helpers; it must not change one observable thing about Arena.
Group 5 is the one that matters most — if it ever goes red, the splice has
leaked out of its lane.

Two places where the shipped implementation is wider than the spec text, both
deliberate and both asserted here in their real form:

  * The spec says "append 4 optional columns"; the build appends TEN
    (TARGETING_FIELDS), because a hiring signal that cannot say what kind of
    signal it is, where it came from and when is not repeatable to a prospect.
    So the widened header is 20 columns, not 14.
  * "load_contacts output byte-identical for a 10-column CSV" cannot be
    literally true — every contact dict now carries the ten targeting keys.
    Test 22 asserts the honest form: the ten original keys are unchanged
    value-for-value, and every added key is the empty string.
"""
import csv
import io
import json
import re
import ast

import pytest


# NEVER import flowdrip_app at module level (see tests/conftest.py).

@pytest.fixture
def fa(isolated_appdata, with_user, monkeypatch):
    """flowdrip_app with per-user paths sandboxed and the funnelforge_core
    fast path disabled, so queue/campaign reads take the JSON fallback."""
    import flowdrip_app as _fa
    monkeypatch.setattr(_fa, "_FUNNELFORGE_OK", False)
    monkeypatch.setattr(_fa, "_ffc", None)
    _fa._cache_campaigns.invalidate()
    _fa._cache_queue.invalidate()
    _fa._cache_contacts.invalidate() if hasattr(_fa, "_cache_contacts") else None
    yield _fa
    _fa._cache_campaigns.invalidate()
    _fa._cache_queue.invalidate()


# ── helpers ────────────────────────────────────────────────────────────────

_LEGACY_HEADER = ["Email", "FirstName", "LastName", "Company", "JobTitle",
                  "MobilePhone", "WorkPhone", "LinkedInPage", "City", "State"]

_LEGACY_ROW = ["dana@acme-logistics.com", "Dana", "Reyes", "Acme Logistics, Inc.",
               "Director of Operations", "555-0100", "555-0101",
               "linkedin.com/in/danareyes", "Denver", "CO"]

# What load_contacts() returned for _LEGACY_ROW before Phase 1 landed.
_PRE_PHASE1_RECORD = {
    "email": "dana@acme-logistics.com",
    "first_name": "Dana",
    "last_name": "Reyes",
    "company": "Acme Logistics, Inc.",
    "title": "Director of Operations",
    "phone_mobile": "555-0100",
    "phone_office": "555-0101",
    "linkedin": "linkedin.com/in/danareyes",
    "city": "Denver",
    "state": "CO",
}


def _write_csv(path, header, rows):
    """Write a CSV the way a real import would, terminators and all."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(buf.getvalue())


def _contact(email, **kw):
    """An in-memory contact in the snake_case key style load_contacts emits."""
    base = {"email": email, "first_name": "X", "last_name": "Y", "company": "",
            "title": "", "phone_mobile": "", "phone_office": "", "linkedin": "",
            "city": "", "state": ""}
    base.update(kw)
    return base


def _seed_campaigns(fa, camps):
    """camps: [{"name":..., "status":...}, ...]"""
    d = fa._user_campaigns_dir()
    d.mkdir(parents=True, exist_ok=True)
    for c in camps:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", c["name"])
        (d / f"{safe}.json").write_text(json.dumps(c), encoding="utf-8")
    fa._cache_campaigns.invalidate()


def _seed_queue(fa, items):
    qp = fa._user_queue_path()
    qp.parent.mkdir(parents=True, exist_ok=True)
    qp.write_text(json.dumps(items), encoding="utf-8")
    fa._cache_queue.invalidate()


# ═══════════════════════════════════════════════════════════════════════════
#  GROUP 1 — CSV back-compat (tests 1-5)
# ═══════════════════════════════════════════════════════════════════════════

def test_01_ten_column_csv_still_loads_with_targeting_empty(fa):
    """A contacts.csv written before Phase 1 loads, and the new fields are
    empty strings — never missing keys, never None."""
    _write_csv(fa._user_contacts_csv_path(), _LEGACY_HEADER, [_LEGACY_ROW])

    got = fa.load_contacts()

    assert len(got) == 1
    rec = got[0]
    for key, val in _PRE_PHASE1_RECORD.items():
        assert rec[key] == val, key
    for col in fa.TARGETING_FIELDS:
        snake = fa._TARGETING_KEYS[col]
        assert snake in rec, f"{snake} missing — callers must not KeyError"
        assert rec[snake] == "", f"{snake} should be blank on a legacy CSV"


def test_02_widened_csv_round_trips(fa):
    """Write firmographics out, read them back, get the same values.

    The spec calls this the "14-column" case; the shipped column set is ten
    targeting columns, so the widened file is twenty columns wide."""
    contacts = [_contact(
        "dana@acme-logistics.com", first_name="Dana", last_name="Reyes",
        company="Acme Logistics, Inc.", title="Director of Operations",
        industry="Transportation", company_size="201-500",
        job_function="Supply Chain", seniority="Director",
        company_domain="acme-logistics.com", company_id="ZI-12345",
        signal_type="hiring", signal_description="Opened a Denver dock",
        signal_source_url="https://example.com/news/1", signal_date="2026-08-01")]

    text = fa._contacts_csv_text(contacts, fa._CONTACT_COLMAP_SNAKE)
    header = text.splitlines()[0].split(",")
    assert header == fa.CONTACT_FIELDS_ALL
    assert len(header) == 20

    path = fa._user_contacts_csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fa._atomic_write_csv_text(path, text)

    back = fa.load_contacts()
    assert len(back) == 1
    for key, val in contacts[0].items():
        assert back[0][key] == val, key


def test_03_first_ten_headers_are_byte_identical_to_today(fa):
    """Append only. A legacy list must still produce the exact old header
    line, and the widened header must start with the same ten columns."""
    assert fa.CONTACT_FIELDS == _LEGACY_HEADER
    assert fa.CONTACT_FIELDS_ALL[:10] == _LEGACY_HEADER
    assert fa._contact_csv_fieldnames([]) == _LEGACY_HEADER

    legacy = [_contact("a@b.com", company="Acme")]
    text = fa._contacts_csv_text(legacy, fa._CONTACT_COLMAP_SNAKE)
    assert text.splitlines()[0] == ",".join(_LEGACY_HEADER)

    widened = [_contact("a@b.com", company="Acme", industry="Transportation")]
    assert fa._contacts_csv_text(widened, fa._CONTACT_COLMAP_SNAKE) \
        .splitlines()[0].split(",")[:10] == _LEGACY_HEADER


def test_04_zoominfo_headers_map(fa):
    """A ZoomInfo export's native column names resolve without the user
    renaming anything."""
    headers = ["Email Address", "First Name", "Last Name", "Company Name",
               "Job Title", "Primary Industry", "Employees",
               "Job Function", "Management Level", "Website",
               "ZoomInfo Company ID", "Scoop Type", "Scoop",
               "Scoop URL", "Scoop Date"]

    m = fa._targeting_header_map(headers)

    assert m == {
        "Industry": "Primary Industry",
        "CompanySize": "Employees",
        "JobFunction": "Job Function",
        "Seniority": "Management Level",
        "CompanyDomain": "Website",
        "CompanyId": "ZoomInfo Company ID",
        "HiringSignalType": "Scoop Type",
        "HiringSignalDescription": "Scoop",
        "HiringSignalSourceUrl": "Scoop URL",
        "HiringSignalDate": "Scoop Date",
    }


def test_05_unknown_columns_are_still_ignored(fa):
    """Columns we do not know about are dropped, and — the real risk — a
    near-miss header must not be captured. A wrong firmographic is worse
    than a missing one, so matching is exact, never substring."""
    near_misses = ["Last Updated Date", "Record Date", "Industry Notes",
                   "Employee Satisfaction", "Personal Domain",
                   "Owner ID", "Signal Strength"]
    assert fa._targeting_header_map(near_misses) == {}

    header = _LEGACY_HEADER + ["Notes", "Last Updated Date", "Lead Score"]
    _write_csv(fa._user_contacts_csv_path(), header,
               [_LEGACY_ROW + ["call back", "2026-01-01", "88"]])

    rec = fa.load_contacts()[0]
    assert rec["signal_date"] == ""
    for junk in ("Notes", "Last Updated Date", "Lead Score",
                 "notes", "lead_score"):
        assert junk not in rec


# ═══════════════════════════════════════════════════════════════════════════
#  GROUP 2 — Company index (tests 6-9)
# ═══════════════════════════════════════════════════════════════════════════

def test_06_same_company_contacts_collapse(fa):
    contacts = [
        _contact("a@acme.com", company="Acme Logistics", company_domain="acme-logistics.com"),
        _contact("b@acme.com", company="Acme Logistics", company_domain="acme-logistics.com"),
        _contact("c@other.com", company="Other Freight", company_domain="otherfreight.com"),
    ]

    idx = fa._company_index(contacts)

    assert len(idx["companies"]) == 2
    assert idx["unindexed"] == []
    acme = idx["companies"]["dom:acme-logistics.com"]
    assert len(acme["contacts"]) == 2
    assert acme["basis"] == "domain"
    assert acme["verified"] is True


def test_07_keying_is_case_and_whitespace_insensitive(fa):
    """Name-based identity folds case, punctuation, spacing and the usual
    legal suffixes — and only those. Different companies stay apart."""
    same = [
        _contact("a@x.com", company="Acme Logistics, Inc."),
        _contact("b@x.com", company="  acme   logistics llc "),
        _contact("c@x.com", company="ACME LOGISTICS"),
    ]
    idx = fa._company_index(same)
    assert len(idx["companies"]) == 1
    assert list(idx["companies"])[0] == "name:acme logistics"
    assert idx["companies"]["name:acme logistics"]["verified"] is False

    different = [_contact("a@x.com", company="Acme Logistics"),
                 _contact("b@x.com", company="Acme Freight")]
    assert len(fa._company_index(different)["companies"]) == 2


def test_08_contact_with_no_company_is_retained_but_unindexed(fa):
    """Still a person worth emailing — they just cannot be grouped. They must
    never be silently dropped."""
    nameless = _contact("solo@gmail.com", company="", company_domain="gmail.com")
    contacts = [_contact("a@x.com", company="Acme"), nameless]

    idx = fa._company_index(contacts)

    assert idx["unindexed"] == [nameless]
    assert len(idx["companies"]) == 1
    assert sum(len(e["contacts"]) for e in idx["companies"].values()) \
        + len(idx["unindexed"]) == len(contacts)
    # A mailbox provider is not a company identity.
    assert fa._company_identity(nameless) == ("", "")


def test_09_conflicting_industry_resolves_deterministically(fa):
    """Two contacts at one company disagreeing about the industry must not
    make the answer depend on row order."""
    a = _contact("a@x.com", company="Acme", company_id="ZI-1", industry="Logistics")
    b = _contact("b@x.com", company="Acme", company_id="ZI-1", industry="Transportation")
    c = _contact("c@x.com", company="Acme", company_id="ZI-1", industry="Transportation")

    forward = fa._company_index([a, b, c])["companies"]["id:zi-1"]["industry"]
    reverse = fa._company_index([c, b, a])["companies"]["id:zi-1"]["industry"]

    assert forward == reverse == "Transportation"      # majority wins
    # A dead tie breaks by sort order, not by position.
    tie_fwd = fa._company_index([a, b])["companies"]["id:zi-1"]["industry"]
    tie_rev = fa._company_index([b, a])["companies"]["id:zi-1"]["industry"]
    assert tie_fwd == tie_rev == "Logistics"


# ═══════════════════════════════════════════════════════════════════════════
#  GROUP 3 — Audience filter (tests 10-16)
# ═══════════════════════════════════════════════════════════════════════════

def _audience(fa):
    return [
        _contact("log@x.com", company="Acme", industry="Logistics",
                 company_size="250", seniority="Director", job_function="Supply Chain"),
        _contact("tra@x.com", company="Beta", industry="Transportation",
                 company_size="60", seniority="VP", job_function="Operations"),
        _contact("man@x.com", company="Gamma", industry="Manufacturing",
                 company_size="4000", seniority="SVP", job_function="Operations"),
        _contact("unk@x.com", company="Delta"),   # no firmographics at all
    ]


def test_10_industry_filter(fa):
    res = fa._tm_audience_filter(_audience(fa), industries=["Logistics"])

    assert [c["email"] for c in res["matched"]] == ["log@x.com"]
    assert res["total"] == 4
    assert res["kept"] == 1
    assert res["excluded_mismatch"] == 2
    assert res["excluded_unknown"] == 1
    assert res["unknown_by_field"] == {"Industry": 1}
    assert res["filters_active"] == ["Industry"]

    # The unknown is a contact we do not know about, not a mismatch.
    inc = fa._tm_audience_filter(_audience(fa), industries=["Logistics"],
                                 include_unknown=True)
    assert sorted(c["email"] for c in inc["matched"]) == ["log@x.com", "unk@x.com"]
    assert inc["excluded_unknown"] == 0
    assert inc["unknown_by_field"] == {"Industry": 1}


def test_11_size_bucket_boundaries_are_exact(fa):
    """Boundaries are inclusive at both ends and the ranges do not overlap,
    so a headcount lands in exactly one bucket."""
    cases = {
        "1": "1-10", "10": "1-10", "11": "11-50", "50": "11-50",
        "51": "51-200", "200": "51-200", "201": "201-500", "500": "201-500",
        "501": "501-1000", "1000": "501-1000", "1001": "1001-5000",
        "5000": "1001-5000", "5001": "5001-10000", "10000": "5001-10000",
        "10001": "10001+", "250000": "10001+",
        "1,250": "1001-5000",          # formatted count
        "201-500": "201-500",          # a range buckets by its LOW end
        "201 to 500": "201-500",
        "10,000+": "5001-10000",
        "": "", "unknown": "", "0": "",
    }
    for raw, want in cases.items():
        assert fa._size_bucket(raw) == want, raw

    # Every bucket name is its own bucket — no drift between the name list
    # and the ranges behind it.
    for name in fa._SIZE_BUCKET_NAMES:
        assert fa._size_bucket(name) == name

    res = fa._tm_audience_filter(_audience(fa), size_buckets=["201-500"])
    assert [c["email"] for c in res["matched"]] == ["log@x.com"]
    # 60 is 51-200 and must not leak into the adjacent bucket.
    assert fa._tm_audience_filter(_audience(fa), size_buckets=["51-200"])["kept"] == 1


def test_12_seniority_is_case_insensitive_and_substring_safe(fa):
    """A filter for VP must not quietly hand back SVP and AVP."""
    res = fa._tm_audience_filter(_audience(fa), seniorities=["vp"])
    assert [c["email"] for c in res["matched"]] == ["tra@x.com"]

    assert fa._token_match("VP", "vp") is True
    assert fa._token_match("VP of Operations", "vp") is True
    assert fa._token_match("SVP", "vp") is False
    assert fa._token_match("AVP", "vp") is False
    assert fa._token_match("Director", "DIRECTOR") is True


def test_13_signal_filter(fa):
    contacts = [
        _contact("full@x.com", industry="Logistics", signal_type="hiring",
                 signal_description="Posted 12 dock roles",
                 signal_source_url="https://example.com/1", signal_date="2026-08-01"),
        _contact("partial@x.com", industry="Logistics", signal_type="hiring",
                 signal_description="Heard they are hiring"),
        _contact("other@x.com", industry="Logistics", signal_type="funding",
                 signal_description="Series B",
                 signal_source_url="https://example.com/2", signal_date="2026-07-01"),
    ]

    res = fa._tm_audience_filter(contacts, signal_types=["hiring"])
    assert sorted(c["email"] for c in res["matched"]) == ["full@x.com", "partial@x.com"]
    assert res["excluded_mismatch"] == 1

    strict = fa._tm_audience_filter(contacts, signal_types=["hiring"],
                                    require_complete_signal=True)
    assert [c["email"] for c in strict["matched"]] == ["full@x.com"]
    assert strict["excluded_incomplete_signal"] == 1
    assert "incomplete hiring signal" in fa._audience_summary_line(strict)


def test_14_combined_filters_are_anded(fa):
    """Matching one criterion is not enough."""
    contacts = _audience(fa) + [
        _contact("half@x.com", industry="Logistics", company_size="4000",
                 seniority="Director", job_function="Supply Chain"),
    ]

    res = fa._tm_audience_filter(contacts, industries=["Logistics"],
                                 size_buckets=["201-500"], seniorities=["Director"])

    assert [c["email"] for c in res["matched"]] == ["log@x.com"]
    assert set(res["filters_active"]) == {"Industry", "CompanySize", "Seniority"}
    assert res["kept"] + res["excluded_mismatch"] + res["excluded_unknown"] == res["total"]


def test_15_empty_filter_returns_everything(fa):
    contacts = _audience(fa)
    for kwargs in ({}, {"industries": []}, {"industries": ["", "  "]},
                   {"industries": None, "seniorities": None}):
        res = fa._tm_audience_filter(contacts, **kwargs)
        assert res["matched"] == contacts
        assert res["kept"] == res["total"] == 4
        assert res["filters_active"] == []
        assert res["excluded_unknown"] == 0
        assert res["excluded_mismatch"] == 0


def test_16_legacy_list_returns_everything_not_nothing(fa):
    """The failure mode this guards: running the filter over a contacts.csv
    that has no firmographics at all and getting an empty audience back."""
    _write_csv(fa._user_contacts_csv_path(), _LEGACY_HEADER,
               [_LEGACY_ROW, ["sam@x.com", "Sam", "Lee", "Beta Freight",
                              "Ops Manager", "", "", "", "Boise", "ID"]])
    legacy = fa.load_contacts()
    assert len(legacy) == 2

    res = fa._tm_audience_filter(legacy)
    assert res["kept"] == res["total"] == 2

    # With a criterion they are unknowns, and the result SAYS so rather than
    # just looking like a small audience.
    named = fa._tm_audience_filter(legacy, industries=["Logistics"],
                                   include_unknown=True)
    assert named["kept"] == 2
    assert named["unknown_by_field"] == {"Industry": 2}
    assert "unknown Industry included" in fa._audience_summary_line(named)


# ═══════════════════════════════════════════════════════════════════════════
#  GROUP 4 — Duplicate guard (tests 17-20)
# ═══════════════════════════════════════════════════════════════════════════

def test_17_duplicate_guard_finds_and_names_the_other_campaign(fa):
    _seed_campaigns(fa, [{"name": "Denver Logistics", "status": "active"},
                         {"name": "Boise Manufacturing", "status": "active"}])
    _seed_queue(fa, [
        {"id": "1", "to": "dana@acme.com", "campaign": "Denver Logistics", "status": "pending"},
        {"id": "2", "to": "sam@beta.com", "campaign": "Boise Manufacturing", "status": "pending"},
    ])

    res = fa._already_targeted(["dana@acme.com", "nobody@x.com"])

    assert res["count"] == 1
    assert res["checked"] == 2
    assert res["duplicates"] == {"dana@acme.com": ["Denver Logistics"]}
    assert res["campaigns"] == ["Denver Logistics"]
    assert res["scope"] == "workspace"


def test_18_duplicate_guard_is_case_insensitive_on_email(fa):
    _seed_campaigns(fa, [{"name": "Denver Logistics", "status": "active"}])
    _seed_queue(fa, [{"id": "1", "to": "Dana@Acme.COM",
                      "campaign": "Denver Logistics", "status": "pending"}])

    res = fa._already_targeted(["  DANA@acme.com  ", "dana@acme.com"])

    assert res["checked"] == 1            # deduplicated before the scan
    assert res["count"] == 1
    assert res["duplicates"] == {"dana@acme.com": ["Denver Logistics"]}


def test_19_current_campaign_only_contacts_are_not_flagged(fa):
    """Everyone in the campaign you are building is in that campaign. Saying
    so would make the warning useless."""
    _seed_campaigns(fa, [{"name": "Denver Logistics", "status": "active"}])
    _seed_queue(fa, [{"id": "1", "to": "dana@acme.com",
                      "campaign": "Denver Logistics", "status": "pending"}])

    assert fa._already_targeted(["dana@acme.com"],
                                exclude_campaign="Denver Logistics")["count"] == 0
    assert fa._already_targeted(["dana@acme.com"],
                                exclude_campaign="  denver logistics ")["count"] == 0

    camp = {"name": "Denver Logistics", "contacts": [{"email": "dana@acme.com"}]}
    before = json.dumps(camp, sort_keys=True)
    res = fa._recheck_enrolment_duplicates(camp)
    assert res["count"] == 0
    # It REPORTS; it does not drop anyone.
    assert json.dumps(camp, sort_keys=True) == before


def test_20_removed_or_completed_contacts_do_not_count(fa):
    """Someone whose mail has already gone out, who replied, or whose
    campaign was cancelled or left in draft is a person we may legitimately
    approach again — not a duplicate."""
    _seed_campaigns(fa, [
        {"name": "Sent Already", "status": "active"},
        {"name": "Replied", "status": "active"},
        {"name": "Cancelled Camp", "status": "cancelled"},
        {"name": "Draft Camp", "status": "draft"},
        {"name": "Live Camp", "status": "active"},
    ])
    _seed_queue(fa, [
        {"id": "1", "to": "sent@x.com", "campaign": "Sent Already", "status": "sent"},
        {"id": "2", "to": "gone@x.com", "campaign": "Replied", "status": "cancelled"},
        {"id": "3", "to": "cancel@x.com", "campaign": "Cancelled Camp", "status": "pending"},
        {"id": "4", "to": "draft@x.com", "campaign": "Draft Camp", "status": "pending"},
        {"id": "5", "to": "live@x.com", "campaign": "Live Camp", "status": "pending"},
    ])

    res = fa._already_targeted(
        ["sent@x.com", "gone@x.com", "cancel@x.com", "draft@x.com", "live@x.com"])

    assert res["checked"] == 5
    assert res["count"] == 1
    assert res["duplicates"] == {"live@x.com": ["Live Camp"]}


# ═══════════════════════════════════════════════════════════════════════════
#  GROUP 5 — Arena isolation (tests 21-25) — the critical group
# ═══════════════════════════════════════════════════════════════════════════

# Every name Phase 1 introduced. If one of these turns up in a render path or
# in the sending/queue machinery, Phase 1 has stopped being inert.
_PHASE1_NAMES = {
    "_targeting_header_map", "_find_targeting_header", "_extract_targeting",
    "_contact_targeting_row", "_has_targeting_data", "_contact_csv_fieldnames",
    "_clean_company_domain", "_norm_company_name", "_company_identity",
    "_pick_consensus", "_company_index", "_size_bucket", "_token_match",
    "_contact_field", "_tm_audience_filter", "_audience_summary_line",
    "_active_enrolments", "_already_targeted", "_recheck_enrolment_duplicates",
    "_atomic_write_csv_text", "_contacts_csv_text", "_campaign_regen_block",
}

# The four that would constitute a segmentation UI if they were ever wired
# into a page. Phase 1 is helpers only; the filter UI is Phase 2.
_SEGMENTATION_NAMES = {"_company_index", "_tm_audience_filter",
                       "_audience_summary_line", "_already_targeted",
                       "_recheck_enrolment_duplicates"}


@pytest.fixture(scope="module")
def app_tree():
    """flowdrip_app.py parsed once, so the three source-level guards below
    cost one parse between them."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent /
           "flowdrip_app.py").read_text(encoding="utf-8")
    return ast.parse(src)


def _called_names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | \
           {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def test_21_no_segmentation_controls_render_under_arena(app_tree):
    """Phase 1 ships no UI. Nothing to render means nothing to gate, which is
    the strongest form of "Arena is untouched" available.

    Checked two ways: no page function reaches for a segmentation helper, and
    no Phase 1 helper builds a widget."""
    import pathlib
    offenders = []
    for node in ast.walk(app_tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("p_"):
            hit = _called_names(node) & _SEGMENTATION_NAMES
            if hit:
                offenders.append((node.name, sorted(hit)))
    assert offenders == [], f"segmentation helpers reached from a page: {offenders}"

    src = (pathlib.Path(__file__).resolve().parent.parent /
           "flowdrip_app.py").read_text(encoding="utf-8")
    for node in ast.walk(app_tree):
        if isinstance(node, ast.FunctionDef) and node.name in _PHASE1_NAMES:
            body = ast.get_source_segment(src, node) or ""
            assert "ui." not in body, f"{node.name} builds UI"


def test_22_load_contacts_output_is_unchanged_for_a_ten_column_csv(fa):
    """The ten original keys are value-for-value what they were before the
    splice, and every key Phase 1 added is the empty string. Nothing that
    reads a legacy contact can tell the difference."""
    _write_csv(fa._user_contacts_csv_path(), _LEGACY_HEADER, [_LEGACY_ROW])

    rec = fa.load_contacts()[0]
    added = {fa._TARGETING_KEYS[c] for c in fa.TARGETING_FIELDS}

    assert {k: v for k, v in rec.items() if k not in added} == _PRE_PHASE1_RECORD
    assert set(rec) - set(_PRE_PHASE1_RECORD) == added
    assert all(rec[k] == "" for k in added)

    # And writing it straight back out reproduces the original file exactly.
    text = fa._contacts_csv_text([rec], fa._CONTACT_COLMAP_SNAKE)
    with open(fa._user_contacts_csv_path(), encoding="utf-8-sig", newline="") as f:
        assert text == f.read()


def test_23_arena_slate_queue_items_are_identical(app_tree):
    """Golden: the step order, delay and step_type of the three Arena slate
    sequences. These three numbers per step are exactly what becomes a queue
    item, so pinning them pins the queue.

    Plus the structural guard: no queue or scheduling function touches a
    Phase 1 helper, so no Phase 1 change can reach a queued item by any
    other route."""
    import flowdrip_app as fa

    golden = {
        "fourbyfour": [
            ("Step 1 - Introducing Available Talent", 0, "email_auto"),
            ("Step 2 - Top Talent Insights", 3, "email_auto"),
            ("Step 3 - Follow-up Call", 0, "call"),
            ("Step 4 - LinkedIn Connect", 0, "linkedin"),
            ("Step 5 - Proven Results", 4, "email_auto"),
            ("Step 6 - Market Trends & Final Note", 4, "email_auto"),
        ],
        "fivebyfive": [
            ("Step 1 - Introducing Myself", 0, "email_auto"),
            ("Step 2 - Top Talent Insights spotlight", 3, "email_auto"),
            ("Step 3 - Follow-up Call", 0, "call"),
            ("Step 4 - LinkedIn Connect", 0, "linkedin"),
            ("Step 5 - Following-up bump", 2, "email_auto"),
            ("Step 6 - Worth a look", 3, "email_auto"),
            ("Step 7 - Closing the loop", 4, "email_auto"),
        ],
        "fivebythree": [
            ("Step 1 - Warm Intro", 0, "email_auto"),
            ("Step 2 - Candidate Slate", 3, "email_auto"),
            ("Step 3 - Interview Guide", 3, "email_auto"),
            ("Step 4 - Following up", 2, "email_auto"),
            ("Step 5 - Closing the loop", 3, "email_auto"),
        ],
    }
    pat = re.compile(
        r"^(Step \d+[^(]*)\(delay_days:\s*(\d+),\s*step_type:\s*([a-z_]+)\)", re.M)
    reg = {t[0]: t for t in fa.AICB_CAMPAIGN_TYPES}
    for key, want in golden.items():
        got = [(m.group(1).strip(" -"), int(m.group(2)), m.group(3))
               for m in pat.finditer(reg[key][6])]
        assert got == want, key

    offenders = []
    for node in ast.walk(app_tree):
        if isinstance(node, ast.FunctionDef) and \
                re.search(r"queue|schedule|_send", node.name):
            hit = _called_names(node) & _PHASE1_NAMES
            if hit:
                offenders.append((node.name, sorted(hit)))
    assert offenders == [], f"queue/sender path touches Phase 1: {offenders}"


def test_24_type_visible_unchanged_for_every_registry_key(fa):
    """Under Arena, visibility is exactly what it was: every key except the
    ThriveModal objectives, minus whatever the instance-level sales flag
    already hid. Phase 1 must not have moved a single key either way."""
    keys = [t[0] for t in fa.AICB_CAMPAIGN_TYPES]
    assert len(keys) == len(set(keys))

    for k in keys:
        arena = fa._type_visible(k, fa.PLAYBOOK_ARENA)
        if k in fa._TM_TYPE_KEYS:
            expected = False
        elif fa._SALES_MODE:
            expected = k not in fa._RECRUITING_TYPE_KEYS
        else:
            expected = k not in fa._SALES_TYPE_KEYS
        assert arena is expected, f"{k} under arena"

        tm = fa._type_visible(k, fa.PLAYBOOK_THRIVEMODAL)
        assert tm is (k in fa._TM_OFFERED_TYPE_KEYS or k in fa._PLAYBOOK_NEUTRAL_TYPE_KEYS), k

    # Visibility filters a display list; they never delete a key, or saved
    # campaigns break and _VALID_TEMPLATES stops being honest for the API.
    for k in fa._TM_TYPE_KEYS | fa._RECRUITING_TYPE_KEYS | fa._SALES_TYPE_KEYS:
        assert k in keys


def test_25_no_playbook_stamp_is_written_or_altered(fa, app_tree):
    """Do not restamp or rewrite saved campaigns. Phase 1 reads provenance;
    it never writes it."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent /
           "flowdrip_app.py").read_text(encoding="utf-8")

    for node in ast.walk(app_tree):
        if isinstance(node, ast.FunctionDef) and node.name in _PHASE1_NAMES:
            body = ast.get_source_segment(src, node) or ""
            assert "_playbook" not in body or node.name == "_campaign_regen_block", \
                f"{node.name} mentions _playbook"
            if node.name == "_campaign_regen_block":
                assert '"_playbook"] =' not in body and "'_playbook'] =" not in body

    # An unstamped campaign is Arena forever, and asking whether it may be
    # regenerated must not stamp it.
    camp = {"name": "Old Campaign", "emails": []}
    before = json.dumps(camp, sort_keys=True)
    assert fa._campaign_playbook(camp) == fa.PLAYBOOK_ARENA
    fa._campaign_regen_block(camp, {"workspace_playbook": fa.PLAYBOOK_THRIVEMODAL})
    assert json.dumps(camp, sort_keys=True) == before
    assert "_playbook" not in camp

    # And the CSV writers carry no provenance at all.
    text = fa._contacts_csv_text(
        [_contact("a@b.com", industry="Logistics")], fa._CONTACT_COLMAP_SNAKE)
    assert "_playbook" not in text

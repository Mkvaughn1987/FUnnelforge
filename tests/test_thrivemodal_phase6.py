"""ThriveModal Phase 6 — ZoomInfo record ingest + MCP coverage for the new entities.

Two gaps, one phase.

**The ingest gap.** Handoff §6.5: "In-app ZoomInfo ingest beyond CSV/XLSX
(exports parse fine today)." Phase 1 taught the CSV reader ZoomInfo's column
names, so a downloaded export lands with full firmographics. But the surface
that actually has the data is not a file — it is the ZoomInfo MCP connector,
which returns RECORDS, and whose seat is the entitled one (the REST API 403s
on Mike's seat, which is why `sales_runs_pending` exists at all). There is no
door for those records today. `sales_campaign._flatten` is the only record
normaliser in the repo and it keeps ten fields, none of them firmographic — so
every contact that arrives by the live path is targeting-blind, and the Phase 2
audience filter, the Phase 4 vertical picker and the Phase 3 analytics all run
over empty columns.

Phase 6 adds the record door. It does NOT retrofit `sales_campaign.py`:
that module is Arena's live sourcing pipeline (R2 — one app file, two
products), and widening what it emits would widen Arena's contacts.csv from
ten columns to twenty for every sales run. The new door is TM-gated end to
end and Arena reaches none of it.

**The MCP gap.** Phases 1-5 created four entities Claude cannot see: saved
audiences, the audience filter, outreach analytics, and the mailbox registry.
An agent asked to "queue 200 contacts" today cannot find out how many the
warmup ramp will actually allow.

What the groups pin, and why each is load-bearing:

  * Group A — reading a ZoomInfo row. Rows arrive flat, wrapped in
    `attributes`, wrapped in `data`, or with the firmographics hanging off a
    nested `company`. `sales_campaign._flatten` already carries a comment
    saying so, which is evidence the shapes really do vary in production, not
    a hypothetical. A reader that only handles one shape silently returns
    blanks for the other three — and a blank firmographic is indistinguishable
    from a contact we legitimately know nothing about.

  * Group B — one record to one contact. The seniority map is the reason this
    is code and not a dict comprehension: ZoomInfo says "C Level Exec" in one
    response shape and "C-Level" in another, and the Phase 2 dropdown is built
    from the values PRESENT in the list, so two pulls a month apart would offer
    the user two options that mean the same thing and each match half the list.

  * Group C — the batch. This runs over whatever an agent hands it, so junk is
    the normal case, not the edge case. Nothing here may raise.

  * Group D — merge. Re-running a ZoomInfo pull must enrich the contacts it
    already has, not duplicate them. A blank incoming value must never erase a
    value already on file: ZoomInfo returning less this time is not evidence
    that what it said last time was wrong.

  * Group E — the round trip. The point of the whole phase: contacts ingested
    from ZoomInfo must be filterable by the Phase 2 audience filter using the
    values the Phase 2 dropdown would offer. No Phase 1-5 test covers this
    seam, because until now nothing could reach it.

  * Group F — the MCP surface. A tool whose backend route does not exist ships
    as a 404 at call time, which is exactly what happened to `candidates_search`
    (fixed 2026-08-27). So this is checked structurally for every tool in the
    server, not just the new ones.

  * Group G — Arena isolation, same guard shape as Phases 2-5.

Written against the spec, not the implementation. Every test in Groups A-F was
red before the Phase 6 splice.
"""
import ast
import json
from pathlib import Path

import pytest


# NEVER import flowdrip_app at module level (see tests/conftest.py).

@pytest.fixture
def fa(isolated_appdata, with_user, monkeypatch):
    """flowdrip_app with the instance playbook lock cleared."""
    import flowdrip_app as _fa
    monkeypatch.setattr(_fa, "_LOCKED_PLAYBOOK", "")
    return _fa


@pytest.fixture
def tm(fa, monkeypatch):
    """flowdrip_app in a ThriveModal workspace."""
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    return fa


@pytest.fixture
def arena(fa, monkeypatch):
    """flowdrip_app in an Arena workspace."""
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    return fa


def _src(fa):
    return Path(fa.__file__).read_text(encoding="utf-8")


def _tree(fa):
    return ast.parse(_src(fa))


def _func(tree, name):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _names_in(node):
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.add(sub.attr)
    return out


def _repo_root():
    return Path(__file__).resolve().parents[1]


# The ZoomInfo row an agent actually hands us: firmographics on a nested
# company, scoop on the row, managementLevel in ZoomInfo's own words.
def _zi(**kw):
    row = {
        "personId": "ZI-1",
        "firstName": "Dana",
        "lastName": "Reyes",
        "email": "Dana.Reyes@Northcrest.com",
        "jobTitle": "VP of Operations",
        "jobFunction": "Operations",
        "managementLevel": "VP Level Exec",
        "linkedInUrl": "https://linkedin.com/in/danareyes",
        "state": "CO",
        "company": {
            "id": 55501,
            "name": "Northcrest Builders",
            "website": "https://northcrest.com",
            "employeeCount": 420,
            "industry": "Commercial Construction",
        },
    }
    row.update(kw)
    return row


# Helpers Phase 6 adds that must never run for an Arena user.
# The whole ingest family, including its leaves. Membership is what guards
# 72/73/75 iterate (no UI, no notify, no sales_campaign), so every helper in
# the chain belongs here - and it is also what exempts a helper from guard 71,
# which asks the rest of the file to carry the gate.
_TM_ZI_NAMES = {
    "_tm_zi_value", "_tm_zi_seniority", "_tm_zi_company_size",
    "_tm_zi_signal", "_tm_zi_contact", "_tm_zi_ingest", "_tm_zi_merge",
    "_tm_zi_list_path", "_tm_zi_save_contacts",
    "_tm_zi_company", "_tm_zi_domain", "_tm_zi_contacts_on_file",
}
_ZI_CHAIN_EXEMPT = _TM_ZI_NAMES
_GATE_NAMES = {"_is_thrivemodal", "_LOCKED_PLAYBOOK", "_workspace_playbook"}


# ─────────────────────────────────────────────────────────────────────────
# Group A — reading a value off a ZoomInfo row, whatever shape it arrived in
# ─────────────────────────────────────────────────────────────────────────

def test_01_reads_a_flat_field(tm):
    assert tm._tm_zi_value({"jobTitle": "VP Ops"}, "jobTitle") == "VP Ops"


def test_02_reads_through_an_attributes_wrapper(tm):
    row = {"attributes": {"jobTitle": "VP Ops"}}
    assert tm._tm_zi_value(row, "jobTitle") == "VP Ops"


def test_03_reads_through_a_data_wrapper(tm):
    row = {"data": {"jobTitle": "VP Ops"}}
    assert tm._tm_zi_value(row, "jobTitle") == "VP Ops"


def test_04_reads_through_attributes_then_data(tm):
    row = {"attributes": {"data": {"jobTitle": "VP Ops"}}}
    assert tm._tm_zi_value(row, "jobTitle") == "VP Ops"


def test_05_reads_a_nested_company_field(tm):
    row = {"company": {"industry": "Commercial Construction"}}
    assert tm._tm_zi_value(row, "industry") == "Commercial Construction"


def test_06_a_row_level_value_beats_the_nested_company(tm):
    """The row is about this person at this company; `company` is a summary
    block that can lag. When both answer, the row wins."""
    row = {"industry": "Civil Engineering", "company": {"industry": "Construction"}}
    assert tm._tm_zi_value(row, "industry") == "Civil Engineering"


def test_07_tries_each_alias_in_order(tm):
    row = {"primaryIndustry": "Logistics"}
    assert tm._tm_zi_value(row, "industry", "primaryIndustry") == "Logistics"


def test_08_a_missing_field_reads_as_blank_not_none(tm):
    assert tm._tm_zi_value({}, "jobTitle") == ""


def test_09_numbers_come_back_as_text(tm):
    """Everything downstream stores strings — a contact dict that sometimes
    holds an int makes `.strip()` throw three layers away."""
    assert tm._tm_zi_value({"employeeCount": 420}, "employeeCount") == "420"


def test_10_whitespace_only_counts_as_missing(tm):
    assert tm._tm_zi_value({"jobTitle": "   "}, "jobTitle") == ""


def test_11_a_non_dict_row_reads_as_blank(tm):
    for junk in (None, "", 17, [], ["a"]):
        assert tm._tm_zi_value(junk, "jobTitle") == ""


def test_12_a_non_dict_company_is_ignored_not_fatal(tm):
    assert tm._tm_zi_value({"company": "Northcrest"}, "industry") == ""


# ─────────────────────────────────────────────────────────────────────────
# Group B — one ZoomInfo record becomes one contact
# ─────────────────────────────────────────────────────────────────────────

def test_13_maps_the_identity_fields(tm):
    c = tm._tm_zi_contact(_zi())
    assert c["first_name"] == "Dana"
    assert c["last_name"] == "Reyes"
    assert c["company"] == "Northcrest Builders"
    assert c["title"] == "VP of Operations"


def test_14_lowercases_the_email(tm):
    """Email is the dedupe key everywhere in this app. Two casings of one
    address are two contacts, and the prospect gets the sequence twice."""
    assert tm._tm_zi_contact(_zi())["email"] == "dana.reyes@northcrest.com"


def test_15_maps_industry(tm):
    assert tm._tm_zi_contact(_zi())["industry"] == "Commercial Construction"


def test_16_maps_job_function(tm):
    assert tm._tm_zi_contact(_zi())["job_function"] == "Operations"


def test_17_maps_company_id(tm):
    assert tm._tm_zi_contact(_zi())["company_id"] == "55501"


def test_18_maps_company_domain_not_the_full_url(tm):
    """`CompanyDomain` is a domain. Storing the URL makes two records for one
    company whenever ZoomInfo returns http in one and https in the other."""
    assert tm._tm_zi_contact(_zi())["company_domain"] == "northcrest.com"


def test_19_strips_www_from_the_domain(tm):
    row = _zi(company={"website": "https://www.northcrest.com/about"})
    assert tm._tm_zi_contact(row)["company_domain"] == "northcrest.com"


def test_20_a_bare_domain_survives_unchanged(tm):
    row = _zi(company={"website": "northcrest.com"})
    assert tm._tm_zi_contact(row)["company_domain"] == "northcrest.com"


def test_21_company_size_is_readable_by_the_size_bucketer(tm):
    """Whatever is stored has to survive `_size_bucket`, because that is what
    both the Phase 2 dropdown and the filter run it through."""
    c = tm._tm_zi_contact(_zi())
    assert tm._size_bucket(c["company_size"]) == "201-500"


def test_22_company_size_accepts_a_range_string(tm):
    row = _zi(company={"employeeCount": "201 - 500"})
    assert tm._size_bucket(tm._tm_zi_contact(row)["company_size"]) == "201-500"


def test_23_a_missing_headcount_is_blank_not_zero(tm):
    """Zero is a headcount. Blank is "we do not know", and the filter treats
    those two completely differently."""
    row = _zi(company={"name": "Northcrest Builders"})
    assert tm._tm_zi_contact(row)["company_size"] == ""


@pytest.mark.parametrize("raw,want", [
    ("C Level Exec", "C-Level"),
    ("C-Level", "C-Level"),
    ("CXO", "C-Level"),
    ("VP Level Exec", "VP"),
    ("VP-Level", "VP"),
    ("Vice President", "VP"),
    ("Director", "Director"),
    ("Manager", "Manager"),
    ("Non Manager", "Non-Manager"),
    ("Non-Manager", "Non-Manager"),
    ("Board Members", "Board Member"),
])
def test_24_seniority_collapses_to_one_vocabulary(tm, raw, want):
    """ZoomInfo's own wording varies between response shapes. The Phase 2
    dropdown lists the values PRESENT in the list, so two spellings of one
    level become two options that each match half the contacts."""
    assert tm._tm_zi_seniority(raw) == want


def test_25_an_unrecognised_level_passes_through_rather_than_vanishing(tm):
    """Never invent and never discard: an unmapped level is still real data,
    and blanking it would turn a known contact into an unknown one."""
    assert tm._tm_zi_seniority("Partner") == "Partner"


def test_26_a_blank_level_stays_blank(tm):
    for junk in (None, "", "   ", 17, []):
        assert tm._tm_zi_seniority(junk) in ("", "17")


def test_27_the_contact_carries_the_mapped_seniority(tm):
    assert tm._tm_zi_contact(_zi())["seniority"] == "VP"


def test_28_title_and_function_and_seniority_stay_three_fields(tm):
    """Phase 1's comment is explicit about this: collapsing them makes a
    seniority filter silently match on job wording."""
    c = tm._tm_zi_contact(_zi())
    assert c["title"] == "VP of Operations"
    assert c["job_function"] == "Operations"
    assert c["seniority"] == "VP"


def test_29_a_scoop_fills_all_four_signal_fields(tm):
    row = _zi(scoop={
        "scoopType": "Hiring",
        "description": "Opening a second estimating team in Q4.",
        "scoopUrl": "https://example.com/news/1",
        "publishedDate": "2026-08-14",
    })
    c = tm._tm_zi_contact(row)
    assert c["signal_type"] == "Hiring"
    assert c["signal_description"] == "Opening a second estimating team in Q4."
    assert c["signal_source_url"] == "https://example.com/news/1"
    assert c["signal_date"] == "2026-08-14"


def test_30_a_partial_scoop_keeps_the_parts_that_arrived(tm):
    """`require_complete_signal` is the enforcement point and it lives on the
    filter, where the user can see what it excluded. Dropping the parts here
    would destroy the very information that flag reports on."""
    row = _zi(scoop={"scoopType": "Hiring", "description": "Hiring estimators."})
    c = tm._tm_zi_contact(row)
    assert c["signal_type"] == "Hiring"
    assert c["signal_description"] == "Hiring estimators."
    assert c["signal_source_url"] == ""
    assert c["signal_date"] == ""


def test_31_no_scoop_leaves_all_four_signal_fields_blank(tm):
    c = tm._tm_zi_contact(_zi())
    for k in ("signal_type", "signal_description", "signal_source_url", "signal_date"):
        assert c[k] == ""


def test_32_a_scoops_list_uses_the_first_entry(tm):
    row = _zi(scoops=[{"scoopType": "Hiring", "description": "First."},
                      {"scoopType": "Funding", "description": "Second."}])
    assert tm._tm_zi_contact(row)["signal_type"] == "Hiring"


def test_33_every_targeting_key_is_present_even_when_empty(tm):
    """A contact with some keys missing and some blank makes every consumer
    write `.get(k, "")` instead of `[k]`, and one of them will forget."""
    c = tm._tm_zi_contact({"email": "a@b.com"})
    for key in tm._TARGETING_KEYS.values():
        assert key in c, key


def test_34_a_junk_record_does_not_raise(tm):
    for junk in (None, "", 17, [], {"company": 4}, {"email": None}):
        assert isinstance(tm._tm_zi_contact(junk), dict)


# ─────────────────────────────────────────────────────────────────────────
# Group C — the batch
# ─────────────────────────────────────────────────────────────────────────

def test_35_ingests_a_batch(tm):
    res = tm._tm_zi_ingest([_zi(), _zi(personId="ZI-2", email="sam@northcrest.com")])
    assert res["kept"] == 2
    assert res["total"] == 2
    assert len(res["contacts"]) == 2


def test_36_drops_a_record_with_no_email_and_says_why(tm):
    """A contact with no address cannot be emailed, so keeping it would only
    inflate the count the user budgets against."""
    res = tm._tm_zi_ingest([_zi(email="")])
    assert res["kept"] == 0
    assert len(res["dropped"]) == 1
    assert res["dropped"][0]["drop_reason"]


def test_37_drops_a_malformed_email(tm):
    res = tm._tm_zi_ingest([_zi(email="not-an-address")])
    assert res["kept"] == 0


def test_38_dedupes_on_email_within_the_batch(tm):
    res = tm._tm_zi_ingest([_zi(), _zi(personId="ZI-9")])
    assert res["kept"] == 1
    assert len(res["dropped"]) == 1


def test_39_dedupe_is_case_insensitive(tm):
    res = tm._tm_zi_ingest([_zi(email="Dana@x.com"), _zi(email="dana@X.com")])
    assert res["kept"] == 1


def test_40_the_first_record_of_a_duplicate_pair_is_the_one_kept(tm):
    res = tm._tm_zi_ingest([_zi(jobTitle="VP of Operations"),
                            _zi(jobTitle="Operations VP")])
    assert res["contacts"][0]["title"] == "VP of Operations"


def test_41_an_empty_batch_is_not_an_error(tm):
    res = tm._tm_zi_ingest([])
    assert res["kept"] == 0
    assert res["contacts"] == []


def test_42_a_junk_batch_does_not_raise(tm):
    """This runs on whatever an agent posts. Junk is the normal case."""
    for junk in (None, "", 17, {}, [None], [17], ["x"], [[]]):
        res = tm._tm_zi_ingest(junk)
        assert isinstance(res, dict)
        assert isinstance(res.get("contacts"), list)


# ─────────────────────────────────────────────────────────────────────────
# Group D — merging a pull into contacts already on file
# ─────────────────────────────────────────────────────────────────────────

def test_43_a_new_contact_is_appended(tm):
    existing = [{"email": "old@x.com", "first_name": "Old"}]
    merged, stats = tm._tm_zi_merge(existing, [{"email": "new@x.com"}])
    assert len(merged) == 2
    assert stats["added"] == 1


def test_44_an_existing_contact_is_updated_in_place_not_duplicated(tm):
    existing = [{"email": "dana@x.com", "first_name": "Dana"}]
    merged, stats = tm._tm_zi_merge(
        existing, [{"email": "dana@x.com", "industry": "Construction"}])
    assert len(merged) == 1
    assert merged[0]["industry"] == "Construction"
    assert stats["updated"] == 1
    assert stats["added"] == 0


def test_45_a_blank_incoming_value_never_erases_one_already_on_file(tm):
    """ZoomInfo returning less this time is not evidence that what it said
    last time was wrong."""
    existing = [{"email": "dana@x.com", "industry": "Construction",
                 "seniority": "VP"}]
    merged, _ = tm._tm_zi_merge(existing, [{"email": "dana@x.com", "industry": ""}])
    assert merged[0]["industry"] == "Construction"
    assert merged[0]["seniority"] == "VP"


def test_46_a_non_blank_incoming_value_wins(tm):
    existing = [{"email": "dana@x.com", "title": "Ops Manager"}]
    merged, _ = tm._tm_zi_merge(existing, [{"email": "dana@x.com",
                                            "title": "VP of Operations"}])
    assert merged[0]["title"] == "VP of Operations"


def test_47_merge_matches_on_email_case_insensitively(tm):
    existing = [{"email": "Dana@X.com"}]
    merged, stats = tm._tm_zi_merge(existing, [{"email": "dana@x.com",
                                                "industry": "Construction"}])
    assert len(merged) == 1
    assert stats["updated"] == 1


def test_48_existing_order_is_preserved_and_new_rows_go_last(tm):
    """The list the user is looking at must not reshuffle because a pull ran."""
    existing = [{"email": "a@x.com"}, {"email": "b@x.com"}]
    merged, _ = tm._tm_zi_merge(existing, [{"email": "b@x.com", "industry": "X"},
                                           {"email": "c@x.com"}])
    assert [c["email"] for c in merged] == ["a@x.com", "b@x.com", "c@x.com"]


def test_49_merging_into_nothing_is_the_same_as_ingesting(tm):
    merged, stats = tm._tm_zi_merge(None, [{"email": "a@x.com"}])
    assert len(merged) == 1
    assert stats["added"] == 1


def test_50_merge_does_not_mutate_the_list_it_was_given(tm):
    """The caller still holds the list it is rendering."""
    existing = [{"email": "a@x.com", "industry": "Old"}]
    tm._tm_zi_merge(existing, [{"email": "a@x.com", "industry": "New"}])
    assert existing[0]["industry"] == "Old"


def test_51_merge_survives_junk_on_either_side(tm):
    for junk in (None, "", 17, {}, [None], [17]):
        merged, stats = tm._tm_zi_merge(junk, junk)
        assert isinstance(merged, list)
        assert isinstance(stats, dict)


# ─────────────────────────────────────────────────────────────────────────
# Group E — the round trip: ingested contacts must be filterable
# ─────────────────────────────────────────────────────────────────────────

def test_52_an_ingested_contact_matches_its_own_industry(tm):
    res = tm._tm_zi_ingest([_zi()])
    out = tm._tm_audience_filter(res["contacts"], industries=["Commercial Construction"])
    assert out["kept"] == 1


def test_53_an_ingested_contact_matches_its_own_size_bucket(tm):
    res = tm._tm_zi_ingest([_zi()])
    out = tm._tm_audience_filter(res["contacts"], size_buckets=["201-500"])
    assert out["kept"] == 1


def test_54_an_ingested_contact_matches_its_own_seniority(tm):
    """The Phase 2 dropdown offers the values present in the list, so the
    value stored must match itself through `_token_match`."""
    res = tm._tm_zi_ingest([_zi()])
    stored = res["contacts"][0]["seniority"]
    out = tm._tm_audience_filter(res["contacts"], seniorities=[stored])
    assert out["kept"] == 1


def test_55_seniority_does_not_match_a_different_level(tm):
    res = tm._tm_zi_ingest([_zi()])
    out = tm._tm_audience_filter(res["contacts"], seniorities=["C-Level"])
    assert out["kept"] == 0


def test_56_an_ingested_contact_survives_require_complete_signal(tm):
    row = _zi(scoop={"scoopType": "Hiring", "description": "d",
                     "scoopUrl": "https://e.com/1", "publishedDate": "2026-08-14"})
    res = tm._tm_zi_ingest([row])
    out = tm._tm_audience_filter(res["contacts"], require_complete_signal=True)
    assert out["kept"] == 1


def test_57_a_partial_signal_is_excluded_by_require_complete_signal(tm):
    row = _zi(scoop={"scoopType": "Hiring", "description": "d"})
    res = tm._tm_zi_ingest([row])
    out = tm._tm_audience_filter(res["contacts"], require_complete_signal=True)
    assert out["kept"] == 0
    assert out["excluded_incomplete_signal"] == 1


def test_58_the_phase_2_dropdown_would_offer_exactly_what_was_stored(tm):
    """`_contact_field` is what the panel reads its options through. If the
    ingest writes a key the panel cannot see, the dropdown comes back empty
    and the whole feature looks broken with no error anywhere."""
    res = tm._tm_zi_ingest([_zi()])
    c = res["contacts"][0]
    assert tm._contact_field(c, "industry") == "Commercial Construction"
    assert tm._contact_field(c, "seniority") == "VP"
    assert tm._contact_field(c, "job_function") == "Operations"


def test_59_an_ingested_list_widens_the_csv_to_twenty_columns(tm):
    """Phase 1 made the header data-driven. Ingested firmographics are data,
    so the file they land in must carry them — otherwise the pull is lost on
    the next round trip through disk."""
    res = tm._tm_zi_ingest([_zi()])
    assert len(tm._contact_csv_fieldnames(res["contacts"])) == 20


def test_60_the_vertical_picker_reads_an_ingested_industry(tm):
    """Phase 4's picker is the other consumer of `industry`, and nothing has
    ever fed it from a live pull."""
    res = tm._tm_zi_ingest([_zi()])
    assert tm._tm_vertical_for(res["contacts"][0]["industry"]) == "construction_aec"


# ─────────────────────────────────────────────────────────────────────────
# Group F — the MCP surface
# ─────────────────────────────────────────────────────────────────────────

def _mcp_tree():
    return ast.parse((_repo_root() / "mcp_server" / "dripdrop_mcp.py")
                     .read_text(encoding="utf-8"))


def _client_tree():
    return ast.parse((_repo_root() / "mcp_server" / "dripdrop_client.py")
                     .read_text(encoding="utf-8"))


def _mcp_tool_names():
    """Every function decorated with @mcp.tool, by name."""
    out = []
    for node in ast.walk(_mcp_tree()):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(target, ast.Attribute) and target.attr == "tool":
                out.append(node.name)
                break
    return out


def _client_method_names():
    out = []
    for node in ast.walk(_client_tree()):
        if isinstance(node, ast.ClassDef) and node.name == "DripDropClient":
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(sub.name)
    return out


_NEW_TOOLS = ("tm_import_contacts", "tm_audiences", "tm_audience_preview",
              "tm_analytics", "tm_mailboxes")


@pytest.mark.parametrize("name", _NEW_TOOLS)
def test_61_the_new_mcp_tools_exist(name):
    assert name in _mcp_tool_names()


@pytest.mark.parametrize("name", _NEW_TOOLS)
def test_62_each_new_tool_has_a_client_method(name):
    assert name in _client_method_names()


def test_63_every_mcp_tool_has_a_client_method(tm):
    """`candidates_search` shipped without one and 404'd at call time
    (fixed 2026-08-27). This is the structural check that would have caught it."""
    missing = [t for t in _mcp_tool_names() if t not in _client_method_names()]
    assert missing == [], missing


@pytest.mark.parametrize("path", [
    "/api/v1/tm/contacts", "/api/v1/tm/audiences",
    "/api/v1/tm/audience_preview", "/api/v1/tm/analytics",
    "/api/v1/tm/mailboxes",
])
def test_64_each_new_route_is_registered_on_the_app(tm, path):
    assert '"%s"' % path in _src(tm)


@pytest.mark.parametrize("name", [
    "api_tm_import_contacts", "api_tm_audiences", "api_tm_audience_preview",
    "api_tm_analytics", "api_tm_mailboxes",
])
def test_65_each_new_route_handler_is_a_top_level_function(tm, name):
    assert _func(_tree(tm), name) is not None


@pytest.mark.parametrize("name", [
    "api_tm_import_contacts", "api_tm_audiences", "api_tm_audience_preview",
    "api_tm_analytics", "api_tm_mailboxes",
])
def test_66_every_new_route_checks_the_thrivemodal_gate(tm, name):
    """These routes are reachable from the public internet with a valid API
    key. An Arena user's key must not open a ThriveModal door."""
    node = _func(_tree(tm), name)
    assert node is not None, name
    assert _GATE_NAMES & _names_in(node), name


@pytest.mark.parametrize("name", [
    "api_tm_import_contacts", "api_tm_audiences", "api_tm_audience_preview",
    "api_tm_analytics", "api_tm_mailboxes",
])
def test_67_every_new_route_resolves_its_owner_through_the_one_auth_door(tm, name):
    """The owner must come from the key, never from the body — otherwise one
    key can write into another account. Pinned as a single shared door rather
    than a copied preamble, because five copies of an auth check is five
    chances for one of them to drift."""
    node = _func(_tree(tm), name)
    assert "_tm_api_owner" in _names_in(node), name


def test_67b_the_auth_door_resolves_the_owner_from_the_key(tm):
    node = _func(_tree(tm), "_tm_api_owner")
    assert node is not None
    assert "_resolve_api_key" in _names_in(node)


@pytest.mark.parametrize("name", [
    "api_tm_import_contacts", "api_tm_audiences", "api_tm_audience_preview",
    "api_tm_analytics", "api_tm_mailboxes",
])
def test_67c_the_owner_comes_only_from_the_auth_door(tm, name):
    """The one mistake this whole shape exists to prevent: a caller naming
    the account it wants to write to. `owner` is assigned exactly once, from
    the door, so there is no second path a body value could arrive by."""
    node = _func(_tree(tm), name)
    sources = [a.value for a in ast.walk(node) if isinstance(a, ast.Assign)
               for t in a.targets if isinstance(t, ast.Name) and t.id == "owner"]
    assert len(sources) == 1, (name, len(sources))
    val = sources[0]
    assert isinstance(val, ast.Call) and isinstance(val.func, ast.Name)         and val.func.id == "_tm_api_owner", (name, ast.dump(val)[:80])


def test_68_the_mailbox_tool_reports_remaining_budget_not_just_the_cap(tm):
    """An agent asked to queue 200 emails needs to know what the warmup ramp
    will actually allow today, which is not the number in the config."""
    node = _func(_tree(tm), "api_tm_mailboxes")
    assert "_tm_mailbox_budgets" in _names_in(node)


def test_69_the_import_route_goes_through_the_zoominfo_ingest(tm):
    node = _func(_tree(tm), "api_tm_import_contacts")
    assert "_tm_zi_ingest" in _names_in(node)


def test_70_the_preview_route_goes_through_the_phase_2_filter(tm):
    """One filter implementation. A second one that "does the same thing"
    would drift and then the preview would lie about the send."""
    node = _func(_tree(tm), "api_tm_audience_preview")
    assert "_tm_audience_filter" in _names_in(node)


# ─────────────────────────────────────────────────────────────────────────
# Group G — Arena isolation
# ─────────────────────────────────────────────────────────────────────────

def test_71_every_function_touching_a_zi_helper_also_checks_the_gate(tm):
    """Same guard shape as Phases 2-5."""
    tree = _tree(tm)
    offenders = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in _ZI_CHAIN_EXEMPT:
            continue
        used = _names_in(node)
        if (_TM_ZI_NAMES & used) and not (_GATE_NAMES & used):
            offenders.append(node.name)
    assert offenders == [], offenders


def test_72_the_zi_helpers_build_no_ui(tm):
    """A pure helper that builds UI cannot be called from a background send
    loop or an API route, which is exactly where these run."""
    tree = _tree(tm)
    for name in sorted(_TM_ZI_NAMES):
        node = _func(tree, name)
        if node is None:
            continue
        assert "ui" not in {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}, name


def test_73_the_zi_helpers_never_notify(tm):
    tree = _tree(tm)
    for name in sorted(_TM_ZI_NAMES):
        node = _func(tree, name)
        if node is None:
            continue
        assert "notify" not in _names_in(node), name


def test_74_an_arena_user_gets_nothing_from_the_import_route(arena):
    """The gate is checked at the top of the handler, before any work."""
    node = _func(_tree(arena), "api_tm_import_contacts")
    src = ast.unparse(node)
    assert "_is_thrivemodal" in src


def test_75_no_zi_helper_reaches_the_sales_campaign_module(tm):
    """Phase 6 deliberately does NOT retrofit Arena's live sourcing pipeline
    (R2). If a helper here starts importing it, that decision has been undone
    without anyone deciding to."""
    tree = _tree(tm)
    for name in sorted(_TM_ZI_NAMES):
        node = _func(tree, name)
        if node is None:
            continue
        assert "sales_campaign" not in ast.unparse(node), name


def test_76_sales_campaign_flatten_is_unchanged_by_this_phase(tm):
    """Arena's contacts.csv stays ten columns for every sales run. The moment
    `_flatten` emits a firmographic, Phase 1's data-driven header widens every
    Arena export to twenty columns."""
    import sales_campaign as _sc
    got = _sc._flatten({"firstName": "A", "lastName": "B",
                        "company": {"industry": "Construction",
                                    "employeeCount": 420}})
    assert "industry" not in got
    assert "company_size" not in got

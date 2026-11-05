"""Mike, 2026-11-05: "make the jobs specific to whatever company or industry
we are targeting". The generic rate line ("most support staff under
$15/hr") names the campaign's own lead job and that job's own ceiling.
"""
import flowdrip_app as fa


def _tm(monkeypatch):
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)


def test_line_names_the_campaign_role(monkeypatch):
    _tm(monkeypatch)
    line = fa._tm_target_rate_line("Dispatcher", "Trucking", "Acme")
    assert line[0] == "dispatcher roles"
    rate = fa._tm_our_hourly(
        fa._tm_benchmark(fa._tm_match_benchmark("Dispatcher"))["base"],
        "Dispatcher")
    assert line[1] == f"${int(rate) + 1}/hr"
    body = ("Did you have a chance to look at my last email, with most "
            "support staff under $15/hr? Most support staff come in under "
            "$15/hr, and the companies that start with one keep adding.")
    out = fa._tm_localize_rate_line(body, line)
    assert "support staff" not in out
    assert f"with most dispatcher roles under {line[1]}?" in out
    assert f"Most dispatcher roles come in under {line[1]}," in out


def test_line_uses_the_industry_job_when_no_role_is_given(monkeypatch):
    _tm(monkeypatch)
    noun, fig = fa._tm_target_rate_line("", "Accounting", "Smith CPA")
    assert noun.endswith(" roles") and "support staff" not in noun
    assert fig.startswith("$") and fig.endswith("/hr")


def test_localizing_a_campaign_touches_every_email(monkeypatch):
    _tm(monkeypatch)
    camp = {"emails": [
        {"body": "Hi,<br><br>Most support staff come in under $15/hr."},
        {"body": "No figure here."},
        {"body": ""},
    ]}
    fa._tm_localize_campaign_rate_lines(camp, "Medical Biller", "Healthcare")
    assert "most medical biller roles come in under $" in camp["emails"][0]["body"].lower()
    assert camp["emails"][1]["body"] == "No figure here."


def test_a_localized_line_still_counts_as_the_rate_line():
    # A profiles rerun must not add the worth-a-shot line a second time.
    assert fa._TM_ANY_RATE_LINE_RE.search("most dispatcher roles come in under $15/hr")
    assert fa._TM_ANY_RATE_LINE_RE.search("most support staff under $15/hr")


def test_bands_start_from_the_28k_logistics_coordinator():
    # $28,000 a year over 2,080 hours, Mike's actual number.
    assert fa._tm_rate_group("Logistics Coordinator")[1] == round(28000 / 2080, 2)
    for role in ("Logistics Coordinator", "Dispatcher", "Track and Trace Specialist"):
        assert fa._tm_our_hourly(20000, role) >= 13.46

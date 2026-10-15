"""Buying News & Signals (tm_signals.py): the Tuesday/Thursday email.

Pins the pure parts: the due check, the parser's filters, the 30-day
repeat guard, the ranking, the email body, and the scheduler's gating
(ThriveModal only, opted-in only, once a day). No live API calls.
"""
import inspect
import json
import sys
import types
from datetime import date, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _stub_nicegui():
    if "nicegui" in sys.modules:
        return
    try:
        import nicegui  # noqa: F401
        return
    except Exception:
        pass
    ng = types.ModuleType("nicegui")

    class _Any:
        def __getattr__(self, _n):
            return _Any()

        def __call__(self, *a, **k):
            return _Any()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    ng.ui = _Any()
    sys.modules["nicegui"] = ng


@pytest.fixture(scope="module")
def tms():
    _stub_nicegui()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import tm_signals
    return tm_signals


TODAY = date(2026, 10, 15)   # a Thursday


def _row(company="Acme Freight", signal="pe", days_ago=3, **kw):
    d = (TODAY - __import__("datetime").timedelta(days=days_ago)).isoformat()
    base = {"company": company, "location": "Dallas, TX", "signal": signal,
            "headline": "Acquired by a PE firm", "date": d,
            "why_now": "New owners.", "opener": "Saw the news.",
            "source_url": "https://www.prnewswire.com/x"}
    base.update(kw)
    return base


# ── due check ─────────────────────────────────────────────────────────────

def test_due_only_tue_thu_after_seven_and_once_a_day(tms):
    s = {"enabled": True, "industries": ["logistics"], "last_run_date": ""}
    assert tms.is_due(s, datetime(2026, 10, 15, 7, 0))      # Thu 7am
    assert tms.is_due(s, datetime(2026, 10, 13, 9, 30))     # Tue
    assert not tms.is_due(s, datetime(2026, 10, 15, 6, 59))  # too early
    assert not tms.is_due(s, datetime(2026, 10, 14, 9, 0))   # Wed
    assert not tms.is_due(s, datetime(2026, 10, 17, 9, 0))   # Sat
    s["last_run_date"] = "2026-10-15"
    assert not tms.is_due(s, datetime(2026, 10, 15, 12, 0))  # already ran


def test_not_due_when_off_or_no_industries(tms):
    thu = datetime(2026, 10, 15, 8, 0)
    assert not tms.is_due({"enabled": False, "industries": ["logistics"]}, thu)
    assert not tms.is_due({"enabled": True, "industries": []}, thu)


def test_next_send_lands_on_next_tue_or_thu_seven(tms):
    n = tms.next_send(datetime(2026, 10, 15, 7, 30))   # Thu after send
    assert n == datetime(2026, 10, 20, 7, 0)            # next Tuesday
    n = tms.next_send(datetime(2026, 10, 15, 6, 0))    # Thu before send
    assert n == datetime(2026, 10, 15, 7, 0)
    n = tms.next_send(datetime(2026, 10, 17, 12, 0))   # Sat
    assert n == datetime(2026, 10, 20, 7, 0)


# ── parser ────────────────────────────────────────────────────────────────

def test_parse_keeps_only_known_fresh_sourced_companies(tms):
    text = "```json\n" + json.dumps({"companies": [
        _row(),                                            # good
        _row("Old Co", days_ago=40),                       # stale
        _row("Made Up Signal", signal="merger"),           # not in catalogue
        _row("No Source", source_url="not a url"),         # no http source
        _row("No Date", date="last week"),                 # unparseable date
        _row("", signal="cost"),                           # no name
        _row("Acme Freight", signal="cost"),               # duplicate name
        _row("Future Co", days_ago=-5),                    # too far ahead
    ], "news": [
        {"headline": "Rates up", "date": "2026-10-12", "summary": "x",
         "source_url": "https://www.freightwaves.com/a"},
        {"headline": "", "date": "2026-10-12"},
        {"headline": "Old news", "date": "2026-08-01"},
        {"headline": "Undated but fine", "summary": "y"},
    ]}) + "\n```"
    got = tms.parse_scan(text, TODAY)
    assert [r["company"] for r in got["companies"]] == ["Acme Freight"]
    assert got["companies"][0]["signal"] == "pe"
    assert [n["headline"] for n in got["news"]] == ["Rates up", "Undated but fine"]


def test_parse_tolerates_garbage(tms):
    assert tms.parse_scan("no json here", TODAY) == {"companies": [], "news": []}
    assert tms.parse_scan("{not: valid", TODAY) == {"companies": [], "news": []}
    assert tms.parse_scan('{"companies": "x", "news": 3}', TODAY) == {"companies": [], "news": []}


def test_parse_strips_tags_and_caps_length(tms):
    text = json.dumps({"companies": [_row(headline="<cite>Big</cite> news " * 40)]})
    got = tms.parse_scan(text, TODAY)
    h = got["companies"][0]["headline"]
    assert "<" not in h and len(h) <= 160


# ── repeat guard + ranking ────────────────────────────────────────────────

def test_recent_companies_only_inside_thirty_days(tms):
    issues = [
        {"date": "2026-10-01", "sections": [{"companies": [_row("Fresh Co")]}]},
        {"date": "2026-08-01", "sections": [{"companies": [_row("Ancient Co")]}]},
    ]
    assert tms.recent_companies(issues, TODAY) == {"fresh co"}


def test_rank_urgent_first_then_catalogue_order_then_newest(tms):
    rows = [_row("A", "remote", 1), _row("B", "cost", 5), _row("C", "pe", 9),
            _row("D", "pe", 2), _row("E", "hiring", 0)]
    assert [r["company"] for r in tms.rank(rows)] == ["D", "C", "B", "E", "A"]


def test_build_issue_one_section_per_picked_industry_and_dedupes(tms):
    calls = []

    def scan(vertical, location):
        calls.append((vertical["key"], location))
        if vertical["key"] == "accounting":
            raise RuntimeError("boom")
        return json.dumps({"companies": [_row("Acme Freight"), _row("New Co", "cost")],
                           "news": []})

    settings = {"enabled": True, "industries": ["accounting", "logistics"],
                "location": "Texas",
                "issues": [{"date": "2026-10-08",
                            "sections": [{"companies": [_row("Acme Freight")]}]}]}
    issue = tms.build_issue(settings, TODAY, scan)
    assert [c[0] for c in calls] == ["logistics", "accounting"]   # catalogue order
    assert calls[0][1] == "Texas"
    secs = {s["industry"]: s for s in issue["sections"]}
    assert secs["accounting"]["error"] and secs["accounting"]["companies"] == []
    assert [r["company"] for r in secs["logistics"]["companies"]] == ["New Co"]
    assert issue["subject"] == "Buying news & signals: Thu 15 Oct"
    assert tms.issue_has_content(issue)
    assert not tms.issue_has_content({"sections": [{"companies": [], "news": []}]})


# ── email ─────────────────────────────────────────────────────────────────

def test_email_has_sections_badges_links_and_no_style_block(tms):
    issue = {"date": "2026-10-15", "location": "USA", "sections": [
        {"industry": "logistics", "label": "Logistics / 3PL",
         "companies": [_row("Acme Freight", "pe"), _row("Watch Co", "remote",
                                                        opener="")],
         "news": [{"headline": "Rates up", "date": "2026-10-12", "summary": "x",
                   "source_url": "https://www.freightwaves.com/a"}]},
        {"industry": "accounting", "label": "Accounting", "companies": [], "news": []},
    ]}
    html = tms.render_email(issue, brand="inboxslide", app_url="https://app.inboxslide.ai")
    assert "Move on these now" in html and "Worth a look" in html
    assert "Industry news" in html
    assert "Acme Freight" in html and "Watch Co" in html
    assert "Private equity acquisition" in html
    assert 'href="https://www.prnewswire.com/x"' in html
    assert "https://app.inboxslide.ai/?open=tm_prompts" in html
    assert "https://app.inboxslide.ai/?open=tm_signals" in html
    assert "Thursday 15 October 2026" in html
    assert "<style" not in html          # inline styles only (merge tokens + clients)
    assert "Accounting" not in html.split("Industry news")[1]   # empty section skipped


def test_email_escapes_model_text(tms):
    issue = {"date": "2026-10-15", "sections": [
        {"label": "L", "companies": [_row("<b>Evil</b> & Co", headline="<script>x</script>")],
         "news": []}]}
    html = tms.render_email(issue)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "&lt;b&gt;Evil&lt;/b&gt; &amp; Co" in html


def test_empty_issue_renders_a_plain_note(tms):
    html = tms.render_email({"date": "2026-10-15", "sections": []})
    assert "Nothing new this time" in html


# ── settings file ─────────────────────────────────────────────────────────

def test_settings_round_trip_and_defaults(tms, tmp_path):
    assert tms.load_settings(tmp_path) == tms.default_settings()
    tms.save_settings({"enabled": True, "industries": ["logistics"], "location": "USA",
                       "issues": [{"date": "2026-10-15", "sections": []}, "junk"]}, tmp_path)
    got = tms.load_settings(tmp_path)
    assert got["enabled"] is True and got["industries"] == ["logistics"]
    assert got["issues"] == [{"date": "2026-10-15", "sections": []}]
    assert got["last_run_date"] == ""
    (tmp_path / tms.SETTINGS_FILE).write_text("{broken", encoding="utf-8")
    assert tms.load_settings(tmp_path) == tms.default_settings()


# ── scheduler gating ──────────────────────────────────────────────────────

def test_scheduler_tick_only_runs_due_thrivemodal_users(tms, tmp_path, monkeypatch):
    users = tmp_path / "users"
    started = []

    class _FF:
        _BASE_DATA_DIR = tmp_path
        _DEFAULT_USER_TZ = "America/Chicago"

        @staticmethod
        def _is_thrivemodal(cfg):
            return cfg.get("playbook") == "thrivemodal"

        @staticmethod
        def _email_from_user_path(p):
            return "mike@example.com" if "mike" in str(p) else "pat@example.com"

        @staticmethod
        def _run_as_user(email, target, name=None):
            started.append(email)

    def mk(name, playbook, settings):
        d = users / name
        d.mkdir(parents=True)
        (d / "dripdrop_config.json").write_text(
            json.dumps({"playbook": playbook, "user_timezone": "America/Chicago"}),
            encoding="utf-8")
        if settings is not None:
            tms.save_settings(settings, d)
        return d

    mike = mk("mike_at_example_com", "thrivemodal",
              {"enabled": True, "industries": ["logistics"]})
    mk("pat_at_example_com", "arena", {"enabled": True, "industries": ["logistics"]})
    mk("off_at_example_com", "thrivemodal", {"enabled": False, "industries": ["logistics"]})
    mk("none_at_example_com", "thrivemodal", None)

    monkeypatch.setattr(tms, "_ff", lambda: _FF)
    monkeypatch.setattr(tms, "is_due", lambda settings, now: bool(settings.get("enabled")))
    tms._last_tick[0] = 0.0
    assert tms.scheduler_tick(force=True) == 1
    assert started == ["mike@example.com"]
    # The run date is stamped before the thread starts, so a slow run can
    # never be started twice by the next tick.
    assert tms.load_settings(mike)["last_run_date"]
    # Throttled: an immediate second call does nothing.
    started.clear()
    assert tms.scheduler_tick() == 0


def test_run_issue_sends_from_own_mailbox_and_stores_issue(tms, tmp_path, monkeypatch):
    sent = []

    class _FF:
        ANTHROPIC_API_KEY = "k"
        BRAND = "inboxslide"
        _PUBLIC_ORIGIN = "https://app.inboxslide.ai"

        @staticmethod
        def _server_send_one(item, config_path, user_dir=None):
            sent.append((item, config_path, user_dir))
            return True, ""

    monkeypatch.setattr(tms, "_ff", lambda: _FF)
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(
        Anthropic=lambda api_key: object()))
    monkeypatch.setattr(tms, "run_scan", lambda client, v, loc, today: json.dumps(
        {"companies": [_row()], "news": []}))
    tms.save_settings({"enabled": True, "industries": ["logistics"]}, tmp_path)
    issue = tms.run_issue("mike@example.com", tmp_path, today=TODAY)
    assert issue["sent_at"]
    item, cfg, udir = sent[0]
    assert item["to"] == "mike@example.com" and item["is_html"] is True
    assert item["subject"] == "Buying news & signals: Thu 15 Oct"
    assert cfg == tmp_path / "dripdrop_config.json" and udir == tmp_path
    stored = tms.load_settings(tmp_path)
    assert stored["issues"][0]["id"] == issue["id"]
    assert stored["last_run_date"] == "2026-10-15"


def test_run_issue_skips_send_when_nothing_found(tms, tmp_path, monkeypatch):
    sent = []

    class _FF:
        ANTHROPIC_API_KEY = "k"
        BRAND = "inboxslide"
        _PUBLIC_ORIGIN = ""

        @staticmethod
        def _server_send_one(item, config_path, user_dir=None):
            sent.append(item)
            return True, ""

    monkeypatch.setattr(tms, "_ff", lambda: _FF)
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(
        Anthropic=lambda api_key: object()))
    monkeypatch.setattr(tms, "run_scan", lambda *a: "nothing")
    tms.save_settings({"enabled": True, "industries": ["logistics"]}, tmp_path)
    issue = tms.run_issue("mike@example.com", tmp_path, today=TODAY)
    assert sent == [] and "no email" in issue["send_error"]
    assert tms.load_settings(tmp_path)["issues"]


BLOCKED_400 = ("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
               "'message': \"The following domains are not accessible to our user agent: "
               "['bizjournals.com', 'reuters.com', 'wsj.com']. Read more: https://x\"}}")


def test_news_allowlist_never_names_a_publisher_that_blocks_the_crawler(tms):
    # The API rejects the WHOLE request with a 400 if any listed domain
    # blocks Anthropic's crawler; this is what made the first live issue
    # come back as "nothing found" for all four industries.
    for d in ("reuters.com", "wsj.com", "bloomberg.com", "bizjournals.com",
              "ft.com", "forbes.com", "businessinsider.com"):
        assert d not in tms.NEWS_DOMAINS


def test_blocked_domains_are_parsed_from_the_400(tms):
    assert tms.blocked_domains_in(BLOCKED_400) == ["bizjournals.com", "reuters.com", "wsj.com"]
    assert tms.blocked_domains_in("Error code: 529 overloaded") == []
    assert tms.blocked_domains_in("") == []


def test_run_scan_drops_blocked_domains_and_retries_once(tms, monkeypatch):
    calls = []

    class _FF:
        _WARN_SEARCH_DOMAINS = ["dol.gov"]

        @staticmethod
        def _injection_guarded_system(s):
            return s

        @staticmethod
        def _safe_web_search_tool(max_uses=3, extra_domains=()):
            return {"allowed_domains": list(extra_domains)}

        @staticmethod
        def _claude_create_with_retry(client, **kw):
            calls.append(kw["tools"][0]["allowed_domains"])
            if len(calls) == 1:
                raise RuntimeError(BLOCKED_400.replace("'bizjournals.com', 'reuters.com', 'wsj.com'",
                                                       "'axios.com'"))
            return types.SimpleNamespace(content=[types.SimpleNamespace(text='{"companies": []}')])

    monkeypatch.setattr(tms, "_ff", lambda: _FF)
    monkeypatch.setattr(tms, "_BLOCKED_DOMAINS", set())
    v = {"label": "Logistics / 3PL", "band": "", "buyers": "", "roles": "", "tells": ""}
    text = tms.run_scan(object(), v, "USA", TODAY)
    assert "companies" in text and len(calls) == 2
    assert "axios.com" in calls[0] and "axios.com" not in calls[1]
    assert "dol.gov" in calls[1] and "prnewswire.com" in calls[1]
    # learned for the life of the process: the next scan never lists it
    assert "axios.com" not in tms.search_domains(_FF)

    # an unrelated error is raised straight away, no retry
    calls.clear()

    def _boom(client, **kw):
        calls.append(1)
        raise RuntimeError("Error code: 529 overloaded")
    monkeypatch.setattr(_FF, "_claude_create_with_retry", staticmethod(_boom))
    with pytest.raises(RuntimeError):
        tms.run_scan(object(), v, "USA", TODAY)
    assert len(calls) == 1


def test_run_issue_reports_research_failure_not_nothing_found(tms, tmp_path, monkeypatch):
    sent = []

    class _FF:
        ANTHROPIC_API_KEY = "k"
        BRAND = "inboxslide"
        _PUBLIC_ORIGIN = ""

        @staticmethod
        def _server_send_one(item, config_path, user_dir=None):
            sent.append(item)
            return True, ""

    monkeypatch.setattr(tms, "_ff", lambda: _FF)
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(
        Anthropic=lambda api_key: object()))

    def _fail(*a):
        raise RuntimeError("Error code: 400 - bad allowlist")
    monkeypatch.setattr(tms, "run_scan", _fail)
    tms.save_settings({"enabled": True, "industries": ["logistics", "manufacturing"]}, tmp_path)
    issue = tms.run_issue("mike@example.com", tmp_path, today=TODAY)
    assert sent == []
    assert issue["send_error"].startswith("Research failed: Error code: 400")
    assert "Nothing found" not in issue["send_error"]
    # one industry failing while the other is merely empty is still "nothing found"
    partial = {"sections": [{"error": "x", "companies": [], "news": []},
                            {"companies": [], "news": []}]}
    assert tms.issue_failure(partial) == ""
    assert tms.issue_failure({"sections": []}) == ""


def test_prompt_names_every_signal_and_the_window(tms):
    v = {"label": "Logistics / 3PL", "band": "25 to 1000", "buyers": "the COO",
         "roles": "track and trace", "tells": "McLeod"}
    p = tms.scan_prompt(v, "Texas", TODAY)
    for sig in tms.SIGNALS:
        assert f"- {sig['id']}:" in p
    assert "15 October 2026" in p and "Texas" in p and "last 14 days" in p
    assert "Direct employers only" in p


# ── host wiring ───────────────────────────────────────────────────────────

def test_host_routes_page_and_ticks_scheduler():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import flowdrip_app as fa
    router = inspect.getsource(fa.render_page)
    assert 'elif page == "tm_signals" and _is_thrivemodal():' in router
    assert "import tm_signals as _tms" in router
    loop = inspect.getsource(fa._start_server_scheduler)
    assert "_tm_signals_tick()" in loop
    assert "tm_signals" in inspect.getsource(fa._tm_signals_tick)
    index = inspect.getsource(fa.index)
    assert '("tm_signals", "tm_prompts")' in index and "_is_thrivemodal()" in index
    assert fa._SIDEBAR_ICONS.get("signals")


def test_settings_are_pills_that_save_on_click(tms):
    src = inspect.getsource(tms.render_page)
    assert "_settings_panel(" in src
    assert "ui.switch(" not in src and 'ui.label("Save")' not in src
    panel = inspect.getsource(tms._settings_panel)
    for bit in ("tms-pill", "tms-x", "drop(k)", "add(k)", "ui.menu()",
                "loc_dlg.open", "Next issue", "save()"):
        assert bit in panel


def test_user_picks_send_days(tms):
    mon = {"enabled": True, "industries": ["logistics"], "days": [0]}
    assert tms.is_due(mon, datetime(2026, 10, 19, 7, 0))         # Mon
    assert not tms.is_due(mon, datetime(2026, 10, 20, 9, 0))     # Tue
    assert not tms.is_due({**mon, "days": []}, datetime(2026, 10, 19, 9, 0))
    assert tms.send_days({}) == [1, 3]                            # default
    assert tms.send_days({"days": [3, "1", 9, "x"]}) == [1, 3]
    assert tms.next_send(datetime(2026, 10, 15, 8, 0), [0]) == datetime(2026, 10, 19, 7, 0)
    assert tms.days_phrase([0]) == "every Monday"
    assert tms.days_phrase([1, 3]) == "every Tuesday and Thursday"
    assert tms.days_phrase(range(5)) == "every weekday"
    html = tms.render_email({"date": "2026-10-15", "sections": []}, days=[0])
    assert "every Monday" in html


def test_days_row_on_page(tms):
    panel = inspect.getsource(tms._settings_panel)
    assert "flip_day(d)" in panel and "tms-day" in panel
    assert 'settings["days"]' in inspect.getsource(tms.render_page)

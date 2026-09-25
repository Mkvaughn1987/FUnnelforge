"""Sales Assets Autofill (inboxslide): one button looks the company up
from its name or website, fills the blank form fields, and shows the
positions it is hiring for right now as chips under Target Role. Mirrors
the New Campaign Target details Autofill."""
import inspect
import threading
from unittest.mock import MagicMock

import flowdrip_app as fa


class _SyncThread:
    def __init__(self, target=None, daemon=None, **kw):
        self._t = target

    def start(self):
        self._t()


def _msg(text):
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


LOOKUP = ('{"company":"M.C. Dean","website":"mcdean.com",'
          '"industry":"construction","location":"Tysons, VA"}')
ROLES = ('{"open_roles":["VDC Coordinator","Estimator","Electrician",'
         '"BIM Modeler","AP Specialist"],'
         '"offshore_pick":["VDC Coordinator","Estimator","AP Specialist"]}')


# ── pure helpers ───────────────────────────────────────────────────────

def test_autofill_fills_only_blank_fields(monkeypatch):
    monkeypatch.setattr(fa, "_tm_nationwide", lambda: True)
    cur = {"company": "", "website": "", "industry": "", "location": "",
           "role": ""}
    data = {"company": "M.C. Dean", "website": "mcdean.com",
            "industry": "construction", "location": "Tysons, VA"}
    out = fa._pdf_autofill_fields(cur, data, ["VDC Coordinator", "Estimator"])
    assert out == {"company": "M.C. Dean", "website": "mcdean.com",
                   "industry": "Construction", "location": "Nationwide",
                   "role": "VDC Coordinator, Estimator"}


def test_autofill_keeps_what_the_user_typed(monkeypatch):
    monkeypatch.setattr(fa, "_tm_nationwide", lambda: True)
    cur = {"company": "MC DEAN", "website": "www.mcdean.com",
           "industry": "MEP Construction", "location": "Nationwide Locations",
           "role": "VDC Manager"}
    data = {"company": "M.C. Dean", "website": "mcdean.com",
            "industry": "construction", "location": "Tysons, VA"}
    out = fa._pdf_autofill_fields(cur, data, ["Estimator"])
    assert out == {}


def test_autofill_replaces_a_company_typed_as_a_domain(monkeypatch):
    monkeypatch.setattr(fa, "_tm_nationwide", lambda: False)
    cur = {"company": "mcdean.com", "website": "", "industry": "",
           "location": "", "role": ""}
    data = {"company": "M.C. Dean", "website": "mcdean.com",
            "industry": "construction", "location": "Tysons, VA"}
    out = fa._pdf_autofill_fields(cur, data, [])
    assert out["company"] == "M.C. Dean"
    # Arena keeps the real city; only ThriveModal goes Nationwide.
    assert out["location"] == "Tysons, VA"
    assert "role" not in out


def test_autofill_passes_an_unknown_industry_through(monkeypatch):
    monkeypatch.setattr(fa, "_tm_nationwide", lambda: True)
    cur = {"company": "", "website": "", "industry": "", "location": "",
           "role": ""}
    out = fa._pdf_autofill_fields(cur, {"industry": "Fintech"}, [])
    assert out["industry"] == "Fintech"


def test_toggle_role_text_adds_and_removes():
    assert fa._pdf_toggle_role_text("", "Estimator") == "Estimator"
    assert fa._pdf_toggle_role_text("VDC Manager", "Estimator") == \
        "VDC Manager, Estimator"
    assert fa._pdf_toggle_role_text("VDC Manager, Estimator", "estimator") == \
        "VDC Manager"
    assert fa._pdf_toggle_role_text(" VDC Manager ,, Estimator ", "BIM") == \
        "VDC Manager, Estimator, BIM"


def test_role_titles_splits_the_comma_list():
    assert fa._pdf_role_titles("VDC Manager, Estimator,, ") == \
        ["VDC Manager", "Estimator"]
    assert fa._pdf_role_titles("") == []


# ── the background runner ──────────────────────────────────────────────

def _run(monkeypatch, replies, tm=True, **state):
    calls = []

    def _fake(client, **kw):
        calls.append(kw)
        r = replies[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return _msg(r)

    monkeypatch.setattr(threading, "Thread", _SyncThread)
    monkeypatch.setattr(fa, "_claude_create_with_retry", _fake)
    monkeypatch.setattr(fa, "_safe_web_search_tool",
                        lambda max_uses=1: {"max_uses": max_uses})
    monkeypatch.setattr(fa, "_tm_nationwide", lambda: tm)
    monkeypatch.setattr(fa, "ANTHROPIC_API_KEY", "x")
    s = fa.AppState()
    fa._ensure_pdf_state(s)
    for k, v in state.items():
        setattr(s, k, v)
    fa._pdf_ai_autofill(s, lambda: None)
    return s, calls


def test_runner_fills_the_form_and_the_chips(monkeypatch):
    s, calls = _run(monkeypatch, [LOOKUP, ROLES], _pdf_website="www.mcdean.com")
    assert s._pdf_af_running is False
    assert s._pdf_af_err == ""
    assert s._pdf_company == "M.C. Dean"
    assert s._pdf_website == "www.mcdean.com"      # typed, kept
    assert s._pdf_industry == "Construction"
    assert s._pdf_location == "Nationwide"
    assert s._pdf_role == "VDC Coordinator, Estimator, AP Specialist"
    # Electrician is on-site work, so it never becomes a chip.
    assert s._pdf_open_roles == ["VDC Coordinator", "Estimator",
                                 "BIM Modeler", "AP Specialist"]
    # The website drives the lookup; the roles call names the company.
    assert "www.mcdean.com" in calls[0]["messages"][0]["content"]
    assert "M.C. Dean" in calls[1]["messages"][0]["content"]


def test_runner_uses_the_company_name_when_no_website(monkeypatch):
    s, calls = _run(monkeypatch, [LOOKUP, ROLES], _pdf_company="MC DEAN")
    assert "MC DEAN" in calls[0]["messages"][0]["content"]
    assert s._pdf_company == "MC DEAN"              # typed, kept
    assert s._pdf_website == "mcdean.com"


def test_runner_skips_roles_off_thrivemodal(monkeypatch):
    s, calls = _run(monkeypatch, [LOOKUP], tm=False, _pdf_company="MC DEAN")
    assert len(calls) == 1
    assert s._pdf_location == "Tysons, VA"
    assert s._pdf_open_roles == []
    assert s._pdf_role == ""


def test_runner_reports_an_unmatched_company(monkeypatch):
    s, calls = _run(monkeypatch, ['{"error":"not found"}'],
                    _pdf_company="Some Unknown Co")
    assert "not found" in s._pdf_af_err
    assert s._pdf_af_running is False
    assert s._pdf_company == "Some Unknown Co"


def test_runner_needs_something_to_look_up(monkeypatch):
    s, calls = _run(monkeypatch, [LOOKUP])
    assert calls == []
    assert s._pdf_af_err


# ── the page ───────────────────────────────────────────────────────────

def test_sales_assets_page_offers_autofill_on_the_sales_instance():
    src = inspect.getsource(fa.p_pdf_gen)
    assert "Autofill with AI" in src
    assert "_pdf_ai_autofill(s, rf)" in src
    assert "if _SALES_MODE" in src
    assert "_pdf_open_roles" in src
    assert "_pdf_toggle_role_text" in src
    # Clear / New PDF forgets the chips too.
    clear = src[src.index("def _clear_pdf"):src.index("if s._pdf_company or s._pdf_role or s._pdf_result")]
    assert "_pdf_open_roles" in clear


def test_pdf_state_init_covers_autofill_fields():
    s = fa.AppState()
    fa._ensure_pdf_state(s)
    assert s._pdf_af_running is False
    assert s._pdf_af_err == ""
    assert s._pdf_open_roles == []


def test_company_lookup_is_shared_with_the_campaign_autofill():
    """One lookup helper feeds both Autofills, so a prompt fix lands in
    both places."""
    assert "_aicb_lookup_company(" in inspect.getsource(fa._aicb_ai_extract)
    assert "_aicb_lookup_company(" in inspect.getsource(fa._pdf_ai_autofill)

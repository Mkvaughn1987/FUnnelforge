"""Shared test stand-ins for the AI Prompts pages: a do-nothing nicegui,
a fake flowdrip_app and a helper that renders every view of a page.
(Moved out of inboxslide's test_tm_prompts.py when DD was made standalone.)"""
import pathlib
import re
import sys
import types
from contextvars import ContextVar


def _stub_nicegui():
    if "nicegui" in sys.modules:
        return
    try:
        import nicegui  # noqa: F401  (the real one, if installed)
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

        def __iter__(self):
            return iter(())

    ng.ui = _Any()
    sys.modules["nicegui"] = ng


class _Colours(dict):
    def __missing__(self, k):
        return "#000000"


_CITE_RE = re.compile(r"[\(\[<]\s*/?\s*cite\b[^>\)\]\n]{0,300}?[>\)\]]",
                      re.IGNORECASE)


def _real_strip_cite_tags(text):
    """What flowdrip_app._strip_cite_tags does, to the extent these tests
    depend on it: the markup goes, the wrapped text stays."""
    return _CITE_RE.sub("", text or "").strip()


class _Reply:
    def __init__(self, text):
        self.content = [types.SimpleNamespace(text=text)]


def _fake_ff(reply, key="sk-ant-test"):
    """flowdrip_app as recommend_tm needs it, recording the call."""
    m = types.ModuleType("flowdrip_app")
    m._BASE_DATA_DIR = pathlib.Path(".")
    m.C = _Colours()
    m.ANTHROPIC_API_KEY = key
    m.sent = {}
    m._injection_guarded_system = lambda base: "GUARD " + base
    m._WARN_SEARCH_DOMAINS = ["dol.gov", "edd.ca.gov"]
    m._safe_web_search_tool = lambda max_uses=3, extra_domains=(): {
        "type": "web_search_20250305", "name": "web_search",
        "max_uses": max_uses,
        "allowed_domains": ["indeed.com"] + list(extra_domains)}
    # The real one off flowdrip_app; the leak it prevents is the point.
    m._strip_cite_tags = _real_strip_cite_tags

    def _create(client, **kw):
        m.sent.update(kw)
        if isinstance(reply, Exception):
            raise reply
        return _Reply(reply)

    m._claude_create_with_retry = _create
    return m


def _fake_anthropic():
    a = types.ModuleType("anthropic")
    a.Anthropic = lambda api_key=None: types.SimpleNamespace(key=api_key)
    return a


def _fake_flowdrip(tmp_path):
    m = types.ModuleType("flowdrip_app")
    m._BASE_DATA_DIR = tmp_path
    m.C = _Colours()
    m._resolve_user_root = lambda: tmp_path / "user"
    m._CURRENT_USER_EMAIL = ContextVar("_CURRENT_USER_EMAIL", default="")
    return m


class _Session:
    _user_email = "mike@example.com"


def _render_all_views(aip, page, cat, tmp_path, monkeypatch, starter_id):
    monkeypatch.setitem(sys.modules, "flowdrip_app", _fake_flowdrip(tmp_path))
    rf = lambda: None  # noqa: E731
    s = _Session()
    page(s, rf)                                  # ask
    assert aip._CAT is cat
    aip._CAT = cat
    s._aip_req = aip._req_from_starter(cat.starter_by_id[starter_id])
    page(s, rf)                                  # confirm
    s._aip_prompt = aip.build_prompt(s._aip_req, cat)
    page(s, rf)                                  # result
    assert aip._setups_path() == tmp_path / "user" / cat.setups_file
    return s

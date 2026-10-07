"""Team profile mirroring: once the owner saves a team default, every
other user on that email domain reads the owner's company + brand
settings and logo, with nothing to set up themselves."""
import json

import pytest

import flowdrip_app as fa

OWNER = "michael.vaughn@arenastaffing.net"
REP = "shelley@arenastaffing.net"


def _udir(root, email):
    d = root / "users" / email.lower().replace("@", "_at_").replace(".", "_")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cfg(root, email, **fields):
    (_udir(root, email) / "dripdrop_config.json").write_text(
        json.dumps(fields), encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_BASE_DATA_DIR", tmp_path)
    monkeypatch.setattr(fa, "_SERVER_MODE", True)
    (tmp_path / "users.json").write_text(json.dumps({
        OWNER: {"name": "Michael Vaughn"},
        REP: {"name": "Shelley V", "is_tenant_admin": False},
        "leigh@arenastaffing.net": {"name": "Leigh", "is_tenant_admin": True},
    }), encoding="utf-8")
    _cfg(tmp_path, OWNER, company_name="Arena Direct Hire",
         company_website="http://www.arenastaffing.net",
         company_description="Direct hire for construction.",
         company_color="#606060", user_timezone="America/Denver")
    (_udir(tmp_path, OWNER) / "company_logo.png").write_bytes(b"\x89PNGowner")
    _cfg(tmp_path, REP, company_name="Arena Staffing",
         company_tagline='(cite index="8-3">Temp staffing</cite>',
         user_timezone="America/New_York")
    return tmp_path


def _as(email):
    return fa._CURRENT_USER_EMAIL.set(email)


def _make_owner(root):
    tok = _as(OWNER)
    try:
        assert fa._sync_team_profile_from(fa._load_own_config(), OWNER)
    finally:
        fa._CURRENT_USER_EMAIL.reset(tok)


def test_teammate_mirrors_owner_company_and_logo(env):
    _make_owner(env)
    tok = _as(REP)
    try:
        cfg = fa.load_config()
        assert cfg["company_name"] == "Arena Direct Hire"
        assert cfg["company_website"] == "http://www.arenastaffing.net"
        assert cfg["company_color"] == "#606060"
        assert "cite" not in cfg.get("company_tagline", "")
        # personal settings stay the rep's own
        assert cfg["user_timezone"] == "America/New_York"
        logo = fa._get_company_logo_path()
        assert "tenants" in logo and open(logo, "rb").read() == b"\x89PNGowner"
        assert fa._mirrors_team_profile()
    finally:
        fa._CURRENT_USER_EMAIL.reset(tok)


def test_owner_reads_own_config_and_tenant_admins_mirror_too(env):
    _make_owner(env)
    tok = _as(OWNER)
    try:
        assert not fa._mirrors_team_profile()
        assert fa.load_config()["user_timezone"] == "America/Denver"
    finally:
        fa._CURRENT_USER_EMAIL.reset(tok)
    tok = _as("leigh@arenastaffing.net")
    try:
        assert fa._mirrors_team_profile()
        assert fa.load_config()["company_name"] == "Arena Direct Hire"
    finally:
        fa._CURRENT_USER_EMAIL.reset(tok)


def test_owner_resave_updates_teammates(env):
    _make_owner(env)
    _cfg(env, OWNER, company_name="Arena Direct Hire", company_phone="443-791-0026")
    _make_owner(env)
    tok = _as(REP)
    try:
        assert fa.load_config()["company_phone"] == "443-791-0026"
    finally:
        fa._CURRENT_USER_EMAIL.reset(tok)


def test_no_team_profile_means_own_settings(env):
    tok = _as(REP)
    try:
        assert not fa._mirrors_team_profile()
        assert fa.load_config()["company_name"] == "Arena Staffing"
    finally:
        fa._CURRENT_USER_EMAIL.reset(tok)


def test_public_mail_domains_never_share(env):
    a, b = "alice@gmail.com", "bob@gmail.com"
    _cfg(env, a, company_name="Alice Co")
    _cfg(env, b, company_name="Bob Co")
    fa._save_tenant_profile({"company_name": "Alice Co", "_owner": a}, a)
    tok = _as(b)
    try:
        assert not fa._mirrors_team_profile()
        assert fa.load_config()["company_name"] == "Bob Co"
    finally:
        fa._CURRENT_USER_EMAIL.reset(tok)


def test_other_domains_isolated(env):
    _make_owner(env)
    o = "pat@othercorp.com"
    _cfg(env, o, company_name="OtherCorp")
    tok = _as(o)
    try:
        assert fa.load_config()["company_name"] == "OtherCorp"
        assert fa._get_company_logo_path() == ""
    finally:
        fa._CURRENT_USER_EMAIL.reset(tok)


def test_strip_cite_tags_handles_mangled_opener():
    s = '(cite index="2-7">+1-909-342-1244</cite>'
    assert fa._strip_cite_tags(s) == "+1-909-342-1244"
    assert fa._strip_cite_tags('<cite index="1-5">Ontario</cite>') == "Ontario"
    assert fa._strip_cite_tags("we cite sources and a > b") == "we cite sources and a > b"

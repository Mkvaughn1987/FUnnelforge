"""Client alias + Ref #: flowdrip_app.py side (card linking, refs, PDF names)."""
import sqlite3
import sys

import pytest

import flowdrip_app as fa
from tests.test_candidate_alias_refs_ats import _SCHEMA, OWNER


@pytest.fixture
def ats(tmp_path, monkeypatch):
    db = tmp_path / "ats.db"
    con = sqlite3.connect(str(db))
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    monkeypatch.setenv("ATS_DB_PATH", str(db))
    sys.modules.pop("ats", None)
    import ats as mod
    monkeypatch.setattr(fa, "_ats_allowed", lambda email: True)
    return mod


def _anon(**kw):
    c = {"label": "Candidate A", "role": "EHS Manager",
         "bullets": ["25 yrs EHS leadership", "EPA refrigeration credentials"]}
    c.update(kw)
    return c


def _identity(**kw):
    ident = {"name": "Travis Kruse", "email": "kruse-24@hotmail.com",
             "phone": "623-235-4346", "state": "AZ",
             "resume_text": "Travis Kruse EHS, refrigeration, OSHA."}
    ident.update(kw)
    return _anon(**ident)


def test_identity_card_is_added_and_stripped(ats):
    cards, err = fa._link_candidate_cards([_identity()], OWNER)
    assert err is None
    c = cards[0]
    for k in fa._CARD_IDENTITY_FIELDS:
        assert k not in c
    assert isinstance(c["_talent_id"], int)
    assert c["ref"] == "Ref #%d" % c["_talent_id"]
    assert c["alias"] and c["label"] == c["alias"]
    assert "Travis" not in c["label"]
    assert c["bullets"] == _anon()["bullets"]


def test_identity_card_dedupes_across_campaigns(ats):
    a, _ = fa._link_candidate_cards([_identity()], OWNER)
    b, _ = fa._link_candidate_cards([_identity(phone="")], OWNER)
    assert a[0]["_talent_id"] == b[0]["_talent_id"]
    assert a[0]["alias"] == b[0]["alias"]


def test_pool_id_card_links_and_keeps_pool_id(ats):
    t = ats.upsert_card_record({"name": "Travis Kruse", "email": "k@x.com"}, OWNER)
    cards, err = fa._link_candidate_cards([_anon(_pool_id=str(t["id"]))], OWNER)
    assert err is None
    assert cards[0]["_pool_id"] == str(t["id"])
    assert cards[0]["_talent_id"] == t["id"]
    assert cards[0]["alias"] == t["alias"]


@pytest.mark.parametrize("bad", ["abc", 999999])
def test_bad_pool_id_strict_errors_nonstrict_passes(ats, bad):
    card = _anon(_pool_id=bad)
    cards, err = fa._link_candidate_cards([card], OWNER)
    assert err and "card 1" in err
    cards, err = fa._link_candidate_cards([card], OWNER, strict=False)
    assert err is None and cards == [card]


def test_unaddable_person_strict_errors(ats):
    card = _anon(name="Travis", email="k@x.com")
    _, err = fa._link_candidate_cards([card], OWNER)
    assert err and "Travis" in err
    cards, err = fa._link_candidate_cards([card], OWNER, strict=False)
    assert err is None and cards == [card]


def test_synthetic_and_anonymous_cards_pass_through_with_warnings(ats):
    synth = _anon(label="Candidate B", _synthetic=True)
    anon = _anon()
    cards, err = fa._link_candidate_cards([anon, synth, _identity()], OWNER)
    assert err is None
    assert cards[0] == anon and cards[1] == synth
    warns = fa._unlinked_card_warnings(cards)
    assert len(warns) == 1 and "card 1" in warns[0]


def test_no_pipeline_access_leaves_cards_alone(ats, monkeypatch):
    monkeypatch.setattr(fa, "_ats_allowed", lambda email: False)
    card = _identity()
    cards, err = fa._link_candidate_cards([card], "x@gmail.com")
    assert err is None and cards == [card]
    assert ats.keyword_search("refrigeration") == []


def test_candidate_refs(ats):
    cards, _ = fa._link_candidate_cards([_anon(), _identity()], OWNER)
    refs = fa._candidate_refs(cards)
    assert refs == [{"slot": "B", "alias": cards[1]["alias"],
                     "ref": cards[1]["ref"], "talent_id": cards[1]["_talent_id"]}]


def test_post_pass_adds_missing_ref_once():
    cards = [{"alias": "Trent K.", "ref": "Ref #1042", "_talent_id": 1042}]
    emails = [
        {"subject": "Trent K.", "body": "Meet Trent K. today. Trent K. is great."},
        {"body": "Trent K. (Ref #1042) is ready."},
        {"body": "No candidate here."},
    ]
    fa._ensure_candidate_refs_in_emails(emails, cards)
    assert emails[0]["body"] == "Meet Trent K. (Ref #1042) today. Trent K. is great."
    assert emails[0]["subject"] == "Trent K."
    assert emails[1]["body"] == "Trent K. (Ref #1042) is ready."
    assert emails[2]["body"] == "No candidate here."


def test_redacted_pdf_names_unique_per_ref():
    assert fa._redacted_pdf_fname("Trent K.", 1042) == "Resume_Ref1042_Redacted.pdf"
    assert fa._redacted_pdf_fname("Trent K.", 1043) != fa._redacted_pdf_fname("Trent K.", 1042)
    assert fa._redacted_pdf_fname("Candidate A") == "Resume_Candidate_A_Redacted.pdf"
    assert fa._redacted_resume_label("Resume_Ref1042_Redacted.pdf") == "Ref #1042"
    assert fa._redacted_resume_label("Resume_Candidate_A_Redacted.pdf") == "Candidate A"


def test_candidate_block_cites_ref():
    block = fa._format_candidate_block(
        [{"label": "Trent K.", "ref": "Ref #1042", "role": "EHS Manager",
          "bullets": ["x"]}, {"label": "Candidate B", "role": "Tech"}],
        "fivebythree")
    assert "Trent K. (Ref #1042): EHS Manager" in block
    assert "Candidate B: Tech" in block

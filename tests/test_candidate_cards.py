"""Round-trip serialization between _aicb_cand_text (plain text) and
aicb_cand_cards (list of dicts)."""


SAMPLE_TEXT = (
    "Candidate A: CNC Machinist, 10+ yrs at Sandvik Coromant\n"
    "• Location: Grand Rapids, MI\n"
    "• Experience: 10+ years\n"
    "• Skills: Mill, lathe, GD&T\n"
    "\n"
    "Candidate B: Mill Operator, 5+ yrs at Haas\n"
    "• Location: Denver, CO\n"
    "• Experience: 5+ years"
)


def test_cards_from_text_parses_two_candidates(isolated_appdata, with_user):
    import flowdrip_app as fa
    cards = fa._aicb_cards_from_text(SAMPLE_TEXT)
    assert len(cards) == 2
    assert cards[0]["label"] == "Candidate A"
    assert "CNC Machinist" in cards[0]["role"]
    assert "Grand Rapids, MI" in cards[0]["bullets"][0]


def test_cards_to_text_round_trip(isolated_appdata, with_user):
    import flowdrip_app as fa
    cards = fa._aicb_cards_from_text(SAMPLE_TEXT)
    text = fa._aicb_cards_to_text(cards)
    cards2 = fa._aicb_cards_from_text(text)
    assert cards == cards2


def test_cards_from_empty_text(isolated_appdata, with_user):
    import flowdrip_app as fa
    assert fa._aicb_cards_from_text("") == []
    assert fa._aicb_cards_from_text(None) == []

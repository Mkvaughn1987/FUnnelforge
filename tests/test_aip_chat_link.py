"""AI Prompts: Open in Claude / ChatGPT puts the prompt in the new chat."""
import json
import os
import urllib.parse

import ai_prompts as aip

_GOLDEN = os.path.join(os.path.dirname(__file__), "fixtures",
                       "ai_prompts_golden.json")


def _q(url):
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["q"][0]


def test_prompt_rides_in_the_link_intact():
    prompt = "Line one & 50% done?\nLine #2 = \"quoted\" / ok"
    for base in ("https://claude.ai/new", "https://chatgpt.com/"):
        url, filled = aip.chat_link(base, prompt)
        assert filled and url.startswith(base + "?q=")
        assert _q(url) == prompt


def test_too_long_falls_back_to_a_blank_chat():
    url, filled = aip.chat_link("https://claude.ai/new", "x" * aip.CHAT_LINK_MAX)
    assert (url, filled) == ("https://claude.ai/new", False)


def test_every_stock_prompt_fits():
    for row in json.load(open(_GOLDEN, encoding="utf-8")):
        for base in ("https://claude.ai/new", "https://chatgpt.com/"):
            assert aip.chat_link(base, row["prompt"])[1], row["name"]

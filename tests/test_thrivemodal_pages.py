"""ThriveModal public landing pages served from static/ThriveModal.

Mounted per section (/ThriveModal/Construction, /ThriveModal/HR) so the
Testimonials route /ThriveModal/review/<token> is not swallowed.
"""
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import flowdrip_app as fa

PAGES = Path(fa._APP_DIR) / "static" / "ThriveModal"


@pytest.fixture(scope="module")
def client():
    return TestClient(fa.app)


def _all_pages():
    return sorted(PAGES.rglob("index.html"))


def test_every_page_serves(client):
    pages = _all_pages()
    assert len(pages) == 12
    for p in pages:
        url = "/ThriveModal/" + p.parent.relative_to(PAGES).as_posix() + "/"
        r = client.get(url)
        assert r.status_code == 200, url
        assert "text/html" in r.headers["content-type"]


def test_every_internal_link_and_image_resolves(client):
    seen = set()
    for p in _all_pages():
        html = p.read_text(encoding="utf-8")
        for ref in re.findall(r'(?:href|src)="(/ThriveModal/[^"#?]*)', html):
            seen.add(ref)
    assert seen
    for ref in sorted(seen):
        assert client.get(ref).status_code == 200, ref


def test_folder_without_slash_and_lowercase_redirect(client):
    assert client.get("/ThriveModal/Construction").status_code == 200
    assert client.get("/thrivemodal/construction").status_code == 200
    assert client.get("/thrivemodal/hr/hr-generalist/").status_code == 200
    r = client.get("/thrivemodal/construction/estimator/", follow_redirects=False)
    assert r.headers["location"] == "/ThriveModal/Construction/estimator/"
    assert client.get("/thrivemodal/nope", follow_redirects=False).status_code == 404


def test_review_route_not_swallowed(client):
    # Unknown token is the Testimonials route's own 404, not a static-file miss.
    r = client.get("/ThriveModal/review/nottherealtoken")
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]

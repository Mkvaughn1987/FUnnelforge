"""Create Your Own PDF on a ThriveModal workspace (2026-09-21): the gallery
is offshore-Filipino-staffing ideas, the generator is held to the playbook,
and every title leads with ThriveModal. Arena keeps its recruiter gallery."""
import re
from types import SimpleNamespace

import flowdrip_app as fa


def test_tm_gallery_is_offshore_and_arena_gallery_is_untouched():
    assert len(fa._TM_CUSTOM_PDF_GALLERY) >= 12
    assert fa._CUSTOM_PDF_GALLERY[0][0] == "Talent Market Briefing"
    titles = {t for t, _ in fa._TM_CUSTOM_PDF_GALLERY}
    assert not titles & {t for t, _ in fa._CUSTOM_PDF_GALLERY}


def test_tm_gallery_stays_inside_the_claim_rules():
    for title, desc in fa._TM_CUSTOM_PDF_GALLERY:
        text = f"{title} {desc}".lower()
        assert "$" not in text, title
        assert "24/7" not in text and "zero risk" not in text, title
        assert "retention" not in text and "native english" not in text, title
        assert "guarantee" not in text, title
        # the only percentage allowed is the approved ceiling
        for pct in re.findall(r"\d[\d-]*%", text):
            assert pct == "60-70%" and "up to 60-70%" in text, title


def _capture_client(reply):
    seen = []

    def _create(client, **kw):
        seen.append(kw["messages"][0]["content"])
        return SimpleNamespace(content=[SimpleNamespace(text=reply)])
    return seen, _create


def test_tm_outline_prompt_carries_the_playbook(monkeypatch):
    seen, fake = _capture_client('{"title": "T", "sections": []}')
    monkeypatch.setattr(fa, "_claude_create_with_retry", fake)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    monkeypatch.setattr(fa, "_thrivemodal_playbook_text", lambda cfg=None: "PLAYBOOK-X")
    fa._custom_pdf_outline(None, "Offshore Savings Snapshot", "Company: Acme\n")
    assert "PLAYBOOK-X" in seen[0] and "Philippines-based" in seen[0]
    assert 'starts with "ThriveModal"' in seen[0]


def test_arena_outline_prompt_has_no_playbook(monkeypatch):
    seen, fake = _capture_client('{"title": "T", "sections": []}')
    monkeypatch.setattr(fa, "_claude_create_with_retry", fake)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    fa._custom_pdf_outline(None, "Talent Market Briefing", "Company: Acme\n")
    assert "staffing recruiter" in seen[0] and "ThriveModal" not in seen[0]


def test_tm_build_prefixes_the_title_and_holds_the_rules(monkeypatch, tmp_path):
    seen, fake = _capture_client(
        '{"title": "Offshore Savings Snapshot", "sections": [], "cta": "x"}')
    monkeypatch.setattr(fa, "_claude_create_with_retry", fake)
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    monkeypatch.setattr(fa, "_thrivemodal_playbook_text", lambda cfg=None: "PLAYBOOK-X")
    built = {}
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(fa.__file__).resolve().parent / "funnel_forge"))
    import arena_pdfs
    monkeypatch.setattr(arena_pdfs, "build_custom_pdf",
                        lambda path, d: built.update(d))
    monkeypatch.setattr(fa, "_save_pdf_sidecar", lambda *a: None)
    monkeypatch.setattr(fa, "_publish_pdf", lambda *a: None)
    monkeypatch.setattr(fa, "_get_company_logo_path", lambda: "")
    fname = fa._custom_pdf_build(None, {"title": "T", "sections": []},
                                 "desc here", "Company: Acme\n",
                                 tmp_path, tmp_path / "cfg.json")
    assert built["title"] == "ThriveModal Offshore Savings Snapshot"
    assert fname.startswith("ThriveModal_")
    assert "THRIVEMODAL RULES" in seen[0] and "PLAYBOOK-X" in seen[0]

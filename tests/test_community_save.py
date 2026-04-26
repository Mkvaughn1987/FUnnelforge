"""C11: community save must be atomic and never silently overwrite."""
import json
import pathlib
import pytest


def test_copy_community_to_local_avoids_overwrite(isolated_appdata, with_user):
    import flowdrip_app as fa

    camp = {"name": "Cool Outreach", "steps": [], "_community": True}

    out1 = fa.copy_community_to_local(camp)
    p1 = pathlib.Path(out1["_path"])
    assert p1.exists()

    p1.write_text(json.dumps({"name": "Cool Outreach", "marker": "ORIGINAL"}, indent=2),
                  encoding="utf-8")

    out2 = fa.copy_community_to_local(camp)
    p2 = pathlib.Path(out2["_path"])
    assert p2 != p1, "copy_community_to_local must rename on collision, not overwrite"
    assert "ORIGINAL" in p1.read_text(encoding="utf-8")


def test_save_to_community_timestamps_on_collision(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    # Patch COMMUNITY_DIR to a writable isolated location
    community_dir = with_user / "Community"
    community_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(fa, "COMMUNITY_DIR", community_dir)

    camp = {"name": "Shared Plan", "steps": []}
    p1 = fa.save_to_community(camp)
    assert p1.exists()
    p1.write_text(json.dumps({"marker": "FIRST"}, indent=2), encoding="utf-8")

    p2 = fa.save_to_community(camp)
    assert p2 != p1, "save_to_community must add a timestamp suffix on collision"
    assert "FIRST" in p1.read_text(encoding="utf-8"), "original must not be overwritten"

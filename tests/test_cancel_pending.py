"""C6: cancel-pending must be case/whitespace-insensitive on campaign name."""
import json
import pathlib
import pytest


def test_cancel_pending_normalizes_campaign_name(isolated_appdata, with_user, monkeypatch):
    import flowdrip_app as fa

    # Disable the funnelforge_core fast path; we want the JSON fallback path.
    monkeypatch.setattr(fa, "_FUNNELFORGE_OK", False)
    monkeypatch.setattr(fa, "_ffc", None)

    qp = fa._user_queue_path()
    qp.parent.mkdir(parents=True, exist_ok=True)
    queue = [
        {"id": "1", "to": "lead@example.com", "campaign": "My Campaign", "status": "pending"},
        {"id": "2", "to": "lead@example.com", "campaign": "My  Campaign ", "status": "pending"},
        {"id": "3", "to": "lead@example.com", "campaign": "Other", "status": "pending"},
    ]
    qp.write_text(json.dumps(queue), encoding="utf-8")

    n = fa._cancel_pending_for_email_in_campaign("lead@example.com", "my campaign")
    assert n == 2  # IDs 1 and 2 should both match (case + whitespace insensitive)

    final = json.loads(qp.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in final}
    assert by_id["1"]["status"] == "cancelled"
    assert by_id["2"]["status"] == "cancelled"
    assert by_id["3"]["status"] == "pending"

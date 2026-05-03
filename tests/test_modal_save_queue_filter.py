"""Modal _save's queue sync must use positive-match filtering: only update
queue items that match by step_name OR previous subject. Steps with empty
names must NOT cause cross-step overwrites."""

import json


def _make_minimal_save_logic():
    """Mirror the queue-filter logic from _save inside _edit_newsletter_modal,
    extracted as a pure function for testability. Mirrors the production
    code in flowdrip_app.py — keep in sync."""

    def _filter_and_update(queue, camp_name, step_name, prev_subj,
                           new_subject, new_body):
        """Match queue items by (campaign + status='pending') AND
        (step_name OR prev_subj). Update matching items' subject/body."""
        n = 0
        for q in queue:
            if q.get("campaign") != camp_name:
                continue
            if q.get("status") != "pending":
                continue
            _q_name = (q.get("step_name") or "").strip()
            _q_subj = (q.get("subject") or "").strip()
            _matches = False
            if step_name:
                # Step has a name: match ONLY by step_name.
                # Don't fall back to subject — would cause cross-step
                # overwrites when subjects collide.
                if _q_name == step_name:
                    _matches = True
            elif prev_subj and _q_subj == prev_subj:
                # No step_name: fall back to previous subject.
                _matches = True
            if not _matches:
                continue
            q["subject"] = new_subject
            q["body"] = new_body
            n += 1
        return n


    return _filter_and_update


def test_empty_step_name_does_not_blast_other_steps():
    """When step.name is empty, the filter must NOT update every queue item
    in the campaign — it should only update items matching the previous
    subject."""
    filt = _make_minimal_save_logic()
    queue = [
        {"campaign": "C1", "status": "pending", "step_name": "",
         "subject": "Issue 1", "body": "old1"},
        {"campaign": "C1", "status": "pending", "step_name": "",
         "subject": "Issue 2", "body": "old2"},
        {"campaign": "C1", "status": "pending", "step_name": "",
         "subject": "Issue 3", "body": "old3"},
    ]
    n = filt(queue, "C1", step_name="", prev_subj="Issue 2",
             new_subject="Updated Issue 2", new_body="newbody")
    assert n == 1
    by_subj = {q["body"] for q in queue}
    assert by_subj == {"old1", "newbody", "old3"}
    # Item with subject "Issue 2" got updated; others untouched.
    assert next(q for q in queue if q["body"] == "newbody")["subject"] == "Updated Issue 2"


def test_step_name_match_wins_when_present():
    filt = _make_minimal_save_logic()
    queue = [
        {"campaign": "C1", "status": "pending", "step_name": "intro",
         "subject": "Hi", "body": "old"},
        {"campaign": "C1", "status": "pending", "step_name": "outro",
         "subject": "Hi", "body": "old"},
    ]
    n = filt(queue, "C1", step_name="intro", prev_subj="Hi",
             new_subject="HiNew", new_body="newbody")
    assert n == 1
    intro = next(q for q in queue if q["step_name"] == "intro")
    outro = next(q for q in queue if q["step_name"] == "outro")
    assert intro["body"] == "newbody"
    assert outro["body"] == "old"


def test_no_match_no_update():
    filt = _make_minimal_save_logic()
    queue = [
        {"campaign": "C1", "status": "pending", "step_name": "x",
         "subject": "A", "body": "old"},
    ]
    n = filt(queue, "C1", step_name="y", prev_subj="B",
             new_subject="updated", new_body="newbody")
    assert n == 0
    assert queue[0]["body"] == "old"


def test_other_campaigns_untouched():
    filt = _make_minimal_save_logic()
    queue = [
        {"campaign": "C1", "status": "pending", "step_name": "intro",
         "subject": "Hi", "body": "c1"},
        {"campaign": "C2", "status": "pending", "step_name": "intro",
         "subject": "Hi", "body": "c2"},
    ]
    filt(queue, "C1", step_name="intro", prev_subj="Hi",
         new_subject="HiNew", new_body="newbody")
    c2 = next(q for q in queue if q["campaign"] == "C2")
    assert c2["body"] == "c2"


def test_sent_items_untouched():
    filt = _make_minimal_save_logic()
    queue = [
        {"campaign": "C1", "status": "sent", "step_name": "intro",
         "subject": "Hi", "body": "old"},
        {"campaign": "C1", "status": "pending", "step_name": "intro",
         "subject": "Hi", "body": "old"},
    ]
    n = filt(queue, "C1", step_name="intro", prev_subj="Hi",
             new_subject="HiNew", new_body="newbody")
    assert n == 1
    sent = next(q for q in queue if q["status"] == "sent")
    pending = next(q for q in queue if q["status"] == "pending")
    assert sent["body"] == "old"  # untouched
    assert pending["body"] == "newbody"

"""Autofill's Target Positions only offer work an offshore team member can
do remotely: the prompt asks for remote-capable postings, and
_tm_remote_capable drops any on-site title that slips through, from the
chips and from the ticks alike."""
import inspect
from unittest.mock import MagicMock

import flowdrip_app as fa


def _msg(text):
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def test_remote_capable_keeps_desk_work():
    for t in ("Dispatcher", "AP/AR Specialist", "Logistics Coordinator",
              "IT Support Technician", "VDC Coordinator", "Construction Scheduler",
              "Bookkeeper", "Customer Service Representative", "Receptionist",
              "Estimator", "Project Coordinator", "Marketing Coordinator"):
        assert fa._tm_remote_capable(t), t


def test_remote_capable_drops_in_person_work():
    for t in ("CDL Driver", "Service Technician", "Warehouse Associate",
              "Forklift Operator", "HVAC Technician", "Plumber", "Electrician",
              "Field Service Coordinator", "Site Superintendent", "Welder",
              "Machine Operator", "Registered Nurse", "Delivery Driver",
              "General Laborer", "Shop Foreman", "Plant Manager", ""):
        assert not fa._tm_remote_capable(t), t


def test_research_filters_chips_and_ticks(monkeypatch):
    reply = ('{"open_roles":["CDL Driver","Dispatcher","Warehouse Associate",'
             '"AP/AR Specialist","Service Technician","Customer Service '
             'Representative"],"offshore_pick":["Dispatcher","CDL Driver",'
             '"AP/AR Specialist"]}')
    monkeypatch.setattr(fa, "_claude_create_with_retry",
                        lambda client, **kw: _msg(reply))
    monkeypatch.setattr(fa, "_safe_web_search_tool", lambda max_uses=1: {})
    out = fa._tm_research_offshore_roles(object(), "Acme", "acme.com", "")
    assert out["open"] == ["Dispatcher", "AP/AR Specialist",
                           "Customer Service Representative"]
    assert out["picks"] == ["Dispatcher", "AP/AR Specialist"]


def test_prompt_asks_for_remote_capable_postings_only():
    p = fa._tm_offshore_roles_prompt("Acme", "acme.com", "Construction")
    assert "could be done remotely by an offshore team member" in p
    assert "Leave out every posting that must be done in person" in p
    assert "an offshore team could do fully remotely" in p


def test_picker_hint_says_remote():
    src = inspect.getsource(fa._render_tm_positions_picker)
    assert "Positions they are hiring for right now that can be done " in src
    assert "remotely. Tick the ones to pitch" in src

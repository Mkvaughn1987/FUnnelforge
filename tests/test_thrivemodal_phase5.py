"""ThriveModal Phase 5 — multi-mailbox sending, per-mailbox caps, warmup.

The handoff calls this out as risk R8: one mailbox per user, no warmup, and a
250/day config cap that deliverability limits bite through long before the
config does. Today `_server_scheduler_tick` reads ONE `dripdrop_config.json`
per user, sends everything through whichever OAuth token that file holds, and
budgets the day against a single `daily_send_limit`.

Phase 5 adds a per-user mailbox registry on top of that, without rewriting the
sender. The seam already exists in two places and Phase 5 uses both rather
than inventing a third:

  * `_server_send_one(item, config_path, user_dir)` already takes the config
    path as a PARAMETER, and both OAuth modules (`ms_email`, `gmail_oauth`)
    are entirely `config_path`-driven — tokens are flat keys in whatever file
    you hand them. So a second mailbox is a second config file, not a new
    sending path.
  * Both OAuth callbacks already accept a `state` query param and currently
    ignore it, and `get_auth_url(state=...)` already threads it. So
    "connect ANOTHER mailbox" is a marker in `state`, and every ordinary
    connect — all of Arena's — is unchanged because it carries no marker.

What the tests pin, and why each group is load-bearing:

  * Group A — the registry. Mailbox ids reach the filesystem as a path
    component, and they are derived from an email address the user typed, so
    id sanitisation is a security property and not a tidiness one. A registry
    that fails to load must read as "no registry" (single-mailbox behaviour),
    never as an exception on the send path.

  * Group B — the warmup ramp. This is the whole point of the phase: a
    brand-new mailbox that starts at 250/day gets burned. The ramp is pure
    date arithmetic, so it is pinned exactly: the floor on day one, the full
    cap on the last day, monotonic in between, and never above the cap the
    user set.

  * Group C — budgets and rotation. The accounting has to survive the
    upgrade: emails already sent today, before Phase 5 existed, carry no
    mailbox stamp. Attributing them to nobody would hand the user a free
    extra day's allowance on the day they upgrade, so they are attributed to
    the primary — which is factually where they went.

  * Group D/E — routing and the OAuth state marker, including that a FORGED
    state cannot write outside the user's own mailbox directory.

  * Group F — send-loop wiring and Arena isolation, same guard shape as
    Phases 2, 3 and 4: this phase edits Arena's live sending loop, so the
    branch must be provably inert for a user with no registry.

Written against the spec, not the implementation. Every test in Groups A-E
was red before the Phase 5 splice.
"""
import ast
import datetime as _dt
import json

import pytest


# NEVER import flowdrip_app at module level (see tests/conftest.py).

@pytest.fixture
def fa(isolated_appdata, with_user, monkeypatch):
    """flowdrip_app with the instance playbook lock cleared."""
    import flowdrip_app as _fa
    monkeypatch.setattr(_fa, "_LOCKED_PLAYBOOK", "")
    return _fa


@pytest.fixture
def tm(fa, monkeypatch):
    """flowdrip_app in a ThriveModal workspace."""
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: True)
    return fa


@pytest.fixture
def arena(fa, monkeypatch):
    """flowdrip_app in an Arena workspace."""
    monkeypatch.setattr(fa, "_is_thrivemodal", lambda cfg=None: False)
    return fa


def _src(fa):
    from pathlib import Path
    return Path(fa.__file__).read_text(encoding="utf-8")


def _tree(fa):
    return ast.parse(_src(fa))


def _func(tree, name):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _names_in(node):
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.add(sub.attr)
    return out


# Helpers Phase 5 adds that must never run for an Arena user.
_TM_MAILBOX_NAMES = {
    "_tm_mailboxes_path", "_tm_load_mailboxes", "_tm_write_mailboxes",
    "_tm_normalise_mailbox", "_tm_mailbox_id", "_tm_warmup_cap",
    "_tm_mailbox_budgets", "_tm_pick_mailbox", "_tm_mailbox_config_path",
    "_tm_state_mailbox_id", "_tm_connect_target_path",
    "_tm_save_mailbox", "_tm_delete_mailbox", "_tm_connect_state",
}

# The helpers themselves, plus the one function whose entire job is to decide
# whether the gate applies, are exempt from "must also reference the gate".
_MAILBOX_CHAIN_EXEMPT = _TM_MAILBOX_NAMES

_GATE_NAMES = {"_is_thrivemodal", "_LOCKED_PLAYBOOK", "_workspace_playbook"}


def _mb(**kw):
    """A registry row as the UI would hand it in."""
    row = {"id": "primary", "email": "a@example.com", "daily_cap": 250,
           "warmup_start": "", "warmup_days": 21, "paused": False}
    row.update(kw)
    return row


# ─────────────────────────────────────────────────────────────────────────
# Group A — the mailbox registry
# ─────────────────────────────────────────────────────────────────────────

def test_01_no_registry_file_reads_as_empty(tm, with_user):
    assert tm._tm_load_mailboxes(with_user) == []


def test_02_unreadable_registry_reads_as_empty(tm, with_user):
    (with_user / "tm_mailboxes.json").write_text("{not json", encoding="utf-8")
    assert tm._tm_load_mailboxes(with_user) == []


def test_03_wrong_shape_registry_reads_as_empty(tm, with_user):
    (with_user / "tm_mailboxes.json").write_text('{"a": 1}', encoding="utf-8")
    assert tm._tm_load_mailboxes(with_user) == []


def test_04_round_trip(tm, with_user):
    rows = [_mb(id="primary", email="a@example.com"),
            _mb(id="second", email="b@example.com", daily_cap=100)]
    tm._tm_write_mailboxes(rows, with_user)
    got = tm._tm_load_mailboxes(with_user)
    assert [r["id"] for r in got] == ["primary", "second"]
    assert got[1]["daily_cap"] == 100


def test_05_registry_order_is_preserved_not_sorted(tm, with_user):
    """Order is the rotation's tiebreak, so it is data, not presentation."""
    rows = [_mb(id="zzz", email="z@example.com"),
            _mb(id="aaa", email="a@example.com")]
    tm._tm_write_mailboxes(rows, with_user)
    assert [r["id"] for r in tm._tm_load_mailboxes(with_user)] == ["zzz", "aaa"]


def test_06_blank_email_is_rejected(tm):
    with pytest.raises(ValueError):
        tm._tm_normalise_mailbox({"email": "   "})


def test_07_rows_without_an_email_are_dropped_not_fatal(tm, with_user):
    (with_user / "tm_mailboxes.json").write_text(
        json.dumps([{"email": ""}, _mb(email="ok@example.com", id="ok")]),
        encoding="utf-8")
    got = tm._tm_load_mailboxes(with_user)
    assert [r["email"] for r in got] == ["ok@example.com"]


def test_08_id_is_derived_from_the_email_when_absent(tm):
    row = tm._tm_normalise_mailbox({"email": "Mike.V@ThriveModal.com"})
    assert row["id"] == tm._tm_mailbox_id("Mike.V@ThriveModal.com")
    assert row["id"]


def test_09_mailbox_id_is_a_safe_slug(tm):
    """The id becomes a path component, so nothing but [a-z0-9_-] survives."""
    import re
    for raw in ("Mike.V@ThriveModal.com", "a b/c", "../../../etc/passwd",
                "..\\..\\win.ini", "UPPER@X.COM", "a+b@c.d"):
        got = tm._tm_mailbox_id(raw)
        assert re.fullmatch(r"[a-z0-9_-]+", got), (raw, got)


def test_10_mailbox_id_never_yields_a_traversal(tm):
    for raw in ("../../etc/passwd", "..", ".", "/", "\\", "../"):
        assert ".." not in tm._tm_mailbox_id(raw)
        assert "/" not in tm._tm_mailbox_id(raw)
        assert "\\" not in tm._tm_mailbox_id(raw)


def test_11_unknown_keys_are_dropped(tm):
    row = tm._tm_normalise_mailbox({"email": "a@b.com", "contacts": [1, 2, 3],
                                    "access_token": "secret"})
    assert "contacts" not in row
    assert "access_token" not in row, "tokens live in the config file, never the registry"


def test_12_daily_cap_is_clamped_and_integral(tm):
    assert tm._tm_normalise_mailbox({"email": "a@b.com", "daily_cap": 99999})["daily_cap"] <= 500
    assert tm._tm_normalise_mailbox({"email": "a@b.com", "daily_cap": -5})["daily_cap"] >= 0
    assert isinstance(tm._tm_normalise_mailbox({"email": "a@b.com", "daily_cap": "40"})["daily_cap"], int)
    assert tm._tm_normalise_mailbox({"email": "a@b.com", "daily_cap": "junk"})["daily_cap"] == 250


# ─────────────────────────────────────────────────────────────────────────
# Group B — the warmup ramp
# ─────────────────────────────────────────────────────────────────────────

def test_13_no_warmup_start_means_the_flat_cap(tm):
    assert tm._tm_warmup_cap(_mb(daily_cap=250, warmup_start=""), "2026-09-17") == 250


def test_14_day_one_is_the_floor(tm):
    box = _mb(daily_cap=250, warmup_start="2026-09-17", warmup_days=21)
    assert tm._tm_warmup_cap(box, "2026-09-17") == tm._TM_WARMUP_FLOOR


def test_15_last_day_reaches_the_full_cap(tm):
    box = _mb(daily_cap=250, warmup_start="2026-09-01", warmup_days=21)
    assert tm._tm_warmup_cap(box, "2026-09-22") == 250


def test_16_after_warmup_stays_at_the_cap(tm):
    box = _mb(daily_cap=250, warmup_start="2026-01-01", warmup_days=21)
    assert tm._tm_warmup_cap(box, "2026-09-17") == 250


def test_17_ramp_is_monotonic_and_never_exceeds_the_cap(tm):
    box = _mb(daily_cap=250, warmup_start="2026-09-01", warmup_days=21)
    start = _dt.date(2026, 9, 1)
    prev = -1
    for d in range(0, 40):
        cap = tm._tm_warmup_cap(box, (start + _dt.timedelta(days=d)).isoformat())
        assert cap >= prev, f"ramp went backwards on day {d}"
        assert tm._TM_WARMUP_FLOOR <= cap <= 250, (d, cap)
        prev = cap


def test_18_paused_mailbox_gets_no_allowance(tm):
    assert tm._tm_warmup_cap(_mb(paused=True, daily_cap=250), "2026-09-17") == 0


def test_19_a_cap_below_the_floor_is_not_ramped_upward(tm):
    """A user who deliberately set 5/day means 5/day, not the warmup floor."""
    box = _mb(daily_cap=5, warmup_start="2026-09-17", warmup_days=21)
    assert tm._tm_warmup_cap(box, "2026-09-17") == 5


def test_20_a_future_start_behaves_like_day_one(tm):
    box = _mb(daily_cap=250, warmup_start="2026-12-01", warmup_days=21)
    assert tm._tm_warmup_cap(box, "2026-09-17") == tm._TM_WARMUP_FLOOR


def test_21_garbage_dates_never_raise(tm):
    for bad in ("not-a-date", "2026-13-45", None, 17, ""):
        cap = tm._tm_warmup_cap(_mb(warmup_start=bad), "2026-09-17")
        assert isinstance(cap, int) and cap >= 0
    for bad_today in ("nope", None, ""):
        cap = tm._tm_warmup_cap(_mb(warmup_start="2026-09-01"), bad_today)
        assert isinstance(cap, int) and cap >= 0


def test_22_zero_warmup_days_means_no_ramp(tm):
    box = _mb(daily_cap=250, warmup_start="2026-09-17", warmup_days=0)
    assert tm._tm_warmup_cap(box, "2026-09-17") == 250


# ─────────────────────────────────────────────────────────────────────────
# Group C — budgets and rotation
# ─────────────────────────────────────────────────────────────────────────

def _sent(mailbox=None, day="2026-09-17"):
    row = {"status": "sent", "sent_at": f"{day}T09:00:00"}
    if mailbox is not None:
        row["tm_mailbox"] = mailbox
    return row


def test_23_fresh_day_gives_every_mailbox_its_full_cap(tm):
    boxes = [_mb(id="primary", daily_cap=250), _mb(id="second", email="b@x.com", daily_cap=100)]
    b = tm._tm_mailbox_budgets(boxes, [], "2026-09-17")
    assert b == {"primary": 250, "second": 100}


def test_24_sends_are_deducted_from_their_own_mailbox(tm):
    boxes = [_mb(id="primary", daily_cap=250), _mb(id="second", email="b@x.com", daily_cap=100)]
    queue = [_sent("second")] * 10
    b = tm._tm_mailbox_budgets(boxes, queue, "2026-09-17")
    assert b == {"primary": 250, "second": 90}


def test_25_legacy_unstamped_sends_are_charged_to_the_primary(tm):
    """Upgrading mid-day must not hand the user a free extra allowance."""
    boxes = [_mb(id="primary", daily_cap=250), _mb(id="second", email="b@x.com", daily_cap=100)]
    b = tm._tm_mailbox_budgets(boxes, [_sent(None)] * 40, "2026-09-17")
    assert b == {"primary": 210, "second": 100}


def test_26_sends_from_other_days_do_not_count(tm):
    boxes = [_mb(id="primary", daily_cap=250)]
    queue = [_sent("primary", day="2026-09-16")] * 200
    assert tm._tm_mailbox_budgets(boxes, queue, "2026-09-17") == {"primary": 250}


def test_27_pending_and_failed_items_do_not_count(tm):
    boxes = [_mb(id="primary", daily_cap=250)]
    queue = [{"status": "pending", "tm_mailbox": "primary"},
             {"status": "failed", "sent_at": "2026-09-17T09:00:00", "tm_mailbox": "primary"}]
    assert tm._tm_mailbox_budgets(boxes, queue, "2026-09-17") == {"primary": 250}


def test_28_sends_stamped_to_a_removed_mailbox_are_ignored(tm):
    boxes = [_mb(id="primary", daily_cap=250)]
    assert tm._tm_mailbox_budgets(boxes, [_sent("deleted")] * 50, "2026-09-17") == {"primary": 250}


def test_29_budget_never_goes_negative(tm):
    boxes = [_mb(id="primary", daily_cap=10)]
    assert tm._tm_mailbox_budgets(boxes, [_sent("primary")] * 99, "2026-09-17") == {"primary": 0}


def test_30_pick_takes_the_mailbox_with_the_most_headroom(tm):
    assert tm._tm_pick_mailbox({"a": 5, "b": 40, "c": 12}, ["a", "b", "c"]) == "b"


def test_31_ties_break_on_registry_order(tm):
    assert tm._tm_pick_mailbox({"a": 40, "b": 40}, ["b", "a"]) == "b"
    assert tm._tm_pick_mailbox({"a": 40, "b": 40}, ["a", "b"]) == "a"


def test_32_pick_returns_empty_when_everything_is_spent(tm):
    assert tm._tm_pick_mailbox({"a": 0, "b": 0}, ["a", "b"]) == ""
    assert tm._tm_pick_mailbox({}, []) == ""


# ─────────────────────────────────────────────────────────────────────────
# Group D — which config file a mailbox sends through
# ─────────────────────────────────────────────────────────────────────────

def test_33_primary_sends_through_the_users_own_config(tm, with_user):
    got = tm._tm_mailbox_config_path(with_user, tm._TM_PRIMARY_MAILBOX_ID)
    assert got == with_user / "dripdrop_config.json"


def test_34_extra_mailboxes_get_their_own_file(tm, with_user):
    got = tm._tm_mailbox_config_path(with_user, "second")
    assert got != with_user / "dripdrop_config.json"
    assert got.name.startswith("second")


def test_35_extra_mailbox_files_stay_inside_the_user_dir(tm, with_user):
    for raw in ("../../etc/passwd", "..\\..\\win.ini", "/abs", "second"):
        got = tm._tm_mailbox_config_path(with_user, raw)
        assert str(got.resolve()).startswith(str(with_user.resolve())), (raw, got)


def test_36_every_registry_row_routes_somewhere(tm, with_user):
    """Totality: a mailbox that resolves to no config can never send."""
    boxes = [_mb(id="primary"), _mb(id="second", email="b@x.com"),
             _mb(id="a-b_c", email="c@x.com")]
    for box in boxes:
        assert tm._tm_mailbox_config_path(with_user, box["id"]) is not None


# ─────────────────────────────────────────────────────────────────────────
# Group E — the "connect another mailbox" OAuth state marker
# ─────────────────────────────────────────────────────────────────────────

def test_37_state_round_trips_a_mailbox_id(tm):
    st = tm._tm_connect_state("second")
    assert tm._tm_state_mailbox_id(st) == "second"


def test_38_ordinary_connects_carry_no_marker(tm):
    for st in (None, "", "csrf-token-abcdef", "login", "tm_mbox"):
        assert tm._tm_state_mailbox_id(st) == ""


def test_39_a_marked_state_diverts_the_tokens(tm, with_user):
    got = tm._tm_connect_target_path(tm._tm_connect_state("second"))
    assert got is not None
    assert got != with_user / "dripdrop_config.json"


def test_40_arena_never_diverts_tokens(arena, with_user):
    """Even a hand-crafted marker is inert outside a ThriveModal workspace."""
    assert arena._tm_connect_target_path(arena._tm_connect_state("second")) is None


def test_41_an_unmarked_state_never_diverts_tokens(tm):
    for st in (None, "", "csrf-token"):
        assert tm._tm_connect_target_path(st) is None


def test_42_a_forged_state_cannot_escape_the_user_dir(tm):
    """`state` comes back from the browser, so it is attacker-controlled.

    The boundary it must not cross is the root the app already writes tokens
    into -- the one `_user_config_path()` is built from. Anchoring on that
    rather than on a fixture path is what makes this a test of the code."""
    root = tm._resolve_user_root()
    got = tm._tm_connect_target_path("tm_mbox:../../../../etc/passwd")
    if got is not None:
        assert str(got.resolve()).startswith(str(root.resolve()))
        assert ".." not in got.parts


def test_43_the_google_callback_consults_the_marker(tm):
    tree = _tree(tm)
    fn = _func(tree, "google_auth_callback")
    assert fn is not None
    assert "_tm_connect_target_path" in _names_in(fn)


def test_44_the_microsoft_callback_consults_the_marker(tm):
    fn = _func(_tree(tm), "ms_auth_callback")
    assert fn is not None
    assert "_tm_connect_target_path" in _names_in(fn)


def test_44b_the_microsoft_callback_accepts_state(tm):
    """Google's callback already took `state`; Microsoft's does not, so the
    splice has to widen the signature. NiceGUI maps query params by name, so
    an absent parameter means the marker is silently dropped."""
    fn = _func(_tree(tm), "ms_auth_callback")
    args = [a.arg for a in fn.args.args]
    assert "state" in args, "the microsoft callback cannot see the marker"
    assert len(fn.args.defaults) == len(args), "state must be optional"


# ─────────────────────────────────────────────────────────────────────────
# Group F — send-loop wiring and Arena isolation
# ─────────────────────────────────────────────────────────────────────────

def test_45_the_scheduler_tick_is_gated(tm):
    fn = _func(_tree(tm), "_server_scheduler_tick")
    assert fn is not None
    assert _GATE_NAMES & _names_in(fn), "the send loop reaches mailbox helpers ungated"


def test_46_the_scheduler_tick_reads_the_registry(tm):
    fn = _func(_tree(tm), "_server_scheduler_tick")
    assert "_tm_load_mailboxes" in _names_in(fn)


def test_47_the_send_call_no_longer_hardcodes_the_user_config(tm):
    """The per-item config path is what makes a second mailbox reachable."""
    fn = _func(_tree(tm), "_server_scheduler_tick")
    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "_server_send_one"]
    assert calls, "_server_send_one is no longer called from the tick"
    for call in calls:
        assert len(call.args) >= 2
        arg = call.args[1]
        assert isinstance(arg, ast.Name), ast.dump(arg)
        assert arg.id != "config_path", "still pinned to the single user config"


def test_48_every_gated_helper_user_also_references_the_gate(tm):
    """Phase 2/3/4 guard shape, extended to the Phase 5 helpers."""
    tree = _tree(tm)
    offenders = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in _MAILBOX_CHAIN_EXEMPT:
            continue
        names = _names_in(node)
        if names & _TM_MAILBOX_NAMES and not (names & _GATE_NAMES):
            offenders.append(node.name)
    assert offenders == [], f"ungated mailbox helper users: {offenders}"


def test_49_the_pure_helpers_build_no_ui(tm):
    tree = _tree(tm)
    pure = {"_tm_normalise_mailbox", "_tm_mailbox_id", "_tm_warmup_cap",
            "_tm_mailbox_budgets", "_tm_pick_mailbox", "_tm_mailbox_config_path",
            "_tm_state_mailbox_id", "_tm_load_mailboxes", "_tm_mailboxes_path"}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in pure:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    owner = sub.func.value
                    assert not (isinstance(owner, ast.Name) and owner.id == "ui"), \
                        f"{node.name} builds UI"
                    assert sub.func.attr != "notify", f"{node.name} notifies"


def test_50_an_arena_user_with_no_registry_is_unaffected(arena, with_user):
    """The registry is the switch: no file, no new behaviour."""
    assert arena._tm_load_mailboxes(with_user) == []
    assert arena._tm_mailbox_budgets([], [], "2026-09-17") == {}
    assert arena._tm_pick_mailbox({}, []) == ""


def test_51_registry_writes_are_confined_to_the_given_user_dir(tm, tmp_path, with_user):
    other = tmp_path / "someone_else"
    other.mkdir()
    tm._tm_write_mailboxes([_mb()], other)
    assert (other / "tm_mailboxes.json").exists()
    assert not (with_user / "tm_mailboxes.json").exists()


def test_52_helpers_never_raise_on_junk_registries(tm):
    """Nothing here runs on a page the user is looking at — it runs on the
    send loop, where an exception silently stops that user's mail."""
    for junk in (None, "", 17, [], [None], [{}], [{"email": None}], {"a": 1}):
        assert tm._tm_mailbox_budgets(junk, junk, "2026-09-17") is not None
        assert isinstance(tm._tm_pick_mailbox(junk, junk), str)
    for row in (None, "", 17, {}, {"email": None}, {"email": "  "}):
        try:
            tm._tm_normalise_mailbox(row)
        except ValueError:
            pass  # the one documented failure: a mailbox with no address
    for bad in (None, "", 17, {}, {"daily_cap": "x", "warmup_start": "nope"}):
        assert isinstance(tm._tm_warmup_cap(bad, "2026-09-17"), int)
        assert isinstance(tm._tm_warmup_cap(bad, junk), int)

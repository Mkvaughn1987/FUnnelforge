"""The generator stashes corner content keyed by (user, camp, step_idx).
Callers read-then-pop. Multi-user safe."""


def test_helper_pop_returns_and_deletes():
    import flowdrip_app as fa
    fa._last_generated_corner.clear()
    fa._last_generated_corner[("u@x.com", "Camp A", 0)] = {
        "mode": "note", "note": "hello"
    }
    got = fa._pop_last_generated_corner("u@x.com", "Camp A", 0)
    assert got == {"mode": "note", "note": "hello"}
    # Subsequent reads return None (popped).
    assert fa._pop_last_generated_corner("u@x.com", "Camp A", 0) is None


def test_helper_pop_missing_key_returns_none():
    import flowdrip_app as fa
    fa._last_generated_corner.clear()
    assert fa._pop_last_generated_corner("nobody", "nothing", 0) is None


def test_two_users_keys_are_isolated():
    import flowdrip_app as fa
    fa._last_generated_corner.clear()
    fa._last_generated_corner[("a@x.com", "Camp", 0)] = {"mode": "note", "note": "A"}
    fa._last_generated_corner[("b@x.com", "Camp", 0)] = {"mode": "note", "note": "B"}
    assert fa._pop_last_generated_corner("a@x.com", "Camp", 0) == {"mode": "note", "note": "A"}
    assert fa._pop_last_generated_corner("b@x.com", "Camp", 0) == {"mode": "note", "note": "B"}

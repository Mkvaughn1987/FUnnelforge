"""A stalled first-issue generation must not spin the banner forever, and the
newsletter AI client must carry a finite timeout."""
import inspect


def test_generator_client_has_timeout():
    import flowdrip_app as fa
    src = inspect.getsource(fa._generate_newsletter_content_for_step)
    assert "timeout=120" in src


def test_banner_gives_up_after_cutoff():
    import flowdrip_app as fa
    src = inspect.getsource(fa._render_nl_first_gen_status)
    assert "_NL_FIRST_GEN_GIVE_UP_S" in src
    assert "taking longer than usual" in src
    assert 0 < fa._NL_FIRST_GEN_GIVE_UP_S <= 300


def test_create_stamps_start_time():
    import flowdrip_app as fa
    src = inspect.getsource(fa)
    assert "s._nl_first_gen_started = time.time()" in src

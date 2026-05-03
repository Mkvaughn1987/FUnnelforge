"""Sanity: the generator's prompt must request personal_corner_note in
its JSON schema, otherwise Claude won't return it."""


def test_prompt_schema_includes_personal_corner_note():
    import flowdrip_app as fa
    import inspect
    src = inspect.getsource(fa._generate_newsletter_content_for_step)
    assert "personal_corner_note" in src
    assert "first-person sentences" in src

from revrecover.gateway.config import resolve_secret


def test_env_value_wins():
    value, generated = resolve_secret("MY_SECRET", env={"MY_SECRET": "s3cret-from-env"})
    assert value == "s3cret-from-env"
    assert generated is False


def test_missing_env_generates_a_strong_random_secret():
    value, generated = resolve_secret("MY_SECRET", env={})
    assert generated is True
    assert len(value) >= 32


def test_generated_secrets_are_unique_per_call():
    first, _ = resolve_secret("MY_SECRET", env={})
    second, _ = resolve_secret("MY_SECRET", env={})
    assert first != second


def test_blank_env_value_counts_as_missing():
    value, generated = resolve_secret("MY_SECRET", env={"MY_SECRET": ""})
    assert generated is True
    assert value

"""Smoke test — confirms the package is importable and the env is wired up."""


def test_engine_importable():
    import engine  # noqa: F401

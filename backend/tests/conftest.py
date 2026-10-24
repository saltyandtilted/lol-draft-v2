import pytest

from app import create_app


@pytest.fixture
def make_client(tmp_path):
    """Return a factory for test clients backed by a throwaway SQLite file."""

    def _make(**overrides):
        config = {"TESTING": True, "DATABASE_PATH": str(tmp_path / "test.db")}
        config.update(overrides)
        return create_app(config).test_client()

    return _make

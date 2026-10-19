import pytest
from runez.conftest import cli, ClickRunner, temp_folder  # noqa: F401, fixtures

from ripple_effect.cli import main

ClickRunner.default_main = main


@pytest.fixture(autouse=True)
def isolated_uv_override(monkeypatch):
    """Tests may run under a ripple-effect run themselves (via tox), which exports a `UV_OVERRIDE` that we'd otherwise append to"""
    monkeypatch.delenv("UV_OVERRIDE", raising=False)

from runez.conftest import cli, ClickRunner, temp_folder  # noqa: F401, fixtures

from ripple_effect import main

ClickRunner.default_main = main

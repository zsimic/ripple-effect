from pathlib import Path
from unittest.mock import patch

from runez.program import RunResult

from ripple_effect.model import VirtualEnv


def test_upstream_editable():
    upstream = Path("/src/upstream")
    venv = VirtualEnv(Path("/src/upstream/.tox/ripple-check/downstream"))

    def is_editable(freeze_output):
        with patch.object(VirtualEnv, "run_uv", return_value=RunResult(output=freeze_output, code=0)):
            return venv.is_upstream_editable(upstream)

    assert is_editable("-e file:///src/upstream\nfoo==1.0")
    assert not is_editable("upstream==1.0")

    # Downstream cloned under upstream folder: its own editable line starts with upstream's path, but that's not upstream
    assert not is_editable("-e file:///src/upstream/.tox/ripple-check/downstream\nupstream==1.0")

    with patch.object(VirtualEnv, "run_uv", return_value=RunResult(code=1)):
        assert not venv.is_upstream_editable(upstream)

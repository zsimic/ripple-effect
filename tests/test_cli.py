import io
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest
import runez

import ripple_effect.__main__
from ripple_effect.model import OutputRecorder, TeeStream, VirtualEnv


def extract_section(section: str, text: str) -> str | None:
    """Content of first output section '## <section>' or '### <section>' in 'text' (up to the next heading of same or higher level)"""
    heading = re.search(rf"^(#+) {re.escape(section)}\n", text, flags=re.MULTILINE)
    if heading:
        end = re.compile(rf"^#{{1,{len(heading.group(1))}}} ", flags=re.MULTILINE).search(text, heading.end())
        return text[heading.end() : end.start() if end else None].strip("\n")

    return None


@pytest.mark.parametrize("name", sorted(path.stem for path in (Path(__file__).parent / "samples").glob("*.yml")))
def test_samples(cli, name):
    # `show` output of each sample config, regenerate with tests/regenerate-expected.sh
    with runez.CurrentFolder(cli.project_folder):
        cli.run("-c", f"tests/samples/{name}.yml", "show")
        expected = Path(f"tests/samples/{name}.txt").read_text()

    errors = extract_section("Errors", expected)
    assert cli.succeeded == (errors is None)
    output = cli.logged.contents()  # Both streams: errors are on stderr
    assert extract_section("Config", output) == extract_section("Config", expected)
    assert extract_section("Errors", output) == errors


def test_trivial(cli):
    cli.run("--help")
    assert cli.succeeded
    assert "Usage:" in cli.logged.stdout

    # For test coverage: exercise invoking ad-hoc `__main__.py`
    cli.run("--help", main=ripple_effect.__main__.__file__)
    assert cli.succeeded
    assert "Usage:" in cli.logged.stdout

    # Missing config file
    cli.run("--config", "no-such.yml", "show")
    assert cli.failed

    # Empty config → fails (nothing to test without upstream and downstream-projects)
    runez.write("sample.yml", "# placeholder\n", logger=None)
    cli.run("--config", "sample.yml", "show")
    assert cli.failed
    assert "upstream: -missing-" in cli.logged.stdout
    assert "Invalid config sample.yml:\n- top level: missing 'upstream', 'downstream-projects'" in cli.logged


def test_default_config(cli):
    cfg = runez.to_path(cli.project_folder) / "ripple-effect.yml"
    runez.copy(cfg, "ripple-effect.yml", logger=None)
    cli.run("--dryrun", "prepare")
    assert cli.succeeded
    assert "git clone https://github.com/codrsquad/runez.git --branch main build/verify-runez/runez\n" in cli.logged
    assert "git clone https://github.com/codrsquad/portable-python.git build/verify-runez/portable-python\n" in cli.logged
    assert "uv pip install -e build/verify-runez/runez" in cli.logged

    cli.run("--dryrun", "run")
    assert cli.succeeded
    assert "Would run: build/verify-runez/ripple-effect/.venv/bin/pytest\n" in cli.logged
    assert not os.path.exists("build/verify-runez/last-run.log")  # Output is not recorded in dryrun mode

    runez.touch("build/verify-runez/leftover/foo", logger=None)
    cli.run("--dryrun", "run", "--clean")
    assert cli.succeeded
    prep = extract_section("Preparation", cli.logged.stdout.contents())
    assert prep
    assert prep.startswith("Would clean 1 file from build/verify-runez\n")


def test_groups(cli):
    runez.write(
        "sample.yml",
        """
upstream: ./upstream
test: tox -r -e py
downstream-projects:
  - ./foo
  - description: Repos with a typecheck target
    test: tox -r -e py,typecheck
    sources:
      - ./bar
      - source-ref: ./baz
        prepare: uv sync --all-groups
  - sources: [./qux]
""",
        logger=None,
    )
    # Summary report nests grouped projects under their description
    for name in ("upstream", "foo", "bar", "baz", "qux"):
        runez.ensure_folder(name, logger=None)

    with patch("uv_metadata.get_metadata_from_pip_spec", side_effect=lambda pip_spec: {"name": Path(pip_spec).name}):
        cli.run("--dryrun", "-c", "sample.yml", "run")

    assert cli.succeeded
    testing = extract_section("Testing", cli.logged.stdout.contents())
    assert testing is not None
    for name in ("bar", "baz"):
        tested = extract_section(name, testing)
        assert tested
        assert re.fullmatch(r"UV_OVERRIDE=\S+\nWould run: tox -r -e py,typecheck", tested)
    outcome = extract_section("Outcome", cli.logged.stdout.contents())
    assert outcome is not None
    lines = [line.partition(": ")[0] for line in outcome.splitlines()]
    assert lines == ["foo", "Repos with a typecheck target:", "  bar", "  baz", "qux"]

    # --clean refuses to wipe a proving-grounds holding anything that isn't ripple-effect's own
    runez.write("sample.yml", "upstream: ./upstream\nproving-grounds: .\ndownstream-projects: [./foo]", logger=None)
    cli.run("--dryrun", "-c", "sample.yml", "run", "--clean")
    assert cli.failed
    errors = extract_section("Errors", cli.logged.contents())
    assert errors
    assert re.fullmatch(r"Not cleaning proving-grounds \S+: it holds sample.yml", errors)


def fake_program(path, script="exit 0"):
    """Executable shell script at 'path', standing in for a real program"""
    runez.write(path, f"#!/bin/sh\n{script}\n", logger=None)
    runez.make_executable(path, logger=None)


def test_run_outcomes(cli):
    # Fake prepare: "installs" in .venv/ the fake pytest found in the project's 'pytest-script' (if any)
    fake_program("fake-prepare", "[ ! -f pytest-script ] || (mkdir -p .venv/bin && cp pytest-script .venv/bin/pytest)")
    fake_program("ok/pytest-script", "echo ok-out; echo ok-err >&2")
    for name in ("not-injected", "redirected"):
        fake_program(f"{name}/pytest-script")

    fake_program("failing/pytest-script", "exit 3")
    fake_program("both/pytest-script", '[ "$1" != "--fail" ] || exit 4')
    runez.ensure_folder("no-pytest", logger=None)
    runez.write("redirected/.venv", ".tox/py\n", logger=None)  # A file (PEP 832 redirect, as written by tox): gets replaced
    runez.ensure_folder("upstream", logger=None)
    runez.write(
        "sample.yml",
        f"""
upstream: ./upstream
prepare: {os.getcwd()}/fake-prepare
downstream-projects:
  - ./ok
  - ./failing
  - ./no-pytest
  - ./not-injected
  - ./redirected
  - source-ref: ./both
    test: [pytest -x, pytest --fail]
""",
        logger=None,
    )
    with (
        patch("uv_metadata.get_metadata_from_pip_spec", side_effect=lambda pip_spec: {"name": Path(pip_spec).name}),
        patch.object(VirtualEnv, "inject_upstream"),
        patch.object(VirtualEnv, "is_upstream_editable", autospec=True, side_effect=lambda venv, _: venv.folder.name != "not-injected"),
    ):
        cli.run("-c", "sample.yml", "run")

    assert cli.failed
    assert "4 tests failed" in cli.logged.stdout
    assert os.path.isdir("redirected/.venv")
    testing = extract_section("Testing", cli.logged.stdout.contents())
    assert testing is not None
    ok_lines = (extract_section("ok", testing) or "").splitlines()
    assert ok_lines[0] == "Running: ok/.venv/bin/pytest"
    assert "ok-out" in ok_lines  # Passed-through output
    assert extract_section("both", testing) == "Running: both/.venv/bin/pytest -x\nRunning: both/.venv/bin/pytest --fail"
    outcome = extract_section("Outcome", cli.logged.stdout.contents())
    assert outcome is not None
    expected = """\
ok: PASSED
failing: FAILED: exit code 3
no-pytest: FAILED: pytest is not installed in .venv/
not-injected: FAILED: upstream is not installed editable in .venv/
redirected: PASSED
both: FAILED
  pytest -x: PASSED
  pytest --fail: FAILED: exit code 4
4 tests failed"""
    assert re.sub(r" \(\d+\.\ds\)", "", outcome) == expected

    # Full output is recorded in proving-grounds: both streams (including the commands' passed-through output), and log chatter
    run_log = Path("build/ripple-check/last-run.log")
    recorded = run_log.read_text()
    assert "full output recorded in: build/ripple-check/last-run.log\n" in recorded
    recorded_ok = extract_section("ok", extract_section("Testing", recorded) or "") or ""
    assert sorted(recorded_ok.splitlines()) == ["Running: ok/.venv/bin/pytest", "ok-err", "ok-out"]  # stdout/stderr order may vary
    assert extract_section("Outcome", recorded) == outcome
    assert "DEBUG Cleaned 1 file from ok/.venv\n" not in recorded  # Not shown without --verbose

    # Recorded again by the next run, `--clean` doesn't wipe it out (log file gets opened after cleaning)
    with (
        patch("uv_metadata.get_metadata_from_pip_spec", side_effect=lambda pip_spec: {"name": Path(pip_spec).name}),
        patch.object(VirtualEnv, "inject_upstream"),
        patch.object(VirtualEnv, "is_upstream_editable", return_value=True),
    ):
        cli.run("--verbose", "-c", "sample.yml", "run", "--clean")

    assert cli.failed
    recorded = run_log.read_text()
    prepared = extract_section("Preparation", recorded)
    assert prepared
    assert prepared.startswith("Cleaned 1 file from build/ripple-check\nfull output recorded in: ")
    assert "DEBUG Cleaned 1 file from ok/.venv\n" in recorded
    assert "\x1b[" not in recorded


def test_tee_stream():
    recorder = OutputRecorder()
    tee = TeeStream(io.StringIO(), recorder)
    assert tee.write("\x1b[31mhello\x1b[0m\n") == 15
    tee.flush()
    assert tee.getvalue() == "\x1b[31mhello\x1b[0m\n"  # Wrapped stream (and its attributes) gets it as-is
    assert recorder.pending == ["hello\n"]  # Recorded uncolored, held until the log file is opened

    # Progress bars: only what was drawn last on a line is recorded, line endings normalized
    tee.write("[  ]\r[= ]\r[==] done\r\n[  ]\x1b[2K[==]\x1b[2Kok\r\r\n")
    assert recorder.pending[-1] == "[==] done\nok\n"

    # Line is recorded once complete: redraws can come in separate writes
    for text in ("[  ] \r", "\x1b[2K[= ] \r", "\x1b[2K", "done\r\r\n"):
        tee.write(text)

    assert recorder.pending[-1] == "done\n"


def tiny_project(folder):
    """A real (tiny) python project, named after 'folder': builds offline in ~20ms"""
    name = Path(folder).name
    pyproject = f'[build-system]\nrequires = ["uv_build"]\nbuild-backend = "uv_build"\n\n[project]\nname = "{name}"\nversion = "1.0"\n'
    runez.write(f"{folder}/pyproject.toml", pyproject, logger=None)
    runez.touch(f"{folder}/src/{name}/__init__.py", logger=None)


def editable_venv(folder, *editables):
    """A real .venv/ in 'folder', with 'editables' installed in editable mode (offline, ~70ms)"""
    runez.run("uv", "venv", "-q", "--offline", f"{folder}/.venv", logger=None)
    for editable in editables:
        runez.run("uv", "pip", "install", "-q", "--offline", "-p", f"{folder}/.venv", "-e", editable, logger=None)


def test_dryrun_existing_setups(cli):
    # What's already in place is checked for real (even with --dryrun): healthy venvs are reused, upstream injected only if needed
    tiny_project("tinyup")
    editable_venv("ready", "tinyup")
    tiny_project("tinyup/nested")  # Downstream under the upstream folder: its own editable path starts with upstream's
    editable_venv("tinyup/nested", "tinyup/nested")
    runez.write("old-school/requirements.txt", "foo\n", logger=None)
    runez.ensure_folder("build/ripple-check/cloned", logger=None)  # Cloned by a previous run
    runez.write(
        "sample.yml",
        "upstream: ./tinyup\ndownstream-projects: [./ready, ./tinyup/nested, ./old-school, https://github.com/example/cloned.git]",
        logger=None,
    )
    with patch("uv_metadata.get_metadata_from_pip_spec", side_effect=lambda pip_spec: {"name": Path(pip_spec).stem}):
        cli.run("--dryrun", "-c", "sample.yml", "run")

    assert cli.succeeded
    prepared = extract_section("Preparation", cli.logged.stdout.contents())
    assert prepared is not None
    expected = """\
upstream: tinyup @ tinyup

### ready
folder: ready
tinyup already installed editable

### nested
folder: tinyup/nested
injecting tinyup (editable)
Would run: uv pip install -e tinyup

### old-school
folder: old-school
Would create old-school/.venv
Would run: uv venv --clear
Would run: uv pip install -r old-school/requirements.txt
Would run: uv pip install -e .
injecting tinyup (editable)
Would run: uv pip install -e tinyup

### cloned
folder: build/ripple-check/cloned
Would run: git fetch
Would run: git reset --hard FETCH_HEAD
Would create build/ripple-check/cloned/.venv
Would run: uv sync
injecting tinyup (editable)
Would run: uv pip install -e tinyup"""
    assert prepared == expected


def test_tox_runs(cli, monkeypatch):
    tiny_project("tinyup")  # Real upstream, ripple-effect builds its wheel

    # Fake tox runs, creating a .tox/py env with the upstream installed: from the wheel stated in UV_OVERRIDE (like tox-uv does),
    # or from an index (ignoring UV_OVERRIDE). A .tox/style env without upstream, and tox's internal .tox/.pkg are ignored
    make_envs = r"""
d=.tox/py/lib/python3.13/site-packages/tinyup-1.0.dist-info
mkdir -p $d .tox/style .tox/.pkg
touch .tox/py/pyvenv.cfg .tox/style/pyvenv.cfg .tox/.pkg/pyvenv.cfg
"""
    from_overrides = r"""echo "{\"url\": \"$(sed 's/.* @ //' ${UV_OVERRIDE%% *})\"}" > $d/direct_url.json"""
    fake_program("fake/uv-tox/tox", make_envs + from_overrides)
    fake_program("fake/pip-tox/tox", make_envs)
    fake_program("fake/failing/tox", make_envs + "exit 2")
    fake_program("fake/no-env/tox")
    cwd = os.getcwd()
    names = ("uv-tox", "pip-tox", "no-env", "failing")
    entries = "".join(f"  - source-ref: ./{name}\n    test: {cwd}/fake/{name}/tox -re py\n" for name in names)
    for name in names:
        runez.ensure_folder(name, logger=None)

    runez.write("sample.yml", f"upstream: ./tinyup\ndownstream-projects:\n{entries}", logger=None)
    monkeypatch.setenv("UV_OVERRIDE", f"{cwd}/user-overrides.txt")  # Kept, ripple-effect's overrides get added to it
    with patch("uv_metadata.get_metadata_from_pip_spec", side_effect=lambda pip_spec: {"name": Path(pip_spec).name}):
        cli.run("-c", "sample.yml", "run")

    assert cli.failed
    assert "3 tests failed" in cli.logged.stdout
    assert "uv sync" not in cli.logged  # No .venv needed for tox-only projects
    wheel = Path("build/ripple-check/.ripple/upstream/tinyup-1.0-py3-none-any.whl").absolute()
    assert wheel.exists()
    assert list(runez.readlines("build/ripple-check/.ripple/overrides.txt")) == [f"tinyup @ file://{wheel}"]
    overrides = "'build/ripple-check/.ripple/overrides.txt user-overrides.txt'"  # Ours first, existing ones kept (paths shortened)
    assert f"UV_OVERRIDE={overrides}\nRunning: fake/uv-tox/tox -re py\n" in cli.logged.stdout
    outcome = extract_section("Outcome", cli.logged.stdout.contents())
    assert outcome is not None
    expected = """\
uv-tox: PASSED
pip-tox: FAILED: tox env 'py' has tinyup 1.0 instead of the upstream wheel
no-env: FAILED: couldn't verify that tox used the upstream checkout: no recreated env found in .tox/
failing: FAILED: exit code 2, tox env 'py' has tinyup 1.0 instead of the upstream wheel
3 tests failed"""
    assert re.sub(r" \(\d+\.\ds\)", "", outcome) == expected


def test_run_invalid_config(cli):
    # Commands other than `show` abort with all problems (same as shown by `show`), before doing anything
    with runez.CurrentFolder(cli.project_folder):
        cli.run("--dryrun", "-c", "tests/samples/bad-config.yml", "run")
        expected = Path("tests/samples/bad-config.txt").read_text()

    assert cli.failed
    # FUTURE-FIX: assert not cli.logged.stdout.contents() when runez 5.11+ is released
    assert cli.logged.contents().startswith("## Errors\n")
    assert extract_section("Errors", cli.logged.contents()) == extract_section("Errors", expected)

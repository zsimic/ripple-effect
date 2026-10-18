import os
import re
from pathlib import Path
from unittest.mock import patch

import runez

import ripple_effect.__main__
from ripple_effect.model import VirtualEnv


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
    assert "Invalid config sample.yml:\n - top level: missing 'upstream', 'downstream-projects'" in cli.logged


def test_show(cli):
    sample = runez.to_path(cli.tests_folder) / "samples/minimal.yml"
    cli.run("--config", sample, "show")
    assert cli.succeeded
    assert "upstream: ~/github/runez" in cli.logged.stdout
    assert "proving-grounds: build/ripple-check" in cli.logged.stdout
    assert "2 downstream projects:" in cli.logged.stdout
    assert "source-ref: ." in cli.logged.stdout
    assert "source-ref: https://github.com/foo/bar.git@main" in cli.logged.stdout


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
    assert "Testing ripple-effect...\nWould run: build/verify-runez/ripple-effect/.venv/bin/pytest\n" in cli.logged


def test_top_level_settings(cli):
    runez.write(
        "sample.yml",
        """
upstream: ~/github/runez
test: tox -re py
downstream-projects:
  - ./foo
  - source-ref: ./bar
    prepare: uv sync
    test: pytest tests/ -x
""",
        logger=None,
    )
    cli.run("-c", "sample.yml", "show")
    assert cli.succeeded
    assert " - source-ref: ./foo\n   prepare: auto\n   test: tox -re py\n" in cli.logged.stdout
    assert " - source-ref: ./bar\n   prepare: uv sync\n   test: pytest tests/ -x" in cli.logged.stdout


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
    cli.run("-c", "sample.yml", "show")
    assert cli.succeeded
    expected = """
4 downstream projects:
 - source-ref: ./foo
   prepare: auto
   test: tox -r -e py
 - Repos with a typecheck target:
   - source-ref: ./bar
     prepare: auto
     test: tox -r -e py,typecheck
   - source-ref: ./baz
     prepare: uv sync --all-groups
     test: tox -r -e py,typecheck
 - source-ref: ./qux
   prepare: auto
   test: tox -r -e py
"""
    assert expected in cli.logged.stdout

    # Summary report nests grouped projects under their description
    for name in ("upstream", "foo", "bar", "baz", "qux"):
        runez.ensure_folder(name, logger=None)

    with patch("uv_metadata.get_metadata_from_pip_spec", side_effect=lambda pip_spec: {"name": Path(pip_spec).name}):
        cli.run("--dryrun", "-c", "sample.yml", "run")

    assert cli.succeeded
    for name in ("bar", "baz"):
        assert re.search(rf"Testing {name}...\nUV_OVERRIDE=\S+\nWould run: \S*tox -r -e py,typecheck\n", cli.logged.stdout.contents())
    summary = cli.logged.stdout.contents().partition("─" * 50)[2]
    lines = [line[2:].partition(": ")[0] for line in summary.strip("\n").splitlines()]
    assert lines == ["foo", "Repos with a typecheck target:", "  bar", "  baz", "qux"]


def test_invalid_config(cli):
    def check(config: str, expected: str, upstream="upstream: .\n"):
        runez.write("bad.yml", upstream + config, logger=None)
        cli.run("-c", "bad.yml", "show")
        assert cli.failed
        assert "Invalid config bad.yml:" in cli.logged
        assert f"\n - {expected}" in cli.logged

    check("- ./foo", "top level: expected a mapping", upstream="")
    check("downstream-projects: [./foo]", "top level: missing 'upstream'", upstream="")
    check("test: a", "top level: missing 'downstream-projects'")
    check("test: a\ntest: b", "invalid YAML: found duplicate key 'test'\n  in \"bad.yml\", line 3")
    check("test: [a", "invalid YAML")
    check("defaults:\n  test: a", "top level: unknown key 'defaults', expected one of: upstream, proving-grounds,")
    check("test:", "top level: 'test' must be a non-empty string")
    check("upstream: [a]", "top level: 'upstream' must be a non-empty string", upstream="")
    check("downstream-projects: ./foo", "top level: 'downstream-projects' must be a non-empty list")
    check("downstream-projects: []", "top level: 'downstream-projects' must be a non-empty list")
    check("downstream-projects:\n  -", "downstream-projects[0]: expected a string or a mapping")
    check("downstream-projects:\n  - test: a", "downstream-projects[0]: needs either 'source-ref' (a project) or 'sources' (a group)")
    check(
        "downstream-projects:\n  - description: a\n    repos: [./foo]",
        "downstream-projects[0]: unknown key 'repos', expected one of: description, source-prefix, prepare, test, sources",
    )
    check("downstream-projects:\n  - source-ref: ./foo\n    sources: [./bar]", "downstream-projects[0]: unknown key 'sources'")
    check("downstream-projects:\n  - source-ref: ./foo\n    description: a", "downstream-projects[0]: unknown key 'description'")
    check("downstream-projects:\n  - sources: [{sources: [./foo]}]", "downstream-projects[0].sources[0]: unknown key 'sources'")
    check("downstream-projects:\n  - sources: [{test: a}]", "downstream-projects[0].sources[0]: missing 'source-ref'")
    check("downstream-projects:\n  - ./foo\n  - sources: [./bar, ./foo]", "'./foo' is listed more than once in downstream-projects")

    # source-prefix
    check(
        "downstream-projects: [./foo, lib-a]",
        "downstream-projects[1]: 'lib-a' is neither a URL nor a local path, and no 'source-prefix' is in effect",
    )
    check("source-prefix: corp/\ndownstream-projects: [./foo]", "top level: 'source-prefix' must be a URL or a local path, got 'corp/'")
    check(
        "downstream-projects:\n  - source-prefix: corp/\n    sources: [lib-a]",
        "downstream-projects[0]: 'source-prefix' must be a URL or a local path, got 'corp/'",
    )
    check(
        "downstream-projects:\n  - source-ref: lib-a\n    source-prefix: ~/dev/",
        "downstream-projects[0]: unknown key 'source-prefix', expected one of: source-ref, prepare, test",
    )
    check("source-prefix: ~/dev/\ndownstream-projects: [foo, ~/dev/foo]", "'~/dev/foo' is listed more than once in downstream-projects")

    # Test commands
    check("test: []\ndownstream-projects: [./foo]", "top level: 'test' must be a non-empty string, or a non-empty list of them")
    check("test: [pytest, 1]\ndownstream-projects: [./foo]", "top level: 'test' must be a non-empty string, or a non-empty list of them")
    check("test: pytest 'a\ndownstream-projects: [./foo]", "top level: test command 'pytest 'a': No closing quotation")
    unsupported = "not supported yet, ripple-effect can't verify that it runs against the upstream checkout"
    check("test: hatch run test\ndownstream-projects: [./foo]", f"top level: test command 'hatch run test': {unsupported}")
    restated = "state it as 'pytest ...', ripple-effect runs pytest from the project's .venv/"
    check("test: .venv/bin/pytest\ndownstream-projects: [./foo]", f"top level: test command '.venv/bin/pytest': {restated}\n")
    check("test: python -mpytest\ndownstream-projects: [./foo]", f"top level: test command 'python -mpytest': {restated}\n")
    check(
        "test: uv run pytest\ndownstream-projects: [./foo]",
        f"top level: test command 'uv run pytest': {restated} (`uv run` would sync .venv/, replacing the injected upstream)",
    )
    no_recreate = "tox's first option must be -r (or --recreate, e.g. 'tox -re py'), tox otherwise reuses existing envs"
    for command in ("tox", "tox -e py", "tox -er py", "tox -vre py", "tox -v -r -e py", "uvx tox -e py", "tox -e py -- -r"):
        check(f"test: {command}\ndownstream-projects: [./foo]", f"top level: test command '{command}': {no_recreate}")

    # All problems in a list of test commands are reported
    config = "downstream-projects:\n  - source-ref: ./foo\n    test: [hatch test, tox -e py]"
    check(config, "downstream-projects[0]: test command 'hatch test'")
    check(config, "downstream-projects[0]: test command 'tox -e py'")


def test_test_commands(cli):
    runez.write(
        "sample.yml",
        """
upstream: ./upstream
test: [pytest -x, tox -re py, tox -rve py, tox --recreate, newt tox -r -e py, uvx --with tox-uv tox -re py]
downstream-projects: [./foo]
""",
        logger=None,
    )
    cli.run("-c", "sample.yml", "show")
    assert cli.succeeded
    expected = """
   test:
     - pytest -x
     - tox -re py
     - tox -rve py
     - tox --recreate
     - newt tox -r -e py
     - uvx --with tox-uv tox -re py
"""
    assert expected in cli.logged.stdout


def fake_program(path, script="exit 0"):
    """Executable shell script at 'path', standing in for a real program"""
    runez.write(path, f"#!/bin/sh\n{script}\n", logger=None)
    runez.make_executable(path, logger=None)


def test_run_outcomes(cli):
    for name in ("ok", "not-injected"):
        fake_program(f"{name}/.venv/bin/pytest")

    fake_program("failing/.venv/bin/pytest", "exit 3")
    fake_program("both/.venv/bin/pytest", '[ "$1" != "--fail" ] || exit 4')
    runez.ensure_folder("no-pytest/.venv/bin", logger=None)
    runez.ensure_folder("upstream", logger=None)
    runez.write(
        "sample.yml",
        """
upstream: ./upstream
prepare: "true"
downstream-projects:
  - ./ok
  - ./failing
  - ./no-pytest
  - ./not-injected
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
    assert "Testing ok...\nRunning: ok/.venv/bin/pytest\n" in cli.logged.stdout
    assert "Testing both...\nRunning: both/.venv/bin/pytest -x\n" in cli.logged.stdout
    summary = cli.logged.stdout.contents().partition("─" * 50)[2]
    expected = """
  ok: PASSED
  failing: FAILED: exit code 3
  no-pytest: FAILED: pytest is not installed in .venv/
  not-injected: FAILED: upstream is not installed editable in .venv/
  both: FAILED
    pytest -x: PASSED
    pytest --fail: FAILED: exit code 4
"""
    assert re.sub(r" \(\d+\.\ds\)", "", summary).startswith(expected)


def test_tox_runs(cli, monkeypatch):
    # A real (tiny) upstream, ripple-effect builds its wheel
    pyproject = '[build-system]\nrequires = ["uv_build"]\nbuild-backend = "uv_build"\n\n[project]\nname = "tinyup"\nversion = "1.0"\n'
    runez.write("tinyup/pyproject.toml", pyproject, logger=None)
    runez.touch("tinyup/src/tinyup/__init__.py", logger=None)

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
    overrides = rf"'\S+/\.ripple/overrides\.txt {re.escape(cwd)}/user-overrides.txt'"  # Ours first, existing ones kept
    assert re.search(rf"Testing uv-tox...\nUV_OVERRIDE={overrides}\nRunning: fake/uv-tox/tox -re py\n", cli.logged.stdout.contents())
    summary = cli.logged.stdout.contents().partition("─" * 50)[2]
    expected = """
  uv-tox: PASSED
  pip-tox: FAILED: tox env 'py' has tinyup 1.0 instead of the upstream wheel
  no-env: FAILED: couldn't verify that tox used the upstream checkout: no recreated env found in .tox/
  failing: FAILED: exit code 2, tox env 'py' has tinyup 1.0 instead of the upstream wheel
"""
    assert re.sub(r" \(\d+\.\ds\)", "", summary).startswith(expected)


def test_problems_reported_together(cli):
    runez.write(
        "bad.yml",
        """
proving-grounds: ./build
downstream-projects:
  - ./foo
  - lib-a
  - source-ref: ./bar
    tset: tox -r -e py
  - test: tox -r -e py
""",
        logger=None,
    )
    expected = """Invalid config bad.yml:
 - top level: missing 'upstream'
 - downstream-projects[1]: 'lib-a' is neither a URL nor a local path, and no 'source-prefix' is in effect
 - downstream-projects[2]: unknown key 'tset', expected one of: source-ref, prepare, test
 - downstream-projects[3]: needs either 'source-ref' (a project) or 'sources' (a group)
"""

    # `show` displays the config (missing values in red), then all problems found
    cli.run("-c", "bad.yml", "show")
    assert cli.failed
    assert "upstream: -missing-\nproving-grounds: ./build\n3 downstream projects:\n - source-ref: ./foo\n" in cli.logged.stdout
    assert " - source-ref: lib-a\n" in cli.logged.stdout
    assert expected in cli.logged

    # Other commands abort with the same problems, before doing anything
    cli.run("--dryrun", "-c", "bad.yml", "run")
    assert cli.failed
    assert "source-ref:" not in cli.logged
    assert "Would run" not in cli.logged
    assert expected in cli.logged


def test_source_prefix(cli):
    runez.write(
        "sample.yml",
        """
upstream: ~/github/runez
source-prefix: https://git.example.com/corp/
downstream-projects:
  - lib-a
  - lib-b@main
  - git@github.com:foo/bar.git
  - https://github.com/foo/baz.git
  - ./local
  - source-ref: lib-c
    test: tox -r -e py
  - description: Local checkouts
    source-prefix: ~/dev/
    sources: [tool-a, {source-ref: tool-b}, /opt/tool-c]
""",
        logger=None,
    )
    cli.run("-c", "sample.yml", "show")
    assert cli.succeeded
    refs = [line.strip() for line in cli.logged.stdout.contents().splitlines() if "source-ref:" in line]
    assert refs == [
        "- source-ref: https://git.example.com/corp/lib-a",
        "- source-ref: https://git.example.com/corp/lib-b@main",
        "- source-ref: git@github.com:foo/bar.git",
        "- source-ref: https://github.com/foo/baz.git",
        "- source-ref: ./local",
        "- source-ref: https://git.example.com/corp/lib-c",
        "- source-ref: ~/dev/tool-a",
        "- source-ref: ~/dev/tool-b",
        "- source-ref: /opt/tool-c",
    ]

"""Model for ripple-effect: spec, project refs, virtual envs."""

from __future__ import annotations

import json
import logging
import os
import shlex
import sys
import time
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, TextIO, TYPE_CHECKING

import runez
import yaml
from runez.pyenv import PypiStd

if TYPE_CHECKING:
    from collections.abc import Callable

# Valid config keys, per level (see "Config reference" in README.rst)
TOP_LEVEL_KEYS = ("upstream", "proving-grounds", "source-prefix", "prepare", "test", "downstream-projects")
GROUP_KEYS = ("description", "source-prefix", "prepare", "test", "sources")
PROJECT_KEYS = ("source-ref", "prepare", "test")
LIST_KEYS = ("downstream-projects", "sources")  # Keys with a list value, 'test' is a string or a list, others are strings
DEFAULT_PROVING_GROUNDS = "build/ripple-check"  # Relative to the config file's folder, 'build/' is typically git-ignored
RUN_LOG = "last-run.log"  # Full output of last `run`, in proving-grounds


class UniqueKeyLoader(yaml.SafeLoader):
    """yaml.SafeLoader that rejects duplicate keys, instead of silently keeping the last one."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(None, None, f"found duplicate key '{key}'", key_node.start_mark)

            seen.add(key)

        return super().construct_mapping(node, deep=deep)


def represented(key: str, value, indent="") -> str:
    """Colored representation of a key/value pair."""
    value = runez.green(runez.short(value)) if value else runez.red("-missing-")
    return f"{indent}{key}: {value}"


def outcome_line(label: str, failure: str | None, elapsed: float) -> str:
    """Line of the run summary: PASSED if 'failure' is None (FAILED otherwise, stating 'failure' if not empty)."""
    status = runez.green("PASSED") if failure is None else runez.red("FAILED")
    return f"{label}: {status} ({elapsed:.1f}s){f': {failure}' if failure else ''}"


def installed_from(venv: Path, name: str) -> str | None:
    """Where package 'name' was installed from in 'venv': its URL, its version if from an index, None if not installed."""
    wanted = PypiStd.std_package_name(name)
    for dist_info in venv.glob("lib/python*/site-packages/*.dist-info"):
        dist_name, _, version = dist_info.name.removesuffix(".dist-info").partition("-")
        if PypiStd.std_package_name(dist_name) == wanted:
            direct_url = dist_info / "direct_url.json"  # Present for direct URL installs only (PEP 610)
            if direct_url.exists():
                return urllib.parse.unquote(json.loads(direct_url.read_text())["url"])

            return version

    return None


def is_local_path(source_ref: str) -> bool:
    """True if 'source_ref' is a local path."""
    return source_ref.startswith((".", "~", "/"))


def is_bare_name(source_ref: str) -> bool:
    """True if 'source_ref' is neither a local path nor a URL, a 'source-prefix' completes it then."""
    return not is_local_path(source_ref) and not source_ref.startswith("git@") and "://" not in source_ref


def quiet_run(program, *args, **kwargs):
    """runez.run() for housekeeping and probes, shown with --verbose only. Programs stated by name are shown as such ('uv')."""
    short_exe = program if isinstance(program, str) and os.path.basename(program) == program else None
    return runez.run(program, *args, short_exe=short_exe, **kwargs)


def logged_run(program, *args, **kwargs):
    """quiet_run() for commands ran on the user's behalf: shown as they run."""
    return quiet_run(program, *args, logger=print, **kwargs)


def split_git_ref(source_ref: str) -> tuple[str, str | None]:
    """Split 'https://github.com/foo/bar.git@main' into ('url', 'main'), None ref if no @ given."""
    if not source_ref.startswith("git@"):
        url, sep, ref = source_ref.rpartition("@")
        if sep:
            return url, ref

    return source_ref, None


class OutputRecorder:
    """Records output of `run` (stdout, stderr, passed-through output of commands, logs) uncolored, see docs/pipeline.md#output."""

    def __init__(self) -> None:
        self.enabled = False
        self.pending: list[str] = []  # Output recorded before the log file gets opened by start()
        self.fh: TextIO | None = None
        self.tees: dict[str, TeeStream] = {}  # Replacing sys.stdout and sys.stderr, while enabled
        self.log_handler = logging.StreamHandler(self)  # runez's console handler holds on to its own stream, record logs separately

    def write(self, text: str):
        """Record complete lines 'text'. Progress bars redraw their line after a '\r' or an 'erase line' code: keep what was drawn last."""
        text = runez.uncolored(text.replace("\x1b[2K", "\r"))  # Passed-through output has '\r\n' (or even '\r\r\n') line ends
        text = "\n".join(line.rstrip("\r").rpartition("\r")[2] for line in text.split("\n"))
        if self.fh is None:
            self.pending.append(text)

        else:
            self.fh.write(text)

    def flush(self):
        if self.fh is not None:
            self.fh.flush()

    def enable(self):
        """Start recording sys.stdout, sys.stderr and logs, held in 'pending' until start()."""
        self.enabled = True
        self.tees = {name: TeeStream(getattr(sys, name), self) for name in ("stdout", "stderr")}
        for name, tee in self.tees.items():
            setattr(sys, name, tee)  # Like runez.CaptureOutput: a TeeStream is not a TextIO

        console = runez.log.console_handler
        if console:  # Record logs as they're shown on console
            self.log_handler.setFormatter(console.formatter)
            self.log_handler.setLevel(console.level)
            logging.root.addHandler(self.log_handler)

    def start(self, path: Path):
        """Start writing to 'path' what's recorded, if enabled (not in dryrun mode). Opened late: `--clean` would delete it."""
        if self.enabled and not runez.DRYRUN:
            print(f"full output recorded in: {runez.short(path)}")
            runez.ensure_folder(path.parent, logger=None)
            self.fh = path.open("w")
            self.fh.writelines(self.pending)
            self.pending = []

    def stop(self):
        """Stop recording, close log file."""
        for name, tee in self.tees.items():
            setattr(sys, name, tee.stream)
            self.write(tee.partial)  # Last line, in case it wasn't complete

        self.tees = {}
        logging.root.removeHandler(self.log_handler)
        if self.fh is not None:
            self.fh.close()
            self.fh = None

        self.enabled = False
        self.pending = []


class TeeStream:
    """Stream writing to 'stream', and to 'recorder' (line by line: a progress bar redraws its line, possibly across writes)."""

    def __init__(self, stream: TextIO, recorder: OutputRecorder):
        self.stream = stream
        self.recorder = recorder
        self.partial = ""  # Current line, recorded once complete

    def __getattr__(self, name: str):
        return getattr(self.stream, name)  # isatty(), encoding etc. are those of the wrapped stream

    def write(self, text: str) -> int:
        complete, newline, self.partial = (self.partial + text).rpartition("\n")
        if newline:
            self.recorder.write(complete + newline)

        return self.stream.write(text)

    def flush(self):
        self.recorder.flush()
        self.stream.flush()


@dataclass(frozen=True)
class ProjectSettings:
    """Settings of downstream projects: how to prepare and test them, and how to complete bare names."""

    prepare: str = "auto"
    test: tuple[str, ...] = ("pytest",)
    source_prefix: str | None = None

    def overridden(self, data: dict[str, Any]) -> ProjectSettings:
        """These settings, with the ones stated in config 'data' (if any) taking precedence."""
        test = data.get("test", self.test)
        return ProjectSettings(
            prepare=data.get("prepare", self.prepare),
            test=(test,) if isinstance(test, str) else tuple(test),
            source_prefix=data.get("source-prefix", self.source_prefix),
        )


@dataclass(frozen=True)
class Outcome:
    """Outcome of running one test command."""

    command: str
    failure: str | None  # Why it failed, None if it passed
    elapsed: float


class VirtualEnv:
    """Models a .venv/ for a project."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.venv_folder = folder / ".venv"
        self.bin_python = self.venv_folder / "bin/python"

    @cached_property
    def is_healthy(self) -> bool:
        """True if the venv has a working Python (skip recreation when True)."""
        return quiet_run(self.bin_python, "--version", dryrun=False, fatal=False, logger=None).succeeded

    @property
    def uv_env(self) -> dict[str, str]:
        """Environment making uv target this venv."""
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = str(self.venv_folder)
        return env

    def run_uv(self, *args, **kwargs):
        """Run uv with args (shown, see logged_run()), targeting this venv."""
        return logged_run("uv", *args, cwd=self.folder, env=self.uv_env, **kwargs)

    def ensure_venv(self, prepare_cmd: str, force: bool = False):
        """Create or update the venv using prepare_cmd or auto-detection."""
        if not force and self.is_healthy:
            logging.debug("Reusing existing venv %s", runez.short(self.venv_folder))
            return

        runez.ensure_folder(self.venv_folder, clean=True)  # Whatever was there (even a file) gets replaced
        if prepare_cmd == "auto":
            reqs = list(self.requirements_files())
            if reqs:
                self.run_uv("venv", "--clear")
                for req in reqs:
                    self.run_uv("pip", "install", "-r", req)

                self.run_uv("pip", "install", "-e", ".")  # install the project itself

            else:
                self.run_uv("sync")

        else:
            logged_run(*shlex.split(prepare_cmd), cwd=self.folder)

    def inject_upstream(self, upstream: UpstreamLocalized):
        """Inject upstream in editable mode, skip if already correctly installed."""
        if self.is_upstream_editable(upstream.local_folder):
            print(f"{upstream.package_name} already installed editable")

        else:
            print(f"injecting {upstream.package_name} (editable)")
            self.run_uv("pip", "install", "-e", str(upstream.local_folder))

    def is_upstream_editable(self, upstream_folder: Path) -> bool:
        """True if upstream (checked out in 'upstream_folder') is already installed as editable in this venv."""
        r = quiet_run("uv", "pip", "freeze", cwd=self.folder, env=self.uv_env, dryrun=False, fatal=False)  # Probe, shown with --verbose
        if r.succeeded:
            # Exact match: a downstream cloned under the upstream folder has an editable line that starts with the upstream path
            needle = f"-e file://{upstream_folder}"
            return any(line.strip() == needle for line in r.output.splitlines())

        return False

    def requirements_files(self):
        """Old-school requirements files in this project, if any."""
        for path in (self.folder / "requirements.txt", self.folder / "tests/requirements.txt"):
            if path.is_file():
                yield path


class RunWith(ABC):
    """Runs a test command from config, verifying that it really tests the upstream checkout (see docs/test-commands.md)."""

    needs_venv = False  # True if the command runs from the project's .venv/ (which then gets prepared, with upstream injected)
    needs_upstream_wheel = False  # True if the command needs an upstream wheel (built once per run, during prepare)

    def __init__(self, project: DownstreamLocalized, command: str):
        self.project = project
        self.command = command
        self.args = shlex.split(command)

    @staticmethod
    def handler_for(args: list[str]) -> type[RunWith]:
        """Handler for test command 'args' (RunWithNotSupported if none can run and verify it)."""
        if args and args[0] == "pytest":
            return RunWithPytest

        if RunWithTox.tox_args(args) is not None:
            return RunWithTox

        return RunWithNotSupported

    @staticmethod
    def for_command(project: DownstreamLocalized, command: str) -> RunWith:
        """Handler running test 'command' for 'project'."""
        return RunWith.handler_for(shlex.split(command))(project, command)

    @staticmethod
    def problem_with(command: str) -> str | None:
        """Why test 'command' can't be used, if it can't: ripple-effect must know how to verify it."""
        try:
            args = shlex.split(command)

        except ValueError as e:
            return f"test command '{command}': {e}"

        problem = RunWith.handler_for(args).problem(args)
        return f"test command '{command}': {problem}" if problem else None

    @classmethod
    def problem(cls, args: list[str]) -> str | None:
        """Why this handler can't run (and verify) test command 'args', if it can't."""
        return None

    @abstractmethod
    def run(self) -> str | None:
        """Run this test command, return why it failed (None if it passed)."""

    def run_command(self, program, *args) -> str | None:
        """Run 'program' with 'args' (shown), return why it failed (None if it passed)."""
        r = logged_run(program, *args, fatal=False, passthrough=True)
        return None if r.succeeded else f"exit code {r.exit_code}"


class RunWithPytest(RunWith):
    """`pytest ...`, ran from the project's .venv/ (where the upstream gets injected editable)."""

    needs_venv = True

    def run(self) -> str | None:
        venv = self.project.venv
        pytest = venv.venv_folder / "bin/pytest"
        upstream = self.project.spec.upstream
        if not runez.DRYRUN:  # Nothing got prepared in dryrun mode, nothing to verify
            if not pytest.exists():
                return "pytest is not installed in .venv/"

            if not venv.is_upstream_editable(upstream.local_folder):
                return f"{upstream.package_name} is not installed editable in .venv/"

        return self.run_command(pytest, *self.args[1:])


class RunWithTox(RunWith):
    """A tox run: `tox ...`, or via a wrapper (`uvx tox ...`, `my-wrapper tox ...`)."""

    @staticmethod
    def tox_args(args: list[str]) -> list[str] | None:
        """tox's own arguments in 'args' (after the `tox` word), None if 'args' doesn't run tox."""
        for i, arg in enumerate(args):
            if os.path.basename(arg) == "tox":
                return args[i + 1 :]

        return None

    @classmethod
    def problem(cls, args: list[str]) -> str | None:
        # Only simple forms are recognized (`tox -r ...`, `tox -re py`, `tox --recreate ...`), see docs/test-commands.md
        first_option = next((arg for arg in cls.tox_args(args) or [] if arg.startswith("-")), "")
        if not first_option.startswith(("-r", "--recreate")):
            return "tox's first option must be -r (or --recreate, e.g. 'tox -re py'), tox otherwise reuses existing envs"

        return None

    needs_upstream_wheel = True

    def run(self) -> str | None:
        overrides = str(self.project.spec.upstream.overrides_file)
        existing = os.environ.get("UV_OVERRIDE")  # uv accepts a space-separated list of files, keep any existing ones
        env = dict(os.environ, UV_OVERRIDE=runez.joined(overrides, existing))
        print(
            f"UV_OVERRIDE={runez.short(shlex.quote(env['UV_OVERRIDE']))}"
        )  # runez doesn't show env vars, allows to reproduce the run by hand
        before = self.tox_envs()
        r = logged_run(*self.args, env=env, fatal=False, passthrough=True)
        problems = [] if r.succeeded else [f"exit code {r.exit_code}"]
        if not runez.DRYRUN:
            problems.extend(self.verification_problems(before))

        return ", ".join(problems) or None

    def tox_envs(self) -> dict[Path, float]:
        """tox envs in the project's .tox/ folder (excluding internal ones such as .pkg), with the mtime of their pyvenv.cfg."""
        return {cfg.parent: cfg.stat().st_mtime for cfg in (self.project.local_folder / ".tox").glob("[!.]*/pyvenv.cfg")}

    def verification_problems(self, before: dict[Path, float]) -> list[str]:
        """Why the tox envs recreated by this run may not have tested the upstream checkout ('before': envs prior to the run)."""
        recreated = sorted(env for env, mtime in self.tox_envs().items() if before.get(env) != mtime)
        if not recreated:
            return ["couldn't verify that tox used the upstream checkout: no recreated env found in .tox/"]

        upstream = self.project.spec.upstream
        problems = []
        for env in recreated:
            installed = installed_from(env, upstream.package_name)
            if installed and installed != f"file://{upstream.wheel}":  # Envs without upstream (style etc.) are fine
                problems.append(f"tox env '{env.name}' has {upstream.package_name} {installed} instead of the upstream wheel")

        return problems


class RunWithNotSupported(RunWith):
    """A test command ripple-effect doesn't know how to verify: a config problem, left abstract as it never runs."""

    @classmethod
    def problem(cls, args: list[str]) -> str | None:
        if any("pytest" in arg for arg in args):
            return "state it as 'pytest ...', ripple-effect runs pytest from the project's .venv/"

        return "not supported yet, ripple-effect can't verify that it runs against the upstream checkout, contributions welcome"


class ProjectRef:
    """A reference to a project — a local folder or a git URL."""

    source_ref: str = ""

    def __init__(self, spec: RippleSpec, source_ref: str | None = None):
        self.spec = spec
        self.source_ref = source_ref or ""

    @cached_property
    def is_local(self) -> bool:
        """True if source_ref is a local path."""
        return is_local_path(self.source_ref)

    @cached_property
    def local_folder(self) -> Path:
        """Resolved local path — directly for local refs, under proving_grounds for URLs."""
        if self.is_local:
            return self.spec.resolved_path(self.source_ref)

        return self.spec.proving_grounds_folder / self.package_name

    @cached_property
    def pip_spec(self) -> str:
        """pip spec for uv_metadata — resolved path for local refs, raw URL for remote."""
        return str(self.local_folder) if self.is_local else self.source_ref

    @cached_property
    def package_metadata(self) -> dict[str, Any]:
        """Package metadata dict from uv_metadata."""
        from uv_metadata import get_metadata_from_pip_spec

        return get_metadata_from_pip_spec(self.pip_spec)

    @cached_property
    def package_name(self) -> str:
        """Package name, from metadata (uv_metadata errors out when it can't determine it)."""
        return str(self.package_metadata["name"])

    def _clone_or_update(self):
        """Clone or fetch-reset this project's git repo into proving_grounds."""
        url, ref = split_git_ref(self.source_ref)
        folder = self.local_folder
        if folder.is_dir():
            # Updating our own clone is housekeeping, shown with --verbose
            quiet_run("git", "fetch", cwd=folder)
            quiet_run("git", "reset", "--hard", "FETCH_HEAD", cwd=folder)

        else:
            args = ["git", "clone", url]
            if ref:
                args += ["--branch", ref]

            args.append(str(folder))
            runez.ensure_folder(self.spec.proving_grounds_folder)
            logged_run(*args)


class UpstreamLocalized(ProjectRef):
    """The upstream library under test — injected editable into each downstream venv."""

    def prepare(self):
        """Clone upstream if it's a URL, nothing to do for local folders."""
        print(f"upstream: {self.package_name} @ {runez.short(self.local_folder)}")
        if not self.is_local:
            self._clone_or_update()

    @cached_property
    def wheel(self) -> Path:
        """Wheel of the upstream checkout, built fresh on first use (once per run), see docs/tox.md."""
        folder = self.spec.ripple_folder / "upstream"
        runez.delete(folder)
        logged_run("uv", "build", "--wheel", "-o", folder, self.local_folder)
        if runez.DRYRUN:
            return folder / f"{self.package_name}.whl"  # Placeholder, nothing got built

        return next(folder.glob("*.whl"))

    @cached_property
    def overrides_file(self) -> Path:
        """uv overrides file, making uv install the upstream wheel in place of any other version of the upstream."""
        path = self.spec.ripple_folder / "overrides.txt"
        runez.write(path, f"{self.package_name} @ file://{self.wheel}\n")
        return path


class DownstreamLocalized(ProjectRef):
    """A downstream project to test the upstream library against."""

    def __init__(self, spec: RippleSpec, source_ref: str, settings: ProjectSettings):
        super().__init__(spec, source_ref)
        self.prepare_cmd = settings.prepare
        self.test_commands = tuple(RunWith.for_command(self, command) for command in settings.test)

    def representable_lines(self, indent=""):
        """Lines for display in `show` output."""
        yield represented("source-ref", self.source_ref, indent=f"{indent} - ")
        yield represented("prepare", self.prepare_cmd, indent=f"{indent}   ")
        if len(self.test_commands) == 1:
            yield represented("test", self.test_commands[0].command, indent=f"{indent}   ")

        else:
            yield f"{indent}   test:"
            for test_command in self.test_commands:
                yield f"{indent}     - {runez.green(runez.short(test_command.command))}"

    @cached_property
    def needs_venv(self) -> bool:
        """True if a test command runs from .venv/, which then needs to be prepared (tox for example uses its own envs)."""
        return any(test_command.needs_venv for test_command in self.test_commands)

    @cached_property
    def venv(self) -> VirtualEnv:
        """Virtual environment for this project."""
        return VirtualEnv(self.local_folder)

    def prepare(self):
        """Clone/update if URL, ensure venv and inject upstream (if a test command needs the venv)."""
        if not self.is_local:
            self._clone_or_update()

        if self.needs_venv:
            self.venv.ensure_venv(self.prepare_cmd)
            self.venv.inject_upstream(self.spec.upstream)

    def run_tests(self) -> list[Outcome]:
        """Run all test commands (even after one fails), return their outcomes."""
        outcomes = []
        with runez.CurrentFolder(self.local_folder):
            for test_command in self.test_commands:
                started = time.monotonic()
                failure = test_command.run()
                outcomes.append(Outcome(test_command.command, failure, time.monotonic() - started))

        return outcomes


class DownstreamGroup:
    """Downstream projects from one 'downstream-projects' entry, a lone project is a group without description."""

    def __init__(self, description: str | None, projects: tuple[DownstreamLocalized, ...]):
        self.description = description
        self.projects = projects

    @property
    def indent(self) -> str:
        """Indentation of this group's projects in reports: nested under the description, when there is one."""
        return "  " if self.description else ""

    def representable_lines(self):
        """Lines for display in `show` output."""
        if self.description:
            yield f" - {runez.bold(self.description)}:"

        for project in self.projects:
            yield from project.representable_lines(indent=self.indent)


class RippleSpec:
    """Parsed and resolved ripple-effect configuration."""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.section_printed = False  # Set first: an invalid YAML aborts from within loaded_config() below
        self.problems: list[str] = []  # Reported all at once: `show` displays them, other commands abort with them
        self.recorder = OutputRecorder()  # Records output of `run` to RUN_LOG
        data = self.checked_mapping(self.loaded_config(), TOP_LEVEL_KEYS, "top level", required=("upstream", "downstream-projects"))
        self.upstream = UpstreamLocalized(self, data.get("upstream"))
        self.proving_grounds = data.get("proving-grounds") or DEFAULT_PROVING_GROUNDS
        self.defaults = ProjectSettings().overridden(data)
        entries: list[Any] = data.get("downstream-projects", [])
        self.groups = tuple(self.parsed_group(entry, f"downstream-projects[{i}]") for i, entry in enumerate(entries))
        self.downstream_projects = tuple(p for group in self.groups for p in group.projects)
        seen = set()
        for project in self.downstream_projects:
            if project.source_ref in seen:
                self.problems.append(f"'{project.source_ref}' is listed more than once in downstream-projects")

            elif project.source_ref:  # Missing ones are already reported
                seen.add(project.source_ref)

    @classmethod
    def from_file(cls, config_path: Path | str) -> RippleSpec:
        """Load a RippleSpec from a YAML config file."""
        return cls(Path(config_path).expanduser())

    def print_section(self, title: str, level: int = 2, color: Callable[[str], str] = runez.blue, file: TextIO | None = None):
        """Heading of an output section (see docs/pipeline.md#output), separated by a blank line from the previous section (if any)."""
        if self.section_printed:
            print(file=file)

        self.section_printed = True
        print(color(f"{'#' * level} {title}"), file=file)

    def abort_with_errors(self, message: str):
        """Exit with code 1, showing 'message' in an '## Errors' section on stderr."""
        # runez colors when stdout is a tty: don't let color codes end up in a redirected stderr
        color = runez.red if runez.SYS_INFO.terminal.is_stderr_tty else runez.plain
        self.print_section("Errors", color=color, file=sys.stderr)
        print(message, file=sys.stderr)
        sys.exit(1)

    def abort_if_invalid(self):
        """Exit with code 1 if problems were found in config, listing them all in an '## Errors' section."""
        if self.problems:
            listed = "".join(f"\n- {problem}" for problem in self.problems)
            self.abort_with_errors(f"Invalid config {runez.short(self.config_path)}:{listed}")

    def loaded_config(self):
        """Contents of the YAML config file."""
        with self.config_path.open() as fh:
            try:
                return yaml.load(fh, Loader=UniqueKeyLoader) or {}  # noqa: S506, UniqueKeyLoader is a SafeLoader

            except yaml.YAMLError as e:
                # Nothing to show then, abort right away
                self.problems.append(f"invalid YAML: {e}")
                self.abort_if_invalid()

    def checked_mapping(self, data, allowed: tuple[str, ...], where: str, required: tuple[str, ...] = ()) -> dict[str, Any]:
        """Valid keys of mapping 'data', recording problems: unknown keys, values of the wrong type, missing 'required' keys."""
        if not isinstance(data, dict):
            self.problems.append(f"{where}: expected a mapping")
            return {}

        valid = {}
        for key, value in data.items():
            problems = []
            if key not in allowed:
                problems.append(f"unknown key '{key}', expected one of: {', '.join(allowed)}")

            elif key in LIST_KEYS:
                if not value or not isinstance(value, list):
                    problems.append(f"'{key}' must be a non-empty list")

            elif key == "test":
                commands = [value] if isinstance(value, str) else value
                if not commands or not isinstance(commands, list) or not all(c and isinstance(c, str) for c in commands):
                    problems.append("'test' must be a non-empty string, or a non-empty list of them")

                else:
                    problems.extend(problem for problem in map(RunWith.problem_with, commands) if problem)

            elif not value or not isinstance(value, str):
                problems.append(f"'{key}' must be a non-empty string")

            elif key == "source-prefix" and is_bare_name(value):
                problems.append(f"'source-prefix' must be a URL or a local path, got '{value}'")

            if problems:
                self.problems.extend(f"{where}: {problem}" for problem in problems)

            else:
                valid[key] = value

        missing = [key for key in required if key not in data]
        if missing:
            self.problems.append(f"{where}: missing {', '.join(repr(key) for key in missing)}")

        return valid

    def parsed_group(self, entry, where: str) -> DownstreamGroup:
        """Group of downstream projects from one 'downstream-projects' entry."""
        if isinstance(entry, dict) and "source-ref" not in entry:
            # A group, or a mistyped one: checking against GROUP_KEYS gives the most helpful problem report then
            group = self.checked_mapping(entry, GROUP_KEYS, where)
            if "sources" not in entry:
                self.problems.append(f"{where}: needs either 'source-ref' (a project) or 'sources' (a group)")

            settings = self.defaults.overridden(group)
            sources = group.get("sources", [])
            projects = tuple(self.parsed_project(x, settings, f"{where}.sources[{i}]") for i, x in enumerate(sources))
            return DownstreamGroup(group.get("description"), projects)

        return DownstreamGroup(None, (self.parsed_project(entry, self.defaults, where),))

    def parsed_project(self, entry, settings: ProjectSettings, where: str) -> DownstreamLocalized:
        """Downstream project from a config entry: a plain string, or a mapping with 'source-ref'."""
        if isinstance(entry, str):
            entry = {"source-ref": entry}

        if isinstance(entry, dict):
            project = self.checked_mapping(entry, PROJECT_KEYS, where, required=("source-ref",))

        else:
            self.problems.append(f"{where}: expected a string or a mapping")
            project = {}

        source_ref = project.get("source-ref", "")  # Shown as '-missing-' by `show` when missing
        if source_ref and is_bare_name(source_ref):
            if settings.source_prefix:
                source_ref = settings.source_prefix + source_ref

            else:
                self.problems.append(f"{where}: '{source_ref}' is neither a URL nor a local path, and no 'source-prefix' is in effect")

        return DownstreamLocalized(self, source_ref, settings.overridden(project))

    @cached_property
    def config_folder(self) -> Path:
        """Folder containing the config file."""
        return self.config_path.parent

    @cached_property
    def proving_grounds_folder(self) -> Path:
        """Resolved proving grounds folder."""
        return self.resolved_path(self.proving_grounds)

    @cached_property
    def ripple_folder(self) -> Path:
        """Folder where ripple-effect keeps its own files (upstream wheel etc.)."""
        return self.proving_grounds_folder / ".ripple"

    def resolved_path(self, source_ref: str) -> Path:
        """Resolve a source_ref to an absolute path, relative to config_folder if not absolute."""
        expanded = os.path.expandvars(os.path.expanduser(source_ref))
        path = Path(expanded)
        if not path.is_absolute():
            path = self.config_folder / path

        return path.resolve()

    def representable_lines(self):
        """Lines for display in `show` output."""
        yield represented("config_path", self.config_path)
        yield represented("upstream", self.upstream.source_ref)
        yield represented("proving-grounds", self.proving_grounds)
        yield "%s:" % runez.plural(self.downstream_projects, "downstream project")
        for group in self.groups:
            yield from group.representable_lines()

    def represented(self) -> str:
        """String representation for `show` command."""
        return runez.joined(self.representable_lines(), delimiter="\n")

    def clean_proving_grounds(self):
        """Empty proving-grounds folder, refusing to if it holds anything that isn't ours."""
        folder = self.proving_grounds_folder
        precious = [self.config_path.resolve()] + [p.local_folder for p in (self.upstream, *self.downstream_projects) if p.is_local]
        for path in precious:
            if path.is_relative_to(folder):
                self.abort_with_errors(f"Not cleaning proving-grounds {runez.short(folder)}: it holds {runez.short(path)}")

        runez.ensure_folder(folder, clean=True, logger=print)

    def prepare(self, clean: bool = False):
        """Prepare all downstream project environments (from an empty proving-grounds folder if 'clean')."""
        self.print_section("Preparation")
        if clean:
            self.clean_proving_grounds()

        self.recorder.start(self.proving_grounds_folder / RUN_LOG)

        self.upstream.prepare()
        if any(test_command.needs_upstream_wheel for project in self.downstream_projects for test_command in project.test_commands):
            print(f"uv overrides for tox runs: {runez.short(self.upstream.overrides_file)}")

        for downstream in self.downstream_projects:
            self.print_section(downstream.package_name, level=3)
            print(f"folder: {runez.short(downstream.local_folder)}")
            downstream.prepare()

    def run(self, clean: bool = False) -> None:
        """Prepare environments, run all test suites, report results (recorded to RUN_LOG, except in dryrun mode)."""
        self.recorder.enable()
        try:
            self.run_and_report(clean)

        finally:
            self.recorder.stop()

    def run_and_report(self, clean: bool):
        """Prepare environments, run all test suites, report results."""
        self.prepare(clean=clean)
        results: dict[DownstreamLocalized, list[Outcome]] = {}
        self.print_section("Testing")
        for downstream in self.downstream_projects:
            self.print_section(downstream.package_name, level=3)
            results[downstream] = downstream.run_tests()

        self.print_section("Outcome")
        fail_count = 0
        for group in self.groups:
            if group.description:
                print(f"{runez.bold(group.description)}:")

            for downstream in group.projects:
                outcomes = results[downstream]
                failures = [outcome.failure for outcome in outcomes if outcome.failure]
                fail_count += len(failures)
                elapsed = sum(outcome.elapsed for outcome in outcomes)
                if len(outcomes) == 1:
                    print(outcome_line(f"{group.indent}{downstream.package_name}", outcomes[0].failure, elapsed))

                else:
                    print(outcome_line(f"{group.indent}{downstream.package_name}", "" if failures else None, elapsed))
                    for outcome in outcomes:
                        print(outcome_line(f"  {group.indent}{outcome.command}", outcome.failure, outcome.elapsed))

        if fail_count:
            print(runez.red(f"{runez.plural(fail_count, 'test')} failed"))
            sys.exit(1)

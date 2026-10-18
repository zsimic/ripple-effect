"""Model for ripple-effect: spec, project refs, virtual envs."""

from __future__ import annotations

import logging
import os
import shlex
import time
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

import runez
import yaml

# Valid config keys, per level (see SPEC.md)
TOP_LEVEL_KEYS = ("upstream", "proving-grounds", "source-prefix", "prepare", "test", "downstream-projects")
GROUP_KEYS = ("description", "source-prefix", "prepare", "test", "sources")
PROJECT_KEYS = ("source-ref", "prepare", "test")
LIST_KEYS = ("downstream-projects", "sources")  # All other keys have string values
DEFAULT_PROVING_GROUNDS = "build/ripple-check"  # Relative to the config file's folder, 'build/' is typically git-ignored


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


def is_local_path(source_ref: str) -> bool:
    """True if 'source_ref' is a local path."""
    return source_ref.startswith((".", "~", "/"))


def is_bare_name(source_ref: str) -> bool:
    """True if 'source_ref' is neither a local path nor a URL, a 'source-prefix' completes it then."""
    return not is_local_path(source_ref) and not source_ref.startswith("git@") and "://" not in source_ref


def logged_run(program, *args, logger=print, **kwargs):
    """runez.run() for commands ran on the user's behalf: shown as they run (internal probes are shown with --verbose only)."""
    return runez.run(program, *args, logger=logger, **kwargs)


def split_git_ref(source_ref: str) -> tuple[str, str | None]:
    """Split 'https://github.com/foo/bar.git@main' into ('url', 'main'), None ref if no @ given."""
    if not source_ref.startswith("git@"):
        url, sep, ref = source_ref.rpartition("@")
        if sep:
            return url, ref

    return source_ref, None


@dataclass(frozen=True)
class ProjectSettings:
    """Settings of downstream projects: how to prepare and test them, and how to complete bare names."""

    prepare: str = "auto"
    test: str = ".venv/bin/pytest tests/"
    source_prefix: str | None = None

    def overridden(self, data: dict[str, Any]) -> ProjectSettings:
        """These settings, with the ones stated in config 'data' (if any) taking precedence."""
        return ProjectSettings(
            prepare=data.get("prepare", self.prepare),
            test=data.get("test", self.test),
            source_prefix=data.get("source-prefix", self.source_prefix),
        )


class VirtualEnv:
    """Models a .venv/ for a project."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.venv_folder = folder / ".venv"
        self.bin_python = self.venv_folder / "bin/python"

    @cached_property
    def is_healthy(self) -> bool:
        """True if the venv has a working Python (skip recreation when True)."""
        return runez.run(self.bin_python, "--version", dryrun=False, fatal=False).succeeded

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
            print(f"  {upstream.package_name} already installed editable")

        else:
            print(f"  injecting {upstream.package_name} (editable)")
            self.run_uv("pip", "install", "-e", str(upstream.local_folder))

    def is_upstream_editable(self, upstream_folder: Path) -> bool:
        """True if upstream (checked out in 'upstream_folder') is already installed as editable in this venv."""
        r = runez.run("uv", "pip", "freeze", cwd=self.folder, env=self.uv_env, dryrun=False, fatal=False)  # Probe, shown with --verbose
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
        """Package name from metadata, raises if not determinable."""
        name = self.package_metadata.get("name")
        if not name:
            raise ValueError(f"Package name could not be determined for {self.source_ref!r}")

        return str(name)

    def _clone_or_update(self):
        """Clone or fetch-reset this project's git repo into proving_grounds."""
        url, ref = split_git_ref(self.source_ref)
        folder = self.local_folder
        if folder.is_dir():
            # Updating our own clone is housekeeping, shown with --verbose
            runez.run("git", "fetch", cwd=folder)
            runez.run("git", "reset", "--hard", "FETCH_HEAD", cwd=folder)

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


class DownstreamLocalized(ProjectRef):
    """A downstream project to test the upstream library against."""

    def __init__(self, spec: RippleSpec, source_ref: str, settings: ProjectSettings):
        super().__init__(spec, source_ref)
        self.prepare_cmd = settings.prepare
        self.test_cmd = settings.test

    def representable_lines(self, indent=""):
        """Lines for display in `show` output."""
        yield represented("source-ref", self.source_ref, indent=f"{indent} - ")
        yield represented("prepare", self.prepare_cmd, indent=f"{indent}   ")
        yield represented("test", self.test_cmd, indent=f"{indent}   ")

    @cached_property
    def venv(self) -> VirtualEnv:
        """Virtual environment for this project."""
        return VirtualEnv(self.local_folder)

    def prepare(self):
        """Clone/update if URL, ensure venv, inject upstream."""
        if not self.is_local:
            self._clone_or_update()

        self.venv.ensure_venv(self.prepare_cmd)
        self.venv.inject_upstream(self.spec.upstream)

    def run_tests(self) -> bool:
        """Run the test suite, return True if passed."""
        with runez.CurrentFolder(self.local_folder):
            # runez.run() uses `which()` and gets fooled when program to run is a relative path (bug in runez)
            parts = shlex.split(self.test_cmd)
            r = logged_run(*parts, fatal=False, passthrough=True)
            return r.succeeded


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
        self.problems: list[str] = []  # Reported all at once: `show` displays them, other commands abort with them
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

    def abort_if_invalid(self):
        """Abort if problems were found in config, listing them all."""
        if self.problems:
            listed = "".join(f"\n - {problem}" for problem in self.problems)
            runez.abort(f"Invalid config {runez.short(self.config_path)}:{listed}")

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
            problem = None
            if key not in allowed:
                problem = f"unknown key '{key}', expected one of: {', '.join(allowed)}"

            elif key in LIST_KEYS:
                if not value or not isinstance(value, list):
                    problem = f"'{key}' must be a non-empty list"

            elif not value or not isinstance(value, str):
                problem = f"'{key}' must be a non-empty string"

            elif key == "source-prefix" and is_bare_name(value):
                problem = f"'source-prefix' must be a URL or a local path, got '{value}'"

            if problem:
                self.problems.append(f"{where}: {problem}")

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

    def prepare(self):
        """Prepare all downstream project environments."""
        self.upstream.prepare()
        for downstream in self.downstream_projects:
            print(f"\n{runez.bold(downstream.package_name)}: {runez.short(downstream.local_folder)}")
            downstream.prepare()

    def run(self) -> None:
        """Prepare environments, run all test suites, report results."""
        self.prepare()
        results: dict[DownstreamLocalized, tuple[bool, float]] = {}
        for downstream in self.downstream_projects:
            print(f"\nTesting {runez.bold(downstream.package_name)}...")
            started = time.monotonic()
            passed = downstream.run_tests()
            results[downstream] = (passed, time.monotonic() - started)

        print(f"\n{'─' * 50}")
        for group in self.groups:
            if group.description:
                print(f"  {runez.bold(group.description)}:")

            for downstream in group.projects:
                passed, elapsed = results[downstream]
                status = runez.green("PASSED") if passed else runez.red("FAILED")
                print(f"  {group.indent}{downstream.package_name}: {status} ({elapsed:.1f}s)")

        runez.abort_if(not all(passed for passed, _ in results.values()), "Some tests failed")

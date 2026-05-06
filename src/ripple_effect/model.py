"""Model for ripple-effect: spec, project refs, virtual envs."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import runez
import yaml


def represented(key: str, value, indent="") -> str:
    """Colored representation of a key/value pair."""
    value = runez.green(runez.short(value)) if value else runez.red("-missing-")
    return f"{indent}{key}: {value}"


def split_git_ref(source_ref: str) -> tuple[str, str | None]:
    """Split 'https://github.com/foo/bar.git@main' into ('url', 'main'), None ref if no @ given."""
    if not source_ref.startswith("git@"):
        url, sep, ref = source_ref.rpartition("@")
        if sep:
            return url, ref

    return source_ref, None


@dataclass(frozen=True)
class CommandSpec:
    """Commands used to prepare and test a project."""

    prepare: str
    test: str

    @classmethod
    def from_config(cls, data: dict | None) -> CommandSpec:
        """Parse prepare/test commands from config data, applying defaults."""
        data = data or {}
        return cls(
            prepare=data.get("prepare") or "auto",
            test=data.get("test") or ".venv/bin/pytest tests/",
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
        return runez.run(self.bin_python, "--version", dryrun=False, fatal=False, logger=None).succeeded

    def run_uv(self, *args, **kwargs):
        """Run uv with args, targeting this venv via VIRTUAL_ENV."""
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = str(self.venv_folder)
        return runez.run("uv", *args, cwd=self.folder, env=env, **kwargs)

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

            else:
                self.run_uv("sync")

        else:
            runez.run(prepare_cmd, cwd=self.folder)

    def inject_upstream(self, upstream: UpstreamLocalized):
        """Inject upstream in editable mode, skip if already correctly installed."""
        if self.is_upstream_editable(upstream):
            print(f"  {upstream.package_name} already installed editable")

        else:
            print(f"  injecting {upstream.package_name} (editable)")
            self.run_uv("pip", "install", "-e", str(upstream.local_folder))

    def is_upstream_editable(self, upstream: UpstreamLocalized) -> bool:
        """True if upstream is already installed as editable in this venv."""
        r = self.run_uv("pip", "freeze", dryrun=False, fatal=False, logger=None)
        if r.succeeded:
            needle = f"-e file://{upstream.local_folder}"
            return any(line.startswith(needle) for line in r.output.splitlines())

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
        return self.source_ref.startswith((".", "~", "/"))

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
    def package_metadata(self) -> dict:
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


class UpstreamLocalized(ProjectRef):
    """The upstream library under test — injected editable into each downstream venv."""


class DownstreamLocalized(ProjectRef):
    """A downstream project to test the upstream library against."""

    def __init__(self, spec: RippleSpec, entry: dict | str):
        if isinstance(entry, str):
            entry = {"source-ref": entry}

        super().__init__(spec, entry.get("source-ref"))
        self.prepare_cmd = entry.get("prepare") or spec.defaults.prepare
        self.test_cmd = entry.get("test") or spec.defaults.test

    def representable_lines(self):
        """Lines for display in `show` output."""
        yield represented("source-ref", self.source_ref, indent=" - ")
        yield represented("prepare", self.prepare_cmd, indent="   ")
        yield represented("test", self.test_cmd, indent="   ")

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

    def _clone_or_update(self):
        """Clone or fetch-reset this project's git repo into proving_grounds."""
        url, ref = split_git_ref(self.source_ref)
        folder = self.local_folder
        if folder.is_dir():
            runez.run("git", "fetch", cwd=folder)
            runez.run("git", "reset", "--hard", "FETCH_HEAD", cwd=folder)

        else:
            args = ["git", "clone", url]
            if ref:
                args += ["--branch", ref]

            args.append(str(folder))
            runez.ensure_folder(self.spec.proving_grounds_folder)
            runez.run(*args)


class RippleSpec:
    """Parsed and resolved ripple-effect configuration."""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        data = yaml.safe_load(config_path.read_text()) or {}
        self.upstream = UpstreamLocalized(self, data.get("upstream"))
        self.proving_grounds = data.get("proving-grounds") or ""
        self.defaults = CommandSpec.from_config(data.get("defaults"))
        entries = data.get("downstream-projects") or []
        self.downstream_projects = tuple(DownstreamLocalized(self, e) for e in entries)

    @classmethod
    def from_file(cls, config_path: Path | str) -> RippleSpec:
        """Load a RippleSpec from a YAML config file."""
        return cls(Path(config_path).expanduser())

    @cached_property
    def config_folder(self) -> Path:
        """Folder containing the config file."""
        return self.config_path.parent

    @cached_property
    def proving_grounds_folder(self) -> Path:
        """Resolved proving grounds folder — raises if not configured."""
        if not self.proving_grounds:
            raise ValueError(f"No proving-grounds specified in {runez.short(self.config_path)}")

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
        for p in self.downstream_projects:
            yield runez.joined(p.representable_lines(), delimiter="\n")

    def represented(self) -> str:
        """String representation for `show` command."""
        return runez.joined(self.representable_lines(), delimiter="\n")

    def prepare(self):
        """Prepare all downstream project environments."""
        runez.abort_if(not self.upstream.source_ref, "No upstream specified")
        print(f"upstream: {self.upstream.package_name} @ {runez.short(self.upstream.local_folder)}")
        for downstream in self.downstream_projects:
            print(f"\n{runez.bold(downstream.package_name)}: {runez.short(downstream.local_folder)}")
            downstream.prepare()

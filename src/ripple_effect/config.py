"""Config loading and normalization for ripple-effect."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when a config file is missing, malformed, or semantically invalid."""


DEFAULT_PREPARE = "auto"
DEFAULT_TEST = ".venv/bin/pytest tests/"

TOP_LEVEL_KEYS = ("upstream", "proving-grounds", "defaults", "downstream-projects")
DEFAULTS_KEYS = ("prepare", "test")
PROJECT_KEYS = ("url", "folder", "prepare", "test")


@dataclass(frozen=True)
class ProjectRef:
    """A reference to a project — a local folder or a git URL."""

    raw: str

    @property
    def is_local(self) -> bool:
        """True if this references a local folder."""
        return self.raw.startswith((".", "~", "/"))


@dataclass(frozen=True)
class DownstreamProject(ProjectRef):
    """A downstream project to test the upstream library against."""

    prepare: str
    test: str


@dataclass(frozen=True)
class Config:
    """A parsed and normalized ripple-effect config."""

    config_path: Path
    upstream: ProjectRef
    proving_grounds: Path | None
    downstream_projects: tuple[DownstreamProject, ...]


def load_config(config_path: Path | str) -> Config:
    """Read and validate a YAML config file. Returns a normalized Config."""
    path = Path(config_path).expanduser()
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")

    try:
        text = path.read_text()
    except OSError as e:
        raise ConfigError(f"Could not read {path}: {e}") from e

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError(f"Could not parse YAML in {path}: {e}") from e

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top-level must be a mapping")

    unknown = [k for k in data if k not in TOP_LEVEL_KEYS]
    if unknown:
        raise ConfigError(f"{path}: unknown top-level keys: {sorted(unknown)}")

    upstream = parse_upstream(data.get("upstream"), path)
    proving_grounds = parse_proving_grounds(data.get("proving-grounds"), path)
    default_prepare, default_test = parse_defaults(data.get("defaults"), path)
    projects = parse_projects(data.get("downstream-projects"), default_prepare, default_test, path)

    if proving_grounds is None and any(not p.is_local for p in projects):
        raise ConfigError(f"{path}: 'proving-grounds' is required when any downstream project is a git URL")

    return Config(
        config_path=path,
        upstream=upstream,
        proving_grounds=proving_grounds,
        downstream_projects=projects,
    )


def parse_upstream(value: Any, path: Path) -> ProjectRef:
    """Validate and normalize the ``upstream`` field, defaulting to '.'."""
    if value is None:
        value = "."
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path}: 'upstream' must be a non-empty string")
    return ProjectRef(raw=value)


def parse_proving_grounds(value: Any, path: Path) -> Path | None:
    """Validate and expand the ``proving-grounds`` path. Returns None if absent."""
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path}: 'proving-grounds' must be a non-empty string")
    return Path(expand(value))


def parse_defaults(value: Any, path: Path) -> tuple[str, str]:
    """Validate and resolve the ``defaults`` block to (prepare, test)."""
    if value is None:
        return DEFAULT_PREPARE, DEFAULT_TEST
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: 'defaults' must be a mapping")
    unknown = [k for k in value if k not in DEFAULTS_KEYS]
    if unknown:
        raise ConfigError(f"{path}: unknown keys in 'defaults': {sorted(unknown)}")
    prepare = value.get("prepare", DEFAULT_PREPARE)
    test = value.get("test", DEFAULT_TEST)
    if not isinstance(prepare, str) or not prepare:
        raise ConfigError(f"{path}: 'defaults.prepare' must be a non-empty string")
    if not isinstance(test, str) or not test:
        raise ConfigError(f"{path}: 'defaults.test' must be a non-empty string")
    return prepare, test


def parse_projects(value: Any, default_prepare: str, default_test: str, path: Path) -> tuple[DownstreamProject, ...]:
    """Validate the ``downstream-projects`` list and parse each entry."""
    if value is None or value == []:
        raise ConfigError(f"{path}: 'downstream-projects' must contain at least one entry")
    if not isinstance(value, list):
        raise ConfigError(f"{path}: 'downstream-projects' must be a list")
    return tuple(parse_project_entry(entry, default_prepare, default_test, path, i) for i, entry in enumerate(value))


def parse_project_entry(entry: Any, default_prepare: str, default_test: str, path: Path, index: int) -> DownstreamProject:
    """Parse a single downstream-projects entry (string shorthand or mapping)."""
    where = f"{path}[downstream-projects][{index}]"
    if isinstance(entry, str):
        if not entry:
            raise ConfigError(f"{where}: project entry is empty")
        return DownstreamProject(raw=entry, prepare=default_prepare, test=default_test)

    if isinstance(entry, dict):
        unknown = [k for k in entry if k not in PROJECT_KEYS]
        if unknown:
            raise ConfigError(f"{where}: unknown keys in project entry: {sorted(unknown)}")
        url = entry.get("url")
        folder = entry.get("folder")
        if url and folder:
            raise ConfigError(f"{where}: project entry has both 'url' and 'folder' — pick one")
        if not url and not folder:
            raise ConfigError(f"{where}: project entry needs one of 'url' or 'folder'")
        raw = url if url else folder
        if not isinstance(raw, str) or not raw:
            raise ConfigError(f"{where}: 'url'/'folder' must be a non-empty string")
        prepare = entry.get("prepare", default_prepare)
        test = entry.get("test", default_test)
        if not isinstance(prepare, str) or not prepare:
            raise ConfigError(f"{where}: 'prepare' must be a non-empty string")
        if not isinstance(test, str) or not test:
            raise ConfigError(f"{where}: 'test' must be a non-empty string")
        return DownstreamProject(
            raw=raw,
            prepare=prepare,
            test=test,
        )

    raise ConfigError(f"{where}: project entry must be a string or mapping, got {type(entry).__name__}")


def expand(value: str) -> str:
    """Expand ``~`` and ``$VAR`` references in a string path."""
    return os.path.expandvars(os.path.expanduser(value))

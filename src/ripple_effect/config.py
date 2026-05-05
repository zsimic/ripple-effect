"""Config loading and normalization for ripple-effect."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

import runez
import yaml


def represented(key: str, value, indent="") -> str:
    """Colored representation of a key/value pair"""
    value = runez.green(runez.short(value)) if value else runez.red("-missing-")
    return f"{indent}{key}: {value}"


class ProjectRef:
    """A reference to a project — a local folder or a git URL."""

    source_ref: str

    def __init__(self, source_ref: str | None = None):
        self.source_ref = source_ref or ""

    @property
    def is_local(self) -> bool:
        """True if this references a local folder."""
        return self.source_ref.startswith((".", "~", "/"))


class Testable(ProjectRef):
    """A downstream project to test the upstream library against."""

    prepare: str
    test: str

    def __init__(self, source_ref: str | None = None, prepare: str | None = None, test: str | None = None):
        super().__init__(source_ref)
        self.prepare = prepare or "auto"
        self.test = test or ".venv/bin/pytest tests/"

    def representable_lines(self):
        yield represented("source-ref", self.source_ref, indent=" - ")
        yield represented("prepare", self.prepare, indent="   ")
        yield represented("test", self.test, indent="   ")

    @classmethod
    def from_defaults(cls, data: dict) -> Testable:
        """Parse the `defaults:` block into a seed Testable (no raw)."""
        return cls(prepare=data.get("prepare"), test=data.get("test"))

    @classmethod
    def from_entry(cls, entry: dict | str, defaults: Testable) -> Testable:
        """Parse one downstream-projects entry, inheriting from defaults."""
        if isinstance(entry, str):
            entry = {"source-ref": entry}
        source_ref = entry.get("source-ref")
        return cls(source_ref=source_ref, prepare=entry.get("prepare") or defaults.prepare, test=entry.get("test") or defaults.test)


class Config:
    """A parsed and normalized ripple-effect config."""

    def __init__(self, path: Path, upstream: ProjectRef, proving_grounds: str | None, downstream_projects: Sequence[Testable]):
        self.path = path
        self.upstream = upstream
        self.proving_grounds = proving_grounds or ""
        self.downstream_projects = downstream_projects

    def representable_lines(self):
        yield represented("config_path", self.path)
        yield represented("upstream", self.upstream.source_ref)
        yield represented("proving-grounds", self.proving_grounds)
        yield "%s:" % runez.plural(self.downstream_projects, "downstream project")
        for p in self.downstream_projects:
            yield runez.joined(p.representable_lines(), delimiter="\n")

    def represented(self) -> str:
        return runez.joined(self.representable_lines(), delimiter="\n")


def load_config(config_path: Path | str) -> Config:
    """Read and validate a YAML config file. Returns a normalized Config."""
    path = Path(config_path).expanduser()
    data = yaml.safe_load(path.read_text()) or {}
    upstream = ProjectRef(data.get("upstream"))
    proving_grounds = data.get("proving-grounds")
    defaults = Testable.from_defaults(data.get("defaults") or {})
    entries = data.get("downstream-projects") or []
    return Config(path, upstream, proving_grounds, tuple(Testable.from_entry(e, defaults) for e in entries))

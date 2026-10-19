# ripple-effect internal docs

The *inside view* of ripple-effect: how it works, and the "why" behind choices that aren't obvious
from the code. For people (and coding agents) working **on** ripple-effect. Users want the
[README](../README.rst), which is also what PyPI shows.

ripple-effect tests an upstream library against downstream projects that depend on it. It clones (or
uses in place) each downstream project, makes the upstream checkout the one they install, runs their
test commands, and reports pass/fail per project. Its whole value is that a pass really means "passes
against the upstream checkout", so a lot of the code is about verifying that, and refusing setups it
can't verify.

Two modules do everything: `src/ripple_effect/cli.py` (click group: `show`, `prepare`, `run`) and
`src/ripple_effect/model.py` (all domain objects). Start reading at `RippleSpec`, then
`DownstreamLocalized`.

## Pages

- [Contributing](./contributing.md): tox envs, testing style, code style.
- [Config](./config.md): how the YAML is loaded, validated, and resolved into projects.
- [Pipeline](./pipeline.md): what `prepare` and `run` do, and how output is logged.
- [Test commands](./test-commands.md): the handlers that run and verify each test command.
- [tox](./tox.md): how tox envs are made to use the upstream checkout, and verified.
- [Release](./release.md): changelog and tagging.
- [Roadmap](./roadmap.md): known gaps and what's out of scope.

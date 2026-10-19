# AGENTS.md

ripple-effect tests an upstream Python library against the downstream projects that depend on it.
The repo docs live in [`docs/`](./docs/index.md): read them rather than re-deriving how this repo
works.

## Looking for

- **How to use ripple-effect** → [`README.rst`](./README.rst) (also what PyPI shows). `docs/` is
  *internal*, not published anywhere.
- **How to develop on it** → [`docs/contributing.md`](./docs/contributing.md).
- **What changed** → [`CHANGELOG.md`](./CHANGELOG.md), how to release → [`docs/release.md`](./docs/release.md).

## Working notes

- `tox.ini` is the hub: every check is a tox env, CI just calls them.
- Five type checkers are kept at zero in CI (`tox -e ty`, `pyrefly`, `pyright`, `mypy`, `zuban`).
- Lean on runez (`runez.run()`, file helpers, `runez.joined()`, `runez.pyenv.PypiStd`...) before
  hand-rolling: it's dryrun-aware.
- As user-visible changes land, keep the top section of `CHANGELOG.md` (the upcoming version) current.
- Early, complete errors are a feature: users are mostly Claude and CI, so a bogus config should be
  reported in full before anything runs.

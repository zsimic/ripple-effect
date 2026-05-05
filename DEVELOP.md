## Commands

```bash
# Run all tests + coverage report + linters
tox

# Run a single test by name
.venv/bin/pytest -k test_help

# Run ruff linter (check only)
tox -e style

# Auto-fix linting/formatting with ruff
tox -e reformat

# Run type checking
tox -e typecheck
```

## Testing

Tests live in `tests/` and use the `cli` fixture from `runez.conftest` to
drive the real CLI entry point. Style guide:

- **Default to high-level CLI tests.** Drive tests through `cli.run(...)` and
  assert against `cli.succeeded` / `cli.failed` and `cli.logged.stdout`.
  Reach for module-level tests of internals only when there's a specific
  reason a case can't be exercised through the CLI — narrow tests pin
  internal shapes and tend to break on refactors even when behaviour is
  unchanged.
- **The `cli` fixture creates and `cd`-s into a per-test temp folder** (and
  cleans it up). Write files inside the test body with relative paths — e.g.
  `runez.write("sample.yml", ...)` — and `os.getcwd()` is that temp folder.
- **Don't pair `cli` with `temp_folder`.** The `temp_folder` fixture is
  redundant when `cli` is in use.
- **Use coverage to find gaps, not to drive tests up-front.** Toward the end
  of a feature run `tox` (which feeds into `tox -e coverage`) to see which
  branches haven't been exercised, and add high-level CLI cases to cover
  them.

Example:

```python
import runez


def test_minimal_valid_config(cli):
    runez.write(
        "sample.yml",
        """
proving-grounds: /work/ripple
downstream-projects:
  - .
""",
        logger=None,
    )
    cli.run("sample.yml")
    assert cli.succeeded
    assert "downstream projects: 1" in cli.logged.stdout
```

## Style

We aim for readability and simplicity over ceremony. A few project preferences
on top of the standard ruff lint rules:

- **No leading `_` by default on module-level names.** Plain `foo` reads
  better than `_foo`. A leading `_` is a real signal — "called only from
  this module / class, not part of the surface anyone else should reach
  for" — so use it when that's genuinely true and worth communicating, but
  don't default to it.
- **Prefer simple containers for small constant collections.** Use a `tuple`
  for a fixed list of (say) ≤ 10 items rather than `frozenset`. Membership
  testing with `if k not in TUPLE` is fine at this scale; the perf
  difference doesn't matter and `tuple` reads plainer. Reach for
  `set`/`frozenset` only when you actually need set semantics on a hot path.
- **Docstrings on every public function and class.** One-line numpy style
  (see `[tool.ruff.lint.pydocstyle] convention = "numpy"`).

## Architecture

See `SPEC.md` for the config format and execution model, and `PLAN.md` for
working progress.

- **`src/ripple_effect/cli.py`** — click CLI entry point. Accepts a YAML
  config file and top-level flags (`--dryrun`, `--verbose`).
- **`src/ripple_effect/config.py`** — `load_config(path) -> Config` parses
  YAML, applies defaults, and produces typed dataclasses (`Config`,
  `UpstreamRef`, `DownstreamProject`). Pure parse + normalize; no external
  calls.

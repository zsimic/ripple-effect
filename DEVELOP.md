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

## Architecture

**`src/ripple_effect/cli.py`** — click CLI entry point. Accepts a YAML config file and
top-level flags (`--dryrun`, `--verbose`).

**Config format** (YAML):

```yaml
location: /tmp/ripple-workspace   # where to clone/cache downstream repos
projects:
  - git+https://github.com/org/project.git@main   # remote ref
  - ~/dev/local-project                           # local folder
```

For each project ripple-effect will:
1. Clone (or `git fetch --reset`) the repo into `location/<name>/`
2. Create a venv, install the project + the library under test in editable mode via `uv`
3. Run `pytest tests/` against that venv
4. Collect and report pass/fail per project

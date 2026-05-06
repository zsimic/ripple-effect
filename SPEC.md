# ripple-effect — Spec

> Know your blast radius before you push.

Test a Python library against its downstream dependent projects — before you tag a release and find out the hard way.

---

## Concept

Given a library **A** and a set of downstream projects **B**, **C**, …, ripple-effect:

1. Resolves and validates each project reference (library + downstream) via `uv-metadata`
2. Clones/updates each downstream project into a local workspace (git URL) or uses it in place (local folder)
3. Builds a venv for each project
4. Injects library **A** in editable mode into that venv
5. Runs the project's test suite
6. Reports pass/fail per project

The inject step is the point of the tool and is not configurable — it always runs
`uv pip install -e <library>` after the venv is prepared.

---

## Invocation

ripple-effect is a multi-command CLI. The config file is resolved in this order:
1. `--config` flag (explicit override)
2. `RIPPLE_CONFIG` env var
3. `ripple-effect.yml` in the current working directory (default)

```bash
# Show the resolved configuration
ripple-effect show
ripple-effect --config ci-config.yml show

# Prepare downstream project environments (clone + venv)
ripple-effect prepare

# Run the full pipeline: prepare → inject → test
ripple-effect run

# Global flags (available on all commands)
ripple-effect --dryrun run         # show what would be done, without doing it
ripple-effect --verbose show       # show more output / debug logging

# Useful in CI — no flags needed when RIPPLE_CONFIG is set
export RIPPLE_CONFIG=ci-config.yml
ripple-effect run
```

---

## Project references

Two forms are accepted for `upstream` and `downstream-projects` entries:

| Form         | Example                                                          | Behaviour                                              |
|--------------|------------------------------------------------------------------|--------------------------------------------------------|
| Local folder | `.` or `~/github/runez` or `/path/to/project`                   | Used as-is, no git operations                          |
| Git URL      | Any URL form accepted by `uv-metadata` (see below)              | Cloned/updated into `proving-grounds/<name>/`          |

PyPI refs (`requests`, `requests<2`), wheels, and sdists are **not** accepted for
`downstream-projects` — ripple-effect needs a `tests/` folder to run against. The
`upstream` field may eventually accept a PyPI spec (e.g. `pedantic==2.5.0rc1`) when
only the inject step is needed, but that is out of scope for v1.

### Validation via `uv-metadata`

Every project reference (`upstream` and each `downstream-projects` entry) is validated early via
[`uv-metadata`](https://github.com/zsimic/uv-metadata):

```bash
uv-metadata <ref>              # full metadata as JSON
uv-metadata <ref> --key name   # just the project name
```

ripple-effect passes the reference as-is to `uv-metadata` and uses the result:
- If `uv-metadata` returns valid metadata — the reference is accepted, whatever form it took
- If `uv-metadata` returns no valid metadata — fail early with a clear error

`uv-metadata` accepts many URL forms (`https://`, `git+https://`, etc.) and normalises them
internally. ripple-effect doesn't need to validate or rewrite URLs — it just hands them off.
The `name` field from the metadata is used to name the workspace subfolder for git repos.

---

## Config format (YAML)

```yaml
# The upstream library under test. Accepts: local folder or git URL.
# Required — ripple-effect will abort with a clear error if missing.
# Future: upstream-libs: [...] will allow multiple upstream libs in one run.
upstream: .

# Where to clone/cache downstream git repos.
# Required when any downstream project is a git URL.
# May use ~ and env vars (expanded at use time, not at parse time).
proving-grounds: /tmp/ripple-proving-grounds

# Optional global defaults, overridable per project.
defaults:
  # How to build the venv. Default: auto-detected (see Three-step model below).
  prepare: auto
  # How to run the tests.
  test: ".venv/bin/pytest tests/"

downstream-projects:
  # Plain string — git URL or local path (detected by leading . ~ or /)
  - https://github.com/codrsquad/portable-python.git@main
  - ~/dev/my-other-project

  # Mapping form — use source-ref: for the location, with optional overrides
  - source-ref: https://github.com/org/project.git@main
    prepare: "hatch env create"         # project uses hatch instead of uv
    test: ".venv/bin/pytest tests/ -x"  # stop on first failure
```

### Project entry forms

A project entry can be a plain string (shorthand) or a mapping with explicit keys:

| Key          | Description                                                                 |
|--------------|-----------------------------------------------------------------------------|
| `source-ref` | Local path or git URL — used as-is (local) or cloned into `proving-grounds/<name>/` |
| `prepare`    | Override the global `defaults.prepare` for this project                     |
| `test`       | Override the global `defaults.test` for this project                        |

Plain string entries are equivalent to `source-ref: <value>`. Local paths are detected by
leading `.`, `~`, or `/`; everything else is treated as a git URL and handed to `uv-metadata`.

---

## Three-step execution model

For each downstream project, ripple-effect runs three steps in order:

```
prepare  →  inject  →  test
```

### Step 1 — prepare

Builds the `.venv/` for the downstream project. Configurable via `defaults.prepare` or
per-project `prepare`. When set to `auto` (the default), ripple-effect detects:

| Condition                  | Command                                                        |
|----------------------------|----------------------------------------------------------------|
| `uv.lock` present          | `uv sync`                                                      |
| `requirements.txt` present | `uv venv && uv pip install -r requirements.txt`                |
| neither                    | error — explicit `prepare` required                            |

Any string is accepted as the prepare command; ripple-effect just runs it and moves on.
This accommodates projects using other venv managers (e.g. `hatch env create`, `poetry install`,
`pipenv install`) without ripple-effect needing to know about them.

### Step 2 — inject (not configurable)

```bash
uv pip install -e <upstream>
```

Injects the upstream library in editable mode into the venv built in step 1, overriding
whatever version was installed (pinned or otherwise).

**Special case — upstream is a local folder:**
Before running inject, ripple-effect checks `uv pip freeze` in the project's venv. If the
upstream is already installed in editable mode pointing at the right folder, inject is
skipped and the venv is reused as-is. If it is pinned/wrong, the venv is recreated from
scratch (prepare re-runs) then inject proceeds.

**Upstream identified by name:** `uv-metadata <upstream> --key name` gives the package name
used to find it in `uv pip freeze` output.

### Step 3 — test

Runs the project's test suite against the prepared+injected venv. Configurable via
`defaults.test` or per-project `test`.

Default: `.venv/bin/pytest tests/`

---

## Known limitation: tox

**tox is intentionally out of scope for v1.**

When tox runs, it creates its own isolated envs from scratch — the `.venv/` that
ripple-effect prepared and injected into is invisible to tox's envs. There is no clean
universal way to inject an editable library into tox environments without file surgery
(editing `requirements.txt`, `pyproject.toml`, or similar).

Workaround for power users: write a thin wrapper script that performs the injection
before calling tox, then point `test:` at that script. ripple-effect doesn't need to
know it's there.

A future version could add first-class tox support with explicit strategies
(e.g. `requirements.txt` surgery + restore, or `[tool.uv.sources]` injection + restore).

---

## CI usage example (GitHub Actions)

```yaml
- name: Run downstream integration tests
  env:
    RIPPLE_CONFIG: ci-config.yml
  run: uvx ripple-effect run
```

With a `ci-config.yml`:

```yaml
upstream: .
proving-grounds: $RUNNER_TEMP/ripple-workspace
downstream-projects:
  - https://github.com/codrsquad/portable-python.git@main
  - https://github.com/codrsquad/pickley.git@main
```

---

## Local iteration example

```yaml
upstream: ~/github/runez
proving-grounds: ~/dev/ripple-workspace

downstream-projects:
  - https://github.com/codrsquad/portable-python.git@main
  - ~/github/pickley        # local checkout, no git pull
  - source-ref: ~/github/some-hatch-project
    prepare: "hatch env create"   # project uses hatch rather than uv
```

---

## v1 scope

- [x] Config parsing (YAML) with `show` command
- [ ] Multi-command CLI: `show`, `prepare`, `run` with `--config` / `RIPPLE_CONFIG` / default `ripple-effect.yml`
- [ ] Project reference validation via `uv-metadata` (fail early on invalid refs)
- [ ] Project cloning/updating (`git clone` / `git fetch --reset`) for git URLs
- [ ] Auto-detection of prepare strategy (`uv.lock` vs `requirements.txt`)
- [ ] Editable-install check (`uv pip freeze`) before deciding to recreate venv
- [ ] `uv pip install -e <upstream>` injection
- [ ] Test runner (`.venv/bin/pytest tests/`)
- [ ] Per-project `prepare` / `test` overrides
- [ ] `--dryrun` mode
- [ ] Pass/fail summary report

Out of scope for v1:
- tox support
- Parallel project execution
- Caching venvs across runs

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

Downstream entries may also be a **bare name** (e.g. `lib-a` or `lib-a@main`),
completed by `source-prefix` into one of the two forms above, see [source-prefix](#source-prefix).

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

# Where to clone/cache git repos, and keep ripple-effect's own files (see tox below).
# Optional, default: build/ripple-check (relative paths are relative to the config file's folder).
# May use ~ and env vars (expanded at use time, not at parse time).
proving-grounds: /tmp/ripple-proving-grounds

# Optional defaults, overridable per group and per project.
# How to build the venv. Default: auto-detected (see Three-step model below).
prepare: auto
# How to run the tests.
test: pytest
# Prepended to bare downstream names (see source-prefix below).
source-prefix: https://github.com/my-org/

# Required: the projects to test the upstream library against.
downstream-projects:
  # Plain string — git URL or local path (detected by leading . ~ or /)
  - https://github.com/codrsquad/portable-python.git@main
  - ~/dev/my-other-project
  - project-b                           # bare name → https://github.com/my-org/project-b

  # Mapping form — use source-ref: for the location, with optional overrides
  - source-ref: https://github.com/org/project.git@main
    prepare: "hatch env create"         # project uses hatch instead of uv
    test: "pytest tests/ -x"            # stop on first failure

  # Group — settings shared by all its sources
  - description: Internal repos using tox, with a typecheck target
    source-prefix: https://git.example.com/corp/
    test: tox -r -e py,typecheck
    sources:
      - lib-a
      - source-ref: lib-b@main  # per-project override still possible
        test:                   # several test commands, run in order
          - pytest
          - tox -re typecheck
```

### Entry forms

A `downstream-projects` entry is one of:
- a **project**: a plain string (shorthand for `source-ref: <value>`), or a mapping with `source-ref`
- a **group**: a mapping with `sources`, a list of projects sharing the group's settings

Groups don't nest: each `sources` item is a project (plain string or `source-ref` mapping).

| Key             | Top level | Group | Project | Description                                                            |
|-----------------|:---------:|:-----:|:-------:|------------------------------------------------------------------------|
| `source-ref`    |           |       | ✓       | Local path, git URL, or bare name                                      |
| `sources`       |           | ✓     |         | Projects in this group (required for a group)                          |
| `description`   |           | ✓     |         | Optional, shown by `show` and as a heading in the run summary          |
| `source-prefix` | ✓         | ✓     |         | Prepended to bare names                                                |
| `prepare`       | ✓         | ✓     | ✓       | How to build the venv                                                  |
| `test`          | ✓         | ✓     | ✓       | A test command, or a list of them, see [Test commands](#test-commands) |

Settings resolve in this order, first one found wins: project, group, top level, built-in
default (`prepare: auto`, `test: pytest`).

Local paths are detected by leading `.`, `~`, or `/`; URLs by `://` or a leading `git@`;
anything else is a bare name.

### Validation

The config is validated as a whole as soon as it's loaded, and all problems found are reported at
once, each pointing at the offending entry:

```
Invalid config ripple.yml:
 - top level: missing 'upstream'
 - downstream-projects[2].sources[0]: missing 'source-ref'
```

`show` displays the config first (missing values in red, as `-missing-`), then the problems, and
exits with code 1: all issues can be fixed in one go. Other commands abort with the problems before
doing anything. Invalid YAML aborts right away (there is no config to show then).

Problems checked:
- invalid YAML, or a key appearing twice in the same mapping (YAML would silently keep the last one)
- unknown keys at any level (besides those in the table above, the top level accepts `upstream`,
  `proving-grounds` and `downstream-projects`): catches typos such as `repos:` for `sources:`,
  or a leftover `defaults:`
- a mapping with both `source-ref` and `sources`, or neither, and groups nested in `sources`
- values of the wrong type: settings must be non-empty strings, `downstream-projects` and
  `sources` non-empty lists, each project a string or a mapping
- a missing `upstream` or `downstream-projects` (there is nothing to test without them)
- a bare name with no `source-prefix` in effect, or a `source-prefix` that is itself a bare name
- the same `source-ref` listed more than once (compared after applying `source-prefix`)
- a `test` command ripple-effect doesn't know how to verify, pytest not stated as `pytest ...`, or
  tox with another first option than `-r` (see [Test commands](#test-commands))

### source-prefix

A bare name is completed by prepending the `source-prefix` in effect (group, else top level).
This is plain concatenation, nothing is added or removed:

| `source-prefix`                  | Entry               | Resolves to                                       |
|----------------------------------|---------------------|---------------------------------------------------|
| `https://git.example.com/corp/`  | `lib-a`             | `https://git.example.com/corp/lib-a`              |
| `https://git.example.com/corp/`  | `lib-a@main`        | `https://git.example.com/corp/lib-a@main`         |
| `~/dev/corp/`                    | `tool-a`            | `~/dev/corp/tool-a` (local folder)                |

- No `.git` suffix is added: git hosts and `uv-metadata` accept URLs without it
- The prefix typically ends with `/`, but doesn't have to (`.../corp/py-` + `lib-a` works too)
- URLs and local paths (`/...`, `~/...`, `.`, `./...`, `../...`) are used as-is, the prefix is not applied
- A bare name with no `source-prefix` in effect is an error, reported early (PyPI names are not accepted)
- `source-prefix` itself must be a URL or a local path
- `show` displays completed names (prefix applied)
- `upstream` is not affected by `source-prefix`

---

## Three-step execution model

For each downstream project, ripple-effect runs three steps in order:

```
prepare  →  inject  →  test
```

### Step 1 — prepare

Builds the `.venv/` for the downstream project, only when one of its test commands uses it (a
pytest command, see [Test commands](#test-commands)): tox builds its own envs. Configurable via
`prepare` (top level, group, or project). When set to `auto` (the default), ripple-effect detects
(first match wins):

| Condition                                                  | Commands                                                                        |
|------------------------------------------------------------|---------------------------------------------------------------------------------|
| `requirements.txt` and/or `tests/requirements.txt` present | `uv venv --clear`, `uv pip install -r` each of them, then `uv pip install -e .` |
| otherwise                                                  | `uv sync` (uses `uv.lock`, creates it if missing)                               |

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

Runs the project's test command(s), verifying that each of them really runs against the upstream
checkout, see [Test commands](#test-commands). Configurable via `test` (top level, group, or
project).

Default: `pytest` (run from `.venv/`, see [Test commands](#test-commands)), which honors the project's
own pytest config (`testpaths` etc.) instead of assuming a `tests/` folder.

Step 2 (inject) also applies only to projects with a pytest command.

---

## Output

Every command ripple-effect runs on the user's behalf (git clone, prepare, inject, upstream wheel
build, test) is printed before it runs (`Running: ...`, or `Would run: ...` with `--dryrun`), so the
output of a run shows exactly what was done. Housekeeping (`git fetch` / `git reset` of existing
clones), internal probes (venv health check, `uv pip freeze`) and other chatter (folder creation
etc.) are debug-level, shown with `--verbose`.

---

## Test commands

`test` is a command, or a list of commands. All of them run, in order, and the project passes when
they all pass. A `test` stated at one level replaces the inherited one as a whole (lists aren't
merged).

ripple-effect only runs test commands it knows how to verify, so that a pass really means "passes
against the upstream checkout". Each command is matched to a handler:

| Handler | Recognized by                                                          | Verification                                                                                    |
|---------|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| pytest  | first word is `pytest`                                                 | before running: pytest and the upstream (editable, from its checkout) are installed in `.venv/` |
| tox     | a `tox` word anywhere (`tox ...`, `uvx tox ...`, `my-wrapper tox ...`) | after running: the recreated `.tox/` envs use the upstream wheel, see [tox](#tox)               |

pytest commands are stated as `pytest ...`, and always run from the project's `.venv/` (the one
ripple-effect prepares and injects into), printed that way: `Running: <project>/.venv/bin/pytest ...`.
One form keeps configs clear: other ways of invoking pytest are config problems pointing to
`pytest ...`, for example:
- `.venv/bin/pytest ...`: redundant, pytest always runs from `.venv/`
- `python -m pytest ...`: only differs by adding the current folder to `sys.path`, which doesn't
  matter here, as projects are installed in their `.venv/`
- `uv run pytest ...`: `uv run` syncs `.venv/` with the project's lock file first, which replaces the
  injected upstream with its locked version (verified: the editable upstream became `runez==5.10.2`),
  tests would then pass or fail against the published upstream

These are config problems (see Validation):
- a command no handler recognizes (e.g. `hatch run test`): "not supported yet", with an invitation
  to contribute a handler able to verify it
- pytest invoked any other way than `pytest ...` (see above): what extra options such as
  `uv run --extra foo` install belongs in `prepare` (e.g. `prepare: uv sync --extra foo`)
- a tox command whose first option doesn't start with `-r` or `--recreate`: only simple forms are
  recognized (`tox -r -e py`, `tox -re py`, `tox -rv -e py`, `tox --recreate -e py`), so that
  ripple-effect doesn't depend on how tox parses its other options (`tox -vre py`, or a `-r` passed
  after `--` to the tests, are problems)

A failed verification fails the project, stating why, even if the command itself succeeded. When a
project has several test commands, the run summary shows each command's outcome.

### tox

When the test command uses tox, tox builds its own envs from scratch (in `.tox/`) and installs
the upstream's published version: the `.venv/` injected in step 2 is not used, and a passing
run says nothing about the upstream checkout.

tox-based test commands (the usual way projects run their type checkers) exercise the upstream
checkout too, via uv's `UV_OVERRIDE`.

1. **Upstream wheel**: during prepare (by `prepare` and `run`), when there is a tox test command,
   build a wheel of the upstream checkout with `uv build --wheel -o <proving-grounds>/.ripple/upstream
   <upstream-folder>` (that folder is cleared first), and write `<proving-grounds>/.ripple/overrides.txt`
   containing `<upstream-name> @ file://<wheel>`.
2. **Override**: run tox test commands with `UV_OVERRIDE` pointing to that file, printed (with
   absolute paths) on its own line before the usual `Running: ...` line, as runez doesn't show env
   vars. Both files are kept after the run, so a failure can be reproduced by hand (from the project's
   folder). An existing `UV_OVERRIDE` in the environment is kept: uv accepts a space-separated list of
   files (verified), ripple-effect's file goes first.
3. **Verify**: after a tox test command, inspect each env under the project's `.tox/` recreated by the
   run (its `pyvenv.cfg` is new, or changed), excluding tox's internal envs (`.pkg` etc.). Where the
   upstream was installed from is read from its `*.dist-info/direct_url.json` (PEP 610, what
   `uv pip freeze` uses to show `<name> @ <url>`), no such file means it came from an index. An env
   with the upstream installed from anywhere else than the wheel (e.g. `runez 5.10.2` from PyPI) fails
   the project, stating why. Envs without the upstream (e.g. a `style` env with `skip_install`) are
   fine. Finding no recreated env at all also fails the project (couldn't verify, e.g. tox configured
   with a custom work dir).

Why a wheel: uv caches builds of local folders, and rebuilds them only when `pyproject.toml`,
`setup.py` or `setup.cfg` change. Overriding with the upstream folder itself
(`<upstream-name> @ file://<upstream-folder>`) can therefore install a stale build (verified: an
edit to the upstream source didn't make it into a `tox -r` env). A wheel built fresh each run can't
be stale.

Overrides apply to the whole resolution: transitive dependencies (another library depending on the
upstream) get the upstream checkout too, and version pins on the upstream are ignored.

**Supported**: tox with [tox-uv](https://github.com/tox-dev/tox-uv)'s default runner (verified),
including tox wrappers built on it. Others (pip-based tox, tox-uv's `uv-venv-lock-runner`, which
installs via `uv sync`) are expected to ignore `UV_OVERRIDE`: step 3 fails them rather than letting
them pass against the published upstream.

**Convention**: tox test commands start with `-r` (e.g. `tox -re py,typecheck`), a config without
it has a problem (see Validation). tox otherwise reuses an existing env as-is (its deps
didn't change from tox's point of view), and an existing `.tox/` keeps the published upstream.
ripple-effect doesn't clean up `.tox/` (or any other tool's envs) itself: that would be intrusive
for local checkouts, and wouldn't stop at tox (hatch etc.). For local checkouts, the developer's own
`.tox/` envs keep the upstream build afterwards (as `.venv/` already does after inject).

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
source-prefix: ~/github/

downstream-projects:
  - https://github.com/codrsquad/portable-python.git@main
  - pickley                 # local checkout ~/github/pickley, no git pull
  - source-ref: some-hatch-project
    prepare: "hatch env create"   # project uses hatch rather than uv
```

---

## v1 scope

- [x] Config parsing (YAML) with `show` command
- [x] Multi-command CLI: `show`, `prepare`, `run` with `--config` / `RIPPLE_CONFIG` / default `ripple-effect.yml`
- [ ] Project reference validation via `uv-metadata` (fail early on invalid refs)
- [ ] Project cloning/updating (`git clone` / `git fetch --reset`) for git URLs
- [x] Auto-detection of prepare strategy (`requirements.txt` vs `uv sync`)
- [ ] Editable-install check (`uv pip freeze`) before deciding to recreate venv
- [ ] `uv pip install -e <upstream>` injection
- [x] Test runner (`.venv/bin/pytest tests/`, default becomes `pytest` with test commands below)
- [ ] Per-project `prepare` / `test` overrides
- [ ] `--dryrun` mode
- [x] Pass/fail summary report
- [x] Top-level `prepare` / `test` (replacing `defaults:`)
- [x] Groups (`sources:`, with optional `description`)
- [x] `source-prefix` for bare names
- [x] Print every command run on the user's behalf
- [x] Test commands: one or several, each verified to run against the upstream checkout
- [x] tox support via `UV_OVERRIDE`

Out of scope for v1:
- Parallel project execution
- Caching venvs across runs

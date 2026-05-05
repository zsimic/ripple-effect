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

```bash
uvx ripple-effect config.yml          # build venvs and run tests as described in config.yml
ripple-effect config.yml              # same, if installed globally
ripple-effect --dryrun config.yml     # show what would be done, without doing it
ripple-effect --verbose config.yml    # show more output
```

---

## Project references

Only two forms are accepted — for both `upstream` and `downstream-projects` entries:

| Form         | Example                                                          | Behaviour                                              |
|--------------|------------------------------------------------------------------|--------------------------------------------------------|
| Local folder | `.` or `~/github/runez` or `/path/to/project`                   | Used as-is, no git operations                          |
| Git URL      | Any URL form accepted by `uv-metadata` (see below)              | Cloned/updated into `proving-grounds/<name>/`          |

PyPI refs (`requests`, `requests<2`), wheels, and sdists are **not** accepted — ripple-effect
needs a `tests/` folder to run against, which only local folders and git repos can provide.

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
# Default: current working directory (.).
# Future: upstream-libs: [...] will allow multiple upstream libs in one run.
upstream: .

# Where to clone/cache downstream git repos.
# May use ~ and env vars. Subfolders are named after each project's name (from uv-metadata).
proving-grounds: /tmp/ripple-proving-grounds

# Optional global defaults, overridable per project.
defaults:
  # How to build the venv. Default: auto-detected (see Three-step model below).
  prepare: auto
  # How to run the tests.
  test: ".venv/bin/pytest tests/"

downstream-projects:
  # Git URL (any form accepted by uv-metadata) — cloned/updated into proving-grounds/<name>/
  - https://github.com/codrsquad/portable-python.git@main
  - git+https://github.com/codrsquad/pickley.git@main

  # Local folder — used as-is, no git operations
  - ~/dev/my-other-project

  # Per-project overrides (mapping form)
  - url: https://github.com/org/project.git@main
    prepare: "hatch env create"         # project uses hatch instead of uv
    test: ".venv/bin/pytest tests/ -x"  # stop on first failure
```

### Project entry forms

A project entry can be a plain string (shorthand) or a mapping with explicit keys:

| Key       | Description                                                                 |
|-----------|-----------------------------------------------------------------------------|
| `url`     | Any URL form accepted by `uv-metadata` — cloned/updated into `proving-grounds/<name>/` |
| `folder`  | Local path — used as-is, no git operations                                  |
| `prepare` | Override the global `defaults.prepare` for this project                     |
| `test`    | Override the global `defaults.test` for this project                        |

Plain string entries are tried against `uv-metadata` first; if that succeeds and the ref
is not a local path, it is treated as a `url`. Local paths (`.`, `~`, `/`, or existing
directories) are treated as `folder` without calling out to `uv-metadata`.

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
  run: uvx ripple-effect ci-config.yml
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
  - folder: ~/github/some-hatch-project
    prepare: "hatch env create"   # project uses hatch rather than uv
```

---

## v1 scope

- [ ] Config parsing (YAML)
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

# ripple-effect — Plan

Working plan and progress for v1. `SPEC.md` is the source of truth for *what*
we're building; this file tracks *how* and *in what order*, and we update it
as we go.

## Steps

- [x] **1. Config parsing** — load YAML, normalize, fail early on shape errors
  (no external calls yet). Produced `src/ripple_effect/config.py`.

- [x] **2. Tox config extraction** — moved tox / coverage / pytest config from
  `pyproject.toml` to `tox.ini`.

- [ ] **3. uv-metadata integration** — call `uv_metadata.get_metadata_from_pip_spec`
  for each project ref to validate it and extract its `name`. Reject PyPI
  refs / wheels / sdists per SPEC. Add a resolved-project layer carrying per-
  project `name` and (for URLs) target clone path.

- [ ] **4. Workspace prep** — for URL projects, `git clone` (or `git fetch --reset`)
  into `proving-grounds/<name>/`. For local projects, sanity-check the folder.

- [ ] **5. Prepare step** — auto-detect `uv.lock` vs `requirements.txt`; run
  the configured prepare command (or the `auto` default).

- [ ] **6. Inject step** — editable-install check via `uv pip freeze`; run
  `uv pip install -e <upstream>`. Special case: if upstream is a local folder
  already installed editable, reuse the venv; if pinned/wrong, recreate it.

- [ ] **7. Test step** — run each project's test command; capture pass/fail.

- [ ] **8. Summary report** — pass/fail per project; exit code reflects overall.

- [ ] **9. Polish** — refine `--verbose` output; tidy error messages and exit
  codes; sweep for missing test coverage and add high-level CLI cases.

## Deferred (out of v1 scope per SPEC)

- tox support for downstream projects (workaround documented in SPEC).
- Parallel project execution.
- Caching venvs across runs.
- Multiple upstream libraries (`upstream-libs: [...]`).

## Cross-cutting concerns

- **`--dryrun`** — thread it through each step as we build that step, not at
  the end. Every new operation should be dry-run-able from day one.
- **`uv-metadata` dependency** — currently a separate repo at
  `~/github/uv-metadata`. Decide how to consume it (PyPI release, git+,
  local-path-dev install) when implementing step 3. We may also need to
  fine-tune its API (it currently calls `sys.exit` on failure; we want
  exceptions for library use).
- **Test coverage** — high-level CLI tests via the runez `cli` fixture. Near
  the end, use `tox` coverage output to spot untested code paths and add
  high-level cases to reach them, instead of writing narrow unit tests
  up-front. See `DEVELOP.md` for testing style.

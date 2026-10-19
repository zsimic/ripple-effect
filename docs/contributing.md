# Contributing

`tox.ini` is the hub: every check is a tox env, and `.github/workflows/` only calls them. Plain
`tox` runs the tests, coverage, style, five type checkers and the README check. `tox -e reformat`
fixes formatting. `tox -e basedpyright` exists but isn't gated (it reports many warnings).

`.venv/bin/pytest` works too, after a `uv sync`.

## Tests

- Default to high-level CLI tests through the `cli` fixture from `runez.conftest`
  (`cli.run(...)`, then `cli.succeeded` / `cli.failed` / `cli.logged`). It creates and `cd`s into a
  temp folder per test, so write files with relative paths. Don't pair it with `temp_folder`.
- Mock only what's external and slow: `uv_metadata.get_metadata_from_pip_spec` (a lambda returning
  the folder name as package name is enough), and the inject step when there's no real venv.
- External programs are faked with small shell scripts (`fake_program()` in `tests/test_cli.py`):
  a fake `pytest` in `.venv/bin/` (installed by a fake `prepare`, since an unhealthy `.venv/` gets
  wiped), fake `tox` scripts that create `.tox/` envs with or without honoring `UV_OVERRIDE`.
- Real tiny projects are cheap: `tiny_project()` builds offline in ~20ms, `editable_venv()` gives a
  real `.venv/` with editable installs in ~70ms. Prefer them to mocking `uv`, see
  `test_dryrun_existing_setups`: `--dryrun` still runs the read-only probes for real.
- `tests/samples/*.yml` are configs showing each feature and each kind of config problem (most in
  `bad-config.yml`), handy as `ripple-effect -c tests/samples/groups.yml show`. `test_samples`
  compares their `show` output with the `.txt` next to them: after a change in output, run
  `tests/regenerate-expected.sh` and review the `git diff`.
- Pick output apart with `extract_section()` (see [Output](./pipeline.md#output)), rather than
  partitioning on decorations that are free to change.
- Use coverage to find untested branches near the end of a change, not to drive tests up front.

## Style

- No leading `_` on module-level names by default; use it only when "private to this module" is
  worth communicating.
- Small constant collections are tuples (see the `*_KEYS` constants in `model.py`).
- A one-line docstring on every public function and class.
- Lean on runez: `runez.run()` and file helpers are dryrun-aware, so every operation honors
  `--dryrun` without extra code.
- `ripple-effect.yml` at the repo root tests runez against this repo and portable-python; it's also
  what `test_default_config` copies.

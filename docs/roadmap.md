# Roadmap

## Known gaps

- **PyPI names, wheels and sdists aren't rejected** as downstream refs: ripple-effect needs a
  checkout to run tests in, but such a ref only fails later. Bare names without a `source-prefix`
  are rejected, which covers the common case.
- **A local downstream folder isn't sanity-checked** before use (it fails on first use instead).
- **A changed `source-ref` for a URL checkout isn't detected**: moving from `foo.git` to
  `foo.git@main` does a `fetch` + `reset` of the existing clone, which stays on its old branch. A
  possible fix: store the `source-ref` next to each clone, and re-clone when it changes.
- **A pinned (non-editable) upstream in `.venv/` is installed over**, rather than the venv being
  recreated from scratch.
- `upstream` only accepts a local folder or git URL; a PyPI spec (e.g. `foo==2.5.0rc1`) could make
  sense later, when only the inject step is needed.

## Ideas

- **A manifest per tested project**, recording what a run tested: the source (`source-ref`), the
  git sha it was tested at (upstream's too), and the prepare and test commands that ran. A YAML file,
  either `<proving-grounds>/<name>.manifest.yml` (next to the clone, easy to spot) or
  `.ripple/<name>.manifest.yml` (with ripple-effect's other files, keeping proving-grounds to one
  folder per project). It would make a CI result reproducible, and could fix the changed
  `source-ref` gap above.

## Out of scope for now

- Running projects in parallel.
- Several upstream libraries in one run.
- Test runners other than pytest and tox (hatch, nox, `uv run`...): a new one needs a handler able
  to verify it, see [Test commands](./test-commands.md).

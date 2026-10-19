# tox

tox builds its own envs and installs the upstream from the index, so the injected `.venv/` is
irrelevant to it. ripple-effect forces an upstream wheel into tox's envs through uv, then checks
that it worked.

1. **Wheel**: during prepare, `UpstreamLocalized.wheel` runs `uv build --wheel` into
   `<proving-grounds>/.ripple/upstream/` (cleared first), and `overrides_file` writes
   `<proving-grounds>/.ripple/overrides.txt` with `<name> @ file://<wheel>`. Both are kept, so a
   failing tox run can be reproduced by hand.
2. **Override**: `RunWithTox.run()` sets `UV_OVERRIDE`, printed on its own line since runez doesn't
   show env vars. Overrides apply to transitive dependencies too, and ignore version pins.
3. **Verify**: every `.tox/` env recreated by the run (its `pyvenv.cfg` changed, internal `.pkg`
   etc. excluded) must have the upstream from the wheel, or not at all (a `style` env). Where it
   came from is read from `*.dist-info/direct_url.json` (`installed_from()`): what `uv pip freeze`
   uses, without a subprocess per env. No recreated env at all also fails ("couldn't verify").

## Why it's done this way

- **A wheel, not the upstream folder.** uv caches builds of local folders and rebuilds only when
  `pyproject.toml`/`setup.py`/`setup.cfg` change: with a folder override, an edit to the upstream
  source didn't make it into a `tox -r` env. A wheel built fresh each run can't be stale.
- **Only tox-uv's default runner is verified to work** (it installs via `uv pip`). pip-based tox,
  and likely tox-uv's `uv-venv-lock-runner` (installs via `uv sync`), ignore `UV_OVERRIDE` and would
  test the published upstream: step 3 is what catches them instead of letting them pass.
- **An existing `UV_OVERRIDE` is kept.** uv takes a space-separated list of files and applies all of
  them at once (no precedence: conflicting entries for one package just can't be satisfied), so
  order doesn't matter.
- **The wheel build writes into the upstream checkout** (`build/`, `*.egg-info` with setuptools),
  normally git-ignored, but that's the user's own checkout when `upstream` is a local folder.

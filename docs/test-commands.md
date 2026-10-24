# Test commands

Each command in `test` gets a handler, a subclass of `RunWith`: `RunWith.handler_for()` picks it,
its `problem()` is reported as a config problem at load time, and `run()` runs it and returns why it
failed (or `None`). A command no other handler recognizes gets `RunWithNotSupported`, whose
`problem()` is always set: ripple-effect would rather refuse than report a pass it can't vouch for.

## pytest (`RunWithPytest`)

- Only the plain form `pytest ...` is accepted, and it always runs `<project>/.venv/bin/pytest`.
  One form keeps configs clear, and `.venv/` is the only venv ripple-effect prepares and injects
  into, so supporting others would add nothing.
- It runs with that `.venv/` activated (`VirtualEnv.activated_env`), so tests that run `python` or
  a console script get the project's venv. ripple-effect's own venv is deliberately not put on
  `PATH` (unlike `uvx`, which prepends its tool env): it would leak into downstream commands.
- `uv run pytest` is rejected with a specific message: `uv run` syncs `.venv/` with the lock file
  first, which silently replaced the injected editable upstream with its locked version
  (`runez==5.10.2`) when tried. `python -m pytest` only differs by putting the current folder on
  `sys.path`, irrelevant since projects are installed in their `.venv/`.
- Verified **before** running: pytest is in `.venv/`, and the upstream is installed editable there.

## tox (`RunWithTox`)

- Recognized by a `tox` word anywhere, so wrappers work (`uvx tox ...`, `my-wrapper tox ...`).
- tox's first option must start with `-r` or `--recreate`, otherwise existing envs keep the
  published upstream. Deliberately that simple: parsing tox's option clusters (`-vre`) or posargs
  would tie ripple-effect to how tox parses its options.
- Verified **after** running, see [tox](./tox.md).

## Adding a handler

Subclass `RunWith`, recognize it in `handler_for()`, add `problem()` for config-time checks,
and make `run()` verify that the upstream checkout is what got tested. Set `needs_venv` (a
`.venv/` is prepared and injected) or `needs_upstream_wheel` (the wheel is built) as needed.

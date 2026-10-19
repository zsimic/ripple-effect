# Changelog

## v1.1.0

- **Breaking**: test commands are verified to really run against the upstream checkout, others are
  rejected. Supported: `pytest ...` (run from the project's `.venv/`) and `tox -r ...`. The default
  is now `pytest` (was `.venv/bin/pytest tests/`, now rejected: state it as `pytest tests/`)
- **Breaking**: `prepare` and `test` are top-level settings, `defaults:` is gone
- **Breaking**: the config is validated up front: unknown keys, duplicate keys, wrong types... are
  errors, all reported at once with their location (`show` lists them after the config)
- tox support: a wheel of the upstream is forced into tox's envs via `UV_OVERRIDE` (needs tox-uv),
  and the recreated envs are checked
- `test` accepts a list of commands
- Groups of downstream projects sharing settings, and `source-prefix` to list repos by name
- `proving-grounds` defaults to `build/ripple-check`
- `prepare --clean` and `run --clean` start from an empty proving-grounds folder (as on CI)
- Output is split into `## Preparation`, `## Testing`, `## Outcome` sections (`## Config` for
  `show`, `## Errors` on stderr), with a `### <project>` sub-section per project
- Every command run on your behalf is shown, the run summary states why a project failed
- Works with projects where tox left a `.venv` redirect file (recent tox versions): a `.venv`
  without a working python is rebuilt

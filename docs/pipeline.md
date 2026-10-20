# Pipeline

`prepare` gets every project ready, `run` is `prepare` followed by the test commands and the
summary. Entry points: `RippleSpec.prepare()` and `RippleSpec.run()`.

## Prepare

`--clean` (on `prepare` and `run`) empties proving-grounds first, like a CI run would see it. It
refuses when proving-grounds holds the config file or a local project: `proving-grounds: .` would
otherwise wipe the repo.

1. **Upstream**: cloned into proving-grounds if it's a URL, used in place if local. When any
   project has a tox command, its wheel is built here too, see [tox](./tox.md).
2. **Each downstream**: cloned (or `git fetch` + `git reset --hard FETCH_HEAD`) if it's a URL. The
   checkout folder is named after the package name from uv-metadata, not the repo name.
3. **`.venv/`, only if a test command runs from it** (`DownstreamLocalized.needs_venv`, i.e. a
   pytest command; tox uses its own envs). A venv with a working python is reused. Otherwise
   whatever is at `.venv` is replaced by an empty folder first: recent tox versions write a PEP 832
   `.venv` *file* pointing into `.tox/`, which uv refuses to build a venv over (and doesn't follow).
   `prepare: auto` uses requirements files if present, else `uv sync`.
4. **Inject**: `uv pip install -e <upstream>` into that `.venv/`, skipped when `uv pip freeze`
   already shows the exact editable line (exact, because a downstream cloned under the upstream
   folder has an editable line that starts with the upstream path).

## Run

All test commands of a project run, even after one fails, each producing an `Outcome`. The summary
nests projects under their group description, lists each command when a project has several,
and exits with code 1 if anything failed.

## Output

Output is split into `## <Section>` headings, so CI logs and agents can pick out the part they need
(tests do too, with `extract_section()`): `## Config` (`show`), `## Preparation`, `## Testing`,
`## Outcome`, and `## Errors` (on stderr: config problems, or `--clean` refusing to clean). Preparation and Testing have a
`### <package name>` sub-section per project. The headings are the interface, keep them stable;
what's inside a section is free to change.

`run` also records its full output in `<proving-grounds>/last-run.log` (not in dryrun mode): stdout
and stderr in the order they were written, including the passed-through output of test commands
and log chatter, uncolored. `OutputRecorder` tees `sys.stdout`/`sys.stderr` (and adds a log handler,
runez's console handler holds on to its own stream). The file gets opened only after `--clean`
emptied proving-grounds, what was written before is held until then.

The rule: **`logged_run()`** for commands run on the user's behalf (clone, prepare, inject, wheel
build, tests), shown as `Running: ...`; **`quiet_run()`** for housekeeping and probes
(`git fetch`/`reset`, `uv pip freeze`), shown only with `--verbose`. Both show a program stated by
name as such (`uv`, not its full path). The venv health check uses `logger=None`: on a first run it
would show a confusing "python is not executable" error.

Two settings in `cli.main()` matter here: `AbortException = SystemExit` (otherwise
`protected_main` logs every abort from runez a second time, e.g. a failed clone), and line-buffered stdout (otherwise, when piped
to CI or an agent, `print()` output ends up out of order with log lines on stderr).

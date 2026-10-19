# Config

The user-facing format is in the [README](../README.rst). This page is about how `RippleSpec`
turns the YAML into projects.

## Loading and validation

`RippleSpec.__init__` validates the whole file before anything runs, and **collects** problems in
`self.problems` instead of stopping at the first one. Each problem is prefixed with where it is
(`top level`, `downstream-projects[2].sources[0]`), so a config with several mistakes can be fixed
in one go. `abort_if_invalid()` lists them all in an `## Errors` section (on stderr) and exits with
code 1: `cli.main()` calls it for every command except `show`, which prints the config first
(missing values in red).

- `checked_mapping()` is the single place that checks keys and value types, and returns only the
  valid keys, so the rest of the parsing can assume well-typed values.
- Allowed keys per level are the `*_KEYS` tuples in `model.py`. `test` is the one key that takes a
  string or a list, and each command is checked by `RunWith.problem_with()`, see
  [Test commands](./test-commands.md).
- YAML errors and duplicate keys abort right away (there's nothing to show). Duplicate keys need
  `UniqueKeyLoader`, because PyYAML silently keeps the last one.
- `upstream` and `downstream-projects` are required, `proving-grounds` defaults to
  `build/ripple-check`, relative to the config file's folder like every relative path.

## Settings and groups

- Each `downstream-projects` entry becomes a `DownstreamGroup`; a lone project is a group without
  description, which keeps `show` and the run summary uniform.
- `ProjectSettings` carries `prepare`, `test` and `source_prefix`, layered with `overridden()`:
  built-in default, then top level, then group, then project. A `test` list replaces the inherited
  one, it isn't merged.
- `source-prefix` completes **bare names** only (`is_bare_name()`: neither a URL nor a local path),
  by plain concatenation: no `.git` added (git hosts and uv-metadata don't need it), and a local
  prefix like `~/dev/` works too. `upstream` never gets a prefix.
- Duplicate projects are detected after prefixing, on the final `source-ref`.

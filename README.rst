ripple-effect
=============

Know your blast radius before you push.

.. image:: https://img.shields.io/pypi/v/ripple-effect.svg
    :target: https://pypi.org/project/ripple-effect/
    :alt: Version on pypi

.. image:: https://github.com/zsimic/ripple-effect/workflows/Tests/badge.svg
    :target: https://github.com/zsimic/ripple-effect/actions
    :alt: Tested with Github Actions

.. image:: https://img.shields.io/pypi/pyversions/ripple-effect.svg
    :target: https://github.com/zsimic/ripple-effect
    :alt: Python versions tested


Test a Python library against the downstream projects that depend on it —
before you tag a release and find out the hard way.

Installation
------------

.. code-block:: bash

    pip install ripple-effect
    # or, without installing:
    uvx ripple-effect show

Usage
-----

Create a ``ripple-effect.yml`` config file in your project root (this is the
default config file name, so no ``--config`` flag needed):

.. code-block:: yaml

    # ripple-effect.yml
    upstream: .                          # the library under test (current folder)
    proving-grounds: ./build/ripple      # where to clone git repos (default: build/ripple-check)

    downstream-projects:
      - https://github.com/example/project-b.git@main
      - https://github.com/example/project-c.git@main

Then:

.. code-block:: bash

    ripple-effect show     # preview resolved config
    ripple-effect prepare  # clone repos, build venvs, inject your library
    ripple-effect run      # prepare + run all test commands, report results
    ripple-effect run --clean  # same, from an empty proving-grounds (as on CI)

ripple-effect will:

1. Clone (or update) each downstream project into ``proving-grounds``
2. Create a venv for each using ``uv sync`` or ``requirements.txt`` (for ``pytest`` test commands)
3. Inject your library in editable mode (``uv pip install -e .``)
4. Run each project's test commands: ``pytest ...`` from that venv, ``tox -r ...`` with a wheel of
   your library forced in its envs (via ``UV_OVERRIDE``), verifying they really used your library
5. Report pass / fail per project with timing
6. Record the full output of the run in ``<proving-grounds>/last-run.log``

Real example — this repo's own ``ripple-effect.yml``:

.. code-block:: yaml

    upstream: https://github.com/codrsquad/runez.git@main
    proving-grounds: ./build/verify-runez
    downstream-projects:
      - https://github.com/zsimic/ripple-effect.git
      - source-ref: https://github.com/codrsquad/portable-python.git
        test: tox -re py,mypy,pyrefly,pyright,ty,zuban

.. code-block:: bash

    $ ripple-effect run --clean
    ## Preparation
    Cleaned 4 files from ~/github/ripple-effect/build/verify-runez
    upstream: runez @ ~/github/ripple-effect/build/verify-runez/runez
    Running: git clone https://github.com/codrsquad/runez.git --branch main ~/github/ripple-effect/build/verify-runez/runez
    Running: uv build --wheel -o ~/github/ripple-effect/build/verify-runez/.ripple/upstream ~/github/ripple-effect/build/verify-runez/runez
    ...
    uv overrides for tox runs: ~/github/ripple-effect/build/verify-runez/.ripple/overrides.txt

    ### ripple-effect
    folder: ~/github/ripple-effect/build/verify-runez/ripple-effect
    Running: git clone https://github.com/zsimic/ripple-effect.git ~/github/ripple-effect/build/verify-runez/ripple-effect
    Running: uv sync
    ...
    injecting runez (editable)
    Running: uv pip install -e ~/github/ripple-effect/build/verify-runez/runez

    ### portable-python
    folder: ~/github/ripple-effect/build/verify-runez/portable-python
    Running: git clone https://github.com/codrsquad/portable-python.git ~/github/ripple-effect/build/verify-runez/portable-python

    ## Testing

    ### ripple-effect
    Running: ~/github/ripple-effect/build/verify-runez/ripple-effect/.venv/bin/pytest
    ... 4 passed in 3.8s ...

    ### portable-python
    UV_OVERRIDE=~/github/ripple-effect/build/verify-runez/.ripple/overrides.txt
    Running: tox -re py,mypy,pyrefly,pyright,ty,zuban
    ...
      congratulations :) (19.8 seconds)

    ## Outcome
    ripple-effect: PASSED (4.4s)
    portable-python: PASSED (19.9s)

Output is split into ``## Preparation``, ``## Testing`` and ``## Outcome`` sections (``show`` prints
``## Config``), with a ``### <project>`` sub-section per project. Config problems (and other errors
found before running anything) are listed in an ``## Errors`` section on stderr. Handy to pick out the part you need from a CI log.

Global flags
------------

.. code-block:: bash

    ripple-effect --dryrun run      # show what would happen without doing it
    ripple-effect --verbose run     # show debug output
    ripple-effect -c other.yml run  # use a different config file

The config file is resolved in this order:

1. ``--config`` / ``-c`` flag
2. ``RIPPLE_CONFIG`` environment variable
3. ``ripple-effect.yml`` in the current working directory

Local iteration
---------------

Mix local checkouts with remote repos freely:

.. code-block:: yaml

    upstream: ~/github/mylib
    proving-grounds: ~/dev/ripple-workspace

    downstream-projects:
      - https://github.com/example/project-b.git@main
      - ~/dev/project-c               # local checkout, no git operations
      - source-ref: https://github.com/example/project-d.git@main
        prepare: "uv sync --all-extras"   # custom way to build its .venv/
        test: "pytest tests/ -x"

Git URLs are cloned into ``proving-grounds``, nothing outside of it is touched. Local folders are
used in place though: their ``.venv/`` gets your library injected (editable install), or is rebuilt
if it has no working python, and ``tox -r`` recreates their ``.tox/`` envs with a wheel of your
library. Handy for quick iterations, but remember to recreate those envs (``uv sync``, ``tox -r``...)
once done.

Many downstream projects
------------------------

Group projects that share settings, and use ``source-prefix`` to list repos by name:

.. code-block:: yaml

    upstream: ~/github/mylib
    proving-grounds: ~/dev/ripple-workspace
    source-prefix: https://github.com/example/   # applies to bare names below
    test: tox -r -e py                           # default test command

    downstream-projects:
      - project-b                                # https://github.com/example/project-b
      - description: Repos with a typecheck tox env
        test: tox -r -e py,typecheck
        sources: [project-c, project-d, project-e@main]
      - description: Repos not using tox
        test: pytest
        source-prefix: https://git.example.com/corp/
        sources: [lib-a, lib-b]

Config reference
----------------

======================= ========= ===== ======= ==========================================================
Key                     Top level Group Project
======================= ========= ===== ======= ==========================================================
``upstream``            required                Library under test: local folder or git URL
``proving-grounds``     ✓                       Where to clone git repos (default: ``build/ripple-check``)
``downstream-projects`` required                Projects (and groups) to test
``source-ref``                          ✓       Local path, git URL, or bare name
``sources``                       ✓             Projects of a group (makes an entry a group)
``description``                   ✓             Shown by ``show`` and in the run summary
``source-prefix``       ✓         ✓             Prepended to bare names
``prepare``             ✓         ✓     ✓       How to build ``.venv/`` (default: ``auto``, uses ``uv``)
``python``              ✓         ✓     ✓       Python of ``.venv/`` with ``prepare: auto`` (see below)
``test``                ✓         ✓     ✓       Test command(s) (default ``pytest``)
======================= ========= ===== ======= ==========================================================

- Settings resolve per project first, then group, then top level. Relative paths are relative to
  the config file's folder, ``~`` and env vars are expanded.
- A project is a plain string (shorthand for ``source-ref: ...``) or a mapping; groups don't nest.
- ``source-prefix`` is prepended as-is (nothing added) to **bare names**: refs that are neither a
  URL (``://``, ``git@``) nor a local path (starting with ``.``, ``~`` or ``/``). It can be a local
  folder too (``source-prefix: ~/dev/``). A bare name without a prefix is an error.
- ``prepare: auto`` uses ``requirements.txt`` / ``tests/requirements.txt`` if present
  (``uv venv`` + ``uv pip install -r`` + the project itself), and ``uv sync`` otherwise. A
  ``.venv/`` is built only for projects with a ``pytest`` test command.
- ``python`` is passed as-is to uv's ``--python`` (a version like ``"3.13"``, quoted, or a path).
  Without it, ``prepare: auto`` uses the project's ``.python-version`` if it has one, and the python
  running ripple-effect otherwise (never just the first ``python3`` on ``PATH``).
- The whole config is validated up front: unknown keys, wrong value types, missing required keys,
  unsupported test commands, duplicate projects... are all reported at once, each with its
  location (e.g. ``downstream-projects[2].sources[0]``). ``show`` displays the config first, then
  the problems.

Test commands
-------------

``test`` is a command, or a list of commands (all of them run, the project passes when they all
pass). Default: ``pytest``.

.. code-block:: yaml

    test:
      - pytest tests/ -x
      - tox -re typecheck

ripple-effect only runs test commands it can verify really test your library, so that a pass
means something:

- ``pytest ...``: runs from the project's ``.venv/``, activated (``VIRTUAL_ENV`` set, its ``bin/``
  first on ``PATH``), after checking that pytest and your library (editable) are installed there. Other ways of invoking pytest (``.venv/bin/pytest``,
  ``python -m pytest``, ``uv run pytest``) are rejected: state them as ``pytest ...``
  (``uv run`` would re-sync ``.venv/``, replacing your library with its published version).
- ``tox ...`` (also via a wrapper: ``uvx tox ...``, ``my-wrapper tox ...``): its first option must
  be ``-r`` / ``--recreate`` (``tox -re py``, ``tox -r -e py``). A wheel of your library is built
  once per run, and forced into tox's envs via ``UV_OVERRIDE`` (requires
  `tox-uv <https://github.com/tox-dev/tox-uv>`_). Afterwards, the recreated ``.tox/`` envs are
  checked: an env that got your library from anywhere else (e.g. from PyPI) fails the project.
- Anything else (e.g. ``hatch run test``) is reported as not supported yet, contributions welcome.

Projects with only tox test commands don't get a ``.venv/`` built (tox uses its own envs).

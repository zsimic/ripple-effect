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
    proving-grounds: ./build/ripple      # where to clone downstream git repos

    downstream-projects:
      - https://github.com/example/project-b.git@main
      - https://github.com/example/project-c.git@main

Then:

.. code-block:: bash

    ripple-effect show     # preview resolved config
    ripple-effect prepare  # clone repos, build venvs, inject your library
    ripple-effect run      # prepare + run all test suites, report results

ripple-effect will:

1. Clone (or update) each downstream project into ``proving-grounds``
2. Create a venv for each using ``uv sync`` or ``requirements.txt``
3. Inject your library in editable mode (``uv pip install -e .``)
4. Run each project's test suite
5. Report pass / fail per project with timing

Real example — this repo's own ``ripple-effect.yml``:

.. code-block:: yaml

    upstream: https://github.com/codrsquad/runez.git@main
    proving-grounds: ./build/verify-runez
    downstream-projects:
      - https://github.com/zsimic/ripple-effect.git
      - https://github.com/codrsquad/portable-python.git

.. code-block:: bash

    $ ripple-effect run
    upstream: runez @ ~/github/ripple-effect/build/verify-runez/runez

    ripple-effect: ~/github/ripple-effect/build/verify-runez/ripple-effect
      runez already installed editable

    portable-python: ~/github/ripple-effect/build/verify-runez/portable-python
      runez already installed editable

    Testing ripple-effect...
    ... 2 passed in 0.1s ...

    Testing portable-python...
    ... 24 passed in 2.1s ...

    ──────────────────────────────────────────────────
      ripple-effect: PASSED (0.3s)
      portable-python: PASSED (3.1s)

Global flags
------------

.. code-block:: bash

    ripple-effect --dryrun run      # show what would happen without doing it
    ripple-effect --verbose run     # show debug output including every command run
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
        prepare: "hatch env create"   # project uses hatch instead of uv
        test: ".venv/bin/pytest tests/ -x"

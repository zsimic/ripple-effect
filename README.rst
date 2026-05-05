ripple-effect
=============

Know your blast radius before you push.

Test a Python library against the downstream projects that depend on it —
before you tag a release and find out the hard way.

Installation
------------

.. code-block:: bash

    uvx ripple-effect config.yml

Usage
-----

Create a YAML config describing your library and the downstream projects to test against:

.. code-block:: yaml

    proving-grounds: /tmp/ripple-effect-workspace
    downstream-projects:
      - git+https://github.com/example/project-b.git@main
      - git+https://github.com/example/project-c.git@main

Then run:

.. code-block:: bash

    ripple-effect config.yml

ripple-effect will:

1. Clone (or update) each downstream project into ``proving-grounds``
2. Create a venv for each, with the downstream project + your library installed in editable mode
3. Run each project's test suite
4. Report which passed, which failed

For local iteration (e.g. testing against a local checkout of a downstream project):

.. code-block:: yaml

    proving-grounds: ~/dev/my-ripple-workspace
    downstream-projects:
      - git+https://github.com/example/project-b.git@main
      - ~/dev/project-c

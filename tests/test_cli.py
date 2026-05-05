import runez

import ripple_effect.__main__


def test_trivial(cli):
    cli.run("--help")
    assert cli.succeeded
    assert "Usage:" in cli.logged.stdout

    # For test coverage: exercise invoking ad-hoc `__main__.py`
    cli.run("--help", main=ripple_effect.__main__.__file__)
    assert cli.succeeded
    assert "Usage:" in cli.logged.stdout

    cli.run("no-such-config.yml")
    assert cli.failed

    runez.write("sample.yml", "# placeholder\n", logger=None)
    cli.run("sample.yml")
    assert cli.failed
    assert "No downstream-projects specified" in cli.logged


def test_minimal_valid_config(cli):
    sample = runez.to_path(cli.tests_folder) / "samples/incomplete.yml"
    cli.run("-v", sample)
    assert cli.succeeded
    assert "upstream: -missing-" in cli.logged.stdout
    assert "proving-grounds: /tmp/ripple" in cli.logged.stdout
    assert "2 downstream projects:" in cli.logged.stdout
    assert "source-ref: ." in cli.logged.stdout
    assert "source-ref: https://github.com/foo/bar.git@main" in cli.logged.stdout

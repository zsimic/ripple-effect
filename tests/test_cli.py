import runez


def test_help(cli):
    cli.run("--help")
    assert cli.succeeded
    assert "downstream" in cli.logged.stdout


def test_missing_config(cli):
    cli.run("no-such-config.yml")
    assert cli.failed


def test_invalid_config(cli):
    runez.write("sample.yml", "# placeholder\n", logger=None)
    cli.run("sample.yml")
    assert cli.failed
    assert "downstream-projects" in cli.logged.stdout


def test_minimal_valid_config(cli):
    runez.write(
        "sample.yml",
        """
proving-grounds: /tmp/ripple
downstream-projects:
  - .
  - https://github.com/foo/bar.git@main
""",
        logger=None,
    )
    cli.run("sample.yml")
    assert cli.succeeded
    assert "upstream: . (local)" in cli.logged.stdout
    assert "downstream projects: 2" in cli.logged.stdout
    assert "folder: ." in cli.logged.stdout
    assert "url: https://github.com/foo/bar.git@main" in cli.logged.stdout

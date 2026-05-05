import runez


def test_help(cli):
    cli.run("--help")
    assert cli.succeeded
    assert "downstream" in cli.logged.stdout


def test_missing_config(cli, temp_folder):
    cli.run("no-such-config.yml")
    assert cli.failed


def test_sample_config(cli, temp_folder):
    runez.write("sample.yml", "# placeholder\n", logger=None)
    cli.run("sample.yml")
    assert cli.succeeded
    assert "not yet implemented" in cli.logged.stdout

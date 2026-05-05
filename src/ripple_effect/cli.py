"""CLI entry point for ripple-effect."""

import click


@click.command()
@click.argument("config", type=click.Path(exists=True, dir_okay=False))
@click.option("-n", "--dryrun", is_flag=True, help="Show what would be done without doing it")
@click.option("-v", "--verbose", is_flag=True, help="Show more output")
def main(config: str, dryrun: bool, verbose: bool) -> None:
    """Test a Python library against its downstream dependents.

    CONFIG is a YAML file describing the library under test and the downstream
    projects to run against it.
    """
    click.echo("ripple-effect: not yet implemented")

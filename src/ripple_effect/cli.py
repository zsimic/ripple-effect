"""CLI entry point for ripple-effect."""

import click
import runez

from ripple_effect.config import load_config


@click.command()
@click.argument("config", type=click.Path(exists=True, dir_okay=False))
@runez.click.dryrun("-n")
@click.option("-v", "--verbose", is_flag=True, help="Show more output")
def main(config: str, verbose: bool) -> None:
    """Test a Python library against its downstream dependents.

    CONFIG is a YAML file describing the library under test and the downstream
    projects to run against it.
    """
    runez.log.setup(debug=verbose)
    cfg = load_config(config)
    runez.abort_if(not cfg.downstream_projects, "No downstream-projects specified")
    print(cfg.represented())

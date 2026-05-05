"""CLI entry point for ripple-effect."""

import sys

import click

from ripple_effect.config import ConfigError, load_config


@click.command()
@click.argument("config", type=click.Path(exists=True, dir_okay=False))
@click.option("-n", "--dryrun", is_flag=True, help="Show what would be done without doing it")
@click.option("-v", "--verbose", is_flag=True, help="Show more output")
def main(config: str, dryrun: bool, verbose: bool) -> None:
    """Test a Python library against its downstream dependents.

    CONFIG is a YAML file describing the library under test and the downstream
    projects to run against it.
    """
    try:
        cfg = load_config(config)
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"upstream: {cfg.upstream.raw} ({'local' if cfg.upstream.is_local else 'url'})")
    click.echo(f"proving-grounds: {cfg.proving_grounds if cfg.proving_grounds else '(none — all downstream are local)'}")
    click.echo(f"downstream projects: {len(cfg.downstream_projects)}")
    for p in cfg.downstream_projects:
        kind = "folder" if p.is_local else "url"
        click.echo(f"  - {kind}: {p.raw}")
        if verbose:
            click.echo(f"      prepare: {p.prepare}")
            click.echo(f"      test:    {p.test}")
    click.echo("(execution not yet implemented)")

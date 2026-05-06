"""CLI entry point for ripple-effect."""

import click
import runez

from ripple_effect.config import Config


@runez.click.group()
@click.option("--config", "-c", envvar="RIPPLE_CONFIG", default="ripple-config.yml", show_default=True, help="Config file")
@runez.click.dryrun("-n")
@runez.click.debug("-v", "--verbose")
@click.pass_context
def main(ctx, debug: bool, config: str):
    """Test a Python library against its downstream dependents."""
    runez.log.setup(debug=debug, console_format="%(levelname)s %(message)s", greetings="args: {argv}")
    ctx.obj = Config.from_file(config)


@main.command()
@click.pass_obj
def show(cfg):
    """Show the resolved configuration."""
    print(cfg.represented())


@main.command()
@click.pass_obj
def prepare(cfg):
    """Prepare downstream project environments (clone + build venvs)."""
    runez.abort_if(not cfg.downstream_projects, "No downstream-projects specified")
    print("(not yet implemented)")


@main.command()
@click.pass_obj
def run(cfg):
    """Run the full pipeline: prepare → inject → test."""
    runez.abort_if(not cfg.downstream_projects, "No downstream-projects specified")
    print("(not yet implemented)")

"""CLI entry point for ripple-effect."""

import logging

import click
import runez

from ripple_effect.model import RippleSpec


@runez.click.group()
@click.option("--config", "-c", envvar="RIPPLE_CONFIG", default="ripple-config.yml", show_default=True, help="Config file")
@runez.click.dryrun("-n")
@runez.click.debug("-v", "--verbose")
@click.pass_context
def main(ctx, debug: bool, config: str):
    """Test a Python library against its downstream dependents."""
    runez.log.setup(debug=debug, level=logging.INFO, console_format="%(levelname)s %(message)s", greetings="args: {argv}")
    ctx.obj = RippleSpec.from_file(config)


@main.command()
@click.pass_obj
def show(cfg: RippleSpec):
    """Show the resolved configuration."""
    print(cfg.represented())


@main.command()
@click.pass_obj
def prepare(cfg: RippleSpec):
    """Prepare downstream project environments (clone + build venvs)."""
    runez.abort_if(not cfg.downstream_projects, "No downstream-projects specified")
    cfg.prepare()


@main.command()
@click.pass_obj
def run(cfg: RippleSpec):
    """Run the full pipeline: prepare → inject → test."""
    runez.abort_if(not cfg.downstream_projects, "No downstream-projects specified")
    cfg.run()

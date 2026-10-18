"""CLI entry point for ripple-effect."""

import io
import logging
import sys

import click
import runez

from ripple_effect.model import RippleSpec


@runez.click.group()
@click.option("--config", "-c", envvar="RIPPLE_CONFIG", default="ripple-effect.yml", show_default=True, help="Config file")
@runez.click.dryrun("-n")
@runez.click.debug("-v", "--verbose")
@click.pass_context
def main(ctx, debug: bool, config: str):
    """Test a Python library against its downstream dependents."""
    runez.system.AbortException = SystemExit
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)  # Keep print() output in order with logs (on stderr) when piped (CI, agents)

    runez.log.setup(debug=debug, level=logging.INFO, console_format="%(levelname)s %(message)s", greetings="args: {argv}")
    ctx.obj = RippleSpec.from_file(config)
    if ctx.invoked_subcommand != "show":
        ctx.obj.abort_if_invalid()  # `show` displays the config first, then all problems found


@main.command()
@click.pass_obj
def show(cfg: RippleSpec):
    """Show the resolved configuration, and any problems found in it."""
    print(cfg.represented())
    cfg.abort_if_invalid()


@main.command()
@click.pass_obj
def prepare(cfg: RippleSpec):
    """Prepare downstream project environments (clone + build venvs)."""
    cfg.prepare()


@main.command()
@click.pass_obj
def run(cfg: RippleSpec):
    """Run the full pipeline: prepare → inject → test."""
    cfg.run()

"""Allows to run via `python -m ripple_effect`."""

import runez

from ripple_effect.cli import main as cli_main


def main():
    """Entry point that wraps the click command with runez exception handling."""
    runez.click.protected_main(cli_main, debug_stacktrace=True)


if __name__ == "__main__":
    main()

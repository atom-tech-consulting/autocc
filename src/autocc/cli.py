"""autocc CLI — install/uninstall/status."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .installer import install, status, uninstall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="autocc",
        description="autopilot for Claude Code — skills + hooks that let a session run unattended.",
    )
    parser.add_argument("--version", action="version", version=f"autocc {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install", help="install skills, hooks, and wire ~/.claude/settings.json")
    p_install.add_argument("--dry-run", action="store_true", help="show what would change, don't write")
    p_install.add_argument("-y", "--yes", action="store_true", help="apply settings.json patch without prompting")

    p_uninstall = sub.add_parser("uninstall", help="remove autocc artifacts and revert settings.json entries")
    p_uninstall.add_argument("--dry-run", action="store_true")
    p_uninstall.add_argument("-y", "--yes", action="store_true")

    sub.add_parser("status", help="show installed components")

    args = parser.parse_args(argv)

    if args.cmd == "install":
        return install(dry_run=args.dry_run, assume_yes=args.yes)
    if args.cmd == "uninstall":
        return uninstall(dry_run=args.dry_run, assume_yes=args.yes)
    if args.cmd == "status":
        return status()
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())

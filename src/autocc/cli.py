"""autocc CLI — install/uninstall/status."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .installer import VALID_AGENTS, install, status, uninstall


def _add_agent_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent",
        choices=VALID_AGENTS,
        default="claude",
        help=(
            "target agent provider (default: claude). "
            "`claude` writes ~/.claude/{skills,hooks}/ and patches settings.json; "
            "`codex` writes a plugin folder at ${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/ "
            "and registers it in ~/.agents/plugins/marketplace.json."
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="autocc",
        description="autopilot for Claude Code / Codex — skills + hooks that let a session run unattended.",
    )
    parser.add_argument("--version", action="version", version=f"autocc {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install", help="install skills, hooks, and wire up the provider config")
    p_install.add_argument("--dry-run", action="store_true", help="show what would change, don't write")
    p_install.add_argument("-y", "--yes", action="store_true", help="apply settings patch without prompting (claude only)")
    _add_agent_arg(p_install)

    p_uninstall = sub.add_parser("uninstall", help="remove autocc artifacts and revert provider config entries")
    p_uninstall.add_argument("--dry-run", action="store_true")
    p_uninstall.add_argument("-y", "--yes", action="store_true")
    _add_agent_arg(p_uninstall)

    p_status = sub.add_parser("status", help="show installed components")
    _add_agent_arg(p_status)

    args = parser.parse_args(argv)

    if args.cmd == "install":
        return install(agent=args.agent, dry_run=args.dry_run, assume_yes=args.yes)
    if args.cmd == "uninstall":
        return uninstall(agent=args.agent, dry_run=args.dry_run, assume_yes=args.yes)
    if args.cmd == "status":
        return status(agent=args.agent)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())

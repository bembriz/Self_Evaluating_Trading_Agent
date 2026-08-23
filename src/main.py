"""Entry point del Self-Evaluating Trading Agent."""

from __future__ import annotations

import argparse
import sys

from version import __version__


def main(argv: list[str] | None = None) -> int:
    """Imprime la identidad o despacha subcomandos (download/verify)."""
    from interfaces.cli import download as cli

    parser = argparse.ArgumentParser(prog="self-evaluating-trading-agent")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("download")
    sub.add_parser("verify")
    args, rest = parser.parse_known_args(argv if argv is not None else [])
    if args.command == "download":
        return cli.download(rest)
    if args.command == "verify":
        return cli.verify(rest)
    print(f"self-evaluating-trading-agent {__version__}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))

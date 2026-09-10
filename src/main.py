"""Entry point del Self-Evaluating Trading Agent."""

from __future__ import annotations

import argparse
import sys

from version import __version__


def main(argv: list[str] | None = None) -> int:
    """Imprime identidad o despacha subcomandos, incluyendo paper-runner."""
    from interfaces.cli import backtest as cli_backtest
    from interfaces.cli import download as cli
    from interfaces.cli import market_worker as worker
    from interfaces.cli import paper_runner as cli_paper_runner
    from interfaces.cli import paper_session as cli_paper
    from interfaces.cli import replay as cli_replay

    parser = argparse.ArgumentParser(prog="self-evaluating-trading-agent")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("download")
    sub.add_parser("verify")
    sub.add_parser("market-worker")
    sub.add_parser("backtest")
    sub.add_parser("replay")
    sub.add_parser("paper-session")
    sub.add_parser("paper-runner")
    args, rest = parser.parse_known_args(argv if argv is not None else [])
    if args.command == "download":
        return cli.download(rest)
    if args.command == "verify":
        return cli.verify(rest)
    if args.command == "market-worker":
        return worker.market_worker(rest)
    if args.command == "backtest":
        return cli_backtest.backtest(rest)
    if args.command == "replay":
        return cli_replay.replay(rest)
    if args.command == "paper-session":
        return cli_paper.paper_session(rest)
    if args.command == "paper-runner":
        return cli_paper_runner.paper_runner(rest)
    print(f"self-evaluating-trading-agent {__version__}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))

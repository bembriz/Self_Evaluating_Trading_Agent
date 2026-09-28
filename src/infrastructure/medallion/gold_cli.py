"""CLI Gold replay dataset — stdlib puro.

Uso en lenovosrv (sin venv):

    python3 -m infrastructure.medallion.gold_cli \\
        --trades-dir /srv/data/medallion/silver/trades/ETHUSDT \\
        --candles-dir /srv/data/medallion/silver/candles/ETHUSDT \\
        --dest-dir /srv/data/medallion/gold/replay-datasets/ETHUSDT \\
        --dates 2024-06-01,2024-06-02,2024-06-03 \\
        --require-marker /srv/data/.lenovosrv-data-volume
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from infrastructure.medallion.bronze import BronzeError, ensure_marker
from infrastructure.medallion.gold import GoldResult, create_dataset
from infrastructure.medallion.split_guard import SplitGuardError

EXIT_OK = 0
EXIT_GOLD_ERROR = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gold replay dataset (idempotente)")
    parser.add_argument("--trades-dir", required=True, type=Path)
    parser.add_argument("--candles-dir", required=True, type=Path)
    parser.add_argument("--dest-dir", required=True, type=Path)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--dates", required=True, help="YYYY-MM-DD separados por coma")
    parser.add_argument("--require-marker", type=Path, default=None)
    return parser


def _parse_dates(raw: str) -> list[date]:
    days: list[date] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            raise ValueError(f"fecha vacía en {raw!r}")
        days.append(date.fromisoformat(token))
    return days


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        days = _parse_dates(args.dates)
    except ValueError as exc:
        print(f"ERROR fechas: {exc}", file=sys.stderr)
        return EXIT_USAGE
    try:
        if args.require_marker is not None:
            ensure_marker(args.require_marker)
        result: GoldResult = create_dataset(
            args.trades_dir, args.candles_dir, args.dest_dir, args.symbol, days
        )
    except (BronzeError, SplitGuardError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_GOLD_ERROR

    print(
        f"{result.status.upper()} dataset_id={result.dataset_id} "
        f"manifest_sha256={result.manifest_sha256} "
        f"trades={result.trade_partitions} candles={result.candle_outputs}"
    )
    created = 1 if result.status == "created" else 0
    skipped = 1 if result.status == "skipped" else 0
    print(f"SUMMARY created={created} skipped={skipped}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

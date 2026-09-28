"""CLI Silver candles multi-timeframe — stdlib puro.

Uso en lenovosrv (sin venv):

    python3 -m infrastructure.medallion.candles_cli \\
        --trades-dir /srv/data/medallion/silver/trades/ETHUSDT \\
        --dest-dir /srv/data/medallion/silver/candles/ETHUSDT \\
        --dates 2024-06-01,2024-06-02,2024-06-03 \\
        --require-marker /srv/data/.lenovosrv-data-volume
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from infrastructure.medallion.bronze import BronzeError, ensure_marker
from infrastructure.medallion.candles import transform_days
from infrastructure.medallion.split_guard import SplitGuardError

EXIT_OK = 0
EXIT_CANDLE_ERROR = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Silver candles multi-timeframe (idempotente)")
    parser.add_argument("--trades-dir", required=True, type=Path)
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
    if not days:
        raise ValueError("se requiere al menos una fecha")
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
        results = transform_days(args.trades_dir, args.dest_dir, args.symbol, days)
    except (BronzeError, SplitGuardError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CANDLE_ERROR

    transformed = sum(1 for r in results if r.status == "transformed")
    skipped = sum(1 for r in results if r.status == "skipped")
    for r in results:
        print(
            f"{r.status.upper()} {r.filename} tf={r.timeframe} "
            f"sha256={r.sha256} candles={r.candles}"
        )
    print(f"SUMMARY transformed={transformed} skipped={skipped} total={len(results)}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

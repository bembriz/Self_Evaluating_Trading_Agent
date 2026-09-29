"""CLI de backfill de schema de fuente (M9-A1) — stdlib puro.

Corrige la metadata Bronze (``schema_version`` por archivo) y el linaje Silver
(``source_schema_version``) a partir del header REAL de cada ``.csv.gz``.
No descarga, no transforma y jamás toca los ``.csv.gz``.

Uso en lenovosrv (sin venv):

    python3 -m infrastructure.medallion.schema_backfill_cli \\
        --bronze-dir /srv/data/medallion/bronze/bybit/spot/ETHUSDT \\
        --dest-dir /srv/data/medallion/silver/trades/ETHUSDT \\
        --require-marker /srv/data/.lenovosrv-data-volume
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from infrastructure.medallion.bronze import (
    BronzeError,
    backfill_source_schema,
    ensure_marker,
)
from infrastructure.medallion.silver import backfill_source_schema as backfill_silver
from infrastructure.medallion.split_guard import SplitGuardError

EXIT_OK = 0
EXIT_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill de schema de fuente (Bronze) y linaje (Silver)"
    )
    parser.add_argument("--bronze-dir", required=True, type=Path)
    parser.add_argument("--dest-dir", required=True, type=Path)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--layer", choices=("all", "bronze", "silver"), default="all")
    parser.add_argument("--require-marker", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.require_marker is not None:
            ensure_marker(args.require_marker)
        if args.layer in ("all", "bronze"):
            bronze = backfill_source_schema(args.bronze_dir)
            print(f"BRONZE_SCANNED={bronze.scanned}")
            print(f"BRONZE_ENTRIES_CHANGED={bronze.changed}")
            print(f"BRONZE_V1_FILES={bronze.v1}")
            print(f"BRONZE_V2_FILES={bronze.v2}")
        if args.layer in ("all", "silver"):
            silver = backfill_silver(args.bronze_dir, args.dest_dir, args.symbol)
            print(f"SILVER_ENTRIES_SCANNED={silver.scanned}")
            print(f"SILVER_ENTRIES_CHANGED={silver.changed}")
            print(f"SILVER_SOURCE_SCHEMA_V1={silver.v1}")
            print(f"SILVER_SOURCE_SCHEMA_V2={silver.v2}")
    except (BronzeError, SplitGuardError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

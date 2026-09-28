"""CLI Trade-Level Replay — stdlib puro.

Uso en lenovosrv (sin venv):

    python3 -m infrastructure.medallion.replay_cli \\
        --dataset-dir /srv/data/medallion/gold/replay-datasets/ETHUSDT/<dataset_id> \\
        --trades-dir /srv/data/medallion/silver/trades/ETHUSDT \\
        --candles-dir /srv/data/medallion/silver/candles/ETHUSDT \\
        --ledger-path /srv/fast/medallion/replay-work/ledger.jsonl \\
        --require-marker /srv/data/.lenovosrv-data-volume

Exit codes: 0 OK · 1 replay/dataset/IO · 2 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from infrastructure.medallion.bronze import BronzeError, ensure_marker
from infrastructure.medallion.replay import (
    DEFAULT_SCENARIO,
    ReplayTrade,
    ScriptedScheduleProvider,
    iter_trades,
    ledger_payload,
    load_candles,
    replay_engine,
    validate_dataset,
    write_ledger,
)
from infrastructure.medallion.split_guard import SplitGuardError

EXIT_OK = 0
EXIT_REPLAY_ERROR = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trade-level replay (dos relojes, idempotente)")
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--trades-dir", required=True, type=Path)
    parser.add_argument("--candles-dir", required=True, type=Path)
    parser.add_argument("--ledger-path", required=True, type=Path)
    parser.add_argument("--require-marker", type=Path, default=None)
    return parser


def _counting_trades(
    trades: Iterable[ReplayTrade], counter: dict[str, int]
) -> Iterator[ReplayTrade]:
    for trade in trades:
        counter["trades"] += 1
        yield trade


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    counter = {"trades": 0}
    try:
        if args.require_marker is not None:
            ensure_marker(args.require_marker)
        dataset = validate_dataset(args.dataset_dir, args.trades_dir, args.candles_dir)
        candles = load_candles(dataset, ("15m", "1h", "4h"))
        result = replay_engine(
            candles["15m"],
            candles["1h"],
            candles["4h"],
            _counting_trades(iter_trades(dataset), counter),
            DEFAULT_SCENARIO,
            ScriptedScheduleProvider(),
            dataset_id=dataset.dataset_id,
            dataset_sha=dataset.dataset_sha,
        )
        payload = ledger_payload(
            result,
            dataset_id=dataset.dataset_id,
            dataset_sha=dataset.dataset_sha,
            symbol=dataset.symbol,
            dates=dataset.dates,
            ordering_fidelity=dataset.ordering_fidelity,
            scenario=DEFAULT_SCENARIO,
        )
        status = write_ledger(args.ledger_path, payload)
    except (BronzeError, SplitGuardError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_REPLAY_ERROR

    created = 1 if status == "created" else 0
    skipped = 1 if status == "skipped" else 0
    ledger_sha = hashlib.sha256(payload).hexdigest()
    print(
        f"STATUS={status} dataset_id={dataset.dataset_id} "
        f"dataset_sha256={dataset.dataset_sha} ledger_sha256={ledger_sha}"
    )
    stats = result.stats
    print(
        f"SUMMARY created={created} skipped={skipped} "
        f"decisions_total={stats['decisions_total']} "
        f"decisions_filled={stats['decisions_filled']} "
        f"decisions_dropped={stats['decisions_dropped']} "
        f"decisions_unfilled={stats['decisions_unfilled']} "
        f"closed_trades={stats['closed_trades']} trades={counter['trades']}"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

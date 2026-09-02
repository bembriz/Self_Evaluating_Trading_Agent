"""Subcomando `replay` — market replay determinista de decisiones (PRD §81).

Transmite el dataset congelado vela a vela por el baseline determinista y emite una
traza JSONL de decisiones para depurar el comportamiento histórico. Verifica el
SHA-256 del manifest ANTES de correr; la salida es byte-idéntica ante el mismo input.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from application.ports.dataset_store import DatasetStore
from domain.market.candle import Timeframe
from domain.trading.strategy import EmaRsiBaseline
from infrastructure.storage.dataset_store import LocalDatasetStore
from interfaces.cli.download import verify_manifest

DEFAULT_DATASET = "BYBIT_ETHBTC_V001"


def _emit(fh: Any, record: dict[str, Any]) -> None:
    fh.write(json.dumps(record, sort_keys=True) + "\n")


def run_replay(
    store: DatasetStore,
    manifest_path: Path,
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="replay")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        timeframe = Timeframe.from_label(args.timeframe)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    try:
        verified = verify_manifest(store, manifest_path) == 0
    except (KeyError, OSError, ValueError):
        verified = False
    if not verified:
        print("ERROR: dataset congelado no verificado; replay abortado")
        return 1

    manifest = store.read_manifest(manifest_path)
    entry = next(
        (f for f in manifest.files if f.symbol == args.symbol and f.timeframe == timeframe.label),
        None,
    )
    if entry is None:
        print(f"ERROR: {args.symbol} {timeframe.label} ausente del dataset congelado")
        return 2

    candles = store.read_candles(Path(entry.path))
    strategy = EmaRsiBaseline()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"buy": 0, "sell": 0, "hold": 0}
    with out_path.open("w", encoding="utf-8") as fh:
        _emit(
            fh,
            {
                "type": "header",
                "experiment_id": (
                    f"replay-{manifest.dataset_version}-"
                    f"{strategy.version}-{args.symbol}-{timeframe.label}"
                ).lower(),
                "dataset": {
                    "version": manifest.dataset_version,
                    "file": entry.path,
                    "sha256": entry.sha256,
                    "rows": entry.row_count,
                },
                "strategy": {"name": type(strategy).__name__, "version": strategy.version},
            },
        )
        for i, candle in enumerate(candles):
            signal = strategy.on_candle(candle)
            counts[signal.action.value] += 1
            _emit(
                fh,
                {
                    "type": "decision",
                    "i": i,
                    "timestamp_ms": candle.timestamp_ms,
                    "close": candle.close,
                    "action": signal.action.value,
                    "reason": signal.reason,
                },
            )
        _emit(
            fh,
            {
                "type": "summary",
                "bars": len(candles),
                **counts,
            },
        )

    print(f"experiment_id=replay-{manifest.dataset_version}-{strategy.version}".lower())
    print(f"bars={len(candles)} buy={counts['buy']} sell={counts['sell']} hold={counts['hold']}")
    return 0


def replay(argv: list[str] | None) -> int:
    local_argv = list(argv if argv is not None else [])
    parser = argparse.ArgumentParser(prog="replay", add_help=False)
    parser.add_argument("--dataset-version", default=DEFAULT_DATASET)
    known, rest = parser.parse_known_args(local_argv)
    manifest_path = Path("docs") / "datasets" / f"{known.dataset_version}.manifest.json"
    return run_replay(LocalDatasetStore(), manifest_path, rest or None)

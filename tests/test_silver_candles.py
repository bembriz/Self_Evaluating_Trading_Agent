"""Unit tests de Silver candles multi-timeframe (M5)."""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from infrastructure.medallion import candles_cli
from infrastructure.medallion.bronze import HashConflictError, download_day, sha256_file
from infrastructure.medallion.candles import (
    CANDLE_HEADER,
    CANDLE_SCHEMA_VERSION,
    TIMEFRAMES,
    CandleError,
    InvalidTradeRowError,
    _aggregate,
    _verify_roundtrip,
    transform_day,
    transform_days,
)
from infrastructure.medallion.silver import (
    SILVER_HEADER,
)
from infrastructure.medallion.silver import (
    transform_day as silver_transform_day,
)
from infrastructure.medallion.split_guard import SplitGuardError

DEV_DAY = date(2024, 6, 1)
WF_DAY = date(2025, 6, 17)
DAY0_MS = 1717200000000  # 2024-06-01T00:00:00Z
DAY_END_MS = 1717286400000
MINUTE_MS = 60_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000


class Fake:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __call__(self, url: str, dest: Path) -> int:
        dest.write_bytes(self.payload)
        return len(self.payload)


def _gz(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"), mtime=0)


def make_trades(
    bronze: Path,
    trades: Path,
    rows: list[tuple[str, str, str, str, str]],
    day: date = DEV_DAY,
) -> None:
    body = "id,timestamp,price,volume,side\n" + "".join(",".join(row) + "\n" for row in rows)
    download_day(bronze, "ETHUSDT", day, fetcher=Fake(_gz(body)))
    silver_transform_day(bronze, trades, "ETHUSDT", day)


def trades_name(day: date = DEV_DAY) -> str:
    return f"ETHUSDT_{day.isoformat()}.csv.gz"


def read_candles(path: Path) -> tuple[list[str], list[list[str]]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        lines = fh.read().splitlines()
    return lines[0].split(","), [line.split(",") for line in lines[1:]]


def candle_path(dest: Path, tf: str, day: date = DEV_DAY) -> Path:
    return (
        dest
        / f"timeframe={tf}"
        / f"date={day.isoformat()}"
        / trades_name(day).replace(".csv.gz", f"_{tf}.csv.gz")
    )


def rewrite_trades(
    trades: Path,
    body_rows: list[tuple[str, ...]],
    day: date = DEV_DAY,
    row_count: int | None = None,
    header: tuple[str, ...] = SILVER_HEADER,
    raw: bytes | None = None,
) -> None:
    """Reescribe el trades Silver (contenido a medida) y sincroniza su manifest."""
    name = trades_name(day)
    path = trades / f"date={day.isoformat()}" / name
    if raw is not None:
        path.write_bytes(raw)
    else:
        text = ",".join(header) + "\n" + "".join(",".join(r) + "\n" for r in body_rows)
        path.write_bytes(_gz(text))
    sha = sha256_file(path)
    mf = json.loads((trades / "manifest.json").read_text(encoding="utf-8"))
    entry = mf["files"][name]
    entry["output_sha256"] = sha
    entry["row_count"] = len(body_rows) if row_count is None else row_count
    (trades / "manifest.json").write_text(
        json.dumps(mf, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def srow(ts: int, price: str, qty: str, n: int, day: date = DEV_DAY) -> tuple[str, ...]:
    name = trades_name(day)
    return (
        str(ts),
        "ETHUSDT",
        price,
        qty,
        "buy",
        str(n),
        "",
        f"date={day.isoformat()}/{name}",
        "0" * 64,
        str(n),
    )


def test_transform_generates_7_timeframes(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS + 1000), "3762.62", "0.07674", "sell")])

    results = transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    assert [r.timeframe for r in results] == list(TIMEFRAMES)
    assert TIMEFRAMES == ("1m", "5m", "15m", "30m", "1h", "4h", "1d")
    assert all(r.status == "transformed" for r in results)
    for tf in TIMEFRAMES:
        assert candle_path(dest, tf).is_file()
    assert not list(dest.rglob("*.part"))


def test_ohlc_exact(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(
        bronze,
        trades,
        [
            ("10", str(DAY0_MS + 274), "3762.62", "0.07674", "sell"),
            ("11", str(DAY0_MS + 512), "3761.00", "1.5", "buy"),
            ("12", str(DAY0_MS + 900), "3762.63", "0.001", "sell"),
        ],
    )

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    _, data = read_candles(candle_path(dest, "1m"))
    assert len(data) == 1
    row = data[0]
    assert row[0] == str(DAY0_MS)
    assert row[1] == str(DAY0_MS + MINUTE_MS)
    assert row[4] == "3762.62"  # open = primera operación (orden canónico)
    assert row[5] == "3762.63"  # high
    assert row[6] == "3761.00"  # low
    assert row[7] == "3762.63"  # close = última operación
    assert row[8] == "1.57774"  # 0.07674 + 1.5 + 0.001 exacto
    assert row[9] == "3"


def test_decimal_exact_no_float(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(
        bronze,
        trades,
        [
            ("1", str(DAY0_MS), "0.00000001", "0.1", "buy"),
            ("2", str(DAY0_MS + 1), "1717200000.12345678", "0.2", "sell"),
        ],
    )

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    _, data = read_candles(candle_path(dest, "1m"))
    row = data[0]
    assert row[4] == "0.00000001"
    assert row[5] == "1717200000.12345678"
    assert row[6] == "0.00000001"
    assert row[7] == "1717200000.12345678"
    assert row[8] == "0.3"  # Decimal exacto: 0.1 + 0.2 != 0.30000000000000004
    assert "e" not in row[8].lower()


def test_utc_boundaries(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(
        bronze,
        trades,
        [
            ("1", str(DAY0_MS), "100.0", "1", "buy"),  # 00:00:00.000
            ("2", str(DAY0_MS + 59_999), "101.0", "1", "buy"),  # 00:00:59.999
            ("3", str(DAY0_MS + 60_000), "102.0", "1", "buy"),  # 00:01:00.000
        ],
    )

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    _, data = read_candles(candle_path(dest, "1m"))
    assert [(r[0], r[1]) for r in data] == [
        (str(DAY0_MS), str(DAY0_MS + MINUTE_MS)),
        (str(DAY0_MS + MINUTE_MS), str(DAY0_MS + 2 * MINUTE_MS)),
    ]
    for r in data:
        assert (int(r[1]) - int(r[0])) == MINUTE_MS
        assert int(r[0]) % MINUTE_MS == 0


def test_first_and_last_trade(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(
        bronze,
        trades,
        [
            ("1", str(DAY0_MS + 10), "500.0", "1", "buy"),
            ("2", str(DAY0_MS + 20), "1.0", "1", "sell"),
            ("3", str(DAY0_MS + 30), "900.0", "1", "buy"),
        ],
    )

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    _, data = read_candles(candle_path(dest, "1m"))
    row = data[0]
    assert row[4] == "500.0"  # open = primera operación, no el mínimo
    assert row[7] == "900.0"  # close = última operación, no el máximo
    assert row[5] == "900.0"
    assert row[6] == "1.0"


def test_volume_and_trade_count(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(
        bronze,
        trades,
        [
            ("1", str(DAY0_MS + 1), "100.0", "0.00000001", "buy"),
            ("2", str(DAY0_MS + 2), "100.0", "0.00000002", "buy"),
            ("3", str(DAY0_MS + MINUTE_MS + 1), "100.0", "1.5", "buy"),
        ],
    )

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    _, data = read_candles(candle_path(dest, "1m"))
    assert [r[8] for r in data] == ["0.00000003", "1.5"]
    assert [r[9] for r in data] == ["2", "1"]


def test_no_gap_filling(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(
        bronze,
        trades,
        [
            ("1", str(DAY0_MS), "100.0", "1", "buy"),
            ("2", str(DAY0_MS + 10 * MINUTE_MS), "101.0", "1", "buy"),
        ],
    )

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    _, data = read_candles(candle_path(dest, "1m"))
    assert len(data) == 2  # minutos 0 y 10; sin velas sintéticas intermedias
    opens = [int(r[0]) for r in data]
    assert opens == [DAY0_MS, DAY0_MS + 10 * MINUTE_MS]


def test_close_equals_next_open(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(
        bronze,
        trades,
        [
            ("1", str(DAY0_MS + 30_000), "100.0", "1", "buy"),
            ("2", str(DAY0_MS + 90_000), "101.0", "1", "buy"),
        ],
    )

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    _, data = read_candles(candle_path(dest, "1m"))
    assert data[0][1] == data[1][0]  # sin solapes: close == siguiente open
    _, data5 = read_candles(candle_path(dest, "5m"))
    assert len(data5) == 1  # ambas operaciones caen en la misma vela de 5m


def test_hash_mismatch_fail_closed(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    path = trades / f"date={DEV_DAY.isoformat()}" / trades_name()
    path.write_bytes(path.read_bytes() + b"x")  # altera el bytes sin actualizar manifest

    with pytest.raises(HashConflictError):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)
    assert not dest.exists()


def test_missing_manifest_entry_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    mf_path = trades / "manifest.json"
    mf = json.loads(mf_path.read_text(encoding="utf-8"))
    del mf["files"][trades_name()]
    mf_path.write_text(json.dumps(mf, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(HashConflictError):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_row_count_mismatch_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    mf_path = trades / "manifest.json"
    mf = json.loads(mf_path.read_text(encoding="utf-8"))
    mf["files"][trades_name()]["row_count"] = 999
    mf_path.write_text(json.dumps(mf, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(HashConflictError):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_invalid_row_fail_closed(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    bad = srow(DAY0_MS, "1e-8", "1", 1)  # notación exponencial prohibida
    rewrite_trades(trades, [bad])

    with pytest.raises(InvalidTradeRowError):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)
    assert not dest.exists()


def test_wrong_symbol_fail_closed(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    row = list(srow(DAY0_MS, "100.0", "1", 1))
    row[1] = "BTCUSDT"
    rewrite_trades(trades, [tuple(row)])

    with pytest.raises(InvalidTradeRowError):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_timestamp_out_of_day_fail_closed(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    rewrite_trades(trades, [srow(DAY_END_MS, "100.0", "1", 1)])

    with pytest.raises(InvalidTradeRowError):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_source_order_violation_fail_closed(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    rewrite_trades(
        trades,
        [
            srow(DAY0_MS + 2000, "100.0", "1", 1),
            srow(DAY0_MS + 1000, "100.0", "1", 2),
        ],
    )

    with pytest.raises(InvalidTradeRowError):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_determinism_same_input_same_hash(tmp_path: Path) -> None:
    bronze, trades = tmp_path / "b", tmp_path / "t"
    make_trades(
        bronze,
        trades,
        [
            ("1", str(DAY0_MS + 1000), "100.0", "1", "buy"),
            ("2", str(DAY0_MS + 70_000), "101.0", "2", "sell"),
        ],
    )

    r1 = transform_day(trades, tmp_path / "c1", "ETHUSDT", DEV_DAY)
    r2 = transform_day(trades, tmp_path / "c2", "ETHUSDT", DEV_DAY)

    assert [r.sha256 for r in r1] == [r.sha256 for r in r2]
    assert [r.candles for r in r1] == [r.candles for r in r2]


def test_idempotent_rerun_skips(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])

    first = transform_day(trades, dest, "ETHUSDT", DEV_DAY)
    manifest_before = (dest / "manifest.json").read_bytes()
    second = transform_day(trades, dest, "ETHUSDT", DEV_DAY)
    manifest_after = (dest / "manifest.json").read_bytes()

    assert [r.status for r in first] == ["transformed"] * 7
    assert [r.status for r in second] == ["skipped"] * 7
    assert [r.sha256 for r in first] == [r.sha256 for r in second]
    assert manifest_before == manifest_after
    assert not list(dest.rglob("*.part"))


def test_output_altered_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    transform_day(trades, dest, "ETHUSDT", DEV_DAY)
    out = candle_path(dest, "1m")
    out.write_bytes(out.read_bytes() + b"x")

    with pytest.raises(HashConflictError):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_part_file_stale_recovered(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    stale = candle_path(dest, "1m").with_name(candle_path(dest, "1m").name + ".part")
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"garbage")

    results = transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    assert all(r.status == "transformed" for r in results)
    assert not list(dest.rglob("*.part"))
    _, data = read_candles(candle_path(dest, "1m"))
    assert len(data) == 1


def test_split_guard_walk_forward(tmp_path: Path) -> None:
    trades, dest = tmp_path / "t", tmp_path / "c"

    with pytest.raises(SplitGuardError):
        transform_day(trades, dest, "ETHUSDT", WF_DAY)
    assert not dest.exists()


def test_4h_boundaries(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    last_of_bucket = DAY0_MS + 4 * HOUR_MS - 1  # 03:59:59.999
    first_of_next = DAY0_MS + 4 * HOUR_MS  # 04:00:00.000
    make_trades(
        bronze,
        trades,
        [
            ("1", str(last_of_bucket), "100.0", "1", "buy"),
            ("2", str(first_of_next), "101.0", "2", "sell"),
        ],
    )

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    _, data = read_candles(candle_path(dest, "4h"))
    assert [(r[0], r[1]) for r in data] == [
        (str(DAY0_MS), str(DAY0_MS + 4 * HOUR_MS)),
        (str(DAY0_MS + 4 * HOUR_MS), str(DAY0_MS + 8 * HOUR_MS)),
    ]
    assert [r[9] for r in data] == ["1", "1"]
    assert [r[4] for r in data] == ["100.0", "101.0"]


def test_4h_only_occupied_buckets(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS + HOUR_MS), "100.0", "1", "buy")])

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    _, data = read_candles(candle_path(dest, "4h"))
    assert len(data) == 1  # bucket 00-04 solamente; sin velas sintéticas
    assert data[0][9] == "1"


def test_1d_aggregation_full_day(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(
        bronze,
        trades,
        [
            ("1", str(DAY0_MS + HOUR_MS), "300.0", "1", "buy"),
            ("2", str(DAY0_MS + 12 * HOUR_MS), "100.0", "2", "sell"),
            ("3", str(DAY0_MS + 20 * HOUR_MS), "700.0", "3", "buy"),
        ],
    )

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    _, data = read_candles(candle_path(dest, "1d"))
    assert len(data) == 1
    row = data[0]
    assert row[0] == str(DAY0_MS)
    assert row[1] == str(DAY_END_MS)  # close_time exclusivo = fin del día UTC
    assert row[2] == "ETHUSDT"
    assert row[3] == "1d"
    assert row[4] == "300.0"
    assert row[5] == "700.0"
    assert row[6] == "100.0"
    assert row[7] == "700.0"
    assert row[8] == "6"  # 1 + 2 + 3
    assert row[9] == "3"


def test_manifest_lineage(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(
        bronze,
        trades,
        [
            ("1", str(DAY0_MS + 1000), "100.0", "1", "buy"),
            ("2", str(DAY0_MS + 2 * HOUR_MS), "101.0", "2", "sell"),
        ],
    )
    trades_sha = sha256_file(trades / f"date={DEV_DAY.isoformat()}" / trades_name())

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    mf = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert mf["schema_version"] == CANDLE_SCHEMA_VERSION
    entry = mf["files"][trades_name().replace(".csv.gz", "_15m.csv.gz")]
    assert entry["timeframe"] == "15m"
    assert entry["symbol"] == "ETHUSDT"
    assert entry["date"] == "2024-06-01"
    assert entry["schema_version"] == CANDLE_SCHEMA_VERSION
    assert entry["source_trades"] == [
        {
            "path": f"date={DEV_DAY.isoformat()}/{trades_name()}",
            "sha256": trades_sha,
        }
    ]
    assert entry["output_path"].startswith("timeframe=15m/date=2024-06-01/")
    assert entry["output_sha256"] == sha256_file(candle_path(dest, "15m"))
    assert entry["candle_count"] == 2
    assert entry["min_open_time"] == DAY0_MS
    assert entry["max_open_time"] == DAY0_MS + 2 * HOUR_MS  # bucket 15m de +2h
    assert entry["duration_ms"] == 15 * MINUTE_MS


def test_candles_confirmed_within_source_day(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(
        bronze,
        trades,
        [
            ("1", str(DAY0_MS), "100.0", "1", "buy"),
            ("2", str(DAY_END_MS - 1), "101.0", "1", "sell"),
        ],
    )

    transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    for tf in TIMEFRAMES:
        _, data = read_candles(candle_path(dest, tf))
        for r in data:
            assert int(r[1]) <= DAY_END_MS  # solo velas cerradas dentro de la fuente
            assert DAY0_MS <= int(r[0]) < int(r[1])


def test_transform_days_multiple(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    day2 = date(2024, 6, 2)
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    make_trades(
        bronze,
        trades,
        [("2", str(DAY0_MS + DAY_MS), "200.0", "2", "sell")],
        day2,
    )

    results = transform_days(trades, dest, "ETHUSDT", [DEV_DAY, day2])

    assert len(results) == 14
    assert all(r.status == "transformed" for r in results)
    assert len(list(dest.glob("timeframe=*/*/*.csv.gz"))) == 14


def test_cli_success_and_idempotent_rerun(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    argv = [
        "--trades-dir",
        str(trades),
        "--dest-dir",
        str(dest),
        "--dates",
        "2024-06-01",
    ]

    rc1 = candles_cli.main(argv)
    out1 = capsys.readouterr().out
    rc2 = candles_cli.main(argv)
    out2 = capsys.readouterr().out

    assert rc1 == 0 and rc2 == 0
    assert "SUMMARY transformed=7 skipped=0 total=7" in out1
    assert "SUMMARY transformed=0 skipped=7 total=7" in out2


def test_cli_rejects_walk_forward_date(tmp_path: Path) -> None:
    rc = candles_cli.main(
        [
            "--trades-dir",
            str(tmp_path / "t"),
            "--dest-dir",
            str(tmp_path / "c"),
            "--dates",
            "2025-06-17",
        ]
    )
    assert rc == 1
    assert not (tmp_path / "c").exists()


def test_cli_bad_date_format(tmp_path: Path) -> None:
    rc = candles_cli.main(
        [
            "--trades-dir",
            str(tmp_path / "t"),
            "--dest-dir",
            str(tmp_path / "c"),
            "--dates",
            "ayer",
        ]
    )
    assert rc == 2


def test_cli_require_marker(tmp_path: Path) -> None:
    marker = tmp_path / ".lenovosrv-data-volume"
    marker.write_text("LENOVO_DATA\n")
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])

    rc_missing = candles_cli.main(
        [
            "--trades-dir",
            str(trades),
            "--dest-dir",
            str(dest),
            "--dates",
            "2024-06-01",
            "--require-marker",
            str(tmp_path / "nope"),
        ]
    )
    rc_ok = candles_cli.main(
        [
            "--trades-dir",
            str(trades),
            "--dest-dir",
            str(dest),
            "--dates",
            "2024-06-01",
            "--require-marker",
            str(marker),
        ]
    )
    assert rc_missing == 1
    assert rc_ok == 0


def _mutate(row: tuple[str, ...], index: int, value: str) -> tuple[str, ...]:
    items = list(row)
    items[index] = value
    return tuple(items)


@pytest.mark.parametrize(
    ("index", "value", "fragment"),
    [
        (0, "17x7", "timestamp"),
        (1, "BTCUSDT", "symbol"),
        (2, "1e-8", "price"),
        (3, "1.5e3", "quantity"),
        (4, "hold", "side"),
        (5, "abc", "native_trade_id"),
        (6, "xy", "native_sequence"),
        (7, "date=2024-06-02/ETHUSDT_2024-06-02.csv.gz", "source_file"),
        (8, "nothex", "source_file_sha256"),
        (9, "1.0", "source_row_number"),
    ],
)
def test_invalid_field_variants_fail_closed(
    tmp_path: Path, index: int, value: str, fragment: str
) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    rewrite_trades(trades, [_mutate(srow(DAY0_MS, "100.0", "1", 1), index, value)])

    with pytest.raises(InvalidTradeRowError, match=fragment):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)
    assert not dest.exists()


def test_trades_file_empty_gzip_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    rewrite_trades(trades, [], raw=_gz(""))

    with pytest.raises(InvalidTradeRowError, match="vacío"):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_trades_header_only_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    rewrite_trades(trades, [])

    with pytest.raises(InvalidTradeRowError, match="sin filas"):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_trades_wrong_header_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    rewrite_trades(
        trades,
        [srow(DAY0_MS, "100.0", "1", 1)],
        header=("a", "b", "c", "d", "e", "f", "g", "h", "i", "j"),
    )

    with pytest.raises(InvalidTradeRowError, match="header"):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_trades_wrong_column_count_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    rewrite_trades(trades, [srow(DAY0_MS, "100.0", "1", 1)[:9]])

    with pytest.raises(InvalidTradeRowError, match="columnas"):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_trades_manifest_schema_version_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    mf_path = trades / "manifest.json"
    mf = json.loads(mf_path.read_text(encoding="utf-8"))
    mf["schema_version"] = "otro-esquema"
    mf_path.write_text(json.dumps(mf, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(CandleError, match="schema_version"):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_trades_file_missing_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    (trades / f"date={DEV_DAY.isoformat()}" / trades_name()).unlink()

    with pytest.raises(HashConflictError, match="ausente"):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_trades_row_count_missing_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    mf_path = trades / "manifest.json"
    mf = json.loads(mf_path.read_text(encoding="utf-8"))
    del mf["files"][trades_name()]["row_count"]
    mf_path.write_text(json.dumps(mf, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(HashConflictError, match="row_count"):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_output_without_manifest_entry_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    transform_day(trades, dest, "ETHUSDT", DEV_DAY)
    mf_path = dest / "manifest.json"
    mf = json.loads(mf_path.read_text(encoding="utf-8"))
    del mf["files"]["ETHUSDT_2024-06-01_1m.csv.gz"]
    mf_path.write_text(json.dumps(mf, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(HashConflictError, match="sin entrada en manifest"):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_output_lineage_changed_fail(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    transform_day(trades, dest, "ETHUSDT", DEV_DAY)
    mf_path = dest / "manifest.json"
    mf = json.loads(mf_path.read_text(encoding="utf-8"))
    mf["files"]["ETHUSDT_2024-06-01_15m.csv.gz"]["source_trades"][0]["sha256"] = "0" * 64
    mf_path.write_text(json.dumps(mf, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(HashConflictError, match="linaje"):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)


def test_mixed_run_rewrites_only_missing(tmp_path: Path) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])
    transform_day(trades, dest, "ETHUSDT", DEV_DAY)
    candle_path(dest, "5m").unlink()

    results = transform_day(trades, dest, "ETHUSDT", DEV_DAY)

    by_tf = {r.timeframe: r.status for r in results}
    assert by_tf["5m"] == "transformed"
    assert sum(1 for r in results if r.status == "transformed") == 1
    assert sum(1 for r in results if r.status == "skipped") == 6
    assert candle_path(dest, "5m").is_file()


def test_write_failure_leaves_no_part(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bronze, trades, dest = tmp_path / "b", tmp_path / "t", tmp_path / "c"
    make_trades(bronze, trades, [("1", str(DAY0_MS), "100.0", "1", "buy")])

    def boom(output_part: Path, expected_candles: int) -> None:
        raise CandleError("forced failure")

    monkeypatch.setattr("infrastructure.medallion.candles._verify_roundtrip", boom)

    with pytest.raises(CandleError, match="forced"):
        transform_day(trades, dest, "ETHUSDT", DEV_DAY)
    assert not list(dest.rglob("*.part"))
    assert not candle_path(dest, "1m").exists()


def test_aggregate_rejects_candle_outside_source_day() -> None:
    with pytest.raises(CandleError, match="fuera del día"):
        _aggregate(
            [(DAY0_MS, "100.0", "1")],
            60_000,
            "ETHUSDT",
            "1m",
            DAY0_MS + 60_000,
            DAY_END_MS,
        )


def test_verify_roundtrip_guards(tmp_path: Path) -> None:
    empty = tmp_path / "e.csv.gz"
    empty.write_bytes(_gz(""))
    with pytest.raises(CandleError, match="vacío"):
        _verify_roundtrip(empty, 1)

    bad_header = tmp_path / "b.csv.gz"
    bad_header.write_bytes(_gz("a,b\n1,2\n"))
    with pytest.raises(CandleError, match="header"):
        _verify_roundtrip(bad_header, 1)

    header_only = tmp_path / "h.csv.gz"
    header_only.write_bytes(_gz(",".join(CANDLE_HEADER) + "\n"))
    with pytest.raises(CandleError, match="!="):
        _verify_roundtrip(header_only, 1)


def test_cli_empty_date_token(tmp_path: Path) -> None:
    rc = candles_cli.main(
        ["--trades-dir", str(tmp_path / "t"), "--dest-dir", str(tmp_path / "c"), "--dates", ","]
    )
    assert rc == 2

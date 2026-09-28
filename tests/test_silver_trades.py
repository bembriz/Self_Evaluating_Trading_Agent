"""Unit tests de la transformación Silver trades canónicos (M4)."""

from __future__ import annotations

import gzip
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from infrastructure.medallion import silver_cli
from infrastructure.medallion.bronze import HashConflictError, download_day, sha256_file
from infrastructure.medallion.silver import (
    ORDERING_FIDELITY,
    SILVER_SCHEMA_VERSION,
    InvalidRowError,
    transform_day,
    transform_days,
)
from infrastructure.medallion.split_guard import SplitGuardError

DEV_DAY = date(2024, 6, 1)
WF_DAY = date(2025, 6, 17)


class Fake:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __call__(self, url: str, dest: Path) -> int:
        dest.write_bytes(self.payload)
        return len(self.payload)


def _gz(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"), mtime=0)


def make_bronze(
    bronze_dir: Path, rows: list[tuple[str, str, str, str, str]], day: date = DEV_DAY
) -> None:
    body = "id,timestamp,price,volume,side\n" + "".join(",".join(row) + "\n" for row in rows)
    download_day(bronze_dir, "ETHUSDT", day, fetcher=Fake(_gz(body)))


def read_silver(path: Path) -> tuple[list[str], list[list[str]]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        lines = fh.read().splitlines()
    header = lines[0].split(",")
    rows = [line.split(",") for line in lines[1:]]
    return header, rows


def test_transform_valid(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    rows = [
        ("10", "1717200000274", "3762.62", "0.07674", "sell"),
        ("11", "1717200000512", "3762.63", "1.5", "buy"),
        ("12", "1717200001000", "3761.00", "0.001", "sell"),
        ("13", "1717200001000", "3761.00", "0.001", "buy"),
    ]
    make_bronze(bronze, rows)

    result = transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    assert result.status == "transformed"
    assert result.rows == 4
    out = silver / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz"
    assert sha256_file(out) == result.sha256
    header, data = read_silver(out)
    assert header == [
        "event_timestamp",
        "symbol",
        "price",
        "quantity",
        "taker_side",
        "native_trade_id",
        "native_sequence",
        "source_file",
        "source_file_sha256",
        "source_row_number",
    ]
    assert len(data) == 4
    first = data[0]
    assert first[0] == "1717200000274"
    assert first[1] == "ETHUSDT"
    assert first[2] == "3762.62"
    assert first[3] == "0.07674"
    assert first[4] == "sell"
    assert first[5] == "10"
    assert first[6] == ""  # native_sequence: no existe en el schema real
    assert first[7] == "date=2024-06-01/ETHUSDT_2024-06-01.csv.gz"
    bronze_sha = sha256_file(bronze / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz")
    assert first[8] == bronze_sha
    assert first[9] == "1"
    assert [r[9] for r in data] == ["1", "2", "3", "4"]

    manifest = json.loads((silver / "manifest.json").read_text())
    entry = manifest["files"]["ETHUSDT_2024-06-01.csv.gz"]
    assert entry["row_count"] == 4
    assert entry["min_timestamp"] == 1717200000274
    assert entry["max_timestamp"] == 1717200001000
    assert entry["schema_version"] == SILVER_SCHEMA_VERSION
    assert entry["ordering_fidelity"] == "PARTIAL"
    assert entry["source_order_preserved"] is True
    assert entry["source_bronze_sha256"] == bronze_sha
    assert entry["output_sha256"] == result.sha256
    assert not list(silver.rglob("*.part"))


def test_decimal_precision_preserved(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    special = [
        ("1", "1000", "0.00000001", "1.000000000000000000", "buy"),
        ("2", "1001", "123456789012345678.987654321012345678", "0.07674", "sell"),
        ("3", "1002", "1.0", "1", "buy"),
    ]
    make_bronze(bronze, special)

    transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    _, data = read_silver(silver / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz")
    for out_row, src in zip(data, special, strict=True):
        assert out_row[2] == src[2], "price debe preservarse byte-a-byte"
        assert out_row[3] == src[3], "quantity debe preservarse byte-a-byte"
        assert Decimal(out_row[2]) == Decimal(src[2])
        assert Decimal(out_row[3]) == Decimal(src[3])
    path = silver / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz"
    raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    assert "e-0" not in raw and "E-0" not in raw and "inf" not in raw


def test_ordering_deterministic(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    rows = [
        ("9", "300", "1.0", "1", "buy"),
        ("8", "100", "1.0", "1", "buy"),
        ("7", "200", "1.0", "1", "buy"),
        ("6", "100", "2.0", "1", "sell"),
    ]
    make_bronze(bronze, rows)

    transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    _, data = read_silver(silver / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz")
    assert [(r[0], r[9]) for r in data] == [
        ("100", "2"),
        ("100", "4"),
        ("200", "3"),
        ("300", "1"),
    ]
    # el orden físico de origen NO coincidía con el canónico → flag en manifest
    manifest = json.loads((silver / "manifest.json").read_text())
    entry = manifest["files"]["ETHUSDT_2024-06-01.csv.gz"]
    assert entry["source_order_preserved"] is False
    assert entry["ordering_fidelity"] == "PARTIAL"


def test_duplicates_preserved(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    dup = ("5", "1717200000274", "3762.62", "0.07674", "sell")
    make_bronze(bronze, [dup, dup, dup])

    result = transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    assert result.rows == 3
    _, data = read_silver(silver / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz")
    assert len(data) == 3
    assert [r[9] for r in data] == ["1", "2", "3"]
    assert len({r[5] for r in data}) == 1  # mismo native_trade_id, distinta fila origen


@pytest.mark.parametrize(
    "bad_row",
    [
        ("1", "100", "1.0", "1", "up"),  # lado inválido
        ("1", "100", "12.3.4", "1", "buy"),  # price no decimal
        ("1", "100", "-1.0", "1", "buy"),  # negativo
        ("1", "100", "NaN", "1", "buy"),  # no numérico
        ("abc", "100", "1.0", "1", "buy"),  # id no entero
        ("1", "nots", "1.0", "1", "buy"),  # timestamp inválido
        ("1", "100", "1e-8", "1", "buy"),  # notación exponencial no canónica
    ],
)
def test_invalid_row_fail_closed(tmp_path: Path, bad_row: tuple[str, str, str, str, str]) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, [("1", "100", "1.0", "1", "buy"), bad_row])

    with pytest.raises(InvalidRowError):
        transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    assert not (silver / "date=2024-06-01").exists()
    assert not (silver / "manifest.json").exists()
    assert not list(silver.rglob("*.part"))


def test_invalid_row_missing_columns(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    body = "id,timestamp,price,volume,side\n1,100,1.0,1\n"
    download_day(bronze, "ETHUSDT", DEV_DAY, fetcher=Fake(_gz(body)))

    with pytest.raises(InvalidRowError, match="columnas"):
        transform_day(bronze, silver, "ETHUSDT", DEV_DAY)
    assert not list(silver.rglob("*date=*"))


def test_wrong_header_fail_closed(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    body = "a,b,c\n1,2,3\n"
    download_day(bronze, "ETHUSDT", DEV_DAY, fetcher=Fake(_gz(body)))

    with pytest.raises(InvalidRowError, match="header"):
        transform_day(bronze, silver, "ETHUSDT", DEV_DAY)
    assert not (silver / "manifest.json").exists()


def test_bronze_hash_mismatch_fail(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, [("1", "100", "1.0", "1", "buy")])
    target = bronze / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz"
    target.write_bytes(target.read_bytes() + b"tamper")

    with pytest.raises(HashConflictError, match="Bronze hash mismatch"):
        transform_day(bronze, silver, "ETHUSDT", DEV_DAY)
    assert not (silver / "date=2024-06-01").exists()


def test_bronze_without_manifest_entry_fail(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, [("1", "100", "1.0", "1", "buy")])
    (bronze / "manifest.json").unlink()

    with pytest.raises(HashConflictError, match="manifest Bronze"):
        transform_day(bronze, silver, "ETHUSDT", DEV_DAY)


def test_part_recovery(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, [("1", "100", "1.0", "1", "buy")])
    stale_dir = silver / "date=2024-06-01"
    stale_dir.mkdir(parents=True)
    stale = stale_dir / "ETHUSDT_2024-06-01.csv.gz.part"
    stale.write_bytes(b"stale basura")

    result = transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    assert result.status == "transformed"
    assert not stale.exists()
    assert (stale_dir / "ETHUSDT_2024-06-01.csv.gz").exists()


def test_run2_idempotent(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, [("1", "100", "1.0", "1", "buy"), ("2", "101", "2.0", "3", "sell")])

    r1 = transform_day(bronze, silver, "ETHUSDT", DEV_DAY)
    out = silver / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz"
    manifest_before = (silver / "manifest.json").read_bytes()
    bytes_before = out.read_bytes()

    r2 = transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    assert r1.status == "transformed"
    assert r2.status == "skipped"
    assert r2.sha256 == r1.sha256
    assert out.read_bytes() == bytes_before
    assert (silver / "manifest.json").read_bytes() == manifest_before
    ops_lines = (silver / "ops-transforms.jsonl").read_text().strip().splitlines()
    assert [json.loads(line)["event"] for line in ops_lines] == [
        "transformed",
        "skipped",
    ]


def test_output_hash_deterministic(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    rows = [("1", "100", "1.0", "1", "buy"), ("2", "200", "2.0", "2", "sell")]
    make_bronze(bronze, rows)
    silver_a = tmp_path / "silver_a"
    silver_b = tmp_path / "silver_b"

    ra = transform_day(bronze, silver_a, "ETHUSDT", DEV_DAY)
    rb = transform_day(bronze, silver_b, "ETHUSDT", DEV_DAY)

    assert ra.sha256 == rb.sha256
    assert (silver_a / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz").read_bytes() == (
        silver_b / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz"
    ).read_bytes()
    ma = json.loads((silver_a / "manifest.json").read_text())
    mb = json.loads((silver_b / "manifest.json").read_text())
    assert ma == mb


def test_silver_output_tamper_fail(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, [("1", "100", "1.0", "1", "buy")])
    transform_day(bronze, silver, "ETHUSDT", DEV_DAY)
    out = silver / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz"
    out.write_bytes(out.read_bytes() + b"x")

    with pytest.raises(HashConflictError, match="alterado"):
        transform_day(bronze, silver, "ETHUSDT", DEV_DAY)


@pytest.mark.parametrize("day", [WF_DAY, date(2026, 3, 15), date(2023, 9, 8)])
def test_split_guard_development_only(tmp_path: Path, day: date) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    with pytest.raises(SplitGuardError):
        transform_day(bronze, silver, "ETHUSDT", day)
    assert not silver.exists()
    assert not bronze.exists()


def test_ordering_fidelity_constant() -> None:
    assert ORDERING_FIDELITY in {"FULL", "PARTIAL"}
    # El archive Spot histórico no trae native_sequence/cross-sequence: no se
    # puede demostrar el orden del matching engine para timestamps iguales.
    assert ORDERING_FIDELITY == "PARTIAL"


def test_cli_two_days_and_idempotent_rerun(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, [("1", "100", "1.0", "1", "buy")])
    make_bronze(bronze, [("2", "200", "2.0", "2", "sell")], date(2024, 6, 2))
    argv = [
        "--bronze-dir",
        str(bronze),
        "--dest-dir",
        str(silver),
        "--dates",
        "2024-06-01,2024-06-02",
    ]

    rc1 = silver_cli.main(argv)
    out1 = capsys.readouterr().out
    rc2 = silver_cli.main(argv)
    out2 = capsys.readouterr().out

    assert rc1 == 0 and rc2 == 0
    assert "SUMMARY transformed=2 skipped=0 total=2" in out1
    assert "SUMMARY transformed=0 skipped=2 total=2" in out2


def test_cli_rejects_walk_forward_date(tmp_path: Path) -> None:
    rc = silver_cli.main(
        [
            "--bronze-dir",
            str(tmp_path / "b"),
            "--dest-dir",
            str(tmp_path / "s"),
            "--dates",
            "2025-06-17",
        ]
    )
    assert rc == 1
    assert not (tmp_path / "s").exists()


def test_cli_bad_date_format(tmp_path: Path) -> None:
    rc = silver_cli.main(
        [
            "--bronze-dir",
            str(tmp_path / "b"),
            "--dest-dir",
            str(tmp_path / "s"),
            "--dates",
            "ayer",
        ]
    )
    assert rc == 2


def test_cli_require_marker(tmp_path: Path) -> None:
    marker = tmp_path / ".lenovosrv-data-volume"
    marker.write_text("LENOVO_DATA\n")
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, [("1", "100", "1.0", "1", "buy")])

    rc_missing = silver_cli.main(
        [
            "--bronze-dir",
            str(bronze),
            "--dest-dir",
            str(silver),
            "--dates",
            "2024-06-01",
            "--require-marker",
            str(tmp_path / "nope"),
        ]
    )
    rc_ok = silver_cli.main(
        [
            "--bronze-dir",
            str(bronze),
            "--dest-dir",
            str(silver),
            "--dates",
            "2024-06-01",
            "--require-marker",
            str(marker),
        ]
    )
    assert rc_missing == 1
    assert rc_ok == 0


def test_transform_days_multiple(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, [("1", "100", "1.0", "1", "buy")])
    make_bronze(bronze, [("2", "200", "2.0", "2", "sell")], date(2024, 6, 2))

    results = transform_days(bronze, silver, "ETHUSDT", [DEV_DAY, date(2024, 6, 2)])

    assert [r.status for r in results] == ["transformed", "transformed"]
    assert len(list(silver.glob("date=*/*.csv.gz"))) == 2

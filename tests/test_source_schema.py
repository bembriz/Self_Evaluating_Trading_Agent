"""Unit tests M9-A1: evolución de schema de la fuente Bybit Spot (V1/V2) + backfill.

La fuente histórica de Bybit Spot cambió de 5 columnas (V1) a 6 columnas con
``rpi`` al final (V2) a partir de 2025-03-13. Reglas obligatorias:

- Detectar el header REAL de cada archivo (nunca asumir columnas fijas).
- V1 y V2 llegan a la misma salida canónica Silver; ``rpi`` jamás se propaga
  ni se reinterpreta.
- Cualquier otro header u orden ⇒ FAIL CLOSED.
- Metadata de Bronze y linaje de Silver se corrigen con backfill determinista
  y atómico, sin tocar los ``.csv.gz`` de origen.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from infrastructure.medallion import schema_backfill_cli
from infrastructure.medallion.bronze import (
    BRONZE_SCHEMA_VERSION,
    SOURCE_SCHEMA_V1,
    SOURCE_SCHEMA_V2,
    BronzeError,
    HashConflictError,
    SchemaBackfillResult,
    SourceSchemaError,
    backfill_source_schema,
    detect_source_schema,
    download_day,
    read_source_schema,
    sha256_file,
)
from infrastructure.medallion.silver import (
    InvalidRowError,
    SilverSchemaBackfillResult,
    transform_day,
)
from infrastructure.medallion.silver import (
    backfill_source_schema as silver_backfill_source_schema,
)
from infrastructure.medallion.split_guard import SplitGuardError

DEV_DAY = date(2024, 6, 1)
V2_DAY = date(2025, 3, 13)  # primer día real con ``rpi`` dentro de DEVELOPMENT
WF_DAY = date(2025, 6, 17)
V1_HEADER = "id,timestamp,price,volume,side"
V2_HEADER = "id,timestamp,price,volume,side,rpi"
RPI_SENTINEL = "424242"


class Fake:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __call__(self, url: str, dest: Path) -> int:
        dest.write_bytes(self.payload)
        return len(self.payload)


def _gz(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"), mtime=0)


def _body(header: str, rows: Sequence[tuple[str, ...]]) -> str:
    return header + "\n" + "".join(",".join(row) + "\n" for row in rows)


def make_bronze(
    bronze_dir: Path, header: str, rows: Sequence[tuple[str, ...]], day: date = DEV_DAY
) -> None:
    download_day(bronze_dir, "ETHUSDT", day, fetcher=Fake(_gz(_body(header, rows))))


def install_bronze(
    bronze_dir: Path,
    body: str,
    day: date,
    *,
    schema_version: str = BRONZE_SCHEMA_VERSION,
) -> Path:
    """Instala un Bronze a mano (bypassa download_day) para escenarios FAIL CLOSED."""
    name = f"ETHUSDT_{day.isoformat()}.csv.gz"
    partition = bronze_dir / f"date={day.isoformat()}"
    partition.mkdir(parents=True, exist_ok=True)
    target = partition / name
    payload = _gz(body)
    target.write_bytes(payload)
    manifest_path = bronze_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"files": {}, "schema_version": BRONZE_SCHEMA_VERSION}
    files = manifest["files"]
    files[name] = {
        "bytes": len(payload),
        "date": day.isoformat(),
        "filename": name,
        "market": "spot",
        "schema_version": schema_version,
        "sha256": sha256_file(target),
        "source_url": f"https://public.bybit.com/spot/ETHUSDT/{name}",
        "symbol": "ETHUSDT",
    }
    manifest["files"] = dict(sorted(files.items()))
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return target


def force_legacy_bronze_metadata(bronze_dir: Path) -> None:
    """Simula el manifest previo a M9-A1: todo marcado como V1."""
    manifest_path = bronze_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"].values():
        entry["schema_version"] = BRONZE_SCHEMA_VERSION
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def strip_silver_lineage_field(silver_dir: Path) -> None:
    """Simula las 551 entradas Silver legacy sin ``source_schema_version``."""
    manifest_path = silver_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"].values():
        entry.pop("source_schema_version", None)
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def silver_output(silver_dir: Path, day: date) -> Path:
    return silver_dir / f"date={day.isoformat()}" / f"ETHUSDT_{day.isoformat()}.csv.gz"


def _read_silver(path: Path) -> tuple[list[str], list[list[str]]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        lines = fh.read().splitlines()
    return lines[0].split(","), [line.split(",") for line in lines[1:]]


def silver_entry(silver_dir: Path, day: date) -> dict[str, object]:
    manifest = json.loads((silver_dir / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["files"][f"ETHUSDT_{day.isoformat()}.csv.gz"]
    assert isinstance(entry, dict)
    return entry


# --------------------------------------------------------------------------
# Detección de schema de la fuente
# --------------------------------------------------------------------------


def test_detect_header_v1_and_v2() -> None:
    assert detect_source_schema(("id", "timestamp", "price", "volume", "side")) == (
        SOURCE_SCHEMA_V1
    )
    assert detect_source_schema(("id", "timestamp", "price", "volume", "side", "rpi")) == (
        SOURCE_SCHEMA_V2
    )
    assert SOURCE_SCHEMA_V1 == BRONZE_SCHEMA_VERSION
    assert SOURCE_SCHEMA_V1 != SOURCE_SCHEMA_V2


@pytest.mark.parametrize(
    "header",
    [
        ("id", "timestamp", "price", "volume", "sideX"),  # 5 cols, nombre cambiado
        ("a", "b", "c", "d", "e"),  # 5 cols desconocidas
        ("id", "timestamp", "price", "volume", "rpi", "side"),  # V2 reordenado
        ("id", "timestamp", "price", "volume", "side", "rpi", "extra"),  # 7 cols
        ("id", "timestamp", "price", "volume"),  # 4 cols
        (),  # vacío
    ],
)
def test_unknown_or_reordered_header_fail_closed(header: tuple[str, ...]) -> None:
    with pytest.raises(SourceSchemaError):
        detect_source_schema(header)


def test_read_source_schema_from_gzip(tmp_path: Path) -> None:
    v1 = tmp_path / "v1.csv.gz"
    v1.write_bytes(_gz(_body(V1_HEADER, [("1", "100", "1.0", "1", "buy")])))
    v2 = tmp_path / "v2.csv.gz"
    v2.write_bytes(_gz(_body(V2_HEADER, [("1", "100", "1.0", "1", "buy", "0")])))

    assert read_source_schema(v1) == SOURCE_SCHEMA_V1
    assert read_source_schema(v2) == SOURCE_SCHEMA_V2


def test_read_source_schema_rejects_empty_and_plain(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv.gz"
    empty.write_bytes(_gz(""))
    plain = tmp_path / "plain.csv.gz"
    plain.write_bytes(b"no soy gzip")

    with pytest.raises(SourceSchemaError):
        read_source_schema(empty)
    with pytest.raises(SourceSchemaError):
        read_source_schema(plain)


# --------------------------------------------------------------------------
# download_day registra el schema real por archivo
# --------------------------------------------------------------------------


def test_download_day_records_v1_schema(tmp_path: Path) -> None:
    make_bronze(tmp_path, V1_HEADER, [("1", "100", "1.0", "1", "buy")])

    entry = json.loads((tmp_path / "manifest.json").read_text())["files"][
        "ETHUSDT_2024-06-01.csv.gz"
    ]
    assert entry["schema_version"] == SOURCE_SCHEMA_V1
    assert entry["schema_version"] == BRONZE_SCHEMA_VERSION


def test_download_day_records_v2_schema(tmp_path: Path) -> None:
    make_bronze(tmp_path, V2_HEADER, [("1", "100", "1.0", "1", "buy", "0")], day=V2_DAY)

    entry = json.loads((tmp_path / "manifest.json").read_text())["files"][
        "ETHUSDT_2025-03-13.csv.gz"
    ]
    assert entry["schema_version"] == SOURCE_SCHEMA_V2
    assert not list(tmp_path.rglob("*.part"))


def test_download_day_unknown_schema_fail_closed(tmp_path: Path) -> None:
    payload = _gz("a,b,c\n1,2,3\n")

    with pytest.raises(SourceSchemaError):
        download_day(tmp_path, "ETHUSDT", DEV_DAY, fetcher=Fake(payload))

    assert not (tmp_path / "date=2024-06-01").exists()
    assert not list(tmp_path.rglob("*.part"))
    assert not (tmp_path / "manifest.json").exists()


# --------------------------------------------------------------------------
# Transformación Silver con V1/V2
# --------------------------------------------------------------------------


def test_transform_v2_records_source_schema_version(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(
        bronze,
        V2_HEADER,
        [
            ("10", "1717200000274", "3762.62", "0.07674", "sell", "0"),
            ("11", "1717200000512", "3762.63", "1.5", "buy", "0"),
        ],
        day=V2_DAY,
    )

    result = transform_day(bronze, silver, "ETHUSDT", V2_DAY)

    assert result.status == "transformed"
    entry = silver_entry(silver, V2_DAY)
    assert entry["source_schema_version"] == SOURCE_SCHEMA_V2
    assert entry["ordering_fidelity"] == "PARTIAL"
    assert entry["row_count"] == 2


def test_transform_refuses_when_manifest_contradicts_file(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    install_bronze(
        bronze,
        _body(V2_HEADER, [("10", "1717200000274", "3762.62", "0.07674", "sell", "0")]),
        V2_DAY,
        schema_version=BRONZE_SCHEMA_VERSION,  # metadata legacy: dice V1, archivo es V2
    )

    with pytest.raises(HashConflictError, match="schema_version"):
        transform_day(bronze, silver, "ETHUSDT", V2_DAY)

    assert not (silver / "date=2025-03-13").exists()
    assert not (silver / "manifest.json").exists()
    assert not list(silver.rglob("*.part"))


def test_transform_v2_unknown_header_fail_closed(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    install_bronze(bronze, "a,b,c\n1,2,3\n", DEV_DAY)

    with pytest.raises(InvalidRowError, match="header"):
        transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    assert not (silver / "manifest.json").exists()
    assert not list(silver.rglob("*.part"))


def test_v2_rpi_not_propagated(tmp_path: Path) -> None:
    """Mismas 5 columnas de datos ⇒ salida Silver idéntica; ``rpi`` jamás aparece."""
    bronze_a = tmp_path / "bronze_a"
    bronze_b = tmp_path / "bronze_b"
    silver_a = tmp_path / "silver_a"
    silver_b = tmp_path / "silver_b"
    rows_v1 = [
        ("10", "1717200000274", "3762.62", "0.07674", "sell"),
        ("11", "1717200000512", "3762.63", "1.5", "buy"),
        ("12", "1717200001000", "3761.00", "0.001", "sell"),
    ]
    rows_v2 = [(*row, RPI_SENTINEL) for row in rows_v1]
    make_bronze(bronze_a, V1_HEADER, rows_v1)
    make_bronze(bronze_b, V2_HEADER, rows_v2)

    transform_day(bronze_a, silver_a, "ETHUSDT", DEV_DAY)
    transform_day(bronze_b, silver_b, "ETHUSDT", DEV_DAY)

    header_a, data_a = _read_silver(silver_output(silver_a, DEV_DAY))
    header_b, data_b = _read_silver(silver_output(silver_b, DEV_DAY))
    assert header_a == header_b
    assert all(len(row) == 10 for row in data_b)
    # solo puede diferir la columna de linaje (source_file_sha256, índice 8)
    assert [row[:8] + row[9:] for row in data_a] == [row[:8] + row[9:] for row in data_b]
    cells = {cell for row in data_b for cell in row}
    assert RPI_SENTINEL not in cells
    assert "rpi" not in header_b


def test_v2_row_wrong_width_fail_closed(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, V2_HEADER, [("10", "1717200000274", "3762.62", "0.07674", "sell")])

    with pytest.raises(InvalidRowError, match="columnas"):
        transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    assert not (silver / "date=2024-06-01").exists()
    assert not (silver / "manifest.json").exists()
    assert not list(silver.rglob("*.part"))


def test_v2_output_hash_deterministic(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    make_bronze(
        bronze,
        V2_HEADER,
        [("1", "100", "1.0", "1", "buy", "0"), ("2", "200", "2.0", "2", "sell", "0")],
    )
    silver_a = tmp_path / "silver_a"
    silver_b = tmp_path / "silver_b"

    ra = transform_day(bronze, silver_a, "ETHUSDT", DEV_DAY)
    rb = transform_day(bronze, silver_b, "ETHUSDT", DEV_DAY)

    assert ra.sha256 == rb.sha256
    assert (
        silver_output(silver_a, DEV_DAY).read_bytes()
        == silver_output(silver_b, DEV_DAY).read_bytes()
    )


# --------------------------------------------------------------------------
# Backfill de metadata Bronze
# --------------------------------------------------------------------------


def test_bronze_backfill_counts_and_fixes(tmp_path: Path) -> None:
    make_bronze(tmp_path, V1_HEADER, [("1", "100", "1.0", "1", "buy")])
    make_bronze(tmp_path, V2_HEADER, [("2", "101", "2.0", "2", "sell", "0")], day=V2_DAY)
    raw_before = {
        p.relative_to(tmp_path).as_posix(): sha256_file(p)
        for p in sorted(tmp_path.rglob("*.csv.gz"))
    }
    force_legacy_bronze_metadata(tmp_path)
    manifest_before_ok = (tmp_path / "manifest.json").read_bytes()

    result = backfill_source_schema(tmp_path)

    assert result == SchemaBackfillResult(scanned=2, changed=1, v1=1, v2=1)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["schema_version"] == BRONZE_SCHEMA_VERSION
    files = manifest["files"]
    assert files["ETHUSDT_2024-06-01.csv.gz"]["schema_version"] == SOURCE_SCHEMA_V1
    assert files["ETHUSDT_2025-03-13.csv.gz"]["schema_version"] == SOURCE_SCHEMA_V2
    assert manifest_before_ok != (tmp_path / "manifest.json").read_bytes()
    raw_after = {
        p.relative_to(tmp_path).as_posix(): sha256_file(p)
        for p in sorted(tmp_path.rglob("*.csv.gz"))
    }
    assert raw_after == raw_before
    assert not list(tmp_path.rglob("*.part"))

    second = backfill_source_schema(tmp_path)
    assert second == SchemaBackfillResult(scanned=2, changed=0, v1=1, v2=1)
    assert (tmp_path / "manifest.json").read_bytes() == json.dumps(
        json.loads((tmp_path / "manifest.json").read_text()),
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ).encode() + b"\n"


def test_bronze_backfill_noop_when_metadata_already_correct(tmp_path: Path) -> None:
    make_bronze(tmp_path, V1_HEADER, [("1", "100", "1.0", "1", "buy")])
    before = (tmp_path / "manifest.json").read_bytes()

    result = backfill_source_schema(tmp_path)

    assert result.changed == 0
    assert (tmp_path / "manifest.json").read_bytes() == before


def test_bronze_backfill_unknown_header_fail_closed(tmp_path: Path) -> None:
    install_bronze(tmp_path, "a,b,c\n1,2,3\n", DEV_DAY)
    manifest_before = (tmp_path / "manifest.json").read_bytes()

    with pytest.raises(SourceSchemaError):
        backfill_source_schema(tmp_path)

    assert (tmp_path / "manifest.json").read_bytes() == manifest_before


def test_bronze_backfill_tampered_raw_fail_closed(tmp_path: Path) -> None:
    make_bronze(tmp_path, V1_HEADER, [("1", "100", "1.0", "1", "buy")])
    target = tmp_path / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz"
    target.write_bytes(target.read_bytes() + b"tamper")
    manifest_before = (tmp_path / "manifest.json").read_bytes()

    with pytest.raises(HashConflictError):
        backfill_source_schema(tmp_path)

    assert (tmp_path / "manifest.json").read_bytes() == manifest_before


def test_bronze_backfill_missing_raw_fail_closed(tmp_path: Path) -> None:
    make_bronze(tmp_path, V1_HEADER, [("1", "100", "1.0", "1", "buy")])
    (tmp_path / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz").unlink()
    manifest_before = (tmp_path / "manifest.json").read_bytes()

    with pytest.raises(HashConflictError):
        backfill_source_schema(tmp_path)

    assert (tmp_path / "manifest.json").read_bytes() == manifest_before


def test_bronze_backfill_rejects_out_of_split_range(tmp_path: Path) -> None:
    install_bronze(tmp_path, _body(V1_HEADER, [("1", "100", "1.0", "1", "buy")]), WF_DAY)
    manifest_before = (tmp_path / "manifest.json").read_bytes()

    with pytest.raises(SplitGuardError):
        backfill_source_schema(tmp_path)

    assert (tmp_path / "manifest.json").read_bytes() == manifest_before


# --------------------------------------------------------------------------
# Backfill de linaje Silver
# --------------------------------------------------------------------------


def test_silver_backfill_adds_source_schema_version(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, V1_HEADER, [("1", "100", "1.0", "1", "buy")])
    make_bronze(bronze, V2_HEADER, [("2", "101", "2.0", "2", "sell", "0")], day=V2_DAY)
    transform_day(bronze, silver, "ETHUSDT", DEV_DAY)
    transform_day(bronze, silver, "ETHUSDT", V2_DAY)
    strip_silver_lineage_field(silver)
    outputs_before = {
        p.name: (sha256_file(p), p.stat().st_mtime_ns) for p in sorted(silver.rglob("*.csv.gz"))
    }

    result = silver_backfill_source_schema(bronze, silver, "ETHUSDT")

    assert result == SilverSchemaBackfillResult(scanned=2, changed=2, v1=1, v2=1)
    assert silver_entry(silver, DEV_DAY)["source_schema_version"] == SOURCE_SCHEMA_V1
    assert silver_entry(silver, V2_DAY)["source_schema_version"] == SOURCE_SCHEMA_V2
    outputs_after = {
        p.name: (sha256_file(p), p.stat().st_mtime_ns) for p in sorted(silver.rglob("*.csv.gz"))
    }
    assert outputs_after == outputs_before
    assert not list(silver.rglob("*.part"))

    second = silver_backfill_source_schema(bronze, silver, "ETHUSDT")
    assert second == SilverSchemaBackfillResult(scanned=2, changed=0, v1=1, v2=1)


def test_silver_backfill_unknown_bronze_header_fail_closed(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, V1_HEADER, [("1", "100", "1.0", "1", "buy")])
    transform_day(bronze, silver, "ETHUSDT", DEV_DAY)
    strip_silver_lineage_field(silver)
    # sustituye el Bronze por un header desconocido y actualiza el linaje registrado
    target = install_bronze(bronze, "a,b,c\n1,2,3\n", DEV_DAY)
    manifest_path = silver / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["files"]["ETHUSDT_2024-06-01.csv.gz"]
    entry["source_bronze_sha256"] = sha256_file(target)
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    manifest_before = manifest_path.read_bytes()

    with pytest.raises(SourceSchemaError):
        silver_backfill_source_schema(bronze, silver, "ETHUSDT")

    assert manifest_path.read_bytes() == manifest_before


def test_silver_backfill_bronze_lineage_mismatch_fail_closed(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, V1_HEADER, [("1", "100", "1.0", "1", "buy")])
    transform_day(bronze, silver, "ETHUSDT", DEV_DAY)
    strip_silver_lineage_field(silver)
    (bronze / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz").write_bytes(b"basura")
    manifest_before = (silver / "manifest.json").read_bytes()

    with pytest.raises(HashConflictError):
        silver_backfill_source_schema(bronze, silver, "ETHUSDT")

    assert (silver / "manifest.json").read_bytes() == manifest_before


def test_silver_backfill_rejects_out_of_split_range(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    silver.mkdir()
    manifest_path = silver / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "files": {
                    "ETHUSDT_2025-06-17.csv.gz": {
                        "date": "2025-06-17",
                        "filename": "ETHUSDT_2025-06-17.csv.gz",
                        "source_bronze_path": "date=2025-06-17/ETHUSDT_2025-06-17.csv.gz",
                        "source_bronze_sha256": "a" * 64,
                        "symbol": "ETHUSDT",
                    }
                },
                "schema_version": "bybit-spot-trades-silver-v1",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_before = manifest_path.read_bytes()

    with pytest.raises(SplitGuardError):
        silver_backfill_source_schema(tmp_path / "bronze", silver, "ETHUSDT")

    assert manifest_path.read_bytes() == manifest_before


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    make_bronze(bronze, V1_HEADER, [("1", "100", "1.0", "1", "buy")])
    make_bronze(bronze, V2_HEADER, [("2", "101", "2.0", "2", "sell", "0")], day=V2_DAY)
    transform_day(bronze, silver, "ETHUSDT", DEV_DAY)
    transform_day(bronze, silver, "ETHUSDT", V2_DAY)
    force_legacy_bronze_metadata(bronze)
    strip_silver_lineage_field(silver)
    return bronze, silver


def test_cli_backfill_all(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bronze, silver = _fixture(tmp_path)

    rc = schema_backfill_cli.main(["--bronze-dir", str(bronze), "--dest-dir", str(silver)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "BRONZE_V1_FILES=1" in out
    assert "BRONZE_V2_FILES=1" in out
    assert "BRONZE_ENTRIES_CHANGED=1" in out
    assert "SILVER_ENTRIES_CHANGED=2" in out
    assert "SILVER_SOURCE_SCHEMA_V1=1" in out
    assert "SILVER_SOURCE_SCHEMA_V2=1" in out


def test_cli_layer_bronze_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bronze, silver = _fixture(tmp_path)
    silver_before = (silver / "manifest.json").read_bytes()

    rc = schema_backfill_cli.main(
        ["--bronze-dir", str(bronze), "--dest-dir", str(silver), "--layer", "bronze"]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "BRONZE_V1_FILES=1" in out
    assert "SILVER_ENTRIES_CHANGED" not in out
    assert (silver / "manifest.json").read_bytes() == silver_before


def test_cli_requires_marker(tmp_path: Path) -> None:
    bronze, silver = _fixture(tmp_path)
    bronze_before = (bronze / "manifest.json").read_bytes()

    rc = schema_backfill_cli.main(
        ["--bronze-dir", str(bronze), "--dest-dir", str(silver), "--require-marker", "/nope"]
    )

    assert rc == 1
    assert (bronze / "manifest.json").read_bytes() == bronze_before


def test_cli_fail_closed_on_unknown_header(tmp_path: Path) -> None:
    bronze, silver = _fixture(tmp_path)
    install_bronze(bronze, "a,b,c\n1,2,3\n", date(2024, 6, 2))
    bronze_before = (bronze / "manifest.json").read_bytes()

    rc = schema_backfill_cli.main(["--bronze-dir", str(bronze), "--dest-dir", str(silver)])

    assert rc == 1
    assert (bronze / "manifest.json").read_bytes() == bronze_before


def test_cli_bad_layer_value() -> None:
    with pytest.raises(SystemExit) as exc:
        schema_backfill_cli.main(
            ["--bronze-dir", "/tmp/b", "--dest-dir", "/tmp/s", "--layer", "gold"]
        )
    assert exc.value.code == 2


# --------------------------------------------------------------------------
# FAIL CLOSED de manifiestos mal formados y de transformación
# --------------------------------------------------------------------------


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _write_silver_manifest(silver_dir: Path, files: dict[str, object]) -> None:
    silver_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        silver_dir / "manifest.json",
        {"files": files, "schema_version": "bybit-spot-trades-silver-v1"},
    )


def test_bronze_backfill_rejects_malformed_entry(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "manifest.json",
        {"files": {"ETHUSDT_2024-06-01.csv.gz": "basura"}, "schema_version": BRONZE_SCHEMA_VERSION},
    )

    with pytest.raises(BronzeError, match="entrada inválida"):
        backfill_source_schema(tmp_path)


def test_bronze_backfill_rejects_incomplete_entry(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "manifest.json",
        {
            "files": {"ETHUSDT_2024-06-01.csv.gz": {"date": "2024-06-01"}},
            "schema_version": BRONZE_SCHEMA_VERSION,
        },
    )

    with pytest.raises(BronzeError, match="incompleta"):
        backfill_source_schema(tmp_path)


def test_bronze_backfill_rejects_invalid_date(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "manifest.json",
        {
            "files": {
                "ETHUSDT_2024-06-01.csv.gz": {
                    "date": "ayer",
                    "filename": "ETHUSDT_2024-06-01.csv.gz",
                    "schema_version": BRONZE_SCHEMA_VERSION,
                    "sha256": "a" * 64,
                    "symbol": "ETHUSDT",
                }
            },
            "schema_version": BRONZE_SCHEMA_VERSION,
        },
    )

    with pytest.raises(BronzeError, match="fecha inválida"):
        backfill_source_schema(tmp_path)


def test_silver_backfill_rejects_malformed_entry(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    _write_silver_manifest(silver, {"ETHUSDT_2024-06-01.csv.gz": "basura"})

    with pytest.raises(BronzeError, match="entrada inválida"):
        silver_backfill_source_schema(tmp_path / "bronze", silver, "ETHUSDT")


def test_silver_backfill_rejects_incomplete_entry(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    _write_silver_manifest(silver, {"ETHUSDT_2024-06-01.csv.gz": {"date": "2024-06-01"}})

    with pytest.raises(BronzeError, match="incompleta"):
        silver_backfill_source_schema(tmp_path / "bronze", silver, "ETHUSDT")


def test_silver_backfill_rejects_invalid_date(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    _write_silver_manifest(
        silver,
        {
            "ETHUSDT_2024-06-01.csv.gz": {
                "date": "ayer",
                "filename": "ETHUSDT_2024-06-01.csv.gz",
                "source_bronze_path": "date=2024-06-01/ETHUSDT_2024-06-01.csv.gz",
                "source_bronze_sha256": "a" * 64,
            }
        },
    )

    with pytest.raises(BronzeError, match="fecha inválida"):
        silver_backfill_source_schema(tmp_path / "bronze", silver, "ETHUSDT")


def test_silver_backfill_rejects_path_traversal(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    _write_silver_manifest(
        silver,
        {
            "ETHUSDT_2024-06-01.csv.gz": {
                "date": "2024-06-01",
                "filename": "ETHUSDT_2024-06-01.csv.gz",
                "source_bronze_path": "../../etc/passwd",
                "source_bronze_sha256": "a" * 64,
            }
        },
    )
    manifest_before = (silver / "manifest.json").read_bytes()

    with pytest.raises(BronzeError, match="source_bronze_path"):
        silver_backfill_source_schema(tmp_path / "bronze", silver, "ETHUSDT")

    assert (silver / "manifest.json").read_bytes() == manifest_before


def test_silver_backfill_missing_bronze_source_fail_closed(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    _write_silver_manifest(
        silver,
        {
            "ETHUSDT_2024-06-01.csv.gz": {
                "date": "2024-06-01",
                "filename": "ETHUSDT_2024-06-01.csv.gz",
                "source_bronze_path": "date=2024-06-01/ETHUSDT_2024-06-01.csv.gz",
                "source_bronze_sha256": "a" * 64,
            }
        },
    )
    manifest_before = (silver / "manifest.json").read_bytes()

    with pytest.raises(HashConflictError, match="ausente"):
        silver_backfill_source_schema(tmp_path / "bronze", silver, "ETHUSDT")

    assert (silver / "manifest.json").read_bytes() == manifest_before


def test_transform_empty_bronze_fail_closed(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    install_bronze(bronze, "", DEV_DAY)

    with pytest.raises(InvalidRowError, match="vacío"):
        transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    assert not (silver / "manifest.json").exists()


def test_transform_header_only_fail_closed(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    install_bronze(bronze, V1_HEADER + "\n", DEV_DAY)

    with pytest.raises(InvalidRowError, match="sin filas"):
        transform_day(bronze, silver, "ETHUSDT", DEV_DAY)

    assert not (silver / "manifest.json").exists()

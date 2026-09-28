"""Unit tests del dataset Gold de replay (M6)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from infrastructure.medallion import gold, gold_cli
from infrastructure.medallion.gold import (
    GOLD_MANIFEST_VERSION,
    MANIFEST_FILENAME,
    REPLAY_CONFIG_FILENAME,
    GoldError,
    GoldResult,
    build_replay_config,
    compute_dataset_id,
    create_dataset,
)
from infrastructure.medallion.split_guard import SplitGuardError

DAYS = [date(2024, 6, 1), date(2024, 6, 2), date(2024, 6, 3)]
WF_DAY = date(2025, 6, 17)
TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")
TRADES_SCHEMA = "bybit-spot-trades-silver-v1"
CANDLES_SCHEMA = "bybit-spot-candles-silver-v1"


def _canon(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_silver(root: Path) -> tuple[Path, Path]:
    """Silver trades + candles sintéticos con layout canónico bajo root."""
    trades_dir = root / "silver" / "trades" / "ETHUSDT"
    candles_dir = root / "silver" / "candles" / "ETHUSDT"
    trades_manifest: dict[str, object] = {"schema_version": TRADES_SCHEMA, "files": {}}
    tfiles = trades_manifest["files"]
    assert isinstance(tfiles, dict)
    for i, day in enumerate(DAYS):
        name = f"ETHUSDT_{day.isoformat()}.csv.gz"
        rel = f"date={day.isoformat()}/{name}"
        path = trades_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"trades-{day.isoformat()}".encode()
        path.write_bytes(payload)
        tfiles[name] = {
            "date": day.isoformat(),
            "filename": name,
            "output_path": rel,
            "output_sha256": _sha(payload),
            "row_count": 100 + i,
            "ordering_fidelity": "PARTIAL",
            "source_order_preserved": True,
            "schema_version": TRADES_SCHEMA,
        }
    trades_dir.mkdir(parents=True, exist_ok=True)
    (trades_dir / "manifest.json").write_bytes(_canon(trades_manifest))

    candles_manifest: dict[str, object] = {"schema_version": CANDLES_SCHEMA, "files": {}}
    cfiles = candles_manifest["files"]
    assert isinstance(cfiles, dict)
    for day in DAYS:
        tentry = tfiles[f"ETHUSDT_{day.isoformat()}.csv.gz"]
        assert isinstance(tentry, dict)
        for tf in TIMEFRAMES:
            name = f"ETHUSDT_{day.isoformat()}_{tf}.csv.gz"
            rel = f"timeframe={tf}/date={day.isoformat()}/{name}"
            path = candles_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = f"candle-{day.isoformat()}-{tf}".encode()
            path.write_bytes(payload)
            cfiles[name] = {
                "date": day.isoformat(),
                "timeframe": tf,
                "filename": name,
                "output_path": rel,
                "output_sha256": _sha(payload),
                "candle_count": 42,
                "schema_version": CANDLES_SCHEMA,
                "source_trades": [
                    {"path": tentry["output_path"], "sha256": tentry["output_sha256"]}
                ],
            }
    candles_dir.mkdir(parents=True, exist_ok=True)
    (candles_dir / "manifest.json").write_bytes(_canon(candles_manifest))
    return trades_dir, candles_dir


def _dirs(root: Path) -> tuple[Path, Path, Path]:
    trades_dir, candles_dir = make_silver(root)
    dest_dir = root / "gold" / "replay-datasets" / "ETHUSDT"
    return trades_dir, candles_dir, dest_dir


def _load_manifest(dest_dir: Path, dataset_id: str) -> dict[str, object]:
    raw = (dest_dir / dataset_id / MANIFEST_FILENAME).read_bytes()
    data = json.loads(raw)
    assert isinstance(data, dict)
    return data


# ---------------------------------------------------------------- dataset_id


def test_dataset_id_determinista(tmp_path: Path) -> None:
    trades_a, candles_a, dest_a = _dirs(tmp_path / "a")
    trades_b, candles_b, dest_b = _dirs(tmp_path / "b")
    res_a = create_dataset(trades_a, candles_a, dest_a, "ETHUSDT", DAYS)
    res_b = create_dataset(trades_b, candles_b, dest_b, "ETHUSDT", list(reversed(DAYS)))
    assert isinstance(res_a, GoldResult)
    assert res_a.dataset_id == res_b.dataset_id
    assert res_a.dataset_id.startswith("gold-replay-")
    assert len(res_a.dataset_id.removeprefix("gold-replay-")) == 64


def test_dataset_id_cambia_con_contenido(tmp_path: Path) -> None:
    trades_a, candles_a, dest_a = _dirs(tmp_path / "a")
    trades_b, candles_b, dest_b = _dirs(tmp_path / "b")
    res_a = create_dataset(trades_a, candles_a, dest_a, "ETHUSDT", DAYS)
    payload = (trades_b / "date=2024-06-02" / "ETHUSDT_2024-06-02.csv.gz").read_bytes()
    tampered = payload + b"-distinto"
    (trades_b / "date=2024-06-02" / "ETHUSDT_2024-06-02.csv.gz").write_bytes(tampered)
    nuevo_sha = _sha(tampered)
    manifest_path = trades_b / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    assert isinstance(manifest, dict)
    files = manifest["files"]
    assert isinstance(files, dict)
    entry = files["ETHUSDT_2024-06-02.csv.gz"]
    assert isinstance(entry, dict)
    entry["output_sha256"] = nuevo_sha
    manifest_path.write_bytes(_canon(manifest))
    candles_path = candles_b / "manifest.json"
    candles_manifest = json.loads(candles_path.read_bytes())
    assert isinstance(candles_manifest, dict)
    cfiles = candles_manifest["files"]
    assert isinstance(cfiles, dict)
    for name, centry in cfiles.items():
        assert isinstance(centry, dict)
        if str(name).startswith("ETHUSDT_2024-06-02_"):
            centry["source_trades"] = [
                {"path": "date=2024-06-02/ETHUSDT_2024-06-02.csv.gz", "sha256": nuevo_sha}
            ]
    candles_path.write_bytes(_canon(candles_manifest))
    res_b = create_dataset(trades_b, candles_b, dest_b, "ETHUSDT", DAYS)
    assert res_a.dataset_id != res_b.dataset_id


def test_canonical_json_determinista(tmp_path: Path) -> None:
    trades_a, candles_a, dest_a = _dirs(tmp_path / "a")
    trades_b, candles_b, dest_b = _dirs(tmp_path / "b")
    res_a = create_dataset(trades_a, candles_a, dest_a, "ETHUSDT", DAYS)
    res_b = create_dataset(trades_b, candles_b, dest_b, "ETHUSDT", DAYS)
    bytes_a = (dest_a / res_a.dataset_id / MANIFEST_FILENAME).read_bytes()
    bytes_b = (dest_b / res_b.dataset_id / MANIFEST_FILENAME).read_bytes()
    assert bytes_a == bytes_b
    cfg_a = (dest_a / res_a.dataset_id / REPLAY_CONFIG_FILENAME).read_bytes()
    cfg_b = (dest_b / res_b.dataset_id / REPLAY_CONFIG_FILENAME).read_bytes()
    assert cfg_a == cfg_b


def test_compute_dataset_id_solo_hash_canonico() -> None:
    identity = {"a": 1, "b": [1, 2]}
    dataset_id = compute_dataset_id(identity)
    expected = "gold-replay-" + hashlib.sha256(_canon(identity)).hexdigest()
    assert dataset_id == expected
    assert compute_dataset_id({"b": [1, 2], "a": 1}) == dataset_id


# ------------------------------------------------------- validación de input


def test_input_hash_mismatch_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    target = trades_dir / "date=2024-06-01" / "ETHUSDT_2024-06-01.csv.gz"
    target.write_bytes(target.read_bytes() + b"x")
    with pytest.raises(GoldError):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_input_hash_mismatch_candles_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    target = candles_dir / "timeframe=5m" / "date=2024-06-03" / "ETHUSDT_2024-06-03_5m.csv.gz"
    target.write_bytes(target.read_bytes() + b"x")
    with pytest.raises(GoldError):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_lineage_mismatch_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    manifest_path = candles_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    assert isinstance(manifest, dict)
    files = manifest["files"]
    assert isinstance(files, dict)
    entry = files["ETHUSDT_2024-06-01_1m.csv.gz"]
    assert isinstance(entry, dict)
    entry["source_trades"] = [{"path": "date=2024-06-01/otro.csv.gz", "sha256": "0" * 64}]
    manifest_path.write_bytes(_canon(manifest))
    with pytest.raises(GoldError):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_missing_trades_partition_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    (trades_dir / "date=2024-06-02" / "ETHUSDT_2024-06-02.csv.gz").unlink()
    with pytest.raises(GoldError):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_missing_trades_manifest_entry_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    manifest_path = trades_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    assert isinstance(manifest, dict)
    files = manifest["files"]
    assert isinstance(files, dict)
    del files["ETHUSDT_2024-06-03.csv.gz"]
    manifest_path.write_bytes(_canon(manifest))
    with pytest.raises(GoldError):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_missing_candle_output_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    (candles_dir / "timeframe=1h" / "date=2024-06-02" / "ETHUSDT_2024-06-02_1h.csv.gz").unlink()
    with pytest.raises(GoldError):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_missing_candle_manifest_entry_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    manifest_path = candles_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    assert isinstance(manifest, dict)
    files = manifest["files"]
    assert isinstance(files, dict)
    del files["ETHUSDT_2024-06-01_4h.csv.gz"]
    manifest_path.write_bytes(_canon(manifest))
    with pytest.raises(GoldError):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_missing_candles_manifest_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    (candles_dir / "manifest.json").unlink()
    with pytest.raises(GoldError):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


# ------------------------------------------------- inmutabilidad / idempotencia


def test_rerun_idempotente_skip(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    first = create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert first.status == "created"
    manifest_bytes = (dest_dir / first.dataset_id / MANIFEST_FILENAME).read_bytes()
    config_bytes = (dest_dir / first.dataset_id / REPLAY_CONFIG_FILENAME).read_bytes()
    second = create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert second.status == "skipped"
    assert second.dataset_id == first.dataset_id
    assert (dest_dir / first.dataset_id / MANIFEST_FILENAME).read_bytes() == manifest_bytes
    assert (dest_dir / first.dataset_id / REPLAY_CONFIG_FILENAME).read_bytes() == config_bytes
    assert sorted(p.name for p in dest_dir.iterdir()) == sorted(
        ["ops-gold.jsonl", first.dataset_id]
    )


def test_existing_dataset_distinto_contenido_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    res = create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    manifest_path = dest_dir / res.dataset_id / MANIFEST_FILENAME
    corrupto = json.loads(manifest_path.read_bytes())
    assert isinstance(corrupto, dict)
    corrupto["symbol"] = "BTCUSDT"
    manifest_path.write_bytes(_canon(corrupto))
    with pytest.raises(GoldError):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)


def test_dataset_dir_inmutable_por_rerun(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    res = create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    dataset_dir = dest_dir / res.dataset_id
    antes = {p.name: p.read_bytes() for p in dataset_dir.iterdir()}
    create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    despues = {p.name: p.read_bytes() for p in dataset_dir.iterdir()}
    assert antes == despues


# ----------------------------------------------------------------- guards


def test_split_guard_development_antes_de_leer(tmp_path: Path) -> None:
    dest_dir = tmp_path / "gold" / "replay-datasets" / "ETHUSDT"
    with pytest.raises(SplitGuardError):
        create_dataset(
            tmp_path / "no-existe",
            tmp_path / "no-existe",
            dest_dir,
            "ETHUSDT",
            [WF_DAY],
        )
    assert not dest_dir.exists()


def test_split_guard_holdout(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    with pytest.raises(SplitGuardError):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", [date(2026, 4, 1)])
    assert not dest_dir.exists()


# ------------------------------------------------------------ manifest/config


def test_manifest_campos_minimos(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    res = create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    manifest = _load_manifest(dest_dir, res.dataset_id)
    assert manifest["manifest_version"] == GOLD_MANIFEST_VERSION
    assert manifest["dataset_id"] == res.dataset_id
    assert manifest["symbol"] == "ETHUSDT"
    assert manifest["allowed_split"] == "DEVELOPMENT"
    assert manifest["date_range"] == {"start": "2024-06-01", "end": "2024-06-03"}
    assert manifest["timeframes"] == list(TIMEFRAMES)

    trades = manifest["trades"]
    assert isinstance(trades, dict)
    assert trades["schema_version"] == TRADES_SCHEMA
    assert trades["ordering_fidelity"] == "PARTIAL"
    assert trades["source_order_preserved"] is True
    partitions = trades["partitions"]
    assert isinstance(partitions, list)
    assert len(partitions) == 3
    for part in partitions:
        assert isinstance(part, dict)
        assert set(part) == {"date", "path", "sha256", "row_count"}
        assert len(str(part["sha256"])) == 64

    candles = manifest["candles"]
    assert isinstance(candles, dict)
    assert candles["schema_version"] == CANDLES_SCHEMA
    outputs = candles["outputs"]
    assert isinstance(outputs, list)
    assert len(outputs) == 21
    for out in outputs:
        assert isinstance(out, dict)
        assert set(out) == {"date", "timeframe", "path", "sha256", "candle_count"}
    by_tf = candles["candle_count_by_timeframe"]
    assert isinstance(by_tf, dict)
    assert sorted(by_tf) == sorted(TIMEFRAMES)

    lineage = manifest["lineage"]
    assert isinstance(lineage, dict)
    assert lineage["verified"] is True
    assert lineage["trade_partitions_referenced"] == 3
    assert lineage["candle_outputs_referenced"] == 21

    replay_ref = manifest["replay_config"]
    assert isinstance(replay_ref, dict)
    cfg_bytes = (dest_dir / res.dataset_id / REPLAY_CONFIG_FILENAME).read_bytes()
    assert replay_ref == {"filename": REPLAY_CONFIG_FILENAME, "sha256": _sha(cfg_bytes)}
    assert res.manifest_sha256 == _sha((dest_dir / res.dataset_id / MANIFEST_FILENAME).read_bytes())


def test_manifest_referencia_3_trades_21_candles(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    res = create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    manifest = _load_manifest(dest_dir, res.dataset_id)
    trades = manifest["trades"]
    assert isinstance(trades, dict)
    partitions = trades["partitions"]
    assert isinstance(partitions, list)
    for part in partitions:
        assert isinstance(part, dict)
        path = trades_dir / str(part["path"])
        assert path.is_file()
        assert _sha(path.read_bytes()) == part["sha256"]
    candles = manifest["candles"]
    assert isinstance(candles, dict)
    outputs = candles["outputs"]
    assert isinstance(outputs, list)
    for out in outputs:
        assert isinstance(out, dict)
        path = candles_dir / str(out["path"])
        assert path.is_file()
        assert _sha(path.read_bytes()) == out["sha256"]


def test_no_wall_clock_fields(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    res = create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    forbidden = {"at", "created_at", "generated_at", "now", "timestamp", "wall_clock"}
    dataset_dir = dest_dir / res.dataset_id
    assert sorted(p.name for p in dataset_dir.iterdir()) == [
        MANIFEST_FILENAME,
        REPLAY_CONFIG_FILENAME,
    ]
    for name in (MANIFEST_FILENAME, REPLAY_CONFIG_FILENAME):
        data = json.loads((dataset_dir / name).read_bytes())

        def _walk(node: object, path: str, filename: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    assert key not in forbidden, (filename, path, key)
                    _walk(value, f"{path}.{key}", filename)
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    _walk(item, f"{path}[{i}]", filename)

        _walk(data, "$", name)


def test_ops_log_fuera_del_dataset(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    res = create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    ops = dest_dir / "ops-gold.jsonl"
    assert ops.is_file()
    assert (dest_dir / res.dataset_id / "ops-gold.jsonl").exists() is False
    eventos = [json.loads(line) for line in ops.read_text().splitlines()]
    assert len(eventos) == 1
    assert eventos[0]["dataset_id"] == res.dataset_id
    assert eventos[0]["status"] == "created"
    assert "at" in eventos[0]


# ---------------------------------------------------------------- replay config


def test_replay_config_esperado() -> None:
    cfg = build_replay_config()
    assert cfg["decision_timeframe"] == "15m"
    assert cfg["context_timeframes"] == ["1h", "4h"]
    assert cfg["execution_source"] == "silver_trades"
    assert cfg["execution_model"] == "TRADE_SEQUENCE_TAKER_PROXY"
    assert cfg["candle_visibility"] == "confirmed_close_only"
    assert "after the confirmed candle close" in str(cfg["decision_rule"])
    assert "first eligible trade" in str(cfg["fill_rule"])
    limitations = cfg["limitations"]
    assert isinstance(limitations, list)
    joined = " ".join(str(item) for item in limitations)
    for token in ("bid/ask", "depth", "queue", "market impact", "latency"):
        assert token in joined
    assert cfg["strategy_params_included"] is False
    assert cfg["risk_params_included"] is False
    assert "strategy_version" not in cfg
    assert "risk_version" not in cfg


# ---------------------------------------------------------------------- CLI


def _cli_args(
    trades_dir: Path,
    candles_dir: Path,
    dest_dir: Path,
    extra: list[str] | None = None,
) -> list[str]:
    args = [
        "--trades-dir",
        str(trades_dir),
        "--candles-dir",
        str(candles_dir),
        "--dest-dir",
        str(dest_dir),
        "--dates",
        "2024-06-01,2024-06-02,2024-06-03",
    ]
    if extra:
        args.extend(extra)
    return args


def test_cli_created_and_skip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    base = _cli_args(trades_dir, candles_dir, dest_dir)
    rc1 = gold_cli.main(base)
    out1 = capsys.readouterr()
    assert rc1 == 0, out1.err
    assert "SUMMARY created=1 skipped=0" in out1.out
    dataset_dirs = [p for p in dest_dir.iterdir() if p.is_dir()]
    assert len(dataset_dirs) == 1
    manifest = json.loads((dataset_dirs[0] / MANIFEST_FILENAME).read_bytes())
    assert isinstance(manifest, dict)
    assert manifest["dataset_id"] == dataset_dirs[0].name
    assert dataset_dirs[0].name in out1.out
    rc2 = gold_cli.main(base)
    out2 = capsys.readouterr()
    assert rc2 == 0, out2.err
    assert "SUMMARY created=0 skipped=1" in out2.out


def test_cli_fecha_invalida_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    args = _cli_args(trades_dir, candles_dir, dest_dir)
    args[-1] = "ayer"
    rc = gold_cli.main(args)
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR" in captured.err
    args[-1] = "2024-06-01,,2024-06-02"
    rc2 = gold_cli.main(args)
    captured2 = capsys.readouterr()
    assert rc2 == 2
    assert "fecha vacía" in captured2.err


def test_cli_split_guard_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    args = _cli_args(trades_dir, candles_dir, dest_dir)
    args[-1] = "2025-06-17"
    rc = gold_cli.main(args)
    captured = capsys.readouterr()
    assert rc == 1
    assert "DEVELOPMENT" in captured.err
    assert not dest_dir.exists()


def test_cli_marker_ausente_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    args = _cli_args(
        trades_dir, candles_dir, dest_dir, ["--require-marker", str(tmp_path / "no-marker")]
    )
    rc = gold_cli.main(args)
    captured = capsys.readouterr()
    assert rc == 1
    assert "ERROR" in captured.err
    assert not dest_dir.exists()


# ------------------------------------------------------- ramas de error FAIL CLOSED


def _edit_trades_manifest(trades_dir: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    path = trades_dir / "manifest.json"
    manifest = json.loads(path.read_bytes())
    mutate(manifest)
    path.write_bytes(_canon(manifest))


def _edit_candles_manifest(candles_dir: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    path = candles_dir / "manifest.json"
    manifest = json.loads(path.read_bytes())
    mutate(manifest)
    path.write_bytes(_canon(manifest))


def test_manifest_trades_ilegible(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    (trades_dir / "manifest.json").write_bytes(b"{no-json")
    with pytest.raises(GoldError, match="ilegible"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_manifest_estructura_invalida(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    (trades_dir / "manifest.json").write_bytes(_canon({"files": "nope"}))
    with pytest.raises(GoldError, match="estructura"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_trades_schema_mismatch(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)

    def mutate(manifest: dict[str, object]) -> None:
        manifest["schema_version"] = "otra-v"

    _edit_trades_manifest(trades_dir, mutate)
    with pytest.raises(GoldError, match="schema_version"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_candles_schema_mismatch(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)

    def mutate(manifest: dict[str, object]) -> None:
        manifest["schema_version"] = "otra-v"

    _edit_candles_manifest(candles_dir, mutate)
    with pytest.raises(GoldError, match="schema_version"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_fidelity_invalida(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)

    def mutate(manifest: dict[str, object]) -> None:
        files = manifest["files"]
        assert isinstance(files, dict)
        entry = files["ETHUSDT_2024-06-01.csv.gz"]
        assert isinstance(entry, dict)
        entry["ordering_fidelity"] = "NONE"

    _edit_trades_manifest(trades_dir, mutate)
    with pytest.raises(GoldError, match="ordering_fidelity"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_fidelity_mixta_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)

    def mutate(manifest: dict[str, object]) -> None:
        files = manifest["files"]
        assert isinstance(files, dict)
        entry = files["ETHUSDT_2024-06-01.csv.gz"]
        assert isinstance(entry, dict)
        entry["ordering_fidelity"] = "FULL"

    _edit_trades_manifest(trades_dir, mutate)
    with pytest.raises(GoldError, match="mixta"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_source_order_preserved_invalida(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)

    def mutate(manifest: dict[str, object]) -> None:
        files = manifest["files"]
        assert isinstance(files, dict)
        entry = files["ETHUSDT_2024-06-01.csv.gz"]
        assert isinstance(entry, dict)
        entry["source_order_preserved"] = "si"

    _edit_trades_manifest(trades_dir, mutate)
    with pytest.raises(GoldError, match="source_order_preserved"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_row_count_invalido(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)

    def mutate(manifest: dict[str, object]) -> None:
        files = manifest["files"]
        assert isinstance(files, dict)
        entry = files["ETHUSDT_2024-06-01.csv.gz"]
        assert isinstance(entry, dict)
        entry["row_count"] = -1

    _edit_trades_manifest(trades_dir, mutate)
    with pytest.raises(GoldError, match="row_count"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_candle_count_invalido(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)

    def mutate(manifest: dict[str, object]) -> None:
        files = manifest["files"]
        assert isinstance(files, dict)
        entry = files["ETHUSDT_2024-06-01_1m.csv.gz"]
        assert isinstance(entry, dict)
        entry["candle_count"] = True

    _edit_candles_manifest(candles_dir, mutate)
    with pytest.raises(GoldError, match="candle_count"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_output_sha_invalido(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)

    def mutate(manifest: dict[str, object]) -> None:
        files = manifest["files"]
        assert isinstance(files, dict)
        entry = files["ETHUSDT_2024-06-01.csv.gz"]
        assert isinstance(entry, dict)
        entry["output_sha256"] = "abc"

    _edit_trades_manifest(trades_dir, mutate)
    with pytest.raises(GoldError, match="output_sha256"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
    assert not dest_dir.exists()


def test_dias_vacios_fail(tmp_path: Path) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    with pytest.raises(GoldError, match="al menos una fecha"):
        create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", [])
    assert not dest_dir.exists()


def test_roundtrip_fail_limpia_part(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trades_dir, candles_dir, dest_dir = _dirs(tmp_path)
    original = Path.write_bytes

    def make_corrupt(target: str) -> Callable[[Path, bytes], int]:
        def corrupt(self: Path, data: bytes) -> int:
            if self.name == target and ".part" in self.parent.name:
                return original(self, data + b"X")
            return original(self, data)

        return corrupt

    for target in (MANIFEST_FILENAME, REPLAY_CONFIG_FILENAME):
        monkeypatch.setattr(Path, "write_bytes", make_corrupt(target))
        with pytest.raises(GoldError, match="round-trip"):
            create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", DAYS)
        assert not list(dest_dir.glob("*.part"))
        assert not list(dest_dir.glob("gold-replay-*"))


def test_part_stale_eliminado(tmp_path: Path) -> None:
    trades_a, candles_a, dest_a = _dirs(tmp_path / "a")
    res = create_dataset(trades_a, candles_a, dest_a, "ETHUSDT", DAYS)
    trades_b, candles_b, dest_b = _dirs(tmp_path / "b")
    stale = dest_b / f"{res.dataset_id}.part"
    stale.mkdir(parents=True)
    (stale / "basura.txt").write_bytes(b"basura")
    res_b = create_dataset(trades_b, candles_b, dest_b, "ETHUSDT", DAYS)
    assert res_b.status == "created"
    assert res_b.dataset_id == res.dataset_id
    assert not stale.exists()
    assert (dest_b / res.dataset_id / MANIFEST_FILENAME).is_file()


def test_module_exports() -> None:
    for name in ("GoldError", "GoldResult", "create_dataset", "build_replay_config"):
        assert hasattr(gold, name)
    assert gold.GOLD_MANIFEST_VERSION.startswith("gold-replay-dataset-")
    assert gold_cli.EXIT_OK == 0
    assert gold_cli.EXIT_USAGE == 2

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

import pytest

from infrastructure.medallion import bronze, candles, capacity_guards, refresh, silver
from infrastructure.medallion.bronze import DEFAULT_BASE_URL

GIB = 1024**3


def _write_manifest(root: Path, filenames: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    files: dict[str, object] = {}
    for name in filenames:
        day = name.removeprefix("ETHUSDT_").split("_")[0].removesuffix(".csv.gz")
        files[name] = {"date": day, "filename": name}
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": "test", "files": files}, sort_keys=True),
        encoding="utf-8",
    )


def _config(tmp_path: Path, *, start: date, target: date) -> refresh.RefreshConfig:
    return refresh.RefreshConfig(
        symbol="ETHUSDT",
        bronze_dir=tmp_path / "bronze",
        silver_dir=tmp_path / "silver" / "trades",
        candles_dir=tmp_path / "silver" / "candles",
        gold_dir=tmp_path / "gold",
        status_path=tmp_path / "status.json",
        start_day=start,
        target_day=target,
    )


@dataclass
class FakeOps:
    calls: list[tuple[str, date]] = field(default_factory=list)
    fail_on: tuple[str, date] | None = None

    def _record(self, layer: str, day: date) -> None:
        self.calls.append((layer, day))
        if self.fail_on == (layer, day):
            raise RuntimeError(f"boom {layer} {day.isoformat()}")

    def download_bronze(self, day: date) -> str:
        self._record("bronze", day)
        return "done"

    def transform_silver(self, day: date) -> str:
        self._record("silver", day)
        return "done"

    def transform_candles(self, day: date) -> str:
        self._record("candles", day)
        return "done"


@dataclass
class FakeGuardProbe:
    free_bytes: int = 100 * GIB
    removed: list[Path] = field(default_factory=list)

    def disk_usage(self, path: Path) -> capacity_guards.DiskUsage:
        return capacity_guards.DiskUsage(total=500 * GIB, used=0, free=self.free_bytes)

    def is_mount(self, path: Path) -> bool:
        return True

    def read_text(self, path: Path) -> str:
        return '{"label":"LENOVO_DATA","uuid":"uuid-ok"}'

    def volume_identity(self, path: Path) -> capacity_guards.VolumeIdentity:
        return capacity_guards.VolumeIdentity(label="LENOVO_DATA", uuid="uuid-ok")

    def remove_tree(self, path: Path) -> None:
        self.removed.append(path)
        path.unlink()


def _guard_config(tmp_path: Path) -> capacity_guards.CapacityGuardConfig:
    return capacity_guards.CapacityGuardConfig(
        data_mount=tmp_path / "srv" / "data",
        marker_path=tmp_path / "srv" / "data" / ".lenovosrv-data-volume",
        expected_label="LENOVO_DATA",
        expected_uuid="uuid-ok",
        ssd_path=tmp_path / "srv" / "fast",
        cache_path=tmp_path / "srv" / "fast" / "medallion",
        disposable_subdirs=("cache",),
    )


def test_classifies_refresh_days_by_frozen_split_boundaries() -> None:
    assert refresh.classify_day(date(2025, 6, 16)) is refresh.AccessClass.DEVELOPMENT
    assert refresh.classify_day(date(2025, 6, 17)) is refresh.AccessClass.WALK_FORWARD
    assert refresh.classify_day(date(2026, 3, 14)) is refresh.AccessClass.FINAL_HOLDOUT
    assert refresh.classify_day(date(2026, 8, 24)) is refresh.AccessClass.FUTURE_COLLECTION


def test_planner_detects_missing_days_from_layer_manifests(tmp_path: Path) -> None:
    cfg = _config(tmp_path, start=date(2025, 6, 14), target=date(2025, 6, 16))
    _write_manifest(cfg.bronze_dir, ["ETHUSDT_2025-06-14.csv.gz"])
    _write_manifest(cfg.silver_dir, ["ETHUSDT_2025-06-14.csv.gz", "ETHUSDT_2025-06-15.csv.gz"])
    _write_manifest(
        cfg.candles_dir,
        ["ETHUSDT_2025-06-14_1m.csv.gz", "ETHUSDT_2025-06-15_1m.csv.gz"],
    )

    plan = refresh.plan_refresh(cfg)

    assert [step.day for step in plan.steps if step.layer == refresh.Layer.BRONZE] == [
        date(2025, 6, 15),
        date(2025, 6, 16),
    ]
    assert [step.day for step in plan.steps if step.layer == refresh.Layer.SILVER_TRADES] == [
        date(2025, 6, 16)
    ]
    assert [step.day for step in plan.steps if step.layer == refresh.Layer.SILVER_CANDLES] == [
        date(2025, 6, 16)
    ]


def test_dry_run_does_not_write_status_or_call_operations(tmp_path: Path) -> None:
    cfg = _config(tmp_path, start=date(2025, 6, 16), target=date(2025, 6, 16))
    ops = FakeOps()

    result = refresh.run_refresh(cfg, operations=ops, dry_run=True)

    assert result.dry_run is True
    assert ops.calls == []
    assert not cfg.status_path.exists()


def test_bronze_source_must_be_exact_public_bybit_url(tmp_path: Path) -> None:
    cfg = refresh.RefreshConfig(
        symbol="ETHUSDT",
        bronze_dir=tmp_path / "bronze",
        silver_dir=tmp_path / "silver" / "trades",
        candles_dir=tmp_path / "silver" / "candles",
        gold_dir=tmp_path / "gold",
        status_path=tmp_path / "status.json",
        start_day=date(2025, 6, 16),
        target_day=date(2025, 6, 16),
        bronze_base_url="https://public.bybit.com/trading",
    )

    with pytest.raises(refresh.RefreshExecutionError):
        refresh.plan_refresh(cfg)


def test_run_is_idempotent_after_successful_status(tmp_path: Path) -> None:
    cfg = _config(tmp_path, start=date(2025, 6, 16), target=date(2025, 6, 16))
    first_ops = FakeOps()

    first = refresh.run_refresh(cfg, operations=first_ops)
    second_ops = FakeOps()
    second = refresh.run_refresh(cfg, operations=second_ops)

    assert first.result == "OK"
    assert len(first_ops.calls) == 3
    assert second.result == "OK_NOOP"
    assert second_ops.calls == []


def test_partial_failure_is_resumable_from_last_completed_step(tmp_path: Path) -> None:
    cfg = _config(tmp_path, start=date(2025, 6, 15), target=date(2025, 6, 16))
    failing = FakeOps(fail_on=("silver", date(2025, 6, 15)))

    with pytest.raises(refresh.RefreshExecutionError):
        refresh.run_refresh(cfg, operations=failing)

    resume = FakeOps()
    result = refresh.run_refresh(cfg, operations=resume)

    assert ("bronze", date(2025, 6, 15)) not in resume.calls
    assert result.result == "OK"
    assert ("silver", date(2025, 6, 15)) in resume.calls
    assert ("candles", date(2025, 6, 16)) in resume.calls


def test_walk_forward_and_holdout_are_fail_closed_before_operations(tmp_path: Path) -> None:
    cfg = _config(tmp_path, start=date(2025, 6, 17), target=date(2025, 6, 17))
    ops = FakeOps()

    with pytest.raises(refresh.AccessBlockedError):
        refresh.run_refresh(cfg, operations=ops)

    assert ops.calls == []


def test_future_collection_runs_only_bronze_silver_and_blocks_gold_research(tmp_path: Path) -> None:
    cfg = _config(tmp_path, start=date(2026, 8, 24), target=date(2026, 8, 24))
    ops = FakeOps()

    result = refresh.run_refresh(cfg, operations=ops)

    assert ops.calls == [
        ("bronze", date(2026, 8, 24)),
        ("silver", date(2026, 8, 24)),
        ("candles", date(2026, 8, 24)),
    ]
    assert result.unassigned_research_reads == 0
    assert result.gold_blocked_days == [date(2026, 8, 24)]


def test_status_json_is_written_atomically(tmp_path: Path) -> None:
    cfg = _config(tmp_path, start=date(2025, 6, 16), target=date(2025, 6, 16))

    refresh.run_refresh(cfg, operations=FakeOps())

    assert cfg.status_path.is_file()
    assert not cfg.status_path.with_name(cfg.status_path.name + ".part").exists()
    payload = json.loads(cfg.status_path.read_text(encoding="utf-8"))
    assert payload["result"] == "OK"
    assert payload["completed_steps"] == [
        "bronze:2025-06-16",
        "silver_trades:2025-06-16",
        "silver_candles:2025-06-16",
    ]


def test_default_operations_delegate_to_existing_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config(tmp_path, start=date(2025, 6, 16), target=date(2025, 6, 16))
    ops = refresh.DefaultRefreshOperations(cfg)
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    @dataclass(frozen=True)
    class OneStatus:
        status: str

    def fake_bronze(*args: object, **kwargs: object) -> OneStatus:
        calls.append(("bronze", args, kwargs))
        return OneStatus("downloaded")

    def fake_silver(*args: object, **kwargs: object) -> OneStatus:
        calls.append(("silver", args, kwargs))
        return OneStatus("transformed")

    def fake_candles(*args: object, **kwargs: object) -> list[OneStatus]:
        calls.append(("candles", args, kwargs))
        return [OneStatus("skipped"), OneStatus("transformed")]

    monkeypatch.setattr(bronze, "download_day", fake_bronze)
    monkeypatch.setattr(silver, "transform_day", fake_silver)
    monkeypatch.setattr(candles, "transform_day", fake_candles)

    assert ops.download_bronze(date(2025, 6, 16)) == "downloaded"
    assert ops.transform_silver(date(2025, 6, 16)) == "transformed"
    assert ops.transform_candles(date(2025, 6, 16)) == "transformed"
    assert calls[0][2]["base_url"] == DEFAULT_BASE_URL


def test_default_candle_operation_reports_skipped_for_no_or_all_skipped_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config(tmp_path, start=date(2025, 6, 16), target=date(2025, 6, 16))
    ops = refresh.DefaultRefreshOperations(cfg)

    @dataclass(frozen=True)
    class OneStatus:
        status: str

    monkeypatch.setattr(candles, "transform_day", lambda *args, **kwargs: [])
    assert ops.transform_candles(date(2025, 6, 16)) == "skipped"

    monkeypatch.setattr(candles, "transform_day", lambda *args, **kwargs: [OneStatus("skipped")])
    assert ops.transform_candles(date(2025, 6, 16)) == "skipped"


def test_planner_fails_closed_on_malformed_manifests_or_status(tmp_path: Path) -> None:
    cfg = _config(tmp_path, start=date(2025, 6, 16), target=date(2025, 6, 16))
    cfg.status_path.write_text("[]", encoding="utf-8")
    with pytest.raises(refresh.RefreshExecutionError):
        refresh.plan_refresh(cfg)

    cfg.status_path.write_text(json.dumps({"completed_steps": "bad"}), encoding="utf-8")
    with pytest.raises(refresh.RefreshExecutionError):
        refresh.plan_refresh(cfg)

    cfg.status_path.unlink()
    cfg.bronze_dir.mkdir(parents=True)
    (cfg.bronze_dir / "manifest.json").write_text(json.dumps({"files": "bad"}), encoding="utf-8")
    with pytest.raises(refresh.RefreshExecutionError):
        refresh.plan_refresh(cfg)


def test_empty_range_is_noop(tmp_path: Path) -> None:
    cfg = _config(tmp_path, start=date(2025, 6, 17), target=date(2025, 6, 16))

    result = refresh.run_refresh(cfg, operations=FakeOps())

    assert result.result == "OK_NOOP"
    assert result.planned_steps == 0


def test_capacity_guard_failure_happens_before_layer_operations(tmp_path: Path) -> None:
    cfg = replace(
        _config(tmp_path, start=date(2025, 6, 16), target=date(2025, 6, 16)),
        capacity_guard=_guard_config(tmp_path),
    )
    ops = FakeOps()

    with pytest.raises(capacity_guards.CapacityGuardError, match="SSD_MIN_FREE_GB"):
        refresh.run_refresh(
            cfg,
            operations=ops,
            capacity_probe=FakeGuardProbe(free_bytes=49 * GIB),
        )

    assert ops.calls == []
    payload = json.loads(cfg.status_path.read_text(encoding="utf-8"))
    assert payload["result"] == "FAIL_GUARD"


def test_capacity_guard_dry_run_does_not_purge_or_write_status(tmp_path: Path) -> None:
    guard_config = _guard_config(tmp_path)
    cfg = replace(
        _config(tmp_path, start=date(2025, 6, 16), target=date(2025, 6, 16)),
        capacity_guard=guard_config,
    )
    disposable = guard_config.cache_path / "cache" / "old.bin"
    disposable.parent.mkdir(parents=True)
    with disposable.open("wb") as fh:
        fh.truncate(65 * GIB)
    probe = FakeGuardProbe()

    with pytest.raises(capacity_guards.CapacityGuardError, match="SSD_CACHE_MAX_GB"):
        refresh.run_refresh(cfg, operations=FakeOps(), dry_run=True, capacity_probe=probe)

    assert disposable.exists()
    assert probe.removed == []
    assert not cfg.status_path.exists()

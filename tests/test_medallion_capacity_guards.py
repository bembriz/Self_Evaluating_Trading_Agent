from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from infrastructure.medallion import capacity_guards

GIB = 1024**3


@dataclass
class FakeProbe:
    free_bytes: int = 100 * GIB
    total_bytes: int = 500 * GIB
    mounted: bool = True
    marker_payload: str = '{"label":"LENOVO_DATA","uuid":"uuid-ok"}'
    label: str = "LENOVO_DATA"
    uuid: str = "uuid-ok"
    removed: list[Path] = field(default_factory=list)

    def disk_usage(self, path: Path) -> capacity_guards.DiskUsage:
        return capacity_guards.DiskUsage(total=self.total_bytes, used=0, free=self.free_bytes)

    def is_mount(self, path: Path) -> bool:
        return self.mounted

    def read_text(self, path: Path) -> str:
        return self.marker_payload

    def volume_identity(self, path: Path) -> capacity_guards.VolumeIdentity:
        return capacity_guards.VolumeIdentity(label=self.label, uuid=self.uuid)

    def remove_tree(self, path: Path) -> None:
        self.removed.append(path)
        if path.is_dir():
            for child in path.iterdir():
                if child.is_file():
                    child.unlink()
                else:
                    self.remove_tree(child)
            path.rmdir()
        else:
            path.unlink()


def _config(tmp_path: Path) -> capacity_guards.CapacityGuardConfig:
    return capacity_guards.CapacityGuardConfig(
        data_mount=tmp_path / "srv" / "data",
        marker_path=tmp_path / "srv" / "data" / ".lenovosrv-data-volume",
        expected_label="LENOVO_DATA",
        expected_uuid="uuid-ok",
        ssd_path=tmp_path / "srv" / "fast",
        cache_path=tmp_path / "srv" / "fast" / "medallion",
        disposable_subdirs=("cache", "tmp", "indexes", "replay-work"),
    )


def _write_bytes(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.truncate(size)


def test_preflight_passes_with_sufficient_space_and_cache_under_limit(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    _write_bytes(cfg.cache_path / "cache" / "small.bin", 10)

    result = capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe())

    assert result.free_gb == 100
    assert result.cache_gb == 0
    assert result.purged == []


def test_preflight_passes_when_cache_path_does_not_exist(tmp_path: Path) -> None:
    cfg = _config(tmp_path)

    result = capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe())

    assert result.cache_gb == 0
    assert result.purged == []


def test_preflight_accepts_legacy_plain_text_marker_label(tmp_path: Path) -> None:
    cfg = _config(tmp_path)

    result = capacity_guards.run_capacity_preflight(
        cfg,
        probe=FakeProbe(marker_payload="LENOVO_DATA\n"),
    )

    assert result.free_gb == 100


def test_free_space_below_threshold_fails_closed_before_purge(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    probe = FakeProbe(free_bytes=49 * GIB)
    _write_bytes(cfg.cache_path / "cache" / "old.bin", 70 * GIB)

    with pytest.raises(capacity_guards.CapacityGuardError, match="SSD_MIN_FREE_GB"):
        capacity_guards.run_capacity_preflight(cfg, probe=probe)

    assert probe.removed == []


def test_cache_over_limit_purges_only_disposable_content(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    disposable = cfg.cache_path / "cache" / "old.bin"
    canonical = cfg.data_mount / "medallion" / "gold" / "keep.bin"
    referenced = cfg.cache_path / "gold" / "replay-datasets" / "keep.bin"
    _write_bytes(disposable, 65 * GIB)
    _write_bytes(canonical, 1)
    _write_bytes(referenced, 1)

    result = capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe())

    assert disposable in result.purged
    assert not disposable.exists()
    assert canonical.exists()
    assert referenced.exists()


def test_cache_over_limit_not_recoverable_fails_guard(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    protected = cfg.cache_path / "gold" / "replay-datasets" / "too-large.bin"
    _write_bytes(protected, 65 * GIB)

    with pytest.raises(capacity_guards.CapacityGuardError, match="SSD_CACHE_MAX_GB"):
        capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe())

    assert protected.exists()


def test_data_volume_marker_mount_label_and_uuid_are_fail_closed(tmp_path: Path) -> None:
    cfg = _config(tmp_path)

    with pytest.raises(capacity_guards.CapacityGuardError, match="mountpoint"):
        capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe(mounted=False))

    with pytest.raises(capacity_guards.CapacityGuardError, match="marker"):
        capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe(marker_payload=""))

    with pytest.raises(capacity_guards.CapacityGuardError, match="label"):
        capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe(label="WRONG"))

    with pytest.raises(capacity_guards.CapacityGuardError, match="UUID"):
        capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe(uuid="wrong"))

    with pytest.raises(capacity_guards.CapacityGuardError, match="JSON no es objeto"):
        capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe(marker_payload="[]"))


def test_retention_removes_only_runtime_logs_older_than_30_days(tmp_path: Path) -> None:
    old_runtime = tmp_path / "runtime" / "refresh-old.log"
    new_runtime = tmp_path / "runtime" / "refresh-new.log"
    versioned_doc = tmp_path / "docs" / "phases" / "24" / "evidence" / "keep.log"
    _write_bytes(old_runtime, 1)
    _write_bytes(new_runtime, 1)
    _write_bytes(versioned_doc, 1)
    old_ns = 1_000_000_000
    old_runtime.touch()
    old_runtime.chmod(0o644)
    old_runtime_stat_time = old_ns / 1_000_000_000
    os.utime(old_runtime, (old_runtime_stat_time, old_runtime_stat_time))

    result = capacity_guards.apply_runtime_log_retention(
        tmp_path / "runtime",
        retention_days=30,
        now_ns=old_ns + (31 * 24 * 60 * 60 * 1_000_000_000),
        probe=FakeProbe(),
    )

    assert result == [old_runtime]
    assert not old_runtime.exists()
    assert new_runtime.exists()
    assert versioned_doc.exists()


def test_preflight_applies_runtime_log_retention_when_configured(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    old_runtime = runtime / "old.log"
    _write_bytes(old_runtime, 1)
    os.utime(old_runtime, (1, 1))
    cfg = capacity_guards.CapacityGuardConfig(
        data_mount=tmp_path / "srv" / "data",
        marker_path=tmp_path / "srv" / "data" / ".lenovosrv-data-volume",
        expected_label="LENOVO_DATA",
        expected_uuid="uuid-ok",
        ssd_path=tmp_path / "srv" / "fast",
        cache_path=tmp_path / "srv" / "fast" / "medallion",
        runtime_log_dir=runtime,
        runtime_log_retention_days=0,
    )

    result = capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe())

    assert result.retained_logs_removed == [old_runtime]
    assert not old_runtime.exists()


def test_runtime_log_retention_missing_directory_is_noop(tmp_path: Path) -> None:
    assert capacity_guards.apply_runtime_log_retention(tmp_path / "missing") == []


def test_dry_run_does_not_purge_or_remove_runtime_logs(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    disposable = cfg.cache_path / "cache" / "old.bin"
    old_runtime = tmp_path / "runtime" / "refresh-old.log"
    _write_bytes(disposable, 65 * GIB)
    _write_bytes(old_runtime, 1)
    os.utime(old_runtime, (1, 1))

    with pytest.raises(capacity_guards.CapacityGuardError):
        capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe(), allow_purge=False)
    retained = capacity_guards.apply_runtime_log_retention(
        tmp_path / "runtime",
        retention_days=30,
        now_ns=31 * 24 * 60 * 60 * 1_000_000_000,
        probe=FakeProbe(),
        dry_run=True,
    )

    assert disposable.exists()
    assert old_runtime.exists()
    assert retained == [old_runtime]


def test_marker_json_must_match_approved_identity(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    marker = json.dumps({"label": "LENOVO_DATA", "uuid": "wrong"})

    with pytest.raises(capacity_guards.CapacityGuardError, match="marker UUID"):
        capacity_guards.run_capacity_preflight(cfg, probe=FakeProbe(marker_payload=marker))


def test_filesystem_probe_missing_marker_and_remove_directory(tmp_path: Path) -> None:
    probe = capacity_guards.FileSystemCapacityProbe()
    target_dir = tmp_path / "discard"
    _write_bytes(target_dir / "file.txt", 1)

    usage = probe.disk_usage(tmp_path)
    assert usage.total >= usage.free
    assert probe.is_mount(tmp_path) is False
    with pytest.raises(capacity_guards.CapacityGuardError, match="marker ausente"):
        probe.read_text(tmp_path / "missing-marker")

    probe.remove_tree(target_dir)
    assert not target_dir.exists()

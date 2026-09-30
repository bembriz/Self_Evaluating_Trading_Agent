"""Fail-closed storage guards for the Phase 24 Medallion refresh."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

GIB = 1024**3
DEFAULT_SSD_MIN_FREE_GB = 50
DEFAULT_SSD_CACHE_MAX_GB = 64
DEFAULT_RUNTIME_LOG_RETENTION_DAYS = 30
DEFAULT_DISPOSABLE_SUBDIRS = ("cache", "tmp", "indexes", "replay-work")
DEFAULT_DATA_MOUNT = Path("/srv/data")
DEFAULT_MARKER_PATH = DEFAULT_DATA_MOUNT / ".lenovosrv-data-volume"
DEFAULT_SSD_PATH = Path("/srv/fast")
DEFAULT_CACHE_PATH = DEFAULT_SSD_PATH / "medallion"
APPROVED_DATA_LABEL = "LENOVO_DATA"
APPROVED_DATA_UUID = "10fff707-60e4-4321-afa0-a3c4704d9e8d"


class CapacityGuardError(RuntimeError):
    """A storage preflight guard failed before Medallion writes were allowed."""


@dataclass(frozen=True)
class DiskUsage:
    total: int
    used: int
    free: int


@dataclass(frozen=True)
class VolumeIdentity:
    label: str
    uuid: str


class CapacityProbe(Protocol):
    def disk_usage(self, path: Path) -> DiskUsage: ...

    def is_mount(self, path: Path) -> bool: ...

    def read_text(self, path: Path) -> str: ...

    def volume_identity(self, path: Path) -> VolumeIdentity: ...

    def remove_tree(self, path: Path) -> None: ...


@dataclass(frozen=True)
class CapacityGuardConfig:
    data_mount: Path = DEFAULT_DATA_MOUNT
    marker_path: Path = DEFAULT_MARKER_PATH
    expected_label: str = APPROVED_DATA_LABEL
    expected_uuid: str = APPROVED_DATA_UUID
    ssd_path: Path = DEFAULT_SSD_PATH
    cache_path: Path = DEFAULT_CACHE_PATH
    min_free_gb: int = DEFAULT_SSD_MIN_FREE_GB
    cache_max_gb: int = DEFAULT_SSD_CACHE_MAX_GB
    disposable_subdirs: tuple[str, ...] = DEFAULT_DISPOSABLE_SUBDIRS
    runtime_log_dir: Path | None = None
    runtime_log_retention_days: int = DEFAULT_RUNTIME_LOG_RETENTION_DAYS


@dataclass(frozen=True)
class CapacityGuardResult:
    free_gb: int
    cache_gb: int
    purged: list[Path] = field(default_factory=list)
    retained_logs_removed: list[Path] = field(default_factory=list)


class FileSystemCapacityProbe:
    def disk_usage(self, path: Path) -> DiskUsage:
        usage = shutil.disk_usage(path)
        return DiskUsage(total=usage.total, used=usage.used, free=usage.free)

    def is_mount(self, path: Path) -> bool:
        return path.is_mount()

    def read_text(self, path: Path) -> str:
        if not path.is_file():
            raise CapacityGuardError(f"marker ausente: {path}")
        return path.read_text(encoding="utf-8")

    def volume_identity(self, path: Path) -> VolumeIdentity:
        device = path.stat().st_dev
        return VolumeIdentity(
            label=_identity_from_dev(Path("/dev/disk/by-label"), device),
            uuid=_identity_from_dev(Path("/dev/disk/by-uuid"), device),
        )

    def remove_tree(self, path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _identity_from_dev(root: Path, device: int) -> str:
    if not root.is_dir():
        return ""
    for candidate in sorted(root.iterdir(), key=lambda item: item.name):
        try:
            if candidate.stat().st_rdev == device:
                return candidate.name
        except OSError:
            continue
    return ""


def _marker_identity(marker_text: str) -> VolumeIdentity:
    stripped = marker_text.strip()
    if not stripped:
        raise CapacityGuardError("marker vacío")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        first_line = stripped.splitlines()[0].strip()
        return VolumeIdentity(label=first_line, uuid="")
    if not isinstance(payload, dict):
        raise CapacityGuardError("marker inválido: JSON no es objeto")
    label = payload.get("label")
    uuid = payload.get("uuid")
    return VolumeIdentity(
        label=label if isinstance(label, str) else "",
        uuid=uuid if isinstance(uuid, str) else "",
    )


def _require_data_volume(config: CapacityGuardConfig, probe: CapacityProbe) -> None:
    if not probe.is_mount(config.data_mount):
        raise CapacityGuardError(f"data volume is not a mountpoint: {config.data_mount}")

    marker = _marker_identity(probe.read_text(config.marker_path))
    if marker.label != config.expected_label:
        actual_label = marker.label or "<empty>"
        raise CapacityGuardError(
            f"marker label mismatch: expected {config.expected_label}, got {actual_label}"
        )
    if marker.uuid and marker.uuid != config.expected_uuid:
        raise CapacityGuardError(
            f"marker UUID mismatch: expected {config.expected_uuid}, got {marker.uuid}"
        )

    identity = probe.volume_identity(config.data_mount)
    if identity.label != config.expected_label:
        raise CapacityGuardError(
            f"data volume label mismatch: expected {config.expected_label}, got {identity.label}"
        )
    if identity.uuid != config.expected_uuid:
        raise CapacityGuardError(
            f"data volume UUID mismatch: expected {config.expected_uuid}, got {identity.uuid}"
        )


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _purge_candidates(config: CapacityGuardConfig) -> Iterable[Path]:
    for name in sorted(config.disposable_subdirs):
        root = config.cache_path / name
        if not root.exists():
            continue
        for item in sorted(root.rglob("*"), key=lambda path: path.as_posix()):
            if item.is_file():
                yield item


def run_capacity_preflight(
    config: CapacityGuardConfig,
    *,
    probe: CapacityProbe | None = None,
    allow_purge: bool = True,
) -> CapacityGuardResult:
    active_probe = probe if probe is not None else FileSystemCapacityProbe()
    _require_data_volume(config, active_probe)

    free_bytes = active_probe.disk_usage(config.ssd_path).free
    if free_bytes < config.min_free_gb * GIB:
        raise CapacityGuardError(
            f"SSD_MIN_FREE_GB guard failed: free={free_bytes // GIB}GB "
            f"required={config.min_free_gb}GB"
        )

    purged: list[Path] = []
    max_cache_bytes = config.cache_max_gb * GIB
    cache_bytes = _directory_size(config.cache_path)
    if cache_bytes > max_cache_bytes:
        if not allow_purge:
            raise CapacityGuardError(
                f"SSD_CACHE_MAX_GB guard failed: cache={cache_bytes // GIB}GB "
                f"max={config.cache_max_gb}GB"
            )
        for candidate in _purge_candidates(config):
            if cache_bytes <= max_cache_bytes:
                break
            size = candidate.stat().st_size
            active_probe.remove_tree(candidate)
            purged.append(candidate)
            cache_bytes -= size
    if cache_bytes > max_cache_bytes:
        raise CapacityGuardError(
            f"SSD_CACHE_MAX_GB guard failed after purge: cache={cache_bytes // GIB}GB "
            f"max={config.cache_max_gb}GB"
        )

    retained_logs_removed: list[Path] = []
    if config.runtime_log_dir is not None:
        retained_logs_removed = apply_runtime_log_retention(
            config.runtime_log_dir,
            retention_days=config.runtime_log_retention_days,
            probe=active_probe,
        )
    return CapacityGuardResult(
        free_gb=free_bytes // GIB,
        cache_gb=cache_bytes // GIB,
        purged=purged,
        retained_logs_removed=retained_logs_removed,
    )


def apply_runtime_log_retention(
    runtime_log_dir: Path,
    *,
    retention_days: int = DEFAULT_RUNTIME_LOG_RETENTION_DAYS,
    now_ns: int | None = None,
    probe: CapacityProbe | None = None,
    dry_run: bool = False,
) -> list[Path]:
    if not runtime_log_dir.is_dir():
        return []
    active_probe = probe if probe is not None else FileSystemCapacityProbe()
    clock_ns = now_ns if now_ns is not None else _now_ns()
    cutoff_ns = clock_ns - (retention_days * 24 * 60 * 60 * 1_000_000_000)
    removed: list[Path] = []
    for path in sorted(runtime_log_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.stat().st_mtime_ns >= cutoff_ns:
            continue
        removed.append(path)
        if not dry_run:
            active_probe.remove_tree(path)
    return removed


def _now_ns() -> int:
    return time.time_ns()

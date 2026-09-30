"""Future-collection ingest authorization (Phase 24 blocker remediation)."""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from infrastructure.medallion import bronze, candles, refresh, silver
from infrastructure.medallion.bronze import download_day
from infrastructure.medallion.split_guard import (
    DEFAULT_INGEST_SCOPE,
    FUTURE_COLLECTION_FIRST_DAY,
    PHASE24_INGEST_SCOPE,
    IngestClass,
    IngestScope,
    SplitGuardError,
    classify_ingest_day,
    ensure_development_day,
    ensure_ingest_allowed,
)

DEV_DAY = date(2024, 6, 1)
PRE_DEV_DAY = date(2023, 9, 8)
WF_DAY = date(2025, 6, 17)
HOLDOUT_DAY = date(2026, 3, 15)
HOLDOUT_LAST_DAY = date(2026, 8, 23)
FUTURE_DAY = date(2026, 8, 24)


class FakeFetcher:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls = 0

    def __call__(self, url: str, dest: Path) -> int:
        self.calls += 1
        dest.write_bytes(self.payload)
        return len(self.payload)


class NoCallFetcher:
    def __call__(self, url: str, dest: Path) -> int:  # pragma: no cover
        raise AssertionError(f"red no permitida en este test: {url}")


def _gz(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"), mtime=0)


def _body(day: date) -> str:
    ts = int(datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC).timestamp() * 1000)
    return f"id,timestamp,price,volume,side\n1,{ts},3762.62,0.07674,sell\n"


def _seed_bronze(bronze_dir: Path, day: date) -> None:
    download_day(
        bronze_dir,
        "ETHUSDT",
        day,
        fetcher=FakeFetcher(_gz(_body(day))),
        scope=PHASE24_INGEST_SCOPE,
    )


@dataclass(frozen=True)
class _OneResult:
    status: str


def test_classify_ingest_day_boundaries() -> None:
    assert date(2026, 8, 24) == FUTURE_COLLECTION_FIRST_DAY
    assert classify_ingest_day(DEV_DAY) is IngestClass.DEVELOPMENT
    assert classify_ingest_day(WF_DAY) is IngestClass.WALK_FORWARD
    assert classify_ingest_day(HOLDOUT_DAY) is IngestClass.FINAL_HOLDOUT
    assert classify_ingest_day(HOLDOUT_LAST_DAY) is IngestClass.FINAL_HOLDOUT
    assert classify_ingest_day(FUTURE_DAY) is IngestClass.FUTURE_COLLECTION
    assert classify_ingest_day(PRE_DEV_DAY) is IngestClass.OUT_OF_RANGE


def test_development_day_is_allowed_in_every_scope() -> None:
    assert ensure_ingest_allowed(DEV_DAY) is IngestClass.DEVELOPMENT
    assert ensure_ingest_allowed(DEV_DAY, scope=PHASE24_INGEST_SCOPE) is IngestClass.DEVELOPMENT


def test_future_collection_requires_explicit_scope() -> None:
    with pytest.raises(SplitGuardError):
        ensure_ingest_allowed(FUTURE_DAY)
    with pytest.raises(SplitGuardError):
        ensure_ingest_allowed(FUTURE_DAY, scope=DEFAULT_INGEST_SCOPE)
    assert (
        ensure_ingest_allowed(FUTURE_DAY, scope=PHASE24_INGEST_SCOPE)
        is IngestClass.FUTURE_COLLECTION
    )


def test_walk_forward_and_holdout_blocked_even_with_future_scope() -> None:
    for day in (WF_DAY, HOLDOUT_DAY, HOLDOUT_LAST_DAY):
        with pytest.raises(SplitGuardError):
            ensure_ingest_allowed(day, scope=PHASE24_INGEST_SCOPE)


def test_holdout_last_day_blocked_and_first_future_day_allowed() -> None:
    with pytest.raises(SplitGuardError):
        ensure_ingest_allowed(HOLDOUT_LAST_DAY, scope=PHASE24_INGEST_SCOPE)
    ensure_ingest_allowed(FUTURE_DAY, scope=PHASE24_INGEST_SCOPE)


def test_scope_must_be_explicit_enum_not_bool_or_str() -> None:
    with pytest.raises(SplitGuardError):
        ensure_ingest_allowed(FUTURE_DAY, scope=True)  # type: ignore[arg-type]
    with pytest.raises(SplitGuardError):
        ensure_ingest_allowed(
            FUTURE_DAY,
            scope="DEVELOPMENT_AND_FUTURE_COLLECTION",  # type: ignore[arg-type]
        )


def test_pre_development_day_is_blocked() -> None:
    with pytest.raises(SplitGuardError):
        ensure_ingest_allowed(PRE_DEV_DAY, scope=PHASE24_INGEST_SCOPE)


def test_is_development_day_helper() -> None:
    from infrastructure.medallion.split_guard import is_development_day

    assert is_development_day(DEV_DAY) is True
    assert is_development_day(FUTURE_DAY) is False
    assert is_development_day(WF_DAY) is False


def test_non_date_day_is_rejected() -> None:
    with pytest.raises(SplitGuardError):
        classify_ingest_day(True)  # type: ignore[arg-type]
    with pytest.raises(SplitGuardError):
        classify_ingest_day("2026-08-24")  # type: ignore[arg-type]


def test_ensure_development_day_default_preserved() -> None:
    ensure_development_day(DEV_DAY)
    for day in (WF_DAY, HOLDOUT_DAY, FUTURE_DAY):
        with pytest.raises(SplitGuardError):
            ensure_development_day(day)


def test_bronze_future_requires_scope_and_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(SplitGuardError):
        download_day(tmp_path, "ETHUSDT", FUTURE_DAY, fetcher=NoCallFetcher())

    assert not (tmp_path / "manifest.json").exists()
    assert not list(tmp_path.rglob("*.csv.gz"))


def test_bronze_future_allowed_with_orchestrator_scope(tmp_path: Path) -> None:
    fetcher = FakeFetcher(_gz(_body(FUTURE_DAY)))

    result = download_day(
        tmp_path, "ETHUSDT", FUTURE_DAY, fetcher=fetcher, scope=PHASE24_INGEST_SCOPE
    )

    assert result.status == "downloaded"
    assert fetcher.calls == 1


def test_bronze_walk_forward_and_holdout_blocked_with_future_scope(tmp_path: Path) -> None:
    for day in (WF_DAY, HOLDOUT_DAY, HOLDOUT_LAST_DAY):
        with pytest.raises(SplitGuardError):
            download_day(
                tmp_path, "ETHUSDT", day, fetcher=NoCallFetcher(), scope=PHASE24_INGEST_SCOPE
            )


def test_silver_future_requires_scope_before_write(tmp_path: Path) -> None:
    bronze_dir = tmp_path / "bronze"
    silver_dir = tmp_path / "silver" / "trades"
    _seed_bronze(bronze_dir, FUTURE_DAY)

    with pytest.raises(SplitGuardError):
        silver.transform_day(bronze_dir, silver_dir, "ETHUSDT", FUTURE_DAY)

    assert not list(silver_dir.rglob("*.csv.gz")) if silver_dir.exists() else True


def test_silver_future_allowed_with_orchestrator_scope(tmp_path: Path) -> None:
    bronze_dir = tmp_path / "bronze"
    silver_dir = tmp_path / "silver" / "trades"
    _seed_bronze(bronze_dir, FUTURE_DAY)

    result = silver.transform_day(
        bronze_dir, silver_dir, "ETHUSDT", FUTURE_DAY, scope=PHASE24_INGEST_SCOPE
    )

    assert result.status == "transformed"


def test_candles_future_requires_scope_before_write(tmp_path: Path) -> None:
    bronze_dir = tmp_path / "bronze"
    trades_dir = tmp_path / "silver" / "trades"
    candles_dir = tmp_path / "silver" / "candles"
    _seed_bronze(bronze_dir, FUTURE_DAY)
    silver.transform_day(bronze_dir, trades_dir, "ETHUSDT", FUTURE_DAY, scope=PHASE24_INGEST_SCOPE)

    with pytest.raises(SplitGuardError):
        candles.transform_day(trades_dir, candles_dir, "ETHUSDT", FUTURE_DAY)

    assert not list(candles_dir.rglob("*.csv.gz")) if candles_dir.exists() else True


def test_candles_future_allowed_with_orchestrator_scope(tmp_path: Path) -> None:
    bronze_dir = tmp_path / "bronze"
    trades_dir = tmp_path / "silver" / "trades"
    candles_dir = tmp_path / "silver" / "candles"
    _seed_bronze(bronze_dir, FUTURE_DAY)
    silver.transform_day(bronze_dir, trades_dir, "ETHUSDT", FUTURE_DAY, scope=PHASE24_INGEST_SCOPE)

    results = candles.transform_day(
        trades_dir, candles_dir, "ETHUSDT", FUTURE_DAY, scope=PHASE24_INGEST_SCOPE
    )

    assert results
    assert all(result.status == "transformed" for result in results)
    assert list(candles_dir.rglob("*.csv.gz"))


def _orchestrator_config(tmp_path: Path, *, scope: IngestScope) -> refresh.RefreshConfig:
    return refresh.RefreshConfig(
        symbol="ETHUSDT",
        bronze_dir=tmp_path / "bronze",
        silver_dir=tmp_path / "silver" / "trades",
        candles_dir=tmp_path / "silver" / "candles",
        gold_dir=tmp_path / "gold",
        status_path=tmp_path / "status.json",
        start_day=FUTURE_DAY,
        target_day=FUTURE_DAY,
        ingest_scope=scope,
    )


def test_default_operations_authorize_future_only_for_future_days(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _orchestrator_config(tmp_path, scope=PHASE24_INGEST_SCOPE)
    ops = refresh.DefaultRefreshOperations(cfg)
    seen: list[tuple[str, object]] = []

    def fake_bronze(*args: object, **kwargs: object) -> _OneResult:
        seen.append(("bronze", kwargs.get("scope")))
        return _OneResult("downloaded")

    def fake_silver(*args: object, **kwargs: object) -> _OneResult:
        seen.append(("silver", kwargs.get("scope")))
        return _OneResult("transformed")

    def fake_candles(*args: object, **kwargs: object) -> list[_OneResult]:
        seen.append(("candles", kwargs.get("scope")))
        return [_OneResult("transformed")]

    monkeypatch.setattr(bronze, "download_day", fake_bronze)
    monkeypatch.setattr(silver, "transform_day", fake_silver)
    monkeypatch.setattr(candles, "transform_day", fake_candles)

    ops.download_bronze(FUTURE_DAY)
    ops.transform_silver(FUTURE_DAY)
    ops.transform_candles(FUTURE_DAY)
    ops.download_bronze(DEV_DAY)
    ops.transform_silver(DEV_DAY)
    ops.transform_candles(DEV_DAY)

    assert seen == [
        ("bronze", PHASE24_INGEST_SCOPE),
        ("silver", PHASE24_INGEST_SCOPE),
        ("candles", PHASE24_INGEST_SCOPE),
        ("bronze", DEFAULT_INGEST_SCOPE),
        ("silver", DEFAULT_INGEST_SCOPE),
        ("candles", DEFAULT_INGEST_SCOPE),
    ]


def test_orchestrator_executes_future_collection_with_explicit_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _orchestrator_config(tmp_path, scope=PHASE24_INGEST_SCOPE)

    monkeypatch.setattr(bronze, "download_day", lambda *a, **k: _OneResult("downloaded"))
    monkeypatch.setattr(silver, "transform_day", lambda *a, **k: _OneResult("transformed"))
    monkeypatch.setattr(candles, "transform_day", lambda *a, **k: [_OneResult("transformed")])

    result = refresh.run_refresh(cfg)

    assert result.result == "OK"
    assert result.executed_steps == 3
    assert result.gold_blocked_days == [FUTURE_DAY]
    assert result.unassigned_research_reads == 0


def test_orchestrator_future_fails_closed_without_scope(tmp_path: Path) -> None:
    cfg = _orchestrator_config(tmp_path, scope=DEFAULT_INGEST_SCOPE)
    ops = refresh.DefaultRefreshOperations(cfg)

    with pytest.raises(SplitGuardError):
        ops.download_bronze(FUTURE_DAY)


def test_orchestrator_dry_run_keeps_reads_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _orchestrator_config(tmp_path, scope=PHASE24_INGEST_SCOPE)
    calls: list[object] = []
    monkeypatch.setattr(bronze, "download_day", lambda *a, **k: calls.append(("bronze", a, k)))

    result = refresh.run_refresh(cfg, dry_run=True)

    assert calls == []
    assert result.unassigned_research_reads == 0
    assert not cfg.status_path.exists()

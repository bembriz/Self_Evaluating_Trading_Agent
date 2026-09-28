"""Unit tests del downloader Bronze idempotente (Bybit Spot, DEVELOPMENT-only)."""

from __future__ import annotations

import gzip
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from infrastructure.medallion import cli
from infrastructure.medallion.bronze import (
    BRONZE_SCHEMA_VERSION,
    DEFAULT_BASE_URL,
    BronzeError,
    HashConflictError,
    InvalidGzipError,
    MarkerError,
    UnexpectedFilenameError,
    bronze_filename,
    download_day,
    download_days,
    ensure_marker,
    sha256_file,
    source_url,
    urllib_fetch,
    validate_filename,
    validate_gzip_file,
)
from infrastructure.medallion.split_guard import (
    DEVELOPMENT_FIRST_DAY,
    DEVELOPMENT_LAST_DAY,
    SplitGuardError,
    ensure_development_day,
)

DEV_DAY = date(2024, 6, 1)
WF_DAY = date(2025, 6, 17)
HOLDOUT_DAY = date(2026, 3, 15)
PRE_DEV_DAY = date(2023, 9, 8)


def _payload(text: str = "id,timestamp,price,volume,side\n") -> bytes:
    return gzip.compress(text.encode("utf-8"), mtime=0)


class FakeFetcher:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def __call__(self, url: str, dest: Path) -> int:
        self.urls.append(url)
        dest.write_bytes(self.payload)
        return len(self.payload)


class NoCallFetcher:
    def __call__(self, url: str, dest: Path) -> int:  # pragma: no cover
        raise AssertionError(f"red no permitida en este test: {url}")


def _partition(tmp_path: Path, day: date = DEV_DAY) -> Path:
    return tmp_path / f"date={day.isoformat()}" / bronze_filename("ETHUSDT", day)


def test_download_new_file(tmp_path: Path) -> None:
    payload = _payload("id,timestamp,price,volume,side\n1,1717200000274,3762.62,0.07674,sell\n")
    fetcher = FakeFetcher(payload)

    result = download_day(tmp_path, "ETHUSDT", DEV_DAY, fetcher=fetcher)

    final = _partition(tmp_path)
    assert result.status == "downloaded"
    assert final.read_bytes() == payload
    assert result.sha256 == sha256_file(final)
    assert result.bytes == len(payload)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    entry = manifest["files"]["ETHUSDT_2024-06-01.csv.gz"]
    assert entry["sha256"] == result.sha256
    assert entry["source_url"] == (
        "https://public.bybit.com/spot/ETHUSDT/ETHUSDT_2024-06-01.csv.gz"
    )
    assert entry["schema_version"] == BRONZE_SCHEMA_VERSION
    assert entry["symbol"] == "ETHUSDT"
    assert entry["date"] == "2024-06-01"
    assert not list(tmp_path.rglob("*.part"))


def test_second_run_skips_without_network(tmp_path: Path) -> None:
    payload = _payload()
    download_day(tmp_path, "ETHUSDT", DEV_DAY, fetcher=FakeFetcher(payload))
    manifest_before = (tmp_path / "manifest.json").read_bytes()

    second = download_day(tmp_path, "ETHUSDT", DEV_DAY, fetcher=NoCallFetcher())

    assert second.status == "skipped"
    assert second.sha256 == sha256_file(_partition(tmp_path))
    assert (tmp_path / "manifest.json").read_bytes() == manifest_before


def test_stale_part_is_recoverable(tmp_path: Path) -> None:
    final = _partition(tmp_path)
    final.parent.mkdir(parents=True)
    stale = final.with_name(final.name + ".part")
    stale.write_bytes(b"interrumpido basura")

    payload = _payload("id,timestamp,price,volume,side\n")
    result = download_day(tmp_path, "ETHUSDT", DEV_DAY, fetcher=FakeFetcher(payload))

    assert result.status == "downloaded"
    assert final.read_bytes() == payload
    assert not stale.exists()


def test_hash_conflict_fails_closed(tmp_path: Path) -> None:
    payload_a = _payload("contenido A\n")
    download_day(tmp_path, "ETHUSDT", DEV_DAY, fetcher=FakeFetcher(payload_a))
    final = _partition(tmp_path)
    final.write_bytes(_payload("contenido B\n"))

    with pytest.raises(HashConflictError):
        download_day(tmp_path, "ETHUSDT", DEV_DAY, fetcher=NoCallFetcher())

    assert final.read_bytes() == _payload("contenido B\n")
    assert (
        sha256_file(final)
        != json.loads((tmp_path / "manifest.json").read_text())["files"][
            "ETHUSDT_2024-06-01.csv.gz"
        ]["sha256"]
    )


def test_existing_file_without_manifest_fails(tmp_path: Path) -> None:
    final = _partition(tmp_path)
    final.parent.mkdir(parents=True)
    final.write_bytes(_payload())

    with pytest.raises(HashConflictError):
        download_day(tmp_path, "ETHUSDT", DEV_DAY, fetcher=NoCallFetcher())


def test_invalid_gzip_fails_closed(tmp_path: Path) -> None:
    fetcher = FakeFetcher(b"esto no es gzip")

    with pytest.raises(InvalidGzipError):
        download_day(tmp_path, "ETHUSDT", DEV_DAY, fetcher=fetcher)

    final = _partition(tmp_path)
    assert not final.exists()
    assert not list(tmp_path.rglob("*.part"))
    manifest_path = tmp_path / "manifest.json"
    assert not manifest_path.exists() or "sha256" not in manifest_path.read_text()


@pytest.mark.parametrize(
    "evil",
    [
        "../evil.csv.gz",
        "ETHUSDT_2024-06-01.csv.gz/../../../etc/passwd",
        "/ETHUSDT_2024-06-01.csv.gz",
        "ethusdt_2024-06-01.csv.gz",
        "ETHUSDT_2024-06-01.csv",
        "ETHUSDT_2024-06-02.csv.gz",
        "OTHER_2024-06-01.csv.gz",
    ],
)
def test_path_traversal_and_unexpected_names_rejected(evil: str) -> None:
    with pytest.raises(UnexpectedFilenameError):
        validate_filename(evil, "ETHUSDT", DEV_DAY)


def test_source_url_rejects_trading_and_foreign_bases() -> None:
    with pytest.raises(BronzeError):
        source_url("https://public.bybit.com/trading/ETHUSDT", "ETHUSDT", DEV_DAY)
    with pytest.raises(BronzeError):
        source_url("https://evil.example.com/spot", "ETHUSDT", DEV_DAY)
    assert source_url(DEFAULT_BASE_URL, "ETHUSDT", DEV_DAY) == (
        "https://public.bybit.com/spot/ETHUSDT/ETHUSDT_2024-06-01.csv.gz"
    )


def test_manifest_is_deterministic(tmp_path: Path) -> None:
    payload = _payload()
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    download_day(dir_a, "ETHUSDT", DEV_DAY, fetcher=FakeFetcher(payload))
    download_day(dir_b, "ETHUSDT", DEV_DAY, fetcher=FakeFetcher(payload))

    bytes_a = (dir_a / "manifest.json").read_bytes()
    bytes_b = (dir_b / "manifest.json").read_bytes()
    assert bytes_a == bytes_b
    text = bytes_a.decode("utf-8")
    entry = json.loads(text)["files"]["ETHUSDT_2024-06-01.csv.gz"]
    assert entry["date"] == "2024-06-01"
    assert "ops" not in text and "skipped" not in text and "downloaded" not in text
    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text) is None


def test_ops_log_is_separate_from_manifest(tmp_path: Path) -> None:
    download_day(tmp_path, "ETHUSDT", DEV_DAY, fetcher=FakeFetcher(_payload()))

    ops = (tmp_path / "ops-downloads.jsonl").read_text().strip().splitlines()
    assert len(ops) == 1
    event = json.loads(ops[0])
    assert event["event"] == "downloaded"
    datetime.fromisoformat(event["at"])  # timestamp operativo presente SOLO aquí
    manifest_text = (tmp_path / "manifest.json").read_text()
    assert '"at"' not in manifest_text


def test_split_guard_accepts_development_day() -> None:
    ensure_development_day(date(2024, 6, 1))
    ensure_development_day(DEVELOPMENT_FIRST_DAY)
    ensure_development_day(DEVELOPMENT_LAST_DAY)


@pytest.mark.parametrize("day", [WF_DAY, HOLDOUT_DAY, PRE_DEV_DAY, date(2026, 8, 24)])
def test_split_guard_rejects_before_network(day: date) -> None:
    fetcher = FakeFetcher(_payload())
    with pytest.raises(SplitGuardError):
        download_day(Path("/no/existe"), "ETHUSDT", day, fetcher=fetcher)
    assert fetcher.urls == []


def test_split_constants_match_frozen_splits_v1() -> None:
    raw = json.loads((Path(__file__).resolve().parent.parent / "splits" / "v1.json").read_text())
    dev = next(s for s in raw["splits"] if s["name"] == "DEVELOPMENT")
    first = datetime.fromisoformat(dev["first_timestamp"])
    last = datetime.fromisoformat(dev["last_timestamp"])
    assert raw["dataset_id"] == "BYBIT_ETHBTC_V001"
    assert raw["split_version"] == 1
    if first.time() != datetime.min.time():
        assert first.date() + timedelta(days=1) == DEVELOPMENT_FIRST_DAY
    if last.time() != datetime.max.time().replace(microsecond=0):
        assert last.date() - timedelta(days=1) == DEVELOPMENT_LAST_DAY


def test_marker_validation(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(MarkerError):
        ensure_marker(missing)

    wrong = tmp_path / "wrong"
    wrong.write_text("OTRA_COSA\n")
    with pytest.raises(MarkerError):
        ensure_marker(wrong)

    good = tmp_path / ".lenovosrv-data-volume"
    good.write_text("LENOVO_DATA\nuuid=10fff707\n")
    ensure_marker(good)


def test_cli_two_days_and_idempotent_rerun(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dest = tmp_path / "ETHUSDT"
    fetcher = FakeFetcher(_payload())
    argv = ["--dest-dir", str(dest), "--dates", "2024-06-01,2024-06-02"]

    rc1 = cli.main(argv, fetcher=fetcher)
    out1 = capsys.readouterr().out
    rc2 = cli.main(argv, fetcher=NoCallFetcher())
    out2 = capsys.readouterr().out

    assert rc1 == 0 and rc2 == 0
    assert "SUMMARY downloaded=2 skipped=0 total=2" in out1
    assert "SUMMARY downloaded=0 skipped=2 total=2" in out2
    assert len(fetcher.urls) == 2


def test_cli_rejects_walk_forward_date(tmp_path: Path) -> None:
    fetcher = FakeFetcher(_payload())
    rc = cli.main(["--dest-dir", str(tmp_path), "--dates", "2025-06-17"], fetcher=fetcher)
    assert rc == 1
    assert fetcher.urls == []


def test_cli_rejects_bad_date_format() -> None:
    assert cli.main(["--dest-dir", "/tmp/x", "--dates", "ayer"]) == 2


def test_cli_require_marker(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dest = tmp_path / "ETHUSDT"
    marker = tmp_path / ".lenovosrv-data-volume"
    marker.write_text("LENOVO_DATA\n")

    rc_missing = cli.main(
        [
            "--dest-dir",
            str(dest),
            "--dates",
            "2024-06-01",
            "--require-marker",
            str(tmp_path / "nope"),
        ],
        fetcher=FakeFetcher(_payload()),
    )
    rc_ok = cli.main(
        ["--dest-dir", str(dest), "--dates", "2024-06-01", "--require-marker", str(marker)],
        fetcher=FakeFetcher(_payload()),
    )
    capsys.readouterr()
    assert rc_missing == 1
    assert rc_ok == 0


def test_urllib_fetch_streams_to_file(tmp_path: Path) -> None:
    src = tmp_path / "orig.bin"
    src.write_bytes(b"x" * (1 << 20) + b"tail")
    dest = tmp_path / "copied.bin"

    written = urllib_fetch(src.as_uri(), dest)

    assert written == src.stat().st_size
    assert dest.read_bytes() == src.read_bytes()


def test_download_days_creates_partition_tree(tmp_path: Path) -> None:
    days = [date(2024, 6, 1), date(2024, 6, 2)]
    fetcher = FakeFetcher(_payload())

    results = download_days(tmp_path, "ETHUSDT", days, fetcher=fetcher)

    assert [r.status for r in results] == ["downloaded", "downloaded"]
    assert len(list(tmp_path.glob("date=*/ETHUSDT_*.csv.gz"))) == 2


def test_validate_gzip_rejects_plain_file(tmp_path: Path) -> None:
    plain = tmp_path / "x.gz"
    plain.write_bytes(b"sin magic")
    with pytest.raises(InvalidGzipError):
        validate_gzip_file(plain)

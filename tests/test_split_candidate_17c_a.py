"""FASE 17C-A — Minimal validation of splits/CANDIDATE.json (proposal only).

No strategy, no backtest, no replay, no trading metrics, no holdout access
beyond boundary timestamps. The validator below only checks geometry of the
[start, end) row ranges against the official dataset CSV.
"""

import copy
import csv
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
CANDIDATE = REPO / "splits" / "CANDIDATE.json"
CSV = REPO / "datasets" / "BYBIT_ETHBTC_V001" / "ETHUSDT_15m.csv"
MANIFEST = REPO / "docs" / "datasets" / "BYBIT_ETHBTC_V001.manifest.json"

STEP_MS = 15 * 60 * 1000  # 15m timeframe


def load_candidate() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(CANDIDATE.read_text())
    return data


def load_csv_timestamps() -> list[int]:
    with open(CSV, newline="") as f:
        return [int(r["timestamp_ms"]) for r in csv.DictReader(f)]


def validate(candidate: dict[str, Any], total_rows: int) -> list[str]:
    """Return a list of geometry errors (empty = valid)."""
    errors: list[str] = []
    splits = candidate.get("splits", [])
    names = [s.get("name") for s in splits]
    if names != ["DEVELOPMENT", "WALK_FORWARD", "FINAL_HOLDOUT"]:
        errors.append(f"bad split names/order: {names}")
        return errors
    for s in splits:
        for key in ("row_start", "row_end", "rows", "first_timestamp", "last_timestamp"):
            if key not in s:
                errors.append(f"{s.get('name')}: missing {key}")
        if s["row_end"] - s["row_start"] != s["rows"]:
            errors.append(f"{s['name']}: rows != row_end - row_start")
        if not (0 <= s["row_start"] < s["row_end"] <= total_rows):
            errors.append(f"{s['name']}: range out of bounds")
    ordered = sorted(splits, key=lambda s: s["row_start"])
    if ordered != splits:
        errors.append("splits not in temporal order")
    for prev, nxt in zip(splits, splits[1:], strict=False):
        if nxt["row_start"] != prev["row_end"]:
            errors.append(
                f"gap/overlap between {prev['name']} end={prev['row_end']} "
                f"and {nxt['name']} start={nxt['row_start']}"
            )
        if nxt["first_timestamp"] <= prev["last_timestamp"]:
            errors.append(f"timestamps not increasing at {prev['name']}->{nxt['name']}")
    if sum(s["rows"] for s in splits) != total_rows:
        errors.append("rows do not sum to total")
    if splits[0]["row_start"] != 0:
        errors.append("first split does not start at row 0")
    if splits[-1]["row_end"] != total_rows:
        errors.append("FINAL_HOLDOUT does not end at last row")
    return errors


def expected_from_source() -> dict[str, Any]:
    """Deterministic rebuild of the expected geometry from manifest + CSV."""
    import hashlib

    manifest = json.loads(MANIFEST.read_text())
    entry = next(
        f for f in manifest["files"] if f["symbol"] == "ETHUSDT" and f["timeframe"] == "15m"
    )
    ts = load_csv_timestamps()
    total = len(ts)
    assert total == entry["row_count"]
    bounds = [
        ("DEVELOPMENT", 0, 62208),
        ("WALK_FORWARD", 62208, 88128),
        ("FINAL_HOLDOUT", 88128, 103680),
    ]
    assert sum(e - s for _, s, e in bounds) == total
    out = []
    for name, s, e in bounds:
        out.append(
            {
                "name": name,
                "row_start": s,
                "row_end": e,
                "rows": e - s,
                "first_timestamp": datetime.fromtimestamp(ts[s] / 1000, tz=UTC).isoformat(),
                "last_timestamp": datetime.fromtimestamp(ts[e - 1] / 1000, tz=UTC).isoformat(),
            }
        )
    return {
        "dataset_id": manifest["dataset_version"],
        "dataset_manifest_sha": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "total_rows": total,
        "splits": out,
    }


def test_rows_sum_to_total() -> None:
    cand = load_candidate()
    assert sum(s["rows"] for s in cand["splits"]) == cand["total_rows"] == 103680


def test_no_overlap_no_gaps_full_coverage() -> None:
    cand = load_candidate()
    splits = cand["splits"]
    assert splits[0]["row_start"] == 0
    for prev, nxt in zip(splits, splits[1:], strict=False):
        assert nxt["row_start"] == prev["row_end"], "gap or overlap"
    assert splits[-1]["row_end"] == cand["total_rows"]


def test_temporal_order_and_continuity() -> None:
    cand = load_candidate()
    ts = load_csv_timestamps()
    splits = cand["splits"]
    for prev, nxt in zip(splits, splits[1:], strict=False):
        assert nxt["first_timestamp"] > prev["last_timestamp"]
        # contiguity: next first candle is exactly one 15m step after prev last
        prev_last_ms = ts[prev["row_end"] - 1]
        nxt_first_ms = ts[nxt["row_start"]]
        assert nxt_first_ms - prev_last_ms == STEP_MS


def test_final_holdout_ends_at_last_row() -> None:
    cand = load_candidate()
    ts = load_csv_timestamps()
    hold = cand["splits"][-1]
    assert hold["name"] == "FINAL_HOLDOUT"
    assert hold["row_end"] == len(ts) == cand["total_rows"]
    last_iso = datetime.fromtimestamp(ts[-1] / 1000, tz=UTC).isoformat()
    assert hold["last_timestamp"] == last_iso


def test_split_timestamps_match_csv() -> None:
    cand = load_candidate()
    ts = load_csv_timestamps()
    for s in cand["splits"]:
        first = datetime.fromtimestamp(ts[s["row_start"]] / 1000, tz=UTC).isoformat()
        last = datetime.fromtimestamp(ts[s["row_end"] - 1] / 1000, tz=UTC).isoformat()
        assert s["first_timestamp"] == first
        assert s["last_timestamp"] == last


def test_deterministic_for_same_manifest() -> None:
    cand = load_candidate()
    exp = expected_from_source()
    assert cand["dataset_id"] == exp["dataset_id"] == "BYBIT_ETHBTC_V001"
    assert cand["dataset_manifest_sha"] == exp["dataset_manifest_sha"]
    assert cand["total_rows"] == exp["total_rows"]
    for got, want in zip(cand["splits"], exp["splits"], strict=True):
        for key in ("name", "row_start", "row_end", "rows", "first_timestamp", "last_timestamp"):
            assert got[key] == want[key], key
    # rebuild twice -> identical geometry
    assert expected_from_source()["splits"] == exp["splits"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["splits"][1].update(row_start=62209),  # gap
        lambda c: c["splits"][1].update(row_start=62207),  # overlap
        lambda c: c["splits"][2].update(row_end=103679),  # truncated holdout
        lambda c: c["splits"].__setitem__(0, {**c["splits"][0], "rows": 1}),  # bad count
    ],
)
def test_invalid_ranges_fail(mutate: Callable[[dict[str, Any]], None]) -> None:
    cand = load_candidate()
    bad = copy.deepcopy(cand)
    mutate(bad)
    assert validate(bad, cand["total_rows"]), "invalid ranges must fail validation"


def test_valid_candidate_passes_validator() -> None:
    cand = load_candidate()
    assert validate(cand, cand["total_rows"]) == []

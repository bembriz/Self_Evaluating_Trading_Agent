"""Tests fase 17C-B: split v1 congelado, estado inicial del holdout y guard.

Solo geometría de rangos [start, end) + estado. Sin estrategias, sin backtest,
sin replay, sin métricas sobre FINAL_HOLDOUT.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lab.splits import (
    DATASET_ID,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    FINAL_HOLDOUT_END,
    FINAL_HOLDOUT_START,
    SPLIT_VERSION,
    TOTAL_ROWS,
    WALK_FORWARD_END,
    WALK_FORWARD_START,
    is_holdout_range,
)

REPO = Path(__file__).resolve().parents[2]
CANDIDATE = REPO / "splits" / "CANDIDATE.json"
SPLIT_V1 = REPO / "splits" / "v1.json"
HOLDOUT_STATE = REPO / "holdout" / "v1.state.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def test_split_v1_matches_approved_candidate() -> None:
    cand = load_json(CANDIDATE)
    v1 = load_json(SPLIT_V1)
    assert v1["dataset_id"] == cand["dataset_id"] == DATASET_ID == "BYBIT_ETHBTC_V001"
    assert v1["dataset_manifest_sha"] == cand["dataset_manifest_sha"]
    assert v1["total_rows"] == cand["total_rows"] == TOTAL_ROWS == 103680
    assert v1["split_version"] == SPLIT_VERSION == 1
    assert v1["splits"] == cand["splits"]
    got = [(s["row_start"], s["row_end"]) for s in v1["splits"]]
    assert got == [(0, 62208), (62208, 88128), (88128, 103680)]


def test_split_v1_geometry() -> None:
    v1 = load_json(SPLIT_V1)
    splits = v1["splits"]
    assert [s["name"] for s in splits] == ["DEVELOPMENT", "WALK_FORWARD", "FINAL_HOLDOUT"]
    assert splits[0]["row_start"] == 0
    for prev, nxt in zip(splits, splits[1:], strict=False):
        assert nxt["row_start"] == prev["row_end"]  # sin huecos ni solapes
        assert nxt["first_timestamp"] > prev["last_timestamp"]
    assert sum(s["rows"] for s in splits) == v1["total_rows"]
    assert splits[-1]["row_end"] == v1["total_rows"]  # holdout llega a la última fila


def test_split_v1_deterministic_except_approval() -> None:
    cand = load_json(CANDIDATE)
    v1 = load_json(SPLIT_V1)
    rebuilt = {
        "dataset_id": cand["dataset_id"],
        "dataset_manifest_sha": cand["dataset_manifest_sha"],
        "total_rows": cand["total_rows"],
        "split_version": 1,
        "timeframe": cand["timeframe"],
        "symbol": cand["symbol"],
        "row_convention": cand["row_convention"],
        "splits": cand["splits"],
    }
    for key, value in rebuilt.items():
        assert v1[key] == value, key
    approval = v1["human_approval"]
    assert approval["approved"] is True
    assert approval["reason"] == "HUMAN_SPLIT_FREEZE_GATE"
    assert isinstance(approval["approved_at"], str) and approval["approved_at"]


def test_holdout_state_pristine() -> None:
    state = load_json(HOLDOUT_STATE)
    assert state == {
        "holdout_id": "BYBIT_ETHBTC_V001-holdout-v1",
        "split_version": 1,
        "state": "PRISTINE",
    }


def test_module_constants_match_frozen_split() -> None:
    v1 = load_json(SPLIT_V1)
    by_name = {s["name"]: s for s in v1["splits"]}
    assert (
        by_name["DEVELOPMENT"]["row_start"],
        by_name["DEVELOPMENT"]["row_end"],
    ) == (DEVELOPMENT_START, DEVELOPMENT_END)
    assert (
        by_name["WALK_FORWARD"]["row_start"],
        by_name["WALK_FORWARD"]["row_end"],
    ) == (WALK_FORWARD_START, WALK_FORWARD_END)
    assert (
        by_name["FINAL_HOLDOUT"]["row_start"],
        by_name["FINAL_HOLDOUT"]["row_end"],
    ) == (FINAL_HOLDOUT_START, FINAL_HOLDOUT_END)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (0, 62208),  # development completo permitido
        (100, 200),  # dentro de development permitido
        (62208, 88128),  # walk-forward completo permitido
        (70000, 80000),  # dentro de walk-forward permitido
        (0, 88128),  # todo lo anterior al holdout permitido
        (88127, 88128),  # termina exactamente donde empieza el holdout
    ],
)
def test_research_ranges_allowed(start: int, end: int) -> None:
    assert is_holdout_range(start, end) is False


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (88128, 103680),  # holdout completo rechazado
        (90000, 95000),  # dentro del holdout rechazado
        (88128, 88129),  # primera fila del holdout rechazada
        (103679, 103680),  # última fila del holdout rechazada
        (80000, 90000),  # cruza hacia el holdout rechazado
        (0, 103680),  # dataset completo cruza el holdout rechazado
    ],
)
def test_holdout_ranges_rejected(start: int, end: int) -> None:
    assert is_holdout_range(start, end) is True


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (-1, 100),  # start negativo
        (0, 103681),  # end más allá del total
        (500, 500),  # rango vacío
        (600, 100),  # start > end
        (88128, 88128),  # vacío en el borde del holdout
    ],
)
def test_invalid_ranges_rejected(start: int, end: int) -> None:
    with pytest.raises(ValueError):
        is_holdout_range(start, end)


def test_non_integer_bounds_rejected() -> None:
    with pytest.raises(ValueError):
        is_holdout_range(True, 100)
    with pytest.raises(ValueError):
        is_holdout_range(0, 103680.0)  # type: ignore[arg-type]

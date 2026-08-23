"""Esquemas de validación de respuestas Bybit REST v5 (Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel


class KlineResult(BaseModel):
    category: str
    symbol: str
    list: list[list[str]]


class KlineResponse(BaseModel):
    retCode: int
    retMsg: str
    result: KlineResult
    time: int

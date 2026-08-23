"""Esquemas de validación de mensajes WebSocket públicos de Bybit v5 (Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel


class WsOrderbookData(BaseModel):
    s: str
    b: list[list[str]]
    a: list[list[str]]
    u: int
    seq: int


class WsOrderbookMessage(BaseModel):
    topic: str
    type: str
    ts: int
    data: WsOrderbookData


class WsKlineItem(BaseModel):
    start: int
    end: int
    interval: str
    open: str
    close: str
    high: str
    low: str
    volume: str
    turnover: str
    confirm: bool
    timestamp: int


class WsKlineMessage(BaseModel):
    topic: str
    type: str
    data: list[WsKlineItem]
    ts: int

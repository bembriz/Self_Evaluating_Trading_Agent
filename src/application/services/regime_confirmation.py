from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from domain.market.regime import MarketRegime, RegimeClassifier


@dataclass(frozen=True, slots=True)
class RegimeEvidence:
    name: str
    symbol: str
    timeframe: str
    first_seen_at_ms: int
    confirmed_at_ms: int
    last_seen_at_ms: int
    classifier_version: str
    confirmation_candles: int


class RegimeConfirmationTracker:
    def __init__(
        self,
        *,
        symbol: str,
        timeframe: str,
        confirmation_candles: int = 3,
    ) -> None:
        if confirmation_candles < 1:
            raise ValueError("confirmation_candles must be positive")
        self._symbol = symbol
        self._timeframe = timeframe
        self._confirmation_candles = confirmation_candles
        self._pending_name: str | None = None
        self._pending_first_seen_at_ms: int | None = None
        self._pending_count = 0
        self._evidence: dict[str, RegimeEvidence] = {}
        self._rejected_candidates = 0

    @property
    def rejected_candidates(self) -> int:
        return self._rejected_candidates

    def observe(self, regime: MarketRegime | None, timestamp_ms: int) -> None:
        name = regime.name if regime is not None else None
        if name is None:
            self._reset_pending(rejected=self._pending_count < self._confirmation_candles)
            return

        if name != self._pending_name:
            self._reset_pending(rejected=self._pending_count < self._confirmation_candles)
            self._pending_name = name
            self._pending_first_seen_at_ms = timestamp_ms
            self._pending_count = 1
        else:
            self._pending_count += 1

        if self._pending_count < self._confirmation_candles:
            return

        existing = self._evidence.get(name)
        if existing is None:
            self._evidence[name] = RegimeEvidence(
                name=name,
                symbol=self._symbol,
                timeframe=self._timeframe,
                first_seen_at_ms=self._pending_first_seen_at_ms or timestamp_ms,
                confirmed_at_ms=timestamp_ms,
                last_seen_at_ms=timestamp_ms,
                classifier_version=RegimeClassifier.version,
                confirmation_candles=self._confirmation_candles,
            )
        else:
            self._evidence[name] = replace(existing, last_seen_at_ms=timestamp_ms)

    def evidence(self) -> list[dict[str, object]]:
        return [asdict(item) for item in self._evidence.values()]

    def _reset_pending(self, *, rejected: bool) -> None:
        if rejected and self._pending_name is not None:
            self._rejected_candidates += 1
        self._pending_name = None
        self._pending_first_seen_at_ms = None
        self._pending_count = 0

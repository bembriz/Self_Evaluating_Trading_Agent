from application.services.regime_confirmation import RegimeConfirmationTracker
from domain.market.regime import MarketRegime


def test_confirms_regime_on_third_consecutive_observation() -> None:
    tracker = RegimeConfirmationTracker(symbol="ETHUSDT", timeframe="15m")

    for timestamp_ms in (1_000, 2_000, 3_000):
        tracker.observe(MarketRegime.SIDEWAYS, timestamp_ms)

    assert tracker.evidence() == [
        {
            "name": "SIDEWAYS",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "first_seen_at_ms": 1_000,
            "confirmed_at_ms": 3_000,
            "last_seen_at_ms": 3_000,
            "classifier_version": "regime-v1",
            "confirmation_candles": 3,
        }
    ]


def test_interrupted_candidate_is_rejected_and_not_confirmed() -> None:
    tracker = RegimeConfirmationTracker(symbol="ETHUSDT", timeframe="15m")

    tracker.observe(MarketRegime.TREND_UP, 1_000)
    tracker.observe(MarketRegime.TREND_UP, 2_000)
    tracker.observe(MarketRegime.SIDEWAYS, 3_000)

    assert tracker.evidence() == []
    assert tracker.rejected_candidates == 1


def test_none_breaks_pending_streak_without_confirming() -> None:
    tracker = RegimeConfirmationTracker(symbol="ETHUSDT", timeframe="15m")

    tracker.observe(MarketRegime.TREND_UP, 1_000)
    tracker.observe(None, 2_000)
    tracker.observe(MarketRegime.TREND_UP, 3_000)
    tracker.observe(MarketRegime.TREND_UP, 4_000)

    assert tracker.evidence() == []
    assert tracker.rejected_candidates == 1


def test_confirmed_regime_is_not_duplicated_and_updates_latest_timestamp() -> None:
    tracker = RegimeConfirmationTracker(symbol="ETHUSDT", timeframe="15m")

    for timestamp_ms in range(1_000, 7_000, 1_000):
        tracker.observe(MarketRegime.SIDEWAYS, timestamp_ms)

    assert tracker.evidence()[0]["confirmed_at_ms"] == 3_000
    assert tracker.evidence()[0]["last_seen_at_ms"] == 6_000
    assert len(tracker.evidence()) == 1

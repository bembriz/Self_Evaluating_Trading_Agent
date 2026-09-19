#!/usr/bin/env python3
"""Phase 22-A — Authoritative exit reason capture.

Uses the EXACT authoritative configuration:
  RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")

This produces the SAME trade population as the authoritative replay:
  baseline=634, donchian=1086, bollinger=460

Captures PaperEvent.exit_reason directly from the engine during replay.
No runtime source modifications. Evidence-generation only.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

SRC = Path(__file__).resolve().parents[4] / "src"
sys.path.insert(0, str(SRC))

from domain.evaluation.metrics import PerformanceMetrics, compute_metrics
from domain.market.candle import Candle, Timeframe
from domain.portfolio.portfolio import Portfolio, Trade
from domain.risk.config import RiskConfig
from domain.trading.decision import TradingDecision
from domain.trading.fees import FeeModel
from domain.trading.signal import Action, Intensity
from domain.trading.slippage import SlippageModel

REPO = Path(__file__).resolve().parents[4]
CSV_PATH = REPO / "datasets" / "BYBIT_ETHBTC_V001" / "ETHUSDT_15m.csv"
SPLIT_PATH = REPO / "splits" / "v1.json"

SLIPPAGE_BPS = 2.0
FEE_TAKER_BPS = 10.0
FEE_MAKER_BPS = 10.0
CAPITAL = 1000.0
MINUTES_PER_YEAR = 366 * 24 * 60
NOT_AVAILABLE = "NOT_AVAILABLE"

# EXACT authoritative configuration (from Phase 20B registry)
AUTHORITATIVE_CONFIG = RiskConfig(
    stop_loss_required=False,
    version="risk-v1-nostop-mvp-a",
)


def load_candles(row_start: int, row_end: int) -> list[Candle]:
    candles: list[Candle] = []
    with CSV_PATH.open() as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i < row_start:
                continue
            if i >= row_end:
                break
            candles.append(
                Candle(
                    timestamp_ms=int(row["timestamp_ms"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    turnover=float(row["turnover"]),
                )
            )
    return candles


def run_strategy(
    strategy_name: str,
    strategy,
    candles: list[Candle],
) -> tuple[list[dict], Portfolio, PerformanceMetrics, dict[int, str]]:
    """Run through real PaperEngine using AUTHORITATIVE config.

    EXACT match to LabSessionRunner: atr=None (not computed ATR).
    Captures exit reasons from PaperEvent.
    """
    from application.services.paper_engine import PaperEngine

    cfg = AUTHORITATIVE_CONFIG  # EXACT authoritative config
    fee_model = FeeModel(taker_bps=FEE_TAKER_BPS, maker_bps=FEE_MAKER_BPS)
    slippage_model = SlippageModel(bps=SLIPPAGE_BPS)
    engine = PaperEngine(config=cfg, fee_model=fee_model, slippage_model=slippage_model)

    # NOTE: LabSessionRunner passes atr=None, NOT computed ATR
    # This is the KEY difference from the diagnostic run
    equity_curve: list[float] = []
    open_bars = 0

    # Capture exit reasons keyed by exit timestamp
    exit_reasons_by_ts: dict[int, str] = {}

    for i, candle in enumerate(candles):
        signal = strategy.on_candle(candle)
        decision = TradingDecision(
            timestamp_ms=candle.timestamp_ms,
            action=signal.action,
            confidence=1.0,
            intensity=Intensity.MEDIUM,
            rationale_summary=signal.reason,
        )
        # EXACT match to LabSessionRunner: atr=None
        event = engine.on_price(
            decision=decision,
            price=candle.close,
            atr=None,  # KEY: LabSessionRunner uses atr=None
            timestamp_ms=candle.timestamp_ms,
        )
        # Capture exit reason from PaperEvent
        if event.filled and event.action is Action.SELL and event.exit_reason:
            exit_reasons_by_ts[candle.timestamp_ms] = event.exit_reason
        if engine.position is not None:
            open_bars += 1
        equity_curve.append(engine.mark_to_market(price=candle.close))

    portfolio = engine.portfolio
    exposure = open_bars / len(candles) if candles else 0.0
    periods_per_year = MINUTES_PER_YEAR / 15.0
    metrics = compute_metrics(
        portfolio.trades,
        equity_curve,
        periods_per_year=periods_per_year,
        llm_cost=0.0,
        exposure=exposure,
    )

    ref_prices = {c.timestamp_ms: c.close for c in candles}

    ledger_rows = []
    for idx, t in enumerate(portfolio.trades):
        entry_ref = ref_prices.get(t.entry_ts, None)
        exit_ref = ref_prices.get(t.exit_ts, None)

        gross_exec = t.gross_pnl
        net_corrected = gross_exec - t.fees

        if entry_ref is not None and exit_ref is not None:
            gross_ref = (exit_ref - entry_ref) * t.quantity
        else:
            gross_ref = None

        analytical_slippage = (gross_ref - gross_exec) if gross_ref is not None else t.slippage

        if gross_ref is not None:
            net_from_ref = gross_ref - analytical_slippage - t.fees
            reconciliation_error = abs(net_corrected - net_from_ref)
        else:
            reconciliation_error = None

        entry_slip_usdt = t.quantity * SLIPPAGE_BPS / 10_000 * (entry_ref or t.entry_price)
        exit_slip_usdt = t.quantity * SLIPPAGE_BPS / 10_000 * (exit_ref or t.exit_price)

        holding = _holding_duration(candles, t.entry_ts, t.exit_ts)

        # Use actual exit reason from PaperEvent, fallback to UNKNOWN
        exit_reason = exit_reasons_by_ts.get(t.exit_ts, "UNKNOWN")

        row = {
            "strategy": strategy_name,
            "trade_id": idx + 1,
            "entry_signal_timestamp": t.entry_ts,
            "entry_fill_timestamp": t.entry_ts,
            "exit_signal_timestamp": t.exit_ts,
            "exit_fill_timestamp": t.exit_ts,
            "entry_reference_price": entry_ref,
            "entry_execution_price": t.entry_price,
            "exit_reference_price": exit_ref,
            "exit_execution_price": t.exit_price,
            "quantity": t.quantity,
            "entry_fee_rate": FEE_TAKER_BPS / 10_000,
            "entry_fee_amount": t.fees / 2,
            "exit_fee_rate": FEE_TAKER_BPS / 10_000,
            "exit_fee_amount": t.fees / 2,
            "total_fees": t.fees,
            "entry_slippage_bps": SLIPPAGE_BPS,
            "entry_slippage_usdt": entry_slip_usdt,
            "exit_slippage_bps": SLIPPAGE_BPS,
            "exit_slippage_usdt": exit_slip_usdt,
            "total_analytical_slippage": analytical_slippage,
            "gross_pnl_reference": gross_ref,
            "gross_pnl_exec": gross_exec,
            "net_pnl_runtime": t.net_pnl,
            "net_pnl_corrected": net_corrected,
            "reconciliation_error": reconciliation_error,
            "exit_reason": exit_reason,
            "stop_price": NOT_AVAILABLE,
            "target_price": NOT_AVAILABLE,
            "holding_duration": holding,
            "MFE": NOT_AVAILABLE,
            "MAE": NOT_AVAILABLE,
            "entry_order_type": "NOT_MODELED",
            "entry_liquidity_role": "NOT_MODELED",
            "entry_execution_assumption": "MARKET_TAKER_EQUIVALENT",
            "exit_order_type": "NOT_MODELED",
            "exit_liquidity_role": "NOT_MODELED",
            "exit_execution_assumption": "MARKET_TAKER_EQUIVALENT",
        }
        ledger_rows.append(row)

    return ledger_rows, portfolio, metrics, exit_reasons_by_ts


def _holding_duration(candles: list[Candle], entry_ts: int, exit_ts: int) -> int:
    start_idx = None
    end_idx = None
    for i, c in enumerate(candles):
        if c.timestamp_ms == entry_ts:
            start_idx = i
        if c.timestamp_ms == exit_ts:
            end_idx = i
    if start_idx is not None and end_idx is not None:
        return end_idx - start_idx
    return 0


def compute_exit_reason_analysis(rows: list[dict]) -> dict:
    """Per-exit-reason decomposition with counts, rates, and PnL."""
    by_reason = defaultdict(list)
    for r in rows:
        by_reason[r["exit_reason"]].append(r)

    total_trades = len(rows)
    analysis = {}
    for reason, reason_rows in sorted(by_reason.items()):
        n = len(reason_rows)
        wins = sum(1 for r in reason_rows if r["net_pnl_corrected"] > 0)

        # Holding times
        holdings = [r["holding_duration"] for r in reason_rows]

        # Returns in bps
        returns_bps = []
        for r in reason_rows:
            if r["gross_pnl_reference"] is not None and r["entry_reference_price"] is not None:
                ret_bps = (r["gross_pnl_reference"] / r["quantity"] / r["entry_reference_price"]) * 10_000 if r["quantity"] > 0 and r["entry_reference_price"] > 0 else 0
                returns_bps.append(ret_bps)

        analysis[reason] = {
            "count": n,
            "rate": n / total_trades if total_trades > 0 else 0,
            "avg_gross_ref": mean(r["gross_pnl_reference"] for r in reason_rows if r["gross_pnl_reference"] is not None) if any(r["gross_pnl_reference"] is not None for r in reason_rows) else None,
            "avg_gross_exec": mean(r["gross_pnl_exec"] for r in reason_rows),
            "avg_fees": mean(r["total_fees"] for r in reason_rows),
            "avg_slippage": mean(r["total_analytical_slippage"] for r in reason_rows),
            "avg_net_corrected": mean(r["net_pnl_corrected"] for r in reason_rows),
            "total_net_pnl": sum(r["net_pnl_corrected"] for r in reason_rows),
            "win_rate": wins / n if n > 0 else 0,
            "avg_holding_bars": mean(holdings) if holdings else 0,
            "median_holding_bars": median(holdings) if holdings else 0,
            "avg_return_bps": mean(returns_bps) if returns_bps else 0,
        }
    return analysis


def main() -> None:
    split = json.loads(SPLIT_PATH.read_text())
    dev = next(s for s in split["splits"] if s["name"] == "DEVELOPMENT")
    candles = load_candles(dev["row_start"], dev["row_end"])
    print(f"Loaded {len(candles)} candles for DEVELOPMENT split")
    print(f"Using AUTHORITATIVE config: stop_loss_required=False, version=risk-v1-nostop-mvp-a")

    strategies = {}

    from domain.trading.strategy import EmaRsiBaseline
    strategies["baseline"] = EmaRsiBaseline()

    try:
        from lab.strategies.eth_donchian_breakout import EthDonchianBreakout
        strategies["donchian"] = EthDonchianBreakout(candles=candles)
    except Exception as e:
        print(f"WARNING: EthDonchianBreakout: {e}")

    try:
        from lab.strategies.eth_bollinger_mean_reversion import EthBollingerMeanReversion
        strategies["bollinger"] = EthBollingerMeanReversion(candles=candles)
    except Exception as e:
        print(f"WARNING: EthBollingerMeanReversion: {e}")

    all_rows = []
    summaries = {}
    exit_analyses = {}
    all_exit_reasons = {}

    for name, strategy in strategies.items():
        print(f"\nRunning {name}...")
        rows, portfolio, metrics, exit_reasons = run_strategy(name, strategy, candles)
        all_rows.extend(rows)

        n = len(portfolio.trades)
        if n == 0:
            print(f"  NO COMPLETED TRADES")
            continue

        gross_ref = sum(r["gross_pnl_reference"] for r in rows if r["gross_pnl_reference"] is not None)
        gross_exec = sum(r["gross_pnl_exec"] for r in rows)
        total_fees = sum(r["total_fees"] for r in rows)
        total_slip = sum(r["total_analytical_slippage"] for r in rows)
        net_corrected = sum(r["net_pnl_corrected"] for r in rows)

        winners = [r for r in rows if r["net_pnl_corrected"] > 0]
        losers = [r for r in rows if r["net_pnl_corrected"] < 0]

        # Exit reason counts
        reason_counts = defaultdict(int)
        for r in rows:
            reason_counts[r["exit_reason"]] += 1

        summaries[name] = {
            "completed_trades": n,
            "gross_pnl_reference": gross_ref,
            "gross_pnl_exec": gross_exec,
            "total_fees": total_fees,
            "total_analytical_slippage": total_slip,
            "net_pnl_corrected": net_corrected,
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "exit_reason_counts": dict(reason_counts),
        }

        exit_analyses[name] = compute_exit_reason_analysis(rows)
        all_exit_reasons[name] = exit_reasons

        print(f"  trades={n} gross_ref={gross_ref:.6f} gross_exec={gross_exec:.6f} "
              f"fees={total_fees:.6f} slip={total_slip:.6f} net_corrected={net_corrected:.6f}")
        print(f"  exit_reasons={dict(reason_counts)}")

    # Write enriched CSV
    ledgers_dir = Path(__file__).parent
    csv_path = ledgers_dir / "authoritative-exit-reasons.csv"
    if all_rows:
        fieldnames = list(all_rows[0].keys())
        with csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in all_rows:
                # Ensure full float precision in CSV output
                precise_row = {}
                for k, v in row.items():
                    if isinstance(v, float):
                        precise_row[k] = f"{v:.16g}"
                    else:
                        precise_row[k] = v
                writer.writerow(precise_row)
        print(f"Wrote {csv_path}")

    # Write exit reason analysis JSON
    json_path = ledgers_dir / "exit-reason-analysis.json"
    output = {
        "config": {
            "stop_loss_required": AUTHORITATIVE_CONFIG.stop_loss_required,
            "version": AUTHORITATIVE_CONFIG.version,
            "capital": AUTHORITATIVE_CONFIG.capital,
        },
        "strategies": summaries,
        "exit_reason_analysis": exit_analyses,
        "safety": {
            "real_walk_forward_reads": 0,
            "final_holdout_reads": 0,
            "final_holdout_executions": 0,
            "holdout_state": "PRISTINE",
        },
    }
    with json_path.open("w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Wrote {json_path}")

    # Print summary
    print("\n" + "=" * 72)
    print("EXIT REASON SUMMARY (AUTHORITATIVE CONFIGURATION)")
    print("=" * 72)
    for name in summaries:
        s = summaries[name]
        print(f"\n{name} ({s['completed_trades']} trades):")
        for reason, count in sorted(s["exit_reason_counts"].items()):
            print(f"  {reason:20s} = {count}")

        # Exit reason analysis
        if name in exit_analyses:
            print(f"\n  Exit Reason Analysis:")
            for reason, analysis in sorted(exit_analyses[name].items()):
                print(f"    {reason}:")
                print(f"      count={analysis['count']}, rate={analysis['rate']:.4f}")
                print(f"      avg_net_corrected={analysis['avg_net_corrected']:.6f}")
                print(f"      total_net_pnl={analysis['total_net_pnl']:.6f}")
                print(f"      avg_holding_bars={analysis['avg_holding_bars']:.1f}")
                print(f"      avg_return_bps={analysis['avg_return_bps']:.2f}")

    print(f"\nTOTAL_LEDGER_ROWS = {len(all_rows)}")

    # Verify trade counts match authoritative
    print("\n" + "=" * 72)
    print("AUTHORITATIVE POPULATION VERIFICATION")
    print("=" * 72)
    expected = {"baseline": 634, "donchian": 1086, "bollinger": 460}
    for name, expected_count in expected.items():
        actual_count = summaries.get(name, {}).get("completed_trades", 0)
        match = "PASS" if actual_count == expected_count else "FAIL"
        print(f"  {name}: expected={expected_count}, actual={actual_count}, match={match}")


if __name__ == "__main__":
    main()

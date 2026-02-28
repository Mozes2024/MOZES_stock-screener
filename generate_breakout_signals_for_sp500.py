#!/usr/bin/env python3
"""Generate breakout_signals.json for SP500-Quant-Ranker integration.

This script is a STANDALONE addition — it does NOT modify any existing MOZES files.
It reuses the existing MOZES screening infrastructure and produces breakout_signals.json
in the exact format expected by SP500-Quant-Ranker_2026.

The SP500-Quant-Ranker workflow fetches this file from:
  https://raw.githubusercontent.com/Mozes2024/MOZES_stock-screener/main/breakout_signals.json

Usage:
    python generate_breakout_signals_for_sp500.py
    python generate_breakout_signals_for_sp500.py --conservative
    python generate_breakout_signals_for_sp500.py --output /path/to/breakout_signals.json
    python generate_breakout_signals_for_sp500.py --min-score 65
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# ── MOZES internal imports (reuse existing infrastructure) ──────────────────
from src.data.universe_fetcher import USStockUniverseFetcher
from src.screening.optimized_batch_processor import OptimizedBatchProcessor
from src.screening.benchmark import (
    analyze_spy_trend,
    calculate_market_breadth,
    classify_market_regime,
    should_generate_signals,
)
from src.screening.signal_engine import score_buy_signal
from src.data.enhanced_fundamentals import EnhancedFundamentalsFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ── Formatting helpers ───────────────────────────────────────────────────────

def _clean_reasons(reasons: list) -> list:
    """Strip emoji from reason strings to keep JSON lightweight."""
    import re
    cleaned = []
    for r in reasons:
        # Remove common emoji used in signal_engine.py
        r = re.sub(r"[🟢🟡🔴✓⚠⭐🔵]+\s*", "", r).strip()
        if r:
            cleaned.append(r)
    return cleaned


def build_signal_entry(rank: int, signal: dict) -> dict:
    """Convert a raw MOZES buy-signal dict into SP500-Quant-Ranker JSON schema."""
    details = signal.get("details", {})
    vcp_data = details.get("vcp_data", {})

    current_price = signal.get("current_price", 0)
    stop_loss = signal.get("stop_loss")
    risk_reward = signal.get("risk_reward_ratio", 0)

    risk  = round(current_price - stop_loss, 2) if stop_loss and current_price else None
    reward = round(risk * risk_reward, 2) if risk and risk_reward else None

    return {
        "rank": rank,
        "ticker": signal["ticker"],
        "breakout_score": signal["score"],
        "phase": signal.get("phase", 2),
        "entry_quality": signal.get("entry_quality", ""),
        "stop_loss": round(stop_loss, 2) if stop_loss else None,
        "risk": risk,
        "reward": reward,
        "risk_reward": risk_reward,
        "rs": round(details.get("rs_slope", 0) or 0, 3),
        "breakout_price": signal.get("breakout_price"),
        "has_vcp": bool(vcp_data),
        "vcp_quality": vcp_data.get("quality", 0),
        "vcp_desc": vcp_data.get("pattern", ""),
        "reasons": _clean_reasons(signal.get("reasons", [])[:5]),
    }


# ── Main routine ─────────────────────────────────────────────────────────────

def run(args) -> bool:
    """Run the scan and write breakout_signals.json.  Returns True on success."""

    output_path = Path(args.output)
    min_score   = args.min_score
    workers     = 3 if args.conservative else 5

    logger.info("=" * 60)
    logger.info("BREAKOUT SIGNAL GENERATOR  (SP500-Quant-Ranker feed)")
    logger.info(f"  Output  : {output_path}")
    logger.info(f"  Min score: {min_score}")
    logger.info(f"  Workers : {workers}")
    logger.info(f"  Git cache: {args.git_storage}")
    logger.info("=" * 60)

    # ── 1. Fetch universe ───────────────────────────────────────────────────
    logger.info("Fetching stock universe…")
    fetcher = USStockUniverseFetcher()
    tickers = fetcher.fetch_universe()
    if args.max_stocks:
        tickers = tickers[:args.max_stocks]
    logger.info(f"Universe: {len(tickers):,} tickers")

    # ── 2. Run batch scan ───────────────────────────────────────────────────
    use_cache = args.git_storage
    processor = OptimizedBatchProcessor(max_workers=workers, use_git_storage=use_cache)
    if use_cache:
        logger.info("  Cache mode : Git-based fundamentals cache (data/fundamentals_cache/)")
    else:
        logger.info("  Cache mode : Fresh fetch from Yahoo Finance (no cache)")
    results   = processor.process_batch_parallel(
        tickers,
        min_price=args.min_price,
        min_volume=args.min_volume,
    )

    if "error" in results:
        logger.error(f"Scan failed: {results['error']}")
        return False

    # ── 3. Market context ────────────────────────────────────────────────────
    spy_analysis = analyze_spy_trend(processor.spy_data, processor.spy_price)
    breadth      = calculate_market_breadth(results["phase_results"])
    market_regime = classify_market_regime(spy_analysis, breadth)
    signal_rec   = should_generate_signals(spy_analysis, breadth)

    logger.info(f"Market regime : {market_regime}")
    logger.info(f"Phase-2 pct   : {breadth['phase_2_pct']:.1f}%")

    # ── 4. Score buy signals ─────────────────────────────────────────────────
    fundamentals_fetcher = EnhancedFundamentalsFetcher()

    buy_signals = []
    if signal_rec["should_generate_buys"]:
        for analysis in results["analyses"]:
            if analysis["phase_info"]["phase"] in [1, 2]:
                signal = score_buy_signal(
                    ticker      = analysis["ticker"],
                    price_data  = analysis["price_data"],
                    current_price = analysis["current_price"],
                    phase_info  = analysis["phase_info"],
                    rs_series   = analysis["rs_series"],
                    fundamentals = analysis.get("quarterly_data"),
                    vcp_data    = analysis.get("vcp_data"),
                )
                if signal["is_buy"] and signal["score"] >= min_score:
                    # Attach current price so build_signal_entry can compute risk/reward
                    signal["current_price"] = analysis["current_price"]
                    buy_signals.append(signal)
    else:
        logger.warning("Market conditions not suitable for buy signals — writing empty payload")

    buy_signals.sort(key=lambda s: s["score"], reverse=True)
    logger.info(f"Buy signals qualifying (>= {min_score}): {len(buy_signals)}")

    # ── 5. Build output JSON ─────────────────────────────────────────────────
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    date_str = datetime.utcnow().strftime("%Y-%m-%d")

    payload = {
        "scan_date"         : date_str,
        "generated"         : datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "converted_at"      : f"{now_str} UTC",
        "market_regime"     : market_regime,
        "total_buy_signals" : len(buy_signals),
        "phase2_pct"        : breadth["phase_2_pct"],
        "top_signals_count" : len(buy_signals),
        "top_signals"       : [
            build_signal_entry(rank + 1, sig)
            for rank, sig in enumerate(buy_signals)
        ],
    }

    # ── 6. Write file ────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    logger.info(f"✅  Written {output_path}  ({len(buy_signals)} signals)")
    return True


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate breakout_signals.json for SP500-Quant-Ranker"
    )
    parser.add_argument(
        "--output", default="breakout_signals.json",
        help="Output path (default: breakout_signals.json in repo root)"
    )
    parser.add_argument(
        "--min-score", type=float, default=60.0,
        help="Minimum signal score to include (default: 60)"
    )
    parser.add_argument(
        "--conservative", action="store_true",
        help="Use 3 workers instead of 5 to reduce rate-limit risk"
    )
    parser.add_argument(
        "--min-price", type=float, default=5.0,
        help="Minimum stock price filter (default: $5)"
    )
    parser.add_argument(
        "--min-volume", type=int, default=100_000,
        help="Minimum average daily volume filter (default: 100,000)"
    )
    parser.add_argument(
        "--max-stocks", type=int, default=None,
        help="Cap the universe size (useful for testing)"
    )
    parser.add_argument(
        "--git-storage", action="store_true", default=True,
        help="Use Git-based fundamentals cache (default: True). Disable with --no-git-storage."
    )
    parser.add_argument(
        "--no-git-storage", dest="git_storage", action="store_false",
        help="Disable Git-based cache — fetch all fundamentals fresh from Yahoo."
    )

    args = parser.parse_args()

    success = run(args)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

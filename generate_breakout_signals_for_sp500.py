#!/usr/bin/env python3
"""Generate breakout_signals.json for SP500-Quant-Ranker integration.

NEW ARCHITECTURE (v2):
  Instead of running a full market scan (~20-25 min), this script now reads
  the structured output from the daily scan (latest_structured_scan.pkl)
  and simply filters + formats → breakout_signals.json in ~2-3 seconds.

  The daily_screening workflow must run with --save-structured BEFORE this.

FALLBACK:
  If the pickle is missing or stale (>6 hours old), the script falls back
  to running a full scan (the old behaviour) so the pipeline never breaks.

Usage:
    python generate_breakout_signals_for_sp500.py                   # read from daily scan
    python generate_breakout_signals_for_sp500.py --min-score 65    # custom threshold
    python generate_breakout_signals_for_sp500.py --force-scan      # ignore pickle, do full scan
    python generate_breakout_signals_for_sp500.py --max-age 12      # accept pickle up to 12h old
"""

import argparse
import json
import logging
import pickle
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

STRUCTURED_SCAN_PATH = Path("./data/daily_scans/latest_structured_scan.pkl")


# ── Formatting helpers ───────────────────────────────────────────────────────

def _clean_reasons(reasons: list) -> list:
    """Strip emoji from reason strings to keep JSON lightweight."""
    cleaned = []
    for r in reasons:
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

    risk = round(current_price - stop_loss, 2) if stop_loss and current_price else None
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


# ── Pickle reader ────────────────────────────────────────────────────────────

def load_structured_scan(max_age_hours: float = 6.0) -> dict | None:
    """Load the daily scan pickle if it exists and is fresh enough.

    Returns the pickle payload dict, or None if unavailable/stale.
    """
    if not STRUCTURED_SCAN_PATH.exists():
        logger.warning(f"Structured scan not found: {STRUCTURED_SCAN_PATH}")
        return None

    # Check freshness
    mtime = datetime.fromtimestamp(STRUCTURED_SCAN_PATH.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - mtime
    if age > timedelta(hours=max_age_hours):
        logger.warning(
            f"Structured scan is {age.total_seconds()/3600:.1f}h old "
            f"(max {max_age_hours}h) — considered stale"
        )
        return None

    try:
        with open(STRUCTURED_SCAN_PATH, "rb") as f:
            data = pickle.load(f)
        logger.info(
            f"Loaded structured scan: {data.get('scan_date', '?')} | "
            f"{data.get('results', {}).get('total_analyzed', 0)} stocks analyzed | "
            f"{len(data.get('buy_signals', []))} buy signals | "
            f"age: {age.total_seconds()/60:.0f} min"
        )
        return data
    except Exception as e:
        logger.error(f"Failed to load pickle: {e}")
        return None


# ── Fallback: full scan (old behaviour) ──────────────────────────────────────

def run_full_scan(args) -> bool:
    """Original full-scan path. Used only as fallback when pickle is unavailable."""
    logger.info("FALLBACK: Running full market scan (pickle unavailable)")

    # Late imports to avoid loading heavy modules unless needed
    from src.data.universe_fetcher import USStockUniverseFetcher
    from src.screening.optimized_batch_processor import OptimizedBatchProcessor
    from src.screening.benchmark import (
        analyze_spy_trend,
        calculate_market_breadth,
        classify_market_regime,
        should_generate_signals,
    )
    from src.screening.signal_engine import score_buy_signal

    output_path = Path(args.output)
    min_score = args.min_score
    workers = 3 if args.conservative else 5

    fetcher = USStockUniverseFetcher()
    tickers = fetcher.fetch_universe()
    if args.max_stocks:
        tickers = tickers[: args.max_stocks]

    processor = OptimizedBatchProcessor(max_workers=workers, use_git_storage=args.git_storage)
    results = processor.process_batch_parallel(
        tickers, min_price=args.min_price, min_volume=args.min_volume
    )

    if "error" in results:
        logger.error(f"Scan failed: {results['error']}")
        return False

    spy_analysis = analyze_spy_trend(processor.spy_data, processor.spy_price)
    breadth = calculate_market_breadth(results["phase_results"])
    market_regime = classify_market_regime(spy_analysis, breadth)
    signal_rec = should_generate_signals(spy_analysis, breadth)

    buy_signals = []
    if signal_rec["should_generate_buys"]:
        for analysis in results["analyses"]:
            if analysis["phase_info"]["phase"] in [1, 2]:
                signal = score_buy_signal(
                    ticker=analysis["ticker"],
                    price_data=analysis["price_data"],
                    current_price=analysis["current_price"],
                    phase_info=analysis["phase_info"],
                    rs_series=analysis["rs_series"],
                    fundamentals=analysis.get("quarterly_data"),
                    vcp_data=analysis.get("vcp_data"),
                )
                if signal["is_buy"] and signal["score"] >= min_score:
                    signal["current_price"] = analysis["current_price"]
                    buy_signals.append(signal)

    buy_signals.sort(key=lambda s: s["score"], reverse=True)
    return _write_output(output_path, buy_signals, market_regime, breadth)


# ── Fast path: read from pickle ──────────────────────────────────────────────

def run_from_pickle(args, scan_data: dict) -> bool:
    """Fast path: filter pre-computed buy signals and write breakout_signals.json."""
    from src.screening.benchmark import classify_market_regime

    output_path = Path(args.output)
    min_score = args.min_score

    spy_analysis = scan_data["spy_analysis"]
    breadth = scan_data["breadth"]
    market_regime = classify_market_regime(spy_analysis, breadth)
    buy_signals = scan_data.get("buy_signals", [])

    # Filter by min_score
    qualified = [s for s in buy_signals if s.get("score", 0) >= min_score]

    # Attach current_price if missing (needed for risk/reward calc in build_signal_entry)
    # The daily scan already attaches it during scoring, but just in case:
    for sig in qualified:
        if "current_price" not in sig:
            sig["current_price"] = sig.get("details", {}).get("current_price", 0)

    qualified.sort(key=lambda s: s["score"], reverse=True)

    logger.info(f"Market regime : {market_regime}")
    logger.info(f"Phase-2 pct   : {breadth.get('phase_2_pct', 0):.1f}%")
    logger.info(f"Buy signals qualifying (>= {min_score}): {len(qualified)} / {len(buy_signals)} total")

    return _write_output(output_path, qualified, market_regime, breadth)


# ── Shared output writer ─────────────────────────────────────────────────────

def _write_output(output_path: Path, buy_signals: list, market_regime: str, breadth: dict) -> bool:
    """Write breakout_signals.json in the SP500-Quant-Ranker schema."""
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    date_str = datetime.utcnow().strftime("%Y-%m-%d")

    payload = {
        "scan_date": date_str,
        "generated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "converted_at": f"{now_str} UTC",
        "market_regime": market_regime,
        "total_buy_signals": len(buy_signals),
        "phase2_pct": breadth.get("phase_2_pct", 0),
        "top_signals_count": len(buy_signals),
        "top_signals": [
            build_signal_entry(rank + 1, sig)
            for rank, sig in enumerate(buy_signals)
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    logger.info(f"✅  Written {output_path}  ({len(buy_signals)} signals)")
    return True


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate breakout_signals.json for SP500-Quant-Ranker (v2 — reads from daily scan)"
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
        "--max-age", type=float, default=6.0,
        help="Max age in hours for the structured scan pickle (default: 6)"
    )
    parser.add_argument(
        "--force-scan", action="store_true",
        help="Ignore pickle and run a full market scan (fallback behaviour)"
    )
    # ── Fallback-only flags (used when pickle is unavailable) ────────────────
    parser.add_argument("--conservative", action="store_true", help="Fallback: use 3 workers")
    parser.add_argument("--min-price", type=float, default=5.0, help="Fallback: min stock price")
    parser.add_argument("--min-volume", type=int, default=100_000, help="Fallback: min avg daily volume")
    parser.add_argument("--max-stocks", type=int, default=None, help="Fallback: cap universe size")
    parser.add_argument("--git-storage", action="store_true", default=True, help="Fallback: use Git cache")
    parser.add_argument("--no-git-storage", dest="git_storage", action="store_false", help="Fallback: disable Git cache")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("BREAKOUT SIGNAL GENERATOR v2  (SP500-Quant-Ranker feed)")
    logger.info(f"  Output   : {args.output}")
    logger.info(f"  Min score: {args.min_score}")
    logger.info(f"  Max age  : {args.max_age}h")
    logger.info(f"  Mode     : {'force-scan' if args.force_scan else 'pickle-first'}")
    logger.info("=" * 60)

    success = False

    if not args.force_scan:
        scan_data = load_structured_scan(max_age_hours=args.max_age)
        if scan_data:
            import time
            t0 = time.time()
            success = run_from_pickle(args, scan_data)
            elapsed = time.time() - t0
            logger.info(f"⚡ Fast path completed in {elapsed:.1f}s")

    if not success:
        logger.info("Falling back to full market scan…")
        success = run_full_scan(args)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

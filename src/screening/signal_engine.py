"""
Signal detection and scoring engine for buy/sell decisions.

Enhanced with:
- Multi-horizon momentum scoring (3m / 12m)
- Relative Strength bonus vs benchmark
- Risk penalties (volatility + drawdown)
- Explainable score breakdown
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .phase_indicators import (
    calculate_volume_ratio,
    calculate_rs_slope,
    detect_volatility_contraction,
    detect_breakout,
    validate_minervini_trend_template,
    calculate_sma
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =========================
# Helper metrics
# =========================

def _safe_pct_change(series: pd.Series, periods: int) -> float:
    if len(series) < periods + 1:
        return 0.0
    return (series.iloc[-1] / series.iloc[-periods - 1] - 1.0) * 100.0


def _annualized_volatility(returns: pd.Series) -> float:
    if len(returns) < 20:
        return 0.0
    return returns.std() * np.sqrt(252) * 100.0


def _max_drawdown(prices: pd.Series) -> float:
    if prices.empty:
        return 0.0
    peak = prices.expanding().max()
    dd = (prices - peak) / peak
    return abs(dd.min()) * 100.0


# =========================
# Stop Loss
# =========================

def calculate_stop_loss(
    price_data: pd.DataFrame,
    current_price: float,
    phase_info: Dict,
    phase: int
) -> float:
    sma_50 = calculate_sma(price_data, 50)

    if phase == 2:
        recent_low = price_data["Low"].rolling(20).min().iloc[-1]
        stop = max(recent_low, sma_50.iloc[-1])
    else:
        stop = price_data["Low"].rolling(50).min().iloc[-1]

    return min(stop, current_price * 0.94)


# =========================
# BUY Signal Scoring
# =========================

def score_buy_signal(
    symbol: str,
    price_data: pd.DataFrame,
    volume_data: pd.Series,
    phase_info: Dict,
    benchmark_rs_slope: float,
    market_regime: Optional[str] = None
) -> Dict:
    """
    Returns a buy score with detailed breakdown.
    """

    score = 0.0
    details: Dict[str, float] = {}

    close = price_data["Close"]
    returns = close.pct_change().dropna()

    # -------------------------
    # Phase & Trend Validation
    # -------------------------
    phase = phase_info.get("phase", 0)
    details["phase"] = phase

    if phase != 2:
        return {"score": 0.0, "details": details}

    if not validate_minervini_trend_template(price_data):
        return {"score": 0.0, "details": details}

    score += 2.0
    details["trend_template"] = 2.0

    # -------------------------
    # Momentum (Multi-Horizon)
    # -------------------------
    ret_63 = _safe_pct_change(close, 63)
    ret_252 = _safe_pct_change(close, 252)

    momentum_score = 0.0
    if ret_252 > 0:
        momentum_score += min(ret_252 / 20.0, 3.0)
    if ret_63 > 0:
        momentum_score += min(ret_63 / 10.0, 2.0)

    score += momentum_score
    details["momentum_3m_pct"] = ret_63
    details["momentum_12m_pct"] = ret_252
    details["momentum_score"] = momentum_score

    # -------------------------
    # Relative Strength Bonus
    # -------------------------
    rs_slope = calculate_rs_slope(price_data)
    rs_bonus = 0.0

    if rs_slope > benchmark_rs_slope:
        rs_bonus = min((rs_slope - benchmark_rs_slope) * 10.0, 3.0)

    score += rs_bonus
    details["rs_slope"] = rs_slope
    details["rs_bonus"] = rs_bonus

    # -------------------------
    # Volume & Breakout
    # -------------------------
    volume_ratio = calculate_volume_ratio(volume_data)
    if volume_ratio > 1.5:
        score += 1.5
        details["volume_confirmation"] = 1.5

    if detect_breakout(price_data):
        score += 1.5
        details["breakout"] = 1.5

    if detect_volatility_contraction(price_data):
        score += 1.0
        details["volatility_contraction"] = 1.0

    # -------------------------
    # Risk Penalty
    # -------------------------
    vol = _annualized_volatility(returns)
    dd = _max_drawdown(close)

    risk_penalty = 0.0
    if vol > 35:
        risk_penalty += min((vol - 35) / 10.0, 5.0)
    if dd > 30:
        risk_penalty += min((dd - 30) / 10.0, 5.0)

    score -= risk_penalty
    details["volatility_pct"] = vol
    details["max_drawdown_pct"] = dd
    details["risk_penalty"] = risk_penalty

    # -------------------------
    # Final normalization
    # -------------------------
    score = max(score, 0.0)
    score = min(score, 10.0)

    details["final_score"] = score

    return {
        "score": score,
        "details": details
    }

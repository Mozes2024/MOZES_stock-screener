"""Signal detection and scoring engine for buy/sell decisions.

This module implements the buy and sell signal detection based on Phase transitions
and technical/fundamental confluence.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .phase_indicators import (
    calculate_volume_ratio,
    calculate_rs_slope,
    detect_volatility_contraction,
    detect_breakout
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def score_buy_signal(
    ticker: str,
    price_data: pd.DataFrame,
    current_price: float,
    phase_info: Dict,
    rs_series: pd.Series,
    fundamentals: Optional[Dict] = None
) -> Dict[str, any]:
    """Score a buy signal based on Phase 1->2 transition or Phase 2 breakout.

    Scoring Components (0-100):
    - Trend structure: 40 points
    - Volume confirmation: 20 points
    - Relative strength slope: 20 points
    - Volatility contraction quality: 20 points

    Fundamental contradiction: -10 points

    Only output scores >= 70

    Args:
        ticker: Stock ticker
        price_data: OHLCV data
        current_price: Current price
        phase_info: Phase classification
        rs_series: Relative strength series
        fundamentals: Optional fundamental snapshot

    Returns:
        Dict with buy signal score and details
    """
    phase = phase_info['phase']

    # Only consider Phase 1 and Phase 2
    if phase not in [1, 2]:
        return {
            'ticker': ticker,
            'is_buy': False,
            'score': 0,
            'reason': f'Wrong phase (Phase {phase})',
            'details': {}
        }

    score = 0
    details = {}
    reasons = []

    # 1. TREND STRUCTURE (40 points)
    trend_score = 0

    # Check if in Phase 2 or transitioning from Phase 1 to Phase 2
    if phase == 2:
        trend_score += 30
        reasons.append('In Phase 2 (Uptrend)')
    elif phase == 1:
        # Check if about to transition to Phase 2
        sma_50 = phase_info.get('sma_50', 0)
        sma_200 = phase_info.get('sma_200', 0)
        slope_50 = phase_info.get('slope_50', 0)

        if (current_price > sma_50 * 0.98 and  # Within 2% of 50 SMA
            sma_50 > sma_200 and
            slope_50 > 0):
            trend_score += 25
            reasons.append('Transitioning Phase 1 -> Phase 2')
        else:
            trend_score += 10
            reasons.append('In Phase 1 (Base Building)')

    # Detect breakout
    breakout_info = detect_breakout(price_data, current_price, phase_info)
    if breakout_info['is_breakout']:
        trend_score += 10
        reasons.append(f"{breakout_info['breakout_type']} at {breakout_info['breakout_level']}")
        details['breakout'] = breakout_info

    # Check SMA alignment
    sma_50 = phase_info.get('sma_50', 0)
    sma_200 = phase_info.get('sma_200', 0)
    slope_50 = phase_info.get('slope_50', 0)
    slope_200 = phase_info.get('slope_200', 0)

    if slope_50 > slope_200:
        reasons.append(f'50 SMA slope ({slope_50:.4f}) > 200 SMA slope ({slope_200:.4f})')

    # Check not over-extended
    distance_50 = phase_info.get('distance_from_50sma', 0)
    if distance_50 > 25:
        trend_score -= 10
        reasons.append(f'Over-extended: {distance_50:.1f}% above 50 SMA')
    elif distance_50 < 10:
        reasons.append(f'Good distance from 50 SMA: {distance_50:.1f}%')

    score += min(trend_score, 40)
    details['trend_score'] = min(trend_score, 40)

    # 2. VOLUME CONFIRMATION (20 points)
    volume_score = 0

    if 'Volume' in price_data.columns and len(price_data) >= 20:
        volume_ratio = calculate_volume_ratio(price_data['Volume'], 20)

        if volume_ratio >= 1.5:
            volume_score = 20
            reasons.append(f'Strong volume: {volume_ratio:.1f}x average')
        elif volume_ratio >= 1.3:
            volume_score = 15
            reasons.append(f'Good volume: {volume_ratio:.1f}x average')
        elif volume_ratio >= 1.1:
            volume_score = 10
            reasons.append(f'Moderate volume: {volume_ratio:.1f}x average')
        else:
            volume_score = 0
            reasons.append(f'Low volume: {volume_ratio:.1f}x average')

        details['volume_ratio'] = round(volume_ratio, 2)

    score += volume_score
    details['volume_score'] = volume_score

    # 3. RELATIVE STRENGTH SLOPE (20 points)
    rs_score = 0

    if len(rs_series) >= 15:
        rs_slope = calculate_rs_slope(rs_series, 15)

        if rs_slope > 0:
            if rs_slope > 2.0:
                rs_score = 20
                reasons.append(f'Excellent RS momentum: {rs_slope:.2f}')
            elif rs_slope > 1.0:
                rs_score = 15
                reasons.append(f'Strong RS momentum: {rs_slope:.2f}')
            elif rs_slope > 0.5:
                rs_score = 10
                reasons.append(f'Positive RS momentum: {rs_slope:.2f}')
            else:
                rs_score = 5
                reasons.append(f'Weak RS momentum: {rs_slope:.2f}')
        else:
            rs_score = 0
            reasons.append(f'Negative RS: {rs_slope:.2f}')

        details['rs_slope'] = round(rs_slope, 3)

    score += rs_score
    details['rs_score'] = rs_score

    # 4. VOLATILITY CONTRACTION QUALITY (20 points)
    vol_data = detect_volatility_contraction(price_data['Close'], 20)
    vol_score = 0

    if vol_data['is_contracting']:
        vol_quality = vol_data['contraction_quality']
        vol_score = min(vol_quality * 0.2, 20)  # Scale to max 20 points
        reasons.append(f'Volatility contraction: {vol_quality:.0f}% quality')
    else:
        vol_score = 5  # Some points for attempting to contract
        reasons.append('No significant volatility contraction')

    details['volatility_data'] = vol_data
    score += vol_score
    details['volatility_score'] = round(vol_score, 1)

    # 5. FUNDAMENTAL CONTRADICTION CHECK
    fundamental_penalty = 0
    if fundamentals:
        # Check for fundamental red flags
        contradictions = []

        eps_trend = fundamentals.get('eps_trend', 'unknown')
        revenue_trend = fundamentals.get('revenue_trend', 'unknown')

        if eps_trend == 'deteriorating':
            contradictions.append('EPS deteriorating')
            fundamental_penalty += 5

        if revenue_trend == 'deteriorating':
            contradictions.append('Revenue declining')
            fundamental_penalty += 5

        inventory_signal = fundamentals.get('inventory_signal', 'neutral')
        if inventory_signal == 'negative':
            contradictions.append('Inventory building')
            fundamental_penalty += 5

        if contradictions:
            reasons.append(f'Fundamental concerns: {", ".join(contradictions)}')
            details['fundamental_concerns'] = contradictions

    score -= fundamental_penalty
    details['fundamental_penalty'] = fundamental_penalty

    # Final score
    final_score = max(0, min(score, 100))

    # Determine if this is a valid buy signal (>= 70)
    is_buy = final_score >= 70

    return {
        'ticker': ticker,
        'is_buy': is_buy,
        'score': round(final_score, 1),
        'phase': phase,
        'breakout_price': breakout_info.get('breakout_level') if breakout_info['is_breakout'] else None,
        'reasons': reasons,
        'details': details
    }


def score_sell_signal(
    ticker: str,
    price_data: pd.DataFrame,
    current_price: float,
    phase_info: Dict,
    rs_series: pd.Series,
    previous_phase: Optional[int] = None
) -> Dict[str, any]:
    """Score a sell signal based on Phase 2->3/4 transition.

    Scoring Components (0-100):
    - Breakdown structure: 60 points
    - Volume confirmation: 30 points
    - RS weakness: 10 points

    Only output scores >= 60

    Args:
        ticker: Stock ticker
        price_data: OHLCV data
        current_price: Current price
        phase_info: Phase classification
        rs_series: Relative strength series
        previous_phase: Previous phase (for transition detection)

    Returns:
        Dict with sell signal score and details
    """
    phase = phase_info['phase']

    # Only consider Phase 3 and Phase 4, or transitions from Phase 2
    if phase not in [3, 4]:
        return {
            'ticker': ticker,
            'is_sell': False,
            'score': 0,
            'severity': 'none',
            'reason': f'No sell signal (Phase {phase})',
            'details': {}
        }

    score = 0
    details = {}
    reasons = []

    # 1. BREAKDOWN STRUCTURE (60 points)
    breakdown_score = 0

    sma_50 = phase_info.get('sma_50', 0)
    sma_200 = phase_info.get('sma_200', 0)
    slope_50 = phase_info.get('slope_50', 0)

    # Phase transition
    if previous_phase == 2 and phase in [3, 4]:
        breakdown_score += 30
        reasons.append(f'Phase transition: {previous_phase} -> {phase}')
    elif phase == 4:
        breakdown_score += 25
        reasons.append('In Phase 4 (Downtrend)')
    elif phase == 3:
        breakdown_score += 15
        reasons.append('In Phase 3 (Distribution)')

    # Breakdown below 50 SMA
    if current_price < sma_50:
        pct_below = ((sma_50 - current_price) / sma_50) * 100
        if pct_below > 5:
            breakdown_score += 20
            reasons.append(f'Broke below 50 SMA by {pct_below:.1f}%')
        elif pct_below > 2:
            breakdown_score += 15
            reasons.append(f'Below 50 SMA by {pct_below:.1f}%')
        else:
            breakdown_score += 10
            reasons.append(f'Just below 50 SMA ({pct_below:.1f}%)')

        details['breakdown_level'] = round(sma_50, 2)

    # Check if 50 SMA is turning down
    if slope_50 < 0:
        breakdown_score += 10
        reasons.append(f'50 SMA declining (slope: {slope_50:.4f})')

    score += min(breakdown_score, 60)
    details['breakdown_score'] = min(breakdown_score, 60)

    # 2. VOLUME CONFIRMATION (30 points)
    volume_score = 0

    if 'Volume' in price_data.columns and len(price_data) >= 20:
        volume_ratio = calculate_volume_ratio(price_data['Volume'], 20)

        # High volume on breakdown is bearish
        if volume_ratio >= 1.5:
            volume_score = 30
            reasons.append(f'High volume breakdown: {volume_ratio:.1f}x')
        elif volume_ratio >= 1.3:
            volume_score = 20
            reasons.append(f'Elevated volume: {volume_ratio:.1f}x')
        elif volume_ratio >= 1.1:
            volume_score = 10
            reasons.append(f'Moderate volume: {volume_ratio:.1f}x')
        else:
            volume_score = 5
            reasons.append(f'Low volume breakdown: {volume_ratio:.1f}x')

        details['volume_ratio'] = round(volume_ratio, 2)

    score += volume_score
    details['volume_score'] = volume_score

    # 3. RS WEAKNESS (10 points)
    rs_score = 0

    if len(rs_series) >= 15:
        rs_slope = calculate_rs_slope(rs_series, 15)

        if rs_slope < 0:
            if rs_slope < -2.0:
                rs_score = 10
                reasons.append(f'Sharp RS decline: {rs_slope:.2f}')
            elif rs_slope < -1.0:
                rs_score = 7
                reasons.append(f'RS declining: {rs_slope:.2f}')
            else:
                rs_score = 5
                reasons.append(f'Weak RS rollover: {rs_slope:.2f}')
        else:
            rs_score = 0
            reasons.append(f'RS still positive: {rs_slope:.2f}')

        details['rs_slope'] = round(rs_slope, 3)

    score += rs_score
    details['rs_score'] = rs_score

    # Check for failed breakout
    close = price_data['Close']
    if len(close) >= 20:
        recent_high = close.iloc[-20:].max()
        if recent_high > sma_50 and current_price < sma_50:
            score += 10
            reasons.append('Failed breakout - closed back inside base')

    # Final score
    final_score = max(0, min(score, 100))

    # Determine severity
    if final_score >= 80:
        severity = 'critical'
    elif final_score >= 70:
        severity = 'high'
    elif final_score >= 60:
        severity = 'medium'
    else:
        severity = 'low'

    # Determine if this is a valid sell signal (>= 60)
    is_sell = final_score >= 60

    return {
        'ticker': ticker,
        'is_sell': is_sell,
        'score': round(final_score, 1),
        'severity': severity,
        'phase': phase,
        'breakdown_level': details.get('breakdown_level'),
        'reasons': reasons,
        'details': details
    }


def format_signal_output(signal: Dict, signal_type: str = 'buy') -> str:
    """Format signal for human-readable output.

    Args:
        signal: Signal dict from score_buy_signal or score_sell_signal
        signal_type: 'buy' or 'sell'

    Returns:
        Formatted string
    """
    ticker = signal['ticker']
    score = signal['score']
    phase = signal['phase']

    if signal_type == 'buy':
        output = f"\n{'='*60}\n"
        output += f"BUY SIGNAL: {ticker} | Score: {score}/100 | Phase {phase}\n"
        output += f"{'='*60}\n"

        if 'breakout_price' in signal and signal['breakout_price']:
            output += f"Breakout Level: ${signal['breakout_price']:.2f}\n"

        details = signal.get('details', {})
        if 'rs_slope' in details:
            output += f"RS Slope: {details['rs_slope']:.3f}\n"
        if 'volume_ratio' in details:
            output += f"Volume vs Avg: {details['volume_ratio']:.1f}x\n"
        if 'distance_from_50sma' in details:
            output += f"Distance from 50 SMA: {details['distance_from_50sma']:.1f}%\n"

        output += f"\nReasons:\n"
        for reason in signal['reasons']:
            output += f"  • {reason}\n"

    else:  # sell
        severity = signal.get('severity', 'unknown')
        output = f"\n{'='*60}\n"
        output += f"SELL SIGNAL: {ticker} | Score: {score}/100 | Severity: {severity.upper()} | Phase {phase}\n"
        output += f"{'='*60}\n"

        if 'breakdown_level' in signal and signal['breakdown_level']:
            output += f"Breakdown Level: ${signal['breakdown_level']:.2f}\n"

        details = signal.get('details', {})
        if 'rs_slope' in details:
            output += f"RS Slope: {details['rs_slope']:.3f}\n"
        if 'volume_ratio' in details:
            output += f"Volume vs Avg: {details['volume_ratio']:.1f}x\n"

        output += f"\nReasons:\n"
        for reason in signal['reasons']:
            output += f"  • {reason}\n"

    return output

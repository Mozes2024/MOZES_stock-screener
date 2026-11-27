"""Offline contract tests; never run the exporter CLI (which can start a scan)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from generate_breakout_signals_for_sp500 import _write_output, build_signal_entry
from src.screening.signal_engine import score_buy_signal


def raw_signal(score=124.3, vcp=None):
    return {
        "ticker": "TEST", "score": score, "phase": 2, "current_price": 100,
        "stop_loss": 95, "risk_reward_ratio": 3, "entry_quality": "Good",
        "breakout_price": 99, "reasons": ["Strong trend"],
        "details": {"rs_slope": 0.123, "vcp_data": vcp or {}},
    }


def test_shared_fixture_matches_actual_producer():
    fixture = json.loads((Path(__file__).parent / "fixtures/breakout_contract.json").read_text(encoding="utf-8"))
    assert [build_signal_entry(i + 1, s) for i, s in enumerate(fixture["source_signals"])] == fixture["feed"]["top_signals"]


@pytest.mark.parametrize("vcp,confirmed", [
    ({"confirmed": True, "quality": 80, "pattern": "3 contractions"}, True),
    ({"confirmed": False, "quality": 28.3, "pattern": "1 contraction"}, False),
    ({"confirmed": False, "quality": 75}, False),
    ({"quality": 90, "pattern": "VCP confirmed"}, False),
    ({"confirmed": "true", "quality": 90}, False),
    ({"confirmed": 1, "quality": 90}, False),
    ({}, False),
])
def test_export_requires_explicit_boolean_confirmation(vcp, confirmed):
    entry = build_signal_entry(7, raw_signal(vcp=vcp))
    assert entry["has_vcp"] is confirmed
    assert entry["vcp_confirmed"] is confirmed
    assert entry["vcp_quality"] == vcp.get("quality", 0)
    assert entry["vcp_desc"] == vcp.get("pattern", "")
    assert {k: entry[k] for k in ("rank", "stop_loss", "risk", "reward", "risk_reward", "rs", "entry_quality")} == {
        "rank": 7, "stop_loss": 95, "risk": 5, "reward": 15,
        "risk_reward": 3, "rs": 0.123, "entry_quality": "Good",
    }


@pytest.mark.parametrize("score", [100, 124.3, 125])
def test_raw_source_scale_survives_json(tmp_path, score):
    output = tmp_path / "feed.json"
    assert _write_output(output, [raw_signal(score)], "RISK-ON", {"phase_2_pct": 40})
    feed = json.loads(output.read_text(encoding="utf-8"))
    assert feed["breakout_score_max"] == 125
    assert feed["top_signals"][0]["breakout_score"] == score


def scored_signal(vcp):
    close = pd.Series(np.linspace(50, 100, 260), index=pd.bdate_range("2025-01-01", periods=260))
    prices = pd.DataFrame({"Close": close, "Open": close, "High": close * 1.01,
                           "Low": close * 0.99, "Volume": 1_000_000})
    return score_buy_signal("TEST", prices, 100, {
        "phase": 2, "sma_50": 95, "sma_150": 85, "sma_200": 80,
        "slope_50": 0.08, "slope_200": 0.05,
        "distance_from_50sma": 5, "distance_from_200sma": 25,
        "week_52_high": 101, "week_52_low": 49,
    }, close, vcp_data=vcp)


@pytest.mark.parametrize("confirmed,quality,bonus", [(True, 85, 5), (True, 65, 3), (True, 55, 1), (False, 28.3, 0), (False, 75, 0)])
def test_engine_preserves_confirmation_without_changing_scores(confirmed, quality, bonus):
    result = scored_signal({"is_vcp": confirmed, "vcp_quality": quality,
                            "contraction_count": 1, "pattern_details": "synthetic"})
    baseline = scored_signal(None)
    assert result["details"]["vcp_data"]["confirmed"] is confirmed
    assert result["details"]["vcp_bonus"] == bonus
    assert result["score"] == round(baseline["score"] + bonus, 1)
    for field in ("stop_loss", "entry_quality", "risk_reward_ratio", "phase"):
        assert result[field] == baseline[field]
    assert build_signal_entry(1, result)["vcp_confirmed"] is confirmed

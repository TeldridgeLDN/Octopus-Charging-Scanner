"""Tests for weekly_forecast.analyze_week ranking.

Ranking must use each day's AVERAGE price combined with a neutral carbon value
(60/40 price/carbon), not the single cheapest slot.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scripts.weekly_forecast as wf  # noqa: E402
from modules.analyzer import Analyzer  # noqa: E402


def _analyzer():
    return Analyzer(
        price_weight=0.6,
        carbon_weight=0.4,
        price_excellent=10,
        price_good=15,
        carbon_excellent=100,
        carbon_good=150,
    )


def test_ranking_uses_avg_not_min_price():
    # Day A: cheap on average. Day B: expensive average but a very low min slot.
    # Min-based ranking would wrongly favour Day B.
    forecast_data = [
        {"date": "2026-01-05", "avg_price": 8.0, "min_price": 5.0},
        {"date": "2026-01-06", "avg_price": 25.0, "min_price": 2.0},
    ]

    analysis = wf.analyze_week(forecast_data, _analyzer())
    scores = analysis["daily_scores"]

    # Sorted best-first: Day A (avg 8p) beats Day B (avg 25p) despite B's low min.
    assert scores[0]["date"] == "2026-01-05"
    assert scores[1]["date"] == "2026-01-06"


def test_score_includes_carbon_weight():
    # avg 8p -> price_score 100; neutral carbon 175 -> carbon_score 50.
    # combined = 0.6*100 + 0.4*50 = 80 (would be 100 if carbon ignored).
    forecast_data = [{"date": "2026-01-05", "avg_price": 8.0, "min_price": 5.0}]

    analysis = wf.analyze_week(forecast_data, _analyzer())

    assert analysis["daily_scores"][0]["score"] == 80.0
    # min_price retained for display
    assert analysis["daily_scores"][0]["min_price"] == 5.0


def test_avoid_days_threshold():
    # avg 25p -> price_score 25; combined = 0.6*25 + 20 = 35 (< 50 -> avoid).
    forecast_data = [
        {"date": "2026-01-05", "avg_price": 8.0, "min_price": 5.0},
        {"date": "2026-01-06", "avg_price": 25.0, "min_price": 2.0},
    ]

    analysis = wf.analyze_week(forecast_data, _analyzer())

    best_dates = [d["date"] for d in analysis["best_days"]]
    avoid_dates = [d["date"] for d in analysis["avoid_days"]]

    assert best_dates == ["2026-01-05"]  # score 80 >= 75
    assert avoid_dates == ["2026-01-06"]  # score 35 < 50

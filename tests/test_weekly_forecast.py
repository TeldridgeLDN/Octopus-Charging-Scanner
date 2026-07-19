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


# Score bands with NEUTRAL_CARBON=175 (carbon_score always 50):
#   combined = 0.6*price_score + 0.4*50 = 0.6*price_score + 20
#     avg <= 10  -> 0.6*100 + 20 = 80  (>=75 best day)
#     10 < avg <= 15 -> 0.6*75 + 20 = 65  (in [50,75))
#     15 < avg <= 20 -> 0.6*50 + 20 = 50  (in [50,75))
#     avg > 20   -> 0.6*25 + 20 = 35  (<50 avoid)

_CONFIG = {"user": {"typical_charge_kwh": 40}}


def test_flat_week_names_cheapest_days():
    # No day <= 10p, so no day reaches score 75. Two days in [50,75).
    #   12.0p -> price_score 75 -> score 65
    #   14.0p -> price_score 75 -> score 65
    #   18.0p -> price_score 50 -> score 50
    # None avoid (all >= 50), best_days empty. Lowest avg = 2026-01-12.
    forecast_data = [
        {"date": "2026-01-12", "avg_price": 12.0, "min_price": 6.0},
        {"date": "2026-01-13", "avg_price": 14.0, "min_price": 7.0},
        {"date": "2026-01-14", "avg_price": 18.0, "min_price": 9.0},
    ]

    analysis = wf.analyze_week(forecast_data, _analyzer())
    assert analysis["best_days"] == []

    message = wf.format_notification(analysis, _CONFIG)

    assert "Cheapest days this week" in message
    assert "Best days to charge" not in message
    # Lowest-avg day (12.0p, 2026-01-12) -> "Mon 12 Jan".
    assert "Mon 12 Jan" in message
    assert "Weekly outlook" in message


def test_good_week_keeps_confident_wording():
    # 8.0p -> price_score 100 -> score 80 (>= 75, a real best day).
    forecast_data = [
        {"date": "2026-01-12", "avg_price": 8.0, "min_price": 4.0},
        {"date": "2026-01-13", "avg_price": 14.0, "min_price": 7.0},
    ]

    analysis = wf.analyze_week(forecast_data, _analyzer())
    assert analysis["best_days"]  # non-empty

    message = wf.format_notification(analysis, _CONFIG)

    assert "Best days to charge" in message
    assert "Cheapest days this week" not in message


def test_no_day_in_both_sections():
    # All avg > 20 -> every day scores 35 (< 50): all-avoid week.
    # cheapest list is empty, so fall back to the 2 least-bad days.
    forecast_data = [
        {"date": "2026-01-12", "avg_price": 22.0, "min_price": 11.0},
        {"date": "2026-01-13", "avg_price": 25.0, "min_price": 12.0},
        {"date": "2026-01-14", "avg_price": 28.0, "min_price": 13.0},
    ]

    analysis = wf.analyze_week(forecast_data, _analyzer())
    assert analysis["best_days"] == []
    assert len(analysis["avoid_days"]) == 3

    message = wf.format_notification(analysis, _CONFIG)

    assert "Cheapest days this week" in message

    # The 2 days named at the top (stable sort keeps input order for ties):
    top_dates = ["Mon 12 Jan", "Tue 13 Jan"]
    for friendly in top_dates:
        assert friendly in message

    # Split into top and avoid sections; no top date may appear in avoid.
    avoid_idx = message.index("Avoid charging on")
    top_section = message[:avoid_idx]
    avoid_section = message[avoid_idx:]
    for friendly in top_dates:
        assert friendly in top_section
        assert friendly not in avoid_section

    # No date string appears twice anywhere in the message.
    for friendly in ["Mon 12 Jan", "Tue 13 Jan", "Wed 14 Jan"]:
        assert message.count(friendly) <= 1

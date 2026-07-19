"""Tests for the forecast-confidence line in format_notification."""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scripts.daily_notification as dn  # noqa: E402
from modules.analyzer import ChargingWindow, OpportunityRating  # noqa: E402


def _make_config():
    return {
        "user": {"typical_charge_kwh": 30.0},
        "apis": {
            "pushover": {
                "user_key": "u",
                "api_token": "t",
                "sounds": {
                    "excellent": "magic",
                    "good": "bike",
                },
            }
        },
    }


def _make_window():
    start = datetime(2026, 1, 5, 2, 0, tzinfo=timezone.utc)
    return ChargingWindow(
        start=start,
        end=start + timedelta(hours=4),
        avg_price=12.0,
        avg_carbon=120,
        total_cost=3.0,
        total_carbon=3600,
        opportunity_score=75.0,
        rating=OpportunityRating.GOOD,
        reason="cheap",
        savings_vs_baseline=None,
    )


def _current_time():
    # 3h before window start -> UPCOMING, no status prefix
    return datetime(2026, 1, 5, 1, 0, tzinfo=timezone.utc) - timedelta(hours=2)


def test_no_confidence_line_for_octopus_actual():
    _, message, _, _ = dn.format_notification(
        _make_window(),
        _make_config(),
        price_source="octopus_actual",
        current_time=_current_time(),
        forecast_confidence="",
    )

    assert "Actual prices (published)" in message
    assert "Forecast confidence" not in message


def test_confidence_line_present_and_positioned_for_forecast():
    _, message, _, _ = dn.format_notification(
        _make_window(),
        _make_config(),
        price_source="forecast",
        current_time=_current_time(),
        forecast_confidence="high",
    )

    assert "Forecast prices (predicted)" in message
    # Confidence line appears on its own line immediately after the Data line.
    assert (
        "<b>📊 Data:</b> Forecast prices (predicted)\n"
        "<b>🔮 Forecast confidence:</b> high\n"
    ) in message


def test_confidence_line_omitted_when_empty():
    _, message, _, _ = dn.format_notification(
        _make_window(),
        _make_config(),
        price_source="forecast",
        current_time=_current_time(),
        forecast_confidence="",
    )

    assert "Forecast prices (predicted)" in message
    assert "Forecast confidence" not in message

"""Tests for the shared forecast conversion + fetch helpers."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.modules.price_sources import (
    agile_to_price_slots,
    guy_lipman_to_price_slots,
    fetch_forecast_price_slots,
)


def _agile_slots():
    return [
        {
            "date_time": "2026-01-05T00:00:00Z",
            "agile_pred": 12.5,
            "agile_low": 8.0,
            "agile_high": 16.0,
            "source": "agile_predict",
        },
        {
            "date_time": "2026-01-05T00:30:00Z",
            "agile_pred": 9.0,
            "agile_low": 6.0,
            "agile_high": 12.0,
            "source": "agile_predict",
        },
    ]


def test_agile_to_price_slots():
    slots = agile_to_price_slots(_agile_slots())

    assert len(slots) == 2
    assert slots[0].time == datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    assert slots[0].price == 12.5
    assert all(s.source == "agile_predict" for s in slots)


def test_guy_lipman_dual_format_parsing():
    forecasts = [
        # Old table-parsed format
        {"date": "2026-01-05", "time": "00:00", "price": 10.0},
        # New ISO with Z
        {"time": "2026-01-05T00:30:00Z", "price": 11.0},
        # New ISO naive (assumed UTC)
        {"time": "2026-01-05T01:00:00", "price": 12.0},
        # New ISO with explicit offset
        {"time": "2026-01-05T01:30:00+00:00", "price": 13.0},
    ]

    slots = guy_lipman_to_price_slots(forecasts)

    expected_times = [
        datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 5, 0, 30, tzinfo=timezone.utc),
        datetime(2026, 1, 5, 1, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 5, 1, 30, tzinfo=timezone.utc),
    ]
    assert [s.time for s in slots] == expected_times
    assert [s.price for s in slots] == [10.0, 11.0, 12.0, 13.0]
    assert all(s.source == "forecast" for s in slots)


def test_fetch_prefers_agile_predict():
    agile = MagicMock()
    agile.get_forecasts.return_value = _agile_slots()
    forecast = MagicMock()

    slots, source = fetch_forecast_price_slots(
        "H", agile_client=agile, forecast_client=forecast
    )

    assert source == "agile_predict"
    assert len(slots) == 2
    # Guy Lipman never consulted
    assert not forecast.get_forecasts.called


def test_fetch_falls_back_to_guy_lipman():
    agile = MagicMock()
    agile.get_forecasts.return_value = []  # agile unavailable
    forecast = MagicMock()
    forecast.get_forecasts.return_value = [
        {"date": "2026-01-05", "time": "00:00", "price": 10.0},
    ]

    slots, source = fetch_forecast_price_slots(
        "H", agile_client=agile, forecast_client=forecast
    )

    assert source == "forecast"
    assert len(slots) == 1
    assert forecast.get_forecasts.called


def test_fetch_raises_when_all_fail():
    agile = MagicMock()
    agile.get_forecasts.return_value = []
    forecast = MagicMock()
    forecast.get_forecasts.return_value = []

    with pytest.raises(RuntimeError):
        fetch_forecast_price_slots("H", agile_client=agile, forecast_client=forecast)

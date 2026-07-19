"""Tests for sync_plan_to_calendar helper in google_calendar module.

These tests patch GoogleCalendarClient so no network calls or real
credentials are ever touched.
"""

import types
from unittest.mock import patch

import pytest

from src.modules.google_calendar import sync_plan_to_calendar


def _make_day(**overrides):
    """Build a fake DayComparison-like object with the 9 sync attributes."""
    defaults = {
        "date": "2026-07-19",
        "day_name": "Today",
        "avg_price": 12.5,
        "optimal_window": {
            "start": "2026-07-19T02:00:00+01:00",
            "end": "2026-07-19T05:00:00+01:00",
        },
        "cost": 3.75,
        "rating": "EXCELLENT",
        "price_source": "octopus_actual",
        "savings_vs_today": 0.0,
        "avg_carbon": 90,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_plan(days=None, kwh_amount=30.0, best_day=None):
    """Build a fake MultiDayPlan-like object."""
    if days is None:
        days = [_make_day()]
    if best_day is None:
        best_day = {"date": days[0].date, "day_name": days[0].day_name}
    return types.SimpleNamespace(
        days=days,
        kwh_amount=kwh_amount,
        best_day=best_day,
    )


EXPECTED_KEYS = {
    "date",
    "day_name",
    "avg_price",
    "optimal_window",
    "cost",
    "rating",
    "price_source",
    "savings_vs_today",
    "avg_carbon",
}


def test_disabled_config_returns_true_without_client():
    """enabled=False short-circuits before constructing a client."""
    with patch("src.modules.google_calendar.GoogleCalendarClient") as mock_client:
        result = sync_plan_to_calendar(_make_plan(), {"enabled": False})

    assert result is True
    mock_client.assert_not_called()


def test_missing_calendar_id_returns_false_without_client():
    """enabled but no calendar_id returns False and never constructs a client."""
    with patch("src.modules.google_calendar.GoogleCalendarClient") as mock_client:
        result = sync_plan_to_calendar(_make_plan(), {"enabled": True})

    assert result is False
    mock_client.assert_not_called()


def test_enabled_valid_calls_create_multi_day_events_once():
    """Happy path: create_multi_day_events called once with expected kwargs."""
    plan = _make_plan()
    cal_config = {"enabled": True, "calendar_id": "cal-123"}

    with patch("src.modules.google_calendar.GoogleCalendarClient") as mock_client_cls:
        instance = mock_client_cls.return_value
        instance.create_multi_day_events.return_value = ["evt-1"]
        instance.delete_old_events.return_value = 0

        result = sync_plan_to_calendar(plan, cal_config)

    assert result is True
    instance.create_multi_day_events.assert_called_once()
    _, kwargs = instance.create_multi_day_events.call_args

    assert kwargs["kwh"] == 30.0
    assert kwargs["best_day"] == plan.best_day
    assert kwargs["reminders"] == [60, 15]

    days_arg = kwargs["days"]
    assert len(days_arg) == 1
    day_dict = days_arg[0]
    assert set(day_dict.keys()) == EXPECTED_KEYS
    assert day_dict["date"] == "2026-07-19"
    assert day_dict["day_name"] == "Today"
    assert day_dict["avg_price"] == 12.5
    assert day_dict["cost"] == 3.75
    assert day_dict["rating"] == "EXCELLENT"
    assert day_dict["price_source"] == "octopus_actual"
    assert day_dict["savings_vs_today"] == 0.0
    assert day_dict["avg_carbon"] == 90


def test_client_construction_filenotfound_returns_false():
    """FileNotFoundError from the client constructor is swallowed → False."""
    cal_config = {"enabled": True, "calendar_id": "cal-123"}

    with patch(
        "src.modules.google_calendar.GoogleCalendarClient",
        side_effect=FileNotFoundError("missing creds"),
    ):
        result = sync_plan_to_calendar(_make_plan(), cal_config)

    assert result is False


def test_delete_past_events_flag_respected():
    """delete_old_events skipped when delete_past_events=False, else called once."""
    plan = _make_plan()

    # Flag False → delete_old_events NOT called
    with patch("src.modules.google_calendar.GoogleCalendarClient") as mock_client_cls:
        instance = mock_client_cls.return_value
        instance.create_multi_day_events.return_value = ["evt-1"]
        sync_plan_to_calendar(
            plan,
            {
                "enabled": True,
                "calendar_id": "cal-123",
                "delete_past_events": False,
            },
        )
        instance.delete_old_events.assert_not_called()

    # Default (flag absent) → delete_old_events called once
    with patch("src.modules.google_calendar.GoogleCalendarClient") as mock_client_cls:
        instance = mock_client_cls.return_value
        instance.create_multi_day_events.return_value = ["evt-1"]
        instance.delete_old_events.return_value = 0
        sync_plan_to_calendar(
            plan,
            {"enabled": True, "calendar_id": "cal-123"},
        )
        instance.delete_old_events.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Pytest configuration and shared fixtures for EV Charging Optimizer tests."""

import pytest
from pathlib import Path
import tempfile
import shutil


@pytest.fixture
def mock_octopus_response():
    """Mock Octopus Energy API response."""
    return {
        "count": 48,
        "results": [
            {
                "valid_from": "2025-12-07T00:00:00Z",
                "valid_to": "2025-12-07T00:30:00Z",
                "value_inc_vat": 12.5,
            },
            {
                "valid_from": "2025-12-07T00:30:00Z",
                "valid_to": "2025-12-07T01:00:00Z",
                "value_inc_vat": 11.8,
            },
            {
                "valid_from": "2025-12-07T01:00:00Z",
                "valid_to": "2025-12-07T01:30:00Z",
                "value_inc_vat": 10.2,
            },
            {
                "valid_from": "2025-12-07T01:30:00Z",
                "valid_to": "2025-12-07T02:00:00Z",
                "value_inc_vat": 9.5,
            },
        ],
    }


@pytest.fixture
def mock_carbon_response():
    """Mock Carbon Intensity API response (national endpoint format)."""
    return {
        "data": [
            {
                "from": "2025-12-07T00:00:00Z",
                "to": "2025-12-07T00:30:00Z",
                "intensity": {"forecast": 250, "index": "moderate"},
            },
            {
                "from": "2025-12-07T00:30:00Z",
                "to": "2025-12-07T01:00:00Z",
                "intensity": {"forecast": 180, "index": "low"},
            },
            {
                "from": "2025-12-07T01:00:00Z",
                "to": "2025-12-07T01:30:00Z",
                "intensity": {"forecast": 150, "index": "low"},
            },
            {
                "from": "2025-12-07T01:30:00Z",
                "to": "2025-12-07T02:00:00Z",
                "intensity": {"forecast": 200, "index": "moderate"},
            },
        ]
    }


@pytest.fixture
def mock_carbon_current_response():
    """Mock Carbon Intensity API current intensity response."""
    return {
        "data": [
            {
                "from": "2025-12-07T10:00:00Z",
                "to": "2025-12-07T10:30:00Z",
                "data": [{"intensity": {"forecast": 220, "index": "moderate"}}],
            }
        ]
    }


@pytest.fixture
def mock_forecast_html():
    """Mock Guy Lipman forecast HTML."""
    return """
    <html>
    <body>
        <table class="forecast-table">
            <tr>
                <th>Date</th>
                <th>Time</th>
                <th>Price (p/kWh)</th>
            </tr>
            <tr>
                <td>2025-12-07</td>
                <td>00:00</td>
                <td>12.5</td>
            </tr>
            <tr>
                <td>2025-12-07</td>
                <td>00:30</td>
                <td>11.8</td>
            </tr>
            <tr>
                <td>2025-12-07</td>
                <td>01:00</td>
                <td>10.2</td>
            </tr>
        </table>
    </body>
    </html>
    """


@pytest.fixture
def mock_pushover_success_response():
    """Mock Pushover API success response."""
    return {"status": 1, "request": "abc123"}


@pytest.fixture
def mock_pushover_error_response():
    """Mock Pushover API error response."""
    return {"status": 0, "errors": ["Invalid token"]}


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_forecast():
    """Sample forecast data."""
    return {
        "timestamp": "2025-12-07T10:00:00Z",
        "data": [
            {"time": "2025-12-07T00:00:00Z", "price": 12.5},
            {"time": "2025-12-07T00:30:00Z", "price": 11.8},
        ],
        "source": "octopus",
    }


@pytest.fixture
def sample_recommendation():
    """Sample recommendation data."""
    return {
        "date": "2025-12-07",
        "rating": "EXCELLENT",
        "best_window_start": "2025-12-07T02:00:00Z",
        "best_window_end": "2025-12-07T06:00:00Z",
        "estimated_cost": 2.85,
        "carbon_footprint": 150,
        "savings": 1.20,
        "reason": "both",
    }


@pytest.fixture
def sample_user_action():
    """Sample user action data."""
    return {
        "timestamp": "2025-12-07T03:00:00Z",
        "type": "manual_charge",
        "duration_hours": 4,
        "cost": 3.50,
        "notes": "Charged during cheap period",
    }


@pytest.fixture(autouse=True)
def reset_env_vars(monkeypatch):
    """Reset environment variables for each test."""
    monkeypatch.setenv("PUSHOVER_USER_KEY", "test_user_key")
    monkeypatch.setenv("PUSHOVER_API_TOKEN", "test_api_token")

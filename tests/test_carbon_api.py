"""Tests for Carbon Intensity API Client."""

import pytest
import requests
from unittest.mock import patch
from src.modules.carbon_api import CarbonAPIClient


class TestCarbonAPIClient:
    """Tests for CarbonAPIClient."""

    def test_init(self):
        """Test client initialization."""
        client = CarbonAPIClient()
        assert client.timeout == 10
        assert client.max_retries == 3

    def test_get_intensity_success(self, mock_carbon_response):
        """Test successful intensity retrieval."""
        client = CarbonAPIClient()

        with patch.object(client, "fetch", return_value=mock_carbon_response):
            intensities = client.get_intensity(postcode="E1")

            assert len(intensities) == 4
            assert intensities[0]["intensity"] == 250
            assert intensities[0]["time"] == "2025-12-07T00:00:00Z"
            assert intensities[1]["intensity"] == 180

    def test_get_intensity_different_postcode(self, mock_carbon_response):
        """Test intensity retrieval uses national endpoint (postcode ignored)."""
        client = CarbonAPIClient()

        with patch.object(client, "fetch", return_value=mock_carbon_response):
            intensities = client.get_intensity(postcode="SW1")

            # Verify national endpoint is used (postcode ignored for backwards compat)
            args = client.fetch.call_args
            assert "/intensity/date" in args[0][0]
            # Still returns valid data
            assert len(intensities) == 4

    def test_get_intensity_empty_response(self):
        """Test handling of empty API response."""
        client = CarbonAPIClient()

        with patch.object(client, "fetch", return_value={"data": []}):
            intensities = client.get_intensity()

            assert intensities == []

    def test_get_intensity_missing_data(self):
        """Test handling of malformed response."""
        client = CarbonAPIClient()

        with patch.object(client, "fetch", return_value={}):
            intensities = client.get_intensity()

            assert intensities == []

    def test_get_current_intensity_success(self, mock_carbon_current_response):
        """Test getting current intensity."""
        client = CarbonAPIClient()

        with patch.object(client, "fetch", return_value=mock_carbon_current_response):
            current = client.get_current_intensity(postcode="E1")

            assert current["intensity"] == 220
            assert current["index"] == "moderate"
            assert current["time"] == "2025-12-07T10:00:00Z"

    def test_get_current_intensity_no_data(self):
        """Test current intensity with no data."""
        client = CarbonAPIClient()

        with patch.object(client, "fetch", return_value={"data": []}):
            with pytest.raises(ValueError, match="No data available"):
                client.get_current_intensity()

    def test_get_cleanest_window_success(self, mock_carbon_response):
        """Test finding cleanest charging window."""
        client = CarbonAPIClient()

        with patch.object(client, "fetch", return_value=mock_carbon_response):
            window = client.get_cleanest_window(postcode="E1", hours=1)

            assert window is not None
            assert window["average_intensity"] == 165  # Average of 180 and 150
            assert window["total_slots"] == 2

    def test_get_cleanest_window_insufficient_data(self):
        """Test cleanest window with insufficient data."""
        client = CarbonAPIClient()

        with patch.object(client, "fetch", return_value={"data": []}):
            with pytest.raises(ValueError, match="Insufficient data"):
                client.get_cleanest_window(hours=4)

    def test_get_cleanest_window_4_hours(self, mock_carbon_response):
        """Test finding 2-hour cleanest window."""
        client = CarbonAPIClient()

        with patch.object(client, "fetch", return_value=mock_carbon_response):
            window = client.get_cleanest_window(postcode="E1", hours=2)

            assert window is not None
            # 2 hours = 4 slots, cleanest is slots 0-3: (250+180+150+200)/4=195
            assert window["total_slots"] == 4
            assert window["start_time"] == "2025-12-07T00:00:00Z"

    def test_api_failure(self):
        """Test handling of API failure returns empty list."""
        client = CarbonAPIClient()

        with patch.object(
            client, "fetch", side_effect=requests.exceptions.RequestException()
        ):
            # API failures are caught and return empty list
            result = client.get_intensity()
            assert result == []

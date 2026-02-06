"""Tests for Octopus Energy API Client."""

import pytest
import requests
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from src.modules.octopus_api import OctopusAPIClient, BaseAPIClient


class TestBaseAPIClient:
    """Tests for BaseAPIClient."""

    def test_init(self):
        """Test client initialization."""
        client = BaseAPIClient(timeout=20, max_retries=5)
        assert client.timeout == 20
        assert client.max_retries == 5

    def test_fetch_success(self, mock_octopus_response):
        """Test successful API fetch."""
        client = BaseAPIClient()

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_octopus_response
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            result = client.fetch("https://api.example.com/test")

            assert result == mock_octopus_response
            mock_get.assert_called_once()

    def test_fetch_retry_on_timeout(self):
        """Test retry logic on timeout."""
        client = BaseAPIClient(max_retries=3)

        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout()

            with pytest.raises(requests.exceptions.Timeout):
                client.fetch("https://api.example.com/test")

            assert mock_get.call_count == 3

    def test_fetch_retry_on_http_error(self):
        """Test retry logic on HTTP error."""
        client = BaseAPIClient(max_retries=2)

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
            mock_get.return_value = mock_response

            with pytest.raises(requests.exceptions.HTTPError):
                client.fetch("https://api.example.com/test")

            assert mock_get.call_count == 2


class TestOctopusAPIClient:
    """Tests for OctopusAPIClient."""

    def test_init(self):
        """Test Octopus client initialization."""
        client = OctopusAPIClient()
        assert client.timeout == 10
        assert client.max_retries == 3

    def test_get_prices_success(self, mock_octopus_response):
        """Test successful price retrieval."""
        client = OctopusAPIClient()

        with patch.object(client, "fetch", return_value=mock_octopus_response):
            prices = client.get_prices(region="H", hours=24)

            assert len(prices) == 4
            assert prices[0]["value_inc_vat"] == 12.5
            assert prices[0]["valid_from"] == "2025-12-07T00:00:00Z"

    def test_get_prices_different_region(self, mock_octopus_response):
        """Test price retrieval for different region."""
        client = OctopusAPIClient()

        with patch.object(client, "fetch", return_value=mock_octopus_response):
            client.get_prices(region="C", hours=24)

            # Verify URL includes correct region
            args = client.fetch.call_args
            assert "-C/" in args[0][0]

    def test_get_prices_empty_response(self):
        """Test handling of empty API response."""
        client = OctopusAPIClient()

        with patch.object(client, "fetch", return_value={"results": []}):
            prices = client.get_prices()

            assert prices == []

    def test_get_current_price_success(self, mock_octopus_response):
        """Test getting current price."""
        client = OctopusAPIClient()

        with patch.object(client, "fetch", return_value=mock_octopus_response):
            with patch("src.modules.octopus_api.datetime") as mock_datetime:
                # Mock current time to match first slot
                mock_datetime.now.return_value = datetime(
                    2025, 12, 7, 0, 15, tzinfo=timezone.utc
                )
                mock_datetime.fromisoformat = datetime.fromisoformat

                price = client.get_current_price(region="H")

                assert price is not None
                assert price["value_inc_vat"] == 12.5

    def test_get_current_price_no_match(self, mock_octopus_response):
        """Test current price when no matching slot found."""
        client = OctopusAPIClient()

        with patch.object(client, "fetch", return_value=mock_octopus_response):
            with patch("src.modules.octopus_api.datetime") as mock_datetime:
                # Mock current time outside all slots
                mock_datetime.now.return_value = datetime(
                    2025, 12, 8, 12, 0, tzinfo=timezone.utc
                )
                mock_datetime.fromisoformat = datetime.fromisoformat

                price = client.get_current_price()

                assert price is None

    def test_get_current_price_empty_results(self):
        """Test current price with empty results."""
        client = OctopusAPIClient()

        with patch.object(client, "fetch", return_value={"results": []}):
            price = client.get_current_price()

            assert price is None

    def test_api_failure(self):
        """Test handling of API failure."""
        client = OctopusAPIClient()

        with patch.object(
            client, "fetch", side_effect=requests.exceptions.RequestException()
        ):
            with pytest.raises(requests.exceptions.RequestException):
                client.get_prices()

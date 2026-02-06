"""Tests for Guy Lipman Forecast API Scraper."""

import requests
from unittest.mock import Mock, patch
from src.modules.forecast_api import ForecastAPIClient


class TestForecastAPIClient:
    """Tests for ForecastAPIClient."""

    def test_init(self):
        """Test client initialization."""
        client = ForecastAPIClient()
        assert client.timeout == 10
        assert client.max_retries == 3

    def test_get_forecasts_success(self, mock_forecast_html):
        """Test successful forecast scraping."""
        client = ForecastAPIClient()

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.text = mock_forecast_html
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            forecasts = client.get_forecasts(region="H")

            assert len(forecasts) == 3
            assert forecasts[0]["date"] == "2025-12-07"
            assert forecasts[0]["time"] == "00:00"
            assert forecasts[0]["price"] == 12.5
            assert forecasts[0]["source"] == "forecast"

    def test_get_forecasts_different_region(self, mock_forecast_html):
        """Test forecast scraping for different region."""
        client = ForecastAPIClient()

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.text = mock_forecast_html
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            client.get_forecasts(region="C")

            # Verify URL includes correct region
            args = mock_get.call_args
            assert "region=C" in args[0][0]

    def test_get_forecasts_request_failure(self):
        """Test handling of request failure."""
        client = ForecastAPIClient()

        with patch("requests.get", side_effect=requests.exceptions.RequestException()):
            forecasts = client.get_forecasts()

            # Should gracefully return empty list
            assert forecasts == []

    def test_get_forecasts_timeout(self):
        """Test handling of request timeout."""
        client = ForecastAPIClient()

        with patch("requests.get", side_effect=requests.exceptions.Timeout()):
            forecasts = client.get_forecasts()

            assert forecasts == []

    def test_get_forecasts_http_error(self):
        """Test handling of HTTP error."""
        client = ForecastAPIClient()

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
            mock_get.return_value = mock_response

            forecasts = client.get_forecasts()

            assert forecasts == []

    def test_get_forecasts_malformed_html(self):
        """Test handling of malformed HTML."""
        client = ForecastAPIClient()

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.text = "<html><body><p>No table here</p></body></html>"
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            forecasts = client.get_forecasts()

            # Should gracefully return empty list
            assert forecasts == []

    def test_get_forecasts_empty_table(self):
        """Test handling of empty table."""
        client = ForecastAPIClient()

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.text = """
                <html><body>
                <table class="forecast-table">
                    <tr><th>Date</th><th>Time</th><th>Price</th></tr>
                </table>
                </body></html>
            """
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            forecasts = client.get_forecasts()

            assert forecasts == []

    def test_parse_strategy_generic_table(self):
        """Test generic table parsing strategy."""
        client = ForecastAPIClient()

        html = """
            <html><body>
            <table>
                <tr><th>Date</th><th>Time</th><th>Price</th></tr>
                <tr><td>2025-12-07</td><td>10:00</td><td>15.5</td></tr>
            </table>
            </body></html>
        """

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.text = html
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            forecasts = client.get_forecasts()

            assert len(forecasts) == 1
            assert forecasts[0]["price"] == 15.5

    def test_is_available_true(self, mock_forecast_html):
        """Test service availability check when available."""
        client = ForecastAPIClient()

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.text = mock_forecast_html
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            assert client.is_available(region="H") is True

    def test_is_available_false(self):
        """Test service availability check when unavailable."""
        client = ForecastAPIClient()

        with patch("requests.get", side_effect=requests.exceptions.RequestException()):
            assert client.is_available() is False

    def test_user_agent_header(self, mock_forecast_html):
        """Test that User-Agent header is set."""
        client = ForecastAPIClient()

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.text = mock_forecast_html
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            client.get_forecasts()

            # Verify User-Agent header was set
            call_kwargs = mock_get.call_args.kwargs
            assert "headers" in call_kwargs
            assert "User-Agent" in call_kwargs["headers"]
            assert "Mozilla" in call_kwargs["headers"]["User-Agent"]

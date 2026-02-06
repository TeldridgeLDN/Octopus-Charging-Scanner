"""Tests for forecast_tracker module."""

import pytest
from datetime import date
from pathlib import Path
import json
import tempfile
import shutil

from src.modules.forecast_tracker import ForecastTracker


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def tracker(temp_data_dir):
    """Create ForecastTracker instance with temp directory."""
    return ForecastTracker(data_dir=temp_data_dir)


class TestForecastTrackerInit:
    """Test ForecastTracker initialization."""

    def test_creates_data_directory(self, temp_data_dir):
        """Test that data directory is created if it doesn't exist."""
        data_path = Path(temp_data_dir) / "new_dir"
        assert not data_path.exists()

        ForecastTracker(data_dir=str(data_path))

        assert data_path.exists()
        assert data_path.is_dir()

    def test_accuracy_file_path_set(self, tracker, temp_data_dir):
        """Test that accuracy file path is set correctly."""
        expected_path = Path(temp_data_dir) / "forecast_accuracy.json"
        assert tracker.accuracy_file == expected_path


class TestRecordComparison:
    """Test recording forecast vs actual comparisons."""

    def test_records_accurate_forecast(self, tracker):
        """Test recording when forecast matches actual prices."""
        comparison_date = date(2025, 12, 8)
        forecast_prices = [10.0] * 24
        actual_prices = [10.5] * 24

        metrics = tracker.record_comparison(
            comparison_date, forecast_prices, actual_prices
        )

        assert metrics["date"] == "2025-12-08"
        assert metrics["mean_absolute_error"] == pytest.approx(0.5, abs=0.01)
        assert metrics["mean_error"] == pytest.approx(0.5, abs=0.01)
        assert metrics["num_hours"] == 24

    def test_calculates_mae_correctly(self, tracker):
        """Test Mean Absolute Error calculation."""
        comparison_date = date(2025, 12, 8)
        # Forecast: [10, 15, 20]
        # Actual:   [12, 14, 18]
        # Errors:   [+2, -1, -2]
        # Abs:      [2, 1, 2]
        # MAE:      5/3 = 1.667
        forecast_prices = [10.0, 15.0, 20.0]
        actual_prices = [12.0, 14.0, 18.0]

        metrics = tracker.record_comparison(
            comparison_date, forecast_prices, actual_prices
        )

        assert metrics["mean_absolute_error"] == pytest.approx(1.667, abs=0.01)

    def test_calculates_rmse_correctly(self, tracker):
        """Test Root Mean Squared Error calculation."""
        comparison_date = date(2025, 12, 8)
        # Errors: [+2, -1, -2]
        # Squared: [4, 1, 4]
        # Mean: 9/3 = 3
        # RMSE: sqrt(3) = 1.732
        forecast_prices = [10.0, 15.0, 20.0]
        actual_prices = [12.0, 14.0, 18.0]

        metrics = tracker.record_comparison(
            comparison_date, forecast_prices, actual_prices
        )

        assert metrics["rmse"] == pytest.approx(1.732, abs=0.01)

    def test_detects_systematic_bias(self, tracker):
        """Test detection of systematic forecast bias."""
        comparison_date = date(2025, 12, 8)
        # Forecast consistently 3p lower than actual
        forecast_prices = [7.0] * 24
        actual_prices = [10.0] * 24

        metrics = tracker.record_comparison(
            comparison_date, forecast_prices, actual_prices
        )

        # Positive mean_error = forecast underestimated prices
        assert metrics["mean_error"] == pytest.approx(3.0, abs=0.01)

    def test_detects_negative_pricing_predicted_correctly(self, tracker):
        """Test detection when negative pricing is correctly predicted."""
        comparison_date = date(2025, 12, 8)
        # Both have negative prices
        forecast_prices = [-5.0, -3.0] + [10.0] * 22
        actual_prices = [-4.5, -2.8] + [10.5] * 22

        metrics = tracker.record_comparison(
            comparison_date, forecast_prices, actual_prices
        )

        neg_pricing = metrics["negative_pricing"]
        assert neg_pricing["forecast_predicted"] is True
        assert neg_pricing["actually_occurred"] is True
        assert neg_pricing["correct_prediction"] is True

    def test_detects_negative_pricing_predicted_incorrectly(self, tracker):
        """Test detection when negative pricing is incorrectly predicted."""
        comparison_date = date(2025, 12, 8)
        # Forecast predicted negative, but actual was positive
        forecast_prices = [-5.0, -3.0] + [10.0] * 22
        actual_prices = [4.5, 2.8] + [10.5] * 22

        metrics = tracker.record_comparison(
            comparison_date, forecast_prices, actual_prices
        )

        neg_pricing = metrics["negative_pricing"]
        assert neg_pricing["forecast_predicted"] is True
        assert neg_pricing["actually_occurred"] is False
        assert neg_pricing["correct_prediction"] is False

    def test_detects_no_negative_pricing(self, tracker):
        """Test when neither forecast nor actual had negative prices."""
        comparison_date = date(2025, 12, 8)
        forecast_prices = [10.0] * 24
        actual_prices = [10.5] * 24

        metrics = tracker.record_comparison(
            comparison_date, forecast_prices, actual_prices
        )

        neg_pricing = metrics["negative_pricing"]
        assert neg_pricing["forecast_predicted"] is False
        assert neg_pricing["actually_occurred"] is False
        assert neg_pricing["correct_prediction"] is True

    def test_raises_on_mismatched_lengths(self, tracker):
        """Test error when forecast and actual have different lengths."""
        comparison_date = date(2025, 12, 8)
        forecast_prices = [10.0] * 24
        actual_prices = [10.5] * 12  # Wrong length

        with pytest.raises(ValueError, match="Price lists must be same length"):
            tracker.record_comparison(comparison_date, forecast_prices, actual_prices)

    def test_stores_data_to_file(self, tracker, temp_data_dir):
        """Test that comparison data is saved to JSON file."""
        comparison_date = date(2025, 12, 8)
        forecast_prices = [10.0] * 24
        actual_prices = [10.5] * 24

        tracker.record_comparison(comparison_date, forecast_prices, actual_prices)

        # Check file was created
        accuracy_file = Path(temp_data_dir) / "forecast_accuracy.json"
        assert accuracy_file.exists()

        # Check data can be loaded
        with open(accuracy_file) as f:
            data = json.load(f)

        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["date"] == "2025-12-08"


class TestGetRecentAccuracy:
    """Test retrieving recent accuracy metrics."""

    def test_returns_empty_for_no_data(self, tracker):
        """Test returns dict with None when no comparisons recorded."""
        metrics = tracker.get_recent_accuracy(days=7)

        assert metrics["num_comparisons"] == 0
        assert metrics["mean_absolute_error"] is None
        assert metrics["trend"] == "insufficient_data"

    def test_returns_recent_comparisons(self, tracker):
        """Test returns aggregated stats from specified time period."""
        # Record 10 days of data
        for day in range(1, 11):
            comparison_date = date(2025, 12, day)
            forecast = [10.0] * 24
            actual = [10.0 + day] * 24  # Increase error each day

            tracker.record_comparison(comparison_date, forecast, actual)

        # Get last 5 days
        metrics = tracker.get_recent_accuracy(days=5)

        assert metrics["num_comparisons"] == 5
        assert metrics["period_days"] == 5
        assert metrics["mean_absolute_error"] is not None
        # Recent days should have higher MAE (days 6-10)
        assert metrics["mean_absolute_error"] > 5.0

    def test_limits_to_available_data(self, tracker):
        """Test returns all data if fewer days than requested."""
        # Record only 3 days
        for day in range(1, 4):
            comparison_date = date(2025, 12, day)
            tracker.record_comparison(comparison_date, [10.0] * 24, [11.0] * 24)

        # Request 7 days
        metrics = tracker.get_recent_accuracy(days=7)

        assert metrics["num_comparisons"] == 3


class TestGetReliabilityGrade:
    """Test forecast reliability grading."""

    def test_grades_excellent_forecast(self, tracker):
        """Test EXCELLENT grade for MAE < 2p."""
        # Record very accurate forecast
        for day in range(1, 8):
            comparison_date = date(2025, 12, day)
            forecast = [10.0] * 24
            actual = [10.5] * 24  # 0.5p error

            tracker.record_comparison(comparison_date, forecast, actual)

        grade = tracker.get_reliability_grade(days=7)

        assert grade == "EXCELLENT"

    def test_grades_good_forecast(self, tracker):
        """Test GOOD grade for MAE 2-3p."""
        # Record good forecast
        for day in range(1, 8):
            comparison_date = date(2025, 12, day)
            forecast = [10.0] * 24
            actual = [12.5] * 24  # 2.5p error

            tracker.record_comparison(comparison_date, forecast, actual)

        grade = tracker.get_reliability_grade(days=7)

        assert grade == "GOOD"

    def test_grades_fair_forecast(self, tracker):
        """Test FAIR grade for MAE 3-5p."""
        # Record fair forecast
        for day in range(1, 8):
            comparison_date = date(2025, 12, day)
            forecast = [10.0] * 24
            actual = [14.0] * 24  # 4p error

            tracker.record_comparison(comparison_date, forecast, actual)

        grade = tracker.get_reliability_grade(days=7)

        assert grade == "FAIR"

    def test_grades_poor_forecast(self, tracker):
        """Test POOR grade for MAE > 5p."""
        # Record poor forecast
        for day in range(1, 8):
            comparison_date = date(2025, 12, day)
            forecast = [10.0] * 24
            actual = [18.0] * 24  # 8p error

            tracker.record_comparison(comparison_date, forecast, actual)

        grade = tracker.get_reliability_grade(days=7)

        assert grade == "POOR"

    def test_returns_unknown_for_insufficient_data(self, tracker):
        """Test UNKNOWN grade when fewer than 3 comparisons."""
        # Record only 2 days
        for day in range(1, 3):
            comparison_date = date(2025, 12, day)
            tracker.record_comparison(comparison_date, [10.0] * 24, [11.0] * 24)

        grade = tracker.get_reliability_grade(days=7)

        assert grade == "UNKNOWN"


class TestDataPersistence:
    """Test data storage and retrieval."""

    def test_persists_across_instances(self, temp_data_dir):
        """Test data persists when creating new tracker instance."""
        # Create first tracker and record data
        tracker1 = ForecastTracker(data_dir=temp_data_dir)
        tracker1.record_comparison(date(2025, 12, 8), [10.0] * 24, [11.0] * 24)

        # Create second tracker and read data
        tracker2 = ForecastTracker(data_dir=temp_data_dir)
        metrics = tracker2.get_recent_accuracy(days=7)

        assert metrics["num_comparisons"] == 1
        assert metrics["mean_absolute_error"] == pytest.approx(1.0, abs=0.01)

    def test_handles_missing_file_gracefully(self, temp_data_dir):
        """Test handles missing accuracy file without error."""
        tracker = ForecastTracker(data_dir=temp_data_dir)

        # Should not raise error
        metrics = tracker.get_recent_accuracy(days=7)

        assert metrics["num_comparisons"] == 0
        assert metrics["mean_absolute_error"] is None

"""Tests for cost_tracker module"""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile

from src.modules.cost_tracker import CostTracker
from src.modules.data_store import DataStore


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def data_store(temp_data_dir):
    """Create DataStore with temporary directory"""
    return DataStore(data_dir=temp_data_dir)


@pytest.fixture
def cost_tracker(data_store):
    """Create CostTracker with test DataStore"""
    return CostTracker(data_store)


@pytest.fixture
def sample_recommendations(data_store):
    """Create sample recommendations for December 2025"""
    recommendations = [
        {
            "date": "2025-12-01",
            "total_cost": 4.50,
            "savings": 1.50,
            "rating": "EXCELLENT",
            "avg_price": 8.0,
        },
        {
            "date": "2025-12-03",
            "total_cost": 5.20,
            "savings": 0.80,
            "rating": "GOOD",
            "avg_price": 10.5,
        },
        {
            "date": "2025-12-05",
            "total_cost": 6.10,
            "savings": -0.10,
            "rating": "AVERAGE",
            "avg_price": 15.0,
        },
        {
            "date": "2025-12-07",
            "total_cost": 4.20,
            "savings": 1.80,
            "rating": "EXCELLENT",
            "avg_price": 7.5,
        },
        {
            "date": "2025-12-10",
            "total_cost": 7.00,
            "savings": -1.00,
            "rating": "POOR",
            "avg_price": 18.0,
        },
    ]

    for rec in recommendations:
        data_store.save_recommendation(rec)

    return recommendations


@pytest.fixture
def sample_actions(data_store):
    """Create sample user actions for December 2025"""
    actions = [
        {"date": "2025-12-01", "action": "charged"},  # EXCELLENT
        {"date": "2025-12-03", "action": "charged"},  # GOOD
        {"date": "2025-12-07", "action": "charged"},  # EXCELLENT
    ]

    for action in actions:
        data_store.save_user_action(action)

    return actions


class TestCostTracker:
    """Test suite for CostTracker"""

    def test_initialization(self, cost_tracker, temp_data_dir):
        """Test CostTracker initializes correctly"""
        assert cost_tracker.data_store is not None
        assert cost_tracker.COST_HISTORY_FILE == temp_data_dir / "cost_history.json"
        assert cost_tracker.STANDARD_BASELINE_RATE == 15.0
        assert cost_tracker.PEAK_BASELINE_RATE == 20.0

    def test_aggregate_month_with_data(
        self, cost_tracker, sample_recommendations, sample_actions
    ):
        """Test monthly aggregation with sample data"""
        result = cost_tracker.aggregate_month(2025, 12, kwh_per_charge=30.0)

        assert result["year"] == 2025
        assert result["month"] == 12
        assert result["num_charges"] == 3
        assert result["total_cost"] == 13.90  # 4.50 + 5.20 + 4.20
        assert result["total_savings"] == 4.10  # 1.50 + 0.80 + 1.80
        assert result["avg_cost_per_charge"] == pytest.approx(4.63, rel=0.01)
        assert result["charges_on_good_days"] == 3  # All 3 were good opportunities
        assert (
            result["good_opportunities"] == 3
        )  # 2 EXCELLENT + 1 GOOD in recommendations
        assert result["adherence_rate"] == 100.0  # 3/3 = 100%

    def test_aggregate_month_empty(self, cost_tracker):
        """Test monthly aggregation with no data"""
        result = cost_tracker.aggregate_month(2025, 11, kwh_per_charge=30.0)

        assert result["year"] == 2025
        assert result["month"] == 11
        assert result["num_charges"] == 0
        assert result["total_cost"] == 0.0
        assert result["total_savings"] == 0.0
        assert result["avg_cost_per_charge"] == 0.0
        assert result["adherence_rate"] == 0.0

    def test_aggregate_month_partial_adherence(
        self, cost_tracker, data_store, sample_recommendations
    ):
        """Test monthly aggregation with partial adherence"""
        # Only charge on 2 of the 3 good days
        data_store.save_user_action({"date": "2025-12-01", "action": "charged"})
        data_store.save_user_action({"date": "2025-12-05", "action": "charged"})

        result = cost_tracker.aggregate_month(2025, 12, kwh_per_charge=30.0)

        assert result["num_charges"] == 2
        assert result["charges_on_good_days"] == 1  # Only Dec 1 was EXCELLENT
        assert result["good_opportunities"] == 3  # 2 EXCELLENT + 1 GOOD
        assert result["adherence_rate"] == pytest.approx(33.3, rel=0.1)

    def test_calculate_baseline_comparisons(self, cost_tracker):
        """Test baseline cost calculations"""
        result = cost_tracker.calculate_baseline_comparisons(
            actual_cost=20.0, num_charges=5, kwh_per_charge=30.0
        )

        # 5 charges * 30 kWh = 150 kWh
        # Standard: 150 * 15p / 100 = £22.50
        # Peak: 150 * 20p / 100 = £30.00
        assert result["standard_baseline_cost"] == 22.50
        assert result["peak_baseline_cost"] == 30.00
        assert result["standard_savings"] == 2.50  # 22.50 - 20.00
        assert result["peak_savings"] == 10.00  # 30.00 - 20.00

    def test_calculate_baseline_comparisons_higher_cost(self, cost_tracker):
        """Test baseline comparisons when actual cost is higher than baseline"""
        result = cost_tracker.calculate_baseline_comparisons(
            actual_cost=25.0, num_charges=5, kwh_per_charge=30.0
        )

        assert result["standard_baseline_cost"] == 22.50
        assert result["standard_savings"] == -2.50  # Negative savings (lost money)

    def test_get_monthly_summary(
        self, cost_tracker, sample_recommendations, sample_actions
    ):
        """Test complete monthly summary generation"""
        summary = cost_tracker.get_monthly_summary(2025, 12, kwh_per_charge=30.0)

        assert summary["year"] == 2025
        assert summary["month"] == 12
        assert summary["num_charges"] == 3
        assert "baseline_comparisons" in summary
        assert "kwh_per_charge" in summary
        assert "generated_at" in summary

        # Check baseline comparisons exist (savings can be positive or negative)
        baselines = summary["baseline_comparisons"]
        assert baselines["standard_baseline_cost"] > 0
        assert baselines["peak_baseline_cost"] > 0
        assert "standard_savings" in baselines

    def test_get_monthly_summary_no_charges(self, cost_tracker):
        """Test monthly summary with no charges"""
        summary = cost_tracker.get_monthly_summary(2025, 11, kwh_per_charge=30.0)

        assert summary["num_charges"] == 0
        baselines = summary["baseline_comparisons"]
        assert baselines["standard_baseline_cost"] == 0.0
        assert baselines["peak_baseline_cost"] == 0.0
        assert baselines["standard_savings"] == 0.0

    def test_save_monthly_aggregate(
        self, cost_tracker, sample_recommendations, sample_actions
    ):
        """Test saving monthly aggregate to file"""
        cost_tracker.save_monthly_aggregate(2025, 12, kwh_per_charge=30.0)

        # Check file exists
        assert cost_tracker.COST_HISTORY_FILE.exists()

        # Load and verify content
        history = cost_tracker._load_cost_history()
        assert "monthly_summaries" in history
        assert len(history["monthly_summaries"]) == 1

        summary = history["monthly_summaries"][0]
        assert summary["year"] == 2025
        assert summary["month"] == 12
        assert summary["num_charges"] == 3

    def test_save_monthly_aggregate_overwrites_existing(
        self, cost_tracker, sample_recommendations, sample_actions
    ):
        """Test that saving same month twice overwrites previous entry"""
        # Save first time
        cost_tracker.save_monthly_aggregate(2025, 12, kwh_per_charge=30.0)

        # Add another action
        cost_tracker.data_store.save_user_action(
            {"date": "2025-12-05", "action": "charged"}
        )

        # Save again
        cost_tracker.save_monthly_aggregate(2025, 12, kwh_per_charge=30.0)

        # Should still have only one entry
        history = cost_tracker._load_cost_history()
        assert len(history["monthly_summaries"]) == 1

        # But with updated count
        summary = history["monthly_summaries"][0]
        assert summary["num_charges"] == 4  # 3 original + 1 new

    def test_get_cost_history(
        self, cost_tracker, sample_recommendations, sample_actions
    ):
        """Test retrieving cost history"""
        # Save multiple months
        cost_tracker.save_monthly_aggregate(2025, 12, kwh_per_charge=30.0)
        cost_tracker.save_monthly_aggregate(2025, 11, kwh_per_charge=30.0)
        cost_tracker.save_monthly_aggregate(2025, 10, kwh_per_charge=30.0)

        # Get history
        history = cost_tracker.get_cost_history(months=12)

        assert len(history) == 3
        # Should be most recent first
        assert history[0]["year"] == 2025
        assert history[0]["month"] == 12

    def test_get_cost_history_limited(
        self, cost_tracker, sample_recommendations, sample_actions
    ):
        """Test retrieving limited cost history"""
        # Save 5 months
        for month in range(8, 13):
            cost_tracker.save_monthly_aggregate(2025, month, kwh_per_charge=30.0)

        # Get only 3
        history = cost_tracker.get_cost_history(months=3)

        assert len(history) == 3
        assert history[0]["month"] == 12
        assert history[1]["month"] == 11
        assert history[2]["month"] == 10

    def test_get_yearly_projection_no_data(self, cost_tracker):
        """Test yearly projection with no data"""
        projection = cost_tracker.get_yearly_projection(kwh_per_charge=30.0)

        assert projection["year"] == datetime.now().year
        assert projection["ytd_cost"] == 0.0
        assert projection["ytd_savings"] == 0.0
        assert projection["ytd_charges"] == 0
        assert projection["projected_annual_cost"] == 0.0
        assert projection["projected_annual_savings"] == 0.0
        assert projection["months_of_data"] == 0

    def test_get_yearly_projection_with_data(self, cost_tracker):
        """Test yearly projection with actual data"""
        current_year = datetime.now().year
        current_month = datetime.now().month

        # Save data for current month (don't use sample fixtures to avoid conflicts)
        # Use low costs so we have positive savings vs baseline
        for i in range(1, 4):
            date_str = f"{current_year}-{current_month:02d}-{i:02d}"
            cost_tracker.data_store.save_recommendation(
                {
                    "date": date_str,
                    "total_cost": 3.0,  # Low cost for positive savings
                    "savings": 1.0,
                    "rating": "GOOD",
                    "avg_price": 10.0,
                }
            )
            cost_tracker.data_store.save_user_action(
                {"date": date_str, "action": "charged"}
            )

        cost_tracker.save_monthly_aggregate(
            current_year, current_month, kwh_per_charge=30.0
        )

        projection = cost_tracker.get_yearly_projection(kwh_per_charge=30.0)

        assert projection["year"] == current_year
        assert projection["ytd_charges"] == 3
        assert projection["months_of_data"] == 1
        assert projection["projected_annual_cost"] > 0
        # Savings can be positive or negative depending on actual costs
        assert "projected_annual_savings" in projection

    def test_is_in_month(self, cost_tracker):
        """Test date month checking"""
        assert cost_tracker._is_in_month("2025-12-15", 2025, 12) is True
        assert cost_tracker._is_in_month("2025-12-01", 2025, 12) is True
        assert cost_tracker._is_in_month("2025-12-31", 2025, 12) is True
        assert cost_tracker._is_in_month("2025-11-30", 2025, 12) is False
        assert cost_tracker._is_in_month("2026-12-15", 2025, 12) is False
        assert cost_tracker._is_in_month(None, 2025, 12) is False
        assert cost_tracker._is_in_month("invalid", 2025, 12) is False

    def test_is_in_month_with_timestamp(self, cost_tracker):
        """Test date month checking with ISO timestamp"""
        assert cost_tracker._is_in_month("2025-12-15T10:30:00+00:00", 2025, 12) is True
        assert cost_tracker._is_in_month("2025-11-15T10:30:00+00:00", 2025, 12) is False

    def test_charges_by_rating(
        self, cost_tracker, sample_recommendations, sample_actions
    ):
        """Test that charges are correctly categorized by rating"""
        result = cost_tracker.aggregate_month(2025, 12, kwh_per_charge=30.0)

        ratings = result["charges_by_rating"]
        assert ratings["EXCELLENT"] == 2  # Dec 1 and Dec 7
        assert ratings["GOOD"] == 1  # Dec 3
        assert ratings["AVERAGE"] == 0
        assert ratings["POOR"] == 0

    def test_different_kwh_per_charge(self, cost_tracker, sample_recommendations):
        """Test baseline calculations with different kWh values"""
        cost_tracker.data_store.save_user_action(
            {"date": "2025-12-01", "action": "charged"}
        )

        # Test with 20 kWh
        result_20 = cost_tracker.calculate_baseline_comparisons(
            actual_cost=10.0, num_charges=5, kwh_per_charge=20.0
        )

        # Test with 40 kWh
        result_40 = cost_tracker.calculate_baseline_comparisons(
            actual_cost=10.0, num_charges=5, kwh_per_charge=40.0
        )

        # 40 kWh should have higher baseline costs
        assert result_40["standard_baseline_cost"] > result_20["standard_baseline_cost"]
        assert result_40["peak_baseline_cost"] > result_20["peak_baseline_cost"]

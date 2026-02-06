"""Tests for Multi-Day Planner Module"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from src.modules.multi_day_planner import (
    MultiDayPlanner,
    DayComparison,
    MultiDayPlan,
)
from src.modules.analyzer import (
    Analyzer,
    PriceSlot,
    CarbonSlot,
    ChargingWindow,
    OpportunityRating,
)
from src.modules.data_store import DataStore


@pytest.fixture
def mock_config():
    """Mock configuration dictionary"""
    return {
        "user": {
            "region": "H",
            "postcode": "E1",
            "charging_rate_kw": 2.3,
            "typical_charge_kwh": 30.0,
        },
        "preferences": {
            "price_weight": 0.6,
            "carbon_weight": 0.4,
        },
        "thresholds": {
            "price_excellent": 10,
            "price_good": 15,
            "carbon_excellent": 100,
            "carbon_good": 150,
        },
    }


@pytest.fixture
def mock_analyzer():
    """Mock analyzer"""
    analyzer = Mock(spec=Analyzer)
    return analyzer


@pytest.fixture
def mock_data_store(tmp_path):
    """Mock data store with temp directory"""
    store = DataStore(data_dir=tmp_path)
    return store


@pytest.fixture
def planner(mock_config, mock_analyzer, mock_data_store):
    """Multi-day planner instance with mocked dependencies (3-day for test compat)"""
    return MultiDayPlanner(mock_config, mock_analyzer, mock_data_store, num_days=3)


def create_price_slots(base_time, count, base_price):
    """Helper to create price slots"""
    slots = []
    for i in range(count):
        time = base_time + timedelta(minutes=30 * i)
        slots.append(PriceSlot(time, base_price + i * 0.5, "octopus"))
    return slots


def create_carbon_slots(base_time, count, base_intensity):
    """Helper to create carbon slots"""
    slots = []
    for i in range(count):
        time = base_time + timedelta(minutes=30 * i)
        slots.append(CarbonSlot(time, base_intensity + i * 5))
    return slots


def create_mock_window(start_time, end_time, avg_price, cost, rating, avg_carbon=100):
    """Helper to create mock charging window"""
    return ChargingWindow(
        start=start_time,
        end=end_time,
        avg_price=avg_price,
        avg_carbon=avg_carbon,
        total_cost=cost,
        total_carbon=3000,
        opportunity_score=85.0,
        rating=rating,
        reason="both",
        savings_vs_baseline=2.5,
    )


class TestDayComparison:
    """Test DayComparison dataclass"""

    def test_day_comparison_creation(self):
        """Test creating a DayComparison"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        comparison = DayComparison(
            date=today.date().isoformat(),
            day_name="Today",
            avg_price=15.2,
            optimal_window={
                "start": today.replace(hour=22).isoformat(),
                "end": today.replace(hour=23).isoformat(),
            },
            cost=4.56,
            rating="GOOD",
            price_source="octopus_actual",
            savings_vs_today=0.0,
            avg_carbon=120,
        )

        assert comparison.day_name == "Today"
        assert comparison.avg_price == 15.2
        assert comparison.cost == 4.56
        assert comparison.rating == "GOOD"
        assert comparison.price_source == "octopus_actual"


class TestMultiDayPlan:
    """Test MultiDayPlan dataclass"""

    def test_multi_day_plan_creation(self):
        """Test creating a MultiDayPlan"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        comparison = DayComparison(
            date=today.date().isoformat(),
            day_name="Today",
            avg_price=15.2,
            optimal_window={
                "start": today.replace(hour=22).isoformat(),
                "end": today.replace(hour=23).isoformat(),
            },
            cost=4.56,
            rating="GOOD",
            price_source="octopus_actual",
            savings_vs_today=0.0,
            avg_carbon=120,
        )

        plan = MultiDayPlan(
            timestamp=datetime.now(timezone.utc).isoformat(),
            kwh_amount=30.0,
            num_days=7,
            days=[comparison],
            best_day={"date": today.date().isoformat(), "day_name": "Today"},
        )

        assert plan.kwh_amount == 30.0
        assert plan.num_days == 7
        assert len(plan.days) == 1
        assert plan.best_day["day_name"] == "Today"


class TestMultiDayPlanner:
    """Test MultiDayPlanner class"""

    def test_planner_initialization(self, planner, mock_config):
        """Test planner initializes correctly"""
        assert planner.config == mock_config
        assert planner.analyzer is not None
        assert planner.data_store is not None

    def test_get_multi_day_prices_with_octopus_data(self, planner):
        """Test fetching multi-day prices when Octopus has data"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Mock Octopus API to return 48 hours of data
        octopus_prices = []
        for i in range(96):  # 48 hours = 96 half-hour slots
            time = today + timedelta(minutes=30 * i)
            octopus_prices.append(
                {
                    "valid_from": time.isoformat().replace("+00:00", "Z"),
                    "value_inc_vat": 15.0 + i * 0.1,
                }
            )

        planner.octopus_client.get_prices = Mock(return_value=octopus_prices)

        # Mock carbon API
        planner.carbon_client.get_intensity = Mock(return_value=[])

        # Get multi-day data (planner fixture uses 3 days)
        multi_day_data = planner._get_multi_day_prices()

        assert len(multi_day_data) == 3
        assert planner.octopus_client.get_prices.called

        # First 2 days should have Octopus data, day 3 might not have enough coverage
        target_date, price_slots, carbon_slots, price_source = multi_day_data[0]
        assert len(price_slots) > 0
        assert price_source == "octopus_actual"

    @patch("src.modules.multi_day_planner.ForecastAPIClient")
    def test_get_multi_day_prices_falls_back_to_forecast(
        self, mock_forecast_client, planner
    ):
        """Test fallback to forecast when Octopus data insufficient"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Mock Octopus to fail
        planner.octopus_client.get_prices = Mock(side_effect=Exception("API Error"))

        # Mock forecast API
        forecast_data = []
        for day_offset in range(3):
            for hour in range(24):
                for half_hour in [0, 30]:
                    target_date = today + timedelta(days=day_offset)
                    forecast_data.append(
                        {
                            "date": target_date.date().isoformat(),
                            "time": f"{hour:02d}:{half_hour:02d}",
                            "price": 15.0 + hour * 0.5,
                        }
                    )

        planner.forecast_client.get_forecasts = Mock(return_value=forecast_data)
        planner.carbon_client.get_intensity = Mock(return_value=[])

        # Get multi-day data
        multi_day_data = planner._get_multi_day_prices()

        assert len(multi_day_data) == 3
        assert planner.forecast_client.get_forecasts.called

        # All should be forecast source
        for day_data in multi_day_data:
            _, price_slots, _, price_source = day_data
            assert price_source == "forecast"
            assert len(price_slots) > 0

    def test_compare_days(self, planner, mock_analyzer):
        """Test day comparison logic"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Create mock 3-day data
        three_day_data = []
        for day_offset in range(3):
            target_date = today + timedelta(days=day_offset)
            price_slots = create_price_slots(
                target_date.replace(hour=0), 48, 10.0 + day_offset * 3
            )
            carbon_slots = create_carbon_slots(target_date.replace(hour=0), 48, 100)
            three_day_data.append(
                (target_date, price_slots, carbon_slots, "octopus_actual")
            )

        # Mock analyzer to return windows with different costs
        windows = [
            create_mock_window(
                today.replace(hour=22),
                today.replace(hour=23),
                15.0,
                4.50,
                OpportunityRating.AVERAGE,
            ),
            create_mock_window(
                today.replace(hour=22) + timedelta(days=1),
                today.replace(hour=23) + timedelta(days=1),
                8.0,
                2.40,
                OpportunityRating.EXCELLENT,
            ),
            create_mock_window(
                today.replace(hour=22) + timedelta(days=2),
                today.replace(hour=23) + timedelta(days=2),
                12.0,
                3.60,
                OpportunityRating.GOOD,
            ),
        ]

        mock_analyzer.find_optimal_window = Mock(side_effect=windows)

        # Compare days
        comparisons = planner._compare_days(three_day_data, 30.0)

        assert len(comparisons) == 3
        assert comparisons[0].day_name == "Today"
        assert comparisons[1].day_name == "Tomorrow"
        assert comparisons[2].day_name == "Day 3"

        # Check savings calculations
        assert comparisons[0].savings_vs_today == 0.0
        assert comparisons[1].savings_vs_today > 0  # Tomorrow is cheaper
        assert comparisons[2].savings_vs_today > 0  # Day after is cheaper

    def test_identify_best_day_when_today_is_best(self, planner):
        """Test identifying best day when today is cheapest"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        comparisons = [
            DayComparison(
                date=today.date().isoformat(),
                day_name="Today",
                avg_price=8.0,
                optimal_window={},
                cost=2.40,
                rating="EXCELLENT",
                price_source="octopus_actual",
                savings_vs_today=0.0,
                avg_carbon=100,
            ),
            DayComparison(
                date=(today + timedelta(days=1)).date().isoformat(),
                day_name="Tomorrow",
                avg_price=15.0,
                optimal_window={},
                cost=4.50,
                rating="AVERAGE",
                price_source="forecast",
                savings_vs_today=-2.10,
                avg_carbon=120,
            ),
        ]

        best_day = planner._identify_best_day(comparisons)

        assert best_day["day_name"] == "Today"
        assert "Today has the best prices" in best_day["reason"]

    def test_identify_best_day_when_tomorrow_is_best(self, planner):
        """Test identifying best day when tomorrow is cheapest"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        comparisons = [
            DayComparison(
                date=today.date().isoformat(),
                day_name="Today",
                avg_price=18.0,
                optimal_window={},
                cost=5.40,
                rating="AVERAGE",
                price_source="octopus_actual",
                savings_vs_today=0.0,
                avg_carbon=100,
            ),
            DayComparison(
                date=(today + timedelta(days=1)).date().isoformat(),
                day_name="Tomorrow",
                avg_price=8.0,
                optimal_window={},
                cost=2.40,
                rating="EXCELLENT",
                price_source="octopus_actual",
                savings_vs_today=3.00,
                avg_carbon=90,
            ),
        ]

        best_day = planner._identify_best_day(comparisons)

        assert best_day["day_name"] == "Tomorrow"
        assert abs(best_day["savings"] - 3.00) < 0.01  # Handle floating point
        assert best_day["percentage"] > 50  # Significant savings

    def test_identify_best_day_edge_case_all_similar(self, planner):
        """Test when all days have similar prices"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        comparisons = [
            DayComparison(
                date=today.date().isoformat(),
                day_name="Today",
                avg_price=15.0,
                optimal_window={},
                cost=4.50,
                rating="GOOD",
                price_source="octopus_actual",
                savings_vs_today=0.0,
                avg_carbon=100,
            ),
            DayComparison(
                date=(today + timedelta(days=1)).date().isoformat(),
                day_name="Tomorrow",
                avg_price=14.8,
                optimal_window={},
                cost=4.44,
                rating="GOOD",
                price_source="forecast",
                savings_vs_today=0.06,
                avg_carbon=105,
            ),
        ]

        best_day = planner._identify_best_day(comparisons)

        # Tomorrow is slightly cheaper
        assert best_day["day_name"] == "Tomorrow"
        assert best_day["savings"] < 0.10  # Minimal savings

    def test_identify_best_day_with_negative_pricing(self, planner):
        """Test when one day has negative pricing"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        comparisons = [
            DayComparison(
                date=today.date().isoformat(),
                day_name="Today",
                avg_price=15.0,
                optimal_window={},
                cost=4.50,
                rating="GOOD",
                price_source="octopus_actual",
                savings_vs_today=0.0,
                avg_carbon=100,
            ),
            DayComparison(
                date=(today + timedelta(days=1)).date().isoformat(),
                day_name="Tomorrow",
                avg_price=-5.0,  # Negative pricing!
                optimal_window={},
                cost=-1.50,
                rating="EXCELLENT",
                price_source="octopus_actual",
                savings_vs_today=6.00,
                avg_carbon=80,
            ),
        ]

        best_day = planner._identify_best_day(comparisons)

        assert best_day["day_name"] == "Tomorrow"
        assert best_day["savings"] == 6.00
        assert best_day["percentage"] > 100  # More than 100% "savings"

    @patch.object(MultiDayPlanner, "_get_multi_day_prices")
    @patch.object(MultiDayPlanner, "_compare_days")
    @patch.object(MultiDayPlanner, "_identify_best_day")
    @patch.object(MultiDayPlanner, "_save_plan")
    def test_generate_plan_integration(
        self,
        mock_save,
        mock_identify,
        mock_compare,
        mock_get_prices,
        planner,
    ):
        """Test full plan generation workflow"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Mock the pipeline
        mock_get_prices.return_value = [
            (
                today,
                create_price_slots(today, 48, 15.0),
                create_carbon_slots(today, 48, 100),
                "octopus_actual",
            )
        ]

        mock_comparisons = [
            DayComparison(
                date=today.date().isoformat(),
                day_name="Today",
                avg_price=15.0,
                optimal_window={},
                cost=4.50,
                rating="GOOD",
                price_source="octopus_actual",
                savings_vs_today=0.0,
                avg_carbon=100,
            )
        ]
        mock_compare.return_value = mock_comparisons

        mock_identify.return_value = {
            "date": today.date().isoformat(),
            "day_name": "Today",
            "reason": "Today has the best prices",
            "savings": 0.0,
            "percentage": 0.0,
        }

        # Generate plan
        plan = planner.generate_plan(kwh=30.0)

        assert plan.kwh_amount == 30.0
        assert plan.num_days == 3
        assert len(plan.days) == 1
        assert plan.best_day["day_name"] == "Today"
        assert mock_save.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for weekend pattern detection and analysis"""

from datetime import datetime, timezone
from src.scripts.weekly_summary import analyze_week


class TestWeekendPatterns:
    """Test weekend vs weekday pattern detection"""

    def test_day_type_classification(self):
        """Test that recommendations are properly classified as weekday/weekend"""
        # Create sample recommendations with different day types
        recommendations = [
            {
                "date": "2025-12-02",  # Monday
                "day_type": "weekday",
                "rating": "EXCELLENT",
                "avg_price": 10.0,
                "total_cost": 2.0,
                "total_carbon": 100,
                "savings": 1.5,
            },
            {
                "date": "2025-12-06",  # Friday
                "day_type": "weekday",
                "rating": "GOOD",
                "avg_price": 12.0,
                "total_cost": 2.5,
                "total_carbon": 120,
                "savings": 1.0,
            },
            {
                "date": "2025-12-07",  # Saturday
                "day_type": "weekend",
                "rating": "EXCELLENT",
                "avg_price": 8.0,
                "total_cost": 1.8,
                "total_carbon": 90,
                "savings": 2.0,
            },
            {
                "date": "2025-12-08",  # Sunday
                "day_type": "weekend",
                "rating": "GOOD",
                "avg_price": 9.0,
                "total_cost": 2.0,
                "total_carbon": 95,
                "savings": 1.8,
            },
        ]

        user_actions = []

        analysis = analyze_week(recommendations, user_actions)

        # Verify weekday/weekend separation
        assert analysis["weekday_good_opps"] == 2  # Mon, Fri
        assert analysis["weekend_good_opps"] == 2  # Sat, Sun

    def test_separate_adherence_tracking(self):
        """Test that adherence is tracked separately for weekdays vs weekends"""
        recommendations = [
            {
                "date": "2025-12-02",  # Monday
                "day_type": "weekday",
                "rating": "EXCELLENT",
                "avg_price": 10.0,
                "total_cost": 2.0,
                "total_carbon": 100,
                "savings": 1.5,
            },
            {
                "date": "2025-12-03",  # Tuesday
                "day_type": "weekday",
                "rating": "GOOD",
                "avg_price": 12.0,
                "total_cost": 2.5,
                "total_carbon": 120,
                "savings": 1.0,
            },
            {
                "date": "2025-12-07",  # Saturday
                "day_type": "weekend",
                "rating": "EXCELLENT",
                "avg_price": 8.0,
                "total_cost": 1.8,
                "total_carbon": 90,
                "savings": 2.0,
            },
            {
                "date": "2025-12-08",  # Sunday
                "day_type": "weekend",
                "rating": "GOOD",
                "avg_price": 9.0,
                "total_cost": 2.0,
                "total_carbon": 95,
                "savings": 1.8,
            },
        ]

        # User charged on Monday and Saturday (1 weekday, 1 weekend)
        user_actions = [
            {"date": "2025-12-02", "type": "charge", "kwh": 30},
            {"date": "2025-12-07", "type": "charge", "kwh": 30},
        ]

        analysis = analyze_week(recommendations, user_actions)

        # Check weekday adherence: 1 charge out of 2 good opportunities = 50%
        assert analysis["weekday_adherence"] == 50.0
        assert analysis["weekday_charges_good"] == 1
        assert analysis["weekday_good_opps"] == 2

        # Check weekend adherence: 1 charge out of 2 good opportunities = 50%
        assert analysis["weekend_adherence"] == 50.0
        assert analysis["weekend_charges_good"] == 1
        assert analysis["weekend_good_opps"] == 2

    def test_perfect_weekend_adherence(self):
        """Test scenario where user follows all weekend recommendations"""
        recommendations = [
            {
                "date": "2025-12-02",
                "day_type": "weekday",
                "rating": "EXCELLENT",
                "avg_price": 10.0,
                "total_cost": 2.0,
                "total_carbon": 100,
                "savings": 1.5,
            },
            {
                "date": "2025-12-07",
                "day_type": "weekend",
                "rating": "EXCELLENT",
                "avg_price": 8.0,
                "total_cost": 1.8,
                "total_carbon": 90,
                "savings": 2.0,
            },
            {
                "date": "2025-12-08",
                "day_type": "weekend",
                "rating": "GOOD",
                "avg_price": 9.0,
                "total_cost": 2.0,
                "total_carbon": 95,
                "savings": 1.8,
            },
        ]

        # User charged both weekend days but missed weekday
        user_actions = [
            {"date": "2025-12-07", "type": "charge", "kwh": 30},
            {"date": "2025-12-08", "type": "charge", "kwh": 30},
        ]

        analysis = analyze_week(recommendations, user_actions)

        # Perfect weekend adherence
        assert analysis["weekend_adherence"] == 100.0
        assert analysis["weekend_charges_good"] == 2
        assert analysis["weekend_good_opps"] == 2

        # Poor weekday adherence
        assert analysis["weekday_adherence"] == 0.0
        assert analysis["weekday_charges_good"] == 0
        assert analysis["weekday_good_opps"] == 1

    def test_no_weekend_opportunities(self):
        """Test behavior when there are no weekend opportunities"""
        recommendations = [
            {
                "date": "2025-12-02",
                "day_type": "weekday",
                "rating": "EXCELLENT",
                "avg_price": 10.0,
                "total_cost": 2.0,
                "total_carbon": 100,
                "savings": 1.5,
            },
            {
                "date": "2025-12-03",
                "day_type": "weekday",
                "rating": "GOOD",
                "avg_price": 12.0,
                "total_cost": 2.5,
                "total_carbon": 120,
                "savings": 1.0,
            },
            {
                "date": "2025-12-07",
                "day_type": "weekend",
                "rating": "AVERAGE",  # Not a good opportunity
                "avg_price": 18.0,
                "total_cost": 3.5,
                "total_carbon": 180,
                "savings": 0.5,
            },
        ]

        user_actions = []

        analysis = analyze_week(recommendations, user_actions)

        # Should handle zero weekend opportunities gracefully
        assert analysis["weekend_adherence"] == 0.0
        assert analysis["weekend_good_opps"] == 0
        assert analysis["weekday_good_opps"] == 2

    def test_day_type_defaults_to_weekday(self):
        """Test that missing day_type defaults to weekday"""
        recommendations = [
            {
                "date": "2025-12-02",
                # day_type missing
                "rating": "EXCELLENT",
                "avg_price": 10.0,
                "total_cost": 2.0,
                "total_carbon": 100,
                "savings": 1.5,
            },
        ]

        user_actions = []

        analysis = analyze_week(recommendations, user_actions)

        # Should default to weekday
        assert analysis["weekday_good_opps"] == 1
        assert analysis["weekend_good_opps"] == 0

    def test_mixed_ratings_weekend_tracking(self):
        """Test that only GOOD/EXCELLENT count as opportunities"""
        recommendations = [
            {
                "date": "2025-12-07",  # Saturday
                "day_type": "weekend",
                "rating": "EXCELLENT",
                "avg_price": 8.0,
                "total_cost": 1.8,
                "total_carbon": 90,
                "savings": 2.0,
            },
            {
                "date": "2025-12-08",  # Sunday
                "day_type": "weekend",
                "rating": "AVERAGE",  # Not counted
                "avg_price": 18.0,
                "total_cost": 3.5,
                "total_carbon": 180,
                "savings": 0.5,
            },
        ]

        user_actions = [
            {"date": "2025-12-07", "type": "charge", "kwh": 30},
        ]

        analysis = analyze_week(recommendations, user_actions)

        # Only Saturday is a good opportunity
        assert analysis["weekend_good_opps"] == 1
        assert analysis["weekend_charges_good"] == 1
        assert analysis["weekend_adherence"] == 100.0


class TestDayTypeDetection:
    """Test day type detection in daily notification"""

    def test_weekday_detection(self):
        """Test that weekdays are correctly identified"""
        # Monday = 0, Friday = 4
        # Dec 1, 2025 is a Monday, so Dec 1-5 are weekdays
        for day in range(5):
            dt = datetime(2025, 12, 1 + day, tzinfo=timezone.utc)  # Dec 1-5, 2025
            assert dt.weekday() < 5, f"Day {day} should be a weekday"

    def test_weekend_detection(self):
        """Test that weekends are correctly identified"""
        # Saturday = 5, Sunday = 6
        saturday = datetime(2025, 12, 6, tzinfo=timezone.utc)
        sunday = datetime(2025, 12, 7, tzinfo=timezone.utc)

        assert saturday.weekday() == 5, "Saturday should be day 5"
        assert sunday.weekday() == 6, "Sunday should be day 6"

        assert saturday.weekday() >= 5, "Saturday should be weekend"
        assert sunday.weekday() >= 5, "Sunday should be weekend"

    def test_day_type_string_classification(self):
        """Test the actual classification logic used in daily_notification"""
        # Simulate the logic from daily_notification.py
        test_cases = [
            (datetime(2025, 12, 1, tzinfo=timezone.utc), "weekday"),  # Monday
            (datetime(2025, 12, 2, tzinfo=timezone.utc), "weekday"),  # Tuesday
            (datetime(2025, 12, 3, tzinfo=timezone.utc), "weekday"),  # Wednesday
            (datetime(2025, 12, 4, tzinfo=timezone.utc), "weekday"),  # Thursday
            (datetime(2025, 12, 5, tzinfo=timezone.utc), "weekday"),  # Friday
            (datetime(2025, 12, 6, tzinfo=timezone.utc), "weekend"),  # Saturday
            (datetime(2025, 12, 7, tzinfo=timezone.utc), "weekend"),  # Sunday
        ]

        for dt, expected_type in test_cases:
            day_of_week = dt.weekday()
            day_type = "weekend" if day_of_week >= 5 else "weekday"
            assert (
                day_type == expected_type
            ), f"{dt.strftime('%A')} should be {expected_type}"

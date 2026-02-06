"""Tests for Data Storage Layer."""

import pytest
from datetime import datetime, timedelta
from src.modules.data_store import DataStore


class TestDataStore:
    """Tests for DataStore."""

    def test_init(self, temp_data_dir):
        """Test data store initialization."""
        store = DataStore(data_dir=temp_data_dir)
        assert store.DATA_DIR == temp_data_dir
        assert temp_data_dir.exists()

    def test_save_forecast(self, temp_data_dir, sample_forecast):
        """Test saving a forecast."""
        store = DataStore(data_dir=temp_data_dir)
        store.save_forecast(sample_forecast)

        # Verify file was created
        assert store.FORECAST_FILE.exists()

        # Verify data was saved
        forecasts = store._load_json(store.FORECAST_FILE, default=[])
        assert len(forecasts) == 1
        assert forecasts[0]["timestamp"] == sample_forecast["timestamp"]

    def test_save_forecast_missing_timestamp(self, temp_data_dir):
        """Test saving forecast without timestamp fails."""
        store = DataStore(data_dir=temp_data_dir)

        with pytest.raises(ValueError, match="must include 'timestamp'"):
            store.save_forecast({"data": []})

    def test_get_latest_forecast(self, temp_data_dir, sample_forecast):
        """Test getting the latest forecast."""
        store = DataStore(data_dir=temp_data_dir)

        # Save multiple forecasts
        store.save_forecast(sample_forecast)

        forecast2 = {
            "timestamp": "2025-12-07T11:00:00Z",
            "data": [],
            "source": "test",
        }
        store.save_forecast(forecast2)

        latest = store.get_latest_forecast()
        assert latest is not None
        assert latest["timestamp"] == forecast2["timestamp"]

    def test_get_latest_forecast_empty(self, temp_data_dir):
        """Test getting latest forecast when none exist."""
        store = DataStore(data_dir=temp_data_dir)
        latest = store.get_latest_forecast()
        assert latest is None

    def test_get_forecasts(self, temp_data_dir, sample_forecast):
        """Test getting forecasts from last N days."""
        store = DataStore(data_dir=temp_data_dir)

        store.save_forecast(sample_forecast)

        forecasts = store.get_forecasts(days=7)
        assert len(forecasts) == 1

    def test_save_recommendation(self, temp_data_dir, sample_recommendation):
        """Test saving a recommendation."""
        store = DataStore(data_dir=temp_data_dir)
        store.save_recommendation(sample_recommendation)

        # Verify file was created
        assert store.RECOMMENDATIONS_FILE.exists()

        # Verify data was saved
        recs = store._load_json(store.RECOMMENDATIONS_FILE, default=[])
        assert len(recs) == 1
        assert recs[0]["date"] == sample_recommendation["date"]

    def test_save_recommendation_missing_date(self, temp_data_dir):
        """Test saving recommendation without date fails."""
        store = DataStore(data_dir=temp_data_dir)

        with pytest.raises(ValueError, match="must include 'date'"):
            store.save_recommendation({"rating": "GOOD"})

    def test_get_recommendations(self, temp_data_dir, sample_recommendation):
        """Test getting recommendations from last N days."""
        store = DataStore(data_dir=temp_data_dir)

        store.save_recommendation(sample_recommendation)

        recs = store.get_recommendations(days=30)
        assert len(recs) == 1

    def test_get_recommendation_by_date(self, temp_data_dir, sample_recommendation):
        """Test getting recommendation for specific date."""
        store = DataStore(data_dir=temp_data_dir)

        store.save_recommendation(sample_recommendation)

        rec = store.get_recommendation_by_date("2025-12-07")
        assert rec is not None
        assert rec["rating"] == "EXCELLENT"

    def test_get_recommendation_by_date_not_found(self, temp_data_dir):
        """Test getting recommendation for non-existent date."""
        store = DataStore(data_dir=temp_data_dir)

        rec = store.get_recommendation_by_date("2025-01-01")
        assert rec is None

    def test_save_user_action(self, temp_data_dir, sample_user_action):
        """Test saving a user action."""
        store = DataStore(data_dir=temp_data_dir)
        store.save_user_action(sample_user_action)

        # Verify file was created
        assert store.USER_ACTIONS_FILE.exists()

        # Verify data was saved
        actions = store._load_json(store.USER_ACTIONS_FILE, default=[])
        assert len(actions) == 1

    def test_save_user_action_auto_timestamp(self, temp_data_dir):
        """Test user action auto-adds timestamp if missing."""
        store = DataStore(data_dir=temp_data_dir)

        action = {"type": "charge", "notes": "test"}
        store.save_user_action(action)

        actions = store._load_json(store.USER_ACTIONS_FILE, default=[])
        assert "timestamp" in actions[0]

    def test_get_user_actions(self, temp_data_dir, sample_user_action):
        """Test getting user actions from last N days."""
        store = DataStore(data_dir=temp_data_dir)

        store.save_user_action(sample_user_action)

        actions = store.get_user_actions(days=90)
        assert len(actions) == 1

    def test_cleanup_old_data(self, temp_data_dir):
        """Test data cleanup with retention policies."""
        store = DataStore(data_dir=temp_data_dir)

        # Save old forecast (8 days ago)
        old_forecast = {
            "timestamp": "2025-12-01T00:00:00Z",
            "saved_at": (datetime.now() - timedelta(days=8)).isoformat(),
            "data": [],
            "source": "test",
        }

        # Save recent forecast (1 day ago)
        recent_forecast = {
            "timestamp": "2025-12-06T00:00:00Z",
            "saved_at": (datetime.now() - timedelta(days=1)).isoformat(),
            "data": [],
            "source": "test",
        }

        # Manually save to bypass validation
        store._save_json(store.FORECAST_FILE, [old_forecast, recent_forecast])

        # Run cleanup
        store.cleanup_old_data()

        # Verify old data was removed
        forecasts = store._load_json(store.FORECAST_FILE, default=[])
        assert len(forecasts) == 1
        assert forecasts[0]["timestamp"] == recent_forecast["timestamp"]

    def test_atomic_write_creates_backup(self, temp_data_dir):
        """Test that atomic write creates backup."""
        store = DataStore(data_dir=temp_data_dir)

        # Create initial file
        store._save_json(store.FORECAST_FILE, [{"test": "data1"}])

        # Update file
        store._save_json(store.FORECAST_FILE, [{"test": "data2"}])

        # Verify backup was created
        backup_file = store.FORECAST_FILE.with_suffix(".json.bak")
        assert backup_file.exists()

        # Verify backup contains old data
        backup_data = store._load_json(backup_file)
        assert backup_data[0]["test"] == "data1"

    def test_load_json_file_not_exists(self, temp_data_dir):
        """Test loading non-existent JSON file."""
        store = DataStore(data_dir=temp_data_dir)

        data = store._load_json(temp_data_dir / "missing.json", default=[])
        assert data == []

    def test_load_json_invalid_json(self, temp_data_dir):
        """Test loading invalid JSON file."""
        store = DataStore(data_dir=temp_data_dir)

        invalid_file = temp_data_dir / "invalid.json"
        invalid_file.write_text("not valid json {")

        data = store._load_json(invalid_file, default=[])
        assert data == []

    def test_save_json_io_error(self, temp_data_dir):
        """Test handling of IO error during save."""
        store = DataStore(data_dir=temp_data_dir)

        # Try to save to a read-only location (simulated)
        with pytest.raises(IOError):
            # Create a directory where file should be
            bad_file = temp_data_dir / "readonly"
            bad_file.mkdir()
            store._save_json(bad_file, {"test": "data"})

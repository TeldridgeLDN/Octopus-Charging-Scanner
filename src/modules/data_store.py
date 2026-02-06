"""Data Storage Layer

JSON-based persistence for forecasts, recommendations, and user actions.
Implements atomic writes and data retention policies.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json
import logging
import shutil

logger = logging.getLogger(__name__)


class DataStore:
    """JSON-based data persistence with atomic writes and retention policies.

    Manages three types of data:
    - Forecast history: 7-day rolling forecasts
    - Daily recommendations: 30-day archive
    - User actions: Manual charge logs
    """

    DATA_DIR = Path("data")
    FORECAST_FILE = DATA_DIR / "forecast_history.json"
    RECOMMENDATIONS_FILE = DATA_DIR / "daily_recommendations.json"
    USER_ACTIONS_FILE = DATA_DIR / "user_actions.json"

    FORECAST_RETENTION_DAYS = 7
    RECOMMENDATION_RETENTION_DAYS = 30
    USER_ACTION_RETENTION_DAYS = 90

    def __init__(self, data_dir: Optional[Path] = None):
        """Initialize data store.

        Args:
            data_dir: Optional custom data directory path
        """
        if data_dir:
            self.DATA_DIR = Path(data_dir)
            self.FORECAST_FILE = self.DATA_DIR / "forecast_history.json"
            self.RECOMMENDATIONS_FILE = self.DATA_DIR / "daily_recommendations.json"
            self.USER_ACTIONS_FILE = self.DATA_DIR / "user_actions.json"

        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Data store initialized at {self.DATA_DIR}")

    def save_forecast(self, forecast: Dict[str, Any]) -> None:
        """Save a forecast to history.

        Args:
            forecast: Forecast data with 'timestamp' and 'data' fields

        Raises:
            ValueError: If forecast missing required fields
        """
        if "timestamp" not in forecast:
            raise ValueError("Forecast must include 'timestamp' field")

        forecasts = self._load_json(self.FORECAST_FILE, default=[])

        # Add new forecast with metadata
        forecast_entry = {
            "timestamp": forecast["timestamp"],
            "saved_at": datetime.now().isoformat(),
            "data": forecast.get("data", []),
            "source": forecast.get("source", "unknown"),
        }

        forecasts.append(forecast_entry)
        logger.info(f"Saving forecast with {len(forecast.get('data', []))} entries")

        self._save_json(self.FORECAST_FILE, forecasts)

    def get_latest_forecast(self) -> Optional[Dict[str, Any]]:
        """Get the most recent forecast.

        Returns:
            Latest forecast or None if no forecasts exist
        """
        forecasts = self._load_json(self.FORECAST_FILE, default=[])

        if not forecasts:
            logger.info("No forecasts available")
            return None

        latest = max(forecasts, key=lambda x: x["saved_at"])
        logger.info(f"Retrieved latest forecast from {latest['saved_at']}")

        return latest

    def get_forecasts(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get forecasts from the last N days.

        Args:
            days: Number of days to retrieve (default: 7)

        Returns:
            List of forecasts within the time window
        """
        forecasts = self._load_json(self.FORECAST_FILE, default=[])

        cutoff = datetime.now() - timedelta(days=days)
        recent_forecasts = [
            f for f in forecasts if datetime.fromisoformat(f["saved_at"]) >= cutoff
        ]

        logger.info(
            f"Retrieved {len(recent_forecasts)} forecasts from last {days} days"
        )
        return recent_forecasts

    def save_recommendation(self, recommendation: Dict[str, Any]) -> None:
        """Save a daily recommendation.

        Args:
            recommendation: Recommendation data with 'date' field

        Raises:
            ValueError: If recommendation missing required fields
        """
        if "date" not in recommendation:
            raise ValueError("Recommendation must include 'date' field")

        recommendations = self._load_json(self.RECOMMENDATIONS_FILE, default=[])

        # Add metadata
        rec_entry = {
            **recommendation,
            "saved_at": datetime.now().isoformat(),
        }

        recommendations.append(rec_entry)
        logger.info(f"Saving recommendation for {recommendation['date']}")

        self._save_json(self.RECOMMENDATIONS_FILE, recommendations)

    def get_recommendations(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get recommendations from the last N days.

        Args:
            days: Number of days to retrieve (default: 30)

        Returns:
            List of recommendations within the time window
        """
        recommendations = self._load_json(self.RECOMMENDATIONS_FILE, default=[])

        cutoff = datetime.now() - timedelta(days=days)
        recent_recs = [
            r
            for r in recommendations
            if datetime.fromisoformat(r["saved_at"]) >= cutoff
        ]

        logger.info(
            f"Retrieved {len(recent_recs)} recommendations from last {days} days"
        )
        return recent_recs

    def get_recommendation_by_date(self, date: str) -> Optional[Dict[str, Any]]:
        """Get recommendation for a specific date.

        Args:
            date: Date string in ISO format (YYYY-MM-DD)

        Returns:
            Recommendation for the date or None if not found
        """
        recommendations = self._load_json(self.RECOMMENDATIONS_FILE, default=[])

        for rec in reversed(recommendations):  # Get most recent for date
            if rec.get("date") == date:
                logger.info(f"Found recommendation for {date}")
                return rec

        logger.info(f"No recommendation found for {date}")
        return None

    def save_user_action(self, action: Dict[str, Any]) -> None:
        """Save a user action (manual charge log).

        Args:
            action: Action data with 'timestamp' field

        Raises:
            ValueError: If action missing required fields
        """
        if "timestamp" not in action:
            action["timestamp"] = datetime.now().isoformat()

        actions = self._load_json(self.USER_ACTIONS_FILE, default=[])

        action_entry = {
            **action,
            "logged_at": datetime.now().isoformat(),
        }

        actions.append(action_entry)
        logger.info(f"Saving user action: {action.get('type', 'unknown')}")

        self._save_json(self.USER_ACTIONS_FILE, actions)

    def get_user_actions(self, days: int = 90) -> List[Dict[str, Any]]:
        """Get user actions from the last N days.

        Args:
            days: Number of days to retrieve (default: 90)

        Returns:
            List of user actions within the time window
        """
        actions = self._load_json(self.USER_ACTIONS_FILE, default=[])

        cutoff = datetime.now() - timedelta(days=days)
        recent_actions = [
            a for a in actions if datetime.fromisoformat(a["logged_at"]) >= cutoff
        ]

        logger.info(
            f"Retrieved {len(recent_actions)} user actions from last {days} days"
        )
        return recent_actions

    def cleanup_old_data(self) -> None:
        """Apply retention policies to all data files.

        Removes data older than:
        - 7 days for forecasts
        - 30 days for recommendations
        - 90 days for user actions
        """
        logger.info("Starting data cleanup")

        # Clean forecasts
        forecasts = self._load_json(self.FORECAST_FILE, default=[])
        forecast_cutoff = datetime.now() - timedelta(days=self.FORECAST_RETENTION_DAYS)
        new_forecasts = [
            f
            for f in forecasts
            if datetime.fromisoformat(f["saved_at"]) >= forecast_cutoff
        ]
        removed_forecasts = len(forecasts) - len(new_forecasts)
        if removed_forecasts > 0:
            self._save_json(self.FORECAST_FILE, new_forecasts)
            logger.info(f"Removed {removed_forecasts} old forecasts")

        # Clean recommendations
        recommendations = self._load_json(self.RECOMMENDATIONS_FILE, default=[])
        rec_cutoff = datetime.now() - timedelta(days=self.RECOMMENDATION_RETENTION_DAYS)
        new_recs = [
            r
            for r in recommendations
            if datetime.fromisoformat(r["saved_at"]) >= rec_cutoff
        ]
        removed_recs = len(recommendations) - len(new_recs)
        if removed_recs > 0:
            self._save_json(self.RECOMMENDATIONS_FILE, new_recs)
            logger.info(f"Removed {removed_recs} old recommendations")

        # Clean user actions
        actions = self._load_json(self.USER_ACTIONS_FILE, default=[])
        action_cutoff = datetime.now() - timedelta(days=self.USER_ACTION_RETENTION_DAYS)
        new_actions = [
            a
            for a in actions
            if datetime.fromisoformat(a["logged_at"]) >= action_cutoff
        ]
        removed_actions = len(actions) - len(new_actions)
        if removed_actions > 0:
            self._save_json(self.USER_ACTIONS_FILE, new_actions)
            logger.info(f"Removed {removed_actions} old user actions")

        logger.info("Data cleanup complete")

    def _load_json(self, file_path: Path, default: Any = None) -> Any:
        """Load JSON data from file with error handling.

        Args:
            file_path: Path to JSON file
            default: Default value if file doesn't exist or is invalid

        Returns:
            Loaded data or default value
        """
        if not file_path.exists():
            logger.debug(f"File {file_path} does not exist, using default")
            return default

        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                logger.debug(f"Loaded {file_path}")
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load {file_path}: {e}, using default")
            return default

    def _save_json(self, file_path: Path, data: Any) -> None:
        """Save JSON data with atomic write.

        Args:
            file_path: Path to JSON file
            data: Data to save

        Raises:
            IOError: If save fails
        """
        # Backup existing file
        if file_path.exists():
            backup_path = file_path.with_suffix(".json.bak")
            shutil.copy2(file_path, backup_path)
            logger.debug(f"Created backup: {backup_path}")

        # Write to temporary file first
        temp_path = file_path.with_suffix(".json.tmp")

        try:
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2, default=str)

            # Atomic rename
            temp_path.replace(file_path)
            logger.debug(f"Saved {file_path}")

        except IOError as e:
            logger.error(f"Failed to save {file_path}: {e}")
            if temp_path.exists():
                temp_path.unlink()
            raise

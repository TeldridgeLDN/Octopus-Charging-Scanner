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

    Manages data types:
    - Forecast history: 7-day rolling forecasts
    - Daily recommendations: 30-day archive
    - User actions: Manual charge logs
    - ACIX usage data: Raw consumption data
    - ACIX events: Detected EV charging events
    - ACIX sessions: Aggregated charging sessions
    - ACIX metrics: Behavioral metrics
    """

    DATA_DIR = Path(__file__).resolve().parents[2] / "data"
    FORECAST_FILE = DATA_DIR / "forecast_history.json"
    RECOMMENDATIONS_FILE = DATA_DIR / "daily_recommendations.json"
    USER_ACTIONS_FILE = DATA_DIR / "user_actions.json"
    EVOLUTION_FILE = DATA_DIR / "forecast_evolution.json"

    # ACIX data files
    USAGE_FILE = DATA_DIR / "usage_raw.json"
    EVENTS_FILE = DATA_DIR / "events.json"
    SESSIONS_FILE = DATA_DIR / "sessions.json"
    BEHAVIOUR_METRICS_FILE = DATA_DIR / "behaviour_metrics.json"

    FORECAST_RETENTION_DAYS = 7
    RECOMMENDATION_RETENTION_DAYS = 30
    USER_ACTION_RETENTION_DAYS = 90
    EVOLUTION_RETENTION_DAYS = 30

    # ACIX retention defaults (can be overridden by config)
    USAGE_RETENTION_DAYS = 30
    EVENTS_RETENTION_DAYS = 90
    SESSIONS_RETENTION_DAYS = 90

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
            self.EVOLUTION_FILE = self.DATA_DIR / "forecast_evolution.json"
            # ACIX files
            self.USAGE_FILE = self.DATA_DIR / "usage_raw.json"
            self.EVENTS_FILE = self.DATA_DIR / "events.json"
            self.SESSIONS_FILE = self.DATA_DIR / "sessions.json"
            self.BEHAVIOUR_METRICS_FILE = self.DATA_DIR / "behaviour_metrics.json"

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

        # Clean forecast evolution
        removed_evolution = self._cleanup_forecast_evolution()
        if removed_evolution > 0:
            logger.info(f"Removed {removed_evolution} old forecast evolution entries")

        logger.info("Data cleanup complete")

    def _cleanup_forecast_evolution(self) -> int:
        """Clean up old forecast evolution data.

        Removes evolution entries for target dates older than retention period.

        Returns:
            Number of entries removed
        """
        if not self.EVOLUTION_FILE.exists():
            return 0

        try:
            with open(self.EVOLUTION_FILE, "r") as f:
                evolution_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return 0

        if "target_forecasts" not in evolution_data:
            return 0

        cutoff = datetime.now() - timedelta(days=self.EVOLUTION_RETENTION_DAYS)
        original_count = len(evolution_data["target_forecasts"])

        # Remove old entries (target dates that have passed beyond retention)
        evolution_data["target_forecasts"] = {
            target_date: data
            for target_date, data in evolution_data["target_forecasts"].items()
            if datetime.strptime(target_date, "%Y-%m-%d") >= cutoff
        }

        removed = original_count - len(evolution_data["target_forecasts"])

        if removed > 0:
            evolution_data["metadata"]["last_cleanup"] = datetime.now().isoformat()
            self._save_json(self.EVOLUTION_FILE, evolution_data)

        return removed

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

    # ========== ACIX Usage Data Methods ==========

    def save_usage(self, usage_records: List[Dict[str, Any]]) -> int:
        """Save consumption records, merging with existing data.

        Deduplicates by interval_start timestamp.

        Args:
            usage_records: List of consumption records with interval_start

        Returns:
            Number of new records added
        """
        existing = self._load_json(self.USAGE_FILE, default=[])

        # Create set of existing timestamps for deduplication
        existing_timestamps = {r["interval_start"] for r in existing}

        # Add only new records
        new_records = [
            r for r in usage_records if r["interval_start"] not in existing_timestamps
        ]

        if new_records:
            combined = existing + new_records
            # Sort by timestamp
            combined.sort(key=lambda x: x["interval_start"])
            self._save_json(self.USAGE_FILE, combined)
            logger.info(f"Added {len(new_records)} new usage records")

        return len(new_records)

    def get_usage(
        self, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get usage records within a time range.

        Args:
            start: Start datetime (default: 48 hours ago)
            end: End datetime (default: now)

        Returns:
            List of usage records in the range
        """
        usage = self._load_json(self.USAGE_FILE, default=[])

        if not start and not end:
            return usage

        if end is None:
            end = datetime.now()
        if start is None:
            start = end - timedelta(hours=48)

        # Filter by time range
        filtered = []
        for record in usage:
            try:
                record_time = datetime.fromisoformat(
                    record["interval_start"].replace("Z", "+00:00")
                )
                # Make naive if comparing with naive datetime
                if start.tzinfo is None:
                    record_time = record_time.replace(tzinfo=None)
                if start <= record_time <= end:
                    filtered.append(record)
            except (ValueError, KeyError):
                continue

        logger.info(f"Retrieved {len(filtered)} usage records")
        return filtered

    def get_latest_usage_timestamp(self) -> Optional[datetime]:
        """Get the timestamp of the most recent usage record.

        Returns:
            Datetime of latest record or None if no data
        """
        usage = self._load_json(self.USAGE_FILE, default=[])

        if not usage:
            return None

        try:
            latest = max(usage, key=lambda x: x["interval_start"])
            return datetime.fromisoformat(
                latest["interval_start"].replace("Z", "+00:00")
            )
        except (ValueError, KeyError):
            return None

    def cleanup_usage(self, retention_days: int = 30) -> int:
        """Remove usage records older than retention period.

        Args:
            retention_days: Days to retain data

        Returns:
            Number of records removed
        """
        usage = self._load_json(self.USAGE_FILE, default=[])
        if not usage:
            return 0

        cutoff_iso = (datetime.now() - timedelta(days=retention_days)).isoformat()

        original_count = len(usage)
        usage = [r for r in usage if r["interval_start"] >= cutoff_iso]

        removed = original_count - len(usage)
        if removed > 0:
            self._save_json(self.USAGE_FILE, usage)
            logger.info(f"Removed {removed} old usage records")

        return removed

    # ========== ACIX Events Methods ==========

    def save_event(self, event: Dict[str, Any]) -> None:
        """Save a detected EV charging event.

        Args:
            event: Event data with timestamp, type, and details
        """
        events = self._load_json(self.EVENTS_FILE, default=[])

        event_entry = {
            **event,
            "saved_at": datetime.now().isoformat(),
        }

        events.append(event_entry)
        self._save_json(self.EVENTS_FILE, events)
        logger.info(f"Saved event: {event.get('event', 'unknown')}")

    def get_events(self, days: int = 90) -> List[Dict[str, Any]]:
        """Get events from the last N days.

        Args:
            days: Number of days to retrieve

        Returns:
            List of events
        """
        events = self._load_json(self.EVENTS_FILE, default=[])

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        recent = [e for e in events if e.get("saved_at", "") >= cutoff]

        logger.info(f"Retrieved {len(recent)} events from last {days} days")
        return recent

    # ========== ACIX Sessions Methods ==========

    def save_session(self, session: Dict[str, Any]) -> None:
        """Save an aggregated charging session.

        Args:
            session: Session data with date, times, and metrics
        """
        sessions = self._load_json(self.SESSIONS_FILE, default=[])

        session_entry = {
            **session,
            "saved_at": datetime.now().isoformat(),
        }

        sessions.append(session_entry)
        self._save_json(self.SESSIONS_FILE, sessions)
        logger.info(f"Saved session for {session.get('date', 'unknown date')}")

    def get_sessions(self, days: int = 90) -> List[Dict[str, Any]]:
        """Get sessions from the last N days.

        Args:
            days: Number of days to retrieve

        Returns:
            List of sessions
        """
        sessions = self._load_json(self.SESSIONS_FILE, default=[])

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        recent = [s for s in sessions if s.get("saved_at", "") >= cutoff]

        logger.info(f"Retrieved {len(recent)} sessions from last {days} days")
        return recent

    def get_session_by_date(self, date: str) -> Optional[Dict[str, Any]]:
        """Get session for a specific date.

        Args:
            date: Date string in ISO format (YYYY-MM-DD)

        Returns:
            Session for the date or None if not found
        """
        sessions = self._load_json(self.SESSIONS_FILE, default=[])

        for session in reversed(sessions):
            if session.get("date") == date:
                return session

        return None

    # ========== ACIX Behaviour Metrics Methods ==========

    def save_behaviour_metrics(self, metrics: Dict[str, Any]) -> None:
        """Save behaviour metrics snapshot.

        Args:
            metrics: Metrics data with efficiency scores, patterns, etc.
        """
        metrics_entry = {
            **metrics,
            "saved_at": datetime.now().isoformat(),
        }

        self._save_json(self.BEHAVIOUR_METRICS_FILE, metrics_entry)
        logger.info("Saved behaviour metrics")

    def get_behaviour_metrics(self) -> Optional[Dict[str, Any]]:
        """Get the latest behaviour metrics.

        Returns:
            Latest metrics or None if not available
        """
        return self._load_json(self.BEHAVIOUR_METRICS_FILE, default=None)

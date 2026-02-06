"""Pushover Notification Client

Sends push notifications via Pushover API with support for priorities,
HTML formatting, image attachments, and rate limiting.
"""

from typing import Optional
import os
import logging
import requests
import json
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class PushoverClient:
    """Send push notifications via Pushover API.

    Supports priority levels, HTML formatting, image attachments,
    and automatic rate limiting.
    """

    API_URL = "https://api.pushover.net/1/messages.json"
    MAX_MESSAGE_LENGTH = 1024
    RATE_LIMIT_FILE = "data/pushover_rate_limit.json"
    MAX_DAILY_NOTIFICATIONS = 5

    def __init__(self, user_key: Optional[str] = None, api_token: Optional[str] = None):
        """Initialize Pushover client.

        Args:
            user_key: Pushover user key (or set PUSHOVER_USER_KEY env var)
            api_token: Pushover API token (or set PUSHOVER_API_TOKEN env var)

        Raises:
            ValueError: If credentials are not provided
        """
        self.user_key = user_key or os.getenv("PUSHOVER_USER_KEY")
        self.api_token = api_token or os.getenv("PUSHOVER_API_TOKEN")

        if not self.user_key or not self.api_token:
            raise ValueError(
                "Pushover credentials required. Set PUSHOVER_USER_KEY and "
                "PUSHOVER_API_TOKEN environment variables or pass to constructor."
            )

        logger.info("Pushover client initialized")

    def send_notification(
        self,
        title: str,
        message: str,
        priority: int = 0,
        sound: str = "pushover",
        html: bool = True,
        attachment: Optional[str] = None,
    ) -> bool:
        """Send a Pushover notification.

        Args:
            title: Notification title
            message: Notification message (max 1024 chars)
            priority: Priority level (-2=lowest, -1=low, 0=normal, 1=high, 2=emergency)
            sound: Notification sound (pushover, cosmic, cashregister, etc.)
            html: Enable HTML formatting in message
            attachment: Path to image file to attach (optional)

        Returns:
            True if notification sent successfully, False otherwise

        Raises:
            ValueError: If message exceeds length limit or priority invalid
        """
        # Validate inputs
        if len(message) > self.MAX_MESSAGE_LENGTH:
            raise ValueError(
                f"Message exceeds {self.MAX_MESSAGE_LENGTH} character limit"
            )

        if priority not in [-2, -1, 0, 1, 2]:
            raise ValueError("Priority must be between -2 and 2")

        # Check rate limit
        if not self._check_rate_limit():
            logger.warning(
                f"Rate limit exceeded: {self.MAX_DAILY_NOTIFICATIONS}/day maximum"
            )
            return False

        # Prepare payload
        payload = {
            "token": self.api_token,
            "user": self.user_key,
            "title": title,
            "message": message,
            "priority": priority,
            "sound": sound,
        }

        if html:
            payload["html"] = 1

        files = None
        if attachment and os.path.exists(attachment):
            try:
                files = {"attachment": open(attachment, "rb")}
                logger.info(f"Attaching file: {attachment}")
            except Exception as e:
                logger.error(f"Failed to attach file {attachment}: {e}")
                return False

        try:
            logger.info(f"Sending Pushover notification: {title}")
            response = requests.post(
                self.API_URL, data=payload, files=files, timeout=10
            )

            if files:
                files["attachment"].close()

            response.raise_for_status()
            result = response.json()

            if result.get("status") == 1:
                logger.info("Notification sent successfully")
                self._record_notification()
                return True
            else:
                logger.error(f"Pushover API error: {result}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limit.

        Returns:
            True if notification can be sent, False if rate limit exceeded
        """
        rate_data = self._load_rate_data()
        today = datetime.now().date().isoformat()

        # Clean up old dates
        rate_data = {
            date: count
            for date, count in rate_data.items()
            if datetime.fromisoformat(date).date()
            >= (datetime.now().date() - timedelta(days=1))
        }

        today_count = rate_data.get(today, 0)

        if today_count >= self.MAX_DAILY_NOTIFICATIONS:
            logger.warning(
                f"Rate limit check failed: {today_count} notifications today"
            )
            return False

        logger.debug(
            f"Rate limit check passed: {today_count}/{self.MAX_DAILY_NOTIFICATIONS}"
        )
        return True

    def _record_notification(self) -> None:
        """Record a sent notification for rate limiting."""
        rate_data = self._load_rate_data()
        today = datetime.now().date().isoformat()

        rate_data[today] = rate_data.get(today, 0) + 1

        self._save_rate_data(rate_data)
        logger.debug(f"Recorded notification: {rate_data[today]} sent today")

    def _load_rate_data(self) -> dict:
        """Load rate limit data from file.

        Returns:
            Dictionary mapping dates to notification counts
        """
        rate_file = Path(self.RATE_LIMIT_FILE)

        if not rate_file.exists():
            logger.debug("Rate limit file does not exist, creating new")
            rate_file.parent.mkdir(parents=True, exist_ok=True)
            return {}

        try:
            with open(rate_file, "r") as f:
                data = json.load(f)
                logger.debug(f"Loaded rate data: {data}")
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load rate data: {e}, using empty data")
            return {}

    def _save_rate_data(self, data: dict) -> None:
        """Save rate limit data to file.

        Args:
            data: Dictionary mapping dates to notification counts
        """
        rate_file = Path(self.RATE_LIMIT_FILE)
        rate_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(rate_file, "w") as f:
                json.dump(data, f, indent=2)
                logger.debug(f"Saved rate data: {data}")
        except IOError as e:
            logger.error(f"Failed to save rate data: {e}")

    def get_today_notification_count(self) -> int:
        """Get the number of notifications sent today.

        Returns:
            Count of notifications sent today
        """
        rate_data = self._load_rate_data()
        today = datetime.now().date().isoformat()
        count = rate_data.get(today, 0)

        logger.info(f"Notifications sent today: {count}/{self.MAX_DAILY_NOTIFICATIONS}")
        return count

    def reset_rate_limit(self) -> None:
        """Reset rate limit counter (for testing purposes)."""
        rate_file = Path(self.RATE_LIMIT_FILE)

        if rate_file.exists():
            rate_file.unlink()
            logger.info("Rate limit data reset")
        else:
            logger.info("No rate limit data to reset")

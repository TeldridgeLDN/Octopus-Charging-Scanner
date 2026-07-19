"""Google Calendar Integration

Publishes EV charging recommendations as calendar events
for easy sharing between household members.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """Represents an EV charging calendar event."""

    title: str
    start: datetime
    end: datetime
    description: str
    color_id: str
    event_id: Optional[str] = None


class GoogleCalendarClient:
    """Client for publishing charging windows to Google Calendar.

    Uses a service account for server-side automation without
    requiring user interaction or browser-based OAuth flows.
    """

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    # Google Calendar color IDs mapped to ratings
    # See: https://developers.google.com/calendar/api/v3/reference/colors
    RATING_COLORS = {
        "EXCELLENT": "10",  # Green (Basil)
        "GOOD": "9",  # Blue (Blueberry)
        "AVERAGE": "5",  # Yellow (Banana)
        "POOR": "11",  # Red (Tomato)
    }

    # Event ID prefix for identifying our events
    EVENT_PREFIX = "evcharger"

    def __init__(self, credentials_path: str, calendar_id: str):
        """Initialize with service account credentials.

        Args:
            credentials_path: Path to service account JSON file
            calendar_id: Google Calendar ID to publish to
        """
        self.calendar_id = calendar_id
        self.credentials_path = Path(credentials_path)

        if not self.credentials_path.exists():
            raise FileNotFoundError(f"Google credentials not found: {credentials_path}")

        self.service = self._build_service()
        logger.info(f"Google Calendar client initialized for {calendar_id}")

    def _build_service(self):
        """Build the Google Calendar API service."""
        credentials = service_account.Credentials.from_service_account_file(
            str(self.credentials_path), scopes=self.SCOPES
        )
        return build("calendar", "v3", credentials=credentials)

    def _generate_event_id(self, date: str, event_type: str = "window") -> str:
        """Generate a deterministic event ID for idempotent updates.

        Args:
            date: Date string in YYYY-MM-DD format
            event_type: Type of event (window, bestday)

        Returns:
            Event ID string (lowercase alphanumeric, 5-1024 chars)
        """
        # Google requires lowercase alphanumeric, 5-1024 characters
        date_clean = date.replace("-", "")
        return f"{self.EVENT_PREFIX}{event_type}{date_clean}"

    def create_charging_event(
        self,
        start: datetime,
        end: datetime,
        rating: str,
        avg_price: float,
        total_cost: float,
        kwh: float,
        avg_carbon: int,
        savings: float = 0.0,
        reason: str = "",
        price_source: str = "unknown",
        reminders: Optional[List[int]] = None,
    ) -> str:
        """Create a calendar event for a charging window.

        Args:
            start: Window start time
            end: Window end time
            rating: OpportunityRating value (EXCELLENT, GOOD, etc.)
            avg_price: Average price in p/kWh
            total_cost: Total cost in GBP
            kwh: Charge amount in kWh
            avg_carbon: Average carbon intensity in gCO2/kWh
            savings: Savings vs baseline in GBP
            reason: Reason for recommendation (cheap, clean, both)
            price_source: Data source (octopus_actual, forecast)
            reminders: List of reminder times in minutes before event

        Returns:
            Created event ID
        """
        date_str = start.date().isoformat()
        event_id = self._generate_event_id(date_str, "window")

        # Build title with key info
        title = f"⚡ EV Charging: {rating} ({avg_price:.1f}p/kWh)"

        # Build description
        description = self._format_event_description(
            rating=rating,
            avg_price=avg_price,
            total_cost=total_cost,
            kwh=kwh,
            avg_carbon=avg_carbon,
            savings=savings,
            reason=reason,
            price_source=price_source,
        )

        # Get color for rating
        color_id = self.RATING_COLORS.get(rating, "9")

        # Build event body
        event = {
            "id": event_id,
            "summary": title,
            "description": description,
            "start": {
                "dateTime": start.isoformat(),
                "timeZone": "Europe/London",
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": "Europe/London",
            },
            "colorId": color_id,
        }

        # Add reminders if specified
        if reminders:
            event["reminders"] = {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": mins} for mins in reminders
                ],
            }

        return self._upsert_event(event)

    def create_best_day_event(
        self,
        date: str,
        day_name: str,
        savings: float,
        percentage: float,
        optimal_start: datetime,
        optimal_end: datetime,
    ) -> str:
        """Create an all-day event highlighting the best day to charge.

        Args:
            date: Date string in YYYY-MM-DD format
            day_name: Human-readable day name (Today, Tomorrow, etc.)
            savings: Savings vs today in GBP
            percentage: Percentage cheaper than today
            optimal_start: Best window start time
            optimal_end: Best window end time

        Returns:
            Created event ID
        """
        event_id = self._generate_event_id(date, "bestday")

        title = f"💰 BEST DAY: {day_name} ({percentage:.0f}% cheaper)"

        window_str = (
            f"{optimal_start.strftime('%H:%M')} - {optimal_end.strftime('%H:%M')}"
        )

        description = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 BEST DAY TO CHARGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{day_name} has the cheapest prices this week!

💵 Save: £{savings:.2f} compared to today
📉 {percentage:.0f}% cheaper than today

⚡ Optimal Window: {window_str}

Consider waiting until {day_name} if you
don't need to charge urgently.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generated by EV Charging Optimizer
"""

        event = {
            "id": event_id,
            "summary": title,
            "description": description,
            "start": {"date": date},
            "end": {"date": date},
            "colorId": self.RATING_COLORS["EXCELLENT"],
        }

        return self._upsert_event(event)

    def create_multi_day_events(
        self,
        days: List[Dict[str, Any]],
        kwh: float,
        best_day: Dict[str, Any],
        reminders: Optional[List[int]] = None,
    ) -> List[str]:
        """Create events for all days in a multi-day plan.

        Args:
            days: List of day comparison dicts from MultiDayPlan
            kwh: Charge amount in kWh
            best_day: Best day info dict
            reminders: Reminder times in minutes

        Returns:
            List of created event IDs
        """
        event_ids = []

        for day in days:
            # Parse window times
            start = datetime.fromisoformat(day["optimal_window"]["start"])
            end = datetime.fromisoformat(day["optimal_window"]["end"])

            event_id = self.create_charging_event(
                start=start,
                end=end,
                rating=day["rating"],
                avg_price=day["avg_price"],
                total_cost=day["cost"],
                kwh=kwh,
                avg_carbon=day["avg_carbon"],
                savings=day.get("savings_vs_today", 0),
                reason="",
                price_source=day["price_source"],
                reminders=reminders,
            )
            event_ids.append(event_id)

        # Create best day event if it's not today
        if best_day.get("date") != days[0].get("date"):
            # Find the best day's window times
            best_day_data = next(
                (d for d in days if d["date"] == best_day["date"]), None
            )
            if best_day_data:
                best_start = datetime.fromisoformat(
                    best_day_data["optimal_window"]["start"]
                )
                best_end = datetime.fromisoformat(
                    best_day_data["optimal_window"]["end"]
                )

                best_event_id = self.create_best_day_event(
                    date=best_day["date"],
                    day_name=best_day["day_name"],
                    savings=best_day["savings"],
                    percentage=best_day["percentage"],
                    optimal_start=best_start,
                    optimal_end=best_end,
                )
                event_ids.append(best_event_id)

        logger.info(f"Created {len(event_ids)} calendar events")
        return event_ids

    def delete_old_events(self, before_date: datetime) -> int:
        """Delete past charging events older than specified date.

        Args:
            before_date: Delete events before this date

        Returns:
            Number of events deleted
        """
        deleted = 0

        try:
            # List events with our prefix
            events_result = (
                self.service.events()
                .list(
                    calendarId=self.calendar_id,
                    timeMax=before_date.isoformat(),
                    singleEvents=True,
                    maxResults=100,
                )
                .execute()
            )

            events = events_result.get("items", [])

            for event in events:
                event_id = event.get("id", "")
                # Only delete our events (identified by prefix)
                if event_id.startswith(self.EVENT_PREFIX):
                    try:
                        self.service.events().delete(
                            calendarId=self.calendar_id, eventId=event_id
                        ).execute()
                        deleted += 1
                        logger.debug(f"Deleted event: {event_id}")
                    except HttpError as e:
                        logger.warning(f"Failed to delete event {event_id}: {e}")

            logger.info(f"Deleted {deleted} old calendar events")

        except HttpError as e:
            logger.error(f"Failed to list events for cleanup: {e}")

        return deleted

    def test_connection(self) -> bool:
        """Test the calendar connection.

        Returns:
            True if connection successful
        """
        try:
            calendar = (
                self.service.calendars().get(calendarId=self.calendar_id).execute()
            )
            logger.info(f"Connected to calendar: {calendar.get('summary')}")
            return True
        except HttpError as e:
            logger.error(f"Failed to connect to calendar: {e}")
            return False

    def _upsert_event(self, event: Dict[str, Any]) -> str:
        """Insert or update an event (idempotent).

        Args:
            event: Event data dict

        Returns:
            Event ID
        """
        event_id = event.get("id")

        try:
            # Try to update existing event
            result = (
                self.service.events()
                .update(calendarId=self.calendar_id, eventId=event_id, body=event)
                .execute()
            )
            logger.debug(f"Updated event: {event_id}")
            return result["id"]

        except HttpError as e:
            if e.resp.status == 404:
                # Event doesn't exist, create it
                result = (
                    self.service.events()
                    .insert(calendarId=self.calendar_id, body=event)
                    .execute()
                )
                logger.debug(f"Created event: {event_id}")
                return result["id"]
            else:
                logger.error(f"Failed to upsert event {event_id}: {e}")
                raise

    def _format_event_description(
        self,
        rating: str,
        avg_price: float,
        total_cost: float,
        kwh: float,
        avg_carbon: int,
        savings: float,
        reason: str,
        price_source: str,
    ) -> str:
        """Format the event description with charging details.

        Args:
            rating: OpportunityRating value
            avg_price: Average price in p/kWh
            total_cost: Total cost in GBP
            kwh: Charge amount in kWh
            avg_carbon: Carbon intensity in gCO2/kWh
            savings: Savings vs baseline in GBP
            reason: Recommendation reason
            price_source: Data source

        Returns:
            Formatted description string
        """
        # Carbon assessment
        if avg_carbon <= 100:
            carbon_note = "(very clean)"
        elif avg_carbon <= 150:
            carbon_note = "(clean)"
        else:
            carbon_note = ""

        # Reason mapping
        reason_text = {
            "both": "Both cheap AND clean",
            "cheap": "Cheap electricity",
            "clean": "Clean energy",
            "neither": "Limited options",
        }.get(reason, reason)

        # Data source indicator
        if price_source == "octopus_actual":
            source_text = "Actual Octopus prices ✓"
        else:
            source_text = "Forecast prices (predicted)"

        # Build description
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "⚡ EV CHARGING WINDOW",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"Rating: {rating}",
            f"Cost: £{total_cost:.2f} for {kwh:.0f}kWh",
            f"Avg Price: {avg_price:.1f}p/kWh",
            f"Carbon: {avg_carbon} gCO2/kWh {carbon_note}",
        ]

        if savings > 0:
            lines.append("")
            lines.append(f"💰 Save £{savings:.2f} vs evening charging")

        if reason_text:
            lines.append("")
            lines.append(f"Why: {reason_text}")

        lines.extend(
            [
                "",
                f"Data: {source_text}",
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "Generated by EV Charging Optimizer",
            ]
        )

        return "\n".join(lines)

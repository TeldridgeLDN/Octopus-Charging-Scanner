"""Automation Triggers for Smart Plug Integration

Generates automation events based on ACIX analysis that can be consumed
by smart home systems (Home Assistant, IFTTT, webhooks, etc.).

Part of the ACIX (Adaptive Charging Intelligence Extension) system.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from enum import Enum
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Types of automation triggers."""

    OPTIMAL_WINDOW_START = "optimal_window_start"
    OPTIMAL_WINDOW_END = "optimal_window_end"
    PLUG_IN_REMINDER = "plug_in_reminder"
    CHEAP_RATE_ALERT = "cheap_rate_alert"
    NEGATIVE_PRICING = "negative_pricing"
    CHARGING_COMPLETE = "charging_complete"
    PATTERN_ALERT = "pattern_alert"


class TriggerPriority(Enum):
    """Priority levels for triggers."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class AutomationTrigger:
    """A single automation trigger event."""

    trigger_type: TriggerType
    timestamp: datetime
    priority: TriggerPriority
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    expires_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/webhook payload."""
        return {
            "trigger_type": self.trigger_type.value,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority.value,
            "priority_name": self.priority.name,
            "data": self.data,
            "message": self.message,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class AutomationSchedule:
    """Schedule of upcoming automation triggers."""

    generated_at: datetime
    triggers: List[AutomationTrigger] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "trigger_count": len(self.triggers),
            "triggers": [t.to_dict() for t in self.triggers],
        }


class AutomationManager:
    """Manages automation triggers for smart plug integration.

    Generates triggers based on:
    - Optimal charging windows from recommendations
    - ACIX behavioral patterns
    - Price alerts and negative pricing events
    """

    TRIGGERS_FILE = Path("data/automation_triggers.json")

    def __init__(
        self,
        data_store: Any,
        config: Dict[str, Any],
    ):
        """Initialize automation manager.

        Args:
            data_store: DataStore instance
            config: Configuration dictionary
        """
        self.data_store = data_store
        self.config = config
        self.typical_kwh = config.get("user", {}).get("typical_charge_kwh", 20)
        self.charge_rate_kw = config.get("user", {}).get("charging_rate_kw", 2.3)

        # Calculate typical charge duration
        self.charge_duration_hours = self.typical_kwh / self.charge_rate_kw

        logger.info(
            f"AutomationManager initialized: {self.typical_kwh}kWh @ {self.charge_rate_kw}kW"
        )

    def generate_schedule(
        self,
        recommendation: Optional[Dict[str, Any]] = None,
        include_reminders: bool = True,
    ) -> AutomationSchedule:
        """Generate automation schedule based on current recommendation.

        Args:
            recommendation: Today's recommendation (fetches latest if None)
            include_reminders: Whether to include plug-in reminders

        Returns:
            AutomationSchedule with triggers
        """
        now = datetime.now(timezone.utc)
        triggers = []

        # Get recommendation if not provided
        if recommendation is None:
            today = now.date().isoformat()
            recommendation = self.data_store.get_recommendation_by_date(today)

        if recommendation:
            # Generate window triggers
            window_triggers = self._generate_window_triggers(recommendation, now)
            triggers.extend(window_triggers)

            # Generate plug-in reminder
            if include_reminders:
                reminder = self._generate_plug_in_reminder(recommendation, now)
                if reminder:
                    triggers.append(reminder)

            # Check for negative pricing
            if recommendation.get("avg_price", 100) < 0:
                neg_trigger = self._generate_negative_pricing_trigger(
                    recommendation, now
                )
                triggers.append(neg_trigger)

        # Generate pattern-based triggers from ACIX
        pattern_triggers = self._generate_pattern_triggers(now)
        triggers.extend(pattern_triggers)

        # Sort by timestamp
        triggers.sort(key=lambda t: t.timestamp)

        schedule = AutomationSchedule(
            generated_at=now,
            triggers=triggers,
        )

        # Save to file
        self._save_schedule(schedule)

        logger.info(f"Generated {len(triggers)} automation triggers")
        return schedule

    def _generate_window_triggers(
        self,
        recommendation: Dict[str, Any],
        now: datetime,
    ) -> List[AutomationTrigger]:
        """Generate triggers for optimal charging window.

        Args:
            recommendation: Recommendation data
            now: Current time

        Returns:
            List of window-related triggers
        """
        triggers = []

        window_start = datetime.fromisoformat(
            recommendation["window_start"].replace("Z", "+00:00")
        )
        window_end = datetime.fromisoformat(
            recommendation["window_end"].replace("Z", "+00:00")
        )

        # Only generate future triggers
        if window_start > now:
            start_trigger = AutomationTrigger(
                trigger_type=TriggerType.OPTIMAL_WINDOW_START,
                timestamp=window_start,
                priority=TriggerPriority.HIGH,
                data={
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "avg_price": recommendation.get("avg_price"),
                    "rating": recommendation.get("rating"),
                    "estimated_cost": recommendation.get("total_cost"),
                },
                message=f"Optimal charging window starting - {recommendation.get('rating', 'GOOD')} opportunity",
                expires_at=window_end,
            )
            triggers.append(start_trigger)

        if window_end > now:
            end_trigger = AutomationTrigger(
                trigger_type=TriggerType.OPTIMAL_WINDOW_END,
                timestamp=window_end,
                priority=TriggerPriority.NORMAL,
                data={
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
                message="Optimal charging window ending",
                expires_at=window_end + timedelta(minutes=30),
            )
            triggers.append(end_trigger)

        return triggers

    def _generate_plug_in_reminder(
        self,
        recommendation: Dict[str, Any],
        now: datetime,
    ) -> Optional[AutomationTrigger]:
        """Generate plug-in reminder based on optimal window.

        Reminds user to plug in before the optimal window starts,
        accounting for their typical arrival pattern.

        Args:
            recommendation: Recommendation data
            now: Current time

        Returns:
            Plug-in reminder trigger or None
        """
        window_start = datetime.fromisoformat(
            recommendation["window_start"].replace("Z", "+00:00")
        )

        # Get arrival window from config
        acix_config = self.config.get("acix", {})
        arrival_config = acix_config.get("arrival_window", {})
        arrival_end = arrival_config.get("end", "20:00")

        # Parse arrival end time
        arrival_hour, arrival_minute = map(int, arrival_end.split(":"))
        reminder_time = window_start.replace(
            hour=arrival_hour, minute=arrival_minute, second=0, microsecond=0
        )

        # If window starts before arrival time, set reminder for arrival time
        if window_start.hour < arrival_hour:
            # Window is overnight, reminder should be evening before
            reminder_time = reminder_time - timedelta(days=1)

        # Ensure reminder is in the future
        if reminder_time <= now:
            return None

        # Adjust if reminder would be after window starts
        if reminder_time >= window_start:
            reminder_time = window_start - timedelta(hours=1)
            if reminder_time <= now:
                return None

        return AutomationTrigger(
            trigger_type=TriggerType.PLUG_IN_REMINDER,
            timestamp=reminder_time,
            priority=TriggerPriority.NORMAL,
            data={
                "window_start": window_start.isoformat(),
                "hours_until_window": (window_start - reminder_time).total_seconds()
                / 3600,
                "rating": recommendation.get("rating"),
            },
            message=f"Remember to plug in - {recommendation.get('rating', 'GOOD')} window at {window_start.strftime('%H:%M')}",
            expires_at=window_start,
        )

    def _generate_negative_pricing_trigger(
        self,
        recommendation: Dict[str, Any],
        now: datetime,
    ) -> AutomationTrigger:
        """Generate urgent trigger for negative pricing.

        Args:
            recommendation: Recommendation data
            now: Current time

        Returns:
            Negative pricing trigger
        """
        window_start = datetime.fromisoformat(
            recommendation["window_start"].replace("Z", "+00:00")
        )

        # Trigger immediately or at window start
        trigger_time = max(now, window_start - timedelta(hours=1))

        return AutomationTrigger(
            trigger_type=TriggerType.NEGATIVE_PRICING,
            timestamp=trigger_time,
            priority=TriggerPriority.URGENT,
            data={
                "avg_price": recommendation.get("avg_price"),
                "window_start": window_start.isoformat(),
                "estimated_earnings": abs(
                    recommendation.get("avg_price", 0) * self.typical_kwh / 100
                ),
            },
            message="NEGATIVE PRICING! You'll be PAID to charge!",
            expires_at=datetime.fromisoformat(
                recommendation["window_end"].replace("Z", "+00:00")
            ),
        )

    def _generate_pattern_triggers(
        self,
        now: datetime,
    ) -> List[AutomationTrigger]:
        """Generate triggers based on ACIX behavioral patterns.

        Args:
            now: Current time

        Returns:
            List of pattern-based triggers
        """
        triggers = []

        try:
            from modules.recommendation_analyzer import RecommendationAnalyzer

            analyzer = RecommendationAnalyzer(self.data_store)
            metrics = analyzer.analyze_period(days=7)

            patterns = metrics.patterns

            # Late start pattern - generate early reminder
            if patterns.get("late_start_ratio", 0) > 0.3:
                # User often plugs in late, send reminder at 18:00
                reminder_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
                if reminder_time <= now:
                    reminder_time += timedelta(days=1)

                triggers.append(
                    AutomationTrigger(
                        trigger_type=TriggerType.PATTERN_ALERT,
                        timestamp=reminder_time,
                        priority=TriggerPriority.NORMAL,
                        data={
                            "pattern": "late_start",
                            "late_ratio": patterns["late_start_ratio"],
                        },
                        message="You often plug in late - remember to connect early for optimal savings!",
                        expires_at=reminder_time + timedelta(hours=4),
                    )
                )

            # Low compliance pattern
            if metrics.compliance_rate < 50 and metrics.sessions_analyzed >= 3:
                triggers.append(
                    AutomationTrigger(
                        trigger_type=TriggerType.PATTERN_ALERT,
                        timestamp=now,
                        priority=TriggerPriority.LOW,
                        data={
                            "pattern": "low_compliance",
                            "compliance_rate": metrics.compliance_rate,
                            "improvement_potential": metrics.improvement_potential,
                        },
                        message=f"Your compliance is {metrics.compliance_rate:.0f}% - you could save £{metrics.improvement_potential:.2f}/month more!",
                        expires_at=now + timedelta(days=1),
                    )
                )

        except Exception as e:
            logger.warning(f"Could not generate pattern triggers: {e}")

        return triggers

    def get_active_triggers(self) -> List[AutomationTrigger]:
        """Get currently active (non-expired) triggers.

        Returns:
            List of active triggers
        """
        schedule = self._load_schedule()
        if not schedule:
            return []

        now = datetime.now(timezone.utc)
        active = []

        for trigger in schedule.triggers:
            # Check if not expired
            if trigger.expires_at and trigger.expires_at < now:
                continue
            # Check if timestamp is in the past (already triggered)
            if trigger.timestamp > now:
                active.append(trigger)

        return active

    def get_next_trigger(self) -> Optional[AutomationTrigger]:
        """Get the next upcoming trigger.

        Returns:
            Next trigger or None
        """
        active = self.get_active_triggers()
        if not active:
            return None

        return min(active, key=lambda t: t.timestamp)

    def export_for_home_assistant(self) -> Dict[str, Any]:
        """Export triggers in Home Assistant compatible format.

        Returns:
            Dictionary suitable for Home Assistant automations
        """
        active = self.get_active_triggers()

        return {
            "ev_charging_optimizer": {
                "triggers": [
                    {
                        "platform": "time",
                        "at": t.timestamp.strftime("%H:%M:%S"),
                        "trigger_type": t.trigger_type.value,
                        "data": t.data,
                    }
                    for t in active
                ],
                "next_window": (
                    self.get_next_trigger().data if self.get_next_trigger() else None
                ),
            }
        }

    def export_webhook_payload(self, trigger: AutomationTrigger) -> Dict[str, Any]:
        """Export a trigger as a webhook payload.

        Args:
            trigger: Trigger to export

        Returns:
            Webhook payload dictionary
        """
        return {
            "event": "ev_charging_trigger",
            "trigger": trigger.to_dict(),
            "source": "ev-charging-optimizer",
            "version": "1.0",
        }

    def _save_schedule(self, schedule: AutomationSchedule) -> None:
        """Save schedule to file.

        Args:
            schedule: Schedule to save
        """
        self.TRIGGERS_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(self.TRIGGERS_FILE, "w") as f:
            json.dump(schedule.to_dict(), f, indent=2)

        logger.debug(f"Saved {len(schedule.triggers)} triggers to {self.TRIGGERS_FILE}")

    def _load_schedule(self) -> Optional[AutomationSchedule]:
        """Load schedule from file.

        Returns:
            Loaded schedule or None
        """
        if not self.TRIGGERS_FILE.exists():
            return None

        try:
            with open(self.TRIGGERS_FILE, "r") as f:
                data = json.load(f)

            triggers = []
            for t_data in data.get("triggers", []):
                triggers.append(
                    AutomationTrigger(
                        trigger_type=TriggerType(t_data["trigger_type"]),
                        timestamp=datetime.fromisoformat(t_data["timestamp"]),
                        priority=TriggerPriority(t_data["priority"]),
                        data=t_data.get("data", {}),
                        message=t_data.get("message", ""),
                        expires_at=(
                            datetime.fromisoformat(t_data["expires_at"])
                            if t_data.get("expires_at")
                            else None
                        ),
                    )
                )

            return AutomationSchedule(
                generated_at=datetime.fromisoformat(data["generated_at"]),
                triggers=triggers,
            )

        except Exception as e:
            logger.warning(f"Could not load schedule: {e}")
            return None

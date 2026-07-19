"""Recommendation Analyzer

Compares actual EV charging behavior (detected sessions) against system
recommendations to provide behavioral insights and optimization feedback.

Part of the ACIX (Adaptive Charging Intelligence Extension) system.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class SessionAnalysis:
    """Analysis of a single charging session vs recommendation."""

    session_date: str
    actual_start: datetime
    actual_end: datetime
    actual_kwh: float
    actual_cost: float

    recommended_start: Optional[datetime]
    recommended_end: Optional[datetime]
    recommended_cost: Optional[float]

    timing_score: int  # 0-100: how well timing aligned
    cost_efficiency: float  # ratio: actual_cost / optimal_cost (1.0 = perfect)
    savings_captured: float  # £ saved vs evening baseline
    savings_missed: float  # £ that could have been saved with optimal timing
    overlap_minutes: int  # minutes of actual charging within optimal window

    compliance_status: str  # "optimal", "partial", "suboptimal", "no_recommendation"
    insights: List[str]  # Human-readable insights

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_date": self.session_date,
            "actual_start": self.actual_start.isoformat(),
            "actual_end": self.actual_end.isoformat(),
            "actual_kwh": round(self.actual_kwh, 2),
            "actual_cost": round(self.actual_cost, 2),
            "recommended_start": (
                self.recommended_start.isoformat() if self.recommended_start else None
            ),
            "recommended_end": (
                self.recommended_end.isoformat() if self.recommended_end else None
            ),
            "recommended_cost": (
                round(self.recommended_cost, 2) if self.recommended_cost else None
            ),
            "timing_score": self.timing_score,
            "cost_efficiency": round(self.cost_efficiency, 3),
            "savings_captured": round(self.savings_captured, 2),
            "savings_missed": round(self.savings_missed, 2),
            "overlap_minutes": self.overlap_minutes,
            "compliance_status": self.compliance_status,
            "insights": self.insights,
        }


@dataclass
class BehaviorMetrics:
    """Aggregated behavior metrics over multiple sessions."""

    period_start: str
    period_end: str
    total_sessions: int
    sessions_analyzed: int

    avg_timing_score: float
    avg_cost_efficiency: float
    total_savings_captured: float
    total_savings_missed: float

    optimal_count: int
    partial_count: int
    suboptimal_count: int
    no_recommendation_count: int

    compliance_rate: float  # % of sessions at least partially optimal
    improvement_potential: float  # estimated monthly savings if fully compliant

    patterns: Dict[str, Any]  # Detected patterns (e.g., late plug-in times)
    recommendations: List[str]  # Personalized recommendations

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_sessions": self.total_sessions,
            "sessions_analyzed": self.sessions_analyzed,
            "avg_timing_score": round(self.avg_timing_score, 1),
            "avg_cost_efficiency": round(self.avg_cost_efficiency, 3),
            "total_savings_captured": round(self.total_savings_captured, 2),
            "total_savings_missed": round(self.total_savings_missed, 2),
            "optimal_count": self.optimal_count,
            "partial_count": self.partial_count,
            "suboptimal_count": self.suboptimal_count,
            "no_recommendation_count": self.no_recommendation_count,
            "compliance_rate": round(self.compliance_rate, 1),
            "improvement_potential": round(self.improvement_potential, 2),
            "patterns": self.patterns,
            "recommendations": self.recommendations,
        }


class RecommendationAnalyzer:
    """Analyzes charging behavior vs recommendations.

    Compares detected EV charging sessions against system recommendations
    to provide insights and optimization feedback.
    """

    # Timing thresholds
    OPTIMAL_OVERLAP_THRESHOLD = 0.8  # 80% overlap = optimal
    PARTIAL_OVERLAP_THRESHOLD = 0.3  # 30% overlap = partial

    # Cost efficiency thresholds
    EXCELLENT_EFFICIENCY = 1.05  # Within 5% of optimal
    GOOD_EFFICIENCY = 1.15  # Within 15% of optimal

    # Evening baseline rate (typical peak rate for comparison)
    EVENING_BASELINE_RATE = 22.0  # pence/kWh typical evening rate

    def __init__(
        self,
        data_store: Any,
        baseline_rate: float = EVENING_BASELINE_RATE,
    ):
        """Initialize analyzer.

        Args:
            data_store: DataStore instance for accessing data
            baseline_rate: Evening baseline rate in pence/kWh for comparison
        """
        self.data_store = data_store
        self.baseline_rate = baseline_rate
        logger.info(f"RecommendationAnalyzer initialized (baseline={baseline_rate}p)")

    def analyze_session(
        self,
        session: Dict[str, Any],
        recommendation: Optional[Dict[str, Any]],
        price_data: Optional[List[Dict[str, Any]]] = None,
    ) -> SessionAnalysis:
        """Analyze a single charging session against its recommendation.

        Args:
            session: Detected charging session
            recommendation: Daily recommendation for that date (or None)
            price_data: Optional actual price data for cost calculation

        Returns:
            SessionAnalysis with detailed comparison
        """
        session_date = session.get("date", "unknown")

        # Parse session times
        actual_start = datetime.fromisoformat(
            session["charge_start"].replace("Z", "+00:00")
        )
        actual_end = datetime.fromisoformat(
            session["charge_end"].replace("Z", "+00:00")
        )
        actual_kwh = session.get("total_kwh", 0.0)

        # Calculate actual cost
        actual_cost = self._calculate_session_cost(
            actual_start, actual_end, actual_kwh, price_data
        )

        # Calculate baseline cost (what they'd pay charging at evening peak)
        baseline_cost = (actual_kwh * self.baseline_rate) / 100

        if recommendation is None:
            # No recommendation available for this date
            return SessionAnalysis(
                session_date=session_date,
                actual_start=actual_start,
                actual_end=actual_end,
                actual_kwh=actual_kwh,
                actual_cost=actual_cost,
                recommended_start=None,
                recommended_end=None,
                recommended_cost=None,
                timing_score=50,  # Neutral score
                cost_efficiency=1.0,
                savings_captured=max(0, baseline_cost - actual_cost),
                savings_missed=0.0,
                overlap_minutes=0,
                compliance_status="no_recommendation",
                insights=["No recommendation was available for this date"],
            )

        # Parse recommendation times
        rec_start = datetime.fromisoformat(
            recommendation["window_start"].replace("Z", "+00:00")
        )
        rec_end = datetime.fromisoformat(
            recommendation["window_end"].replace("Z", "+00:00")
        )
        rec_cost = recommendation.get("total_cost")

        # Scale recommended cost to actual kWh charged
        if rec_cost and recommendation.get("avg_price"):
            rec_cost_scaled = (recommendation["avg_price"] * actual_kwh) / 100
        else:
            rec_cost_scaled = rec_cost

        # Calculate overlap
        overlap_minutes = self._calculate_overlap(
            actual_start, actual_end, rec_start, rec_end
        )
        actual_duration_minutes = (actual_end - actual_start).total_seconds() / 60
        overlap_ratio = (
            overlap_minutes / actual_duration_minutes
            if actual_duration_minutes > 0
            else 0
        )

        # Determine timing score
        timing_score = self._calculate_timing_score(
            actual_start, actual_end, rec_start, rec_end, overlap_ratio
        )

        # Calculate cost efficiency
        cost_efficiency = (
            actual_cost / rec_cost_scaled
            if rec_cost_scaled and rec_cost_scaled > 0
            else 1.0
        )

        # Calculate savings
        savings_captured = max(0, baseline_cost - actual_cost)
        optimal_savings = (
            max(0, baseline_cost - rec_cost_scaled) if rec_cost_scaled else 0
        )
        savings_missed = max(0, optimal_savings - savings_captured)

        # Determine compliance status
        compliance_status = self._determine_compliance(overlap_ratio, cost_efficiency)

        # Generate insights
        insights = self._generate_session_insights(
            actual_start,
            actual_end,
            rec_start,
            rec_end,
            overlap_ratio,
            cost_efficiency,
            savings_missed,
        )

        return SessionAnalysis(
            session_date=session_date,
            actual_start=actual_start,
            actual_end=actual_end,
            actual_kwh=actual_kwh,
            actual_cost=actual_cost,
            recommended_start=rec_start,
            recommended_end=rec_end,
            recommended_cost=rec_cost_scaled,
            timing_score=timing_score,
            cost_efficiency=cost_efficiency,
            savings_captured=savings_captured,
            savings_missed=savings_missed,
            overlap_minutes=overlap_minutes,
            compliance_status=compliance_status,
            insights=insights,
        )

    def analyze_period(
        self,
        days: int = 30,
    ) -> BehaviorMetrics:
        """Analyze behavior over a period.

        Args:
            days: Number of days to analyze

        Returns:
            BehaviorMetrics with aggregated insights
        """
        # Get sessions and recommendations
        sessions = self.data_store.get_sessions(days=days)
        recommendations = self.data_store.get_recommendations(days=days)

        if not sessions:
            logger.info("No sessions to analyze")
            return self._empty_metrics(days)

        # Build recommendation lookup by date
        rec_by_date = {}
        for rec in recommendations:
            date = rec.get("date")
            if date:
                # Keep the most recent recommendation for each date
                if (
                    date not in rec_by_date
                    or rec["saved_at"] > rec_by_date[date]["saved_at"]
                ):
                    rec_by_date[date] = rec

        # Analyze each session
        analyses = []
        for session in sessions:
            session_date = session.get("date")
            recommendation = rec_by_date.get(session_date)
            analysis = self.analyze_session(session, recommendation)
            analyses.append(analysis)

        # Aggregate metrics
        return self._aggregate_metrics(analyses, days)

    def get_latest_analysis(self) -> Optional[SessionAnalysis]:
        """Get analysis for the most recent charging session.

        Returns:
            SessionAnalysis for latest session or None
        """
        sessions = self.data_store.get_sessions(days=7)
        if not sessions:
            return None

        # Get most recent session
        latest_session = max(sessions, key=lambda s: s.get("saved_at", ""))

        # Get recommendation for that date
        session_date = latest_session.get("date")
        recommendation = self.data_store.get_recommendation_by_date(session_date)

        return self.analyze_session(latest_session, recommendation)

    def _calculate_overlap(
        self,
        actual_start: datetime,
        actual_end: datetime,
        rec_start: datetime,
        rec_end: datetime,
    ) -> int:
        """Calculate overlap in minutes between actual and recommended windows.

        Args:
            actual_start: Actual charging start
            actual_end: Actual charging end
            rec_start: Recommended window start
            rec_end: Recommended window end

        Returns:
            Overlap in minutes
        """
        # Find the overlap interval
        overlap_start = max(actual_start, rec_start)
        overlap_end = min(actual_end, rec_end)

        if overlap_start >= overlap_end:
            return 0

        return int((overlap_end - overlap_start).total_seconds() / 60)

    def _calculate_timing_score(
        self,
        actual_start: datetime,
        actual_end: datetime,
        rec_start: datetime,
        rec_end: datetime,
        overlap_ratio: float,
    ) -> int:
        """Calculate timing score (0-100).

        Considers:
        - Overlap with recommended window
        - How early/late charging started relative to recommendation
        - Duration alignment

        Args:
            actual_start: Actual charging start
            actual_end: Actual charging end
            rec_start: Recommended window start
            rec_end: Recommended window end
            overlap_ratio: Ratio of actual charging within recommended window

        Returns:
            Score 0-100
        """
        score = 0

        # Overlap component (up to 60 points)
        score += int(overlap_ratio * 60)

        # Start time alignment (up to 20 points)
        start_diff_hours = abs((actual_start - rec_start).total_seconds() / 3600)
        if start_diff_hours <= 0.5:
            score += 20  # Within 30 mins
        elif start_diff_hours <= 1:
            score += 15
        elif start_diff_hours <= 2:
            score += 10
        elif start_diff_hours <= 4:
            score += 5

        # Whether charging covered the cheapest periods (up to 20 points)
        # If they started during the recommended window
        if rec_start <= actual_start <= rec_end:
            score += 20
        elif actual_start < rec_start:
            # Started early - might have caught some cheap rates
            early_minutes = (rec_start - actual_start).total_seconds() / 60
            score += max(0, 15 - int(early_minutes / 30))

        return min(100, score)

    def _calculate_session_cost(
        self,
        start: datetime,
        end: datetime,
        kwh: float,
        price_data: Optional[List[Dict[str, Any]]],
    ) -> float:
        """Calculate actual cost for a charging session.

        Uses actual price data if available, otherwise estimates from stored prices.

        Args:
            start: Session start time
            end: Session end time
            kwh: Total kWh charged
            price_data: Optional price data list

        Returns:
            Cost in £
        """
        if not price_data:
            # Use average nighttime rate as estimate
            # This is a rough estimate when we don't have actual price data
            avg_rate = 15.0  # Typical overnight Agile rate
            return (kwh * avg_rate) / 100

        # Calculate weighted average price for the session period
        total_weighted_price = 0.0
        total_weight = 0.0

        for price in price_data:
            price_start = datetime.fromisoformat(
                price["interval_start"].replace("Z", "+00:00")
            )
            price_end = datetime.fromisoformat(
                price["interval_end"].replace("Z", "+00:00")
            )

            # Check if this price interval overlaps with session
            overlap_start = max(start, price_start)
            overlap_end = min(end, price_end)

            if overlap_start < overlap_end:
                # Weight by overlap duration
                overlap_minutes = (overlap_end - overlap_start).total_seconds() / 60
                total_weighted_price += (
                    price.get("value_inc_vat", 15.0) * overlap_minutes
                )
                total_weight += overlap_minutes

        if total_weight > 0:
            avg_price = total_weighted_price / total_weight
            return (kwh * avg_price) / 100

        return (kwh * 15.0) / 100  # Fallback

    def _determine_compliance(
        self,
        overlap_ratio: float,
        cost_efficiency: float,
    ) -> str:
        """Determine compliance status based on overlap and efficiency.

        Args:
            overlap_ratio: Ratio of charging within optimal window
            cost_efficiency: Cost ratio vs optimal

        Returns:
            Compliance status string
        """
        if overlap_ratio >= self.OPTIMAL_OVERLAP_THRESHOLD:
            if cost_efficiency <= self.EXCELLENT_EFFICIENCY:
                return "optimal"
            return "partial"
        elif overlap_ratio >= self.PARTIAL_OVERLAP_THRESHOLD:
            return "partial"
        else:
            return "suboptimal"

    def _generate_session_insights(
        self,
        actual_start: datetime,
        actual_end: datetime,
        rec_start: datetime,
        rec_end: datetime,
        overlap_ratio: float,
        cost_efficiency: float,
        savings_missed: float,
    ) -> List[str]:
        """Generate human-readable insights for a session.

        Args:
            actual_start: Actual charging start
            actual_end: Actual charging end
            rec_start: Recommended window start
            rec_end: Recommended window end
            overlap_ratio: Ratio of charging within optimal window
            cost_efficiency: Cost ratio vs optimal
            savings_missed: Savings that could have been captured

        Returns:
            List of insight strings
        """
        insights = []

        # Overlap analysis
        if overlap_ratio >= self.OPTIMAL_OVERLAP_THRESHOLD:
            insights.append("Excellent timing - most charging during optimal window")
        elif overlap_ratio >= self.PARTIAL_OVERLAP_THRESHOLD:
            insights.append(
                f"Partial overlap ({int(overlap_ratio * 100)}%) with optimal window"
            )
        elif overlap_ratio > 0:
            insights.append(
                f"Limited overlap ({int(overlap_ratio * 100)}%) - consider adjusting timing"
            )
        else:
            insights.append("No overlap with optimal window")

        # Start time analysis
        start_diff = actual_start - rec_start
        start_diff_hours = start_diff.total_seconds() / 3600

        if start_diff_hours > 0.5:
            insights.append(
                f"Started {start_diff_hours:.1f} hours after optimal window began"
            )
        elif start_diff_hours < -1:
            insights.append(
                f"Started {abs(start_diff_hours):.1f} hours before optimal window"
            )

        # Cost analysis
        if cost_efficiency <= 1.0:
            insights.append("Achieved optimal or better pricing")
        elif cost_efficiency <= self.EXCELLENT_EFFICIENCY:
            insights.append(
                f"Very close to optimal cost (within {int((cost_efficiency - 1) * 100)}%)"
            )
        elif cost_efficiency <= self.GOOD_EFFICIENCY:
            insights.append(
                f"Close to optimal cost (within {int((cost_efficiency - 1) * 100)}%)"
            )
        else:
            insights.append(
                f"Cost was {int((cost_efficiency - 1) * 100)}% above optimal"
            )

        # Savings analysis
        if savings_missed > 0.50:
            insights.append(f"Could have saved an additional £{savings_missed:.2f}")
        elif savings_missed > 0:
            insights.append(
                f"Minor additional savings possible (£{savings_missed:.2f})"
            )

        return insights

    def _aggregate_metrics(
        self,
        analyses: List[SessionAnalysis],
        days: int,
    ) -> BehaviorMetrics:
        """Aggregate individual session analyses into period metrics.

        Args:
            analyses: List of SessionAnalysis objects
            days: Analysis period in days

        Returns:
            BehaviorMetrics with aggregated data
        """
        if not analyses:
            return self._empty_metrics(days)

        # Count compliance categories
        optimal_count = sum(1 for a in analyses if a.compliance_status == "optimal")
        partial_count = sum(1 for a in analyses if a.compliance_status == "partial")
        suboptimal_count = sum(
            1 for a in analyses if a.compliance_status == "suboptimal"
        )
        no_rec_count = sum(
            1 for a in analyses if a.compliance_status == "no_recommendation"
        )

        # Calculate averages (excluding no_recommendation sessions)
        analyzed = [a for a in analyses if a.compliance_status != "no_recommendation"]

        if analyzed:
            avg_timing = sum(a.timing_score for a in analyzed) / len(analyzed)
            avg_efficiency = sum(a.cost_efficiency for a in analyzed) / len(analyzed)
        else:
            avg_timing = 0
            avg_efficiency = 1.0

        total_captured = sum(a.savings_captured for a in analyses)
        total_missed = sum(a.savings_missed for a in analyses)

        # Calculate compliance rate
        analyzed_count = len(analyzed)
        compliant_count = optimal_count + partial_count
        compliance_rate = (
            (compliant_count / analyzed_count * 100) if analyzed_count > 0 else 0
        )

        # Estimate monthly improvement potential
        avg_missed_per_session = total_missed / len(analyses) if analyses else 0
        # Assume ~20 charging sessions per month
        improvement_potential = avg_missed_per_session * 20

        # Detect patterns
        patterns = self._detect_patterns(analyses)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            analyses, patterns, compliance_rate
        )

        # Determine period
        dates = [a.session_date for a in analyses]
        period_start = min(dates) if dates else ""
        period_end = max(dates) if dates else ""

        return BehaviorMetrics(
            period_start=period_start,
            period_end=period_end,
            total_sessions=len(analyses),
            sessions_analyzed=analyzed_count,
            avg_timing_score=avg_timing,
            avg_cost_efficiency=avg_efficiency,
            total_savings_captured=total_captured,
            total_savings_missed=total_missed,
            optimal_count=optimal_count,
            partial_count=partial_count,
            suboptimal_count=suboptimal_count,
            no_recommendation_count=no_rec_count,
            compliance_rate=compliance_rate,
            improvement_potential=improvement_potential,
            patterns=patterns,
            recommendations=recommendations,
        )

    def _detect_patterns(
        self,
        analyses: List[SessionAnalysis],
    ) -> Dict[str, Any]:
        """Detect behavioral patterns from session analyses.

        Args:
            analyses: List of session analyses

        Returns:
            Dictionary of detected patterns
        """
        patterns: Dict[str, Any] = {}

        if not analyses:
            return patterns

        # Analyze start times
        start_hours = [a.actual_start.hour for a in analyses]
        if start_hours:
            avg_start_hour = sum(start_hours) / len(start_hours)
            patterns["avg_start_hour"] = round(avg_start_hour, 1)

            # Check for late starts (after 22:00)
            late_starts = sum(1 for h in start_hours if h >= 22)
            patterns["late_start_count"] = late_starts
            patterns["late_start_ratio"] = round(late_starts / len(start_hours), 2)

        # Analyze day of week patterns
        days_of_week = [a.actual_start.weekday() for a in analyses]
        weekend_sessions = sum(1 for d in days_of_week if d >= 5)
        patterns["weekend_ratio"] = round(
            weekend_sessions / len(days_of_week) if days_of_week else 0, 2
        )

        # Energy usage patterns
        kwh_values = [a.actual_kwh for a in analyses]
        if kwh_values:
            patterns["avg_kwh"] = round(sum(kwh_values) / len(kwh_values), 1)
            patterns["max_kwh"] = round(max(kwh_values), 1)
            patterns["min_kwh"] = round(min(kwh_values), 1)

        # Timing consistency
        if len(start_hours) >= 3:
            variance = sum((h - avg_start_hour) ** 2 for h in start_hours) / len(
                start_hours
            )
            patterns["start_time_variance"] = round(variance, 2)
            patterns["consistent_timing"] = variance < 4  # Low variance = consistent

        return patterns

    def _generate_recommendations(
        self,
        analyses: List[SessionAnalysis],
        patterns: Dict[str, Any],
        compliance_rate: float,
    ) -> List[str]:
        """Generate personalized recommendations based on analysis.

        Args:
            analyses: List of session analyses
            patterns: Detected patterns
            compliance_rate: Overall compliance rate

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if not analyses:
            return ["Not enough data for recommendations yet"]

        # Low compliance rate
        if compliance_rate < 50:
            recommendations.append(
                "Consider setting a timer or smart plug to start charging during "
                "optimal windows"
            )

        # Late start pattern
        if patterns.get("late_start_ratio", 0) > 0.3:
            recommendations.append(
                "You often plug in late. Consider connecting the charger earlier "
                "and using scheduled charging"
            )

        # Inconsistent timing
        if not patterns.get("consistent_timing", True):
            recommendations.append(
                "Your charging times vary significantly. A consistent schedule "
                "could improve savings"
            )

        # High average start hour
        avg_hour = patterns.get("avg_start_hour", 20)
        if avg_hour > 21:
            recommendations.append(
                "Your average plug-in time is late. The cheapest rates often "
                "start earlier (around 00:00-05:00)"
            )

        # Savings opportunity
        total_missed = sum(a.savings_missed for a in analyses)
        if total_missed > 2.0:
            recommendations.append(
                f"You could have saved £{total_missed:.2f} more over this period "
                "by optimizing charging times"
            )

        # Positive reinforcement
        if compliance_rate >= 80:
            recommendations.append("Great job! Your charging timing is well-optimized")

        return recommendations if recommendations else ["Keep monitoring for patterns"]

    def _empty_metrics(self, days: int) -> BehaviorMetrics:
        """Create empty metrics when no data is available.

        Args:
            days: Analysis period

        Returns:
            BehaviorMetrics with zero values
        """
        return BehaviorMetrics(
            period_start="",
            period_end="",
            total_sessions=0,
            sessions_analyzed=0,
            avg_timing_score=0,
            avg_cost_efficiency=1.0,
            total_savings_captured=0,
            total_savings_missed=0,
            optimal_count=0,
            partial_count=0,
            suboptimal_count=0,
            no_recommendation_count=0,
            compliance_rate=0,
            improvement_potential=0,
            patterns={},
            recommendations=["Not enough data to analyze yet"],
        )

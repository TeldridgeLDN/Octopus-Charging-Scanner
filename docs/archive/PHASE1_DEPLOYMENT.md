# Phase 1 Enhancements - Deployment Guide

**Date**: 8 December 2025
**Features**: Forecast Accuracy Tracking, Smart Threshold Auto-Tuning, Window Overlap Detection

---

## 🎯 Quick Deployment (5 minutes)

### Step 1: Create Launch Agent for Forecast Comparison

```bash
# Create the plist file
cat > ~/Library/LaunchAgents/com.ev-optimizer.forecast-comparison.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ev-optimizer.forecast-comparison</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/tomeldridge/my_python_project/scripts/Momentum_dashboard/venv/bin/python3</string>
        <string>/Users/tomeldridge/ev-charging-optimizer/src/scripts/forecast_comparison.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/tomeldridge/ev-charging-optimizer</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>23</integer>
        <key>Minute</key>
        <integer>59</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/tomeldridge/ev-charging-optimizer/logs/forecast_comparison.out.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/tomeldridge/ev-charging-optimizer/logs/forecast_comparison.err.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF

# Load the launch agent
launchctl load ~/Library/LaunchAgents/com.ev-optimizer.forecast-comparison.plist

# Verify it's loaded
launchctl list | grep forecast-comparison
```

### Step 2: Test Manually

```bash
cd /Users/tomeldridge/ev-charging-optimizer

# Test forecast comparison script
python3 src/scripts/forecast_comparison.py

# Check it created the data file
ls -lh data/forecast_accuracy.json

# View the data
cat data/forecast_accuracy.json | python3 -m json.tool | head -30
```

### Step 3: Test Threshold Tuner

```
# Quick Python test
cd /Users/tomeldridge/ev-charging-optimizer
python3 << 'EOF'
from pathlib import Path
from src.modules.threshold_tuner import ThresholdTuner

tuner = ThresholdTuner()
recommendations = tuner.get_recommended_thresholds(
    Path("data/daily_recommendations.json")
)

print("Current Threshold Recommendations:")
print(f"  Price Excellent: {recommendations['price_excellent']}p/kWh")
print(f"  Price Good: {recommendations['price_good']}p/kWh")
print(f"  Days Analyzed: {recommendations['days_analyzed']}")
if 'using_defaults' in recommendations:
    print("  ⚠️  Using defaults (insufficient data)")
else:
    print("  ✅ Based on historical data")
EOF
```

### Step 4: Test Window Status

```
# Quick Python test
cd /Users/tomeldridge/ev-charging-optimizer
python3 << 'EOF'
from datetime import datetime, timezone, timedelta
from src.modules.analyzer import ChargingWindow, OpportunityRating, WindowStatus

# Create a test window for tonight
now = datetime.now(timezone.utc)
tonight = now.replace(hour=23, minute=0, second=0, microsecond=0)

window = ChargingWindow(
    start=tonight,
    end=tonight + timedelta(hours=4),
    avg_price=11.4,
    avg_carbon=130,
    total_cost=3.42,
    total_carbon=3900,
    opportunity_score=85,
    rating=OpportunityRating.EXCELLENT,
    reason="cheap",
    savings_vs_baseline=1.08
)

status = window.get_status()
time_until = window.time_until_start()

print(f"Window Status: {status.value}")
print(f"Time until start: {time_until}")
print(f"Window is: {status.value.upper()}")
EOF
```

---

## 📊 What Each Feature Does

### 1. Forecast Accuracy Tracking

**Runs**: Daily at 23:59
**Purpose**: Compare Guy Lipman forecast vs Octopus actual prices
**Output**: `data/forecast_accuracy.json`

**Metrics Collected**:

- Mean Absolute Error (MAE)
- Systematic bias
- RMSE
- Negative pricing prediction accuracy
- 7-day and 30-day trends

**Reliability Grades**:

- MAE <2p = EXCELLENT
- MAE <3p = GOOD
- MAE <5p = FAIR
- MAE ≥5p = POOR

**Usage**:
```
from src.modules.forecast_tracker import ForecastTracker

tracker = ForecastTracker()
accuracy = tracker.get_recent_accuracy(days=7)
grade = tracker.get_reliability_grade(days=7)
should_trust = tracker.should_trust_forecast(days=7)

print(f"7-day MAE: {accuracy['mean_absolute_error']:.2f}p/kWh")
print(f"Grade: {grade}")
print(f"Should trust: {should_trust}")
```

---

### 2. Smart Threshold Auto-Tuning

**Runs**: On-demand (monthly recommended)
**Purpose**: Calculate optimal price/carbon thresholds from historical data
**Output**: `data/threshold_tuning.json`

**How It Works**:

- Analyzes last 30 days of recommendations
- Excellent threshold = 25th percentile (better than 75% of days)
- Good threshold = 50th percentile (median)
- Adapts to market conditions automatically

**Usage**:
```
from src.modules.threshold_tuner import ThresholdTuner
from pathlib import Path

tuner = ThresholdTuner()
recommended = tuner.get_recommended_thresholds(
    Path("data/daily_recommendations.json"),
    days=30
)

print(f"Current config: 10p/15p")
print(f"Recommended: {recommended['price_excellent']}p/{recommended['price_good']}p")

# Check if update needed
current = {"price_excellent": 10, "price_good": 15}
if tuner.should_update_thresholds(current):
    print("⚠️  Thresholds need updating!")
```

---

### 3. Window Overlap Detection

**Runs**: Real-time (in daily_notification and charge_reminder)
**Purpose**: Detect if recommended window already started/passed
**Output**: Window status enum

**Statuses**:

- `UPCOMING`: Window hasn't started yet (normal case)
- `ACTIVE`: Window is currently happening (urgent!)
- `PASSED`: Window already ended (need fallback)

**Usage in Scripts**:
```
from src.modules.analyzer import WindowStatus

# In daily_notification.py or charge_reminder.py
window = analyzer.find_optimal_window(prices, carbon, 4.05)
status = window.get_status()

if status == WindowStatus.PASSED:
    # Find next best window or show alternative
    message = "⚠️ Recommended window has passed. Next best: ..."
elif status == WindowStatus.ACTIVE:
    # Window is happening NOW
    message = "⚡ URGENT: Optimal window is ACTIVE NOW! Plug in immediately!"
else:
    # Normal upcoming window
    hours_until = window.time_until_start().total_seconds() / 3600
    message = f"🔋 Best window starts in {hours_until:.1f} hours..."
```

---

## 🔧 Configuration Updates

### Add to `config/config.yaml`

```yaml
# Forecast accuracy tracking
accuracy:
  alert_if_mae_exceeds: 5.0      # Alert if forecast MAE > 5p
  min_comparisons: 3             # Minimum days before grading
  trust_threshold: 4.0           # MAE threshold for "trustworthy"

# Threshold auto-tuning
tuning:
  auto_update_thresholds: false  # Manual approval required
  min_days_for_tuning: 14        # Minimum data before tuning
  update_interval_days: 30       # How often to recalculate
  percentile_excellent: 25       # 25th percentile for excellent
  percentile_good: 50            # 50th percentile (median) for good
```

---

## 📝 Logging

### New Log Files Created

```bash
logs/forecast_comparison.log       # Daily comparison script
logs/forecast_comparison.out.log   # Standard output
logs/forecast_comparison.err.log   # Error output
```

### Monitor Logs

```bash
# Watch forecast comparison logs
tail -f logs/forecast_comparison.log

# Check for errors
grep ERROR logs/forecast_comparison.log

# View last comparison
tail -20 logs/forecast_comparison.log
```

---

## 🧪 Validation Checklist

After deployment, verify:

- [ ] **Forecast Comparison**
  ```bash
  # Run manually
  python3 src/scripts/forecast_comparison.py
  # Check exit code
  echo $?  # Should be 0
  # Verify data file
  [ -f data/forecast_accuracy.json ] && echo "✅ File exists"
  ```

- [ ] **Launch Agent**
  ```bash
  # Check it's loaded
  launchctl list | grep forecast-comparison
  # Should show: com.ev-optimizer.forecast-comparison
  ```

- [ ] **Threshold Tuner**
  ```
  from src.modules.threshold_tuner import ThresholdTuner
  t = ThresholdTuner()
  r = t.get_recommended_thresholds(Path("data/daily_recommendations.json"))
  assert r is not None
  print("✅ Threshold tuner works")
  ```

- [ ] **Window Status**
  ```
  from src.modules.analyzer import WindowStatus
  assert WindowStatus.UPCOMING.value == "upcoming"
  print("✅ Window status enum works")
  ```

---

## 📊 Expected Data Files

After first run, you should see:

```
data/
├── daily_recommendations.json     # Existing
├── forecast_history.json          # Existing
├── user_actions.json              # Existing
├── forecast_accuracy.json         # NEW ✨
└── threshold_tuning.json          # NEW (after first tuning) ✨
```

### Sample `forecast_accuracy.json`

```json
[
  {
    "date": "2025-12-08",
    "timestamp": "2025-12-08T23:59:00Z",
    "forecast_source": "guy_lipman",
    "num_hours": 24,
    "mean_absolute_error": 2.85,
    "mean_error": 0.59,
    "rmse": 3.47,
    "forecast_avg": 14.55,
    "actual_avg": 15.14,
    "forecast_min": -4.17,
    "actual_min": 2.43,
    "negative_pricing": {
      "forecast_predicted": true,
      "actually_occurred": false,
      "correct_prediction": false
    }
  }
]
```

---

## 🚨 Troubleshooting

### Issue: "No forecast data available"

**Solution**: Guy Lipman API might be down or changed structure
```bash
# Check API directly
curl "https://energy.guylipman.com/forecasts?region=H" | head -50

# Run with verbose logging
python3 src/scripts/forecast_comparison.py 2>&1 | tee debug.log
```

### Issue: "Insufficient data for threshold tuning"

**Solution**: Need at least 7 days of recommendations
```bash
# Check how many recommendations exist
cat data/daily_recommendations.json | python3 -m json.tool | grep '"date"' | wc -l

# Wait for more data to accumulate (normal for new installations)
```

### Issue: Launch agent not running

**Solution**: Check launchd status
```bash
# Unload and reload
launchctl unload ~/Library/LaunchAgents/com.ev-optimizer.forecast-comparison.plist
launchctl load ~/Library/LaunchAgents/com.ev-optimizer.forecast-comparison.plist

# Check for errors
launchctl list | grep forecast

# View system logs
log show --predicate 'process == "com.ev-optimizer.forecast-comparison"' --last 1h
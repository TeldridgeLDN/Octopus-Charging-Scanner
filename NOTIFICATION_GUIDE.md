# EV Charging Optimizer - Notification Guide

## 🔔 Two Ways to Get Notifications

### 1. **On-Demand Notifications** (Recommended ⭐)

Run when YOU need charging advice based on YOUR actual battery level.

```bash
# Quick command
./charge 57 80 --notify

# Full command
python src/scripts/smart_charge_planner.py --current 57 --target 80 --notify
```

**What you get on your phone:**
```
🔋 57%→80% (£1.02)

👉 Plug in at 09:00 PM
⏱️  7.2h charge time

💰 Cost: £1.02
📊 Rate: 6.8p/kWh avg
⚡ Energy: 14.9 kWh

🎯 Ready by 08:00 AM Wed
```

**Advantages:**

- ✅ Personalized to your actual battery level
- ✅ You control when to receive notifications
- ✅ No spam - only when you need it
- ✅ Always uses real-time prices

---

### 2. **Automated Daily Notifications** (Passive)

Runs automatically at 4 PM daily via launchd.

**Now SMART - Only notifies for exceptional opportunities:**

#### What Triggers a Notification
- ⚡ **EXCELLENT** rated windows (90+ score)
- 💰 **Very cheap** prices (<8p/kWh average)
- 💵 **Big savings** (>£1.50 vs baseline)
- 🚨 **NEGATIVE pricing** (you get PAID to charge!)

#### What Gets Skipped
- GOOD/AVERAGE/POOR opportunities
- Normal pricing (10-15p/kWh)
- Small savings (<£1.50)

**Why this is better:**

- 🎯 Only alerts when there's a real opportunity
- 🔕 No daily spam for normal prices
- 💡 Still tracks all data for historical analysis
- 🤖 Use on-demand notifications for routine charging

---

## 📱 Notification Examples

### On-Demand (Personalized)
```
Title: 🔋 57%→80% (£1.02)

Body:
👉 Plug in at 09:00 PM
⏱️  7.2h charge time

💰 Cost: £1.02
📊 Rate: 6.8p/kWh avg
⚡ Energy: 14.9 kWh

🎯 Ready by 08:00 AM Wed

💵 Saves £0.97 vs 07:30 PM
```

### Automated - Exceptional Opportunity
```
Title: EV Optimizer: ⚡ Tonight: EXCELLENT opportunity

Body:
⚡ Best window: 02:00 AM - 06:00 AM
💰 Cost: £0.85 for 20kWh
📊 Avg price: 4.2p/kWh
💵 Save: £2.15 vs evening
🌱 Carbon: 87 gCO2/kWh (very clean)

Action: Cheap electricity
```

### Automated - Negative Pricing 🎉
```
Title: 💰 MONEY-MAKING ALERT: Negative Pricing Tonight!

Body:
⚡ You'll be PAID to charge tonight!

💵 Expected earnings: £3.47 for 20kWh
📊 Negative price slots: 8

Best negative slots:
  • 02:00: -5.2p/kWh (PAID £1.04)
  • 02:30: -4.8p/kWh (PAID £0.96)
  • 03:00: -4.1p/kWh (PAID £0.82)

🔋 Action: Plug in tonight - you'll make money!
```

### Automated - Skipped (No Notification)
```
[Log only - No Pushover notification sent]

⏸️  Skipping notification - not exceptional
(rating=GOOD, price=12.3p/kWh, savings=£0.85)

💡 Tip: Use './charge <current%> <target%> --notify' for personalized recommendations
```

---

## 🎛️ Configuration

### Notification Settings
Edit `config/config.yaml`:

```yaml
notifications:
  daily_time: "16:00"         # When daily check runs
  reminder_time: "20:00"      # Evening reminder
  weekly_summary_time: "18:00"  # Sunday summary
  max_per_day: 5              # Max notifications per day

apis:
  pushover:
    sounds:
      excellent: "cashregister"  # For EXCELLENT opportunities
      good: "cosmic"             # For GOOD opportunities
      reminder: "pushover"       # For reminders
      summary: "pushover"        # For summaries
```

### Exceptional Opportunity Thresholds
Edit `src/scripts/daily_notification.py`:

```python
is_exceptional = (
    window.rating == OpportunityRating.EXCELLENT  # EXCELLENT rating
    or window.avg_price <= 8.0  # Very cheap (<8p/kWh)
    or window.savings_vs_baseline >= 1.50  # Significant savings (>£1.50)
    or has_negative_pricing  # Negative pricing
)
```

**Adjust these values** based on your notification preferences:

- Lower `8.0` to `6.0` for stricter filtering (fewer notifications)
- Raise `1.50` to `2.00` for only huge savings
- Change to `GOOD` rating to get more notifications

---

## 🔄 Workflow Comparison

### Scenario 1: Regular Weeknight (No notification needed)
**14:30** - Battery at 45%, no urgent need
**16:00** - Automated check runs
**16:01** - Finds GOOD window (10.5p/kWh, £1.20 savings)
**16:01** - **Skips notification** (not exceptional)
**18:45** - You check car: 45%
**18:46** - Run: `./charge 45 80 --notify`
**18:46** - **Get personalized notification** for tonight's plan

### Scenario 2: Exceptional Opportunity
**14:30** - Battery fine, not planning to charge
**16:00** - Automated check runs
**16:01** - Finds **EXCELLENT** window (4.8p/kWh, £2.50 savings)
**16:01** - **Sends notification automatically** 🔔
**16:05** - You see it and decide to charge tonight

### Scenario 3: Negative Pricing Event
**14:30** - Battery at 70%, wasn't planning to charge
**16:00** - Automated check runs
**16:01** - Detects **negative pricing** (-3.2p/kWh)
**16:01** - **Sends HIGH PRIORITY alert** 🚨
**16:05** - You see it and charge to 100% to maximize earnings!

---

## 📊 Best Practices

### When to Use On-Demand
- ✅ You need to charge tonight
- ✅ Want personalized plan for current battery level
- ✅ Testing different target percentages (70% vs 80%)
- ✅ Checking prices before deciding to charge

### When to Rely on Automated
- ✅ Passive monitoring for exceptional deals
- ✅ Negative pricing alerts (rare but valuable)
- ✅ Don't want to remember to check manually
- ✅ Historical tracking (runs daily even when skipped)

### Recommended Hybrid Approach
1. **Keep automated notifications enabled** for exceptional opportunities
2. **Use on-demand** when you actually need to charge
3. **Adjust thresholds** if you get too many/few automated alerts

---

## 🛠️ Testing Your Notifications

```bash
# Test on-demand notification
./charge 57 80 --notify

# Test automated notification (manually trigger daily script)
python src/scripts/daily_notification.py

# Check logs to see if notification would have been sent
tail -50 logs/daily_notification.log
```

---

## 📈 Notification History

All notifications (sent and skipped) are logged:

- **Sent notifications**: `logs/daily_notification.log`
- **Recommendations**: `data/recommendations.json` (includes all opportunities, even skipped ones)
- **Historical analysis**: Weekly and monthly summaries

You can review what you missed:
```bash
# See last 10 days of recommendations
cat data/recommendations.json | jq '.[] | select(.date >= "2025-12-01")'

# Check if any EXCELLENT opportunities were skipped
grep "EXCELLENT" logs/daily_notification.log | grep "Skipping"
```

---

## 💡 Tips

1. **First week**: Keep automated notifications as-is to see what qualifies as "exceptional"
2. **Adjust thresholds**: After a week, tune based on your notification volume
3. **On-demand is primary**: Think of automated as "bonus alerts" for rare opportunities
4. **Weekend patterns**: Prices often differ - automated notifications help catch these
5. **Winter vs Summer**: Adjust thresholds seasonally (winter = higher average prices)

---

## 🎯 Summary

**Option B (On-Demand + Smart Automation) Delivered:**

✅ **On-demand notifications** - Personalized, on YOUR schedule
✅ **Smart daily alerts** - Only for exceptional opportunities
✅ **No spam** - Skips normal/average opportunities
✅ **Full control** - You decide when to get advice
✅ **Best of both worlds** - Passive monitoring + active control

**Usage:**
```bash
# Your go-to command when you need to charge
./charge 57 80 --notify

# Automated system watches for special opportunities
# (EXCELLENT ratings, negative pricing, huge savings)
```

This is the 80/20 solution - maximum value with minimal complexity!

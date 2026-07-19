# EV Charging Optimizer - Quick Start Guide

## 🚗 Smart Charge Planner

The easiest way to find the cheapest charging window for your BMW iX1.

### Basic Usage

```bash
# Check optimal charging window from current battery to 80%
python src/scripts/smart_charge_planner.py --current 57 --target 80

# Get a Pushover notification with the plan
python src/scripts/smart_charge_planner.py --current 57 --target 80 --notify

# Charge to a different target (e.g., 70% if that's cheaper)
python src/scripts/smart_charge_planner.py --current 45 --target 70

# Specify a different deadline (default is 08:00 next day)
python src/scripts/smart_charge_planner.py --current 60 --target 80 --deadline "06:00"

# Short form (using aliases)
python src/scripts/smart_charge_planner.py -c 57 -t 80 -d "08:00" -n
```

### Quick Alias (Recommended)

```bash
# Even easier - use the charge wrapper script
./charge 57 80              # Terminal output only
./charge 57 80 --notify     # Terminal + Pushover notification
./charge 57 75 06:00        # Custom target and deadline
```

### What It Does

1. **Calculates** how much energy you need (based on BMW iX1 specs)
2. **Fetches** real-time Octopus Energy Agile prices for next 48 hours
3. **Analyzes** all possible charging windows before your deadline
4. **Recommends** the cheapest option
5. **Shows alternatives** so you can see all your options
6. **Sends Pushover notification** (with `--notify` flag) for mobile access

### Example Output

```
================================================================================
🔋 BMW iX1 SMART CHARGING PLAN
================================================================================

📊 Battery:
   Current: 57.0%
   Target:  80.0%
   Energy needed: 14.9 kWh
   Charging time: 7.2 hours

🎯 Deadline: Wednesday 10 December, 08:00 AM
   Latest start: 12:48 AM

================================================================================
⚡ RECOMMENDED CHARGING WINDOW
================================================================================
🕐 Start:  Tuesday 09:00 PM
🕐 End:    Wednesday 04:12 AM
💰 Cost:   £1.02
📊 Rate:   6.84p/kWh (average)
⭐ Rating: EXCELLENT
✅ Finishes 3.8h before deadline

================================================================================
💡 ALTERNATIVE OPTIONS
================================================================================

Start Now:
   Start: Tuesday 05:43 PM
   Rate:  13.71p/kWh
   Cost:  £2.04
   📈 £1.02 more expensive

2 AM Tomorrow:
   Start: Wednesday 02:00 AM
   Rate:  4.50p/kWh
   Cost:  £0.67
   📉 £0.35 CHEAPER than recommended
   ⚠️  Tight timing - finishes at 09:12 AM (1.2h after deadline)

================================================================================
✅ READY TO CHARGE
================================================================================
👉 Best value: Plug in at 09:00 PM
   (Saves £1.02 vs other options)

💵 Total cost: £1.02
```

### Understanding the Output

- **Recommended Window**: The algorithm's best pick (balances cost + timing)
- **Alternative Options**: Other start times ranked by cost
- **Best value**: The absolute cheapest option that meets your deadline
- **Ratings**: EXCELLENT (90-100), GOOD (70-89), AVERAGE (50-69), POOR (<50)

### Tips

1. **Run it daily** - Prices change daily around 4 PM when Octopus publishes tomorrow's rates
2. **Lower targets save money** - Sometimes 75% is much cheaper than 80%
3. **Flexible deadlines** - If you don't need the car early, later deadlines = cheaper rates
4. **Early morning is cheapest** - 2-6 AM typically has lowest rates (4-5p/kWh)
5. **Avoid 4-7 PM** - Peak demand period (often 25-35p/kWh)

### Vehicle Specs (BMW iX1 xLine)

- **Battery capacity**: 66.5 kWh total, 64.8 kWh usable
- **Your charger**: 2.3 kW (from config.yaml)
- **Efficiency**: ~90% (accounting for charging losses)

**Charging times:**

- 0% → 80%: ~25 hours (51.8 kWh ÷ 2.3 kW ÷ 0.9)
- 20% → 80%: ~18.7 hours (38.9 kWh ÷ 2.3 kW ÷ 0.9)
- 50% → 80%: ~9.4 hours (19.4 kWh ÷ 2.3 kW ÷ 0.9)
- 60% → 80%: ~6.2 hours (13.0 kWh ÷ 2.3 kW ÷ 0.9)

### Advanced Options

```bash
# Specify a different Octopus region
python src/scripts/smart_charge_planner.py -c 57 -t 80 --region "H"

# See help for all options
python src/scripts/smart_charge_planner.py --help
```

### Configuration

Edit `config/config.yaml` to customize:

- **charging_rate_kw**: Your charger power (default: 2.3 kW)
- **region**: Octopus Agile region (default: "H" for Southern England)
- **postcode**: For carbon intensity data (default: "E1")

### Troubleshooting

**"Target must be higher than current"**
→ You're already at or above your target charge

**"Charging requires X hours, which is too long"**
→ Not enough time before deadline - reduce target % or push deadline later

**"Error fetching prices"**
→ Check internet connection or Octopus API status

**"No price data available before target time"**
→ Octopus hasn't published prices yet (typically available after 4 PM for next day)

---

## 📊 Other Tools

### Daily Notification
Automatic daily recommendations at 4 PM (configured in launchd):
```bash
python src/scripts/daily_notification.py
```

### Weekly Summary
Performance review every Sunday at 6 PM:
```bash
python src/scripts/weekly_summary.py
```

### Log a Charge
Record when you actually charged:
```bash
python src/scripts/log_charge.py
```

### Window Analysis
Detailed analysis of price windows:
```bash
python analyze_windows.py
```

---

## 🔋 Real-World Example

**Scenario**: Tuesday 5:43 PM, car at 57%, need 80% by 8 AM Wednesday

**Your options**:

1. **Plug in NOW**: £2.04 (expensive peak rates 6-8 PM)
2. **Wait until 9 PM**: £1.02 (best value - captures overnight cheap rates)
3. **Wait until 2 AM**: £0.67 (absolute cheapest but risky - finishes after 8 AM)

**Smart choice**: Plug in at 9 PM

- Saves £1.02 vs charging now
- Safe margin (finishes 4h before deadline)
- Captures cheapest overnight period (4-7p/kWh)

---

## 💡 Pro Tips

### Target Flexibility
Instead of always charging to 80%, check if 75% or 70% is significantly cheaper:

```bash
# Check all targets
python src/scripts/smart_charge_planner.py -c 57 -t 75
python src/scripts/smart_charge_planner.py -c 57 -t 80
python src/scripts/smart_charge_planner.py -c 57 -t 85
```

If 75% costs £0.80 and 80% costs £1.20, the extra 5% costs £0.40 (40p per 3.2 kWh = 12.5p/kWh). You can decide if it's worth it.

### Weekend vs Weekday
Weekend rates are often different - run the planner to see if Saturday/Sunday charging is cheaper.

### Seasonal Patterns
- **Winter**: Higher demand = higher evening prices
- **Summer**: More solar = lower daytime prices
- **Wind events**: Can cause negative pricing (you get PAID to charge!)

---

**Need help?** Check the [main README](README.md) or [PRD](PRD.md) for full documentation.

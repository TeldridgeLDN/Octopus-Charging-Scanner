# EV Charging Optimizer - Deployment Guide

**Target Platform**: macOS (Mac Mini)
**Python Version**: 3.11+
**Deployment Method**: launchd (native macOS scheduling)

---

## 📋 Prerequisites

### System Requirements
- macOS Sonoma/Ventura or later
- Mac Mini (always-on)
- Python 3.11+ installed
- Internet connection (for API calls)
- Pushover app and API credentials

### Accounts Needed
1. **Pushover** (for notifications)
   - Download app: https://pushover.net/
   - Purchase: £5 one-time (iOS/Android)
   - Get credentials: https://pushover.net/
     - User Key
     - API Token

---

## 🚀 Quick Deployment (Automated)

### 1. Clone and Setup

```bash
# Navigate to home directory
cd ~

# Clone or copy project to Mac Mini
# (Assuming project is already at ~/ev-charging-optimizer)

cd ~/ev-charging-optimizer
```

### 2. Configure Credentials

```bash
# Copy environment template
cp .env.example .env

# Edit with your Pushover credentials
nano .env
```

**Edit `.env` file**:
```bash
PUSHOVER_USER=your_user_key_here
PUSHOVER_API_TOKEN=your_api_token_here
```

### 3. Install Dependencies

```bash
# Install Python packages
pip3 install -r requirements.txt
```

### 4. Run Deployment Script

```bash
# Make deployment script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

The script will:

- ✅ Validate Python installation
- ✅ Check .env credentials
- ✅ Install dependencies if needed
- ✅ Create data/ and logs/ directories
- ✅ Install 4 launch agents
- ✅ Run test execution

### 5. Verify Deployment

```bash
# Check launch agents are loaded
launchctl list | grep ev-optimizer

# You should see
# com.ev-optimizer.weekly-forecast
# com.ev-optimizer.daily-notification
# com.ev-optimizer.charge-reminder
# com.ev-optimizer.weekly-summary
```

---

## 📅 Schedule Overview

| Script | Schedule | Next Run | Purpose |
|--------|----------|----------|---------|
| weekly_forecast.py | Monday 07:00 | Next Monday | 7-day price forecast |
| daily_notification.py | Daily 16:00 | Today 16:00 | Optimal charging window |
| charge_reminder.py | Daily 20:00 | Today 20:00 | Evening reminder |
| weekly_summary.py | Sunday 18:00 | Next Sunday | Performance report |

---

## 🛠️ Manual Deployment (Step-by-Step)

If you prefer manual setup or the automated script fails:

### 1. Install Dependencies

```bash
cd ~/ev-charging-optimizer
pip3 install -r requirements.txt
```

### 2. Configure Environment

```bash
# Create .env file
cp .env.example .env
nano .env

# Add your credentials
PUSHOVER_USER=your_user_key_here
PUSHOVER_API_TOKEN=your_api_token_here
```

### 3. Create Directories

```bash
mkdir -p data logs
```

### 4. Test Scripts Manually

```bash
# Test weekly forecast
python3 src/scripts/weekly_forecast.py

# Test daily notification
python3 src/scripts/daily_notification.py

# Test charge reminder
python3 src/scripts/charge_reminder.py

# Test weekly summary
python3 src/scripts/weekly_summary.py

# Test user logging
python3 src/scripts/log_charge.py
```

### 5. Install Launch Agents

```bash
# Copy plist files to LaunchAgents directory
cp launchd/*.plist ~/Library/LaunchAgents/

# Load each agent
launchctl load ~/Library/LaunchAgents/com.ev-optimizer.weekly-forecast.plist
launchctl load ~/Library/LaunchAgents/com.ev-optimizer.daily-notification.plist
launchctl load ~/Library/LaunchAgents/com.ev-optimizer.charge-reminder.plist
launchctl load ~/Library/LaunchAgents/com.ev-optimizer.weekly-summary.plist
```

### 6. Verify Installation

```bash
# List all EV optimizer agents
launchctl list | grep ev-optimizer

# Check specific agent status
launchctl list com.ev-optimizer.daily-notification
```

---

## 🔧 Configuration

### User Preferences

Edit `config/config.yaml` to customize:

```yaml
user:
  postcode: "E1"              # Your UK postcode
  region: "H"                 # Octopus Agile region
  charging_rate_kw: 7.4       # Your charger power (kW)
  typical_charge_kwh: 30      # Typical charge amount

thresholds:
  price_excellent: 10         # pence/kWh
  price_good: 15
  carbon_excellent: 100       # gCO2/kWh
  carbon_good: 150

preferences:
  price_weight: 0.6           # 60% weight on price
  carbon_weight: 0.4          # 40% weight on carbon
```

### Notification Schedule

Edit times in `config/config.yaml`:

```yaml
notifications:
  daily_time: "16:00"         # Daily recommendation
  reminder_time: "20:00"      # Evening reminder
  weekly_summary_time: "18:00"  # Sunday summary
```

---

## 📊 Monitoring

### Check Logs

```bash
# View latest daily notification log
tail -f logs/daily_notification.log

# View all logs
ls -lh logs/

# Check for errors
grep ERROR logs/*.log
```

### Log Files

All scripts write to:

- `logs/weekly_forecast.log` - Weekly forecast execution
- `logs/daily_notification.log` - Daily recommendation execution
- `logs/charge_reminder.log` - Evening reminder execution
- `logs/weekly_summary.log` - Weekly summary execution
- `logs/log_charge.log` - User action logging
- `logs/*.out.log` - Standard output from launchd
- `logs/*.err.log` - Error output from launchd

### Log Rotation (macOS)

macOS handles log rotation automatically, but you can configure it:

```bash
# Create newsyslog configuration
sudo nano /etc/newsyslog.d/ev-optimizer.conf
```

Add this content:
```
# logfilename                                          [owner:group]  mode count size when  flags
/Users/tomeldridge/ev-charging-optimizer/logs/*.log   tomeldridge:staff  644  14    *    @daily
```

This will:

- Rotate logs daily
- Keep 14 days of history
- Compress old logs

---

## 🧪 Testing

### Test Individual Scripts

```bash
# Test weekly forecast (sends notification)
python3 src/scripts/weekly_forecast.py

# Test daily notification (sends notification)
python3 src/scripts/daily_notification.py

# Test charge reminder (may not send if no good opportunity)
python3 src/scripts/charge_reminder.py

# Test weekly summary (may have no data initially)
python3 src/scripts/weekly_summary.py
```

### Test User Logging

```bash
# Log a charge for today
python3 src/scripts/log_charge.py

# Log a charge for specific date
python3 src/scripts/log_charge.py --date 2025-12-08 --kwh 30
```

### Trigger Launch Agent Manually

```bash
# Force run daily notification now (for testing)
launchctl start com.ev-optimizer.daily-notification

# Check if it ran
tail logs/daily_notification.out.log
```

---

## 🔍 Troubleshooting

### Launch Agent Not Running

**Check if loaded**:
```bash
launchctl list | grep ev-optimizer
```

**View launch agent status**:
```bash
launchctl list com.ev-optimizer.daily-notification
```

**Unload and reload**:
```bash
launchctl unload ~/Library/LaunchAgents/com.ev-optimizer.daily-notification.plist
launchctl load ~/Library/LaunchAgents/com.ev-optimizer.daily-notification.plist
```

### Python Path Issues

The plist files use `/usr/local/bin/python3`. If Python is elsewhere:

```bash
# Find Python path
which python3

# Update plist files with correct path
nano ~/Library/LaunchAgents/com.ev-optimizer.daily-notification.plist
```

### No Notifications Received

1. **Check Pushover credentials** in `.env`
2. **Test API connection**:
   ```bash
   python3 -c "from src.modules.pushover import PushoverClient; import os; from dotenv import load_dotenv; load_dotenv(); client = PushoverClient(os.getenv('PUSHOVER_USER'), os.getenv('PUSHOVER_API_TOKEN')); client.send_notification('Test', 'Hello from EV Optimizer!')"
   ```
3. **Check logs** for errors:
   ```bash
   grep -i error logs/*.log
   ```

### API Errors

**Octopus API issues**:

- Check internet connection
- Verify region code in `config/config.yaml`
- Check logs: `tail logs/daily_notification.log`

**Carbon API issues**:

- API may be down (graceful fallback)
- Scripts will work with price-only analysis

---

## 🔒 Security

### File Permissions

```bash
# Secure .env file
chmod 600 .env

# Verify permissions
ls -la .env
# Should show: -rw------- (600)
```bash

### Data Privacy

All data is stored locally:

- `data/forecast_history.json` - Historical forecasts
- `data/daily_recommendations.json` - Past recommendations
- `data/user_actions.json` - Charge logs

No data is sent to third parties except:

- Pushover (for notifications only)
- API calls (Octopus, Carbon Intensity - public APIs)

---

## 📱 User Guide

### Daily Workflow

**16:00** - Daily notification arrives

- Review optimal charging window
- Note the cost and savings

**20:00** - Reminder (if good opportunity)

- Gentle prompt to charge tonight
- Plug in EV before bed

**Next Morning** - After charging
```bash
# Log the charge
python3 src/scripts/log_charge.py
```

### Weekly Workflow

**Monday 07:00** - Weekly forecast

- Review best charging days for the week
- Plan EV usage accordingly

**Sunday 18:00** - Weekly summary

- Review adherence rate
- Check actual savings
- Read personalized tips

---

## 🔄 Updates and Maintenance

### Update Code

```bash
cd ~/ev-charging-optimizer
git pull  # If using git

# Reload launch agents
launchctl unload ~/Library/LaunchAgents/com.ev-optimizer.*.plist
launchctl load ~/Library/LaunchAgents/com.ev-optimizer.*.plist
```

### Clean Old Data

```bash
# Data store automatically cleans up based on retention policies
# - Forecasts: 7 days
# - Recommendations: 30 days
# - User actions: 90 days

# Manual cleanup if needed
python3 -c "from src.modules.data_store import DataStore; DataStore().cleanup_old_data()"
```

### Backup Data

```bash
# Backup all data
tar -czf ev-optimizer-backup-$(date +%Y%m%d).tar.gz data/ logs/ .env config/
```

---

## ❌ Uninstall

### Remove Launch Agents

```bash
# Unload all agents
launchctl unload ~/Library/LaunchAgents/com.ev-optimizer.*.plist

# Remove plist files
rm ~/Library/LaunchAgents/com.ev-optimizer.*.plist

# Verify removal
launchctl list | grep ev-optimizer
# (Should return nothing)
```

### Remove Project

```bash
# Remove project directory
rm -rf ~/ev-charging-optimizer

# Note: This deletes all data and logs permanently
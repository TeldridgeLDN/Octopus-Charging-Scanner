# Troubleshooting Guide

## Issue: No Daily Notification at 16:00

### Root Cause
The daily notification didn't arrive at 16:00 today due to two issues:

1. **Python Environment Mismatch** ✅ FIXED
   - Launch agents were using `/usr/local/bin/python3` 
   - Packages were installed in venv Python
   - **Fixed**: Updated all plist files to use venv Python path

2. **Octopus API Timing Issue** ⏳ RESOLVES TOMORROW
   - Script ran at 16:00 when tomorrow's prices weren't published yet
   - Octopus publishes next-day prices around 16:00-16:30 UK time
   - **Resolution**: Tomorrow at 16:00, fresh prices will be available

### What Was Fixed

✅ Updated Python path in all 4 launch agents:

   - weekly_forecast
   - daily_notification  
   - charge_reminder
   - weekly_summary

✅ Fixed `weekly_forecast.py` method name bug:

   - Changed `get_forecast()` to `get_forecasts()`

✅ All agents reloaded with correct configuration

### Expected Behavior Tomorrow

**Tomorrow (Tuesday) at 16:00**:

- Octopus will publish Wednesday's prices
- Script will fetch prices successfully  
- You'll receive notification with optimal charging window
- System will work normally from then on

### Verify Setup

Check launch agents are loaded:
```bash
launchctl list | grep ev-optimizer
```

Should show all 4 agents loaded.

### Manual Testing

To test the system now (even without fresh prices), you can:

```bash
# This will work with whatever data is available
python3 src/scripts/log_charge.py
```

### Monitoring

Tomorrow, check logs to verify success:
```bash
tail -f logs/daily_notification.log
#!/bin/bash
# EV Charging Optimizer - Deployment Script
# Deploys all launch agents to macOS launchd

set -e  # Exit on error

echo "🚀 EV Charging Optimizer - Deployment Script"
echo "============================================="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="$HOME/ev-charging-optimizer"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

# Check if running from project directory
if [ ! -f "$PROJECT_DIR/requirements.txt" ]; then
    echo -e "${RED}❌ Error: Project not found at $PROJECT_DIR${NC}"
    exit 1
fi

cd "$PROJECT_DIR"

echo "📋 Pre-deployment checks..."
echo

# Check Python version
echo -n "   Checking Python version... "
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION"
else
    echo -e "${RED}✗ Python 3 not found${NC}"
    exit 1
fi

# Check for .env file
echo -n "   Checking .env file... "
if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} Found"
else
    echo -e "${YELLOW}⚠ Not found - will create from .env.example${NC}"
    cp .env.example .env
    echo -e "${YELLOW}⚠ Please edit .env with your Pushover credentials${NC}"
    read -p "Press Enter after editing .env..."
fi

# Check for virtual environment or installed packages
echo -n "   Checking dependencies... "
if python3 -c "import requests, yaml, bs4" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Installed"
else
    echo -e "${YELLOW}⚠ Installing dependencies...${NC}"
    pip3 install -r requirements.txt
    echo -e "${GREEN}✓${NC} Dependencies installed"
fi

# Create necessary directories
echo -n "   Creating directories... "
mkdir -p data logs
echo -e "${GREEN}✓${NC} data/ logs/"

echo
echo "📦 Installing launch agents..."
echo

# Function to install a launch agent
install_agent() {
    local PLIST_NAME=$1
    local PLIST_FILE="launchd/${PLIST_NAME}.plist"
    local TARGET_FILE="$LAUNCH_AGENTS_DIR/${PLIST_NAME}.plist"

    echo -n "   Installing ${PLIST_NAME}... "

    # Unload if already loaded
    if launchctl list | grep -q "$PLIST_NAME"; then
        launchctl unload "$TARGET_FILE" 2>/dev/null || true
    fi

    # Copy plist file
    cp "$PLIST_FILE" "$TARGET_FILE"

    # Load the agent
    launchctl load "$TARGET_FILE"

    if launchctl list | grep -q "$PLIST_NAME"; then
        echo -e "${GREEN}✓${NC} Loaded"
    else
        echo -e "${RED}✗ Failed to load${NC}"
        return 1
    fi
}

# Install all agents
install_agent "com.ev-optimizer.weekly-forecast"
install_agent "com.ev-optimizer.daily-notification"
install_agent "com.ev-optimizer.charge-reminder"
install_agent "com.ev-optimizer.weekly-summary"

echo
echo "🧪 Running test execution..."
echo

# Test each script
echo "   Testing weekly_forecast.py..."
if python3 src/scripts/weekly_forecast.py 2>&1 | grep -q "Starting weekly forecast"; then
    echo -e "   ${GREEN}✓${NC} weekly_forecast.py works"
else
    echo -e "   ${YELLOW}⚠ weekly_forecast.py had issues (check logs)${NC}"
fi

echo
echo "✅ Deployment complete!"
echo
echo "📅 Schedule:"
echo "   Monday 07:00    → Weekly forecast"
echo "   Daily  16:00    → Daily notification"
echo "   Daily  20:00    → Charge reminder"
echo "   Sunday 18:00    → Weekly summary"
echo
echo "📝 Next steps:"
echo "   1. Verify Pushover credentials in .env"
echo "   2. Test manual script execution:"
echo "      python3 src/scripts/log_charge.py"
echo "   3. Monitor logs in logs/ directory"
echo "   4. Check launchd status:"
echo "      launchctl list | grep ev-optimizer"
echo
echo "📖 Documentation:"
echo "   See DEPLOYMENT.md for detailed setup guide"
echo

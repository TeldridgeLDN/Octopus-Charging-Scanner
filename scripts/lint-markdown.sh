#!/bin/bash
# Markdown linting script - prevents common markdown violations
# Run this before committing markdown files

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Markdown Linting..."
echo "────────────────────────────────────────────"

# Check if Python scripts exist
if [ ! -f "$PROJECT_ROOT/fix_md032.py" ] || [ ! -f "$PROJECT_ROOT/fix_md026.py" ] || [ ! -f "$PROJECT_ROOT/fix_md040.py" ]; then
    echo -e "${RED}❌ Markdown linting scripts not found!${NC}"
    exit 1
fi

# Track violations
total_violations=0
has_errors=0

# MD032: Lists should be surrounded by blank lines
echo ""
echo "Checking MD032 (lists need blank lines)..."
if ! python3 "$PROJECT_ROOT/fix_md032.py" > /tmp/md032_output.txt 2>&1; then
    echo -e "${RED}❌ MD032 check failed${NC}"
    cat /tmp/md032_output.txt
    has_errors=1
else
    violations=$(grep -o 'Summary: [0-9]* violations' /tmp/md032_output.txt | grep -o '[0-9]*' | head -1 || echo "0")
    if [ "$violations" -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Found $violations MD032 violations${NC}"
        total_violations=$((total_violations + violations))
        has_errors=1
    else
        echo -e "${GREEN}✅ No MD032 violations${NC}"
    fi
fi

# MD026: Trailing punctuation in headings
echo ""
echo "Checking MD026 (no trailing punctuation in headings)..."
if ! python3 "$PROJECT_ROOT/fix_md026.py" > /tmp/md026_output.txt 2>&1; then
    echo -e "${RED}❌ MD026 check failed${NC}"
    cat /tmp/md026_output.txt
    has_errors=1
else
    violations=$(grep -o 'Summary: [0-9]* violations' /tmp/md026_output.txt | grep -o '[0-9]*' | head -1 || echo "0")
    if [ "$violations" -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Found $violations MD026 violations${NC}"
        total_violations=$((total_violations + violations))
        has_errors=1
    else
        echo -e "${GREEN}✅ No MD026 violations${NC}"
    fi
fi

# MD040: Fenced code blocks should have language
# TEMPORARILY DISABLED: Script has bug with nested code blocks
echo ""
echo "Checking MD040 (code blocks need language tags)..."
echo -e "${YELLOW}⚠️  MD040 check temporarily disabled (bug in detection script)${NC}"
# if ! python3 "$PROJECT_ROOT/fix_md040.py" > /tmp/md040_output.txt 2>&1; then
#     echo -e "${RED}❌ MD040 check failed${NC}"
#     cat /tmp/md040_output.txt
#     has_errors=1
# else
#     violations=$(grep -o 'Summary: [0-9]* violations' /tmp/md040_output.txt | grep -o '[0-9]*' | head -1 || echo "0")
#     if [ "$violations" -gt 0 ]; then
#         echo -e "${YELLOW}⚠️  Found $violations MD040 violations${NC}"
#         total_violations=$((total_violations + violations))
#         has_errors=1
#     else
#         echo -e "${GREEN}✅ No MD040 violations${NC}"
#     fi
# fi

echo ""
echo "────────────────────────────────────────────"

if [ $has_errors -eq 1 ]; then
    echo -e "${RED}❌ Found $total_violations markdown violations${NC}"
    echo ""
    echo -e "${YELLOW}💡 To fix automatically, run:${NC}"
    echo "  python3 fix_md032.py --fix"
    echo "  python3 fix_md026.py --fix"
    echo "  python3 fix_md040.py --fix"
    echo ""
    exit 1
else
    echo -e "${GREEN}✅ All markdown files are clean!${NC}"
    echo ""
    exit 0
fi

.PHONY: help test lint fmt clean markdown-check markdown-fix all

help:
	@echo "EV Charging Optimizer - Development Commands"
	@echo ""
	@echo "Code Quality:"
	@echo "  make test          - Run all tests"
	@echo "  make lint          - Run linters (black, ruff)"
	@echo "  make fmt           - Format code (black)"
	@echo ""
	@echo "Markdown Quality:"
	@echo "  make markdown-check - Check markdown files for violations"
	@echo "  make markdown-fix   - Auto-fix markdown violations"
	@echo ""
	@echo "All Checks:"
	@echo "  make all           - Run all checks (code + markdown)"
	@echo "  make clean         - Remove cache and temp files"

test:
	@echo "Running tests..."
	python -m pytest tests/ -v

lint:
	@echo "Running Python linters..."
	python -m black --check .
	python -m ruff check .

fmt:
	@echo "Formatting Python code..."
	python -m black .

markdown-check:
	@echo "Checking markdown files..."
	@./scripts/lint-markdown.sh

markdown-fix:
	@echo "Fixing markdown violations..."
	@python3 fix_md032.py --fix
	@python3 fix_md026.py --fix
	@python3 fix_md040.py --fix
	@echo "✅ All markdown files fixed!"

all: lint test markdown-check
	@echo ""
	@echo "✅ All checks passed!"

clean:
	@echo "Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@rm -rf .pytest_cache
	@echo "✅ Cleanup complete!"

# EV Charging Optimizer — Wave 3 Handover (Health & Cleanup)

**Start branch:** cut a new branch off `feature/review-improvements-wave2` (Wave 2 tip,
commit `ab5c6ce`), e.g. `feature/review-improvements-wave3`. Wave 2 is under review in
PR #1 (base `feature/review-improvements`); Wave 3 can proceed in parallel on top of it.

**Ground rules (same as Waves 1–2):** only do what you can fully verify; recompute every
test expectation from first principles; a blocking PostToolUse hook enforces black + ruff
on each edit; never run `launchctl` / install on the live machine without explicit user
sign-off. Suggested method: Fable plans → Opus subagent implements → Fable verifies the
diff → commit.

**Test baseline to expect at start:** `source venv/bin/activate && python -m pytest tests -q`
→ **245 passed, 1 skipped, 1 failed**. The single failure is `test_no_update_for_small_change`
(W3.2 below). No test should hit the network — keep it that way.

---

## New items surfaced during Wave 2 (do these first — they are real latent bugs)

### W3.0a — Null `savings` breaks month/cost aggregation  [Bug, High, S]
Wave 1 made `savings_vs_baseline` `Optional`, so stored daily recommendations can now
persist `"savings": null`. Two consumers then do unguarded arithmetic:
- `src/scripts/weekly_summary.py:94` — `total_savings_potential += rec.get("savings", 0)`.
  `.get("savings", 0)` returns **`None`** when the key exists with a null value (the default
  only applies when the key is absent) → `TypeError: unsupported operand +=` on any week
  containing a forecast-sourced (baseline-less) day.
- `src/modules/cost_tracker.py:95` — same `.get(..., 0)`-returns-None pattern; verify and fix.
- **Fix:** use `(rec.get("savings") or 0)` (treats both missing and null as 0) at both sites;
  grep for any other `.get("savings"` / `savings_vs_baseline` readers and apply the same.
- **Tests:** add a case to the weekly-summary / cost-tracker tests with a rec whose
  `savings` is `null`, asserting no crash and the null contributes 0.

### W3.0b — Reconcile foreign venv in existing launchd plists  [Reliability, Med, S]
`launchd/com.ev-optimizer.daily-notification.plist` (and siblings in `launchd/`) point their
interpreter at a **foreign** venv: `/Users/tomeldridge/my_python_project/scripts/
Momentum_dashboard/venv/bin/python3`. The new `com.ev-optimizer.detect-sessions.plist`
(installed 2026-07-19, scheduled 21:30 daily) correctly uses the repo's own
`venv/bin/python3`. **Fix:** repoint every `launchd/*.plist` interpreter to
`/Users/tomeldridge/ev-charging-optimizer/venv/bin/python3`, then **hand the reinstall
(`cp` to `~/Library/LaunchAgents` + `launchctl unload/load`) to the user** — do not run it
autonomously. One-time check: confirm the repo venv actually has every dependency the
scheduled scripts import (it ran the full test suite, so it should).

---

## Wave 3 items carried over from the original handover

### W3.1 — Duplicate Google Calendar sync logic  [Code-health, Low, S-M]
`daily_notification.py` `sync_to_google_calendar()` (~L560-595 as of Wave 2; re-verify — the
file shifted during Wave 2) duplicates `multi_day_planner.sync_to_calendar()` (~L494-517):
both convert `DayComparison` → dicts and call `client.create_multi_day_events()`.
- **Fix:** extract one shared sync helper (likely into `src/modules/google_calendar.py`) and
  call it from both. `google_calendar.py` is at 0% coverage — adding the helper is a good
  moment to add its first tests.

### W3.2 — Fix the last failing test  [Bug, Med, S]
`tests/test_threshold_tuner.py::TestShouldUpdateThresholds::test_no_update_for_small_change`
— `threshold_tuner` small-change logic returns an update when it should not. Read
`src/modules/threshold_tuner.py` `should_update_thresholds()`, determine from first
principles whether the bug is in the threshold comparison or the test's expectation, fix the
correct side, and confirm green. Do NOT "fix" by loosening the test without understanding it.

### W3.3 — flake8 / mypy / coverage debt  [Health, Low, TIMEBOX]
- flake8 ~480 issues, almost all E501 (line length) in tests; mypy ~75 (mostly missing
  internal-module stubs + a few Optional-default mismatches). **Timebox any blanket sweep** —
  it sprawls. Prefer fixing lint only in files you already touch for W3.0/W3.1/W3.2.
- Coverage ~46% overall. 0%-coverage modules: `automation_triggers.py`, `ev_detector.py`,
  `google_calendar.py`, `recommendation_analyzer.py`. W3.1 naturally lifts `google_calendar.py`.

### W3.5 — Weekly forecast never named best days  [Bug, Med, S]  ✅ DONE (`62b6f4c`)

`weekly_forecast.format_notification()` rendered the "Best days to charge" section only
`if best_days:` where `best_days = score >= 75`. On flat/expensive weeks (all days ≤50) the
push named ZERO charging days — the message's whole purpose. **Fix (format-only, no
`analyze_week` schema change):** top section always renders; ≥75 keeps confident wording
byte-identically, else falls back to top-scored days under "Cheapest days this week"
(score≥50, then `daily_scores[:2]` on all-avoid weeks); avoid section filtered to exclude
any already-shown date (no day in both). +3 tests (flat/good/all-avoid). Suite 255/1/0.

### W3.4 — Untracked docs & root tools  [Housekeeping, Low, S]
Still untracked (pre-existing, NOT Wave 2 output): `docs/archive/` (moved session
summaries), several root guides (`DEPLOYMENT.md`, `PRD.md`, `QUICK_START.md`,
`TROUBLESHOOTING.md`, `NOTIFICATION_GUIDE.md`), root tools (`demo.py`, `analyze_windows.py`,
`calculate_charge_window.py`), and `.taskmaster/`. **User decision:** commit as history,
add to `.gitignore`, or leave local. Also decide whether to commit `docs/WAVE_2_3_HANDOVER.md`
and this file. Nothing here is urgent.

---

## Suggested execution order
1. Cut `feature/review-improvements-wave3` off Wave 2 tip; confirm the 245/1/1 baseline.
2. **W3.0a** (null-savings guards) + **W3.2** (threshold_tuner test) — both small, high-value,
   independent; safe to bundle into one Opus subagent.
3. **W3.1** (calendar sync dedup) — separate pass; touches `google_calendar.py` + two callers.
4. **W3.0b** (plist venv reconcile) — edit files, hand install to user.
5. **W3.3 / W3.4** — opportunistic / user-gated; do not let them sprawl.

## Key references
- Wave 2 memory: `~/.claude/.../memory/project_review_improvements.md`
- Original combined handover: `docs/WAVE_2_3_HANDOVER.md` (Wave 2 sections now done)
- Architecture: `docs/architecture.md`; agile tier: `AGILE_PREDICT_INTEGRATION.md`

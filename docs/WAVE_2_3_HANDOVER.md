# EV Charging Optimizer — Improvement Handover (Waves 2 & 3)

**Branch:** `feature/review-improvements`
**Context:** A code review (2026-07-19) found correctness bugs, reliability gaps, and
cruft. Wave 1 (correctness + security) is DONE on this branch. This doc hands off the
remaining Wave 2 (reliability & user value) and Wave 3 (health) work to a new session.

All line numbers are as of the review; re-verify before editing — Wave 1 shifted some
lines in `analyzer.py` and `daily_notification.py`.

---

## What Wave 1 already did (context for the next agent)

1. **Security** — `config/google_credentials.json` (real Google service-account private
   key) and `*.bak` files added to `.gitignore` (commit "Harden .gitignore…"). Key was
   NOT rotated (user decided gitignore-only; provenance believed clean). If provenance is
   ever in doubt, rotate in Google Cloud Console.
2. **Cost bug** — `analyzer.find_optimal_window` no longer hardcodes 7.4 kW; it takes a
   `charge_rate_kw` param and callers pass the configured rate (2.3 kW). All cost/carbon/
   savings figures are now correct.
3. **Fabricated savings** — `savings_vs_baseline` is now `Optional[float]`; when no real
   evening baseline exists it is `None` and the "save £X" line is omitted rather than
   invented (`* 1.5` / flat `£5` fallbacks removed).
4. **Duplicate notification** — negative-pricing days now send exactly one Pushover
   message instead of two.
5. **Cruft** — ~22 dated session/handover/feature/week summary docs moved to
   `docs/archive/`; one-off `fix_md*.py` scripts deleted. `demo.py`, `analyze_windows.py`,
   `calculate_charge_window.py` kept in root as user tools. Prior uncommitted agile_predict/
   ACIX WIP committed as one "WIP:" commit to give clean bug-fix diffs.

**Known test baseline (pre-existing, NOT introduced by Wave 1):** 2 failing tests —
`test_get_multi_day_prices_falls_back_to_forecast` and `test_no_update_for_small_change`.
The first is fixed as part of W2.1 below.

---

## Wave 2 — Reliability & User Value

Recommended order W2.1 → W2.2 → W2.3 → W2.4. W2.1–2.3 all touch `daily_notification.py`/
`weekly_forecast.py`, so run them sequentially, not in parallel. Suitable for one Opus
subagent bundle (give it the same "only do what you can fully verify / recompute test
expectations from first principles" ground rules Wave 1 used).

### W2.1 — Daily window skips the agile_predict ML tier  [Reliability, High, M]
`src/scripts/daily_notification.py` `fetch_data()` (~line 124-152) falls back
**Octopus → Guy Lipman only** (`fetch_forecast_prices`). `MultiDayPlanner` already uses the
correct 3-tier chain **Octopus → agile_predict → Guy Lipman**. So tonight's actual window
recommendation misses the better ML forecast when Octopus is unpublished.
- **Fix:** insert agile_predict between Octopus and Guy Lipman in `fetch_data()`, mirroring
  `MultiDayPlanner`'s chain. Prefer extracting the planner's fetch logic into a shared
  helper rather than duplicating it.
- **Tests:** add a 3-tier fallback-order test. The pre-existing failure
  `test_get_multi_day_prices_falls_back_to_forecast` lives in this area — fix it here.

### W2.2 — Weekly "best days" ranked by a single cheap slot  [Bug, Med, S-M]
`src/scripts/weekly_forecast.py:79` — `score = analyzer.calculate_price_score(min_price)`
uses only the single cheapest slot's price and ignores the 40% carbon weight, so the
weekly ranking is inconsistent with the daily logic.
- **Fix:** rank by average window price + `analyzer.calculate_opportunity_score(avg_price,
  avg_carbon)` (60/40), matching daily. Update ranking tests.

### W2.3 — Forecast confidence bands not shown for tonight's window  [UX, Med, S-M]
`agile_predict_api.py` already computes p10/p90 bands and `confidence_label()` (~line 159),
but they're only used in the "better day ahead" hint (`daily_notification.py:~273`), never
on the main recommendation. When tonight's window comes from a forecast (not published
Octopus prices), the user gets no reliability signal.
- **Fix:** when the price source is a forecast, append a "Forecast confidence: high /
  moderate / uncertain" line (thresholds already in `config.yaml` →
  `apis.agile_predict.confidence_narrow_threshold` / `confidence_wide_threshold`) to the
  main notification. Give the subagent the exact desired line format. Add format tests for
  both the published-prices and forecast branches.

### W2.4 — Absolute DATA_DIR + schedule detect_sessions  [Reliability + UX, Med]
Two independent pieces:
- **(a) `src/modules/data_store.py:30`** — `DATA_DIR = Path("data")` is relative. If
  launchd's `WorkingDirectory` is ever wrong, all JSON is silently written to the wrong
  place (fresh empty store, no error). **Fix:** resolve to an absolute path at import
  (e.g. `Path(__file__).resolve().parents[2] / "data"`) or accept an env override. Add a
  path test. **One-time check:** confirm existing data files aren't stranded at the old
  relative location after the change. This part is subagent-safe.
- **(b) Monthly savings show £0** — `cost_tracker.aggregate_month()` needs `log_charge.py`
  runs to correlate actions with recommendations. `aggregate_month_from_acix()` (~line 271)
  can automate this from detected sessions, but `detect_sessions.py` is **not scheduled in
  launchd** (verified: no plist references it). **Fix options (USER DECISION):** (i) add a
  launchd plist for `detect_sessions.py`, and/or (ii) call `aggregate_month_from_acix()`
  from `monthly_summary.py`. **Do NOT install/`launchctl load` plists on the live machine
  autonomously** — write the plist and hand the install step to the user.

---

## Wave 3 — Health & Cruft (optional)

### W3.1 — Duplicate Google Calendar sync logic  [Code-health, Low, S-M]
`daily_notification.py:569-594` duplicates `multi_day_planner.py:494-517` (both convert
`DayComparison` → dicts and call `client.create_multi_day_events()`).
`daily_notification.sync_to_google_calendar()` does not delegate to
`planner.sync_to_calendar()`. **Fix:** extract one shared sync helper (likely into
`src/modules/google_calendar.py`) and call it from both.

### W3.2 — Remaining test/lint debt
- Fix the 2nd pre-existing failure `test_no_update_for_small_change` (threshold_tuner
  small-change logic returns an update when it should not).
- flake8 ~480 issues, almost all E501 (line length) in tests; mypy ~75 (mostly missing
  internal-module stubs + a few Optional-default mismatches). Coverage 46% overall;
  `automation_triggers.py`, `ev_detector.py`, `google_calendar.py`,
  `recommendation_analyzer.py` are at 0%. **Timebox** any blanket mypy/flake8 sweep — it
  sprawls. Coverage naturally rises as Wave 2 adds tests.

### W3.3 — docs/archive & untracked docs
`docs/archive/` (moved session summaries) is currently untracked. Decide whether to commit
it as history or leave it local. Several root guides (README, PRD, DEPLOYMENT, QUICK_START,
TROUBLESHOOTING, NOTIFICATION_GUIDE, AGILE_PREDICT_INTEGRATION) were kept.

---

## Suggested execution for the next session
1. Read this file + `AGILE_PREDICT_INTEGRATION.md` + `docs/architecture.md`.
2. Re-establish the test baseline (`source venv/bin/activate && python -m pytest tests -q`).
3. Bundle W2.1 → W2.2 → W2.3 + W2.4(a) into one Opus subagent with the Wave 1 ground rules
   (only do what it can fully verify; recompute test expectations from first principles;
   keep black + ruff clean — a blocking PostToolUse hook enforces formatting on each edit).
4. Keep W2.4(b) launchd install and W3.2 sweeps human-gated.

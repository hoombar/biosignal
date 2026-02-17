# Lessons Learned

Abstract, transferable thinking patterns from mistakes made during development.

---

### Lesson: Verify External API Contracts Before Implementing

**Context**: Implementing fallback logic for HabitSync API when embedded records are missing

**Mistake Pattern**:
- Assumed the offset parameter in `/api/record/{uuid}/simple?offset=N` worked like "days ago" (positive = past)
- Implemented `offset = (today - target_date).days` which produces positive values for past dates
- API actually uses signed offsets: negative = past, positive = future
- Code "worked" (no errors) but returned wrong data (future dates instead of past)

**Epistemological Failure**:
- Did not test the external API directly before implementing
- Trusted assumption about API behavior without verification
- Initial test showed data was being fetched, but didn't verify the *correct* data was returned
- Only discovered when user reported missing data despite "successful" sync

**Better Approach**:
1. Test external API directly first (curl/httpx in REPL) to understand its contract
2. Verify with multiple inputs: what does offset=0, offset=-1, offset=1 return?
3. Check the epochDay in response matches expected date
4. Cross-reference API documentation if available

**Applies To**:
- Any external API integration
- Any parameter where direction/sign matters (offsets, deltas, increments)
- Pagination APIs (page vs offset vs cursor)
- Date/time APIs (timezone offsets, epoch timestamps)

---

### Lesson: SQLAlchemy merge() Requires Primary Key for Upsert

**Context**: Upserting HabitSync habit records during backfill sync

**Mistake Pattern**:
- Used `session.merge(habit)` expecting SQLAlchemy to match on unique constraint (date + habit_name)
- Model has auto-increment `id` as primary key, not a composite primary key
- `merge()` only matches on primary key - new objects without `id` are treated as INSERTs
- INSERT failed with UNIQUE constraint violation, transaction rolled back
- Raw response update also rolled back, making it appear sync never happened

**Epistemological Failure**:
- Assumed `merge()` works like database UPSERT (matches on unique constraints)
- Did not verify merge behavior in SQLAlchemy docs
- Error was logged but not surfaced clearly (sync_log showed "success" because Garmin succeeded)
- Didn't check the actual database state to verify data was written

**Better Approach**:
1. Understand SQLAlchemy `merge()` semantics: it only merges on primary key
2. For upsert on unique constraint, use dialect-specific `insert().on_conflict_do_update()`
3. Always check database state after sync to verify data was actually written
4. Design models with appropriate primary keys if upsert-by-unique-constraint is needed

**Applies To**:
- Any ORM upsert operation
- Understanding difference between application-level merge vs database-level upsert
- Transaction rollback cascades (one failure can undo unrelated changes in same transaction)

---

### Lesson: Server Restart Required After Code Changes (No Hot Reload)

**Context**: Testing fix for HabitSync offset calculation

**Mistake Pattern**:
- Made code fix, ran backfill, expected new behavior
- Forgot that FastAPI server was running without hot-reload
- Server still had old bytecode cached in memory
- Test script (running fresh Python process) showed correct behavior
- Server (running old code) showed incorrect behavior
- Confusion between "code is correct" vs "server is running correct code"

**Epistemological Failure**:
- Verified fix by running standalone Python test, not by testing through the server
- Assumed server would pick up changes automatically
- Didn't verify server was actually using updated code

**Better Approach**:
1. After code changes, explicitly restart the server (or use `--reload` in development)
2. Clear `__pycache__` directories if uncertain about bytecode state
3. Verify through the actual execution path (API call), not just unit test
4. Add logging that shows code version or key parameter values to confirm correct code is running

**Applies To**:
- Any interpreted language without hot-reload enabled
- Docker containers with cached layers
- Any system with caching (bytecode, config, memoization)

---

### Lesson: "Success" Status Can Mask Partial Failures

**Context**: Backfill showing "success" but HabitSync data not saved

**Mistake Pattern**:
- Backfill endpoint returned success, UI showed completion
- Actual sync_log showed `overall_success: true` because Garmin sync succeeded
- HabitSync sync had `success: false` with error details, but this was buried in JSON
- User saw "success" and assumed all data was synced
- Had to dig into sync_log.details JSON to find the actual HabitSync error

**Epistemological Failure**:
- Trusted high-level success indicator without examining component status
- UI didn't surface partial failures clearly
- "Success" was defined as "Garmin succeeded" rather than "all components succeeded"

**Better Approach**:
1. Define success criteria explicitly (all components vs any component)
2. Surface partial failures in UI (warnings, not just success/fail)
3. When investigating sync issues, check component-level status, not just overall status
4. Log errors prominently, not just in nested JSON details

**Applies To**:
- Any multi-step operation with independent components
- Aggregated status indicators (build pipelines, deploy stages)
- Any system where "success" is a simplification of complex state

---

---

### Lesson: Audit All Instances When Fixing a Class of Bug

**Context**: Discovering the SpO2 parser was missing data; later discovering stress data had a similar but different timestamp bug.

**Mistake Pattern**:
- SpO2 data was missing from DB — found the parser bug, fixed it, moved on.
- Later: stress data was also missing, with a related but distinct root cause (wrong timestamp interpretation vs. missing endpoint entirely).
- Each bug was found reactively (user noticed missing data) rather than proactively.
- When SpO2 was fixed, we did not scan other parsers to ask "does this class of error exist elsewhere?"

**Epistemological Failure**:
- Treated the bug as a one-off rather than a symptom of a class of error.
- Closed the loop at the symptom level ("SpO2 is fixed") rather than the pattern level ("all parsers correctly handle Garmin response formats").
- No regression guard was added to catch the same bug in other parsers.

**Better Approach**:
1. When fixing a bug, immediately ask: "Does this bug pattern exist anywhere else?"
2. Scan all siblings (all parsers, all API integrations, all format handlers) for the same issue.
3. Write a regression test that makes the whole class of bug visible — e.g., test all parsers return timestamps within a reasonable year range.
4. Document the pattern in lessons learned at fix time, not after the next occurrence.

**Applies To**:
- Any repeated code pattern (parsers, serializers, validators, format handlers)
- Data pipeline stages (ingest → parse → store → display)
- Any integration that depends on implicit format contracts

---

### Lesson: Timestamp Format Contracts Must Be Explicit and Verified

**Context**: `parse_stress()` treating absolute epoch ms timestamps as relative millisecond offsets from `startTimestampGMT`.

**Mistake Pattern**:
- Garmin's `stressValuesArray` format is `[epoch_ms, stress_level]` — identical to `heartRateValues` and `bodyBatteryValuesArray`.
- Implementation assumed the first element was a *relative offset* from a start timestamp (common in some APIs).
- The code added the "offset" to `startTimestampGMT`, producing timestamps 1.9 million minutes in the future (year 2082).
- 19,270 stress samples written with wrong timestamps; none appeared in any query (all date-range filtered).
- Bug was silent — no error, no warning, just invisible data.

**Epistemological Failure**:
- Did not cross-reference `stressValuesArray` format against other Garmin array types that were correctly implemented.
- Trusted code review ("looks right") over testing against real data.
- Did not assert reasonable year bounds on parsed timestamps in tests.
- The year-2082 data sat in the DB unnoticed until the user reported no stress data.

**Better Approach**:
1. When implementing a data parser, verify the timestamp format against a known good example (real API response or captured fixture).
2. Add a sanity check assertion in tests: timestamps must fall within a reasonable range (e.g., `assert 2020 <= timestamp.year <= 2030`).
3. Cross-reference: if other parsers in the same file handle similar arrays, confirm the format is consistent before assuming a different convention.
4. After a sync, spot-check the DB: `SELECT MIN(timestamp), MAX(timestamp) FROM <table>` catches out-of-range data immediately.

**Applies To**:
- Any parser handling external timestamp data (epoch ms, epoch seconds, relative offsets, ISO strings, Unix ms vs. seconds)
- Any integration with inconsistent data formats across endpoints
- Any silent data pipeline where errors don't surface until the user reports missing data

---

### Lesson: `datetime.utcnow()` Is Deprecated — Always Use Timezone-Aware UTC

**Context**: Running tests surfaced `DeprecationWarning: datetime.datetime.utcnow() is deprecated` across `app/api/sync.py` and `app/services/sync.py`.

**Mistake Pattern**:
- Used `datetime.utcnow()` throughout sync code to generate timestamps.
- This returns a naive datetime with no timezone info — ambiguous by construction.
- Python 3.12+ deprecates `utcnow()` and will remove it in a future version.
- The warnings don't break anything today, but they signal intent to fail in a future Python version.

**Better Approach**:
Replace `datetime.utcnow()` with `datetime.now(UTC)`:
```python
from datetime import datetime, UTC
# Instead of:
datetime.utcnow()
# Use:
datetime.now(UTC)
```

Note: if storing in SQLite (which has no timezone column type), strip tzinfo at the storage boundary only, not at the computation boundary. Keep timezone awareness as deep into the stack as possible.

**Applies To**:
- Any use of `datetime.utcnow()`, `datetime.now()` (without tz), or `time.time()` that needs to produce UTC
- Cross-platform code that may run in different system timezones
- Any codebase that will be upgraded across Python minor versions

---

### Lesson: Don't Assume First Element Is Representative in Sparse Data

**Context**: Correlation analysis using feature names from the first day with target habit.

**Mistake Pattern**:
- Code extracted feature names from `target_data[0]` to determine which metrics to correlate
- Assumed the first day with the target habit would have all available features
- After backfill, earliest days with habits often predate Garmin data
- First day had only `had_training` feature; Garmin metrics like `sleep_hours`, `hrv_overnight_avg` were missing
- Correlation results showed only habit-to-habit correlations, no Garmin metrics
- Bug was silent — no error, just incomplete results

**Epistemological Failure**:
- Assumed data completeness without verifying
- Used a single sample to infer the schema of a heterogeneous dataset
- Didn't test with sparse/partial data scenarios
- Only discovered when user reported missing Garmin correlations

**Better Approach**:
1. When inferring schema from data, collect keys from ALL records, not just the first
2. Test with realistic sparse data: early records with partial data, later records complete
3. For optional fields, the presence in ANY record should make it available for analysis
4. Consider: "What if the first N records are incomplete?"

**Code Pattern**:
```python
# Bad: assumes first record has all features
feature_names = list(data[0].keys())

# Good: collects features from all records
all_features = set()
for record in data:
    all_features.update(record.keys())
feature_names = list(all_features)
```

**Applies To**:
- Any schema inference from sample data
- Time-series data where early records may be incomplete
- Data aggregation across sources with different availability windows
- Any "union of schemas" scenario

---

## Meta-Pattern: The Verification Cascade

These four lessons follow a pattern - each failure could have been caught earlier with proper verification:

1. **API Contract** - Test external API before integrating
2. **ORM Behavior** - Verify ORM operation semantics match expectations
3. **Runtime State** - Confirm running code matches source code
4. **Status Accuracy** - Validate success indicators reflect actual state

**The Cascade**:
```
External API → ORM Layer → Runtime → Status Reporting → User Perception
```

A bug at any layer propagates to user perception as "it doesn't work" without clear indication of where the failure occurred. Defense in depth means verifying at each layer.

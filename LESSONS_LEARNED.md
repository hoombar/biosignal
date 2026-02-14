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

# Claude Development Guide - Biosignal Energy Tracker

## Project Overview

**Purpose**: Self-hosted biometric analysis dashboard that correlates Garmin health data with lifestyle habits to identify patterns related to afternoon energy slumps and brain fog.

**Tech Stack**:
- Backend: FastAPI (async) + SQLAlchemy (async) + SQLite
- Frontend: Jinja2 templates + vanilla JavaScript + Chart.js
- Integrations: Garmin Connect API, HabitSync API
- Deployment: Docker + Docker Compose on Synology NAS

**Architecture Pattern**: Service-layer architecture with clear separation:
- `/app/models` - SQLAlchemy ORM models
- `/app/schemas` - Pydantic request/response models
- `/app/services` - Business logic (Garmin client, feature computation, analysis)
- `/app/api` - FastAPI endpoint handlers (thin, delegate to services)

---

## Core Development Philosophy

### Epistemological Rigor: How Do You KNOW?

**Never claim something is "fixed" or "working" without evidence.**

#### Levels of Certainty (Weakest → Strongest)

1. **"Looks right" / Code review only** → ❌ INSUFFICIENT
2. **"Runs without errors"** → ⚠️ WEAK (absence of error ≠ correctness)
3. **"Manual test passed"** → ⚙️ MODERATE (one data point, not reproducible)
4. **"Automated tests pass"** → ✅ STRONG (reproducible verification)
5. **"Tests pass + cross-referenced with ground truth"** → ✅✅ STRONGEST (verified against oracle)

#### Always State Your Certainty Level Explicitly

**Bad**: "Fixed the HabitSync upsert issue"

**Good**: "Fixed the HabitSync upsert issue (Certainty: STRONG)
- Proof: `test_habitsync_upsert.py::test_duplicate_habits` now passes
- Verified: Manual test in browser shows no duplicate habits created
- Cross-referenced: HabitSync API docs confirm upsert endpoint returns `updated_at` timestamp on update"

#### Ground Truth Sources for This Project

- **Garmin Connect API**: Official documentation (primary source)
- **HabitSync API**: Actual responses captured in development (verify against docs)
- **SQLite Database**: Direct query results (`SELECT * FROM ...`)
- **Browser DevTools**: Network tab (actual API calls), Console (actual errors)
- **Test Assertions**: Expected vs actual values in pytest output

**Rule**: When in doubt, verify against the authoritative source. Blog posts, Stack Overflow, and AI-generated examples are secondary sources.

---

## Multi-Perspective Development Framework

When making decisions, consider all five perspectives. **No single perspective always wins** - balance is context-dependent.

### 🔒 Security Engineer Perspective

**Ask**: "What could go wrong if this is exploited?"

- **Input Validation**: All API endpoints must use Pydantic schemas (no raw `request.json`)
- **SQL Injection**: Use SQLAlchemy ORM exclusively (no raw SQL strings with user input)
- **Authentication**: Garmin tokens stored in `/data/.garmin_tokens` with restrictive permissions
- **Secrets Management**: API keys via environment variables (never hardcode)
- **OWASP Top 10**: Be aware of common vulnerabilities (XSS in templates, CSRF on state-changing endpoints)

**Red Flags**:
- Using `eval()`, `exec()`, or shell commands with user input
- Constructing SQL queries with string concatenation
- Storing secrets in code or config files
- Missing input validation on API boundaries

### 🏗️ Senior Engineer Perspective

**Ask**: "Will this be maintainable in 6 months?"

- **SOLID Principles**:
  - Single Responsibility: Services do one thing well
  - Open/Closed: Extend via new services, not modifying existing ones
  - Dependency Inversion: Depend on abstractions (database session), not concretions
- **Service Layer Pattern**: Keep API handlers thin (5-20 lines) - delegate to services
- **Async/Await**: This codebase is async - don't block the event loop (no `requests`, use `httpx`)
- **Database Optimization**: Use indexes on frequently filtered columns (date ranges, habit names)
- **DRY Principle**: Extract common patterns, but avoid premature abstraction (Rule of Three: duplicate twice, abstract on third occurrence)

**Code Organization**:
```
New feature checklist:
1. Model in /app/models (if new data)
2. Schema in /app/schemas (request/response)
3. Service in /app/services (business logic)
4. API endpoint in /app/api (thin handler)
5. Tests in /tests (TDD - write first!)
```

### 🧪 Test Engineer Perspective

**Ask**: "How will we know if this breaks in the future?"

**TDD Workflow** (mandatory for new features):
1. Write failing test first
2. Implement minimum code to pass
3. Refactor while keeping tests green
4. Commit with test + implementation together

**Test Pyramid**:
- **Unit Tests** (most): Test individual functions/methods in isolation
- **Integration Tests** (some): Test service layer with real database (use test fixtures)
- **E2E Tests** (few): Test API endpoints end-to-end

**Async Testing**:
```python
import pytest
from app.core.database import get_session

@pytest.mark.asyncio
async def test_feature_computation():
    async for session in get_session():
        # Test async code here
        result = await compute_feature(session, date="2024-01-15")
        assert result.sleep_hours > 0
```

**Mock External APIs**:
```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
@patch('app.services.garmin.GarminConnect')
async def test_garmin_sync(mock_garmin):
    mock_garmin.return_value.get_sleep_data = AsyncMock(return_value={"sleepTimeSeconds": 28800})
    # Test your code's logic, not Garmin's API
```

**Current Pain Point**: This project has ~3% test coverage. All new code must include tests.

### 🎨 Designer Perspective

**Ask**: "Is this usable and accessible?"

- **Accessibility**: Use semantic HTML (`<button>` not `<div onclick>`), ARIA labels where needed
- **Responsive Design**: Test at mobile widths (320px, 768px, 1024px)
- **Error States**: Show user-friendly error messages (not raw exceptions)
- **Loading States**: Show spinners/skeleton screens during async operations
- **Progressive Enhancement**: Core functionality works without JavaScript

**UI Checklist**:
- [ ] Works on mobile (test in DevTools responsive mode)
- [ ] Error messages are helpful ("Failed to sync Garmin data" not "500 Internal Server Error")
- [ ] Loading indicators prevent confusion during waits
- [ ] Keyboard navigation works (tab through interactive elements)

### 📊 Product Owner Perspective

**Ask**: "Does this deliver user value completely?"

- **Feature Completeness**: Don't ship half-finished features (boy scout principle applies)
- **Edge Cases**: Test with missing data (no sleep data for a day, HabitSync API down)
- **Data Integrity**: Ensure sync operations are idempotent (re-running doesn't duplicate data)
- **Performance**: Dashboard should load in <2 seconds (profile with DevTools Performance tab)
- **User Validation**: Does this actually help identify energy patterns? Test with real data

**Definition of Done**:
- Feature works with real data (not just mocked)
- Edge cases handled gracefully
- User can complete their goal without errors
- Performance meets expectations

---

## Boy Scout Principle (Pragmatic)

**"Leave code better than you found it" - but complete the work.**

### What This Means

✅ **DO**:
- Fix bugs completely (with tests)
- Refactor messy code you're already touching
- Add missing error handling to code you're modifying
- Improve variable names for clarity
- Extract duplicated logic into reusable functions

❌ **DON'T**:
- Leave TODO comments ("TODO: Fix this later" = abandoned work)
- Start refactoring unrelated code and leave it incomplete
- Add features beyond the current scope
- Make partial improvements that create inconsistency

### The Rule

**If you can't improve something completely in this session, don't touch it.**

Quality improvements must be finished, not partial. An incomplete refactoring is worse than the original messy code because it signals broken intent.

**Exception**: If you discover a critical bug while working on something else, fix it immediately (with test) even if unrelated to current task.

---

## Perseverance Over Settling

**Don't accept workarounds without understanding root problems.**

### When Stuck

1. **Dig Deeper**: Question your assumptions. What do you think is true that might not be?
2. **Switch Strategies**: If approach A isn't working after 3 attempts, try approach B (don't stubbornly repeat)
3. **Think Outside the Box**: Challenge the problem statement. Is there a better way to achieve the goal?
4. **Push Back**: If something seems excessively difficult, consider if there's a simpler alternative approach

### Example: SQLite Concurrency Issues

**Bad (Settling)**: "SQLite is slow, let's just add `time.sleep(0.5)` retries and hope it works"

**Good (Persevering)**:
1. Understand root cause: SQLite locks entire database on writes
2. Research solutions: WAL mode, connection pooling, proper async usage
3. Test hypothesis: Enable WAL mode and verify lock contention reduced
4. If still blocked: Consider if PostgreSQL is justified, or if problem is actually query inefficiency

### Red Flags (You're Settling)

- Adding `try/except: pass` without understanding why it fails
- Using workarounds like sleeps, manual retries, or arbitrary delays
- Saying "it works on my machine" without understanding why it fails elsewhere
- Implementing features that don't actually solve the user's problem

---

## Mistake Management Protocol

**When you make a mistake, turn it into a learning asset.**

### The 6-Step Process

1. **Fix It Completely** - No partial fixes, no bandaids
2. **Prove the Fix** - Demonstrate how you KNOW it's fixed (see Epistemological Rigor above)
3. **Document the Meta-Lesson** - Add to `LESSONS_LEARNED.md` (see format below)
4. **Write Preventive Test** - Ensure similar mistakes are caught automatically in future
5. **Scan for Patterns** - Check if same flawed thinking exists elsewhere in codebase
6. **Leave Code Better** - Apply boy scout principle to related code

### LESSONS_LEARNED.md Format

**Focus**: Abstract, transferable thinking patterns (not code-specific details)

**Example Entry**:
```markdown
### Lesson: Timezone-Aware DateTime Arithmetic

**Context**: When performing datetime calculations across timezones

**Mistake Pattern**:
- Computed "hours since midnight" by subtracting timestamps
- Forgot that midnight in user's timezone ≠ midnight UTC
- Tests passed because mock data didn't cross DST boundaries
- Production failed during DST transition

**Epistemological Failure**:
- Assumed datetime math is simple (it's not with timezones)
- Didn't test edge cases (DST transitions, timezone boundaries)
- Trusted intuition over cross-referencing datetime library docs

**Better Approach**:
1. Always be explicit about timezone (UTC vs local)
2. Test datetime logic at DST boundaries (March/November)
3. Use libraries correctly (`.astimezone()`, not manual offset math)
4. Cross-reference: Python datetime docs, timezone database

**Applies To**:
- Any datetime arithmetic
- Currency conversions
- Floating-point comparisons
- Any domain with subtle edge cases
```

**NOT this** (too specific):
```markdown
Fixed bug in features.py line 342 where I used .hour instead of .astimezone().hour
```

---

## Project-Specific Guardrails

### Current Pain Points & Solutions

#### 1. UI-Level Feedback Loops (🔥 Top Priority)

**Problem**: Bugs discovered late in UI because no tests caught them earlier

**Solution**: **Test-Driven Development (mandatory)**
- Write test first, watch it fail, implement, watch it pass
- Bug fixes start with reproduction test
- No PR without tests (self-enforcement)

**Example**:
```python
# Step 1: Write failing test
@pytest.mark.asyncio
async def test_body_battery_drain_rate():
    features = await compute_features(date="2024-01-15")
    assert features["body_battery_drain_rate_morning"] < 50  # Should be realistic drain

# Step 2: Run test (it fails because feature not implemented)

# Step 3: Implement feature in services/features.py

# Step 4: Run test (now passes) → PROOF it works
```

#### 2. Integration Fragility (Garmin, HabitSync)

**Problem**: Recent git history shows repeated auth fixes, upsert issues

**Solution**:
- **Mock External APIs in Tests**: Test your logic, not their API
- **Capture Real Responses**: Use actual API responses as test fixtures (in `/tests/fixtures`)
- **Cross-Reference Docs**: Always verify against official API documentation (not blog posts)
- **Error Handling**: Test error cases (API down, timeout, malformed response)

**Example**:
```python
# Good: Mock Garmin API to test our parser logic
@patch('app.services.garmin.GarminConnect')
async def test_parse_sleep_data(mock_garmin):
    # Use actual response from Garmin (captured in fixtures/garmin_sleep.json)
    with open('tests/fixtures/garmin_sleep.json') as f:
        mock_garmin.return_value.get_sleep_data = AsyncMock(return_value=json.load(f))

    result = await sync_sleep_data(date="2024-01-15")
    assert result.deep_sleep_seconds > 0  # Our parser works
```

#### 3. SQLite Concurrency

**Problem**: Database locked errors under concurrent API calls

**Solutions** (in priority order):
1. Enable WAL mode (write-ahead logging)
2. Configure connection pooling properly (`pool_size`, `max_overflow`)
3. Optimize queries (indexes on date ranges)
4. Profile with `EXPLAIN QUERY PLAN` to find slow queries

**Don't Settle**: Adding arbitrary sleeps/retries masks the problem without fixing it.

#### 4. Timezone Complexity (`features.py`)

**Problem**: Complex UTC/local timezone conversions in feature computation

**Solution**:
- Centralize datetime utilities (create `app/utils/datetime.py`)
- Test at DST boundaries (March 2nd, November 1st)
- Be explicit: Use `datetime.now(tz=...)` not `datetime.now()` (naive datetimes are bugs waiting to happen)

---

## Code Quality Checklist

**Before marking work complete, verify:**

### Epistemological Verification

- [ ] **How do I KNOW this works?** (State certainty level + proof)
- [ ] Tests written and passing (see test output)
- [ ] Manual verification performed (describe what you tested)
- [ ] Cross-referenced with ground truth (API docs, database query, etc.)

### Boy Scout Principle

- [ ] No abandoned TODO comments
- [ ] Related code improved (if touched)
- [ ] No partial refactorings left incomplete

### Security

- [ ] Input validated (Pydantic schema on API endpoint)
- [ ] No SQL injection risk (ORM only, no string concatenation)
- [ ] No secrets in code (env vars only)

### Testing

- [ ] TDD followed (test written first for new features)
- [ ] Async tests use `pytest-asyncio`
- [ ] External APIs mocked
- [ ] Edge cases tested (missing data, API errors, timezone boundaries)

### Code Quality

- [ ] Service layer pattern followed (thin handlers, logic in services)
- [ ] Async/await used correctly (no blocking calls)
- [ ] Error handling added (don't silently swallow exceptions)
- [ ] Documentation updated (docstrings for complex functions)

### User Experience

- [ ] Error messages are user-friendly
- [ ] Loading states shown during async operations
- [ ] Works on mobile (tested in responsive mode)
- [ ] Performance acceptable (<2s page load)

---

## Testing Philosophy

### Test-Driven Development (TDD)

**Red → Green → Refactor**

1. **Red**: Write a failing test that defines desired behavior
2. **Green**: Write minimal code to make test pass
3. **Refactor**: Improve code while keeping tests green

**Why TDD?**
- Tests become proof of correctness (epistemological tool)
- Prevents regression (future changes won't break this)
- Forces you to think about edge cases upfront
- Catches bugs before they reach UI

### Test Coverage Goals

- **New Features**: 100% coverage (all new code has tests)
- **Bug Fixes**: Reproduction test mandatory
- **Existing Code**: Opportunistically add tests when modifying (boy scout principle)

### Testing Patterns for This Project

See `TESTING_GUIDE.md` for detailed examples of:
- Async database tests with pytest-asyncio
- Mocking Garmin/HabitSync APIs
- Fixture setup for datetime-based tests
- Integration tests with test database

---

## Supporting Documentation

This guide references these additional files:

- **`LESSONS_LEARNED.md`**: Abstract meta-learnings (epistemological failures, thinking patterns)
  - NOT code-specific ("fixed line 42")
  - YES transferable principles ("always verify external API contracts")

- **`TESTING_GUIDE.md`**: Project-specific testing patterns
  - Async test setup
  - Mocking external APIs
  - Database fixtures
  - Datetime test utilities

- **`ARCHITECTURE.md`**: Design decisions and rationale
  - Why SQLite (portability for Synology NAS)
  - Why service layer pattern
  - Why vanilla JS (simplicity, no build tooling)

---

## Quick Reference

### Decision Framework

When stuck on a decision, ask:

1. **🔒 Security**: Is this safe? (input validation, no injection risks)
2. **🧪 Testability**: Can I prove this works? (write test first)
3. **🏗️ Maintainability**: Will I understand this in 6 months? (clear naming, simple logic)
4. **🎨 Usability**: Is this user-friendly? (error messages, loading states)
5. **📊 Value**: Does this solve the actual problem? (not just a workaround)

**No single perspective wins** - balance based on context. Document your reasoning.

### Verification Standards

| Claim | Required Proof |
|-------|---------------|
| "Fixed bug X" | Reproduction test + test now passes + manual verification |
| "Added feature Y" | Unit tests + integration test + manual UI test |
| "Refactored Z" | All existing tests pass + no behavior change |
| "API integration works" | Mock test + real API test + matches docs |

### When to Update LESSONS_LEARNED.md

- ✅ You made an incorrect assumption (document the thinking pattern)
- ✅ You skipped a verification step and it caused a bug
- ✅ You learned a better approach to a common problem
- ❌ You fixed a typo (too trivial)
- ❌ You changed a specific line of code (too specific)

---

**Remember**: This guide exists to prevent pain (UI-level feedback loops, integration fragility, false confidence). Use it as a thinking tool, not a rulebook. The goal is better code through better thinking.

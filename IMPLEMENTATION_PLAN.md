# Energy Correlation Tracker — Implementation Plan

> This document is a step-by-step build guide designed to be followed across multiple
> coding sessions by an AI coding agent. Each phase is independently testable.
> Check off items as they are completed.

---

## Project Structure

```
energy-tracker/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, lifespan, mount static/templates
│   ├── api/
│   │   ├── __init__.py
│   │   ├── sync.py              # POST /api/sync/*, GET /api/sync/status
│   │   ├── raw.py               # GET /api/raw/{type}
│   │   ├── daily.py             # GET /api/daily, GET /api/habits
│   │   ├── analysis.py          # GET /api/correlations, /patterns, /insights
│   │   ├── export.py            # GET /api/export, /export/timeseries, /export/metadata
│   │   └── config.py            # GET/PUT /api/config, GET /api/health
│   ├── models/
│   │   ├── __init__.py
│   │   └── database.py          # SQLAlchemy ORM models for all tables
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── responses.py         # Pydantic response models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── garmin.py            # Garmin API client wrapper
│   │   ├── habitsync.py         # HabitSync API client wrapper
│   │   ├── sync.py              # Sync orchestration (calls garmin.py + habitsync.py)
│   │   ├── parsers.py           # Parse raw API JSON into DB rows
│   │   ├── features.py          # Compute derived features from raw data
│   │   ├── analysis.py          # Correlation, pattern detection, insights
│   │   └── scheduler.py         # APScheduler cron job setup
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Pydantic Settings (env vars)
│   │   └── database.py          # SQLAlchemy engine, async session factory
│   └── templates/
│       ├── base.html            # Layout shell
│       ├── overview.html        # FR3.1
│       ├── daily.html           # FR3.2
│       ├── correlations.html    # FR3.3
│       ├── trends.html          # FR3.4
│       └── insights.html        # FR3.5
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── overview.js
│       ├── daily.js
│       ├── correlations.js
│       ├── trends.js
│       └── insights.js
├── migrations/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── tests/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_parsers.py
│   ├── test_features.py
│   ├── test_analysis.py
│   ├── test_api_sync.py
│   ├── test_api_export.py
│   └── fixtures/               # Sample Garmin/HabitSync JSON responses
│       ├── garmin_sleep.json
│       ├── garmin_heart_rate.json
│       ├── garmin_body_battery.json
│       ├── garmin_stress.json
│       ├── garmin_hrv.json
│       ├── garmin_spo2.json
│       ├── garmin_steps.json
│       ├── garmin_activities.json
│       └── habitsync_response.json
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── requirements.txt
└── pyproject.toml
```

---

## Phase 1: Project Scaffolding & Configuration

**Goal:** Runnable FastAPI app with health check endpoint, all config wired up.

### Steps

- [ ] **1.1** Create `pyproject.toml` with project metadata and dependencies:
  ```
  dependencies:
    fastapi>=0.115
    uvicorn[standard]>=0.30
    sqlalchemy[asyncio]>=2.0
    aiosqlite>=0.20
    alembic>=1.14
    garminconnect>=0.2.38
    httpx>=0.27
    apscheduler>=3.10,<4
    pydantic-settings>=2.0
    jinja2>=3.1
    python-multipart>=0.0.7
    numpy>=1.26
    scipy>=1.12
  ```
- [ ] **1.2** Create `requirements.txt` that mirrors pyproject.toml deps (for Docker).
- [ ] **1.3** Create `app/__init__.py` (empty).
- [ ] **1.4** Create `app/core/__init__.py` (empty).
- [ ] **1.5** Create `app/core/config.py`:
  - Use `pydantic_settings.BaseSettings` with `model_config = SettingsConfigDict(env_file=".env")`.
  - Fields:
    - `db_path: str = "/data/energy_tracker.db"`
    - `garmin_email: str`
    - `garmin_password: str`
    - `garmin_token_dir: str = "/data/.garmin_tokens"`
    - `habitsync_url: str`
    - `habitsync_api_key: str`
    - `tz: str = "Europe/London"`
    - `sync_hour: int = 6`
    - `sync_minute_garmin: int = 0`
    - `sync_minute_habitsync: int = 15`
    - `debug: bool = False`
  - Create a module-level function `get_settings()` that returns a cached `Settings()` instance.
- [ ] **1.6** Create `app/core/database.py`:
  - Create async engine with `create_async_engine(f"sqlite+aiosqlite:///{settings.db_path}")`.
  - Create `async_sessionmaker` bound to engine.
  - Create `Base = declarative_base()`.
  - Create an `async def get_db()` dependency generator that yields a session.
  - Create `async def init_db()` that calls `Base.metadata.create_all()` using `run_sync`.
- [ ] **1.7** Create `app/main.py`:
  - Use `@asynccontextmanager` lifespan to call `init_db()` on startup.
  - Mount `StaticFiles` at `/static`.
  - Set up `Jinja2Templates` pointing at `app/templates`.
  - Include a single router from `app/api/config.py` for now.
- [ ] **1.8** Create `app/api/__init__.py` (empty).
- [ ] **1.9** Create `app/api/config.py`:
  - `GET /api/health` → returns `{"status": "ok", "version": "0.1.0"}`.
  - `GET /api/config` → returns non-secret settings (exclude password).
- [ ] **1.10** Create a `.env.example` file documenting all env vars.
- [ ] **1.11** Create `static/css/style.css` (minimal placeholder).
- [ ] **1.12** Create `app/templates/base.html` (minimal HTML5 shell with nav links for the 5 dashboard pages, a `{% block content %}{% endblock %}`, and Chart.js CDN script tag).

### Verification

```bash
pip install -e .
uvicorn app.main:app --reload
curl http://localhost:8000/api/health
# Expect: {"status":"ok","version":"0.1.0"}
```

---

## Phase 2: Database Models & Migrations

**Goal:** All SQLAlchemy models defined, Alembic configured, initial migration runs.

### Steps

- [ ] **2.1** Create `app/models/__init__.py` (empty).
- [ ] **2.2** Create `app/models/database.py` with SQLAlchemy ORM models for every table in the PRD schema. Use the `Base` from `app/core/database.py`. Models to define:
  1. `RawGarminResponse` — columns: `id`, `date` (Date), `endpoint` (String), `response` (JSON), `fetched_at` (DateTime). UniqueConstraint on `(date, endpoint)`.
  2. `RawHabitSyncResponse` — columns: `id`, `date` (Date, unique), `response` (JSON), `fetched_at`.
  3. `HeartRateSample` — columns: `id`, `timestamp` (DateTime, unique, indexed), `heart_rate` (Integer).
  4. `BodyBatterySample` — columns: `id`, `timestamp` (DateTime, unique, indexed), `body_battery` (Integer).
  5. `StressSample` — columns: `id`, `timestamp` (DateTime, unique, indexed), `stress_level` (Integer).
  6. `HrvSample` — columns: `id`, `timestamp` (DateTime, unique, indexed), `hrv_value` (Float), `reading_type` (String, nullable).
  7. `Spo2Sample` — columns: `id`, `timestamp` (DateTime, unique, indexed), `spo2_value` (Integer).
  8. `StepsSample` — columns: `id`, `timestamp` (DateTime, unique, indexed), `steps` (Integer), `duration_seconds` (Integer, nullable).
  9. `SleepSession` — columns: `id`, `date` (Date, unique), `sleep_start`, `sleep_end`, `total_sleep_seconds`, `deep_sleep_seconds`, `light_sleep_seconds`, `rem_sleep_seconds`, `awake_seconds`, `sleep_score`, `avg_overnight_hrv`, `avg_overnight_spo2`, `avg_overnight_rr`, `raw_sleep_levels` (JSON).
  10. `Activity` — columns: `id`, `garmin_activity_id` (String, unique), `activity_type`, `start_time`, `end_time`, `duration_seconds`, `avg_hr`, `max_hr`, `min_hr`, `calories`, `avg_stress`, `training_effect_aerobic`, `training_effect_anaerobic`, `hr_zones_json` (JSON), `raw_data` (JSON).
  11. `DailyHabit` — columns: `id`, `date` (Date), `habit_name` (String), `habit_value` (String), `habit_type` (String, nullable). UniqueConstraint on `(date, habit_name)`.
  12. `DailySummaryCache` — columns: `date` (Date, primary_key), `computed_at` (DateTime), `summary_json` (JSON).

  **Important notes for the implementer:**
  - The PRD schema has `sleep_sessions` with both `id INTEGER PRIMARY KEY AUTOINCREMENT` and `date DATE PRIMARY KEY`. This is a bug in the PRD. Use `id` as the autoincrement PK and put a unique constraint on `date` instead.
  - Use `sqlalchemy.JSON` type for JSON columns — SQLite stores them as TEXT but SQLAlchemy handles serialization.
  - Add `__tablename__` to every model.
  - Index `timestamp` columns on all time-series tables.
  - Index `date` and `habit_name` on `daily_habits`.
  - Index `start_time` on `activities`.

- [ ] **2.3** Set up Alembic:
  - Run `alembic init migrations`.
  - Edit `alembic.ini`: set `sqlalchemy.url = sqlite+aiosqlite:///data/energy_tracker.db` (will be overridden in env.py).
  - Edit `migrations/env.py`:
    - Import `Base` from `app.models.database` (ensure all models are imported so metadata is populated).
    - Set `target_metadata = Base.metadata`.
    - Override `sqlalchemy.url` from `app.core.config.get_settings().db_path`.
    - Use `render_as_batch=True` in `context.configure()` (required for SQLite ALTER TABLE support).
    - Make both `run_migrations_online` and `run_migrations_offline` work.
- [ ] **2.4** Generate initial migration: `alembic revision --autogenerate -m "initial schema"`.
- [ ] **2.5** Run migration: `alembic upgrade head`.

### Verification

```bash
alembic upgrade head
# No errors
python -c "import sqlite3; conn = sqlite3.connect('data/energy_tracker.db'); print([t[0] for t in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])"
# Should list all 12 tables
```

---

## Phase 3: Garmin API Client & Data Parsing

**Goal:** Can authenticate with Garmin, fetch data for a single day, parse raw JSON into database rows.

### Steps

- [ ] **3.1** Create `app/services/__init__.py` (empty).
- [ ] **3.2** Create `app/services/garmin.py`:
  - Class `GarminClient` with methods:
    - `__init__(self, email, password, token_dir)`: stores credentials and token directory path.
    - `async def connect(self)`: Wraps `garminconnect.Garmin(email, password)` + `login()` in `asyncio.to_thread()` (the garminconnect library is synchronous). Set `GARMINTOKENS` env var to `token_dir` before login so tokens persist. Wrap in try/except for `GarminConnectAuthenticationError`.
    - `async def fetch_sleep(self, date_str: str) -> dict`: Calls `self.client.get_sleep_data(date_str)` via `asyncio.to_thread()`.
    - `async def fetch_heart_rate(self, date_str: str) -> dict`: Calls `get_heart_rates(date_str)`.
    - `async def fetch_hrv(self, date_str: str) -> dict | None`: Calls `get_hrv_data(date_str)`. May return None.
    - `async def fetch_body_battery(self, date_str: str) -> list`: Calls `get_body_battery(date_str, date_str)`.
    - `async def fetch_stress(self, date_str: str) -> dict`: Calls `get_all_day_stress(date_str)`.
    - `async def fetch_spo2(self, date_str: str) -> dict | None`: Calls `get_spo2_data(date_str)`. May return None.
    - `async def fetch_steps(self, date_str: str) -> dict`: Calls `get_steps_data(date_str)`.
    - `async def fetch_activities(self, start: int = 0, limit: int = 20) -> list`: Calls `get_activities(start, limit)`.
    - `async def fetch_all_for_date(self, date_str: str) -> dict[str, Any]`: Calls all fetch methods, returns dict keyed by endpoint name. Wraps each call in try/except so one failure doesn't block others. Logs errors.
  - **Retry logic:** Create a decorator or wrapper `async def _with_retry(func, max_retries=3)` that catches `GarminConnectTooManyRequestsError` and `GarminConnectConnectionError`, waits with exponential backoff (2, 4, 8 seconds), and retries. On `GarminConnectAuthenticationError`, attempt re-login once.
  - **Important:** All garminconnect library calls are synchronous — always wrap in `asyncio.to_thread()`.

- [ ] **3.3** Create `tests/fixtures/` directory with sample JSON files. These are essential for testing parsers without hitting the real API. Create realistic sample responses for each endpoint:
  - `garmin_sleep.json` — include `dailySleepDTO` with fields: `sleepTimeSeconds`, `deepSleepSeconds`, `lightSleepSeconds`, `remSleepSeconds`, `awakeSleepSeconds`, `sleepStartTimestampGMT`, `sleepEndTimestampGMT`, `averageSpO2Value`, `averageRespirationValue`, `sleepScores` (with `overall.value`), `sleepLevels` array.
  - `garmin_heart_rate.json` — include `heartRateValues` array of `[timestampMs, hrValue]` pairs (null hrValue means no reading). Include `restingHeartRate`.
  - `garmin_body_battery.json` — array of objects with `startTimestampGMT`, `endTimestampGMT`, `bodyBatteryValuesArray` (array of `[timestampMs, bbLevel, bbStatus]`).
  - `garmin_stress.json` — include `stressValuesArray` as array of `[timestampOffsetMs, stressLevel]` pairs (-1 or -2 means rest/no reading). Include `startTimestampGMT`.
  - `garmin_hrv.json` — include `hrvSummary` with `lastNightAvg`, `lastNight5MinHigh`, `startTimestampGMT`. Also `hrv` readings array if available.
  - `garmin_spo2.json` — include `spO2SingleValues` or similar with `[timestampMs, spo2Value]` pairs.
  - `garmin_steps.json` — include step intervals or a total.
  - `garmin_activities.json` — array of activity objects with `activityId`, `activityType.typeKey`, `startTimeGMT`, `duration`, `averageHR`, `maxHR`, `calories`, etc.

  **NOTE:** The exact field names depend on the real Garmin API responses. The implementer should do a single real API call first (Phase 3.5) and capture the actual response shapes, then update these fixtures. The field names above are best-guesses based on community documentation.

- [ ] **3.4** Create `app/services/parsers.py`:
  - Function for each data type that takes raw JSON and returns a list of ORM model instances.
  - `parse_heart_rate(raw: dict, date: date) -> list[HeartRateSample]`:
    - Extract `heartRateValues` array. Each entry is `[timestampMs, hrValue]`.
    - Skip entries where `hrValue` is `None` or `0`.
    - Convert `timestampMs` (epoch milliseconds) to Python `datetime`.
  - `parse_body_battery(raw: list | dict, date: date) -> list[BodyBatterySample]`:
    - Navigate to the body battery values array. Each entry: `[timestampMs, bbLevel, status]`.
    - Skip entries where `bbLevel` is `None`.
  - `parse_stress(raw: dict, date: date) -> list[StressSample]`:
    - Extract `stressValuesArray`. Each entry: `[offsetMs, stressLevel]`.
    - `stressLevel` of `-1` or `-2` means rest/unmeasured — store as-is (the features layer will filter).
    - Calculate timestamp from `startTimestampGMT` (or `startTimestampLocal`) + offset.
  - `parse_hrv(raw: dict | None, date: date) -> list[HrvSample]`:
    - Handle `None` input (device may not have HRV).
    - Extract HRV readings, set `reading_type = "overnight"`.
  - `parse_spo2(raw: dict | None, date: date) -> list[Spo2Sample]`:
    - Handle `None` input.
    - Extract SpO2 readings from the response array.
  - `parse_steps(raw: dict, date: date) -> list[StepsSample]`:
    - Extract step intervals with timestamps.
  - `parse_sleep(raw: dict, date: date) -> SleepSession | None`:
    - Extract from `dailySleepDTO` or top-level fields.
    - Map fields to the `SleepSession` model.
    - Store `sleepLevels` as `raw_sleep_levels` JSON.
  - `parse_activities(raw: list) -> list[Activity]`:
    - Iterate activity list.
    - Map `activityType.typeKey` to `activity_type`.
    - Store full activity object as `raw_data` JSON.

  **Key design decision:** Each parser uses `INSERT OR REPLACE` semantics (via SQLAlchemy `merge` or manual upsert) so re-syncing a day is idempotent.

- [ ] **3.5** Write a one-off test script `scripts/test_garmin_fetch.py` (not part of the app):
  - Authenticates with real credentials from `.env`.
  - Fetches yesterday's data for each endpoint.
  - Prints the raw JSON response to stdout (or saves to `tests/fixtures/`).
  - This is used ONCE to capture real response shapes, then the fixtures are used for testing.
  - **Action for the implementer:** Run this script, examine the actual JSON shapes, and update the parsers and fixtures accordingly. The field names in step 3.3 are approximate.

- [ ] **3.6** Create `tests/test_parsers.py`:
  - Load each fixture JSON file.
  - Call the corresponding parser.
  - Assert the correct number of ORM instances are returned.
  - Assert timestamps are in the correct range.
  - Assert values are within expected bounds.

### Verification

```bash
# Run the test garmin fetch (once, manually)
python scripts/test_garmin_fetch.py

# Run parser tests
pytest tests/test_parsers.py -v
```

### Pitfalls & Edge Cases

- Garmin timestamps are sometimes in epoch milliseconds, sometimes in ISO-8601 strings — the parsers must handle both.
- `get_body_battery()` takes a date range (`start, end`) unlike other methods that take a single date.
- `get_hrv_data()` and `get_spo2_data()` may return `None` if the device doesn't support them or if no data was recorded.
- Heart rate values can be `None` in the array (gaps when watch is off wrist).
- Stress values of `-1` and `-2` are sentinel values meaning "rest" and "unmeasured" — do NOT discard them, store them and handle at the features layer.

---

## Phase 4: HabitSync API Client

**Goal:** Can fetch habits list and daily records from HabitSync.

### Steps

- [ ] **4.1** Create `app/services/habitsync.py`:
  - Class `HabitSyncClient`:
    - `__init__(self, base_url: str, api_key: str)`: store config, create `httpx.AsyncClient` with `X-Api-Key` header.
    - `async def get_habits(self) -> list[dict]`: `GET {base_url}/api/habit` — returns list of habit definitions. Each has `uuid`, `name`, `type`, `archived` fields.
    - `async def get_habit_record(self, habit_uuid: str, offset: int, timezone: str) -> dict | None`: `GET {base_url}/api/record/{habit_uuid}/simple?offset={offset}&timeZone={timezone}`. Returns the record or None if not found. `offset=0` is today, `offset=1` is yesterday, etc.
    - `async def fetch_all_for_date(self, target_date: date, timezone: str) -> dict`:
      1. Call `get_habits()` to discover all habits.
      2. Calculate `offset` as `(today - target_date).days`.
      3. For each non-archived habit, call `get_habit_record(habit_uuid, offset, timezone)`.
      4. Return a dict mapping habit names to their values.
    - Error handling: catch `httpx.HTTPStatusError`, `httpx.ConnectError`. Log and return empty/None on failure.
  - **Important:** HabitSync's offset is days-from-today, not a date parameter. The offset changes depending on when the sync runs.

- [ ] **4.2** Create `tests/fixtures/habitsync_habits.json` — sample list of habits.
- [ ] **4.3** Create `tests/fixtures/habitsync_record.json` — sample record response.

- [ ] **4.4** Add parsing logic (can be in `habitsync.py` or `parsers.py`):
  - `parse_habitsync_response(habits_data: dict, date: date) -> list[DailyHabit]`:
    - For each habit, create a `DailyHabit` row.
    - Determine `habit_type` from the HabitSync habit definition (boolean → "boolean", counter → "counter", etc).
    - Normalize `habit_name` to snake_case (e.g., "PM Energy Slump" → "pm_energy_slump").

### Verification

```bash
# Quick integration test with real HabitSync (if available)
python -c "
import asyncio, httpx
async def test():
    async with httpx.AsyncClient() as c:
        r = await c.get('http://YOUR_HABITSYNC_URL/api/habit', headers={'X-Api-Key': 'YOUR_KEY'})
        print(r.json())
asyncio.run(test())
"
```

### Pitfalls & Edge Cases

- HabitSync may not have records for every day (user didn't log). Return None/skip for those days.
- Habit names in HabitSync are user-defined and may contain spaces, mixed case, or special characters. Always normalize to snake_case for storage.
- The offset calculation must account for the timezone — "today" in `Europe/London` may differ from UTC.
- HabitSync API docs are at `/swagger-ui/index.html` — the implementer should check these for exact endpoint shapes before coding.

---

## Phase 5: Sync Orchestration

**Goal:** A service that coordinates fetching from both APIs, stores raw responses, and parses into structured tables. Runs on schedule.

### Steps

- [ ] **5.1** Create `app/services/sync.py`:
  - Class `SyncService`:
    - `__init__(self, garmin: GarminClient, habitsync: HabitSyncClient, db_session_factory)`.
    - `async def sync_garmin_day(self, date: date, session) -> dict`:
      1. Call `garmin.fetch_all_for_date(date_str)`.
      2. For each endpoint response, upsert into `raw_garmin_responses` (date + endpoint as unique key).
      3. Parse each response using `parsers.py` functions.
      4. Upsert parsed rows into the corresponding time-series/daily tables.
      5. Return a status dict with counts of rows inserted per table.
    - `async def sync_habitsync_day(self, date: date, session) -> dict`:
      1. Call `habitsync.fetch_all_for_date(date, timezone)`.
      2. Upsert raw response into `raw_habitsync_responses`.
      3. Parse into `daily_habits` rows.
      4. Return status dict.
    - `async def sync_day(self, date: date) -> dict`:
      1. Open a DB session.
      2. Call `sync_garmin_day`.
      3. Call `sync_habitsync_day`.
      4. Commit.
      5. Return combined status.
    - `async def sync_date_range(self, start: date, end: date) -> list[dict]`:
      1. Iterate from `start` to `end` inclusive.
      2. Call `sync_day` for each date.
      3. Return list of statuses.
    - `async def run_daily_sync(self)`:
      1. Determine yesterday's date (in configured timezone).
      2. Call `sync_day(yesterday)`.
      3. Log result.
      4. This is what the scheduler calls.

  - **Upsert strategy for SQLite:** Use `INSERT OR REPLACE` via SQLAlchemy. For each parsed row, check if a row with the same unique key exists. If yes, update it. If no, insert. In SQLAlchemy, this can be done with:
    ```python
    from sqlalchemy.dialects.sqlite import insert
    stmt = insert(HeartRateSample).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["timestamp"],
        set_={col: stmt.excluded[col] for col in update_cols}
    )
    await session.execute(stmt)
    ```

- [ ] **5.2** Create a `sync_log` table (add to models):
  - Columns: `id`, `sync_type` ("garmin"/"habitsync"/"all"), `date_synced` (Date), `started_at` (DateTime), `completed_at` (DateTime), `status` ("success"/"failed"), `details` (JSON, nullable), `error_message` (Text, nullable).
  - This supports `GET /api/sync/status`.

- [ ] **5.3** Create `app/services/scheduler.py`:
  - Use `APScheduler` `AsyncIOScheduler` (or `BackgroundScheduler` with async wrapper).
  - Add two cron jobs:
    1. Garmin sync: runs at `SYNC_HOUR:00` daily.
    2. HabitSync sync: runs at `SYNC_HOUR:15` daily.
  - The scheduler is started in the FastAPI lifespan (`on_startup`) and shut down in `on_shutdown`.
  - **Important:** APScheduler 3.x uses `BackgroundScheduler` or `AsyncIOScheduler`. Do NOT use APScheduler 4.x (alpha) — it has a completely different API.

- [ ] **5.4** Create `app/api/sync.py` (API router):
  - `POST /api/sync/garmin` — triggers Garmin sync for yesterday (or `?date=YYYY-MM-DD`).
  - `POST /api/sync/habitsync` — triggers HabitSync sync for yesterday (or `?date=YYYY-MM-DD`).
  - `POST /api/sync/all` — triggers both.
  - `GET /api/sync/status` — queries `sync_log` table, returns last sync time and status for each type.
  - All sync endpoints should run the sync in the background (return 202 Accepted immediately) using `asyncio.create_task` or FastAPI `BackgroundTasks`.

- [ ] **5.5** Wire the sync router and scheduler into `app/main.py`.

### Verification

```bash
# Trigger manual sync
curl -X POST http://localhost:8000/api/sync/garmin?date=2025-01-28

# Check status
curl http://localhost:8000/api/sync/status

# Verify data in DB
python -c "
import sqlite3
conn = sqlite3.connect('data/energy_tracker.db')
for table in ['raw_garmin_responses', 'heart_rate_samples', 'body_battery_samples', 'sleep_sessions', 'daily_habits']:
    count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'{table}: {count} rows')
"
```

### Pitfalls & Edge Cases

- The Garmin `connect()` call should happen once at app startup, not per-sync. Store the connected client. Handle token refresh failures by catching auth errors and re-connecting.
- When syncing a date range (e.g., backfill), add a 1-2 second delay between days to avoid Garmin rate limiting.
- SQLite upserts with `on_conflict_do_update` require the conflicting columns to have a UNIQUE constraint or be a PRIMARY KEY.
- If Garmin returns no data for a date (e.g., watch was off), the raw response should still be stored (as empty/null) so we know we attempted the sync and don't retry unnecessarily.
- Timezone handling: use `zoneinfo.ZoneInfo(settings.tz)` for timezone-aware datetime calculations. Yesterday = `datetime.now(tz) - timedelta(days=1)`.

---

## Phase 6: Raw Data API Endpoints

**Goal:** API endpoints to retrieve raw time-series data for a given date.

### Steps

- [ ] **6.1** Create `app/schemas/__init__.py` (empty).
- [ ] **6.2** Create `app/schemas/responses.py`:
  - Pydantic models for API responses:
    - `TimeSeriesPoint(timestamp: datetime, value: float)`
    - `TimeSeriesResponse(date: str, type: str, points: list[TimeSeriesPoint])`
    - `SleepResponse` — mirrors `SleepSession` fields.
    - `ActivityResponse` — mirrors `Activity` fields.
    - `HabitResponse(date: str, habits: dict[str, Any])` — flat dict of habit_name → value.
    - `SyncStatusResponse(garmin_last_sync: datetime | None, garmin_status: str, habitsync_last_sync: datetime | None, habitsync_status: str)`
    - `DailySummary` — will be filled out in Phase 7.
    - `CorrelationResult(metric: str, coefficient: float, p_value: float, n: int, strength: str)`
    - `PatternResult(description: str, probability: float, sample_size: int)`
    - `InsightResult(text: str, confidence: str, supporting_metric: str)`

- [ ] **6.3** Create `app/api/raw.py`:
  - `GET /api/raw/heart_rate?date=YYYY-MM-DD` → query `heart_rate_samples` for that day, return as `TimeSeriesResponse`.
  - `GET /api/raw/body_battery?date=YYYY-MM-DD` → query `body_battery_samples`.
  - `GET /api/raw/stress?date=YYYY-MM-DD` → query `stress_samples`.
  - `GET /api/raw/hrv?date=YYYY-MM-DD` → query `hrv_samples`.
  - `GET /api/raw/spo2?date=YYYY-MM-DD` → query `spo2_samples`.
  - `GET /api/raw/steps?date=YYYY-MM-DD` → query `steps_samples`.
  - `GET /api/raw/sleep?date=YYYY-MM-DD` → query `sleep_sessions`.
  - `GET /api/activities?days=30` → query `activities` table for last N days.

  Use a single route with a `type` path parameter where possible: `GET /api/raw/{metric_type}`.

- [ ] **6.4** Create `app/api/daily.py`:
  - `GET /api/habits?days=30` → query `daily_habits`, pivot by date, return list of `HabitResponse`.
  - `GET /api/daily?days=30` → placeholder for now (will return computed daily summaries in Phase 7).

- [ ] **6.5** Wire these routers into `app/main.py`.

### Verification

```bash
# After syncing a day:
curl "http://localhost:8000/api/raw/heart_rate?date=2025-01-28"
curl "http://localhost:8000/api/raw/body_battery?date=2025-01-28"
curl "http://localhost:8000/api/raw/sleep?date=2025-01-28"
curl "http://localhost:8000/api/activities?days=7"
curl "http://localhost:8000/api/habits?days=7"
# All should return JSON with data
```

---

## Phase 7: Computed Features Engine

**Goal:** Derive all 35+ computed features from raw time-series data. This is the core analytical engine.

### Steps

- [ ] **7.1** Create `app/services/features.py`:
  - Main entry point: `async def compute_daily_features(date: date, session) -> dict`
    - Queries all relevant raw tables for the given date.
    - Calls each feature computation function.
    - Returns a flat dict of `{feature_name: value}`.
  - Helper: `async def compute_features_range(start: date, end: date, session) -> list[dict]`
    - Calls `compute_daily_features` for each date in range.
    - Returns list of dicts (one per day).

- [ ] **7.2** Implement sleep features:
  - `sleep_hours`: `total_sleep_seconds / 3600`
  - `deep_sleep_pct`: `deep_sleep_seconds / total_sleep_seconds * 100`
  - `rem_sleep_pct`: `rem_sleep_seconds / total_sleep_seconds * 100`
  - `sleep_efficiency`: `total_sleep_seconds / (sleep_end - sleep_start).total_seconds() * 100`
  - `sleep_score`: passthrough from `SleepSession.sleep_score`
  - Data source: `sleep_sessions` table.

- [ ] **7.3** Implement HRV features:
  - `hrv_overnight_avg`: mean of `hrv_samples` where `reading_type = "overnight"` for that night.
  - `hrv_overnight_min`: min of same.
  - `hrv_rmssd_slope`: linear regression slope of HRV values over the night (use numpy `polyfit(x, y, 1)[0]`). Positive = improving, negative = declining.
  - Data source: `hrv_samples` table. Filter by overnight window (sleep_start to sleep_end from `sleep_sessions`).

- [ ] **7.4** Implement heart rate features:
  - `resting_hr`: from `SleepSession.avg_overnight_hrv`... no, this is HR not HRV. Query `heart_rate_samples` — find the lowest 30-minute rolling average in 24h.
  - `hr_morning_avg`: mean HR from 6am-12pm.
  - `hr_afternoon_avg`: mean HR 12pm-6pm.
  - `hr_2pm_window`: mean HR 1pm-4pm.
  - `hr_max_24h`: max HR in 24h.
  - `hr_recovery_slope`: rate of HR decrease after peak activity. Find the highest HR, then compute slope of HR over the next 30 minutes. If no activity, set to None.
  - Data source: `heart_rate_samples` table. Filter by time windows using the configured timezone.
  - **Important:** Filter out `None` and `0` HR values before computing.

- [ ] **7.5** Implement body battery features:
  - `bb_wakeup`: BB value closest to `sleep_end` time.
  - `bb_9am`: BB value closest to 9:00 AM.
  - `bb_12pm`: BB value closest to 12:00 PM.
  - `bb_2pm`: BB value closest to 2:00 PM.
  - `bb_6pm`: BB value closest to 6:00 PM.
  - For each "closest to time X" lookup: query BB samples within ±30 minutes of target time, pick the one closest. Return None if no sample in range.
  - `bb_morning_drain_rate`: `(bb_12pm - bb_wakeup) / hours_between`. Will be negative if draining.
  - `bb_afternoon_drain_rate`: `(bb_6pm - bb_12pm) / hours_between`.
  - `bb_daily_min`: minimum BB value for the day.
  - Data source: `body_battery_samples` table.

- [ ] **7.6** Implement stress features:
  - `stress_morning_avg`: mean stress 6am-12pm. **Exclude values ≤ 0** (sentinel values for rest/unmeasured).
  - `stress_afternoon_avg`: mean stress 12pm-6pm (exclude ≤ 0).
  - `stress_2pm_window`: mean stress 1pm-4pm (exclude ≤ 0).
  - `stress_peak`: max stress value (exclude ≤ 0).
  - `high_stress_minutes`: count samples with stress > 60, multiply by sample interval (~15 min).
  - Data source: `stress_samples` table.

- [ ] **7.7** Implement activity features:
  - `steps_total`: sum of `steps` from `steps_samples` for the day.
  - `steps_morning`: sum of steps before 12pm.
  - `active_minutes`: count of HR samples where HR > resting_hr * 1.4 (rough proxy), multiply by interval.
  - `had_training`: boolean — any row in `activities` with `start_time` on this date.
  - `training_type`: `activity_type` of the activity (or None).
  - `training_duration_min`: `duration_seconds / 60`.
  - `training_avg_hr`: from the activity row.
  - `training_intensity`: classify based on avg_hr as % of estimated max HR (220 - age, or use Garmin's zones if available). low: <70%, medium: 70-85%, high: >85%. Default max_hr = 190 if not configured.
  - `hours_since_training`: hours from activity's `end_time` to 2pm on the current day. Can be negative (training after 2pm) or span across days (yesterday's evening training).
  - Data source: `activities` and `steps_samples` tables.

- [ ] **7.8** Implement habit features:
  - `pm_slump`: query `daily_habits` where `habit_name` matches the PM slump habit. Convert to boolean (1/0).
  - `coffee_count`: integer value.
  - `beer_count`: integer value.
  - `healthy_lunch`: boolean.
  - `carb_heavy_lunch`: boolean.
  - **Dynamic habits:** Also include ANY other habits found in `daily_habits` for that date. Use the snake_case `habit_name` as the feature name.
  - Data source: `daily_habits` table.
  - **Habit name matching:** The PRD habit names ("PM Energy Slump", "Coffee", etc.) may not exactly match what the user creates in HabitSync. The system should work with whatever habit names exist. The config mapping (FR5.2) handles aliasing — but for v1, just use the normalized snake_case names directly.

- [ ] **7.9** Wire into `GET /api/daily?days=N` endpoint:
  - Compute features for each day in the range.
  - Return as list of `DailySummary` objects.
  - Consider caching in `daily_summary_cache` table for performance (optional in v1, but populate it if you do compute).

- [ ] **7.10** Create `tests/test_features.py`:
  - Insert known sample data into an in-memory SQLite database.
  - Call `compute_daily_features`.
  - Assert each feature value is correct.
  - Test edge cases: missing data, days with no sleep session, days with no activities.

### Verification

```bash
# After syncing several days:
curl "http://localhost:8000/api/daily?days=7"
# Should return JSON array with computed features per day

pytest tests/test_features.py -v
```

### Pitfalls & Edge Cases

- Time-of-day queries (e.g., "BB at 9am") must use the configured timezone, NOT UTC. Convert sample timestamps to local time before comparing.
- If no sample exists near a target time (e.g., watch was off), return `None` for that feature — do NOT fill with 0.
- Sleep sessions may span midnight. The "date" of a sleep session is the wake-up date.
- Activities from the previous evening (e.g., BJJ at 8pm) should have `hours_since_training` calculated to 2pm of the NEXT day.
- Division by zero: check denominators before computing rates (e.g., `total_sleep_seconds` could be 0 if sleep wasn't tracked).
- The features module should NEVER write to the database (principle: computed features are code, not data). The optional cache is the only exception.

---

## Phase 8: Correlation & Analysis Engine

**Goal:** Statistical analysis of the relationship between each metric and PM slump occurrence.

### Steps

- [ ] **8.1** Create `app/services/analysis.py`:

  - `async def compute_correlations(session, min_days: int = 7) -> list[dict]`:
    1. Compute features for all days that have `pm_slump` data.
    2. Separate into `fog_days` (pm_slump=True) and `clear_days` (pm_slump=False).
    3. For each numeric feature:
       a. Calculate Pearson correlation with pm_slump (use `scipy.stats.pearsonr`).
       b. Get the correlation coefficient `r` and p-value.
       c. Calculate mean on fog days vs clear days.
       d. Calculate percentage difference.
    4. Return list sorted by `|r|` descending.
    5. Flag as "preliminary" if total days < 30.
    6. Skip features with insufficient non-null values (< `min_days`).

  - `async def compute_patterns(session) -> list[dict]`:
    1. Define pattern rules (each is a condition → outcome check):
       - Sleep < 7 hours → fog probability
       - Beer count > 2 → fog probability
       - Previous evening intense training → fog probability (need to check previous day's activities)
       - Coffee > 3 → fog probability
       - Carb-heavy lunch = True → fog probability
       - BB at 9am < 50 → fog probability
    2. For each rule:
       a. Count days matching the condition.
       b. Count fog days among those.
       c. Compute conditional probability: `P(fog | condition)`.
       d. Also compute baseline fog rate: `P(fog)`.
       e. Compute relative risk: `P(fog | condition) / P(fog)`.
    3. Return list of patterns with probabilities and sample sizes.

  - `async def compute_trends(session, window_7: int = 7, window_30: int = 30) -> dict`:
    1. Get daily features ordered by date.
    2. Compute rolling averages for: fog occurrence, sleep_score, hrv_overnight_avg, bb_2pm.
    3. Detect if fog frequency is increasing or decreasing (linear regression slope over last 30 days).
    4. Return trend data as time series.

  - `async def generate_insights(session) -> list[dict]`:
    1. Call `compute_correlations` and `compute_patterns`.
    2. Generate plain-English insights:
       - For each pattern with relative risk > 1.5 or < 0.7 and sample size ≥ 5:
         - "You're {RR}x more likely to experience brain fog when {condition}"
         - or "Days with {condition} show {pct}% less fog"
       - For top 3 correlations with |r| > 0.3:
         - "Higher {metric} is associated with {'more' if r > 0 else 'fewer'} fog days (r={r:.2f})"
    3. Sort by confidence (combination of effect size and sample size).

- [ ] **8.2** Create `app/api/analysis.py`:
  - `GET /api/correlations` → calls `compute_correlations`, returns list of `CorrelationResult`.
  - `GET /api/patterns` → calls `compute_patterns`, returns list of `PatternResult`.
  - `GET /api/insights` → calls `generate_insights`, returns list of `InsightResult`.
  - All accept optional `?days=N` to limit the analysis window.

- [ ] **8.3** Wire analysis router into `app/main.py`.

- [ ] **8.4** Create `tests/test_analysis.py`:
  - Create synthetic data with known patterns (e.g., fog always occurs when sleep < 6h).
  - Verify correlation is detected.
  - Verify pattern probabilities are correct.
  - Verify insights are generated.

### Verification

```bash
curl http://localhost:8000/api/correlations
curl http://localhost:8000/api/patterns
curl http://localhost:8000/api/insights
# All should return JSON

pytest tests/test_analysis.py -v
```

### Pitfalls & Edge Cases

- `scipy.stats.pearsonr` will raise an error if all values are identical (zero variance). Catch this and skip the metric.
- Boolean features (pm_slump, healthy_lunch) should be converted to 0/1 integers for correlation.
- "Previous evening" training: for the pattern "BJJ yesterday evening → fog today", you need to look at activities from the previous calendar day after ~5pm. This requires a cross-day query.
- With very few data points (< 14 days), correlations are unreliable. Display but clearly mark as "preliminary".
- Handle the case where pm_slump has never been True or never been False (can't compute meaningful correlations).

---

## Phase 9: Export System

**Goal:** CSV/JSON export of computed features and raw time-series data.

### Steps

- [ ] **9.1** Create `app/api/export.py`:

  - `GET /api/export`:
    - Query parameters: `format` (csv|json, default csv), `days` (int, optional), `start` (date, optional), `end` (date, optional), `include_metadata` (bool, default false).
    - Compute features for the requested date range using `features.compute_features_range()`.
    - If `format=csv`: return as `StreamingResponse` with `text/csv` content type. Use Python `csv.DictWriter`. One row per day, columns = all feature names.
    - If `format=json`: return as JSON array of objects.
    - If `include_metadata=true`: for JSON, add a `_metadata` key. For CSV, include a companion metadata response (or use multipart? Simpler: just have a separate `/api/export/metadata` endpoint).
    - Set `Content-Disposition: attachment; filename=energy_tracker_export_{start}_{end}.csv`.

  - `GET /api/export/timeseries`:
    - Query parameters: `type` (required: heart_rate|body_battery|stress|hrv|spo2|steps), `start` (date, required), `end` (date, required).
    - Query the corresponding time-series table.
    - Return as CSV: columns `timestamp, value`.

  - `GET /api/export/metadata`:
    - Return a JSON (or Markdown) document containing:
      - Column definitions with units and derivation logic for each computed feature.
      - Date range of available data.
      - Data completeness stats: total days, days with missing Garmin data, days with missing habit data.
      - Suggested AI analysis prompts (hardcoded strings like "Analyze the correlation between sleep metrics and pm_slump...").

- [ ] **9.2** Add a metadata definition structure in `app/services/features.py` (or a separate file `app/services/metadata.py`):
  - A dict mapping each feature name to: `{description, unit, derivation, category}`.
  - Example: `"bb_morning_drain_rate": {"description": "Body Battery change per hour 6am-12pm", "unit": "BB points/hour", "derivation": "(bb_12pm - bb_wakeup) / hours", "category": "Body Battery"}`.
  - This is used by both the metadata export endpoint and the dashboard tooltips.

### Verification

```bash
# CSV export
curl "http://localhost:8000/api/export?format=csv&days=30" -o export.csv
head export.csv  # Should have header row + data rows

# JSON export
curl "http://localhost:8000/api/export?format=json&days=7"

# Time-series export
curl "http://localhost:8000/api/export/timeseries?type=heart_rate&start=2025-01-20&end=2025-01-28" -o hr.csv

# Metadata
curl "http://localhost:8000/api/export/metadata"
```

---

## Phase 10: Frontend Dashboard

**Goal:** Web dashboard with 5 views: Overview, Daily, Correlations, Trends, Insights.

### Design Notes

- Use server-side rendered HTML via Jinja2 templates.
- Use Chart.js (loaded from CDN) for all charts.
- Each page fetches its data from the API endpoints via `fetch()` in JavaScript.
- Minimal, clean design. No CSS framework required — use a simple custom stylesheet.
- The dashboard is at the root URL `/`.

### Steps

- [ ] **10.1** Update `app/templates/base.html`:
  - HTML5 document with:
    - `<nav>` with links: Overview, Daily, Correlations, Trends, Insights.
    - Active page highlighting.
    - Chart.js CDN: `<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>`.
    - Link to `/static/css/style.css`.
    - `{% block content %}{% endblock %}` in `<main>`.

- [ ] **10.2** Add page routes in `app/main.py` (or a new `app/api/pages.py`):
  - `GET /` → redirect to `/overview`.
  - `GET /overview` → render `overview.html`.
  - `GET /daily` → render `daily.html`.
  - `GET /correlations` → render `correlations.html`.
  - `GET /trends` → render `trends.html`.
  - `GET /insights` → render `insights.html`.

- [ ] **10.3** Build Overview page (`app/templates/overview.html` + `static/js/overview.js`):
  - Stat cards: Total days tracked, Fog day count, Fog %, Current clear streak.
  - "Top 3 correlates" section — fetched from `/api/correlations`, take top 3 by |r|.
  - Sync status indicator — fetched from `/api/sync/status`.
  - Manual sync button that POSTs to `/api/sync/all`.
  - JS fetches data on page load, populates the DOM.

- [ ] **10.4** Build Daily view (`app/templates/daily.html` + `static/js/daily.js`):
  - Calendar heatmap: Use a grid of `<div>` elements, one per day. Color: green (clear), red (fog), grey (no data). Overlay sleep score as a small number.
  - Click handler: clicking a day opens a detail panel showing all metrics for that day.
  - Detail panel: fetches from `/api/daily?days=1&date=YYYY-MM-DD` (you may need to add a `date` query param to this endpoint).
  - Show the last 90 days by default with pagination/scrolling for older data.

- [ ] **10.5** Build Correlations view (`app/templates/correlations.html` + `static/js/correlations.js`):
  - Horizontal bar chart: one bar per metric, length = correlation coefficient, color = positive (blue) / negative (orange). Use Chart.js horizontal bar chart.
  - Below chart: a table with columns: Metric, r, p-value, Fog Day Avg, Clear Day Avg, Difference.
  - Scatter plot area: dropdown to select a metric, shows scatter plot of that metric's values on fog vs clear days (jittered strip plot or box plot).
  - Data from `/api/correlations`.

- [ ] **10.6** Build Trends view (`app/templates/trends.html` + `static/js/trends.js`):
  - Line chart with multiple datasets. Default: fog occurrence (7-day rolling avg).
  - Checkboxes to toggle overlay of: sleep_score, hrv_overnight_avg, bb_2pm, stress_afternoon_avg.
  - Date range selector (last 30 / 90 / all days).
  - Data from `/api/daily?days=N` — compute rolling averages in JS or add a dedicated trends endpoint.

- [ ] **10.7** Build Insights view (`app/templates/insights.html` + `static/js/insights.js`):
  - List of insight cards, each showing:
    - Icon (based on confidence: green check, yellow warning, grey question mark).
    - The plain-English insight text.
    - Supporting stat (e.g., "Based on 45 days of data, r=0.42").
  - Pattern section: list of conditional probabilities.
  - Data from `/api/insights` and `/api/patterns`.
  - Export button: link to `/api/export?format=csv`.

- [ ] **10.8** Create `static/css/style.css`:
  - Clean, minimal styles. Dark header/nav, white content area.
  - Responsive layout (CSS grid or flexbox).
  - Stat card styles (bordered boxes with large numbers).
  - Calendar grid styles.
  - Chart container sizing.

### Verification

- Open `http://localhost:8000/` in browser.
- Navigate through all 5 pages — no JS errors in console.
- All charts render with data (after syncing at least a few days).
- Calendar heatmap shows correctly colored days.
- Export button downloads a CSV file.

### Pitfalls & Edge Cases

- Chart.js requires data in specific formats. Ensure labels and datasets arrays are correctly structured.
- The calendar heatmap doesn't need a library — a simple CSS grid with 7 columns works well.
- Handle empty states gracefully: if no data has been synced yet, show a friendly message + sync button, not a broken chart.
- All API fetches in JS should have error handling (try/catch, show error message to user).

---

## Phase 11: Docker & Deployment

**Goal:** Dockerized app ready to deploy on Synology NAS.

### Steps

- [ ] **11.1** Create `Dockerfile`:
  ```dockerfile
  FROM python:3.11-slim

  WORKDIR /app

  # Install deps first for layer caching
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  COPY . .

  # Create data directory
  RUN mkdir -p /data

  EXPOSE 8000

  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```

- [ ] **11.2** Create `docker-compose.yml`:
  ```yaml
  services:
    energy-tracker:
      build: .
      environment:
        - DB_PATH=/data/energy_tracker.db
        - GARMIN_EMAIL=${GARMIN_EMAIL}
        - GARMIN_PASSWORD=${GARMIN_PASSWORD}
        - GARMIN_TOKEN_DIR=/data/.garmin_tokens
        - HABITSYNC_URL=${HABITSYNC_URL}
        - HABITSYNC_API_KEY=${HABITSYNC_API_KEY}
        - TZ=${TZ:-Europe/London}
        - SYNC_HOUR=${SYNC_HOUR:-6}
      volumes:
        - ./data:/data
      ports:
        - "8000:8000"
      restart: unless-stopped
  ```

- [ ] **11.3** Create `.dockerignore`:
  ```
  .git
  .env
  __pycache__
  *.pyc
  .pytest_cache
  data/
  tests/
  scripts/
  ```

- [ ] **11.4** Create `.env.example` (if not already done in Phase 1):
  ```
  GARMIN_EMAIL=your@email.com
  GARMIN_PASSWORD=your_password
  HABITSYNC_URL=http://habitsync:6842
  HABITSYNC_API_KEY=your_api_key
  TZ=Europe/London
  SYNC_HOUR=6
  ```

- [ ] **11.5** Ensure database migrations run on container start:
  - Option A: Add `alembic upgrade head` to the Docker CMD before uvicorn.
  - Option B: Run migrations in the FastAPI lifespan startup.
  - **Recommended:** Option A, using a shell entrypoint script:
    ```bash
    #!/bin/sh
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ```
    Save as `entrypoint.sh`, make executable, use `ENTRYPOINT ["./entrypoint.sh"]` in Dockerfile.

- [ ] **11.6** Test Docker build and run locally:
  ```bash
  docker compose build
  docker compose up -d
  curl http://localhost:8000/api/health
  ```

- [ ] **11.7** Ensure Garmin token persistence:
  - The token directory (`/data/.garmin_tokens`) is inside the mounted volume, so tokens survive container restarts.
  - First run will require fresh login — tokens will be created and stored.

### Verification

```bash
docker compose up --build
# Wait for startup
curl http://localhost:8000/api/health
curl -X POST http://localhost:8000/api/sync/all
# Check logs
docker compose logs energy-tracker
```

### Pitfalls & Edge Cases

- SQLite database file must be on a mounted volume, not inside the container filesystem.
- The Garmin token directory must also be persisted across container restarts.
- On Synology, the Docker user may not have write permissions to the mounted volume. Ensure the directory is writable.
- APScheduler's timezone handling: ensure `TZ` env var is set in the container so `zoneinfo.ZoneInfo` works.
- If running alongside HabitSync in the same Docker Compose, use the Docker network hostname (`habitsync`) not an IP address.

---

## Phase 12: Testing, Polish & Documentation

**Goal:** Comprehensive tests, error handling, and documentation for production readiness.

### Steps

- [ ] **12.1** Create `tests/conftest.py`:
  - Set up an in-memory SQLite database for tests.
  - Create all tables using `Base.metadata.create_all`.
  - Provide a `db_session` fixture.
  - Provide an `async_client` fixture using `httpx.AsyncClient` with FastAPI's `TestClient`.

- [ ] **12.2** Create `tests/test_api_sync.py`:
  - Mock `GarminClient` and `HabitSyncClient` to return fixture data.
  - Test `POST /api/sync/garmin` returns 202.
  - Test `GET /api/sync/status` returns correct format.

- [ ] **12.3** Create `tests/test_api_export.py`:
  - Insert known data.
  - Test CSV export has correct headers and row count.
  - Test JSON export returns valid JSON.
  - Test date filtering works.
  - Test time-series export for each metric type.

- [ ] **12.4** Review and improve error handling:
  - All API endpoints return proper HTTP status codes (400 for bad params, 404 for no data, 500 for server errors).
  - Garmin/HabitSync connection failures return 503 with descriptive message.
  - Add `logging` throughout (use Python `logging` module, not print).
  - Add a global exception handler in FastAPI.

- [ ] **12.5** Add loading states and empty states to frontend:
  - Show spinner while API calls are in flight.
  - Show "No data yet — trigger a sync to get started" when tables are empty.
  - Show "Insufficient data for correlations (need at least 7 days)" when appropriate.

- [ ] **12.6** Performance check:
  - Test with 90+ days of data. Ensure `/api/daily?days=90` responds in < 2 seconds.
  - If slow, implement the `daily_summary_cache` table: compute once, serve from cache, invalidate when new data is synced.

- [ ] **12.7** Create a `README.md` with:
  - Project overview (one paragraph).
  - Setup instructions (Docker Compose).
  - Environment variables reference.
  - First-run instructions (initial Garmin auth, HabitSync setup).
  - API endpoint reference (link to `/docs` for auto-generated OpenAPI).
  - Troubleshooting common issues (Garmin auth failures, rate limiting, timezone issues).

- [ ] **12.8** Run full test suite and fix any failures:
  ```bash
  pytest tests/ -v --tb=short
  ```

### Verification

```bash
pytest tests/ -v
# All tests pass

docker compose up --build
# App starts without errors
# Dashboard loads in browser
# All 5 pages render correctly
# Export downloads work
```

---

## Appendix A: Dependency on Real API Response Shapes

The Garmin API response shapes are not officially documented. The parsers in Phase 3 are based on community knowledge and may need adjustment after the first real API call. The recommended workflow:

1. Complete Phase 3 parsers with best-guess field names.
2. Run `scripts/test_garmin_fetch.py` to get real responses.
3. Save real responses as test fixtures.
4. Update parsers to match actual field names.
5. This is expected and normal — do not consider it a failure.

## Appendix B: Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Sync approach | Pull via cron, not webhook | Garmin has no webhook API. HabitSync may have one but pull is simpler and consistent. |
| Feature computation | On-demand, not pre-computed | PRD principle: "computed features are code, not data". Keeps flexibility. Cache if slow. |
| Frontend rendering | Server-side templates + client-side Chart.js | No build step needed. Simple to deploy. Chart.js handles all visualization. |
| Database | SQLite (single file) | No separate DB service. Easy backup (copy one file). Handles 10+ years of data easily. |
| Async framework | FastAPI with async SQLAlchemy | Non-blocking I/O for API calls. APScheduler integrates with asyncio. |
| Upsert strategy | SQLite INSERT OR REPLACE | Re-syncing a day is idempotent. No duplicate data. |

## Appendix C: Phase Dependencies

```
Phase 1 (Scaffold) ─────┐
                         ▼
Phase 2 (Database) ──────┐
                         ▼
Phase 3 (Garmin) ────┐   │
Phase 4 (HabitSync) ─┤   │
                     ▼   ▼
Phase 5 (Sync) ──────────┐
                         ▼
Phase 6 (Raw API) ───────┐
                         ▼
Phase 7 (Features) ──────┐
                         ▼
Phase 8 (Analysis) ──┐   │
Phase 9 (Export) ─────┤   │
                     ▼   ▼
Phase 10 (Frontend) ─────┐
                         ▼
Phase 11 (Docker) ───────┐
                         ▼
Phase 12 (Polish) ───────┘
```

Phases 3 and 4 can be done in parallel. Phases 8 and 9 can be done in parallel.
All other phases are sequential.

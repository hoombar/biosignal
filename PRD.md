# Product Requirements Document: Energy Correlation Tracker

## Overview

A self-hosted analysis dashboard that correlates Garmin biometric data with lifestyle habits (logged via HabitSync) to identify patterns related to afternoon energy slumps and brain fog.

**Primary User:** The system owner (single user)

**Problem Statement:** User experiences consistent energy slumps and brain fog around 2-3pm daily. They want to identify which factors (sleep quality, HRV, caffeine intake, lunch choices, training intensity, etc.) correlate with these episodes to make data-driven lifestyle adjustments.

---

## System Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│     HabitSync       │     │   Garmin Connect    │
│  (Docker container) │     │   (Cloud API)       │
│                     │     │                     │
│  - PM slump Y/N     │     │  - Sleep data       │
│  - Coffee count     │     │  - HRV              │
│  - Beer count       │     │  - Body Battery     │
│  - Lunch type       │     │  - Stress           │
│                     │     │  - Heart rate       │
└────────┬────────────┘     │  - SpO2             │
         │                  │  - Steps            │
         │                  │  - Activities       │
         │                  └──────────┬──────────┘
         │                             │
         │    ┌────────────────────┐   │
         │    │                    │   │
         └───►│  Energy Tracker    │◄──┘
              │  (Docker container)│
              │                    │
              │  - Data collection │
              │  - Correlation     │
              │  - Web dashboard   │
              │                    │
              └────────────────────┘
```

**Deployment:** Docker containers on Synology NAS

---

## Architectural Principles

1. **Store raw, export computed.** Raw time-series data from Garmin is stored at full granularity (~15 min intervals). Aggregations and computed features are derived at query/export time, never at storage time. This preserves optionality for future analysis.

2. **Keep raw API responses.** Store the complete JSON responses from both Garmin and HabitSync APIs. If parsing logic changes or new fields become interesting, data can be reprocessed without re-fetching.

3. **Flexible habit schema.** Habits from HabitSync are stored with name/value pairs, not fixed columns. New habits can be added in HabitSync without any changes to the Energy Tracker.

4. **Computed features are code, not data.** The logic to derive features like "body battery drain rate" or "HR recovery slope" lives in application code and can be modified, added to, or corrected at any time.

5. **Export is a view, not a table.** The export endpoint dynamically computes features from raw data. There's no "export table" that could become stale or inconsistent.

---

## Data Sources

### From HabitSync (via API)

| Habit | Type | Purpose |
|-------|------|---------|
| PM Slump | Boolean (daily) | Primary outcome variable - did brain fog occur today? |
| Coffee Count | Integer (daily) | Track caffeine intake |
| Beer Count | Integer (daily) | Track alcohol consumption (previous evening) |
| Healthy Lunch | Boolean (daily) | Subjective assessment of lunch quality |
| Carb-Heavy Lunch | Boolean (daily) | Track high-carb meals that may cause glucose crashes |

**Note:** User will log these manually in HabitSync throughout the day. The PM slump is logged as a daily yes/no rather than timestamped, as precise timing is difficult to recall accurately.

### From Garmin Connect (via garminconnect library)

| Metric | Granularity | Relevance |
|--------|-------------|-----------|
| Sleep Score | Daily | Overall sleep quality indicator |
| Sleep Duration | Daily | Total sleep time |
| Sleep Stages | Daily | Deep/Light/REM/Awake breakdown |
| HRV (Heart Rate Variability) | Daily average + overnight | Recovery/stress indicator |
| Resting Heart Rate | Daily | Baseline fitness/stress indicator |
| Body Battery | Hourly throughout day | Energy levels, particularly trajectory 12pm-4pm |
| Stress Level | Hourly throughout day | Patterns before/during slump window |
| SpO2 | Overnight average | Blood oxygen during sleep |
| Steps | Daily + hourly | Activity levels, morning vs afternoon |
| Activities | Per activity | BJJ training sessions - intensity, duration, timing |
| Heart Rate Zones | Per activity | Training intensity classification |

---

## Functional Requirements

### FR1: Data Collection

**FR1.1 - Garmin Data Sync**
- System shall pull Garmin data daily via automated cron job
- Default sync time: 06:00 local time (to capture complete previous day)
- System shall support manual sync trigger via API/UI
- System shall handle Garmin API authentication (email/password stored as environment variables)
- System shall store raw API responses for debugging/reprocessing
- System shall gracefully handle API failures with retry logic (3 attempts, exponential backoff)

**FR1.2 - HabitSync Data Sync**
- System shall pull HabitSync data daily via automated cron job
- System shall authenticate to HabitSync API using API key
- Sync shall run after Garmin sync (e.g., 06:15) to ensure both sources are current
- System shall map HabitSync habit names to internal schema

**FR1.3 - Data Storage**
- System shall use SQLite for persistence (simple, file-based, easy backup on Synology)
- Database file location shall be configurable via environment variable
- Schema shall support:
  - Daily summary table (one row per day, all metrics)
  - Hourly metrics table (Body Battery, stress, HR for intraday analysis)
  - Activities table (training sessions with metadata)
  - Raw data table (JSON blobs for reprocessing)

### FR2: Correlation Analysis

**FR2.1 - Basic Statistics**
- System shall calculate averages for all metrics on "fog days" vs "clear days"
- System shall display percentage difference between fog/clear day averages
- System shall indicate statistical significance where sample size permits (n > 14)

**FR2.2 - Correlation Coefficients**
- System shall calculate Pearson correlation between PM slump occurrence and each metric
- System shall rank metrics by correlation strength
- System shall flag correlations with |r| > 0.3 as "potentially meaningful"

**FR2.3 - Pattern Detection**
- System shall identify if fog occurs more frequently on:
  - Days following < 7 hours sleep
  - Days following > 2 alcoholic drinks
  - Days following intense BJJ training (previous evening)
  - Days with > 3 coffees
  - Days with carb-heavy lunches
  - Days with low morning Body Battery (< 50 at 9am)
- System shall calculate conditional probabilities (e.g., "P(fog | sleep < 6h) = 73%")

**FR2.4 - Trend Analysis**
- System shall calculate 7-day and 30-day rolling averages for key metrics
- System shall detect if fog frequency is increasing/decreasing over time

### FR3: Web Dashboard

**FR3.1 - Overview Page**
- Display key stats: total days tracked, fog day count, fog day percentage
- Show current streak (days without fog)
- Display "top 3 correlates" - metrics most strongly associated with fog

**FR3.2 - Daily View**
- Calendar heatmap showing fog days (red) vs clear days (green)
- Click on day to see all metrics for that day
- Overlay previous night's sleep score on calendar

**FR3.3 - Correlation View**
- Bar chart showing correlation coefficient for each metric
- Scatter plots for selected metric vs fog occurrence
- Side-by-side comparison: average values on fog days vs clear days

**FR3.4 - Trends View**
- Line charts over time for:
  - Fog occurrence (7-day rolling average)
  - Sleep score
  - HRV
  - Body Battery at 2pm
- Ability to overlay multiple metrics on same chart

**FR3.5 - Insights View**
- Plain-English summary of strongest patterns found
- Example: "You're 3x more likely to experience brain fog when you sleep less than 6 hours"
- Example: "Days following BJJ training show 40% less fog than rest days"
- Recommendations based on data (if patterns are clear)

### FR4: Data Export

**FR4.1 - Combined Dataset Export (Computed Features)**
- System shall export a flat CSV with one row per day and computed features as columns
- Features are computed at export time from raw time-series data
- Export formats: CSV (primary), JSON (alternative)
- Export shall be available via:
  - Web UI download button
  - API endpoint (`GET /api/export?format=csv&days=all`)

**FR4.2 - Computed Features for Export**
Features are derived from raw time-series data at export time. Initial feature set:

| Category | Feature | Derivation |
|----------|---------|------------|
| **Sleep** | `sleep_hours` | Total sleep duration |
| | `deep_sleep_pct` | Deep sleep / total sleep |
| | `rem_sleep_pct` | REM / total sleep |
| | `sleep_efficiency` | Time asleep / time in bed |
| | `sleep_score` | Garmin's score (passthrough) |
| **HRV** | `hrv_overnight_avg` | Mean overnight HRV |
| | `hrv_overnight_min` | Lowest overnight HRV |
| | `hrv_rmssd_slope` | Trend direction overnight |
| **Heart Rate** | `resting_hr` | Lowest 30-min average |
| | `hr_morning_avg` | Mean HR 6am-12pm |
| | `hr_afternoon_avg` | Mean HR 12pm-6pm |
| | `hr_2pm_window` | Mean HR 1pm-4pm |
| | `hr_max_24h` | Peak HR in 24h period |
| | `hr_recovery_slope` | HR decrease rate post-activity |
| **Body Battery** | `bb_wakeup` | BB at sleep end |
| | `bb_9am` | BB at 9am |
| | `bb_12pm` | BB at noon |
| | `bb_2pm` | BB at 2pm |
| | `bb_6pm` | BB at 6pm |
| | `bb_morning_drain_rate` | BB change per hour 6am-12pm |
| | `bb_afternoon_drain_rate` | BB change per hour 12pm-6pm |
| | `bb_daily_min` | Lowest BB of day |
| **Stress** | `stress_morning_avg` | Mean stress 6am-12pm |
| | `stress_afternoon_avg` | Mean stress 12pm-6pm |
| | `stress_2pm_window` | Mean stress 1pm-4pm |
| | `stress_peak` | Highest stress reading |
| | `high_stress_minutes` | Minutes with stress > 60 |
| **Activity** | `steps_total` | Daily step count |
| | `steps_morning` | Steps before noon |
| | `active_minutes` | Minutes with elevated HR |
| | `had_training` | Boolean: training session logged |
| | `training_type` | Activity type if training |
| | `training_duration_min` | Duration of training |
| | `training_avg_hr` | Avg HR during training |
| | `training_intensity` | low/medium/high from HR zones |
| | `hours_since_training` | Hours from training end to 2pm |
| **Habits** | `pm_slump` | From HabitSync (boolean) |
| | `coffee_count` | From HabitSync |
| | `beer_count` | From HabitSync (previous evening) |
| | `healthy_lunch` | From HabitSync (boolean) |
| | `carb_heavy_lunch` | From HabitSync (boolean) |
| | *(dynamic)* | Any additional habits auto-included |

**FR4.3 - Raw Time-Series Export**
- System shall support export of raw time-series data for deep analysis
- Endpoint: `GET /api/export/timeseries?type=heart_rate&start=DATE&end=DATE`
- Supported types: `heart_rate`, `body_battery`, `stress`, `hrv`, `spo2`, `steps`
- Format: CSV with columns `timestamp, value`

**FR4.4 - Export Metadata**
- Export shall include a companion metadata file describing:
  - Column definitions, units, and derivation logic
  - Date range covered
  - Data completeness (missing days, gaps in time-series)
  - Suggested AI analysis prompts
- Metadata format: Markdown or JSON

**FR4.5 - Export Filtering**
- Support date range filtering (`?start=2025-01-01&end=2025-12-31`)
- Support "last N days" filtering (`?days=90`)
- Default: export all available data

**FR4.6 - Future-Proof Design**
- New computed features can be added without schema changes
- Feature computation logic is separate from storage
- Raw data is always preserved for reprocessing

### FR5: Configuration

**FR5.1 - Environment Variables**
```
# Database
DB_PATH=/data/energy_tracker.db

# Garmin credentials
GARMIN_EMAIL=user@example.com
GARMIN_PASSWORD=xxxxx

# HabitSync connection
HABITSYNC_URL=http://habitsync:6842
HABITSYNC_API_KEY=xxxxx

# Optional
TZ=Europe/London
SYNC_HOUR=6
```

**FR5.2 - Habit Mapping Configuration**
- Config file or UI to map HabitSync habit names to internal schema
- Support for adding new habits without code changes

---

## Non-Functional Requirements

### NFR1: Deployment
- Application shall be deployable via Docker Compose
- Single container (no external database service required)
- Compatible with Synology Container Manager / Docker
- Memory usage shall not exceed 256MB under normal operation

### NFR2: Performance
- Dashboard pages shall load in < 2 seconds
- Daily sync job shall complete in < 60 seconds
- Database shall handle 5+ years of daily data without degradation

### NFR3: Reliability
- System shall continue functioning if Garmin API is temporarily unavailable
- System shall continue functioning if HabitSync is temporarily unavailable
- Failed syncs shall be logged and retried on next scheduled run
- Data shall never be overwritten (append-only with updates to current day only)

### NFR4: Security
- Garmin credentials shall be stored as environment variables (not in code/config files)
- Web UI shall be accessible only on local network (no authentication required given single-user local deployment)
- Optional: Basic auth can be enabled via environment variable for remote access

### NFR5: Maintainability
- Code shall be structured for easy addition of new data sources
- API responses shall be logged in debug mode for troubleshooting
- Database schema shall support migrations for future changes

---

## Technical Specifications

### Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Backend | Python 3.11+ | Good Garmin library support, rapid development |
| Web Framework | FastAPI | Async support, automatic OpenAPI docs, lightweight |
| Database | SQLite | Simple, no separate service, easy Synology backup |
| Frontend | HTML + Chart.js or Plotly | Simple, no build step, good charting |
| Garmin Integration | garminconnect library | Most maintained unofficial Garmin library |
| HTTP Client | httpx | Async support for HabitSync API calls |
| Scheduling | APScheduler or cron | In-process scheduling for daily sync |
| Containerisation | Docker | Standard deployment on Synology |

### API Endpoints

```
# Data sync
POST /api/sync/garmin              # Trigger manual Garmin sync
POST /api/sync/habitsync           # Trigger manual HabitSync sync
POST /api/sync/all                 # Trigger full sync
GET  /api/sync/status              # Last sync times and status

# Raw data retrieval
GET  /api/raw/heart_rate?date=X    # Get HR samples for a day
GET  /api/raw/body_battery?date=X  # Get BB samples for a day
GET  /api/raw/stress?date=X        # Get stress samples for a day
GET  /api/raw/sleep?date=X         # Get sleep session details
GET  /api/activities?days=30       # Get training activities

# Computed/aggregated data
GET  /api/daily?days=30            # Get computed daily summaries
GET  /api/habits?days=30           # Get habit data

# Analysis
GET  /api/correlations             # Get correlation coefficients
GET  /api/patterns                 # Get pattern analysis
GET  /api/insights                 # Get plain-English insights

# Export
GET  /api/export                   # Export computed daily features
                                   # ?format=csv|json (default: csv)
                                   # ?days=N or ?start=DATE&end=DATE
                                   # ?include_metadata=true
GET  /api/export/timeseries        # Export raw time-series data
                                   # ?type=heart_rate|body_battery|stress|hrv|spo2|steps
                                   # ?start=DATE&end=DATE
GET  /api/export/metadata          # Get column definitions and derivation logic

# Configuration
GET  /api/config                   # Get current configuration
PUT  /api/config                   # Update configuration
GET  /api/health                   # Health check endpoint
```

### Database Schema

**Design Principle:** Store raw data at the highest granularity available from source APIs. Computed features and aggregations are derived at query/export time, not at storage time. This ensures flexibility for future analysis without data loss.

```sql
-- ============================================
-- RAW DATA TABLES (source of truth)
-- ============================================

-- Raw Garmin API responses (for reprocessing if needed)
CREATE TABLE raw_garmin_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    endpoint TEXT NOT NULL,          -- e.g., "sleep", "stress", "heartRate", "bodyBattery"
    response JSON NOT NULL,          -- Complete API response
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, endpoint)
);

-- Raw HabitSync API responses
CREATE TABLE raw_habitsync_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    response JSON NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- ============================================
-- TIME-SERIES TABLES (parsed from raw)
-- ============================================

-- Heart rate at ~15 minute intervals (Garmin provides this granularity)
CREATE TABLE heart_rate_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    heart_rate INTEGER NOT NULL,
    UNIQUE(timestamp)
);
CREATE INDEX idx_hr_timestamp ON heart_rate_samples(timestamp);

-- Body Battery at ~15 minute intervals
CREATE TABLE body_battery_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    body_battery INTEGER NOT NULL,   -- 0-100
    UNIQUE(timestamp)
);
CREATE INDEX idx_bb_timestamp ON body_battery_samples(timestamp);

-- Stress level at ~15 minute intervals  
CREATE TABLE stress_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    stress_level INTEGER NOT NULL,   -- 0-100, or -1 for "rest"
    UNIQUE(timestamp)
);
CREATE INDEX idx_stress_timestamp ON stress_samples(timestamp);

-- HRV readings (typically overnight, varies by device)
CREATE TABLE hrv_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    hrv_value REAL NOT NULL,         -- milliseconds
    reading_type TEXT,               -- "overnight", "spot_check", etc.
    UNIQUE(timestamp)
);
CREATE INDEX idx_hrv_timestamp ON hrv_samples(timestamp);

-- SpO2 readings (typically overnight)
CREATE TABLE spo2_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    spo2_value INTEGER NOT NULL,     -- percentage
    UNIQUE(timestamp)
);
CREATE INDEX idx_spo2_timestamp ON spo2_samples(timestamp);

-- Steps per interval (hourly or finer)
CREATE TABLE steps_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    steps INTEGER NOT NULL,
    duration_seconds INTEGER,        -- interval duration
    UNIQUE(timestamp)
);
CREATE INDEX idx_steps_timestamp ON steps_samples(timestamp);

-- ============================================
-- DAILY TABLES (one row per day)
-- ============================================

-- Sleep data (one record per night)
CREATE TABLE sleep_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE PRIMARY KEY,           -- Date sleep is attributed to (wake date)
    sleep_start DATETIME,
    sleep_end DATETIME,
    total_sleep_seconds INTEGER,
    deep_sleep_seconds INTEGER,
    light_sleep_seconds INTEGER,
    rem_sleep_seconds INTEGER,
    awake_seconds INTEGER,
    sleep_score INTEGER,             -- Garmin's computed score
    avg_overnight_hrv REAL,
    avg_overnight_spo2 REAL,
    avg_overnight_rr REAL,           -- Respiratory rate if available
    raw_sleep_levels JSON            -- Array of sleep stage transitions with timestamps
);

-- Activities (training sessions)
CREATE TABLE activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    garmin_activity_id TEXT UNIQUE,
    activity_type TEXT NOT NULL,     -- "brazilian_jiu_jitsu", "strength_training", etc.
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    duration_seconds INTEGER,
    avg_hr INTEGER,
    max_hr INTEGER,
    min_hr INTEGER,
    calories INTEGER,
    avg_stress INTEGER,
    training_effect_aerobic REAL,
    training_effect_anaerobic REAL,
    hr_zones_json JSON,              -- Time in each HR zone
    raw_data JSON                    -- Full activity data for future use
);
CREATE INDEX idx_activities_start ON activities(start_time);

-- Habits from HabitSync (flexible schema)
CREATE TABLE daily_habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    habit_name TEXT NOT NULL,        -- e.g., "pm_slump", "coffee", "healthy_lunch"
    habit_value TEXT NOT NULL,       -- Stored as text, interpreted based on habit type
    habit_type TEXT,                 -- "boolean", "counter", "scale"
    UNIQUE(date, habit_name)
);
CREATE INDEX idx_habits_date ON daily_habits(date);
CREATE INDEX idx_habits_name ON daily_habits(habit_name);

-- ============================================
-- COMPUTED/CACHE TABLE (optional, for performance)
-- ============================================

-- Materialized daily summary (rebuilt on demand, not source of truth)
CREATE TABLE daily_summary_cache (
    date DATE PRIMARY KEY,
    computed_at TIMESTAMP,
    summary_json JSON                -- All computed features for this day
);
```

### Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Garmin API ──► raw_garmin_responses ──► Parse ──► Time-series │
│                        (JSON blob)              tables          │
│                                                                 │
│   HabitSync API ──► raw_habitsync_responses ──► daily_habits    │
│                        (JSON blob)                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      QUERY/EXPORT TIME                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Time-series tables ──► Compute features ──► Export            │
│   + daily tables              │                                 │
│                               ▼                                 │
│                    ┌─────────────────────┐                      │
│                    │ Computed Features:  │                      │
│                    │ - HR recovery slope │                      │
│                    │ - BB drain rate     │                      │
│                    │ - Stress windows    │                      │
│                    │ - Sleep efficiency  │                      │
│                    │ - etc.              │                      │
│                    └─────────────────────┘                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Storage Estimates

| Table | Rows per day | Rows per year | Estimated size |
|-------|--------------|---------------|----------------|
| heart_rate_samples | ~96 (15 min intervals) | 35,000 | ~1 MB |
| body_battery_samples | ~96 | 35,000 | ~1 MB |
| stress_samples | ~96 | 35,000 | ~1 MB |
| hrv_samples | ~20 (overnight) | 7,300 | ~0.2 MB |
| spo2_samples | ~30 (overnight) | 11,000 | ~0.3 MB |
| steps_samples | ~96 | 35,000 | ~1 MB |
| sleep_sessions | 1 | 365 | ~0.1 MB |
| activities | ~0.5 (every other day) | 180 | ~0.1 MB |
| daily_habits | ~5 | 1,825 | ~0.1 MB |
| raw_*_responses | ~6 | 2,190 | ~10 MB |

**Total estimated storage: ~15-20 MB per year**

SQLite handles this easily. After 10 years you'd have ~200MB which is still trivial.

---

## HabitSync Setup Guide

### Habits Configuration

HabitSync allows you to create and modify habits dynamically through its UI - no pre-configuration required. Create habits as needed when you start tracking. Example habits you might create:

| Example Habit | Type | Notes |
|---------------|------|-------|
| PM Energy Slump | Yes/No (negative) | Log if brain fog occurred |
| Coffee | Counter | Log each coffee consumed |
| Alcohol | Counter | Log previous evening's drinks |
| Healthy Lunch | Yes/No | Did you eat a balanced lunch? |
| Carb-Heavy Lunch | Yes/No (negative) | Was lunch predominantly carbs? |

The Energy Tracker will dynamically discover and import whatever habits exist in HabitSync - you can add, remove, or rename habits at any time and the system will adapt.

### HabitSync Docker Compose Addition

```yaml
services:
  habitsync:
    image: ghcr.io/jofoerster/habitsync:latest
    environment:
      - BASE_URL=http://your-nas-ip:6842
      - APP_SECURITY_BASIC-AUTH-USERS_admin=$2y$10$... # bcrypt hash
    volumes:
      - /volume1/docker/habitsync/data:/data
    ports:
      - "6842:6842"
    restart: unless-stopped

  energy-tracker:
    image: energy-tracker:latest  # Built from this project
    environment:
      - DB_PATH=/data/energy_tracker.db
      - GARMIN_EMAIL=${GARMIN_EMAIL}
      - GARMIN_PASSWORD=${GARMIN_PASSWORD}
      - HABITSYNC_URL=http://habitsync:6842
      - HABITSYNC_API_KEY=${HABITSYNC_API_KEY}
      - TZ=Europe/London
    volumes:
      - /volume1/docker/energy-tracker/data:/data
    ports:
      - "8000:8000"
    depends_on:
      - habitsync
    restart: unless-stopped
```

---

## Success Criteria

1. **Data Collection:** Successfully pulling and storing data from both Garmin and HabitSync daily for 14+ consecutive days
2. **Correlation Identification:** System identifies at least one metric with |r| > 0.3 correlation to PM slump (assuming pattern exists)
3. **Actionable Insights:** Dashboard provides clear, understandable insights that could inform behaviour change
4. **Reliability:** System runs unattended on Synology for 30+ days without manual intervention
5. **User Adoption:** User logs habits in HabitSync consistently (>80% of days)
6. **Data Export:** Can export complete combined dataset in a format suitable for AI analysis (CSV with metadata)

---

## Out of Scope (v1)

- Mobile app (use HabitSync PWA for logging, web dashboard for analysis)
- Push notifications or alerts
- Multi-user support
- Automated recommendations or interventions
- Integration with other health platforms (Apple Health, Fitbit, etc.)
- Food logging / calorie tracking (too high friction)
- Glucose monitoring integration (would require CGM device)

---

## Future Considerations (v2+)

- **Predictive alerts:** "Based on last night's sleep, you have 70% chance of fog today - consider reducing caffeine"
- **Weekly email digest:** Summary of patterns and trends
- **Additional data sources:** Weather, calendar (meeting load), screen time
- **Machine learning:** More sophisticated pattern detection beyond simple correlation
- **Export:** Generate reports for discussion with healthcare provider
- **Direct AI integration:** Send exported data directly to Claude API for automated pattern analysis
- **Longitudinal health insights:** After 1+ years of data, identify seasonal patterns or long-term trends

---

## Open Questions

1. **HabitSync API stability:** Need to verify the API is stable and documented enough for reliable integration. Swagger docs are available at `/swagger-ui/index.html`.

2. **Garmin session handling:** The `garminconnect` library may require periodic re-authentication. Need to handle session expiry gracefully.

3. **Body Battery timing:** What specific times should we capture Body Battery? Proposal: 9am (morning baseline), 12pm (pre-lunch), 2pm (slump window), 6pm (end of day).

4. **Training intensity classification:** How should we classify BJJ training intensity? Proposal: Based on average HR as percentage of max HR (low: <70%, medium: 70-85%, high: >85%).

5. **Minimum data requirement:** How many days of data before showing correlations? Proposal: Show after 7 days, but flag as "preliminary" until 30 days.

---

## References

- HabitSync GitHub: https://github.com/jofoerster/habitsync
- HabitSync Demo: https://demo.habitsync.de
- garminconnect library: https://github.com/cyberjunky/python-garminconnect
- Garmin Venu 3 specs: https://www.garmin.com/en-GB/p/866097

---

## Appendix: User's Medical Context

From medical history (for context on why this matters):

- History of respiratory investigations (normal lung function)
- Gastro-oesophageal reflux (could affect sleep quality)
- Alpha-1-antitrypsin deficiency (partial, MZ genotype - shouldn't affect day-to-day energy)
- Active lifestyle including BJJ training
- Ex-smoker
- Previous vitamin D deficiency (now supplementing)

The afternoon energy slump is a new focus area not previously investigated medically. This tool aims to identify lifestyle factors that correlate with the symptom before considering further medical investigation.
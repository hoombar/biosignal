# Energy Correlation Tracker

A self-hosted analysis dashboard that correlates Garmin biometric data with lifestyle habits to identify patterns related to afternoon energy slumps and brain fog.

## Features

- **Automated Data Collection**: Daily Garmin Connect sync via cron
- **Native Habit Logging**: Log habits directly in biosignal — binary (yes/no) or counter — with edit-any-day support
- **35+ Computed Features**: Sleep quality, HRV, heart rate, body battery, stress, activity, and habit tracking
- **Statistical Analysis**: Pearson correlations, pattern detection, conditional probabilities
- **Interactive Dashboard**: 5 views (Overview, Daily, Correlations, Trends, Insights)
- **Data Export**: CSV/JSON export for external analysis
- **Self-Hosted**: Runs directly on your own infrastructure

## Quick Start

### Prerequisites

- Python 3.11+
- Garmin Connect account with a compatible device (e.g., Garmin Venu 3)

### 1. Clone and Configure

```bash
git clone <repository-url>
cd biosignal

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

### 2. Prepare and Start the Application

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8234
```

The dashboard will be available at `http://localhost:8234`

### 3. Initial Sync

Navigate to the Overview page and click "Run Manual Sync" to perform the first data sync.

## Configuration

All configuration is done via environment variables in `.env`:

```bash
# Local data paths
DB_PATH=./data/energy_tracker.db
GARMIN_TOKEN_DIR=./data/.garmin_tokens

# Garmin credentials
GARMIN_EMAIL=your@email.com
GARMIN_PASSWORD=your_password

# Optional settings
TZ=Europe/London          # Your timezone
SYNC_HOUR=6               # Daily sync time (24h format)
SYNC_MINUTE_GARMIN=0      # Garmin sync minute
SYNC_MINUTE_ENVIRONMENT=5 # Environment sync minute
ENVIRONMENT_LATITUDE=51.5074   # Optional: home latitude for environment/weather metrics
ENVIRONMENT_LONGITUDE=-0.1278  # Optional: home longitude for environment/weather metrics
DEBUG=false               # Enable debug logging
```

Environmental sync uses the configured latitude/longitude as the user's home
location. Daylight metrics are computed locally; pollen and weather metrics are
fetched from Open-Meteo.

## Habit Tracking

Habits are logged natively in biosignal — no external service required. Two types are supported:

- **Binary** habits (yes/no): toggle once per day. Example: "PM Energy Slump", "Healthy Lunch".
- **Counter** habits (0+): increment/decrement throughout the day. Example: "Coffee", "Alcohol".

Habit logs are sparse positive-only events. An absent row in the raw database
export is not an explicit zero. Analysis uses an activation window: an
explicit `tracking_start_date`, or otherwise the first positive value; dates
before activation remain missing, and archived habits stop receiving inferred
zeros on the archive date. During active tracking, an absent binary/counter
row is normalized to zero with `value_state: "inferred_zero"`; explicit zeros
remain `explicit_zero`. Use `data/daily_habits.jsonl` to preserve raw history,
or `analysis/daily_habit_matrix.jsonl` and `analysis/daily_features.jsonl` for
effective values with provenance. Sensor, sleep, and environmental nulls are
always missing and are never zero-filled.

Manage habits in **Settings → Habits**: add new ones, customise display label/emoji/color, archive ones you no longer track. Archived habits keep their history (they still appear in correlations and trends for past dates) but are hidden from daily logging.

Log habits in **Daily**: pick any date — including past days for retrospective entry — and the habits panel renders editable controls for every active habit.

### Migrating from external HabitSync

If you previously fed habit data into biosignal from a separate HabitSync instance, run the one-shot import once after upgrading:

```bash
python -m scripts.import_habitsync_history \
    --from 2025-01-01 --to 2026-04-26 \
    --binary pm_slump,healthy_lunch,carb_heavy_lunch \
    --counter coffee,alcohol
```

Set `HABITSYNC_URL` and `HABITSYNC_API_KEY` in the environment for the duration of that one command. After the import succeeds and you've spot-checked the data, the external HabitSync service is no longer needed.

## API Endpoints

### Sync
- `POST /api/sync/garmin` - Manual Garmin sync
- `POST /api/sync/environment` - Manual deterministic environment sync
- `POST /api/sync/all` - Back-compat alias for `/api/sync/garmin`
- `GET /api/sync/status` - Last sync status

### Habits
- `GET /api/habits/list` - Active habits with id, type, and display config
- `PUT /api/habits/log/{date}/{habit_id}` - Log/edit a habit value for a date
- `DELETE /api/habits/log/{date}/{habit_id}` - Clear a logged value
- `POST /api/habits` - Create a habit (`name`, `habit_type`, optional display fields)
- `PATCH /api/habits/{id}` - Update display attributes (label/emoji/color/order)
- `POST /api/habits/{id}/archive` - Archive a habit (keeps history)
- `POST /api/habits/{id}/unarchive` - Restore an archived habit

### Data
- `GET /api/raw/{type}?date=YYYY-MM-DD` - Raw time-series data
- `GET /api/daily?days=N` - Computed daily summaries
- `GET /api/habits?days=N` - Habit data
- `GET /api/activities?days=N` - Training activities

### Analysis
- `GET /api/correlations` - Correlation coefficients
- `GET /api/patterns` - Pattern detection results
- `GET /api/insights` - Plain-English insights

### Runtime
- `GET /api/health` - Service health with app `version` and DB `db_revision`
- `GET /api/config` - Runtime config (non-secret) with `app_version` and `db_revision`

### Export
- `GET /api/export?format=csv&days=N` - Export computed features
- `GET /api/export/timeseries?type=heart_rate&start=...&end=...` - Raw data export
- `GET /api/export/full` - Download a ZIP archive of all analysis data
- `GET /api/export/metadata` - Feature definitions

## Dashboard Views

### Overview
- Total days tracked, fog days, current streak
- Top 3 correlates
- Sync status and manual sync button

### Daily
- Calendar heatmap (last 90 days)
- Click days for detailed metrics
- Color-coded: green (clear), red (fog), grey (no data)

### Correlations
- Bar chart of correlation coefficients
- Detailed table with fog vs clear day averages
- Statistical significance indicators

### Trends
- Multi-metric time series charts
- Toggle metrics on/off
- 7-day rolling averages

### Insights
- AI-generated plain-English findings
- Pattern probabilities with relative risk
- Data export buttons

## Architecture

```
┌─────────────────────┐
│   Garmin Connect    │
│   (Cloud API)       │
└──────────┬──────────┘
           │
           ▼
   ┌────────────────────┐
   │  Energy Tracker    │
   │  (Uvicorn process) │
   │                    │
   │  - FastAPI backend │
   │  - SQLite database │
   │  - APScheduler     │
   │  - Native habits   │
   │  - Chart.js UI     │
   │                    │
   └────────────────────┘
```

## Data Storage

- **Database**: SQLite (file-based, easy backup)
- **Location**: `./data/energy_tracker.db`
- **Size**: ~15-20 MB per year
- **Tables**: 14 tables (raw data, time-series, daily summaries, sync logs, UI settings)

### Backup

```bash
# Backup database
cp data/energy_tracker.db data/backup_$(date +%Y%m%d).db

# Backup Garmin tokens
cp -r data/.garmin_tokens data/.garmin_tokens_backup
```

## Troubleshooting

### Garmin Authentication Failed

1. Check credentials in `.env`
2. If MFA is enabled, tokens should persist after first login
3. Check `/tmp/biosignal-uvicorn.log`
4. Tokens are stored in `./data/.garmin_tokens`

### Rate Limiting (429 Error)

Garmin limits login attempts. Wait 1 hour and ensure tokens are persisting correctly.

### No Data Appearing

1. Check sync status on Overview page
2. Manually trigger sync
3. Check logs for errors

### Database Locked Error

SQLite doesn't handle high concurrency well. The app uses write locks. If you see this:
- Reduce concurrent API calls
- Check for stuck processes

## Development

### Local Development

```bash
# Install dependencies
pip install -e .

# Run migrations (migration-only schema management)
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload
```

### Run Tests

```bash
pytest tests/ -v
```

### Create Migration

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
./scripts/check_migrations.sh
```

`./scripts/check_migrations.sh` verifies that a clean database upgraded to `head` has no model drift (`alembic check`).

### Machine-Specific Startup

See `LOCAL.md` for the direct Uvicorn command, port, log path, and local proxy
address used by this installation.

## Computed Features

The system derives 35+ features from raw data:

**Sleep** (5): hours, deep %, REM %, efficiency, score
**HRV** (3): overnight avg/min, slope
**Heart Rate** (5): resting, morning/afternoon avg, 2pm window, max
**Body Battery** (8): wakeup, 9am/12pm/2pm/6pm, drain rates, daily min
**Stress** (5): morning/afternoon avg, 2pm window, peak, high stress minutes
**Activity** (8): steps total/morning, training type/duration/intensity, hours since training
**Habits** (dynamic): pm_slump, coffee_count, beer_count, healthy_lunch, carb_heavy_lunch, + any custom habits

## Privacy & Security

- **Self-hosted**: All data stays on your infrastructure
- **No cloud**: Garmin credentials stored as environment variables, never transmitted
- **Local network**: Dashboard accessible only on your local network by default
- **Optional auth**: Can add basic auth via reverse proxy (nginx, Traefik)

## Roadmap

See [PRD.md](PRD.md) section "Future Considerations" for v2+ features:
- Predictive alerts
- Weekly email digests
- Additional data sources (weather, calendar)
- Machine learning models
- Direct AI integration

## License

MIT

## Credits

Built with:
- FastAPI
- SQLAlchemy
- Chart.js
- garminconnect library
- scipy/numpy

## Support

For issues and feature requests, see the [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for technical details.

# Energy Correlation Tracker

A self-hosted analysis dashboard that correlates Garmin biometric data with lifestyle habits to identify patterns related to afternoon energy slumps and brain fog.

## Features

- **Automated Data Collection**: Daily sync from Garmin Connect and HabitSync
- **35+ Computed Features**: Sleep quality, HRV, heart rate, body battery, stress, activity, and habit tracking
- **Statistical Analysis**: Pearson correlations, pattern detection, conditional probabilities
- **Interactive Dashboard**: 5 views (Overview, Daily, Correlations, Trends, Insights)
- **Data Export**: CSV/JSON export for external analysis
- **Self-Hosted**: Runs on your own infrastructure (Docker on Synology NAS)

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Garmin Connect account with a compatible device (e.g., Garmin Venu 3)
- HabitSync instance (optional, or set up alongside)

### 1. Clone and Configure

```bash
git clone <repository-url>
cd biosignal

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

### 2. Start the Application

```bash
docker compose up -d
```

The dashboard will be available at `http://localhost:8000`

### 3. Initial Sync

Navigate to the Overview page and click "Run Manual Sync" to perform the first data sync.

## Configuration

All configuration is done via environment variables in `.env`:

```bash
# Garmin credentials
GARMIN_EMAIL=your@email.com
GARMIN_PASSWORD=your_password

# HabitSync connection
HABITSYNC_URL=http://habitsync:6842
HABITSYNC_API_KEY=your_api_key

# Optional settings
TZ=Europe/London          # Your timezone
SYNC_HOUR=6               # Daily sync time (24h format)
DEBUG=false               # Enable debug logging
```

## HabitSync Setup

Create these habits in HabitSync:

| Habit Name | Type | Purpose |
|------------|------|---------|
| PM Energy Slump | Yes/No | Primary outcome - did brain fog occur? |
| Coffee | Counter | Track caffeine intake |
| Alcohol | Counter | Track evening drinks |
| Healthy Lunch | Yes/No | Lunch quality assessment |
| Carb-Heavy Lunch | Yes/No | High-carb meal tracking |

The system automatically discovers and imports any habits you create.

## API Endpoints

### Sync
- `POST /api/sync/garmin` - Manual Garmin sync
- `POST /api/sync/habitsync` - Manual HabitSync sync
- `POST /api/sync/all` - Full sync
- `GET /api/sync/status` - Last sync status

### Data
- `GET /api/raw/{type}?date=YYYY-MM-DD` - Raw time-series data
- `GET /api/daily?days=N` - Computed daily summaries
- `GET /api/habits?days=N` - Habit data
- `GET /api/activities?days=N` - Training activities

### Analysis
- `GET /api/correlations` - Correlation coefficients
- `GET /api/patterns` - Pattern detection results
- `GET /api/insights` - Plain-English insights

### Export
- `GET /api/export?format=csv&days=N` - Export computed features
- `GET /api/export/timeseries?type=heart_rate&start=...&end=...` - Raw data export
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
┌─────────────────────┐     ┌─────────────────────┐
│   Garmin Connect    │     │     HabitSync       │
│   (Cloud API)       │     │  (Docker container) │
└──────────┬──────────┘     └──────────┬──────────┘
           │                           │
           │    ┌────────────────────┐ │
           │    │                    │ │
           └───►│  Energy Tracker    │◄┘
                │  (Docker container)│
                │                    │
                │  - FastAPI backend │
                │  - SQLite database │
                │  - APScheduler     │
                │  - Chart.js UI     │
                │                    │
                └────────────────────┘
```

## Data Storage

- **Database**: SQLite (file-based, easy backup)
- **Location**: `./data/energy_tracker.db`
- **Size**: ~15-20 MB per year
- **Tables**: 13 tables (raw data, time-series, daily summaries, sync logs)

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
3. Check logs: `docker compose logs energy-tracker`
4. Tokens are stored in `/data/.garmin_tokens`

### Rate Limiting (429 Error)

Garmin limits login attempts. Wait 1 hour and ensure tokens are persisting correctly.

### No Data Appearing

1. Check sync status on Overview page
2. Manually trigger sync
3. Check logs for errors
4. Verify HabitSync is accessible from the container

### Database Locked Error

SQLite doesn't handle high concurrency well. The app uses write locks. If you see this:
- Reduce concurrent API calls
- Check for stuck processes

## Development

### Local Development

```bash
# Install dependencies
pip install -e .

# Run migrations
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
```

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

# Cloud Run Deployment Plan (deferred)

> **Status:** Not yet actioned. This is a parked plan to tackle later when the
> decision is made to host biosignal publicly. Captured 2026-04-27.

## Why this plan exists

Biosignal currently runs on minibot via Docker Compose. To host it publicly on
a custom domain — free at hobby scale, with a path to paid scale on the same
platform if/when paying users arrive — Google Cloud Run is the chosen target.

Why Cloud Run specifically (vs. Fly.io, AWS, Render, Hostinger, etc.):

- **Truly free at biosignal scale**: 2M req/mo + 180k vCPU-s + 360k GB-s + 5GB
  GCS + Cloud Scheduler 3 jobs covers idle + occasional sync indefinitely.
- **No platform lock-in**: data is a SQLite file in GCS; one `gcloud storage cp`
  downloads everything. Standard Docker + SQLAlchemy + Alembic stays portable.
- **Same platform scales to paid**: when free tier is exhausted, Cloud Run just
  starts billing per-request; no migration. If single-writer SQLite ever
  becomes a bottleneck, swap to Cloud SQL Postgres on the same platform.
- **Reliability**: Cloud Run is mainstream GCP, built on the open Knative
  standard so portable to any K8s if Google ever retired it.

Other paths considered and rejected at this point in time:

- **Render free tier** has no persistent disk — Garmin tokens lost on every deploy.
- **Fly.io** ended its free tier in 2024; minimum ~$2–3/mo. Same architectural
  changes as Cloud Run without the truly-free benefit.
- **AWS EC2 t4g.small** is free until 2026-12-31 then $9–15/mo cliff; AWS
  operational complexity (IAM/VPC/security groups) is real.
- **Hostinger / DigitalOcean / Hetzner VPS**: $4–6/mo, never free; "scaling" is
  buying a bigger plan.
- **Oracle Always Free**: $0 forever in theory, account-termination risk and
  ARM A1 capacity issues in practice.

## Prerequisite

The persistent scheduled-job model (`app/services/scheduler.py` running
APScheduler) is the historical blocker for serverless hosting. Replacing the
internal scheduler with Cloud Scheduler hitting an HTTP endpoint removes that
blocker. The broader on-load sync UX (banner, >2-week prompt) is a
complementary but separate change — not required for this deploy.

## Target stack

| Layer | Service | Role |
|---|---|---|
| Compute | Cloud Run | Runs Docker image; auto-scales 0→1; HTTPS + custom domain free |
| Cron | Cloud Scheduler | Triggers `/api/cron/sync-daily` and `/api/cron/backup` |
| Backups | Cloud Storage (GCS) | Hourly gzipped SQLite snapshots |
| DB | SQLite (unchanged) | Lives on container disk; restored from GCS on cold start |
| DNS | External registrar | CNAME to Cloud Run URL |

No Litestream (cron backup is sufficient at hourly RPO and removes a
maintained-elsewhere dependency). No Cloud SQL. No FUSE volume mounts.

## Code changes

Roughly 1–2 days of one-time work.

### 1. Drop APScheduler

- Delete `app/services/scheduler.py`.
- Remove scheduler hooks from `app/main.py:14-20`.
- Remove `apscheduler` from `pyproject.toml:14` and `requirements.txt`.

### 2. New cron endpoints

`app/api/cron.py` (new):

- `POST /api/cron/sync-daily` — wraps current `run_scheduled_sync()` logic
  (currently in `app/services/scheduler.py:21-81`).
- `POST /api/cron/backup` — runs SQLite online backup, gzips, uploads to GCS.
- Auth via Cloud Scheduler OIDC ID token (validated in middleware).

Register router in `app/main.py`.

### 3. Move Garmin tokens into SQLite

Today: `app/services/garmin_auth.py:49-50` writes `oauth1_token.json` and
`oauth2_token.json` under `GARMIN_TOKEN_DIR` (`app/core/config.py:20`).

Changes:

- New Alembic migration: `garmin_tokens` table (id, name, value JSON, updated_at).
- New ORM model `app/models/garmin_token.py`.
- Refactor `app/services/garmin_auth.py` to read/write tokens via the DB session
  instead of disk.
- Drop `garmin_token_dir` from `app/core/config.py:20`.

Result: tokens ride backups for free; no separate token-storage backend needed.

### 4. Backup/restore service

`app/services/backup.py` (new, ~50 lines):

- `backup_to_gcs(db_path, bucket, max_versions)` — uses
  `sqlite3.Connection.backup()` (online, safe with concurrent reads/writes) to
  produce a snapshot, gzip, upload to `gs://<bucket>/backups/<timestamp>.sqlite.gz`.
- `restore_from_gcs(db_path, bucket)` — list bucket, download latest, gunzip
  to `db_path` if no local DB exists.

Wire restore into `entrypoint.sh:5-10`: after `/data` is created, before
`alembic upgrade head`, run a `python -m app.services.backup --restore-if-missing`
step. Skip if `BACKUP_BUCKET` env var is unset (so local Compose still works).

Auth via Cloud Run's default service account; no key files to manage.

### 5. Cloud Run config

`service.yaml` (new, Knative-style):

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: biosignal
spec:
  template:
    spec:
      containerConcurrency: 80
      timeoutSeconds: 3600
      containers:
      - image: <artifact-registry>/biosignal:<sha>
        resources:
          limits:
            cpu: "1"
            memory: 512Mi
        env:
        - name: GARMIN_EMAIL
          valueFrom: { secretKeyRef: { name: garmin-email, key: latest } }
        # ... HABITSYNC_*, BACKUP_BUCKET, TZ, etc.
  traffic:
  - percent: 100
    latestRevision: true
```

Annotation `autoscaling.knative.dev/maxScale: "1"` is **required** because
SQLite is single-writer.

### 6. Deploy pipeline

Either `cloudbuild.yaml` or a GitHub Action: build image → push to Artifact
Registry → `gcloud run services replace service.yaml`.

Custom domain via Cloud Run domain mappings, or Cloudflare proxy + CNAME.

## Verification

1. **Local**: `docker compose up` still works with `BACKUP_BUCKET` unset
   (backup endpoint is a no-op). Run existing `pytest tests/ -v`.
2. **Token migration**: run alembic upgrade against a copy of the prod SQLite
   DB, confirm tokens populate, app reads them, Garmin auth still works.
3. **Backup round-trip locally**: use the `fake-gcs-server` Docker image →
   call `/api/cron/backup` → wipe DB → start container → verify restore
   happens and DB matches.
4. **Staging Cloud Run deploy**: deploy to a staging service, run a manual
   `/api/cron/sync-daily` via authenticated `gcloud run services proxy`,
   confirm sync log shows success and `/api/health` returns expected
   `db_revision`.
5. **End-to-end**: trigger Cloud Scheduler manually for both crons; confirm
   daily sync succeeds and a backup blob appears in GCS.
6. **Cold-start measurement**: kill the running instance, hit the URL, time
   the first response. Should be 2–5 s. If unacceptable in practice, set
   `min_instances: 1`.
7. **Custom domain**: configure mapping, verify HTTPS via
   `curl -sS https://<domain>/api/health`.

Per `AGENTS.md`: write reproducer tests first for the migration/refactor work,
keep commits small and scoped, run `./scripts/check_migrations.sh` for the
new migration.

## Known risks

- **Cold starts**: `max_instances: 1` + scale-to-zero means an idle container
  shuts down after ~15 min; next request takes 2–5 s (Python warmup + SQLite
  restore-if-missing). Acceptable for biosignal's traffic profile. Mitigation:
  `min_instances: 1` (~$5/mo) for always-warm.
- **Single-writer SQLite**: `max_instances: 1` is a hard requirement. Caps
  horizontal scale. The day this becomes a problem is the day to move to
  Cloud SQL Postgres anyway (~1 day: DB URL change + alembic + `pgloader`).
- **Google deprecating services**: low risk for Cloud Run (mainstream,
  Knative-portable), but Google did kill Cloud IoT Core (2023). Cron backup
  to vanilla GCS keeps exit cost to a 1–2-day migration, not a rewrite.

## Migration & exit cost

- **Free tier exhaustion**: egress is the first thing to bite (1 GB/mo free,
  $0.12/GB after). At 100 GB/mo that's $12/mo. Compute remains nearly free at
  biosignal scale.
- **Migrate out**: `gcloud storage cp gs://<bucket>/backups/<latest>.sqlite.gz`
  → restore on Fly/AWS/anywhere. ~10 min user-visible downtime with planned
  maintenance window, near-zero with a brief dual-write phase.
- **Migrate to Postgres later**: change connection string at
  `app/core/database.py:13` (`sqlite+aiosqlite` → `postgresql+asyncpg`),
  Alembic upgrade, `pgloader` from SQLite. ~1 day.

## Out of scope (deliberately deferred)

- TokenStore / SyncTrigger interfaces — don't introduce preemptively;
  current change is small enough that adding them later is also small.
- Repository / data-store abstraction — SQLAlchemy already abstracts the DB.
- Multi-region, multi-instance, horizontal scale — single instance handles
  biosignal's expected load comfortably.
- HabitSync absorption — complementary initiative tracked elsewhere.
- On-load sync UX — Cloud Scheduler covers the daily case; banner/prompt UX is
  a separate concern.

## Files this plan will touch

- `app/main.py` (remove scheduler hooks, register cron router)
- `app/services/scheduler.py` (delete)
- `app/services/garmin_auth.py` (token storage refactor)
- `app/core/config.py` (drop `garmin_token_dir`)
- `app/api/cron.py` (new)
- `app/services/backup.py` (new)
- `app/models/garmin_token.py` (new)
- `migrations/versions/<new>_garmin_tokens.py` (new)
- `entrypoint.sh` (add restore step)
- `Dockerfile` (no functional change; ensure `google-cloud-storage` installs)
- `pyproject.toml` (drop apscheduler, add google-cloud-storage)
- `requirements.txt` (same)
- `service.yaml` (new)
- `cloudbuild.yaml` or `.github/workflows/deploy.yml` (new)

# Agent Working Agreement (Cross-Tool)

This file is the canonical instruction set for all coding agents in this repo
(Codex, Claude, Gemini, and others).

## Objective

Build and maintain biosignal safely and predictably:
- preserve user data
- avoid schema drift
- keep behavior verified by tests
- ship in small, reviewable commits

## Non-Negotiables

1. Tests first for behavior changes.
- New feature: write a failing test first.
- Bug fix: write a reproducer test first.

2. Database schema changes are migration-only.
- Use Alembic migrations.
- Do not introduce runtime schema mutation paths.

3. Never claim "fixed" without evidence.
- Provide what was tested and the result.
- Prefer automated tests over manual checks.

4. Keep secrets out of code and logs.
- No hardcoded credentials, API keys, or tokens.
- Redact sensitive values in examples and outputs.

5. Commit often, with meaningful commits.
- Commit at each coherent, green checkpoint.
- Messages must describe intent and scope, not "misc" or "wip".
- Split unrelated changes into separate commits.

6. Avoid destructive operations.
- Do not run destructive git/file commands unless explicitly requested.

## Required Workflow

1. Understand context.
- Read relevant files first.
- Confirm existing patterns before editing.

2. Define expected behavior with tests.
- Add or update focused tests that fail first.

3. Implement minimal correct change.
- Keep handlers thin.
- Put business logic in services.

4. Verify.
- Run targeted tests for changed area.
- Run broader test suite when risk warrants it.
- For migration changes, run migration checks on a clean DB.

5. Commit.
- Make a small logical commit once tests pass.
- If multiple concerns were changed, split into multiple commits.

## Commit Policy

Use concise, meaningful commit messages. Examples:
- `fix(sync): use timezone-safe backfill date boundaries`
- `feat(db): add migration for habit display config`
- `test(sync): cover app-timezone yesterday behavior`
- `docs(agents): clarify commit and verification rules`

Preferred commit shape:
- one concern per commit
- code + tests together when possible
- no unrelated formatting churn in functional commits

## Project Guardrails

Architecture:
- `app/api` for HTTP handlers
- `app/services` for business logic
- `app/models` for ORM models
- `app/schemas` for API schemas
- `migrations` for Alembic revisions
- `tests` for test coverage

Deployment/data safety:
- Container startup should run `alembic upgrade head`.
- Production deploys should use pinned image tags, not implicit floating behavior.
- Persistent DB data must remain on mounted host storage.

Timezone/date safety:
- Use configured app timezone for "today/yesterday" logic.
- Avoid UTC date truncation bugs in frontend date formatting.

## Commands Reference

Core:
```bash
pytest tests/ -v
```

Local development:
```bash
# From the repository root; use the local virtual environment, not Docker.
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload
```

The local server is available at `http://localhost:8000`. Check
`http://localhost:8000/api/health` before investigating the Docker deployment;
the Compose service uses the separate host port `8234`.

Migration safety:
```bash
alembic upgrade head
alembic revision --autogenerate -m "description"
./scripts/check_migrations.sh
```

Docker deploy (pinned tag):
```bash
docker compose pull
docker compose up -d
```

## Definition of Done

Before considering work complete:
- Behavior is covered by automated tests.
- Relevant tests pass locally.
- Migration checks pass for schema changes.
- Risky paths (dates/timezones, sync flows, persistence) were validated.
- Changes are split into meaningful commits.
- User-facing notes include what changed and how it was verified.

## Extended Playbooks

Detailed guidance lives in:
- `docs/testing-playbook.md`
- `docs/db-migration-playbook.md`
- `docs/integration-debug-playbook.md`
- `docs/ui-smoke-playbook.md`
- `LESSONS_LEARNED.md`

If any playbook conflicts with this file, follow this file.

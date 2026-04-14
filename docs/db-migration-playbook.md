# DB Migration Playbook

## Rules

- Schema changes must go through Alembic.
- Do not rely on runtime `create_all` style schema creation for app behavior.
- Keep migrations forward-safe and idempotent where practical.

## Workflow

1. Update model/schema definitions.
2. Generate migration:
```bash
alembic revision --autogenerate -m "describe change"
```
3. Review migration manually.
4. Apply migration:
```bash
alembic upgrade head
```
5. Validate clean-DB drift:
```bash
./scripts/check_migrations.sh
```
6. Add/adjust tests for changed behavior.

## Production Safety

- Preserve existing data on persistent volumes.
- Ensure deploy path runs `alembic upgrade head` on startup.
- Prefer additive migrations; be cautious with destructive operations.

## Commit Guidance

Split commits when needed:
- migration and model change
- behavior changes
- tests

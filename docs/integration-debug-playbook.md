# Integration Debug Playbook

## Scope

The single remaining external integration: **Garmin Connect**. Habits are
logged natively (see `app/api/habits.py`) and have no external moving parts.

## Debug Sequence

1. Reproduce with explicit date and endpoint.
2. Inspect logs and API responses.
3. Confirm parsed payload shape before DB writes.
4. Verify stored rows directly in DB.
5. Add regression test for the found issue.

## Garmin Checks

- Token validity and token directory persistence.
- Rate limiting handling and retries.
- Day-specific data availability differences by endpoint.

## Data Verification

Use DB truth to confirm outcomes:
- raw response tables
- parsed sample tables
- sync log status and timestamps

## Commit Guidance

Keep debug tooling/logging changes separate from functional fixes when practical.

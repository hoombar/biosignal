# UI Smoke Playbook

## Purpose

Catch high-impact regressions quickly in dashboard flows.

## Core Checks

- Overview loads without console errors.
- Manual sync starts and reports status.
- Backfill date picker boundaries are correct.
- Backfill request uses correct start/end dates.
- Daily/trends views render with expected data shape.

## Date/Timezone Checks

- Verify "yesterday" is based on app/local day semantics, not UTC truncation.
- Avoid `toISOString().split('T')[0]` for local-date intent.

## API Contract Checks

- UI request payloads match server expectations.
- Error responses render user-friendly messages.

## Commit Guidance

For UI behavior changes, include:
- at least one automated test where possible
- brief manual smoke evidence in final summary

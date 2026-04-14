# Testing Playbook

## Purpose

Keep behavior changes safe and reproducible.

## Standard Pattern

1. Write failing test.
2. Implement minimal change.
3. Re-run test until green.
4. Run nearby related tests.
5. Commit code + tests together.

## What to Test

- New endpoint behavior: status code + response body shape + edge cases.
- Bug fixes: direct regression test covering the failure mode.
- Data transforms: deterministic input/output assertions.
- Timezone/date logic: explicit date expectations.

## Command Patterns

Run focused tests first:
```bash
pytest tests/test_api_sync.py -v
```

Run broader suite before finalizing risky changes:
```bash
pytest tests/ -v
```

## Quality Bar

A test is good when it:
- fails for the right reason before the fix
- passes after the fix
- is deterministic
- is easy to read and maintain

## Commit Guidance

Commit after a coherent tested checkpoint. Avoid batching unrelated test changes.

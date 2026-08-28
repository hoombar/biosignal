# Full Data Export

Settings provides **Export all data**, which downloads a versioned ZIP archive
for analysis. It is not currently a restore or import package.

## Archive layout

- `manifest.json` describes the format, date range, record counts, timestamp policy, and privacy exclusions.
- `README.md` summarizes the archive for tools that inspect it without a UI.
- `data/*.jsonl` contains normalized persisted datasets, one JSON object per line.
- `analysis/daily_features.jsonl` contains computed daily features for the complete observed date range.
- `analysis/feature_metadata.json` describes daily feature fields and units.

Dates use `YYYY-MM-DD`. Naive database timestamps are treated as UTC and are
written with a `Z` suffix. JSON values remain structured JSON rather than being
converted to strings.

## Privacy scope

The archive includes normalized Garmin measurements, sleep and activity data,

The archive contains sensitive personal and health information. Treat it as
private when uploading it to an LLM or sharing it with another service.

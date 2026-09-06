# Biosignal Roadmap

This is the canonical backlog for future Biosignal features. Add new feature
ideas and status updates here rather than maintaining a separate backlog in
the Obsidian vault.

Items below were migrated from the vault backlog on 2026-08-23. They are
product direction, not commitments or a delivery schedule. The migration was
reconciled against the vault snapshot and retro notes on 2026-09-03: weather
completion, daily layout persistence, and impromptu substitutions were
restored, and context range editing was recorded as done.

## Analysis And Data Quality

- [ ] Make context-aware baselines consistent across correlations, snapshots,
  notable days, and future anomaly detection. Preserve tests for excluded
  travel, illness, and conference days.
- [ ] Tune correlation discovery with an explicit metric taxonomy or relevance
  score covering novelty, sample size, domain distance, lag direction, and
  user feedback.
- [ ] Add feedback for surfaced correlation suggestions: interesting,
  obvious, not useful, or hidden. Retain the underlying correlations.
- [ ] Model sustained environmental exposure, including multi-day pollen and
  heat windows, rather than only point-in-time highs. Original driver
  (2026-07-02): sustained high pollen across 80+ hours, or heat holding
  around 28 C for five days with nights not cooling down, signals
  differently than brief spikes.
- [ ] Add forecasts and proactive insights after sync gaps, weather, context
  baselines, and signal relevance are reliable.

## Environment And Sync

- [ ] Add a local sensor source abstraction, starting with bedroom temperature
  and humidity from Home Assistant. Attribute readings to sleep windows when
  useful while retaining general observations.
- [ ] Add on-load catch-up sync for small recent Garmin and environment gaps,
  with a clear banner or automatic yesterday sync. Prompt before large gaps.

### Done

- [x] Complete weather metric coverage: surface pressure (avg/min/max) and a
  WMO weather condition code mode now sync from Open-Meteo, surface in the
  Daily weather card, and appear in export metadata. No migration was needed
  since environmental metrics are stored as metric-key rows (completed
  2026-09-06).

## Daily View

### Done

- [x] Persist expanded/collapsed preferences for Daily metric detail sections
  so the page reopens the way the user left it, while keeping cards collapsed
  by default with summary values for scannability. Implemented via
  localStorage keyed per card; covered by JS tests (completed 2026-09-06).

## Context And Activity

- [ ] Improve Daily activity sections for general activity, walking,
  swimming, and formal training. Keep inferred walks separate from formal
  workouts and surface the most useful Garmin metrics for each section.
- [ ] Add a review loop for inferred walks so they can be confirmed,
  dismissed, or retained as unconfirmed signals before analysis.
- [ ] Support activity-attributed observations with an explicit reviewed state
  so reviewed absence is distinct from missing data.
- [ ] Review the data model for strength and mobility exercises that do not fit
  the current activity or habit model, such as dead bugs.

### Done

- [x] Context range editing: editing an existing context event prefills the
  saved start/end dates rather than the viewed day and submits through the
  PATCH endpoint. Covered by API and UI regression tests (completed
  2026-08-15).

## Gym Workflow

Items below were captured in braindumps on 2026-06-30, 2026-07-02,
2026-07-14, and 2026-07-16 (vault daily notes; consolidated snapshot in the
vault's `Machine/AI Workflows/Biosignal/biosignal-upcoming-features.md`) and
implemented in September 2026.

### Done

- [x] Auto-finish a gym session when all activities are complete and all
  effort levels are filled in (pre-existing; covered by
  `tests/test_api_gym.py` auto-finish tests).
- [x] Preserve full detail for impromptu/ad hoc exercises: sets, reps,
  weight, and notes regardless of exercise type. Original example: kettlebell
  mason twist 3x10 @ 12 kg added mid-session. Mobility-typed entries now
  accept weight and notes server-side, and the add/adjust panels expose
  weight, unit, and notes for every type.
- [x] Support impromptu substitutions inside a session (e.g. laid-back leg
  press replacing an out-of-order leg press) without losing planned-session
  context. Cards show "Instead of ..." for the planned exercise; the
  substitute form hides after finish. Substitution API predated this work.
- [x] Retry failed activity saves in the background with a durable
  unsaved-state warning. Transient failures keep the optimistic edit locally,
  retry every 5 s while the page is open, mark the activity "Unsaved", show a
  session-level banner, and warn on navigation; non-transient failures still
  reload from the server.
- [x] Offer to update the future template when an activity's weight or
  sets/reps change, not only on completion. The in-session summary reflects
  the change immediately.
- [x] Allow jumping to the previous gym session in one click via a
  "Previous session" button backed by `GET /api/gym/sessions/previous`,
  showing that session's weights and effort ratings.
- [x] Show previous performance and effort for an activity only after the
  current activity is completed ("Last time (date): ... felt ..."), so it
  cannot bias the current rating.
- [x] Reframe post-finish cancellation as "Discard session" with confirm copy
  stating the permanent deletion; pre-finish stays "Cancel session".

## Open Design Questions

- [ ] Decide whether weather belongs in daily summaries, hourly samples, or
  both.
- [ ] Decide whether bedroom temperature belongs in sleep-window summaries,
  full time-series samples, or both.
- [ ] Decide whether context exclusions apply to all correlations, only
  baseline/anomaly features, or are selectable in the UI.
- [ ] Decide whether inferred walks should become context events, observations,
  hidden habits, or a separate reviewable signal type.
- [ ] Decide whether correlation feedback is global per metric pair, per
  target, or per surfaced snapshot instance.
- [ ] Decide how sustained exposure windows should be represented: rolling
  windows, daily aggregates, event-like context ranges, or all three.
- [ ] Decide whether finished gym sessions should become read-only (toggles,
  ratings, adjust fields, and substitutions are currently still editable
  after finishing).

## Delivery Rules

- Add a reproducer test before behavior changes.
- Use Alembic migrations for schema changes; never mutate the schema at
  runtime.
- Run focused tests and the relevant broader suite before marking an item
  complete.
- For date and time features, test app-timezone boundaries near midnight and
  DST changes.

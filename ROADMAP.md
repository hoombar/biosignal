# Biosignal Roadmap

This is the canonical backlog for future Biosignal features. Add new feature
ideas and status updates here rather than maintaining a separate backlog in
the Obsidian vault.

Items below were migrated from the vault backlog on 2026-08-23. They are
product direction, not commitments or a delivery schedule.

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
  heat windows, rather than only point-in-time highs.
- [ ] Add forecasts and proactive insights after sync gaps, weather, context
  baselines, and signal relevance are reliable.

## Environment And Sync

- [ ] Add a local sensor source abstraction, starting with bedroom temperature
  and humidity from Home Assistant. Attribute readings to sleep windows when
  useful while retaining general observations.
- [ ] Add on-load catch-up sync for small recent Garmin and environment gaps,
  with a clear banner or automatic yesterday sync. Prompt before large gaps.

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

## Gym Workflow

- [ ] Preserve ad hoc exercise details such as kettlebell mason twists with
  sets, reps, and weight.
- [ ] Retry failed activity saves in the background and show a durable
  unsaved-state warning.
- [ ] Auto-finish a gym session when all activities and required effort levels
  are complete.
- [ ] Update the in-session summary immediately when exercise weight changes,
  and offer to update the future template.
- [ ] Allow jumping to the previous gym session without choosing a date
  manually.
- [ ] Show previous performance or effort annotations after completing the
  current activity, without biasing the current rating.
- [ ] Reframe post-finish cancellation as "discard session" so the destructive
  intent is clearer.

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

## Delivery Rules

- Add a reproducer test before behavior changes.
- Use Alembic migrations for schema changes; never mutate the schema at
  runtime.
- Run focused tests and the relevant broader suite before marking an item
  complete.
- For date and time features, test app-timezone boundaries near midnight and
  DST changes.

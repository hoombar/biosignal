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

Items below were captured in braindumps on 2026-06-30, 2026-07-02,
2026-07-14, and 2026-07-16 (vault daily notes; consolidated snapshot in the
vault's `Machine/AI Workflows/Biosignal/biosignal-upcoming-features.md`).

### Done

- [x] Auto-finish a gym session when all activities are complete and all
  effort levels are filled in.
  - Intent: ticking the last activity should finish the session without an
    explicit finish tap (2026-07-14).
  - Current: implemented server-side and mirrored in the UI; covered by
    `tests/test_api_gym.py` auto-finish tests.

### Open

- [ ] Preserve full detail for impromptu/ad hoc exercises: sets, reps,
  weight, and notes regardless of exercise type. Original example: kettlebell
  mason twist 3x10 @ 12 kg added mid-session (2026-07-02).
  - Current: custom activities can be added, but mobility-typed entries
    cannot record weight and their notes are dropped; the add panel has no
    notes field.
  - Done when: any custom exercise faithfully captures every detail the user
    enters, including weight and notes.

- [ ] Support impromptu substitutions inside a session (e.g. laid-back leg
  press replacing an out-of-order leg press) without losing planned-session
  context (2026-07-02).
  - Current: substitution API endpoint exists and is tested; UI controls
    were deliberately removed, so it is API-only.
  - Done when: swaps are possible from the session UI while retaining the
    planned activity for comparison.

- [ ] Retry failed activity saves in the background with a durable
  unsaved-state warning (2026-07-14).
  - Intent: a save failed while the app appeared online; the transient
    top-of-page error was easy to miss. Retry quietly and only surface a
    warning if persistence truly cannot succeed.
  - Current: single synchronous retry, then error banner plus reload that
    discards unsaved input.
  - Done when: failed edits are held locally and retried in the background;
    a persistent indicator shows unsaved state until synced; navigation with
    pending edits is warned (exact retry policy decided at implementation).

- [ ] Offer to update the future template when an activity's weight (or
  sets/reps) changes, not only on completion (2026-07-14).
  - Intent: weight-change bug report plus "ask if you want to update it
    moving forwards so it actually updates the template."
  - Current: the in-session per-activity summary re-renders on save (bug
    appears fixed); the template-update offer fires only when an activity is
    marked complete.
  - Done when: value edits during a session trigger the same offer, and the
    summary reflects the change immediately (verify in browser).

- [ ] Allow jumping to the previous gym session in one click instead of
  picking a date (2026-07-16).
  - Intent: "select previous rather than a date... jump to the last training
    session to see what weights etc you did and how the effort was."
  - Current: date input only; no history or link.
  - Done when: a "previous" affordance loads the most recent earlier session,
    showing its weights and effort ratings.

- [ ] Show previous performance and effort for an activity only after the
  current activity is completed (2026-07-16).
  - Intent: "annotate the last time you did that activity with how it felt,
    but only after you completed it so it doesn't bias the current rating."
  - Current: no prior-performance display anywhere.
  - Done when: completing an activity surfaces last time's numbers and
    effort on the card; no prior performance is shown before completion.

- [ ] Reframe post-finish cancellation as "discard session" (2026-07-16).
  - Intent: "should not have a cancel session button [after you] tapped
    finish; it should probably be a discard session."
  - Current: "Cancel session" is always visible, including post-finish, and
    hard-deletes the session after confirm.
  - Done when: pre-finish Cancel stays; after finishing the destructive
    action is labeled "Discard session" with confirm copy that states the
    deletion explicitly.
  - Open sub-question: whether finished sessions should become read-only
    (toggles/ratings/adjust fields are currently still editable).

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

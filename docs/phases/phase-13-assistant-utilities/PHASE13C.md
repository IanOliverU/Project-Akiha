# Phase 13C: One-shot timers

Status: active; context review and bounded implementation preparation begun
2026-10-08 following the owner's accepted Phase 13B closure. No timer operation
is exposed yet; implementation and acceptance remain pending.

## Required context and existing boundaries

Reviewed the maintained Phase 13 plan/13A architecture record, Phase 13B closing
record and bounded review, Phase 8 action contract, codebase structure, security
and privacy references, and existing `core/utilities/contracts.py` and `clock.py`.

Use the existing ActionRequest/ActionRegistry, action service, scoped policy,
clarification/confirmation owner, EventBus, Notification Center and presentation
arbitration. Use one schedule-service owner; do not create separate scheduler,
permission, notification or voice systems. Providers may propose typed requests
but receive no scheduler/repository/executor authority.

## Authorized scope

- Create, list, inspect and cancel one-shot timers; snooze is optional.
- Use the injected UtilityClock monotonic time while running. Persist only
  bounded schedule metadata and wall-clock state needed for restart recovery;
  never persist process-local monotonic timestamps.
- Deliver elapsed timers through existing notification/chat/tray/voice policy
  and presentation arbitration. Muting, quiet hours and channel preferences
  must remain enforced.
- Prevent duplicate delivery after restart or clock changes. Define recovery
  and delivery-receipt behavior before exposing timer execution.
- Add deterministic simultaneous-timer, cancellation, shutdown, clock-change,
  restart/recovery and duplicate-delivery tests with fake clocks/repositories.

The existing utility contract reserves timers.create/list/cancel/snooze but no
inspect operation. Define inspect consistently before registry exposure; do not
invent an unvalidated provider route. The Phase 13 plan reserves migration 0015
for 13C/13D while listing its addition under 13D. Reconcile the minimal durable
timer schema with that shared reservation before creating a migration; never
add a competing schema/version or silently omit restart recovery.

## Initial work sequence

1. Specify timer identity, bounded duration/label, lifecycle, idempotency,
   cancellation race, restart/missed-expiry policy and durable receipt rules.
2. Implement framework-free timer contracts and fake-clock tests.
3. Add the single schedule service and minimal repository/migration integration
   through the existing migrator and package-data validation contract.
4. Add typed action adapters, bounded deterministic parsing and local
   clarification; preserve Phase 13B ownership/privacy guarantees.
5. Wire lifecycle/delivery to existing app and presentation boundaries and run
   focused tests. Run the full single-process gate after implementation changes.

No timer executor, migration, network request or new persistent data has been
introduced by this kickoff. No 13D+ reminder, weather, navigation expansion,
export, recurrence or unrestricted automation is included.

## Carried follow-up obligations

- FOLLOWUP-13B-SHUTDOWN: graceful shutdown with a pending clarification remains
  unproved and explicitly deferred by the owner.
- FOLLOWUP-13B-PACKAGE: packaged smoke remains explicitly deferred.
- FOLLOWUP-CLEANUP-GUARD: fix and verify the destructive WorkDir cleanup guard
  before any clean packaging. Phase activation does not waive this prerequisite.

These items remain tracked in the [13B closing review](../../audits/PHASE13B_BOUNDED_REVIEW_2026-10-08.md).
Phase 13C activation is not package/release acceptance.

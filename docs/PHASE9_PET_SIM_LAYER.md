# Phase 9: Pet Sim Layer

**Status:** Planned - gameplay and asset research pending

## Phase Goal

Add a persistent care loop that lets Akiha's condition change over time and
respond to deliberate user care without coupling pet mechanics to conversation
language or AI-provider output.

## Hard Architecture Rule

Pet state is structured, language-neutral application data.

- Hunger, attention, affection, energy, XP, level, and currency are stored as
  typed values.
- Time decay and care actions modify those values through explicit domain
  rules.
- Mood, proactive behavior, animation, and dialogue may reflect pet state.
- Dialogue, sentiment, translations, and language-specific keywords must never
  be used as the source of truth for pet-state changes.
- AI output must not directly write pet statistics.

```text
Clock / explicit care action / approved interaction event
    -> Pet domain rules
        -> Validated state transition
            -> SQLite repository and history
                -> Pet-state event
                    -> UI / mood / proactive behavior / voice reaction
```

This preserves the same mechanics whether Akiha is speaking Japanese, English,
or another language in the future.

## Mutation Boundary

`PetStateService` is the only application service allowed to apply pet-state
rules. Its mutation surface must accept typed domain inputs only:

- a clock value for elapsed-time decay
- an explicit `CareAction`
- an approved, structured `PetInteractionEvent`

The service must not expose a generic patch method or any mutation method that
accepts dialogue, prompts, translations, sentiment, or arbitrary strings. AI
providers are not given the service or pet repository as dependencies.

The repository persists validated snapshots and history but does not calculate
care rewards or decay. Mood, proactive behavior, UI, voice, and animation
consume committed pet-state events as read-only reactions.

Tests must prove that processing provider text alone cannot change pet state
and that a typed action or interaction event is required.

## Neglect And Floor Behavior

Phase 9 uses recoverable floors rather than punishment:

- Decaying statistics clamp at their defined minimum.
- Reaching the minimum may emit a structured `needs_care` transition for mood,
  UI, proactive behavior, voice, or animation consumers.
- Remaining at the floor does not create repeated history rows or repeated
  threshold events on every timer tick.
- Explicit care actions can always recover a statistic from its minimum.
- Akiha does not die, become permanently sick, run away, or reset because of
  neglect in Phase 9.

More serious long-term condition mechanics require a separate design decision
and are not an accidental consequence of clamp logic.

## Migration Sequence

Phase 8 reserves migration `0008` for assistant-action permissions and audit
history. The first Phase 9 migration is therefore `0009`. Pet-state and
pet-history tables may be introduced together in that migration when their
schema is finalized.

## Research And Asset Readiness

Phase 9 does not begin with stat bars. Before implementation, define how the
care loop should feel and how Akiha can communicate each state with the assets
that are actually available.

- Compare Tamagotchi-style maintenance, VPet-style interaction, and a gentler
  companion-care loop.
- Decide the intended pressure level for decay, attention requests, rewards,
  and recovery.
- Inventory existing idle, walk, sleep, mood, listening, and speaking assets.
- Define the minimum reaction matrix for hunger, low energy, attention,
  affection, feeding, resting, and spending time together.
- Define a fallback order for missing assets: dedicated animation, static pose,
  mood indicator plus voice, then the existing idle presentation.
- Record frame dimensions, transparency, frame rate, direction, loop behavior,
  offsets, naming, and preview requirements for future assets.

## Planned Scope

- Persistent hunger, attention or affection, and energy statistics.
- Bounded time decay, including elapsed time while the app was closed.
- Explicit care actions such as feeding, resting, and spending time together.
- XP, levels, and currency accrual from validated interactions.
- Pet status and care controls.
- Attention-seeking behavior through the existing notification policy.
- Voice and animation reactions derived from structured pet-state events.
- Settings, diagnostics, reset behavior, automated tests, and packaged smoke.

## Out Of Scope

- Parsing conversation text to infer pet statistics.
- Allowing an AI provider to mutate pet state directly.
- Punitive death, running away, sickness, or irreversible neglect.
- Shop spending, inventory, wearable cosmetics, or Live2D work.
- Expansion of Phase 8 assistant actions or operating-system automation.

## Preliminary Checklist

- [ ] Complete gameplay and asset-readiness research.
- [ ] Approve the minimum reaction and animation-fallback matrix.
- [ ] Define typed pet-state models and invariants.
- [ ] Define decay, offline elapsed-time, and clock rules.
- [ ] Add SQLite pet-state and history migrations.
- [ ] Implement repository and pet-state service boundaries.
- [ ] Add explicit care actions.
- [ ] Add XP, levels, and currency accrual.
- [ ] Add pet status and care UI.
- [ ] Integrate structured pet events with mood and proactive behavior.
- [ ] Add voice and animation reactions.
- [ ] Add settings, diagnostics, and reset behavior.
- [ ] Add automated and manual verification.

## Required Boundary Tests

- [ ] Provider response text cannot mutate pet state without a typed event.
- [ ] Care and interaction mutations reject invalid typed values.
- [ ] Decay clamps at the floor and does not duplicate floor events.
- [ ] A care action recovers a statistic from its floor.
- [ ] Voice and animation reactions originate from structured state events,
  never dialogue parsing.
- [ ] Migration `0009` applies cleanly to both fresh and existing databases
  after the Phase 8 migration.

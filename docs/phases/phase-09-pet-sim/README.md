# Phase 9: Pet Sim Layer

**Status:** In progress - corrected Phase 9J automated and packaged gates pass;
owner manual standalone approval remains

## Phase Goal

Add a persistent care loop that lets Akiha's condition change over time and
respond to deliberate user care without coupling pet mechanics to conversation
language or AI-provider output.

## Hard Architecture Rule

Pet state is structured, language-neutral application data.

- Satiety, attention, affection, energy, XP, level, and currency are stored as
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
schema is finalized. Migration `0010` adds the restart-safe reward ledger used
for cooldowns, rolling caps, and conversation-event deduplication.

## Research And Asset Readiness

Phase 9 does not begin with stat bars. Before implementation, define how the
care loop should feel and how Akiha can communicate each state with the assets
that are actually available.

- Compare Tamagotchi-style maintenance, VPet-style interaction, and a gentler
  companion-care loop.
- Decide the intended pressure level for decay, attention requests, rewards,
  and recovery.
- Inventory existing idle, walk, sleep, mood, listening, and speaking assets.
- Define the minimum reaction matrix for low satiety, low energy, attention,
  affection, feeding, resting, and spending time together.
- Define a fallback order for missing assets: dedicated animation, static pose,
  mood indicator plus voice, then the existing idle presentation.
- Record frame dimensions, transparency, frame rate, direction, loop behavior,
  offsets, naming, and preview requirements for future assets.

## Phase 9A: Gameplay And Asset Specification

Phase 9A started on 2026-08-14. Its purpose is to lock the care-loop behavior
before database, service, or UI implementation begins.

### Product Direction

Phase 9 uses one gentle companion-care profile. It borrows the readable care
loop of traditional virtual pets and the modular state, interaction, and asset
separation demonstrated by VPet, without copying a punitive maintenance model
or requiring hundreds of animations.

- Care should reward regular interaction without demanding constant attention.
- Akiha remains recoverable after any absence.
- There is no difficulty selector in Phase 9.
- Missing artwork degrades presentation, never mechanics or saved state.
- Pet status is shown in a dedicated compact care surface, not permanently
  overlaid on the desktop character.
- Daily care controls do not turn the Settings window into a gameplay screen.

Research references:

- [VPet repository and architecture](https://github.com/LorisYounger/VPet)
- [VPet English overview](https://github.com/LorisYounger/VPet/blob/main/README_en.md)
- [Official Tamagotchi manuals](https://tamagotchi-official.com/manual/)

### Canonical State Semantics

All bounded wellbeing values use `0..100`, where a higher value is healthier.
The canonical model therefore uses `satiety` rather than an ambiguous `hunger`
number whose direction would be easy to misuse.

| Value | Meaning | Initial | Gentle decay |
|---|---|---:|---:|
| `satiety` | `0` empty, `100` well fed | 80 | -1 per 45 minutes |
| `energy` | `0` exhausted, `100` rested | 80 | -1 per 60 minutes |
| `attention` | `0` needs company, `100` content | 70 | -1 per 90 minutes |
| `affection` | long-term bond, not an immediate need | 50 | no time decay |
| `xp` | validated progression total | 0 | no decay |
| `level` | derived from XP thresholds | 1 | no decay |
| `currency` | earned now, spent only in Phase 10 | 0 | no decay |

The rates are initial implementation constants, not user-facing advanced
settings. Phase 9D manual testing may tune them once, but must preserve the
gentle profile and migration compatibility.

Wellbeing thresholds are edge-triggered:

| Band | Range | Meaning |
|---|---:|---|
| Stable | 51-100 | No care request |
| Low | 26-50 | Subtle status and optional low-urgency reminder |
| Critical | 0-25 | Clear care need, still fully recoverable |

Crossing a boundary emits one structured transition. Remaining in the same
band does not repeat history or notifications. Returning above a boundary
re-arms that transition for a future crossing.

### Time And Absence Policy

- Runtime decay is computed from elapsed UTC time through an injected clock.
- The service may evaluate once per minute but applies elapsed time rather than
  assuming every timer tick arrives on schedule.
- Offline decay is capped at 12 hours per launch.
- Clock rollback produces zero elapsed decay and a diagnostic outcome.
- Startup applies one atomic catch-up transition and may propose at most one
  highest-priority care notification.
- Closing and reopening the app cannot apply the same elapsed interval twice.

### Explicit Care Actions

Phase 9 exposes three typed actions. Their exact values are intentionally easy
to understand and test:

| Care action | State effect | Presentation target |
|---|---|---|
| `feed` | `satiety +25` | eating reaction when available |
| `rest` | `energy +25` | resting/sleepy cue |
| `spend_time` | `attention +20`, `affection +1` | attentive reaction |

All values clamp at `100`. An action that changes no state produces no reward.
Care remains available at the floor; reward cooldowns must never prevent
recovery.

### Progression And Anti-Farming

- A reward-eligible care action grants 5 XP and 2 currency.
- Each care-action kind has a 30-minute reward cooldown.
- At most 12 care reward grants are allowed in a rolling 24-hour window.
- A validated completed conversation may grant 1 XP at most once per 10
  minutes, capped at 12 grants per rolling 24 hours.
- Empty, cancelled, failed, or provider-only text does not create an
  interaction reward.
- Repeated clicks, dragging, animation commands, assistant actions, and
  proactive messages do not grant progression.
- Level thresholds use cumulative triangular 25-XP steps and are finalized by
  the Phase 9E tests; currency spending remains unavailable until Phase 10.

Conversation rewards originate from a typed `conversation_completed` event
after a valid turn is persisted. They never inspect message wording, language,
sentiment, translation, or provider output.

### Attention-Seeking Policy

Pet care requests reuse the existing notification policy, quiet hours,
away-state rules, and global cooldown. They do not create a second delivery
system.

- Low-band transitions request low urgency.
- Critical-band transitions request normal urgency.
- Only the highest-priority unmet need may be surfaced after startup.
- Suppressed notifications remain suppressed; pet state never bypasses policy.
- Recovery and future re-crossing are required before the same threshold can
  request attention again.

### Runtime Reaction Priority

Pet reactions are read-only consumers of committed pet-state events. Runtime
presentation priority is:

1. Voice listening, thinking, speaking, muted, or error state.
2. Direct user manipulation such as dragging or an explicit walk/sleep action.
3. A short explicit care-action reaction.
4. A threshold-driven need cue.
5. Background activity mood and idle presentation.

A lower-priority pet reaction never interrupts voice, dragging, or a direct
user animation command.

### Current Asset Inventory

| Asset | Technical shape | Phase 9 readiness |
|---|---|---|
| `standing/000.png` | 100x100 transparent PNG | Active universal fallback |
| `walking/Akiha-Walking.png` | 800x100 strip, 8 frames at 100x100 | Active; displayed at 8 fps and flipped for left movement |
| `Akiha.gif` | 256x256, 25 frames, 80 ms/frame, 2 seconds | Feeding candidate; not wired into the manifest yet |
| `idle/000.png` | 885x1777 alpha-capable PNG | Inactive source candidate |
| `dragging/000.png` | 885x1777 alpha-capable PNG | Inactive source candidate |
| `source-chroma.png` | 885x1777 RGB source | Not runtime-ready |
| Other walking sources | 1280x1280 and 6400x256 PNGs | Retained source variants; inactive |

The current manifest supports `idle`, `walking`, `dragging`, and `sleeping`.
Idle, dragging, and sleeping currently resolve to the standing fallback. Mood
cues already provide attention, waiting, checking-in, resting, sleepy,
listening, thinking, speaking, muted, and error presentation without requiring
new sprite sets.

### Akiha Sprite Asset Contract

Phase 9 animation prototypes use the active `standing/000.png` sprite as the
canonical identity and style reference. Generated artwork is an offline asset
input only; no image-generation dependency is added to the Akiha runtime.

The current compatibility profile is:

| Property | Requirement |
|---|---|
| Runtime canvas | 100x100 pixels per frame |
| Pixel format | RGBA PNG with transparent background |
| Subject anchor | Bottom-center with a stable feet/ground line |
| Scale | One shared character scale across every frame and action |
| Padding | Consistent transparent padding; no body part touches an edge |
| Identity | Preserve silhouette, hair, face, uniform, palette, and proportions |
| Motion | One coherent action per generated sheet |
| Direction | Generate one side when mirroring is visually valid; declare otherwise |
| Delivery | Individual frames, preview GIF, manifest metadata, and QC summary |

Raw generation may use a larger working grid for better image quality, but the
accepted Phase 9 compatibility export is normalized deterministically to a
100x100 transparent frame. Frames must be aligned and scaled as one animation;
per-frame resizing is not allowed to hide generation drift.

The pet window may use a different configured width and height. Runtime
rendering remains responsible for adapting the canonical frames with preserved
aspect ratio. Assets must never be stretched to the configured window shape or
generated separately for each window size.

Reference-guided prototype production follows this offline pipeline:

```text
standing/000.png identity reference
    -> one-action multi-row generation grid
        -> chroma/background cleanup
            -> transparent frame extraction
                -> shared-scale and feet alignment
                    -> 100x100 compatibility export
                        -> visual and automated QC
                            -> owner review before manifest activation
```

Prototype output stays outside the active animation manifest until owner
approval. A prototype must be rejected or regenerated when it has identity
drift, inconsistent scale, clipped pixels, colored background residue, an
unstable ground anchor, empty frames, or incoherent motion.

[Agent Sprite Forge](https://github.com/0x0funky/agent-sprite-forge) is an
optional reference workflow for generation and local post-processing. Its
generated output is not trusted automatically and must pass the Akiha-specific
contract above before integration.

#### First Reference-Guided Prototype

`idle-v1` is a four-frame, restrained idle reaction generated from the active
standing sprite. It was provisionally approved on 2026-08-14, then superseded
after closer review found that generated poses could not guarantee exact
palette, shading, and identity fidelity. Its review bundle remains as research
history, but its generated frames are not referenced by the active manifest and
must not be used as a canonical source.

- [Animated preview](prototypes/idle-v1/animation.gif)
- [Enlarged contact sheet](prototypes/idle-v1/review-contact-sheet.png)
- [Normalized filmstrip](prototypes/idle-v1/filmstrip.png)
- [Pipeline and QC metadata](prototypes/idle-v1/pipeline-meta.json)
- [Generation prompt](prototypes/idle-v1/prompt-used.txt)

The prototype passed basic format, dimension, transparency, and output-edge
checks, demonstrating why automated image-shape checks are necessary but not
sufficient for identity approval. The active idle now reuses only the exact
`standing/000.png` image with integer-position offsets. The reconciled current
and future boundaries are recorded in
[the pet animation architecture](../../../PROJECT_AKIHA_PET_ANIMATION_ARCHITECTURE.MD).

### Minimum Reaction Matrix

| Trigger | Structured cue | Current presentation | Future preferred asset |
|---|---|---|---|
| Fed | `care.feed.completed` | attentive cue plus standing | adapted eating GIF |
| Rested | `care.rest.completed` | resting/sleepy cue plus sleeping fallback | dedicated rest loop |
| Time together | `care.spend_time.completed` | attention cue plus standing | reserved happy/attentive pose |
| Low satiety | `pet.need.satiety.low` | checking-in cue plus policy-gated line | hungry pose |
| Low energy | `pet.need.energy.low` | sleepy cue; sleeping only when otherwise idle | tired pose or loop |
| Low attention | `pet.need.attention.low` | waiting/checking-in cue | attention pose |
| Affection increased | `pet.affection.increased` | brief attention cue | reserved warm reaction |
| Level increased | `pet.level.increased` | checking-in cue | level-up reaction |

Every row uses this fallback order:

```text
dedicated animation
    -> compatible static pose
        -> procedural mood cue plus optional local voice line
            -> standing/idle presentation
```

### Future Asset Contract

New Phase 9 assets should provide:

- transparent PNG frames or a transparent filmstrip
- a stable canvas and consistent foot/ground anchor across frames
- frame dimensions, count, playback ticks, loop/one-shot behavior, scale, and
  offsets in the animation manifest
- explicit direction behavior for movement assets
- a preview image or GIF for review
- no baked-in background color
- no requirement that gameplay wait for the asset to exist

The preferred future visual-evolution canvas is 256x256. It is a separate
profile that must be adopted across compatible actions together; it must not be
mixed casually with the current 100x100 compatibility profile. The manifest
remains authoritative and the runtime must not hard-code either size.

### Phase 9A Approval Gate

Phase 9A was approved and closed by the owner on 2026-08-14. The completed
gate confirms:

- [x] The gentle pressure profile.
- [x] Positive wellbeing semantics and `satiety` naming.
- [x] The three explicit care actions.
- [x] Non-punitive neglect and the 12-hour offline cap.
- [x] Progression and anti-farming limits.
- [x] The minimum reaction and animation-fallback matrix.
- [x] The 100x100 compatibility asset contract and first animated idle.

This gate authorized Phase 9B to proceed with typed pet-state models,
invariants, and clock-independent domain rules. Additional reaction artwork
remains incremental and does not block the gameplay foundation.

## Phase 9B: Pet-State Foundation

Phase 9B was completed on 2026-08-14. It establishes a framework-free domain
package under `project_akiha.core.pet` before persistence, timers, services, or
UI are introduced.

### Implemented Contracts

- `PetWellbeing` validates `satiety`, `energy`, `attention`, and `affection` as
  exact integers in the inclusive `0..100` range.
- `PetProgression` validates nonnegative XP and currency plus a positive level;
  level-threshold derivation remains deferred to the progression module.
- `PetDecayProgress` carries unconsumed elapsed seconds independently for each
  decaying need, allowing short evaluations to accumulate deterministically.
- `PetState` owns wellbeing, progression, and decay progress as one immutable
  aggregate with the approved gentle-profile initial values.
- `CareAction` is a closed enum containing only `feed`, `rest`, and
  `spend_time`.
- `PetInteractionEvent` accepts only a UUID, a typed interaction kind, and an
  aware timestamp. It has no dialogue, prompt, translation, sentiment, or
  arbitrary payload field.
- `WellbeingBand` and `PetBandTransition` represent exact, adjacent threshold
  edges for stable, low, and critical state changes.

### Pure Decay Rules

`evaluate_elapsed_decay` accepts a validated state, a `timedelta`, an explicit
runtime/offline mode, and a typed decay policy. It never reads a clock or calls
an external service.

- Satiety decays once per 45 accumulated minutes.
- Energy decays once per 60 accumulated minutes.
- Attention decays once per 90 accumulated minutes.
- Affection and progression do not decay.
- Offline catch-up is capped at 12 hours; runtime elapsed evaluation is not
  silently capped.
- Negative elapsed time returns a bounded clock-rollback outcome and applies no
  state change.
- Values clamp at zero. Once a need reaches zero, excess elapsed progress is
  discarded so future care cannot be followed by hidden immediate decay.
- Remaining in the same wellbeing band emits no transition. Crossing multiple
  bands emits one adjacent transition per crossed edge so later consumers can
  select the highest-priority result without parsing values or dialogue.

Phase 9B does not publish application events or write SQLite. Phase 9C owns the
repository schema, atomic persistence, injected-clock orchestration, and the
sole `PetStateService` mutation boundary.

### Phase 9B Verification

- 23 focused pet-domain tests cover invariants, type rejection, threshold
  edges, partial intervals, offline capping, rollback, floors, and deterministic
  evaluation.
- The complete suite passes with 1,398 tests and 3 optional-provider skips.
- Ruff, Black verification, Python compilation, and diff checks pass.

## Phase 9C: Persistence And Pet-State Service

Phase 9C was completed on 2026-08-14. It adds the durable pet-state aggregate
without starting runtime timers or exposing care controls before their rules
are implemented.

### SQLite Migration And Repository

Migration `0009_pet_state.sql` introduces one constrained singleton
`pet_state` row and append-only `pet_state_history` records.

- SQLite checks enforce bounded wellbeing, nonnegative progression and decay
  remainders, a positive level, and nonnegative revisions.
- `SQLitePetStateRepository` creates the initial aggregate and its typed
  initialization history atomically.
- Every later write uses a compare-and-swap revision and verifies the complete
  expected previous state before committing.
- State, its elapsed-time baseline, and optional history are committed in one
  transaction. A stale writer raises `PetStateConflictError` rather than
  overwriting newer state.
- History JSON is serialized only from validated pet domain objects and is
  decoded back through the same invariants. Dialogue, provider output, file
  contents, and arbitrary payloads are not accepted.
- Partial elapsed-time progress advances the durable baseline without adding
  noisy history. Initialization and visible wellbeing changes remain
  reviewable history entries.

### Sole Service Boundary

`PetStateService` owns elapsed-time orchestration through an injected
timezone-aware clock.

- Startup loads or creates state and applies one bounded offline catch-up.
- Runtime evaluations calculate elapsed UTC time from the last committed
  baseline instead of assuming timer callbacks arrive on schedule.
- Clock rollback applies no state and does not move the durable baseline.
- In-process evaluations are serialized; a database revision conflict reloads
  current state and retries once.
- Floor evaluations may advance their timestamp but never duplicate history
  or threshold transitions.
- The public Phase 9C surface is limited to `initialize`, `snapshot`, and
  `evaluate_runtime`. It has no text, sentiment, prompt, generic patch, care,
  or progression mutation method.

Phase 9C deliberately does not wire a timer into the application runtime.
Phase 9D adds typed care actions and their recovery rules before UI or event
consumers can request pet-state mutations.

### Phase 9C Verification

- Fresh migration and Phase 8-to-Phase 9 upgrade paths are tested.
- Repository tests cover singleton creation, typed history round-trips,
  revision conflicts, state mismatch rejection, partial progress, and schema
  constraints.
- Service tests cover offline capping, runtime remainder accumulation, clock
  rollback, floor history suppression, concurrent stale-writer recovery, and
  the absence of a provider-text mutation surface.
- The complete suite passes with 1,413 tests and 3 optional-provider skips.
- Ruff, Black verification, Python compilation, and diff checks pass.

## Phase 9D: Explicit Care Actions And Recovery

Phase 9D was completed on 2026-08-14. It adds the three approved care actions
as pure domain rules and exposes them only through the typed pet-state service
boundary.

### Pure Care Rules

`apply_care_action` accepts only a validated `PetState` and `CareAction`.

- `feed` restores 25 satiety.
- `rest` restores 25 energy.
- `spend_time` restores 20 attention and 1 affection.
- Every value clamps at 100.
- Care preserves XP, level, currency, and accumulated decay progress.
- Recovery threshold transitions are calculated from structured values for
  the affected immediate need only.
- A fully capped action is a true no-op with no hidden state change.
- Every care action remains effective at the floor; neglect cannot prevent
  recovery.

The pure rule accepts no dialogue, prompt, provider response, translation,
sentiment, or arbitrary payload.

### Service And History Boundary

`PetStateService.apply_care_action` validates the typed action before loading
or creating state. Under its existing mutation lock it then:

1. Settles elapsed runtime decay at the current injected UTC clock value.
2. Applies the pure care rule to the resulting durable state.
3. Commits a compare-and-swap transition with a specific `care_feed`,
   `care_rest`, or `care_spend_time` history kind.

No-op care does not advance the revision or add history. Revision conflicts
reload current state, settle any remaining elapsed time, and retry the care
intent once so concurrent valid user actions are not silently lost.

Phase 9D does not award XP or currency. Reward eligibility, cooldowns, daily
caps, and level derivation belong to Phase 9E. It also does not yet expose care
buttons, voice commands, provider tools, or reaction events.

### Phase 9D Verification

- Pure-rule tests cover all approved effects, caps, floor recovery, threshold
  recovery, preserved progression and remainders, no-op behavior, and rejection
  of text or untyped actions.
- Service tests cover typed history, durable floor recovery, capped no-ops,
  elapsed-decay ordering, concurrent care preservation, and rejection before
  state initialization.
- The complete suite passes with 1,426 tests and 3 optional-provider skips.
- Ruff, Black verification, Python compilation, and diff checks pass.

## Phase 9E: Progression And Anti-Farming

Phase 9E was completed on 2026-08-14. It adds restart-safe XP, levels, and
currency accrual while keeping care recovery independent from reward
eligibility.

### Level And Reward Rules

Level is derived from XP and cannot be assigned independently. The cumulative
thresholds begin at 0, 25, 75, 150, and 250 XP for levels 1 through 5. Each
later level requires 25 more XP than the previous step.

- An eligible changed care action grants 5 XP and 2 currency.
- Each care kind has an independent 30-minute reward cooldown.
- Care rewards share a rolling cap of 12 grants per 24 hours.
- A typed `conversation_completed` event grants 1 XP and no currency at most
  once per 10 minutes.
- Conversation rewards have a separate rolling cap of 12 grants per 24 hours.
- A conversation event UUID can receive a reward only once, permanently.
- Fully capped care remains a no-op and grants nothing.
- Cooldowns and caps suppress only progression; they never block a valid care
  action or recovery from the floor.
- Clock rollback cannot bypass cooldowns because future-dated durable grants
  remain inside the conservative eligibility window.

### Durable Reward Ledger

Migration `0010_pet_rewards.sql` introduces `pet_reward_grants` with closed
reward kinds, constrained XP and currency amounts, optional event UUIDs only
for conversation rewards, and a unique event index.

The SQLite repository commits pet state, typed state history, and an optional
reward grant in one transaction. It mechanically rejects progression changes
without a grant and verifies that XP, derived level, and currency exactly match
the attached grant. A duplicate event UUID rolls back the entire state and
history transaction.

The service reloads recent grants for every compare-and-swap retry, so two
concurrent care requests preserve both care effects while only the eligible
request receives progression. The ledger remains authoritative after service
or application restart.

### Typed Interaction Boundary

`PetStateService.apply_interaction_event` accepts only a validated
`PetInteractionEvent`. The event contains a UUID, the closed
`conversation_completed` kind, and an aware timestamp. It contains no message,
translation, sentiment, provider response, or arbitrary payload.

Phase 9E provides this service capability but does not yet wire chat runtime
events into it. UI and runtime integration remain deliberate later-phase work,
preventing incomplete, cancelled, failed, or provider-only turns from being
rewarded accidentally.

### Phase 9E Verification

- Pure tests cover the level curve, exact cooldown edges, separate care and
  conversation caps, per-action care cooldowns, no-op denial, duplicate event
  denial, and clock rollback behavior.
- Migration and repository tests cover fresh and existing databases, durable
  reward lookup, progression-to-grant validation, and atomic duplicate-event
  rollback.
- Service tests cover rewarded care, restart-safe cooldowns, concurrent care,
  conversation cooldowns, event deduplication, and rejection of untyped input
  before state initialization.
- The complete suite passes with 1,446 tests and 3 optional-provider skips.
- Ruff, Black verification, Python compilation, and diff checks pass.

## Phase 9F: Pet Status And Care UI

Phase 9F was completed on 2026-08-14. It exposes the existing durable pet-state
service through a dedicated compact `Akiha Care` window without moving gameplay
controls into Settings or placing permanent stat bars over the desktop pet.

### Care Surface

- The care window shows satiety, energy, attention, and affection on bounded
  `0..100` progress bars.
- Stable, low, and critical values use distinct semantic colors while retaining
  the approved Akiha interface palette.
- Level, progress within the current XP step, and accrued currency are visible.
- Currency remains display-only until the Phase 10 shop and inventory system.
- `Feed`, `Rest`, and `Spend time` emit only their corresponding closed
  `CareAction` enum values.
- The surface reports completed care, no-op state, reward cooldown, daily cap,
  and sanitized failure outcomes without exposing repository details.
- Care is available from both the pet context menu and the system tray menu.

### Runtime Boundary

The composition root now constructs `SQLitePetStateRepository` and
`PetStateService` and initializes them once during startup. This applies the
bounded offline catch-up policy before the first care-window refresh. UI reads
and care actions run through a short-lived `PetCareThread`, keeping SQLite work
off the Qt UI thread and preventing overlapping button mutations.

`PetCareWindow` owns presentation only. It has no repository reference and no
method that accepts dialogue, provider output, arbitrary action names, or raw
state values. AI providers remain structurally unable to mutate pet state.

Phase 9F deliberately does not add the one-minute runtime evaluation timer,
conversation reward wiring, proactive delivery, or voice and animation
reactions. Those integrations require structured application events and remain
the next Phase 9 work.

### Phase 9F Verification

- UI tests cover need bands, XP-step presentation, currency, summaries, typed
  care signals, busy-state overlap prevention, and invalid record rejection.
- Worker tests cover snapshot selection, typed care forwarding, and rejection
  of arbitrary care strings.
- Pet and tray tests cover both `Care` entry points.
- Source startup smoke passes with isolated fresh local data and a clean log.
- Source and packaged smoke scripts now require the pet state, history, and
  reward-ledger tables.
- The complete suite passes with 1,455 tests and 3 optional-provider skips.
- Ruff, Black verification, Python compilation, and diff checks pass.

## Phase 9G: Structured Mood And Proactive Integration

Phase 9G was completed on 2026-08-14. It connects durable pet-state outcomes to
the existing behavior pipeline without allowing dialogue, transcripts, or AI
provider output to become pet-state inputs.

### Runtime Evaluation

- A dedicated Qt worker calls `PetStateService.evaluate_runtime` once per
  minute so elapsed decay and SQLite work do not block the desktop pet UI.
- Runtime evaluation and explicit care operations cannot overlap in the
  composition root.
- Startup offline catch-up, runtime decay, and care recovery all feed the same
  typed transition bridge.
- The care window refreshes from completed runtime evaluations only while it is
  visible.

### Structured Behavior Events

- Only validated `PetBandTransition` values may publish
  `pet.need_band_changed`; there is no text-input or provider-input method.
- Every crossed edge is recorded locally, while one deterministic priority
  selector marks the strongest current cue for mood presentation.
- Critical edges outrank low edges. Downward edges outrank recovery edges, and
  a multi-edge recovery selects the final healthiest band.
- Low energy maps to sleepy, low attention maps to waiting, critical attention
  and satiety map to checking in, and recovery maps to attentive.

### Proactive Guardrails

- Only a downward edge into low or critical can request a pet check-in.
- At most one unmet need is surfaced from a batch of simultaneous transitions.
- Low needs use low urgency and critical needs use normal urgency.
- Check-ins pass through the existing proactive-enabled setting, quiet hours,
  away-state rule, and shared notification cooldown before delivery.
- Remaining in the same band produces no new edge and therefore no repeated
  pet notification. Recovery produces no notification.

### Idle Sprite Correction

Owner review rejected the generated idle prototypes because palette matching
alone could not preserve canonical line art, shading, alpha edges, facial
details, or silhouette. The runtime contract is now deliberately stricter:

- `assets/animations/akiha/standing/000.png` is the authoritative Akiha sprite.
- Every active idle pose references that exact file. No generated, recolored,
  blended, redrawn, or interpolated bitmap participates in idle rendering.
- A 16-pose manifest sequence applies only integer screen-pixel Y offsets to
  create a restrained breathing motion. The cycle lasts 1.6 seconds at the
  fresh-install 30 FPS default and does not scale or deform the source image.
- Sprite enlargement uses Qt nearest-neighbor transformation rather than
  smooth filtering, preserving the source's hard pixel edges.
- Contract tests pin the canonical image to `100x100` RGBA, 27 visible colors,
  binary transparency, and its reviewed SHA-256 fingerprint. They also verify
  that every runtime idle pose resolves to the canonical image at 100% scale.
- The generated prototype directories remain non-runtime reference material
  only and must not be restored to the active manifest.
- Visual acceptance remains pending owner review and is not implied by the
  automated contract checks.

### Experimental 60 FPS Canonical Idle

`assets/animations/manifest.idle-60fps-experiment.toml` is a separate timing
experiment. It does not replace or modify the approved default manifest.

- The timeline contains exactly 600 render ticks and declares a required 60
  FPS playback rate, yielding a nominal 10-second loop.
- Variable frame durations describe three restrained breathing cycles across
  those ticks. Every pose references the same canonical standing PNG and uses
  only integer Y offsets of `0`, `-1`, or `-2` display pixels.
- The Qt frame scheduler distributes 16 ms and 17 ms intervals so every 60
  callbacks total exactly 1,000 nominal milliseconds. A 600-tick cycle therefore
  totals 10,000 nominal milliseconds without fractional-millisecond drift.
- Test it by selecting the experimental manifest under Akiha > Pet > Animation
  manifest, setting FPS to `60`, saving, and observing the desktop pet.
- The experiment adds no image assets and remains visually unapproved until the
  owner completes a manual review.

### Phase 9G Verification

- Pure and controller tests cover low and critical urgency, recovery silence,
  typed input rejection, deterministic multi-need priority, mood mapping, and
  preservation of need mood after delivery.
- Integration coverage follows one typed low-energy edge through mood,
  behavior history, policy-gated chat delivery, and sanitized event payloads.
- Worker tests cover background elapsed-time evaluation.
- Canonical idle contract tests verify image identity, dimensions, palette,
  binary transparency, frame source paths, scale, and integer offsets.
- Ruff, Black verification, Python compilation, and diff checks pass.

## Phase 9H: Structured Voice And Animation Reactions

Phase 9H was completed on 2026-08-18. It connects committed care outcomes and
typed need edges to the existing voice and animation surfaces without parsing
dialogue, transcripts, translations, sentiment, or provider output.

### Typed Reaction Events

- A successful `PetCareEvaluation` is the only input accepted by the care
  reaction publisher. Dictionary-shaped dialogue or provider output is
  rejected.
- Every state-changing committed care result publishes a sanitized
  `pet.care_completed` event containing the closed care action, state-change
  result, reward result, and whether the action crossed a level boundary.
- A fully capped no-op produces no reaction event, speech, or progression cue.
- Spending time may additionally publish `pet.affection_increased`; any care
  reward that crosses a level boundary publishes `pet.level_increased`.
- The reaction payloads contain no dialogue, transcript, translation, file
  content, or AI-provider response.
- Care, affection, level, and need events are recorded through the existing
  local behavior-history boundary.

### Voice Reaction Policy

- Feed, Rest, Spend time, and Level-up use short built-in Japanese lines. The
  lines are original local presentation strings and are not generated by an
  AI provider.
- Explicit care speech uses the existing automatic-speech and output-enabled
  controls. A disabled or busy voice lane suppresses speech without suppressing
  the typed event or mood reaction.
- Low and critical need lines are spoken only after the existing proactive
  policy successfully delivers their suggestion. Quiet hours, away state,
  cooldowns, and the proactive-speech setting remain authoritative.
- All speech still passes through `AssistantSpeechController`, the active
  speech style renderer, and the configured local output provider, including
  GPT-SoVITS.

### Animation Fallback Policy

- Feed and Spend time resolve to attentive/checking-in presentation while the
  canonical standing idle remains the sprite fallback.
- Rest requests the existing sleeping state when Akiha is otherwise idle.
- A typed low or critical energy edge may also request sleep while idle.
- Walking, dragging, and direct user animation states are not interrupted by a
  lower-priority pet reaction. Voice state remains the highest-priority visual
  overlay and safely restores the underlying pet mood afterward.
- No new generated artwork was activated. The authoritative
  `standing/000.png` sprite and nearest-neighbor renderer remain unchanged.

### Phase 9H Verification

- Controller tests cover care, affection, and level event publication; local
  voice submission; disabled speech; and rejection of dialogue-shaped input.
- Mood and animation tests cover typed Rest reactions, low-energy sleep,
  unrelated sleepy cues, and invalid care payloads.
- Proactive speech tests cover structured pet-need delivery, while behavior
  history tests confirm sanitized reaction persistence.
- The complete suite passes with 1,472 tests and 3 optional-provider skips.
- Ruff, changed-file Black verification, and Python compilation pass. A small
  set of unrelated pre-existing files remains outside Black's preferred
  formatting and is left untouched by this module.

## Phase 9I: Settings, Diagnostics, And Reset

Phase 9I was completed on 2026-08-18. It adds a read-only pet diagnostics
surface and an explicit recovery operation without expanding the AI or
assistant-action mutation boundary.

### Pet Diagnostics

- The Pet page in Settings includes a compact Care system section with current
  wellbeing, progression, revision, elapsed-decay remainder, and evaluation
  time summaries.
- Diagnostics are built only from a validated `PetStateRecord`; dialogue-
  shaped dictionaries and arbitrary provider output are rejected.
- The diagnostics snapshot contains no chat text, transcript, translation,
  file content, provider response, credential, or private path.
- Refresh and reset work run off the Qt UI thread. Overlapping pet care,
  runtime evaluation, diagnostics, and reset operations are blocked.

### Confirmed Reset Boundary

- Reset requires an explicit Settings confirmation that states what will be
  removed and what will be preserved.
- One SQLite transaction restores the approved initial wellbeing and
  progression state, resets decay remainders and revision, clears pet-state
  history, and clears pet reward grants.
- Reset preserves chat, memories, settings, assistant-action permissions and
  audit history, Spotify credentials and preferences, and general behavior
  history.
- The repository records one new typed `reset` history entry after clearing
  the prior pet ledgers. The service refreshes its cached snapshot only after
  the transaction succeeds.
- A successful reset publishes a sanitized `pet.state_reset` event so the Care
  window, mood, diagnostics, and behavior history agree on the new state.
- No reset capability is exposed to AI providers, tool proposals, chat text,
  or assistant-action dispatch.

### Phase 9I Verification

- Repository tests cover atomic state restoration, revision reset, reward and
  pet-history clearing, and the replacement reset record.
- Service, worker, UI, mood, diagnostics, and behavior-history tests cover
  typed input, cache refresh, explicit confirmation, busy-state exclusion,
  sanitized presentation, and reset reactions.
- The complete suite passes with 1,485 tests and 3 optional-provider skips.
- Ruff, changed-file Black verification, Python compilation, and diff checks
  pass.

## Phase 9J: Final Verification And Standalone Candidate

Phase 9J produced an automated Phase 9 candidate on 2026-08-19. Owner testing
found one packaged GPT-SoVITS cold-start race, so the original candidate was
superseded by a corrected candidate. The replacement is ready for the
owner-only visual, audio, interaction, and graceful Quit pass; Phase 9 is not
formally closed until that manual result is recorded.

### Automated Source Gate

- The complete suite passes with 1,491 tests and 3 optional-provider skips.
- Ruff passes across `project_akiha` and `tests`.
- Black passes across all 452 checked Python files. Older formatting drift in
  configuration, GPT-SoVITS preparation, and provider-test code was normalized
  without changing behavior.
- Python compilation and Git whitespace checks pass.
- An isolated fresh-data source startup creates the Phase 9 database tables and
  a clean application log.

### Standalone Candidate

- Python 3.13.14 and Nuitka 4.1.3 initially produced
  `dist/nuitka-phase9-final/main.dist/Akiha.exe` through the `CleanRelease`
  workflow.
- The clean build took 6,505.709 seconds (about 1 hour 48 minutes). Its timing
  JSON and Nuitka compilation XML are stored beside the artifact.
- The Windows GUI subsystem and packaged-artifact validators pass.
- The package contains 814 files and is approximately 0.421 GiB.
- Fresh-data and seeded existing-data packaged smoke passes both create/load
  migrations through `0010`, show no visible console window, and produce logs
  without unexpected errors.
- The automated harness force-stops the tray-owned process after requesting
  `CloseMainWindow()`; this is expected and does not replace manual tray Quit.
- Nuitka reported that the Microsoft Visual C++ 2015-2022 runtime must be
  installed on a target Windows machine because its redistributable DLLs were
  not bundled by this build environment.

### Corrected Voice Candidate

The original candidate allowed a synthesis request to probe the managed
GPT-SoVITS endpoint while its models were still loading. A cold launch could
therefore report that the local API was unreachable even though the owned
process became ready roughly 30 seconds later.

- `SpeechOutputService` now waits off the Qt UI thread for an owned,
  auto-started GPT-SoVITS process to become ready, with a fixed 60-second
  minimum bound and a privacy-safe timeout failure.
- External or manually managed GPT-SoVITS endpoints retain immediate health
  behavior, and the engine manager now honors the auto-start setting.
- Privacy-safe latency diagnostics record elapsed time to the first provider
  delta and first stable speech segment without logging response text.
- Python 3.13.14 and Nuitka 4.1.3 produced the replacement at
  `dist/nuitka-phase9-final-fixed/main.dist/Akiha.exe` through the isolated
  `FastBuild` workflow.
- The first project-local cache build took 6,420.078 seconds (about 1 hour 47
  minutes). Nuitka attributed 5,820.49 seconds to compiling the generated
  `google.genai.types` module; later builds may reuse the populated cache.
- The Windows GUI subsystem and packaged-artifact validators pass. The package
  contains 814 files and is approximately 0.421 GiB.
- Fresh-data and seeded existing-data packaged smoke passes both create/load
  migrations through `0010`, show no visible console window, and produce logs
  without unexpected errors.

### Owner Manual Gate

Use `docs/phases/phase-06-packaging/MANUAL_PACKAGED_SMOKE.md` with
`dist/nuitka-phase9-final-fixed/main.dist/Akiha.exe`. In addition to the existing
voice, provider, action, memory, and shutdown checks, the report now covers
care actions, progression, diagnostics, reset preservation, canonical idle
fidelity, and walking direction.

## Planned Scope

- Persistent satiety, attention, affection, and energy statistics.
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

- [x] Complete gameplay and asset-readiness research.
- [x] Define the Akiha sprite asset contract.
- [x] Produce the first reference-guided Phase 9 animation prototype.
- [x] Review and activate the first reference-guided idle prototype.
- [x] Approve the minimum reaction and animation-fallback matrix.
- [x] Define typed pet-state models and invariants.
- [x] Define decay, offline elapsed-time, and clock-independent rules.
- [x] Add SQLite pet-state and history migrations.
- [x] Implement repository and pet-state service boundaries.
- [x] Add explicit care actions.
- [x] Add XP, levels, and currency accrual.
- [x] Add pet status and care UI.
- [x] Integrate structured pet events with mood and proactive behavior.
- [x] Add voice and animation reactions.
- [x] Add settings, diagnostics, and reset behavior.
- [x] Complete final automated source and packaged verification.
- [ ] Complete owner manual standalone verification.

## Required Boundary Tests

- [x] Provider response text cannot mutate pet state without a typed event.
- [x] Care mutations reject invalid typed values.
- [x] Interaction mutations reject invalid typed values.
- [x] Decay clamps at the floor and does not duplicate floor events.
- [x] A care action recovers a statistic from its floor.
- [x] Voice and animation reactions originate from structured state events,
  never dialogue parsing.
- [x] Migration `0009` applies cleanly to both fresh and existing databases
  after the Phase 8 migration.

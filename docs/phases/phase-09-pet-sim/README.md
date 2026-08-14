# Phase 9: Pet Sim Layer

**Status:** In progress - Phase 9A gameplay and asset specification drafted;
reaction-matrix approval pending

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
- Level thresholds are derived from XP and finalized with the Phase 9F tests;
  currency spending remains unavailable until Phase 10.

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

`attentive-v1` is a four-frame, reserved happy/attentive reaction generated
from the active standing sprite. It is a review candidate for
`care.spend_time.completed`, not an active runtime animation.

- [Animated preview](prototypes/attentive-v1/animation.gif)
- [Enlarged contact sheet](prototypes/attentive-v1/review-contact-sheet.png)
- [Normalized filmstrip](prototypes/attentive-v1/filmstrip.png)
- [Pipeline and QC metadata](prototypes/attentive-v1/pipeline-meta.json)
- [Generation prompt](prototypes/attentive-v1/prompt-used.txt)

The generated frames passed format, dimension, transparency, and output-edge
checks. Identity, motion, and character-fit approval remain deliberately
manual. The prototype is stored under Phase 9 documentation so clean release
builds do not package unapproved artwork.

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

Phase 9B may begin after the owner confirms:

- the gentle pressure profile
- positive wellbeing semantics and `satiety` naming
- the three explicit care actions
- non-punitive neglect and 12-hour offline cap
- progression limits
- the minimum reaction and fallback matrix

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
- [ ] Review the first reference-guided Phase 9 animation prototype.
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

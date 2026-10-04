# Project Akiha Pet Animation Architecture

**Status:** Architecture retained and artwork work paused on 2026-08-27;
sleep/wake and revised walk assets remain pending owner approval

## Purpose

This document records the active sprite-animation architecture and the safe
extension path for future pet reactions. It is a design constraint and roadmap,
not a second implementation competing with the existing animation provider,
pet window, mood controller, or pet-state pipeline.

The immediate goal is visual fidelity and predictable low-cost playback. Richer
animation vocabulary may be added only when approved assets exist.

The active Seifuku appearance uses an owner-approved 256 px asset profile with
a dedicated base sprite, staged sleep entry, sleeping loop, and wake sequence.
The checked-in source sheets remain untouched; deterministic preparation writes
the transparent runtime filmstrips under `akiha/seifuku-256/`.

## 1. Canonical Asset Rule

`assets/animations/akiha/seifuku-256/base.png` is the authoritative active Akiha
sprite. `standing/000.png` remains only as the legacy 100 px experiment source.

This is a hard rule:

- Do not redraw, regenerate, recolor, retouch, rescale, or reinterpret it.
- Preserve its dimensions, palette, shading, line art, proportions, silhouette,
  transparency, and pixel edges.
- Motion derived from this file may use only declared integer-position offsets,
  frame reuse, cropping of an approved filmstrip, or other explicitly reviewed
  lossless operations.
- A future artist-approved replacement must be introduced as a new reviewed
  asset decision; it must never silently overwrite the canonical source.

The current contract test fixes the canonical sprite at:

| Property | Required value |
|---|---|
| Dimensions | 256 x 256 pixels |
| Format | RGBA PNG |
| Alpha | Full alpha channel with transparent background |
| SHA-256 | `0082d8d17df60cdda252fed6437ef1e5988366d740f420eb17b95c55d9a2c00b` |

Visual fidelity takes priority over frame count. Repeating the canonical image
is preferable to inventing inaccurate artwork.

## 2. Active Runtime Architecture

Project Akiha already has the animation boundaries needed for the current
sprite system:

```text
Typed application event
    -> PetController / MoodAnimationController
        -> known AnimationState
            -> PetWindow playback clock
                -> AnimationProvider
                    -> manifest-defined AnimationFrame
                        -> SpritePetRenderer
                            -> transparent desktop window
```

### Domain state

`project_akiha/core/state/animation.py` owns the closed runtime states:

- `idle`
- `walking`
- `dragging`
- `sleeping`
- `waking`

It also owns the explicit transition rules. Provider output and dialogue text
cannot name arbitrary files or bypass those transitions.

### Application arbitration

- `PetController` owns direct idle, walk, drag, sleep, and wake transitions.
- `MoodAnimationController` maps typed mood changes to safe sleep/wake requests.
- `PetReactionController` consumes committed typed care outcomes and routes
  bounded local speech through the configured voice provider.
- `MoodController` treats listening, thinking, speaking, muted, and error as a
  temporary voice overlay. The underlying pet mood is restored afterward.

The current priority policy is behavioral rather than a generic numeric queue:

1. Voice presentation overlays the underlying mood.
2. Dragging, walking, and explicit user animation requests are not interrupted
   by lower-priority pet reactions.
3. Explicit care reactions may request an existing safe state.
4. Typed need edges may request sleep only while otherwise idle.
5. Idle remains the universal fallback.

Do not add a second priority controller until the current policy can no longer
represent an approved asset transition.

### Asset provider and manifest

`project_akiha/providers/animation/asset_provider.py` loads trusted clips from
`assets/animations/manifest.toml`. A clip may use individual frame paths or an
approved filmstrip. The provider supports:

- ticks per frame
- per-frame integer offsets
- per-frame tick durations
- source rectangles for filmstrips
- fixed scale percentages
- horizontal mirroring requested by the pet window

Missing or invalid manifests fall back to the placeholder provider instead of
crashing startup.

### Playback and rendering

`PetWindow` owns one Qt timer. `AnimationPlaybackController` owns the
state-relative frame clock and optional staged clip progression without owning
semantic pet state. Every state change resets the playback clock, preventing a
new clip from inheriting an unrelated state's frame position. Renderer FPS and
visual pose count are separate: a 60 FPS timer does not require 60 unique
images per second.

`SpritePetRenderer`:

- caches source pixmaps
- preserves aspect ratio
- uses Qt `FastTransformation` for hard pixel edges
- applies integer frame offsets after scaling
- mirrors the approved walking strip for leftward movement
- falls back safely if an image cannot be loaded

The pet window size is configurable, but assets are not regenerated for each
window size.

## 3. Active Assets And Playback

### Canonical idle

The active idle and dragging clips reference only the new 256 px base sprite.
No runtime resampling is needed to mix them with the staged 256 px sequences.

### 60 FPS experiment

`assets/animations/manifest.idle-60fps-experiment.toml` is an opt-in experiment,
not the default manifest. It provides:

- a 60 FPS playback requirement
- exactly 600 timeline ticks
- an approximately 10-second loop
- only the canonical `standing/000.png` image
- only integer offsets of `0`, `-1`, and `-2` pixels
- no generated, scaled, blended, or interpolated artwork

The experiment tests timing feel, not 600 unique drawings.

### Walking

The active walking clip uses the approved eight-frame filmstrip normalized to
256 x 256 per frame.
Movement speed and pose playback remain separate. Left movement mirrors the
same strip at render time so Akiha faces the travel direction.

### Dragging, sleeping, and waking

Dragging uses the new base sprite. Sleeping plays the 24-frame `sleep_start`
clip once, then the 12-frame `sleep_loop` indefinitely. A wake request plays
the 12-frame `wake_start` clip once before the state authority returns Akiha to
idle or the pending direct-control state.

### Inactive prototype artwork

The `idle/generated-v1` and `idle/palette-v2` files are historical experiments.
They are not referenced by the active or 60 FPS manifests and are not canonical
sources. They must not be reactivated without a fresh visual review proving
identity, palette, transparency, alignment, and loop quality.

## 4. Pet-State And Animation Boundary

Pet mechanics remain language-neutral structured state:

```text
Clock / CareAction / PetInteractionEvent
    -> PetStateService
        -> committed typed result
            -> sanitized event
                -> mood / proactive / voice / animation reaction
```

Animation reflects state; it never calculates hunger, energy, attention,
affection, XP, level, or currency.

Forbidden paths include:

```text
dialogue text -> keyword scan -> animation file
LLM output -> arbitrary animation ID
LLM output -> asset path
animation result -> pet-state mutation
```

Approved paths use a typed event, a known state or future known clip ID, and a
manifest entry validated before rendering.

## 5. Voice Boundary

Voice providers, including GPT-SoVITS and Gemini Live native audio, do not own
the renderer. They publish or cause typed voice-state transitions through the
existing application controllers.

The current sprite presentation uses mood indicators for listening, thinking,
speaking, muted, and error. Mouth shapes or expression frames are deferred until
approved artwork exists. Audio duration must not be guessed from dialogue text.

Future synchronization may consume typed playback lifecycle events such as:

```text
VoiceStarted -> approved speaking clip or visual cue
VoiceInterrupted -> stop stale speaking presentation
VoiceFinished -> restore the underlying pet state
```

## 6. Safe Extension Model

New animation capability should extend the existing provider/controller path.
Do not create parallel `core/animation`, `services/animation`, or renderer trees
unless a later renderer migration proves the current boundaries insufficient.

### New loop or reaction

The preferred addition is:

```text
approved asset
    + manifest clip
    + typed trigger
    + policy mapping
    + automated asset checks
    + owner visual approval
```

### Staged sleep / wake sequences

The provider accepts optional closed `[clips.*]` and `[sequences.*]` manifest
tables. This is infrastructure only; it does not authorize or add artwork.

The accepted staged vocabulary is:

```text
sleep = sleep_start -> sleep_loop
wake  = wake_start -> half_awake -> sitting_on_futon -> getting_up
```

Rules are mechanical and fail closed:

- named clips use closed IDs and one known semantic state
- only the final sequence clip may loop
- `sleep_loop` must loop
- `getting_up` must be finite
- both sequences remain interruptible
- every fallback names an available legacy state
- every referenced PNG remains inside the trusted appearance root
- every staged PNG must be included in the appearance approval fingerprint

`PetController` remains semantic state authority. The playback controller emits
one typed completion event for a terminal wake sequence; it cannot transition
pet state itself. Drag, voice, care, and direct user control cancel autonomous
sleep and request wake. Requests received during wake are queued as one bounded
post-wake state. If either sequence is absent, the existing instant safe wake
path remains active.

Do not generalize this into arbitrary runtime clip IDs or a second animation
controller when artwork is added.

### Multiple idle variants

Idle variation may consider typed mood, activity, pet need, and elapsed time.
Selection must be bounded and testable. Random selection should use an injected
or seedable source so tests remain deterministic.

### Future renderer replacement

Live2D, Spine, or 3D can become a future renderer/provider implementation while
pet state, behavior, permission, and AI-provider boundaries remain unchanged.
That work belongs to a separately approved visual-evolution phase and must not
be smuggled into Phase 9 maintenance.

### Phase 10 complete appearances

Phase 10 does not add cosmetic layers. It selects one complete trusted
appearance manifest through the existing animation provider and renderer:

```text
AppearanceService
    -> seifuku | dress | vermillion
        -> complete approved manifest
            -> AssetAnimationProvider
                -> SpritePetRenderer
```

`assets/animations/appearances.toml` is the closed registry. Seifuku is the safe
default. Dress and Vermillion remain unavailable until their complete sprite
sets pass automated checks and owner visual review. A stale, unavailable, or
unowned selection repairs to Seifuku without deleting shop ownership.

An available appearance also names a checked-in approval record under
`assets/animations/approvals/`. The record pins the complete manifest and each
referenced PNG by SHA-256, dimensions, and trusted relative path. Runtime
registry loading rejects any mismatch before selection. The current complete
set contract requires `idle`, `walking`, `dragging`, and `sleeping`, with every
rendered frame matching the manifest-declared profile. The active Seifuku set
uses 256 by 256 RGBA frames with full alpha transparency.

There are no equipment slots, z-order rules, wardrobe loadouts, or runtime
compositing paths. Every appearance owns its whole approved animation set, and
all existing nearest-neighbor, integer-offset, trusted-path, and safe-fallback
rules continue to apply within that manifest.

Whole-set technical review runs through the production provider and renderer:

```powershell
.venv313\Scripts\python.exe scripts\review_appearance_assets.py --appearance seifuku
```

The command writes only derived contact sheets, GIFs, frame renders, and JSON
results beneath `dist/appearance-review/`. A candidate can be reviewed with
`--manifest` while its registry entry remains unavailable. Automated success
does not replace explicit owner visual approval.

Phase 10 autonomous activity work extends the existing controller/provider path
with bounded activity IDs and manifests. The behavior controller selects an
activity from structured pet state, presence, mood, and time; providers and
dialogue never select files or continuously drive animation.

The Phase 10H runtime implements three closed activities in
`assets/animations/activities.toml`: `quiet_idle`, `wander`, and `rest`. They
map exactly to the already approved idle, walking, and sleeping animation
states. The manifest controls bounded duration, cooldown, eligibility, and
selection priority; it cannot name image paths or map an activity to dragging.

`AutonomousActivityController` owns the in-memory start, completion, and
cancellation lifecycle. The deterministic scheduler runs only from typed user
activity, mood, pet state, time, and current animation. Drag, voice, explicit
pet controls, care, and renewed user activity preempt it, while autonomous
animation requests are tagged so they cannot be mistaken for user input or
mutate mood through direct-control handlers. Lifecycle history is local and
contains no dialogue or transcript content.

## 7. Asset Acceptance Contract

Every new sprite clip must include:

- individual RGBA frames or one declared filmstrip
- stable dimensions and ground anchor
- consistent transparent padding and scale
- manifest metadata
- an enlarged contact sheet
- a GIF or video preview at intended playback speed
- automated QC output
- explicit owner approval before activation

Reject a candidate when it contains:

- palette or shading drift
- changed face, hair, uniform, proportions, or silhouette
- colored background residue
- blur, smearing, anti-aliasing, or subpixel movement
- unstable scale or feet alignment
- clipped body pixels
- empty or corrupt frames
- incoherent loop boundaries

AI-generated artwork may be used only as an isolated research prototype. It is
never trusted automatically and cannot become canonical without explicit owner
approval. The current safest production method is approved artwork plus
deterministic lossless transforms.

## 8. Verification Requirements

Automated checks must cover:

- canonical SHA-256 fingerprint
- dimensions, RGBA mode, palette, and alpha contract
- manifest syntax and existing frame paths
- known animation states
- positive timing values and bounded FPS
- per-frame offset and duration cardinality
- filmstrip geometry
- transition validity
- staged clip ordering, loop rules, completion, and interruption
- state-relative playback-clock reset
- safe missing-asset fallback
- canonical-only idle source paths
- 600-tick/10-second experimental timeline
- renderer use of hard-edge transformation
- provider or dialogue input cannot select arbitrary paths
- available appearances have exact manifest and asset approval fingerprints
- complete sets cover idle, walking, dragging, and sleeping
- review output uses the production provider and renderer

Manual checks must cover:

- no blur at configured pet-window sizes
- stable character identity and palette
- no visible clipping or ground-anchor jumps
- smooth loop boundaries
- correct left/right walking orientation
- direct walk/drag actions are not interrupted by care cues
- voice overlays restore the prior mood/presentation
- sleep/wake fallback remains understandable without dedicated artwork

Automated checks protect invariants; only the owner can grant final visual
approval.

## 9. Implementation Roadmap

### Completed in Phase 9

- Canonical sprite fingerprint and fidelity tests.
- Manifest-backed idle, walk, drag, and sleep states.
- Canonical-only integer-offset idle loop.
- Separate 60 FPS / 10-second canonical experiment.
- Hard-edge rendering and aspect-ratio preservation.
- Typed pet-state, mood, proactive, voice, and animation reaction boundaries.
- Safe fallback when dedicated reaction artwork is unavailable.

### Architecture prepared after Phase 10

- Closed `waking` state plus closed sleep/wake clip and sequence IDs.
- Backward-compatible optional staged manifest metadata.
- State-relative playback clock with finite one-shot completion.
- Single-authority staged wake and bounded post-wake requests.
- High-priority voice, care, drag, and direct-control interruption path.
- Trusted appearance validation and approval coverage for future staged assets.
- Legacy instant wake retained until both approved sequences exist.

### Deferred until approved assets exist

- Dedicated sleep-start, sleep-loop, and wake clips.
- Final staged-manifest activation and owner visual approval.
- Replacement walking cycle and its owner visual approval.
- Feeding, affection, attention, and level-up reactions.
- Speaking mouth/expression frames.
- Expanded idle variants.
- Richer animation arbitration.
- Live2D, Spine, or 3D rendering.

### Completed in Phase 10H

- Strict closed autonomous activity manifest and fail-closed loading.
- Deterministic selection and cooldown behavior without LLM involvement.
- Preemptible idle, wander, and rest lifecycles using approved clips only.
- Mechanical drag, voice, direct-control, and care priority handling.
- Privacy-safe local activity lifecycle history.

## 10. Final Principle

Akiha should gain an extensible animation vocabulary without losing her visual
identity or becoming coupled to an AI provider.

`seifuku-256/base.png` is the active source of truth. Animation brings that
approved character to life; it does not redesign her.

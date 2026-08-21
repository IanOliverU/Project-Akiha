# Project Akiha Pet Animation Architecture

**Status:** Reconciled with the Phase 9 implementation on 2026-08-19

## Purpose

This document records the active sprite-animation architecture and the safe
extension path for future pet reactions. It is a design constraint and roadmap,
not a second implementation competing with the existing animation provider,
pet window, mood controller, or pet-state pipeline.

The immediate goal is visual fidelity and predictable low-cost playback. Richer
animation vocabulary may be added only when approved assets exist.

## 1. Canonical Asset Rule

`assets/animations/akiha/standing/000.png` is the authoritative Akiha sprite.

This is a hard rule:

- Do not redraw, regenerate, recolor, retouch, rescale, or reinterpret it.
- Do not introduce AI-generated pixels into canonical runtime frames.
- Preserve its dimensions, palette, shading, line art, proportions, silhouette,
  binary transparency, and pixel edges.
- Motion derived from this file may use only declared integer-position offsets,
  frame reuse, cropping of an approved filmstrip, or other explicitly reviewed
  lossless operations.
- A future artist-approved replacement must be introduced as a new reviewed
  asset decision; it must never silently overwrite the canonical source.

The current contract test fixes the canonical sprite at:

| Property | Required value |
|---|---|
| Dimensions | 100 x 100 pixels |
| Format | RGBA PNG |
| Alpha | Binary transparent/opaque pixels |
| Opaque RGB palette | 27 colors |
| SHA-256 | `b74a30f8a198658a09478d12b98fe66cc075ab775bb7d7239b65bb5676c4cf81` |

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

`PetWindow` owns one Qt timer and a monotonic frame number. Renderer FPS and
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

The active idle clip references only `standing/000.png`. Its 16 timeline poses
reuse that exact file with restrained vertical offsets of `0`, `-1`, and `-2`
pixels. No alternate artwork or interpolated pixels are used.

At the default 30 FPS renderer rate and three ticks per pose, the active cycle
is approximately 1.6 seconds. The movement is intentionally subtle; visual
review remains authoritative.

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

The active walking clip uses the approved eight-frame 100 x 100 filmstrip.
Movement speed and pose playback remain separate. Left movement mirrors the
same strip at render time so Akiha faces the travel direction.

### Dragging and sleeping

Dragging and sleeping currently resolve to the canonical standing sprite.
Their mechanics are functional, but dedicated transition artwork is not yet
available.

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

### Start / loop / end sequences

Sleep, wake, petting, or speaking may eventually need start/loop/end clips.
Add that concept to `AnimationClip` and the existing state/controller model only
after at least one approved asset set requires it. Do not build speculative
transition machinery around missing artwork.

### Multiple idle variants

Idle variation may consider typed mood, activity, pet need, and elapsed time.
Selection must be bounded and testable. Random selection should use an injected
or seedable source so tests remain deterministic.

### Future renderer replacement

Live2D, Spine, or 3D can become a future renderer/provider implementation while
pet state, behavior, permission, and AI-provider boundaries remain unchanged.
That work belongs to a separately approved visual-evolution phase and must not
be smuggled into Phase 9 maintenance.

### Phase 10 cosmetic layers

Phase 10 extends the existing renderer with approved overlay metadata; it does
not create a replacement character or a second animation system. The typed
contract lives in `project_akiha/core/shop/models.py` and accepts only:

- normalized relative PNG paths resolved beneath the trusted cosmetic root;
- the canonical 100 x 100 canvas;
- binary alpha and nearest-neighbor presentation;
- explicit known animation states and left/right directions;
- bounded integer offsets and z-order; and
- one equipped item per `head`, `face`, `neck`, or `accessory` slot.

Unsupported states, directions, missing files, or rejected assets render no
cosmetic layer. They do not alter `standing/000.png`, delete ownership, invent an
anchor, or fall back to an arbitrary file. At least one visible cosmetic still
requires owner visual approval before Phase 10 can claim visual completion.

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
- safe missing-asset fallback
- canonical-only idle source paths
- 600-tick/10-second experimental timeline
- renderer use of hard-edge transformation
- provider or dialogue input cannot select arbitrary paths

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

### Deferred until approved assets exist

- Dedicated sleep-start, sleep-loop, and wake clips.
- Feeding, affection, attention, and level-up reactions.
- Speaking mouth/expression frames.
- Expanded idle variants.
- Generalized start/loop/end clip support.
- Richer animation arbitration.
- Live2D, Spine, or 3D rendering.

## 10. Final Principle

Akiha should gain an extensible animation vocabulary without losing her visual
identity or becoming coupled to an AI provider.

`standing/000.png` remains the source of truth. Animation brings that approved
character to life; it does not redesign her.
